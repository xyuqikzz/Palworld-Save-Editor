import json
import os
from pathlib import Path
import re
import sys
from typing import Optional
from urllib.parse import unquote, urlparse
import aiohttp

def get_program_path():
    # If running in AppImage, use the real file path
    if "APPIMAGE" in os.environ:
        return Path(os.environ["APPIMAGE"]).parent
    elif getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    else:
        return Path(__file__).parent.resolve()

PROGRAM_PATH = get_program_path()
if hasattr(sys, 'frozen'):
    if hasattr(sys, "_MEIPASS"):
        ASSETS_PATH = Path(sys._MEIPASS)
    else:
        ASSETS_PATH = get_program_path()
else:
    ASSETS_PATH = get_program_path()

CONFIG_PATH = PROGRAM_PATH / 'config.json'

VERSION = "1.0.1"
RELEASE_TYPE = "RELEASE"
BUILD_TIME = "0000000001"
GIT_HASH = "0000000"
REPO = "undefined"
PROJECT_RELEASES_URL = "https://github.com/xyuqikzz/Palworld-Save-Editor/releases/latest"

def version_info() -> str:
    if GIT_HASH == "0000000":
        return f"{VERSION}-COMPAT-FULLASSETS-BUILD24088745"
    if RELEASE_TYPE == "NIGHTLY":
        return f"{VERSION}-{RELEASE_TYPE}-{GIT_HASH}-{REPO}-{BUILD_TIME}"
    if RELEASE_TYPE == "RELEASE":
        return f"{VERSION}-{RELEASE_TYPE}-{GIT_HASH}"
    
def is_gh_build() -> bool:
    return GIT_HASH != "0000000"
    
async def get_new_version() -> Optional[tuple[str, str]]:
    if not is_gh_build():
        return None

    def parse_version(value: str) -> Optional[tuple[int, int, int]]:
        match = re.match(r"^v?(\d+)\.(\d+)\.(\d+)", value)
        if not match:
            return None
        return tuple(int(part) for part in match.groups())

    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(
                PROJECT_RELEASES_URL,
                allow_redirects=True,
            ) as response:
                if response.status != 200:
                    return None
                release_url = str(response.url)

        release_path = urlparse(release_url).path
        marker = "/releases/tag/"
        if marker not in release_path:
            return None
        latest_version = unquote(release_path.split(marker, 1)[1]).strip("/")
        latest_parts = parse_version(latest_version)
        current_parts = parse_version(VERSION)
        if not latest_parts or not current_parts or latest_parts <= current_parts:
            return None
        return latest_version, release_url
    except Exception as e:
        print(f"Error checking for updates: {e}")
        return None


class Config:
    i18n: str = "en"
    mode: str = "gui"
    port: int = 58080
    debug: bool = False
    path: str = None
    password: str = None
    nocli: bool = False
    max_souls_level: int = 60
    _password_hash: str = None
    JWT_SECRET_KEY: str = "X2Nvbm5sb3N0"

    @classmethod
    def load_from_file(cls, file_path: str=CONFIG_PATH):
        """Load configuration values from a JSON file using pathlib."""
        path = Path(file_path)
        if path.exists():
            with path.open("r") as file:
                data = json.load(file)
                for key, value in data.items():
                    if hasattr(cls, key):
                        setattr(cls, key, value)

    @classmethod
    def set_configs(cls, attrs: dict):
        for key, value in attrs.items():
            if hasattr(cls, key):
                setattr(cls, key, value)
        Config.save_to_file()

    @classmethod
    def set_config(cls, key, value):
        if hasattr(cls, key):
            setattr(cls, key, value)
        Config.save_to_file()

    @classmethod
    def save_to_file(cls, file_path: str=CONFIG_PATH):
        """Save current configuration values to a JSON file using the to_dict method and pathlib."""
        config_data = cls.to_dict()
        path = Path(file_path)
        with path.open("w") as file:
            json.dump(config_data, file, indent=4)

    @classmethod
    def __str__(cls):
        dic = cls.to_dict()
        attrs = [f"{key}: {dic[key]}" for key in dic]
        return ", ".join(attrs)

    @classmethod
    def to_dict(cls):
        return {
            'i18n': Config.i18n,
            'mode': Config.mode,
            'port': Config.port,
            'path': Config.path,
            'password': Config.password,
            'max_souls_level': Config.max_souls_level,
            'JWT_SECRET_KEY': Config.JWT_SECRET_KEY
        }

