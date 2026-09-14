# Soda Prompt Hub — Linux 适配

> **非官方构建。** 本目录归属于社区维护的 Linux 适配分支（`linux/main`），不是
> [cOkieeman/soda-prompt-hub](https://github.com/cOkieeman/soda-prompt-hub) 的官方发行。
> 上游项目、许可证与各平台说明见仓库根目录 `README.md` 与 `LICENSE`。

## 这是什么

在不改动上游 macOS / Windows 功能的前提下，让 Soda Prompt Hub 在 Linux 上原生运行，
并建立一套跟随上游更新、自动测试、自动构建的长效维护机制。

上游版本基线：`1.1.1`（`upstream/main` = `e96249b`）。

## 支持状态

| 能力 | Linux 状态 |
| --- | --- |
| Core：资料库、检索、创作、审核、数据集整理 | **支持**（Ubuntu 24.04 实测；22.04 见下） |
| systemd 用户服务、安装 / 更新 / 卸载脚本 | **支持** |
| CLI（`prompt-hub` / `soda-prompt-hub`） | **支持** |
| Compute Worker（本机 ComfyUI 执行端） | 暂不支持（Windows-only） |
| SMB 双机配对 | 暂不支持（上游实现硬编码 macOS） |
| LoRA 正式训练 | 暂不支持（Windows-only） |
| 桌面宿主（托盘 / 启动器 GUI） | 暂不支持，用 systemd + 浏览器代替 |
| `.deb` / `.rpm` / AppImage / Snap / Flatpak | 暂不提供，第一阶段只出 `tar.gz` + `SHA256SUMS` |

支持状态以 **Experimental** 对待：核心与部署链路已实测，但不承诺与官方安装包同样的验收强度。

## 怎么用

```bash
git clone https://github.com/TPSROG/soda-prompt-hub.git
cd soda-prompt-hub
git switch linux/main
./deploy/linux/install.sh
```

完整说明见 [安装指南](INSTALL.md) 与 [更新指南](UPDATE.md)。

常用命令：

```bash
soda-prompt-hub status        # 安装位置、服务状态、监听地址、健康检查、数据占用
soda-prompt-hub logs          # journalctl --user -u soda-prompt-hub -f
soda-prompt-hub update        # 安全更新（不动用户数据）
```

程序与用户数据完全分离：程序在仓库目录，数据默认在 `~/.local/share/soda-prompt-hub/`。

## 这个分支做了什么

| 阶段 | 内容 | 证据 |
| --- | --- | --- |
| Phase 1 | 仓库审计：找出全部平台耦合点并分级 | [兼容性审计](COMPATIBILITY_AUDIT.md) |
| Phase 2 | 设计决策与实施计划（含"明确不做"清单） | [实施计划](IMPLEMENTATION_PLAN.md) |
| Phase 3 | Linux 原生运行验证 | WSL2 Ubuntu 24.04 实测通过 |
| Phase 4 | `deploy/linux/`：安装 / 卸载 / 更新 / 启停 / 状态 + systemd 用户服务 | 14 项实机验收见实施计划 §7 |
| Phase 5 | `tests/linux/`：部署层静态契约测试 + Linux 行为测试 | 25 个用例；完整套件 577 passed |
| Phase 6 | `.github/workflows/linux.yml`：lint / 22.04+24.04 测试 / 部署冒烟 / systemd 用户服务 | 见 Actions 运行记录 |
| Phase 7 | `.github/workflows/upstream-sync.yml`：每日检查上游，自动开同步 PR，冲突开 Issue | 设计见实施计划 |
| Phase 8 | `.github/workflows/release-linux.yml`：版本变化且 CI 通过时产出 `tar.gz` + `SHA256SUMS` | 打包逻辑已端到端实测 |
| Phase 9 | 文档：本目录、README 的 Linux 章节、CHANGELOG | 本文件与 [INSTALL](INSTALL.md) / [UPDATE](UPDATE.md) |
| 附加 | 修复上游一处真实的 Linux 缺陷（见下节） | `fix: pin media types for images we serve ourselves` |

**刻意的约束**：Linux 侧的改动几乎全部是新增文件（`deploy/linux/`、`scripts/linux/`、
`tests/linux/`、`docs/linux/`、三个工作流），核心代码只动了下面这一个真实缺陷，
目的是让分支容易跟随上游 rebase。

## 本分支修复的上游缺陷：WebP 缩略图被当成二进制流下发

| 项目 | 内容 |
| --- | --- |
| 现象 | 在 Ubuntu 22.04 上，资料库来源缩略图、创作项目结果图返回 `Content-Type: application/octet-stream` 而不是 `image/webp`，浏览器不会内联显示图片 |
| 根因 | 若干 `FileResponse(path)` 没有显式 `media_type`，Starlette 于是调用 `mimetypes.guess_type()`；**Python 内置的 MIME 表不含 `.webp`**，只有系统 `/etc/mime.types` 提供映射时才知道它。Ubuntu 24.04 有该映射，22.04 没有 |
| 影响 | 任何 `/etc/mime.types` 不完整的 Linux（含 22.04 LTS、最小化容器、服务器镜像）都会命中；与平台无关，Windows 上也存在同类隐患 |
| 修法 | 新增 `prompt_hub.media.media_type_for(path)`，对项目自己产出的图片格式给出确定答案，其余后缀仍交给 `mimetypes`；应用到 4 个图片端点 |
| 复现 | 隐藏 `/etc/mime.types` 后：修复前 3 个测试失败，修复后全部通过 |
| 位置 | `src/prompt_hub/media.py`、`api.py`、`source_routes.py`、`workspace_routes.py`；回归测试 `tests/test_media_types.py` |

### 准备提交给上游的 PR（可直接复制）

**标题**

```text
fix: 显式指定图片媒体类型，不再依赖系统 MIME 数据库
```

**正文**

```markdown
## 问题

若干 `FileResponse(path)` 没有传 `media_type`，Starlette 会退回 `mimetypes.guess_type()`。
Python 内置的 MIME 表不含 `.webp`，该映射只能来自系统 `/etc/mime.types`：

- Ubuntu 24.04：有 `image/webp webp` → 正常
- Ubuntu 22.04（以及没有 media-types 数据的最小化镜像）：没有该映射 → `guess_type` 返回 `None`
  → 响应变成 `Content-Type: application/octet-stream`

后果是缩略图和结果图在浏览器里不再内联显示，而是被当作文件下载。

## 复现

```bash
uv run pytest tests/test_api.py::test_api_health_stats_search_and_page -q
# 在 ubuntu-22.04 上，或先把 /etc/mime.types 移走后运行：
# AssertionError: assert 'application/octet-stream' == 'image/webp'
```

## 改动

- 新增 `prompt_hub.media.media_type_for(path)`：对项目自己产出的图片格式
  （webp / png / jpg / jpeg / gif / avif / bmp / tif / tiff）返回确定类型，
  其余后缀仍然交给 `mimetypes`，未识别时回退 `application/octet-stream`。
- 应用于 4 个图片端点：资料库来源媒体、创作项目结果图、网页收藏媒体、数据集工作区原图。
- 新增 `tests/test_media_types.py`：把 `mimetypes.guess_type` 打桩成永远返回 `None`
  （模拟缺少系统 MIME 数据库的环境），断言上述格式仍返回正确类型。

行为变化仅限"以前依赖系统 MIME 数据库、现在有确定答案"，不改变任何接口。

## 验证

- `uv run pytest -q`：577 passed, 9 skipped（Ubuntu 24.04）
- 隐藏 `/etc/mime.types` 后重跑受影响的端点测试：64 passed
- `ruff format --check .` / `ruff check .` / `ty check src/` 全部通过
```

### 准备提交给上游的第二个 PR（测试稳定性，可选）

**标题**

```text
test: 修正心跳新鲜度用例的时间戳漂移
```

**正文**

```markdown
## 问题

`tests/test_desktop_connection.py::test_connection_only_reports_fresh_live_worker`
的参数表在**收集阶段**就计算 `datetime.now(UTC) + timedelta(minutes=2)`；
而 `connection_summary()` 判定 stale 的条件是 `age < -MAX_CLOCK_SKEW(-15s)` 或
`age > HEARTBEAT_MAX_AGE(25s)`。

因此当该用例在"收集后 105 ~ 145 秒"之间执行时，`age` 落在 -15 ~ +25 秒内，
期望 `stale` 却得到 `connected` —— 用例偶发失败。

这不是平台相关缺陷，机器越慢越容易命中：在整轮耗时 223 秒的 ubuntu-22.04 上命中，
同一提交在 ubuntu-24.04 上通过。

## 改动

把"未来 2 分钟"的时间戳移到用例内部生成（参数表里用哨兵值占位），
让它与判定使用同一时刻的时钟。等待更久的"过去 2 分钟"用例不受影响。
```

## 上游同步机制

```text
upstream（官方）── 每日检查 ──▶ 有更新？
                              │
                     ┌────────┴────────┐
                     ▼                 ▼
              建同步分支并合并       合并冲突
                     │                 │
                     ▼                 ▼
              自动跑 Linux CI      开 Issue（人工处理）
                     │
                     ▼
                 开 Pull Request
```

同步分支名 `linux/sync-<上游短 SHA>`，一推送就自动触发 Linux 工作流；基线记录在
`.github/upstream-baseline.txt`，随合并一起前进。**不会**把上游直接合并进维护分支。

> 平台限制：GitHub 只会运行**默认分支**上存在的 `schedule` 与 `workflow_run` 工作流。
> 因此每日检查与自动发布需要把仓库默认分支设为 `linux/main`（或在后续阶段把 Linux 线合并进 `main`）。

## 已知限制

| 项目 | 说明 |
| --- | --- |
| 数据集目录浏览不含外接卷 | `browse_roots()` 只认 `$HOME` 与 macOS `/Volumes`，Linux 上的 `/media`、`/mnt` 不在范围内（审计 §11 F1） |
| 主目录快捷入口仅英文名 | `Desktop / Pictures / Downloads`，中文等 locale 下不显示（有 `is_dir()` 保护，不报错，审计 §11 F2） |
| 使用模式语义 | 核心只有 `windows_local` / `mac_remote` 两种模式，Linux 目前按 `mac_remote` 语义运行，界面文案仍偏 macOS（审计 G1） |
| Ubuntu 22.04 | 需要本分支的 WebP 媒体类型修复；未修复前有 3 个测试失败 |

## 验证方式

```bash
scripts/linux/check-env.sh              # 环境自检（只检查不安装）
./deploy/linux/status.sh                # 服务与数据状态
uv run pytest tests/linux -q            # 25 个 Linux 用例
uv run pytest -q                        # 完整套件
```

CI 见仓库 **Actions → Linux**：`lint`、`Tests on ubuntu-22.04`、`Tests on ubuntu-24.04`、
`systemd 用户服务` 四个作业。

## 文档索引

| 文档 | 内容 |
| --- | --- |
| [INSTALL.md](INSTALL.md) | 安装步骤、参数、目录布局、排错 |
| [UPDATE.md](UPDATE.md) | 安全更新、回滚、从发行包更新 |
| [COMPATIBILITY_AUDIT.md](COMPATIBILITY_AUDIT.md) | 平台耦合审计与实测结论 |
| [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) | 设计决策、阶段计划、验收证据 |
| [DEV_ENVIRONMENT.md](DEV_ENVIRONMENT.md) | WSL2 开发/测试环境的实际状态 |
