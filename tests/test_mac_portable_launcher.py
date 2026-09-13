from __future__ import annotations

import json
import os
import plistlib
import shlex
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest
from scripts.build_mac_portable_launcher import (
    BUNDLE_IDENTIFIER,
    DESKTOP_UI_DIR_NAME,
    EXECUTABLE_NAME,
    RUNNER_NAME,
    build_app,
)

MACOS_ONLY = pytest.mark.skipif(sys.platform != "darwin", reason="launcher requires macOS")


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/api/health":
            body = json.dumps({"status": "ok", "service": "soda-prompt-hub"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, _format: str, *_args: object) -> None:
        return


def _available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _launcher_environment(tmp_path: Path, *, port: int) -> dict[str, str]:
    return {
        **os.environ,
        "PROMPT_HUB_PORT": str(port),
        "PROMPT_HUB_LAUNCHER_SKIP_OPEN": "1",
        "PROMPT_HUB_LAUNCHER_TIMEOUT": "10",
        "PROMPT_HUB_LAUNCHER_STATE_ROOT": str(tmp_path / "state"),
        "PROMPT_HUB_LAUNCHER_LOG_ROOT": str(tmp_path / "logs"),
        "PROMPT_HUB_LAUNCHER_DIALOG_LOG": str(tmp_path / "dialog.log"),
        "PROMPT_HUB_UV_BIN": str(tmp_path / "missing-uv"),
        "PROMPT_HUB_LAUNCHER_NO_LAUNCHD": "1",
    }


def _create_fake_repository(tmp_path: Path, *, startup_delay: float = 0) -> tuple[Path, Path]:
    fake_repository = tmp_path / "fake-project"
    (fake_repository / "src" / "prompt_hub").mkdir(parents=True)
    (fake_repository / "pyproject.toml").write_text('[project]\nname = "prompt-hub"\n')
    start_marker = fake_repository / "start-count.log"
    fake_server = fake_repository / "fake_server.py"
    fake_server.write_text(
        f"""from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import sys
import time

port = int(sys.argv[sys.argv.index('--port') + 1])
time.sleep({startup_delay!r})

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/api/health':
            body = json.dumps({{'status': 'ok', 'service': 'soda-prompt-hub'}}).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        return

ThreadingHTTPServer(('127.0.0.1', port), Handler).serve_forever()
"""
    )
    fake_python = fake_repository / ".venv" / "bin" / "python"
    fake_python.parent.mkdir(parents=True)
    fake_python.write_text(
        f"#!/bin/sh\nprintf 'start\\n' >> {shlex.quote(str(start_marker))}\n"
        f'exec {shlex.quote(sys.executable)} {shlex.quote(str(fake_server))} "$@"\n'
    )
    fake_python.chmod(0o755)
    return fake_repository, start_marker


def _stop_background_service(pid_file: Path) -> None:
    pid = int(pid_file.read_text())
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    for _ in range(30):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)


def test_build_mac_portable_launcher_creates_valid_bundle(tmp_path) -> None:
    repository = Path(__file__).resolve().parents[1]
    output = tmp_path / "Soda Prompt Hub.app"

    built = build_app(
        repository,
        output,
        runtime_root_hint=repository,
        codesign=False,
        native=False,
    )

    executable = built / "Contents" / "MacOS" / EXECUTABLE_NAME
    with (built / "Contents" / "Info.plist").open("rb") as stream:
        info = plistlib.load(stream)
    assert executable.is_file()
    assert os.access(executable, os.X_OK)
    runner = built / "Contents" / "Resources" / RUNNER_NAME
    assert os.access(runner, os.X_OK)
    assert "ORT_DISABLE_TELEMETRY" in runner.read_text()
    assert info["CFBundleIdentifier"] == BUNDLE_IDENTIFIER
    assert info["CFBundlePackageType"] == "APPL"
    assert info["CFBundleIconFile"] == "app-icon.icns"
    assert (built / "Contents" / "Resources" / "app-icon.icns").is_file()
    assert info["LSUIElement"] is True
    desktop_ui = built / "Contents" / "Resources" / DESKTOP_UI_DIR_NAME
    assert (desktop_ui / "index.html").is_file()
    assert (desktop_ui / "desktop.css").is_file()
    assert "window.SodaDesktop" in (desktop_ui / "desktop.js").read_text()
    assert (built / "Contents" / "Resources" / "repository-path").read_text().strip() == str(
        repository
    )


@MACOS_ONLY
def test_build_native_mac_launcher(tmp_path) -> None:
    repository = Path(__file__).resolve().parents[1]
    built = build_app(
        repository,
        tmp_path / "Soda Prompt Hub.app",
        runtime_root_hint=repository,
        codesign=False,
    )
    executable = built / "Contents" / "MacOS" / EXECUTABLE_NAME
    with executable.open("rb") as stream:
        assert stream.read(4) == b"\xcf\xfa\xed\xfe"
    with (built / "Contents" / "Info.plist").open("rb") as stream:
        info = plistlib.load(stream)
    assert "Documents" in info["NSDocumentsFolderUsageDescription"]
    assert (built / "Contents" / "Resources" / DESKTOP_UI_DIR_NAME / "index.html").is_file()


def test_desktop_ui_uses_restricted_host_bridge() -> None:
    repository = Path(__file__).resolve().parents[1]
    desktop_ui = repository / "deploy" / DESKTOP_UI_DIR_NAME
    markup = (desktop_ui / "index.html").read_text()
    script = (desktop_ui / "desktop.js").read_text()
    contract = (desktop_ui / "BRIDGE_CONTRACT.md").read_text()

    assert 'data-phase="checking"' in markup
    assert "messageHandlers?.sodaHost" in script
    for method in (
        "getStatus",
        "openWorkspace",
        "restartCore",
        "retryCore",
        "openLogs",
        "openDataFolder",
        "hideWindow",
    ):
        assert method in contract
    assert "window.SodaDesktop.receiveStatus" in contract


def test_native_launcher_prefers_bundled_commercial_runtime() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "deploy"
        / "mac"
        / "portable-launcher"
        / "SodaPromptHubLauncher.swift"
    ).read_text()

    assert '"product"' in source
    assert '"runtime/python/bin/python3.12"' in source
    assert 'childEnvironment["PYTHONNOUSERSITE"] = "1"' in source
    assert 'childEnvironment["PYTHONDONTWRITEBYTECODE"] = "1"' in source
    assert 'childEnvironment["PYTHONPATH"]' in source


@MACOS_ONLY
def test_launcher_reuses_running_service(tmp_path) -> None:
    repository = Path(__file__).resolve().parents[1]
    output = build_app(
        repository,
        tmp_path / "Soda Prompt Hub.app",
        runtime_root_hint=repository,
        codesign=False,
        native=False,
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), _HealthHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run(  # noqa: S603
            [str(output / "Contents" / "MacOS" / EXECUTABLE_NAME)],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
            env=_launcher_environment(tmp_path, port=server.server_port),
        )
    finally:
        server.shutdown()
        server.server_close()

    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "state" / "prompt-hub.pid").exists()
    assert "服务已经运行" in (tmp_path / "logs" / "launcher.log").read_text()


@MACOS_ONLY
def test_launcher_starts_project_in_background(tmp_path) -> None:
    repository = Path(__file__).resolve().parents[1]
    fake_repository, start_marker = _create_fake_repository(tmp_path)
    output = build_app(
        repository,
        tmp_path / "Soda Prompt Hub.app",
        runtime_root_hint=fake_repository,
        codesign=False,
        native=False,
    )
    port = _available_port()
    environment = _launcher_environment(tmp_path, port=port)

    result = subprocess.run(  # noqa: S603
        [str(output / "Contents" / "MacOS" / EXECUTABLE_NAME)],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
        env=environment,
    )

    pid_file = tmp_path / "state" / "prompt-hub.pid"
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=3) as response:
            assert json.load(response)["service"] == "soda-prompt-hub"
    finally:
        _stop_background_service(pid_file)

    assert result.returncode == 0, result.stderr
    assert start_marker.read_text().splitlines() == ["start"]
    assert "服务已就绪" in (tmp_path / "logs" / "launcher.log").read_text()


@MACOS_ONLY
def test_concurrent_launches_start_only_one_service(tmp_path) -> None:
    repository = Path(__file__).resolve().parents[1]
    fake_repository, start_marker = _create_fake_repository(tmp_path, startup_delay=1)
    output = build_app(
        repository,
        tmp_path / "Soda Prompt Hub.app",
        runtime_root_hint=fake_repository,
        codesign=False,
        native=False,
    )
    executable = output / "Contents" / "MacOS" / EXECUTABLE_NAME
    environment = _launcher_environment(tmp_path, port=_available_port())

    first = subprocess.Popen(  # noqa: S603
        [str(executable)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
    )
    time.sleep(0.1)
    second = subprocess.Popen(  # noqa: S603
        [str(executable)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
    )
    first_output = first.communicate(timeout=20)
    second_output = second.communicate(timeout=20)
    try:
        assert first.returncode == 0, first_output
        assert second.returncode == 0, second_output
        assert start_marker.read_text().splitlines() == ["start"]
    finally:
        _stop_background_service(tmp_path / "state" / "prompt-hub.pid")


@MACOS_ONLY
def test_launcher_submits_service_to_launchd(tmp_path) -> None:
    repository = Path(__file__).resolve().parents[1]
    fake_repository, start_marker = _create_fake_repository(tmp_path)
    output = build_app(
        repository,
        tmp_path / "Soda Prompt Hub.app",
        runtime_root_hint=fake_repository,
        codesign=False,
        native=False,
    )
    launchctl_trace = tmp_path / "launchctl.log"
    fake_launchctl = tmp_path / "launchctl"
    fake_launchctl.write_text(
        f"""#!/bin/sh
printf '%s\\n' "$*" >> {shlex.quote(str(launchctl_trace))}
if [ "$1" = "bootout" ] || [ "$1" = "bootstrap" ]; then
  exit 0
fi
if [ "$1" = "kickstart" ]; then
  "$FAKE_RUNNER" "$FAKE_REPOSITORY" "" "$FAKE_PYTHON" \
    "127.0.0.1" "$PROMPT_HUB_PORT" \
    "$PROMPT_HUB_LAUNCHER_STATE_ROOT/prompt-hub.pid" \
    "$PROMPT_HUB_LAUNCHER_LOG_ROOT/server.log" &
fi
exit 0
"""
    )
    fake_launchctl.chmod(0o755)
    environment = _launcher_environment(tmp_path, port=_available_port())
    environment.pop("PROMPT_HUB_LAUNCHER_NO_LAUNCHD")
    environment["PROMPT_HUB_LAUNCHCTL_BIN"] = str(fake_launchctl)
    environment["FAKE_RUNNER"] = str(output / "Contents" / "Resources" / RUNNER_NAME)
    environment["FAKE_REPOSITORY"] = str(fake_repository)
    environment["FAKE_PYTHON"] = str(fake_repository / ".venv" / "bin" / "python")

    result = subprocess.run(  # noqa: S603
        [str(output / "Contents" / "MacOS" / EXECUTABLE_NAME)],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
        env=environment,
    )
    try:
        assert result.returncode == 0, result.stderr
        assert start_marker.read_text().splitlines() == ["start"]
        trace = launchctl_trace.read_text()
        assert "bootout gui/" in trace
        assert "bootstrap gui/" in trace
        assert "kickstart -k gui/" in trace
        with (tmp_path / "state" / "server-launch-agent.plist").open("rb") as stream:
            launch_agent = plistlib.load(stream)
        assert launch_agent["Label"] == "com.soda.prompt-hub.server"
        assert launch_agent["ProgramArguments"][0].endswith(RUNNER_NAME)
        assert launch_agent["ProcessType"] == "Interactive"
        assert launch_agent["KeepAlive"] is False
    finally:
        _stop_background_service(tmp_path / "state" / "prompt-hub.pid")
