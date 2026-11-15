# 多设备与 AI 协作开发方案（Assetto Corsa Gym）

> 适用项目：`assetto_corsa_gym`（基于 dasGringuen/assetto_corsa_gym 的 fork）。
> 本文档是修订版，替代先前的通用方案。它只保留本项目实际需要、并且已在仓库中核实的部分。

## 1. 原则

1. **Git 是代码的唯一事实来源。** 活跃仓库不放进 OneDrive、iCloud、Dropbox 或 Syncthing 的双向同步目录。
2. **运行 Assetto Corsa 的任务只在 Windows 上执行。** 模拟器、插件、vJoy、屏幕采集和 GPU 训练都只在两台 Windows 机器上进行。
3. **同一分支同一时刻只在一台机器上编辑。** 交接通过推送 `wip/` 分支完成。
4. **大文件与机器相关内容不进 Git。** 数据集、检查点、`outputs/` 和本机路径都留在本地。
5. **AI 工具的项目规则只写一份。** 以仓库内的 `AGENTS.md` 为准，`CLAUDE.md` 引用它。

## 2. 设备分工

| 设备 | 角色 | 是否运行 AC | 是否编辑代码 |
|---|---|---|---|
| Windows 台式机 | 主仿真与训练节点；保存稳定的实验目录与 `outputs/` | 是 | 是 |
| Windows 移动工作站 | AC 插件联调、短验证、备用训练节点 | 是 | 是 |
| MacBook Pro | 资料查询、文献与商业计划撰写 | 否 | 否 |

Mac 不参与仓库的开发、运行和 AI 编码。商业计划书（`docs/商业计划书_BP.md`）属于个人文档，不应留在项目仓库里，见第 4 节。

## 3. 仓库与分支

### 3.1 远程

- `origin`：`https://github.com/KuangRD/assetto_corsa_gym.git`（fork，日常推送到这里）。
- `upstream`：`https://github.com/dasGringuen/assetto_corsa_gym.git`（上游，已于本地添加）。上游可能已停止更新，同步是可选的。

需要同步上游时：

```bash
git fetch upstream
git switch -c sync/upstream-YYYY-MM-DD main
git merge upstream/main          # 或 rebase，按冲突情况决定
# 检查通过后再合并到 main，不直接在 main 上合并上游
```

### 3.2 分支约定

- `main`：可运行的稳定分支。
- `feat/<name>`：功能分支，例如 `feat/raceroom-shared-memory`。
- `wip/<machine>-<date>`：交接用分支，例如 `wip/handoff-2026-11-15`。在离开某台机器前推送，到另一台机器后检出。
- `sync/upstream-<date>`：上游同步分支。

### 3.3 当前状态

本次交接已在本地创建 `wip/handoff-2026-11-15`，包含 RaceRoom 迁移的未完成改动、遥测对比工具以及本方案文档。**该分支需要在一台能访问 GitHub 的 Windows 机器上手动推送**，因为本次操作的环境无法完成 GitHub 认证：

```bash
git push -u origin wip/handoff-2026-11-15
```

`商业计划书_BP.md` 没有被提交，这是有意的。

## 4. 仓库卫生

需要在 `main` 合并前完成的修改：

- **`.gitignore` 显式添加**：`AssettoCorsaGymDataSet/`、`outputs/`（已有 `output/`，需确认两个目录的用途）。当前数据集目录被忽略，但没有对应规则，属于偶然状态。
- **`.gitattributes` 补充二进制声明**：`*.png`、`*.jpg`、`*.pkl`、`*.pyd`、`*.dll` 等显式标为 `binary`。
- **`test_environment_setup.py` 引用**：`CLAUDE.md` 提到该文件，但仓库中不存在。要么补上，要么删除引用。
- **`windows-libs/`**：仓库中提交了 Windows 上的 Python 3.12 运行时（`.dll`、`.pyd`）。它与插件使用的 Python 3.3 不同。**待确认用途后再决定保留、移除或迁出**，本方案不做改动。
- **商业计划书**：建议移到仓库外，例如 `Documents\商业计划书\`，并加入 `.gitignore` 作为兜底。Mac 上的资料也应放在仓库外。
- **Git 历史中的大文件**：`windows-libs/` 与带输出的 notebook（如 `ks_barcelona-layout_gp-racing_line.ipynb`，约 1.4 MB）会占用历史空间。暂不改写历史，记录即可。

## 5. 环境

- 两台 Windows 机器各自用 `environment.yml` 创建 conda 环境 `p309`（Python 3.9.23、PyTorch 1.12.1、CUDA Toolkit 11.6）。
- 不提交环境目录。版本变更只改 `environment.yml` 与 `requirements.txt`，并在两台机器上验证。
- 插件运行于游戏内嵌的 Python 3.3。修改插件代码时，避免使用 3.4 之后的语法，并在 AC 环境中验证。
- 插件配置中的解释器路径、端口和屏幕采集开关是机器相关的，应放进本机配置，而不是直接修改已跟踪的 `config.py`。可以提供 `*.example` 模板。

## 6. 数据与实验

### 6.1 数据集

数据集（约 764 MB）从 Hugging Face 下载，各台 Windows 机器各存一份：

```bash
python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='dasgringuen/assettoCorsaGym', repo_type='dataset', local_dir='AssettoCorsaGymDataSet', allow_patterns='AssettoCorsaConfigs/tracks/*')"
```

数据集不通过 Git 传输。

### 6.2 实验记录

- **规范位置**：`docs/experiments/<日期>_<简称>/`，已有的 `docs/experiments/fastest_line_20261004/` 作为范例。仓库内只放轻量的结果摘要与 `manifest.json`。
- **检查点与原始输出**：放在 `outputs/`，不进 Git，每台机器各自管理。
- **根目录散落的训练评估文档**（如 `100万步训练效果评估.md`）暂不移动，等主线稳定后再统一迁入 `docs/experiments/`。

每次训练生成的 `manifest.json` 至少包含：`run_id`、主机名、代码 commit SHA 及是否有未提交改动、`environment.yml` 的版本、赛道与车辆、覆盖的命令行参数、随机种子、恢复的检查点来源、日志路径。

## 7. AI 工具分工

### 7.1 规则入口

- 新建 `AGENTS.md`，包含项目结构、运行命令、哪些文件不能改、验证边界、提交规范。
- `CLAUDE.md` 改为引用 `AGENTS.md`，只保留 Claude Code 专属的内容。

### 7.2 各工具定位

| 工具 | 定位 | 说明 |
|---|---|---|
| Codex | 仓库内的实现与修复 | 在独立 worktree 中工作，交付可审查的 diff |
| Claude Code | 仓库内的实现、审查与文档 | 同上；审查时优先只读 |
| DeepSeek Harness | 资料整理、日志汇总、周报等非核心任务 | 官方页面未说明会读取 `AGENTS.md`、不说明 worktree 与隔离机制，**在验证通过之前不用于修改代码** |

DeepSeek Harness 的官方说明中，平台包括 Windows 64 位桌面端，并提供 `npx @deepseek-ai/dsh web` 的 Web UI。它支持定时任务，但没有文档化的隔离机制，所以定时任务不应指向正在训练的工作树。

### 7.3 DeepSeek Harness 验证清单

1. 在一个临时 worktree 中，让它读取一条只写在 `AGENTS.md` 中的规则，观察它是否遵守。
2. 让它只修改 worktree 内的文件，确认不会写入主工作树。
3. 确认它的定时任务无法在训练期间修改 `outputs/` 或当前工作树。
4. 三项都通过后，再考虑把它用于代码任务。

### 7.4 worktree 布局

同一仓库在 Windows 上可以用多个 worktree 隔离 AI 任务，但它们不隔离游戏实例、端口、GPU 和 `outputs/`。并行运行模拟器与训练时必须人工确认资源互不冲突。

```bash
git fetch origin
git worktree add ../AC_gym-codex -b feat/codex-task origin/main
```

## 8. 交接流程

离开机器前：

1. 更新 `docs/HANDOFF.md`：当前进度、未完成步骤、下一步动作、正在运行的训练或模拟器。
2. `git status` 确认没有误纳入大文件或个人文档。
3. 提交到 `wip/` 分支并推送。

到达另一台机器后：

1. `git fetch origin`，检出对应的 `wip/` 分支。
2. 阅读 `docs/HANDOFF.md`。
3. 确认 `p309` 环境与本机配置，再开始工作。

运行 AC 或训练前，记录当前 commit SHA。运行期间不在同一工作树切换分支或更新代码。

## 9. 验证边界

- **提交前**：`git diff --check`、相关单元测试、导入检查。
- **Windows 验收**：涉及真实仿真、插件、端口、vJoy、屏幕采集、CUDA 或长时间训练时，在指定 Windows 机器上执行，并保存 manifest 与日志。
- 无模拟器的单元测试可以在任一台 Windows 机器上运行。是否接入 CI，等测试稳定后再决定；CI 不需要安装完整的 PyTorch/CUDA 环境。

## 10. 分阶段落地

**阶段 1（本周）**

- 在一台机器上推送 `wip/handoff-2026-11-15`。
- 另一台机器 `fetch` 并检出该分支，确认可以完整继续工作。
- 清理第 4 节列出的仓库卫生问题，并把商业计划书移出仓库。
- 决定 `windows-libs/` 的去留。

**阶段 2（随后）**

- 编写 `AGENTS.md`，改造 `CLAUDE.md`。
- 完成 DeepSeek Harness 的验证清单。
- 用两台机器各做一次短训练，检查 manifest 和日志是否完整。

**暂不做**：W&B/MLflow、NAS、对象存储、远程调度、多平台 CI 矩阵。等以上两个阶段稳定后，再根据实际瓶颈决定。

## 11. 验收清单

- [ ] 两台 Windows 机器都能从 `origin` 拉取并推送 `wip/` 分支。
- [ ] 两台机器各自的 `p309` 环境能导入项目并通过单元测试。
- [ ] 一台 Windows 机器能启动 AC 插件并完成一次有日志的短验证。
- [ ] 两个 AI 任务在不同 worktree 中工作，没有互相覆盖文件。
- [ ] 一次训练的 manifest 能回答：代码版本、配置、数据、机器、种子与检查点来源。
- [ ] 数据集与检查点有第二份备份，并已验证可读。
- [ ] `main` 上没有个人文档、大文件或机器相关路径。

## 12. 尚未确认的事项

- `windows-libs/` 的用途与去留。
- GitHub 上 fork 的可见性（公开仓库意味着已跟踪文件全部公开）。
- DeepSeek Harness 的 `AGENTS.md` 读取行为与 worktree 行为，需按第 7.3 节验证。
