from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import unittest

from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.domain.errors import DomainError


class _Player:
    def __init__(self, player_id: str, alias: str = "InventoryInfo") -> None:
        self.PlayerUId = player_id
        self.InstanceId = f"instance-{player_id}"
        self.NickName = f"Player {player_id}"
        self.Level = 10
        self._player_save_data = {alias: {"value": {"marker": player_id}}}


class SaveSessionTests(unittest.TestCase):
    def make_session(self) -> SaveSession:
        header = SimpleNamespace(
            save_game_version=3,
            engine_version_major=5,
            engine_version_minor=1,
            engine_version_patch=1,
            engine_version_changelist=123,
        )
        manager = SimpleNamespace(
            gvas_file=SimpleNamespace(header=header),
            player_mapping={"a": _Player("a")},
        )
        return SaveSession.from_loaded_manager(manager, Path("synthetic-save"))

    def test_summary_and_reads_do_not_create_changes(self) -> None:
        session = self.make_session()
        self.assertEqual(0, session.summary().revision)
        self.assertEqual(1, len(session.list_players()))
        self.assertEqual([], session.changes())
        self.assertEqual("InventoryInfo", session.compatibility().field_aliases["a"])

    def test_successful_atomic_command_increments_once(self) -> None:
        session = self.make_session()
        state = {"count": 5, "unknown": [1, 2, 3]}
        entry = session.apply_atomic(
            session_id=session.session_id,
            expected_revision=0,
            command="SyntheticUpdate",
            target={"slot_index": 1},
            snapshot=lambda: deepcopy(state),
            restore=lambda old: (state.clear(), state.update(old)),
            before=lambda: dict(state),
            mutate=lambda: state.update(count=6),
            validate=lambda: None,
            after=lambda: dict(state),
            affected_records=("synthetic:slot:1",),
        )
        self.assertEqual(1, session.revision)
        self.assertEqual(1, len(session.changes()))
        self.assertEqual(1, entry.revision_after)
        self.assertEqual([1, 2, 3], state["unknown"])

    def test_failed_atomic_command_restores_state_and_revision(self) -> None:
        session = self.make_session()
        state = {"count": 5, "unknown": [1, 2, 3]}

        def fail() -> None:
            raise DomainError("INVARIANT_VIOLATION", "synthetic failure")

        with self.assertRaises(DomainError):
            session.apply_atomic(
                session_id=session.session_id,
                expected_revision=0,
                command="SyntheticUpdate",
                target={"slot_index": 1},
                snapshot=lambda: deepcopy(state),
                restore=lambda old: (state.clear(), state.update(old)),
                before=lambda: dict(state),
                mutate=lambda: state.update(count=6),
                validate=fail,
                after=lambda: dict(state),
                affected_records=("synthetic:slot:1",),
            )
        self.assertEqual({"count": 5, "unknown": [1, 2, 3]}, state)
        self.assertEqual(0, session.revision)
        self.assertEqual([], session.changes())

    def test_stale_revision_is_rejected_before_mutation(self) -> None:
        session = self.make_session()
        state = {"count": 5}
        with self.assertRaisesRegex(DomainError, "changed") as raised:
            session.apply_atomic(
                session_id=session.session_id,
                expected_revision=9,
                command="SyntheticUpdate",
                target={},
                snapshot=lambda: deepcopy(state),
                restore=lambda old: state.update(old),
                before=lambda: dict(state),
                mutate=lambda: state.update(count=6),
                validate=lambda: None,
                after=lambda: dict(state),
                affected_records=(),
            )
        self.assertEqual("STALE_REVISION", raised.exception.code)
        self.assertEqual({"count": 5}, state)

    def test_conflicting_inventory_aliases_disable_static_write(self) -> None:
        session = self.make_session()
        player = session.manager.player_mapping["a"]
        player._player_save_data["inventoryInfo"] = {"value": {"marker": "other"}}
        compatibility = SaveSession.from_loaded_manager(
            session.manager, Path("synthetic-save")
        ).compatibility()
        self.assertFalse(compatibility.capabilities["inventory.write.static"].writable)
        self.assertIn(
            "COMPATIBILITY_FIELD_AMBIGUOUS",
            [warning["code"] for warning in compatibility.warnings],
        )

    def test_mark_saved_allows_later_contiguous_change(self) -> None:
        session = self.make_session()
        state = {"count": 5}

        def apply(expected_revision: int, count: int) -> None:
            session.apply_atomic(
                session_id=session.session_id,
                expected_revision=expected_revision,
                command="SyntheticUpdate",
                target={},
                snapshot=lambda: deepcopy(state),
                restore=lambda old: (state.clear(), state.update(old)),
                before=lambda: dict(state),
                mutate=lambda: state.update(count=count),
                validate=lambda: None,
                after=lambda: dict(state),
                affected_records=("synthetic",),
            )

        apply(0, 6)
        session.mark_saved(1)
        apply(1, 7)
        self.assertEqual(2, session.revision)
        self.assertEqual(1, len(session.changes()))


if __name__ == "__main__":
    unittest.main()
