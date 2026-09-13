# Windows Worker 交付说明

这份旧路径继续保留，公开用户应阅读 [Windows Worker 完整指南](docs/WINDOWS_WORKER.md)。

普通用户从[Mac + Windows Worker Release](https://github.com/cOkieeman/soda-prompt-hub/releases/tag/v1.1.0-mac-windows-20260913)
下载Worker Setup，安装后从开始菜单打开控制台，在设置中确认ComfyUI和共享任务目录。
Windows单机应使用[Desktop](docs/QUICK_START.md#windows-单机第一次安装)，不另开这份独立Worker。

仅维护人员使用纯脚本Worker ZIP时，按包内离线教程 `README-WINDOWS.md` 的顺序：

```text
校验发行包 → 0-首次配置.bat → 启动 ComfyUI → 1-先自检.bat → 2-启动Worker.bat
```

版本兼容、升级和 Mac/Windows 文件关系分别见：

- [正式版本体系](docs/RELEASES.md)
- [设备与文件关系](docs/ARCHITECTURE.md)
- [常见问题与排错](docs/TROUBLESHOOTING.md)
