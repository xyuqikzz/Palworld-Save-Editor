from __future__ import annotations

from pathlib import Path
import unittest

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from palworld_pal_editor.api.pal import pal_blueprint
from palworld_pal_editor.api.save import save_blueprint
from palworld_pal_editor.application.runtime import SESSION_RUNTIME
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.core.character_index import CharacterIndex
from palworld_pal_editor.core.save_manager import SaveManager
from palworld_pal_editor.utils.data_provider import PAL_DATA, DataProvider
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
        app.register_blueprint(save_blueprint, url_prefix="/api/save")
        with app.app_context():
            token = create_access_token(identity="test-user")
        self.client = app.test_client()
        self.headers = {"Authorization": f"Bearer {token}"}

    def test_pal_catalog_exposes_every_synced_human_npc(self) -> None:
        response = self.client.get("/api/save/pal_data", headers=self.headers)

        self.assertEqual(200, response.status_code)
        catalog = response.get_json()["data"]["arr"]
        humans = {item["InternalName"]: item for item in catalog if item["IsHuman"]}
        expected_humans = {
            internal_name
            for internal_name in PAL_DATA
            if DataProvider.is_pal_human(internal_name)
        }
        self.assertEqual(expected_humans, set(humans))
        self.assertEqual("Handgun", humans["SalesPerson_Wander"]["DefaultWeapon"])
        self.assertEqual(
            "GatlingGun",
            humans["Male_DarkTrader02"]["DefaultWeapon"],
        )
        self.assertEqual(
            {
                internal_name
                for internal_name in expected_humans
                if DataProvider.has_human_icon(internal_name)
            },
            {
                internal_name
                for internal_name, item in humans.items()
                if item["HasIcon"]
            },
        )

    def test_pal_catalog_exposes_only_the_rideable_king_whale_record(self) -> None:
        response = self.client.get("/api/save/pal_data", headers=self.headers)

        self.assertEqual(200, response.status_code)
        catalog = {
            item["InternalName"]: item for item in response.get_json()["data"]["arr"]
        }
        self.assertNotIn("KingWhale", catalog)
        self.assertEqual(
            "203",
            catalog["BOSS_KingWhale_otomo"]["SortingKey"],
        )

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

    def test_add_command_accepts_creation_presets_as_one_revision(self) -> None:
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
                "passive": ["WorldTree_CraftSpeed", "CraftSpeed_up3"],
                "max_pal": False,
                "max_work": True,
                "unrestricted": False,
            },
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()["data"]
        pal = CharacterIndex(self.manager).pals[payload["pal"]["pal_id"]]
        self.assertEqual(
            ["WorldTree_CraftSpeed", "CraftSpeed_up3"],
            pal.PassiveSkillList,
        )
        self.assertEqual(5, pal.Rank)
        self.assertTrue(pal.WorkSuitabilities)
        self.assertTrue(all(level == 10 for level in pal.WorkSuitabilities.values()))
        self.assertEqual(1, self.session.revision)

    def test_add_max_npc_reports_and_persists_maximum_trust(self) -> None:
        response = self.client.post(
            "/api/pal/structural/commands",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 0,
                "command": "add_pal",
                "player_id": str(PLAYER_ID),
                "species_id": "SalesPerson_Wander",
                "container_type": "PAL_STORAGE",
                "max_pal": True,
            },
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()["data"]
        npc = CharacterIndex(self.manager).pals[payload["pal"]["pal_id"]]
        self.assertTrue(npc.IsHuman)
        self.assertEqual(10, payload["pal"]["friendship_level"])
        self.assertEqual(10, npc.FriendshipLevel)
        self.assertEqual(DataProvider.get_pal_friendship(10), npc.FriendshipPoint)
        self.assertNotIn("bIsAwakening", npc._pal_param)
        self.assertEqual(1, self.session.revision)

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
