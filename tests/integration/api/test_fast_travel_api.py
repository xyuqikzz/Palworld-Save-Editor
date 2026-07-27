from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from palworld_pal_editor.api.player import player_blueprint
from palworld_pal_editor.application.fast_travel_editor import (
    FAST_TRAVEL_UNLOCK_CONFIRMATION,
)
from palworld_pal_editor.application.runtime import SESSION_RUNTIME
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.core.pal_objects import PalObjects
from palworld_pal_editor.domain.fast_travel_catalog import FAST_TRAVEL_POINT_IDS


class _Player:
    PlayerUId = "fast-travel-api-player"
    InstanceId = "fast-travel-api-instance"
    NickName = "Fast Travel API"
    Level = 1

    def __init__(self) -> None:
        flag = PalObjects.MapProperty("NameProperty", "BoolProperty")
        flag["value"] = [{"key": FAST_TRAVEL_POINT_IDS[0], "value": True}]
        self._player_save_data = {
            "RecordData": PalObjects.PalLoggedinPlayerSaveDataRecordData(
                {
                    "FastTravelPointUnlockFlag": flag,
                    "PreservedCounter": PalObjects.IntProperty(42),
                }
            ),
            "InventoryInfo": {"value": {}},
        }


class FastTravelApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.player = _Player()
        manager = SimpleNamespace(
            gvas_file=SimpleNamespace(header=None),
            player_mapping={self.player.PlayerUId: self.player},
            get_player=lambda player_id: (
                self.player if player_id == self.player.PlayerUId else None
            ),
        )
        self.session = SaveSession.from_loaded_manager(
            manager, Path("synthetic-save")
        )
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

    def test_revision_bound_unlock_command_preserves_other_player_fields(self) -> None:
        response = self.client.post(
            f"/api/player/{self.player.PlayerUId}/commands",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 0,
                "command": "unlock_all_fast_travel_points",
                "confirmation": FAST_TRAVEL_UNLOCK_CONFIRMATION,
            },
        )

        self.assertEqual(200, response.status_code, response.get_json())
        result = response.get_json()["data"]
        self.assertEqual(1, result["revision"])
        self.assertTrue(result["changed"])
        self.assertEqual(len(FAST_TRAVEL_POINT_IDS), result["value"]["unlocked_count"])
        self.assertEqual(
            42,
            self.player._player_save_data["RecordData"]["value"][
                "PreservedCounter"
            ]["value"],
        )
        self.assertEqual(
            [f"player_file:{self.player.PlayerUId}"],
            self.session.changes()[0]["affected_records"],
        )

    def test_confirmation_and_unknown_fields_are_rejected_without_mutation(self) -> None:
        endpoint = f"/api/player/{self.player.PlayerUId}/commands"
        base = {
            "session_id": self.session.session_id,
            "expected_revision": 0,
            "command": "unlock_all_fast_travel_points",
        }
        response = self.client.post(
            endpoint,
            headers=self.headers,
            json={**base, "confirmation": "解锁全地图"},
        )
        self.assertEqual(400, response.status_code)
        self.assertEqual(
            "FAST_TRAVEL_CONFIRMATION_REQUIRED",
            response.get_json()["error"]["code"],
        )

        response = self.client.post(
            endpoint,
            headers=self.headers,
            json={
                **base,
                "confirmation": FAST_TRAVEL_UNLOCK_CONFIRMATION,
                "raw_save_data": {},
            },
        )
        self.assertEqual(400, response.status_code)
        self.assertEqual(
            "UNSUPPORTED_COMMAND_FIELD",
            response.get_json()["error"]["code"],
        )
        self.assertEqual(0, self.session.revision)
        self.assertEqual([], self.session.changes())


if __name__ == "__main__":
    unittest.main()
