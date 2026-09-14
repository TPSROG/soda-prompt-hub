# Soda Prompt Hub Windows Desktop

这是 Windows 完整单机版的图形启动台。它用 `.NET 8 + WinForms + WebView2` 承载共享 Desktop UI，
在同一台Windows上管理Prompt Hub Core，默认自动准备并启动本机Compute Worker。用户可手动停止本机Worker，
但不需要再开独立的Soda Compute Worker，也不经过SMB配对。

普通用户请从[Windows单机Release](https://github.com/cOkieeman/soda-prompt-hub/releases/tag/v1.1.1-windows-standalone-20260914)
下载Setup，按[快速开始](../../docs/QUICK_START.md)安装；下方构建命令仅供维护人员。

## 产品行为

- 双击 `Soda Prompt Hub.exe`，自动检查并启动 `127.0.0.1:8765` 的 Core。
- 商业安装版始终使用包内 Python 3.12 和固定依赖，不创建 `.venv`，也不在首次启动时联网安装。
- 便携开发包缺少包内 runtime 时，才会尝试复用 Python 3.12 并在程序目录创建 `.venv`；进度写入
  `setup.log`。
- Core 日志位于 `%LOCALAPPDATA%\Soda Prompt Hub\Logs\core.log`。
- 用户资料位于 `%USERPROFILE%\Documents\Soda Prompt Hub\prompt-library`。
- 本机任务目录固定使用 `%USERPROFILE%\Documents\Soda Prompt Hub\Bridge\prompt-hub`，继续复用现有 bridge 协议。
- 单机Worker配置存于 `%LOCALAPPDATA%\Soda Prompt Hub\Desktop Worker`，与独立Worker的Compute Worker目录分离。
- 外部 Core 或 Worker 只显示状态，不会被启动器接管或强制停止。
- 关闭窗口只收起到托盘；“退出启动器”保留服务；只有“退出并停止本机服务”会停止当前启动器持有的进程。

## 构建

在 Windows 10/11 和 .NET 8 SDK 中运行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\deploy\windows-desktop\build.ps1
```

输出是 self-contained 的 Desktop Shell 便携 payload。面向普通用户时，再使用
`deploy/windows-installer/build.ps1` 把它转换为包含固定 Python runtime、依赖和 WebView2 bootstrapper 的
per-user Setup；最终用户不需要 `.NET Runtime`、Python、`uv` 或 SDK。

版本从根 `RELEASE.json` / `pyproject.toml` 读取，当前源码候选为 `1.1.1`。发布包含 Core、Worker、共享 UI
和三层 SHA-256 manifest，但不包含用户数据库、模型、真实 `worker-config.json` 或凭据。
