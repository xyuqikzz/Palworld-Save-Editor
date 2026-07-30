from __future__ import annotations

from pathlib import Path

import pytest

from palworld_save_tools.gvas import GvasFile, GvasHeader
from palworld_save_tools.palsav import compress_gvas_to_sav

from palworld_pal_editor.application.dps_migration import (
    DpsSave,
    import_character_dps,
    rewrite_full_dps_tree,
    validate_dps_tree,
)
from palworld_pal_editor.core.pal_objects import PalObjects, toUUID
from palworld_pal_editor.core.save_manager import MAIN_SKIP_PROPERTIES
from palworld_pal_editor.domain.errors import DomainError


SOURCE_UID = "11111111-1111-1111-1111-111111111111"
TARGET_UID = "22222222-2222-2222-2222-222222222222"
OTHER_UID = "33333333-3333-3333-3333-333333333333"
SOURCE_CONTAINER = "44444444-4444-4444-4444-444444444444"
TARGET_CONTAINER = "55555555-5555-5555-5555-555555555555"
PAL_ID = "66666666-6666-6666-6666-666666666666"
ZERO_UUID = "00000000-0000-0000-0000-000000000000"


def _struct(struct_type: str, value: object) -> dict:
    return {
        "struct_type": struct_type,
        "struct_id": PalObjects.EMPTY_UUID,
        "id": None,
        "value": value,
        "type": "StructProperty",
    }


def _dps_gvas(
    *,
    owner_uid: str = SOURCE_UID,
    container_id: str = SOURCE_CONTAINER,
    pal_id: str = PAL_ID,
) -> GvasFile:
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
            "engine_version_branch": "synthetic-dps-migration",
            "custom_version_format": 3,
            "custom_versions": [],
            "save_game_class_name": (
                "/Script/Pal.PalDimensionPalStorageSaveGame"
            ),
        }
    )
    parameter = {
        "CharacterID": PalObjects.NameProperty("SheepBall"),
        "OwnerPlayerUId": PalObjects.Guid(owner_uid),
        "OldOwnerPlayerUIds": PalObjects.ArrayProperty(
            "StructProperty",
            {
                "prop_name": "OldOwnerPlayerUIds",
                "prop_type": "StructProperty",
                "values": [toUUID(owner_uid)],
                "type_name": "Guid",
                "id": PalObjects.EMPTY_UUID,
            },
        ),
        "LastNickNameModifierPlayerUid": PalObjects.Guid(owner_uid),
        "SlotId": PalObjects.PalCharacterSlotId(2, container_id),
    }
    instance = _struct(
        "PalInstanceID",
        {
            "PlayerUId": PalObjects.Guid(ZERO_UUID),
            "InstanceId": PalObjects.Guid(pal_id),
            "DebugName": PalObjects.StrProperty(""),
        },
    )
    entry = {
        "SaveParameter": _struct(
            "PalIndividualCharacterSaveParameter",
            parameter,
        ),
        "InstanceId": instance,
    }
    gvas.properties = {
        "SaveParameterArray": PalObjects.ArrayProperty(
            "StructProperty",
            {
                "prop_name": "SaveParameterArray",
                "prop_type": "StructProperty",
                "values": [entry],
                "type_name": "PalDimensionPalStorageSaveParameter",
                "id": PalObjects.EMPTY_UUID,
            },
        )
    }
    gvas.trailer = b"\0\0\0\0"
    return gvas


def _write_dps(
    root: Path,
    player_uid: str,
    *,
    owner_uid: str = SOURCE_UID,
    container_id: str = SOURCE_CONTAINER,
    pal_id: str = PAL_ID,
) -> Path:
    players = root / "Players"
    players.mkdir(parents=True, exist_ok=True)
    path = players / f"{player_uid.replace('-', '').upper()}_dps.sav"
    path.write_bytes(
        compress_gvas_to_sav(
            _dps_gvas(
                owner_uid=owner_uid,
                container_id=container_id,
                pal_id=pal_id,
            ).write(MAIN_SKIP_PROPERTIES),
            0x32,
            zlib=True,
        )
    )
    return path


def test_supported_dps_structure_roundtrips(tmp_path: Path) -> None:
    path = _write_dps(tmp_path, SOURCE_UID)

    saves = validate_dps_tree(tmp_path)

    assert len(saves) == 1
    assert saves[0].player_uid == SOURCE_UID
    assert saves[0].active_pal_ids() == {PAL_ID}
    assert DpsSave.load(path).active_pal_ids() == {PAL_ID}


def test_character_dps_rebinds_all_personal_identity_fields(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    _write_dps(
        source,
        SOURCE_UID,
        owner_uid=OTHER_UID,
    )
    _write_dps(
        target,
        TARGET_UID,
        owner_uid=TARGET_UID,
        container_id=TARGET_CONTAINER,
        pal_id="77777777-7777-7777-7777-777777777777",
    )

    pal_mapping = import_character_dps(
        source,
        target,
        source_player_uid=SOURCE_UID,
        target_player_uid=TARGET_UID,
        target_pal_storage_id=TARGET_CONTAINER,
        used_pal_ids=set(),
    )

    output = DpsSave.load(
        target / "Players" / f"{TARGET_UID.replace('-', '').upper()}_dps.sav"
    )
    record = output.active_records()[0]
    assert pal_mapping == {PAL_ID: PAL_ID}
    assert record.owner_player_uid == TARGET_UID
    assert record.old_owner_player_uids == (TARGET_UID,)
    assert record.last_nickname_modifier_player_uid == TARGET_UID
    assert record.container_id == TARGET_CONTAINER
    assert record.pal_instance_id == PAL_ID


def test_character_dps_remaps_pal_instance_collision(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source_path = _write_dps(source, SOURCE_UID)
    source_save = DpsSave.load(source_path)
    source_save.active_records()[0].parameter["LinkedInstanceId"] = (
        PalObjects.Guid(PAL_ID)
    )
    source_path.write_bytes(source_save.serialize())

    pal_mapping = import_character_dps(
        source,
        target,
        source_player_uid=SOURCE_UID,
        target_player_uid=TARGET_UID,
        target_pal_storage_id=TARGET_CONTAINER,
        used_pal_ids={PAL_ID},
    )

    output = DpsSave.load(
        target / "Players" / f"{TARGET_UID.replace('-', '').upper()}_dps.sav"
    )
    replacement = output.active_records()[0].pal_instance_id
    assert replacement != PAL_ID
    assert pal_mapping == {PAL_ID: replacement}
    assert (
        str(
            output.active_records()[0]
            .parameter["LinkedInstanceId"]["value"]
        )
        == replacement
    )


def test_full_dps_rewrite_renames_sidecar_and_rewrites_player_uids(
    tmp_path: Path,
) -> None:
    _write_dps(tmp_path, SOURCE_UID)

    rewrite_full_dps_tree(tmp_path, {SOURCE_UID: TARGET_UID})

    assert not (
        tmp_path / "Players" / f"{SOURCE_UID.replace('-', '').upper()}_dps.sav"
    ).exists()
    output = DpsSave.load(
        tmp_path / "Players" / f"{TARGET_UID.replace('-', '').upper()}_dps.sav"
    )
    record = output.active_records()[0]
    assert record.owner_player_uid == TARGET_UID
    assert record.old_owner_player_uids == (TARGET_UID,)
    assert record.last_nickname_modifier_player_uid == TARGET_UID
    assert record.container_id == SOURCE_CONTAINER
    assert record.pal_instance_id == PAL_ID


def test_unknown_dps_structure_fails_closed(tmp_path: Path) -> None:
    path = _write_dps(tmp_path, SOURCE_UID)
    gvas = _dps_gvas()
    gvas.header.save_game_class_name = "/Script/Pal.UnknownSaveGame"
    path.write_bytes(
        compress_gvas_to_sav(
            gvas.write(MAIN_SKIP_PROPERTIES),
            0x32,
            zlib=True,
        )
    )

    with pytest.raises(DomainError) as raised:
        validate_dps_tree(tmp_path)

    assert raised.value.code == "MIGRATION_DPS_UNSUPPORTED"


def test_opaque_dps_player_reference_fails_before_replacing_file(
    tmp_path: Path,
) -> None:
    path = _write_dps(tmp_path, SOURCE_UID)
    original = path.read_bytes()
    save = DpsSave.load(path)
    save.active_records()[0].parameter["OpaqueIdentity"] = PalObjects.Guid(
        SOURCE_UID
    )
    path.write_bytes(
        compress_gvas_to_sav(
            save.gvas.write(MAIN_SKIP_PROPERTIES),
            0x32,
            zlib=True,
        )
    )
    unsupported = path.read_bytes()

    with pytest.raises(DomainError) as raised:
        rewrite_full_dps_tree(tmp_path, {SOURCE_UID: TARGET_UID})

    assert raised.value.code == "MIGRATION_DPS_UNSUPPORTED"
    assert path.read_bytes() == unsupported
    assert path.read_bytes() != original
