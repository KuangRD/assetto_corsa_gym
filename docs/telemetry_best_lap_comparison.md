# MX-5 Cup / Silverstone GP 遥测录制与对比

## 已核实的项目接口

- `AssettoCorsaEnv.ac_env` 的 `set_actions()` 将策略动作送到 `client.controls.set_controls(steer, acc, brake)`。相对动作和方向盘限速/平滑处理已在发包前完成。
- `AssettoCorsaPlugin/plugins/sensors_par/car_control.py` 把三个输入映射到 vJoy：转向 `[-1,1] → [0,2]`，油门和制动命令 `[-1,1] → [0,1]`。所以 AI 的油门/制动内部零点是 `-1`，记录的实际踏板遥测 `accStatus` / `brakeStatus` 则是 AC 报告的 `[0,1]`。
- 换挡协议确实有 `enable_gear_shift`、`shift_up`、`shift_down` 和 vJoy 按钮 1/2；但当前 `ac_env.set_actions()` 只传方向、油门、制动三个量，MX-5 配置没有额外动作维度。此配置下 AI 不会主动换挡，挡位来自 AC 驾驶辅助（建议自动挡、自动离合开启）。记录 `actualGear` 用于观察实际挡位。
- `sensors_par/plugins/.../structures.py` 通过 AC Python API 采集 `speed`、`accStatus`、`brakeStatus`、`actualGear`、`RPM`、`steerAngle`、`NormalizedSplinePosition`、`LapCount`、`LapInvalidated`、加速度、世界位置等；`ac_env.step()` 添加环境时间戳和已执行动作字段。训练采样率来自配置，当前 MX-5 训练配置为 25 Hz。
- `end_of_episode_stats()` 在 `save_observations=True` 时保存完整 episode 的 `laps/<时间戳>_states.parquet`，因此训练遥测已具备源数据；原来的 `save_lap_csv` 配置没有在这个 episode 保存位置用于最佳圈筛选。
- AC MoTeC 原生 `.ld` 记录和 i2 导出可作为人类来源。仓库已有 `MotecLoader` 映射 MoTeC 的 `session lap count`、`car pos norm`、`lap time`、`ground speed`、踏板、方向盘、挡位、RPM 与加速度等名称。

## AI 最快有效圈

1. 用 `configs/mx5_silverstone_1m_to_5m.yml`（车 `ks_mazda_mx5_cup`、赛道 `ks_silverstone-gp`）启动正常评估或训练。episode 结束时在输出目录的 `laps` 子目录确认出现 `*_states.parquet`。现有配置的环境默认 `save_observations=True`。
2. 使用实际 `static_info.json` 中的 `TrackLength`，提取 episode 里最快的完整有效圈：

```powershell
$repo = 'C:\Users\freedom\Documents\assetto_corsa_gym'
$source = 'C:\path\to\run\laps\YYYYMMDD_HHMMSS_states.parquet'
& 'C:\Users\freedom\anaconda3\envs\p309\python.exe' `
  "$repo\scripts\telemetry_compare.py" $source `
  --driver AI --track-length 5891 --out "$repo\outputs\AI_best_lap.csv"
```

此工具要求一圈有至少 80% 的归一化赛道距离覆盖；排除 `LapInvalidated` 非零的圈，并在可用时排除四轮均出界的圈。圈时来自 AC 采样的单调时间戳。每圈候选按 `LapCount` 分组并以最短时间选圈。Silverstone GP 默认长度是 5891 m；优先以本次会话 `static_info.json` 的 `TrackLength` 覆盖示例值。

## 人类圈与 MoTeC i2

1. 在 AC 开启 MoTeC 遥测记录，用 MX-5 Cup / Silverstone GP 跑圈；保留完整有效最快圈的 `.ld`。确保赛道、车辆、天气、辅助、胎况、燃油和时间倍率与 AI 场景一致。
2. 在 MoTeC i2 打开 `.ld`，以 CSV 导出这些通道：`session lap count`、`car pos norm`、`lap time`、`ground speed`、`throttle pos`、`brake pos`、`steering angle`、`gear`、`engine rpm`、`cg accel lateral`、`cg accel longitudinal`。这些名称依据项目的 `MotecLoader` 映射；i2 通道显示名可能随记录配置而不同，导出前检查名称与单位。
3. 直接将导出的通道 CSV 交给脚本，脚本把上述 MoTeC 名称归一化，车速从 km/h 转 m/s，踏板百分比转 `[0,1]`，并把 MoTeC 挡位编码加 1 对齐项目里的 AC `actualGear`：

```powershell
& 'C:\Users\freedom\anaconda3\envs\p309\python.exe' `
  "$repo\scripts\telemetry_compare.py" 'C:\path\to\human_i2_export.csv' `
  --driver Human --track-length 5891 --out "$repo\outputs\Human_best_lap.csv"
```

4. 将另一位驾驶者的标准 CSV 传给 `--compare`。生成文件以赛道距离为公共轴，默认每 5 m 插值一次，并为两圈的时间、车速、踏板、转向、挡位等字段生成独立列；`delta_time_s = 当前 driver 的 lap_time_s - 对比 CSV 的 lap_time_s`，正值表示当前 driver 落后。

```powershell
& 'C:\Users\freedom\anaconda3\envs\p309\python.exe' `
  "$repo\scripts\telemetry_compare.py" $source --driver AI `
  --track-length 5891 --out "$repo\outputs\AI_best_lap.csv" `
  --compare "$repo\outputs\Human_best_lap.csv" --step-m 5
```

标准圈 CSV 包含 `distance_m, lap_time_s, speed_m_s, throttle, brake, steer_deg, gear, rpm, lat_accel_g, long_accel_g, lap_invalidated`。JSON 附件写入源文件、驾驶者、赛道长度、圈编号、圈时、距离轴和字段名。

## 在 MoTeC i2 中查看

项目导出的 CSV 是通用分析/交换格式，不是 MoTeC 原生 `.ld`。如需在 i2 中叠加比较，分别把 AI 与人类 `.ld` 用同一个 i2 workspace/通道表打开，在 i2 的 channel report/overlay 中对齐圈起点并查看时间差；或把统一 CSV 导入 i2 支持的 CSV 数据源/日志格式（由安装的 i2 版本与通道配置决定）。若 i2 不接受通用 CSV，仍可在外部表格/图表工具查看脚本输出的距离对齐文件。不要把 CSV 扩展名改为 `.ld`。

目前仓库没有可验证的 MoTeC i2 自动导入插件、`.ld` 写入器，也没有 AI 控制时对人类方向盘/踏板原始输入的并行记录接口。现成接口能可靠记录仿真实际车况和 AI 命令；人类最快圈以 AC/MoTeC 的原始记录为权威来源。
