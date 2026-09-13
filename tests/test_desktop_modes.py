from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from prompt_hub.api import create_app
from prompt_hub.desktop_connection import reconnect_url


@pytest.mark.parametrize("host", ["x@y", "x/path", "-option", "x:445", "", "x\n"])
def test_reconnect_rejects_unsafe_hosts(host) -> None:
    if host == "x\n":
        host = "x\ny"
    assert reconnect_url({"host": host, "smb_share": "share"}) == ""


def test_reconnect_uses_saved_share_without_credentials() -> None:
    assert reconnect_url({"host": "192.168.1.10", "smb_mount": "/Volumes/My Share"}) == (
        "smb://192.168.1.10/My%20Share"
    )
    assert reconnect_url({"host": "pc", "smb_share": "../secret"}) == ""
    assert reconnect_url({"host": "pc", "smb_mount": "/Users/example/local"}) == ""


def test_reconnect_route_checks_origin_and_platform(settings) -> None:
    with TestClient(create_app(settings), base_url="http://127.0.0.1") as client:
        client.put(
            "/api/remote-nodes/compute-5060ti",
            json={
                "role": "compute_5060ti",
                "host": "pc",
                "smb_share": "share",
                "enabled": True,
            },
        )
        with patch("prompt_hub.remote_routes.sys.platform", "darwin"):
            assert client.post("/api/remote-nodes/compute-5060ti/connect").status_code == 403
            with patch("prompt_hub.remote_routes.subprocess.run") as launch:
                response = client.post(
                    "/api/remote-nodes/compute-5060ti/connect",
                    headers={"Origin": "http://127.0.0.1"},
                )
                assert response.status_code == 200
                assert launch.call_args.args[0] == ["/usr/bin/open", "smb://pc/share"]
        with patch("prompt_hub.remote_routes.sys.platform", "win32"):
            assert client.post("/api/remote-nodes/compute-5060ti/connect").status_code == 409


def test_windows_modes_have_separate_profiles_and_automatic_start() -> None:
    root = Path(__file__).resolve().parents[1]
    host = (root / "deploy/windows-desktop/SodaPromptHub/DesktopHost.cs").read_text()
    shell = (root / "deploy/windows-desktop/SodaPromptHub/ShellForm.cs").read_text()
    worker = (root / "deploy/windows-shell/SodaComputeWorker/WorkerHost.cs").read_text()
    assert "new(localDesktop: true)" in host
    assert "var configPath = worker.ConfigPath" in host
    assert '"desktop-local-worker"' in host
    assert "await host.StartLocalWorkspaceAsync();" in shell
    assert 'localDesktop ? "Desktop Worker" : "Compute Worker"' in worker


def test_local_settings_keep_comfyui_visible() -> None:
    root = Path(__file__).resolve().parents[1]
    markup = (root / "deploy/desktop-ui/index.html").read_text()
    assert "settings-section bridge-config" not in markup
    assert 'label for="bridgeRoot" class="bridge-config"' in markup
    assert '<input id="comfyUiUrl"' in markup
