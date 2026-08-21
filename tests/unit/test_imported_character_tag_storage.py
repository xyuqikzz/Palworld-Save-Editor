from pathlib import Path, PurePosixPath

from palworld_save_tools.gvas import GvasFile, GvasHeader
from palworld_save_tools.palsav import compress_gvas_to_sav, decompress_sav_to_gvas
from palworld_save_tools.paltypes import PALWORLD_TYPE_HINTS

from palworld_pal_editor.core.pal_objects import PalObjects, toUUID
from palworld_pal_editor.core.save_manager import MAIN_SKIP_PROPERTIES
from palworld_pal_editor.domain.models import StorageCommitRequest
from palworld_pal_editor.storage.discovery import XgpSourceCatalog
from palworld_pal_editor.storage.steam import SteamDirectoryAdapter, make_steam_source
from palworld_pal_editor.storage.wgs_format import normalize_palworld_payload
from palworld_pal_editor.storage.xgp import XgpWgsAdapter
from tests.wgs_fixture import make_user_directory


PAL_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
OWNER_ID = "11111111-2222-3333-4444-555555555555"
CONTAINER_ID = "22222222-3333-4444-5555-666666666666"
GROUP_ID = "33333333-4444-5555-6666-777777777777"


def _gvas_with_imported_pal() -> GvasFile:
    entry = PalObjects.PalSaveParameter(
        toUUID(PAL_ID),
        toUUID(OWNER_ID),
        toUUID(CONTAINER_ID),
        0,
        toUUID(GROUP_ID),
    )
    parameter = entry["value"]["RawData"]["value"]["object"][
        "SaveParameter"
    ]["value"]
    parameter["bImportedCharacter"] = PalObjects.BoolProperty(True)

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
            "engine_version_branch": "imported-character-tag-fixture",
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
            "value": {
                "CharacterSaveParameterMap": {
                    "key_type": "StructProperty",
                    "value_type": "StructProperty",
                    "key_struct_type": "StructProperty",
                    "value_struct_type": "StructProperty",
                    "id": None,
                    "type": "MapProperty",
                    "value": [entry],
                }
            },
        }
    }
    gvas.trailer = b"\0\0\0\0"
    return gvas


def _sav(gvas: GvasFile) -> bytes:
    return compress_gvas_to_sav(
        gvas.write(MAIN_SKIP_PROPERTIES), 0x32, zlib=True
    )


def _read_gvas(path: Path) -> GvasFile:
    payload = normalize_palworld_payload(path.read_bytes())
    raw, _compression = decompress_sav_to_gvas(payload.data)
    return GvasFile.read(raw, PALWORLD_TYPE_HINTS, MAIN_SKIP_PROPERTIES)


def _imported_field(gvas: GvasFile) -> dict | None:
    entries = gvas.properties["worldSaveData"]["value"][
        "CharacterSaveParameterMap"
    ]["value"]
    parameter = entries[0]["value"]["RawData"]["value"]["object"][
        "SaveParameter"
    ]["value"]
    return parameter.get("bImportedCharacter")


def _remove_imported_tag(gvas: GvasFile) -> None:
    field = _imported_field(gvas)
    assert field == PalObjects.BoolProperty(True)
    entries = gvas.properties["worldSaveData"]["value"][
        "CharacterSaveParameterMap"
    ]["value"]
    entries[0]["value"]["RawData"]["value"]["object"][
        "SaveParameter"
    ]["value"].pop("bImportedCharacter")


def _request(opened, stage: Path) -> StorageCommitRequest:
    return StorageCommitRequest(
        opened=opened,
        staged_workspace=stage,
        changed_files=(PurePosixPath("Level.sav"),),
        expected_revision=1,
        verify_file=lambda path, _relative: _read_gvas(path),
    )


def test_steam_imported_tag_removal_commits_and_reopens(tmp_path: Path) -> None:
    source_root = tmp_path / "steam-save"
    source_root.mkdir()
    (source_root / "Level.sav").write_bytes(_sav(_gvas_with_imported_pal()))
    adapter = SteamDirectoryAdapter()
    opened = adapter.open(make_steam_source(source_root))
    stage = tmp_path / "steam-stage"
    stage.mkdir()
    candidate = _read_gvas(source_root / "Level.sav")
    _remove_imported_tag(candidate)
    (stage / "Level.sav").write_bytes(_sav(candidate))

    result = adapter.commit(_request(opened, stage))

    assert result.source_reloaded is True
    reopened = adapter.open(make_steam_source(source_root))
    assert _imported_field(_read_gvas(reopened.workspace / "Level.sav")) is None


def test_wgs_imported_tag_removal_commits_and_reopens(tmp_path: Path) -> None:
    wgs_root = tmp_path / "wgs"
    wgs_root.mkdir()
    user = make_user_directory(
        wgs_root,
        "1111111111111111_" + "A" * 32,
        {"B" * 32: {"Level.sav": _sav(_gvas_with_imported_pal())}},
    )
    catalog = XgpSourceCatalog(roots=(wgs_root,))
    adapter = XgpWgsAdapter(
        catalog=catalog,
        process_checker=lambda: False,
        workspace_validator=lambda _path: None,
        workspace_root=tmp_path / "workspaces",
        backup_root=tmp_path / "backups",
        stability_delay=0,
    )
    opened = adapter.open(catalog.discover()[0])
    stage = tmp_path / "wgs-stage"
    stage.mkdir()
    candidate = _read_gvas(opened.workspace / "Level.sav")
    _remove_imported_tag(candidate)
    (stage / "Level.sav").write_bytes(_sav(candidate))

    result = adapter.commit(_request(opened, stage))

    assert result.source_reloaded is True
    reopened = adapter.open(catalog.discover()[0])
    try:
        assert _imported_field(_read_gvas(reopened.workspace / "Level.sav")) is None
        assert (user / "containers.index").is_file()
    finally:
        adapter.close(reopened)
        adapter.close(opened)
