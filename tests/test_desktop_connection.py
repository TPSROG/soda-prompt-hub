from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from threading import Event

import pytest

from prompt_hub.desktop_connection import connection_summary
from prompt_hub.remote_nodes import RemoteNodeStore
from prompt_hub.windows_worker import WindowsWorker, WorkerConfig
from prompt_hub.windows_worker_core import ComfyUIClient


@pytest.fixture
def connection_store(tmp_path):
    store = RemoteNodeStore(tmp_path / "nodes")
    store.initialize()
    mount = tmp_path / "share"
    mount.mkdir()
    store.save_node(
        "compute-5060ti",
        {
            "role": "compute_5060ti",
            "enabled": True,
            "host": "windows",
            "smb_mount": str(mount),
            "label": "测试计算机",
        },
    )
    store.prepare_bridge("compute-5060ti")
    return store, mount / "prompt-hub"


def heartbeat(**overrides):
    return {
        "format": "soda-worker-heartbeat-v1",
        "running": True,
        "checked_at": datetime.now(UTC).isoformat(),
        "role": "compute_5060ti",
        "worker_version": "1.1.0",
        "release_channel": "stable",
        "protocol_version": "soda-compute-bridge-v2",
        "comfyui_reachable": True,
        **overrides,
    }


@pytest.mark.parametrize(
    ("changes", "state"),
    [
        ({}, "connected"),
        ({"running": False}, "stopped"),
        ({"comfyui_reachable": False}, "compute_unavailable"),
        ({"protocol_version": "wrong"}, "incompatible"),
        ({"checked_at": "invalid"}, "stale"),
        ({"checked_at": (datetime.now(UTC) - timedelta(minutes=2)).isoformat()}, "stale"),
        ({"checked_at": (datetime.now(UTC) + timedelta(minutes=2)).isoformat()}, "stale"),
    ],
)
def test_connection_only_reports_fresh_live_worker(connection_store, changes, state):
    store, bridge = connection_store
    (bridge / "worker-heartbeat.json").write_text(json.dumps(heartbeat(**changes)))
    result = connection_summary(store)
    assert result["state"] == state
    assert result["can_compute"] is (state == "connected")


def test_old_self_test_is_not_live_connection(connection_store):
    store, bridge = connection_store
    (bridge / "worker-status.json").write_text(json.dumps({"status": "ready"}))
    assert connection_summary(store)["state"] == "unconfirmed"
    bridge.rename(bridge.with_name("disconnected"))
    assert connection_summary(store)["state"] == "mount_ready_bridge_unprepared"


def test_no_device_is_valid_local_only_state(tmp_path):
    store = RemoteNodeStore(tmp_path)
    assert connection_summary(store)["state"] == "not_configured"


def test_worker_emits_live_and_stopped_heartbeats(tmp_path, monkeypatch):
    monkeypatch.setattr(ComfyUIClient, "system_stats", lambda _: {})
    worker = WindowsWorker(
        WorkerConfig(
            bridge_root=tmp_path, comfyui_url="http://127.0.0.1:8188", worker_id="test-worker"
        )
    )
    worker.write_heartbeat()
    path = tmp_path / "worker-heartbeat.json"
    assert json.loads(path.read_text())["comfyui_reachable"] is True
    worker.write_heartbeat(running=False)
    assert json.loads(path.read_text())["running"] is False


def test_worker_heartbeat_runs_during_recovery_and_stops_on_exit(tmp_path, monkeypatch):
    worker = WindowsWorker(
        WorkerConfig(
            bridge_root=tmp_path, comfyui_url="http://127.0.0.1:8188", worker_id="test-worker"
        )
    )
    live = Event()
    writes = []

    def write(*, running=True):
        writes.append(running)
        live.set()

    def recover():
        assert live.wait(2)
        raise KeyboardInterrupt

    monkeypatch.setattr(worker, "write_heartbeat", write)
    monkeypatch.setattr(worker, "recover_processing", recover)
    with pytest.raises(KeyboardInterrupt):
        worker.run_forever()
    assert writes == [True, False]
