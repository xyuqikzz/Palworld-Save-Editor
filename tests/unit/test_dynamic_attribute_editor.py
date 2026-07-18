from __future__ import annotations

from copy import deepcopy
import unittest

from palworld_pal_editor.application.dynamic_attribute_editor import (
    DynamicAttributeEditor,
)
from palworld_pal_editor.domain.commands import UpdateDynamicItemAttributes
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.domain.models import ItemContainerType

from tests.unit.test_dynamic_item_data import dynamic_entry, make_editor


class DynamicAttributeEditorTests(unittest.TestCase):
    CASES = {
        "weapon": {
            "durability": 30.5,
            "ammo": 42,
            "passive_traits": ["Swift", "Rare"],
        },
        "armor": {"durability": 50.0, "passive_traits": ["Rare"]},
        "accessory": {"passive_traits": ["Swift"]},
        "shield": {"durability": 80.0},
        "glider": {"durability": 60.0},
        "food": {"freshness": 120.0},
    }

    def make_kind(self, kind: str):
        entry = dynamic_entry(kind=kind)
        if kind == "food":
            entry["RawData"]["value"]["remaining_time"] = 25.0
        inventory, session, manager, container_id = make_editor(records=[entry])
        slot = manager.item_container_data.get(container_id).get_occupied(0)
        return (
            DynamicAttributeEditor(session),
            session,
            manager,
            slot,
        )

    def test_each_supported_kind_edits_only_present_public_fields(self) -> None:
        for kind, values in self.CASES.items():
            with self.subTest(kind=kind):
                editor, session, manager, slot = self.make_kind(kind)
                record = manager.dynamic_item_data.require_writable_reference(slot)
                before = deepcopy(record.raw_data)
                result = editor.execute(
                    UpdateDynamicItemAttributes(
                        session_id=session.session_id,
                        expected_revision=0,
                        player_id="player-dynamic",
                        container_type=ItemContainerType.COMMON,
                        slot_index=0,
                        expected_static_id=slot.static_id,
                        expected_dynamic_id=slot.dynamic_id,
                        values=values,
                    )
                )
                self.assertEqual(values, result["dynamic_item"]["attributes"])
                current = manager.dynamic_item_data.require_writable_reference(slot)
                self.assertEqual(
                    before["trailing_bytes"] if "trailing_bytes" in before else None,
                    current.raw_data.get("trailing_bytes"),
                )
                self.assertEqual(1, session.revision)

    def test_missing_or_unknown_attribute_does_not_mutate(self) -> None:
        entry = dynamic_entry(kind="shield")
        del entry["RawData"]["value"]["durability"]
        inventory, session, manager, container_id = make_editor(records=[entry])
        slot = manager.item_container_data.get(container_id).get_occupied(0)
        record = manager.dynamic_item_data.require_writable_reference(slot)
        before = deepcopy(record.raw_data)
        editor = DynamicAttributeEditor(session)
        for values, code in (
            ({"durability": 10}, "DYNAMIC_ATTRIBUTE_MISSING"),
            ({"ammo": 10}, "UNSUPPORTED_COMMAND_FIELD"),
        ):
            with self.subTest(code=code), self.assertRaises(DomainError) as raised:
                editor.execute(
                    UpdateDynamicItemAttributes(
                        session_id=session.session_id,
                        expected_revision=0,
                        player_id="player-dynamic",
                        container_type=ItemContainerType.COMMON,
                        slot_index=0,
                        expected_static_id=slot.static_id,
                        expected_dynamic_id=slot.dynamic_id,
                        values=values,
                    )
                )
            self.assertEqual(code, raised.exception.code)
            self.assertEqual(before, record.raw_data)
            self.assertEqual(0, session.revision)


if __name__ == "__main__":
    unittest.main()
