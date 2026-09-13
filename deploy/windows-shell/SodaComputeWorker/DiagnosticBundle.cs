using System.IO.Compression;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace SodaPromptHub.ComputeWorker;

internal static partial class DiagnosticBundle
{
    private const int MaxLogBytes = 512 * 1024;
    private const int MaxLogFiles = 8;
    private static readonly string[] StatusKeys =
    [
        "phase",
        "coreState",
        "libraryState",
        "computeState",
        "comfyState",
        "version",
        "releaseChannel",
        "checkedAt",
        "errorTitle",
    ];

    internal static string Create(
        string productSlug,
        string productName,
        string version,
        bool installedMode,
        IReadOnlyDictionary<string, object?> status,
        string logsRoot,
        IEnumerable<string> metadataPaths)
    {
        var generatedAt = DateTimeOffset.UtcNow;
        var destinationRoot = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
            "Downloads");
        if (!Directory.Exists(destinationRoot))
        {
            destinationRoot = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
        }
        Directory.CreateDirectory(destinationRoot);

        var stem = $"{productSlug}-Diagnostics-{generatedAt:yyyyMMdd-HHmmss}";
        var archivePath = Path.Combine(destinationRoot, $"{stem}.zip");
        if (File.Exists(archivePath))
        {
            archivePath = Path.Combine(destinationRoot, $"{stem}-{Guid.NewGuid():N}.zip");
        }

        var stagingRoot = Path.Combine(Path.GetTempPath(), $"soda-diagnostics-{Guid.NewGuid():N}");
        Directory.CreateDirectory(stagingRoot);
        try
        {
            var safeStatus = StatusKeys
                .Where(status.ContainsKey)
                .ToDictionary(key => key, key => status[key], StringComparer.Ordinal);
            var summary = new Dictionary<string, object?>
            {
                ["format"] = "soda-diagnostics-v1",
                ["product"] = productName,
                ["version"] = version,
                ["generated_at_utc"] = generatedAt.ToString("O"),
                ["installed_mode"] = installedMode,
                ["os"] = RuntimeInformation.OSDescription,
                ["architecture"] = RuntimeInformation.OSArchitecture.ToString(),
                ["status"] = safeStatus,
            };
            File.WriteAllText(
                Path.Combine(stagingRoot, "diagnostics.json"),
                JsonSerializer.Serialize(summary, new JsonSerializerOptions { WriteIndented = true }) + Environment.NewLine,
                new UTF8Encoding(false));

            WritePrivacyNotice(stagingRoot);
            CopyReleaseMetadata(stagingRoot, metadataPaths);
            CopySanitizedLogs(stagingRoot, logsRoot);
            ZipFile.CreateFromDirectory(stagingRoot, archivePath, CompressionLevel.Optimal, includeBaseDirectory: false);
            return archivePath;
        }
        finally
        {
            try
            {
                Directory.Delete(stagingRoot, recursive: true);
            }
            catch (IOException)
            {
                // The archive is complete. Windows can clean a temporarily locked folder later.
            }
            catch (UnauthorizedAccessException)
            {
                // Do not fail an export because antivirus briefly holds a temporary file.
            }
        }
    }

    internal static void Reveal(string archivePath)
    {
        System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(
            "explorer.exe",
            $"/select,\"{archivePath}\"")
        {
            UseShellExecute = true,
        });
    }

    private static void WritePrivacyNotice(string root)
    {
        const string notice = """
            Soda diagnostics privacy note

            This archive contains release metadata, a small allowlisted status summary, and sanitized log tails.
            It does not include worker-config.json, backup configs, databases, prompt libraries, bridge tasks,
            model files, images, API keys, or the full user profile path.

            Log text can still contain filenames or task identifiers created by other applications. Review this
            archive before sharing it with support.
            """;
        File.WriteAllText(
            Path.Combine(root, "PRIVACY.txt"),
            notice + Environment.NewLine,
            new UTF8Encoding(false));
    }

    private static void CopyReleaseMetadata(string root, IEnumerable<string> metadataPaths)
    {
        var targetRoot = Path.Combine(root, "release");
        foreach (var source in metadataPaths.Where(File.Exists).Distinct(StringComparer.OrdinalIgnoreCase))
        {
            Directory.CreateDirectory(targetRoot);
            var name = Path.GetFileName(source);
            var safeName = File.Exists(Path.Combine(targetRoot, name))
                ? $"{Path.GetFileNameWithoutExtension(name)}-{Guid.NewGuid():N}{Path.GetExtension(name)}"
                : name;
            File.WriteAllText(
                Path.Combine(targetRoot, safeName),
                Redact(File.ReadAllText(source)),
                new UTF8Encoding(false));
        }
    }

    private static void CopySanitizedLogs(string root, string logsRoot)
    {
        if (!Directory.Exists(logsRoot))
        {
            return;
        }
        var targetRoot = Path.Combine(root, "logs");
        foreach (var source in Directory.EnumerateFiles(logsRoot, "*.log", SearchOption.TopDirectoryOnly)
                     .Select(path => new FileInfo(path))
                     .OrderByDescending(file => file.LastWriteTimeUtc)
                     .Take(MaxLogFiles))
        {
            Directory.CreateDirectory(targetRoot);
            File.WriteAllText(
                Path.Combine(targetRoot, source.Name),
                Redact(ReadTail(source.FullName)),
                new UTF8Encoding(false));
        }
    }

    private static string ReadTail(string path)
    {
        using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
        var offset = Math.Max(0, stream.Length - MaxLogBytes);
        stream.Seek(offset, SeekOrigin.Begin);
        using var reader = new StreamReader(stream, Encoding.UTF8, detectEncodingFromByteOrderMarks: true);
        if (offset > 0)
        {
            _ = reader.ReadLine();
        }
        return reader.ReadToEnd();
    }

    private static string Redact(string value)
    {
        var result = value;
        var profile = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        if (!string.IsNullOrWhiteSpace(profile))
        {
            result = result.Replace(profile, "[USER_HOME]", StringComparison.OrdinalIgnoreCase);
        }
        result = SecretPattern().Replace(result, "$1$2[REDACTED]");
        result = BearerPattern().Replace(result, "$1[REDACTED]");
        return result;
    }

    [GeneratedRegex("(?im)(api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret)(\\s*[:=]\\s*[\"']?)[^\\s,\"']+")]
    private static partial Regex SecretPattern();

    [GeneratedRegex("(?im)(authorization\\s*[:=]\\s*bearer\\s+)[^\\s,\"']+")]
    private static partial Regex BearerPattern();
}
