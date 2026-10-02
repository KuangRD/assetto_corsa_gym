# MX-5 Cup / Silverstone GP 手动训练操作手册

本文用于在不依赖 Codex 持续操作的情况下，手动启动、检查、停止和恢复当前 SAC 训练任务。

## 1. 当前任务基线

- 项目目录：`C:\Users\freedom\Documents\assetto_corsa_gym`
- Python：`C:\Users\freedom\anaconda3\envs\p309\python.exe`
- 配置文件：`configs\mx5_silverstone_1m_to_5m.yml`
- 训练输出目录：`outputs\train_mx5cup_silverstone_1m2_to_5m_stable_resume_retry1`
- 车辆：`ks_mazda_mx5_cup`
- 赛道：`ks_silverstone-gp`
- 目标：累计训练到 500 万步
- 每 10 万步自动保存完整 checkpoint，并进行 3 次评估、生成 Markdown 报告。

截至 2026-08-11，最新完整节点是 **190 万步**：

```text
outputs\train_mx5cup_silverstone_1m2_to_5m_stable_resume_retry1\model\checkpoints\step_01900000\training_state.ckpt
```

上一次进程运行到约 192.8 万步后停止，190 万步之后约 2.8 万步没有 checkpoint，应从 190 万步重新开始。

> 必须使用 `--resume_ckpt`。不要用 `--load_path` 或 `--weights_only` 继续正式训练，否则 replay buffer、优化器、熵系数、随机数状态和步数不能完整恢复。

## 2. 一次性环境要求

开始前确认以下项目已经安装和启用：

- Assetto Corsa 和 Content Manager；
- `sensors_par` Python App；
- vJoy，且 AC 当前控制配置使用 vJoy；
- 自动挡和自动离合已启用；
- Python `p309` 环境及 CUDA/PyTorch 可用。

推荐驾驶设置：

| 设置 | 值 |
|---|---|
| Automatic Gearbox | ON |
| Automatic Clutch | ON |
| Traction Control | OFF |
| Stability Control | OFF |
| ABS | OFF |
| Mechanical Damage | OFF |
| Fuel Consumption | OFF |
| Tyre Wear | OFF |
| Tyre Blankets | ON |
| Track Surface | Optimum |
| Weather | Mid Clear |
| Ambient Temperature | 26°C |

## 3. 启动 AC Hotlap

在 Content Manager 中选择：

1. 模式：`Challenge > Hotlap`；
2. 车辆：`Mazda MX-5 Cup`；
3. 赛道：`Silverstone GP`；
4. 时间：建议 `12:00`；
5. **Time Multiplier：`0x`**；
6. 天气：`Mid Clear`；
7. 启动并进入驾驶舱，等待车辆和 Python Apps 完全加载。

仓库原始 `INSTALL.md` 中的 `Time Multiplier=1x` 不适合数小时训练。使用 `1x` 会让长时间 Hotlap 从白天逐渐进入夜晚。

AC 启动后，在 PowerShell 中验证实际会话配置：

```powershell
Select-String -Path 'C:\Users\freedom\Documents\Assetto Corsa\cfg\race.ini' `
  -Pattern 'TRACK=|CONFIG_TRACK=|MODEL=|SUN_ANGLE=|TIME_MULT=|NAME='
```

必须看到正确的车辆、赛道，并确认：

```text
TIME_MULT=0
```

如果不是 `0`，退出 Hotlap，在 Content Manager 中修正后重新启动。已经开始的会话不会因为运行中修改 `race.ini` 而立即冻结时间。

检查 AC 进程和通信端口：

```powershell
Get-Process acs -ErrorAction Stop
Get-NetUDPEndpoint -LocalPort 2345 -ErrorAction SilentlyContinue
Get-NetTCPConnection -LocalPort 2347 -State Listen -ErrorAction SilentlyContinue
```

`acs` 应存在；端口检查至少不应出现被其他异常进程占用的情况。

## 4. 选择最新完整 checkpoint

打开 PowerShell，执行：

```powershell
$repo = 'C:\Users\freedom\Documents\assetto_corsa_gym'
$run = Join-Path $repo 'outputs\train_mx5cup_silverstone_1m2_to_5m_stable_resume_retry1'
$checkpointRoot = Join-Path $run 'model\checkpoints'

$latestDir = Get-ChildItem -LiteralPath $checkpointRoot -Directory |
  Where-Object {
    (Test-Path (Join-Path $_.FullName 'training_state.ckpt')) -and
    (Test-Path (Join-Path $_.FullName 'replay_delta.npz')) -and
    (Test-Path (Join-Path $_.FullName 'policy_net.pth')) -and
    (Test-Path (Join-Path $_.FullName 'online_q_net.pth')) -and
    (Test-Path (Join-Path $_.FullName 'target_q_net.pth'))
  } |
  Sort-Object Name |
  Select-Object -Last 1

$checkpoint = Join-Path $latestDir.FullName 'training_state.ckpt'
$checkpoint
Get-ChildItem -LiteralPath $latestDir.FullName
```

当前应选择：

```text
...\step_01900000\training_state.ckpt
```

checkpoint 使用增量 replay 链。**不要删除、移动或只复制最新目录**；必须保留 `step_01200000` 到最新节点所引用的历史 checkpoint 和 `replay_delta.npz`。启动时程序会自动验证整条链，缺少任一 replay delta 都会报错。

## 5. 启动训练

### 5.1 前台运行（最简单）

适合希望直接观察日志的情况：

```powershell
$repo = 'C:\Users\freedom\Documents\assetto_corsa_gym'
$python = 'C:\Users\freedom\anaconda3\envs\p309\python.exe'
$config = Join-Path $repo 'configs\mx5_silverstone_1m_to_5m.yml'
$checkpoint = Join-Path $repo 'outputs\train_mx5cup_silverstone_1m2_to_5m_stable_resume_retry1\model\checkpoints\step_01900000\training_state.ckpt'

Set-Location $repo
& $python train.py --config $config --resume_ckpt $checkpoint
```

保持这个 PowerShell 窗口打开。关闭窗口等同于中断训练。

### 5.2 后台运行并保存独立日志

适合关闭当前 PowerShell 后继续运行：

```powershell
$repo = 'C:\Users\freedom\Documents\assetto_corsa_gym'
$python = 'C:\Users\freedom\anaconda3\envs\p309\python.exe'
$config = Join-Path $repo 'configs\mx5_silverstone_1m_to_5m.yml'
$run = Join-Path $repo 'outputs\train_mx5cup_silverstone_1m2_to_5m_stable_resume_retry1'
$checkpoint = Join-Path $run 'model\checkpoints\step_01900000\training_state.ckpt'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$stdout = Join-Path $run "manual_$stamp.stdout.log"
$stderr = Join-Path $run "manual_$stamp.stderr.log"

$process = Start-Process `
  -FilePath $python `
  -ArgumentList @('train.py', '--config', $config, '--resume_ckpt', $checkpoint) `
  -WorkingDirectory $repo `
  -RedirectStandardOutput $stdout `
  -RedirectStandardError $stderr `
  -WindowStyle Hidden `
  -PassThru

$process | Select-Object Id, StartTime, Path
"PID=$($process.Id)"
"STDERR=$stderr"
"STDOUT=$stdout"
```

记下 PID 和日志路径。不要同时启动第二个训练进程。

## 6. 确认完整恢复成功

启动后查看 stderr：

```powershell
Get-Content -LiteralPath $stderr -Tail 80 -Wait
```

前台运行时直接查看窗口即可。成功恢复必须出现类似信息：

```text
restored complete training checkpoint ... at total step 1900000
with replay size 900000 and alpha ...
```

同时应看到：

- 当前训练进度从 continuation step `900000` 附近开始，而不是从 0 开始；
- AC 自动收到 reset；
- `Client connected on 2345`；
- 车辆开始受控行驶；
- 没有 `Traceback`、`CUDA out of memory`、`ConnectionRefused` 或 replay 文件缺失错误。

快速检查：

```powershell
Get-Process python,acs -ErrorAction SilentlyContinue |
  Select-Object Id, ProcessName, StartTime, CPU, Responding

nvidia-smi --query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total `
  --format=csv,noheader
```

## 7. 自动保存和评估

配置文件已经启用：

```yaml
eval_interval: 100_000
num_eval_episodes: 3
checkpoint_freq: 100_000
save_checkpoint_file: true
checkpoint_replay_buffer: true
```

因此从 190 万步恢复后，下一个节点是 200 万步，并自动生成：

```text
outputs\...\model\checkpoints\step_02000000\training_state.ckpt
outputs\...\model\checkpoints\step_02000000\replay_delta.npz
outputs\...\evaluations\step_02000000\eval_summary.csv
200万步训练效果评估.md
```

每次 checkpoint 目录应至少包含：

```text
training_state.ckpt
replay_delta.npz
policy_net.pth
online_q_net.pth
target_q_net.pth
```

训练圈约 152–153 秒、评估原始结果约 160 秒并不矛盾：目前评估包含静止起步和 AC 重置计时偏移。进入正常速度后的分段表现与训练飞驰圈基本一致。

## 8. 查看当前状态

查找最近更新的训练日志：

```powershell
$run = 'C:\Users\freedom\Documents\assetto_corsa_gym\outputs\train_mx5cup_silverstone_1m2_to_5m_stable_resume_retry1'
$latestLog = Get-ChildItem -LiteralPath $run -Filter 'manual_*.stderr.log' |
  Sort-Object LastWriteTime |
  Select-Object -Last 1

$latestLog.FullName
Get-Content -LiteralPath $latestLog.FullName -Tail 100
```

查看最新 checkpoint：

```powershell
Get-ChildItem -LiteralPath (Join-Path $run 'model\checkpoints') -Directory |
  Sort-Object Name |
  Select-Object -Last 5 Name, LastWriteTime
```

查看最新评估：

```powershell
Get-ChildItem -LiteralPath 'C:\Users\freedom\Documents\assetto_corsa_gym' `
  -Filter '*万步训练效果评估.md' |
  Sort-Object LastWriteTime |
  Select-Object -Last 5 Name, LastWriteTime
```

## 9. 安全停止

停止顺序必须是：**先停止 Python 训练，再退出 AC**。

最安全的方法：

1. 等待新的 10 万步 checkpoint 完成；
2. 确认 `training_state.ckpt` 和 `replay_delta.npz` 都存在且大小不为 0；
3. 等待该节点 3 次评估和 Markdown 报告写完；
4. 前台运行时按一次 `Ctrl+C`；后台运行时使用记录的 PID：

```powershell
Stop-Process -Id <训练PID>
```

5. 确认 Python 已退出后，再关闭 AC。

强制停止只会保留上一个完整 checkpoint。该节点之后尚未保存的步数会被放弃；下次仍从最近完整 checkpoint 恢复。

### 9.1 随时保存当前进度后自动停止（推荐）

使用已启用外部 checkpoint 功能的训练进程时，在另一个 PowerShell 窗口运行：

> 该功能在训练进程启动时加载。运行中修改代码或配置不会热更新；首次启用时需要从最近的完整 checkpoint 重启一次，之后即可使用下列命令安全保存和停止。

```powershell
$repo = 'C:\Users\freedom\Documents\assetto_corsa_gym'
$python = 'C:\Users\freedom\anaconda3\envs\p309\python.exe'
$run = Join-Path $repo 'outputs\train_mx5cup_silverstone_1m8_to_3m_rollback'

Set-Location $repo
& $python scripts\request_training_checkpoint.py `
  --run-dir $run `
  --stop-after-save `
  --timeout 300
```

训练进程会在当前环境 transition 完成后：

1. 在 replay buffer 中写入安全 episode 边界；
2. 保存模型、优化器、熵系数、RNG 和增量 replay；
3. 通过临时目录原子发布 checkpoint；
4. 返回 checkpoint 的准确路径；
5. 自行干净退出，AC 继续保持运行。

只想额外保存、不停止训练时，去掉 `--stop-after-save`：

```powershell
& $python scripts\request_training_checkpoint.py --run-dir $run --timeout 300
```

外部 checkpoint 目录形如：

```text
model\checkpoints\step_02546261_external_20260811_174700_a1b2c3d4
```

它会成为后续增量 replay checkpoint 的父节点，因此不可单独删除。恢复时直接把该目录中的 `training_state.ckpt` 传给 `--resume_ckpt`。

## 10. 常见问题

### 车辆不动或动作不受控

- 确认 AC 控制配置使用 vJoy；
- 确认 `sensors_par` 已启用；
- 确认只运行一个训练进程；
- 检查端口 2345/2347；
- 先启动并进入 AC Hotlap，再启动 Python。

### `ConnectionRefused` 或一直等待端口

AC 或 `sensors_par` 尚未准备好。停止 Python，进入 Hotlap 驾驶舱并等待插件加载，然后重新执行恢复命令。

### `Replay delta not found`

增量 replay 链不完整。恢复被删除或移动的旧 checkpoint 目录；不能只保留最新 `training_state.ckpt`。

### `Checkpoint offset mismatch`

使用了错误配置。当前 checkpoint 必须配合：

```text
configs\mx5_silverstone_1m_to_5m.yml
```

该配置的 `checkpoint_step_offset` 必须保持为 `1_000_000`。

### 现场逐渐变暗

说明 Hotlap 实际仍为 `TIME_MULT=1`。等待 checkpoint 后停止训练，重启固定中午且 `TIME_MULT=0` 的 Hotlap，再从完整 checkpoint 恢复。

### 画面不是全屏或仪表缺失

这通常是 AC 的 640×480 独占全屏和 HUD 坐标不匹配。当前策略不使用画面输入（`screen_capture_enable: false`），不会直接影响训练；可在下次重启时统一分辨率并重新布置 HUD。

### 评估第一次出现 300 秒以上

通常是 AC 跨 reset 残留计时。重点查看第 2、3 次 trial 和训练飞驰圈，不要把第一次残留时间当成策略真实圈速。

## 11. 每次启动的最短清单

1. 启动 AC Hotlap：MX-5 Cup、Silverstone GP、中午、`Time Multiplier=0x`。
2. 确认进入驾驶舱，vJoy 和 `sensors_par` 正常。
3. 确认没有旧 Python 训练进程。
4. 找到最新完整 checkpoint。
5. 使用 `--resume_ckpt` 启动，禁止使用 weights-only。
6. 日志确认恢复了 total step、replay size、optimizer 和 alpha。
7. 确认步数持续增长、车辆正常跑圈。
8. 停止时先等完整 checkpoint 和评估报告，再停 Python，最后退出 AC。
