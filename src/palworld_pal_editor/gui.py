import hashlib
import os
import re
import shutil
import sys
import threading
import time
import requests
import traceback
import webbrowser
import webview
from pathlib import Path
from palworld_pal_editor.config import Config
from palworld_pal_editor.utils import LOGGER
from palworld_pal_editor.webui import main as web_main
from palworld_pal_editor.windows_dialog import choose_folder


class NativeDialogApi:
    def __init__(
        self,
        window_provider=None,
        modern_folder_picker=choose_folder,
        platform_name: str | None = None,
        bridge_mod_package: str | Path | None = None,
    ):
        self._window_provider = window_provider or (lambda: webview.windows)
        self._modern_folder_picker = modern_folder_picker
        self._platform_name = platform_name or sys.platform
        self._bridge_mod_package = (
            Path(bridge_mod_package).resolve()
            if bridge_mod_package is not None
            else None
        )

    def select_save_directory(self, requested_directory=None):
        initial_directory = ""
        if requested_directory and Path(requested_directory).is_dir():
            initial_directory = str(Path(requested_directory).resolve())
        elif Config.path and Path(Config.path).is_dir():
            initial_directory = Config.path

        if self._platform_name == "win32":
            return self._modern_folder_picker(initial_directory)

        windows = self._window_provider()
        if not windows:
            return None
        selected = windows[0].create_file_dialog(webview.FOLDER_DIALOG, directory=initial_directory)
        if not selected:
            return None
        return str(selected[0])

    @staticmethod
    def _bridge_mod_version(path: Path) -> tuple[int, int, int]:
        match = re.fullmatch(
            r"PalEditorBridge-UE4SS-Mod-(\d+)\.(\d+)\.(\d+)\.zip",
            path.name,
        )
        if not match:
            return (0, 0, 0)
        return tuple(int(part) for part in match.groups())

    def _resolve_bridge_mod_package(self) -> Path:
        if self._bridge_mod_package is not None:
            if not self._bridge_mod_package.is_file():
                raise FileNotFoundError("The bundled PalEditorBridge package is missing.")
            return self._bridge_mod_package

        roots = []
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            roots.append(Path(sys._MEIPASS) / "mod")
        roots.append(Path(__file__).resolve().parents[2] / "mod")
        candidates = [
            package
            for root in roots
            if root.is_dir()
            for package in root.glob("PalEditorBridge-UE4SS-Mod-*.zip")
            if self._bridge_mod_version(package) != (0, 0, 0)
        ]
        if not candidates:
            raise FileNotFoundError("The bundled PalEditorBridge package is missing.")
        return max(candidates, key=self._bridge_mod_version)

    @staticmethod
    def _available_download_path(directory: Path, filename: str) -> Path:
        target = directory / filename
        if not target.exists():
            return target
        stem = Path(filename).stem
        suffix = Path(filename).suffix
        counter = 1
        while True:
            candidate = directory / f"{stem} ({counter}){suffix}"
            if not candidate.exists():
                return candidate
            counter += 1

    @staticmethod
    def _file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as package_file:
            for chunk in iter(lambda: package_file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def download_bridge_mod(self, requested_directory=None):
        if self._platform_name != "win32":
            return {
                "status": "unsupported",
                "reason": "WINDOWS_DESKTOP_REQUIRED",
            }

        initial_directory = ""
        if requested_directory and Path(requested_directory).is_dir():
            initial_directory = str(Path(requested_directory).resolve())
        else:
            downloads = Path.home() / "Downloads"
            if downloads.is_dir():
                initial_directory = str(downloads.resolve())

        selected = self._modern_folder_picker(initial_directory)
        if not selected:
            return {"status": "cancelled"}

        temporary = None
        try:
            destination = Path(selected).resolve()
            if not destination.is_dir():
                return {
                    "status": "failed",
                    "reason": "DOWNLOAD_DIRECTORY_INVALID",
                }
            package = self._resolve_bridge_mod_package()
            target = self._available_download_path(destination, package.name)
            temporary = destination / f".{target.name}.{os.getpid()}.part"
            shutil.copy2(package, temporary)
            expected_hash = self._file_sha256(package)
            if self._file_sha256(temporary) != expected_hash:
                raise OSError("The copied PalEditorBridge package failed verification.")
            os.replace(temporary, target)
            temporary = None
            return {
                "status": "completed",
                "path": str(target),
                "filename": target.name,
                "sha256": expected_hash,
            }
        except Exception:
            LOGGER.warning(
                f"Failed to save the bundled PalEditorBridge package: {traceback.format_exc()}"
            )
            return {
                "status": "failed",
                "reason": "BRIDGE_MOD_DOWNLOAD_FAILED",
            }
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    LOGGER.warning(
                        "Failed to remove an incomplete PalEditorBridge download."
                    )

    def select_local_data_file(self, requested_path=None):
        initial_directory = ""
        if requested_path:
            requested = Path(requested_path)
            if requested.is_file():
                initial_directory = str(requested.resolve().parent)
            elif requested.is_dir():
                initial_directory = str(requested.resolve())
        if not initial_directory and Config.path:
            configured = Path(Config.path)
            if configured.is_dir():
                initial_directory = str(configured.resolve())

        windows = self._window_provider()
        if not windows:
            return None
        selected = windows[0].create_file_dialog(
            webview.OPEN_DIALOG,
            directory=initial_directory,
            allow_multiple=False,
            file_types=("Palworld LocalData (*.sav)",),
        )
        if not selected:
            return None
        return str(selected[0])


def main():
    t = threading.Thread(target=web_main)
    t.daemon = True
    t.start()
    
    while True:
        LOGGER.info("Waiting for backend response...")
        try:
            response = requests.get(f"http://127.0.0.1:{Config.port}/api/ready")
            if response.status_code == 200:
                LOGGER.info("Backend ready, launching GUI...")
                break
            time.sleep(0.5)
        except requests.exceptions.ConnectionError:
            time.sleep(0.5)

    LOGGER.info("If the desktop window fails, use Web mode or report the issue at https://github.com/xyuqikzz/Palworld-Save-Editor/issues")

    try:
        webview.create_window(
            "Palworld-Save-Editor",
            url=f"http://127.0.0.1:{Config.port}/",
            js_api=NativeDialogApi(),
            width=1600,
            height=1000,
            min_size=(960, 600),
        )
        webview.start()
    except KeyboardInterrupt:
        pass
    except:
        LOGGER.warning(f"Failed Launching pywebview: {traceback.format_exc()}")
        LOGGER.info(f"Fallback to web browser, opening http://127.0.0.1:{Config.port} ...")
        threading.Timer(1, lambda: webbrowser.open(f"http://127.0.0.1:{Config.port}") ).start()
        t.join()
    sys.exit()

if __name__ == "__main__":
    main()
