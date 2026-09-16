# Linux 最终验收（主任务书 §27 / §29）

Soda Prompt Hub Linux 适配的最终验收结论。本文件只回答两件事：
主任务书 §29 的 13 个问题，以及 §27 的第一阶段验收标准。

> **文档位置说明**：上游 `tests/test_public_docs.py` 要求 `docs/*.md`（顶层）**恰好**是 12 个既有文件。
> 为不修改上游文档契约，Linux 相关文档统一放在 `docs/linux/` 子目录；
> 与主任务书路径的对应关系见 [README 的文档位置说明](README.md#文档位置说明)。

## 验收对象

| 项目 | 值 |
| --- | --- |
| 验收对象 | `linux/main` 维护分支（2026-09-16） |
| 上游基线 | `upstream/linux/main`：Linux 适配已进入官方分支（PR #20 / #21 / #22 已合并），维护者随后追加 PR #23（桌面启动器与发行打包） |
| 环境 A | WSL2 + Ubuntu 24.04.5 LTS，x86_64 — 见 [DEV_ENVIRONMENT.md](DEV_ENVIRONMENT.md) |
| 环境 B | GitHub Actions `ubuntu-22.04` / `ubuntu-24.04` — 见 [`.github/workflows/linux.yml`](../../.github/workflows/linux.yml) |
| 总体结论 | Core、部署、测试、CI、文档通过；**上游自动检测与自动发布未实现**（维护者决策），逐条见[未闭合项](#未闭合项) |

本文件的规则：每条结论都给出可复现的证据出处；未完成或已降级的条目**如实标注为未完成**，不写成"已具备"。

## 一、主任务书 §29：13 个问题

| # | 问题 | 结论 | 证据 | 残留 |
| --- | --- | --- | --- | --- |
| 1 | Linux 核心是否可以独立运行？ | **是** | WSL2 Ubuntu 24.04 实机 `prompt-hub serve` 启动，`GET /` 200、`/api/health` 返回 `status: ok`；CI 在 ubuntu-22.04 / 24.04 跑完整套件与构建 | 其他发行版与 aarch64 未验证 |
| 2 | Linux 是否需要修改核心 Python 代码？ | **是，但改动量很小**：让它"能跑"不需要改核心，改的都是缺陷与平台语义 | 相对上游基线，既有文件只动了 16 个，且集中在：① `media.py`（新增）+ 4 个图片端点显式 `media_type`（已随 PR #20 合并）；② `usage_modes.py` 的 `linux_local`（已随 PR #22 合并）；③ `dataset_workspace.py` 的外接卷与 XDG 用户目录（`9c7dbda`，**未上游**）；④ 远端/带认证 ComfyUI（跨平台功能，非 Linux 专属） | ③ 仍只在本分支 |
| 3 | Windows / macOS 是否受到影响？ | **未受影响** | 改动几乎全是新增文件；既有文件均为增量修改（如 `browse_roots()` 在保留 `/Volumes` 的基础上追加 `/media`、`/run/media`、`/mnt`）；无数据库 schema、数据格式或 API 变更；上游 `ci.yml` 继续全绿，两处修复已通过上游审核合入 | F1/F2 尚未经上游 macOS 用户使用验证 |
| 4 | Linux Worker 是否已实现？ | **是（实验性、无 GUI）** | `install.sh --with-worker` 准备桥接目录、`soda-worker` 命令与 systemd 单元；协议端到端验证（真 Worker + 真桥接 + 假 ComfyUI，无需 GPU）；真实远端 ComfyUI 出图一次并逐个校验 sha256 — 见 [WORKER.md](WORKER.md) | 不含 LoRA 训练类任务；ComfyUI 凭据目前明文存于本机 `worker-config.json` |
| 5 | 哪些功能仍然是 Windows-only？ | LoRA 正式训练；Windows Worker 的 GUI / 托盘宿主；官方 Setup 安装包（DMG 同理为 macOS 专属） | [支持状态](README.md#支持状态)、审计 §6 | 另：SMB 双机配对是 macOS-only；Linux 无桌面宿主/托盘，用轻量启动器 + 浏览器替代 |
| 6 | Linux 是否可以通过 systemd 运行？ | **是** | 用户级 unit，非 root，默认只监听 `127.0.0.1:8765`，`Restart=on-failure` + `RestartSec=5`，日志进 journald；CI 在真实 runner 上执行安装 → `systemctl --user status` → 健康检查 → 卸载；WSL 实机 `kill -9` 后第 5 秒自动恢复 | 默认不开 `linger`，注销会话后服务停止（`install.sh --enable-linger` 为可选项） |
| 7 | Linux 是否可以安全更新？ | **是** | `update.sh` 只做快进合并，更新前打印数据库大小 / mtime 与资料库字节数，工作区不干净时拒绝执行；实测更新前后数据库大小与 mtime 完全一致、标记文件保留；`uninstall.sh` 默认保留全部用户数据 — 见 [UPDATE.md](UPDATE.md) | 回滚需依赖 git 历史，未提供一键回滚 |
| 8 | upstream 更新后多久能够发现？ | **不会自动发现** | 本分支不携带 `schedule` 工作流：非默认分支上的 `schedule` / `workflow_run` 不会按预期触发；该决策见 [上游同步机制](README.md#上游同步机制) | 发现时延 = 人工 `git fetch upstream` 的间隔，无 SLA。这是主任务书 §15 **未交付**的要求 |
| 9 | upstream 更新后能否自动进行 Linux CI？ | **部分可以**：CI 自动，发现与合并人工 | 上游更新本身不触发任何工作流；把合并结果推送到 `linux/main` 或开 PR 后，`.github/workflows/linux.yml` 自动执行 4 个作业（触发条件：push 到 `main`/`linux/**`、`pull_request`、`workflow_dispatch`） | 无"新增 upstream 提交 → 自动起同步分支 → 自动跑 CI"的链路（§16 未交付） |
| 10 | upstream 更新后能否自动生成 Linux Release？ | **否，且不会随 upstream 版本变化触发** | `scripts/build_linux_release.py` 已可产出可复现的 `soda-prompt-hub-linux-x86_64-<版本>-<日期>.tar.gz` + `SHA256SUMS` + `LINUX_RELEASE.json`，打包 → 解包 → 隔离安装 → 启动器启动全链路已实测；但由人工触发 | §17 属**部分交付**：产物形式达成，自动化未达成 |
| 11 | 用户数据是否与程序更新完全分离？ | **是** | 程序在仓库目录（虚拟环境 `<repo>/.venv`），数据默认在 `$XDG_DATA_HOME/soda-prompt-hub/{library,models}`，安装记录为 `install.env`；更新不动数据目录（实测），卸载默认保留数据 | 数据目录位置由 `PROMPT_HUB_LIBRARY_ROOT` / `PROMPT_HUB_MODELS_ROOT` 决定，迁移需自行移动 |
| 12 | 是否存在需要人工处理的 merge conflict？ | **目前没有，但属高概率事件** | 最近三次合并 `upstream → linux/main`（`ce5023b` / `44371ca` / `14bc4a0`）均以普通 merge 提交完成，无冲突处理痕迹 | 本分支目前有 1 处对上游活跃文件的改动（第 2 问的第 ③ 项）尚未上游化，一旦上游改到同一区域就必须人工解决 |
| 13 | 是否存在 Linux-specific patch 无法自动 rebase？ | **有 1 处** | `9c7dbda` 对 `src/prompt_hub/dataset_workspace.py` 的改写在被上游接受前需要人工 rebase；其余 Linux 内容全部是新增文件（`deploy/linux/`、`tests/linux/`、`scripts/linux/`、`docs/linux/`、`.github/workflows/linux.yml`），可自动跟随 | 消除风险的动作只有一步：把 `9c7dbda` 拆成上游 PR |

## 二、主任务书 §27：第一阶段验收标准

| 验收步骤 | 结果 | 证据 |
| --- | --- | --- |
| 干净环境中 clone 后执行 `./deploy/linux/install.sh` | 通过 | WSL2 Ubuntu 24.04 实机一次通过；CI 的 `systemd 用户服务` 作业在真实 runner 上重复该流程 |
| `systemctl --user status soda-prompt-hub` 显示运行中 | 通过 | `active (running)`、`enabled`，日志进 journald |
| 访问 `http://127.0.0.1:8765` | 通过 | `GET /` 200；`/api/health` 返回 `status: ok` |
| `./deploy/linux/update.sh` 安全更新且不丢用户资料 | 通过 | 更新前后数据库大小与 mtime 一致，资料库标记文件保留 |

14 项逐条实机记录（安装、幂等、监听范围、崩溃重启、无 systemd 场景、卸载与重装等）见
[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) §7。

## 三、未闭合项

以下条目**没有**完成或**被降级**，列出以免被误读为已完成：

| 条款 | 要求 | 实际状态 | 备注 |
| --- | --- | --- | --- |
| §15 | `upstream-sync.yml` 定期检测上游更新并建 Issue | **未交付** | 曾实现（`0b653d3`），后与发布工作流一并在 `4e38e6b` 移除；维护者决定接受手动同步 |
| §16 | 自动建同步分支 → 跑 CI → 成功开 PR / 失败报冲突 | **降级为人工** | 流程要求写在 [上游同步机制](README.md#上游同步机制) |
| §17 | upstream 版本变化且 Linux CI 通过后自动发布 | **部分交付** | 打包脚本与产物形式已具备，触发仍为人工 |
| §28 | 模拟上游提交验收同步链路 | **未执行** | 依赖 §15/§16，没有自动化就没有可验收的链路 |
| §26 | 文档落在 `docs/LINUX_*.md` | **主动偏差** | 上游测试契约限制，映射关系见 [README](README.md#文档位置说明) |
| — | `9c7dbda`（F1/F2）进入上游 | **待办** | 该提交目前只存在于本分支，上游没有；它也是第 13 问里唯一的 rebase 风险点 |

## 四、怎么自己复现这份验收

```bash
scripts/linux/check-env.sh              # 环境自检（只检查、不安装）
./deploy/linux/install.sh               # §27 的安装链路
./deploy/linux/status.sh                # 服务、监听、健康、数据占用
uv run pytest tests/linux -q            # Linux 专属用例
uv run pytest -q                        # 完整套件
```

CI 侧：仓库 **Actions → Linux**，四个作业 —— `格式 / Lint / 类型检查`、`Tests on ubuntu-22.04`、
`Tests on ubuntu-24.04`、`systemd 用户服务`。

## 五、本次验收的实测记录

环境：WSL2 + Ubuntu 24.04.5 LTS，x86_64，2026-09-16，检出 `linux/main`。

| 项目 | 命令 | 结果 |
| --- | --- | --- |
| 完整套件 | `uv run pytest -q` | **619 passed / 9 skipped**（165.65 s；9 个 skip 全部是 macOS 专属用例） |
| Linux 专属用例 | `uv run pytest tests/linux -q` | **59 passed** |
| 格式 | `uv run ruff format --check .` | 208 files already formatted |
| Lint | `uv run ruff check .` | All checks passed |
| 类型检查 | `uv run ty check src/` | All checks passed |

单独跑子集时 `--cov` 的 80% 门槛会失败（覆盖率统计范围是整个 `src/`），这是设计如此，不是回归；
完整套件下门槛通过。
