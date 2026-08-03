import os
import pandas as pd
import numpy as np
from torch.utils.tensorboard import SummaryWriter
import pickle
from pathlib import Path
from tqdm import tqdm
from datetime import datetime

from discor.replay_buffer import ReplayBuffer, EnsembleBuffer
from discor.utils import RunningMeanStats
from AssettoCorsaEnv.data_loader import DataLoader

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

import time

class Agent:
    def __init__(self, env, test_env, algo, log_dir, device, num_steps=3000000,
                 batch_size=256, memory_size=1_000_000,
                 update_interval=1, start_steps=10000, log_interval=10, checkpoint_freq=0,
                 eval_interval=5000, num_eval_episodes=5, seed=0, use_offline_buffer=False, offline_buffer_size=1_000_000,
                 wandb_logger=None, save_final_buffer=False, random_steps=None,
                 checkpoint_step_offset=0, stop_episode_at_eval_interval=False,
                 evaluation_report_dir=None):

        # Environment.
        self._env = env
        self._test_env = test_env
        self.checkpoint_freq = checkpoint_freq
        self.checkpoint_step_offset = checkpoint_step_offset
        self.wandb_logger = wandb_logger
        self.save_final_buffer = save_final_buffer
        self.stop_episode_at_eval_interval = stop_episode_at_eval_interval
        self.evaluation_report_dir = evaluation_report_dir

        self._env.seed(seed)
        self._test_env.seed(2**31-1-seed)

        # Algorithm.
        self._algo = algo

        if use_offline_buffer:
            self._replay_buffer = EnsembleBuffer(memory_size=memory_size, state_shape=self._env.observation_space.shape,
                                                 action_shape=self._env.action_space.shape, gamma=self._algo.gamma, nstep=self._algo.nstep, offline_buffer_size=offline_buffer_size)
        else:
            # Replay buffer with n-step return.
            self._replay_buffer = ReplayBuffer(memory_size=memory_size, state_shape=self._env.observation_space.shape,
                                               action_shape=self._env.action_space.shape, gamma=self._algo.gamma, nstep=self._algo.nstep)

        # Directory to log.
        self._log_dir = log_dir
        self._model_dir = os.path.join(log_dir, 'model')
        self._summary_dir = os.path.join(log_dir, 'summary')
        if not os.path.exists(self._model_dir):
            os.makedirs(self._model_dir)
        if not os.path.exists(self._summary_dir):
            os.makedirs(self._summary_dir)

        self.episodes_stats = []
        self._steps = 0
        self._episodes = 0
        self._train_return = RunningMeanStats(log_interval)
        self._writer = SummaryWriter(log_dir=self._summary_dir)
        self._best_eval_score = -np.inf

        self._device = device
        self._num_steps = num_steps
        self._batch_size = batch_size
        self._update_interval = update_interval
        self._start_steps = start_steps
        # By default, preserve the original behavior: collect random actions
        # until learning starts.  Warm-start runs can set random_steps=0 to use
        # loaded policy weights immediately while still delaying updates until
        # the replay buffer has enough target-domain transitions.
        self._random_steps = start_steps if random_steps is None else random_steps
        self._log_interval = log_interval
        self._eval_interval = eval_interval
        self._num_eval_episodes = num_eval_episodes
        self._start_time = time.time()
        self._training_progress = None
        self._last_evaluated_step = None

        self.best_lap_time = np.inf
        self.best_reward = -np.inf

        logger.info(f'num_steps: {num_steps}')
        logger.info(f'batch_size: {batch_size}')
        logger.info(f'update_interval: {update_interval}')
        logger.info(f'start_steps: {start_steps}')
        logger.info(f'random_steps: {self._random_steps}')
        logger.info(f'log_interval: {log_interval}')
        logger.info(f'eval_interval: {eval_interval}')
        logger.info(f'num_eval_episodes: {num_eval_episodes}')
        logger.info(f'seed: {seed}')
        logger.info(f'gamma: {self._algo.gamma}')
        logger.info(f'nstep: {self._algo.nstep}')
        logger.info(f'memory_size: {memory_size}')

    def save(self, path, save_buffer=True):
        self._algo.save_models(path)
        if save_buffer:
            with open(os.path.join(path, 'replay_buffer.pkl'), 'wb') as f:
                pickle.dump(self._replay_buffer, f)
            logger.info("saved replay buffer to {}".format(path))
        logger.info("saved models to {}".format(path))

    def load(self, path, load_buffer=True):
        self._algo.load_models(path)
        logger.info(f"loaded model from {path}")
        if load_buffer:
            with open(path + "replay_buffer.pkl", 'rb') as f:
                self._replay_buffer = pickle.load(f)
            self._steps = self._replay_buffer._n
            logger.info(f"loaded buffer from {path}. Number of steps: {len(self._replay_buffer)}")

    def run(self):
        self._start_time = time.time()
        initial_steps = min(self._steps, self._num_steps)
        self._training_progress = tqdm(
            total=self._num_steps,
            initial=initial_steps,
            unit=" step",
            dynamic_ncols=True,
            bar_format=(
                "训练进度 | 总步数: {total_fmt} | 当前步数: {n_fmt} | "
                "训练时长: {elapsed} | {bar} {percentage:3.0f}%"
            ),
        )
        try:
            while self._steps < self._num_steps:
                self.train_episode()
                if (self._eval_interval
                        and self._steps > 0
                        and self._steps % self._eval_interval == 0
                        and self._last_evaluated_step != self._steps):
                    logger.info("Evaluating")
                    eval_records = self.evaluate()
                    self._last_evaluated_step = self._steps
                    self.write_evaluation_report(eval_records)
        finally:
            self._training_progress.close()
            self._training_progress = None
            self.save(os.path.join(self._model_dir, 'final'), save_buffer=self.save_final_buffer)

    def update_model(self):
        train_stats = None
        # Update online networks.
        if self._steps % self._update_interval == 0:
            batch = self._replay_buffer.sample(self._batch_size, self._device)
            train_stats = self._algo.update_online_networks(batch, self._writer)

        # Update target networks.
        self._algo.update_target_networks()
        return train_stats

    def train_episode(self):
        """
        Train only one episode
        """
        self._episodes += 1
        episode_return = 0.
        episode_steps = 0

        ep_start_time = time.time()
        ep_stats = {}
        train_stats = None

        try:
            done = False
            step_perf, action_perf, update_model_perf = [], [], []
            state = self._env.reset()
            step_start_time = time.perf_counter()

            while (not done) and self._steps < self._num_steps:
                start_profile = time.perf_counter()
                if self._random_steps > self._steps:
                    action = self._env.action_space.sample()
                else:
                    action, _ = self._algo.explore(state)
                action_perf.append(time.perf_counter() - start_profile)

                # The AC environment attaches this information to the control
                # packet so the in-game plugin can render a training HUD.
                set_training_progress = getattr(self._env, 'set_training_progress', None)
                if set_training_progress is not None:
                    set_training_progress(
                        total_steps=self._num_steps,
                        current_step=min(self._steps + 1, self._num_steps),
                        elapsed_seconds=time.time() - self._start_time,
                    )

                # apply actions right away without blocking
                self._env.set_actions(action)

                # update model
                start_profile = time.perf_counter()
                if self._steps >= self._start_steps:
                    train_stats = self.update_model()
                update_model_perf.append(time.perf_counter() - start_profile)

                # get observations
                next_state, reward, done, info = self._env.step(action=None)  # action is already applied
                step_perf.append(time.perf_counter() - step_start_time)
                step_start_time = time.perf_counter()

                # Set done=True only when the agent fails, ignoring done signal
                # if the agent reach time horizons.
                if (episode_steps + 1 >= self._env._max_episode_steps):
                    masked_done = False
                else:
                    masked_done = done

                milestone_boundary = (
                    self.stop_episode_at_eval_interval
                    and self._eval_interval
                    and (self._steps + 1) % self._eval_interval == 0
                )

                if info['terminated']:
                    rb_done = True
                else:
                    rb_done = False

                self._replay_buffer.append(
                    state, action, reward, next_state, masked_done,
                    episode_done=(rb_done or milestone_boundary))

                self._steps += 1
                episode_steps += 1
                episode_return += reward
                state = next_state

                if self._training_progress is not None:
                    self._training_progress.update(1)

                if self.checkpoint_freq and (self._steps % self.checkpoint_freq == 0):
                    logger.info(f"checkpointing model {self._steps} steps")
                    checkpoint_step = self._steps + self.checkpoint_step_offset
                    self.save(os.path.join(self._model_dir, "checkpoints", f"step_{checkpoint_step:08d}"), save_buffer=False)

                if milestone_boundary:
                    logger.info(f"Reached evaluation boundary at {self._steps} continuation steps")
                    break
        except TimeoutError:
            logger.exception("Agent TimeoutError")
        finally:
            env_ep_stats = self._env.close()

        # We log running mean of training rewards.
        self._train_return.append(episode_return)

        if self._episodes % self._log_interval == 0:
            self._writer.add_scalar(
                'reward/train', self._train_return.get(), self._steps)

        episode_message = (f'Episode: {self._episodes:<4}  '
                           f'Episode steps: {episode_steps:<4}  '
                           f'Return: {episode_return:<5.1f}')
        if self._training_progress is not None:
            self._training_progress.write(episode_message)
        else:
            print(episode_message)

        ep_time = time.time() - ep_start_time
        ep_stats['total_steps'] = self._steps
        ep_stats['episode'] = self._episodes
        ep_stats['ep_reward'] = episode_return
        ep_stats['ep_steps'] = episode_steps
        ep_stats.update(env_ep_stats if isinstance(env_ep_stats, dict) else {})

        if env_ep_stats["BestLap"] < self.best_lap_time:
            logger.info(f"new best lap time {env_ep_stats['BestLap']}")
            self.best_lap_time = env_ep_stats["BestLap"]
            self.save(os.path.join(self._model_dir, 'best_lap_time'), save_buffer=False)

        if env_ep_stats["ep_reward"] > self.best_reward:
            logger.info(f"new best reward {env_ep_stats['ep_reward']}")
            self.best_reward = env_ep_stats["ep_reward"]
            self.save(os.path.join(self._model_dir, 'best_reward'), save_buffer=False)

        eval_metrics = self.common_metrics()
        eval_metrics.update(ep_stats)
        if train_stats:
            eval_metrics.update(train_stats)
        eval_metrics["update_model_perf_mean"] = np.array(update_model_perf).mean()
        eval_metrics["update_model_perf_max"] = np.array(update_model_perf).max()
        eval_metrics["update_model_perf_std"] = np.array(update_model_perf).std()
        eval_metrics["step_perf_mean"] = np.array(step_perf).mean()
        eval_metrics["step_perf_max"] = np.array(step_perf).max()
        eval_metrics["step_perf_std"] = np.array(step_perf).std()
        eval_metrics["step_perf_q99"] = np.quantile(np.array(step_perf), 0.99)
        eval_metrics["step_perf_> thres"] = np.sum(np.array(step_perf) > 0.041)
        eval_metrics["action_perf_mean"] = np.array(action_perf).mean()
        eval_metrics["action_perf_max"] = np.array(action_perf).max()
        eval_metrics["action_perf_std"] = np.array(action_perf).std()
        logger.info(f"Avr step time: {eval_metrics['step_perf_mean']:.3f}s, actions: {eval_metrics['action_perf_mean']:.4f}s, update: {eval_metrics['update_model_perf_mean']:.3f}s")
        logger.info(f"Max step time: {eval_metrics['step_perf_max']:.3f}s, actions: {eval_metrics['action_perf_max']:.4f}s, update: {eval_metrics['update_model_perf_max']:.3f}s")
        logger.info(f"std step time: {eval_metrics['step_perf_std']:.3f}s, actions: {eval_metrics['action_perf_std']:.4f}s, update: {eval_metrics['update_model_perf_std']:.3f}s")
        logger.info(f"step_perf_> thres: {eval_metrics['step_perf_> thres']} / {len(step_perf)}")
        if self.wandb_logger:
            self.wandb_logger.log(eval_metrics, 'episodes')
        self.episodes_stats.append(eval_metrics)
        pd.DataFrame(self.episodes_stats).to_csv(os.path.join(self._log_dir, 'summary.csv'), index=None)
        logger.info(f'Episode done. Took {ep_time:.2f}s.  Steps per episode: {episode_steps}. Buffer size: {len(self._replay_buffer)} fps: {episode_steps/ep_time:.2f}')

    def evaluate(self):
        eval_records = []
        previous_max_laps = getattr(self._test_env, "max_laps_number", None)
        self._test_env.set_eval_mode()
        try:
            for trial in range(1, self._num_eval_episodes + 1):
                completed_lap_times = []
                termination_reason = "unknown"
                info = {}
                episode_return = 0.0
                env_ep_stats = {}
                try:
                    state = self._test_env.reset()
                    previous_lap_count = self._test_env.state["LapCount"]
                    done = False

                    while not done:
                        action, entropies = self._algo.exploit(state)
                        next_state, reward, done, info = self._test_env.step(action)
                        self._test_env.states[-1]["entropies"] = entropies.cpu().numpy().item()
                        episode_return += reward
                        state = next_state

                        current_lap_count = self._test_env.state["LapCount"]
                        if current_lap_count != previous_lap_count:
                            lap_time = self._test_env.state["iLastTime"] / 1000.0
                            if lap_time > 0:
                                completed_lap_times.append(lap_time)
                            previous_lap_count = current_lap_count

                    if len(completed_lap_times) >= self._test_env.config.eval_number_of_laps:
                        termination_reason = "target_laps_completed"
                    elif self._test_env.state.get("out_of_track"):
                        termination_reason = "out_of_track"
                    elif self._test_env.state.get("going_backwards", 0) > 0:
                        termination_reason = "going_backwards"
                    elif info.get("terminated"):
                        termination_reason = "terminated_before_lap_completion"
                    else:
                        termination_reason = "episode_ended"
                except TimeoutError:
                    logger.exception("Agent TimeoutError during evaluation trial %s", trial)
                    termination_reason = "timeout"
                finally:
                    env_ep_stats = self._test_env.close()

                record = dict(env_ep_stats if isinstance(env_ep_stats, dict) else {})
                record.update(
                    trial=trial,
                    continuation_step=self._steps,
                    total_step=self._steps + self.checkpoint_step_offset,
                    eval_completed_laps=len(completed_lap_times),
                    eval_lap_times=";".join(f"{lap_time:.3f}" for lap_time in completed_lap_times),
                    eval_best_lap=min(completed_lap_times) if completed_lap_times else 0.0,
                    termination_reason=termination_reason,
                    policy_mode="deterministic",
                    ep_reward=record.get("ep_reward", episode_return),
                )
                eval_records.append(record)
                logger.info("Evaluation trial %s complete: %s", trial, record)
        finally:
            self._test_env.max_laps_number = previous_max_laps

        eval_dir = Path(self._log_dir) / "evaluations" / f"step_{self._steps + self.checkpoint_step_offset:08d}"
        eval_dir.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(eval_records).to_csv(eval_dir / "eval_summary.csv", index=False)
        return eval_records

    def write_evaluation_report(self, eval_records):
        """Save a human-readable Markdown report for a training milestone."""
        total_step = self._steps + self.checkpoint_step_offset
        report_root = Path(self.evaluation_report_dir or self._log_dir)
        report_root.mkdir(parents=True, exist_ok=True)
        report_path = report_root / f"{total_step // 10000}万步训练效果评估.md"
        eval_dir = Path(self._log_dir) / "evaluations" / f"step_{total_step:08d}"
        checkpoint_dir = Path(self._model_dir) / "checkpoints" / f"step_{total_step:08d}"

        completed = [int(record.get("eval_completed_laps", 0) or 0) for record in eval_records]
        valid_trials = sum(value > 0 for value in completed)
        lap_times = []
        for record in eval_records:
            raw_times = str(record.get("eval_lap_times", "") or "")
            lap_times.extend(float(value) for value in raw_times.split(";") if value)

        lines = [
            f"# MX-5 Cup Silverstone GP {total_step // 10000} 万步训练效果评估",
            "",
            "## 评估概况",
            "",
            f"- 评估时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "- 车辆：`ks_mazda_mx5_cup`",
            "- 赛道：`ks_silverstone-gp`",
            "- 算法：SAC",
            f"- 累计总步数：{total_step:,}",
            f"- 本轮续训步数：{self._steps:,}",
            f"- 模型 checkpoint：`{checkpoint_dir}`",
            f"- 评估原始数据：`{eval_dir / 'eval_summary.csv'}`",
            f"- 评估方式：确定性策略，共 {len(eval_records)} 次独立 trial",
            "",
            "## 逐次评估结果",
            "",
            "| Trial | 完成圈数 | 最佳有效圈速 | Steps | Reward | 平均速度 (m/s) | 最高速度 (m/s) | 终止原因 |",
            "|---:|---:|---:|---:|---:|---:|---:|---|",
        ]

        for record in eval_records:
            best_lap = float(record.get("eval_best_lap", 0.0) or 0.0)
            best_lap_text = f"{best_lap:.3f} s" if best_lap > 0 else "DNF"
            lines.append(
                "| {trial} | {laps} | {lap} | {steps} | {reward:.1f} | {speed_mean:.2f} | {speed_max:.2f} | {reason} |".format(
                    trial=int(record.get("trial", 0) or 0),
                    laps=int(record.get("eval_completed_laps", 0) or 0),
                    lap=best_lap_text,
                    steps=int(record.get("ep_steps", 0) or 0),
                    reward=float(record.get("ep_reward", 0.0) or 0.0),
                    speed_mean=float(record.get("speed_mean", 0.0) or 0.0),
                    speed_max=float(record.get("speed_max", 0.0) or 0.0),
                    reason=record.get("termination_reason", "unknown"),
                )
            )

        lines.extend([
            "",
            "## 汇总与结论",
            "",
            f"- 有效完圈 trial：{valid_trials}/{len(eval_records)}",
            f"- 有效圈总数：{sum(completed)}",
            f"- 最佳有效圈速：{min(lap_times):.3f} s" if lap_times else "- 最佳有效圈速：DNF（本节点未产生严格有效圈）",
            f"- 平均有效圈速：{np.mean(lap_times):.3f} s" if lap_times else "- 平均有效圈速：无",
            "",
            "严格有效圈只统计本次评估进程中实际观察到 `LapCount` 跳变且 `iLastTime > 0` 的圈；不会采用 Assetto Corsa 跨 reset 残留的 `BestLap`。",
            "",
        ])

        report_text = "\n".join(lines)
        report_path.write_text(report_text, encoding="utf-8")
        (eval_dir / report_path.name).write_text(report_text, encoding="utf-8")
        logger.info("Saved evaluation report to %s", report_path)
        return report_path

    def __del__(self):
        self._env.close()
        self._test_env.close()
        self._writer.close()
        if self.wandb_logger:
            self.wandb_logger.finish()

    def common_metrics(self):
        """Return a dictionary of current metrics."""
        return dict(
            step=self._steps,
            episode=self._episodes,
            buffer_size=len(self._replay_buffer),
            total_time=time.time() - self._start_time,
        )

    def load_pre_train_data(self, trajs_path, env):
        total_added_episodes = 0

        env_data = DataLoader(env, trajs_path)
        for ep in tqdm(range(env_data.trajectories_count)[:]):
            state = env_data.reset()

            total_added_episodes += 1
            for i in range(len(env_data.trajectory) - 1):
                action = env_data.act()
                next_state, reward, done, info = env_data.step(action)

                if info['terminated']:
                    terminated = True
                else:
                    terminated = False

                # end of trajectory
                if i >= len(env_data.trajectory) - 2:
                    episode_done = True # will add done as zero to the RB
                else:
                    episode_done = False # use the termination signal from the environment

                self._replay_buffer.append(state, action, reward, next_state, terminated=terminated, episode_done=episode_done)
                state = next_state
                if episode_done:
                    break
        logger.info(f"Loaded {trajs_path} Buffer size: {len(self._replay_buffer)}")

    def pre_train(self):
        self._algo.update_entropy = False
        logger.info("Pre-training...")
        for _ in tqdm(range(self._replay_buffer._n)):
            self.update_model()
        self._algo.update_entropy = True
