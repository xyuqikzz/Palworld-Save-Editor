from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from palworld_save_tools.gvas import GvasFile, GvasHeader
from palworld_save_tools.palsav import compress_gvas_to_sav
from palworld_save_tools.paltypes import PALWORLD_CUSTOM_PROPERTIES

from palworld_pal_editor.application.global_palbox import GlobalPalboxDocument
from palworld_pal_editor.core.pal_objects import PalObjects, toUUID
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.storage.wgs_format import parse_index
from tests.wgs_fixture import make_user_directory


ZERO = "00000000-0000-0000-0000-000000000000"
CONTAINER_ID = "11111111-2222-3333-4444-555555555555"
PAL_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _parameter(
    species_id: str,
    instance_id: str,
    slot_index: int,
) -> tuple[dict, dict]:
    record = PalObjects.PalSaveParameter(
        instance_id,
        ZERO,
        CONTAINER_ID,
        slot_index,
        ZERO,
    )
    parameter = record["value"]["RawData"]["value"]["object"][
        "SaveParameter"
    ]
    parameter["value"]["CharacterID"] = PalObjects.NameProperty(species_id)
    parameter["value"]["SkinName"] = PalObjects.NameProperty("None")
    parameter["value"]["Level"] = PalObjects.ByteProperty(1)
    external_id = {
        "struct_type": "PalInstanceID",
        "struct_id": PalObjects.EMPTY_UUID,
        "id": None,
        "value": {
            "PlayerUId": PalObjects.Guid(ZERO),
            "InstanceId": PalObjects.Guid(instance_id),
            "DebugName": PalObjects.StrProperty(""),
        },
        "type": "StructProperty",
    }
    return parameter, external_id


def _entry(species_id: str, instance_id: str, slot_index: int) -> dict:
    parameter, external_id = _parameter(species_id, instance_id, slot_index)
    return {"SaveParameter": parameter, "InstanceId": external_id}


def _empty_entry() -> dict:
    entry = _entry("None", ZERO, -1)
    entry["SaveParameter"]["value"]["SlotId"]["value"]["ContainerId"][
        "value"
    ]["ID"]["value"] = toUUID(ZERO)
    return entry


def _gvas(*, capacity: int = 3, occupied: int = 1) -> GvasFile:
    values = []
    for index in range(occupied):
        instance_id = PAL_ID if index == 0 else str(
            toUUID(f"00000000-0000-0000-0000-{index + 1:012d}")
        )
        values.append(_entry("SheepBall", instance_id, index))
    values.extend(_empty_entry() for _ in range(capacity - occupied))
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
            "engine_version_branch": "synthetic-global-palbox",
            "custom_version_format": 3,
            "custom_versions": [],
            "save_game_class_name": "/Script/Pal.PalGlobalPalStorageSaveGame",
        }
    )
    gvas.properties = {
        "SaveParameterArray": PalObjects.ArrayProperty(
            "StructProperty",
            {
                "prop_name": "SaveParameterArray",
                "prop_type": "StructProperty",
                "values": values,
                "type_name": "PalGlobalPalStorageSaveParameter",
                "id": PalObjects.EMPTY_UUID,
            },
        )
    }
    gvas.trailer = b"\0\0\0\0"
    return gvas


def _sav(*, capacity: int = 3, occupied: int = 1) -> bytes:
    return compress_gvas_to_sav(
        _gvas(capacity=capacity, occupied=occupied).write(
            PALWORLD_CUSTOM_PROPERTIES
        ),
        0x32,
        zlib=True,
    )


def test_global_palbox_open_edit_save_reopen_roundtrip(tmp_path: Path) -> None:
    source = tmp_path / "GlobalPalStorage.sav"
    source.write_bytes(_sav())
    backup_root = tmp_path / "backups"
    document = GlobalPalboxDocument.open(
        source,
        process_checker=lambda: False,
        backup_root=backup_root,
    )

    initial = document.summary()
    assert initial["capacity"] == 3
    assert initial["occupied"] == 1
    assert initial["free"] == 2
    assert document.pals()[0]["IconAccessKey"] == "SheepBall"

    updated = document.update_pal(
        pal_id=PAL_ID,
        expected_revision=0,
        values={
            "species_id": "GYM_ElecPanda_Otomo",
            "nickname": "Tower Partner",
            "level": 10,
        },
    )
    added = document.add_pal(
        species_id="GrassBoss",
        expected_revision=updated["revision"],
    )
    cloned = document.clone_pal(
        pal_id=added["pal"]["InstanceId"],
        expected_revision=added["revision"],
    )
    deleted = document.delete_pal(
        pal_id=cloned["pal"]["InstanceId"],
        expected_revision=cloned["revision"],
    )

    result = document.save(expected_revision=deleted["revision"])

    assert result["backup_path"]
    assert Path(result["backup_path"]).is_file()
    assert result["source_reloaded"] is True
    reopened = GlobalPalboxDocument.open(
        source,
        process_checker=lambda: False,
        backup_root=backup_root,
    )
    pals = {pal["InstanceId"]: pal for pal in reopened.pals()}
    assert pals[PAL_ID]["CharacterID"] == "GYM_ElecPanda_Otomo"
    assert pals[PAL_ID]["NickName"] == "Tower Partner"
    assert pals[PAL_ID]["Level"] == 10
    assert any(pal["CharacterID"] == "GrassBoss" for pal in pals.values())
    assert reopened.summary()["occupied"] == 2


def test_global_palbox_full_file_can_replace_existing_species(tmp_path: Path) -> None:
    source = tmp_path / "GlobalPalStorage.sav"
    source.write_bytes(_sav(capacity=2, occupied=2))
    document = GlobalPalboxDocument.open(
        source,
        process_checker=lambda: False,
        backup_root=tmp_path / "backups",
    )

    with pytest.raises(DomainError) as raised:
        document.add_pal(species_id="GYM_ElecPanda", expected_revision=0)
    assert raised.value.code == "GLOBAL_PALBOX_FULL"

    result = document.update_pal(
        pal_id=PAL_ID,
        expected_revision=0,
        values={"species_id": "GYM_ElecPanda"},
    )

    assert result["pal"]["CharacterID"] == "GYM_ElecPanda"
    assert document.summary()["free"] == 0


def test_global_palbox_full_file_can_delete_then_add_and_reopen(
    tmp_path: Path,
) -> None:
    source = tmp_path / "GlobalPalStorage.sav"
    source.write_bytes(_sav(capacity=2, occupied=2))
    backup_root = tmp_path / "backups"
    document = GlobalPalboxDocument.open(
        source,
        process_checker=lambda: False,
        backup_root=backup_root,
    )

    deleted = document.delete_pal(pal_id=PAL_ID, expected_revision=0)
    added = document.add_pal(
        species_id="GrassBoss",
        expected_revision=deleted["revision"],
    )
    document.save(expected_revision=added["revision"])
    reopened = GlobalPalboxDocument.open(
        source,
        process_checker=lambda: False,
        backup_root=backup_root,
    )

    assert reopened.summary()["occupied"] == 2
    assert any(
        pal["CharacterID"] == "GrassBoss" for pal in reopened.pals()
    )


def test_global_palbox_xgp_open_edit_save_reopen_roundtrip(tmp_path: Path) -> None:
    user = make_user_directory(
        tmp_path / "wgs",
        "0000000000000000_00000000000000000000000000000000",
        {},
        account_files={"GlobalPalStorage": _sav()},
    )
    source_hashes = {
        path.relative_to(user).as_posix(): path.read_bytes()
        for path in user.rglob("*")
        if path.is_file()
    }
    document = GlobalPalboxDocument.open(
        user,
        process_checker=lambda: False,
        backup_root=tmp_path / "backups",
    )

    updated = document.update_pal(
        pal_id=PAL_ID,
        expected_revision=0,
        values={"species_id": "GYM_ElecPanda", "nickname": "WGS Global"},
    )
    result = document.save(expected_revision=updated["revision"])

    assert result["platform"] == "xgp"
    assert result["source_reloaded"] is True
    assert Path(result["backup_path"]).is_dir()
    reopened = GlobalPalboxDocument.open(
        user / "containers.index",
        process_checker=lambda: False,
        backup_root=tmp_path / "backups",
    )
    pal = next(item for item in reopened.pals() if item["InstanceId"] == PAL_ID)
    assert pal["CharacterID"] == "GYM_ElecPanda"
    assert pal["NickName"] == "WGS Global"

    index = parse_index((user / "containers.index").read_bytes())
    entry = next(item for item in index.entries if item.name.rstrip("\0") == "GlobalPalStorage")
    assert entry.cloud_id.rstrip("\0") == ""
    assert entry.flags & 0x4
    changed = {
        path.relative_to(user).as_posix()
        for path in user.rglob("*")
        if path.is_file() and source_hashes.get(path.relative_to(user).as_posix()) != path.read_bytes()
    }
    assert "containers.index" in changed
    assert len(changed) == 2


def test_global_palbox_stops_if_game_starts_before_replacement(
    tmp_path: Path,
) -> None:
    source = tmp_path / "GlobalPalStorage.sav"
    original = _sav()
    source.write_bytes(original)
    checks = 0

    def game_running() -> bool:
        nonlocal checks
        checks += 1
        return checks >= 3

    document = GlobalPalboxDocument.open(
        source,
        process_checker=game_running,
        backup_root=tmp_path / "backups",
    )
    document.update_pal(
        pal_id=PAL_ID,
        expected_revision=0,
        values={"species_id": "GYM_ElecPanda"},
    )

    with pytest.raises(DomainError) as raised:
        document.save(expected_revision=1)

    assert raised.value.code == "GLOBAL_PALBOX_GAME_RUNNING"
    assert source.read_bytes() == original
    assert document.summary()["pending_change_count"] == 1


def test_global_palbox_save_rejects_external_source_change(tmp_path: Path) -> None:
    source = tmp_path / "GlobalPalStorage.sav"
    original = _sav()
    source.write_bytes(original)
    document = GlobalPalboxDocument.open(
        source,
        process_checker=lambda: False,
        backup_root=tmp_path / "backups",
    )
    document.update_pal(
        pal_id=PAL_ID,
        expected_revision=0,
        values={"species_id": "GYM_ElecPanda"},
    )
    source.write_bytes(original + b"external-change")

    with pytest.raises(DomainError) as raised:
        document.save(expected_revision=1)

    assert raised.value.code == "GLOBAL_PALBOX_SOURCE_CHANGED"
    assert source.read_bytes() == original + b"external-change"


def test_global_palbox_rejects_unknown_entry_structure(tmp_path: Path) -> None:
    gvas = _gvas()
    broken = deepcopy(
        gvas.properties["SaveParameterArray"]["value"]["values"][0]
    )
    broken.pop("InstanceId")
    gvas.properties["SaveParameterArray"]["value"]["values"][0] = broken
    source = tmp_path / "GlobalPalStorage.sav"
    source.write_bytes(
        compress_gvas_to_sav(
            gvas.write(PALWORLD_CUSTOM_PROPERTIES),
            0x32,
            zlib=True,
        )
    )

    with pytest.raises(DomainError) as raised:
        GlobalPalboxDocument.open(source, process_checker=lambda: False)

    assert raised.value.code == "GLOBAL_PALBOX_STRUCTURE_UNSUPPORTED"


def test_global_palbox_opens_unknown_species_with_a_valid_slot(
    tmp_path: Path,
) -> None:
    gvas = _gvas()
    entry = gvas.properties["SaveParameterArray"]["value"]["values"][0]
    entry["SaveParameter"]["value"]["CharacterID"] = PalObjects.NameProperty(
        "FuturePal"
    )
    source = tmp_path / "GlobalPalStorage.sav"
    source.write_bytes(
        compress_gvas_to_sav(
            gvas.write(PALWORLD_CUSTOM_PROPERTIES),
            0x32,
            zlib=True,
        )
    )

    document = GlobalPalboxDocument.open(source, process_checker=lambda: False)

    assert document.pals()[0]["CharacterID"] == "FuturePal"


def test_global_palbox_accepts_game_produced_duplicate_source_slots(
    tmp_path: Path,
) -> None:
    gvas = _gvas(capacity=3, occupied=2)
    values = gvas.properties["SaveParameterArray"]["value"]["values"]
    PalObjects.set_PalCharacterSlotId(
        values[1]["SaveParameter"]["value"]["SlotId"],
        toUUID(CONTAINER_ID),
        0,
    )
    source = tmp_path / "GlobalPalStorage.sav"
    source.write_bytes(
        compress_gvas_to_sav(
            gvas.write(PALWORLD_CUSTOM_PROPERTIES),
            0x32,
            zlib=True,
        )
    )

    document = GlobalPalboxDocument.open(source, process_checker=lambda: False)

    assert document.summary()["occupied"] == 2
