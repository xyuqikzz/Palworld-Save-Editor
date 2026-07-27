from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from palworld_pal_editor.api.pal import _pal_data, pal_blueprint
from palworld_pal_editor.api.player import player_blueprint, player_to_dict
from palworld_pal_editor.application.runtime import SESSION_RUNTIME
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.config import Config
from palworld_pal_editor.core.pal_objects import PalObjects
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

    def test_custom_passive_api_requires_explicit_allow_flag(self) -> None:
        custom = "OtherMod_ApiPassive_Exact"
        endpoint = f"/api/pal/{self.pal.InstanceId}/commands"
        base = {
            "session_id": self.session.session_id,
            "expected_revision": 0,
            "command": "update_pal_skills",
            "active": None,
            "mastered": None,
            "passive": [custom],
        }

        rejected = self.client.post(
            endpoint,
            headers=self.headers,
            json=base,
        )

        self.assertEqual(422, rejected.status_code)
        self.assertEqual(
            "UNKNOWN_SKILL",
            rejected.get_json()["error"]["code"],
        )
        self.assertEqual(0, self.session.revision)

        accepted = self.client.post(
            endpoint,
            headers=self.headers,
            json={**base, "allow_custom_passive": True},
        )

        self.assertEqual(200, accepted.status_code, accepted.get_json())
        payload = accepted.get_json()["data"]
        self.assertEqual([custom], payload["value"]["passive"])
        self.assertEqual(1, payload["revision"])
        self.assertEqual([custom], self.pal.PassiveSkillList)
        self.assertEqual(
            "NameProperty",
            self.pal._pal_param["PassiveSkillList"]["array_type"],
        )

    def test_explicit_player_attribute_command_updates_read_model(self) -> None:
        response = self.client.post(
            f"/api/player/{self.player.PlayerUId}/commands",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 0,
                "command": "update_player_attributes",
                "values": {
                    "max_hp": 50,
                    "capture_power": 15,
                    "move_speed": 92,
                },
            },
        )

        self.assertEqual(200, response.status_code, response.get_json())
        payload = response.get_json()["data"]
        self.assertEqual(
            {"capture_power": 15, "max_hp": 50, "move_speed": 92},
            payload["value"]["updated"],
        )
        self.player.has_viewing_cage = lambda: False
        attributes = {
            row["key"]: row for row in player_to_dict(self.player)["PlayerAttributes"]
        }
        self.assertEqual(5500, attributes["max_hp"]["display_value"])
        self.assertEqual(15, attributes["capture_power"]["rank"])
        self.assertEqual(50.0, attributes["move_speed"]["effect_percent"])
        self.assertEqual(1, self.session.revision)

    def test_legacy_read_models_do_not_expose_raw_container_ids(self) -> None:
        self.player.has_viewing_cage = lambda: False
        player_payload = player_to_dict(self.player)
        pal_payload = _pal_data(self.pal)

        self.assertNotIn("OtomoCharacterContainerId", player_payload)
        self.assertNotIn("PalStorageContainerId", player_payload)
        self.assertNotIn("ContainerId", pal_payload)
        self.assertIn("SlotIndex", pal_payload)

    def test_boss_only_catalog_variant_uses_full_id_for_localization(self) -> None:
        original_i18n = Config.i18n
        try:
            Config.i18n = "zh-CN"
            PalObjects.set_BaseType(
                self.pal._pal_param["CharacterID"],
                "BOSS_KingWhale_otomo",
            )
            self.pal._pal_param.pop("NickName", None)
            self.pal._display_name_cache.clear()
            pal_payload = _pal_data(self.pal)
        finally:
            Config.i18n = original_i18n

        self.assertEqual("BOSS_KingWhale_otomo", pal_payload["CharacterID"])
        self.assertEqual("BOSS_KingWhale_otomo", pal_payload["DataAccessKey"])
        self.assertEqual("KingWhale", pal_payload["IconAccessKey"])
        self.assertEqual("奥沧鲸", pal_payload["I18nName"])
        self.assertEqual("👑奥沧鲸", pal_payload["DisplayName"])
        self.assertTrue(pal_payload["IsBOSS"])

        PalObjects.set_BaseType(self.pal._pal_param["CharacterID"], "BOSS_SheepBall")
        self.assertEqual("SheepBall", self.pal.DataAccessKey)

    def test_localized_species_name_is_not_exposed_as_custom_nickname(self) -> None:
        original_i18n = Config.i18n
        try:
            Config.i18n = "en"
            PalObjects.set_BaseType(
                self.pal._pal_param["CharacterID"],
                "BOSS_IceHorse",
            )
            self.pal.NickName = "唤冬兽"
            self.pal._display_name_cache.clear()
            pal_payload = _pal_data(self.pal)

            stored_default_nickname = self.pal.NickName
            self.pal.NickName = "Winter Guardian"
            self.pal._display_name_cache.clear()
            custom_payload = _pal_data(self.pal)
        finally:
            Config.i18n = original_i18n

        self.assertEqual("", pal_payload["NickName"])
        self.assertEqual("Frostallion", pal_payload["I18nName"])
        self.assertEqual("👑Frostallion", pal_payload["DisplayName"])
        self.assertEqual("唤冬兽", stored_default_nickname)
        self.assertEqual("Winter Guardian", custom_payload["NickName"])
        self.assertEqual(
            "👑Frostallion (Winter Guardian)",
            custom_payload["DisplayName"],
        )

    def test_initial_pal_list_includes_variant_flags(self) -> None:
        PalObjects.set_BaseType(
            self.pal._pal_param["CharacterID"],
            "BOSS_KingWhale_otomo",
        )
        self.pal._display_name_cache.clear()
        self.player.get_sorted_pals = lambda: [self.pal]
        SaveManager().player_mapping[self.player.PlayerUId] = self.player

        response = self.client.post(
            "/api/player/player_pals",
            headers=self.headers,
            json={"PlayerUId": self.player.PlayerUId},
        )

        self.assertEqual(200, response.status_code)
        pal_payload = response.get_json()["data"][0]
        self.assertTrue(pal_payload["IsBOSS"])
        self.assertFalse(pal_payload["IsRarePal"])
        self.assertFalse(pal_payload["IsTower"])
        self.assertEqual(10, pal_payload["Level"])
        self.assertEqual(self.pal.SlotIndex, pal_payload["SlotIndex"])

    def test_initial_pal_list_and_detail_include_awakening_state(self) -> None:
        self.pal._pal_param["bIsAwakening"] = PalObjects.BoolProperty(True)
        self.player.get_sorted_pals = lambda: [self.pal]
        SaveManager().player_mapping[self.player.PlayerUId] = self.player

        response = self.client.post(
            "/api/player/player_pals",
            headers=self.headers,
            json={"PlayerUId": self.player.PlayerUId},
        )

        self.assertEqual(200, response.status_code)
        self.assertTrue(response.get_json()["data"][0]["IsAwakened"])
        detail = _pal_data(self.pal)
        self.assertTrue(detail["IsAwakened"])
        self.assertEqual(1.5, detail["AwakeningStatusMultiplier"])

    def test_initial_pal_list_and_detail_include_expedition_reference_status(self) -> None:
        expedition_id = "44444444-5555-6666-7777-888888888888"
        self.pal._pal_param[
            "MapObjectConcreteInstanceIdAssignedToExpedition"
        ] = PalObjects.Guid(expedition_id)
        self.player.get_sorted_pals = lambda: [self.pal]
        SaveManager().player_mapping[self.player.PlayerUId] = self.player

        with patch.object(
            SaveManager,
            "expedition_assignment_status",
            return_value="valid",
        ):
            response = self.client.post(
                "/api/player/player_pals",
                headers=self.headers,
                json={"PlayerUId": self.player.PlayerUId},
            )
            detail = _pal_data(self.pal)

        self.assertEqual(200, response.status_code)
        summary = response.get_json()["data"][0]
        for payload in (summary, detail):
            self.assertTrue(payload["IsExpeditionPal"])
            self.assertEqual(expedition_id, payload["ExpeditionInstanceId"])
            self.assertEqual("valid", payload["ExpeditionAssignmentStatus"])

    def test_explicit_pal_command_unlocks_expedition_assignment(self) -> None:
        field = "MapObjectConcreteInstanceIdAssignedToExpedition"
        self.pal._pal_param[field] = PalObjects.Guid(
            "44444444-5555-6666-7777-888888888888"
        )

        response = self.client.post(
            f"/api/pal/{self.pal.InstanceId}/commands",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 0,
                "command": "unlock_pal_expedition",
            },
        )

        self.assertEqual(200, response.status_code)
        self.assertFalse(response.get_json()["data"]["value"]["expedition_locked"])
        self.assertFalse(self.pal.IsExpeditionPal)
        self.assertNotIn(field, self.pal._pal_param)
        self.assertEqual(1, self.session.revision)

    def test_npc_weapon_is_read_only_catalog_metadata(self) -> None:
        PalObjects.set_BaseType(
            self.pal._pal_param["CharacterID"], "SalesPerson_Wander"
        )
        self.pal._pal_param["OverrideWeaponType"] = PalObjects.EnumProperty(
            "EPalWeaponType", "EPalWeaponType::GatlingGun"
        )

        detail = _pal_data(self.pal)
        self.assertEqual("Handgun", detail["NpcDefaultWeapon"])
        self.assertNotIn("NpcWeaponOverride", detail)
        self.assertNotIn("NpcWeaponEffective", detail)
        self.assertNotIn("NpcWeaponTypes", detail)

        rejected = self.client.post(
            f"/api/pal/{self.pal.InstanceId}/commands",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 0,
                "command": "update_npc_weapon",
                "weapon": "Shotgun",
                "acknowledge_risk": True,
            },
        )
        self.assertEqual(400, rejected.status_code)
        self.assertEqual("UNSUPPORTED_COMMAND", rejected.get_json()["error"]["code"])
        self.assertEqual(0, self.session.revision)
        self.assertEqual(
            "EPalWeaponType::GatlingGun",
            PalObjects.get_EnumProperty(
                self.pal._pal_param["OverrideWeaponType"]
            ),
        )

    def test_explicit_pal_command_allows_cheat_condensation_level_254(self) -> None:
        response = self.client.post(
            f"/api/pal/{self.pal.InstanceId}/commands",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 0,
                "command": "update_pal_enhancement",
                "values": {"condensation": 254},
            },
        )

        self.assertEqual(200, response.status_code, response.get_json())
        self.assertEqual(254, response.get_json()["data"]["value"]["condensation"])
        self.assertEqual(254, self.pal.Rank)
        self.assertEqual(1, self.session.revision)

    def test_max_pal_command_applies_unrestricted_maximums_in_one_revision(self) -> None:
        response = self.client.post(
            f"/api/pal/{self.pal.InstanceId}/commands",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 0,
                "command": "max_pal",
                "unrestricted": True,
            },
        )

        self.assertEqual(200, response.status_code, response.get_json())
        payload = response.get_json()["data"]
        self.assertEqual(1, payload["revision"])
        self.assertEqual(100, payload["value"]["level"])
        self.assertEqual(10, payload["value"]["friendship_level"])
        self.assertEqual(255, payload["value"]["enhancements"]["iv_melee"])
        self.assertEqual(
            255, payload["value"]["enhancements"]["condensation"]
        )
        self.assertTrue(payload["value"]["enhancements"]["awakening"])
        self.assertEqual(1, self.session.revision)

    def test_max_pal_command_skips_non_applicable_npc_awakening(self) -> None:
        PalObjects.set_BaseType(
            self.pal._pal_param["CharacterID"], "SalesPerson_Wander"
        )
        self.pal._pal_param["bIsAwakening"] = PalObjects.IntProperty(1)

        response = self.client.post(
            f"/api/pal/{self.pal.InstanceId}/commands",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 0,
                "command": "max_pal",
            },
        )

        self.assertEqual(200, response.status_code, response.get_json())
        value = response.get_json()["data"]["value"]
        self.assertEqual(80, value["level"])
        self.assertEqual(10, value["friendship_level"])
        self.assertNotIn("awakening", value["enhancements"])
        self.assertIn("awakening", value["skipped_fields"])
        self.assertTrue(value["work_suitability"])
        self.assertEqual(
            {"value": 1, "id": None, "type": "IntProperty"},
            self.pal._pal_param["bIsAwakening"],
        )

    def test_explicit_pal_command_updates_awakening_as_a_boolean(self) -> None:
        response = self.client.post(
            f"/api/pal/{self.pal.InstanceId}/commands",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 0,
                "command": "update_pal_enhancement",
                "values": {"awakening": True},
            },
        )

        self.assertEqual(200, response.status_code, response.get_json())
        self.assertTrue(response.get_json()["data"]["value"]["awakening"])
        self.assertTrue(self.pal.IsAwakened)

        invalid = self.client.post(
            f"/api/pal/{self.pal.InstanceId}/commands",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 1,
                "command": "update_pal_enhancement",
                "values": {"awakening": "true"},
            },
        )
        self.assertEqual(400, invalid.status_code)
        self.assertEqual("INVALID_FIELD_TYPE", invalid.get_json()["error"]["code"])

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
