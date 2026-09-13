using System.Diagnostics;

namespace SodaPromptHub.Desktop;

internal static class GitRuntime
{
    internal static string? Resolve(string appRoot)
    {
        var root = Path.Combine(appRoot, "runtime", "git");
        if (!Directory.Exists(root))
        {
            // Source-development builds may use the developer's Git installation.
            if (!File.Exists(Path.Combine(appRoot, "INSTALL_MODE.json"))) return null;
            throw new InvalidOperationException("安装包缺少内置 Git，无法拉取资料库。请重新安装完整的 Windows Desktop 安装包。");
        }
        foreach (var relative in new[] {
            "cmd/git.exe", "mingw64/bin/git.exe", "mingw64/bin/git-remote-https.exe",
            "mingw64/etc/ssl/certs/ca-bundle.crt", "LICENSE.txt" })
        {
            if (!File.Exists(Path.Combine(root, relative)))
                throw new InvalidOperationException($"内置 Git 文件不完整（{relative}）。请重新安装完整的 Windows Desktop 安装包。");
        }
        return Path.Combine(root, "cmd", "git.exe");
    }

    internal static void Configure(ProcessStartInfo info, string appRoot)
    {
        var executable = Resolve(appRoot);
        if (executable is not null)
        {
            info.Environment.TryGetValue("PATH", out var inheritedPath);
            info.Environment["PATH"] = Path.GetDirectoryName(executable)
                + (string.IsNullOrEmpty(inheritedPath) ? "" : Path.PathSeparator + inheritedPath);
            // Do not accidentally execute another installation's Git helpers.
            info.Environment.Remove("GIT_EXEC_PATH");
        }
        // Public source downloads must fail clearly instead of waiting for a hidden prompt.
        info.Environment["GIT_TERMINAL_PROMPT"] = "0";
        info.Environment["GCM_INTERACTIVE"] = "Never";
    }
}
