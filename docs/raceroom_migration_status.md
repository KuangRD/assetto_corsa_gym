# RaceRoom 迁移执行状态

更新日期：2026-08-02 20:24 PDT

## 当前批次

本批次对应 M0/M1 的可离线实施部分。控制功能保持关闭，不进入 vJoy 写入。

| ID | 状态 | 说明 |
|---|---|---|
| RR-001 | 已完成 | 冻结同日 MX-5 Cup / Silverstone GP 基线：12,076 steps、连续 3 圈、0 丢包，见 `docs/baselines/ac_m0_baseline.json` |
| RR-002 | 已完成 | 冻结 RaceRoom `0.9.7.81`、Audi RS 3 LMS TCR (`11325`)、Shanghai Circuit (`2021`) / Grand Prix (`2027`) |
| RR-005 | 已完成 | 建立 RaceRoom 配置、版本化 schema、日志字段和读写 feature flag |
| RR-101 | 已完成（离线） | ctypes 对齐官方 API 3.5，来源提交 `29a3e958...` |
| RR-102 | 已完成（离线） | 只打开已存在的 `$R3E` map；包含版本/偏移校验和 tick 前后重读 |
| RR-103 | 已完成（首轮实测） | API 3.5；3 秒读取 1,127 个新帧，约 375.6 Hz，0 timeout、0 tick reset；报告位于 ignored outputs 目录 |
| RR-104 | 已完成（低速首轮） | 受控直行/左转/右转完成；冻结线性轴、角速度伪向量变换和 X/Z 世界水平面，高速复核列为 M2 验收项 |
| RR-105 | 已完成 | 去身份化 typed Parquet 录制器、7,492 行真实 fixture，以及 step/accelerated/real-time replay 均已实现并离线验证 |
| RR-106 | 已完成（pilot v1） | `TelemetryFrame` mapper 发布经验证的 linear/angular/orientation 变换及 availability；缺失字段仍使用 `None` |
| RR-202 | 已完成（keyboard spike） | deny-by-default guard 仅允许指定 pilot 的 TRACK_TEST / GREEN / PLAYER；多人、排名、竞赛、回放、暂停、菜单和 garage 均拒绝 |
| RR-204 | 已完成（低速 keyboard spike） | 扫描码控制回授、Q/Z 挡位切换和安全制动通过；vJoy 路径仍按原计划单独验证 |

## AC 基线命令

当前基线使用已有最终模型，复现命令为：

```powershell
C:\Users\freedom\anaconda3\envs\p309\python.exe run_demo_lap.py `
  --checkpoint outputs\train_mx5cup_silverstone_400k_to_1m_resume\model\final `
  --track ks_silverstone-gp `
  --car ks_mazda_mx5_cup `
  --laps 3 `
  --output outputs\baseline_ac_m0_lap
```

基线清单记录了配置、模型、摘要、静态信息和完整 Parquet trace 的 SHA-256；
后续回归必须先校验哈希。若基线代码或资产发生变更，应创建新的 baseline ID，不能覆盖本清单。

## RaceRoom probe 命令

先在 RaceRoom 中启动无对手的 Track Test，再运行：

```powershell
C:\Users\freedom\anaconda3\envs\p309\python.exe scripts\raceroom_probe.py `
  --duration 60 `
  --pretty `
  --output outputs\raceroom_m1\probe_60s.json
```

完成 RR-104 前，`configs/raceroom.yml` 中 `raceroom_control` 必须保持 `false`。

## 首轮实测结果

- 进程：`RRRE64.exe`，文件版本 `0.9.7.81`。
- 模式：`game_mode=0` (`TRACK_TEST`)、`session_type=0` (`PRACTICE`)、`control_type=0` (`PLAYER`)。
- 组合：Audi RS 3 LMS TCR / Shanghai Circuit / Grand Prix。
- 官方 ID：car `11325`、track `2021`、layout `2027`。
- API：3.5，`all_drivers_offset=2008`，`driver_data_size=328`。
- 采样：3.002 秒，1,127 个新帧，约 375.6 Hz；14 次撕裂重读被一致性机制成功拦截。
- 报告：`outputs/raceroom_m1/probe_shanghai_rs3tcr_3s.json`（outputs 默认不纳入 Git）。
- 静止 fixture：5.001 秒、1,853 行；最大速度约 `5.48e-7 m/s`，位置跨度低于 `2.8e-6 m`，符合静止基线。
- 两次标记为 straight 的试录中油门、转向和制动均为零，车辆无位移；已判为无效直行样本并保留作诊断，不用于轴向结论。

## 键盘控制 spike

用户在 RaceRoom 正常控制设置中绑定：方向键控制油门、制动和转向，`Q` 升档，`Z` 降档。
测试入口必须显式传入 `--armed`，并同时满足 session guard、pilot ID、前台 PID 和最高速度限制。

- 普通 virtual-key 输入未被 RaceRoom 接收；改用标准键盘扫描码后回授正常。
- 左转回授：`-0.8750`；右转回授：`+0.6687`。
- 油门回授：`1.0`；制动回授：`1.0`。
- `Q`：1 挡升至 2 挡；`Z`：2 挡降回 1 挡。
- 测试最高速度：`0.2333 m/s`；结束速度：`0.0064 m/s`；结束挡位：1。
- 结果：`outputs/raceroom_m2/keyboard_control_test_scancode.json`（ignored output）。
- `Features.raceroom_control` 继续保持 `false`；当前入口仅用于显式 armed 的离线低速工程验证。

## RR-104 轴向结论

验证清单：`docs/baselines/raceroom_axis_validation_v1.json`。

- 直行速度与 `local_velocity_z` 的相关系数为 `-0.99995`：前向为 `-R3E Z`。
- 左转时 `local_velocity_x` 均值为正，右转时为负：左向为 `+R3E X`。
- R3E Y 为竖直线性轴；世界位置的水平面为 X/Z。
- 左转时 R3E local angular Y 为负，右转时为正；转换到 forward/left/up 后，正 yaw 定义为左转。
- 线性向量转换：`(-R3E Z, +R3E X, +R3E Y)`。
- 角速度转换：`(+R3E Z, -R3E X, -R3E Y)`；不能直接复用线性变换，因为坐标系换手性后伪向量需要额外符号。

真实 trace 已由 `RaceRoomTraceReplay` 成功打开并逐帧映射；首帧 sequence `606786`，
fixture 共 `7,492` 帧。M1 的字段、坐标和更新率决策门已初步通过，剩余退出项是 1 小时只读 soak。
