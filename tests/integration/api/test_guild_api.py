from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from palworld_pal_editor.api.save import save_blueprint
from palworld_pal_editor.application.runtime import SESSION_RUNTIME
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.core.group_data import PalGroup
from palworld_pal_editor.core.pal_objects import toUUID


GUILD_ID = toUUID("11111111-1111-1111-1111-111111111111")


class _Groups:
    def __init__(self, group: PalGroup) -> None:
        self.group = group

    def get_group(self, group_id):
        return self.group if str(group_id) == str(self.group.group_id) else None


class GuildApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.group = PalGroup(
            {
                "value": {
                    "RawData": {
                        "value": {
                            "group_id": GUILD_ID,
                            "group_name": "Guild",
                            "guild_name": "Builders",
                            "individual_character_handle_ids": [],
                            "base_ids": [
                                toUUID("22222222-2222-2222-2222-222222222222")
                            ],
                        }
                    }
                }
            },
            "EPalGroupType::Guild",
        )
        manager = SimpleNamespace(
            gvas_file=SimpleNamespace(properties={}, header=None),
            group_data=_Groups(self.group),
            player_mapping={},
        )
        self.session = SaveSession.from_loaded_manager(manager, Path("synthetic-save"))
        SESSION_RUNTIME.replace_for_tests(self.session)

        app = Flask(__name__)
        app.config.update(
            JWT_SECRET_KEY="test-secret-key-that-is-at-least-32-bytes",
            TESTING=True,
        )
        JWTManager(app)
        app.register_blueprint(save_blueprint, url_prefix="/api/save")
        with app.app_context():
            token = create_access_token(identity="test-user")
        self.client = app.test_client()
        self.headers = {"Authorization": f"Bearer {token}"}

    def tearDown(self) -> None:
        SESSION_RUNTIME.replace_for_tests(None)

    def test_update_guild_name_uses_session_revision_contract(self) -> None:
        response = self.client.post(
            f"/api/save/guilds/{GUILD_ID}/commands",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 0,
                "command": "update_guild_name",
                "name": "API Builders",
            },
        )

        self.assertEqual(200, response.status_code, response.get_json())
        payload = response.get_json()["data"]
        self.assertEqual(1, payload["revision"])
        self.assertEqual("API Builders", payload["value"]["name"])
        self.assertEqual("API Builders", self.group.guild_name)

        stale = self.client.post(
            f"/api/save/guilds/{GUILD_ID}/commands",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 0,
                "command": "update_guild_name",
                "name": "Stale Name",
            },
        )
        self.assertEqual(409, stale.status_code)
        self.assertEqual("STALE_REVISION", stale.get_json()["error"]["code"])
        self.assertEqual("API Builders", self.group.guild_name)


if __name__ == "__main__":
    unittest.main()
