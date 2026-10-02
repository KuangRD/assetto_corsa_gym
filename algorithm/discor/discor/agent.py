import os
import json
import random
import shutil
import pandas as pd
import numpy as np
import torch
from torch.utils.tensorboard import SummaryWriter
import pickle
from pathlib import Path
from tqdm import tqdm
from datetime import datetime

from discor.replay_buffer import ReplayBuffer, EnsembleBuffer
from discor.utils import RunningMeanStats
from AssettoCorsaEnv.data_loader import DataLoader
from AssettoCorsaEnv.lap_timing import PhysicalLapTimer

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
                 evaluation_report_dir=None, save_checkpoint_file=False,
                 checkpoint_replay_buffer=False, initial_entropy_alpha=None,
                 warmup_deterministic=False, resume_policy_lr=None,
                 resume_q_lr=None, resume_entropy_lr=None,
                 resume_reset_replay=False,
                 replay_rebuild_steps=0,
                 replay_rebuild_deterministic=True,
                 online_collection_deterministic=False,
                 resume_reset_episode_stats=False,
                 external_checkpoint_enabled=False,
                 external_checkpoint_poll_interval_steps=25,
                 external_checkpoint_control_dir=None):

        # Environment.
        self._env = env
        self._test_env = test_env
        self.checkpoint_freq = checkpoint_freq
        self.checkpoint_step_offset = checkpoint_step_offset
        self.wandb_logger = wandb_logger
        self.save_final_buffer = save_final_buffer
        self.stop_episode_at_eval_interval = stop_episode_at_eval_interval
        self.evaluation_report_dir = evaluation_report_dir
        self.save_checkpoint_file = save_checkpoint_file
        self.checkpoint_replay_buffer = checkpoint_replay_buffer
        self.warmup_deterministic = warmup_deterministic
        self.resume_reset_replay = bool(resume_reset_replay)
        self.replay_rebuild_steps = max(0, int(replay_rebuild_steps))
        self.replay_rebuild_deterministic = bool(replay_rebuild_deterministic)
        self.online_collection_deterministic = bool(
            online_collection_deterministic)
        self.resume_reset_episode_stats = bool(resume_reset_episode_stats)
        self._replay_rebuild_until_step = 0
        self.external_checkpoint_enabled = bool(external_checkpoint_enabled)
        self.external_checkpoint_poll_interval_steps = max(
            1, int(external_checkpoint_poll_interval_steps))
        self.external_checkpoint_control_dir = Path(
            external_checkpoint_control_dir or (Path(log_dir) / "control"))
        self._external_checkpoint_request_path = (
            self.external_checkpoint_control_dir / "save_checkpoint.request.json")
        self._external_checkpoint_processing_path = (
            self.external_checkpoint_control_dir / "save_checkpoint.processing.json")
        self._last_external_checkpoint_poll_step = -self.external_checkpoint_poll_interval_steps
        self._external_stop_requested = False
        self._last_replay_checkpoint_path = None
        self._last_replay_total_appends = 0
        self.resume_optimizer_lrs = {
            "_policy_optim": resume_policy_lr,
            "_q_optim": resume_q_lr,
            "_alpha_optim": resume_entropy_lr,
        }

        self._env.seed(seed)
        self._test_env.seed(2**31-1-seed)

        # Algorithm.
        self._algo = algo
        if initial_entropy_alpha is not None:
            self.set_entropy_alpha(initial_entropy_alpha)

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
        logger.info(f'warmup_deterministic: {self.warmup_deterministic}')
        logger.info(f'external_checkpoint_enabled: {self.external_checkpoint_enabled}')
        if self.external_checkpoint_enabled:
            self.external_checkpoint_control_dir.mkdir(parents=True, exist_ok=True)
            logger.info(
                "external checkpoint request file: %s",
                self._external_checkpoint_request_path,
            )
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

    def set_entropy_alpha(self, alpha):
        """Set SAC's entropy coefficient without replacing its optimizer tensor."""
        alpha = float(alpha)
        if not np.isfinite(alpha) or alpha <= 0:
            raise ValueError(f"initial_entropy_alpha must be positive, got {alpha}")
        log_alpha = getattr(self._algo, "_log_alpha", None)
        if log_alpha is None:
            raise ValueError(
                f"{type(self._algo).__name__} does not expose an entropy coefficient")
        with torch.no_grad():
            log_alpha.copy_(torch.tensor(
                np.log(alpha), dtype=log_alpha.dtype, device=log_alpha.device))
        self._algo._alpha = log_alpha.detach().exp()
        logger.info("initialized entropy alpha to %.8f", self._algo._alpha.item())

    def save_training_checkpoint(self, checkpoint_dir):
        """Save complete training state plus an incremental replay snapshot."""
        checkpoint_dir = Path(checkpoint_dir)
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        algorithm_state = {}
        for name in (
                "_policy_net", "_online_q_net", "_target_q_net",
                "_online_error_net", "_target_error_net",
                "_policy_optim", "_q_optim", "_alpha_optim", "_error_optim"):
            value = getattr(self._algo, name, None)
            if value is not None and hasattr(value, "state_dict"):
                algorithm_state[name] = value.state_dict()

        log_alpha = getattr(self._algo, "_log_alpha", None)
        if log_alpha is not None:
            algorithm_state["_log_alpha"] = log_alpha.detach().cpu()

        replay_state = None
        if self.checkpoint_replay_buffer:
            if isinstance(self._replay_buffer, EnsembleBuffer):
                raise NotImplementedError(
                    "Incremental checkpoints do not yet support EnsembleBuffer")
            replay_delta_path = checkpoint_dir / "replay_delta.npz"
            replay_info = self._replay_buffer.save_delta(
                replay_delta_path,
                since_total_appends=self._last_replay_total_appends,
            )
            parent_checkpoint = None
            if self._last_replay_checkpoint_path is not None:
                parent_checkpoint = os.path.relpath(
                    self._last_replay_checkpoint_path, checkpoint_dir)
            replay_state = {
                "delta_file": replay_delta_path.name,
                "parent_checkpoint": parent_checkpoint,
                **replay_info,
            }

            nstep_buffer = getattr(self._replay_buffer, "_nstep_buffer", None)
            if nstep_buffer is not None:
                replay_state["nstep_buffer"] = {
                    "states": list(nstep_buffer._states),
                    "actions": list(nstep_buffer._actions),
                    "rewards": list(nstep_buffer._rewards),
                }

        total_step = self._steps + self.checkpoint_step_offset
        checkpoint = {
            "format_version": 2,
            "algorithm": type(self._algo).__name__,
            "algorithm_state": algorithm_state,
            "agent_state": {
                "continuation_step": self._steps,
                "total_step": total_step,
                "checkpoint_step_offset": self.checkpoint_step_offset,
                "episodes": self._episodes,
                "learning_steps": getattr(self._algo, "_learning_steps", None),
                "best_lap_time": self.best_lap_time,
                "best_reward": self.best_reward,
                "episodes_stats": self.episodes_stats,
                "train_return": list(self._train_return._stats),
            },
            "replay_state": replay_state,
            "rng_state": {
                "python": random.getstate(),
                "numpy": np.random.get_state(),
                "torch": torch.get_rng_state(),
                "torch_cuda": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else None,
            },
        }
        checkpoint_path = checkpoint_dir / "training_state.ckpt"
        torch.save(checkpoint, checkpoint_path)
        if replay_state is not None:
            self._last_replay_checkpoint_path = str(checkpoint_path.resolve())
            self._last_replay_total_appends = replay_state["total_appends"]
        logger.info("saved training checkpoint to %s", checkpoint_path)
        return checkpoint_path

    @staticmethod
    def _resolve_checkpoint_reference(checkpoint_path, reference):
        reference = Path(reference)
        if reference.is_absolute():
            return reference
        return (checkpoint_path.parent / reference).resolve()

    def _load_replay_checkpoint_chain(self, checkpoint_path):
        chain = []
        seen = set()
        current = Path(checkpoint_path).resolve()
        while current is not None:
            if current in seen:
                raise ValueError(f"Replay checkpoint cycle detected at {current}")
            seen.add(current)
            payload = torch.load(str(current), map_location="cpu")
            replay_state = payload.get("replay_state")
            if replay_state is None:
                raise ValueError(f"Checkpoint has no replay state: {current}")
            chain.append((current, replay_state))
            parent = replay_state.get("parent_checkpoint")
            current = (self._resolve_checkpoint_reference(current, parent)
                       if parent else None)

        for owner, replay_state in reversed(chain):
            delta_path = self._resolve_checkpoint_reference(
                owner, replay_state["delta_file"])
            if not delta_path.exists():
                raise FileNotFoundError(f"Replay delta not found: {delta_path}")
            self._replay_buffer.load_delta(delta_path)

        latest_replay = chain[0][1]
        nstep_state = latest_replay.get("nstep_buffer")
        nstep_buffer = getattr(self._replay_buffer, "_nstep_buffer", None)
        if nstep_state is not None and nstep_buffer is not None:
            nstep_buffer.reset()
            nstep_buffer._states.extend(nstep_state["states"])
            nstep_buffer._actions.extend(nstep_state["actions"])
            nstep_buffer._rewards.extend(nstep_state["rewards"])

    def load_training_checkpoint(self, checkpoint_path):
        """Restore networks, optimizers, entropy, counters, RNG and replay."""
        checkpoint_path = Path(checkpoint_path).resolve()
        checkpoint = torch.load(str(checkpoint_path), map_location=self._device)
        if checkpoint.get("format_version", 0) < 2:
            raise ValueError(
                f"Checkpoint {checkpoint_path} predates complete-state format v2")
        if checkpoint.get("algorithm") != type(self._algo).__name__:
            raise ValueError(
                f"Algorithm mismatch: checkpoint={checkpoint.get('algorithm')}, "
                f"configured={type(self._algo).__name__}")

        algorithm_state = checkpoint["algorithm_state"]
        for name in (
                "_policy_net", "_online_q_net", "_target_q_net",
                "_online_error_net", "_target_error_net"):
            if name in algorithm_state:
                getattr(self._algo, name).load_state_dict(algorithm_state[name])

        if "_log_alpha" in algorithm_state:
            log_alpha = self._algo._log_alpha
            with torch.no_grad():
                log_alpha.copy_(algorithm_state["_log_alpha"].to(log_alpha.device))
            self._algo._alpha = log_alpha.detach().exp()

        for name in ("_policy_optim", "_q_optim", "_alpha_optim", "_error_optim"):
            if name in algorithm_state:
                getattr(self._algo, name).load_state_dict(algorithm_state[name])

        for optimizer_name, learning_rate in self.resume_optimizer_lrs.items():
            if learning_rate is None:
                continue
            learning_rate = float(learning_rate)
            if not np.isfinite(learning_rate) or learning_rate <= 0:
                raise ValueError(
                    f"Resume learning rate for {optimizer_name} must be positive")
            optimizer = getattr(self._algo, optimizer_name, None)
            if optimizer is None:
                raise ValueError(
                    f"Configured resume learning rate for missing {optimizer_name}")
            for parameter_group in optimizer.param_groups:
                parameter_group["lr"] = learning_rate
            logger.info(
                "overrode resumed %s learning rate to %.8g",
                optimizer_name,
                learning_rate,
            )

        agent_state = checkpoint["agent_state"]
        saved_offset = int(agent_state["checkpoint_step_offset"])
        if saved_offset != self.checkpoint_step_offset:
            raise ValueError(
                f"Checkpoint offset mismatch: checkpoint={saved_offset}, "
                f"configured={self.checkpoint_step_offset}")
        self._steps = int(agent_state["continuation_step"])
        self._episodes = int(agent_state["episodes"])
        self._algo._learning_steps = int(agent_state["learning_steps"])
        self.best_lap_time = float(agent_state["best_lap_time"])
        self.best_reward = float(agent_state["best_reward"])
        if self.resume_reset_episode_stats:
            self.episodes_stats = []
            logger.info("cleared resumed episode statistics for fresh reports")
        else:
            self.episodes_stats = agent_state.get("episodes_stats", [])
        self._train_return._stats.clear()
        self._train_return._stats.extend(agent_state.get("train_return", []))

        if self.resume_reset_replay:
            self._last_replay_checkpoint_path = None
            self._last_replay_total_appends = 0
            self._replay_rebuild_until_step = self._steps + self.replay_rebuild_steps
            logger.info(
                "skipped checkpoint replay; rebuilding with %s fresh policy "
                "transitions through continuation step %s",
                self.replay_rebuild_steps,
                self._replay_rebuild_until_step,
            )
        else:
            self._load_replay_checkpoint_chain(checkpoint_path)
            replay_state = checkpoint["replay_state"]
            self._last_replay_checkpoint_path = str(checkpoint_path)
            self._last_replay_total_appends = int(replay_state["total_appends"])

        rng_state = checkpoint.get("rng_state", {})
        if rng_state.get("python") is not None:
            random.setstate(rng_state["python"])
        if rng_state.get("numpy") is not None:
            np.random.set_state(rng_state["numpy"])
        if rng_state.get("torch") is not None:
            torch.set_rng_state(rng_state["torch"].cpu())
        if torch.cuda.is_available() and rng_state.get("torch_cuda") is not None:
            torch.cuda.set_rng_state_all([
                state.cpu() for state in rng_state["torch_cuda"]
            ])

        logger.info(
            "restored complete training checkpoint %s at total step %s "
            "with replay size %s and alpha %.8f%s",
            checkpoint_path,
            agent_state["total_step"],
            len(self._replay_buffer),
            self._algo._alpha.item(),
            " (fresh replay rebuild active)" if self.resume_reset_replay else "",
        )

    @staticmethod
    def _write_json_atomic(path, payload):
        """Write a small control/status file without exposing partial JSON."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_name(path.name + f".{os.getpid()}.tmp")
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(str(temporary_path), str(path))

    def _claim_external_checkpoint_request(self):
        """Atomically claim one file-based checkpoint request, if available."""
        if not self.external_checkpoint_enabled:
            return None
        if (self._steps - self._last_external_checkpoint_poll_step
                < self.external_checkpoint_poll_interval_steps):
            return None
        self._last_external_checkpoint_poll_step = self._steps

        request_path = self._external_checkpoint_request_path
        processing_path = self._external_checkpoint_processing_path
        if processing_path.exists() or not request_path.exists():
            return None

        try:
            os.replace(str(request_path), str(processing_path))
        except FileNotFoundError:
            return None

        try:
            request = json.loads(processing_path.read_text(encoding="utf-8"))
            request_id = str(request["request_id"])
            safe_request_id = "".join(
                char for char in request_id if char.isalnum() or char in "-_"
            )[:64]
            if not safe_request_id:
                raise ValueError("request_id contains no safe filename characters")
            request["request_id"] = safe_request_id
            logger.info(
                "Claimed external checkpoint request %s at continuation step %s",
                safe_request_id,
                self._steps,
            )
            return request
        except Exception as exc:
            logger.exception("Invalid external checkpoint request")
            invalid_id = f"invalid_{int(time.time())}"
            response_path = (
                self.external_checkpoint_control_dir /
                f"checkpoint.status.{invalid_id}.json")
            self._write_json_atomic(response_path, {
                "request_id": invalid_id,
                "status": "failed",
                "error": str(exc),
                "finished_at": datetime.now().isoformat(timespec="seconds"),
            })
            processing_path.unlink(missing_ok=True)
            return None

    def _save_external_checkpoint(self, request):
        """Save an externally requested checkpoint through an atomic directory rename."""
        request_id = request["request_id"]
        total_step = self._steps + self.checkpoint_step_offset
        checkpoints_root = Path(self._model_dir) / "checkpoints"
        checkpoints_root.mkdir(parents=True, exist_ok=True)
        final_dir = checkpoints_root / (
            f"step_{total_step:08d}_external_{request_id}")
        staging_dir = checkpoints_root / (
            f".step_{total_step:08d}_external_{request_id}.tmp")
        response_path = (
            self.external_checkpoint_control_dir /
            f"checkpoint.status.{request_id}.json")
        previous_replay_path = self._last_replay_checkpoint_path
        previous_total_appends = self._last_replay_total_appends

        response = {
            "request_id": request_id,
            "requested_at": request.get("requested_at"),
            "continuation_step": self._steps,
            "total_step": total_step,
            "stop_after_save": bool(request.get("stop_after_save", False)),
        }
        try:
            if final_dir.exists() or staging_dir.exists():
                raise FileExistsError(
                    f"External checkpoint directory already exists: {final_dir}")
            staging_dir.mkdir(parents=True)
            logger.info(
                "Saving external checkpoint request %s at total step %s",
                request_id,
                total_step,
            )
            self.save(str(staging_dir), save_buffer=False)
            self.save_training_checkpoint(staging_dir)
            staging_dir.rename(final_dir)
            checkpoint_path = final_dir / "training_state.ckpt"
            self._last_replay_checkpoint_path = str(checkpoint_path.resolve())
            response.update({
                "status": "success",
                "checkpoint_path": str(checkpoint_path.resolve()),
                "finished_at": datetime.now().isoformat(timespec="seconds"),
            })
            self._write_json_atomic(response_path, response)
            self._write_json_atomic(
                self.external_checkpoint_control_dir /
                "latest_checkpoint.status.json",
                response,
            )
            if response["stop_after_save"]:
                self._external_stop_requested = True
            logger.info(
                "External checkpoint request %s completed: %s",
                request_id,
                checkpoint_path,
            )
            return checkpoint_path
        except Exception as exc:
            self._last_replay_checkpoint_path = previous_replay_path
            self._last_replay_total_appends = previous_total_appends
            if staging_dir.exists():
                shutil.rmtree(staging_dir)
            response.update({
                "status": "failed",
                "error": str(exc),
                "finished_at": datetime.now().isoformat(timespec="seconds"),
            })
            self._write_json_atomic(response_path, response)
            logger.exception(
                "External checkpoint request %s failed", request_id)
            return None
        finally:
            self._external_checkpoint_processing_path.unlink(missing_ok=True)

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
            while self._steps < self._num_steps and not self._external_stop_requested:
                self.train_episode()
                if self._external_stop_requested:
                    logger.info(
                        "Stopping training cleanly after external checkpoint request")
                    break
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

    @staticmethod
    def _is_valid_lap_time(value):
        try:
            value = float(value)
        except (TypeError, ValueError):
            return False
        return np.isfinite(value) and value > 0

    def record_best_lap_update(self, lap_time, ep_stats, train_stats=None):
        """Write a per-record snapshot and append the cumulative best-lap log."""
        lap_time = float(lap_time)
        total_step = self._steps + self.checkpoint_step_offset
        update_dir = Path(self._log_dir) / "best_lap_updates"
        update_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = update_dir / (
            f"step_{total_step:08d}_episode_{self._episodes:06d}.md")
        history_path = Path(self._log_dir) / "best_lap_history.md"

        alpha = getattr(self._algo, "_alpha", None)
        alpha_value = float(alpha.item()) if alpha is not None else float("nan")
        training_phase = "warm-up（仅采样）" if self._steps < self._start_steps else "在线更新"
        episode_laps = []
        for key, value in ep_stats.items():
            if key.startswith("LapNo_") and self._is_valid_lap_time(value):
                episode_laps.append((key, float(value)))
        episode_laps.sort(key=lambda item: int(item[0].split("_")[-1]))

        lines = [
            f"# 最快圈更新：{lap_time:.3f} s",
            "",
            "## 当前训练状况",
            "",
            f"- 记录时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"- 累计总步数：{total_step:,}",
            f"- 本轮续训步数：{self._steps:,}",
            f"- Episode：{self._episodes:,}",
            f"- 训练阶段：{training_phase}",
            f"- 当前训练最快圈：{lap_time:.3f} s",
            f"- 本 Episode 步数：{int(ep_stats.get('ep_steps', 0) or 0):,}",
            f"- 本 Episode Reward：{float(ep_stats.get('ep_reward', 0.0) or 0.0):.3f}",
            f"- 平均速度：{float(ep_stats.get('speed_mean', 0.0) or 0.0):.3f} m/s",
            f"- 最高速度：{float(ep_stats.get('speed_max', 0.0) or 0.0):.3f} m/s",
            f"- Replay buffer：{len(self._replay_buffer):,}",
            f"- SAC α：{alpha_value:.8f}" if np.isfinite(alpha_value) else "- SAC α：无",
            f"- 当前最佳 Reward：{self.best_reward:.3f}" if np.isfinite(self.best_reward) else "- 当前最佳 Reward：无",
            f"- 模型目录：`{Path(self._model_dir) / 'best_lap_time'}`",
        ]

        if train_stats:
            lines.extend([
                "",
                "## 最近一次更新指标",
                "",
            ])
            for key in sorted(train_stats):
                value = train_stats[key]
                if isinstance(value, (int, float, np.number)):
                    lines.append(f"- {key}：{float(value):.8f}")

        lines.extend([
            "",
            "## 本 Episode 圈速",
            "",
        ])
        if episode_laps:
            lines.extend(f"- {key}：{value:.3f} s" for key, value in episode_laps)
        else:
            lines.append("- 无有效圈")
        lines.append("")
        snapshot_path.write_text("\n".join(lines), encoding="utf-8")

        if not history_path.exists():
            history_path.write_text(
                "# 训练最快圈更新历史\n\n"
                "| 时间 | 累计步数 | Episode | 最快圈 | Reward | 平均速度 | 最高速度 | Buffer | α | 状态快照 |\n"
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|\n",
                encoding="utf-8",
            )
        history_row = (
            f"| {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} "
            f"| {total_step:,} | {self._episodes:,} | {lap_time:.3f} s "
            f"| {float(ep_stats.get('ep_reward', 0.0) or 0.0):.3f} "
            f"| {float(ep_stats.get('speed_mean', 0.0) or 0.0):.3f} m/s "
            f"| {float(ep_stats.get('speed_max', 0.0) or 0.0):.3f} m/s "
            f"| {len(self._replay_buffer):,} "
            f"| {alpha_value:.8f} "
            f"| [{snapshot_path.name}](best_lap_updates/{snapshot_path.name}) |\n"
        )
        with history_path.open("a", encoding="utf-8") as history_file:
            history_file.write(history_row)
        logger.info("Saved best-lap training snapshot to %s", snapshot_path)
        return snapshot_path

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
        external_checkpoint_request = None

        try:
            done = False
            step_perf, action_perf, update_model_perf = [], [], []
            state = self._env.reset()
            step_start_time = time.perf_counter()

            while (not done) and self._steps < self._num_steps:
                start_profile = time.perf_counter()
                rebuilding_replay = self._steps < self._replay_rebuild_until_step
                if ((rebuilding_replay
                        and self.replay_rebuild_deterministic)
                        or self.online_collection_deterministic):
                    action, _ = self._algo.exploit(state)
                elif self._random_steps > self._steps:
                    action = self._env.action_space.sample()
                elif self.warmup_deterministic and self._steps < self._start_steps:
                    action, _ = self._algo.exploit(state)
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
                if (self._steps >= self._start_steps
                        and not rebuilding_replay
                        and len(self._replay_buffer) >= self._batch_size):
                    train_stats = self.update_model()
                update_model_perf.append(time.perf_counter() - start_profile)

                # get observations
                next_state, reward, done, info = self._env.step(action=None)  # action is already applied
                step_perf.append(time.perf_counter() - step_start_time)
                step_start_time = time.perf_counter()

                if info.get('control_state_invalid'):
                    raise RuntimeError(
                        "Training aborted before storing the invalid control "
                        "transition: the simulator is in a low-speed highest-"
                        "gear state. Return the physical H-shifter to neutral "
                        "or disable its gear binding, then restart.")

                # Set done=True only when the agent fails, ignoring done signal
                # if the agent reach time horizons.
                if (episode_steps + 1 >= self._env._max_episode_steps):
                    masked_done = False
                else:
                    masked_done = done

                external_checkpoint_request = self._claim_external_checkpoint_request()
                external_checkpoint_boundary = external_checkpoint_request is not None
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
                    episode_done=(
                        rb_done or milestone_boundary or external_checkpoint_boundary))

                self._steps += 1
                episode_steps += 1
                episode_return += reward
                state = next_state

                if self._training_progress is not None:
                    self._training_progress.update(1)

                if self.checkpoint_freq and (self._steps % self.checkpoint_freq == 0):
                    logger.info(f"checkpointing model {self._steps} steps")
                    checkpoint_step = self._steps + self.checkpoint_step_offset
                    checkpoint_dir = os.path.join(
                        self._model_dir, "checkpoints", f"step_{checkpoint_step:08d}")
                    self.save(checkpoint_dir, save_buffer=False)
                    if self.save_checkpoint_file:
                        self.save_training_checkpoint(checkpoint_dir)

                if milestone_boundary:
                    logger.info(f"Reached evaluation boundary at {self._steps} continuation steps")
                    break
                if external_checkpoint_boundary:
                    logger.info(
                        "Ending episode at continuation step %s for external checkpoint",
                        self._steps,
                    )
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

        candidate_best_lap = float(env_ep_stats.get("BestLap", 0.0) or 0.0)
        if (self._is_valid_lap_time(candidate_best_lap)
                and candidate_best_lap < self.best_lap_time):
            logger.info(f"new best lap time {candidate_best_lap}")
            self.best_lap_time = candidate_best_lap
            self.save(os.path.join(self._model_dir, 'best_lap_time'), save_buffer=False)
            try:
                self.record_best_lap_update(candidate_best_lap, ep_stats, train_stats)
            except Exception:
                logger.exception("Failed to record best-lap training status")

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
        if external_checkpoint_request is not None:
            self._save_external_checkpoint(external_checkpoint_request)

    def evaluate(self):
        eval_records = []
        previous_max_laps = getattr(self._test_env, "max_laps_number", None)
        self._test_env.set_eval_mode()
        # AC's LapCount can miss the first crossing after a car reset.  Stop
        # on reset-local physical laps instead of the persistent AC counter.
        self._test_env.max_laps_number = None
        set_reward_training_step = getattr(
            self._test_env, "set_reward_training_step", None)
        if set_reward_training_step is not None:
            set_reward_training_step(self._steps)
        try:
            for trial in range(1, self._num_eval_episodes + 1):
                completed_lap_times = []
                termination_reason = "unknown"
                info = {}
                episode_return = 0.0
                env_ep_stats = {}
                try:
                    state = self._test_env.reset()
                    lap_timer = PhysicalLapTimer(self._test_env.track_length)
                    lap_timer.reset_state(self._test_env.state)
                    done = False

                    while not done:
                        action, entropies = self._algo.exploit(state)
                        next_state, reward, done, info = self._test_env.step(action)
                        if info.get('control_state_invalid'):
                            termination_reason = "invalid_control_state"
                            logger.error(
                                "Evaluation aborted: physical shifter input is "
                                "overriding automatic shifting")
                            break
                        self._test_env.states[-1]["entropies"] = entropies.cpu().numpy().item()
                        episode_return += reward
                        state = next_state

                        lap_time = lap_timer.update_state(self._test_env.state)
                        if lap_time is not None:
                            completed_lap_times.append(lap_time)
                            logger.info(
                                "Completed physical evaluation lap %s: %.3fs",
                                len(completed_lap_times), lap_time)
                            if len(completed_lap_times) >= (
                                    self._test_env.config.eval_number_of_laps):
                                termination_reason = "target_laps_completed"
                                break

                    if termination_reason == "target_laps_completed":
                        pass
                    elif len(completed_lap_times) >= self._test_env.config.eval_number_of_laps:
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

        evaluation_lap_times = []
        for record in eval_records:
            raw_times = str(record.get("eval_lap_times", "") or "")
            evaluation_lap_times.extend(
                float(value) for value in raw_times.split(";") if value)
        evaluation_best_lap = min(evaluation_lap_times) if evaluation_lap_times else 0.0
        training_best_lap = (
            float(self.best_lap_time)
            if self._is_valid_lap_time(self.best_lap_time) else 0.0)
        for record in eval_records:
            record["training_best_lap_at_eval"] = training_best_lap
            record["evaluation_best_lap"] = evaluation_best_lap

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
        training_best_lap = (
            float(self.best_lap_time)
            if self._is_valid_lap_time(self.best_lap_time) else 0.0)
        evaluation_best_lap = min(lap_times) if lap_times else 0.0
        training_best_text = (
            f"{training_best_lap:.3f} s" if training_best_lap > 0 else "无有效圈")
        evaluation_best_text = (
            f"{evaluation_best_lap:.3f} s" if evaluation_best_lap > 0 else "DNF")

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
            f"- 当前训练最快圈：{training_best_text}",
            f"- 本次评估最快圈：{evaluation_best_text}",
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
            f"- 当前训练最快圈：{training_best_text}",
            f"- 本次评估最快圈：{evaluation_best_text}",
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
