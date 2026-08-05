from __future__ import annotations

import json
import warnings

import jwt
from jwt.warnings import InsecureKeyLengthWarning

from palworld_pal_editor.config import Config
from palworld_pal_editor import webui


def test_loading_legacy_config_rotates_and_persists_short_jwt_secret(
    tmp_path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "i18n": "en",
                "JWT_SECRET_KEY": "X2Nvbm5sb3N0",
                "future_setting": "preserve-me",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(Config, "JWT_SECRET_KEY", "temporary-test-value")

    Config.load_from_file(config_path)

    assert len(Config.JWT_SECRET_KEY.encode("utf-8")) >= 32
    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    assert persisted["JWT_SECRET_KEY"] == Config.JWT_SECRET_KEY
    assert persisted["future_setting"] == "preserve-me"
    with warnings.catch_warnings():
        warnings.simplefilter("error", InsecureKeyLengthWarning)
        jwt.encode(
            {"sub": "regression"},
            Config.JWT_SECRET_KEY,
            algorithm="HS256",
        )


def test_loading_legacy_soul_limit_migrates_the_old_default(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "i18n": "en",
                "max_souls_level": 60,
                "future_setting": "preserve-me",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(Config, "max_souls_level", 20)

    Config.load_from_file(config_path)

    assert Config.max_souls_level == 20
    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    assert persisted["max_souls_level"] == 20
    assert persisted["future_setting"] == "preserve-me"


def test_webui_refreshes_flask_jwt_secret_after_config_load(
    monkeypatch,
) -> None:
    strong_secret = "runtime-secret-" + ("x" * 32)
    monkeypatch.setattr(Config, "JWT_SECRET_KEY", strong_secret)

    webui.configure_runtime_security()

    assert webui.app.config["JWT_SECRET_KEY"] == strong_secret


def test_config_log_output_redacts_secrets(monkeypatch) -> None:
    monkeypatch.setattr(Config, "password", "web-password")
    monkeypatch.setattr(Config, "JWT_SECRET_KEY", "jwt-signing-secret")

    output = Config.__str__()

    assert "web-password" not in output
    assert "jwt-signing-secret" not in output
