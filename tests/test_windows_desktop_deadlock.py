from pathlib import Path


def test_workspace_open_never_blocks_the_ui_thread() -> None:
    root = Path(__file__).resolve().parents[1]
    host = (root / "deploy/windows-desktop/SodaPromptHub/DesktopHost.cs").read_text()
    shell = (root / "deploy/windows-desktop/SodaPromptHub/ShellForm.cs").read_text()
    assert "internal async Task OpenWorkspaceAsync()" in host
    assert ".GetAwaiter().GetResult()" not in host
    assert "var health = await ReadHealthAsync();" in host
    assert "await host.OpenWorkspaceAsync();" in shell
    assert shell.count("await RunNativeActionAsync(host.OpenWorkspaceAsync)") == 2
    assert "host.OpenWorkspace)" not in shell
    assert "host.OpenWorkspace();" not in shell
