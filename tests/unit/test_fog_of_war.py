from __future__ import annotations

import copy
import errno
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pytest

from palworld_save_tools.gvas import GvasFile, GvasHeader
from palworld_save_tools.palsav import compress_gvas_to_sav, decompress_sav_to_gvas
from palworld_save_tools.paltypes import PALWORLD_TYPE_HINTS
from palworld_pal_editor.application.fog_of_war_editor import FogOfWarEditor
from palworld_pal_editor.application.local_data import (
    CLEARED_PIXEL,
    FOG_CLEAR_CONFIRMATION,
    FOG_RESET_CONFIRMATION,
    LOCAL_DATA_CUSTOM_PROPERTIES,
    LocalDataDocument,
    UNEXPLORED_PIXEL,
)
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.application.save_writer import SaveWriter
from palworld_pal_editor.core.pal_objects import PalObjects
from palworld_pal_editor.core.save_manager import MAIN_SKIP_PROPERTIES
from palworld_pal_editor.domain.commands import ClearFogOfWar, ResetFogOfWar
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.storage.discovery import XgpSourceCatalog
from palworld_pal_editor.storage.xgp import XgpWgsAdapter
from tests.wgs_fixture import make_user_directory


MAIN_MASK_BYTES = 4_194_304
TREE_MASK_BYTES = 1_048_576


def _header(class_name: str) -> GvasHeader:
    return GvasHeader.load(
        {
            "magic": 0x53415647,
            "save_game_version": 3,
            "package_file_version_ue4": 522,
            "package_file_version_ue5": 1008,
            "engine_version_major": 5,
            "engine_version_minor": 1,
            "engine_version_patch": 1,
            "engine_version_changelist": 0,
            "engine_version_branch": "synthetic-fog-test",
            "custom_version_format": 3,
            "custom_versions": [],
            "save_game_class_name": class_name,
        }
    )


def _byte_mask(byte_length: int, *, explored: bool) -> dict:
    values = UNEXPLORED_PIXEL * (byte_length // 4)
    if explored:
        values = (0, 0, 0, 0) + values[4:]
    return {
        "array_type": "ByteProperty",
        "id": None,
        "type": "ArrayProperty",
        "value": {"values": values},
    }


def _local_gvas(format_name: str, *, explored: bool = True) -> GvasFile:
    gvas = GvasFile()
    gvas.header = _header("/Script/Pal.PalLocalWorldSaveGame")
    save_data = {
        "PreservedCounter": PalObjects.IntProperty(73),
        "Local_HiddenLocationFlagMap": PalObjects.StrProperty("preserve-hidden"),
        "Local_ShowSkyIslandCloudOnWorldMapUI": PalObjects.BoolProperty(True),
    }
    if format_name == "current":
        save_data["WorldMapUISaveDataMap"] = {
            "key_type": "NameProperty",
            "value_type": "StructProperty",
            "key_struct_type": None,
            "value_struct_type": "StructProperty",
            "id": None,
            "type": "MapProperty",
            "value": [
                {
                    "key": "MainMap",
                    "value": {
                        "MaskTextureData": _byte_mask(
                            MAIN_MASK_BYTES,
                            explored=explored,
                        )
                    },
                },
                {
                    "key": "Tree",
                    "value": {
                        "MaskTextureData": _byte_mask(
                            TREE_MASK_BYTES,
                            explored=explored,
                        )
                    },
                },
            ],
        }
    elif format_name == "legacy":
        save_data["WorldMapMaskTextureV4"] = _byte_mask(
            MAIN_MASK_BYTES,
            explored=explored,
        )
    elif format_name != "unknown":
        raise ValueError(format_name)
    gvas.properties = {
        "SaveData": {
            "struct_type": "PalLocalSaveData",
            "struct_id": PalObjects.EMPTY_UUID,
            "id": None,
            "type": "StructProperty",
            "value": save_data,
        }
    }
    gvas.trailer = b"\x00\x00\x00\x00"
    return gvas


def _level_gvas(counter: int = 1) -> GvasFile:
    gvas = GvasFile()
    gvas.header = _header("/Script/Pal.PalWorldSaveGame")
    gvas.properties = {"Counter": PalObjects.IntProperty(counter)}
    gvas.trailer = b"\x00\x00\x00\x00"
    return gvas


def _sav(gvas: GvasFile, *, local_data: bool = False) -> bytes:
    custom = LOCAL_DATA_CUSTOM_PROPERTIES if local_data else MAIN_SKIP_PROPERTIES
    return compress_gvas_to_sav(gvas.write(custom), 0x32, zlib=True)


def _cnk0_payload(sav: bytes) -> bytes:
    return b"\x32\x5f\x00\x00" + (1).to_bytes(4, "little") + b"CNK0" + sav


def _manager(level: GvasFile | None = None):
    return SimpleNamespace(
        gvas_file=level or _level_gvas(),
        _compression_times=0x32,
        player_mapping={},
        item_container_data=None,
    )


def _make_steam_world(
    root: Path,
    *,
    format_name: str = "current",
    include_local_data: bool = True,
) -> tuple[bytes, bytes | None]:
    root.mkdir()
    level_bytes = _sav(_level_gvas())
    (root / "Level.sav").write_bytes(level_bytes)
    local_bytes = None
    if include_local_data:
        local_bytes = _sav(
            _local_gvas(format_name, explored=True),
            local_data=True,
        )
        (root / "LocalData.sav").write_bytes(local_bytes)
    return level_bytes, local_bytes


def _command(session: SaveSession, confirmation: str = FOG_RESET_CONFIRMATION):
    return ResetFogOfWar(
        session_id=session.session_id,
        expected_revision=session.revision,
        confirmation=confirmation,
    )


def _clear_command(
    session: SaveSession,
    confirmation: str = FOG_CLEAR_CONFIRMATION,
):
    return ClearFogOfWar(
        session_id=session.session_id,
        expected_revision=session.revision,
        confirmation=confirmation,
    )


def _select_local_data(
    session: SaveSession,
    path: Path | None = None,
) -> dict:
    return session.select_local_data(
        session_id=session.session_id,
        expected_revision=session.revision,
        path=path,
    )


def _mask_neutral_properties(document: LocalDataDocument) -> dict:
    return document._properties_without_masks()


@pytest.mark.parametrize(
    ("format_name", "expected_format", "expected_maps"),
    [
        ("current", "WorldMapUISaveDataMap", ("MainMap", "Tree")),
        ("legacy", "WorldMapMaskTextureV4", ("MainMap",)),
    ],
)
def test_new_and_legacy_local_data_reset_roundtrip_preserves_every_other_field(
    tmp_path: Path,
    format_name: str,
    expected_format: str,
    expected_maps: tuple[str, ...],
) -> None:
    source = tmp_path / "LocalData.sav"
    source.write_bytes(
        _sav(_local_gvas(format_name, explored=True), local_data=True)
    )
    document = LocalDataDocument.open_file(source)
    before = _mask_neutral_properties(document)

    assert document.capability.available is True
    assert document.capability.format == expected_format
    assert document.capability.maps == expected_maps
    assert document.is_fully_unexplored() is False

    document.reset_fog_of_war()
    document.validate_reset()
    staged = tmp_path / "staged.sav"
    staged.write_bytes(document.serialize_bytes())
    document.verify_reloaded_file(staged)
    reloaded = LocalDataDocument.open_file(staged)

    assert reloaded.is_fully_unexplored() is True
    assert _mask_neutral_properties(reloaded) == before
    save_data = reloaded.gvas_file.properties["SaveData"]["value"]
    assert save_data["PreservedCounter"]["value"] == 73
    assert save_data["Local_HiddenLocationFlagMap"]["value"] == "preserve-hidden"
    assert save_data["Local_ShowSkyIslandCloudOnWorldMapUI"]["value"] is True


@pytest.mark.parametrize(
    ("format_name", "expected_format", "expected_maps"),
    [
        ("current", "WorldMapUISaveDataMap", ("MainMap", "Tree")),
        ("legacy", "WorldMapMaskTextureV4", ("MainMap",)),
    ],
)
def test_new_and_legacy_local_data_clear_roundtrip_preserves_every_other_field(
    tmp_path: Path,
    format_name: str,
    expected_format: str,
    expected_maps: tuple[str, ...],
) -> None:
    source = tmp_path / "LocalData.sav"
    source.write_bytes(
        _sav(_local_gvas(format_name, explored=True), local_data=True)
    )
    document = LocalDataDocument.open_file(source)
    before = _mask_neutral_properties(document)

    assert document.capability.available is True
    assert document.capability.format == expected_format
    assert document.capability.maps == expected_maps
    assert document.is_fully_cleared() is False

    document.clear_fog_of_war()
    document.validate_clear()
    staged = tmp_path / "staged-clear.sav"
    staged.write_bytes(document.serialize_bytes())
    document.verify_reloaded_file(staged)
    reloaded = LocalDataDocument.open_file(staged)

    assert reloaded.is_fully_cleared() is True
    assert all(
        bytes(mask["value"]["values"])
        == bytes(CLEARED_PIXEL) * (len(mask["value"]["values"]) // 4)
        for _name, mask in reloaded._mask_bindings()
    )
    assert _mask_neutral_properties(reloaded) == before
    save_data = reloaded.gvas_file.properties["SaveData"]["value"]
    assert save_data["PreservedCounter"]["value"] == 73
    assert save_data["Local_HiddenLocationFlagMap"]["value"] == "preserve-hidden"
    assert save_data["Local_ShowSkyIslandCloudOnWorldMapUI"]["value"] is True


@pytest.mark.parametrize(
    ("format_name", "include_local_data", "expected_reason"),
    [
        ("current", False, "LOCAL_DATA_MISSING"),
        ("unknown", True, "FOG_OF_WAR_STRUCTURE_UNSUPPORTED"),
    ],
)
def test_missing_or_unknown_local_data_is_exposed_and_rejected(
    tmp_path: Path,
    format_name: str,
    include_local_data: bool,
    expected_reason: str,
) -> None:
    root = tmp_path / "world"
    _make_steam_world(
        root,
        format_name=format_name,
        include_local_data=include_local_data,
    )
    session = SaveSession.from_loaded_manager(_manager(), root)

    for capability_name in ("fogOfWarClear", "fogOfWarReset"):
        capability = session.save_capabilities[capability_name]
        assert capability["available"] is False
        assert capability["reason"] == "LOCAL_DATA_NOT_SELECTED"
    if not include_local_data:
        with pytest.raises(DomainError) as raised:
            _select_local_data(session, root / "LocalData.sav")
        assert raised.value.code == expected_reason
        assert session.revision == 0
        assert session.changes() == []
        return

    _select_local_data(session, root / "LocalData.sav")
    for capability_name in ("fogOfWarClear", "fogOfWarReset"):
        capability = session.save_capabilities[capability_name]
        assert capability["available"] is False
        assert capability["reason"] == expected_reason
    for command in (_clear_command(session), _command(session)):
        with pytest.raises(DomainError) as raised:
            FogOfWarEditor(session).execute(command)
        assert raised.value.code == expected_reason
        assert session.revision == 1
        assert session.changes() == []


def test_reset_requires_exact_risk_confirmation(tmp_path: Path) -> None:
    root = tmp_path / "world"
    _make_steam_world(root)
    session = SaveSession.from_loaded_manager(_manager(), root)
    _select_local_data(session, root / "LocalData.sav")

    with pytest.raises(DomainError) as raised:
        FogOfWarEditor(session).execute(_command(session, "解锁全地图"))

    assert raised.value.code == "FOG_OF_WAR_CONFIRMATION_REQUIRED"
    assert session.revision == 1

def test_clear_requires_exact_risk_confirmation(tmp_path: Path) -> None:
    root = tmp_path / "world"
    _make_steam_world(root)
    session = SaveSession.from_loaded_manager(_manager(), root)
    _select_local_data(session, root / "LocalData.sav")

    with pytest.raises(DomainError) as raised:
        FogOfWarEditor(session).execute(
            _clear_command(session, FOG_RESET_CONFIRMATION)
        )

    assert raised.value.code == "FOG_OF_WAR_CLEAR_CONFIRMATION_REQUIRED"
    assert session.revision == 1


def test_steam_open_reset_save_reopen_only_writes_local_data(
    tmp_path: Path,
) -> None:
    root = tmp_path / "world"
    level_before, local_before = _make_steam_world(root)
    players = root / "Players"
    players.mkdir()
    player_marker = players / "UNRELATED.sav"
    player_marker.write_bytes(b"unrelated-player")
    session = SaveSession.from_loaded_manager(_manager(), root)
    _select_local_data(session, root / "LocalData.sav")

    result = FogOfWarEditor(session).execute(_command(session))
    assert result["changed"] is True
    assert session.changes()[0]["affected_records"] == ["local_data"]
    save_result = SaveWriter().save(session, root, 2)

    assert save_result.written_files == ("LocalData.sav",)
    assert (root / "Level.sav").read_bytes() == level_before
    assert player_marker.read_bytes() == b"unrelated-player"
    assert (root / "LocalData.sav").read_bytes() != local_before
    reopened = SaveSession.from_loaded_manager(_manager(), root)
    _select_local_data(reopened, root / "LocalData.sav")
    assert reopened.local_data.is_fully_unexplored() is True
    assert reopened.save_capabilities["fogOfWarReset"]["available"] is True
    backup_files = Path(save_result.backup_path) / "files"
    assert (backup_files / "Level.sav").read_bytes() == level_before
    assert (backup_files / "LocalData.sav").read_bytes() == local_before
    assert (backup_files / "Players" / "UNRELATED.sav").read_bytes() == (
        b"unrelated-player"
    )


def test_steam_open_clear_save_reopen_only_writes_local_data(
    tmp_path: Path,
) -> None:
    root = tmp_path / "world"
    level_before, local_before = _make_steam_world(root)
    players = root / "Players"
    players.mkdir()
    player_marker = players / "UNRELATED.sav"
    player_marker.write_bytes(b"unrelated-player")
    session = SaveSession.from_loaded_manager(_manager(), root)
    _select_local_data(session, root / "LocalData.sav")

    result = FogOfWarEditor(session).execute(_clear_command(session))
    assert result["changed"] is True
    assert session.changes()[0]["affected_records"] == ["local_data"]
    save_result = SaveWriter().save(session, root, 2)

    assert save_result.written_files == ("LocalData.sav",)
    assert (root / "Level.sav").read_bytes() == level_before
    assert player_marker.read_bytes() == b"unrelated-player"
    assert (root / "LocalData.sav").read_bytes() != local_before
    reopened = SaveSession.from_loaded_manager(_manager(), root)
    _select_local_data(reopened, root / "LocalData.sav")
    assert reopened.local_data.is_fully_cleared() is True
    assert reopened.save_capabilities["fogOfWarClear"]["available"] is True
    backup_files = Path(save_result.backup_path) / "files"
    assert (backup_files / "Level.sav").read_bytes() == level_before
    assert (backup_files / "LocalData.sav").read_bytes() == local_before
    assert (backup_files / "Players" / "UNRELATED.sav").read_bytes() == (
        b"unrelated-player"
    )


def test_steam_external_local_data_is_backed_up_and_written_in_place(
    tmp_path: Path,
) -> None:
    root = tmp_path / "world"
    level_before, local_before = _make_steam_world(root)
    profile = tmp_path / "profile"
    profile.mkdir()
    selected = profile / "LocalData.sav"
    selected.write_bytes(local_before)
    (root / "LocalData.sav").unlink()
    session = SaveSession.from_loaded_manager(_manager(), root)

    selection = _select_local_data(session, selected)
    assert selection["selection"]["source"] == str(selected.resolve())
    FogOfWarEditor(session).execute(_command(session))
    result = SaveWriter().save(session, root, 2)

    assert (root / "Level.sav").read_bytes() == level_before
    assert not (root / "LocalData.sav").exists()
    assert selected.read_bytes() != local_before
    backup_file = (
        Path(result.backup_path)
        / "files"
        / "__external__"
        / "LocalData.sav"
    )
    assert backup_file.read_bytes() == local_before
    manifest_entry = next(
        entry for entry in result.manifest if entry.get("external") is True
    )
    assert manifest_entry["source_path"] == str(selected.resolve())

    reopened = SaveSession.from_loaded_manager(_manager(), root)
    _select_local_data(reopened, selected)
    assert reopened.local_data.is_fully_unexplored() is True


def test_steam_external_local_data_failure_restores_selected_file(
    tmp_path: Path,
) -> None:
    root = tmp_path / "world"
    _level_before, local_before = _make_steam_world(root)
    selected = tmp_path / "LocalData.sav"
    selected.write_bytes(local_before)
    (root / "LocalData.sav").unlink()
    session = SaveSession.from_loaded_manager(_manager(), root)
    _select_local_data(session, selected)
    FogOfWarEditor(session).execute(_clear_command(session))

    def fail(stage, context):
        if stage == "after_replace" and context.get("path") == "LocalData.sav":
            raise OSError("synthetic external replacement failure")

    with pytest.raises(DomainError) as raised:
        SaveWriter(failure_hook=fail).save(session, root, 2)

    assert raised.value.code == "WRITE_FAILED"
    assert raised.value.details["recovered"] is True
    assert selected.read_bytes() == local_before
    assert not (root / "LocalData.sav").exists()


class _SyntheticManager:
    def open(self, path, *, lazy_players=False):
        raw, self._compression_times = decompress_sav_to_gvas(
            (Path(path) / "Level.sav").read_bytes()
        )
        self.gvas_file = GvasFile.read(
            raw,
            PALWORLD_TYPE_HINTS,
            MAIN_SKIP_PROPERTIES,
        )
        self.player_mapping = {}
        self.item_container_data = None
        return self.gvas_file


def test_wgs_fixture_open_reset_write_back_and_reopen_original_slot() -> None:
    with TemporaryDirectory() as temp:
        base = Path(temp)
        wgs_root = base / "wgs"
        wgs_root.mkdir()
        world_id = "A" * 32
        make_user_directory(
            wgs_root,
            "1111111111111111_" + "B" * 32,
            {
                world_id: {
                    "Level.sav": _cnk0_payload(_sav(_level_gvas())),
                    "LocalData.sav": _sav(
                        _local_gvas("legacy", explored=True),
                        local_data=True,
                    ),
                }
            },
        )
        catalog = XgpSourceCatalog(roots=(wgs_root,))
        adapter = XgpWgsAdapter(
            catalog=catalog,
            process_checker=lambda: False,
            workspace_validator=lambda _path: None,
            workspace_root=base / "workspaces",
            backup_root=base / "backups",
            stability_delay=0,
        )
        source = catalog.discover()[0]
        session = SaveSession.open_storage(
            source,
            adapter,
            manager=_SyntheticManager(),
        )
        assert session.local_data.capability.format == "WorldMapMaskTextureV4"
        with pytest.raises(DomainError) as raised:
            _select_local_data(session, base / "LocalData.sav")
        assert raised.value.code == "WGS_LOCAL_DATA_EXTERNAL_UNSUPPORTED"
        _select_local_data(session)
        FogOfWarEditor(session).execute(_command(session))

        result = SaveWriter().save(session, None, 2)
        assert result.written_files == ("LocalData.sav",)
        assert result.target_reload_verified is True
        assert result.cloud_sync_verified is False
        assert Path(result.backup_path).is_dir()
        session.close()

        reopened = SaveSession.open_storage(
            source,
            adapter,
            manager=_SyntheticManager(),
        )
        try:
            assert reopened.platform.value == "xgp"
            assert reopened.source_id == source.source_id
            assert reopened.local_data.is_fully_unexplored() is True
        finally:
            reopened.close()


def test_wgs_fixture_open_clear_write_back_and_reopen_original_slot() -> None:
    with TemporaryDirectory() as temp:
        base = Path(temp)
        wgs_root = base / "wgs"
        wgs_root.mkdir()
        world_id = "A" * 32
        make_user_directory(
            wgs_root,
            "1111111111111111_" + "B" * 32,
            {
                world_id: {
                    "Level.sav": _cnk0_payload(_sav(_level_gvas())),
                    "LocalData.sav": _sav(
                        _local_gvas("legacy", explored=True),
                        local_data=True,
                    ),
                }
            },
        )
        catalog = XgpSourceCatalog(roots=(wgs_root,))
        adapter = XgpWgsAdapter(
            catalog=catalog,
            process_checker=lambda: False,
            workspace_validator=lambda _path: None,
            workspace_root=base / "workspaces",
            backup_root=base / "backups",
            stability_delay=0,
        )
        source = catalog.discover()[0]
        session = SaveSession.open_storage(
            source,
            adapter,
            manager=_SyntheticManager(),
        )
        assert session.local_data.capability.format == "WorldMapMaskTextureV4"
        _select_local_data(session)
        FogOfWarEditor(session).execute(_clear_command(session))

        result = SaveWriter().save(session, None, 2)
        assert result.written_files == ("LocalData.sav",)
        assert result.target_reload_verified is True
        assert result.cloud_sync_verified is False
        assert Path(result.backup_path).is_dir()
        session.close()

        reopened = SaveSession.open_storage(
            source,
            adapter,
            manager=_SyntheticManager(),
        )
        try:
            assert reopened.platform.value == "xgp"
            assert reopened.source_id == source.source_id
            assert reopened.local_data.is_fully_cleared() is True
        finally:
            reopened.close()


@pytest.mark.parametrize("command_factory", [_command, _clear_command])
def test_local_data_source_conflict_stops_before_save(
    tmp_path: Path,
    command_factory,
) -> None:
    root = tmp_path / "world"
    _level_before, local_before = _make_steam_world(root)
    session = SaveSession.from_loaded_manager(_manager(), root)
    _select_local_data(session, root / "LocalData.sav")
    FogOfWarEditor(session).execute(command_factory(session))
    (root / "LocalData.sav").write_bytes(local_before + b"external-change")

    with pytest.raises(DomainError) as raised:
        SaveWriter().save(session, root, 2)

    assert raised.value.code == "SAVE_TARGET_CHANGED"
    assert (root / "LocalData.sav").read_bytes() == local_before + b"external-change"
    assert len(session.changes()) == 1


@pytest.mark.parametrize("command_factory", [_command, _clear_command])
def test_local_data_backup_failure_never_writes_target(
    tmp_path: Path,
    command_factory,
) -> None:
    root = tmp_path / "world"
    _level_before, local_before = _make_steam_world(root)
    session = SaveSession.from_loaded_manager(_manager(), root)
    _select_local_data(session, root / "LocalData.sav")
    FogOfWarEditor(session).execute(command_factory(session))

    def fail(stage, _context):
        if stage == "before_backup_copy":
            raise OSError(errno.ENOSPC, "synthetic disk full")

    with pytest.raises(DomainError) as raised:
        SaveWriter(failure_hook=fail).save(session, root, 2)

    assert raised.value.code == "BACKUP_FAILED"
    assert (root / "LocalData.sav").read_bytes() == local_before
    assert len(session.changes()) == 1


@pytest.mark.parametrize("command_factory", [_command, _clear_command])
def test_local_data_replace_failure_restores_original(
    tmp_path: Path,
    command_factory,
) -> None:
    root = tmp_path / "world"
    _level_before, local_before = _make_steam_world(root)
    session = SaveSession.from_loaded_manager(_manager(), root)
    _select_local_data(session, root / "LocalData.sav")
    FogOfWarEditor(session).execute(command_factory(session))

    def fail(stage, context):
        if stage == "after_replace" and context.get("path") == "LocalData.sav":
            raise OSError("synthetic replacement failure")

    with pytest.raises(DomainError) as raised:
        SaveWriter(failure_hook=fail).save(session, root, 2)

    assert raised.value.code == "WRITE_FAILED"
    assert raised.value.details["recovered"] is True
    assert (root / "LocalData.sav").read_bytes() == local_before
    restored = LocalDataDocument.open_file(root / "LocalData.sav")
    assert restored.is_fully_unexplored() is False
    assert restored.is_fully_cleared() is False
    assert len(session.changes()) == 1
