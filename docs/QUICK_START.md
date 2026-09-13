# 快速开始

这份说明只负责让普通 Mac 用户第一次把 Soda Prompt Hub 安装并打开。Windows 用户请直接阅读
[商业分发与安装说明](COMMERCIAL_RELEASE.md)。完成后再按需要阅读
[核心工作流](WORKFLOWS.md)或[Windows Worker 指南](WINDOWS_WORKER.md)。

## 安装前准备

- macOS Apple Silicon 设备；
- 可访问 GitHub 和公开提示词仓库的网络；
- 至少预留数 GB 空间。带图片的视觉资料库会占用更多空间；
- 下载的是 Apple Silicon DMG；维护人员才需要完整 Release 源码 ZIP。

## 第一次安装

1. 打开 `Soda-Prompt-Hub-1.1.0-macOS-arm64.dmg`。
2. 把 `Soda Prompt Hub.app` 拖入 Applications。
3. 第一次打开时，如果 macOS 提示无法验证开发者，关闭提示后在 Finder 中右键 App，选择“打开”。
4. App 会使用包内 Python 3.12 和固定依赖启动 Core，不需要安装 Homebrew、Python 或 `uv`。
5. 启动台显示就绪后打开工作台；本机地址仍是 <http://127.0.0.1:8765/>。

安装后的程序位置：

```text
/Applications/Soda Prompt Hub.app
```

新用户的个人资料位置：

```text
$HOME/Documents/Soda Prompt Hub/prompt-library
```

如果电脑已经有旧版 `$HOME/Documents/Codex/soda-person/prompt-library`，程序会继续沿用旧目录，
不会复制出第二套资料。

## 第一次打开

首页出现“把推荐提示词资料装到本机”时：

1. 先查看来源名和许可证提示；
2. 点“安装推荐资料库”；
3. 等待下载和本地索引完成；
4. 某个来源失败时可稍后在“资料管理”中单独重试。

Kisegaeningyou 包含较多视觉图片，第一次下载可能比纯文字仓库慢。AnimaDex 首次安装只使用仓库
自带的角色、画师和作品缩略图样例；完整公共目录需要在 `animadex.net` 的 Account 页面生成
“Offline dataset export” token，并按 AnimaDex 自己的导入说明下载到独立 `animadex-data` 目录。
Prompt Hub 不保存 token，也不会把下载数据放进 GitHub 仓库。点“暂时跳过”只隐藏当前提醒，
不会关闭资料管理功能。

## 每天使用

- 启动：双击 Applications 中的 `Soda Prompt Hub.app`。
- 关闭启动台：关闭窗口；Core 会继续在后台运行。
- 完全退出：使用菜单栏 `S` 菜单中的退出选项。
- 页面打不开：从启动台或菜单栏打开日志；维护人员仍可使用源码包中的诊断脚本。

只用 Mac 时，现在就可以查资料、写 Prompt、导入 OC、整理和打标数据集。需要 Windows 出图时，
继续阅读[Windows Worker 指南](WINDOWS_WORKER.md)。

## 怎样确认安装正确

- 首页右侧能看到当前程序版本和数据结构版本；
- “提示词库”能打开，不出现空白错误页；
- “数据集”可以选择一个本地图片目录并进行只读扫描；
- “设备连接”在未配置 Windows 时显示“尚未配置”，而不是连接失败。

若不符合，按[常见问题与排错](TROUBLESHOOTING.md)处理。
