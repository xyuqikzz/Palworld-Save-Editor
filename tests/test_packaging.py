from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def test_windows_bundle_collects_ooz_extension(self) -> None:
        build_script = (PROJECT_ROOT / "build_executable.ps1").read_text(
            encoding="utf-8"
        )
        gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")

        self.assertTrue((PROJECT_ROOT / "src" / "ooz.pyd").is_file())
        self.assertIn("!src/ooz.pyd", gitignore)
        self.assertIn('--paths="src"', build_script)
        self.assertIn('--hidden-import="ooz"', build_script)


if __name__ == "__main__":
    unittest.main()
