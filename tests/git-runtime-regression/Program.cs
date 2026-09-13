using System.Diagnostics;
using SodaPromptHub.Desktop;

var temporary = Path.Combine(Path.GetTempPath(), "soda-git-regression-" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(temporary);
try
{
    Check(GitRuntime.Resolve(temporary) is null, "source builds can use developer Git");
    File.WriteAllText(Path.Combine(temporary, "INSTALL_MODE.json"), "{}");
    ExpectMissing(() => GitRuntime.Resolve(temporary));
    var gitRoot = Path.Combine(temporary, "runtime", "git");
    foreach (var file in new[] { "cmd/git.exe", "mingw64/bin/git.exe", "mingw64/etc/ssl/certs/ca-bundle.crt", "LICENSE.txt" })
    {
        var path = Path.Combine(gitRoot, file);
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllText(path, "fixture");
    }
    ExpectMissing(() => GitRuntime.Resolve(temporary));
    File.WriteAllText(Path.Combine(gitRoot, "mingw64/bin/git-remote-https.exe"), "fixture");
    var expected = Path.Combine(gitRoot, "cmd", "git.exe");
    Check(GitRuntime.Resolve(temporary) == expected, "resolve bundled Git");
    var originalPath = Environment.GetEnvironmentVariable("PATH");
    var info = new ProcessStartInfo();
    info.Environment["PATH"] = "existing-path";
    info.Environment["GIT_EXEC_PATH"] = "unrelated-git";
    GitRuntime.Configure(info, temporary);
    Check(info.Environment["PATH"] == Path.GetDirectoryName(expected) + Path.PathSeparator + "existing-path", "prepend only child PATH");
    Check(!info.Environment.ContainsKey("GIT_EXEC_PATH"), "do not reuse foreign Git helpers");
    Check(info.Environment["GIT_TERMINAL_PROMPT"] == "0", "no invisible terminal prompts");
    Check(Environment.GetEnvironmentVariable("PATH") == originalPath, "parent PATH unchanged");
    info.Environment.Remove("PATH");
    GitRuntime.Configure(info, temporary);
    Check(info.Environment["PATH"] == Path.GetDirectoryName(expected), "empty PATH supported without current-directory entry");
    Console.WriteLine("PASS: private Git resolution, incomplete-package refusal, no global PATH changes, noninteractive child environment.");
    return 0;
}
finally { Directory.Delete(temporary, recursive: true); }

static void Check(bool success, string message) { if (!success) throw new Exception(message); }
static void ExpectMissing(Func<string?> action)
{
    try { action(); }
    catch (InvalidOperationException error) when (error.Message.Contains("Git")) { return; }
    throw new Exception("Incomplete installed Git was accepted");
}
