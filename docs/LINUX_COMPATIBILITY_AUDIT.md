# Linux Compatibility Audit

Soda Prompt Hub Linux 适配审计报告（第一阶段交付物）。

| 项目 | 值 |
| --- | --- |
| 上游仓库 | `https://github.com/cOkieeman/soda-prompt-hub` |
| 基线 commit | `e96249bc29b71cdf8efba52d232c368f5c466549`（`main`，2026-09-14 10:34 UTC） |
| 软件版本 | `1.1.1`（`pyproject.toml`） |
| 审计分支 | `linux/main`（基于 `upstream/main`） |
| 审计日期 | 2026-09-14 |
| 审计方式 | 只读静态分析（`git grep` 遍历 `upstream/main` 树），未修改任何上游文件 |
| 覆盖范围 | `src/`、`tests/`、`deploy/`、`scripts/`、`docs/`、`.github/` |

---

## 0. 结论摘要

1. **上游 Python 核心已在 Linux 上事实可用。** 官方 CI（`.github/workflows/ci.yml`）的 `quality` job 全程运行于 `ubuntu-latest`：`uv sync --locked` → `ruff format --check` → `ruff check` → `ty check src/` → `pytest` → `uv build`。`tests/` 共 498 个测试函数，其中只有 4 个 macOS 专属文件带 `skipif(darwin)`；Windows 相关测试断言的是打包脚本的文本与逻辑，在 Linux 上照常运行。
2. **Linux 适配的真实工作量集中在“部署层 + 流水线 + 文档”，而不是“改业务代码”。**
3. **核心代码只有 2 个真实缺口**，且都不阻塞“Linux Core 可启动”：
   - **G1｜使用模式没有 Linux 语义**：Linux 会被推断为 `mac_remote`（“Mac 管理 Windows”的远端模式）。
   - **G2｜SMB 双机配对仅 macOS**：Linux 上该能力不存在，应标注“暂不支持”，而不是伪造一条走不通的路径。
4. 其余工作全部是新增文件（`deploy/linux/`、`.github/workflows/linux.yml`、`docs/LINUX_*.md`、`CHANGELOG.md` 条目），**不触碰上游核心**，满足主任务书 §1/§16 对“diff 纯新增、可自动 rebase”的要求。

分类统计：

| 分类 | 条目数 | 说明 |
| --- | --- | --- |
| A 无需修改 | 12 | CLI、环境变量、路径、文件管理器、git 调用、模型下载、无 GPU 硬依赖等 |
| B 需要路径适配 | 1 | 默认资料库目录 `~/Documents/...` 不符合 Linux XDG 习惯 |
| C 需要替代命令 | 1 | SMB 挂载诊断固定调用 `/usr/bin/open`（macOS 专属） |
| D Linux 暂不支持 | 5 | Compute Worker、桌面宿主、SMB 双机、LoRA 训练、平台安装包 |
| E 建议抽象 | 0 | 不建议新增平台抽象层（见 §3） |

---

## 1. 已兼容（A）

| # | 文件 / 位置 | 证据 | 说明 |
| --- | --- | --- | --- |
| A1 | `.github/workflows/ci.yml:16-49` | `runs-on: ubuntu-latest` + `uv sync --locked` + `ruff`/`ty`/`pytest`/`uv build` | **Linux 基线已存在**：核心、测试、构建全部在 Ubuntu 上通过 |
| A2 | `src/prompt_hub/cli.py:47-50, 110-111` | `serve --host` 默认 `127.0.0.1`、`--port` 默认 `8765`；`uvicorn.run("prompt_hub.api:app", ...)` | 满足主任务书 §8、§25（仅监听本机） |
| A3 | `src/prompt_hub/config.py:55-66` | `PROMPT_HUB_LIBRARY_ROOT` / `PROMPT_HUB_DATABASE` | 资料库位置可由环境变量覆盖，部署脚本可完全接管 |
| A4 | `src/prompt_hub/config.py:161-167` | `PROMPT_HUB_MODELS_ROOT` / `PROMPT_HUB_TAGGER_MODEL` | 模型目录可覆盖，无硬编码 |
| A5 | `src/prompt_hub/config.py:42-52` | `Path.home() / "Documents" / ...` 且带旧目录回退 | 使用 `pathlib`，无 `C:\`、无 `AppData`（见 B1 仅为默认值语义问题） |
| A6 | `src/prompt_hub/workspace_routes.py:744-757` | `darwin → /usr/bin/open -R`、`win32 → explorer.exe /select,`、`linux → xdg-open` | “打开所在文件夹”**已有 Linux 分支** |
| A7 | `src/prompt_hub/importers.py:615`、`maintenance.py:392`、`source_sync.py:196` | 均使用 `shutil.which("git")` | 无 `/usr/bin/git` 硬编码；历史 Windows 修复已被上游吸收，**不要重复实现** |
| A8 | `src/prompt_hub/model_connections.py:365-367` | `chmod(0o600)` 写入后设置权限 | 满足主任务书 §25（不明文保存 API Key、不用 `777`） |
| A9 | `src/prompt_hub/windows_worker_core.py:69-95` | `msvcrt` / `fcntl` 双实现文件锁 | Worker 的文件锁逻辑本身是跨平台写法 |
| A10 | `src/prompt_hub/wd14.py:132-140` | `auto` → 无 CoreML 时退回 `CPUExecutionProvider` | WD14 打标在 Linux 上可用（仅显式指定 `coreml` 才报错） |
| A11 | `src/prompt_hub/optional_models.py:181-241` | HuggingFace HTTPS 下载 + `sha256` 校验 + `revision` 收据 | 可选模型安装在 Linux 上平台无关 |
| A12 | 全 `src/` 扫描 | 无 `windll` / `kernel32` / `nvidia-smi` / `torch` / `cuda` 引用；无盘符硬编码 | 满足主任务书 §11：**没有 NVIDIA GPU 也不影响 Prompt Hub 启动** |

---

## 2. 必须修改 / 需要决策（B、C）

### G1｜使用模式（usage mode）没有 Linux 语义 — 严重度 Medium

| 项目 | 内容 |
| --- | --- |
| 文件 | `src/prompt_hub/web.py`、`src/prompt_hub/desktop_connection.py`、`src/prompt_hub/api.py` |
| 代码位置 | `web.py:53-57`、`web.py:72-85`、`desktop_connection.py:24-45`、`api.py:372-374` |
| 问题 | `render_index_html()` 在未显式传入时执行 `mode = "windows_local" if sys.platform == "win32" else "mac_remote"`；`connection_summary()` 中 `local = sys.platform == "win32"`。`api.py:374` 调用时**没有传 `usage_mode`**，因此 Linux 一律落入 `mac_remote`。 |
| 原因 | 使用模式是二元的（本机 / Mac 远程双机），用 `sys.platform` 推断，没有第三个取值；`web.py:55-57` 对未知取值直接 `raise ValueError`。 |
| 影响 | 不崩溃，但语义错误：Linux 用户看到的是“Mac 连接 …”文案、引导进入 SMB 配对（而 SMB 诊断是 macOS 专属，见 G2），示例路径也被替换成 `/Users/your-name/...`。 |
| 解决方案 | 方案 A（第一阶段，零核心改动）：接受 `mac_remote` 事实语义，在文档中如实说明 Linux Core 作为“资料库/创作/审核端”。方案 B（推荐长期）：向上游提 PR，把取值集合扩为 `{windows_local, mac_remote, linux_local}`，`sys.platform` 推断改为三分支，并把示例路径与文案补上 Linux 版本。方案 C：新增 `PROMPT_HUB_USAGE_MODE` 环境变量由部署层覆盖（仍需核心改动）。 |
| 是否影响 upstream merge | **影响**。`web.py` / `desktop_connection.py` 属于核心文件，本地长期携带 patch 会持续产生 rebase 冲突，建议走方案 B 反哺上游，合并后再 rebase。 |

### G2｜SMB 双机模式仅 macOS — 严重度 Low（归类为“暂不支持”）

| 项目 | 内容 |
| --- | --- |
| 文件 | `src/prompt_hub/remote_routes.py`、`src/prompt_hub/desktop_connection.py` |
| 代码位置 | `remote_routes.py:85`（`if sys.platform != "darwin": …`）、`remote_routes.py:99-100`（`["/usr/bin/open", destination]`）、`desktop_connection.py:149-160`（`smb://` 目标构造） |
| 问题 | 挂载诊断与“连接 Windows”的打开动作硬编码 macOS：非 darwin 直接返回不支持，且调用 `/usr/bin/open`。 |
| 原因 | 这是 Mac↔Windows 双机工作流的实现，未设计 Linux 侧对等能力（Linux 上对应的是 `gio mount` / `mount.cifs` + GVFS，需要桌面会话）。 |
| 影响 | Linux 无法进入“双机模式”；不影响 Linux Core 独立运行。 |
| 解决方案 | 第一阶段**明确标注 Linux 不支持 SMB 双机**，UI/文档不要暗示可配对；后续若需要，另立设计（HTTP Worker 协议或 `gio mount` 集成）。 |
| 是否影响 upstream merge | 不改代码则**无影响**。 |

### B1｜默认资料库目录不符合 Linux XDG 习惯 — 严重度 Low

| 项目 | 内容 |
| --- | --- |
| 文件 | `src/prompt_hub/config.py` |
| 代码位置 | `config.py:42-52` |
| 问题 | 默认值是 `~/Documents/Soda Prompt Hub/prompt-library`；Linux 上 `~/Documents` 可能不存在（由 xdg-user-dirs 创建，中文桌面下还可能显示为本地化名称），且 XDG 惯例是 `$XDG_DATA_HOME`。 |
| 原因 | 默认值面向 macOS / Windows 用户目录习惯设计。 |
| 影响 | 程序会自动 `mkdir(parents=True)`，因此**不会启动失败**；只是目录位置不符合 Linux 惯例，且在未装 xdg-user-dirs 的精简系统上会凭空创建 `~/Documents`。 |
| 解决方案 | 第一阶段**不改核心**：由 `deploy/linux/install.sh` 与 systemd unit 显式设置 `PROMPT_HUB_LIBRARY_ROOT` / `PROMPT_HUB_MODELS_ROOT`（默认建议 `~/.local/share/soda-prompt-hub`）。若要改核心默认值，需同时保住既有用户数据语义（`config.py` 中已有旧目录回退先例，可照此模式扩展），并写入 CHANGELOG。 |
| 是否影响 upstream merge | 不改核心则无影响；改核心则 Medium。 |

### B2｜模型目录内部的符号链接会被拒绝 — 严重度 Low-Medium

| 项目 | 内容 |
| --- | --- |
| 文件 | `src/prompt_hub/optional_models.py` |
| 代码位置 | `optional_models.py:131-140` |
| 问题 | `root()` 在 `models_root` 及其子目录路径上发现符号链接即抛 `VisualModelError("安装目录不能经过符号链接")`。Linux 上把大模型放到另一块盘再用符号链接接回来是常见做法。 |
| 原因 | 符号链接检查是安全设计（防止越出模型根目录）。 |
| 影响 | `models_root` 自身是符号链接时是安全的（先 `resolve()`，见 `:131`），但**`models_root` 内部子目录是符号链接**时会直接报错，属于 Linux 使用习惯上的真实摩擦点。 |
| 解决方案 | 第一阶段不改，文档中给出规避方式（把 `PROMPT_HUB_MODELS_ROOT` 直接指向真实目录，而不是在内部做软链）；若要放开，需向上游论证。 |
| 是否影响 upstream merge | 不改代码则无影响。 |

### C1｜平台显示标签 — 严重度 Trivial（仅外观）

| 项目 | 内容 |
| --- | --- |
| 文件 | `src/prompt_hub/optional_models.py` |
| 代码位置 | `optional_models.py:142-148` |
| 问题 | `host` 字段是 `Windows` / `Mac` / `platform.system()` 三选一，Linux 上会显示英文 `Linux`。 |
| 原因 | 二元标签设计。 |
| 影响 | 仅影响展示文案，不影响功能。 |
| 解决方案 | 可选：向上游 PR 补一个 `Linux` 分支；或第一阶段忽略。 |
| 是否影响 upstream merge | Low。 |

---

## 3. 建议抽象（E）

**结论：不建议为 Linux 适配新增 `src/prompt_hub/platform/` 抽象层。**

理由：

1. 上游已经把平台差异收敛到**极少的数据点**（`sys.platform` 判断 3 处 + `platform.system()` 1 处），没有散落的 `if Windows: …` 分支需要治理。
2. 上游迭代极快（`1.1.0` 于 2026-09-13、`1.1.1` 预发布于 2026-09-14，另有 `fix/windows-standalone-frontend`、`ui/unify-art-direction` 活跃分支与 18 个 PR）。**任何新增的中间层都会提高 rebase 成本**，与主任务书 §1/§4/§31 的“低维护成本”目标相冲突。
3. Linux 特有逻辑天然适合放在 `deploy/linux/` 与 `scripts/linux/`——它们是新增目录，不会与上游产生冲突。

因此：**先不抽象，等 Linux 侧真的出现第二处需要平台分支的核心逻辑时再评估**（符合主任务书“不要为了形式主义增加抽象层”）。

---

## 4. Windows-only（D，保持不动）

| 组件 | 位置 | 说明 |
| --- | --- | --- |
| Compute Worker（Python） | `src/prompt_hub/windows_worker.py`、`windows_worker_core.py`、`windows_worker_support.py`、`deploy/windows-worker/` | 核心代码**从不 import**（仅 worker 内部互相 import），因此不影响 Linux Core 启动 |
| Windows 桌面宿主 | `deploy/windows-desktop/`（C#：`DesktopHost.cs`、`GitRuntime.cs`、`ShellForm.cs`、`build.ps1`） | .NET/WinForms + WebView2，Linux 无等价物 |
| Compute Worker 外壳 | `deploy/windows-shell/`（C#：`SodaComputeWorker`、托盘、诊断包） | 同上 |
| 安装器 | `deploy/windows-installer/`（Inno Setup `desktop.iss` / `worker.iss`、`prepare-runtime.ps1`） | Windows 安装体系 |
| 桌面 UI 桥 | `deploy/desktop-ui/desktop.js`（15 处盘符引用）、`BRIDGE_CONTRACT.md` | 宿主注入的桥接 UI |
| 打包脚本 | `scripts/package_windows_desktop_release.py`、`package_windows_shell_release.py`、`stage_windows_*`、`build_windows_worker_release.py` | Windows 发行流水线 |
| 测试 | `tests/test_windows_*.py`、`tests/desktop-host-regression/`（C# 项目） | 在 Linux 上为文本/逻辑断言，可继续运行 |
| 功能 | LoRA 正式训练、CUDA/GPU 侧工作 | 依赖 Windows 训练工具链 |

**原则：不动、不删、不重构。** Linux 第一步不提供对等实现。

---

## 5. macOS-only

| 组件 | 位置 | 说明 |
| --- | --- | --- |
| 启动器脚本 | `deploy/mac/*.command`（首次安装 / 启动 / 停止 / 更新 / 诊断） | 5 个 `.command` |
| 便携启动器 | `deploy/mac/portable-launcher/`（Swift + zsh） | 含 `run-server.zsh` |
| SMB 配对诊断 | `src/prompt_hub/remote_routes.py:85-105`、`desktop_connection.py:149-160` | 见 G2 |
| 打包脚本 | `scripts/build_mac_commercial_release.py`、`build_mac_portable_launcher.py` | 含 `.dmg` 与 `/usr/bin/...` 调用 |
| 测试 | `tests/test_mac_*.py`、`test_desktop_icon_signing.py` | 已带 `skipif(sys.platform != "darwin")`，Linux 上自动跳过 |

---

## 6. Linux 暂不支持（明确标注）

| 能力 | 状态 | 原因 | 处理方式 |
| --- | --- | --- | --- |
| Compute Worker（ComfyUI 执行端） | **暂不支持** | Worker 是 Windows 实体（GUI/托盘/`.bat`/`.ps1`/本机服务管理） | 标注 `Linux unsupported / future work`；未来需另立设计（HTTP/WebSocket 协议 + CLI daemon） |
| SMB 双机配对 | **暂不支持** | 见 G2，实现硬编码 macOS + GVFS 桌面会话 | 标注不支持，不提供入口 |
| LoRA 正式训练 | **暂不支持** | 上游本身也在 Windows 训练工具中完成 | 标注不支持 |
| 桌面宿主（托盘/启动器 GUI） | **暂不支持** | 上游宿主为 C#/WinForms 与 Swift | 第一版用 `systemd --user` + 浏览器访问 `127.0.0.1:8765` |
| 平台安装包（`.deb` / `.rpm` / AppImage / Snap / Flatpak） | **暂缓** | 主任务书 §18 明确排除 | 第一阶段只出 `tar.gz` + `SHA256SUMS` |
| Docker | **暂缓** | 主任务书 §19 明确排除 | 第二阶段再评估 |

---

## 7. 潜在风险

| # | 风险 | 等级 | 缓解 |
| --- | --- | --- | --- |
| R1 | 上游更新频率极高（每日多次提交、频繁 PR / Pre-release） | High | Linux 侧改动**只新增文件、不改核心**；唯一核心改动（G1）走上游 PR 而非长期携带 |
| R2 | 验证环境与真实 Ubuntu 存在差异（WSL2 的 systemd user、无桌面会话导致 `xdg-open` 不可用、`/mnt/*` 性能与权限） | Medium | `check-env.sh` 显式报告差异；CI 用真实 `ubuntu-latest` 交叉验证；文档标注 WSL2 的局限 |
| R3 | 上游 CI 只保证“测试与构建通过”，不保证“用户级部署行为”（systemd、`install.sh`、linger） | Medium | Linux 专属 CI 增加部署冒烟作业（上游没有的部分） |
| R4 | 数据目录语义被无意改变（主任务书 §24 明令禁止） | High | Linux 端只通过环境变量注入路径，绝不改数据库 schema / 资料库格式 / hash 规则 |
| R5 | 用户把 Linux 版误当成“官方全功能版” | Medium | README 标注 `Linux support: Experimental`，明确列出支持/不支持矩阵（主任务书 §20） |
| R6 | 本机 C 盘仅剩约 9.6 GB，WSL 发行版默认落在 C 盘 | Medium | 发行版安装后迁移到 D 盘；`install.sh` 不往 C 盘写大文件 |
| R7 | fork `main` 与上游历史分叉（落后 91 个 commit，另有 1 个游离 commit） | Low | Linux 工作基于 `upstream/main` 独立分支；fork 主线清理另行决定 |
| R8 | 许可证与署名（上游为 MIT，另有商业化打包脚本） | Low | 保留 `LICENSE` 与来源说明；Linux 构建标注“非官方构建” |

---

## 8. 推荐实施顺序

映射主任务书 Phase 2–10：

| 阶段 | 内容 | 是否触碰核心 |
| --- | --- | --- |
| Phase 2 | Linux compatibility design（本文档 + Implementation Plan） | 否 |
| Phase 3 | Linux native runtime：在 WSL2 Ubuntu 实跑 `uv sync` / `pytest` / `serve` | 否 |
| Phase 4 | Linux 部署：`deploy/linux/{install,uninstall,update,start,stop,status}.sh` + `soda-prompt-hub.service` | 否 |
| Phase 5 | Linux 测试：`tests/linux/`（启动、数据目录、路径、UTF-8/空格/中文、API） | 否 |
| Phase 6 | Linux CI：`.github/workflows/linux.yml`（补充上游没有的部署冒烟与 22.04/24.04 矩阵） | 否 |
| Phase 7 | 上游同步：`.github/workflows/upstream-sync.yml` | 否 |
| Phase 8 | 自动 Release：`.github/workflows/release-linux.yml`（`tar.gz` + `SHA256SUMS`） | 否 |
| Phase 9 | 文档：`docs/LINUX_INSTALL.md`、`docs/LINUX_UPDATE.md`、`docs/LINUX_DEV_ENVIRONMENT.md`、README / CHANGELOG | 否 |
| Phase 10 | 最终验收（主任务书 §27/§29） | 否 |
| 独立轨道 | G1 反哺上游 PR（`linux_local` 使用模式） | **是** |

---

## 9. 与验收标准对照（主任务书 §27 / §29）

| 验收问题 | 当前答案（基于本次审计） | 验证方式 |
| --- | --- | --- |
| 1. Linux 核心是否可以独立运行？ | 预期可以（上游 CI 已在 Ubuntu 跑通测试与构建） | Phase 3 实机 `uv run --no-sync prompt-hub serve` |
| 2. 是否需要修改核心 Python 代码？ | **不需要即可运行**；建议仅修 G1（使用模式）以修正语义 | Phase 3 实机验证 |
| 3. Windows / macOS 是否受影响？ | 不受影响（Linux 侧全部为新增文件） | 全量 `pytest` + 上游 CI 对照 |
| 4. Linux Worker 是否已实现？ | **否**（Windows-only） | 文档标注 |
| 5. 哪些功能仍 Windows-only？ | Compute Worker、桌面宿主、LoRA 训练、SMB 双机的 Windows 侧 | 见 §4 |
| 6. 是否可以通过 systemd 运行？ | 待实现（`deploy/linux/`），WSL2 可验证 `systemctl --user` | Phase 4/5 |
| 7. 是否可以安全更新？ | 待实现（`update.sh` 不动用户数据） | Phase 4 |
| 8–10. 上游更新后多久发现 / 能否自动 CI / 自动 Release？ | 待实现（§14–§17 流水线） | Phase 7/8 |
| 11. 用户数据是否与程序更新完全分离？ | 是（程序在仓库/安装目录，数据由 `PROMPT_HUB_LIBRARY_ROOT` 指向） | Phase 4 验收 |
| 12. 是否存在需要人工处理的 merge conflict？ | 预期不存在（纯新增 diff） | Phase 7 模拟上游提交 |
| 13. 是否存在无法自动 rebase 的 Linux patch？ | 只有 G1 属于核心改动，若上游未接受则需人工处理 | Phase 7 |

---

## 附录 A：复现本次审计的命令

```bash
git fetch upstream
git switch -c linux/main upstream/main

# 平台判断 / Windows 目录 / 盘符 / 外壳
git grep -nIE "sys\.platform|platform\.system|os\.name|winreg|WindowsError|pywin32" upstream/main -- src tests
git grep -nIE "USERPROFILE|LOCALAPPDATA|APPDATA|PROGRAMDATA|AppData" upstream/main -- src tests
git grep -nIE "[A-Za-z]:\\\\" upstream/main -- src tests
git grep -nIE "powershell|pwsh|cmd\.exe" upstream/main -- src tests

# macOS / SMB / 文件管理器 / 可执行文件
git grep -nIE "osascript|/Volumes|\.dmg|darwin" upstream/main -- src tests
git grep -nIE "smb://|SMB|cifs|mount" upstream/main -- src tests
git grep -nIE "xdg-open|explorer\.exe|startfile" upstream/main -- src
git grep -nIE "shutil\.which|/usr/bin/" upstream/main -- src

# 子进程 / 权限 / GPU
git grep -nIE "subprocess\.(run|Popen|check_output|call)" upstream/main -- src
git grep -nIE "chmod|is_symlink" upstream/main -- src
git grep -nIE "nvidia-smi|torch|cuda|rocm" upstream/main -- src

# 测试规模与平台跳过
git grep -h -E "^\s*def test_" upstream/main -- tests | wc -l
git grep -nE "pytest\.mark\.skipif" upstream/main -- tests
```

## 附录 B：本次审计**未能**覆盖、需要在真实 Ubuntu 上验证的项

1. `uv sync --locked` 在 Linux 上解析出的 wheel 集合（`onnxruntime`、`numpy`、`pillow`）与上游 CI 完全一致。
2. `pytest` 在 Linux 上的跳过/失败明细（预期仅 4 个 macOS 文件跳过）。
3. `prompt-hub serve` 冷启动与 `GET /`、`/api/health`、`/api/stats` 的实际响应。
4. 中文 / 空格 / UTF-8 路径下的资料库读写与缩略图生成。
5. `xdg-open` 在无桌面会话（纯 WSL2、无 GUI）时的失败路径是否返回可读错误而不是崩溃。
6. `systemctl --user` 下 unit 的启动、重启、日志进入 journald、`loginctl enable-linger` 行为。
7. `install.sh` / `update.sh` 的幂等性与“更新不动用户数据”的实证。
