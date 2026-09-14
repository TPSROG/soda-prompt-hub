"""deploy/linux 部署层的静态契约检查, 跨平台可运行。

这些用例只读取文件, 不执行脚本, 因此在 Windows / macOS 上同样有效:
Linux 适配最容易犯的错 (CRLF, 硬编码路径, 默认监听 0.0.0.0, sudo, 777 权限)
都可以在这里拦住。
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_LINUX = REPO_ROOT / "deploy" / "linux"
UNIT_TEMPLATE = DEPLOY_LINUX / "soda-prompt-hub.service"

# 主任务书 §5 要求的最小脚本集合, 外加便利命令
SHELL_SCRIPTS = (
    "lib.sh",
    "install.sh",
    "uninstall.sh",
    "update.sh",
    "start.sh",
    "stop.sh",
    "status.sh",
    "soda-prompt-hub.sh",
)

# lib.sh 是被 source 的函数库, 本身不设置 shell 选项
STANDALONE_SCRIPTS = tuple(name for name in SHELL_SCRIPTS if name != "lib.sh")

UNIT_PLACEHOLDERS = (
    "__SPH_REPO__",
    "__SPH_LIBRARY_ROOT__",
    "__SPH_MODELS_ROOT__",
    "__SPH_HOST__",
    "__SPH_PORT__",
)


def _text(name: str) -> str:
    return (DEPLOY_LINUX / name).read_text(encoding="utf-8")


def test_deploy_linux_layout_exists() -> None:
    missing = [
        name for name in (*SHELL_SCRIPTS, UNIT_TEMPLATE.name) if not (DEPLOY_LINUX / name).is_file()
    ]
    assert not missing, f"deploy/linux 缺少文件: {missing}"


def test_scripts_declare_strict_mode_and_ignore_cwd() -> None:
    for name in STANDALONE_SCRIPTS:
        text = _text(name)
        assert text.startswith("#!/usr/bin/env bash"), f"{name} 缺少 bash shebang"
        assert "set -Eeuo pipefail" in text, f"{name} 未开启严格模式"
        assert "BASH_SOURCE" in text, f"{name} 未按脚本自身位置解析路径, 会依赖当前工作目录"


def test_scripts_never_escalate_and_never_widen_permissions() -> None:
    for name in SHELL_SCRIPTS:
        text = _text(name)
        assert not re.search(r"(?m)^\s*sudo\b", text), f"{name} 直接调用了 sudo"
        for pattern in ("chmod 777", "chmod -R 777", "chmod 0777", "chmod -R 0777"):
            assert pattern not in text, f"{name} 出现 {pattern}"


def test_scripts_never_pipe_remote_content_into_a_shell() -> None:
    # 主任务书 §25: 安装脚本不得执行来源不明的远程脚本
    for name in SHELL_SCRIPTS:
        text = _text(name)
        assert "| sh" not in text, f"{name} 把远程内容管道给 sh"
        assert "| bash" not in text, f"{name} 把远程内容管道给 bash"


def test_defaults_never_expose_the_service() -> None:
    lib = _text("lib.sh")
    assert 'SPH_DEFAULT_HOST="127.0.0.1"' in lib
    assert 'SPH_DEFAULT_PORT="8765"' in lib
    assert 'HOST="${SPH_DEFAULT_HOST}"' in _text("install.sh")
    for name in (*SHELL_SCRIPTS, UNIT_TEMPLATE.name):
        assert "0.0.0.0" not in _text(name), f"{name} 出现全接口监听地址"  # noqa: S104


def test_linux_layer_does_not_remove_other_platforms() -> None:
    # 守住不破坏 macOS / Windows 的底线: 其他平台目录必须仍在
    for directory in (
        "mac",
        "windows-desktop",
        "windows-installer",
        "windows-shell",
        "windows-worker",
    ):
        assert (REPO_ROOT / "deploy" / directory).is_dir(), f"deploy/{directory} 不应被删除"
    assert (REPO_ROOT / "src" / "prompt_hub" / "windows_worker.py").is_file()


def test_systemd_unit_is_a_user_service_with_restart_policy() -> None:
    unit = _text(UNIT_TEMPLATE.name)
    for directive in (
        "Restart=on-failure",
        "RestartSec=5",
        "WantedBy=default.target",
        "NoNewPrivileges=yes",
        "KillSignal=SIGINT",
        "WorkingDirectory=__SPH_REPO__",
        "Environment=PROMPT_HUB_LIBRARY_ROOT=__SPH_LIBRARY_ROOT__",
        "Environment=PROMPT_HUB_MODELS_ROOT=__SPH_MODELS_ROOT__",
    ):
        assert directive in unit, f"unit 缺少 {directive}"
    assert "User=root" not in unit
    expected_exec = (
        "ExecStart=__SPH_REPO__/.venv/bin/prompt-hub serve --host __SPH_HOST__ --port __SPH_PORT__"
    )
    assert expected_exec in unit


def test_installer_renders_every_placeholder_in_the_template() -> None:
    unit = _text(UNIT_TEMPLATE.name)
    declared = set(re.findall(r"__SPH_[A-Z_]+__", unit))
    assert declared == set(UNIT_PLACEHOLDERS)

    install = _text("install.sh")
    for placeholder in sorted(declared):
        assert f"${{UNIT_CONTENT//{placeholder}/" in install, f"install.sh 没有替换 {placeholder}"


def test_data_directories_follow_xdg_and_env_vars() -> None:
    lib = _text("lib.sh")
    assert "XDG_DATA_HOME" in lib
    assert "XDG_CONFIG_HOME" in lib
    install = _text("install.sh")
    assert 'LIBRARY_ROOT="${DATA_HOME}/library"' in install
    # 部署层通过环境变量接管路径, 不改核心默认值 (实现计划 D3/D4)
    assert "PROMPT_HUB_LIBRARY_ROOT" in install
    assert "PROMPT_HUB_MODELS_ROOT" in install
    assert "PROMPT_HUB_LIBRARY_ROOT" in _text("start.sh")
    assert "PROMPT_HUB_MODELS_ROOT" in _text("start.sh")


def test_update_is_fast_forward_only_and_data_safe() -> None:
    update = _text("update.sh")
    assert "--ff-only" in update, "更新必须只允许快进"
    assert "git status --porcelain" in update, "更新前必须检查工作区"
    assert "rm -rf" not in update, "更新脚本不得删除任何东西"
    assert "sph_data_usage" in update, "更新必须给出用户数据未改动的证据"


def test_uninstall_keeps_user_data_by_default() -> None:
    uninstall = _text("uninstall.sh")
    assert "--purge-data" in uninstall
    confirm_at = uninstall.index("if ((PURGE == 0))")
    delete_at = uninstall.index("rm -rf -- ")
    assert confirm_at < delete_at, "默认分支必须排在删除逻辑之前"
    assert 'case "${target}" in' in uninstall, "删除目标必须经过路径白名单检查"


def test_scripts_are_lf_utf8_without_local_paths() -> None:
    for name in SHELL_SCRIPTS:
        raw = (DEPLOY_LINUX / name).read_bytes()
        assert b"\r\n" not in raw, f"{name} 含 CRLF, shebang 会在 Linux 上失效"
        text = raw.decode("utf-8")
        assert "/home/voldm" not in text, f"{name} 含开发者本机路径"
        assert "C:\\" not in text, f"{name} 含 Windows 盘符路径"


def test_gitattributes_pins_shell_scripts_to_lf() -> None:
    attributes = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "*.sh text eol=lf" in attributes
    assert "deploy/linux/* text eol=lf" in attributes


def test_shell_scripts_pass_bash_syntax_check() -> None:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash not available")
    for name in SHELL_SCRIPTS:
        result = subprocess.run(  # noqa: S603 - 固定命令与文件参数
            [bash, "-n", str(DEPLOY_LINUX / name)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"{name} 语法错误: {result.stderr}"


def test_environment_checker_covers_required_signals() -> None:
    checker = (REPO_ROOT / "scripts" / "linux" / "check-env.sh").read_text(encoding="utf-8")
    for signal in ("Linux", "systemctl --user", "uv", "python3", "PROMPT_HUB_LIBRARY_ROOT"):
        assert signal in checker


def _workflow(name: str) -> str:
    return (REPO_ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")


def test_linux_workflow_runs_existing_checks_and_deployment_smoke() -> None:
    """主任务书 §13: 执行项目既有的检查命令, 并跑 Linux 专用测试与部署冒烟。"""
    workflow = _workflow("linux.yml")
    for command in (
        "uv sync --locked",
        "uv run ruff format --check .",
        "uv run ruff check .",
        "uv run ty check src/",
        "uv run pytest",
    ):
        assert command in workflow, f"linux.yml 缺少 {command}"
    assert "ubuntu-22.04" in workflow
    assert "ubuntu-24.04" in workflow
    assert "./deploy/linux/install.sh --no-service" in workflow
    assert "./deploy/linux/start.sh" in workflow
    assert "./deploy/linux/stop.sh" in workflow
    assert "systemctl --user status soda-prompt-hub" in workflow
    # 主任务书 §13: 不要擅自引入新的 lint 工具
    for forbidden in ("flake8", "pylint", "mypy", "eslint"):
        assert forbidden not in workflow, f"linux.yml 引入了新工具 {forbidden}"


def test_upstream_sync_never_merges_into_the_maintenance_branch() -> None:
    """主任务书 §15 / §16: 每日检查、成功开 PR、冲突开 Issue, 绝不直接合并到维护分支。"""
    workflow = _workflow("upstream-sync.yml")
    assert 'cron: "0 2 * * *"' in workflow, "应为每日一次检查"
    assert "git merge --no-edit upstream/main" in workflow, "应在同步分支上尝试合并"
    assert "gh pr create" in workflow, "合并成功应开 PR"
    assert "gh issue create" in workflow, "冲突应开 Issue"
    assert "--force-with-lease origin" in workflow, "只应推送同步分支"
    assert "upstream-baseline.txt" in workflow, "应记录已同步的上游基线"
    # 不允许把上游直接推/合并到维护分支
    assert "push origin main" not in workflow
    assert "push origin ${SYNC_BASE_BRANCH}" not in workflow
    assert "merge --no-edit origin" not in workflow


def test_release_workflow_publishes_prerelease_with_checksums() -> None:
    """主任务书 §17: 仅在 CI 通过且版本变化时, 产出 tar.gz + SHA256SUMS。"""
    workflow = _workflow("release-linux.yml")
    assert "workflow_run" in workflow
    assert "conclusion == 'success'" in workflow
    assert "sha256sum" in workflow
    assert "SHA256SUMS" in workflow
    assert "--prerelease" in workflow
    assert "tar -C" in workflow
