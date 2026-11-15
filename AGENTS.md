# AGENTS.md

本文件是所有 AI 代理（Codex、Claude Code、DeepSeek Harness）在本仓库工作时的共同规则。
`CLAUDE.md` 通过 `@AGENTS.md` 引入本文件，只补充 Claude Code 专属内容。

## 1. 项目概览

Assetto Corsa Gym：把 Assetto Corsa 赛车模拟器封装为 OpenAI Gym 环境，用于自动驾驶强化学习研究。
本仓库是 dasGringuen/assetto_corsa_gym 的 fork。

两套运行时，不能混用：
- 训练与环境端：Python 3.9+（conda 环境 `p309`）。
- AC 插件端：运行于游戏内嵌的 Python 3.3，`assetto_corsa_gym/AssettoCorsaPlugin/plugins/sensors_par/`。

## 2. 环境与命令

```bash
conda env create -f environment.yml   # 首次
conda activate p309
pip install -r requirements-dev.txt
pytest                                 # 无模拟器的单元测试
```

- `environment.yml` 是 Python、PyTorch、CUDA 版本的唯一来源，不要单独升级。
- `requirements.txt` 是运行时锁定版本；`requirements-dev.txt` 增加 pytest。
- 本项目只在 Windows 上运行。不要为 macOS 或 Linux 编写依赖 AC 的代码路径。

## 3. 目录约定

- `assetto_corsa_gym/AssettoCorsaEnv/`：Gym 环境、客户端、赛道与参考线。
- `assetto_corsa_gym/AssettoCorsaPlugin/`：AC 插件（Python 3.3）。
- `assetto_corsa_gym/RaceRoom/`：RaceRoom 共享内存接口（进行中）。
- `algorithm/discor/`：SAC 与 DisCor 实现。
- `scripts/`：独立运行的工具脚本。
- `tests/unit/`：单元测试，不依赖模拟器。
- `docs/`：设计文档、实验记录、方案。`docs/experiments/` 是实验结果的规范位置。
- `docs/HANDOFF.md`：当前进度与交接记录。

## 4. 接手协议（每次会话必做）

开始工作前：
1. 阅读 `docs/HANDOFF.md`，确认上一次会话的目标、未完成步骤和正在运行的任务。
2. 运行 `git status` 与 `git log --oneline -5`，确认工作区状态与当前分支。
3. 如果 HANDOFF 与仓库状态不一致，先报告差异，不要自行假定哪一方正确。

结束工作前：
1. 更新 `docs/HANDOFF.md`：进度、已验证项、未验证项、下一步、正在运行的训练或模拟器。
2. 不要把 HANDOFF 写成聊天记录。只写结论、命令和路径。

## 5. 禁止事项

以下操作必须经过人工确认，AI 不得自行执行：

- 推送到 `main`，或对任何分支执行 force push。
- 删除文件、目录或实验输出；删除前必须列出目标路径。
- 修改 `environment.yml`、`requirements*.txt` 中的版本号。
- 修改 `config.yml` 中影响训练的默认超参数（允许新增带注释的可选项）。【待确认】
- 修改 `AssettoCorsaPlugin/plugins/sensors_par/config.py` 中的机器相关项（解释器路径、端口、屏幕采集开关）。这些应放在本机配置中。
- 提交以下内容：数据集（`AssettoCorsaGymDataSet/`）、`outputs/`、`output/`、检查点、`.pkl`、`.pth`、个人文档（如商业计划书）、任何凭据或 API key。
- 在同一工作树中切换分支或更新代码，而训练或 AC 实例正在该工作树运行。

## 6. 工作方式

- 功能开发在独立分支或 worktree 中进行，分支名 `feat/<name>`。不要在 `main` 上直接修改。
- 一次提交只包含一个逻辑改动。提交信息说明目的、验证命令和已知限制。
- 修改前先列出：假设、涉及的文件、运行风险。完成后报告：改动文件、验证结果、未验证部分。
- 涉及以下内容的改动需要特别审查：奖励函数、动作边界与安全限制、训练恢复与检查点加载、数据覆盖与路径处理、插件与端口通信。

## 7. 验证边界

- **提交前必须通过**：`git diff --check`、相关单元测试、导入检查。
- **可以在任一台 Windows 机器上完成**：纯 Python 单元测试、配置解析、数据处理。
- **必须在指定 Windows 机器上完成，并保存日志**：启动 AC、插件收发、vJoy、屏幕采集、CUDA 训练、长时间评估。
- **不得声称**：单元测试通过即代表仿真闭环通过；短 smoke run 即代表性能结论。
- 无法运行的验证，必须在交接记录与最终报告中写明原因。

## 8. 实验记录

- 每次训练在 `outputs/` 生成 `manifest.json`，包含：`run_id`、主机名、commit SHA 及是否有未提交改动、赛道与车辆、覆盖的命令行参数、随机种子、恢复的检查点来源。
- 仓库中只保留结果摘要，放在 `docs/experiments/<日期>_<简称>/`。
- 恢复训练时新建 run 目录并记录来源检查点，不覆盖旧目录。

## 9. 提交与分支

- 分支：`main`（稳定）、`feat/<name>`（功能）、`wip/<机器>-<日期>`（交接）、`sync/upstream-<日期>`（上游同步）。
- 提交信息：`<类型>: <摘要>`，类型可用 `feat`、`fix`、`docs`、`wip`、`build`、`test`。
- 合并由人工完成。AI 不得自行合并到 `main`。

## 10. 角色

- Claude：设计与审查。审查应在新会话中进行，且为只读。
- Codex：仓库内的实现与修复，在独立 worktree 中工作。
- DeepSeek Harness：资料整理、插件与非核心脚本。在验证清单通过前，不修改训练主干代码。
