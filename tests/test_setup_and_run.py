from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SetupAndRunScriptTests(unittest.TestCase):
    def test_windows_launcher_uses_supported_isolated_python(self) -> None:
        script = (PROJECT_ROOT / "setup_and_run.ps1").read_text(encoding="utf-8")

        self.assertIn("Python 3.11 or newer is required.", script)
        self.assertIn("function Invoke-Checked", script)
        self.assertIn("$ErrorActionPreference = 'Stop'", script)
        self.assertIn("build\\runtime-venv", script)
        self.assertIn("@{ Command = 'py'; Arguments = @('-3') }", script)
        self.assertNotIn("Activate.ps1", script)


if __name__ == "__main__":
    unittest.main()
