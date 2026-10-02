# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Assetto Corsa Gym integrates the Assetto Corsa racing simulator with OpenAI Gym for autonomous racing RL research. It has two main runtimes: a Python 3.9+ training environment and a Python 3.3 plugin running inside the Assetto Corsa game.

## Commands

### Environment Setup
```bash
conda env create -f environment.yml
conda activate p309
pip install -r requirements-dev.txt
```

`environment.yml` owns Python, PyTorch, and CUDA Toolkit versions;
`requirements.txt` is the runtime lock, and `requirements-dev.txt` adds pytest.

### Download Track Data
```bash
python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='dasgringuen/assettoCorsaGym', repo_type='dataset', local_dir='AssettoCorsaGymDataSet', allow_patterns='AssettoCorsaConfigs/tracks/*')"
# Then move pickle files to assetto_corsa_gym/AssettoCorsaConfigs/tracks/
```

### Training & Testing
```bash
# Train (defaults: Barcelona, dallara_f317)
python train.py

# Train on specific track/car
python train.py AssettoCorsa.track=monza AssettoCorsa.car=bmw_z4_gt3

# Test pre-trained model
python train.py --test --load_path <checkpoint_path> AssettoCorsa.track=monza AssettoCorsa.car=bmw_z4_gt3

# Train with offline human demonstration data
python train.py load_offline_data=True Agent.use_offline_buffer=True dataset_path=<path>

# Enable Weights & Biases logging
python train.py disable_wandb=False wandb_entity=<user> wandb_project=sac
```

### Verify Setup
```bash
python test_environment_setup.py
```

Notebooks for manual testing (require AC running):
- `test_client.ipynb` — raw socket connection test
- `test_gym.ipynb` — Gym interface test
- `test_gym_images.ipynb` — screen capture test

## Architecture

### Data Flow
```
train.py → Agent (agent.py) → AssettoCorsaEnv (ac_env.py) → Client (ac_client.py)
                                                                    ↕ UDP/TCP sockets
                                               Assetto Corsa game ← Plugin (sensors_par.py)
                                                                       ↕ vJoy
                                                                   Telemetry (25 Hz)
```

### Key Components

**`assetto_corsa_gym/AssettoCorsaEnv/`** — OpenAI Gym environment (Python 3.9+)
- `ac_env.py` — Core `AssettoCorsaEnv(Env)` class; observation space (23 channels: speed, gaps, RPM, accelerations, slip angles), action space (steering, throttle, brake), reward calculation, episode termination logic
- `ac_client.py` — UDP/TCP socket client; sends vJoy controls, receives telemetry, handles shared-memory image transfer
- `track.py` — Track occupancy grids loaded from pickle files
- `reference_lap.py` — Racing line coordinates and reference speeds
- `sensors_ray_casting.py` — Ray-casting to detect track boundaries (gap features)

**`assetto_corsa_gym/AssettoCorsaPlugin/plugins/sensors_par/`** — AC plugin (Python 3.3, runs inside the game)
- `sensors_par.py` — Plugin entry point called by AC's Python runtime
- `ego_server.py` — UDP server streaming 22-channel telemetry at 25 Hz
- `config.py` — Plugin configuration (ports, screen capture toggle, Python interpreter path)
- `vjoy.py` / `vjoy_linux.py` — vJoy controller command handling
- `screen_capture.py` — Spawns a Python 3.9+ subprocess for image capture (AC's Python 3.3 can't handle it)
- `dual_buffer.py` — Shared memory for fast image transfer between processes

**`algorithm/discor/discor/`** — RL algorithms
- `agent.py` — Training loop, replay buffer management, checkpoint saving
- `algorithm/sac.py` — Soft Actor-Critic implementation
- `algorithm/discor.py` — DisCor (Discrepancy Correction) extension of SAC
- `network.py` — Policy (actor) and Q-function (critic) networks
- `replay_buffer.py` — Experience replay with optional offline demonstration buffer

**`assetto_corsa_gym/AssettoCorsaConfigs/`** — Car/track configuration files (pickle format)

**`config.yml`** — All hyperparameters via OmegaConf; any key overridable from CLI as `key=value` or `Section.key=value`

### Dual Python Runtime
The AC plugin runs under Python 3.3 (the game's embedded interpreter). Screen capture and any modern Python features require spawning a separate Python 3.9+ subprocess. Set `enable_alternative_python_interpreter = True` and `screen_capture_enable = True` in `AssettoCorsaPlugin/plugins/sensors_par/config.py`.

### Supported Cars & Tracks
- Cars: `dallara_f317`, `bmw_z4_gt3`, `ks_mazda_miata`
- Tracks: `ks_barcelona-layout_gp`, `monza`, `ks_red_bull_ring-layout_gp`, `silverstone`, `indianapolis`

### Logs & Debugging
- AC plugin logs: `C:\Users\<user>\Documents\Assetto Corsa\logs\py_log.txt`
- Screen capture subprocess logs: `<AC_install>/sensor_par_subprocess_log.txt`
