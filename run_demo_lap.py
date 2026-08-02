import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import torch
from omegaconf import OmegaConf


sys.path.extend(
    [os.path.abspath("./assetto_corsa_gym"), os.path.abspath("./algorithm/discor")]
)

import AssettoCorsaEnv.assettoCorsa as assetto_corsa
from discor.network import GaussianPolicy


logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description="Run a lightweight AC policy demo lap.")
    parser.add_argument("--config", default="config.yml")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--track", default="monza")
    parser.add_argument("--car", default="bmw_z4_gt3")
    parser.add_argument("--laps", type=int, default=1)
    parser.add_argument("--output", default=None)
    parser.add_argument(
        "--stochastic",
        action="store_true",
        help="Sample SAC policy actions instead of using the deterministic mean.",
    )
    parser.add_argument("--seed", type=int, default=0)
    return parser.parse_args()


def main():
    args = parse_args()
    torch.manual_seed(args.seed)
    config = OmegaConf.load(args.config)
    config.AssettoCorsa.track = args.track
    config.AssettoCorsa.car = args.car
    # In Hotlap mode LapCount stays at zero during the untimed start segment.
    # Each later increment represents one complete timed lap.
    config.AssettoCorsa.eval_number_of_laps = args.laps
    config.AssettoCorsa.screen_capture_enable = False

    output_dir = Path(
        args.output
        or Path("outputs") / ("demo_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    ).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s[%(levelname)s] %(name)s %(message)s",
    )
    logger.info("Demo output: %s", output_dir)

    env = assetto_corsa.make_ac_env(cfg=config, work_dir=str(output_dir))
    env.set_eval_mode()

    device = torch.device("cpu")
    policy = GaussianPolicy(
        state_dim=env.observation_space.shape[0],
        action_dim=env.action_space.shape[0],
        hidden_units=OmegaConf.to_container(config.SAC.policy_hidden_units),
    ).to(device)
    policy_path = Path(args.checkpoint).resolve() / "policy_net.pth"
    policy.load_state_dict(torch.load(str(policy_path), map_location=device))
    policy.eval()
    logger.info("Loaded policy: %s", policy_path)

    summary = {}
    completed_lap_times = []
    termination_reason = "unknown"
    try:
        state = env.reset()
        previous_lap_count = env.state["LapCount"]
        done = False
        while not done:
            state_tensor = torch.tensor(
                state[None, ...].copy(), dtype=torch.float32, device=device
            )
            with torch.no_grad():
                sampled_action, entropies, mean_action = policy(state_tensor)
            action_tensor = sampled_action if args.stochastic else mean_action
            action = action_tensor.cpu().numpy()[0]
            state, _, done, info = env.step(action)
            env.states[-1]["entropies"] = entropies.item()

            current_lap_count = env.state["LapCount"]
            if current_lap_count != previous_lap_count:
                lap_time = env.state["iLastTime"] / 1000.0
                if lap_time > 0:
                    completed_lap_times.append(lap_time)
                    logger.info(
                        "Completed evaluation lap %d: %.3fs",
                        len(completed_lap_times),
                        lap_time,
                    )
                previous_lap_count = current_lap_count

        if len(completed_lap_times) >= args.laps:
            termination_reason = "target_laps_completed"
        elif env.state.get("out_of_track"):
            termination_reason = "out_of_track"
        elif env.state.get("going_backwards", 0) > 0:
            termination_reason = "going_backwards"
        elif info.get("terminated"):
            termination_reason = "terminated_before_lap_completion"
        else:
            termination_reason = "episode_ended"
    finally:
        summary = env.close()
        # BestLap/iLastTime persist across car resets in an AC session. Only
        # LapCount transitions observed during this process are valid evidence
        # that the current evaluation completed a lap.
        summary["eval_completed_laps"] = len(completed_lap_times)
        summary["eval_lap_times"] = ";".join(
            "{:.3f}".format(lap_time) for lap_time in completed_lap_times
        )
        summary["eval_best_lap"] = (
            min(completed_lap_times) if completed_lap_times else 0.0
        )
        summary["termination_reason"] = termination_reason
        summary["policy_mode"] = "stochastic" if args.stochastic else "deterministic"
        summary["policy_seed"] = args.seed
        pd.DataFrame([summary]).to_csv(output_dir / "eval_summary.csv", index=False)

    logger.info("Demo complete: %s", summary)


if __name__ == "__main__":
    main()
