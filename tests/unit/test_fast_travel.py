from __future__ import annotations

from copy import deepcopy
import errno
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from palworld_save_tools.gvas import GvasFile, GvasHeader
from palworld_save_tools.palsav import compress_gvas_to_sav, decompress_sav_to_gvas
from palworld_save_tools.paltypes import PALWORLD_TYPE_HINTS
from palworld_pal_editor.application.fast_travel import PlayerFastTravelData
from palworld_pal_editor.application.fast_travel_editor import (
    FAST_TRAVEL_UNLOCK_CONFIRMATION,
    FastTravelEditor,
)
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.application.save_writer import SaveWriter
from palworld_pal_editor.core.pal_objects import PalObjects
from palworld_pal_editor.core.save_manager import (
    MAIN_SKIP_PROPERTIES,
    PLAYER_SKIP_PROPERTIES,
)
from palworld_pal_editor.domain.commands import UnlockAllFastTravelPoints
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.domain.fast_travel_catalog import (
    FAST_TRAVEL_POINT_IDS,
)
from palworld_pal_editor.storage.discovery import XgpSourceCatalog
from palworld_pal_editor.storage.xgp import XgpWgsAdapter
from tests.wgs_fixture import make_user_directory


PLAYER_ID = "00000000-0000-0000-0000-000000000001"
PLAYER_FILE = "Players/00000000000000000000000000000001.sav"
PALWORLD_1_0_WATCHTOWER_IDS = frozenset(
    {
        "0C0AF9F34C0491BCAD80B1BF355B9A98",
        "11E3E3C44F040B34E3809CB69CD87435",
        "328BCAC94E01988D944C4F85D49E457C",
        "3BF1495E406AD5F437DA5AA2134954A2",
        "479A228C4032AAF144B3808E753E1690",
        "47E04FF245A4FB6F4E1E9C864ED8F2B0",
        "4C204C3842EAB210A7A9DA9D2CF9CBBE",
        "58A29B814E069D61EC75B1A6E9658FC1",
        "5FA6EB494384E4134BAA589F02A580DC",
        "6948B7914C8D1701DB7F4081E4D970E5",
        "84D48EA34666191781868E809ACBCBCE",
        "8A9AE3B44AD758EDD7FE44BA9B75000B",
        "A9213E6E425F2F696D8B3EB19AA547FE",
        "C5E2ABA14A8F6D35EF4A81AD47EC19C9",
        "CCCD29E444CEB548D5B5E589DAF086F2",
        "D8C1A86541DACA78B1250AB9B85B7E67",
        "DEE0F8BB4609C83285CE6CA80B84B679",
        "E8351DF348B268672F0A219840C6BE47",
        "E9FC08444BFE7E3EE6E06F84AC8688EC",
        "EDE1AB2C44B1846879BB789C3951B2F7",
        "F46296FF4274FEDBF32DC5957835A18A",
        "FD235A5B4F02CD76312A459D77398CA6",
    }
)


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
            "engine_version_branch": "synthetic-fast-travel-test",
            "custom_version_format": 3,
            "custom_versions": [],
            "save_game_class_name": class_name,
        }
    )


def _level_gvas() -> GvasFile:
    gvas = GvasFile()
    gvas.header = _header("/Script/Pal.PalWorldSaveGame")
    gvas.properties = {"PreservedLevelCounter": PalObjects.IntProperty(19)}
    gvas.trailer = b"\x00\x00\x00\x00"
    return gvas


def _player_gvas(
    *,
    field: str = "valid",
    unlocked: tuple[str, ...] = FAST_TRAVEL_POINT_IDS[:2],
) -> GvasFile:
    flag = PalObjects.MapProperty("NameProperty", "BoolProperty")
    flag["value"] = [{"key": point_id, "value": True} for point_id in unlocked]
    if field == "unknown":
        flag["value"].append({"key": "F" * 32, "value": True})
    elif field == "wrong_type":
        flag["value_type"] = "IntProperty"
    record_value = {"PreservedRecordCounter": PalObjects.IntProperty(23)}
    if field != "missing":
        record_value["FastTravelPointUnlockFlag"] = flag
    gvas = GvasFile()
    gvas.header = _header("/Script/Pal.PalWorldPlayerSaveGame")
    gvas.properties = {
        "SaveData": {
            "struct_type": "PalWorldPlayerSaveData",
            "struct_id": PalObjects.EMPTY_UUID,
            "id": None,
            "type": "StructProperty",
            "value": {
                "PreservedPlayerCounter": PalObjects.IntProperty(31),
                "RecordData": PalObjects.PalLoggedinPlayerSaveDataRecordData(
                    record_value
                ),
            },
        }
    }
    gvas.trailer = b"\x00\x00\x00\x00"
    return gvas


def _sav(gvas: GvasFile, *, player: bool = False) -> bytes:
    properties = PLAYER_SKIP_PROPERTIES if player else MAIN_SKIP_PROPERTIES
    return compress_gvas_to_sav(gvas.write(properties), 0x32, zlib=True)


class _SyntheticPlayer:
    InstanceId = "11111111-1111-1111-1111-111111111111"
    NickName = "Fast Travel Tester"
    Level = 20
    is_loaded = True

    def __init__(self, gvas_file: GvasFile, compression: int) -> None:
        self.PlayerUId = PLAYER_ID
        self._gvas_file = gvas_file
        self._compression = compression
        self._player_save_data = gvas_file.properties["SaveData"]["value"]

    @property
    def PlayerGVAS(self):
        return self._gvas_file, self._compression

    def load_details(self) -> None:
        return None


class _SyntheticManager:
    def open(self, path, *, lazy_players=False):
        root = Path(path)
        raw, self._compression_times = decompress_sav_to_gvas(
            (root / "Level.sav").read_bytes()
        )
        self.gvas_file = GvasFile.read(
            raw,
            PALWORLD_TYPE_HINTS,
            MAIN_SKIP_PROPERTIES,
        )
        player_raw, compression = decompress_sav_to_gvas(
            (root / PLAYER_FILE).read_bytes()
        )
        player_gvas = GvasFile.read(
            player_raw,
            PALWORLD_TYPE_HINTS,
            PLAYER_SKIP_PROPERTIES,
        )
        self.player = _SyntheticPlayer(player_gvas, compression)
        self.player_mapping = {PLAYER_ID: self.player}
        self.item_container_data = None
        return self.gvas_file

    def get_player(self, player_id):
        return self.player if str(player_id) == PLAYER_ID else None


def _make_steam_world(
    root: Path,
    *,
    field: str = "valid",
) -> tuple[bytes, bytes]:
    root.mkdir()
    (root / "Players").mkdir()
    level = _sav(_level_gvas())
    player = _sav(_player_gvas(field=field), player=True)
    (root / "Level.sav").write_bytes(level)
    (root / PLAYER_FILE).write_bytes(player)
    return level, player


def _open_steam(root: Path) -> SaveSession:
    return SaveSession.open(root, manager=_SyntheticManager())


def _command(
    session: SaveSession,
    *,
    confirmation: str = FAST_TRAVEL_UNLOCK_CONFIRMATION,
) -> UnlockAllFastTravelPoints:
    return UnlockAllFastTravelPoints(
        session_id=session.session_id,
        expected_revision=session.revision,
        player_id=PLAYER_ID,
        confirmation=confirmation,
    )


def test_catalog_includes_palworld_1_0_watchtowers() -> None:
    catalog = set(FAST_TRAVEL_POINT_IDS)

    assert len(FAST_TRAVEL_POINT_IDS) == 163
    assert len(catalog) == len(FAST_TRAVEL_POINT_IDS)
    assert PALWORLD_1_0_WATCHTOWER_IDS <= catalog


def test_unlock_all_changes_only_verified_fast_travel_map() -> None:
    player = _SyntheticPlayer(_player_gvas(), 0x32)
    document = PlayerFastTravelData.from_player(player)
    before = document.properties_without_flags()

    assert document.capability.available is True
    assert document.capability.unlocked_count == 2
    document.unlock_all()
    document.validate_all_unlocked()

    assert document.summary()["unlocked_count"] == len(FAST_TRAVEL_POINT_IDS)
    assert document.properties_without_flags() == before
    record = player._player_save_data["RecordData"]["value"]
    assert record["PreservedRecordCounter"]["value"] == 23
    assert player._player_save_data["PreservedPlayerCounter"]["value"] == 31


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ("missing", "FAST_TRAVEL_FIELD_MISSING"),
        ("wrong_type", "FAST_TRAVEL_STRUCTURE_UNSUPPORTED"),
    ],
)
def test_missing_unknown_or_unverified_structure_is_rejected(
    tmp_path: Path,
    field: str,
    reason: str,
) -> None:
    root = tmp_path / "world"
    _make_steam_world(root, field=field)
    session = _open_steam(root)
    try:
        capability = FastTravelEditor(session).capability(PLAYER_ID)
        assert capability.available is False
        assert capability.reason == reason
        with pytest.raises(DomainError) as raised:
            FastTravelEditor(session).execute(_command(session))
        assert raised.value.code == reason
        assert session.revision == 0
        assert session.changes() == []
    finally:
        session.close()


def test_existing_non_fast_travel_flags_are_preserved(tmp_path: Path) -> None:
    root = tmp_path / "world"
    _make_steam_world(root, field="unknown")
    session = _open_steam(root)
    try:
        player = session.load_player(PLAYER_ID)
        document = PlayerFastTravelData.from_player(player)
        unrelated_before = document.non_catalog_entries()
        assert document.capability.available is True

        FastTravelEditor(session).execute(_command(session))

        assert document.non_catalog_entries() == unrelated_before
        document.validate_all_unlocked()
    finally:
        session.close()


def test_unlock_requires_exact_risk_confirmation(tmp_path: Path) -> None:
    root = tmp_path / "world"
    _make_steam_world(root)
    session = _open_steam(root)
    try:
        with pytest.raises(DomainError) as raised:
            FastTravelEditor(session).execute(
                _command(session, confirmation="清除战争迷雾")
            )
        assert raised.value.code == "FAST_TRAVEL_CONFIRMATION_REQUIRED"
        assert session.revision == 0
    finally:
        session.close()


def test_steam_open_unlock_save_reopen_only_writes_selected_player(
    tmp_path: Path,
) -> None:
    root = tmp_path / "world"
    level_before, player_before = _make_steam_world(root)
    session = _open_steam(root)
    result = FastTravelEditor(session).execute(_command(session))

    assert result["changed"] is True
    assert session.changes()[0]["affected_records"] == [
        f"player_file:{PLAYER_ID}"
    ]
    save_result = SaveWriter().save(session, root, session.revision)
    session.close()

    assert save_result.written_files == (PLAYER_FILE,)
    assert (root / "Level.sav").read_bytes() == level_before
    assert (root / PLAYER_FILE).read_bytes() != player_before
    reopened = _open_steam(root)
    try:
        player = reopened.load_player(PLAYER_ID)
        document = PlayerFastTravelData.from_player(player)
        document.validate_all_unlocked()
        assert document.summary()["all_unlocked"] is True
    finally:
        reopened.close()


def test_wgs_fixture_open_unlock_write_back_and_reopen_original_slot() -> None:
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
                    "Level.sav": _sav(_level_gvas()),
                    PLAYER_FILE: _sav(_player_gvas(), player=True),
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
        FastTravelEditor(session).execute(_command(session))
        result = SaveWriter().save(session, None, session.revision)
        session.close()

        assert result.written_files == (PLAYER_FILE,)
        assert result.target_reload_verified is True
        assert result.cloud_sync_verified is False
        assert Path(result.backup_path).is_dir()
        reopened = SaveSession.open_storage(
            source,
            adapter,
            manager=_SyntheticManager(),
        )
        try:
            assert reopened.platform.value == "xgp"
            assert reopened.source_id == source.source_id
            PlayerFastTravelData.from_player(
                reopened.load_player(PLAYER_ID)
            ).validate_all_unlocked()
        finally:
            reopened.close()


def test_player_source_conflict_stops_before_save(tmp_path: Path) -> None:
    root = tmp_path / "world"
    _level_before, player_before = _make_steam_world(root)
    session = _open_steam(root)
    FastTravelEditor(session).execute(_command(session))
    (root / PLAYER_FILE).write_bytes(player_before + b"external-change")

    with pytest.raises(DomainError) as raised:
        SaveWriter().save(session, root, session.revision)

    assert raised.value.code == "SAVE_TARGET_CHANGED"
    assert (root / PLAYER_FILE).read_bytes() == player_before + b"external-change"
    assert len(session.changes()) == 1
    session.close()


def test_player_backup_failure_never_writes_target(tmp_path: Path) -> None:
    root = tmp_path / "world"
    _level_before, player_before = _make_steam_world(root)
    session = _open_steam(root)
    FastTravelEditor(session).execute(_command(session))

    def fail(stage, _context):
        if stage == "before_backup_copy":
            raise OSError(errno.ENOSPC, "synthetic disk full")

    with pytest.raises(DomainError) as raised:
        SaveWriter(failure_hook=fail).save(session, root, session.revision)

    assert raised.value.code == "BACKUP_FAILED"
    assert (root / PLAYER_FILE).read_bytes() == player_before
    assert len(session.changes()) == 1
    session.close()


def test_player_replace_failure_restores_original(tmp_path: Path) -> None:
    root = tmp_path / "world"
    _level_before, player_before = _make_steam_world(root)
    session = _open_steam(root)
    FastTravelEditor(session).execute(_command(session))

    def fail(stage, context):
        if stage == "after_replace" and context.get("path") == PLAYER_FILE:
            raise OSError("synthetic replacement failure")

    with pytest.raises(DomainError) as raised:
        SaveWriter(failure_hook=fail).save(session, root, session.revision)

    assert raised.value.code == "WRITE_FAILED"
    assert raised.value.details["recovered"] is True
    assert (root / PLAYER_FILE).read_bytes() == player_before
    assert len(session.changes()) == 1
    session.close()
