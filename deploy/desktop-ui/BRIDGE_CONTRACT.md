# Soda Desktop Host Bridge Contract

共享 Desktop UI 不直接访问文件系统、启动进程或打开外部 URL。平台宿主只通过一个受限消息通道提供能力。

## Transport

Web UI 向宿主发送：

```json
{
  "id": "desktop-1750000000000-1",
  "method": "getStatus",
  "params": {}
}
```

macOS 使用 `window.webkit.messageHandlers.sodaHost.postMessage(...)`。Windows WebView2 使用
`window.chrome.webview.postMessage(...)`，消息结构完全相同。

宿主调用以下函数返回结果：

```js
window.SodaDesktop.resolve(id, payload)
window.SodaDesktop.reject(id, message)
window.SodaDesktop.receiveStatus(status)
```

## Allowed methods

| Method | Params | Result | 说明 |
|---|---|---|---|
| `getStatus` | `{}` | `{ status }` | 获取当前启动与服务状态 |
| `checkConnection` | `{}` | `{ status }` | Mac 立即检查设备连接，后台每 5 秒刷新 |
| `reconnectDevice` | `{}` | `{ status }` | Mac 连接已保存的 Windows 共享，未配对时打开设备设置；不保存密码 |
| `openDeviceSettings` | `{}` | `{ status }` | Mac 打开本机 WebUI 的设备设置页 |
| `openWorkspace` | `{}` | `{ status }` | 仅打开宿主已经验证身份的本地 WebUI |
| `restartCore` | `{}` | `{ status }` | 重启当前宿主持有的 Core |
| `retryCore` | `{}` | `{ status }` | 从错误状态重新检查并启动 Core |
| `openLogs` | `{}` | `{ status }` | 用系统文件管理器打开日志目录 |
| `exportDiagnostics` | `{}` | `{ path, message }` | Windows 导出白名单状态、发布元数据与脱敏日志尾部，明确排除配置、数据库、任务和素材 |
| `openDataFolder` | `{}` | `{ status }` | 打开现有用户资料根目录，不创建或迁移数据 |
| `hideWindow` | `{}` | `{ status }` | 收起启动器窗口，后台服务继续运行 |
| `startWorker` | `{}` | `{ status }` | 无窗口启动当前目录中已验证配置的 Worker |
| `stopWorker` | `{}` | `{ status }` | 只停止当前宿主持有且没有执行任务的 Worker |
| `selfTestWorker` | `{}` | `{ status }` | Worker 停止时运行独立自检 |
| `openConfig` | `{}` | `{ status }` | 打开固定的 `worker-config.json`；缺失时只从示例创建 |
| `getWorkerConfig` | `{}` | `{ config }` | 读取可视化设置所需的白名单字段 |
| `chooseFolder` | `{ "initial": "..." }` | `{ path }` | 只调用系统目录选择器，不直接采用 UI 任意路径 |
| `saveWorkerConfig` | `{ "config": { ... } }` | `{ status }` | 校验本机 URL 与绝对路径，备份后原子保存白名单字段 |

未知 method 必须拒绝。Web UI 不接受任意 shell、路径或 URL 参数。

## Status model

```json
{
  "phase": "checking | starting | ready | attention",
  "step": 1,
  "stepTitle": "正在确认服务身份",
  "stepDetail": "127.0.0.1:8765",
  "coreState": "CHECKING | STARTING | READY | ERROR",
  "coreDetail": "127.0.0.1:8765",
  "libraryState": "LOCAL",
  "libraryDetail": "Documents / Soda Prompt Hub",
  "computeState": "OPTIONAL",
  "computeDetail": "可以稍后连接 Windows",
  "version": "1.1.0",
  "releaseChannel": "Stable · Local first",
  "checkedAt": "12:33:13",
  "canOpenWorkspace": false,
  "canRestart": false,
  "errorTitle": "",
  "errorDetail": ""
}
```

Windows Worker 模式在同一对象中增加 `comfyState`、`comfyDetail`、`taskState`、`taskTitle`、
`taskDetail`、`canPrimary`、`primaryCommand` 和 `primaryLabel`。它允许额外主状态 `idle`（环境就绪但
Worker 未启动）和 `busy`（已领取任务）。宿主仍必须忽略 UI 传入的路径或命令参数。

`phase` 是 UI 状态机的唯一主状态。颜色只辅助表达，正文状态必须始终可读。

## Browser preview

没有原生 bridge 时，可使用 `?preview=starting`、`?preview=ready` 或 `?preview=attention` 做只读视觉验收。
Windows Worker 使用 `?product=worker&preview=idle|starting|ready|busy|attention`。
该参数在 WKWebView 中不会覆盖宿主状态。
