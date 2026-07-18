from __future__ import annotations

from pathlib import Path
import unittest

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from palworld_pal_editor.api.pal import pal_blueprint
from palworld_pal_editor.application.runtime import SESSION_RUNTIME
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.core.character_index import CharacterIndex
from palworld_pal_editor.core.save_manager import SaveManager
from tests.unit.test_structural_pal_editor import (
    PAL_ID,
    PLAYER_ID,
    make_manager,
)


class StructuralPalApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manager, self.player, self.pal = make_manager()
        self.session = SaveSession.from_loaded_manager(
            self.manager, Path("synthetic-structural-api-save")
        )
        SESSION_RUNTIME.replace_for_tests(self.session)
        singleton = SaveManager()
        self._had_singleton_players = hasattr(singleton, "player_mapping")
        self._singleton_players = getattr(singleton, "player_mapping", None)
        singleton.player_mapping = self.manager.player_mapping

        app = Flask(__name__)
        app.config.update(
            JWT_SECRET_KEY="test-secret-key-that-is-at-least-32-bytes",
            TESTING=True,
        )
        JWTManager(app)
        app.register_blueprint(pal_blueprint, url_prefix="/api/pal")
        with app.app_context():
            token = create_access_token(identity="test-user")
        self.client = app.test_client()
        self.headers = {"Authorization": f"Bearer {token}"}

    def tearDown(self) -> None:
        SESSION_RUNTIME.replace_for_tests(None)
        singleton = SaveManager()
        if self._had_singleton_players:
            singleton.player_mapping = self._singleton_players
        else:
            del singleton.player_mapping

    def test_add_preview_and_delete_use_structural_contract(self) -> None:
        response = self.client.post(
            "/api/pal/structural/commands",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 0,
                "command": "add_pal",
                "player_id": str(PLAYER_ID),
                "species_id": "SheepBall",
                "container_type": "PAL_STORAGE",
            },
        )
        self.assertEqual(200, response.status_code)
        pal_id = response.get_json()["data"]["pal"]["pal_id"]
        self.assertIn(pal_id, CharacterIndex(self.manager).pals)

        preview = self.client.post(
            f"/api/pal/{pal_id}/delete-preview",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 1,
            },
        )
        self.assertEqual(200, preview.status_code)
        token = preview.get_json()["data"]["impact_token"]
        deleted = self.client.post(
            "/api/pal/structural/commands",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 1,
                "command": "delete_pal",
                "pal_id": pal_id,
                "impact_token": token,
            },
        )
        self.assertEqual(200, deleted.status_code)
        self.assertNotIn(pal_id, CharacterIndex(self.manager).pals)
        self.assertEqual(2, self.session.revision)

    def test_raw_ids_unknown_fields_and_stale_revision_are_rejected(self) -> None:
        response = self.client.post(
            "/api/pal/structural/commands",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 0,
                "command": "move_pal",
                "pal_id": str(PAL_ID),
                "target_player_id": str(PLAYER_ID),
                "container_type": "PAL_STORAGE",
                "container_id": "raw-id-must-not-cross-interface",
            },
        )
        self.assertEqual(400, response.status_code)
        self.assertEqual(
            "UNSUPPORTED_COMMAND_FIELD", response.get_json()["error"]["code"]
        )

        missing = self.client.post(
            "/api/pal/structural/commands",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 0,
                "command": "move_pal",
                "pal_id": str(PAL_ID),
                "target_player_id": str(PLAYER_ID),
                "container_type": "PAL_STORAGE",
            },
        )
        self.assertEqual(409, missing.status_code)
        self.assertEqual(
            "IMPACT_PREVIEW_REQUIRED", missing.get_json()["error"]["code"]
        )
        preview = self.client.post(
            "/api/pal/structural/preview",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 0,
                "command": "move_pal",
                "pal_id": str(PAL_ID),
                "target_player_id": str(PLAYER_ID),
                "container_type": "PAL_STORAGE",
            },
        )
        self.assertEqual(200, preview.status_code)
        moved = self.client.post(
            "/api/pal/structural/commands",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 0,
                "command": "move_pal",
                "pal_id": str(PAL_ID),
                "target_player_id": str(PLAYER_ID),
                "container_type": "PAL_STORAGE",
                "impact_token": preview.get_json()["data"]["impact_token"],
            },
        )
        self.assertEqual(200, moved.status_code)
        stale = self.client.post(
            f"/api/pal/{PAL_ID}/delete-preview",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 0,
            },
        )
        self.assertEqual(409, stale.status_code)
        self.assertEqual("STALE_REVISION", stale.get_json()["error"]["code"])


if __name__ == "__main__":
    unittest.main()
