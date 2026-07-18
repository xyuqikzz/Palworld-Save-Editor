from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import unittest

from palworld_pal_editor.application.character_editor import CharacterEditor
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.config import Config
from palworld_pal_editor.core.pal_entity import PalEntity
from palworld_pal_editor.core.pal_objects import PalObjects, toUUID
from palworld_pal_editor.core.save_manager import SaveManager
from palworld_pal_editor.domain.commands import (
    UpdatePalEnhancement,
    UpdatePalIdentity,
    UpdatePalProgression,
    UpdatePalSkills,
    UpdatePlayerIdentity,
    UpdatePlayerProgression,
    UpdatePlayerTechnology,
)
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.utils.data_provider import DataProvider


class _Player:
    PlayerUId = "player-character"
    InstanceId = "instance-character"

    def __init__(self) -> None:
        self._player_param = {
            "NickName": PalObjects.StrProperty("Player One"),
            "Level": PalObjects.ByteProperty(10),
            "Exp": PalObjects.Int64Property(
                DataProvider.get_player_level_xp(10)
            ),
        }
        self._player_save_data = {
            "InventoryInfo": {"value": {}},
            "TechnologyPoint": PalObjects.IntProperty(3),
            "bossTechnologyPoint": PalObjects.IntProperty(1),
            "UnlockedRecipeTechnologyNames": PalObjects.ArrayProperty(
                "NameProperty", {"values": []}
            ),
        }

    @property
    def NickName(self):
        return PalObjects.get_BaseType(self._player_param.get("NickName"))

    @NickName.setter
    def NickName(self, value):
        PalObjects.set_BaseType(self._player_param["NickName"], value)

    @property
    def Level(self):
        return PalObjects.get_ByteProperty(self._player_param.get("Level"))

    @Level.setter
    def Level(self, value):
        PalObjects.set_ByteProperty(self._player_param["Level"], value)
        self.Exp = DataProvider.get_player_level_xp(value)

    @property
    def Exp(self):
        return PalObjects.get_BaseType(self._player_param.get("Exp"))

    @Exp.setter
    def Exp(self, value):
        PalObjects.set_BaseType(self._player_param["Exp"], value)

    @property
    def TechnologyPoint(self):
        return PalObjects.get_BaseType(
            self._player_save_data.get("TechnologyPoint")
        )

    @TechnologyPoint.setter
    def TechnologyPoint(self, value):
        PalObjects.set_BaseType(
            self._player_save_data["TechnologyPoint"], value
        )
        if value == 999:
            raise ValueError("synthetic setter failure")

    @property
    def bossTechnologyPoint(self):
        return PalObjects.get_BaseType(
            self._player_save_data.get("bossTechnologyPoint")
        )

    @bossTechnologyPoint.setter
    def bossTechnologyPoint(self, value):
        PalObjects.set_BaseType(
            self._player_save_data["bossTechnologyPoint"], value
        )

    @property
    def UnlockedRecipeTechnologyNames(self):
        return PalObjects.get_ArrayProperty(
            self._player_save_data.get("UnlockedRecipeTechnologyNames")
        )

    def toggle_UnlockedRecipeTechnologyNames(self, tech, status):
        values = self.UnlockedRecipeTechnologyNames
        if status and tech not in values:
            values.append(tech)
        if not status and tech in values:
            values.remove(tech)

    def unlock_all_techs(self):
        values = self.UnlockedRecipeTechnologyNames
        for tech in DataProvider.get_tech_data():
            if tech not in values:
                values.append(tech)


def make_pal() -> PalEntity:
    instance_id = toUUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    owner_id = toUUID("11111111-2222-3333-4444-555555555555")
    container_id = toUUID("22222222-3333-4444-5555-666666666666")
    group_id = toUUID("33333333-4444-5555-6666-777777777777")
    pal = PalEntity(
        PalObjects.PalSaveParameter(
            instance_id, owner_id, container_id, 0, group_id
        )
    )
    pal._pal_param["Level"] = PalObjects.ByteProperty(10)
    pal._pal_param["Exp"] = PalObjects.Int64Property(
        DataProvider.get_pal_level_xp(10)
    )
    pal._pal_param["FriendshipPoint"] = PalObjects.IntProperty(0)
    pal._pal_param["SanityValue"] = PalObjects.FloatProperty(80.0)
    return pal


class CharacterEditorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.player = _Player()
        self.pal = make_pal()
        singleton = SaveManager()
        self._had_singleton_players = hasattr(singleton, "player_mapping")
        self._singleton_players = getattr(singleton, "player_mapping", None)
        singleton.player_mapping = {
            str(self.pal.OwnerPlayerUId): SimpleNamespace(NickName="Owner")
        }
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
        self.editor = CharacterEditor(self.session)

    def tearDown(self) -> None:
        singleton = SaveManager()
        if self._had_singleton_players:
            singleton.player_mapping = self._singleton_players
        else:
            del singleton.player_mapping

    def test_player_identity_and_progression_are_explicit_changes(self) -> None:
        identity = self.editor.execute(
            UpdatePlayerIdentity(
                session_id=self.session.session_id,
                expected_revision=0,
                player_id=self.player.PlayerUId,
                name="新玩家",
            )
        )
        self.assertEqual("新玩家", identity["value"]["name"])

        result = self.editor.execute(
            UpdatePlayerProgression(
                session_id=self.session.session_id,
                expected_revision=1,
                player_id=self.player.PlayerUId,
                level=20,
                experience=123456,
                technology_points=100,
                boss_technology_points=10,
            )
        )
        self.assertEqual(20, result["value"]["level"])
        self.assertEqual(123456, result["value"]["experience"])
        self.assertEqual(100, result["value"]["technology_points"])
        changes = self.session.changes()
        self.assertEqual(2, len(changes))
        self.assertEqual(
            ["level:CharacterSaveParameterMap"],
            changes[0]["affected_records"],
        )
        self.assertEqual(
            {
                "level:CharacterSaveParameterMap",
                f"player_file:{self.player.PlayerUId}",
            },
            set(changes[1]["affected_records"]),
        )

    def test_player_setter_failure_rolls_back_all_fields(self) -> None:
        before_param = deepcopy(self.player._player_param)
        before_save = deepcopy(self.player._player_save_data)
        with self.assertRaises(DomainError) as raised:
            self.editor.execute(
                UpdatePlayerProgression(
                    session_id=self.session.session_id,
                    expected_revision=0,
                    player_id=self.player.PlayerUId,
                    level=30,
                    technology_points=999,
                )
            )
        self.assertEqual("COMMAND_EXECUTION_FAILED", raised.exception.code)
        self.assertEqual(before_param, self.player._player_param)
        self.assertEqual(before_save, self.player._player_save_data)
        self.assertEqual(0, self.session.revision)
        self.assertEqual([], self.session.changes())

    def test_player_boundaries_and_unknown_technology_do_not_mutate(self) -> None:
        before = deepcopy(self.player._player_param)
        commands = (
            UpdatePlayerIdentity(
                session_id=self.session.session_id,
                expected_revision=0,
                player_id=self.player.PlayerUId,
                name="x" * 25,
            ),
            UpdatePlayerProgression(
                session_id=self.session.session_id,
                expected_revision=0,
                player_id=self.player.PlayerUId,
                level=101,
            ),
            UpdatePlayerTechnology(
                session_id=self.session.session_id,
                expected_revision=0,
                player_id=self.player.PlayerUId,
                recipe_id="MissingTechnology",
                unlocked=True,
            ),
        )
        for command in commands:
            with self.subTest(command=type(command).__name__):
                with self.assertRaises(DomainError):
                    self.editor.execute(command)
                self.assertEqual(0, self.session.revision)
        self.assertEqual(before, self.player._player_param)

    def test_player_technology_is_atomic_and_validated(self) -> None:
        result = self.editor.execute(
            UpdatePlayerTechnology(
                session_id=self.session.session_id,
                expected_revision=0,
                player_id=self.player.PlayerUId,
                recipe_id="DisplayCharacter",
                unlocked=True,
            )
        )
        self.assertIn("DisplayCharacter", result["value"]["unlocked"])
        self.assertEqual(1, self.session.revision)

    def test_pal_identity_uses_public_gender_and_rejects_unknown_variant(self) -> None:
        result = self.editor.execute(
            UpdatePalIdentity(
                session_id=self.session.session_id,
                expected_revision=0,
                pal_id=str(self.pal.InstanceId),
                name="棉花",
                gender="male",
            )
        )
        self.assertEqual("棉花", result["value"]["name"])
        self.assertEqual("male", result["value"]["gender"])
        before = deepcopy(self.pal._pal_param)
        with self.assertRaises(DomainError) as raised:
            self.editor.execute(
                UpdatePalIdentity(
                    session_id=self.session.session_id,
                    expected_revision=1,
                    pal_id=str(self.pal.InstanceId),
                    variant="MissingPalVariant",
                )
            )
        self.assertEqual("INVALID_VARIANT", raised.exception.code)
        self.assertEqual(before, self.pal._pal_param)
        self.assertEqual(1, self.session.revision)

    def test_pal_skills_replace_as_one_validated_set(self) -> None:
        active = ("EPalWazaID::AquaJet", "EPalWazaID::WaterGun")
        mastered = active + ("EPalWazaID::BubbleShot",)
        passive = ("Rare", "Legend")
        result = self.editor.execute(
            UpdatePalSkills(
                session_id=self.session.session_id,
                expected_revision=0,
                pal_id=str(self.pal.InstanceId),
                active=active,
                mastered=mastered,
                passive=passive,
            )
        )
        self.assertEqual(list(active), result["value"]["active"])
        self.assertEqual(list(mastered), result["value"]["mastered"])
        self.assertEqual(list(passive), result["value"]["passive"])

    def test_invalid_skill_sets_leave_all_lists_unchanged(self) -> None:
        before = deepcopy(self.pal._pal_param)
        commands = (
            UpdatePalSkills(
                session_id=self.session.session_id,
                expected_revision=0,
                pal_id=str(self.pal.InstanceId),
                passive=("Rare", "Rare"),
            ),
            UpdatePalSkills(
                session_id=self.session.session_id,
                expected_revision=0,
                pal_id=str(self.pal.InstanceId),
                active=("MissingSkill",),
                mastered=("MissingSkill",),
            ),
            UpdatePalSkills(
                session_id=self.session.session_id,
                expected_revision=0,
                pal_id=str(self.pal.InstanceId),
                active=("EPalWazaID::AquaJet",),
                mastered=(),
            ),
        )
        expected_codes = (
            "DUPLICATE_SKILL",
            "UNKNOWN_SKILL",
            "ACTIVE_SKILL_NOT_MASTERED",
        )
        for command, code in zip(commands, expected_codes):
            with self.subTest(code=code):
                with self.assertRaises(DomainError) as raised:
                    self.editor.execute(command)
                self.assertEqual(code, raised.exception.code)
                self.assertEqual(before, self.pal._pal_param)
                self.assertEqual(0, self.session.revision)

    def test_skill_cleanup_preserves_unmodified_legacy_entries(self) -> None:
        self.pal._pal_param["PassiveSkillList"] = PalObjects.ArrayProperty(
            "NameProperty", {"values": ["UnknownPassive", "Rare"]}
        )
        self.pal._pal_param["EquipWaza"] = PalObjects.ArrayProperty(
            "EnumProperty",
            {"values": ["EPalWazaID::AquaJet", "EPalWazaID::WaterGun"]},
        )
        self.pal._pal_param["MasteredWaza"] = PalObjects.ArrayProperty(
            "EnumProperty", {"values": []}
        )

        self.editor.execute(
            UpdatePalSkills(
                session_id=self.session.session_id,
                expected_revision=0,
                pal_id=str(self.pal.InstanceId),
                passive=("UnknownPassive",),
            )
        )
        result = self.editor.execute(
            UpdatePalSkills(
                session_id=self.session.session_id,
                expected_revision=1,
                pal_id=str(self.pal.InstanceId),
                active=("EPalWazaID::WaterGun",),
                mastered=(),
            )
        )

        self.assertEqual(["UnknownPassive"], result["value"]["passive"])
        self.assertEqual(["EPalWazaID::WaterGun"], result["value"]["active"])

    def test_pal_enhancement_updates_derived_fields_atomically(self) -> None:
        work_type = "EPalWorkSuitability::Handcraft"
        result = self.editor.execute(
            UpdatePalEnhancement(
                session_id=self.session.session_id,
                expected_revision=0,
                pal_id=str(self.pal.InstanceId),
                values={
                    "iv_hp": 80,
                    "iv_shot": 70,
                    "soul_hp": 10,
                    "soul_attack": 5,
                    "condensation": 3,
                },
                work_suitability={work_type: 3},
            )
        )
        self.assertEqual(80, result["value"]["iv_hp"])
        self.assertEqual(10, result["value"]["soul_hp"])
        self.assertEqual(3, result["value"]["condensation"])
        self.assertEqual(3, result["value"]["work_suitability"][work_type])
        self.assertIsNotNone(result["value"]["derived"]["max_health"])

    def test_condensed_pal_work_suitability_reaches_level_ten(self) -> None:
        work_type = "EPalWorkSuitability::Handcraft"
        self.pal.Rank = 5
        result = self.editor.execute(
            UpdatePalEnhancement(
                session_id=self.session.session_id,
                expected_revision=0,
                pal_id=str(self.pal.InstanceId),
                work_suitability={work_type: 10},
            )
        )
        self.assertEqual(10, result["value"]["work_suitability"][work_type])

        with self.assertRaises(DomainError) as raised:
            self.editor.execute(
                UpdatePalEnhancement(
                    session_id=self.session.session_id,
                    expected_revision=1,
                    pal_id=str(self.pal.InstanceId),
                    work_suitability={work_type: 11},
                )
            )
        self.assertEqual("VALUE_OUT_OF_RANGE", raised.exception.code)
        self.assertEqual(10, raised.exception.details["maximum"])

    def test_pal_enhancement_allows_cheat_byte_maximum(self) -> None:
        self.assertLess(Config.max_souls_level, 255)
        result = self.editor.execute(
            UpdatePalEnhancement(
                session_id=self.session.session_id,
                expected_revision=0,
                pal_id=str(self.pal.InstanceId),
                values={"iv_hp": 255, "soul_hp": 255},
            )
        )
        self.assertEqual(255, result["value"]["iv_hp"])
        self.assertEqual(255, result["value"]["soul_hp"])

        with self.assertRaises(DomainError) as raised:
            self.editor.execute(
                UpdatePalEnhancement(
                    session_id=self.session.session_id,
                    expected_revision=1,
                    pal_id=str(self.pal.InstanceId),
                    values={"iv_hp": 256},
                )
            )
        self.assertEqual("VALUE_OUT_OF_RANGE", raised.exception.code)
        self.assertEqual(255, raised.exception.details["maximum"])

    def test_pal_progression_heals_then_applies_explicit_health_and_satiety(self) -> None:
        self.pal._pal_param["WorkerSick"] = PalObjects.EnumProperty(
            "EPalBaseCampWorkerSickType",
            "EPalBaseCampWorkerSickType::DepressionSprain",
        )
        self.pal._pal_param["PhysicalHealth"] = PalObjects.EnumProperty(
            "EPalStatusPhysicalHealthType",
            "EPalStatusPhysicalHealthType::Dying",
        )
        self.pal._pal_param["PalReviveTimer"] = PalObjects.FloatProperty(10.0)
        self.pal._pal_param["HungerType"] = PalObjects.EnumProperty(
            "EPalHungerType", "EPalHungerType::Starvation"
        )
        result = self.editor.execute(
            UpdatePalProgression(
                session_id=self.session.session_id,
                expected_revision=0,
                pal_id=str(self.pal.InstanceId),
                values={
                    "friendship_level": 5,
                    "heal": True,
                    "health": 100,
                    "satiety": 75.0,
                },
            )
        )
        self.assertEqual(5, result["value"]["friendship_level"])
        self.assertEqual(100, result["value"]["health"])
        self.assertEqual(75.0, result["value"]["satiety"])
        self.assertFalse(result["value"]["worker_sick"])
        self.assertFalse(result["value"]["fainted"])
        self.assertIsNone(result["value"]["hunger_status"])

    def test_pal_progression_validates_health_against_requested_level(self) -> None:
        proposed = PalEntity(deepcopy(self.pal._pal_obj))
        proposed.Level = 40
        requested_health = proposed.ComputedMaxHP
        self.assertGreater(requested_health, self.pal.ComputedMaxHP)

        result = self.editor.execute(
            UpdatePalProgression(
                session_id=self.session.session_id,
                expected_revision=0,
                pal_id=str(self.pal.InstanceId),
                values={"level": 40, "health": requested_health},
            )
        )

        self.assertEqual(40, result["value"]["level"])
        self.assertEqual(requested_health, result["value"]["health"])

    def test_pal_progression_preserves_real_health_above_approximate_derived_max(self) -> None:
        requested_health = self.pal.ComputedMaxHP + 1

        result = self.editor.execute(
            UpdatePalProgression(
                session_id=self.session.session_id,
                expected_revision=0,
                pal_id=str(self.pal.InstanceId),
                values={"health": requested_health},
            )
        )

        self.assertEqual(requested_health, result["value"]["health"])

    def test_unknown_progression_and_enhancement_fields_are_rejected(self) -> None:
        before = deepcopy(self.pal._pal_param)
        commands = (
            UpdatePalProgression(
                session_id=self.session.session_id,
                expected_revision=0,
                pal_id=str(self.pal.InstanceId),
                values={"_pal_param": {}},
            ),
            UpdatePalEnhancement(
                session_id=self.session.session_id,
                expected_revision=0,
                pal_id=str(self.pal.InstanceId),
                values={"Rank_HP": 20},
            ),
        )
        for command in commands:
            with self.assertRaises(DomainError) as raised:
                self.editor.execute(command)
            self.assertEqual(
                "UNSUPPORTED_COMMAND_FIELD", raised.exception.code
            )
            self.assertEqual(before, self.pal._pal_param)
            self.assertEqual(0, self.session.revision)


if __name__ == "__main__":
    unittest.main()
