from __future__ import annotations

import unittest
from unittest.mock import patch

from palworld_pal_editor.application.batch_editor import BatchEditor
from palworld_pal_editor.domain.commands import PutItem, UpdateItemCount
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.domain.item_catalog import ItemCatalog
from palworld_pal_editor.domain.models import ItemContainerType

from tests.unit import test_inventory_read as inventory_fixtures


class BatchEditorTests(unittest.TestCase):
    def make_commands(self, session, second_count: int):
        base = {
            "session_id": session.session_id,
            "expected_revision": session.revision,
            "player_id": "player-a",
            "slot_index": 1,
            "expected_static_id": "Stone",
        }
        return (
            UpdateItemCount(
                **base,
                container_type=ItemContainerType.COMMON,
                count=10,
            ),
            PutItem(
                session_id=session.session_id,
                expected_revision=session.revision,
                player_id="player-a",
                container_type=ItemContainerType.COMMON,
                slot_index=0,
                static_id="Stone",
                count=second_count,
            ),
        )

    def test_successful_batch_commits_one_revision_and_change(self) -> None:
        inventory, ids, manager = inventory_fixtures.InventoryReadTests().make_editor()
        session = inventory._session
        commands = self.make_commands(session, 20)
        editor = BatchEditor(session)
        preview = editor.preview(
            session_id=session.session_id,
            expected_revision=0,
            operations=commands,
        )
        with patch.object(
            ItemCatalog, "load_default", return_value=inventory_fixtures.catalog()
        ):
            result = editor.execute(
                session_id=session.session_id,
                expected_revision=0,
                operations=commands,
                impact_token=preview["impact_token"],
            )
        self.assertEqual(1, result["revision"])
        self.assertEqual(2, result["operation_count"])
        self.assertEqual(10, manager.item_container_data.get(
            ids["CommonContainerId"]
        ).get_occupied(1).count)
        self.assertEqual(20, manager.item_container_data.get(
            ids["CommonContainerId"]
        ).get_occupied(0).count)
        self.assertEqual(1, len(session.changes()))
        self.assertEqual("BatchCommand", session.changes()[0]["command"])

    def test_late_validation_failure_rolls_back_entire_batch(self) -> None:
        inventory, ids, manager = inventory_fixtures.InventoryReadTests().make_editor()
        session = inventory._session
        commands = self.make_commands(session, 10_000)
        editor = BatchEditor(session)
        preview = editor.preview(
            session_id=session.session_id,
            expected_revision=0,
            operations=commands,
        )
        with patch.object(
            ItemCatalog, "load_default", return_value=inventory_fixtures.catalog()
        ):
            with self.assertRaises(DomainError) as raised:
                editor.execute(
                    session_id=session.session_id,
                    expected_revision=0,
                    operations=commands,
                    impact_token=preview["impact_token"],
                )
        self.assertEqual("MAX_STACK_EXCEEDED", raised.exception.code)
        self.assertEqual(
            5,
            manager.item_container_data.get(ids["CommonContainerId"])
            .get_occupied(1)
            .count,
        )
        with self.assertRaises(KeyError):
            manager.item_container_data.get(
                ids["CommonContainerId"]
            ).get_occupied(0)
        self.assertEqual(0, session.revision)
        self.assertEqual([], session.changes())

    def test_stale_or_missing_preview_is_rejected_before_mutation(self) -> None:
        inventory, _ids, _manager = (
            inventory_fixtures.InventoryReadTests().make_editor()
        )
        session = inventory._session
        commands = self.make_commands(session, 20)
        with self.assertRaises(DomainError) as raised:
            BatchEditor(session).execute(
                session_id=session.session_id,
                expected_revision=0,
                operations=commands,
                impact_token="stale",
            )
        self.assertEqual("IMPACT_PREVIEW_STALE", raised.exception.code)
        self.assertEqual(0, session.revision)


if __name__ == "__main__":
    unittest.main()
