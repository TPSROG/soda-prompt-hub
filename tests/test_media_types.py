"""服务端下发的媒体类型不能依赖系统 MIME 数据库。

Python 内置的 MIME 表不含 webp, `mimetypes` 只有在系统 /etc/mime.types 提供映射
时才知道它。Ubuntu 22.04 等环境没有该映射, Starlette 的 FileResponse 会把缩略图
当成 application/octet-stream 下发, 浏览器就不再内联显示图片。
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

import pytest

from prompt_hub.media import media_type_for


@pytest.fixture
def without_system_mime_database(monkeypatch: pytest.MonkeyPatch) -> None:
    """模拟没有 /etc/mime.types 映射的环境 (例如 Ubuntu 22.04 上的 webp)。"""
    monkeypatch.setattr(mimetypes, "guess_type", lambda *_args, **_kwargs: (None, None))


@pytest.mark.usefixtures("without_system_mime_database")
@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("thumb.webp", "image/webp"),
        ("thumb.WEBP", "image/webp"),
        ("frame.png", "image/png"),
        ("photo.jpg", "image/jpeg"),
        ("photo.JPEG", "image/jpeg"),
        ("anim.gif", "image/gif"),
        ("next.avif", "image/avif"),
    ],
)
def test_project_image_formats_have_fixed_media_types(
    filename: str,
    expected: str,
) -> None:
    assert media_type_for(Path(filename)) == expected


def test_unknown_extension_still_falls_back_to_mimetypes() -> None:
    guessed = media_type_for(Path("archive.zip"))
    assert guessed in {"application/zip", "application/octet-stream"}


@pytest.mark.usefixtures("without_system_mime_database")
def test_unmapped_extension_without_database_falls_back_to_octet_stream() -> None:
    assert media_type_for(Path("blob.bin")) == "application/octet-stream"
