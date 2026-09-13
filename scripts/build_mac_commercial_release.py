from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from scripts.build_mac_portable_launcher import APP_NAME, build_app, read_version
except ModuleNotFoundError:
    from build_mac_portable_launcher import APP_NAME, build_app, read_version

PRODUCT_DIR_NAME = "product"
PYTHON_DIR_NAME = "runtime/python"
RELEASE_FORMAT = "soda-commercial-mac-release-v1"
MAX_BUILD_PATH_HITS = 10


class CommercialBuildError(RuntimeError):
    """Raised when a commercial macOS artifact cannot be built safely."""


def build_parser() -> argparse.ArgumentParser:
    repository = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Build the unsigned self-contained macOS release")
    parser.add_argument("--source-root", type=Path, default=repository)
    parser.add_argument("--output-dir", type=Path, default=repository / "dist" / "commercial-mac")
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--uv", type=Path, default=None)
    return parser


def build_release(
    source_root: Path,
    output_dir: Path,
    *,
    python_executable: Path,
    uv_executable: Path | None = None,
) -> dict[str, object]:
    if sys.platform != "darwin":
        msg = "Commercial macOS release must be built on macOS"
        raise CommercialBuildError(msg)

    source = source_root.expanduser().resolve()
    output = output_dir.expanduser().resolve()
    version = read_version(source)
    architecture = platform.machine()
    if architecture not in {"arm64", "x86_64"}:
        msg = f"Unsupported macOS architecture: {architecture}"
        raise CommercialBuildError(msg)

    uv = _resolve_uv(uv_executable)
    python = python_executable.expanduser().resolve()
    python_info = _python_info(python)
    if python_info["version"][:2] != [3, 12]:
        msg = f"Python 3.12 is required, got {'.'.join(map(str, python_info['version']))}"
        raise CommercialBuildError(msg)
    if python_info["machine"] != architecture:
        msg = f"Python architecture {python_info['machine']} does not match {architecture}"
        raise CommercialBuildError(msg)

    output.mkdir(parents=True, exist_ok=True)
    app_path = output / APP_NAME
    dmg_path = output / f"Soda-Prompt-Hub-{version}-macOS-{architecture}.dmg"
    release_path = output / "COMMERCIAL_RELEASE.json"
    if dmg_path.exists():
        dmg_path.unlink()

    build_app(source, app_path, runtime_root_hint=None, codesign=False)
    resources = app_path / "Contents" / "Resources"
    product_root = resources / PRODUCT_DIR_NAME
    runtime_root = resources / PYTHON_DIR_NAME
    _copy_product(source, product_root)
    _copy_python(Path(str(python_info["base_prefix"])), runtime_root)
    _install_locked_dependencies(source, runtime_root, uv)
    _sanitize_runtime(runtime_root, Path(str(python_info["base_prefix"])))
    _verify_runtime(runtime_root, product_root, version)
    _assert_no_build_paths(app_path, source)

    internal_release = {
        "format": RELEASE_FORMAT,
        "product": "Soda Prompt Hub",
        "version": version,
        "architecture": architecture,
        "python_version": ".".join(map(str, python_info["version"])),
        "signed": False,
        "signing_mode": "adhoc",
        "notarized": False,
        "dependency_source": "uv.lock",
        "user_data": "~/Documents/Soda Prompt Hub",
    }
    (resources / "COMMERCIAL_RELEASE.json").write_text(
        f"{json.dumps(internal_release, ensure_ascii=False, indent=2)}\n",
        encoding="utf-8",
    )
    _sign_runtime(app_path)
    _write_manifest(app_path)
    _seal_app(app_path)
    _create_dmg(app_path, dmg_path, version)

    public_release = {
        **internal_release,
        "file": dmg_path.name,
        "bytes": dmg_path.stat().st_size,
        "sha256": _sha256(dmg_path),
    }
    release_path.write_text(
        f"{json.dumps(public_release, ensure_ascii=False, indent=2)}\n",
        encoding="utf-8",
    )
    return {
        **public_release,
        "app": str(app_path),
        "dmg": str(dmg_path),
        "manifest": str(release_path),
    }


def _resolve_uv(explicit: Path | None) -> Path:
    candidate = explicit.expanduser().resolve() if explicit else None
    if candidate is None:
        located = shutil.which("uv")
        candidate = Path(located).resolve() if located else None
    if candidate is None or not candidate.is_file():
        msg = "uv is required to export and install dependencies from uv.lock"
        raise CommercialBuildError(msg)
    return candidate


def _python_info(python: Path) -> dict[str, object]:
    if not python.is_file():
        msg = f"Python executable does not exist: {python}"
        raise CommercialBuildError(msg)
    script = (
        "import json,platform,sys;"
        "print(json.dumps({'base_prefix':sys.base_prefix,'version':list(sys.version_info[:3]),"
        "'machine':platform.machine()}))"
    )
    result = subprocess.run(  # noqa: S603
        [str(python), "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def _copy_product(source: Path, destination: Path) -> None:
    required_files = ("pyproject.toml", "uv.lock", "README.md", "RELEASE.json", "LICENSE")
    for relative in required_files:
        path = source / relative
        if not path.is_file():
            msg = f"Missing commercial runtime file: {path}"
            raise CommercialBuildError(msg)
    shutil.copytree(
        source / "src",
        destination / "src",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    for relative in required_files:
        shutil.copy2(source / relative, destination / relative)


def _copy_python(base_prefix: Path, destination: Path) -> None:
    if not (base_prefix / "bin" / "python3.12").is_file():
        msg = f"Python base runtime is incomplete: {base_prefix}"
        raise CommercialBuildError(msg)
    shutil.copytree(
        base_prefix,
        destination,
        symlinks=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )


def _install_locked_dependencies(source: Path, runtime_root: Path, uv: Path) -> None:
    python = runtime_root / "bin" / "python3.12"
    site_packages = runtime_root / "lib" / "python3.12" / "site-packages"
    with tempfile.TemporaryDirectory(prefix="soda-mac-requirements-") as temporary:
        temporary_root = Path(temporary)
        requirements = temporary_root / "requirements.txt"
        wheels = temporary_root / "wheels"
        subprocess.run(  # noqa: S603
            [
                str(uv),
                "export",
                "--frozen",
                "--no-default-groups",
                "--no-emit-project",
                "--format",
                "requirements-txt",
                "--no-hashes",
                "--output-file",
                str(requirements),
                "--project",
                str(source),
            ],
            check=True,
        )
        subprocess.run(  # noqa: S603
            [
                str(uv),
                "build",
                "--wheel",
                "--out-dir",
                str(wheels),
                "--no-create-gitignore",
                str(source),
            ],
            check=True,
        )
        project_wheels = list(wheels.glob("prompt_hub-*.whl"))
        if len(project_wheels) != 1:
            msg = "Expected exactly one Prompt Hub wheel from the commercial build"
            raise CommercialBuildError(msg)
        subprocess.run(  # noqa: S603
            [
                str(uv),
                "pip",
                "install",
                "--python",
                str(python),
                "--target",
                str(site_packages),
                "--requirements",
                str(requirements),
                str(project_wheels[0]),
                "--no-build",
                "--link-mode",
                "copy",
            ],
            check=True,
        )


def _sanitize_runtime(runtime_root: Path, original_prefix: Path) -> None:
    install_name_tool = shutil.which("install_name_tool")
    if not install_name_tool:
        msg = "install_name_tool is required to sanitize the bundled Python runtime"
        raise CommercialBuildError(msg)
    dylib = runtime_root / "lib" / "libpython3.12.dylib"
    if dylib.is_file():
        subprocess.run(  # noqa: S603
            [install_name_tool, "-id", "@rpath/libpython3.12.dylib", str(dylib)],
            check=True,
        )

    standard_library = runtime_root / "lib" / "python3.12"
    installed_prefix = "/Applications/Soda Prompt Hub.app/Contents/Resources/runtime/python"
    for sysconfig in standard_library.glob("_sysconfigdata_*.py"):
        content = sysconfig.read_text(encoding="utf-8")
        sysconfig.write_text(
            content.replace(str(original_prefix), installed_prefix),
            encoding="utf-8",
        )
        for cached in (standard_library / "__pycache__").glob(f"{sysconfig.stem}.*.pyc"):
            cached.unlink()

    for direct_url in standard_library.glob("site-packages/*.dist-info/direct_url.json"):
        direct_url.unlink()
    # The launcher runs python -m; pip's console wrappers embed the staging path.
    console_scripts = standard_library / "site-packages" / "bin"
    if console_scripts.is_dir():
        shutil.rmtree(console_scripts)
    # Build tools may import the bundled stdlib and leave build paths in bytecode.
    for cached in standard_library.rglob("*.pyc"):
        cached.unlink()
    for cache_dir in sorted(standard_library.rglob("__pycache__"), reverse=True):
        if not any(cache_dir.iterdir()):
            cache_dir.rmdir()


def _verify_runtime(runtime_root: Path, product_root: Path, expected_version: str) -> None:
    python = runtime_root / "bin" / "python3.12"
    environment = {
        **os.environ,
        "PYTHONPATH": str(product_root / "src"),
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "ORT_DISABLE_TELEMETRY": "1",
    }
    result = subprocess.run(  # noqa: S603
        [
            str(python),
            "-c",
            (
                "import fastapi,mcp,numpy,onnxruntime,PIL,uvicorn,prompt_hub;"
                "print(prompt_hub.__version__)"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    actual_version = result.stdout.strip()
    if actual_version != expected_version:
        msg = f"Bundled Prompt Hub version is {actual_version}, expected {expected_version}"
        raise CommercialBuildError(msg)


def _assert_no_build_paths(app_path: Path, source: Path) -> None:
    forbidden = (
        str(Path.home()).encode(),
        str(source).encode(),
        b"soda-mac-requirements-",
    )
    hits: list[str] = []
    for path in sorted(item for item in app_path.rglob("*") if item.is_file()):
        data = path.read_bytes()
        if any(value and value in data for value in forbidden):
            hits.append(path.relative_to(app_path).as_posix())
            if len(hits) >= MAX_BUILD_PATH_HITS:
                break
    if hits:
        msg = f"Commercial app contains build-machine paths: {', '.join(hits)}"
        raise CommercialBuildError(msg)


def _sign_runtime(app_path: Path) -> None:
    """Sign modified bundled Mach-O files before recording their hashes."""
    magic = {b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca"}
    for path in sorted(app_path.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        if path.parent == app_path / "Contents" / "MacOS":
            continue
        with path.open("rb") as stream:
            is_macho = stream.read(4) in magic
        if is_macho:
            subprocess.run(  # noqa: S603
                ["/usr/bin/codesign", "--force", "--sign", "-", str(path)], check=True
            )


def _seal_app(app_path: Path) -> None:
    subprocess.run(  # noqa: S603
        ["/usr/bin/codesign", "--force", "--sign", "-", str(app_path)], check=True
    )
    subprocess.run(  # noqa: S603
        ["/usr/bin/codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app_path)],
        check=True,
    )


def _write_manifest(app_path: Path) -> None:
    manifest_path = app_path / "Contents" / "Resources" / "PACKAGE_MANIFEST.sha256"
    lines = [
        f"{_sha256(path)}  {path.relative_to(app_path).as_posix()}"
        for path in sorted(item for item in app_path.rglob("*") if item.is_file())
        if path != manifest_path
        and "_CodeSignature" not in path.parts
        and path.parent != app_path / "Contents" / "MacOS"
    ]
    manifest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _create_dmg(app_path: Path, dmg_path: Path, version: str) -> None:
    hdiutil = shutil.which("hdiutil")
    if not hdiutil:
        msg = "hdiutil is required to build the macOS DMG"
        raise CommercialBuildError(msg)
    with tempfile.TemporaryDirectory(prefix="soda-dmg-") as temporary:
        root = Path(temporary)
        shutil.copytree(app_path, root / APP_NAME, symlinks=True)
        (root / "Applications").symlink_to("/Applications", target_is_directory=True)
        subprocess.run(  # noqa: S603
            [
                hdiutil,
                "create",
                "-volname",
                f"Soda Prompt Hub {version}",
                "-srcfolder",
                str(root),
                "-format",
                "UDZO",
                "-imagekey",
                "zlib-level=9",
                str(dmg_path),
            ],
            check=True,
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    args = build_parser().parse_args()
    result = build_release(
        args.source_root,
        args.output_dir,
        python_executable=args.python,
        uv_executable=args.uv,
    )
    sys.stdout.write(f"{json.dumps(result, ensure_ascii=False, indent=2)}\n")


if __name__ == "__main__":
    main()
