# Mac 使用与维护

Mac 是事实源：项目、审核、Caption、任务记录和冻结版本都以 Mac 保存的内容为准。

## 启动、停止与诊断

安装后的日常入口位于：

```text
$HOME/Applications/Soda Prompt Hub
```

- `Soda Prompt Hub.app`：推荐的日常入口；双击后显示启动状态，在后台启动服务并打开页面，不显示 Terminal。
- `启动-Prompt-Hub.command`：启动本地服务并打开 `127.0.0.1:8765`。
- `停止-Prompt-Hub.command`：检查后台任务后安全停止。
- `诊断-Prompt-Hub.command`：检查程序、数据库、视觉索引、WD14、磁盘和服务。
- `更新-Soda-Prompt-Hub.command`：从新下载的完整源码包执行安全更新。

有扫描、打标或草稿任务运行时，停止脚本会先提示。优先在页面取消或等待完成，再关闭服务。

`.app` 启动器可以复制到桌面或 Applications。实际程序仍应由首次安装器放在
`$HOME/Applications/Soda Prompt Hub`，避免 macOS 对 Documents 等目录的后台访问限制。启动器会优先
使用构建时指定的程序目录，找不到时再检查默认安装目录。如果启动失败，服务日志位于
`$HOME/Library/Logs/Soda Prompt Hub/server.log`。

服务就绪后，启动台保留设备连接卡片，方便确认状态；可以手动收起。关闭窗口只隐藏启动台，不会停止 Core。
菜单栏的应用图标旁会显示“在线”“断开”“本机”等状态，入口提供：

- 打开启动台或工作台。
- 打开日志和数据目录。
- 重新检查设备连接，或从连接卡片进入设备设置。
- 退出启动器但保留当前服务。
- 当服务确实由当前启动器托管时，退出并停止服务。

启动失败时窗口会停留在错误状态，可以直接查看日志并重试。为了避免误杀其他进程，启动器不会重启或
停止一个并非由当前 App 启动的 Core。

设备连接每 5 秒自动检查一次。“共享已连接”仅代表能访问任务目录；“已连接 · 可以计算”还要求新版 Worker
持续发送心跳且 ComfyUI 可访问。心跳超过 25 秒未更新会显示连接中断，旧 Worker 的历史自检不算在线证据。
断开或恢复时启动台会显示一次提示，状态不变时不会重复弹窗。未配置设备时显示本机模式，不影响资料管理。

维护者可以从源码根目录重新构建启动器：

```bash
uv run --no-sync python scripts/build_mac_portable_launcher.py \
  --runtime-root-hint "$HOME/Applications/Soda Prompt Hub"
```

默认产物为 `dist/Soda Prompt Hub.app`。这是轻量启动器，不内置 Python 和模型；首次使用仍需运行首次
安装器准备运行环境。直接让后台 App 从 Documents 内的开发仓库运行，可能受到 macOS 隐私权限限制。

面向普通用户分发时，维护者应改用无签名商业构建器：

```bash
.venv/bin/python scripts/build_mac_commercial_release.py
```

它生成架构对应的自包含 `.app`、带 Applications 快捷入口的标准 DMG、包内 SHA-256 manifest 和
`COMMERCIAL_RELEASE.json`。最终用户不需要预装 Python 或 `uv`；覆盖旧 `.app` 即可升级，删除 `.app`
即可卸载，`~/Documents/Soda Prompt Hub` 中的个人资料不会随程序删除。当前产物尚未 Developer ID 签名或
notarize，首次打开会看到 macOS 的未知开发者提醒。

## 安全更新顺序

1. 从 GitHub Release 下载并完整解压新版源码 ZIP。
2. 不要在已安装目录里覆盖文件。
3. 在新版解压目录的 `deploy/mac` 双击 `更新-Soda-Prompt-Hub.command`。
4. 更新器核对 `pyproject.toml` 与 `RELEASE.json` 的版本一致性。
5. 更新器先停止旧服务，再建立个人资料备份和旧程序快照。
6. 新版在临时目录准备依赖；初始化成功后才正式启用。
7. 新版初始化失败时，更新器会保存失败副本并恢复旧程序。

更新只替换程序。提示词 Git 来源、模型、个人数据库、图片和外部数据集不会随代码包更新。

默认个人资料备份位置：

```text
$HOME/Documents/Soda Prompt Hub/backups/prompt-hub
```

默认旧程序快照位置：

```text
$HOME/Library/Application Support/Soda Prompt Hub/program-backups
```

## 备份与恢复

开发者或维护人员可以在安装目录运行：

```bash
uv run --no-sync prompt-hub backup
uv run --no-sync prompt-hub verify-backup /绝对路径/备份目录
```

恢复必须先写入一个不存在或为空的新目录：

```bash
uv run --no-sync prompt-hub restore /绝对路径/备份目录 \
  --destination "$HOME/Documents/Soda Prompt Hub/restore-tests/prompt-hub-YYYYMMDD"
```

核对新目录正确后，再单独决定是否切换正式资料位置。程序不提供覆盖当前资料库的一键恢复。

外部导入的数据集原图仍在原文件夹，需要使用移动硬盘、NAS 或其他方式另行备份。

## 自定义位置

- `PROMPT_HUB_LIBRARY_ROOT`：个人资料目录。
- `PROMPT_HUB_MODELS_ROOT`：本地模型目录。
- `PROMPT_HUB_INSTALL_ROOT`：首次安装和更新时的程序目录。
- `PROMPT_HUB_PORT`：本地页面端口，默认 `8765`。

普通用户不需要设置这些变量。自定义后应让启动、停止、诊断和更新使用同一组设置。

## 手机访问

默认 `127.0.0.1` 仅限 Mac 本机，最安全。若主动使用局域网模式，确保 Wi-Fi 是可信网络，并在
使用后恢复本机监听。手机只是在浏览 Mac 上的页面；数据仍保存在 Mac，Windows 连接方式不变。
