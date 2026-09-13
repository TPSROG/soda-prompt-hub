from __future__ import annotations

from io import BytesIO
from pathlib import Path
from threading import Event
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from prompt_hub.api import create_app
from prompt_hub.background_jobs import BackgroundJobRunner, BackgroundJobStore, JobCancelledError
from prompt_hub.comfy_results import ComfyResultError, ComfyResultStore
from prompt_hub.creative_web_layout import CREATIVE_HTML
from prompt_hub.remote_web import REMOTE_SCRIPT


def test_local_mode_only_hides_device_pairing_forms() -> None:
    assert "page.querySelectorAll('.remote-form,.remote-actions')" not in REMOTE_SCRIPT
    assert "#remoteNodeGrid .remote-form" in REMOTE_SCRIPT


def test_device_connection_name_stays_the_same_in_local_mode() -> None:
    assert "[data-view=\"remote\"]').textContent='本机计算'" not in REMOTE_SCRIPT
    assert "page.querySelector('h1').textContent='设备连接'" in REMOTE_SCRIPT
    assert "Windows 单机模式" in REMOTE_SCRIPT


def test_creative_assist_uses_ai_completion_name() -> None:
    assert '<p class="section-label">AI补全</p>' in CREATIVE_HTML
    assert "让模型帮忙" not in CREATIVE_HTML


def test_desktop_inputs_use_theme_aware_foreground() -> None:
    css = (Path(__file__).parents[1] / "deploy/desktop-ui/desktop.css").read_text()
    rule = css.split(".settings-fields textarea {", 1)[1].split("}", 1)[0]
    assert "color: var(--field-text)" in rule
    assert "::placeholder" in css
    assert "--field-text: #171815" in css
    assert "--field-text: #f4eddf" in css


def test_duplicate_image_skips_decoding(settings) -> None:
    raw = BytesIO()
    Image.new("RGB", (16, 16), "red").save(raw, "PNG")
    store = ComfyResultStore(settings.comfy_results_root)
    store.initialize()
    store.import_bytes(raw.getvalue(), filename="first.png")
    with patch("prompt_hub.comfy_results.inspect_comfy_image") as inspect:
        result = store.import_bytes(raw.getvalue(), filename="duplicate.png")
    assert result["duplicate"]
    inspect.assert_not_called()


def test_scan_job_is_async_exclusive_and_cancelable(settings, tmp_path) -> None:
    source = tmp_path / "output"
    source.mkdir()
    entered, release = Event(), Event()

    def scan(_self, _path, *, context=None):
        context.update(0, 2, "扫描测试")
        entered.set()
        assert release.wait(5)
        context.raise_if_cancelled()
        return {}

    with (
        patch.object(ComfyResultStore, "import_directory", scan),
        TestClient(create_app(settings)) as client,
    ):
        try:
            response = client.post(
                "/api/comfy-results/scan-jobs", json={"source_path": str(source)}
            )
            assert response.status_code == 202
            job = response.json()
            assert entered.wait(3)
            duplicate = client.post(
                "/api/comfy-results/scan-jobs", json={"source_path": str(source)}
            ).json()
            assert duplicate["job_id"] == job["job_id"]
            latest = client.get("/api/comfy-results/scan-jobs/latest").json()
            assert latest["job_id"] == job["job_id"]
            assert latest["progress_total"] == 2
            cancelled = client.post(f"/api/jobs/{job['job_id']}/cancel").json()
            assert cancelled["cancel_requested"]
        finally:
            release.set()


class ScanContext:
    def __init__(self, cancel_after=None):
        self.updates = []
        self.cancel_after = cancel_after

    def update(self, current, total, message):
        self.updates.append((current, total, message))
        if self.cancel_after is not None and current >= self.cancel_after and total:
            raise JobCancelledError

    def raise_if_cancelled(self):
        pass


def test_scan_progress_batch_commit_and_read_only_source(settings, tmp_path) -> None:
    source = tmp_path / "output"
    source.mkdir()
    for index in range(12):
        Image.new("RGB", (16, 16), (index, 30, 40)).save(source / f"{index:02}.png")
    (source / "bad.png").write_bytes(b"not an image")
    before = {p.name: p.read_bytes() for p in source.iterdir()}
    store = ComfyResultStore(settings.comfy_results_root)
    store.initialize()
    context = ScanContext()
    with patch.object(store, "_write_index", wraps=store._write_index) as write_index:  # noqa: SLF001
        report = store.import_directory(source, context=context)
    assert (report["imported"], len(report["failed"]), report["scanned"]) == (12, 1, 13)
    assert write_index.call_count == 2
    assert context.updates[0][:2] == (0, 0)
    assert context.updates[-1][:2] == (13, 13)
    assert any(0 < current < total for current, total, _ in context.updates)
    assert before == {p.name: p.read_bytes() for p in source.iterdir()}


def test_cancel_flushes_partial_batch_and_retry_deduplicates(settings, tmp_path) -> None:
    source = tmp_path / "output"
    source.mkdir()
    for index in range(3):
        Image.new("RGB", (16, 16), (index, 30, 40)).save(source / f"{index}.png")
    store = ComfyResultStore(settings.comfy_results_root)
    store.initialize()
    with pytest.raises(JobCancelledError):
        store.import_directory(source, context=ScanContext(cancel_after=1))
    assert len(store.list_results()) == 1
    report = store.import_directory(source)
    assert (report["imported"], report["duplicates"]) == (2, 1)


def test_scan_stops_discovery_at_limit(settings, tmp_path) -> None:
    source = tmp_path / "output"
    source.mkdir()
    for index in range(4):
        (source / f"{index}.png").touch()
    store = ComfyResultStore(settings.comfy_results_root)
    store.initialize()
    with (
        patch("prompt_hub.comfy_results.MAX_DIRECTORY_IMAGES", 2),
        pytest.raises(
            ComfyResultError,
            match="超过 2 张",
        ),
    ):
        store.import_directory(source)
    assert store.list_results() == []


def test_scan_failure_and_restart_use_existing_job_queue(settings, tmp_path) -> None:
    store = ComfyResultStore(settings.comfy_results_root)
    store.initialize()
    jobs = BackgroundJobStore(settings.database_path)
    jobs.initialize()
    runner = BackgroundJobRunner(jobs, {"comfy_scan": store.scan_job})
    first = runner.submit("comfy_scan", {"source_path": str(tmp_path / "missing")}, exclusive=True)
    claimed = jobs.claim_next({"comfy_scan"})
    assert jobs.recover_interrupted() == 1
    restored = runner.submit("comfy_scan", {"source_path": "another"}, exclusive=True)
    assert restored["job_id"] == first["job_id"]
    assert claimed["job_id"] == first["job_id"]
    runner._execute(jobs.claim_next({"comfy_scan"}))  # noqa: SLF001
    result = jobs.get(first["job_id"])
    assert result["status"] == "failed"
    assert "不存在" in result["error"]
