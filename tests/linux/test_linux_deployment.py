"""deploy/linux 的行为测试, 仅 Linux 运行。

用一个隔离的 HOME 与 XDG 路径执行真实的安装 / 启停 / 状态流程,
不触碰开发机上已安装的服务与用户数据。
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_LINUX = REPO_ROOT / "deploy" / "linux"

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux 部署脚本的行为测试")


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _run(
    script: str, *args: str, env: dict[str, str], timeout: int = 180
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - 固定脚本路径与参数
        [str(DEPLOY_LINUX / script), *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
        check=False,
    )


def _wait_health(port: int, timeout: float = 30.0) -> dict[str, object] | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            response = httpx.get(f"http://127.0.0.1:{port}/api/health", timeout=2.0)
            if response.status_code == 200:
                return response.json()
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    return None


@pytest.fixture
def isolated(tmp_path: Path) -> dict[str, str]:
    """隔离的 HOME / XDG 环境, 保证不碰到开发机上真实的安装与服务。"""
    home = tmp_path / "home"
    (home / ".local" / "bin").mkdir(parents=True)
    data = tmp_path / "xdg-data"
    config = tmp_path / "xdg-config"
    runtime = tmp_path / "xdg-runtime"
    for directory in (data, config, runtime):
        directory.mkdir(parents=True, exist_ok=True)
    runtime.chmod(0o700)

    env = dict(os.environ)
    env["HOME"] = str(home)
    env["XDG_DATA_HOME"] = str(data)
    env["XDG_CONFIG_HOME"] = str(config)
    env["XDG_RUNTIME_DIR"] = str(runtime)
    # 保留真实缓存, 避免隔离 HOME 之后 uv 重新下载依赖
    env.setdefault("UV_CACHE_DIR", str(Path.home() / ".cache" / "uv"))
    return env


def test_help_flags_exit_cleanly(isolated: dict[str, str]) -> None:
    for script in ("install.sh", "update.sh", "uninstall.sh"):
        result = _run(script, "--help", env=isolated, timeout=60)
        assert result.returncode == 0, f"{script} --help 退出码 {result.returncode}"
        assert "用法" in result.stdout


def test_commands_report_missing_installation(isolated: dict[str, str]) -> None:
    for script in ("start.sh", "stop.sh", "status.sh"):
        result = _run(script, env=isolated, timeout=60)
        assert result.returncode != 0, f"{script} 在未安装时不应成功"
        assert "install.sh" in (result.stderr + result.stdout)


def test_install_start_stop_cycle_keeps_program_and_data_separate(
    tmp_path: Path, isolated: dict[str, str]
) -> None:
    library = tmp_path / "library with space"
    port = _free_port()

    install = _run(
        "install.sh",
        "--no-service",
        "--port",
        str(port),
        "--library-root",
        str(library),
        env=isolated,
    )
    assert install.returncode == 0, install.stdout + install.stderr

    env_file = Path(isolated["XDG_DATA_HOME"]) / "soda-prompt-hub" / "install.env"
    assert env_file.is_file()
    # install.env 用 printf %q 写入, 空格会被转义成 "\ "
    recorded = env_file.read_text(encoding="utf-8").replace("\\ ", " ")
    assert f"SPH_PORT={port}" in recorded
    assert str(library) in recorded
    assert "SPH_SERVICE=no" in recorded

    start = _run("start.sh", env=isolated)
    assert start.returncode == 0, start.stdout + start.stderr
    stop: subprocess.CompletedProcess[str] | None = None
    try:
        health = _wait_health(port)
        assert health is not None, "服务未在 30 秒内通过健康检查"
        assert health["status"] == "ok"
        assert str(library) in str(health["database"])

        status = _run("status.sh", env=isolated)
        assert status.returncode == 0
        assert f"127.0.0.1:{port}" in status.stdout
        assert "健康检查: ok" in status.stdout
    finally:
        stop = _run("stop.sh", env=isolated)

    assert stop is not None
    assert stop.returncode == 0, stop.stdout + stop.stderr
    assert _wait_health(port, timeout=3.0) is None, "停止后端口仍在响应"

    # 程序与用户数据分离: 数据由安装参数决定, 便利命令装进隔离的 HOME
    assert (library / "database" / "prompt-library.sqlite").is_file()
    assert (Path(isolated["HOME"]) / ".local" / "bin" / "soda-prompt-hub").is_file()
