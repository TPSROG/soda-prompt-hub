from __future__ import annotations

import hashlib
import re
from http import HTTPStatus
from typing import TYPE_CHECKING
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

from prompt_hub.visual_model import (
    VisualModelError,
    WhitelistedRedirectHandler,
    assert_https_download_url,
)

if TYPE_CHECKING:
    from http.client import HTTPResponse
    from pathlib import Path

    from prompt_hub.background_jobs import JobContext


def verified_digest(path: Path, context: JobContext) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            context.raise_if_cancelled()
            digest.update(chunk)
    return digest.hexdigest()


def download_file(
    target: Path,
    url: str,
    size: int,
    sha256: str,
    context: JobContext,
    *,
    completed: int = 0,
    total: int = 0,
) -> None:
    """Resume only pinned files; never overwrite an existing user model."""
    assert_https_download_url(url)
    part = target.with_name(target.name + ".part")
    if target.is_symlink() or part.is_symlink():
        raise VisualModelError("模型路径不能是符号链接")
    total = total or size
    context.update(completed, total, f"准备 {target.name}，正在检查已有文件……")
    if target.exists():
        if target.stat().st_size == size and verified_digest(target, context) == sha256:
            context.update(completed + size, total, f"{target.name} 校验通过")
            return
        raise VisualModelError(
            "已有模型文件与推荐版本不同，未覆盖。请先备份并移走冲突文件，再重试。"
        )
    offset = part.stat().st_size if part.exists() else 0
    if offset > size:
        part.unlink()
        offset = 0
    if offset < size:
        offset = _transfer(
            part, url, size, context, offset=offset, completed=completed, total=total
        )
    if offset != size:
        raise VisualModelError("模型下载不完整，已保留断点，请重试")
    context.update(completed + size, total, f"正在校验 {target.name} 的 SHA-256……")
    if verified_digest(part, context) != sha256:
        part.unlink()
        raise VisualModelError("SHA-256 校验失败，已清除本次损坏的下载，请重试")
    context.raise_if_cancelled()
    part.replace(target)


def _response_offset(response: HTTPResponse, offset: int, size: int) -> int:
    if response.status == HTTPStatus.OK:
        return 0
    if response.status == HTTPStatus.PARTIAL_CONTENT:
        match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("Content-Range", ""))
        if not match or tuple(map(int, match.groups())) != (offset, size - 1, size):
            raise VisualModelError("下载服务返回了不匹配的续传范围，已保留断点，请重试")
        return offset
    raise VisualModelError(f"模型下载失败：HTTP {response.status}")


def _transfer(
    part: Path,
    url: str,
    size: int,
    context: JobContext,
    *,
    offset: int,
    completed: int,
    total: int,
) -> int:
    request = Request(
        url,
        headers={"Range": f"bytes={offset}-", "User-Agent": "SodaPromptHub/model-installer"},
    )
    try:
        with build_opener(WhitelistedRedirectHandler()).open(request, timeout=20) as response:
            offset = _response_offset(response, offset, size)
            with part.open("ab" if offset else "wb") as sink:
                while True:
                    context.raise_if_cancelled()
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    if offset + len(chunk) > size:
                        raise VisualModelError("下载内容超过预期大小，已停止")
                    sink.write(chunk)
                    offset += len(chunk)
                    context.update(completed + offset, total, f"正在下载 {part.stem}")
    except HTTPError as error:
        raise VisualModelError(f"模型下载失败：HTTP {error.code}，请检查网络后重试") from error
    except (URLError, OSError, TimeoutError) as error:
        raise VisualModelError(
            "模型下载中断，已保留断点。请检查网络、磁盘空间或目录权限后重试"
        ) from error
    return offset
