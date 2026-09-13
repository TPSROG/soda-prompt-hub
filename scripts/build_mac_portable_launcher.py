from __future__ import annotations

import argparse
import json
import platform
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

APP_NAME = "Soda Prompt Hub.app"
BUNDLE_IDENTIFIER = "com.soda.prompt-hub.launcher"
EXECUTABLE_NAME = "SodaPromptHubLauncher"
RUNNER_NAME = "run-server.zsh"
SWIFT_SOURCE_NAME = "SodaPromptHubLauncher.swift"
DESKTOP_UI_DIR_NAME = "desktop-ui"


def build_parser() -> argparse.ArgumentParser:
    repository = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Build the lightweight macOS launcher app")
    parser.add_argument("--source-root", type=Path, default=repository)
    parser.add_argument("--output", type=Path, default=repository / "dist" / APP_NAME)
    parser.add_argument(
        "--runtime-root-hint",
        type=Path,
        default=None,
        help="Preferred Prompt Hub program directory written into the app bundle",
    )
    parser.add_argument("--skip-codesign", action="store_true")
    parser.add_argument(
        "--shell-launcher",
        action="store_true",
        help="Build the legacy shell test launcher instead of the native macOS launcher",
    )
    return parser


def read_version(source_root: Path) -> str:
    release_path = source_root / "RELEASE.json"
    release = json.loads(release_path.read_text(encoding="utf-8"))
    version = str(release.get("product_version", "")).strip()
    if not version:
        msg = f"Missing product_version in {release_path}"
        raise ValueError(msg)
    return version


def validate_output(output: Path) -> None:
    if output.name != APP_NAME or output.suffix != ".app":
        msg = f"Output must end with {APP_NAME}: {output}"
        raise ValueError(msg)


def write_info_plist(path: Path, *, version: str) -> None:
    payload = {
        "CFBundleDevelopmentRegion": "zh_CN",
        "CFBundleDisplayName": "Soda Prompt Hub",
        "CFBundleExecutable": EXECUTABLE_NAME,
        "CFBundleIdentifier": BUNDLE_IDENTIFIER,
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleName": "Soda Prompt Hub",
        "CFBundleIconFile": "app-icon.icns",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": version,
        "CFBundleVersion": version,
        "LSMinimumSystemVersion": "12.0",
        "LSUIElement": True,
        "LSApplicationCategoryType": "public.app-category.graphics-design",
        "NSDocumentsFolderUsageDescription": (
            "Soda Prompt Hub 需要读取你选择保存在 Documents 中的本地提示词、图片和项目资料。"
        ),
        "NSHighResolutionCapable": True,
    }
    with path.open("wb") as stream:
        plistlib.dump(payload, stream, sort_keys=True)


def sign_app(app_path: Path) -> None:
    codesign = shutil.which("codesign")
    if sys.platform != "darwin" or not codesign:
        return
    subprocess.run(  # noqa: S603
        [codesign, "--force", "--deep", "--sign", "-", str(app_path)],
        check=True,
        capture_output=True,
        text=True,
    )


def compile_native_launcher(source: Path, executable: Path) -> None:
    xcrun = shutil.which("xcrun")
    if not xcrun:
        msg = "xcrun is required to build the native macOS launcher"
        raise FileNotFoundError(msg)
    architecture = platform.machine()
    if architecture not in {"arm64", "x86_64"}:
        msg = f"Unsupported macOS architecture: {architecture}"
        raise ValueError(msg)
    subprocess.run(  # noqa: S603
        [
            xcrun,
            "swiftc",
            "-O",
            "-parse-as-library",
            "-target",
            f"{architecture}-apple-macosx12.0",
            "-framework",
            "AppKit",
            "-framework",
            "Foundation",
            "-framework",
            "WebKit",
            "-o",
            str(executable),
            str(source),
        ],
        check=True,
    )


def build_app(
    source_root: Path,
    output: Path,
    *,
    runtime_root_hint: Path | None,
    codesign: bool,
    native: bool = True,
) -> Path:
    source_root = source_root.expanduser().resolve()
    output = output.expanduser().resolve()
    validate_output(output)

    launcher_source = (
        source_root / "deploy" / "mac" / "portable-launcher" / "SodaPromptHubLauncher.zsh"
    )
    runner_source = source_root / "deploy" / "mac" / "portable-launcher" / RUNNER_NAME
    swift_source = source_root / "deploy" / "mac" / "portable-launcher" / SWIFT_SOURCE_NAME
    desktop_ui_source = source_root / "deploy" / DESKTOP_UI_DIR_NAME
    launcher_files = (swift_source,) if native else (launcher_source, runner_source)
    desktop_ui_files = tuple(
        desktop_ui_source / name for name in ("index.html", "desktop.css", "desktop.js")
    )
    for required in (source_root / "RELEASE.json", *launcher_files, *desktop_ui_files):
        if not required.is_file():
            msg = f"Missing required launcher source: {required}"
            raise FileNotFoundError(msg)

    version = read_version(source_root)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(tempfile.mkdtemp(prefix=".soda-launcher-", dir=output.parent))
    temporary_app = temporary_root / APP_NAME
    contents = temporary_app / "Contents"
    macos = contents / "MacOS"
    resources = contents / "Resources"
    macos.mkdir(parents=True)
    resources.mkdir()
    shutil.copytree(desktop_ui_source, resources / DESKTOP_UI_DIR_NAME)
    shutil.copy2(desktop_ui_source / "app-icon.icns", resources / "app-icon.icns")

    executable = macos / EXECUTABLE_NAME
    if native:
        compile_native_launcher(swift_source, executable)
    else:
        shutil.copy2(launcher_source, executable)
    executable.chmod(0o755)
    if not native:
        runner = resources / RUNNER_NAME
        shutil.copy2(runner_source, runner)
        runner.chmod(0o755)
    write_info_plist(contents / "Info.plist", version=version)
    (contents / "PkgInfo").write_text("APPL????", encoding="ascii")
    if runtime_root_hint is not None:
        hint = runtime_root_hint.expanduser().resolve()
        (resources / "repository-path").write_text(f"{hint}\n", encoding="utf-8")

    try:
        if codesign:
            sign_app(temporary_app)
        if output.exists():
            shutil.rmtree(output)
        temporary_app.replace(output)
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)
    return output


def main() -> None:
    args = build_parser().parse_args()
    output = build_app(
        args.source_root,
        args.output,
        runtime_root_hint=args.runtime_root_hint,
        codesign=not args.skip_codesign,
        native=not args.shell_launcher,
    )
    sys.stdout.write(f"{output}\n")


if __name__ == "__main__":
    main()
