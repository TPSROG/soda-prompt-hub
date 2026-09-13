from __future__ import annotations

from pathlib import Path


def _repository() -> Path:
    return Path(__file__).resolve().parents[1]


def test_mac_commercial_builder_is_locked_self_contained_and_unsigned() -> None:
    source = (_repository() / "scripts" / "build_mac_commercial_release.py").read_text()

    assert '"--frozen"' in source
    assert '"--no-default-groups"' in source
    assert '"build",' in source
    assert '"--wheel"' in source
    assert '"--no-build"' in source
    assert '"PYTHONNOUSERSITE": "1"' in source
    assert '"PYTHONDONTWRITEBYTECODE": "1"' in source
    assert '"signed": False' in source
    assert '"notarized": False' in source
    assert '"Applications").symlink_to("/Applications"' in source
    assert '"PACKAGE_MANIFEST.sha256"' in source
    assert "hdiutil" in source
    assert "actual_version != expected_version" in source
    assert '"install_name_tool"' in source
    assert "direct_url.unlink()" in source
    assert "_assert_no_build_paths(app_path, source)" in source


def test_mac_guide_explains_install_upgrade_uninstall_and_unsigned_boundary() -> None:
    guide = (_repository() / "docs" / "MAC_GUIDE.md").read_text()

    assert "build_mac_commercial_release.py" in guide
    assert "不需要预装 Python" in guide
    assert "覆盖旧 `.app` 即可升级" in guide
    assert "删除 `.app`" in guide
    assert "尚未 Developer ID 签名" in guide
