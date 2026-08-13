from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from palworld_save_tools.gvas import GvasFile, GvasHeader
from palworld_save_tools.palsav import compress_gvas_to_sav, decompress_sav_to_gvas
from palworld_save_tools.paltypes import PALWORLD_TYPE_HINTS

from palworld_pal_editor.application.character_editor import CharacterEditor
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.application.save_writer import SaveWriter
from palworld_pal_editor.core.pal_objects import PalObjects
from palworld_pal_editor.core.save_manager import MAIN_SKIP_PROPERTIES
from palworld_pal_editor.domain.commands import UpdatePlayerConsumableBonuses
from palworld_pal_editor.domain.player_consumable_bonuses import (
    inspect_consumable_bonus_values,
)
from palworld_pal_editor.storage.discovery import XgpSourceCatalog
from palworld_pal_editor.storage.xgp import XgpWgsAdapter
from tests.wgs_fixture import make_user_directory


PLAYER_ID = "11111111-2222-3333-4444-555555555555"
INSTANCE_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _player_record() -> dict:
    record = PalObjects.PalSaveParameter(
        INSTANCE_ID,
        PLAYER_ID,
        PalObjects.EMPTY_UUID,
        0,
        PalObjects.EMPTY_UUID,
    )
    record["key"]["PlayerUId"] = PalObjects.Guid(PLAYER_ID)
    parameter = record["value"]["RawData"]["value"]["object"][
        "SaveParameter"
    ]["value"]
    parameter["IsPlayer"] = PalObjects.BoolProperty(True)
    parameter["NickName"] = PalObjects.StrProperty("Consumable Player")
    rows = PalObjects.get_ArrayProperty(parameter["GotExStatusPointList"])
    PalObjects.set_BaseType(rows[0]["StatusPoint"], 28)
    rows.append(PalObjects.StatusPointStruct("future-field", 7))
    return record


def _gvas() -> GvasFile:
    character_map = PalObjects.MapProperty(
        "StructProperty",
        "StructProperty",
        "StructProperty",
        "StructProperty",
    )
    character_map["value"].append(_player_record())
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
            "engine_version_branch": "synthetic-consumable-bonus-roundtrip",
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


def _sav() -> bytes:
    return compress_gvas_to_sav(
        _gvas().write(MAIN_SKIP_PROPERTIES), 0x32, zlib=True
    )


class _ConsumableManager:
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
        record = self.gvas_file.properties["worldSaveData"]["value"][
            "CharacterSaveParameterMap"
        ]["value"][0]
        parameter = record["value"]["RawData"]["value"]["object"][
            "SaveParameter"
        ]["value"]
        player_id = str(PalObjects.get_BaseType(record["key"]["PlayerUId"]))
        self.player_mapping = {
            player_id: SimpleNamespace(
                PlayerUId=PalObjects.get_BaseType(record["key"]["PlayerUId"]),
                InstanceId=PalObjects.get_BaseType(record["key"]["InstanceId"]),
                NickName=PalObjects.get_BaseType(parameter["NickName"]),
                group_id=None,
                _player_param=parameter,
                _player_save_data={},
            )
        }
        return self.gvas_file

    def get_player(self, player_id):
        return self.player_mapping.get(str(player_id))


def _update_and_save(session: SaveSession) -> object:
    CharacterEditor(session).execute(
        UpdatePlayerConsumableBonuses(
            session_id=session.session_id,
            expected_revision=session.revision,
            player_id=PLAYER_ID,
            values={"max_hp": 35},
        )
    )
    return SaveWriter().save(
        session,
        session.source if session.platform.value == "steam" else None,
        session.revision,
    )


def _assert_reopened(session: SaveSession) -> None:
    player = session.manager.get_player(PLAYER_ID)
    assert inspect_consumable_bonus_values(player._player_param)["max_hp"] == 35
    rows = PalObjects.get_ArrayProperty(player._player_param["GotExStatusPointList"])
    assert PalObjects.get_BaseType(rows[-1]["StatusName"]) == "future-field"
    assert PalObjects.get_BaseType(rows[-1]["StatusPoint"]) == 7


def test_steam_consumable_bonus_open_edit_save_reopen_roundtrip() -> None:
    with TemporaryDirectory() as temp:
        root = Path(temp) / "steam-world"
        root.mkdir()
        (root / "Level.sav").write_bytes(_sav())

        session = SaveSession.open(root, manager=_ConsumableManager())
        result = _update_and_save(session)
        session.close()

        reopened = SaveSession.open(root, manager=_ConsumableManager())
        _assert_reopened(reopened)
        reopened.close()

        assert result.platform == "steam"
        assert result.target_reload_verified is True
        assert result.written_files == ("Level.sav",)


def test_wgs_consumable_bonus_open_edit_save_reopen_roundtrip() -> None:
    with TemporaryDirectory() as temp:
        base = Path(temp)
        root = base / "wgs"
        root.mkdir()
        make_user_directory(
            root,
            "1111111111111111_" + "C" * 32,
            {"A" * 32: {"Level.sav": _sav()}},
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

        session = SaveSession.open_storage(
            source, adapter, manager=_ConsumableManager()
        )
        result = _update_and_save(session)
        session.close()

        reopened_adapter = XgpWgsAdapter(
            catalog=catalog,
            process_checker=lambda: False,
            workspace_validator=lambda _path: None,
            workspace_root=base / "reopened-workspaces",
            backup_root=base / "reopened-backups",
            stability_delay=0,
        )
        reopened = SaveSession.open_storage(
            source, reopened_adapter, manager=_ConsumableManager()
        )
        _assert_reopened(reopened)
        reopened.close()

        assert result.platform == "xgp"
        assert result.source_reloaded is True
        assert result.target_reload_verified is True
        assert result.cloud_sync_verified is False
        assert result.backup_path is not None
        assert result.written_files == ("Level.sav",)
