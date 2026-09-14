# Linux Compute Worker（实验性）

把本机（或局域网内任意 Linux 机器）变成 Soda Prompt Hub 的计算节点：
从桥接目录领取任务 → 调用 ComfyUI 的 HTTP API 出图 → 把结果与校验和写回桥接目录。

> 状态：**实验性**。协议层已端到端验证（见下方"验证结果"），但**界面侧的设备配置**目前仍带
> macOS/Windows 假设（审计 G1/G2），从 UI 直接配对还需要后续工作；当前可用方式是命令行与桥接目录。

## 前置条件

| 项目 | 要求 |
| --- | --- |
| Core | 已按 [INSTALL.md](INSTALL.md) 安装（`install.sh --with-worker` 会顺带准备 Worker） |
| ComfyUI | 一个可访问的实例（本机或局域网），HTTP API 可达，例如 `http://127.0.0.1:8188` |
| GPU | **不需要**在 Linux 侧；出图算力来自那台跑 ComfyUI 的机器 |
| 桥接目录 | 与 Core 共用（单机时就是本地目录，不需要 SMB） |

## 安装

```bash
./deploy/linux/install.sh --with-worker
```

会额外完成：

| 内容 | 位置 |
| --- | --- |
| Worker 配置 | `~/.local/share/soda-prompt-hub/worker-config.json`（已存在则不覆盖） |
| 桥接目录 | `~/.local/share/soda-prompt-hub/worker-share/prompt-hub/{outbox,inbox,processing,completed,failed,packages}` |
| 便利命令 | `~/.local/bin/soda-worker` |
| systemd 单元 | `~/.config/systemd/user/soda-worker.service`（**默认不启用**） |

先改 `comfyui_url` 指向你的 ComfyUI，然后：

```bash
soda-worker self-test        # 检查配置、桥接目录写入权限与 ComfyUI 可达性
soda-worker once             # 只处理一个任务，便于验证
systemctl --user enable --now soda-worker   # 常驻（或 soda-worker start 前台运行）
soda-worker logs             # 跟踪日志
```

## 配置字段

```json
{
  "bridge_root": "~/.local/share/soda-prompt-hub/worker-share/prompt-hub",
  "comfyui_url": "http://127.0.0.1:8188",
  "worker_id": "linux-worker",
  "role": "compute_5060ti",
  "poll_interval_seconds": 2,
  "history_poll_seconds": 1,
  "task_timeout_seconds": 1800,
  "http_timeout_seconds": 30,
  "lora_roots": [],
  "model_roots": []
}
```

- `comfyui_url` 是**唯一必须改**的字段；
- `lora_roots` / `model_roots` 只在需要 LoRA 只读清单、模型清单快照时填写；
- `role` 需与 Core 侧设备登记的 `role` 一致（默认 `compute_5060ti`）。

## 桥接协议

来自 `src/prompt_hub/compute_bridge.py`（`soda-compute-bridge-v2`）：

```text
Core ──写任务──▶ outbox/  ──worker 领取──▶ processing/ ──▶ completed/ 或 failed/
Core ◀─读结果── inbox/（结果 JSON + 产物目录，含每个产物的 sha256）
```

任务信封必填：`task_id`、`task_type`、`target_role`、`created_at`、`payload`、`manifest`（sha256 校验）。
结果信封必填：`task_id`、`task_type`、`worker_id`、`status`、`started_at`、`finished_at`、`source_hashes`、`outputs`。
Core 在导入前会逐个校验产物 sha256（`RemoteNodeStore.verify_returned_task`）。

## 支持的任务类型

| 类型 | Linux Worker |
| --- | --- |
| `comfyui_generate`（出图） | ✅ 已端到端验证 |
| `workflow_test`、`result_metadata`、`wd14_batch` | ✅ 由同一 Worker 处理 |
| `lora_catalog_snapshot`、`model_catalog_snapshot`（只读清单） | ✅ 可用于整理 LoRA/模型清单 |
| `lora_train`（正式训练） | ❌ 仍仅 Windows（上游训练工具链） |

## 验证结果

在 WSL2 Ubuntu 24.04 上完成（假 ComfyUI 返回真实 PNG）：

| 步骤 | 结果 |
| --- | --- |
| `soda-worker self-test` | 输出 `capabilities` 与 ComfyUI 的 `system_stats`，可达性为真 |
| 提交 `comfyui_generate` 任务到 `outbox/` | 任务被领取并移出 outbox |
| `soda-worker once` | 输出"完成任务 …，回传 3 个文件" |
| 结果 | `inbox/<task_id>.json`（`status: completed`，产物 kind = image / workflow / run_log） |
| 产物校验 | `inbox/<task_id>/001-*.png` 是真 PNG，**sha256 与结果信封一致** |
| 发往 ComfyUI 的请求 | `/prompt` 收到 `{"1": {"class_type": "Example", "inputs": {"seed": 7}}}` |

自动化回归见 `tests/linux/test_linux_worker.py`（真 Worker + 真桥接 + 假 ComfyUI，无需 GPU）。

## 已知限制

| 项目 | 说明 |
| --- | --- |
| 界面配对 | Core 的设备页仍按 macOS/Windows 语义工作（审计 G1/G2）；目前建议用命令行驱动，或直接调用桥接 API |
| SMB 相关动作 | `remote_routes.py` 的挂载诊断仅在 macOS 实现；Linux 用本地目录代替，不会走那条路径 |
| 训练 | `lora_train` 不在 Linux Worker 能力内 |
| ComfyUI 安装 | 需要你自备一个可访问的 ComfyUI；本仓库不打包 ComfyUI，也不下载模型 |
