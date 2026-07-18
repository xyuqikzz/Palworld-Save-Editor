from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch

from palworld_pal_editor.application.query_service import SaveQueryService
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.domain.errors import DomainError

from tests.unit.test_dynamic_item_data import dynamic_catalog, make_editor
from tests.unit.test_structural_pal_editor import PLAYER_ID, make_manager


class SaveQueryServiceTests(unittest.TestCase):
    def test_player_and_pal_filters_are_read_only(self) -> None:
        manager, _player, _pal = make_manager()
        session = SaveSession.from_loaded_manager(manager, Path("synthetic-save"))
        service = SaveQueryService(session)

        players = service.players(text="player one", sort_by="level")
        self.assertEqual(str(PLAYER_ID), players[0]["player_id"])
        self.assertEqual(1, players[0]["pal_count"])

        pals = service.pals(
            player_id=str(PLAYER_ID),
            text="sheep",
            element="Neutral",
            min_level=1,
            boss=False,
            rare=False,
            container_state="owner_container",
            sort_by="internal_id",
        )
        self.assertEqual("SheepBall", pals[0]["internal_id"])
        self.assertEqual(0, session.revision)
        self.assertEqual([], session.changes())

    def test_item_filters_include_empty_slots_without_mutation(self) -> None:
        _editor, session, _manager, _container_id = make_editor()
        with patch(
            "palworld_pal_editor.application.inventory_editor.ItemCatalog.load_default",
            return_value=dynamic_catalog(),
        ):
            service = SaveQueryService(session)
            occupied = service.items(
                "player-dynamic", dynamic_kind="weapon", state="occupied"
            )
            empty = service.items("player-dynamic", state="empty")
        self.assertEqual("Weapon_Test", occupied[0]["internal_id"])
        self.assertEqual(1, empty[0]["slot_index"])
        self.assertEqual(0, session.revision)

    def test_unknown_sort_is_rejected(self) -> None:
        manager, _player, _pal = make_manager()
        session = SaveSession.from_loaded_manager(manager, Path("synthetic-save"))
        with self.assertRaises(DomainError) as raised:
            SaveQueryService(session).players(sort_by="gvas_path")
        self.assertEqual("INVALID_SORT_FIELD", raised.exception.code)


if __name__ == "__main__":
    unittest.main()
