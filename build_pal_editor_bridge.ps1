param(
    [string]$UE4SSRoot = "",
    [string]$UE4SSRepository = "https://github.com/Okaetsu/RE-UE4SS.git",
    [string]$UE4SSRevision = "c838a8acaade1a0f860bdf249f039e58f4e10088",
    [switch]$AllowDirtyUE4SSRoot,
    [switch]$UseVerifiedPrebuilt,
    [switch]$RefreshVerifiedPrebuilt
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $PSCommandPath

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Command,
        [string[]]$Arguments = @()
    )

    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $Command $($Arguments -join ' ')"
    }
}

function Get-CMakeCommand {
    $cmake = Get-Command cmake.exe -ErrorAction SilentlyContinue
    if ($null -ne $cmake) {
        return $cmake.Source
    }

    $vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
    if (Test-Path -LiteralPath $vswhere -PathType Leaf) {
        $candidate = (
            & $vswhere -latest -products * `
                -find "Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe" |
                Select-Object -First 1
        )
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            return $candidate
        }
    }

    throw "CMake was not found. Install Visual Studio with C++ and CMake tools."
}

$git = (Get-Command git.exe -ErrorAction Stop).Source
$cmake = Get-CMakeCommand
$ctest = Join-Path (Split-Path -Parent $cmake) "ctest.exe"
if (-not (Test-Path -LiteralPath $ctest -PathType Leaf)) {
    throw "CTest was not found beside CMake: $ctest"
}

$nativeRoot = Join-Path $repoRoot "native\pal_editor_bridge"
$coreBuildRoot = Join-Path $repoRoot "build\pal_editor_bridge_core"
$ue4ssBuildRoot = Join-Path $repoRoot "build\pal_editor_bridge_ue4ss"
$prebuiltRoot = Join-Path $nativeRoot "prebuilt"
$prebuiltDll = Join-Path $prebuiltRoot "PalEditorBridge.dll"
$prebuiltVerifier = Join-Path $repoRoot "scripts\verify_bridge_prebuilt.py"
$python = (Get-Command python.exe -ErrorAction Stop).Source

Invoke-Checked -Command $cmake -Arguments @(
    "-S", $nativeRoot,
    "-B", $coreBuildRoot,
    "-A", "x64",
    "-DPAL_EDITOR_BRIDGE_BUILD_TESTS=ON"
)
Invoke-Checked -Command $cmake -Arguments @(
    "--build", $coreBuildRoot,
    "--config", "Release",
    "--target", "PalEditorBridgeCoreTests"
)
Invoke-Checked -Command $ctest -Arguments @(
    "--test-dir", $coreBuildRoot,
    "-C", "Release",
    "--output-on-failure"
)

if ($UseVerifiedPrebuilt) {
    if ($RefreshVerifiedPrebuilt) {
        throw "UseVerifiedPrebuilt and RefreshVerifiedPrebuilt cannot be combined."
    }
    Invoke-Checked -Command $python -Arguments @(
        $prebuiltVerifier,
        "--expected-ue4ss-revision", $UE4SSRevision
    )
    & (Join-Path $repoRoot "package_pal_editor_bridge.ps1") `
        -DllPath $prebuiltDll
    if ($LASTEXITCODE -ne 0) {
        throw "PalEditorBridge packaging failed with exit code $LASTEXITCODE."
    }
    Write-Output "DLL_PATH=$prebuiltDll"
    exit 0
}

if (-not $UE4SSRoot) {
    $UE4SSRoot = Join-Path $repoRoot "build\dependencies\RE-UE4SS"
}
$ue4ssPath = [System.IO.Path]::GetFullPath($UE4SSRoot)

if (-not (Test-Path -LiteralPath (Join-Path $ue4ssPath ".git"))) {
    if (Test-Path -LiteralPath $ue4ssPath) {
        throw "UE4SSRoot exists but is not a Git checkout: $ue4ssPath"
    }
    $ue4ssParent = Split-Path -Parent $ue4ssPath
    New-Item -ItemType Directory -Path $ue4ssParent -Force | Out-Null
    Invoke-Checked -Command $git -Arguments @(
        "clone",
        "--filter=blob:none",
        "--no-checkout",
        $UE4SSRepository,
        $ue4ssPath
    )
    Invoke-Checked -Command $git -Arguments @(
        "-C", $ue4ssPath, "config", "core.longpaths", "true"
    )
    Invoke-Checked -Command $git -Arguments @(
        "-C", $ue4ssPath, "checkout", "--detach", $UE4SSRevision
    )
    Invoke-Checked -Command $git -Arguments @(
        "-c", "url.https://github.com/.insteadOf=git@github.com:",
        "-c", "url.https://github.com/.insteadOf=ssh://git@github.com/",
        "-C", $ue4ssPath, "submodule", "update", "--init", "--recursive"
    )
}

$actualRevision = (
    & $git -C $ue4ssPath rev-parse HEAD
).Trim()
if ($LASTEXITCODE -ne 0 -or $actualRevision -ne $UE4SSRevision) {
    throw "UE4SS revision mismatch. Expected $UE4SSRevision, got $actualRevision."
}
$ue4ssStatus = (& $git -C $ue4ssPath status --porcelain | Out-String).Trim()
if ($ue4ssStatus -and -not $AllowDirtyUE4SSRoot) {
    throw "UE4SS checkout is dirty and cannot be used for a reproducible build."
}

Invoke-Checked -Command $cmake -Arguments @(
    "-S", $nativeRoot,
    "-B", $ue4ssBuildRoot,
    "-A", "x64",
    "-DPAL_EDITOR_BRIDGE_BUILD_TESTS=OFF",
    "-DPAL_EDITOR_BRIDGE_UE4SS_ROOT=$ue4ssPath"
)
Invoke-Checked -Command $cmake -Arguments @(
    "--build", $ue4ssBuildRoot,
    "--config", "Game__Shipping__Win64",
    "--target", "PalEditorBridge"
)

$dllPath = Join-Path (
    $ue4ssBuildRoot
) "ue4ss\Game__Shipping__Win64\PalEditorBridge.dll"
if (-not (Test-Path -LiteralPath $dllPath -PathType Leaf)) {
    throw "PalEditorBridge build completed without the expected DLL: $dllPath"
}

if ($RefreshVerifiedPrebuilt) {
    New-Item -ItemType Directory -Path $prebuiltRoot -Force | Out-Null
    Copy-Item -LiteralPath $dllPath -Destination $prebuiltDll -Force
    Invoke-Checked -Command $python -Arguments @(
        $prebuiltVerifier,
        "--write",
        "--ue4ss-revision", $UE4SSRevision
    )
    Invoke-Checked -Command $python -Arguments @(
        $prebuiltVerifier,
        "--expected-ue4ss-revision", $UE4SSRevision
    )
}

& (Join-Path $repoRoot "package_pal_editor_bridge.ps1") -DllPath $dllPath
if ($LASTEXITCODE -ne 0) {
    throw "PalEditorBridge packaging failed with exit code $LASTEXITCODE."
}
Write-Output "DLL_PATH=$dllPath"
