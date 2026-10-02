# RaceRoom / vJoy 兼容性验证报告

验证日期：2026-08-03（PDT）

## 结论

在当前机器和游戏版本中，RaceRoom Racing Experience 不会把 vJoy Device 1
作为可绑定的控制输入。Windows 能正常接收同一设备的轴和按钮输入，因此故障边界
位于 RaceRoom 的控制设备枚举/输入层，而不是策略映射、vJoy SDK 写入或
Windows HID 层。

按闭环迁移计划的停止条件，vJoy 控制路径停止推进：

- `Features.raceroom_control` 保持 `false`；
- `RaceRoom.vjoy_device_id` 保持 `null`；
- 不进入多人、排名、竞赛或匹配模式验证；
- 不采用 DLL 注入、内存写入、反作弊绕过或协议模拟；
- 键盘扫描码路径仅保留为离线低速工程 spike，不视为连续控制后端。

## 验证环境

- RaceRoom：`0.9.7.81`
- Shared Memory API：3.5
- vJoy driver/interface：`0x0219`（2.1.9）
- vJoy Device 1：X/Y/Z/RX/RY/RZ/Slider0/Slider1，8 buttons
- Pilot：Audi RS 3 LMS TCR / Shanghai Circuit / Grand Prix
- 允许模式：离线 Track Test

## 已验证事实

### Windows 和 vJoy SDK

- `vJoyEnabled()` 返回 true。
- Device 1 空闲时为 `FREE`，被测试进程持有时为 `BUSY`。
- X/Y/Z 范围均为 `(0, 32767)`。
- `scripts/vjoy_probe.py` 通过 `vJoyInterface.dll` 发送
  `50% -> 80% -> 20% -> 50%` 时，`joy.cpl` 实时响应。
- vJoyFeeder GUI 的数值与 `joy.cpl` 不一致；直接 SDK 探针可绕过 Feeder，
  说明 Feeder 本身也存在异常，但这不是 RaceRoom 失败的唯一原因。

### RaceRoom

- 原 `device_statistics.xml` 曾记录 `vJoy Device`，device ID 为
  `3199013428`，且 `hasBeenConnected=true`、`hasBeenEvaluated=true`。
- 从键盘方案创建的 `vJoy_RL_Research.rcs` 始终为
  `Device Count="0"`；方向轴和 Button 1 均无法在绑定页面触发。
- 显式方案使用 `Device Count="1"`、设备 ID `3199013428` 及 X/Y/Z、
  Button 1/2 控制元组；RaceRoom 仍显示 `DISCONNECTED`。
- 已测试 RaceRoom 前台、延迟脉冲、连续脉冲、Button 1、启动前持续持有
  Device 1，以及从 `Custom Wheel` 复制原生方案；均不能生成设备关联。
- 重新生成的 `vJoy_RL_Native.rcs` 仍为 `Device Count="0"`。
- 备份并移走 `device_statistics.xml` 后，在 vJoy 已被持续持有的条件下重启
  RaceRoom；新设备缓存没有重新枚举 vJoy，绑定页面仍不响应。
- 同一绑定页面可以正常绑定本机键盘，排除了页面未监听和前台焦点问题。

## 产生的诊断资产

- `assetto_corsa_gym/RacingEnv/controls/vjoy.py`：依赖零第三方包的 vJoy SDK 包装。
- `scripts/vjoy_probe.py`：默认只读、需要 `--armed` 才能输出的轴/按钮探针。
- `scripts/build_raceroom_vjoy_profile.py`：显式 `.rcs` 方案生成器。
- `output/raceroom/vJoy_RL_Research_Explicit.rcs`：失败复现实验方案。

RaceRoom 原设备缓存的可恢复备份：

`C:\Users\freedom\Documents\My Games\SimBin\RaceRoom Racing Experience\UserData\device_statistics.xml.bak_20260803_003850`

## 后续决策选项

1. 将本报告和控制器信息提交给 KW Studios HelpDesk，确认当前版本是否有意
   拒绝 vJoy，或是否存在受支持的虚拟 DirectInput 配置。
2. 经单独批准后，评估表现为普通物理 USB HID 的硬件桥接器；这是硬件/架构
   范围扩展，不能作为 vJoy 的静默替代。
3. 继续完成只读遥测、trace replay、赛道资产和环境接口工作；控制里程碑保持
   阻塞，不能宣称已经形成 RaceRoom 闭环。

## Assetto Corsa 回归验证

RaceRoom 兼容性测试结束后，使用同一 vJoy Device 1 在正在运行的离线
Assetto Corsa 会话中执行了静止控制回归。AC 插件 2345/2347 服务正常，
测试全程保持全刹车：

- 左/右方向回授：`-97.2°` / `+97.2°`；
- 轻油门命令回授：`0.25`；
- 制动命令回授：`1.0`；
- 挡位：1 挡经 Button 1 升至 2 挡，再经 Button 2 降回 1 挡；
- 最大车速：`0.004520657 m/s`；
- vJoy 测试后状态：`FREE`。

结果文件：`outputs/ac_vjoy_smoke_test.json`。这证明 RaceRoom 失败没有破坏
Assetto Corsa 原有的 vJoy 控制链路。
