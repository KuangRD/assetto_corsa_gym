# 交接记录

> 每次离开机器或结束会话前更新本文件。只写结论、命令与路径，不写聊天过程。
> 不得在此写入凭据、API key、个人路径中的敏感信息。

## 元数据

- 更新时间：2026-11-15
- 机器：台式机（Windows）
- 分支：`wip/handoff-2026-11-15`
- 基线 commit：`01194e9`（本次提交之前）
- 未提交改动：无（提交后以 `git log -1` 为准）
- 本次会话工具：Claude Code（模型 claude-haiku-5-5）

## 当前目标

落地多设备与 AI 协作方案：两台 Windows 机器共享同一仓库，Claude 负责设计与审查，Codex 与 DeepSeek Harness 负责执行。

## 已完成

- [x] 添加 `upstream` 远程（dasGringuen/assetto_corsa_gym），上游同步为可选项。
- [x] 将 RaceRoom 未完成改动、遥测对比工具、多设备方案提交到 `wip/handoff-2026-11-15`。
- [x] 修订多设备方案 `docs/multi-device-ai-development.md`，限定为两台 Windows 机器。
- [x] 新增 `AGENTS.md`，定义项目规则、接手协议、禁止事项与验证边界。
- [x] `CLAUDE.md` 改为通过 `@AGENTS.md` 引入共同规则，并删除对不存在文件 `test_environment_setup.py` 的引用。

## 未完成

- [ ] 将 `wip/handoff-2026-11-15` 推送到 `origin`。本次操作环境无法完成 GitHub 认证，需在能访问 GitHub 的 Windows 机器上执行 `git push -u origin wip/handoff-2026-11-15`。
- [ ] 决定 `assetto_corsa_gym/AssettoCorsaPlugin/windows-libs/` 的处理方式（见"风险与注意事项"）。
- [ ] 在第二台 Windows 机器上检出该分支，确认可以完整继续工作。
- [ ] 将 `docs/商业计划书_BP.md` 移到仓库外（当前为未跟踪文件，不提交）。
- [ ] `.gitignore` 补充 `AssettoCorsaGymDataSet/` 与 `outputs/` 的显式规则。
- [ ] `.gitattributes` 补充二进制声明（`*.png`、`*.jpg`、`*.pkl`、`*.pyd`、`*.dll`）。

## 已验证 / 未验证

| 项目 | 状态 | 命令或证据 | 备注 |
|---|---|---|---|
| Git 提交与分支 | 通过 | `git log --oneline -2` | 两次提交已在本地完成 |
| 推送到 origin | 未运行 | — | 需要人工认证 |
| 单元测试 | 未运行 | `pytest` | 尚未在本次会话中执行 |
| AC 实机验证 | 未运行 | — | 需在台式机执行 |
| DeepSeek Harness 行为验证 | 未运行 | 见方案第 7.3 节 | 是否读取 AGENTS.md 未知 |

## 正在运行的任务

无。

## 下一步（按优先级）

1. 在台式机执行 `git push -u origin wip/handoff-2026-11-15`。
2. 决定 `windows-libs/` 的处理方式，并在 AGENTS.md 与方案文档中同步更新。
3. 在移动工作站上 `git fetch origin` 并检出 `wip/handoff-2026-11-15`，阅读本文件与 AGENTS.md，确认可以继续工作。
4. 运行 `pytest`，记录结果到本文件的"已验证"表。
5. 补充 `.gitignore` 与 `.gitattributes` 的规则。

## 风险与注意事项

- **`windows-libs/` 不是可随意移除的目录。** `INSTALL.md` 与 `INSTALL_Linux.md` 都要求从该目录复制 `DLLs`、`Lib`、`Vjoy.ini`、`WASD.ini` 到 Assetto Corsa 安装目录。移走它会使新机器的安装步骤失效。处理前需确认方案。
- `docs/商业计划书_BP.md` 为个人文档，只保留在本地，不要使用 `git add -A` 提交。
- DeepSeek Harness 为开发者预览版，有破坏性变更。使用时记录版本号。
- 机器相关的解释器路径、端口与盘符只写在本机配置中，不写入提交的文件。

## 决策记录

- 2026-11-15：项目只在两台 Windows 机器上运行，Mac 不参与开发与运行，仅用于资料查询与商业计划撰写。理由：AC 与 vJoy 只能在 Windows 上运行。
- 2026-11-15：删除 `CLAUDE.md` 中对 `test_environment_setup.py` 的引用。理由：该文件不存在。
- 2026-11-15：`AGENTS.md` 的 `config.yml` 超参数规则暂定，待确认。

## 历史记录

- 2026-11-15 ｜ 台式机 ｜ 基线 `01194e9` ｜ 修订多设备方案，创建 wip 分支，新增 AGENTS.md 与 HANDOFF.md。
