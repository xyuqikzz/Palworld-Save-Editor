from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from palworld_save_tools.gvas import GvasFile, GvasHeader
from palworld_save_tools.palsav import compress_gvas_to_sav, decompress_sav_to_gvas
from palworld_save_tools.paltypes import PALWORLD_TYPE_HINTS

from palworld_pal_editor.application.arena_leaderboard_editor import (
    ArenaLeaderboardEditor,
)
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.application.save_writer import SaveWriter
from palworld_pal_editor.core.pal_objects import PalObjects
from palworld_pal_editor.core.save_manager import MAIN_SKIP_PROPERTIES
from palworld_pal_editor.storage.discovery import XgpSourceCatalog
from palworld_pal_editor.storage.xgp import XgpWgsAdapter
from tests.wgs_fixture import make_user_directory


PLAYER_ID = "11111111-2222-3333-4444-555555555555"
INSTANCE_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _player_record(rank_point: int | None) -> dict:
    record = PalObjects.PalSaveParameter(
        INSTANCE_ID,
        PLAYER_ID,
        PalObjects.EMPTY_UUID,
        0,
        PalObjects.EMPTY_UUID,
    )
    record["key"]["PlayerUId"] = PalObjects.Guid(PLAYER_ID)
    parameter = record["value"]["RawData"]["value"]["object"]["SaveParameter"][
        "value"
    ]
    parameter["IsPlayer"] = PalObjects.BoolProperty(True)
    parameter["NickName"] = PalObjects.StrProperty("Arena Player")
    if rank_point is not None:
        parameter["ArenaRankPoint"] = PalObjects.IntProperty(rank_point)
    return record


def _gvas(rank_point: int | None) -> GvasFile:
    character_map = PalObjects.MapProperty(
        "StructProperty",
        "StructProperty",
        "StructProperty",
        "StructProperty",
    )
    character_map["value"].append(_player_record(rank_point))
    gvas = GvasFile()
    gvas.header = GvasHeader.load(
        {
            "magic": 0x53415647,
            "save_game_version": 3,
            "package_file_version_ue4": 522,
            "package_file_version_ue5": 1008,
            "engine_version_major": 5,
            "engine_version_minor": 1,
            "engine_version_patch": 1,
            "engine_version_changelist": 0,
            "engine_version_branch": "synthetic-arena-roundtrip",
            "custom_version_format": 3,
            "custom_versions": [],
            "save_game_class_name": "/Script/Pal.PalWorldSaveGame",
        }
    )
    gvas.properties = {
        "worldSaveData": {
            "type": "StructProperty",
            "struct_type": "PalWorldSaveData",
            "struct_id": PalObjects.EMPTY_UUID,
            "id": None,
            "value": {"CharacterSaveParameterMap": character_map},
        }
    }
    gvas.trailer = b"\0\0\0\0"
    return gvas


def _sav(rank_point: int | None) -> bytes:
    return compress_gvas_to_sav(
        _gvas(rank_point).write(MAIN_SKIP_PROPERTIES), 0x32, zlib=True
    )


class _ArenaManager:
    def __init__(self) -> None:
        self.gvas_file = None
        self._compression_times = None
        self.player_mapping = {}
        self.item_container_data = SimpleNamespace(container_map={})

    def open(self, path, *, lazy_players=False):
        raw, self._compression_times = decompress_sav_to_gvas(
            (Path(path) / "Level.sav").read_bytes()
        )
        self.gvas_file = GvasFile.read(
            raw, PALWORLD_TYPE_HINTS, MAIN_SKIP_PROPERTIES
        )
        records = self.gvas_file.properties["worldSaveData"]["value"][
            "CharacterSaveParameterMap"
        ]["value"]
        self.player_mapping = {}
        for record in records:
            parameter = record["value"]["RawData"]["value"]["object"][
                "SaveParameter"
            ]["value"]
            player_id = str(PalObjects.get_BaseType(record["key"]["PlayerUId"]))
            self.player_mapping[player_id] = SimpleNamespace(
                PlayerUId=PalObjects.get_BaseType(record["key"]["PlayerUId"]),
                InstanceId=PalObjects.get_BaseType(record["key"]["InstanceId"]),
                NickName=PalObjects.get_BaseType(parameter["NickName"]),
                group_id=None,
                _player_param=parameter,
            )
        return self.gvas_file


def _set_and_save(session: SaveSession, rank_point: int) -> None:
    ArenaLeaderboardEditor(session).set_rank_point(
        session_id=session.session_id,
        expected_revision=0,
        player_id=PLAYER_ID,
        rank_point=rank_point,
    )
    SaveWriter().save(
        session,
        session.source if session.platform.value == "steam" else None,
        expected_revision=1,
    )


def _player_rank_point(session: SaveSession) -> int:
    entry = next(
        row
        for row in ArenaLeaderboardEditor(session).leaderboard()["entries"]
        if row.get("player_id") == PLAYER_ID
    )
    return entry["rank_point"]


def test_steam_arena_rank_point_open_edit_save_reopen_roundtrip() -> None:
    with TemporaryDirectory() as temp:
        root = Path(temp) / "steam-world"
        root.mkdir()
        (root / "Level.sav").write_bytes(_sav(50))

        session = SaveSession.open(root, manager=_ArenaManager())
        _set_and_save(session, 900)
        session.close()

        reopened = SaveSession.open(root, manager=_ArenaManager())
        assert _player_rank_point(reopened) == 900
        reopened.close()


def test_steam_missing_arena_rank_point_initialize_save_reopen_roundtrip() -> None:
    with TemporaryDirectory() as temp:
        root = Path(temp) / "steam-world"
        root.mkdir()
        (root / "Level.sav").write_bytes(_sav(None))

        session = SaveSession.open(root, manager=_ArenaManager())
        _set_and_save(session, 321)
        session.close()

        reopened = SaveSession.open(root, manager=_ArenaManager())
        assert _player_rank_point(reopened) == 321
        assert reopened.manager.player_mapping[PLAYER_ID]._player_param[
            "ArenaRankPoint"
        ] == PalObjects.IntProperty(321)
        reopened.close()


def test_wgs_arena_rank_point_open_edit_commit_reopen_roundtrip() -> None:
    with TemporaryDirectory() as temp:
        base = Path(temp)
        root = base / "wgs"
        root.mkdir()
        make_user_directory(
            root,
            "1111111111111111_" + "C" * 32,
            {"A" * 32: {"Level.sav": _sav(50)}},
        )
        catalog = XgpSourceCatalog(roots=(root,))
        source = catalog.discover()[0]
        adapter = XgpWgsAdapter(
            catalog=catalog,
            process_checker=lambda: False,
            workspace_validator=lambda _path: None,
            workspace_root=base / "workspaces",
            backup_root=base / "backups",
            stability_delay=0,
        )

        session = SaveSession.open_storage(source, adapter, manager=_ArenaManager())
        _set_and_save(session, 900)
        session.close()

        reopened = SaveSession.open_storage(source, adapter, manager=_ArenaManager())
        assert _player_rank_point(reopened) == 900
        reopened.close()


def test_wgs_missing_arena_rank_point_initialize_commit_reopen_roundtrip() -> None:
    with TemporaryDirectory() as temp:
        base = Path(temp)
        root = base / "wgs"
        root.mkdir()
        make_user_directory(
            root,
            "1111111111111111_" + "C" * 32,
            {"A" * 32: {"Level.sav": _sav(None)}},
        )
        catalog = XgpSourceCatalog(roots=(root,))
        source = catalog.discover()[0]
        adapter = XgpWgsAdapter(
            catalog=catalog,
            process_checker=lambda: False,
            workspace_validator=lambda _path: None,
            workspace_root=base / "workspaces",
            backup_root=base / "backups",
            stability_delay=0,
        )

        session = SaveSession.open_storage(source, adapter, manager=_ArenaManager())
        _set_and_save(session, 321)
        session.close()

        reopened = SaveSession.open_storage(source, adapter, manager=_ArenaManager())
        assert _player_rank_point(reopened) == 321
        assert reopened.manager.player_mapping[PLAYER_ID]._player_param[
            "ArenaRankPoint"
        ] == PalObjects.IntProperty(321)
        reopened.close()
