from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from palworld_pal_editor.api.pal import _pal_data, pal_blueprint
from palworld_pal_editor.api.player import player_blueprint, player_to_dict
from palworld_pal_editor.application.runtime import SESSION_RUNTIME
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.core.save_manager import SaveManager
from tests.unit.test_character_editor import _Player, make_pal


class CharacterApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.player = _Player()
        self.pal = make_pal()
        manager = SimpleNamespace(
            gvas_file=SimpleNamespace(header=None),
            player_mapping={self.player.PlayerUId: self.player},
            get_player=lambda player_id: (
                self.player if player_id == self.player.PlayerUId else None
            ),
            get_pal=lambda pal_id: (
                self.pal if str(pal_id) == str(self.pal.InstanceId) else None
            ),
        )
        self.session = SaveSession.from_loaded_manager(
            manager, Path("synthetic-save")
        )
        SESSION_RUNTIME.replace_for_tests(self.session)

        singleton = SaveManager()
        self._had_singleton_players = hasattr(singleton, "player_mapping")
        self._singleton_players = getattr(singleton, "player_mapping", None)
        singleton.player_mapping = {
            str(self.pal.OwnerPlayerUId): SimpleNamespace(NickName="Owner")
        }

        app = Flask(__name__)
        app.config.update(
            JWT_SECRET_KEY="test-secret-key-that-is-at-least-32-bytes",
            TESTING=True,
        )
        JWTManager(app)
        app.register_blueprint(player_blueprint, url_prefix="/api/player")
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

    def test_explicit_player_and_pal_commands_share_session_revision(self) -> None:
        response = self.client.post(
            f"/api/player/{self.player.PlayerUId}/commands",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 0,
                "command": "update_player_identity",
                "name": "API Player",
            },
        )
        self.assertEqual(200, response.status_code)
        self.assertEqual("API Player", response.get_json()["data"]["value"]["name"])

        response = self.client.post(
            f"/api/pal/{self.pal.InstanceId}/commands",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 1,
                "command": "update_pal_skills",
                "active": ["EPalWazaID::AquaJet"],
                "mastered": ["EPalWazaID::AquaJet"],
                "passive": ["Rare"],
            },
        )
        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual(2, payload["data"]["revision"])
        self.assertEqual(["Rare"], payload["data"]["value"]["passive"])
        self.assertEqual(2, self.session.revision)

    def test_legacy_read_models_do_not_expose_raw_container_ids(self) -> None:
        self.player.has_viewing_cage = lambda: False
        player_payload = player_to_dict(self.player)
        pal_payload = _pal_data(self.pal)

        self.assertNotIn("OtomoCharacterContainerId", player_payload)
        self.assertNotIn("PalStorageContainerId", player_payload)
        self.assertNotIn("ContainerId", pal_payload)
        self.assertIn("SlotIndex", pal_payload)

    def test_unknown_top_level_and_domain_fields_are_rejected(self) -> None:
        response = self.client.post(
            f"/api/player/{self.player.PlayerUId}/commands",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 0,
                "command": "update_player_identity",
                "name": "No change",
                "_player_param": {},
            },
        )
        self.assertEqual(400, response.status_code)
        self.assertEqual(
            "UNSUPPORTED_COMMAND_FIELD", response.get_json()["error"]["code"]
        )

        response = self.client.post(
            f"/api/pal/{self.pal.InstanceId}/commands",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 0,
                "command": "update_pal_enhancement",
                "values": {"Talent_HP": 100},
            },
        )
        self.assertEqual(400, response.status_code)
        self.assertEqual(
            "UNSUPPORTED_COMMAND_FIELD", response.get_json()["error"]["code"]
        )
        self.assertEqual("Player One", self.player.NickName)
        self.assertEqual(0, self.session.revision)

    def test_stale_character_command_is_rejected_before_mutation(self) -> None:
        first = self.client.post(
            f"/api/player/{self.player.PlayerUId}/commands",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 0,
                "command": "update_player_progression",
                "technology_points": 10,
            },
        )
        self.assertEqual(200, first.status_code)
        response = self.client.post(
            f"/api/pal/{self.pal.InstanceId}/commands",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 0,
                "command": "update_pal_identity",
                "name": "Stale",
            },
        )
        self.assertEqual(409, response.status_code)
        self.assertEqual("STALE_REVISION", response.get_json()["error"]["code"])
        self.assertNotEqual("Stale", self.pal.NickName)
        self.assertEqual(1, self.session.revision)

    def test_legacy_routes_map_only_known_fields_to_explicit_commands(self) -> None:
        response = self.client.patch(
            "/api/player/player_data",
            headers=self.headers,
            json={
                "PlayerUId": self.player.PlayerUId,
                "key": "TechnologyPoint",
                "value": 20,
            },
        )
        self.assertEqual(200, response.status_code)
        self.assertEqual(20, self.player.TechnologyPoint)

        response = self.client.patch(
            "/api/pal/paldata",
            headers=self.headers,
            json={
                "PalGuid": str(self.pal.InstanceId),
                "PlayerUId": self.player.PlayerUId,
                "key": "Talent_HP",
                "value": 75,
            },
        )
        self.assertEqual(200, response.status_code)
        self.assertEqual(75, self.pal.Talent_HP)

        response = self.client.patch(
            "/api/pal/paldata",
            headers=self.headers,
            json={
                "PalGuid": str(self.pal.InstanceId),
                "key": "_pal_param",
                "value": {},
            },
        )
        self.assertEqual(400, response.status_code)
        self.assertEqual(
            "UNSUPPORTED_COMMAND_FIELD", response.get_json()["error"]["code"]
        )
        self.assertEqual(2, self.session.revision)


if __name__ == "__main__":
    unittest.main()
