# Soda Compute Worker Desktop Shell

这是 Windows Worker 的图形控制台源码。它使用 `.NET 8 + WinForms + WebView2` 承载与 Mac
启动器同源的 Desktop UI，不改变 Worker bridge 协议，也不会迁移或覆盖 `worker-config.json`。

## 产品行为

- 双击 `Soda Compute Worker.exe` 打开，无命令窗口。
- 可启动、停止和自检 Worker；运行日志写入 Worker 目录下的 `logs/`。
- Worker 运行时可以收起到系统托盘。
- 正在执行 `processing` 任务时拒绝普通停止，避免中断任务和结果回传。
- 第二次双击只唤回现有窗口，不启动第二个控制台。
- 外部 `.bat` 或命令行启动的 Worker 只显示为 `EXTERNAL`，控制台不会接管或强制停止。
- 退出控制台默认保留 Worker；托盘另有“退出并停止 Worker”。

## Windows 构建

需要 Windows 10/11 和 .NET 8 SDK。WebView2 Runtime 已随现代 Windows/Edge 安装；若被精简，需先安装
Microsoft Edge WebView2 Runtime。

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\deploy\windows-shell\build.ps1
```

构建脚本生成 self-contained 的 `win-x64` 目录和 ZIP，不要求目标电脑另装 .NET Runtime。版本从
`deploy/windows-worker/RELEASE.json` 读取，当前源码候选为 `1.1.1`。发布目录中的 `校验桌面包.ps1` 会按
`PACKAGE_MANIFEST.sha256` 校验 `.exe`、Desktop UI 和内置 Worker；真实配置不在清单或 ZIP 中。

## 安装到现有 Worker

先关闭旧 Worker，再执行：

```powershell
.\deploy\windows-shell\install-to-worker.ps1 `
  -PublishedRoot ".\deploy\windows-shell\dist\Soda-Compute-Worker-<版本>-win-x64" `
  -WorkerRoot "D:\你的现有Worker目录"
```

安装脚本会先记录真实 `worker-config.json` 的 SHA-256，复制结束后再次校验；它不会从发布目录复制
同名配置。之后直接双击 Worker 目录里的 `Soda Compute Worker.exe`。

## 环境约定

商业安装版优先使用安装目录内的 Python 3.12 runtime，不要求用户安装 Python。便携开发包默认依次寻找
`py.exe -3.12` 和 `python.exe`；若 Python 位于非标准位置，可以设置 `SODA_PROMPT_HUB_PYTHON` 为
`python.exe` 的绝对路径。
