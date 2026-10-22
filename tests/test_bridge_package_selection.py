from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def select_package(directory, explicit=""):
    def quote(value):
        return "'" + str(value).replace("'", "''") + "'"

    return subprocess.run(
        ["pwsh", "-NoProfile", "-Command",
         f". {quote(ROOT / 'build_executable.ps1')} -FunctionsOnly; "
         f"(Get-BridgeModPackage -ProjectRoot {quote(directory)} "
         f"-PackagePath {quote(explicit)}).Name"],
        capture_output=True, text=True, timeout=15,
    )


@pytest.mark.skipif(not shutil.which("pwsh"), reason="PowerShell required")
@pytest.mark.parametrize("empty_mod", [False, True])
def test_missing_bridge_reports_actionable_dependency(tmp_path, empty_mod):
    if empty_mod:
        (tmp_path / "mod").mkdir()
    result = select_package(tmp_path)
    assert result.returncode != 0
    assert "No versioned PalEditorBridge" in result.stderr
    assert "-BridgeModPackage" in result.stderr
    assert "PropertyNotFoundStrict" not in result.stderr


@pytest.mark.skipif(not shutil.which("pwsh"), reason="PowerShell required")
def test_bridge_uses_numeric_version_and_validates_explicit_path(tmp_path):
    mod = tmp_path / "mod"
    mod.mkdir()
    for version in ["1.9.0", "1.10.0", "invalid"]:
        (mod / f"PalEditorBridge-UE4SS-Mod-{version}.zip").touch()
    result = select_package(tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "PalEditorBridge-UE4SS-Mod-1.10.0.zip"
    chosen = mod / "PalEditorBridge-UE4SS-Mod-1.9.0.zip"
    assert select_package(tmp_path, chosen).stdout.strip() == chosen.name
    assert select_package(tmp_path, mod / "PalEditorBridge-UE4SS-Mod-invalid.zip").returncode != 0
    assert select_package(tmp_path, mod).returncode != 0
