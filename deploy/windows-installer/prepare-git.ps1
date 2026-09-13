param(
    [Parameter(Mandatory = $true)]
    [string]$PayloadRoot,
    [string]$GitArchive = ""
)

$ErrorActionPreference = "Stop"
$gitVersion = "2.55.0.windows.5"
$archiveSha256 = "56d7b226b7693196cfc71fef26568f536c4a021ab6c37ff2db4287bed908e96e"
$archiveUrl = "https://github.com/git-for-windows/git/releases/download/v2.55.0.windows.5/MinGit-2.55.0.5-64-bit.zip"
$payload = (Resolve-Path -LiteralPath $PayloadRoot).Path
$runtimeRoot = Join-Path $payload "runtime\git"
$temporaryRoot = Join-Path ([IO.Path]::GetTempPath()) ("soda-git-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $temporaryRoot | Out-Null
try {
    if ([string]::IsNullOrWhiteSpace($GitArchive)) {
        $GitArchive = Join-Path $temporaryRoot "MinGit.zip"
        Invoke-WebRequest -Uri $archiveUrl -OutFile $GitArchive -UseBasicParsing
    }
    $archive = (Resolve-Path -LiteralPath $GitArchive).Path
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $archiveSha256) {
        throw "MinGit SHA-256 mismatch. Refusing to unpack or execute the archive."
    }
    $expanded = Join-Path $temporaryRoot "expanded"
    # Preserve the complete official distribution, including all DLLs, certificates and licenses.
    Expand-Archive -LiteralPath $archive -DestinationPath $expanded
    foreach ($relative in @("cmd\git.exe", "mingw64\bin\git.exe", "mingw64\bin\git-remote-https.exe", "mingw64\etc\ssl\certs\ca-bundle.crt", "LICENSE.txt")) {
        if (-not (Test-Path -LiteralPath (Join-Path $expanded $relative) -PathType Leaf)) {
            throw "Incomplete MinGit archive: $relative"
        }
    }
    $actualVersion = & (Join-Path $expanded "cmd\git.exe") --version
    if ($LASTEXITCODE -ne 0 -or "$actualVersion".Trim() -ne "git version $gitVersion") {
        throw "Bundled Git self-check failed: $actualVersion"
    }
    New-Item -ItemType Directory -Path (Join-Path $payload "runtime") -Force | Out-Null
    if (Test-Path -LiteralPath $runtimeRoot) {
        Remove-Item -LiteralPath $runtimeRoot -Recurse -Force
    }
    Move-Item -LiteralPath $expanded -Destination $runtimeRoot
    $metadata = [ordered]@{
        format = "soda-git-runtime-v1"
        git_version = $gitVersion
        architecture = "x64"
        archive_url = $archiveUrl
        archive_sha256 = $archiveSha256
        license = "runtime/git/LICENSE.txt"
        component_licenses = "runtime/git/mingw64/share/licenses"
        upstream_source = "https://github.com/git-for-windows/git/tree/v2.55.0.windows.5"
        modified = $false
    }
    [IO.File]::WriteAllText((Join-Path $payload "GIT_RUNTIME.json"),
        (($metadata | ConvertTo-Json -Depth 4) + "`n"), [Text.UTF8Encoding]::new($false))
    Write-Host "[OK] bundled $actualVersion (private application runtime; no system PATH changes)"
}
finally {
    Remove-Item -LiteralPath $temporaryRoot -Recurse -Force -ErrorAction SilentlyContinue
}
