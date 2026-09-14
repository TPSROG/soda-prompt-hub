from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from scripts.build_commercial_release_bundle import (
    CommercialBundleError,
    assemble_release,
)

from prompt_hub import __version__


def _repository() -> Path:
    return Path(__file__).resolve().parents[1]


def _write_manifest(root: Path, name: str, payload: dict[str, object]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(json.dumps(payload), encoding="utf-8")


def _artifact(root: Path, name: str, content: bytes) -> dict[str, object]:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return {
        "file": name,
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def test_assemble_release_verifies_and_indexes_all_products(tmp_path: Path) -> None:
    windows = tmp_path / "windows"
    mac = tmp_path / "mac"
    desktop = _artifact(windows, f"Soda-Prompt-Hub-Desktop-{__version__}-Setup.exe", b"desktop")
    worker = _artifact(windows, f"Soda-Compute-Worker-{__version__}-Setup.exe", b"worker")
    dmg = _artifact(mac, f"Soda-Prompt-Hub-{__version__}-macOS-arm64.dmg", b"mac")
    _write_manifest(
        windows,
        "COMMERCIAL_RELEASE.json",
        {"version": __version__, "signed": False, "installers": [desktop, worker]},
    )
    _write_manifest(
        mac,
        "COMMERCIAL_RELEASE.json",
        {
            "version": __version__,
            "architecture": "arm64",
            "signed": False,
            "notarized": False,
            **dmg,
        },
    )

    output = tmp_path / "release"
    index = assemble_release(_repository(), windows, mac, output)

    assert index["version"] == __version__
    assert len(index["artifacts"]) == 3
    assert (output / "Windows" / desktop["file"]).read_bytes() == b"desktop"
    assert (output / "Windows" / worker["file"]).read_bytes() == b"worker"
    assert (output / "macOS" / dmg["file"]).read_bytes() == b"mac"
    assert (output / "安装与发布说明.md").is_file()
    checksums = (output / "SHA256SUMS.txt").read_text(encoding="utf-8")
    assert "RELEASE_INDEX.json" in checksums
    assert "SBOM.spdx.json" in checksums
    sbom = json.loads((output / "SBOM.spdx.json").read_text(encoding="utf-8"))
    assert sbom["spdxVersion"] == "SPDX-2.3"
    assert any(package["name"] == "fastapi" for package in sbom["packages"])
    assert all(package["name"] != "pytest" for package in sbom["packages"])


def test_assemble_release_rejects_tampered_or_existing_output(tmp_path: Path) -> None:
    windows = tmp_path / "windows"
    mac = tmp_path / "mac"
    desktop = _artifact(windows, f"Soda-Prompt-Hub-Desktop-{__version__}-Setup.exe", b"desktop")
    worker = _artifact(windows, f"Soda-Compute-Worker-{__version__}-Setup.exe", b"worker")
    dmg = _artifact(mac, f"Soda-Prompt-Hub-{__version__}-macOS-arm64.dmg", b"mac")
    desktop["sha256"] = "0" * 64
    _write_manifest(
        windows,
        "COMMERCIAL_RELEASE.json",
        {"version": __version__, "signed": False, "installers": [desktop, worker]},
    )
    _write_manifest(
        mac,
        "COMMERCIAL_RELEASE.json",
        {"version": __version__, "architecture": "arm64", **dmg},
    )

    with pytest.raises(CommercialBundleError, match="SHA-256 mismatch"):
        assemble_release(_repository(), windows, mac, tmp_path / "release")

    (tmp_path / "existing").mkdir()
    with pytest.raises(CommercialBundleError, match="Refusing to replace"):
        assemble_release(_repository(), windows, mac, tmp_path / "existing")
