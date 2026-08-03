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
    HealAllPals,
    MaxPal,
    UnlockAllExpeditionPals,
    UnlockPalExpedition,
    UpdatePalEnhancement,
    UpdatePalIdentity,
    UpdatePalProgression,
    UpdatePalSkills,
    UpdatePlayerIdentity,
    UpdatePlayerAttributes,
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

    def status_point(self, name):
        for status in PalObjects.get_ArrayProperty(
            self._player_param.get("GotStatusPointList")
        ) or ():
            if PalObjects.get_BaseType(status.get("StatusName")) == name:
                return PalObjects.get_BaseType(status.get("StatusPoint"))
        return None

    def set_status_point(self, name, value):
        statuses = PalObjects.get_ArrayProperty(
            self._player_param.get("GotStatusPointList")
        )
        if statuses is None:
            if value == 0:
                return
            self._player_param["GotStatusPointList"] = PalObjects.GotStatusPointList()
            statuses = PalObjects.get_ArrayProperty(
                self._player_param["GotStatusPointList"]
            )
            statuses.clear()
        for status in statuses:
            if PalObjects.get_BaseType(status.get("StatusName")) == name:
                PalObjects.set_BaseType(status["StatusPoint"], value)
                return
        if value > 0:
            statuses.append(PalObjects.StatusPointStruct(name, value))

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


def make_pal(
    instance_id: str = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    owner_id: str = "11111111-2222-3333-4444-555555555555",
) -> PalEntity:
    instance_id = toUUID(instance_id)
    owner_id = toUUID(owner_id)
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

    def test_unlock_pal_expedition_removes_only_the_assignment(self) -> None:
        expedition_id = "44444444-5555-6666-7777-888888888888"
        field = "MapObjectConcreteInstanceIdAssignedToExpedition"
        self.pal._pal_param[field] = PalObjects.Guid(expedition_id)

        self.assertEqual(expedition_id, str(self.pal.ExpeditionInstanceId))
        self.assertTrue(self.pal.IsExpeditionPal)
        level_before = deepcopy(self.pal._pal_param["Level"])

        result = self.editor.execute(
            UnlockPalExpedition(
                session_id=self.session.session_id,
                expected_revision=0,
                pal_id=str(self.pal.InstanceId),
            )
        )

        self.assertFalse(self.pal.IsExpeditionPal)
        self.assertIsNone(self.pal.ExpeditionInstanceId)
        self.assertNotIn(field, self.pal._pal_param)
        self.assertEqual(level_before, self.pal._pal_param["Level"])
        self.assertEqual(
            {"pal_id": str(self.pal.InstanceId), "expedition_locked": False},
            result["value"],
        )
        self.assertEqual(1, self.session.revision)

    def test_unlock_valid_pal_removes_reverse_expedition_membership(self) -> None:
        expedition_id = "44444444-5555-6666-7777-888888888888"
        pal_id = str(self.pal.InstanceId)
        field = "MapObjectConcreteInstanceIdAssignedToExpedition"
        self.pal._pal_param[field] = PalObjects.Guid(expedition_id)
        reverse_members = {pal_id.lower()}
        manager = self.session.manager
        manager.expedition_has_member = lambda candidate_expedition_id, candidate_pal_id: (
            str(candidate_expedition_id).lower() == expedition_id
            and str(candidate_pal_id).lower() in reverse_members
        )
        manager.snapshot_expedition_data = lambda: set(reverse_members)

        def restore_expedition_data(snapshot) -> None:
            reverse_members.clear()
            reverse_members.update(snapshot)

        def remove_expedition_members(pal_ids) -> dict[str, list[str]]:
            removed = sorted(
                str(candidate).lower()
                for candidate in pal_ids
                if str(candidate).lower() in reverse_members
            )
            reverse_members.difference_update(removed)
            return {expedition_id: removed} if removed else {}

        manager.restore_expedition_data = restore_expedition_data
        manager.remove_expedition_members = remove_expedition_members

        result = self.editor.execute(
            UnlockPalExpedition(
                session_id=self.session.session_id,
                expected_revision=0,
                pal_id=pal_id,
            )
        )

        self.assertEqual(set(), reverse_members)
        self.assertFalse(self.pal.IsExpeditionPal)
        self.assertIn(
            "level:MapObjectSaveData",
            self.session.changes()[0]["affected_records"],
        )

    def test_unlock_all_expedition_pals_removes_reverse_members_once(self) -> None:
        expedition_id = "44444444-5555-6666-7777-888888888888"
        second_pal = make_pal("bbbbbbbb-cccc-dddd-eeee-ffffffffffff")
        pals = (self.pal, second_pal)
        for pal in pals:
            pal._pal_param[
                "MapObjectConcreteInstanceIdAssignedToExpedition"
            ] = PalObjects.Guid(expedition_id)
        manager = self.session.manager
        manager.player_mapping = {
            "owner": SimpleNamespace(
                _palbox={str(pal.InstanceId): pal for pal in pals}
            )
        }
        manager.baseworker_mapping = {}
        manager._dangling_pals = {}
        reverse_members = {str(pal.InstanceId).lower() for pal in pals}
        manager.expedition_has_member = lambda candidate_expedition_id, candidate_pal_id: (
            str(candidate_expedition_id).lower() == expedition_id
            and str(candidate_pal_id).lower() in reverse_members
        )
        manager.snapshot_expedition_data = lambda: set(reverse_members)

        def restore_expedition_data(snapshot) -> None:
            reverse_members.clear()
            reverse_members.update(snapshot)

        remove_calls = []

        def remove_expedition_members(pal_ids) -> dict[str, list[str]]:
            remove_calls.append(sorted(str(value).lower() for value in pal_ids))
            removed = sorted(reverse_members.intersection(remove_calls[-1]))
            reverse_members.difference_update(removed)
            return {expedition_id: removed}

        manager.restore_expedition_data = restore_expedition_data
        manager.remove_expedition_members = remove_expedition_members

        result = self.editor.execute(
            UnlockAllExpeditionPals(
                session_id=self.session.session_id,
                expected_revision=0,
            )
        )

        self.assertEqual(2, result["value"]["unlocked_count"])
        self.assertEqual(2, result["value"]["reverse_member_count"])
        self.assertEqual(1, len(remove_calls))
        self.assertEqual(set(), reverse_members)
        self.assertEqual(1, self.session.revision)
        self.assertTrue(all(not pal.IsExpeditionPal for pal in pals))
        self.assertEqual(
            [
                "level:CharacterSaveParameterMap",
                "level:MapObjectSaveData",
            ],
            self.session.changes()[0]["affected_records"],
        )

    def test_unlock_pal_expedition_rejects_an_unassigned_pal(self) -> None:
        with self.assertRaises(DomainError) as raised:
            self.editor.execute(
                UnlockPalExpedition(
                    session_id=self.session.session_id,
                    expected_revision=0,
                    pal_id=str(self.pal.InstanceId),
                )
            )

        self.assertEqual("PAL_NOT_EXPEDITION_ASSIGNED", raised.exception.code)
        self.assertEqual(0, self.session.revision)

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

    def test_player_attributes_update_existing_and_new_status_rows(self) -> None:
        self.player._player_param["GotStatusPointList"] = PalObjects.GotStatusPointList()
        result = self.editor.execute(
            UpdatePlayerAttributes(
                session_id=self.session.session_id,
                expected_revision=0,
                player_id=self.player.PlayerUId,
                values={"max_hp": 50, "swim_speed": 20, "move_speed": 92},
            )
        )

        self.assertEqual(
            {"max_hp": 50, "move_speed": 92, "swim_speed": 20},
            result["value"]["updated"],
        )
        views = {row["key"]: row for row in result["value"]["attributes"]}
        self.assertEqual(5500, views["max_hp"]["display_value"])
        self.assertEqual(100.0, views["swim_speed"]["effect_percent"])
        self.assertEqual(50.0, views["move_speed"]["effect_percent"])
        self.assertEqual(1, self.session.revision)
        self.assertEqual(
            ["level:CharacterSaveParameterMap"],
            self.session.changes()[0]["affected_records"],
        )

    def test_player_attribute_range_error_does_not_mutate(self) -> None:
        before = deepcopy(self.player._player_param)
        with self.assertRaises(DomainError) as raised:
            self.editor.execute(
                UpdatePlayerAttributes(
                    session_id=self.session.session_id,
                    expected_revision=0,
                    player_id=self.player.PlayerUId,
                    values={"move_speed": 93},
                )
            )

        self.assertEqual("VALUE_OUT_OF_RANGE", raised.exception.code)
        self.assertEqual(before, self.player._player_param)
        self.assertEqual(0, self.session.revision)

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

    def test_unrestricted_passives_allow_more_than_four_and_duplicates(self) -> None:
        passive = ("Rare", "Rare", "Legend", "Rare", "Legend")

        result = self.editor.execute(
            UpdatePalSkills(
                session_id=self.session.session_id,
                expected_revision=0,
                pal_id=str(self.pal.InstanceId),
                passive=passive,
                unrestricted=True,
            )
        )

        self.assertEqual(list(passive), result["value"]["passive"])
        self.assertEqual(list(passive), self.pal.PassiveSkillList)
        self.assertEqual(1, self.session.revision)

    def test_unrestricted_passive_flag_must_be_boolean(self) -> None:
        with self.assertRaises(DomainError) as raised:
            self.editor.execute(
                UpdatePalSkills(
                    session_id=self.session.session_id,
                    expected_revision=0,
                    pal_id=str(self.pal.InstanceId),
                    passive=("Rare",),
                    unrestricted="true",
                )
            )

        self.assertEqual("INVALID_FIELD_TYPE", raised.exception.code)
        self.assertEqual(0, self.session.revision)

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

    def test_unrelated_pal_edit_preserves_existing_unknown_passive(self) -> None:
        unknown = "OtherMod_ExistingPassive_Exact"
        self.pal._pal_param["PassiveSkillList"] = PalObjects.ArrayProperty(
            "NameProperty", {"values": [unknown, "Rare"]}
        )

        self.editor.execute(
            UpdatePalProgression(
                session_id=self.session.session_id,
                expected_revision=0,
                pal_id=str(self.pal.InstanceId),
                values={"level": 11},
            )
        )

        self.assertEqual([unknown, "Rare"], self.pal.PassiveSkillList)

    def test_existing_unknown_passive_can_be_deleted_without_custom_flag(
        self,
    ) -> None:
        unknown = "OtherMod_ExistingPassive_Exact"
        self.pal._pal_param["PassiveSkillList"] = PalObjects.ArrayProperty(
            "NameProperty", {"values": [unknown, "Rare"]}
        )

        result = self.editor.execute(
            UpdatePalSkills(
                session_id=self.session.session_id,
                expected_revision=0,
                pal_id=str(self.pal.InstanceId),
                passive=("Rare",),
            )
        )

        self.assertEqual(["Rare"], result["value"]["passive"])
        self.assertEqual(["Rare"], self.pal.PassiveSkillList)

    def test_unknown_passive_requires_explicit_custom_flag(self) -> None:
        custom = "OtherMod_NewPassive_Exact"

        with self.assertRaises(DomainError) as raised:
            self.editor.execute(
                UpdatePalSkills(
                    session_id=self.session.session_id,
                    expected_revision=0,
                    pal_id=str(self.pal.InstanceId),
                    passive=(custom,),
                )
            )

        self.assertEqual("UNKNOWN_SKILL", raised.exception.code)
        self.assertEqual(0, self.session.revision)
        self.assertNotIn(custom, self.pal.PassiveSkillList or [])

        result = self.editor.execute(
            UpdatePalSkills(
                session_id=self.session.session_id,
                expected_revision=0,
                pal_id=str(self.pal.InstanceId),
                passive=(custom,),
                allow_custom_passive=True,
            )
        )

        self.assertEqual([custom], result["value"]["passive"])
        self.assertEqual([custom], self.pal.PassiveSkillList)
        self.assertEqual(
            "NameProperty",
            self.pal._pal_param["PassiveSkillList"]["array_type"],
        )

    def test_custom_passive_validation_rejects_unsafe_values_atomically(
        self,
    ) -> None:
        before = deepcopy(self.pal._pal_param)
        invalid = (
            ((123,), "INVALID_FIELD_TYPE"),
            (("",), "INVALID_CUSTOM_PASSIVE_ID"),
            (("x" * 129,), "INVALID_CUSTOM_PASSIVE_ID"),
            (("OtherMod_\nPassive",), "INVALID_CUSTOM_PASSIVE_ID"),
            (
                ("OtherMod_Duplicate", "OtherMod_Duplicate"),
                "DUPLICATE_SKILL",
            ),
            (
                (
                    "OtherMod_One",
                    "OtherMod_Two",
                    "OtherMod_Three",
                    "OtherMod_Four",
                    "OtherMod_Five",
                ),
                "SKILL_SLOT_LIMIT_EXCEEDED",
            ),
        )

        for passive, expected_code in invalid:
            with self.subTest(expected_code=expected_code, passive=passive):
                with self.assertRaises(DomainError) as raised:
                    self.editor.execute(
                        UpdatePalSkills(
                            session_id=self.session.session_id,
                            expected_revision=0,
                            pal_id=str(self.pal.InstanceId),
                            passive=passive,
                            allow_custom_passive=True,
                        )
                    )
                self.assertEqual(expected_code, raised.exception.code)
                self.assertEqual(before, self.pal._pal_param)
                self.assertEqual(0, self.session.revision)

    def test_custom_passive_flag_must_be_boolean_and_apply_to_passives(
        self,
    ) -> None:
        with self.assertRaises(DomainError) as invalid_type:
            self.editor.execute(
                UpdatePalSkills(
                    session_id=self.session.session_id,
                    expected_revision=0,
                    pal_id=str(self.pal.InstanceId),
                    passive=("OtherMod_NewPassive_Exact",),
                    allow_custom_passive="true",
                )
            )
        self.assertEqual("INVALID_FIELD_TYPE", invalid_type.exception.code)

        with self.assertRaises(DomainError) as missing_passive:
            self.editor.execute(
                UpdatePalSkills(
                    session_id=self.session.session_id,
                    expected_revision=0,
                    pal_id=str(self.pal.InstanceId),
                    active=(),
                    mastered=(),
                    allow_custom_passive=True,
                )
            )
        self.assertEqual(
            "INVALID_CUSTOM_PASSIVE_REQUEST",
            missing_passive.exception.code,
        )

        with self.assertRaises(DomainError) as active_skill:
            self.editor.execute(
                UpdatePalSkills(
                    session_id=self.session.session_id,
                    expected_revision=0,
                    pal_id=str(self.pal.InstanceId),
                    active=("OtherMod_ActiveSkill",),
                    mastered=("OtherMod_ActiveSkill",),
                    passive=("OtherMod_NewPassive_Exact",),
                    allow_custom_passive=True,
                )
            )
        self.assertEqual("UNKNOWN_SKILL", active_skill.exception.code)
        self.assertEqual(0, self.session.revision)

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

    def test_pal_awakening_round_trips_and_updates_estimated_combat_stats(self) -> None:
        self.pal.Talent_HP = 100
        self.pal.Talent_Shot = 100
        self.pal.Talent_Defense = 100
        unawakened = {
            "hp": self.pal.ComputedMaxHP,
            "attack": self.pal.ComputedAttack,
            "defense": self.pal.ComputedDefense,
        }

        awakened = self.editor.execute(
            UpdatePalEnhancement(
                session_id=self.session.session_id,
                expected_revision=0,
                pal_id=str(self.pal.InstanceId),
                values={"awakening": True},
            )
        )["value"]

        self.assertTrue(awakened["awakening"])
        self.assertEqual(1.5, awakened["awakening_status_multiplier"])
        self.assertEqual(
            {"value": True, "id": None, "type": "BoolProperty"},
            self.pal._pal_param["bIsAwakening"],
        )
        self.assertGreater(awakened["derived"]["max_health"], unawakened["hp"])
        self.assertGreater(awakened["derived"]["attack"], unawakened["attack"])
        self.assertGreater(awakened["derived"]["defense"], unawakened["defense"])

        restored = self.editor.execute(
            UpdatePalEnhancement(
                session_id=self.session.session_id,
                expected_revision=1,
                pal_id=str(self.pal.InstanceId),
                values={"awakening": False},
            )
        )["value"]
        self.assertFalse(restored["awakening"])
        self.assertNotIn("bIsAwakening", self.pal._pal_param)
        self.assertEqual(unawakened["hp"], restored["derived"]["max_health"])
        self.assertEqual(unawakened["attack"], restored["derived"]["attack"])
        self.assertEqual(unawakened["defense"], restored["derived"]["defense"])

    def test_pal_awakening_rejects_unknown_property_structure(self) -> None:
        self.pal._pal_param["bIsAwakening"] = PalObjects.IntProperty(1)
        before = deepcopy(self.pal._pal_param)

        with self.assertRaises(DomainError) as raised:
            self.editor.execute(
                UpdatePalEnhancement(
                    session_id=self.session.session_id,
                    expected_revision=0,
                    pal_id=str(self.pal.InstanceId),
                    values={"awakening": True},
                )
            )

        self.assertEqual("COMPATIBILITY_FIELD_MISSING", raised.exception.code)
        self.assertEqual(before, self.pal._pal_param)
        self.assertEqual(0, self.session.revision)

    def test_max_pal_sets_every_applicable_regular_field_atomically(self) -> None:
        result = self.editor.execute(
            MaxPal(
                session_id=self.session.session_id,
                expected_revision=0,
                pal_id=str(self.pal.InstanceId),
            )
        )["value"]

        self.assertEqual(80, result["level"])
        self.assertEqual(10, result["friendship_level"])
        self.assertEqual(
            {
                "iv_hp": 100,
                "iv_shot": 100,
                "iv_defense": 100,
                "soul_hp": Config.max_souls_level,
                "soul_attack": Config.max_souls_level,
                "soul_defense": Config.max_souls_level,
                "soul_craft_speed": Config.max_souls_level,
                "condensation": 5,
                "awakening": True,
            },
            result["enhancements"],
        )
        self.assertTrue(result["work_suitability"])
        self.assertTrue(
            all(
                level == Config.max_suitability_level
                for level in result["work_suitability"].values()
            )
        )
        self.assertEqual(["iv_melee"], result["skipped_fields"])
        self.assertEqual(1, self.session.revision)
        self.assertEqual(1, len(self.session.changes()))
        self.assertEqual("MaxPal", self.session.changes()[0]["command"])

    def test_max_npc_skips_awakening_but_maxes_supported_fields(self) -> None:
        PalObjects.set_BaseType(
            self.pal._pal_param["CharacterID"], "SalesPerson_Wander"
        )
        unsupported_awakening = PalObjects.IntProperty(1)
        self.pal._pal_param["bIsAwakening"] = deepcopy(unsupported_awakening)

        result = self.editor.execute(
            MaxPal(
                session_id=self.session.session_id,
                expected_revision=0,
                pal_id=str(self.pal.InstanceId),
            )
        )["value"]

        self.assertTrue(self.pal.IsHuman)
        self.assertEqual(80, result["level"])
        self.assertEqual(10, result["friendship_level"])
        self.assertNotIn("awakening", result["enhancements"])
        self.assertEqual(
            ["iv_melee", "awakening"], result["skipped_fields"]
        )
        self.assertEqual(
            unsupported_awakening,
            self.pal._pal_param["bIsAwakening"],
        )
        self.assertTrue(result["work_suitability"])
        self.assertTrue(
            all(
                level == Config.max_suitability_level
                for level in result["work_suitability"].values()
            )
        )
        self.assertEqual(Config.max_souls_level, self.pal.Rank_CraftSpeed)
        self.assertEqual(5, self.pal.Rank)

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

    def test_pal_progression_heal_restores_supported_status_maximums(self) -> None:
        self.pal.Hp = 1
        self.pal.FullStomach = 1.0
        self.pal.SanityValue = 1.0
        expected_health = self.pal.ComputedMaxHP
        expected_satiety = DataProvider.get_pal_stats(
            self.pal.DataAccessKey, "FOOD"
        )

        result = self.editor.execute(
            UpdatePalProgression(
                session_id=self.session.session_id,
                expected_revision=0,
                pal_id=str(self.pal.InstanceId),
                values={"heal": True},
            )
        )

        self.assertIsNotNone(expected_health)
        self.assertIsNotNone(expected_satiety)
        self.assertEqual(expected_health, result["value"]["health"])
        self.assertEqual(expected_satiety, result["value"]["satiety"])
        self.assertEqual(100.0, result["value"]["sanity"])

    def test_pal_progression_heal_preserves_values_above_supported_maximums(self) -> None:
        maximum_health = self.pal.ComputedMaxHP
        maximum_satiety = DataProvider.get_pal_stats(
            self.pal.DataAccessKey, "FOOD"
        )
        self.pal.Hp = maximum_health + 1
        self.pal.FullStomach = maximum_satiety + 1.0

        result = self.editor.execute(
            UpdatePalProgression(
                session_id=self.session.session_id,
                expected_revision=0,
                pal_id=str(self.pal.InstanceId),
                values={"heal": True},
            )
        )

        self.assertEqual(maximum_health + 1, result["value"]["health"])
        self.assertEqual(maximum_satiety + 1.0, result["value"]["satiety"])
        self.assertEqual(100.0, result["value"]["sanity"])

    def test_heal_all_pals_covers_player_base_and_detached_records_atomically(self) -> None:
        base_pal = make_pal("bbbbbbbb-cccc-dddd-eeee-ffffffffffff")
        detached_pal = make_pal("cccccccc-dddd-eeee-ffff-aaaaaaaaaaaa")
        pals = (self.pal, base_pal, detached_pal)
        for pal in pals:
            pal.Hp = 1
            pal.FullStomach = 1.0
            pal.SanityValue = 1.0
            pal._pal_param["WorkerSick"] = PalObjects.EnumProperty(
                "EPalBaseCampWorkerSickType",
                "EPalBaseCampWorkerSickType::DepressionSprain",
            )
            pal._pal_param["PalReviveTimer"] = PalObjects.FloatProperty(10.0)

        manager = self.session.manager
        manager.player_mapping = {
            "owner": SimpleNamespace(
                _palbox={str(self.pal.InstanceId): self.pal}
            )
        }
        manager.baseworker_mapping = {
            str(base_pal.InstanceId): base_pal
        }
        manager._dangling_pals = {
            str(detached_pal.InstanceId): detached_pal
        }

        result = self.editor.execute(
            HealAllPals(
                session_id=self.session.session_id,
                expected_revision=0,
            )
        )

        self.assertEqual(3, result["value"]["healed_count"])
        self.assertEqual(3, result["value"]["condition"]["fully_healed"])
        self.assertEqual(1, self.session.revision)
        for pal in pals:
            self.assertEqual(pal.ComputedMaxHP, pal.Hp)
            self.assertEqual(
                DataProvider.get_pal_stats(pal.DataAccessKey, "FOOD"),
                pal.FullStomach,
            )
            self.assertEqual(100.0, pal.SanityValue)
            self.assertFalse(pal.HasWorkerSick)
            self.assertFalse(pal.IsFaintedPal)

    def test_heal_all_pals_rolls_back_every_record_on_failure(self) -> None:
        failing_pal = make_pal("dddddddd-eeee-ffff-aaaa-bbbbbbbbbbbb")
        self.pal.Hp = 1
        failing_pal.Hp = 2
        before = {
            str(self.pal.InstanceId): deepcopy(self.pal._pal_param),
            str(failing_pal.InstanceId): deepcopy(failing_pal._pal_param),
        }
        manager = self.session.manager
        manager.player_mapping = {
            "owner": SimpleNamespace(
                _palbox={str(self.pal.InstanceId): self.pal}
            )
        }
        manager.baseworker_mapping = {
            str(failing_pal.InstanceId): failing_pal
        }
        manager._dangling_pals = {}

        def fail_heal() -> None:
            raise RuntimeError("synthetic heal failure")

        failing_pal.heal_pal = fail_heal
        with self.assertRaises(DomainError) as raised:
            self.editor.execute(
                HealAllPals(
                    session_id=self.session.session_id,
                    expected_revision=0,
                )
            )

        self.assertEqual("COMMAND_EXECUTION_FAILED", raised.exception.code)
        self.assertEqual(0, self.session.revision)
        self.assertEqual(before[str(self.pal.InstanceId)], self.pal._pal_param)
        self.assertEqual(
            before[str(failing_pal.InstanceId)],
            failing_pal._pal_param,
        )

    def test_pal_progression_rejects_negative_friendship_level(self) -> None:
        before = deepcopy(self.pal._pal_param)

        with self.assertRaises(DomainError) as raised:
            self.editor.execute(
                UpdatePalProgression(
                    session_id=self.session.session_id,
                    expected_revision=0,
                    pal_id=str(self.pal.InstanceId),
                    values={"friendship_level": -1},
                )
            )

        self.assertEqual("VALUE_OUT_OF_RANGE", raised.exception.code)
        self.assertEqual(0, raised.exception.details["minimum"])
        self.assertEqual(before, self.pal._pal_param)
        self.assertEqual(0, self.session.revision)

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
