from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from palworld_pal_editor.application.inventory_editor import InventoryEditor
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.core.dynamic_item_data import DynamicItemData
from palworld_pal_editor.core.item_container_data import ItemContainerData
from palworld_pal_editor.core.pal_objects import PalObjects, toUUID
from palworld_pal_editor.domain.commands import ClearItemSlot, PutItem, UpdateItemCount
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.domain.item_catalog import ItemCatalog
from palworld_pal_editor.domain.models import (
    INVENTORY_CONTAINER_FIELDS,
    ItemCatalogEntry,
    ItemContainerType,
)


ZERO = toUUID("00000000-0000-0000-0000-000000000000")
LOCAL_ID = toUUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


def item_slot(index: int, *, dynamic: bool, count: int = 1) -> dict:
    return {
        "RawData": {
            "value": {
                "slot_index": index,
                "count": count if dynamic else 0,
                "item": {
                    "static_id": "Weapon_Test" if dynamic else "None",
                    "dynamic_id": {
                        "created_world_id": ZERO,
                        "local_id_in_created_world": LOCAL_ID if dynamic else ZERO,
                    },
                },
                "trailing_bytes": [1, 3, 5, 7],
            }
        }
    }


def item_container(container_id, values: list[dict]) -> dict:
    return {
        "key": {"ID": PalObjects.Guid(container_id)},
        "value": {
            "SlotNum": PalObjects.IntProperty(len(values)),
            "Slots": {"value": {"values": values}},
            "RawData": {
                "value": {
                    "permission": {"item_categories": []},
                    "used_dynamic_item_ids": [],
                }
            },
        },
    }


def dynamic_entry(
    *,
    static_id: str = "Weapon_Test",
    local_id=LOCAL_ID,
    kind: str = "weapon",
) -> dict:
    return {
        "RawData": {
            "type": "ArrayProperty",
            "value": {
                "id": {
                    "created_world_id": ZERO,
                    "local_id_in_created_world": local_id,
                    "static_id": static_id,
                },
                "type": kind,
                "durability": 74.25,
                "remaining_bullets": 6,
                "passive_skill_list": ["Rare", "Swift"],
            },
        }
    }


class _Player:
    def __init__(self, common_id) -> None:
        self.PlayerUId = "player-dynamic"
        self.InstanceId = "instance-dynamic"
        self.NickName = "Dynamic Player"
        self.Level = 20
        self._ids = {
            field: common_id
            for field in INVENTORY_CONTAINER_FIELDS.values()
        }
        self._player_save_data = {"InventoryInfo": {"value": {}}}

    def resolve_item_container_ids(self):
        return dict(self._ids)


def dynamic_catalog() -> ItemCatalog:
    def entry(static_id: str, dynamic_kind: str) -> ItemCatalogEntry:
        return ItemCatalogEntry(
            static_id=static_id,
            names={"en": static_id},
            descriptions={"en": "Synthetic item"},
            category="weapon",
            rarity=2,
            icon=None,
            max_stack=99,
            allowed_containers=(ItemContainerType.COMMON,),
            dynamic_kind=dynamic_kind,
            rule_status="verified",
            rule_source="synthetic-test",
            rule_version="fixture-v1",
        )

    return ItemCatalog(
        [
            entry("Stone", "none"),
            entry("Weapon_Test", "weapon"),
            entry("Armor_Test", "armor"),
            entry("PalEgg_Test", "egg"),
        ]
    )


def make_editor(
    *,
    slots: list[dict] | None = None,
    records: list[dict] | None = None,
    reference_scope_complete: bool = False,
    reference_scope_verifier=None,
):
    common_id = toUUID("11111111-2222-3333-4444-555555555555")
    world = {
        "ItemContainerSaveData": {
            "value": [
                item_container(
                    common_id,
                    slots
                    or [item_slot(0, dynamic=True), item_slot(1, dynamic=False)],
                )
            ]
        },
        "DynamicItemSaveData": {
            "type": "ArrayProperty",
            "array_type": "StructProperty",
            "value": {
                "values": records if records is not None else [dynamic_entry()]
            },
        },
    }
    gvas = SimpleNamespace(
        properties={"worldSaveData": {"value": world}}, header=None
    )
    containers = ItemContainerData(gvas)
    dynamic_items = DynamicItemData(
        gvas,
        containers,
        reference_scope_complete=reference_scope_complete,
        reference_scope_verifier=reference_scope_verifier,
    )
    player = _Player(common_id)
    manager = SimpleNamespace(
        gvas_file=gvas,
        player_mapping={"player-dynamic": player},
        item_container_data=containers,
        dynamic_item_data=dynamic_items,
        get_player=lambda player_id: (
            player if player_id == "player-dynamic" else None
        ),
    )
    session = SaveSession.from_loaded_manager(manager, Path("synthetic-save"))
    return InventoryEditor(session, dynamic_catalog()), session, manager, common_id


class DynamicItemDataTests(unittest.TestCase):
    def test_indexes_records_and_reverse_references(self) -> None:
        editor, _session, manager, _container_id = make_editor()
        dynamic_items = manager.dynamic_item_data
        dynamic_items.assert_consistent()
        self.assertEqual("weapon", dynamic_items.get(str(LOCAL_ID)).kind)
        self.assertEqual(1, len(dynamic_items.references[str(LOCAL_ID)]))
        inventory = editor.get_inventory("player-dynamic").to_dict()
        occupied = inventory["containers"][0]["slots"][0]
        self.assertEqual("weapon", occupied["item"]["dynamic_kind"])

    def test_dangling_reference_blocks_consistency(self) -> None:
        _editor, _session, manager, _container_id = make_editor(records=[])
        with self.assertRaises(DomainError) as raised:
            manager.dynamic_item_data.assert_consistent()
        self.assertEqual("DYNAMIC_ITEM_REFERENCE_DANGLING", raised.exception.code)

    def test_slot_and_dynamic_record_static_ids_are_independent(self) -> None:
        slots = [item_slot(0, dynamic=True)]
        slots[0]["RawData"]["value"]["item"]["static_id"] = "Accessory_HP_1"
        records = [dynamic_entry(static_id="Accessory_HP_3")]
        _editor, _session, manager, _container_id = make_editor(
            slots=slots,
            records=records,
        )

        manager.dynamic_item_data.assert_consistent()
        record = manager.dynamic_item_data.require_writable_reference(
            manager.item_container_data.get(_container_id).get_occupied(0)
        )
        self.assertEqual("Accessory_HP_3", record.static_id)

    def test_duplicate_record_ids_are_rejected(self) -> None:
        _editor, _session, manager, _container_id = make_editor(
            records=[dynamic_entry(), dynamic_entry()]
        )
        with self.assertRaises(DomainError) as raised:
            manager.dynamic_item_data.assert_consistent()
        self.assertEqual("DYNAMIC_ITEM_RECORD_DUPLICATE", raised.exception.code)

    def test_known_dynamic_count_update_preserves_record_payload(self) -> None:
        editor, session, manager, container_id = make_editor()
        container = manager.item_container_data.get(container_id)
        before = deepcopy(manager.dynamic_item_data.get(str(LOCAL_ID)).raw_data)
        result = editor.execute(
            UpdateItemCount(
                session_id=session.session_id,
                expected_revision=0,
                player_id="player-dynamic",
                container_type=ItemContainerType.COMMON,
                slot_index=0,
                expected_static_id="Weapon_Test",
                count=2,
            )
        )
        self.assertEqual(1, result["revision"])
        self.assertEqual(2, container.get_occupied(0).count)
        self.assertEqual(
            before, manager.dynamic_item_data.get(str(LOCAL_ID)).raw_data
        )

    def test_unknown_dynamic_type_is_read_only(self) -> None:
        editor, session, manager, container_id = make_editor(
            records=[dynamic_entry(kind="unknown")]
        )
        container = manager.item_container_data.get(container_id)
        before_slot = container.snapshot_slot(0)
        before_record = deepcopy(
            manager.dynamic_item_data.get(str(LOCAL_ID)).raw_data
        )
        with self.assertRaises(DomainError) as raised:
            editor.execute(
                UpdateItemCount(
                    session_id=session.session_id,
                    expected_revision=0,
                    player_id="player-dynamic",
                    container_type=ItemContainerType.COMMON,
                    slot_index=0,
                    expected_static_id="Weapon_Test",
                    count=2,
                )
            )
        self.assertEqual("DYNAMIC_ITEM_TYPE_READ_ONLY", raised.exception.code)
        self.assertEqual(before_slot, container.snapshot_slot(0))
        self.assertEqual(
            before_record,
            manager.dynamic_item_data.get(str(LOCAL_ID)).raw_data,
        )
        self.assertEqual(0, session.revision)

    def test_delete_requires_complete_reference_scope(self) -> None:
        editor, session, manager, container_id = make_editor()
        container = manager.item_container_data.get(container_id)
        before = container.snapshot_slot(0)
        with self.assertRaises(DomainError) as raised:
            editor.execute(
                ClearItemSlot(
                    session_id=session.session_id,
                    expected_revision=0,
                    player_id="player-dynamic",
                    container_type=ItemContainerType.COMMON,
                    slot_index=0,
                    expected_static_id="Weapon_Test",
                    expected_dynamic_id=container.get_occupied(0).dynamic_id,
                )
            )
        self.assertEqual(
            "DYNAMIC_ITEM_REFERENCE_SCOPE_UNVERIFIED", raised.exception.code
        )
        self.assertEqual(before, container.snapshot_slot(0))
        self.assertIsNotNone(manager.dynamic_item_data.get(str(LOCAL_ID)))

    def test_delete_can_be_unlocked_by_raw_reference_audit(self) -> None:
        calls = []

        def verify(local_id: str, expected_occurrences: int) -> bool:
            calls.append((local_id, expected_occurrences))
            return True

        editor, session, manager, container_id = make_editor(
            reference_scope_verifier=verify
        )
        container = manager.item_container_data.get(container_id)

        result = editor.execute(
            ClearItemSlot(
                session_id=session.session_id,
                expected_revision=0,
                player_id="player-dynamic",
                container_type=ItemContainerType.COMMON,
                slot_index=0,
                expected_static_id="Weapon_Test",
                expected_dynamic_id=container.get_occupied(0).dynamic_id,
            )
        )

        self.assertEqual([(str(LOCAL_ID), 2)], calls)
        self.assertEqual("empty", result["slot"]["state"])
        self.assertIsNone(manager.dynamic_item_data.get(str(LOCAL_ID)))

    def test_failed_raw_reference_audit_remains_read_only(self) -> None:
        editor, session, manager, container_id = make_editor(
            reference_scope_verifier=lambda _local_id, _count: False
        )
        container = manager.item_container_data.get(container_id)

        with self.assertRaises(DomainError) as raised:
            editor.execute(
                ClearItemSlot(
                    session_id=session.session_id,
                    expected_revision=0,
                    player_id="player-dynamic",
                    container_type=ItemContainerType.COMMON,
                    slot_index=0,
                    expected_static_id="Weapon_Test",
                    expected_dynamic_id=container.get_occupied(0).dynamic_id,
                )
            )

        self.assertEqual(
            "DYNAMIC_ITEM_REFERENCE_SCOPE_UNVERIFIED", raised.exception.code
        )
        self.assertIsNotNone(manager.dynamic_item_data.get(str(LOCAL_ID)))

    def test_last_reference_delete_is_atomic_with_verified_scope(self) -> None:
        editor, session, manager, container_id = make_editor(
            reference_scope_complete=True
        )
        container = manager.item_container_data.get(container_id)
        result = editor.execute(
            ClearItemSlot(
                session_id=session.session_id,
                expected_revision=0,
                player_id="player-dynamic",
                container_type=ItemContainerType.COMMON,
                slot_index=0,
                expected_static_id="Weapon_Test",
                expected_dynamic_id=container.get_occupied(0).dynamic_id,
            )
        )
        self.assertEqual("empty", result["slot"]["state"])
        self.assertIsNone(manager.dynamic_item_data.get(str(LOCAL_ID)))
        manager.dynamic_item_data.assert_consistent()
        self.assertEqual(1, session.revision)

    def test_dynamic_delete_rolls_back_slot_and_record_on_validation_failure(self) -> None:
        editor, session, manager, container_id = make_editor(
            reference_scope_complete=True
        )
        container = manager.item_container_data.get(container_id)
        before_slot = container.snapshot_slot(0)
        before_record = deepcopy(
            manager.dynamic_item_data.get(str(LOCAL_ID)).raw_data
        )
        error = DomainError(
            code="INJECTED_VALIDATION_FAILURE",
            message="Synthetic validation failure.",
            http_status=409,
        )
        with patch.object(
            manager.dynamic_item_data,
            "assert_consistent",
            side_effect=error,
        ):
            with self.assertRaises(DomainError) as raised:
                editor.execute(
                    ClearItemSlot(
                        session_id=session.session_id,
                        expected_revision=0,
                        player_id="player-dynamic",
                        container_type=ItemContainerType.COMMON,
                        slot_index=0,
                        expected_static_id="Weapon_Test",
                        expected_dynamic_id=container.get_occupied(0).dynamic_id,
                    )
                )
        self.assertEqual("INJECTED_VALIDATION_FAILURE", raised.exception.code)
        self.assertEqual(before_slot, container.snapshot_slot(0))
        self.assertEqual(
            before_record,
            manager.dynamic_item_data.get(str(LOCAL_ID)).raw_data,
        )
        self.assertEqual(0, session.revision)
        self.assertEqual([], session.changes())

    def test_verified_weapon_armor_and_egg_constructors_create_current_records(self) -> None:
        cases = (
            (
                "Weapon_Test",
                "weapon",
                {
                    "record_static_id": "Weapon_Test",
                    "durability": 125.5,
                    "ammo": 7,
                    "passive_traits": ["Rare"],
                },
            ),
            (
                "Armor_Test",
                "armor",
                {"record_static_id": "Armor_Test", "durability": 250.0},
            ),
            (
                "PalEgg_Test",
                "egg",
                {
                    "record_static_id": "PalEgg_Test",
                    "character_id": "SheepBall",
                },
            ),
        )
        for index, (static_id, kind, dynamic_init) in enumerate(cases, start=1):
            with self.subTest(kind=kind):
                _editor, session, manager, container_id = make_editor(
                    slots=[item_slot(0, dynamic=False)],
                    records=[],
                    reference_scope_complete=True,
                )
                new_id = f"70000000-0000-0000-0000-{index:012d}"
                editor = InventoryEditor(
                    session,
                    dynamic_catalog(),
                    id_factory=lambda value=new_id: value,
                )

                result = editor.execute(
                    PutItem(
                        session_id=session.session_id,
                        expected_revision=0,
                        player_id="player-dynamic",
                        container_type=ItemContainerType.COMMON,
                        slot_index=0,
                        static_id=static_id,
                        count=1,
                        dynamic_init=dynamic_init,
                    )
                )

                slot = manager.item_container_data.get(container_id).get_occupied(0)
                record = manager.dynamic_item_data.get(new_id)
                self.assertEqual(new_id, slot.dynamic_local_id)
                self.assertEqual(kind, record.kind)
                self.assertEqual(static_id, record.static_id)
                self.assertEqual([0, 0, 0, 0], record.raw_data["leading_bytes"])
                self.assertEqual(1, result["revision"])
                manager.dynamic_item_data.assert_consistent()
                expected_custom_size = 24 if kind == "armor" else 44
                self.assertEqual(
                    expected_custom_size,
                    len(record.entry["CustomVersionData"]["value"]["values"]),
                )
                if kind == "weapon":
                    self.assertEqual("None", record.raw_data["unknown_str"])
                    self.assertEqual(7, record.raw_data["remaining_bullets"])
                if kind == "egg":
                    self.assertEqual("SheepBall", record.raw_data["character_id"])
                    self.assertEqual({}, record.raw_data["object"])
                    self.assertEqual([0] * 28, record.raw_data["trailing_bytes"])

    def test_dynamic_replace_with_plain_removes_last_record_atomically(self) -> None:
        editor, session, manager, container_id = make_editor(
            reference_scope_complete=True
        )
        editor = InventoryEditor(session, dynamic_catalog())

        editor.execute(
            PutItem(
                session_id=session.session_id,
                expected_revision=0,
                player_id="player-dynamic",
                container_type=ItemContainerType.COMMON,
                slot_index=0,
                static_id="Stone",
                count=3,
                mode="replace",
            )
        )

        slot = manager.item_container_data.get(container_id).get_occupied(0)
        self.assertEqual("Stone", slot.static_id)
        self.assertIsNone(slot.dynamic_id)
        self.assertIsNone(manager.dynamic_item_data.get(str(LOCAL_ID)))
        manager.dynamic_item_data.assert_consistent()

    def test_invalid_dynamic_initializer_is_rejected_without_mutation(self) -> None:
        _editor, session, manager, container_id = make_editor(
            slots=[item_slot(0, dynamic=False)],
            records=[],
            reference_scope_complete=True,
        )
        editor = InventoryEditor(session, dynamic_catalog())
        container = manager.item_container_data.get(container_id)
        before = container.snapshot_slot(0)

        with self.assertRaises(DomainError) as raised:
            editor.execute(
                PutItem(
                    session_id=session.session_id,
                    expected_revision=0,
                    player_id="player-dynamic",
                    container_type=ItemContainerType.COMMON,
                    slot_index=0,
                    static_id="Weapon_Test",
                    count=1,
                    dynamic_init={"durability": 1, "ammo": True},
                )
            )

        self.assertEqual("INVALID_DYNAMIC_INITIALIZER", raised.exception.code)
        self.assertEqual(before, container.snapshot_slot(0))
        self.assertEqual({}, manager.dynamic_item_data.records)
        self.assertEqual(0, session.revision)

    def test_constructor_rejects_altered_existing_record_envelope(self) -> None:
        _editor, session, manager, _container_id = make_editor(
            slots=[item_slot(0, dynamic=False)],
            records=[],
            reference_scope_complete=True,
        )
        InventoryEditor(
            session,
            dynamic_catalog(),
            id_factory=lambda: "73000000-0000-0000-0000-000000000001",
        ).execute(
            PutItem(
                session_id=session.session_id,
                expected_revision=0,
                player_id="player-dynamic",
                container_type=ItemContainerType.COMMON,
                slot_index=0,
                static_id="Weapon_Test",
                count=1,
                dynamic_init={
                    "record_static_id": "Weapon_Test",
                    "durability": 1,
                    "ammo": 0,
                    "passive_traits": [],
                },
            )
        )
        record = manager.dynamic_item_data.get(
            "73000000-0000-0000-0000-000000000001"
        )
        record.entry["RawData"]["type"] = "StructProperty"

        with self.assertRaises(DomainError) as raised:
            manager.dynamic_item_data.prepare_construction(
                "Weapon_Test",
                "weapon",
                {
                    "record_static_id": "Weapon_Test",
                    "durability": 1,
                    "ammo": 0,
                    "passive_traits": [],
                },
            )

        self.assertEqual(
            "DYNAMIC_ITEM_CONSTRUCTION_UNSUPPORTED", raised.exception.code
        )

    def test_shared_reference_clear_preserves_record_for_remaining_slot(self) -> None:
        slots = [
            item_slot(0, dynamic=True),
            item_slot(1, dynamic=True),
            item_slot(2, dynamic=False),
        ]
        editor, session, manager, container_id = make_editor(
            slots=slots, reference_scope_complete=True
        )
        container = manager.item_container_data.get(container_id)
        result = editor.execute(
            ClearItemSlot(
                session_id=session.session_id,
                expected_revision=0,
                player_id="player-dynamic",
                container_type=ItemContainerType.COMMON,
                slot_index=0,
                expected_static_id="Weapon_Test",
                expected_dynamic_id=container.get_occupied(0).dynamic_id,
            )
        )
        self.assertEqual("empty", result["slot"]["state"])
        self.assertTrue(container.is_empty(0))
        self.assertEqual(str(LOCAL_ID), container.get_occupied(1).dynamic_local_id)
        self.assertIsNotNone(manager.dynamic_item_data.get(str(LOCAL_ID)))
        manager.dynamic_item_data.assert_consistent()
        self.assertEqual(1, session.revision)


if __name__ == "__main__":
    unittest.main()
