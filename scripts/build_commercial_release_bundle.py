from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tomllib
import uuid
from pathlib import Path

RELEASE_FORMAT = "soda-commercial-release-bundle-v1"
SPDX_VERSION = "SPDX-2.3"


class CommercialBundleError(ValueError):
    """Raised when commercial artifacts cannot be assembled safely."""


class ReleaseMetadataError(CommercialBundleError):
    def __init__(self) -> None:
        super().__init__("Project release metadata is not the expected stable version")


class ExistingReleaseError(CommercialBundleError):
    def __init__(self, path: Path) -> None:
        super().__init__(f"Refusing to replace existing release directory: {path}")


class ArtifactVersionError(CommercialBundleError):
    def __init__(self) -> None:
        super().__init__("Commercial artifact version does not match project version")


class ProductSetError(CommercialBundleError):
    def __init__(self) -> None:
        super().__init__("Expected exactly the three desktop commercial products")


class MissingArtifactError(CommercialBundleError):
    def __init__(self, path: Path) -> None:
        super().__init__(f"Missing commercial artifact: {path}")


class ArtifactSizeError(CommercialBundleError):
    def __init__(self, path: Path) -> None:
        super().__init__(f"Commercial artifact size mismatch: {path.name}")


class ArtifactChecksumError(CommercialBundleError):
    def __init__(self, path: Path) -> None:
        super().__init__(f"Commercial artifact SHA-256 mismatch: {path.name}")


class InvalidDependencyError(CommercialBundleError):
    def __init__(self, value: str) -> None:
        super().__init__(f"Invalid project dependency: {value}")


def assemble_release(
    repository_root: Path,
    windows_root: Path,
    mac_root: Path,
    output_root: Path,
) -> dict[str, object]:
    repository = repository_root.resolve()
    windows = windows_root.resolve()
    mac = mac_root.resolve()
    output = output_root.resolve()
    version = _project_version(repository / "pyproject.toml")
    release = _read_json(repository / "RELEASE.json")
    if release.get("product_version") != version or release.get("release_channel") != "stable":
        raise ReleaseMetadataError
    if output.exists():
        raise ExistingReleaseError(output)

    windows_manifest_path = windows / "COMMERCIAL_RELEASE.json"
    mac_manifest_path = mac / "COMMERCIAL_RELEASE.json"
    windows_manifest = _read_json(windows_manifest_path)
    mac_manifest = _read_json(mac_manifest_path)
    if windows_manifest.get("version") != version or mac_manifest.get("version") != version:
        raise ArtifactVersionError

    artifacts: list[dict[str, object]] = []
    for item in windows_manifest.get("installers", []):
        source = windows / str(item["file"])
        _verify_artifact(source, item)
        product = "Windows Desktop" if "Desktop" in source.name else "Windows Compute Worker"
        artifacts.append(
            {
                "product": product,
                "platform": "windows-x64",
                "path": f"Windows/{source.name}",
                "bytes": source.stat().st_size,
                "sha256": _sha256(source),
                "signed": bool(windows_manifest.get("signed", False)),
            }
        )
    mac_source = mac / str(mac_manifest["file"])
    _verify_artifact(mac_source, mac_manifest)
    artifacts.append(
        {
            "product": "Mac Desktop",
            "platform": f"macos-{mac_manifest.get('architecture', 'unknown')}",
            "path": f"macOS/{mac_source.name}",
            "bytes": mac_source.stat().st_size,
            "sha256": _sha256(mac_source),
            "signed": bool(mac_manifest.get("signed", False)),
            "notarized": bool(mac_manifest.get("notarized", False)),
        }
    )
    if {str(item["product"]) for item in artifacts} != {
        "Windows Desktop",
        "Windows Compute Worker",
        "Mac Desktop",
    }:
        raise ProductSetError

    temporary = output.with_name(f".{output.name}.tmp-{uuid.uuid4().hex}")
    try:
        (temporary / "Windows").mkdir(parents=True)
        (temporary / "macOS").mkdir(parents=True)
        for item in artifacts:
            source_root = windows if str(item["platform"]).startswith("windows") else mac
            shutil.copy2(source_root / Path(str(item["path"])).name, temporary / str(item["path"]))
        shutil.copy2(windows_manifest_path, temporary / "Windows" / windows_manifest_path.name)
        shutil.copy2(mac_manifest_path, temporary / "macOS" / mac_manifest_path.name)
        shutil.copy2(repository / "docs" / "COMMERCIAL_RELEASE.md", temporary / "安装与发布说明.md")

        index = {
            "format": RELEASE_FORMAT,
            "product": "Soda Prompt Hub",
            "version": version,
            "release_channel": "stable",
            "signing_status": "deferred",
            "artifacts": sorted(artifacts, key=lambda item: str(item["path"])),
            "user_data_preserved_on_upgrade_and_uninstall": True,
        }
        _write_json(temporary / "RELEASE_INDEX.json", index)
        _write_json(temporary / "SBOM.spdx.json", _build_spdx(repository, version))
        _write_checksums(temporary)
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary.rename(output)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return index


def _verify_artifact(path: Path, expected: dict[str, object]) -> None:
    if not path.is_file():
        raise MissingArtifactError(path)
    if path.stat().st_size != int(expected["bytes"]):
        raise ArtifactSizeError(path)
    if _sha256(path) != str(expected["sha256"]).casefold():
        raise ArtifactChecksumError(path)


def _build_spdx(repository: Path, version: str) -> dict[str, object]:
    locked = tomllib.loads((repository / "uv.lock").read_text(encoding="utf-8"))["package"]
    by_name: dict[str, list[dict[str, object]]] = {}
    for package in locked:
        by_name.setdefault(_normalize(str(package["name"])), []).append(package)
    project = tomllib.loads((repository / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    pending = [_requirement_name(value) for value in project.get("dependencies", [])]
    selected: dict[tuple[str, str], dict[str, object]] = {}
    while pending:
        name = _normalize(pending.pop())
        for package in by_name.get(name, []):
            key = (name, str(package["version"]))
            if key in selected:
                continue
            selected[key] = package
            pending.extend(str(item["name"]) for item in package.get("dependencies", []))

    application_id = "SPDXRef-Package-Soda-Prompt-Hub"
    packages: list[dict[str, object]] = [
        {
            "SPDXID": application_id,
            "name": "soda-prompt-hub",
            "versionInfo": version,
            "downloadLocation": "https://github.com/cOkieeman/soda-prompt-hub",
            "filesAnalyzed": False,
            "licenseConcluded": "MIT",
            "licenseDeclared": "MIT",
            "copyrightText": "Copyright (c) 2026 cOkieeman",
        }
    ]
    relationships: list[dict[str, str]] = [
        {
            "spdxElementId": "SPDXRef-DOCUMENT",
            "relationshipType": "DESCRIBES",
            "relatedSpdxElement": application_id,
        }
    ]
    for (name, package_version), package in sorted(selected.items()):
        spdx_id = f"SPDXRef-Python-{_spdx_token(name)}-{_spdx_token(package_version)}"
        packages.append(
            {
                "SPDXID": spdx_id,
                "name": name,
                "versionInfo": package_version,
                "downloadLocation": str(package.get("source", {}).get("registry", "NOASSERTION")),
                "filesAnalyzed": False,
                "licenseConcluded": "NOASSERTION",
                "licenseDeclared": "NOASSERTION",
                "copyrightText": "NOASSERTION",
                "externalRefs": [
                    {
                        "referenceCategory": "PACKAGE-MANAGER",
                        "referenceType": "purl",
                        "referenceLocator": f"pkg:pypi/{name}@{package_version}",
                    }
                ],
            }
        )
        relationships.append(
            {
                "spdxElementId": application_id,
                "relationshipType": "DEPENDS_ON",
                "relatedSpdxElement": spdx_id,
            }
        )
    return {
        "spdxVersion": SPDX_VERSION,
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"Soda-Prompt-Hub-{version}-commercial",
        "documentNamespace": (
            "https://github.com/cOkieeman/soda-prompt-hub/"
            f"releases/download/v{version}/SBOM.spdx.json"
        ),
        "creationInfo": {
            "creators": ["Tool: scripts/build_commercial_release_bundle.py"],
            "licenseListVersion": "3.26",
        },
        "packages": packages,
        "relationships": relationships,
    }


def _write_checksums(root: Path) -> None:
    output = root / "SHA256SUMS.txt"
    lines = [
        f"{_sha256(path)}  {path.relative_to(root).as_posix()}"
        for path in sorted(item for item in root.rglob("*") if item.is_file())
        if path != output
    ]
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _project_version(path: Path) -> str:
    with path.open("rb") as stream:
        return str(tomllib.load(stream)["project"]["version"])


def _requirement_name(value: str) -> str:
    match = re.match(r"[A-Za-z0-9_.-]+", value)
    if not match:
        raise InvalidDependencyError(value)
    return match.group(0)


def _normalize(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).casefold()


def _spdx_token(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9.-]", "-", value)


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Assemble the three commercial desktop products")
    parser.add_argument("--repository-root", type=Path, default=Path(__file__).parents[1])
    parser.add_argument("--windows-dir", type=Path, required=True)
    parser.add_argument("--mac-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = assemble_release(
        args.repository_root,
        args.windows_dir,
        args.mac_dir,
        args.output_dir,
    )
    sys.stdout.write(f"{json.dumps(result, ensure_ascii=False, indent=2)}\n")


if __name__ == "__main__":
    main()
