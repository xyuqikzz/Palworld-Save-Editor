from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import unittest

from palworld_pal_editor.application.character_editor import CharacterEditor
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.application.structural_pal_editor import StructuralPalEditor
from palworld_pal_editor.config import Config
from palworld_pal_editor.core.character_index import (
    CharacterIndex,
    inspect_decoded_character_graph,
)
from palworld_pal_editor.core.container_data import ContainerData
from palworld_pal_editor.core.group_data import GroupData
from palworld_pal_editor.core.pal_entity import PalEntity
from palworld_pal_editor.core.pal_objects import PalObjects, toUUID
from palworld_pal_editor.core.player_entity import PlayerEntity
from palworld_pal_editor.core.save_manager import SaveManager
from palworld_pal_editor.domain.commands import (
    AddPal,
    ClonePal,
    DeletePal,
    MovePal,
    RecoverDetachedPal,
    UpdatePalProgression,
)
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.domain.models import CharacterContainerType
from palworld_pal_editor.utils.data_provider import DataProvider


PLAYER_ID = toUUID("11111111-1111-1111-1111-111111111111")
PLAYER_INSTANCE_ID = toUUID("22222222-2222-2222-2222-222222222222")
PAL_ID = toUUID("33333333-3333-3333-3333-333333333333")
PARTY_ID = toUUID("44444444-4444-4444-4444-444444444444")
STORAGE_ID = toUUID("55555555-5555-5555-5555-555555555555")
GROUP_ID = toUUID("66666666-6666-6666-6666-666666666666")


def _container(container_id, size: int) -> dict:
    return {
        "key": {"ID": PalObjects.Guid(container_id)},
        "value": {
            "Slots": PalObjects.ArrayProperty(
                "StructProperty", {"values": []}
            ),
            "SlotNum": PalObjects.IntProperty(size),
        },
    }


def _group() -> dict:
    return {
        "key": GROUP_ID,
        "value": {
            "GroupType": PalObjects.EnumProperty(
                "EPalGroupType", "EPalGroupType::Guild"
            ),
            "RawData": PalObjects.ArrayProperty(
                "ByteProperty",
                {
                    "group_id": GROUP_ID,
                    "guild_name": "Synthetic Guild",
                    "players": [
                        {
                            "player_uid": PLAYER_ID,
                            "player_info": {"player_name": "Player One"},
                        }
                    ],
                    "base_ids": [],
                    "individual_character_handle_ids": [],
                },
            ),
        },
    }


def _player_object() -> dict:
    value = PalObjects.PalSaveParameter(
        PLAYER_INSTANCE_ID, PLAYER_ID, PARTY_ID, 0, GROUP_ID
    )
    value["key"]["PlayerUId"] = PalObjects.Guid(PLAYER_ID)
    param = value["value"]["RawData"]["value"]["object"]["SaveParameter"][
        "value"
    ]
    param["IsPlayer"] = PalObjects.BoolProperty(True)
    param["NickName"] = PalObjects.StrProperty("Player One")
    return value


def _player_gvas() -> SimpleNamespace:
    return SimpleNamespace(
        properties={
            "SaveData": {
                "value": {
                    "IndividualId": {
                        "value": {
                            "PlayerUId": PalObjects.Guid(PLAYER_ID),
                            "InstanceId": PalObjects.Guid(PLAYER_INSTANCE_ID),
                        }
                    },
                    "OtomoCharacterContainerId": PalObjects.PalContainerId(
                        PARTY_ID
                    ),
                    "PalStorageContainerId": PalObjects.PalContainerId(
                        STORAGE_ID
                    ),
                    "InventoryInfo": {"value": {}},
                    "UnlockedRecipeTechnologyNames": PalObjects.ArrayProperty(
                        "NameProperty", {"values": []}
                    ),
                }
            }
        }
    )


def make_manager():
    player_object = _player_object()
    pal_object = PalObjects.PalSaveParameter(
        PAL_ID, PLAYER_ID, PARTY_ID, 0, GROUP_ID
    )
    entities = [player_object, pal_object]
    gvas = SimpleNamespace(
        header=None,
        properties={
            "worldSaveData": {
                "value": {
                    "CharacterSaveParameterMap": {"value": entities},
                    "CharacterContainerSaveData": {
                        "value": [
                            _container(PARTY_ID, 5),
                            _container(STORAGE_ID, 10),
                        ]
                    },
                    "GroupSaveDataMap": {"value": [_group()]},
                }
            }
        },
    )
    containers = ContainerData(gvas)
    groups = GroupData(gvas)
    party = containers.get_container(PARTY_ID)
    assert party.add_pal(PAL_ID, 0) == 0
    group = groups.get_group(GROUP_ID)
    assert group.add_pal(PAL_ID)
    pal = PalEntity(pal_object)
    player = PlayerEntity(
        GROUP_ID,
        player_object,
        {str(PAL_ID): pal},
        _player_gvas(),
        0,
    )
    pal.set_owner_player_entity(player)
    manager = SimpleNamespace(
        gvas_file=gvas,
        _entities_list=entities,
        player_mapping={str(PLAYER_ID): player},
        baseworker_mapping={},
        _dangling_pals={},
        container_data=containers,
        group_data=groups,
        item_container_data=SimpleNamespace(container_map={}),
    )
    manager.get_player = lambda player_id: manager.player_mapping.get(str(player_id))
    manager.get_pal = lambda pal_id: CharacterIndex(manager).pals.get(str(pal_id))
    return manager, player, pal


def normalized_state(manager) -> dict:
    return {
        "entities": deepcopy(manager._entities_list),
        "containers": {
            str(container.ID): deepcopy(container._slots_data)
            for container in manager.container_data.get_containers()
        },
        "groups": {
            str(group.group_id): deepcopy(group._group_param)
            for group in manager.group_data.get_groups()
        },
        "palboxes": {
            player_id: sorted(player._palbox)
            for player_id, player in manager.player_mapping.items()
        },
        "new_palboxes": {
            player_id: sorted(player._new_palbox)
            for player_id, player in manager.player_mapping.items()
        },
        "player_saves": {
            player_id: deepcopy(player._player_save_data)
            for player_id, player in manager.player_mapping.items()
        },
        "baseworkers": sorted(manager.baseworker_mapping),
        "dangling": sorted(manager._dangling_pals),
    }


class StructuralPalEditorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manager, self.player, self.pal = make_manager()
        self.session = SaveSession.from_loaded_manager(
            self.manager, Path("synthetic-structural-save")
        )
        self.generated = iter(
            [
                "70000000-0000-0000-0000-000000000001",
                "70000000-0000-0000-0000-000000000002",
                "70000000-0000-0000-0000-000000000003",
                "70000000-0000-0000-0000-000000000004",
                "70000000-0000-0000-0000-000000000005",
            ]
        )
        singleton = SaveManager()
        self._had_singleton_players = hasattr(singleton, "player_mapping")
        self._singleton_players = getattr(singleton, "player_mapping", None)
        singleton.player_mapping = self.manager.player_mapping

    def tearDown(self) -> None:
        singleton = SaveManager()
        if self._had_singleton_players:
            singleton.player_mapping = self._singleton_players
        else:
            del singleton.player_mapping

    def editor(self, failure_hook=None):
        return StructuralPalEditor(
            self.session,
            id_factory=lambda: next(self.generated),
            failure_hook=failure_hook,
        )

    def test_add_human_npc_to_pal_storage_with_safe_moveset(self) -> None:
        added = self.editor().execute(
            AddPal(
                session_id=self.session.session_id,
                expected_revision=0,
                player_id=str(PLAYER_ID),
                species_id="SalesPerson_Wander",
                container_type=CharacterContainerType.PAL_STORAGE,
            )
        )["pal"]

        npc = CharacterIndex(self.manager).pals[added["pal_id"]]
        self.assertEqual("SalesPerson_Wander", npc.CharacterID)
        self.assertTrue(npc.IsHuman)
        self.assertIsNone(npc.Gender)
        self.assertEqual(["EPalWazaID::Weapon_Use"], npc.MasteredWaza)
        self.assertEqual(["EPalWazaID::Weapon_Use"], npc.EquipWaza)
        self.assertEqual(str(STORAGE_ID), added["container_id"])

    def test_add_max_human_npc_sets_trust_without_awakening(self) -> None:
        added = self.editor().execute(
            AddPal(
                session_id=self.session.session_id,
                expected_revision=0,
                player_id=str(PLAYER_ID),
                species_id="SalesPerson_Wander",
                container_type=CharacterContainerType.PAL_STORAGE,
                max_pal=True,
            )
        )["pal"]

        npc = CharacterIndex(self.manager).pals[added["pal_id"]]
        self.assertTrue(npc.IsHuman)
        self.assertEqual(10, npc.FriendshipLevel)
        self.assertEqual(DataProvider.get_pal_friendship(10), npc.FriendshipPoint)
        self.assertEqual(10, added["friendship_level"])
        self.assertNotIn("bIsAwakening", npc._pal_param)
        self.assertEqual(80, npc.Level)

    def test_existing_human_npc_materializes_missing_trust_field(self) -> None:
        PalObjects.set_BaseType(
            self.pal._pal_param["CharacterID"], "SalesPerson_Wander"
        )
        self.pal._pal_param.pop("FriendshipPoint", None)

        result = CharacterEditor(self.session).execute(
            UpdatePalProgression(
                session_id=self.session.session_id,
                expected_revision=0,
                pal_id=str(self.pal.InstanceId),
                values={"friendship_level": 10},
            )
        )

        self.assertTrue(self.pal.IsHuman)
        self.assertEqual(10, result["value"]["friendship_level"])
        self.assertEqual(
            DataProvider.get_pal_friendship(10),
            self.pal.FriendshipPoint,
        )
        self.assertEqual(
            "IntProperty",
            self.pal._pal_param["FriendshipPoint"]["type"],
        )
        self.assertEqual(1, self.session.revision)

    def test_add_boss_only_otomo_uses_species_moves_and_player_record_key(self) -> None:
        added = self.editor().execute(
            AddPal(
                session_id=self.session.session_id,
                expected_revision=0,
                player_id=str(PLAYER_ID),
                species_id="BOSS_KingWhale_otomo",
                container_type=CharacterContainerType.PAL_STORAGE,
            )
        )["pal"]

        pal = CharacterIndex(self.manager).pals[added["pal_id"]]
        pal.Level = 16

        expected_moves = [
            "EPalWazaID::Unique_KingWhale_HomingBubble",
            "EPalWazaID::CreepingBubble",
            "EPalWazaID::Unique_KingWhale_AquaBlade",
        ]
        self.assertEqual("BOSS_KingWhale_otomo", pal.CharacterID)
        self.assertEqual("BOSS_KingWhale_otomo", pal.DataAccessKey)
        self.assertEqual(expected_moves, pal.MasteredWaza)
        self.assertEqual(expected_moves, pal.EquipWaza)
        self.assertEqual(
            ["KingWhale"],
            [row["key"] for row in self.player.PaldeckUnlockFlag],
        )
        self.assertEqual(
            ["KingWhale"],
            [row["key"] for row in self.player.PalCaptureCount],
        )

    def test_add_pal_applies_passive_preset_and_max_work_atomically(self) -> None:
        before_level = self.session.revision
        added = self.editor().execute(
            AddPal(
                session_id=self.session.session_id,
                expected_revision=before_level,
                player_id=str(PLAYER_ID),
                species_id="SheepBall",
                container_type=CharacterContainerType.PAL_STORAGE,
                passive=("WorldTree_CraftSpeed", "CraftSpeed_up3"),
                max_work=True,
            )
        )["pal"]

        pal = CharacterIndex(self.manager).pals[added["pal_id"]]
        self.assertEqual(
            ["WorldTree_CraftSpeed", "CraftSpeed_up3"],
            pal.PassiveSkillList,
        )
        self.assertEqual(Config.max_souls_level, pal.Rank_CraftSpeed)
        self.assertEqual(5, pal.Rank)
        self.assertTrue(pal.WorkSuitabilities)
        self.assertTrue(
            all(
                level == Config.max_suitability_level
                for level in pal.WorkSuitabilities.values()
            )
        )
        self.assertIsNone(pal.Level)
        self.assertIsNone(pal.Rank_HP)
        self.assertFalse(pal.IsAwakened)
        self.assertEqual(before_level + 1, self.session.revision)
        self.assertEqual(1, len(self.session.changes()))

    def test_add_pal_max_pal_uses_the_existing_unrestricted_maxima(self) -> None:
        added = self.editor().execute(
            AddPal(
                session_id=self.session.session_id,
                expected_revision=0,
                player_id=str(PLAYER_ID),
                species_id="SheepBall",
                container_type=CharacterContainerType.PAL_STORAGE,
                passive=("Rare",),
                max_pal=True,
                unrestricted=True,
            )
        )["pal"]

        pal = CharacterIndex(self.manager).pals[added["pal_id"]]
        self.assertEqual(["Rare"], pal.PassiveSkillList)
        self.assertEqual(100, pal.Level)
        self.assertEqual(10, pal.FriendshipLevel)
        self.assertEqual(255, pal.Talent_HP)
        self.assertEqual(255, pal.Talent_Melee)
        self.assertEqual(255, pal.Talent_Shot)
        self.assertEqual(255, pal.Talent_Defense)
        self.assertEqual(255, pal.Rank_HP)
        self.assertEqual(255, pal.Rank_Attack)
        self.assertEqual(255, pal.Rank_Defence)
        self.assertEqual(255, pal.Rank_CraftSpeed)
        self.assertEqual(255, pal.Rank)
        self.assertTrue(pal.IsAwakened)
        self.assertTrue(
            all(
                level == Config.max_suitability_level
                for level in pal.WorkSuitabilities.values()
            )
        )

    def test_add_pal_rejects_invalid_passive_preset_without_partial_mutation(self) -> None:
        before = normalized_state(self.manager)

        with self.assertRaises(DomainError) as raised:
            self.editor().execute(
                AddPal(
                    session_id=self.session.session_id,
                    expected_revision=0,
                    player_id=str(PLAYER_ID),
                    species_id="SheepBall",
                    container_type=CharacterContainerType.PAL_STORAGE,
                    passive=("UnknownPassive",),
                    max_work=True,
                )
            )

        self.assertEqual("UNKNOWN_SKILL", raised.exception.code)
        self.assertEqual(before, normalized_state(self.manager))
        self.assertEqual(0, self.session.revision)
        self.assertEqual([], self.session.changes())

    def test_add_pal_rejects_conflicting_max_presets_without_partial_mutation(self) -> None:
        before = normalized_state(self.manager)

        with self.assertRaises(DomainError) as raised:
            self.editor().execute(
                AddPal(
                    session_id=self.session.session_id,
                    expected_revision=0,
                    player_id=str(PLAYER_ID),
                    species_id="SheepBall",
                    container_type=CharacterContainerType.PAL_STORAGE,
                    max_pal=True,
                    max_work=True,
                )
            )

        self.assertEqual("CONFLICTING_CREATION_PRESETS", raised.exception.code)
        self.assertEqual(before, normalized_state(self.manager))
        self.assertEqual(0, self.session.revision)
        self.assertEqual([], self.session.changes())

    def test_add_clone_move_delete_and_recover_pal(self) -> None:
        editor = self.editor()
        added = editor.execute(
            AddPal(
                session_id=self.session.session_id,
                expected_revision=0,
                player_id=str(PLAYER_ID),
                species_id="SheepBall",
                container_type=CharacterContainerType.PARTY,
            )
        )["pal"]
        self.assertNotEqual(str(PAL_ID), added["pal_id"])

        clone_command = ClonePal(
            session_id=self.session.session_id,
            expected_revision=1,
            source_pal_id=str(PAL_ID),
            target_player_id=str(PLAYER_ID),
            container_type=CharacterContainerType.PAL_STORAGE,
        )
        clone_preview = editor.preview_clone(clone_command)
        cloned = editor.execute(
            replace(clone_command, impact_token=clone_preview["impact_token"])
        )["pal"]
        self.assertNotIn(cloned["pal_id"], {str(PAL_ID), added["pal_id"]})

        move_command = MovePal(
            session_id=self.session.session_id,
            expected_revision=2,
            pal_id=str(PAL_ID),
            target_player_id=str(PLAYER_ID),
            container_type=CharacterContainerType.PAL_STORAGE,
            target_slot=1,
        )
        move_preview = editor.preview_move(move_command)
        moved = editor.execute(
            replace(move_command, impact_token=move_preview["impact_token"])
        )["pal"]
        self.assertEqual(str(STORAGE_ID), moved["container_id"])
        self.assertEqual(1, moved["slot_index"])

        preview = editor.preview_delete(
            pal_id=cloned["pal_id"],
            session_id=self.session.session_id,
            expected_revision=3,
        )
        deleted = editor.execute(
            DeletePal(
                session_id=self.session.session_id,
                expected_revision=3,
                pal_id=cloned["pal_id"],
                impact_token=preview["impact_token"],
            )
        )["deleted"]
        self.assertEqual(cloned["pal_id"], deleted["pal_id"])

        storage = self.manager.container_data.get_container(STORAGE_ID)
        storage.del_pal(PAL_ID)
        self.pal.is_unreferenced_pal = True
        recovered = editor.execute(
            RecoverDetachedPal(
                session_id=self.session.session_id,
                expected_revision=4,
                pal_id=str(PAL_ID),
                target_player_id=str(PLAYER_ID),
                container_type=CharacterContainerType.PARTY,
                target_slot=0,
            )
        )["pal"]
        self.assertEqual(str(PARTY_ID), recovered["container_id"])
        self.assertFalse(recovered["detached"])
        self.assertEqual([], CharacterIndex(self.manager).issues_for(str(PAL_ID)))
        self.assertEqual(5, self.session.revision)

    def test_delete_requires_revision_bound_current_preview(self) -> None:
        editor = self.editor()
        preview = editor.preview_delete(
            pal_id=str(PAL_ID),
            session_id=self.session.session_id,
            expected_revision=0,
        )
        editor.execute(
            AddPal(
                session_id=self.session.session_id,
                expected_revision=0,
                player_id=str(PLAYER_ID),
                species_id="SheepBall",
            )
        )
        with self.assertRaises(DomainError) as raised:
            editor.execute(
                DeletePal(
                    session_id=self.session.session_id,
                    expected_revision=1,
                    pal_id=str(PAL_ID),
                    impact_token=preview["impact_token"],
                )
            )
        self.assertEqual("IMPACT_PREVIEW_STALE", raised.exception.code)

    def test_every_structural_failure_point_rolls_back_all_records(self) -> None:
        stages = {
            "after_character_record_insert": "add",
            "after_source_slot_remove": "move",
            "after_target_slot_add": "add",
            "after_owner_index_update": "add",
            "after_group_index_update": "add",
            "before_invariant_commit": "add",
        }
        for stage, operation in stages.items():
            with self.subTest(stage=stage):
                before = normalized_state(self.manager)

                def fail(actual, _context, expected=stage):
                    if actual == expected:
                        raise RuntimeError(f"failure at {actual}")

                editor = self.editor(fail)
                if operation == "move":
                    command = MovePal(
                        session_id=self.session.session_id,
                        expected_revision=0,
                        pal_id=str(PAL_ID),
                        target_player_id=str(PLAYER_ID),
                        container_type=CharacterContainerType.PAL_STORAGE,
                    )
                    preview = editor.preview_move(command)
                    command = replace(
                        command, impact_token=preview["impact_token"]
                    )
                else:
                    command = AddPal(
                        session_id=self.session.session_id,
                        expected_revision=0,
                        player_id=str(PLAYER_ID),
                        species_id="SheepBall",
                    )
                with self.assertRaises(DomainError) as raised:
                    editor.execute(command)
                self.assertEqual("COMMAND_EXECUTION_FAILED", raised.exception.code)
                self.assertEqual(before, normalized_state(self.manager))
                self.assertEqual(0, self.session.revision)
                self.assertEqual([], self.session.changes())

    def test_duplicate_character_record_disables_structural_write(self) -> None:
        self.manager._entities_list.append(deepcopy(self.pal._pal_obj))
        with self.assertRaises(DomainError) as raised:
            self.editor().execute(
                MovePal(
                    session_id=self.session.session_id,
                    expected_revision=0,
                    pal_id=str(PAL_ID),
                    target_player_id=str(PLAYER_ID),
                    container_type=CharacterContainerType.PAL_STORAGE,
                )
            )
        self.assertEqual("CHARACTER_INDEX_INVARIANT_FAILED", raised.exception.code)
        self.assertEqual(0, self.session.revision)

    def test_clone_and_move_require_current_impact_preview(self) -> None:
        editor = self.editor()
        clone = ClonePal(
            session_id=self.session.session_id,
            expected_revision=0,
            source_pal_id=str(PAL_ID),
            target_player_id=str(PLAYER_ID),
            container_type=CharacterContainerType.PAL_STORAGE,
        )
        with self.assertRaises(DomainError) as missing:
            editor.execute(clone)
        self.assertEqual("IMPACT_PREVIEW_REQUIRED", missing.exception.code)

        preview = editor.preview_clone(clone)
        editor.execute(
            AddPal(
                session_id=self.session.session_id,
                expected_revision=0,
                player_id=str(PLAYER_ID),
                species_id="SheepBall",
            )
        )
        with self.assertRaises(DomainError) as stale:
            editor.execute(
                replace(
                    clone,
                    expected_revision=1,
                    impact_token=preview["impact_token"],
                )
            )
        self.assertEqual("IMPACT_PREVIEW_STALE", stale.exception.code)

    def test_decoded_roundtrip_index_detects_slot_mismatch(self) -> None:
        self.assertEqual(
            [],
            [
                issue
                for issue in inspect_decoded_character_graph(
                    self.manager.gvas_file
                )
                if not issue.recoverable
            ],
        )
        self.pal.SlotId = (STORAGE_ID, 9)
        codes = {
            issue.code
            for issue in inspect_decoded_character_graph(
                self.manager.gvas_file
            )
            if not issue.recoverable
        }
        self.assertIn("PAL_SLOT_REFERENCE_MISMATCH", codes)


if __name__ == "__main__":
    unittest.main()
