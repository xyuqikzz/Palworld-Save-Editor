from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from palworld_pal_editor.api.player import player_blueprint
from palworld_pal_editor.application.runtime import SESSION_RUNTIME
from palworld_pal_editor.application.save_session import SaveSession
from tests.unit.test_mission_editor import _name_array, _ordered_array, _ordered_record


class _Player:
    PlayerUId = "mission-api-player"
    InstanceId = "mission-api-instance"
    NickName = "Mission API"
    Level = 1

    def __init__(self) -> None:
        self._player_save_data = {
            "CompletedQuestArray_FullRelease": _name_array(
                ["Main_UnlockFastTravel"]
            ),
            "OrderedQuestArray_FullRelease": _ordered_array(
                [_ordered_record("Main_OpenSurvivalGuide")]
            ),
            "InventoryInfo": {"value": {}},
        }


class MissionApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.player = _Player()
        manager = SimpleNamespace(
            gvas_file=SimpleNamespace(header=None),
            player_mapping={self.player.PlayerUId: self.player},
            get_player=lambda player_id: (
                self.player if player_id == self.player.PlayerUId else None
            ),
        )
        self.session = SaveSession.from_loaded_manager(manager, Path("synthetic-save"))
        SESSION_RUNTIME.replace_for_tests(self.session)
        app = Flask(__name__)
        app.config.update(
            JWT_SECRET_KEY="test-secret-key-that-is-at-least-32-bytes",
            TESTING=True,
        )
        JWTManager(app)
        app.register_blueprint(player_blueprint, url_prefix="/api/player")
        with app.app_context():
            token = create_access_token(identity="test-user")
        self.client = app.test_client()
        self.headers = {"Authorization": f"Bearer {token}"}

    def tearDown(self) -> None:
        SESSION_RUNTIME.replace_for_tests(None)

    def test_read_preview_and_confirmed_command_share_revision_metadata(self) -> None:
        response = self.client.get(
            f"/api/player/{self.player.PlayerUId}/missions",
            headers=self.headers,
            query_string={"session_id": self.session.session_id, "locale": "zh-CN"},
        )
        self.assertEqual(200, response.status_code)
        data = response.get_json()["data"]
        self.assertEqual(120, data["summary"]["total"])
        self.assertEqual("24088745", data["source"]["build_id"])
        self.assertEqual("zh-CN", data["locale"])

        command = {
            "session_id": self.session.session_id,
            "expected_revision": 0,
            "operation": "mark_completed",
            "mission_ids": ["Main_OpenSurvivalGuide"],
        }
        response = self.client.post(
            f"/api/player/{self.player.PlayerUId}/missions/preview",
            headers=self.headers,
            json=command,
        )
        self.assertEqual(200, response.status_code)
        preview = response.get_json()["data"]
        self.assertEqual(1, preview["impact_count"])

        response = self.client.post(
            f"/api/player/{self.player.PlayerUId}/missions/commands",
            headers=self.headers,
            json={**command, "preview_token": preview["preview_token"]},
        )
        self.assertEqual(200, response.status_code)
        result = response.get_json()["data"]
        self.assertEqual(1, result["revision"])
        self.assertEqual(1, result["pending_change_count"])

    def test_unknown_fields_missing_token_and_stale_revision_are_rejected(self) -> None:
        base = {
            "session_id": self.session.session_id,
            "expected_revision": 0,
            "operation": "reset_to_unaccepted",
            "mission_ids": ["Main_UnlockFastTravel"],
        }
        response = self.client.post(
            f"/api/player/{self.player.PlayerUId}/missions/preview",
            headers=self.headers,
            json={**base, "raw_save_data": {}},
        )
        self.assertEqual(400, response.status_code)
        self.assertEqual(
            "UNSUPPORTED_COMMAND_FIELD", response.get_json()["error"]["code"]
        )

        response = self.client.post(
            f"/api/player/{self.player.PlayerUId}/missions/commands",
            headers=self.headers,
            json=base,
        )
        self.assertEqual(409, response.status_code)
        self.assertEqual(
            "MISSION_PREVIEW_STALE", response.get_json()["error"]["code"]
        )

        preview = self.client.post(
            f"/api/player/{self.player.PlayerUId}/missions/preview",
            headers=self.headers,
            json=base,
        ).get_json()["data"]
        response = self.client.post(
            f"/api/player/{self.player.PlayerUId}/missions/commands",
            headers=self.headers,
            json={
                **base,
                "expected_revision": 1,
                "preview_token": preview["preview_token"],
            },
        )
        self.assertEqual(409, response.status_code)
        self.assertEqual("STALE_REVISION", response.get_json()["error"]["code"])


if __name__ == "__main__":
    unittest.main()
