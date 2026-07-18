from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import math
from typing import Any, Callable, Iterator, Optional
import uuid

from palworld_save_tools.gvas import GvasFile

from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.utils.data_provider import DataProvider

from .item_container_data import ItemContainerData, ItemContainerSlot
from .pal_objects import toUUID


ZERO_UUID = "00000000-0000-0000-0000-000000000000"
KNOWN_DYNAMIC_KINDS = frozenset(
    {"accessory", "armor", "egg", "food", "glider", "shield", "weapon"}
)
_CURRENT_CUSTOM_VERSION_DATA: dict[str, tuple[int, ...]] = {
    "armor": (
        1, 0, 0, 0, 56, 11, 0, 222, 73, 73, 215, 206,
        151, 223, 45, 153, 192, 193, 195, 105, 1, 0, 0, 0,
    ),
    "weapon": (
        2, 0, 0, 0, 92, 229, 209, 55, 41, 73, 33, 94,
        220, 90, 181, 147, 225, 89, 68, 227, 1, 0, 0, 0,
        56, 11, 0, 222, 73, 73, 215, 206, 151, 223, 45, 153,
        192, 193, 195, 105, 1, 0, 0, 0,
    ),
    "egg": (
        2, 0, 0, 0, 56, 11, 0, 222, 73, 73, 215, 206,
        151, 223, 45, 153, 192, 193, 195, 105, 1, 0, 0, 0,
        108, 246, 252, 15, 153, 72, 144, 17, 248, 156, 96, 177,
        94, 71, 70, 74, 1, 0, 0, 0,
    ),
}


@dataclass(frozen=True)
class DynamicItemIssue:
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DynamicItemReference:
    container_id: str
    slot_index: int
    static_id: str
    created_world_id: str
    local_id: str
    source_kind: str = "item_slot"
    source_path: str = ""


class DynamicItemRecord:
    def __init__(self, entry: dict[str, Any], raw_data: dict[str, Any]) -> None:
        self.entry = entry
        self.raw_data = raw_data

    @property
    def created_world_id(self) -> str:
        return str(self.raw_data["id"]["created_world_id"])

    @property
    def local_id(self) -> str:
        return str(self.raw_data["id"]["local_id_in_created_world"])

    @property
    def static_id(self) -> str:
        return str(self.raw_data["id"]["static_id"])

    @property
    def kind(self) -> str:
        return str(self.raw_data.get("type", "unknown"))

    @property
    def dynamic_id(self) -> str:
        return f"{self.created_world_id}/{self.local_id}"


class DynamicItemData:
    """Read index and guarded lifecycle operations for DynamicItemSaveData."""

    def __init__(
        self,
        gvas_file: GvasFile,
        item_container_data: ItemContainerData,
        *,
        reference_scope_complete: bool = False,
        reference_scope_verifier: Callable[[str, int], bool] | None = None,
    ) -> None:
        self._gvas_file = gvas_file
        self._item_container_data = item_container_data
        self.reference_scope_complete = reference_scope_complete
        self._reference_scope_verifier = reference_scope_verifier
        self._verified_reference_counts: dict[str, int] = {}
        self._introduced_local_ids: set[str] = set()
        self._layout_issues: list[DynamicItemIssue] = []
        self._record_issues: list[DynamicItemIssue] = []
        self._reference_issues: list[DynamicItemIssue] = []
        self._values = self._extract_values(gvas_file)
        self.records: dict[str, DynamicItemRecord] = {}
        self.references: dict[str, list[DynamicItemReference]] = {}
        self._rebuild_records()
        self.rebuild_references()

    @property
    def layout_supported(self) -> bool:
        return self._values is not None and not self._layout_issues

    def issues(self) -> tuple[DynamicItemIssue, ...]:
        return tuple(
            self._layout_issues + self._record_issues + self._reference_issues
        )

    def get(self, local_id: str) -> Optional[DynamicItemRecord]:
        return self.records.get(str(local_id))

    def kind_for_slot(self, slot: ItemContainerSlot) -> str:
        local_id = slot.dynamic_local_id
        if slot.dynamic_id is None:
            return "none"
        if local_id in (None, ZERO_UUID):
            return "invalid"
        record = self.records.get(local_id)
        return record.kind if record is not None else "dangling"

    def require_writable_reference(
        self, slot: ItemContainerSlot
    ) -> DynamicItemRecord:
        if slot.dynamic_id is None:
            raise DomainError(
                code="DYNAMIC_ITEM_REFERENCE_MISSING",
                message="The selected slot has no dynamic item reference.",
                http_status=409,
            )
        local_id = slot.dynamic_local_id
        if local_id in (None, ZERO_UUID):
            raise DomainError(
                code="DYNAMIC_ITEM_REFERENCE_INVALID",
                message="The selected slot has an invalid dynamic item identifier.",
                http_status=409,
            )
        record = self.records.get(local_id)
        if record is None:
            raise DomainError(
                code="DYNAMIC_ITEM_REFERENCE_DANGLING",
                message="The dynamic item record referenced by this slot is missing.",
                details={"local_id": local_id},
                http_status=409,
            )
        if record.created_world_id != slot.dynamic_created_world_id:
            raise DomainError(
                code="DYNAMIC_ITEM_WORLD_ID_MISMATCH",
                message="The slot and dynamic item record use different world IDs.",
                http_status=409,
            )
        if record.kind not in KNOWN_DYNAMIC_KINDS:
            raise DomainError(
                code="DYNAMIC_ITEM_TYPE_READ_ONLY",
                message="This dynamic item type is preserved as read-only.",
                details={"dynamic_kind": record.kind},
            )
        return record

    def require_deletable_reference(
        self, slot: ItemContainerSlot
    ) -> DynamicItemRecord:
        record, references = self._require_verified_reference_scope(slot)
        if len(references) != 1:
            raise DomainError(
                code="DYNAMIC_ITEM_SHARED_REFERENCE",
                message="The dynamic item record is referenced by more than one slot.",
                details={"reference_count": len(references)},
                http_status=409,
            )
        return record

    def require_removable_reference(
        self, slot: ItemContainerSlot
    ) -> DynamicItemRecord:
        record, _references = self._require_verified_reference_scope(slot)
        return record

    def _require_verified_reference_scope(
        self, slot: ItemContainerSlot
    ) -> tuple[DynamicItemRecord, list[DynamicItemReference]]:
        record = self.require_writable_reference(slot)
        self.rebuild_references()
        references = self.references.get(record.local_id, [])
        reference_count = len(references)
        scope_verified = self.reference_scope_complete or (
            self._verified_reference_counts.get(record.local_id)
            == reference_count
        )
        if not scope_verified and self._reference_scope_verifier is not None:
            expected_original_occurrences = (
                0
                if record.local_id in self._introduced_local_ids
                else 1 + reference_count
            )
            if self._reference_scope_verifier(
                record.local_id, expected_original_occurrences
            ):
                self._verified_reference_counts[record.local_id] = reference_count
                scope_verified = True
        if not scope_verified:
            raise DomainError(
                code="DYNAMIC_ITEM_REFERENCE_SCOPE_UNVERIFIED",
                message="Dynamic item deletion is disabled until all reference sources are verified.",
            )
        return record, references

    def require_transferable_record(
        self, record: DynamicItemRecord
    ) -> DynamicItemRecord:
        """Fail closed when a complex record contains IDs we cannot remap."""
        if record.kind not in KNOWN_DYNAMIC_KINDS:
            raise DomainError(
                code="DYNAMIC_ITEM_TYPE_READ_ONLY",
                message="This dynamic item type is preserved as read-only.",
                details={"dynamic_kind": record.kind},
            )
        if record.kind == "egg":
            self._validate_current_egg_transfer_layout(record.raw_data)
        return record

    def assert_consistent(self) -> None:
        self._rebuild_records()
        self.rebuild_references()
        issues = self.issues()
        if issues:
            issue = issues[0]
            raise DomainError(
                code=issue.code,
                message=issue.message,
                details=issue.details,
                http_status=409,
            )

    def snapshot_values(self) -> list[dict[str, Any]]:
        if self._values is None:
            raise DomainError(
                code="DYNAMIC_ITEM_LAYOUT_UNSUPPORTED",
                message="DynamicItemSaveData does not use the verified array layout.",
            )
        return deepcopy(self._values)

    def restore_values(self, snapshot: list[dict[str, Any]]) -> None:
        if self._values is None:
            raise RuntimeError("Dynamic item layout is unavailable")
        self._values[:] = deepcopy(snapshot)
        self._rebuild_records()
        self._introduced_local_ids.intersection_update(self.records)
        self._verified_reference_counts = {
            local_id: count
            for local_id, count in self._verified_reference_counts.items()
            if local_id in self.records
        }
        self.rebuild_references()

    def delete_unreferenced(self, local_id: str) -> None:
        if self._values is None:
            raise DomainError(
                code="DYNAMIC_ITEM_LAYOUT_UNSUPPORTED",
                message="DynamicItemSaveData does not use the verified array layout.",
            )
        self.rebuild_references()
        if self.references.get(local_id):
            raise DomainError(
                code="DYNAMIC_ITEM_STILL_REFERENCED",
                message="The dynamic item record is still referenced.",
                http_status=409,
            )
        record = self.records.get(local_id)
        if record is None:
            raise DomainError(
                code="DYNAMIC_ITEM_RECORD_NOT_FOUND",
                message="The dynamic item record no longer exists.",
                http_status=409,
            )
        self._values.remove(record.entry)
        self._verified_reference_counts.pop(local_id, None)
        self._introduced_local_ids.discard(local_id)
        self._rebuild_records()
        self.rebuild_references()

    def clone_record(
        self,
        source_local_id: str,
        target_local_id: str,
        *,
        target_created_world_id: str | None = None,
    ) -> DynamicItemRecord:
        if self._values is None:
            raise DomainError(
                code="DYNAMIC_ITEM_LAYOUT_UNSUPPORTED",
                message="DynamicItemSaveData does not use the verified array layout.",
            )
        source = self.records.get(str(source_local_id))
        if source is None:
            raise DomainError(
                code="DYNAMIC_ITEM_RECORD_NOT_FOUND",
                message="The copied dynamic item record no longer exists.",
                http_status=409,
            )
        if source.kind not in KNOWN_DYNAMIC_KINDS:
            raise DomainError(
                code="DYNAMIC_ITEM_TYPE_READ_ONLY",
                message="This dynamic item type is preserved as read-only.",
                details={"dynamic_kind": source.kind},
            )
        self.require_transferable_record(source)
        normalized = str(target_local_id)
        if normalized == ZERO_UUID or normalized in self.records:
            raise DomainError(
                code="DYNAMIC_ITEM_ID_COLLISION",
                message="The generated dynamic item identifier is not unique.",
                http_status=409,
            )
        return self.insert_cloned_record(
            source.entry,
            target_local_id=normalized,
            target_created_world_id=(
                target_created_world_id or source.created_world_id
            ),
        )

    def insert_cloned_record(
        self,
        source_entry: dict[str, Any],
        *,
        target_local_id: str,
        target_created_world_id: str,
    ) -> DynamicItemRecord:
        if self._values is None:
            raise DomainError(
                code="DYNAMIC_ITEM_LAYOUT_UNSUPPORTED",
                message="DynamicItemSaveData does not use the verified array layout.",
            )
        raw = source_entry.get("RawData", {}).get("value", {})
        kind = str(raw.get("type", "unknown"))
        if kind not in KNOWN_DYNAMIC_KINDS:
            raise DomainError(
                code="DYNAMIC_ITEM_TYPE_READ_ONLY",
                message="This dynamic item type is preserved as read-only.",
                details={"dynamic_kind": kind},
            )
        self._validate_transferable_raw_data(raw)
        normalized = str(target_local_id)
        if normalized == ZERO_UUID or normalized in self.records:
            raise DomainError(
                code="DYNAMIC_ITEM_ID_COLLISION",
                message="The generated dynamic item identifier is not unique.",
                http_status=409,
            )
        entry = deepcopy(source_entry)
        entry["RawData"]["value"]["id"]["local_id_in_created_world"] = toUUID(
            normalized
        )
        entry["RawData"]["value"]["id"]["created_world_id"] = toUUID(
            target_created_world_id
        )
        self._values.append(entry)
        self._introduced_local_ids.add(normalized)
        self._rebuild_records()
        return self.records[normalized]

    def prepare_construction(
        self,
        static_id: str,
        kind: str,
        dynamic_init: object,
    ) -> dict[str, Any]:
        if kind not in _CURRENT_CUSTOM_VERSION_DATA:
            raise DomainError(
                code="DYNAMIC_ITEM_CONSTRUCTION_UNSUPPORTED",
                message="This dynamic item kind has no verified constructor.",
                details={"dynamic_kind": kind},
            )
        if not self._item_container_data.dynamic_reference_layout_complete:
            raise DomainError(
                code="DYNAMIC_ITEM_CONSTRUCTION_UNSUPPORTED",
                message="The save does not use the verified Palworld 1.0 item-container layout.",
                details={"dynamic_kind": kind},
            )
        if self._values is None:
            raise DomainError(
                code="DYNAMIC_ITEM_LAYOUT_UNSUPPORTED",
                message="DynamicItemSaveData does not use the verified array layout.",
            )
        self._require_current_record_envelope(kind)
        if not isinstance(dynamic_init, dict):
            raise DomainError(
                code="DYNAMIC_ITEM_INITIALIZER_REQUIRED",
                message="This item requires explicit dynamic initialization fields.",
                field="dynamic_init",
                details={"dynamic_kind": kind},
                http_status=400,
            )

        if kind == "weapon":
            self._require_initializer_fields(
                dynamic_init,
                {
                    "record_static_id",
                    "durability",
                    "ammo",
                    "passive_traits",
                },
            )
            return {
                "type": "weapon",
                "leading_bytes": [0, 0, 0, 0],
                "durability": self._non_negative_float(
                    dynamic_init["durability"], "durability"
                ),
                "remaining_bullets": self._non_negative_i32(
                    dynamic_init["ammo"], "ammo"
                ),
                "passive_skill_list": self._string_list(
                    dynamic_init["passive_traits"], "passive_traits"
                ),
                "unknown_str": "None",
                "trailing_bytes": [0, 0, 0, 0],
            }
        if kind == "armor":
            self._require_initializer_fields(
                dynamic_init, {"record_static_id", "durability"}
            )
            return {
                "type": "armor",
                "leading_bytes": [0, 0, 0, 0],
                "durability": self._non_negative_float(
                    dynamic_init["durability"], "durability"
                ),
                "trailing_bytes": [0, 0, 0, 0],
            }

        self._require_initializer_fields(
            dynamic_init, {"record_static_id", "character_id"}
        )
        character_id = dynamic_init["character_id"]
        if (
            not isinstance(character_id, str)
            or not character_id
            or not DataProvider.in_pal_data(character_id)
        ):
            raise DomainError(
                code="PAL_SPECIES_NOT_FOUND",
                message="The requested egg species is not in the current Pal catalog.",
                field="dynamic_init.character_id",
                http_status=404,
            )
        return {
            "type": "egg",
            "leading_bytes": [0, 0, 0, 0],
            "character_id": character_id,
            "object": {},
            "trailing_bytes": [0] * 28,
        }

    def construct_record(
        self,
        *,
        static_id: str,
        kind: str,
        dynamic_init: object,
        target_local_id: str,
    ) -> DynamicItemRecord:
        raw = {
            "id": {
                "created_world_id": toUUID(ZERO_UUID),
                "local_id_in_created_world": toUUID(target_local_id),
                "static_id": dynamic_init["record_static_id"],
            },
            **self.prepare_construction(static_id, kind, dynamic_init),
        }
        normalized = str(target_local_id)
        if normalized == ZERO_UUID or normalized in self.records:
            raise DomainError(
                code="DYNAMIC_ITEM_ID_COLLISION",
                message="The generated dynamic item identifier is not unique.",
                http_status=409,
            )
        entry = self._new_current_record_entry(kind, raw)
        self._values.append(entry)
        self._introduced_local_ids.add(normalized)
        self._rebuild_records()
        return self.records[normalized]

    def construction_initializer_for_record(
        self, record: DynamicItemRecord
    ) -> dict[str, Any]:
        """Serialize only dynamic records that the current constructor can recreate."""
        self.require_transferable_record(record)
        if record.kind not in _CURRENT_CUSTOM_VERSION_DATA:
            raise DomainError(
                code="DYNAMIC_ITEM_CONSTRUCTION_UNSUPPORTED",
                message="This dynamic item kind cannot be represented by a preset.",
                details={"dynamic_kind": record.kind},
            )
        self._require_current_record_envelope(record.kind)
        raw = record.raw_data
        identifier = raw.get("id")
        if (
            not isinstance(identifier, dict)
            or set(identifier)
            != {
                "created_world_id",
                "local_id_in_created_world",
                "static_id",
            }
            or str(identifier.get("created_world_id")) != ZERO_UUID
            or str(identifier.get("local_id_in_created_world")) != record.local_id
            or identifier.get("static_id") != record.static_id
        ):
            raise DomainError(
                code="DYNAMIC_ITEM_CONSTRUCTION_UNSUPPORTED",
                message="The dynamic item identifier layout cannot be recreated safely.",
                details={"dynamic_kind": record.kind},
            )

        if record.kind == "weapon":
            expected_fields = {
                "id",
                "type",
                "leading_bytes",
                "durability",
                "remaining_bullets",
                "passive_skill_list",
                "unknown_str",
                "trailing_bytes",
            }
            initializer = {
                "record_static_id": record.static_id,
                "durability": raw.get("durability"),
                "ammo": raw.get("remaining_bullets"),
                "passive_traits": deepcopy(raw.get("passive_skill_list")),
            }
            extra_valid = raw.get("unknown_str") == "None"
        elif record.kind == "armor":
            expected_fields = {
                "id",
                "type",
                "leading_bytes",
                "durability",
                "trailing_bytes",
            }
            initializer = {
                "record_static_id": record.static_id,
                "durability": raw.get("durability"),
            }
            extra_valid = True
        else:
            expected_fields = {
                "id",
                "type",
                "leading_bytes",
                "character_id",
                "object",
                "trailing_bytes",
            }
            initializer = {
                "record_static_id": record.static_id,
                "character_id": raw.get("character_id"),
            }
            extra_valid = raw.get("object") == {}

        expected_tail = [0] * (28 if record.kind == "egg" else 4)
        if (
            set(raw) != expected_fields
            or raw.get("type") != record.kind
            or raw.get("leading_bytes") != [0, 0, 0, 0]
            or raw.get("trailing_bytes") != expected_tail
            or not extra_valid
        ):
            raise DomainError(
                code="DYNAMIC_ITEM_CONSTRUCTION_UNSUPPORTED",
                message="The dynamic item contains fields a preset cannot recreate safely.",
                details={"dynamic_kind": record.kind},
            )
        self.prepare_construction(record.static_id, record.kind, initializer)
        return initializer

    def _require_current_record_envelope(self, kind: str) -> None:
        expected = _CURRENT_CUSTOM_VERSION_DATA[kind]
        expected_raw_meta = {
            "array_type": "ByteProperty",
            "id": None,
            "type": "ArrayProperty",
            "custom_type": (
                ".worldSaveData.DynamicItemSaveData."
                "DynamicItemSaveData.RawData"
            ),
        }
        expected_custom_meta = {
            "array_type": "ByteProperty",
            "id": None,
            "type": "ArrayProperty",
        }
        for record in self.records.values():
            if record.kind != kind:
                continue
            raw_property = record.entry.get("RawData")
            custom_property = record.entry.get("CustomVersionData")
            raw_meta = (
                {key: value for key, value in raw_property.items() if key != "value"}
                if isinstance(raw_property, dict)
                else None
            )
            custom_meta = (
                {
                    key: value
                    for key, value in custom_property.items()
                    if key != "value"
                }
                if isinstance(custom_property, dict)
                else None
            )
            custom_value = (
                custom_property.get("value")
                if isinstance(custom_property, dict)
                else None
            )
            values = (
                custom_value.get("values")
                if isinstance(custom_value, dict)
                and set(custom_value) == {"values"}
                else None
            )
            if (
                set(record.entry) != {"RawData", "CustomVersionData"}
                or raw_meta != expected_raw_meta
                or custom_meta != expected_custom_meta
                or tuple(values or ()) != expected
            ):
                raise DomainError(
                    code="DYNAMIC_ITEM_CONSTRUCTION_UNSUPPORTED",
                    message="Existing records use a different dynamic-item envelope.",
                    details={"dynamic_kind": kind},
                )

    def _new_current_record_entry(
        self, kind: str, raw: dict[str, Any]
    ) -> dict[str, Any]:
        for record in self.records.values():
            if record.kind == kind:
                entry = deepcopy(record.entry)
                entry["RawData"]["value"] = raw
                return entry
        return {
            "RawData": {
                "array_type": "ByteProperty",
                "id": None,
                "value": raw,
                "type": "ArrayProperty",
                "custom_type": (
                    ".worldSaveData.DynamicItemSaveData."
                    "DynamicItemSaveData.RawData"
                ),
            },
            "CustomVersionData": {
                "array_type": "ByteProperty",
                "id": None,
                "value": {"values": _CURRENT_CUSTOM_VERSION_DATA[kind]},
                "type": "ArrayProperty",
            },
        }

    @staticmethod
    def _require_initializer_fields(
        value: dict[str, Any], expected: set[str]
    ) -> None:
        if set(value) != expected:
            raise DomainError(
                code="INVALID_DYNAMIC_INITIALIZER",
                message="The dynamic initializer fields do not match this item kind.",
                field="dynamic_init",
                details={
                    "expected_fields": sorted(expected),
                    "received_fields": sorted(str(key) for key in value),
                },
                http_status=400,
            )

    @staticmethod
    def _non_negative_float(value: object, field: str) -> float:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
            or value > 3.402823466e38
        ):
            raise DomainError(
                code="INVALID_DYNAMIC_INITIALIZER",
                message=f"{field} must be a non-negative finite float32 value.",
                field=f"dynamic_init.{field}",
                http_status=400,
            )
        return float(value)

    @staticmethod
    def _non_negative_i32(value: object, field: str) -> int:
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
            or value > 2_147_483_647
        ):
            raise DomainError(
                code="INVALID_DYNAMIC_INITIALIZER",
                message=f"{field} must be a non-negative int32 value.",
                field=f"dynamic_init.{field}",
                http_status=400,
            )
        return value

    @staticmethod
    def _string_list(value: object, field: str) -> list[str]:
        if (
            not isinstance(value, list)
            or len(value) > 64
            or any(
                not isinstance(item, str)
                or not item
                or len(item.encode("utf-8")) > 512
                for item in value
            )
            or len(value) != len(set(value))
        ):
            raise DomainError(
                code="INVALID_DYNAMIC_INITIALIZER",
                message=f"{field} must contain unique non-empty strings.",
                field=f"dynamic_init.{field}",
                http_status=400,
            )
        return list(value)

    def _validate_transferable_raw_data(self, raw: dict[str, Any]) -> None:
        if str(raw.get("type", "unknown")) == "egg":
            self._validate_current_egg_transfer_layout(raw)

    @staticmethod
    def _validate_current_egg_transfer_layout(raw: dict[str, Any]) -> None:
        expected_keys = {
            "id",
            "type",
            "leading_bytes",
            "character_id",
            "object",
            "trailing_bytes",
        }
        character_id = raw.get("character_id")
        object_data = raw.get("object")
        if (
            set(raw) != expected_keys
            or raw.get("type") != "egg"
            or raw.get("leading_bytes") != [0, 0, 0, 0]
            or raw.get("trailing_bytes") != [0] * 28
            or not isinstance(character_id, str)
            or not character_id
            or not isinstance(object_data, dict)
            or set(object_data) not in (set(), {"SaveParameter"})
        ):
            raise DomainError(
                code="COMPLEX_DYNAMIC_LAYOUT_UNVERIFIED",
                message="This egg does not use the verified Palworld 1.0 transfer layout.",
                details={"dynamic_kind": "egg"},
            )

        save_parameter = object_data.get("SaveParameter")
        if save_parameter is not None:
            embedded_character_id = (
                save_parameter.get("value", {})
                .get("CharacterID", {})
                .get("value")
                if isinstance(save_parameter, dict)
                else None
            )
            if (
                not isinstance(save_parameter, dict)
                or save_parameter.get("struct_type")
                != "PalIndividualCharacterSaveParameter"
                or embedded_character_id != character_id
            ):
                raise DomainError(
                    code="COMPLEX_DYNAMIC_LAYOUT_UNVERIFIED",
                    message="The egg's embedded Pal data is not structurally consistent.",
                    details={"dynamic_kind": "egg"},
                )

        nonzero_ids = list(
            DynamicItemData._iter_nonzero_uuid_values(object_data, "object")
        )
        if nonzero_ids:
            raise DomainError(
                code="COMPLEX_DYNAMIC_REFERENCE_UNVERIFIED",
                message="The egg contains an embedded identifier with no verified remap rule.",
                details={"paths": [path for path, _value in nonzero_ids]},
            )

    @staticmethod
    def _iter_nonzero_uuid_values(
        value: Any, path: str
    ) -> Iterator[tuple[str, str]]:
        if isinstance(value, dict):
            for key, child in value.items():
                yield from DynamicItemData._iter_nonzero_uuid_values(
                    child, f"{path}.{key}"
                )
            return
        if isinstance(value, (list, tuple)):
            for index, child in enumerate(value):
                yield from DynamicItemData._iter_nonzero_uuid_values(
                    child, f"{path}[{index}]"
                )
            return
        try:
            normalized = str(uuid.UUID(str(value)))
        except (ValueError, TypeError, AttributeError):
            return
        if normalized != ZERO_UUID:
            yield path, normalized

    def _extract_values(self, gvas_file: GvasFile):
        world_property = gvas_file.properties.get("worldSaveData")
        world = world_property.get("value") if isinstance(world_property, dict) else None
        dynamic_property = (
            world.get("DynamicItemSaveData") if isinstance(world, dict) else None
        )
        if dynamic_property is None:
            return None
        value = (
            dynamic_property.get("value")
            if isinstance(dynamic_property, dict)
            else None
        )
        values = value.get("values") if isinstance(value, dict) else None
        if not isinstance(values, list):
            self._layout_issues.append(
                DynamicItemIssue(
                    code="DYNAMIC_ITEM_LAYOUT_UNSUPPORTED",
                    message="DynamicItemSaveData does not use the verified array layout.",
                )
            )
            return None
        return values

    def _rebuild_records(self) -> None:
        self.records = {}
        self._record_issues = []
        if self._values is None:
            return
        for index, entry in enumerate(self._values):
            raw_property = entry.get("RawData") if isinstance(entry, dict) else None
            raw_data = (
                raw_property.get("value")
                if isinstance(raw_property, dict)
                else None
            )
            if not isinstance(raw_data, dict) or not isinstance(
                raw_data.get("id"), dict
            ):
                self._record_issues.append(
                    DynamicItemIssue(
                        code="DYNAMIC_ITEM_RECORD_INVALID",
                        message="A dynamic item record could not be indexed safely.",
                        details={"record_index": index},
                    )
                )
                continue
            try:
                record = DynamicItemRecord(entry, raw_data)
                local_id = record.local_id
                if local_id == ZERO_UUID:
                    raise ValueError("nil local id")
                if not record.created_world_id or not record.static_id:
                    raise ValueError("missing dynamic item identity")
            except (KeyError, TypeError, ValueError):
                self._record_issues.append(
                    DynamicItemIssue(
                        code="DYNAMIC_ITEM_RECORD_INVALID",
                        message="A dynamic item record has an invalid identifier.",
                        details={"record_index": index},
                    )
                )
                continue
            if local_id in self.records:
                self._record_issues.append(
                    DynamicItemIssue(
                        code="DYNAMIC_ITEM_RECORD_DUPLICATE",
                        message="Two dynamic item records use the same local identifier.",
                        details={"local_id": local_id},
                    )
                )
                continue
            self.records[local_id] = record

    def rebuild_references(self) -> None:
        self.references = {}
        self._reference_issues = []
        for container_id, slot in self._item_container_data.iter_occupied_slots():
            if slot.dynamic_id is None:
                continue
            local_id = slot.dynamic_local_id
            created_world_id = slot.dynamic_created_world_id
            if local_id in (None, ZERO_UUID) or created_world_id is None:
                self._reference_issues.append(
                    DynamicItemIssue(
                        code="DYNAMIC_ITEM_REFERENCE_INVALID",
                        message="An item slot has an invalid dynamic item identifier.",
                        details={
                            "container_id": container_id,
                            "slot_index": slot.slot_index,
                        },
                    )
                )
                continue
            reference = DynamicItemReference(
                container_id=container_id,
                slot_index=slot.slot_index,
                static_id=slot.static_id,
                created_world_id=created_world_id,
                local_id=local_id,
                source_kind="item_slot",
                source_path=(
                    f"ItemContainerSaveData[{container_id}].Slots[{slot.slot_index}]"
                ),
            )
            self._add_reference(reference)

        for container_id, created_world_id, local_id in (
            self._item_container_data.iter_used_dynamic_item_ids()
        ):
            if local_id == ZERO_UUID and created_world_id == ZERO_UUID:
                continue
            reference = DynamicItemReference(
                container_id=container_id,
                slot_index=-1,
                static_id="",
                created_world_id=created_world_id,
                local_id=local_id,
                source_kind="container_used_dynamic_id",
                source_path=(
                    f"ItemContainerSaveData[{container_id}].UsedDynamicItemIDs"
                ),
            )
            self._add_reference(reference)

        for source_path, static_id, created_world_id, local_id in (
            self._iter_external_dynamic_references()
        ):
            if local_id == ZERO_UUID and created_world_id == ZERO_UUID:
                continue
            self._add_reference(
                DynamicItemReference(
                    container_id="",
                    slot_index=-1,
                    static_id=static_id,
                    created_world_id=created_world_id,
                    local_id=local_id,
                    source_kind="external_dynamic_id",
                    source_path=source_path,
                )
            )

    def _add_reference(self, reference: DynamicItemReference) -> None:
        local_id = reference.local_id
        created_world_id = reference.created_world_id
        if local_id == ZERO_UUID:
            self._reference_issues.append(
                DynamicItemIssue(
                    code="DYNAMIC_ITEM_REFERENCE_INVALID",
                    message="A save object has an invalid dynamic item identifier.",
                    details={
                        "source_kind": reference.source_kind,
                        "source_path": reference.source_path,
                        "local_id": local_id,
                    },
                )
            )
            return
        self.references.setdefault(local_id, []).append(reference)
        record = self.records.get(local_id)
        if record is None:
            code = (
                "DYNAMIC_ITEM_LAYOUT_MISSING"
                if self._values is None and not self._layout_issues
                else "DYNAMIC_ITEM_REFERENCE_DANGLING"
            )
            self._reference_issues.append(
                DynamicItemIssue(
                    code=code,
                    message="A save object references a missing dynamic item record.",
                    details={
                        "source_kind": reference.source_kind,
                        "source_path": reference.source_path,
                        "container_id": reference.container_id,
                        "slot_index": reference.slot_index,
                        "local_id": local_id,
                    },
                )
            )
            return
        if record.created_world_id != created_world_id:
            self._reference_issues.append(
                DynamicItemIssue(
                    code="DYNAMIC_ITEM_WORLD_ID_MISMATCH",
                    message="A save object and dynamic item record use different world IDs.",
                    details={
                        "source_kind": reference.source_kind,
                        "source_path": reference.source_path,
                        "container_id": reference.container_id,
                        "slot_index": reference.slot_index,
                        "local_id": local_id,
                    },
                )
            )

    def _iter_external_dynamic_references(
        self,
    ) -> Iterator[tuple[str, str, str, str]]:
        world_property = self._gvas_file.properties.get("worldSaveData")
        world = world_property.get("value") if isinstance(world_property, dict) else None
        if not isinstance(world, dict):
            return
        for property_name, value in world.items():
            if property_name in {"ItemContainerSaveData", "DynamicItemSaveData"}:
                continue
            yield from self._walk_dynamic_ids(
                value, f"worldSaveData.{property_name}"
            )

    def _walk_dynamic_ids(
        self, value: Any, path: str
    ) -> Iterator[tuple[str, str, str, str]]:
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}.{key}"
                if key == "dynamic_id" and isinstance(child, dict):
                    created = child.get("created_world_id")
                    local = child.get("local_id_in_created_world")
                    if created is not None and local is not None:
                        yield (
                            child_path,
                            str(value.get("static_id", "")),
                            str(created),
                            str(local),
                        )
                yield from self._walk_dynamic_ids(child, child_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                yield from self._walk_dynamic_ids(child, f"{path}[{index}]")
