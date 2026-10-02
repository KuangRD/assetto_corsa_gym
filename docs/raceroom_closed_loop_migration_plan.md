# RaceRoom 闭环迁移完整计划

状态：Execution v2（M2 控制路径 No-Go，闭环交付阻塞）<br>
制定日期：2026-08-02  
最近更新：2026-08-03<br>
目标仓库：`assetto_corsa_gym`  
首个交付范围：一个 RaceRoom 车辆、一个赛道布局、25 Hz 状态控制闭环、无对手、无排名/多人模式

## 0. 当前执行结论（2026-08-03）

| 范围 | 状态 | 结论 |
|---|---|---|
| M0 基线/范围 | 部分完成 | AC 基线、pilot 组合、配置与 feature flag 已冻结；RR-004 官方书面确认仍待完成 |
| M1 只读遥测 | 首轮通过 | API 3.5 结构、稳定快照、约 375.6 Hz 实测、轴向验证、Parquet trace/replay 和 mapper 已完成；1 小时 soak 仍待执行 |
| M2 vJoy 控制 | **No-Go** | Windows/AC 可正常消费 vJoy，但 RaceRoom `0.9.7.81` 不枚举或绑定 vJoy；已触发原计划停止条件 |
| AC 回归 | 通过 | 同一 vJoy Device 1 的方向、油门、刹车、升降挡均获 AC 遥测回授，证明原 AC 控制链路未回归 |
| RaceRoom 闭环 | 阻塞 | 未获得游戏正常识别的受支持控制设备前，不进入真实 `apply/reset/train` 闭环 |

完整证据见 `docs/raceroom_vjoy_compatibility_20260803.md`，AC 实机回归原始结果见
`outputs/ac_vjoy_smoke_test.json`。当前继续推进只读遥测、trace replay、通用 Core、
AC adapter 回归和人工驾驶赛道资产；暂停依赖真实 RaceRoom 控制的标定、reset、
闭环 Gym 和训练任务。

## 1. 目标与完成标准

本项目的目标是将当前 Assetto Corsa Gym 的训练链路迁移为可扩展的多模拟器架构，并首先交付一个可持续训练的 RaceRoom 闭环环境：

```text
SAC / DisCor / Replay Buffer
            |
       RacingEnvCore
 observation / reward / termination / history
            |
      SimulatorAdapter
       |              |
 AssettoCorsa     RaceRoom
       |              |
 AC plugin        shared memory + supported input
                                  (vJoy currently blocked)
```

“完成”不是仅能读到遥测，而是同时满足：

1. Python 可以稳定读取 RaceRoom 新遥测帧，并转换成版本化的统一状态结构。
2. 策略动作可以通过 RaceRoom 正常识别的受支持控制设备控制方向、油门、刹车，
   控制方向和幅值经过标定；当前 vJoy 路径已实测失败，不能计为完成。
3. `env.step()` 以 25 Hz 工作，不重复消费旧帧，不因共享内存撕裂产生混合状态。
4. `env.reset()` 有可观测、可超时、可重试的状态机；失败时安全停车并返回明确错误。
5. 一个车辆/赛道组合具备 RaceRoom 原生参考线、左右边界、占用栅格和车辆控制标定。
6. RaceRoom 原生 observation schema 可以从零开始训练 SAC，并稳定完成连续圈。
7. 原有 AC 入口和训练行为不发生非预期回归。
8. 控制适配器在 RaceRoom 多人、排名或竞赛模式下强制拒绝启用。

## 2. 明确不在首个 MVP 中的范围

- 不迁移已有 AC checkpoint 并宣称可以零样本直接驾驶 RaceRoom。
- 不支持 RaceRoom 排名、多人服务器或官方竞赛。
- 不通过注入、修改游戏文件、读取非公开内存或绕过安全机制实现控制。
- 不在第一阶段支持多车对手状态、图像 observation、DRS、PTP、混合动力控制和完整维修站策略。
- 不在第一阶段支持并行启动多个 RaceRoom 实例。
- 不把 RaceRoom 缺失的四轮真实滑移角简单填零并伪装成 AC 等价状态。

## 3. 合规与安全边界

RaceRoom 官方 EULA 禁止在在线排名产品中使用 AI bot、宏和其他作弊方式。本项目必须遵守以下硬约束：

- 只允许 `TRACKTEST`、明确的单机练习或经 RaceRoom 书面许可的研究模式。
- `RaceRoomAdapter.connect()` 必须读取 `game_mode`、`session_type` 和 `control_type`。
- 检测到 multiplayer、ranked、competition 或未知模式时，控制后端保持禁用并抛出 `UnsafeSessionError`。
- 遥测只使用官方 `$R3E` shared memory API。
- 控制只使用游戏正常识别的虚拟控制器设备和游戏内控制绑定。
- 如果 vJoy 被游戏或安全组件拒绝，不采用 DLL 注入、内存写入或协议模拟等替代方案。
- 所有自动控制运行日志记录游戏模式、赛道 ID、车辆 ID、适配器版本和安全互锁结果。

在 M2 开始前，建议向 RaceRoom/KW Studios 发出简短书面说明，确认离线自主驾驶研究和 vJoy 自动输入的允许范围。未收到回复不阻碍只读遥测开发，但不得进入在线环境。

## 4. 当前代码的主要耦合点

当前系统需要拆分以下职责：

| 当前位置 | 当前职责 | 迁移动作 |
|---|---|---|
| `AssettoCorsaEnv/ac_env.py` | Gym API、状态扩展、奖励、终止、历史、AC 客户端 | 拆出 `RacingEnvCore`，AC 特有字段放回 AC adapter/mapper |
| `AssettoCorsaEnv/ac_client.py` | UDP 同步、vJoy、AC 管理 TCP、截图共享内存 | 拆分为 simulator adapter、通用控制后端和截图后端 |
| `AssettoCorsaPlugin/.../structures.py` | AC 原始字段采集和字段命名 | 保留为 AC adapter 的数据源，不再作为通用 schema |
| `AssettoCorsaPlugin/.../car_control.py` | vJoy 轴映射 | 提取为通用 `VJoyControlBackend`，增加标定和安全停车 |
| `AssettoCorsaConfigs` | AC 坐标系的赛道和车辆资产 | 新增按 simulator 隔离的 RaceRoom 资产根目录 |
| `train.py` | 硬编码创建 AC 环境 | 改为按 `simulator` 配置选择环境工厂 |

迁移采用“绞杀者”方式：先引入新接口和包装器，再逐步让 AC 走新接口；不进行一次性全量重写。

## 5. 目标目录结构

建议新增：

```text
assetto_corsa_gym/
  RacingEnv/
    __init__.py
    core_env.py
    types.py
    errors.py
    observation.py
    reward.py
    termination.py
    factory.py
    adapters/
      __init__.py
      base.py
      assetto_corsa.py
      raceroom.py
    controls/
      __init__.py
      base.py
      vjoy.py
      calibration.py
    capture/
      window_capture.py
    tracks/
      assets.py
      builder.py
      validation.py
  RaceRoom/
    __init__.py
    shared_memory.py
    structures.py
    mapper.py
    reset_controller.py
    session_guard.py
    constants.py
    version.py

configs/
  raceroom.yml

scripts/
  raceroom_probe.py
  raceroom_control_calibration.py
  raceroom_collect_track.py
  raceroom_build_track.py
  raceroom_validate_adapter.py

tests/
  unit/racing_env/
  unit/raceroom/
  integration/raceroom/

data/raceroom/
  cars/<car_id>/
    controls.yml
    geometry.yml
  tracks/<track_id>-<layout_id>/
    manifest.yml
    reference_line.csv
    borders.csv
    occupancy_0.1m.pkl
```

最终名称可在实现时按现有包风格微调，但 simulator-neutral 与 RaceRoom-specific 代码必须物理分离。

## 6. 核心接口设计

### 6.1 统一遥测帧

在 `RacingEnv/types.py` 中定义不可变、带版本号的数据类：

```python
@dataclass(frozen=True)
class TelemetryFrame:
    schema_version: str
    simulator: str
    sequence: int
    simulation_time_s: float
    received_at_s: float

    speed_mps: float
    rpm: float
    gear: int

    position_xyz_m: np.ndarray | None
    orientation_rpy_rad: np.ndarray | None
    local_velocity_xyz_mps: np.ndarray
    local_acceleration_xyz_mps2: np.ndarray
    local_angular_velocity_xyz_radps: np.ndarray

    steering_normalized: float
    throttle_normalized: float
    brake_normalized: float
    ffb_normalized: float | None

    lap_fraction: float
    completed_laps: int
    lap_valid: bool | None
    in_pitlane: bool | None
    game_mode: int
    session_phase: int
    control_type: int

    raw: Mapping[str, Any]
```

约束：

- 所有物理单位在 adapter 层完成转换；Core 不接触 `engine_rps`、G 值或游戏轴方向。
- 缺失值使用 `None` 和 availability mask，不使用静默填零。
- `raw` 只用于调试和落盘，不允许 reward/observation 直接依赖它。
- `sequence` 对 RaceRoom 使用 `player.game_simulation_ticks`，不能使用 Python 本地计数替代。

### 6.2 SimulatorAdapter

```python
class SimulatorAdapter(Protocol):
    def connect(self) -> StaticSessionInfo: ...
    def close(self) -> None: ...
    def wait_for_frame(self, after_sequence: int, timeout_s: float) -> TelemetryFrame: ...
    def apply_action(self, action: DriverAction) -> AppliedAction: ...
    def reset(self, request: ResetRequest) -> ResetResult: ...
    def emergency_stop(self, reason: str) -> None: ...
    def health(self) -> AdapterHealth: ...
```

Core 的 `step()` 顺序固定为：

1. 预处理并限幅 action。
2. adapter 写入动作。
3. 等待 `sequence > last_sequence` 的目标遥测帧。
4. 将 frame 转换为 observation、reward、terminated/truncated。
5. 记录动作写入时间、帧时间和端到端延迟。

### 6.3 控制接口

通用 `DriverAction` 使用：

```text
steering: [-1, 1]
throttle: [0, 1]
brake:    [0, 1]
clutch:   optional [0, 1]
shift_up/down: optional edge-triggered bool
```

AC 目前内部把油门和刹车表示为 `[-1, 1]`。兼容转换只能留在 AC wrapper 中；新 Core 和数据集一律采用踏板 `[0, 1]`。

### 6.4 TrackProvider

Core 只能通过 `TrackProvider` 获取：

- 赛道长度。
- 参考线和参考速度。
- 左右边界。
- 占用栅格。
- 世界坐标到 Frenet/圈距离的映射。
- 资产版本、来源模拟器、track/layout ID 和坐标变换元数据。

不得根据赛道名称误用 AC 资产。即使两个模拟器都有同名赛道，也必须视为不同坐标资产。

## 7. RaceRoom 遥测映射

第一版字段映射如下；所有轴向在 M1 实车验证后才能冻结：

| 通用/现有特征 | RaceRoom 官方字段 | 转换/说明 |
|---|---|---|
| sequence | `player.game_simulation_ticks` | 1 tick = 1/400 s |
| simulation time | `player.game_simulation_time` | 秒 |
| speed | `car_speed` | 已是 m/s；与局部纵向速度交叉验证 |
| RPM | `engine_rps` | `rps * 60 / (2*pi)` |
| gear | `gear` | 保留 RaceRoom 约定并在 mapper 标准化倒挡/空挡 |
| world position | `player.position` | 预计使用水平 X/Z，必须通过静止、直行、转弯实验确认 |
| orientation | `player.orientation` / `car_orientation` | 确认欧拉顺序、符号和 wrap |
| local velocity | `player.local_velocity` | 验证前向、左向、上向轴 |
| local acceleration | `player.local_acceleration` | m/s²；旧 AC observation 若用 G，则在 observation 层除以 9.80665 |
| angular velocity | `player.local_angular_velocity` | 确认 yaw 轴 |
| FFB | `player.steering_force_percentage` | 标定符号和范围后裁剪 |
| steering feedback | `steer_input_raw` | `[-1,1]` |
| throttle/brake feedback | `throttle_raw`, `brake_raw` | `[0,1]`，同时记录处理后的字段用于诊断 |
| lap fraction | `lap_distance_fraction` | `[0,1]`；无效值 `-1` 转为 unavailable |
| lap count | `completed_laps` | 整数 |
| lap valid | `current_lap_valid` / `lap_valid_state` | 建立明确 truth table |
| pit status | `in_pitlane`, `pit_state` | 用于 reset 和 episode guard |
| session | `game_mode`, `session_type`, `session_phase` | 安全互锁和生命周期 |
| steering range | `steer_lock_degrees`, `steer_wheel_range_degrees` | 与实际 vJoy 标定交叉验证 |

### 7.1 共享内存一致性

共享内存没有 AC UDP 请求/响应式的天然帧边界。读取器必须：

1. 打开官方 `$R3E` memory map。
2. 校验 major/minor 版本和结构体大小。
3. 读取起始 `game_simulation_ticks`。
4. 将整个结构复制到本地 buffer。
5. 再次读取 tick；若改变则重试。
6. 只发布 tick 前后一致的快照。
7. 对相同 tick 去重，对倒退 tick 识别为 session reset/restart。

控制目标是 25 Hz。由于 RaceRoom 物理 tick 为 400 Hz，默认每消费约 16 个物理 tick 发布一步；实际共享内存发布频率需在 M1 测量，不提前假定能读取每一个物理 tick。

### 7.2 缺失的四轮滑移角

推荐新增 `raceroom_native_v1` observation schema，不保持虚假的 AC 23-channel 等价。推荐替换为：

- 车身侧滑角 `beta = atan2(v_lateral, max(abs(v_longitudinal), eps))`。
- 横摆角速度。
- 前轴估算滑移角。
- 后轴估算滑移角。

估算模型需要车辆轴距、质心到前后轴距离和方向盘到前轮转角比：

```text
alpha_front = atan2(v_lat + lf * yaw_rate, |v_long|) - road_wheel_angle
alpha_rear  = atan2(v_lat - lr * yaw_rate, |v_long|)
```

`legacy_ac_compat` 可以作为研究性 ablation，把前/后轴估算复制到左右轮，但不得作为默认 schema，也不得认为与 AC 真值等价。

## 8. 控制与标定计划（vJoy 路径已阻塞）

2026-08-03 实测已经触发本计划的 vJoy 停止条件。vJoy 2.1.9 Device 1 可由
`joy.cpl` 和 Assetto Corsa 正常消费，但 RaceRoom 在前台绑定、持续输入、启动前持有
设备、原生 `Custom Wheel` 方案和设备缓存重建后仍不接收轴或按钮。RaceRoom 新建
方案保持 `Device Count="0"`，显式方案显示 `DISCONNECTED`。

以下 8.1–8.3 保留为目标设计和 AC 可复用能力，不代表 RaceRoom 控制已获准继续。

### 8.1 通用化现有控制代码

将当前 `car_control.py` 中的 vJoy 细节提取为 `VJoyControlBackend`：

- 设备 ID 可配置，不默认抢占用户方向盘设备。
- 每个轴具有 `min/center/max/inverted/deadzone`。
- 轴写入前做 finite check、clip 和 rate limit。
- 提供 `neutral()`, `safe_brake()`, `release()`。
- 进程退出、异常、遥测超时都调用 `safe_brake()`。
- 按钮使用 edge-trigger，避免换挡/复位按钮长按。

### 8.2 RaceRoom 控制标定脚本

状态：暂停。只有满足 8.4 的解锁条件后才恢复。

`raceroom_control_calibration.py` 分步完成：

1. 检测 vJoy 设备存在且未被其他进程占用。
2. 用户在 RaceRoom 正常控制设置中绑定方向、油门、刹车和复位按钮。
3. 脚本写入已知轴序列，读取 `steer_input_raw/throttle_raw/brake_raw` 回授。
4. 自动求方向、最小值、最大值、中心、死区和非线性。
5. 保存到 `data/raceroom/cars/<car_id>/controls.yml`。
6. 执行小幅方向、10% 油门、10% 刹车的低风险验证。

### 8.3 控制安全规则

- 遥测超过 250 ms 未更新：油门 0、方向回中、制动到安全值。
- Python 收到 `KeyboardInterrupt`、adapter error 或 NaN action：立即安全停车。
- session guard 失效：立即禁用所有动作。
- 油门和刹车同时高于阈值时记录告警；可配置是否允许 trail braking overlap。
- 第一次闭环测试必须在低速、无对手、宽阔赛道区域完成。

### 8.4 控制路径解锁条件

恢复 RR-203 及后续真实控制任务前，必须至少满足一项：

1. KW Studios 书面确认并给出当前版本支持的虚拟/外部控制输入配置，按正常游戏
   绑定完成端到端回授；或
2. 用户单独批准一个表现为普通物理 USB HID 的硬件桥接方案，并完成新的安全、
   合规和延迟评审。

键盘扫描码只允许离线低速工程 spike。它是数字输入，不满足连续方向/油门/刹车的
训练控制要求，不能用来绕过本决策门。不得把 DLL 注入、内存写入、反作弊绕过或
在线模式测试列为候选解锁路线。

## 9. Reset 状态机

RaceRoom 没有当前 AC 插件提供的管理 TCP reset API。M1/M2 技术验证必须确认游戏正常控制绑定中可用的复位/返回赛道行为。初始实现只允许正常绑定按钮，不做窗口菜单脚本。

状态机：

```text
READY
  -> NEUTRALIZE
  -> REQUEST_RESET
  -> WAIT_TRANSITION
  -> WAIT_VALID_SESSION
  -> WAIT_STABLE_POSITION
  -> WARMUP_HISTORY
  -> READY

任意状态超时 -> RETRY（最多 N 次） -> FAILED_SAFE_STOP
```

判定信号包括：

- tick 继续前进，而不是游戏暂停或退出。
- 世界坐标出现符合复位的跳变，或 pit/session 状态发生预期变化。
- `control_type == PLAYER`。
- 不在回放、garage countdown、结束 session 或未知 phase。
- 连续若干帧速度低于阈值且位置稳定。
- `lap_distance_fraction` 恢复有效。

Reset 后必须：

- 清空 observation history、past actions、低速终止计数和 episode 累积量。
- 保持油门 0、制动安全值，直到 Core 开始 warmup。
- 消费至少 `PAST_ACTIONS_WINDOW + 1` 个新帧再返回初始 observation。
- 返回 reset 耗时、重试次数和触发策略到 `info`。

如果游戏只支持返回维修站且存在不可跳过等待，M4 的备选方案是使用更长 episode、减少 reset 次数，并把 session restart 交给人工/外层 runner；不通过非公开手段绕过等待。

## 10. 赛道资产生成

### 10.1 首条赛道采集流程

选定一个用户已拥有、布局简单、无混合路面、适合低速标定的道路赛道，以及一辆无复杂混动/DRS 的车辆。具体组合在 M0 冻结为 `<pilot_car_id>` 与 `<pilot_track_id>-<layout_id>`。

采集三类干净数据：

1. 参考线：人工或稳定控制器完成至少 3 圈，选择有效且平滑的一圈。
2. 左边界：低速沿允许驾驶表面的左边缘完成一圈。
3. 右边界：低速沿允许驾驶表面的右边缘完成一圈。

每条样本至少记录：tick、世界坐标、姿态、lap fraction、速度、lap valid、控制输入和 track/layout ID。

### 10.2 后处理

- 根据 lap fraction 和累计弧长排序、去重。
- 去除复位、进站、倒车和无效跳点。
- 将 3D 坐标投影到经验证的水平平面。
- 统一顺/逆时针方向和起终点。
- 以固定弧长间隔重采样。
- 对左右边界做自交、宽度、突变和左右翻转检查。
- 构建与当前格式兼容的 CSV 和 0.1 m occupancy grid。
- 保存采集版本、API 版本、游戏版本、车辆 ID、track/layout ID、坐标轴定义和源 trace hash。

### 10.3 资产验收

- 参考线所有点位于左右边界之间。
- 赛道宽度无负值，异常宽度点必须人工复核。
- 人工正常圈的世界坐标至少 99.9% 位于 occupancy grid 内。
- 明确出界样本至少 95% 被判为 grid 外。
- ray casting 方向与驾驶视角一致，不发生镜像。
- `lap_distance_fraction * layout_length` 与参考线累计弧长误差有报告，不静默覆盖官方长度。

## 11. Observation、奖励和终止迁移

### 11.1 Observation schema

每个数据集、checkpoint 和运行日志必须保存：

```text
simulator
observation_schema
observation_schema_version
action_schema_version
track_asset_version
car_calibration_version
```

推荐 `raceroom_native_v1` 包含：

- speed、RPM、gear。
- longitudinal/lateral acceleration。
- longitudinal/lateral local velocity。
- yaw rate、body slip、front/rear estimated slip。
- steering/throttle/brake feedback。
- FFB（若验证稳定）。
- ray distances。
- curvature lookahead。
- 当前 absolute action 和 past actions/history。
- out-of-track indicator 与 availability mask。

### 11.2 Reward

第一版继续使用“速度 × 参考线横向误差”的现有思想，但完成单位和范围校验：

- 速度始终使用 m/s，在 reward 内只做一次明确转换或完全取消 km/h 中间量。
- gap 使用 RaceRoom 自己的参考线坐标。
- 出界惩罚和终止必须区分游戏判定、lap invalid 与 occupancy 判定。
- action smoothness 使用通用动作 schema，避免受旧 `[-1,1]` 踏板定义影响。
- 所有 reward 分量分别写入 `info['reward_terms']`。

### 11.3 Termination

首版终止条件：

- 进入不安全/不支持的 session 模式。
- 共享内存断开或遥测 stale 超时。
- occupancy 出界，且经过连续帧 debounce。
- 低进度超时。
- 最大 step/lap 数。
- session 结束、返回 garage 或控制权不再属于 player。

RaceRoom 的 lap invalid 不应默认等价为立即终止；它可能由轻微赛道限制触发。行为应配置并通过采样数据确定。

## 12. 配置迁移

新配置建议：

```yaml
simulator: raceroom

Environment:
  control_hz: 25
  observation_schema: raceroom_native_v1
  action_schema: normalized_controls_v1
  max_episode_seconds: 600
  telemetry_timeout_ms: 250

RaceRoom:
  shared_memory_name: "$R3E"
  allowed_game_modes: [track_test]
  expected_api_major: 3
  vjoy_device_id: 1
  reset_button: null
  track_id: null
  layout_id: null
  car_id: null

Track:
  asset_root: data/raceroom
  occupancy_resolution_m: 0.1

Safety:
  refuse_multiplayer: true
  stale_action: safe_brake
  safe_brake_level: 0.5
```

保留旧 `AssettoCorsa` section，在 AC 完成 adapter 包装前不做破坏性重命名。`train.py` 通过 `RacingEnv.factory.make_env(config)` 创建环境。

## 13. 数据集和 checkpoint 策略

- 旧 AC 数据仍可用于算法回归测试，但不能直接装入 RaceRoom replay buffer，除非经过 schema 显式转换。
- RaceRoom trace 使用 Parquet 或明确 schema 的压缩格式；不新增不受信 pickle 数据交换格式。
- 数据转换器必须输出缺失字段统计、单位、裁剪率和无效帧数量。
- SAC actor/critic 输入维度由 observation schema 决定。
- 加载 checkpoint 时强校验 simulator、observation schema、action schema；不匹配默认拒绝。
- 可单独研究 AC 权重初始化，但必须使用 `--weights_only` 和显式的 feature adapter，并作为实验而非迁移主路径。

## 14. 测试计划

### 14.1 单元测试

- RaceRoom packed ctypes 结构体 size、offset 和 API version fixture。
- tick 一致性重读、重复帧去重、tick 倒退处理。
- 每个遥测字段的单位和符号转换。
- rps 到 RPM、m/s² 到 G、角度 wrap。
- session guard 对每个 game mode 的 allow/deny。
- vJoy 轴标定、限幅、反向、死区和 NaN 拒绝。
- reset 状态机所有成功、超时、重试、断连路径。
- observation schema 的固定顺序、维度、availability mask。
- checkpoint schema mismatch 拒绝。
- 赛道坐标、gap、occupancy 和 ray casting fixture。

### 14.2 无游戏集成测试

建立 RaceRoom trace replay adapter：

- 使用录制的共享内存帧回放，不要求启动游戏。
- 支持实时、加速和逐帧模式。
- 用于 CI 验证 Core、reward、termination 和 reset 之外的逻辑。
- fixture 必须去除玩家姓名、用户 ID 等无关个人信息。

### 14.3 游戏在环测试

| 测试 | 目标 |
|---|---|
| 静止 5 分钟 | 无虚假新帧、NaN、字段跳变和 CPU 忙等 |
| 低速直行/左右转 | 轴方向、yaw rate、世界坐标和方向反馈一致 |
| 踏板阶跃 | 命令与 raw feedback 单调，范围正确 |
| 1 小时只读 | 无内存泄漏、死锁和断连 |
| 90,000 step 闭环 | 25 Hz 连续运行 1 小时，无重复消费帧 |
| 50 次 reset | 统计成功率、p50/p95 时间和失败原因 |
| 人工有效/出界圈 | 验证 gap、occupancy、lap valid truth table |
| 随机低幅策略 | 安全停车、终止和 reset 完整工作 |
| SAC smoke train | replay buffer、更新、保存、加载和 evaluate 可用 |
| AC 回归 | 原 AC demo/train smoke test 不退化 |

### 14.4 性能验收目标

- 目标控制频率：25 Hz；1 小时测试无永久掉步或死锁。
- 新帧重复消费率：0。
- 非有限核心遥测字段：0。
- action 到可观测控制反馈延迟：测量并报告，目标 p95 不超过 80 ms。
- telemetry stale：正常运行中 p99 小于 100 ms；超过 250 ms 触发安全停车。
- reset：50 次成功率至少 95%；p95 小于 5 秒，或记录为模拟器不可消除的已知限制并调整训练设计。
- 单机模式安全互锁误放行：0。

## 15. 分阶段实施与里程碑

### M0：基线、范围冻结和开发环境（2–3 天）

任务：

- [x] RR-001 记录当前 AC 环境一次 reset、1000 step 和一圈 trace，作为回归基线。
- [x] RR-002 冻结 pilot car/track/layout，记录 RaceRoom 游戏版本和 shared memory API 版本。
- [ ] RR-003 确认控制设备、RaceRoom 控制绑定和单机测试模式。**阻塞：vJoy No-Go；Track Test 已确认。**
- [ ] RR-004 向 RaceRoom 发出离线研究使用确认请求。
- [x] RR-005 建立迁移配置、日志字段和 feature flag。

退出条件：可以稳定启动 pilot session；官方 shared memory 可见；不存在立即阻断的控制/许可问题。

### M1：RaceRoom 只读遥测 spike（4–6 天）

任务：

- [x] RR-101 按官方 v3.x header 实现 packed ctypes 结构。
- [x] RR-102 实现 memory map 生命周期、版本校验和一致性快照。
- [x] RR-103 实现 `raceroom_probe.py` 输出核心字段和更新频率统计。
- [x] RR-104 完成坐标轴、姿态、局部速度、角速度实验。
- [x] RR-105 建立原始 frame recorder 和 trace replay fixture。
- [x] RR-106 完成 `TelemetryFrame` mapper 与字段 availability 报告。

退出条件：连续只读 1 小时无错误；核心字段单位/轴向已验证；世界坐标可用于二维赛道映射。

停止条件：若官方 API 在实际版本不提供稳定的世界位置或 tick，则暂停 world-map 路线，先重新评审 observation/赛道方案。

### M2：vJoy 控制 spike 与安全互锁（3–5 天）

状态：**No-Go（2026-08-03）**。控制 feature flag 保持关闭；详见
`docs/raceroom_vjoy_compatibility_20260803.md`。

任务：

- [ ] RR-201 提取通用 vJoy backend。部分完成：SDK wrapper、轴/按钮探针和显式方案生成器已实现；生产级 rate limit/safe-brake 接口未完成。
- [x] RR-202 实现 RaceRoom session guard。
- [ ] RR-203 开发控制标定脚本和车辆 calibration 文件。**等待控制路径解锁。**
- [ ] RR-204 完成低速方向/油门/刹车闭环验证。键盘 spike 通过；vJoy 端到端失败，不能验收。
- [ ] RR-205 实现 stale telemetry、异常退出和 NaN action 安全停车。
- [ ] RR-206 测量动作到 raw feedback 延迟。

退出条件：控制单调、方向正确、可重复；安全互锁在所有禁止模式拒绝启用；紧急停车通过。

停止条件：若 vJoy 不被正常支持，或安全组件报警，则停止控制开发并联系 RaceRoom，不尝试绕过。

**停止条件已触发。** 在 8.4 解锁前，RR-203～RR-206 及所有真实 RaceRoom
控制依赖任务保持暂停。

### M3：通用 Core 与 Adapter 重构（6–9 天）

执行约束：可继续 RR-301、RR-302、RR-303、RR-306、RR-307 的离线/AC/trace
部分；RR-304 的 `apply` 只能保留禁用实现，不能宣称真实 RaceRoom adapter 完成。

任务：

- [ ] RR-301 新增通用 types/errors/adapter interfaces。
- [ ] RR-302 从 `ac_env.py` 提取 simulator-neutral observation/reward/termination/history。
- [ ] RR-303 为现有 AC client 编写兼容 adapter，保证旧入口仍可用。
- [ ] RR-304 实现 RaceRoom adapter 的 connect/wait/apply/health/close。
- [ ] RR-305 改造 factory 和 `train.py` 按 simulator 创建环境。
- [ ] RR-306 引入 schema version 和 checkpoint compatibility check。
- [ ] RR-307 建立 AC trace replay 回归和 RaceRoom trace replay 集成测试。

退出条件：AC smoke test 通过；RaceRoom trace replay 可运行 `reset/step` 核心逻辑；无游戏专属 raw 字段泄漏到 Core。

### M4：Reset 和 episode 生命周期（4–7 天）

状态：真实 RaceRoom reset 控制任务暂停；不依赖写入的状态机与 trace 测试可离线开发。

任务：

- [ ] RR-401 验证 RaceRoom 正常控制绑定支持的 reset/recover 行为。
- [ ] RR-402 实现 reset 状态机、超时、重试和安全失败。
- [ ] RR-403 处理 session restart、tick 倒退、garage、pause 和 replay。
- [ ] RR-404 reset 后正确 warmup history 和 applied actions。
- [ ] RR-405 执行 50 次 reset soak test，形成失败分类报告。

退出条件：reset 成功率达到门槛，或确认模拟器限制并批准长 episode 备选设计。

### M5：首条 RaceRoom 赛道资产（6–10 天）

执行约束：允许使用人工驾驶和只读遥测继续采集/构建资产，不依赖自动控制。

任务：

- [ ] RR-501 开发 track collector 并采集参考线/左右边界。
- [ ] RR-502 实现清洗、同步、重采样和坐标轴转换。
- [ ] RR-503 生成 RaceRoom track CSV、reference line 和 occupancy grid。
- [ ] RR-504 验证 gap、出界判定、ray casting 和 curvature lookahead。
- [ ] RR-505 创建 pilot car geometry/controls manifest。
- [ ] RR-506 版本化所有资产并保存 provenance。

退出条件：人工正常圈和出界样本达到资产验收指标；环境可输出完整 `raceroom_native_v1` observation。

### M6：闭环 Gym 与训练验证（5–8 天，不含长时间训练）

状态：暂停，等待 8.4 控制路径解锁。

任务：

- [ ] RR-601 打通真实游戏 `reset -> step -> reward -> done -> reset`。
- [ ] RR-602 完成随机低幅策略和人工回放动作测试。
- [ ] RR-603 采集 RaceRoom 原生 replay buffer/dataset。
- [ ] RR-604 从零运行 SAC smoke training、save/load/evaluate。
- [ ] RR-605 调整 observation scale、reward 分量和终止 debounce。
- [ ] RR-606 完成至少一个可重复完成连续圈的 checkpoint。

退出条件：训练曲线显示明确学习进展；策略能连续完成目标圈数；checkpoint 重载结果可复现。

### M7：稳定性、文档和交付（5–8 天）

任务：

- [ ] RR-701 运行 1 小时/90,000 step soak test。
- [ ] RR-702 完成性能、延迟、reset 和地图误差报告。
- [ ] RR-703 增加安装、RaceRoom 控制绑定、校准和故障排查文档。
- [ ] RR-704 增加 shared memory API version drift 检测说明。
- [ ] RR-705 完成 AC 回归矩阵和最终代码清理。
- [ ] RR-706 标记 MVP release，并列出图像、多车、换挡等下一阶段 backlog。

退出条件：满足第 1 节完成标准和第 14 节测试门槛。

## 16. 工期与资源估算

单名熟悉 Python、Windows shared memory、Gym 和虚拟控制器的工程师：

| 工作包 | 估算 |
|---|---:|
| M0 基线和环境 | 2–3 天 |
| M1 遥测 | 4–6 天 |
| M2 控制 | 3–5 天 |
| M3 Core 重构 | 6–9 天 |
| M4 Reset | 4–7 天 |
| M5 赛道资产 | 6–10 天 |
| M6 闭环训练工程 | 5–8 天 |
| M7 稳定和交付 | 5–8 天 |
| 合计 | 35–56 工程日 |

原始估算为 **7–10 周**，不包含长时间强化学习训练的纯计算时间。该估算现已暂停：
RaceRoom 控制输入成为外部依赖，在 8.4 解锁前不能给出可信的闭环交付日期。
只读遥测、Core/AC 重构和人工赛道资产仍可按原工作包估算推进。

所需环境：

- Windows 机器、RaceRoom、pilot 车辆/赛道内容。
- RaceRoom 正常识别的受支持控制设备。vJoy Device 1 已验证不满足当前版本要求。
- 稳定 60 FPS 或更高的游戏设置；记录实际掉帧。
- Python 训练环境和足够磁盘空间存储 raw trace/Parquet。
- 推荐训练与游戏进程 CPU affinity 分离；GPU 训练不得让游戏低于稳定实时帧率。

## 17. 主要风险和应对

| 风险 | 概率/影响 | 应对 |
|---|---|---|
| shared memory API 更新导致结构错位 | 中/高 | major/minor 和 sizeof/offset 校验；fixture；拒绝未知 major |
| 共享内存读取到撕裂帧 | 中/高 | tick 前后校验、复制快照、重试和统计 |
| 坐标轴/单位误解 | 中/高 | 静止/直行/转弯实验；所有变换单元测试化 |
| 没有四轮真实滑移角 | 高/中 | 使用 RaceRoom native schema 和轴级估算，重新训练 |
| Reset 不稳定或过慢 | 高/高 | 状态机；长 episode 备选；不采用非公开绕过手段 |
| RaceRoom 不枚举 vJoy | 已发生/高 | M2 No-Go；保持控制关闭；联系 KW Studios；仅在 8.4 条件满足后恢复 |
| 游戏与训练争抢 CPU/GPU | 中/中 | affinity、降低训练并发、记录帧率和 stale telemetry |
| AC 重构回归 | 中/高 | adapter 包装、trace replay、旧入口 smoke test |
| 赛道边界采集误差 | 中/高 | 三轨迹采集、可视化 QA、人工异常复核 |
| 在线误用导致账号风险 | 低/极高 | game mode 硬互锁、默认 deny、日志和文档警告 |
| AC 数据导致负迁移 | 中/中 | schema 强校验；RaceRoom 从零训练作为基线 |

## 18. 关键决策门

在以下节点必须明确作出 go/no-go 决策：

1. **M1 后：**世界坐标是否稳定、轴向是否可验证、共享内存实际更新率是否满足 25 Hz。
2. **M2 后：No-Go 已记录。** 当前 RaceRoom 不正常支持本机 vJoy 路径；闭环暂停，等待 8.4 解锁。
3. **M4 后：**reset 是否满足训练吞吐；若不满足，是否接受长 episode 设计。
4. **M5 后：**赛道资产误差是否足以支撑 gap/ray/out-of-track；若不满足，是否切换到视觉或弱地图 observation。
5. **M6 后：**RaceRoom native schema 是否出现学习进展；若没有，先检查控制和 reward，不直接扩大训练预算。

## 19. MVP 后续 backlog

按优先级排列：

1. 第二辆车和第二条赛道，验证 adapter/asset 泛化。
2. 手动换挡、离合和起步状态机。
3. 图像 observation：窗口标题配置化，由 Python adapter 定时触发截图。
4. RaceRoom opponents 数据和多车 observation。
5. 多任务 track/car ID 和统一数据集。
6. AC-to-RaceRoom 权重初始化与 domain randomization 实验。
7. 远端训练机/本地游戏机通信；保持游戏侧只使用官方 shared memory 和正常输入设备。
8. RaceRoom API 更新自动兼容检查和 release fixture 更新流程。

## 20. 下一批实际执行任务（2026-08-03 修订）

按以下顺序继续：

1. RR-004：以 `docs/raceroom_vjoy_compatibility_20260803.md` 为附件依据，向
   KW Studios 询问离线研究许可和当前版本支持的控制输入方案。
2. 完成 M1 一小时只读 soak，冻结更新率、撕裂重试、timeout 和版本基线。
3. 推进 M3 中不依赖 RaceRoom 写入的 Core、AC adapter、schema 和 trace replay 工作。
4. 使用人工驾驶推进 M5 的上海 GP 参考线、边界和 occupancy 资产。
5. 用户明确批准控制硬件/方案扩展后，按 8.4 重新打开 RR-003/RR-203；建立新的
   设备识别、标定、延迟和安全报告。
6. 只有控制决策门重新通过后，才恢复 M4 真实 reset、M6 闭环 Gym 和训练验证。

当前优先级是保存已经通过的只读和 AC 能力，同时隔离失败的 RaceRoom 控制路径，
避免把键盘 spike 或手工 `.rcs` 方案误报为闭环完成。
