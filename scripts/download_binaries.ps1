param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$artifacts = @(
    @{ Name = "obscura.exe";     Url = "https://github.com/henriklundgren/obscura/releases/latest/download/obscura-windows-x64.exe";    Path = "obscura.exe" },
    @{ Name = "obscura-worker.exe"; Url = "https://github.com/henriklundgren/obscura/releases/latest/download/obscura-worker-windows-x64.exe"; Path = "obscura-worker.exe" }
)

$TargetDir = Join-Path (Split-Path -Parent $PSScriptRoot) ""

foreach ($artifact in $artifacts) {
    $outPath = Join-Path $TargetDir $artifact.Path
    if ((Test-Path -LiteralPath $outPath) -and -not $Force) {
        Write-Host "  [SKIP] $($artifact.Name) — already exists (use -Force to overwrite)"
        continue
    }
    Write-Host "  [DOWNLOAD] $($artifact.Name)..."
    try {
        Invoke-WebRequest -Uri $artifact.Url -OutFile $outPath -UseBasicParsing
        Write-Host "  [OK] Saved to $outPath"
    } catch {
        Write-Warning "  [FAIL] $($artifact.Name): $_"
    }
}

Write-Host "`nDone. Binaries downloaded to $TargetDir"
