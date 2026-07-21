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
    ):
        self._window_provider = window_provider or (lambda: webview.windows)
        self._modern_folder_picker = modern_folder_picker
        self._platform_name = platform_name or sys.platform

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
