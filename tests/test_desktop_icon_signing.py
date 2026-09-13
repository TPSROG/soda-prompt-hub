from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image
from scripts.build_mac_commercial_release import _seal_app, _write_manifest
from scripts.build_mac_portable_launcher import build_app

ROOT = Path(__file__).resolve().parents[1]


def test_desktop_icon_containers() -> None:
    assets = ROOT / "deploy" / "desktop-ui"
    with Image.open(assets / "app-icon.png") as png:
        assert png.size == (1024, 1024)
        assert png.mode == "RGBA"
        assert png.getpixel((0, 0))[3] == 0
    with Image.open(assets / "app-icon.ico") as ico:
        assert {(16, 16), (32, 32), (48, 48), (256, 256)} <= ico.ico.sizes()
    with Image.open(assets / "app-icon.icns") as icns:
        assert icns.size == (1024, 1024)


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS codesign required")
def test_app_seal_fixes_linker_signature_and_detects_resource_tampering(tmp_path) -> None:
    app = build_app(ROOT, tmp_path / "Soda Prompt Hub.app", runtime_root_hint=None, codesign=False)
    command = ["/usr/bin/codesign", "--verify", "--deep", "--strict", str(app)]
    assert subprocess.run(command, capture_output=True, check=False).returncode != 0  # noqa: S603
    _write_manifest(app)
    _seal_app(app)
    assert subprocess.run(command, capture_output=True, check=False).returncode == 0  # noqa: S603
    (app / "Contents" / "Resources" / "desktop-ui" / "desktop.css").write_text("tampered")
    assert subprocess.run(command, capture_output=True, check=False).returncode != 0  # noqa: S603
