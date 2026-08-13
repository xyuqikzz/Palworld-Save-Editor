from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from palworld_save_tools.gvas import GvasFile, GvasHeader
from palworld_save_tools.palsav import compress_gvas_to_sav, decompress_sav_to_gvas
from palworld_save_tools.paltypes import PALWORLD_TYPE_HINTS

from palworld_pal_editor.application.guild_base_editor import GuildBaseEditor
from palworld_pal_editor.application.guild_editor import GuildEditor
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.application.save_writer import SaveWriter
from palworld_pal_editor.core.group_data import GroupData
from palworld_pal_editor.core.pal_objects import PalObjects, toUUID
from palworld_pal_editor.core.save_manager import MAIN_SKIP_PROPERTIES
from palworld_pal_editor.domain.commands import (
    UpdateGuildBaseCampLevel,
    UpdateGuildName,
    UpdateGuildOwner,
)
from palworld_pal_editor.storage.discovery import XgpSourceCatalog
from palworld_pal_editor.storage.xgp import XgpWgsAdapter
from tests.wgs_fixture import make_user_directory


GUILD_ID = "11111111-1111-1111-1111-111111111111"
OWNER_ID = "aaaaaaaa-1111-2222-3333-444444444444"
MEMBER_ID = "bbbbbbbb-1111-2222-3333-444444444444"


def _gvas(name: str, *, level: int = 1) -> GvasFile:
    group_map = PalObjects.MapProperty(
        "StructProperty",
        "StructProperty",
        "Guid",
        "StructProperty",
    )
    group_map["custom_type"] = ".worldSaveData.GroupSaveDataMap"
    group_map["value"].append(
        {
            "key": toUUID(GUILD_ID),
            "value": {
                "GroupType": PalObjects.EnumProperty(
                    "EPalGroupType", "EPalGroupType::Guild"
                ),
                "RawData": PalObjects.ArrayProperty(
                    "ByteProperty",
                    {
                        "group_type": "EPalGroupType::Guild",
                        "group_id": toUUID(GUILD_ID),
                        "group_name": "Guild",
                        "individual_character_handle_ids": [],
                        "org_type": 0,
                        "leading_bytes": [0, 0, 0, 0],
                        "base_ids": [],
                        "unknown_1": 0,
                        "base_camp_level": level,
                        "map_object_instance_ids_base_camp_points": [],
                        "guild_name": name,
                        "last_guild_name_modifier_player_uid": (
                            PalObjects.EMPTY_UUID
                        ),
                        "guild_format": "1.0",
                        "guild_marker_count": 0,
                        "guild_marker_data": [],
                        "guild_chest_allowed_roles": [1, 2, 3],
                        "unknown_i32": 0,
                        "admin_player_uid": toUUID(OWNER_ID),
                        "players": [
                            {
                                "player_uid": toUUID(OWNER_ID),
                                "player_info": {
                                    "last_online_real_time": 10,
                                    "player_name": "Owner",
                                    "role": 1,
                                },
                            },
                            {
                                "player_uid": toUUID(MEMBER_ID),
                                "player_info": {
                                    "last_online_real_time": 5,
                                    "player_name": "Member",
                                    "role": 3,
                                },
                            },
                        ],
                        "role_permissions": [
                            {"role": 2, "permissions": [0, 3, 4]},
                            {"role": 3, "permissions": [4]},
                            {"role": 4, "permissions": []},
                        ],
                        "trailing_bytes": [0, 0, 0, 0],
                    },
                ),
            },
        }
    )
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
            "engine_version_branch": "synthetic-guild-roundtrip",
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
            "value": {"GroupSaveDataMap": group_map},
        }
    }
    gvas.trailer = b"\0\0\0\0"
    return gvas


def _sav(gvas: GvasFile) -> bytes:
    return compress_gvas_to_sav(gvas.write(MAIN_SKIP_PROPERTIES), 0x32, zlib=True)


def _read_gvas(path: Path) -> tuple[GvasFile, int]:
    raw, compression = decompress_sav_to_gvas(path.read_bytes())
    return (
        GvasFile.read(raw, PALWORLD_TYPE_HINTS, MAIN_SKIP_PROPERTIES),
        compression,
    )


class _Manager:
    def __init__(self) -> None:
        self.gvas_file = None
        self.group_data = None
        self.player_mapping = {}
        self.item_container_data = None
        self._compression_times = 0x32

    def open(self, path, *, lazy_players=False):
        self.gvas_file, self._compression_times = _read_gvas(Path(path) / "Level.sav")
        self.group_data = GroupData(self.gvas_file)
        return self.gvas_file


def _rename(session: SaveSession, name: str) -> None:
    GuildEditor(session).execute(
        UpdateGuildName(
            session_id=session.session_id,
            expected_revision=session.revision,
            guild_id=GUILD_ID,
            name=name,
        )
    )


def _set_owner(session: SaveSession, player_id: str) -> None:
    GuildEditor(session).execute(
        UpdateGuildOwner(
            session_id=session.session_id,
            expected_revision=session.revision,
            guild_id=GUILD_ID,
            player_id=player_id,
        )
    )


def _set_level(session: SaveSession, level: int) -> None:
    GuildBaseEditor(session).execute(
        UpdateGuildBaseCampLevel(
            session_id=session.session_id,
            expected_revision=session.revision,
            guild_id=GUILD_ID,
            level=level,
            confirm_lowering=True,
        )
    )


def test_synthetic_steam_guild_name_open_edit_save_reopen(tmp_path: Path) -> None:
    source = tmp_path / "steam"
    source.mkdir()
    (source / "Level.sav").write_bytes(_sav(_gvas("Builders")))

    session = SaveSession.open(source, manager=_Manager())
    _rename(session, "Steam Builders")
    result = SaveWriter().save(session, source, session.revision)
    session.close()

    reopened = SaveSession.open(source, manager=_Manager())
    assert reopened.manager.group_data.get_group(GUILD_ID).guild_name == "Steam Builders"
    reopened.close()
    assert result.platform == "steam"
    assert result.target_reload_verified is True
    assert result.written_files == ("Level.sav",)


def test_synthetic_wgs_guild_name_open_edit_save_reopen() -> None:
    with TemporaryDirectory(prefix="g") as temp:
        base = Path(temp)
        root = base / "wgs"
        root.mkdir()
        make_user_directory(
            root,
            "1111111111111111_" + "C" * 32,
            {"A" * 32: {"Level.sav": _sav(_gvas("Builders"))}},
        )
        catalog = XgpSourceCatalog(roots=(root,))
        adapter = XgpWgsAdapter(
            catalog=catalog,
            process_checker=lambda: False,
            workspace_validator=lambda _path: None,
            workspace_root=base / "workspaces",
            backup_root=base / "backups",
            stability_delay=0,
        )
        session = SaveSession.open_storage(
            catalog.discover()[0], adapter, manager=_Manager()
        )

        _rename(session, "WGS Builders")
        result = SaveWriter().save(session, None, session.revision)
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
            catalog.discover()[0], reopened_adapter, manager=_Manager()
        )
        assert (
            reopened.manager.group_data.get_group(GUILD_ID).guild_name
            == "WGS Builders"
        )
        reopened.close()
        assert result.platform == "xgp"
        assert result.source_reloaded is True
        assert result.target_reload_verified is True
        assert result.cloud_sync_verified is False
        assert result.written_files == ("Level.sav",)


def test_synthetic_steam_guild_owner_open_edit_save_reopen(
    tmp_path: Path,
) -> None:
    source = tmp_path / "steam-owner"
    source.mkdir()
    (source / "Level.sav").write_bytes(_sav(_gvas("Builders")))

    session = SaveSession.open(source, manager=_Manager())
    _set_owner(session, MEMBER_ID)
    result = SaveWriter().save(session, source, session.revision)
    session.close()

    reopened = SaveSession.open(source, manager=_Manager())
    group = reopened.manager.group_data.get_group(GUILD_ID)
    assert str(group.admin_player_uid) == MEMBER_ID
    assert {
        str(player_uid): role
        for player_uid, _name, role in group.guild_members
    } == {
        OWNER_ID: 2,
        MEMBER_ID: 1,
    }
    reopened.close()
    assert result.platform == "steam"
    assert result.target_reload_verified is True
    assert result.written_files == ("Level.sav",)


def test_synthetic_wgs_guild_owner_open_edit_save_reopen() -> None:
    with TemporaryDirectory(prefix="g") as temp:
        base = Path(temp)
        root = base / "wgs"
        root.mkdir()
        make_user_directory(
            root,
            "1111111111111111_" + "D" * 32,
            {"B" * 32: {"Level.sav": _sav(_gvas("Builders"))}},
        )
        catalog = XgpSourceCatalog(roots=(root,))
        adapter = XgpWgsAdapter(
            catalog=catalog,
            process_checker=lambda: False,
            workspace_validator=lambda _path: None,
            workspace_root=base / "workspaces",
            backup_root=base / "backups",
            stability_delay=0,
        )
        session = SaveSession.open_storage(
            catalog.discover()[0], adapter, manager=_Manager()
        )

        _set_owner(session, MEMBER_ID)
        result = SaveWriter().save(session, None, session.revision)
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
            catalog.discover()[0], reopened_adapter, manager=_Manager()
        )
        group = reopened.manager.group_data.get_group(GUILD_ID)
        assert str(group.admin_player_uid) == MEMBER_ID
        assert {
            str(player_uid): role
            for player_uid, _name, role in group.guild_members
        } == {
            OWNER_ID: 2,
            MEMBER_ID: 1,
        }
        reopened.close()
        assert result.platform == "xgp"
        assert result.source_reloaded is True
        assert result.target_reload_verified is True
        assert result.cloud_sync_verified is False
        assert result.written_files == ("Level.sav",)


def test_synthetic_steam_out_of_range_level_repair_save_reopen(
    tmp_path: Path,
) -> None:
    source = tmp_path / "steam-level"
    source.mkdir()
    (source / "Level.sav").write_bytes(_sav(_gvas("Builders", level=60)))

    session = SaveSession.open(source, manager=_Manager())
    _set_level(session, 35)
    result = SaveWriter().save(session, source, session.revision)
    session.close()

    reopened = SaveSession.open(source, manager=_Manager())
    assert reopened.manager.group_data.get_group(GUILD_ID).base_camp_level == 35
    reopened.close()
    assert result.platform == "steam"
    assert result.target_reload_verified is True
    assert result.written_files == ("Level.sav",)


def test_synthetic_wgs_level_lower_save_reopen() -> None:
    with TemporaryDirectory(prefix="g") as temp:
        base = Path(temp)
        root = base / "wgs"
        root.mkdir()
        make_user_directory(
            root,
            "1111111111111111_" + "E" * 32,
            {"C" * 32: {"Level.sav": _sav(_gvas("Builders", level=14))}},
        )
        catalog = XgpSourceCatalog(roots=(root,))
        adapter = XgpWgsAdapter(
            catalog=catalog,
            process_checker=lambda: False,
            workspace_validator=lambda _path: None,
            workspace_root=base / "workspaces",
            backup_root=base / "backups",
            stability_delay=0,
        )
        session = SaveSession.open_storage(
            catalog.discover()[0], adapter, manager=_Manager()
        )

        _set_level(session, 1)
        result = SaveWriter().save(session, None, session.revision)
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
            catalog.discover()[0], reopened_adapter, manager=_Manager()
        )
        assert reopened.manager.group_data.get_group(GUILD_ID).base_camp_level == 1
        reopened.close()
        assert result.platform == "xgp"
        assert result.source_reloaded is True
        assert result.target_reload_verified is True
        assert result.cloud_sync_verified is False
        assert result.written_files == ("Level.sav",)
