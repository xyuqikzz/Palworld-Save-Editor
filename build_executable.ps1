param(
    [switch]$FunctionsOnly,
    [string]$BridgeModPackage = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$PROJECT_ROOT = $PSScriptRoot

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Command,
        [string[]]$Arguments = @()
    )

    & $Command @Arguments
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "Command failed with exit code ${exitCode}: $Command $($Arguments -join ' ')"
    }
}

function Get-PythonCommand {
    $candidates = @(
        @{ Command = 'python3'; Arguments = @() },
        @{ Command = 'python'; Arguments = @() },
        @{ Command = 'py'; Arguments = @('-3') }
    )
    $detectedVersions = @()

    foreach ($candidate in $candidates) {
        if ($null -eq (Get-Command $candidate.Command -ErrorAction SilentlyContinue)) {
            continue
        }

        $versionArguments = @($candidate.Arguments) + @('--version')
        try {
            $versionOutput = & $candidate.Command @versionArguments 2>&1
        } catch {
            continue
        }
        if ($LASTEXITCODE -ne 0) {
            continue
        }

        $versionText = ($versionOutput | Out-String).Trim()
        if ($versionText -notmatch '^Python (?<major>\d+)\.(?<minor>\d+)(?:\.(?<patch>\d+))?') {
            continue
        }

        $majorVersion = [int]$Matches.major
        $minorVersion = [int]$Matches.minor
        $detectedVersions += "$($candidate.Command): $versionText"
        if ($majorVersion -gt 3 -or ($majorVersion -eq 3 -and $minorVersion -ge 11)) {
            return [pscustomobject]@{
                Command = $candidate.Command
                Arguments = @($candidate.Arguments)
                Version = $versionText
            }
        }
    }

    $detectedText = if ($detectedVersions.Count -gt 0) {
        " Detected: $($detectedVersions -join ', ')."
    } else {
        ''
    }
    throw "Python 3.11 or newer is required.$detectedText"
}

function Remove-BuildOutputDirectory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [ValidateRange(1, 100)]
        [int]$MaxAttempts = 8,
        [ValidateRange(0, 60000)]
        [int]$RetryDelayMilliseconds = 500
    )

    $lastError = $null
    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        if (-not (Test-Path -LiteralPath $Path)) {
            return
        }

        try {
            Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
            return
        } catch {
            $lastError = $_
            $isEmptyDirectory = $false
            try {
                if (Test-Path -LiteralPath $Path -PathType Container) {
                    $remainingItem = (
                        Get-ChildItem -LiteralPath $Path -Force -ErrorAction Stop |
                            Select-Object -First 1
                    )
                    $isEmptyDirectory = $null -eq $remainingItem
                }
            } catch {
                $isEmptyDirectory = $false
            }
            if ($isEmptyDirectory) {
                Write-Warning (
                    "Build output directory is empty but its directory handle is in use. " +
                    "Reusing the empty directory: $Path"
                )
                return
            }

            if ($attempt -lt $MaxAttempts) {
                if ($attempt -eq 1) {
                    Write-Warning "Build output is temporarily locked: $Path. Retrying cleanup..."
                }
                if ($RetryDelayMilliseconds -gt 0) {
                    Start-Sleep -Milliseconds $RetryDelayMilliseconds
                }
            }
        }
    }

    $blockingProcesses = @()
    try {
        $normalizedPath = [System.IO.Path]::GetFullPath($Path).TrimEnd(
            [System.IO.Path]::DirectorySeparatorChar,
            [System.IO.Path]::AltDirectorySeparatorChar
        ) + [System.IO.Path]::DirectorySeparatorChar
        $blockingProcesses = @(
            Get-CimInstance Win32_Process -ErrorAction Stop |
                Where-Object {
                    $_.ExecutablePath -and
                    [System.IO.Path]::GetFullPath($_.ExecutablePath).StartsWith(
                        $normalizedPath,
                        [System.StringComparison]::OrdinalIgnoreCase
                    )
                }
        )
    } catch {
        $blockingProcesses = @()
    }

    $processHint = if ($blockingProcesses.Count -gt 0) {
        $processList = (
            $blockingProcesses |
                ForEach-Object { "$($_.Name) (PID $($_.ProcessId))" }
        ) -join ', '
        " Blocking process(es): $processList."
    } else {
        ''
    }
    $message = (
        "Could not clean build output '$Path' after $MaxAttempts attempts." +
        $processHint +
        ' Close any running palworld-save-editor.exe and any terminal or File Explorer window using this folder, ' +
        "then run .\build_executable.ps1 again. Last error: $($lastError.Exception.Message)"
    )
    throw [System.IO.IOException]::new($message, $lastError.Exception)
}

if ($FunctionsOnly) {
    return
}

Set-Location -LiteralPath $PROJECT_ROOT

$python = Get-PythonCommand
Write-Host "Using $($python.Command) ($($python.Version))"

if ($null -eq (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw 'Node.js and npm are required.'
}

$frontendRoot = Join-Path $PROJECT_ROOT 'frontend\palworld-pal-editor-webui'
Push-Location -LiteralPath $frontendRoot
try {
    Invoke-Checked -Command 'npm' -Arguments @('install')
    Invoke-Checked -Command 'npm' -Arguments @('run', 'build')
} finally {
    Pop-Location
}

$frontendDist = Join-Path $frontendRoot 'dist'
$webuiRoot = Join-Path $PROJECT_ROOT 'src\palworld_pal_editor\webui'
if (-not (Test-Path -LiteralPath $frontendDist -PathType Container)) {
    throw "Frontend build output was not created: $frontendDist"
}
if (Test-Path -LiteralPath $webuiRoot) {
    Remove-Item -LiteralPath $webuiRoot -Recurse -Force
}
Move-Item -LiteralPath $frontendDist -Destination $webuiRoot

$buildVenv = Join-Path $PROJECT_ROOT 'build\venv'
Remove-BuildOutputDirectory -Path $buildVenv
$venvArguments = @($python.Arguments) + @('-m', 'venv', $buildVenv)
Invoke-Checked -Command $python.Command -Arguments $venvArguments

$buildPython = Join-Path $buildVenv 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $buildPython -PathType Leaf)) {
    throw "Build virtual environment was not created: $buildPython"
}

Invoke-Checked -Command $buildPython -Arguments @(
    '-m', 'pip', 'install', '-r', (Join-Path $PROJECT_ROOT 'requirements.txt')
)

$distRoot = Join-Path $PROJECT_ROOT 'dist'
Remove-BuildOutputDirectory -Path $distRoot

$bridgePackagePattern = '^PalEditorBridge-UE4SS-Mod-(\d+\.\d+\.\d+)\.zip$'
if ($BridgeModPackage) {
    $resolvedBridgePackage = Resolve-Path -LiteralPath $BridgeModPackage
    $selectedBridgeModPackage = Get-Item -LiteralPath $resolvedBridgePackage.Path
    if ($selectedBridgeModPackage.Name -notmatch $bridgePackagePattern) {
        throw "Invalid PalEditorBridge package name: $($selectedBridgeModPackage.Name)"
    }
} else {
    $selectedBridgeModPackage = (
        Get-ChildItem -LiteralPath (Join-Path $PROJECT_ROOT 'mod') `
            -Filter 'PalEditorBridge-UE4SS-Mod-*.zip' -File |
            ForEach-Object {
                $versionMatch = [regex]::Match(
                    $_.Name,
                    $bridgePackagePattern
                )
                if ($versionMatch.Success) {
                    [pscustomobject]@{
                        File = $_
                        Version = [version]$versionMatch.Groups[1].Value
                    }
                }
            } |
            Sort-Object -Property Version -Descending |
            Select-Object -First 1
    ).File
    if ($null -eq $selectedBridgeModPackage) {
        throw 'No versioned PalEditorBridge UE4SS Mod package was found in mod/.'
    }
}
Write-Host "Bundling bridge mod: $($selectedBridgeModPackage.FullName)"

Invoke-Checked -Command $buildPython -Arguments @(
    '-m', 'PyInstaller',
    '--noconfirm',
    '--clean',
    '--onefile',
    '-i', (Join-Path $PROJECT_ROOT 'icon.ico'),
    '--paths=src',
    '--add-data=src/palworld_pal_editor/assets;assets',
    '--add-data=src/palworld_pal_editor/webui;webui',
    "--add-data=$($selectedBridgeModPackage.FullName);mod",
    '.\src\palworld_pal_editor\__main__.py',
    '--name', 'palworld-save-editor',
    '--log-level=INFO',
    '--hidden-import=ooz'
)

$artifact = Join-Path $distRoot 'palworld-save-editor.exe'
if (-not (Test-Path -LiteralPath $artifact -PathType Leaf)) {
    throw "Build completed without the expected executable: $artifact"
}
Write-Host "Build complete: $artifact"
