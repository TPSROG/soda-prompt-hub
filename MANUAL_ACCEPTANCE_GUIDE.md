# Prompt Hub · 人工验收入口

当前桌面构建请使用[1.1.1 pre1 两模式手动验收清单](docs/acceptance/manual-1.1.1-pre1-20260914.md)。
这份旧路径保留为导航，不再维护一套重复操作步骤。

## 先选测试模式

| 模式 | 启动方式 | 验收步骤 |
| --- | --- | --- |
| Windows 单机 | 只开 Soda Prompt Hub，自动管理本机 Core / Worker；ComfyUI 自行开启 | W1–W6 |
| Mac 管理 Windows | Mac 开 Prompt Hub；Windows 开独立 Soda Compute Worker 和 ComfyUI | M1–M6 |

两种模式分开测试，避免同时运行两种 Windows 启动器。项目和审核记录保存在运行 WebUI 服务的设备，
不是无论什么模式都保存在 Mac。

## 验收范围

1. 按新清单完成安装前备份、退出旧服务、核对包名/日期/hash。
2. 先走启动、设备状态、AI补全、出图、保存、退出重开的核心闭环。
3. 再测试资料更新、清单更新、扫描、打标、审核、ZIP交付和已安装的可选模型。
4. 双机模式额外测首次共享授权、实时心跳、断开恢复和跨设备复制。
5. 每项记录“通过 / 失败 / 未测”，失败按清单中的模板反馈；截图不要含 Key 或密码。

2026-09-14的1.1.1包以 Pre-release 发布，尚未正式平台签名。
代码测试和打包校验不代表新包完整原生人工验收完成；不能只用打开窗口或出过一张图代替全部验收。

## 操作参考

- [下载与快速开始](docs/QUICK_START.md)
- [核心工作流](docs/WORKFLOWS.md)
- [安装、升级与数据边界](docs/COMMERCIAL_RELEASE.md)
- [常见问题与排错](docs/TROUBLESHOOTING.md)

`FINAL_TEST_REPORT.md`、`completion_audit.md` 是历史版本证据，保留原结论，不作为本次验收通过证明。
