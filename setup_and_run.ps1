$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$PROJECT_ROOT = $PSScriptRoot
Set-Location -LiteralPath $PROJECT_ROOT

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

$runtimeVenv = Join-Path $PROJECT_ROOT 'build\runtime-venv'
$runtimePython = Join-Path $runtimeVenv 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $runtimePython -PathType Leaf)) {
    $venvArguments = @($python.Arguments) + @('-m', 'venv', $runtimeVenv)
    Invoke-Checked -Command $python.Command -Arguments $venvArguments
}

$runtimeVersion = & $runtimePython --version 2>&1
if ($LASTEXITCODE -ne 0 -or $runtimeVersion -notmatch '^Python (?<major>\d+)\.(?<minor>\d+)') {
    throw "Runtime virtual environment is invalid: $runtimePython"
}
if ([int]$Matches.major -lt 3 -or ([int]$Matches.major -eq 3 -and [int]$Matches.minor -lt 11)) {
    throw "Runtime virtual environment must use Python 3.11 or newer: $runtimeVersion"
}

Invoke-Checked -Command $runtimePython -Arguments @(
    '-m', 'pip', 'install', '-r', (Join-Path $PROJECT_ROOT 'requirements.txt')
)
Invoke-Checked -Command $runtimePython -Arguments @(
    '-m', 'pip', 'install', '-e', $PROJECT_ROOT
)

$applicationArguments = @('-m', 'palworld_pal_editor') + @($args)
Invoke-Checked -Command $runtimePython -Arguments $applicationArguments
