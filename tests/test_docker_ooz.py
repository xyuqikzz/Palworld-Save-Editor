import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PALOOZ_COMMIT = "c23ceebceca4a7ffe7ccc0c5084a20cbce353f50"


class DockerOozTests(unittest.TestCase):
    def _run_isolated_import(
        self, backends: dict[str, str | None], assertion: str
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            isolated_root = Path(temporary_directory)
            shutil.copytree(
                PROJECT_ROOT / "src" / "palworld_save_tools",
                isolated_root / "palworld_save_tools",
            )
            for module_name, backend_name in backends.items():
                if backend_name is None:
                    (isolated_root / module_name).mkdir()
                else:
                    (isolated_root / f"{module_name}.py").write_text(
                        f"BACKEND = {backend_name!r}\n"
                        "def compress(*args): return b'compressed'\n"
                        "def decompress(*args): return b'decompressed'\n",
                        encoding="utf-8",
                    )

            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(isolated_root)
            result = subprocess.run(
                [
                    sys.executable,
                    "-S",
                    "-c",
                    "from palworld_save_tools.compressor import oozlib; "
                    + assertion,
                ],
                cwd=isolated_root,
                env=environment,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )

        self.assertEqual(
            0,
            result.returncode,
            msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_linux_backend_falls_back_to_palooz(self) -> None:
        self._run_isolated_import(
            {"palooz": "palooz"},
            "assert oozlib.ooz.BACKEND == 'palooz'",
        )

    def test_incomplete_ooz_namespace_falls_back_to_palooz(self) -> None:
        self._run_isolated_import(
            {"ooz": None, "palooz": "palooz"},
            "assert oozlib.ooz.BACKEND == 'palooz'",
        )

    def test_windows_backend_keeps_ooz_priority(self) -> None:
        self._run_isolated_import(
            {"ooz": "ooz", "palooz": "palooz"},
            "assert oozlib.ooz.BACKEND == 'ooz'",
        )

    def test_docker_builds_pinned_linux_backend_from_source(self) -> None:
        dockerfile = (PROJECT_ROOT / "docker" / "Dockerfile").read_text(
            encoding="utf-8"
        )

        self.assertIn(f"ARG PALOOZ_COMMIT={PALOOZ_COMMIT}", dockerfile)
        self.assertIn(
            "git+https://github.com/deafdudecomputers/"
            "PalworldSaveTools.git@${PALOOZ_COMMIT}"
            "#subdirectory=src/palsav/palooz",
            dockerfile,
        )
        self.assertIn("import palooz", dockerfile)
        self.assertIn("palooz.compress", dockerfile)
        self.assertIn("palooz.decompress", dockerfile)
        self.assertIn("sed -i 's/\\r$//' /app/docker/app.sh", dockerfile)


if __name__ == "__main__":
    unittest.main()
