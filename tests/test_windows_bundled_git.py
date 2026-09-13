from pathlib import Path
from unittest.mock import Mock

from scripts.package_windows_desktop_release import REQUIRED_PATHS

from prompt_hub import source_sync

ROOT = Path(__file__).resolve().parents[1]


def test_desktop_release_requires_git_transport_certificates_and_license() -> None:
    assert {
        "runtime/git/cmd/git.exe",
        "runtime/git/mingw64/bin/git-remote-https.exe",
        "runtime/git/mingw64/etc/ssl/certs/ca-bundle.crt",
        "runtime/git/LICENSE.txt",
        "GIT_RUNTIME.json",
    } <= set(REQUIRED_PATHS)


def test_git_archive_is_pinned_and_prepared_for_both_desktop_packages() -> None:
    prepare = ROOT / "deploy/windows-installer/prepare-git.ps1"
    assert prepare.is_file()
    script = prepare.read_text(encoding="utf-8-sig")
    assert "56d7b226b7693196cfc71fef26568f536c4a021ab6c37ff2db4287bed908e96e" in script
    assert "https://github.com/git-for-windows/git/releases/download/" in script
    assert "Get-FileHash" in script
    assert "--version" in script
    assert "git-remote-https.exe" in script
    assert "LICENSE.txt" in script
    for relative in (
        "deploy/windows-desktop/build.ps1",
        "deploy/windows-installer/prepare-runtime.ps1",
    ):
        assert "prepare-git.ps1" in (ROOT / relative).read_text(encoding="utf-8-sig")


def test_launcher_configures_private_git_and_probes_before_python() -> None:
    host = (ROOT / "deploy/windows-desktop/SodaPromptHub/DesktopHost.cs").read_text()
    assert "GitRuntime.Configure(info, AppRoot);" in host
    assert host.index("await EnsureGitRuntimeAsync();") < host.index(
        "await EnsurePythonRuntimeAsync();"
    )
    helper = (ROOT / "deploy/windows-desktop/SodaPromptHub/GitRuntime.cs").read_text()
    assert "SetEnvironmentVariable" not in helper
    assert 'info.Environment["PATH"]' in helper
    assert '"GIT_TERMINAL_PROMPT"' in helper


def test_git_subprocess_never_creates_windows_console(monkeypatch, tmp_path) -> None:
    runner = Mock(return_value=Mock(returncode=0, stdout="ok\n", stderr=""))
    monkeypatch.setattr(source_sync.shutil, "which", lambda _: "private/git.exe")
    monkeypatch.setattr(source_sync.subprocess, "run", runner)
    monkeypatch.setattr(source_sync.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    assert source_sync._git(tmp_path, "status") == "ok"  # noqa: SLF001 - regression at subprocess boundary
    assert runner.call_args.kwargs["creationflags"] == 0x08000000
