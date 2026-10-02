# Assetto Corsa、RaceRoom 与 iRacing 的 Racing Line 生成逻辑调研

更新日期：2026-08-04<br>
适用项目：`assetto_corsa_gym` 及其 RaceRoom 迁移<br>
证据等级：A = 官方资料或本机文件直接验证；B = 可复现的文件格式/社区工具；C = 根据产品行为和公开线索作出的工程推断

## 1. 先明确“racing line”指什么

模拟器里至少有四种不同对象经常都被叫作 racing line：

1. **驾驶辅助线**：画在地面上的彩色线，提示加速、滑行和制动。
2. **AI 基准路径**：赛道坐标中的中心 spline/waypoint，AI 正常情况下沿它行驶。
3. **车辆最短圈轨迹**：给定车辆、配置、轮胎和环境后，使圈时最小的轨迹与速度剖面。
4. **比赛中的实际走线**：考虑防守、超车、跟车、湿地、轮胎和其他车辆后，实时偏离基准路径的轨迹。

这四者不能互换。尤其是“AI 能沿线开完一圈”，不等于“该线是这辆车的数学最优线”。

## 2. 核心结论

| 模拟器 | 基准几何线的粒度 | 车型差异如何进入 | 是否公开精确算法 | 对“每车×每场地”的判断 |
|---|---|---|---|---|
| Assetto Corsa | 主要是**每赛道布局一条 `fast_lane.ai`** | 车辆物理、AI 车辆参数、难度、赛道 hint 和运行时控制 | 文件结构可读，控制算法闭源 | 不应认为原生内容为每辆车保存独立几何线；更多是共用几何线、按车计算可行速度和控制 |
| RaceRoom | 闭源的赛道/AI 资产，公开接口不导出路径 | 车辆/组别性能、固定难度或 Adaptive AI 选出的难度、运行时竞赛逻辑 | 未公开 | Adaptive AI 学的是**圈速与 AI skill 的对应关系**，没有证据表明它为玩家重生成几何线 |
| iRacing | 闭源的 ideal/pace line 与可选位置空间 | 官方分别“训练”车辆和赛道；skill、optimism、smoothness、轮胎/路面及实时位置决策影响线路和速度 | 未公开 | 车辆与赛道都有专门内容训练，但公开证据不足以断言为每个笛卡尔组合保存一条静态线；更像可组合模型加专项调校 |

最重要的工程结论是：**真正的最短圈轨迹必然依赖车辆；三款游戏却都没有通过公开接口提供完整的“每车×每场地最优轨迹数据库”。** 若本项目需要这种数据，应自行生成或从实跑遥测估计，而不是把游戏 AI 线当作真值。

## 3. Assetto Corsa

### 3.1 已验证的文件组织

证据等级 A：本机 Kunos 内容中，Monza 的文件位于：

```text
content/tracks/monza/ai/fast_lane.ai
content/tracks/monza/ai/pit_lane.ai
content/tracks/monza/data/ai_hints.ini
```

这些文件属于赛道/布局目录，不属于车型目录。因此同一布局默认由所有车辆共用同一个 `fast_lane.ai`。

本仓库也直接读取这一文件：

- `AssettoCorsaPlugin/plugins/sensors_par/structures.py` 从 `content/tracks/<track>/<layout>/ai/fast_lane.ai` 读取 spline。
- `AssettoCorsaEnv/ac_client.py` 把它导出为 `track-layout-racing_line.csv`，车型后缀目前被注释，并留有 `TODO check if this is car dependent`。
- `AssettoCorsaConfigs/tracks/config.yaml` 也是按赛道布局选择一个 `ref_lap_file`，不是按车型选择。

### 3.2 `fast_lane.ai` 是怎么生成的

证据等级 B：AC 的制作者流程不是让游戏离线求解一个车辆动力学最优控制问题，而是：

1. 在游戏中驾驶并开启 AI line 录制。
2. 完成一圈后产生 `fast_lane.ai.candidate`。
3. 将 candidate 作为正式 `fast_lane.ai`，再用 AI Spline Editor 修正和平滑。
4. 单独录制 `pit_lane.ai`；必要时补充左右边界和 `ai_hints.ini`。

AssettoServer 的公开文档同样要求先“recording splines”，再在 Blender 或工具中裁剪、优化和建立 junction；这进一步说明 spline 是创作者录制/编辑的资产，而不是每次加载时在线求出的最短圈轨迹：

- https://assettoserver.org/docs/next/ai-splines/junctions_guide/

### 3.3 文件里包含什么

证据等级 B：本仓库的解析器把文件拆成：

```text
header: 4 × int32
base point[N]: x, y, z, cumulative_distance, id
detail payload[N]: 18 × float32
new-format auxiliary/grid payload
```

当前代码从 detail payload 中读取或推断：

- 参考速度类字段；
- 油门、制动类字段；
- 行进方向/切向量；
- 左右可用宽度。

本机原版 Monza 文件为 header version 7、3750 个 base points。需要注意，18 个 payload 字段的完整官方语义没有公开；本仓库的字段命名属于社区逆向，不应把每个 float 都当成稳定 API。

### 3.4 车型差异如何进入

最可信的运行模型是：

```text
赛道 fast_lane spline
      + 赛道 ai_hints / danger 区段
      + 当前车型动力学与 AI 参数
      + AI strength / aggression
      + 当前轮胎、损伤、交通状态
      -> 前视目标点、目标速度、转向/油门/制动
```

因此：

- **几何基准线主要是赛道级的**；
- **目标速度和控制输出是车辆相关的**；
- 很慢的街车、GT3 和高下压力方程式赛车理论上应有不同最优线，但原生 AC 并没有为它们各存一条独立 `fast_lane.ai`；
- 极端车型在同一 spline 上表现差时，社区通常修 `fast_lane.ai`、边界或 `ai_hints.ini`，而不是调用一个公开的 per-car 最短圈求解器。

### 3.5 驾驶辅助线

公开证据不足以证明 AC 的彩色理想线会针对当前车辆重新求解几何轨迹。结合单一的赛道 `fast_lane.ai` 和其 payload，更合理的判断是：辅助线以赛道录制线为基础，颜色/制动提示来自记录数据或运行时缩放。它不能作为“当前车的精确最优线”。

### 3.6 结论与置信度

- “一条布局线供多车使用”：高置信度，A。
- “线由人驾驶录制并编辑”：高置信度，B。
- “运行时按车辆物理重算可行速度/控制”：高置信度，但具体公式闭源，B/C。
- “每车都有独立原生最优几何线”：没有证据，且文件组织与此相反。

## 4. RaceRoom Racing Experience

### 4.1 公开接口能看到什么

证据等级 A：官方 `$R3E` shared memory 提供：

- `track_id`、`layout_id`、`layout_length`；
- 玩家世界坐标、姿态、局部速度/加速度；
- `lap_distance`、`lap_distance_fraction`；
- 车辆、组别、控制和 session 状态。

它不提供：

- track centerline / left-right boundary；
- AI ideal line；
- 辅助线顶点；
- AI 的目标速度剖面。

本机安装的赛道核心内容在 `GameData/General/tracks.jca` 等封装资产中，没有官方的 AI line 导出工具。因此通过合规公开接口无法直接枚举全部原生线路。

### 4.2 Adaptive AI 到底适配什么

官方只宣称 Adaptive AI 会在每场比赛后根据玩家表现调整难度：

- https://www.raceroom.com/en/content_features/

社区可检查的 `aiadaptation.xml` 给出更具体的结构：

```xml
<key type="int32">...</key>
<playerBestLapTimes>
  <custom type="float32">...</custom>
</playerBestLapTimes>
<aiSkillVsLapTimes>
  ...
</aiSkillVsLapTimes>
```

也就是说，它保存的是玩家圈速样本以及 AI skill 与圈速的映射。更新记录还曾修复大型 `aiadaptation.xml` 在单机赛后造成的卡顿，佐证这些数据是在赛后更新：

- https://steamdb.info/patchnotes/7330489/
- 示例结构：https://steamcommunity.com/app/211500/discussions/1/601914519534459951/

因此 Adaptive AI 的逻辑应理解为：

```text
输入：当前赛道/布局、车辆或车辆组别、玩家有效圈速历史
查表/插值：估计能匹配玩家圈速的 AI skill
比赛开始前：选定难度或难度分布
比赛中：使用该难度运行原有 AI 驾驶与竞赛逻辑
比赛结束后：追加/更新圈速—skill 样本
```

它不是在线模仿学习，也没有公开证据表明它会从玩家轨迹生成新的几何 racing line。

### 4.3 原生 AI 走线的合理结构

以下为证据等级 C 的工程推断，不是 KW Studios 公布的源代码：

1. 每个赛道布局有内部导航/路径资产和赛道宽度信息。
2. 每个车辆或组别有性能模型，使目标速度、制动点和可实现横向加速度不同。
3. AI difficulty 对目标圈速、制动裕量、油门使用或路径“最优程度”作缩放。
4. 比赛中另有空间感知、跟车、超车、防守和碰撞规避状态机，使实际轨迹偏离基准线。

这与 RaceRoom 长期更新日志中“spatial awareness”“随机性能因子”“pit strategy”等相符，但具体路径优化器、代价函数和控制器没有公开。

### 4.4 “每车型×每场地”的粒度

`aiadaptation.xml` 的经验数据至少与赛道和车辆/组别条件相关，但这只是**难度标定粒度**，不能推出内部存在同粒度的几何路径文件。

对本项目应保守建模为：

```text
layout-level corridor/base line
+ car/class-level performance adaptation
+ player-level difficulty calibration
+ runtime racecraft deviations
```

### 4.5 结论与置信度

- “Adaptive AI 调整难度而不是比赛中 rubber-banding”：官方描述和文件结构支持，A/B。
- “数据核心是圈速—skill 映射”：高置信度，B。
- “内部具体几何线格式与生成算法”：未知。
- “可从 shared memory 直接读出原生线”：否，A。

## 5. iRacing

### 5.1 内容不是完全通用生成的

iRacing 的官方发布说明长期分别列出：

- AI 新增/改进了哪些**车辆**；
- AI 新增/改进了哪些**赛道配置**；
- 个别车辆或赛道的专项训练和修复。

例如 2026 S1 同时列出“fully trained to race with”新车辆和“fully trained to race at”新赛道，并进一步列出车辆专项和赛道专项改进：

- https://support.iracing.com/support/solutions/articles/31000177717-2026-season-1-initial-release-notes-2025-12-08-03-

2026 S3 仍按车辆训练、赛道训练、车辆专项和赛道专项分别发布：

- https://support.iracing.com/support/solutions/articles/31000179016-2026-season-3-initial-release-notes-2026-06-09-01-

这说明 AI 内容至少由“车辆能力”和“赛道知识”两部分组成，并需要人工训练/验证，不是对任意新车新赛道零配置求解。

### 5.2 AI 驾驶员参数怎样影响线

iRacing 官方对 roster 属性的说明非常直接：

- `Relative Skill` 低时，弯速较慢、线路较不理想；高时弯速更快、线路更接近最优。
- `Optimism` 控制油门与制动的保守/激进程度，包括 lift-and-coast 和是否更常瞄准最佳制动点。
- `Smoothness` 影响转向行为及偏转向过度/不足的倾向。
- 年龄影响反应时间和经验。

来源：

- https://support.iracing.com/support/solutions/articles/31000153531-ai-rosters

这表明 iRacing 并非只有“同一条线、统一速度乘百分比”；至少 line optimality、弯速、制动/油门行为和转向特性是分开的参数维度。

### 5.3 名义线与动态位置决策

官方 2026 S1 说明 AI 会围绕 `ideal pace line` 对自己在赛道上的位置作更独立的决定，并呈现不同路径。2026 S2 Patch 1 又说明 AI 改进了“随着赛道位置变化计算 racing-line speed”的过程：

- https://support.iracing.com/support/solutions/articles/31000177717-2026-season-1-initial-release-notes-2025-12-08-03-
- https://support.iracing.com/support/solutions/articles/31000178265-2026-season-2-patch-1-release-notes-2026-03-13-02-

因此可把运行结构概括为：

```text
ideal pace line / 可行位置带
      + 当前车辆的速度与轮胎模型
      + driver attributes
      + 路面温度、橡胶、水和轮胎状态
      + 对手、并排、节奏车和事故状态
      -> 当前目标位置、线路速度和控制动作
```

注意：这是系统分层的可信概括，不是官方公开的数学公式。

### 5.4 驾驶辅助线明显包含车型信息

iRacing 的 Driving Line 是彩色加速/制动提示线：

- https://support.iracing.com/support/solutions/articles/31000133499-driving-aids

2023 S1 发布说明曾专门修改 BMW M Hybrid V8 的辅助线，使其显示 Race 与 Qualifying 两种动力模式的平均值。这是辅助线速度/颜色 profile 依赖车辆状态的直接证据：

- https://support.iracing.com/support/solutions/articles/31000168823-2023-season-1-release-notes-2022-12-06-01-

但这不能证明辅助线的**几何顶点**也为每种动力模式重新优化；更可能是共用或近似共用几何线，使用车辆相关的速度/油门制动 profile。

### 5.5 SDK 与可提取性

iRacing SDK/IBT 可提供大量车辆遥测和圈距离；离线 telemetry 可在 ATLAS 中绘制 track map。官方没有提供 AI ideal line、驾驶辅助线顶点或 AI 内部目标速度的导出接口。

因此：

- 可以从自己的 `.ibt` 最快有效圈恢复**实际驾驶轨迹**；
- 不能把该轨迹称为 iRacing 内部 AI 的原生 ideal line；
- 在线/实时接口还受到反作弊限制，不应尝试从非公开内存提取内部线。

### 5.6 结论与置信度

- “车辆和赛道分别需要 AI 训练/支持”：A。
- “skill 改变弯速和线路最优程度”：A。
- “存在 ideal pace line，运行时会选择不同位置”：A。
- “每车每场地保存一条静态线”或“使用某种已知 RL/最优控制算法”：没有公开证据。

## 6. 三款模拟器的共同算法框架

即使内部实现不同，它们都可以用以下四层抽象：

### 6.1 赛道几何层

以弧长 `s` 参数化中心线 `c(s)`，单位法向量为 `n(s)`，左右宽度为 `w_L(s), w_R(s)`。候选线可表示为：

```text
p(s) = c(s) + alpha(s) * n(s)
-w_R(s) + margin_R <= alpha(s) <= w_L(s) - margin_L
```

`alpha(s)` 是优化变量。路肩是否可用、车辆宽度和安全余量都进入约束。

### 6.2 几何 racing line

成本最低的近似是最短路或最小曲率：

```text
min Σ ||p[i+1] - p[i]||                         shortest path
min Σ kappa[i]^2                                minimum curvature
```

最小曲率常可写成二次规划，计算快、只需边界和车辆宽度，但它不是严格最短圈。高加速车辆会更偏向晚 apex 和出口，低功率高弯速车辆可能更重视保持曲率连续和弯中速度。

### 6.3 车辆相关速度剖面

在给定路径曲率 `kappa(s)` 后，先算弯速上限，再作前向加速与反向制动积分：

```text
v_lat_max(s) ≈ sqrt(a_y_max(v, load, tyre, aero, surface) / |kappa(s)|)
v_fwd[i+1]^2 <= v[i]^2 + 2 * a_accel(v, gear, power) * ds
v_bwd[i]^2   <= v[i+1]^2 + 2 * |a_brake(v, tyre, aero)| * ds
v[i] = min(v_lat_max, v_fwd, v_bwd, speed limits)
```

更准确时要使用轮胎 friction ellipse/circle，让横向和纵向加速度共享抓地预算，并加入坡度、横坡、空气动力、动力曲线、挡位、能量部署、轮胎温度和路面摩擦。

### 6.4 联合最短圈优化

严格问题是：

```text
min    T = integral(ds / v_s)
over   state x(s), control u(s), lateral offset alpha(s)
s.t.   vehicle dynamics
       tyre force limits
       power/brake/aero limits
       track boundaries and vehicle footprint
       periodic start/end state
```

可用 direct collocation/direct transcription + nonlinear programming（如 CasADi/IPOPT），也可用动态规划、贝叶斯优化或仿真内黑箱搜索。车辆模型越完整，结果越像真正的“每车型每场地最优线”，但参数需求和求解成本也越高。

可复用的开源实现与论文：

- TUM `global_racetrajectory_optimization`：最短路、最小曲率、最短时间和带动力系统的最短时间求解。https://github.com/TUMFTM/global_racetrajectory_optimization
- Sequential Two-Step Algorithm：先路径，再用前向/反向积分求最短时间速度剖面。https://arxiv.org/abs/1902.00606
- Bayesian Optimization racing line：明确指出最优线同时依赖赛道几何和车辆动力学。https://arxiv.org/abs/2002.04794

## 7. 对本仓库的推荐数据模型

当前项目把参考线按赛道存储，这适合作为几何基准，但不足以代表所有车辆的最优轨迹。建议拆成三种资产：

```text
tracks/<sim>/<track_id>/<layout_id>/
  corridor.csv             # center/left/right、表面、路肩、坡度，赛道级
  base_line.csv            # 中性/最小曲率线，赛道级，可选

trajectories/<sim>/<track_id>/<layout_id>/<car_id>/<variant_id>/
  trajectory.csv           # x,y,z,s,yaw,curvature
  speed_profile.csv        # target_speed, throttle, brake, gear
  manifest.yml             # 条件、来源、算法、验证结果
```

`variant_id` 至少应包含或在 manifest 中记录：

- 车辆物理版本和 setup hash；
- 轮胎 compound；
- 油量；
- 干/湿、温度、抓地/橡胶状态；
- 是否允许使用路肩；
- 生成方法：AC spline、人工最快圈、AI 遥测、minimum-curvature、minimum-time、RL；
- 求解器版本和质量指标。

不要用文件名省略 simulator。不同游戏中同名赛道的坐标、边界、表面和长度都不同。

## 8. 推荐生成流程

### 8.1 MVP：可落地且风险最低

1. **采集赛道走廊**：人工低速跑左右边界和中心/参考圈；按 `lap_distance_fraction` 对齐并清理跳点。
2. **构建赛道级 base line**：在走廊中求 minimum-curvature line。
3. **按车生成速度剖面**：用简化的 `a_y(v)`、加速包络和制动包络做 forward/backward pass。
4. **仿真验证**：用规则控制器/MPC 或人工跟线跑圈，检查出界、控制饱和和圈时。
5. **迭代轨迹**：把轨迹的 lateral offset 控制点作为优化变量，用仿真圈时和越界惩罚作目标。

这已经会得到真正按车辆变化的结果，并比直接复制游戏辅助线更可解释。

### 8.2 各模拟器的数据来源

**Assetto Corsa**

- 用 `fast_lane.ai` 作为 base line 和走廊的初始值。
- 不把其 payload speed 当作当前车辆真值。
- 对每辆车采集稳定快速圈或运行车辆模型速度规划器。
- 可以用本项目现有的世界坐标和边界导出，无需读取非公开内存。

**RaceRoom**

- 用官方 shared memory 记录人工驾驶的 `position`、`lap_distance_fraction`、速度、控制、姿态。
- 对每个目标车辆/组别至少录制 5–10 个干净圈，按 Frenet 横向 offset 聚合。
- 先用最快有效圈作为 imitation reference，再由最小曲率/圈时优化平滑。
- 当前 RaceRoom 自动控制路径仍是 No-Go；在获得游戏支持的控制设备前，只做人工采集和离线优化。

**iRacing**

- 使用合规的磁盘 telemetry `.ibt` 和 ATLAS/SDK 数据导出实际轨迹。
- 为每个目标组合收集固定条件下的最佳有效圈。
- 不尝试读取在线未公开坐标或 AI 内部状态。

### 8.3 更高精度版本

当 MVP 稳定后，再升级到：

- 3D 赛道、坡度和横坡；
- 速度相关下压力和阻力；
- combined-slip tyre envelope；
- 车辆 footprint 而非质点边界；
- 轮胎温度/磨损和能量管理；
- full minimum-time nonlinear optimal control；
- 雨线、超车线、防守线和多车局部规划。

## 9. 如何实证“线是否按车型变化”

对每个模拟器选同一场地、三种差异明显的车辆，例如低功率街车、GT3、高下压力方程式车：

1. 固定天气、抓地、油量和 setup。
2. 分别采集驾驶辅助线（若可视觉提取）、AI 无交通圈和高手/最快有效圈。
3. 投影到同一赛道 Frenet 坐标，得到横向 offset `d(s)` 和速度 `v(s)`。
4. 比较：

```text
RMS lateral difference
95th percentile lateral difference
apex position shift
braking-point shift
minimum-speed location shift
lap-time difference after swapping line/speed profile
```

判断时必须把“几何线差异”和“速度剖面差异”分开。如果不同车辆的 `d(s)` 几乎相同、`v(s)` 差异很大，说明系统主要复用几何线并按车适配速度；如果 apex 和出口 offset 系统性变化，才支持 per-car geometry。

## 10. 最终判断

1. **Assetto Corsa**：公开和本地证据最明确。核心是赛道布局级、人工录制/编辑的 `fast_lane.ai`；车辆差异主要在运行时速度与控制层。把它作为所有车辆的“最优线”是不成立的。
2. **RaceRoom**：Adaptive AI 的公开可见机制是圈速历史与 AI skill 映射，作用是选择难度，不是生成玩家专属线路。内部路径资产与算法闭源。
3. **iRacing**：公开证据显示车辆、赛道、驾驶员属性和实时位置选择都参与 AI 线路与速度；但没有公开最短圈算法，也不能证明为每个组合保存独立静态几何线。
4. **本项目**：应维护“赛道走廊 / 赛道级 base line / 车型级 trajectory / 车型级 speed profile”四层，而不是继续让一个 `track-racing_line.csv` 同时承担全部语义。
