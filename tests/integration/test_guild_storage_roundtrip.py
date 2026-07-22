from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

from palworld_save_tools.gvas import GvasFile, GvasHeader
from palworld_save_tools.palsav import compress_gvas_to_sav, decompress_sav_to_gvas
from palworld_save_tools.paltypes import PALWORLD_TYPE_HINTS

from palworld_pal_editor.application.guild_editor import GuildEditor
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.application.save_writer import SaveWriter
from palworld_pal_editor.core.pal_objects import PalObjects
from palworld_pal_editor.core.save_manager import MAIN_SKIP_PROPERTIES
from palworld_pal_editor.domain.commands import UpdateGuildName
from palworld_pal_editor.storage.discovery import XgpSourceCatalog
from palworld_pal_editor.storage.xgp import XgpWgsAdapter
from tests.wgs_fixture import make_user_directory


GUILD_ID = "11111111-1111-1111-1111-111111111111"


def _gvas(name: str) -> GvasFile:
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
    gvas.properties = {"SyntheticGuildName": PalObjects.StrProperty(name)}
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


class _SyntheticGuild:
    """Binds GuildEditor to one serialized synthetic string property."""

    group_id = GUILD_ID

    def __init__(self, gvas: GvasFile) -> None:
        self._property = gvas.properties["SyntheticGuildName"]
        self._group_param = {"guild_name": self._property["value"]}

    @property
    def guild_name(self) -> str:
        return self._group_param["guild_name"]

    def set_guild_name(self, name: str) -> None:
        self._group_param["guild_name"] = name
        self._property["value"] = name

    def snapshot(self):
        return deepcopy(self._group_param)

    def restore(self, snapshot) -> None:
        self._group_param.clear()
        self._group_param.update(deepcopy(snapshot))
        self._property["value"] = self._group_param["guild_name"]


class _Groups:
    def __init__(self, group: _SyntheticGuild) -> None:
        self.group = group

    def get_group(self, group_id):
        return self.group if str(group_id) == GUILD_ID else None


class _Manager:
    def __init__(self) -> None:
        self.gvas_file = None
        self.group_data = None
        self.player_mapping = {}
        self.item_container_data = None
        self._compression_times = 0x32

    def open(self, path, *, lazy_players=False):
        self.gvas_file, self._compression_times = _read_gvas(Path(path) / "Level.sav")
        self.group_data = _Groups(_SyntheticGuild(self.gvas_file))
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
