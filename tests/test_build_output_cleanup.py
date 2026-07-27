import ctypes
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading
import time
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def start_exclusive_lock(
    artifact: Path, hold_seconds: float
) -> tuple[threading.Thread, threading.Event, threading.Event, list[str]]:
    lock_ready = threading.Event()
    lock_released = threading.Event()
    lock_errors: list[str] = []

    def hold_exclusive_lock() -> None:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_file = kernel32.CreateFileW
        create_file.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
        ]
        create_file.restype = ctypes.c_void_p
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = [ctypes.c_void_p]
        close_handle.restype = ctypes.c_int

        handle = create_file(
            str(artifact),
            0x80000000,
            0,
            None,
            3,
            0x80,
            None,
        )
        invalid_handle = ctypes.c_void_p(-1).value
        if handle == invalid_handle:
            lock_errors.append(
                f"CreateFileW failed with error {ctypes.get_last_error()}"
            )
            lock_ready.set()
            return

        try:
            lock_ready.set()
            time.sleep(hold_seconds)
        finally:
            close_handle(handle)
            lock_released.set()

    lock_thread = threading.Thread(target=hold_exclusive_lock, daemon=True)
    lock_thread.start()
    return lock_thread, lock_ready, lock_released, lock_errors


@unittest.skipUnless(sys.platform == "win32", "Windows file locking is required")
class BuildOutputCleanupTests(unittest.TestCase):
    def test_build_venv_uses_resilient_cleanup(self) -> None:
        script = (PROJECT_ROOT / "build_executable.ps1").read_text(
            encoding="utf-8"
        )

        self.assertIn("Remove-BuildOutputDirectory -Path $buildVenv", script)

    def test_cleanup_reuses_an_empty_directory_held_as_a_working_directory(
        self,
    ) -> None:
        with TemporaryDirectory() as temporary_directory:
            output_directory = Path(temporary_directory) / "dist"
            output_directory.mkdir()
            holder = subprocess.Popen(
                [
                    "pwsh",
                    "-NoProfile",
                    "-Command",
                    "[Console]::Out.WriteLine('READY'); Start-Sleep -Seconds 10",
                ],
                cwd=output_directory,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                self.assertEqual("READY", holder.stdout.readline().strip())
                command = (
                    f". '{PROJECT_ROOT / 'build_executable.ps1'}' -FunctionsOnly; "
                    f"Remove-BuildOutputDirectory -Path '{output_directory}' "
                    "-MaxAttempts 1 -RetryDelayMilliseconds 0"
                )
                completed = subprocess.run(
                    ["pwsh", "-NoProfile", "-Command", command],
                    cwd=PROJECT_ROOT,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                self.assertEqual(
                    0,
                    completed.returncode,
                    completed.stdout + completed.stderr,
                )
                self.assertTrue(output_directory.is_dir())
                self.assertEqual([], list(output_directory.iterdir()))
            finally:
                holder.terminate()
                holder.wait(timeout=5)
                holder.stdout.close()
                holder.stderr.close()

    def test_cleanup_retries_a_transiently_locked_artifact(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            output_directory = Path(temporary_directory) / "dist"
            output_directory.mkdir()
            artifact = output_directory / "palworld-save-editor.exe"
            artifact.write_bytes(b"locked build artifact")

            lock_thread, lock_ready, lock_released, lock_errors = (
                start_exclusive_lock(artifact, hold_seconds=0.75)
            )
            self.assertTrue(lock_ready.wait(timeout=5), "File lock was not acquired")
            self.assertEqual([], lock_errors)

            command = (
                f". '{PROJECT_ROOT / 'build_executable.ps1'}' -FunctionsOnly; "
                f"Remove-BuildOutputDirectory -Path '{output_directory}'"
            )
            completed = subprocess.run(
                ["pwsh", "-NoProfile", "-Command", command],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                timeout=10,
            )

            lock_thread.join(timeout=5)
            self.assertTrue(lock_released.is_set(), "File lock was not released")
            self.assertEqual(
                0,
                completed.returncode,
                completed.stdout + completed.stderr,
            )
            self.assertFalse(output_directory.exists())

    def test_cleanup_reports_a_persistent_lock_after_bounded_attempts(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            output_directory = Path(temporary_directory) / "dist"
            output_directory.mkdir()
            artifact = output_directory / "palworld-save-editor.exe"
            artifact.write_bytes(b"locked build artifact")

            lock_thread, lock_ready, lock_released, lock_errors = (
                start_exclusive_lock(artifact, hold_seconds=0.75)
            )
            self.assertTrue(lock_ready.wait(timeout=5), "File lock was not acquired")
            self.assertEqual([], lock_errors)

            command = (
                f". '{PROJECT_ROOT / 'build_executable.ps1'}' -FunctionsOnly; "
                f"Remove-BuildOutputDirectory -Path '{output_directory}' "
                "-MaxAttempts 1 -RetryDelayMilliseconds 0"
            )
            completed = subprocess.run(
                ["pwsh", "-NoProfile", "-Command", command],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                timeout=10,
            )

            lock_thread.join(timeout=5)
            self.assertTrue(lock_released.is_set(), "File lock was not released")
            self.assertNotEqual(0, completed.returncode)
            output = completed.stdout + completed.stderr
            self.assertIn("Could not clean build output", output)
            self.assertIn("after 1 attempts", output)
            self.assertIn("Close any", output)
            self.assertIn("running palworld-save-editor.exe", output)


if __name__ == "__main__":
    unittest.main()
