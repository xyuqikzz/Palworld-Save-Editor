from __future__ import annotations

from pathlib import Path
import unittest

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from palworld_pal_editor.api.preset import preset_blueprint
from palworld_pal_editor.application.runtime import SESSION_RUNTIME
from palworld_pal_editor.application.save_session import SaveSession
from tests.unit.test_structural_pal_editor import PAL_ID, make_manager


class PresetApiTests(unittest.TestCase):
    def setUp(self) -> None:
        manager, _player, self.pal = make_manager()
        self.session = SaveSession.from_loaded_manager(
            manager, Path("synthetic-preset-api-save")
        )
        SESSION_RUNTIME.replace_for_tests(self.session)
        app = Flask(__name__)
        app.config.update(
            JWT_SECRET_KEY="test-secret-key-that-is-at-least-32-bytes",
            TESTING=True,
        )
        JWTManager(app)
        app.register_blueprint(preset_blueprint, url_prefix="/api/preset")
        with app.app_context():
            token = create_access_token(identity="test-user")
        self.client = app.test_client()
        self.headers = {"Authorization": f"Bearer {token}"}

    def tearDown(self) -> None:
        SESSION_RUNTIME.replace_for_tests(None)

    def test_export_preview_and_apply_are_versioned_and_atomic(self) -> None:
        exported = self.client.post(
            "/api/preset/export",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "kind": "skills",
                "target_id": str(PAL_ID),
            },
        )
        self.assertEqual(200, exported.status_code)
        preset = exported.get_json()["data"]["preset"]
        self.assertEqual("palworld-pal-editor-preset", preset["schema"])
        payload = {
            "session_id": self.session.session_id,
            "expected_revision": 0,
            "preset": preset,
            "target_ids": [str(PAL_ID)],
        }
        preview = self.client.post(
            "/api/preset/preview", headers=self.headers, json=payload
        )
        self.assertEqual(200, preview.status_code)
        payload["impact_token"] = preview.get_json()["data"]["impact_token"]
        applied = self.client.post(
            "/api/preset/apply", headers=self.headers, json=payload
        )
        self.assertEqual(200, applied.status_code)
        self.assertEqual(1, applied.get_json()["data"]["revision"])
        self.assertEqual("BatchCommand", self.session.changes()[0]["command"])

    def test_unknown_fields_and_invalid_targets_are_rejected(self) -> None:
        response = self.client.post(
            "/api/preset/export",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "kind": "skills",
                "target_id": str(PAL_ID),
                "raw_payload": {},
            },
        )
        self.assertEqual(400, response.status_code)
        self.assertEqual(
            "UNSUPPORTED_COMMAND_FIELD", response.get_json()["error"]["code"]
        )


if __name__ == "__main__":
    unittest.main()
