from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from prompt_hub.desktop_connection import connection_summary
from prompt_hub.web import render_index_html
from prompt_hub.workspace_web import WORKSPACE_HTML, WORKSPACE_SCRIPT


@pytest.mark.parametrize("mode", ["windows_local", "mac_remote"])
def test_first_render_declares_usage_mode(mode: str) -> None:
    markup = render_index_html("QA device", usage_mode=mode)
    assert f'data-usage-mode="{mode}"' in markup
    assert "__PROMPT_HUB_USAGE_MODE__" not in markup


def test_windows_mode_has_appropriate_path_examples() -> None:
    markup = render_index_html("QA device", usage_mode="windows_local")
    assert 'placeholder="D:/Pictures/my-dataset"' in markup
    assert 'placeholder="D:/Models/vision_model.onnx"' in markup
    assert 'data-usage-only="mac_remote"' in markup
    assert "window.isPromptHubLocal" in markup


def test_dataset_local_work_is_not_mislabeled_as_mac() -> None:
    assert "Mac" not in WORKSPACE_HTML
    assert "Mac" not in WORKSPACE_SCRIPT
    assert "Finder" not in WORKSPACE_SCRIPT
    assert 'data-export-action="copy"' in WORKSPACE_SCRIPT
    assert "window.isPromptHubLocal" in WORKSPACE_SCRIPT


def test_mac_keeps_its_path_and_pairing_support() -> None:
    markup = render_index_html("QA device", usage_mode="mac_remote")
    assert 'placeholder="/Users/your-name/Pictures/my-dataset"' in markup
    assert "pairingDialog" in markup
    assert "密码由 Mac 钥匙串保存" in markup


def test_render_does_not_allow_mode_markup_injection() -> None:
    with pytest.raises(ValueError, match="usage mode"):
        render_index_html("QA", usage_mode='"><script>')


@pytest.mark.parametrize("state", ["not_configured", "mount_missing", "bridge_read_only"])
def test_local_connection_errors_do_not_request_smb_pairing(monkeypatch, state: str) -> None:
    monkeypatch.setattr("prompt_hub.desktop_connection.sys", SimpleNamespace(platform="win32"))
    store = Mock()
    store.list_nodes.return_value = [
        {"node_id": "local", "role": "compute_5060ti", "enabled": True}
    ]
    store.diagnostics.return_value = {"state": state, "mount_exists": False}
    result = connection_summary(store)
    assert result["mode"] == "windows_local"
    assert "启动器" in result["detail"]
    assert "Finder" not in result["detail"]
    assert "共享" not in result["detail"]
    assert result["reconnect_url"] == ""
