param(
    [Parameter(Mandatory = $true)]
    [string]$DesktopPackageRoot,
    [Parameter(Mandatory = $true)]
    [string]$WorkerPackageRoot,
    [string]$OutputRoot = (Join-Path $PSScriptRoot "dist"),
    [string]$PythonEmbedArchive = "",
    [string]$UvExecutable = "",
    [string]$GitArchive = "",
    [string]$InnoCompiler = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$desktopSource = (Resolve-Path -LiteralPath $DesktopPackageRoot).Path
$workerSource = (Resolve-Path -LiteralPath $WorkerPackageRoot).Path
$output = [IO.Path]::GetFullPath($OutputRoot)
$stagingId = [Guid]::NewGuid().ToString("N").Substring(0, 8)
$staging = Join-Path ([IO.Path]::GetTempPath()) ("SB-" + $stagingId)
$installerOutput = Join-Path $output "installers"
New-Item -ItemType Directory -Path $output -Force | Out-Null
if (Test-Path -LiteralPath $installerOutput) {
    Remove-Item -LiteralPath $installerOutput -Recurse -Force
}
New-Item -ItemType Directory -Path $installerOutput -Force | Out-Null
if (Test-Path -LiteralPath $staging) {
    Remove-Item -LiteralPath $staging -Recurse -Force
}
New-Item -ItemType Directory -Path $staging -Force | Out-Null

function Assert-CleanPayload {
    param([string]$Root)
    if (-not (Test-Path -LiteralPath (Join-Path $Root "PACKAGE_MANIFEST.sha256") -PathType Leaf)) {
        throw "缺少 PACKAGE_MANIFEST.sha256：$Root"
    }
    $privateFiles = Get-ChildItem -LiteralPath $Root -Recurse -Force |
        Where-Object { $_.Name -in @("worker-config.json", ".venv", "__pycache__") -or $_.Extension -eq ".pyc" }
    if ($privateFiles) {
        throw "安装 payload 含有私有配置或缓存：$($privateFiles[0].FullName)"
    }
}

Assert-CleanPayload -Root $desktopSource
Assert-CleanPayload -Root $workerSource
$desktopStage = Join-Path $staging "desktop"
$workerStage = Join-Path $staging "worker"
Copy-Item -LiteralPath $desktopSource -Destination $desktopStage -Recurse
Copy-Item -LiteralPath $workerSource -Destination $workerStage -Recurse

& (Join-Path $PSScriptRoot "prepare-runtime.ps1") -Product desktop `
    -PayloadRoot $desktopStage -RepositoryRoot $repositoryRoot `
    -PythonEmbedArchive $PythonEmbedArchive -UvExecutable $UvExecutable -GitArchive $GitArchive
if ($LASTEXITCODE -ne 0) { throw "Desktop Python runtime 准备失败。" }
& (Join-Path $PSScriptRoot "prepare-runtime.ps1") -Product worker `
    -PayloadRoot $workerStage -RepositoryRoot $repositoryRoot `
    -PythonEmbedArchive $PythonEmbedArchive -UvExecutable $UvExecutable
if ($LASTEXITCODE -ne 0) { throw "Worker Python runtime 准备失败。" }

$desktopRelease = Get-Content -LiteralPath (Join-Path $desktopStage "core\RELEASE.json") -Raw -Encoding UTF8 | ConvertFrom-Json
$workerRelease = Get-Content -LiteralPath (Join-Path $workerStage "worker\RELEASE.json") -Raw -Encoding UTF8 | ConvertFrom-Json
$version = [string]$desktopRelease.product_version
if ($version -ne [string]$workerRelease.worker_version) {
    throw "Desktop 与 Worker 版本不一致。"
}

$webViewBootstrapper = Join-Path $output "MicrosoftEdgeWebview2Setup.exe"
Invoke-WebRequest -UseBasicParsing -Uri "https://go.microsoft.com/fwlink/p/?LinkId=2124703" -OutFile $webViewBootstrapper
$signature = Get-AuthenticodeSignature -FilePath $webViewBootstrapper
if ($signature.Status -ne "Valid" -or $signature.SignerCertificate.Subject -notmatch "Microsoft") {
    throw "WebView2 bootstrapper 的 Microsoft 签名校验失败。"
}

if ([string]::IsNullOrWhiteSpace($InnoCompiler)) {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
    )
    $InnoCompiler = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if ([string]::IsNullOrWhiteSpace($InnoCompiler) -or -not (Test-Path -LiteralPath $InnoCompiler)) {
    throw "未找到 Inno Setup 6 ISCC.exe。请先在构建机安装 Inno Setup 6。"
}

foreach ($definition in @(
    @{ Script = "desktop.iss"; Payload = $desktopStage },
    @{ Script = "worker.iss"; Payload = $workerStage }
)) {
    & $InnoCompiler "/DPayloadRoot=$($definition.Payload)" "/DOutputRoot=$installerOutput" `
        "/DProductVersion=$version" "/DWebView2Bootstrapper=$webViewBootstrapper" `
        (Join-Path $PSScriptRoot $definition.Script)
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup 编译失败：$($definition.Script)"
    }
}

$installers = Get-ChildItem -LiteralPath $installerOutput -Filter "*.exe" -File | Sort-Object Name
$manifest = [ordered]@{
    format = "soda-commercial-windows-release-v1"
    version = $version
    signed = $false
    python_runtime = "3.12.10"
    git_runtime = (Get-Content -LiteralPath (Join-Path $desktopStage "GIT_RUNTIME.json") -Raw -Encoding UTF8 | ConvertFrom-Json)
    installers = @($installers | ForEach-Object {
        [ordered]@{
            file = $_.Name
            bytes = $_.Length
            sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    })
}
[IO.File]::WriteAllText(
    (Join-Path $installerOutput "COMMERCIAL_RELEASE.json"),
    (($manifest | ConvertTo-Json -Depth 6) + "`n"),
    [Text.UTF8Encoding]::new($false))
Remove-Item -LiteralPath $staging -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "[OK] $installerOutput"
