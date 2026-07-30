from __future__ import annotations

import contextlib
from copy import deepcopy
from dataclasses import dataclass
import io
from pathlib import Path
import re
from typing import Any, Iterable
import uuid

from palworld_save_tools.archive import UUID
from palworld_save_tools.gvas import GvasFile
from palworld_save_tools.palsav import (
    compress_gvas_to_sav,
    decompress_sav_to_gvas,
)
from palworld_save_tools.paltypes import PALWORLD_TYPE_HINTS

from palworld_pal_editor.core.pal_objects import (
    PalObjects,
    UUID2HexStr,
    toUUID,
)
from palworld_pal_editor.core.save_manager import MAIN_SKIP_PROPERTIES
from palworld_pal_editor.domain.errors import DomainError


_DPS_CLASS_NAME = "/Script/Pal.PalDimensionPalStorageSaveGame"
_DPS_FILE_PATTERN = re.compile(r"([0-9A-Fa-f]{32})_dps\.sav")
_ZERO_UUID = "00000000-0000-0000-0000-000000000000"
_PLAYER_UID_FIELDS = frozenset(
    {
        "ownerplayeruid",
        "owner_player_uid",
        "oldownerplayeruids",
        "old_owner_player_uids",
        "lastnicknamemodifierplayeruid",
        "last_nickname_modifier_player_uid",
        "sellerplayeruid",
        "seller_player_uid",
    }
)


def _unsupported(path: Path, message: str, **details: Any) -> DomainError:
    return DomainError(
        code="MIGRATION_DPS_UNSUPPORTED",
        message=message,
        details={"file": path.as_posix(), **details},
        http_status=409,
    )


def _normalize_uuid(value: Any) -> str | None:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return None


def _require_guid(path: Path, value: Any, field: str) -> str:
    if (
        not isinstance(value, dict)
        or value.get("type") != "StructProperty"
        or value.get("struct_type") != "Guid"
    ):
        raise _unsupported(
            path,
            "A dimensional Pal storage identity field uses an unknown structure.",
            field=field,
        )
    normalized = _normalize_uuid(value.get("value"))
    if normalized is None:
        raise _unsupported(
            path,
            "A dimensional Pal storage identity field is not a UUID.",
            field=field,
        )
    return normalized


def _require_old_owners(path: Path, value: Any) -> tuple[str, ...]:
    if (
        not isinstance(value, dict)
        or value.get("type") != "ArrayProperty"
        or value.get("array_type") != "StructProperty"
        or not isinstance(value.get("value"), dict)
        or value["value"].get("prop_name") != "OldOwnerPlayerUIds"
        or value["value"].get("prop_type") != "StructProperty"
        or value["value"].get("type_name") != "Guid"
        or not isinstance(value["value"].get("values"), list)
    ):
        raise _unsupported(
            path,
            "A dimensional Pal storage owner history uses an unknown structure.",
            field="OldOwnerPlayerUIds",
        )
    result: list[str] = []
    for owner in value["value"]["values"]:
        normalized = _normalize_uuid(owner)
        if normalized is None:
            raise _unsupported(
                path,
                "A dimensional Pal storage owner history contains a non-UUID value.",
                field="OldOwnerPlayerUIds",
            )
        result.append(normalized)
    return tuple(result)


@dataclass(frozen=True)
class DpsRecord:
    path: Path
    entry: dict[str, Any]

    @property
    def parameter(self) -> dict[str, Any]:
        return self.entry["SaveParameter"]["value"]

    @property
    def character_id(self) -> str:
        return str(self.parameter["CharacterID"]["value"])

    @property
    def active(self) -> bool:
        return self.character_id not in {"", "None"}

    @property
    def owner_player_uid(self) -> str:
        return _require_guid(
            self.path,
            self.parameter["OwnerPlayerUId"],
            "OwnerPlayerUId",
        )

    @property
    def old_owner_player_uids(self) -> tuple[str, ...]:
        return _require_old_owners(
            self.path,
            self.parameter["OldOwnerPlayerUIds"],
        )

    @property
    def last_nickname_modifier_player_uid(self) -> str:
        return _require_guid(
            self.path,
            self.parameter["LastNickNameModifierPlayerUid"],
            "LastNickNameModifierPlayerUid",
        )

    @property
    def container_id(self) -> str:
        slot = PalObjects.get_PalCharacterSlotId(self.parameter["SlotId"])
        if slot is None:
            raise _unsupported(
                self.path,
                "A dimensional Pal storage slot uses an unknown structure.",
                field="SlotId",
            )
        return str(slot[0])

    @property
    def slot_index(self) -> int:
        slot = PalObjects.get_PalCharacterSlotId(self.parameter["SlotId"])
        if slot is None:
            raise _unsupported(
                self.path,
                "A dimensional Pal storage slot uses an unknown structure.",
                field="SlotId",
            )
        return int(slot[1])

    @property
    def pal_instance_id(self) -> str:
        return _require_guid(
            self.path,
            self.entry["InstanceId"]["value"]["InstanceId"],
            "InstanceId.InstanceId",
        )

    def rebind(
        self,
        *,
        player_uid: str,
        container_id: str,
        pal_instance_id: str,
    ) -> None:
        PalObjects.set_BaseType(
            self.parameter["OwnerPlayerUId"],
            toUUID(player_uid),
        )
        self.parameter["OldOwnerPlayerUIds"]["value"]["values"] = [
            toUUID(player_uid)
        ]
        PalObjects.set_BaseType(
            self.parameter["LastNickNameModifierPlayerUid"],
            toUUID(player_uid),
        )
        PalObjects.set_PalCharacterSlotId(
            self.parameter["SlotId"],
            container_id,
            self.slot_index,
        )
        PalObjects.set_BaseType(
            self.entry["InstanceId"]["value"]["InstanceId"],
            toUUID(pal_instance_id),
        )


@dataclass
class DpsSave:
    path: Path
    player_uid: str
    gvas: GvasFile
    compression: int
    original_raw: bytes

    @classmethod
    def load(cls, path: Path) -> "DpsSave":
        match = _DPS_FILE_PATTERN.fullmatch(path.name)
        if match is None:
            raise _unsupported(
                path,
                "A dimensional Pal storage file name has an unknown identity layout.",
            )
        try:
            player_uid = str(uuid.UUID(hex=match.group(1)))
            with contextlib.redirect_stdout(io.StringIO()), (
                contextlib.redirect_stderr(io.StringIO())
            ):
                raw, compression = decompress_sav_to_gvas(path.read_bytes())
                gvas = GvasFile.read(
                    raw,
                    PALWORLD_TYPE_HINTS,
                    MAIN_SKIP_PROPERTIES,
                )
        except DomainError:
            raise
        except Exception as error:
            raise _unsupported(
                path,
                "A dimensional Pal storage file could not be parsed safely.",
            ) from error
        save = cls(
            path=path,
            player_uid=player_uid,
            gvas=gvas,
            compression=compression,
            original_raw=raw,
        )
        save._validate()
        return save

    def _validate(self) -> None:
        if self.gvas.header.save_game_class_name != _DPS_CLASS_NAME:
            raise _unsupported(
                self.path,
                "A dimensional Pal storage file uses an unknown save class.",
            )
        if set(self.gvas.properties) != {"SaveParameterArray"}:
            raise _unsupported(
                self.path,
                "A dimensional Pal storage file has unknown top-level properties.",
            )
        array = self.gvas.properties["SaveParameterArray"]
        value = array.get("value") if isinstance(array, dict) else None
        if (
            not isinstance(array, dict)
            or array.get("type") != "ArrayProperty"
            or array.get("array_type") != "StructProperty"
            or not isinstance(value, dict)
            or value.get("prop_name") != "SaveParameterArray"
            or value.get("prop_type") != "StructProperty"
            or value.get("type_name")
            != "PalDimensionPalStorageSaveParameter"
            or not isinstance(value.get("values"), list)
        ):
            raise _unsupported(
                self.path,
                "A dimensional Pal storage file uses an unknown entry array.",
            )
        seen: set[str] = set()
        for index, entry in enumerate(value["values"]):
            self._validate_entry(entry, index)
            record = DpsRecord(self.path, entry)
            if not record.active:
                continue
            pal_id = record.pal_instance_id
            if pal_id == _ZERO_UUID or pal_id in seen:
                raise _unsupported(
                    self.path,
                    "A dimensional Pal storage file contains an invalid or duplicate Pal identity.",
                    entry=index,
                    pal_instance_id=pal_id,
                )
            seen.add(pal_id)
            record.owner_player_uid
            record.old_owner_player_uids
            record.last_nickname_modifier_player_uid
            record.container_id

    def _validate_entry(self, entry: Any, index: int) -> None:
        if not isinstance(entry, dict) or set(entry) != {
            "SaveParameter",
            "InstanceId",
        }:
            raise _unsupported(
                self.path,
                "A dimensional Pal storage entry has an unknown structure.",
                entry=index,
            )
        parameter = entry["SaveParameter"]
        instance = entry["InstanceId"]
        if (
            not isinstance(parameter, dict)
            or parameter.get("type") != "StructProperty"
            or parameter.get("struct_type")
            != "PalIndividualCharacterSaveParameter"
            or not isinstance(parameter.get("value"), dict)
            or not isinstance(instance, dict)
            or instance.get("type") != "StructProperty"
            or instance.get("struct_type") != "PalInstanceID"
            or not isinstance(instance.get("value"), dict)
        ):
            raise _unsupported(
                self.path,
                "A dimensional Pal storage entry uses an unknown save parameter layout.",
                entry=index,
            )
        fields = parameter["value"]
        character = fields.get("CharacterID")
        required = {
            "OwnerPlayerUId",
            "OldOwnerPlayerUIds",
            "LastNickNameModifierPlayerUid",
            "SlotId",
        }
        if (
            not isinstance(character, dict)
            or character.get("type") != "NameProperty"
            or not required.issubset(fields)
            or not {"PlayerUId", "InstanceId"}.issubset(instance["value"])
        ):
            raise _unsupported(
                self.path,
                "A dimensional Pal storage entry is missing required identity fields.",
                entry=index,
            )
        _require_guid(
            self.path,
            instance["value"]["PlayerUId"],
            "InstanceId.PlayerUId",
        )
        _require_guid(
            self.path,
            instance["value"]["InstanceId"],
            "InstanceId.InstanceId",
        )

    def records(self) -> tuple[DpsRecord, ...]:
        values = self.gvas.properties["SaveParameterArray"]["value"]["values"]
        return tuple(DpsRecord(self.path, item) for item in values)

    def active_records(self) -> tuple[DpsRecord, ...]:
        return tuple(record for record in self.records() if record.active)

    def active_pal_ids(self) -> set[str]:
        return {record.pal_instance_id for record in self.active_records()}

    def rewrite_player_uids(self, mapping: dict[str, str]) -> None:
        normalized = {
            str(uuid.UUID(source)): str(uuid.UUID(target))
            for source, target in mapping.items()
        }
        self._require_no_opaque_uuid_occurrences(normalized)
        _rewrite_known_player_uids(self.gvas.properties, normalized)
        self._validate()

    def rewrite_uuid_values(self, mapping: dict[str, str]) -> None:
        normalized = {
            str(uuid.UUID(source)): str(uuid.UUID(target))
            for source, target in mapping.items()
        }
        self._require_no_opaque_uuid_occurrences(normalized)
        _rewrite_uuid_node(self.gvas.properties, normalized)
        self._validate()

    def serialize(self, *, removed_uuids: Iterable[str] = ()) -> bytes:
        try:
            raw = deepcopy(self.gvas).write(MAIN_SKIP_PROPERTIES)
            removed = {
                str(uuid.UUID(value))
                for value in removed_uuids
                if str(uuid.UUID(value)) != _ZERO_UUID
            }
            for player_uid in removed:
                if UUID.from_str(player_uid).raw_bytes in raw:
                    raise _unsupported(
                        self.path,
                        "An opaque reference to a replaced dimensional storage identity remains.",
                        identity=player_uid,
                    )
            with contextlib.redirect_stdout(io.StringIO()), (
                contextlib.redirect_stderr(io.StringIO())
            ):
                return compress_gvas_to_sav(raw, self.compression)
        except DomainError:
            raise
        except Exception as error:
            raise _unsupported(
                self.path,
                "A dimensional Pal storage file could not be serialized safely.",
            ) from error

    def _require_no_opaque_uuid_occurrences(
        self,
        mapping: dict[str, str],
    ) -> None:
        changed = {
            source
            for source, target in mapping.items()
            if source != target
        }
        for player_uid in changed:
            raw_count = self.original_raw.count(
                UUID.from_str(player_uid).raw_bytes
            )
            parsed_count = _count_uuid_occurrences(
                self.gvas.properties,
                player_uid,
            )
            if raw_count != parsed_count:
                raise _unsupported(
                    self.path,
                    "An opaque dimensional storage identity reference cannot be rewritten safely.",
                    identity=player_uid,
                    visible_occurrences=parsed_count,
                    raw_occurrences=raw_count,
                )


def validate_dps_tree(root: Path) -> tuple[DpsSave, ...]:
    players = root / "Players"
    if not players.is_dir():
        return ()
    saves = tuple(
        DpsSave.load(path)
        for path in sorted(players.glob("*_dps.sav"))
        if path.is_file()
    )
    seen: dict[str, str] = {}
    for save in saves:
        for pal_id in save.active_pal_ids():
            previous = seen.get(pal_id)
            if previous is not None:
                raise _unsupported(
                    save.path,
                    "A dimensional Pal identity is duplicated across storage files.",
                    pal_instance_id=pal_id,
                    other_file=previous,
                )
            seen[pal_id] = save.path.as_posix()
    return saves


def rewrite_full_dps_tree(root: Path, mapping: dict[str, str]) -> None:
    saves = validate_dps_tree(root)
    if not saves:
        return
    normalized = {
        str(uuid.UUID(source)): str(uuid.UUID(target))
        for source, target in mapping.items()
    }
    targets: dict[str, tuple[DpsSave, bytes]] = {}
    removed = {
        source
        for source, target in normalized.items()
        if source != target and source not in set(normalized.values())
    }
    for save in saves:
        save.rewrite_player_uids(normalized)
        target_uid = normalized.get(save.player_uid, save.player_uid)
        if target_uid in targets:
            raise _unsupported(
                save.path,
                "Dimensional Pal storage file identities collide after migration.",
                player_uid=target_uid,
            )
        targets[target_uid] = (
            save,
            save.serialize(removed_uuids=removed),
        )
    for save in saves:
        save.path.unlink()
    players = root / "Players"
    for target_uid, (_save, data) in targets.items():
        (players / f"{UUID2HexStr(target_uid)}_dps.sav").write_bytes(data)
    validate_dps_tree(root)


def import_character_dps(
    source_root: Path,
    target_root: Path,
    *,
    source_player_uid: str,
    target_player_uid: str,
    target_pal_storage_id: str,
    used_pal_ids: set[str],
) -> dict[str, str]:
    source_uid = str(uuid.UUID(source_player_uid))
    target_uid = str(uuid.UUID(target_player_uid))
    target_container = str(uuid.UUID(target_pal_storage_id))
    source_path = (
        source_root / "Players" / f"{UUID2HexStr(source_uid)}_dps.sav"
    )
    target_path = (
        target_root / "Players" / f"{UUID2HexStr(target_uid)}_dps.sav"
    )
    target_saves = validate_dps_tree(target_root)
    occupied = {str(uuid.UUID(value)) for value in used_pal_ids}
    for save in target_saves:
        if save.player_uid != target_uid:
            occupied.update(save.active_pal_ids())
    if not source_path.is_file():
        if target_path.is_file():
            target_path.unlink()
        return {}
    save = DpsSave.load(source_path)
    pal_mapping = _allocate_uuid_mapping(
        save.active_pal_ids(),
        occupied,
    )
    remapped_pal_ids = {
        source: target
        for source, target in pal_mapping.items()
        if source != target
    }
    save.rewrite_uuid_values(remapped_pal_ids)
    removed_owners: set[str] = set()
    for record in save.active_records():
        removed_owners.add(record.owner_player_uid)
        removed_owners.update(record.old_owner_player_uids)
        removed_owners.add(record.last_nickname_modifier_player_uid)
        record.rebind(
            player_uid=target_uid,
            container_id=target_container,
            pal_instance_id=record.pal_instance_id,
        )
    save._validate()
    data = save.serialize(
        removed_uuids=(
            removed_owners
            | set(remapped_pal_ids)
        )
        - {target_uid, _ZERO_UUID},
    )
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(data)
    DpsSave.load(target_path)
    return pal_mapping


def _allocate_uuid_mapping(
    source_ids: Iterable[str],
    used_ids: set[str],
) -> dict[str, str]:
    used = {str(uuid.UUID(value)) for value in used_ids}
    result: dict[str, str] = {}
    for source_id in sorted({str(uuid.UUID(value)) for value in source_ids}):
        candidate = source_id
        if candidate in used:
            candidate = str(uuid.uuid4())
            while candidate in used:
                candidate = str(uuid.uuid4())
        result[source_id] = candidate
        used.add(candidate)
    return result


def _rewrite_known_player_uids(
    value: Any,
    mapping: dict[str, str],
) -> None:
    if isinstance(value, dict):
        for key, child in list(value.items()):
            normalized_key = str(key).replace("-", "_").casefold()
            if normalized_key in _PLAYER_UID_FIELDS:
                value[key] = _rewrite_uuid_node(child, mapping)
            else:
                _rewrite_known_player_uids(child, mapping)
    elif isinstance(value, list):
        for child in value:
            _rewrite_known_player_uids(child, mapping)


def _rewrite_uuid_node(value: Any, mapping: dict[str, str]) -> Any:
    if isinstance(value, UUID):
        normalized = str(value)
        return toUUID(mapping[normalized]) if normalized in mapping else value
    if isinstance(value, dict):
        if "value" in value:
            normalized = _normalize_uuid(value["value"])
            if normalized in mapping:
                value["value"] = toUUID(mapping[normalized])
                return value
        for key, child in list(value.items()):
            value[key] = _rewrite_uuid_node(child, mapping)
        return value
    if isinstance(value, list):
        for index, child in enumerate(value):
            value[index] = _rewrite_uuid_node(child, mapping)
        return value
    normalized = _normalize_uuid(value)
    return toUUID(mapping[normalized]) if normalized in mapping else value


def _count_uuid_occurrences(value: Any, expected: str) -> int:
    if isinstance(value, UUID):
        return int(str(value) == expected)
    if isinstance(value, dict):
        return sum(
            _count_uuid_occurrences(child, expected)
            for child in value.values()
        )
    if isinstance(value, (list, tuple)):
        return sum(
            _count_uuid_occurrences(child, expected)
            for child in value
        )
    return 0
