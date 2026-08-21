from pathlib import Path
import tomllib
import unittest

from scripts.verify_bridge_prebuilt import normalize_source_bytes


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def test_bridge_source_hash_is_independent_of_checkout_line_endings(
        self,
    ) -> None:
        self.assertEqual(
            normalize_source_bytes(b"first\r\nsecond\rthird\n"),
            normalize_source_bytes(b"first\nsecond\nthird\n"),
        )

    def test_windows_bundle_collects_ooz_extension(self) -> None:
        build_script = (PROJECT_ROOT / "build_executable.ps1").read_text(
            encoding="utf-8"
        )
        gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")

        self.assertTrue((PROJECT_ROOT / "src" / "ooz.pyd").is_file())
        self.assertIn("!src/ooz.pyd", gitignore)
        self.assertIn("'--paths=src'", build_script)
        self.assertIn("'--hidden-import=ooz'", build_script)

    def test_windows_build_uses_supported_isolated_python(self) -> None:
        build_script = (PROJECT_ROOT / "build_executable.ps1").read_text(
            encoding="utf-8"
        )
        pyproject = tomllib.loads(
            (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )

        self.assertEqual(">=3.11", pyproject["project"]["requires-python"])
        self.assertIn("Python 3.11 or newer is required.", build_script)
        self.assertIn("function Invoke-Checked", build_script)
        self.assertIn("$ErrorActionPreference = 'Stop'", build_script)
        self.assertIn("build\\venv", build_script)
        self.assertNotIn("Activate.ps1", build_script)

    def test_windows_bundle_accepts_the_exact_bridge_mod_package(self) -> None:
        build_script = (PROJECT_ROOT / "build_executable.ps1").read_text(
            encoding="utf-8"
        )

        self.assertIn("[string]$BridgeModPackage", build_script)
        self.assertIn("PalEditorBridge-UE4SS-Mod-*.zip", build_script)
        self.assertIn("selectedBridgeModPackage", build_script)
        self.assertIn(";mod", build_script)
        self.assertIn("Resolve-Path -LiteralPath $BridgeModPackage", build_script)

    def test_server_mod_package_uses_one_declared_version(self) -> None:
        package_script = (
            PROJECT_ROOT / "package_pal_editor_bridge.ps1"
        ).read_text(encoding="utf-8")
        build_script = (
            PROJECT_ROOT / "build_pal_editor_bridge.ps1"
        ).read_text(encoding="utf-8")
        prebuilt_verifier = (
            PROJECT_ROOT / "scripts" / "verify_bridge_prebuilt.py"
        ).read_text(encoding="utf-8")
        version = (
            PROJECT_ROOT / "native" / "pal_editor_bridge" / "VERSION"
        ).read_text(encoding="utf-8").strip()
        bridge_header = (
            PROJECT_ROOT
            / "native"
            / "pal_editor_bridge"
            / "include"
            / "pal_editor_bridge"
            / "bridge_core.hpp"
        ).read_text(encoding="utf-8")
        mod_source = (
            PROJECT_ROOT
            / "native"
            / "pal_editor_bridge"
            / "ue4ss"
            / "src"
            / "pal_editor_bridge_mod.cpp"
        ).read_text(encoding="utf-8")
        install_guide = (
            PROJECT_ROOT
            / "native"
            / "pal_editor_bridge"
            / "package"
            / "INSTALL.zh-CN.md"
        ).read_text(encoding="utf-8")

        self.assertEqual("0.6.3", version)
        self.assertIn("native\\pal_editor_bridge\\VERSION", package_script)
        self.assertIn(version, bridge_header)
        self.assertIn(version, mod_source)
        self.assertIn(version, install_guide)
        self.assertIn('Join-Path $repoRoot "mod"', package_script)
        self.assertNotIn('Join-Path $repoRoot "dist"', package_script)
        self.assertIn(
            "url.https://github.com/.insteadOf=git@github.com:",
            build_script,
        )
        self.assertNotIn("Visual Studio 17 2022", build_script)
        self.assertIn("UseVerifiedPrebuilt", build_script)
        self.assertIn("sourceSha256", prebuilt_verifier)
        self.assertIn("dllSha256", prebuilt_verifier)
        self.assertIn("ue4ssRevision", prebuilt_verifier)
        self.assertIn("normalize_source_bytes", prebuilt_verifier)

    def test_release_workflow_rebuilds_and_verifies_the_mod_before_publish(
        self,
    ) -> None:
        workflow = (
            PROJECT_ROOT / ".github" / "workflows" / "release-build.yml"
        ).read_text(encoding="utf-8")
        bridge_build = workflow.index("./build_pal_editor_bridge.ps1")
        exe_build = workflow.index(
            './build_executable.ps1 -BridgeModPackage "${{ steps.bridge.outputs.package }}"'
        )
        verification = workflow.index("scripts/verify_release_artifacts.py")
        publish = workflow.index("publish-release:")

        self.assertLess(bridge_build, exe_build)
        self.assertLess(exe_build, verification)
        self.assertLess(verification, publish)
        self.assertIn("needs: release-checks", workflow)
        self.assertIn("needs: release-build", workflow)
        self.assertIn("actions/download-artifact@v4", workflow)
        self.assertIn("-UseVerifiedPrebuilt", workflow)
        self.assertIn("${{ steps.bridge.outputs.dll }}", workflow)
        self.assertIn("Prepare categorized release notes", workflow)
        self.assertIn('grep -Fxq "## New Features"', workflow)
        self.assertIn('grep -Fxq "## Bug Fixes"', workflow)
        self.assertIn('grep -Fxq "## Other Changes"', workflow)
        self.assertIn("body_path: release-notes.md", workflow)
        self.assertIn("SHA256SUMS.txt", workflow)
        self.assertIn("fail_on_unmatched_files: true", workflow)

    def test_application_release_versions_are_synchronized(self) -> None:
        pyproject = tomllib.loads(
            (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )
        config = (
            PROJECT_ROOT / "src" / "palworld_pal_editor" / "config.py"
        ).read_text(encoding="utf-8")
        lockfile = (PROJECT_ROOT / "uv.lock").read_text(encoding="utf-8")

        self.assertEqual("1.1.8", pyproject["project"]["version"])
        self.assertIn('VERSION = "1.1.8"', config)
        self.assertIn(
            'name = "palworld-save-editor"\nversion = "1.1.8"',
            lockfile,
        )


if __name__ == "__main__":
    unittest.main()
