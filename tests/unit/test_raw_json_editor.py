from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import json

import pytest

from palworld_save_tools.gvas import GvasFile, GvasHeader
from palworld_save_tools.palsav import compress_gvas_to_sav, decompress_sav_to_gvas
from palworld_save_tools.paltypes import (
    PALWORLD_CUSTOM_PROPERTIES,
    PALWORLD_TYPE_HINTS,
)

from palworld_pal_editor.application.raw_json_editor import RawJsonEditor
from palworld_pal_editor.application.runtime import SessionRuntime
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.application.save_writer import SaveWriter
from palworld_pal_editor.core.lazy_player_entity import LazyPlayerEntity
from palworld_pal_editor.core.pal_objects import PalObjects, UUID2HexStr, toUUID
from palworld_pal_editor.core.save_manager import (
    MAIN_SKIP_PROPERTIES,
    PLAYER_SKIP_PROPERTIES,
)
from palworld_pal_editor.domain.errors import DomainError
from tests.unit.test_save_writer import (
    LOCKER_INSTANCE_ID,
    LOCKER_PLAYER_UID,
    START_POINT_ID,
    make_gvas as make_legacy_gvas,
    read_locker_character_ids,
    read_start_point_ids,
)

PLAYER_ID = toUUID("11111111-2222-3333-4444-555555555555")
PLAYER_INSTANCE_ID = toUUID("99999999-aaaa-bbbb-cccc-dddddddddddd")
PLAYER_GROUP_ID = toUUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
REPLACEMENT_PLAYER_ID = toUUID("aaaaaaaa-1111-2222-3333-bbbbbbbbbbbb")


def _gvas(counter: int) -> GvasFile:
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
            "engine_version_branch": "synthetic-json-editor-test",
            "custom_version_format": 3,
            "custom_versions": [],
            "save_game_class_name": "/Script/Pal.PalWorldSaveGame",
        }
    )
    gvas.properties = {
        "Counter": PalObjects.IntProperty(counter),
        "RawBytes": PalObjects.ArrayProperty(
            "ByteProperty",
            {"values": [1, 2, 255]},
        ),
        "worldSaveData": {
            "type": "StructProperty",
            "struct_type": "PalWorldSaveData",
            "struct_id": PalObjects.EMPTY_UUID,
            "id": None,
            "value": {},
        },
    }
    gvas.trailer = b"\0\0\0\0"
    return gvas


def _player_object() -> dict:
    value = PalObjects.PalSaveParameter(
        PLAYER_INSTANCE_ID,
        PLAYER_ID,
        PalObjects.EMPTY_UUID,
        0,
        PLAYER_GROUP_ID,
    )
    value["key"]["PlayerUId"] = PalObjects.Guid(PLAYER_ID)
    parameter = value["value"]["RawData"]["value"]["object"]["SaveParameter"][
        "value"
    ]
    parameter["IsPlayer"] = PalObjects.BoolProperty(True)
    parameter["NickName"] = PalObjects.StrProperty("JSON Player")
    parameter["Level"] = PalObjects.ByteProperty(20)
    return value


def _player_gvas(counter: int = 10) -> GvasFile:
    gvas = _gvas(counter)
    gvas.properties["SaveData"] = {
        "struct_type": "PalWorldPlayerSaveData",
        "struct_id": PalObjects.EMPTY_UUID,
        "id": None,
        "type": "StructProperty",
        "value": {
            "IndividualId": {
                "struct_type": "PalInstanceID",
                "struct_id": PalObjects.EMPTY_UUID,
                "id": None,
                "type": "StructProperty",
                "value": {
                    "PlayerUId": PalObjects.Guid(PLAYER_ID),
                    "InstanceId": PalObjects.Guid(PLAYER_INSTANCE_ID),
                },
            },
        },
    }
    return gvas


def _lazy_player_session(
    root: Path,
) -> tuple[SaveSession, LazyPlayerEntity, Path]:
    players_root = root / "Players"
    players_root.mkdir()
    level = _gvas(1)
    player_gvas = _player_gvas()
    player_path = players_root / f"{UUID2HexStr(PLAYER_ID)}.sav"
    (root / "Level.sav").write_bytes(
        compress_gvas_to_sav(
            level.write(MAIN_SKIP_PROPERTIES),
            0x32,
            zlib=True,
        )
    )
    player_path.write_bytes(
        compress_gvas_to_sav(
            player_gvas.write(PLAYER_SKIP_PROPERTIES),
            0x32,
            zlib=True,
        )
    )
    player = LazyPlayerEntity(
        PLAYER_GROUP_ID,
        _player_object(),
        {},
        lambda: (player_gvas, 0x32),
    )
    manager = SimpleNamespace(
        gvas_file=level,
        _compression_times=0x32,
        player_mapping={str(PLAYER_ID): player},
        item_container_data=SimpleNamespace(container_map={}),
        get_player=lambda value: (
            player if str(value) == str(PLAYER_ID) else None
        ),
    )
    return SaveSession.from_loaded_manager(manager, root), player, player_path


def _session(root: Path) -> SaveSession:
    level = _gvas(1)
    (root / "Level.sav").write_bytes(
        compress_gvas_to_sav(
            level.write(MAIN_SKIP_PROPERTIES),
            0x32,
            zlib=True,
        )
    )
    manager = SimpleNamespace(
        gvas_file=level,
        _compression_times=0x32,
        player_mapping={},
        item_container_data=SimpleNamespace(container_map={}),
    )
    return SaveSession.from_loaded_manager(manager, root)


def _counter(path: Path) -> int:
    raw, _compression = decompress_sav_to_gvas(path.read_bytes())
    return GvasFile.read(
        raw,
        PALWORLD_TYPE_HINTS,
        MAIN_SKIP_PROPERTIES,
    ).properties["Counter"]["value"]


def test_raw_json_level_roundtrip_stays_unrestricted_until_verified_save(
    monkeypatch,
) -> None:
    with TemporaryDirectory() as temp:
        root = Path(temp)
        session = _session(root)
        editor = RawJsonEditor()

        listed = editor.list_files(session)
        assert [entry["path"] for entry in listed] == ["Level.sav"]
        document = editor.read_document(session, "Level.sav")
        decoded = json.loads(document["text"])
        assert decoded["properties"]["Counter"]["value"] == 1
        assert decoded["properties"]["RawBytes"]["value"]["values"] == [1, 2, 255]

        unchanged = editor.apply_document(
            session,
            session_id=session.session_id,
            expected_revision=0,
            relative_path="Level.sav",
            text=document["text"],
        )
        assert unchanged["changed"] is False
        assert session.revision == 0

        decoded["properties"]["Counter"]["value"] = 2
        result = editor.apply_document(
            session,
            session_id=session.session_id,
            expected_revision=0,
            relative_path="Level.sav",
            text=json.dumps(decoded),
        )

        assert result["changed"] is True
        assert result["revision"] == 1
        assert session.raw_json_pending is True
        session.require_command(session.session_id, 1)

        session.manager.dynamic_item_data = SimpleNamespace(
            assert_no_new_issues=lambda _baseline: (_ for _ in ()).throw(
                AssertionError("raw JSON must bypass domain validation")
            ),
        )
        monkeypatch.setattr(
            "palworld_pal_editor.application.save_writer."
            "inspect_decoded_character_graph",
            lambda _gvas: (_ for _ in ()).throw(
                AssertionError("raw JSON must bypass reload semantics")
            ),
        )
        saved = SaveWriter().save(session, root, 1)
        assert _counter(root / "Level.sav") == 2
        assert session.raw_json_pending is False
        assert Path(saved.backup_path).is_dir()
        assert _counter(Path(saved.backup_path) / "files" / "Level.sav") == 1


def test_raw_json_level_keeps_skipped_payloads_lossless(monkeypatch) -> None:
    with TemporaryDirectory() as temp:
        root = Path(temp)
        session = _session(root)
        skipped_path = ".worldSaveData.WorkSaveData"
        session.manager.gvas_file.properties["worldSaveData"]["value"][
            "WorkSaveData"
        ] = {
            "type": "ArrayProperty",
            "custom_type": skipped_path,
            "skip_type": "ArrayProperty",
            "array_type": "IntProperty",
            "id": None,
            "value": b"\0\0\0\0",
        }

        def reject_full_decode(*_args, **_kwargs):
            raise Exception("Warning: EOF not reached")

        original = PALWORLD_CUSTOM_PROPERTIES[skipped_path]
        monkeypatch.setitem(
            PALWORLD_CUSTOM_PROPERTIES,
            skipped_path,
            (reject_full_decode, original[1]),
        )

        editor = RawJsonEditor()
        result = editor.read_document(session, "Level.sav")
        document = json.loads(result["text"])
        payload = document["properties"]["worldSaveData"]["value"][
            "WorkSaveData"
        ]

        assert payload["skip_type"] == "ArrayProperty"
        assert payload["value"] == {
            "$palworld_binary_base64": "AAAAAA==",
        }
        unchanged = editor.apply_document(
            session,
            session_id=session.session_id,
            expected_revision=0,
            relative_path="Level.sav",
            text=result["text"],
        )
        assert unchanged["changed"] is False


def test_raw_json_invalid_syntax_and_structure_do_not_mutate_session() -> None:
    with TemporaryDirectory() as temp:
        root = Path(temp)
        session = _session(root)
        editor = RawJsonEditor()

        with pytest.raises(DomainError) as syntax:
            editor.apply_document(
                session,
                session_id=session.session_id,
                expected_revision=0,
                relative_path="Level.sav",
                text='{"header":',
            )
        assert syntax.value.code == "RAW_JSON_INVALID"
        assert syntax.value.details["line"] == 1

        with pytest.raises(DomainError) as structure:
            editor.apply_document(
                session,
                session_id=session.session_id,
                expected_revision=0,
                relative_path="Level.sav",
                text="{}",
            )
        assert structure.value.code == "RAW_JSON_SERIALIZATION_FAILED"
        assert session.revision == 0
        assert session.changes() == []
        assert session.raw_json_pending is False


def test_raw_json_roundtrip_preserves_existing_guid_set_layouts() -> None:
    with TemporaryDirectory() as temp:
        root = Path(temp)
        level = make_legacy_gvas(1)
        (root / "Level.sav").write_bytes(
            compress_gvas_to_sav(
                level.write(MAIN_SKIP_PROPERTIES),
                0x32,
                zlib=True,
            )
        )
        manager = SimpleNamespace(
            gvas_file=level,
            _compression_times=0x32,
            player_mapping={},
            item_container_data=SimpleNamespace(container_map={}),
        )
        session = SaveSession.from_loaded_manager(manager, root)
        editor = RawJsonEditor()

        document = json.loads(editor.read_document(session, "Level.sav")["text"])
        start_points = document["properties"]["worldSaveData"]["value"][
            "InvaderDeclarationSaveData"
        ]["value"]["ValidatedStartPointIds"]["value"]["values"]
        assert start_points == [START_POINT_ID]

        document["properties"]["Counter"]["value"] = 3
        editor.apply_document(
            session,
            session_id=session.session_id,
            expected_revision=0,
            relative_path="Level.sav",
            text=json.dumps(document),
        )
        SaveWriter().save(session, root, 1)

        assert read_start_point_ids(root / "Level.sav") == (START_POINT_ID,)
        assert read_locker_character_ids(root / "Level.sav") == (
            (LOCKER_PLAYER_UID, LOCKER_INSTANCE_ID),
        )


def test_raw_json_player_file_is_listed_loaded_and_saved() -> None:
    with TemporaryDirectory() as temp:
        root = Path(temp)
        players_root = root / "Players"
        players_root.mkdir()
        player_id = "11111111-2222-3333-4444-555555555555"
        player_path = players_root / f"{UUID2HexStr(player_id)}.sav"
        level = _gvas(1)
        player_gvas = _gvas(10)
        (root / "Level.sav").write_bytes(
            compress_gvas_to_sav(
                level.write(MAIN_SKIP_PROPERTIES),
                0x32,
                zlib=True,
            )
        )
        player_path.write_bytes(
            compress_gvas_to_sav(
                player_gvas.write(PLAYER_SKIP_PROPERTIES),
                0x32,
                zlib=True,
            )
        )
        player = SimpleNamespace(
            PlayerUId=player_id,
            InstanceId="99999999-aaaa-bbbb-cccc-dddddddddddd",
            NickName="JSON Player",
            Level=20,
            PlayerGVAS=(player_gvas, 0x32),
            load_details=lambda: None,
        )
        manager = SimpleNamespace(
            gvas_file=level,
            _compression_times=0x32,
            player_mapping={player_id: player},
            item_container_data=SimpleNamespace(container_map={}),
            get_player=lambda value: player if str(value) == player_id else None,
        )
        session = SaveSession.from_loaded_manager(manager, root)
        editor = RawJsonEditor()

        listed = editor.list_files(session)
        assert [entry["path"] for entry in listed] == [
            "Level.sav",
            f"Players/{player_path.name}",
        ]
        assert listed[1]["player_name"] == "JSON Player"
        document = json.loads(
            editor.read_document(session, listed[1]["path"])["text"]
        )
        document["properties"]["Counter"]["value"] = 11
        editor.apply_document(
            session,
            session_id=session.session_id,
            expected_revision=0,
            relative_path=listed[1]["path"],
            text=json.dumps(document),
        )
        result = SaveWriter().save(session, root, 1)

        assert result.written_files == (f"Players/{player_path.name}",)
        assert _counter(player_path) == 11


def test_raw_json_real_player_entity_allows_identity_replacement() -> None:
    with TemporaryDirectory() as temp:
        root = Path(temp)
        session, player, player_path = _lazy_player_session(root)
        editor = RawJsonEditor()
        relative_path = f"Players/{player_path.name}"

        document = json.loads(editor.read_document(session, relative_path)["text"])
        document["properties"]["Counter"]["value"] = 11
        document["properties"]["SaveData"]["value"]["IndividualId"]["value"][
            "PlayerUId"
        ]["value"] = str(REPLACEMENT_PLAYER_ID)
        result = editor.apply_document(
            session,
            session_id=session.session_id,
            expected_revision=0,
            relative_path=relative_path,
            text=json.dumps(document),
        )

        details = player.load_details()
        assert result["changed"] is True
        assert details._player_save_data is details.PlayerGVAS[0].properties[
            "SaveData"
        ]["value"]
        assert str(
            details._player_save_data["IndividualId"]["value"]["PlayerUId"][
                "value"
            ]
        ) == str(REPLACEMENT_PLAYER_ID)

        SaveWriter().save(session, root, 1)
        raw, _compression = decompress_sav_to_gvas(player_path.read_bytes())
        saved = GvasFile.read(
            raw,
            PALWORLD_TYPE_HINTS,
            PLAYER_SKIP_PROPERTIES,
        )
        assert saved.properties["Counter"]["value"] == 11
        assert str(
            saved.properties["SaveData"]["value"]["IndividualId"]["value"][
                "PlayerUId"
            ]["value"]
        ) == str(REPLACEMENT_PLAYER_ID)


def test_raw_json_pending_session_can_still_be_explicitly_discarded() -> None:
    with TemporaryDirectory() as temp:
        session = _session(Path(temp))
        editor = RawJsonEditor()
        document = json.loads(editor.read_document(session, "Level.sav")["text"])
        document["properties"]["Counter"]["value"] = 2
        editor.apply_document(
            session,
            session_id=session.session_id,
            expected_revision=0,
            relative_path="Level.sav",
            text=json.dumps(document),
        )
        runtime = SessionRuntime()
        runtime.replace_for_tests(session)

        result = runtime.close(
            session.session_id,
            1,
            discard_changes=True,
        )

        assert result["discarded_change_count"] == 1
