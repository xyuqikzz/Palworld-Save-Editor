from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
import unittest

from palworld_pal_editor.application.inventory_editor import InventoryEditor
from palworld_pal_editor.application.inventory_layout_editor import (
    InventoryLayoutEditor,
)
from palworld_pal_editor.core.item_container_data import ItemContainerData
from palworld_pal_editor.domain.commands import (
    FillItemSlots,
    PasteItemSlot,
    PutItem,
    SortItemContainer,
    SwapItemSlots,
    UpdateItemCount,
)
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.domain.item_catalog import (
    ItemCatalog,
    new_item_slot_metadata,
)
from palworld_pal_editor.domain.models import ItemCatalogEntry, ItemContainerType

from tests.unit import test_inventory_read as inventory_fixtures
from tests.unit.test_dynamic_item_data import (
    dynamic_catalog,
    make_editor as make_dynamic_editor,
)


class InventoryLayoutEditorTests(unittest.TestCase):
    def test_copy_paste_fill_and_sort_use_domain_slots(self) -> None:
        inventory, ids, manager = (
            inventory_fixtures.InventoryReadTests().make_editor()
        )
        session = inventory._session
        base_catalog = inventory_fixtures.catalog()
        all_catalog = ItemCatalog(
            [
                replace(
                    base_catalog.get("Stone"),
                    allowed_containers=tuple(ItemContainerType),
                )
            ]
        )
        layout = InventoryLayoutEditor(session, all_catalog)
        copied = layout.copy_slot(
            session_id=session.session_id,
            expected_revision=0,
            player_id="player-a",
            container_type=ItemContainerType.COMMON,
            slot_index=1,
        )
        layout.execute(
            PasteItemSlot(
                session_id=session.session_id,
                expected_revision=0,
                player_id="player-a",
                container_type=ItemContainerType.COMMON,
                slot_index=0,
                clipboard_token=copied["clipboard_token"],
            )
        )
        common = manager.item_container_data.get(ids["CommonContainerId"])
        self.assertEqual(5, common.get_occupied(0).count)

        layout.execute(
            FillItemSlots(
                session_id=session.session_id,
                expected_revision=1,
                player_id="player-a",
                container_type=ItemContainerType.ESSENTIAL,
                slot_indices=(0, 2),
                static_id="Stone",
                count=2,
            )
        )
        essential = manager.item_container_data.get(ids["EssentialContainerId"])
        self.assertEqual([0, 1, 2], sorted(essential.slots))

        InventoryEditor(session, all_catalog).execute(
            PutItem(
                session_id=session.session_id,
                expected_revision=2,
                player_id="player-a",
                container_type=ItemContainerType.WEAPON_LOADOUT,
                slot_index=0,
                static_id="Stone",
                count=2,
            )
        )
        layout.execute(
            SortItemContainer(
                session_id=session.session_id,
                expected_revision=3,
                player_id="player-a",
                container_type=ItemContainerType.WEAPON_LOADOUT,
                sort_by="count",
                descending=True,
            )
        )
        weapon = manager.item_container_data.get(ids["WeaponLoadOutContainerId"])
        self.assertEqual(5, weapon.get_occupied(0).count)
        self.assertEqual(2, weapon.get_occupied(1).count)
        self.assertEqual(4, session.revision)

    def test_dynamic_paste_creates_independent_record_and_preserves_payload(self) -> None:
        inventory, session, manager, container_id = make_dynamic_editor()
        layout = InventoryLayoutEditor(session, inventory._catalog)
        source = manager.item_container_data.get(container_id).get_occupied(0)
        source_record = manager.dynamic_item_data.require_writable_reference(source)
        source_payload = deepcopy(source_record.raw_data)
        copied = layout.copy_slot(
            session_id=session.session_id,
            expected_revision=0,
            player_id="player-dynamic",
            container_type=ItemContainerType.COMMON,
            slot_index=0,
        )
        result = layout.execute(
            PasteItemSlot(
                session_id=session.session_id,
                expected_revision=0,
                player_id="player-dynamic",
                container_type=ItemContainerType.COMMON,
                slot_index=1,
                clipboard_token=copied["clipboard_token"],
            )
        )
        target = manager.item_container_data.get(container_id).get_occupied(1)
        self.assertNotEqual(source.dynamic_id, target.dynamic_id)
        target_record = manager.dynamic_item_data.require_writable_reference(target)
        target_payload = deepcopy(target_record.raw_data)
        target_payload["id"]["local_id_in_created_world"] = source_payload["id"][
            "local_id_in_created_world"
        ]
        self.assertEqual(source_payload, target_payload)
        self.assertEqual(2, len(manager.dynamic_item_data.records))
        manager.dynamic_item_data.assert_consistent()
        self.assertEqual(1, result["revision"])

    def test_dynamic_batch_fill_creates_independent_records_atomically(self) -> None:
        _inventory, session, manager, container_id = make_dynamic_editor(
            slots=[
                inventory_fixtures.slot(0, "None", 0),
                inventory_fixtures.slot(1, "None", 0),
                inventory_fixtures.slot(2, "None", 0),
            ],
            records=[],
            reference_scope_complete=True,
        )
        generated = iter(
            (
                "71000000-0000-0000-0000-000000000001",
                "71000000-0000-0000-0000-000000000002",
            )
        )
        layout = InventoryLayoutEditor(
            session,
            dynamic_catalog(),
            id_factory=lambda: next(generated),
        )

        result = layout.execute(
            FillItemSlots(
                session_id=session.session_id,
                expected_revision=0,
                player_id="player-dynamic",
                container_type=ItemContainerType.COMMON,
                slot_indices=(0, 2),
                static_id="Weapon_Test",
                count=1,
                dynamic_init={
                    "record_static_id": "Weapon_Test",
                    "durability": 50,
                    "ammo": 3,
                    "passive_traits": ["Rare"],
                },
            )
        )

        container = manager.item_container_data.get(container_id)
        first = container.get_occupied(0)
        second = container.get_occupied(2)
        self.assertNotEqual(first.dynamic_local_id, second.dynamic_local_id)
        self.assertEqual(2, len(manager.dynamic_item_data.records))
        self.assertEqual(1, result["revision"])
        manager.dynamic_item_data.assert_consistent()

    def test_egg_clipboard_copy_uses_verified_transfer_layout(self) -> None:
        _inventory, session, manager, container_id = make_dynamic_editor(
            slots=[
                inventory_fixtures.slot(0, "None", 0),
                inventory_fixtures.slot(1, "None", 0),
            ],
            records=[],
            reference_scope_complete=True,
        )
        InventoryEditor(
            session,
            dynamic_catalog(),
            id_factory=lambda: "72000000-0000-0000-0000-000000000001",
        ).execute(
            PutItem(
                session_id=session.session_id,
                expected_revision=0,
                player_id="player-dynamic",
                container_type=ItemContainerType.COMMON,
                slot_index=0,
                static_id="PalEgg_Test",
                count=1,
                dynamic_init={
                    "record_static_id": "PalEgg_Test",
                    "character_id": "SheepBall",
                },
            )
        )
        layout = InventoryLayoutEditor(
            session,
            dynamic_catalog(),
            id_factory=lambda: "72000000-0000-0000-0000-000000000002",
        )
        copied = layout.copy_slot(
            session_id=session.session_id,
            expected_revision=1,
            player_id="player-dynamic",
            container_type=ItemContainerType.COMMON,
            slot_index=0,
        )

        layout.execute(
            PasteItemSlot(
                session_id=session.session_id,
                expected_revision=1,
                player_id="player-dynamic",
                container_type=ItemContainerType.COMMON,
                slot_index=1,
                clipboard_token=copied["clipboard_token"],
            )
        )

        container = manager.item_container_data.get(container_id)
        self.assertNotEqual(
            container.get_occupied(0).dynamic_local_id,
            container.get_occupied(1).dynamic_local_id,
        )
        manager.dynamic_item_data.assert_consistent()

    def test_equipment_sort_stays_within_verified_slot_category_groups(self) -> None:
        inventory, ids, manager = inventory_fixtures.InventoryReadTests().make_editor()
        session = inventory._session
        equipment_id = ids["PlayerEquipArmorContainerId"]

        def equipment_slot(index: int, static_id: str = "None") -> dict:
            value = inventory_fixtures.slot(
                index,
                static_id,
                0 if static_id == "None" else 1,
            )
            value["RawData"]["value"].update(
                new_item_slot_metadata(
                    ItemContainerType.PLAYER_EQUIP_ARMOR, index
                )
            )
            return value

        values = [equipment_slot(index) for index in range(9)]
        for index, static_id in {
            0: "Head_Z",
            1: "Body_A",
            2: "Accessory_Z",
            6: "Accessory_A",
        }.items():
            values[index] = equipment_slot(index, static_id)
        gvas = SimpleNamespace(
            properties={
                "worldSaveData": {
                    "value": {
                        "ItemContainerSaveData": {
                            "value": [
                                inventory_fixtures.container(
                                    equipment_id, values, capacity=9
                                )
                            ]
                        }
                    }
                }
            }
        )
        manager.item_container_data.container_map[str(equipment_id)] = (
            ItemContainerData(gvas).get(equipment_id)
        )

        def entry(static_id: str, category: str) -> ItemCatalogEntry:
            return ItemCatalogEntry(
                static_id=static_id,
                names={"en": static_id},
                descriptions={"en": ""},
                category=category,
                rarity=1,
                icon=None,
                max_stack=1,
                allowed_containers=(ItemContainerType.PLAYER_EQUIP_ARMOR,),
                dynamic_kind="none",
                rule_status="verified",
            )

        catalog = ItemCatalog(
            [
                entry("Head_Z", "head"),
                entry("Body_A", "body"),
                entry("Accessory_Z", "accessory"),
                entry("Accessory_A", "accessory"),
            ]
        )
        InventoryLayoutEditor(session, catalog).execute(
            SortItemContainer(
                session_id=session.session_id,
                expected_revision=0,
                player_id="player-a",
                container_type=ItemContainerType.PLAYER_EQUIP_ARMOR,
                sort_by="internal_id",
            )
        )

        equipment = manager.item_container_data.get(equipment_id)
        self.assertEqual("Head_Z", equipment.get_occupied(0).static_id)
        self.assertEqual("Body_A", equipment.get_occupied(1).static_id)
        self.assertEqual("Accessory_A", equipment.get_occupied(2).static_id)
        self.assertEqual("Accessory_Z", equipment.get_occupied(3).static_id)
        for index in range(9):
            raw = equipment.get_raw_slot(index)._raw_data
            expected = new_item_slot_metadata(
                ItemContainerType.PLAYER_EQUIP_ARMOR, index
            )
            self.assertEqual(expected["permission"], raw["permission"])
            self.assertEqual(expected["trailing_bytes"], raw["trailing_bytes"])

    def test_move_to_empty_and_occupied_swap_preserve_slot_payloads(self) -> None:
        inventory, ids, manager = (
            inventory_fixtures.InventoryReadTests().make_editor()
        )
        session = inventory._session
        catalog = inventory_fixtures.catalog()
        container = manager.item_container_data.get(ids["CommonContainerId"])
        original = deepcopy(container.get_occupied(1)._raw_data)
        InventoryEditor(session, catalog).execute(
            PutItem(
                session_id=session.session_id,
                expected_revision=0,
                player_id="player-a",
                container_type=ItemContainerType.COMMON,
                slot_index=2,
                static_id="Stone",
                count=2,
            )
        )
        layout = InventoryLayoutEditor(session, catalog)

        moved = layout.execute(
            SwapItemSlots(
                session_id=session.session_id,
                expected_revision=1,
                player_id="player-a",
                container_type=ItemContainerType.COMMON,
                source_slot_index=1,
                target_slot_index=0,
            )
        )

        expected_at_zero = deepcopy(original)
        expected_at_zero["slot_index"] = 0
        self.assertTrue(container.is_empty(1))
        self.assertEqual(expected_at_zero, container.get_occupied(0)._raw_data)
        self.assertEqual(2, moved["revision"])

        layout.execute(
            SwapItemSlots(
                session_id=session.session_id,
                expected_revision=2,
                player_id="player-a",
                container_type=ItemContainerType.COMMON,
                source_slot_index=0,
                target_slot_index=2,
            )
        )
        expected_at_two = deepcopy(original)
        expected_at_two["slot_index"] = 2
        self.assertEqual(2, container.get_occupied(0).count)
        self.assertEqual(expected_at_two, container.get_occupied(2)._raw_data)
        self.assertEqual(
            ["level:ItemContainerSaveData"],
            session.changes()[-1]["affected_records"],
        )

    def test_dynamic_move_keeps_record_identity_and_reference_consistency(self) -> None:
        inventory, session, manager, container_id = make_dynamic_editor()
        container = manager.item_container_data.get(container_id)
        source = container.get_occupied(0)
        local_id = source.dynamic_local_id
        record_count = len(manager.dynamic_item_data.records)

        InventoryLayoutEditor(session, inventory._catalog).execute(
            SwapItemSlots(
                session_id=session.session_id,
                expected_revision=0,
                player_id="player-dynamic",
                container_type=ItemContainerType.COMMON,
                source_slot_index=0,
                target_slot_index=1,
            )
        )

        self.assertTrue(container.is_empty(0))
        self.assertEqual(local_id, container.get_occupied(1).dynamic_local_id)
        self.assertEqual(record_count, len(manager.dynamic_item_data.records))
        manager.dynamic_item_data.assert_consistent()

    def test_swap_rejects_same_or_empty_source_without_mutation(self) -> None:
        inventory, ids, manager = (
            inventory_fixtures.InventoryReadTests().make_editor()
        )
        session = inventory._session
        container = manager.item_container_data.get(ids["CommonContainerId"])
        before = container.snapshot_all()
        layout = InventoryLayoutEditor(session, inventory_fixtures.catalog())

        for source, target, code in (
            (1, 1, "NO_LAYOUT_CHANGE"),
            (0, 2, "ITEM_SLOT_EMPTY"),
        ):
            with self.assertRaises(DomainError) as raised:
                layout.execute(
                    SwapItemSlots(
                        session_id=session.session_id,
                        expected_revision=0,
                        player_id="player-a",
                        container_type=ItemContainerType.COMMON,
                        source_slot_index=source,
                        target_slot_index=target,
                    )
                )
            self.assertEqual(code, raised.exception.code)

        self.assertEqual(0, session.revision)
        self.assertEqual(before, container.snapshot_all())
    def test_clipboard_is_revision_bound(self) -> None:
        inventory, _ids, _manager = (
            inventory_fixtures.InventoryReadTests().make_editor()
        )
        session = inventory._session
        layout = InventoryLayoutEditor(session, inventory_fixtures.catalog())
        copied = layout.copy_slot(
            session_id=session.session_id,
            expected_revision=0,
            player_id="player-a",
            container_type=ItemContainerType.COMMON,
            slot_index=1,
        )
        inventory.execute(
            UpdateItemCount(
                session_id=session.session_id,
                expected_revision=0,
                player_id="player-a",
                container_type=ItemContainerType.COMMON,
                slot_index=1,
                expected_static_id="Stone",
                count=6,
            )
        )
        with self.assertRaises(DomainError) as raised:
            layout.execute(
                PasteItemSlot(
                    session_id=session.session_id,
                    expected_revision=1,
                    player_id="player-a",
                    container_type=ItemContainerType.COMMON,
                    slot_index=0,
                    clipboard_token=copied["clipboard_token"],
                )
            )
        self.assertEqual("CLIPBOARD_STALE", raised.exception.code)


if __name__ == "__main__":
    unittest.main()
