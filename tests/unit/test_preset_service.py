from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import patch

from palworld_pal_editor.application.preset_service import PresetService
from palworld_pal_editor.application.inventory_editor import InventoryEditor
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.domain.item_catalog import ItemCatalog
from palworld_pal_editor.domain.models import ItemContainerType
from palworld_pal_editor.domain.commands import PutItem

from tests.unit import test_inventory_read as inventory_fixtures
from tests.unit.test_structural_pal_editor import PAL_ID, make_manager
from tests.unit.test_dynamic_item_data import (
    dynamic_catalog,
    item_slot as dynamic_item_slot,
    make_editor as make_dynamic_editor,
)


class PresetServiceTests(unittest.TestCase):
    def test_inventory_preset_is_versioned_and_applied_atomically(self) -> None:
        inventory, ids, manager = (
            inventory_fixtures.InventoryReadTests().make_editor()
        )
        for field_name, container_id in ids.items():
            if field_name != "CommonContainerId":
                manager.item_container_data.get(container_id).clear_plain(1)
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
        with patch.object(ItemCatalog, "load_default", return_value=all_catalog):
            service = PresetService(session)
            preset = service.export_inventory("player-a")
            preview = service.preview_apply(
                session_id=session.session_id,
                expected_revision=0,
                preset=preset,
                target_ids=("player-a",),
            )
            result = service.apply(
                session_id=session.session_id,
                expected_revision=0,
                preset=preset,
                target_ids=("player-a",),
                impact_token=preview["impact_token"],
            )
        self.assertEqual(PresetService.SCHEMA, preset["schema"])
        self.assertEqual(PresetService.VERSION, preset["version"])
        self.assertEqual(1, result["revision"])
        self.assertEqual(1, len(session.changes()))

    def test_dynamic_inventory_preset_roundtrips_constructor_fields(self) -> None:
        _editor, session, manager, container_id = make_dynamic_editor(
            slots=[dynamic_item_slot(0, dynamic=False)],
            records=[],
            reference_scope_complete=True,
        )
        manager.player_mapping["player-dynamic"]._ids = {
            "CommonContainerId": container_id
        }
        catalog = dynamic_catalog()
        InventoryEditor(
            session,
            catalog,
            id_factory=lambda: "74000000-0000-0000-0000-000000000001",
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
                    "durability": 88.5,
                    "ammo": 9,
                    "passive_traits": ["Rare", "Swift"],
                },
            )
        )

        with patch.object(ItemCatalog, "load_default", return_value=catalog):
            service = PresetService(session)
            preset = service.export_inventory("player-dynamic")
            exported_slot = preset["containers"][0]["slots"][0]
            self.assertEqual(
                {
                    "record_static_id": "Weapon_Test",
                    "durability": 88.5,
                    "ammo": 9,
                    "passive_traits": ["Rare", "Swift"],
                },
                exported_slot["dynamic_init"],
            )
            preview = service.preview_apply(
                session_id=session.session_id,
                expected_revision=1,
                preset=preset,
                target_ids=("player-dynamic",),
            )
            service.apply(
                session_id=session.session_id,
                expected_revision=1,
                preset=preset,
                target_ids=("player-dynamic",),
                impact_token=preview["impact_token"],
            )

        slot = manager.item_container_data.get(container_id).get_occupied(0)
        record = manager.dynamic_item_data.require_writable_reference(slot)
        self.assertEqual(88.5, record.raw_data["durability"])
        self.assertEqual(9, record.raw_data["remaining_bullets"])
        self.assertEqual(["Rare", "Swift"], record.raw_data["passive_skill_list"])
        self.assertEqual(1, len(manager.dynamic_item_data.records))
        manager.dynamic_item_data.assert_consistent()

    def test_skill_preset_uses_explicit_batch_command(self) -> None:
        manager, _player, pal = make_manager()
        session = SaveSession.from_loaded_manager(manager, Path("synthetic-save"))
        service = PresetService(session)
        preset = service.export_skills(str(PAL_ID))
        preview = service.preview_apply(
            session_id=session.session_id,
            expected_revision=0,
            preset=preset,
            target_ids=(str(PAL_ID),),
        )
        result = service.apply(
            session_id=session.session_id,
            expected_revision=0,
            preset=preset,
            target_ids=(str(PAL_ID),),
            impact_token=preview["impact_token"],
        )
        self.assertEqual(list(pal.EquipWaza or []), preset["skills"]["active"])
        self.assertEqual(1, result["revision"])
        self.assertEqual("BatchCommand", session.changes()[0]["command"])

    def test_unknown_or_malformed_preset_is_rejected(self) -> None:
        manager, _player, _pal = make_manager()
        session = SaveSession.from_loaded_manager(manager, Path("synthetic-save"))
        service = PresetService(session)
        with self.assertRaises(DomainError) as raised:
            service.preview_apply(
                session_id=session.session_id,
                expected_revision=0,
                preset={
                    "schema": PresetService.SCHEMA,
                    "version": 99,
                    "kind": "skills",
                    "skills": {},
                },
                target_ids=(str(PAL_ID),),
            )
        self.assertEqual("PRESET_VERSION_UNSUPPORTED", raised.exception.code)
        self.assertEqual(0, session.revision)


if __name__ == "__main__":
    unittest.main()
