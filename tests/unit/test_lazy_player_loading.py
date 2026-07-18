from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest

from palworld_pal_editor.application.character_editor import CharacterEditor
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.core.lazy_player_entity import LazyPlayerEntity
from palworld_pal_editor.core.pal_objects import PalObjects, toUUID
from palworld_pal_editor.domain.commands import UpdatePlayerProgression
from palworld_pal_editor.domain.errors import DomainError


PLAYER_ID = toUUID("11111111-1111-1111-1111-111111111111")
INSTANCE_ID = toUUID("22222222-2222-2222-2222-222222222222")
GROUP_ID = toUUID("33333333-3333-3333-3333-333333333333")


def player_object() -> dict:
    value = PalObjects.PalSaveParameter(
        INSTANCE_ID, PLAYER_ID, PalObjects.EMPTY_UUID, 0, GROUP_ID
    )
    value["key"]["PlayerUId"] = PalObjects.Guid(PLAYER_ID)
    parameter = value["value"]["RawData"]["value"]["object"]["SaveParameter"][
        "value"
    ]
    parameter["IsPlayer"] = PalObjects.BoolProperty(True)
    parameter["NickName"] = PalObjects.StrProperty("Lazy Player")
    parameter["Level"] = PalObjects.ByteProperty(12)
    parameter["Exp"] = PalObjects.Int64Property(250)
    return value


def player_gvas():
    return SimpleNamespace(
        properties={
            "SaveData": {
                "value": {
                    "IndividualId": {
                        "value": {
                            "PlayerUId": PalObjects.Guid(PLAYER_ID),
                            "InstanceId": PalObjects.Guid(INSTANCE_ID),
                        }
                    },
                    "InventoryInfo": {"value": {}},
                    "TechnologyPoint": PalObjects.IntProperty(7),
                    "bossTechnologyPoint": PalObjects.IntProperty(2),
                    "UnlockedRecipeTechnologyNames": PalObjects.ArrayProperty(
                        "NameProperty", {"values": []}
                    ),
                }
            }
        }
    )


class LazyPlayerLoadingTests(unittest.TestCase):
    def make_session(self):
        loads: list[int] = []

        def loader():
            loads.append(1)
            return player_gvas(), 0

        player = LazyPlayerEntity(GROUP_ID, player_object(), {}, loader)
        manager = SimpleNamespace(
            gvas_file=SimpleNamespace(header=None),
            player_mapping={str(PLAYER_ID): player},
            get_player=lambda player_id: (
                player if str(player_id) == str(PLAYER_ID) else None
            ),
            player_file_load_count=0,
            player_file_load_seconds={},
        )
        return (
            SaveSession.from_loaded_manager(manager, Path("synthetic-save")),
            player,
            loads,
        )

    def test_summary_is_cold_and_detail_is_cached(self) -> None:
        session, player, loads = self.make_session()
        self.assertEqual("Lazy Player", session.list_players()[0].name)
        self.assertEqual(0, len(loads))
        self.assertEqual(0, session.performance_metrics()["player_files_loaded"])

        self.assertEqual(7, session.load_player(str(PLAYER_ID)).TechnologyPoint)
        self.assertEqual(7, player.TechnologyPoint)
        self.assertEqual(1, len(loads))
        self.assertEqual(1, session.performance_metrics()["player_files_loaded"])

        session.invalidate_player_cache(str(PLAYER_ID))
        self.assertFalse(player.is_loaded)
        self.assertEqual(7, player.TechnologyPoint)
        self.assertEqual(2, len(loads))

    def test_dirty_player_detail_cannot_be_evicted(self) -> None:
        session, _player, loads = self.make_session()
        CharacterEditor(session).execute(
            UpdatePlayerProgression(
                session_id=session.session_id,
                expected_revision=0,
                player_id=str(PLAYER_ID),
                technology_points=9,
            )
        )
        self.assertEqual(1, len(loads))
        with self.assertRaises(DomainError) as raised:
            session.invalidate_player_cache(str(PLAYER_ID))
        self.assertEqual("PLAYER_CACHE_DIRTY", raised.exception.code)


if __name__ == "__main__":
    unittest.main()
