from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest

from palworld_pal_editor.application.inventory_editor import InventoryEditor
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.core.item_container_data import ItemContainerData
from palworld_pal_editor.core.pal_objects import PalObjects, toUUID
from palworld_pal_editor.domain.item_catalog import ItemCatalog, new_item_slot_metadata
from palworld_pal_editor.domain.commands import ClearItemSlot, PutItem, UpdateItemCount
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.domain.models import (
    INVENTORY_CONTAINER_FIELDS,
    ItemCatalogEntry,
    ItemContainerType,
)


ZERO = toUUID("00000000-0000-0000-0000-000000000000")


def slot(index: int, static_id: str = "Stone", count: int = 5) -> dict:
    return {
        "RawData": {
            "value": {
                "slot_index": index,
                "count": count,
                "item": {
                    "static_id": static_id,
                    "dynamic_id": {
                        "created_world_id": ZERO,
                        "local_id_in_created_world": ZERO,
                    },
                },
                "trailing_bytes": [9, 8, 7],
            }
        }
    }


def container(container_id, values: list[dict], capacity: int = 3) -> dict:
    return {
        "key": {"ID": PalObjects.Guid(container_id)},
        "value": {
            "SlotNum": PalObjects.IntProperty(capacity),
            "Slots": {"value": {"values": values}},
        },
    }


class _Player:
    def __init__(self, ids: dict[str, object]) -> None:
        self.PlayerUId = "player-a"
        self.InstanceId = "instance-a"
        self.NickName = "Player A"
        self.Level = 10
        self._ids = ids
        self._player_save_data = {"InventoryInfo": {"value": {"synthetic": True}}}

    def resolve_item_container_ids(self):
        return dict(self._ids)


def catalog() -> ItemCatalog:
    return ItemCatalog(
        [
            ItemCatalogEntry(
                static_id="Stone",
                names={"en": "Stone"},
                descriptions={"en": "A stone"},
                category="material",
                rarity=0,
                icon="stone",
                max_stack=9999,
                allowed_containers=(ItemContainerType.COMMON,),
                dynamic_kind="none",
                rule_status="verified",
                rule_source="synthetic-test",
                rule_version="fixture-v1",
            )
        ]
    )


class InventoryReadTests(unittest.TestCase):
    def make_editor(self, item_catalog: ItemCatalog | None = None):
        ids = {
            field: toUUID(f"00000000-0000-0000-0000-{index:012d}")
            for index, field in enumerate(INVENTORY_CONTAINER_FIELDS.values(), start=1)
        }
        gvas = SimpleNamespace(
            properties={
                "worldSaveData": {
                    "value": {
                        "ItemContainerSaveData": {
                            "value": [
                                container(
                                    value,
                                    [
                                        slot(0, "None", 0),
                                        slot(1),
                                        slot(2, "None", 0),
                                    ],
                                )
                                for value in ids.values()
                            ]
                        }
                    }
                }
            }
        )
        player = _Player(ids)
        manager = SimpleNamespace(
            gvas_file=SimpleNamespace(header=None),
            player_mapping={"player-a": player},
            item_container_data=ItemContainerData(gvas),
            get_player=lambda player_id: player if player_id == "player-a" else None,
        )
        session = SaveSession.from_loaded_manager(manager, Path("synthetic-save"))
        return InventoryEditor(session, item_catalog or catalog()), ids, manager

    def test_reads_all_five_as_dense_views_without_container_ids(self) -> None:
        editor, ids, _manager = self.make_editor()
        payload = editor.get_inventory("player-a").to_dict()
        self.assertEqual(5, len(payload["containers"]))
        for value in payload["containers"]:
            self.assertEqual("available", value["status"])
            self.assertEqual([0, 1, 2], [slot["slot_index"] for slot in value["slots"]])
            self.assertEqual("empty", value["slots"][0]["state"])
            self.assertEqual("occupied", value["slots"][1]["state"])
            self.assertEqual("empty", value["slots"][2]["state"])
        serialized = str(payload)
        for container_id in ids.values():
            self.assertNotIn(str(container_id), serialized)

    def test_duplicate_and_out_of_range_slots_are_rejected(self) -> None:
        container_id = toUUID("11111111-2222-3333-4444-555555555555")
        for values in ([slot(1), slot(1)], [slot(3)]):
            gvas = SimpleNamespace(
                properties={
                    "worldSaveData": {
                        "value": {
                            "ItemContainerSaveData": {
                                "value": [container(container_id, values, capacity=3)]
                            }
                        }
                    }
                }
            )
            with self.subTest(values=values), self.assertRaises(ValueError):
                ItemContainerData(gvas)

    def test_sparse_slot_can_be_created_and_rolled_back_to_absence(self) -> None:
        container_id = toUUID("11111111-2222-3333-4444-555555555555")
        gvas = SimpleNamespace(
            properties={
                "worldSaveData": {
                    "value": {
                        "ItemContainerSaveData": {
                            "value": [container(container_id, [slot(1)], capacity=3)]
                        }
                    }
                }
            }
        )
        item_container = ItemContainerData(gvas).get(container_id)
        before = item_container.snapshot_slot(0)

        item_container.put_plain(
            0,
            "Stone",
            7,
            replace=False,
            slot_metadata=new_item_slot_metadata(ItemContainerType.COMMON, 0),
        )

        created = item_container.get_occupied(0)._raw_data
        self.assertEqual([], created["permission"]["type_a"])
        self.assertEqual([], created["permission"]["type_b"])
        self.assertEqual([], created["permission"]["item_static_ids"])
        self.assertEqual(0.0, created["corruption_progress_value"])
        self.assertEqual([0, 0, 0, 0], created["trailing_bytes"])
        self.assertEqual([0, 1], [slot.slot_index for slot in item_container.iter_encoded_slots()])

        item_container.restore_slot(0, before)

        self.assertTrue(item_container.is_empty(0))
        self.assertEqual([1], [slot.slot_index for slot in item_container.iter_encoded_slots()])

    def test_empty_container_uses_save_level_slot_envelope(self) -> None:
        empty_id = toUUID("11111111-2222-3333-4444-555555555555")
        template_id = toUUID("66666666-7777-8888-9999-aaaaaaaaaaaa")
        gvas = SimpleNamespace(
            properties={
                "worldSaveData": {
                    "value": {
                        "ItemContainerSaveData": {
                            "value": [
                                container(empty_id, [], capacity=2),
                                container(template_id, [slot(0)], capacity=1),
                            ]
                        }
                    }
                }
            }
        )
        item_container = ItemContainerData(gvas).get(empty_id)

        item_container.put_plain(
            1,
            "Stone",
            1,
            replace=False,
            slot_metadata=new_item_slot_metadata(ItemContainerType.COMMON, 1),
        )

        self.assertEqual("Stone", item_container.get_occupied(1).static_id)

    def test_update_count_is_atomic_and_preserves_identity_and_tail(self) -> None:
        editor, ids, manager = self.make_editor()
        session = editor._session
        common = manager.item_container_data.get(ids["CommonContainerId"])
        raw = common.get_occupied(1)._raw_data
        before_tail = list(raw["trailing_bytes"])
        before_dynamic = dict(raw["item"]["dynamic_id"])

        result = editor.execute(
            UpdateItemCount(
                session_id=session.session_id,
                expected_revision=0,
                player_id="player-a",
                container_type=ItemContainerType.COMMON,
                slot_index=1,
                expected_static_id="Stone",
                count=9999,
            )
        )
        self.assertEqual(1, result["revision"])
        self.assertEqual(9999, raw["count"])
        self.assertEqual(before_tail, raw["trailing_bytes"])
        self.assertEqual(before_dynamic, raw["item"]["dynamic_id"])
        self.assertEqual(1, len(session.changes()))

        with self.assertRaises(DomainError) as stale:
            editor.execute(
                UpdateItemCount(
                    session_id=session.session_id,
                    expected_revision=0,
                    player_id="player-a",
                    container_type=ItemContainerType.COMMON,
                    slot_index=1,
                    expected_static_id="Stone",
                    count=1,
                )
            )
        self.assertEqual("STALE_REVISION", stale.exception.code)
        self.assertEqual(9999, raw["count"])
        self.assertEqual(1, session.revision)
        self.assertEqual(1, len(session.changes()))

    def test_update_count_rejects_catalog_limit_without_mutation(self) -> None:
        editor, ids, manager = self.make_editor()
        session = editor._session
        common = manager.item_container_data.get(ids["CommonContainerId"])
        raw = common.get_occupied(1)._raw_data
        with self.assertRaises(DomainError) as raised:
            editor.execute(
                UpdateItemCount(
                    session_id=session.session_id,
                    expected_revision=0,
                    player_id="player-a",
                    container_type=ItemContainerType.COMMON,
                    slot_index=1,
                    expected_static_id="Stone",
                    count=10000,
                )
            )
        self.assertEqual("MAX_STACK_EXCEEDED", raised.exception.code)
        self.assertEqual(5, raw["count"])
        self.assertEqual(0, session.revision)
        self.assertEqual([], session.changes())

    def test_update_count_can_safely_decrease_without_catalog_rules(self) -> None:
        unknown_catalog = ItemCatalog(
            [
                ItemCatalogEntry(
                    static_id="Stone",
                    names={"en": "Stone"},
                    descriptions={"en": "A stone"},
                    category="unknown",
                    rarity=None,
                    icon=None,
                    max_stack=None,
                    allowed_containers=(),
                    dynamic_kind="unknown",
                    rule_status="unknown",
                )
            ]
        )
        editor, ids, manager = self.make_editor(unknown_catalog)
        session = editor._session
        common = manager.item_container_data.get(ids["CommonContainerId"])

        editor.execute(
            UpdateItemCount(
                session_id=session.session_id,
                expected_revision=0,
                player_id="player-a",
                container_type=ItemContainerType.COMMON,
                slot_index=1,
                expected_static_id="Stone",
                count=4,
            )
        )

        self.assertEqual(4, common.get_occupied(1).count)
        self.assertEqual(1, session.revision)

    def test_put_replace_and_clear_plain_items(self) -> None:
        editor, ids, manager = self.make_editor()
        session = editor._session
        common = manager.item_container_data.get(ids["CommonContainerId"])

        put = editor.execute(
            PutItem(
                session_id=session.session_id,
                expected_revision=0,
                player_id="player-a",
                container_type=ItemContainerType.COMMON,
                slot_index=0,
                static_id="Stone",
                count=7,
            )
        )
        self.assertEqual(7, common.get_occupied(0).count)
        self.assertIsNone(common.get_occupied(0).dynamic_id)
        self.assertEqual([9, 8, 7], common.get_occupied(0)._raw_data["trailing_bytes"])

        replaced = editor.execute(
            PutItem(
                session_id=session.session_id,
                expected_revision=1,
                player_id="player-a",
                container_type=ItemContainerType.COMMON,
                slot_index=1,
                static_id="Stone",
                count=8,
                mode="replace",
            )
        )
        self.assertEqual(8, common.get_occupied(1).count)
        self.assertEqual(
            [9, 8, 7], common.get_occupied(1)._raw_data["trailing_bytes"]
        )

        cleared = editor.execute(
            ClearItemSlot(
                session_id=session.session_id,
                expected_revision=2,
                player_id="player-a",
                container_type=ItemContainerType.COMMON,
                slot_index=1,
                expected_static_id="Stone",
            )
        )
        self.assertEqual("empty", cleared["slot"]["state"])
        self.assertNotIn(1, common.slots)
        self.assertTrue(common.is_empty(1))
        self.assertEqual(3, session.revision)
        self.assertEqual(3, len(session.changes()))

    def test_failed_replace_keeps_original_slot(self) -> None:
        editor, ids, manager = self.make_editor()
        session = editor._session
        common = manager.item_container_data.get(ids["CommonContainerId"])
        before = common.snapshot_slot(1)
        with self.assertRaises(DomainError) as raised:
            editor.execute(
                PutItem(
                    session_id=session.session_id,
                    expected_revision=0,
                    player_id="player-a",
                    container_type=ItemContainerType.COMMON,
                    slot_index=1,
                    static_id="MissingItem",
                    count=1,
                    mode="replace",
                )
            )
        self.assertEqual("ITEM_NOT_FOUND", raised.exception.code)
        self.assertEqual(before, common.snapshot_slot(1))
        self.assertEqual(0, session.revision)
        self.assertEqual([], session.changes())


if __name__ == "__main__":
    unittest.main()
