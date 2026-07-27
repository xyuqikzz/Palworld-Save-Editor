from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from palworld_pal_editor.application.query_service import SaveQueryService
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.core.character_index import CharacterIndex
from palworld_pal_editor.core.pal_objects import PalObjects
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.domain.models import SavePlatform

from tests.unit.test_dynamic_item_data import dynamic_catalog, make_editor
from tests.unit.test_structural_pal_editor import (
    PAL_ID,
    PARTY_ID,
    PLAYER_ID,
    make_manager,
)


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

    def test_overview_reports_normalized_counts_and_pal_anomalies(self) -> None:
        manager, _player, pal = make_manager()
        manager.camp_data = None
        manager.get_expedition_instance_ids = lambda: frozenset({"expedition-1"})
        manager.completable_expeditions = lambda: [{"expedition_id": "expedition-1"}]
        manager.expedition_assignment_status = lambda _pal: "invalid"
        pal._pal_param[
            "MapObjectConcreteInstanceIdAssignedToExpedition"
        ] = PalObjects.Guid("44444444-5555-6666-7777-888888888888")
        manager.container_data.get_container(PARTY_ID).del_pal(PAL_ID)
        manager.character_index = CharacterIndex(manager)
        session = SaveSession.from_loaded_manager(manager, Path("synthetic-save"))

        overview = SaveQueryService(session).overview()

        self.assertEqual(1, overview["totals"]["players"])
        self.assertEqual(1, overview["totals"]["pals"])
        self.assertEqual(1, overview["totals"]["creature_pals"])
        self.assertEqual(1, overview["totals"]["species"])
        self.assertEqual(1, overview["expeditions"]["assigned_pals"])
        self.assertEqual(1, overview["expeditions"]["invalid_assignments"])
        self.assertEqual(1, overview["expeditions"]["completable"])
        self.assertEqual(1, overview["anomalies"]["pal_count"])
        self.assertEqual(
            {
                "EXPEDITION_ASSIGNMENT_INVALID",
                "PAL_DETACHED",
            },
            {
                item["code"]
                for item in overview["anomalies"]["by_code"]
            },
        )
        self.assertEqual(str(PAL_ID), overview["anomalies"]["preview"][0]["pal_id"])
        self.assertEqual(0, session.revision)
        self.assertEqual([], session.changes())

    def test_overview_is_platform_neutral_after_steam_or_wgs_normalization(
        self,
    ) -> None:
        manager, _player, _pal = make_manager()
        manager.camp_data = None
        manager.character_index = CharacterIndex(manager)
        snapshots = []

        for platform in (SavePlatform.STEAM, SavePlatform.XGP):
            session = SimpleNamespace(
                manager=manager,
                revision=0,
                platform=platform,
            )
            snapshots.append(SaveQueryService(session).overview())

        self.assertEqual(snapshots[0], snapshots[1])
        self.assertEqual(1, snapshots[1]["totals"]["players"])
        self.assertEqual(1, snapshots[1]["totals"]["pals"])


if __name__ == "__main__":
    unittest.main()
