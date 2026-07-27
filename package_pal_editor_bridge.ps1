param(
    [string]$DllPath = "",
    [string]$Version = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSCommandPath
if (-not $Version) {
    $Version = (
        Get-Content -LiteralPath (
            Join-Path $repoRoot "native\pal_editor_bridge\VERSION"
        ) -Raw
    ).Trim()
}
if ($Version -notmatch '^\d+\.\d+\.\d+$') {
    throw "Invalid PalEditorBridge version: $Version"
}
if (-not $DllPath) {
    $DllPath = Join-Path $repoRoot "build\pal_editor_bridge_ue4ss\ue4ss\Game__Shipping__Win64\PalEditorBridge.dll"
}
$resolvedDll = (Resolve-Path -LiteralPath $DllPath).Path

$outputRoot = Join-Path $repoRoot "mod"
$packageName = "PalEditorBridge-UE4SS-Mod-$Version"
$packageRoot = Join-Path $outputRoot $packageName
$zipPath = Join-Path $outputRoot "$packageName.zip"
$expectedPrefix = [System.IO.Path]::GetFullPath($outputRoot).TrimEnd('\') + '\'
$resolvedPackageRoot = [System.IO.Path]::GetFullPath($packageRoot)

if (-not $resolvedPackageRoot.StartsWith($expectedPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Package output escaped the repository mod directory."
}

New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null

if (Test-Path -LiteralPath $packageRoot) {
    Remove-Item -LiteralPath $packageRoot -Recurse -Force
}
if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}

$modRoot = Join-Path $packageRoot "PalEditorBridge"
$dllRoot = Join-Path $modRoot "dlls"
New-Item -ItemType Directory -Path $dllRoot -Force | Out-Null

Copy-Item -LiteralPath $resolvedDll -Destination (Join-Path $dllRoot "main.dll")
Copy-Item -LiteralPath (Join-Path $repoRoot "native\pal_editor_bridge\package\PalEditorBridge\enabled.txt") -Destination $modRoot
Copy-Item -LiteralPath (Join-Path $repoRoot "native\pal_editor_bridge\package\INSTALL.zh-CN.md") -Destination $packageRoot

Compress-Archive -LiteralPath $packageRoot -DestinationPath $zipPath -CompressionLevel Optimal

Write-Output "PACKAGE_ROOT=$packageRoot"
Write-Output "PACKAGE_ZIP=$zipPath"
