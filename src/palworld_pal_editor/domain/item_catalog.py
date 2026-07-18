from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import re
from typing import Iterable, Mapping

from palworld_pal_editor.config import ASSETS_PATH

from .errors import DomainError
from .models import ItemCatalogEntry, ItemContainerType


EQUIPMENT_SLOT_CATEGORIES: dict[int, frozenset[str]] = {
    0: frozenset({"head"}),
    1: frozenset({"body"}),
    2: frozenset({"accessory"}),
    3: frozenset({"accessory"}),
    4: frozenset({"shield"}),
    5: frozenset({"glider"}),
    6: frozenset({"accessory"}),
    7: frozenset({"accessory"}),
    8: frozenset({"sphere_module"}),
}

EQUIPMENT_SLOT_PERMISSION_TYPE_B: dict[int, int] = {
    0: 20,
    1: 21,
    2: 22,
    3: 22,
    4: 58,
    5: 57,
    6: 22,
    7: 22,
    8: 67,
}


def new_item_slot_metadata(
    container_type: ItemContainerType, slot_index: int
) -> dict:
    """Return the verified Palworld 1.0 metadata for a newly encoded slot."""
    type_a: list[int] = []
    type_b: list[int] = []
    if container_type == ItemContainerType.PLAYER_EQUIP_ARMOR:
        permission_type_b = EQUIPMENT_SLOT_PERMISSION_TYPE_B.get(slot_index)
        if permission_type_b is None:
            raise DomainError(
                code="ITEM_NOT_ALLOWED_IN_EQUIPMENT_SLOT",
                message="This equipment slot is not supported by the current save schema.",
                field="slot_index",
                http_status=400,
            )
        type_a = [3, 4, 10, 13]
        type_b = [permission_type_b]
    return {
        "permission": {
            "type_a": type_a,
            "type_b": type_b,
            "item_static_ids": [],
        },
        "corruption_progress_value": 0.0,
        # Palworld 1.0 Steam build 24088745 appends one zeroed 32-bit field.
        # Its semantics are not edited; the verified creation value is zero.
        "trailing_bytes": [0, 0, 0, 0],
    }


class ItemCatalog:
    """Versioned display metadata and conservative placement rules."""

    def __init__(self, entries: Iterable[ItemCatalogEntry]) -> None:
        self._entries: dict[str, ItemCatalogEntry] = {}
        for entry in entries:
            if entry.static_id in self._entries:
                raise ValueError(f"Duplicate catalog item: {entry.static_id}")
            self._entries[entry.static_id] = entry

    @classmethod
    def load_default(cls) -> "ItemCatalog":
        path = ASSETS_PATH / "assets" / "data" / "item_data.json"
        return cls.load(path)

    @classmethod
    def load(cls, path: str | Path) -> "ItemCatalog":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        entries: list[ItemCatalogEntry] = []
        for key, value in data.items():
            internal_name = str(value.get("InternalName") or key)
            localized = value.get("I18n") or {}
            names = {
                locale: str(text.get("Name") or internal_name)
                for locale, text in localized.items()
            }
            descriptions = {
                locale: str(text.get("Description") or "")
                for locale, text in localized.items()
            }
            rule = value.get("Rule") or {}
            raw_containers = rule.get("AllowedContainers") or []
            allowed: list[ItemContainerType] = []
            for container in raw_containers:
                try:
                    allowed.append(ItemContainerType(str(container)))
                except ValueError:
                    continue
            entries.append(
                ItemCatalogEntry(
                    static_id=internal_name,
                    names=names,
                    descriptions=descriptions,
                    category=str(rule.get("Category") or "unknown"),
                    rarity=(
                        int(rule["Rarity"])
                        if isinstance(rule.get("Rarity"), int)
                        and not isinstance(rule.get("Rarity"), bool)
                        else None
                    ),
                    icon=value.get("Icon"),
                    max_stack=(
                        int(rule["MaxStack"])
                        if isinstance(rule.get("MaxStack"), int)
                        and not isinstance(rule.get("MaxStack"), bool)
                        else None
                    ),
                    allowed_containers=tuple(allowed),
                    dynamic_kind=str(rule.get("DynamicKind") or "unknown"),
                    rule_status=str(rule.get("Status") or "unknown"),
                    rule_source=rule.get("Source"),
                    rule_version=rule.get("Version"),
                    disabled=bool(rule.get("Disabled", False)),
                )
            )
        return cls(entries)

    def get(self, static_id: str) -> ItemCatalogEntry:
        entry = self._entries.get(static_id)
        if entry is None:
            raise DomainError(
                code="ITEM_NOT_FOUND",
                message=f"Unknown item: {static_id}",
                field="static_id",
                details={"static_id": static_id},
                http_status=404,
            )
        return entry

    def get_optional(self, static_id: str) -> ItemCatalogEntry | None:
        return self._entries.get(static_id)

    def validate_dynamic_record_static_id(
        self,
        slot_static_id: str,
        record_static_id: object,
        dynamic_kind: str,
    ) -> ItemCatalogEntry:
        if not isinstance(record_static_id, str) or not record_static_id:
            raise DomainError(
                code="INVALID_DYNAMIC_INITIALIZER",
                message="record_static_id must be a non-empty item ID.",
                field="dynamic_init.record_static_id",
                http_status=400,
            )
        slot_entry = self.get(slot_static_id)
        record_entry = self.get(record_static_id)
        if (
            record_entry.rule_status != "verified"
            or record_entry.dynamic_kind != dynamic_kind
        ):
            raise DomainError(
                code="DYNAMIC_RECORD_ITEM_MISMATCH",
                message="The dynamic record item does not match the selected item kind.",
                field="dynamic_init.record_static_id",
                http_status=400,
            )
        if slot_entry.category == "accessory":
            slot_variant = re.fullmatch(r"(.+)_1", slot_static_id)
            record_variant = re.fullmatch(r"(.+)_[123]", record_static_id)
            compatible = (
                slot_static_id == record_static_id
                or (
                    slot_variant is not None
                    and record_variant is not None
                    and slot_variant.group(1) == record_variant.group(1)
                )
            )
        else:
            compatible = slot_static_id == record_static_id
        if not compatible:
            raise DomainError(
                code="DYNAMIC_RECORD_ITEM_MISMATCH",
                message="The dynamic record item is not a verified variant of the slot item.",
                field="dynamic_init.record_static_id",
                details={
                    "slot_static_id": slot_static_id,
                    "record_static_id": record_static_id,
                },
                http_status=400,
            )
        return record_entry

    def search(
        self,
        *,
        text: str = "",
        category: str | None = None,
        rarity: int | None = None,
        container_type: ItemContainerType | None = None,
        dynamic_kind: str | None = None,
        locale: str = "en",
        include_disabled: bool = False,
    ) -> list[ItemCatalogEntry]:
        needle = text.strip().casefold()
        result: list[ItemCatalogEntry] = []
        for entry in self._entries.values():
            if entry.disabled and not include_disabled:
                continue
            if needle and needle not in entry.static_id.casefold() and all(
                needle not in name.casefold() for name in entry.names.values()
            ):
                continue
            if category is not None and entry.category != category:
                continue
            if rarity is not None and entry.rarity != rarity:
                continue
            if container_type is not None and container_type not in entry.allowed_containers:
                continue
            if dynamic_kind is not None and entry.dynamic_kind != dynamic_kind:
                continue
            result.append(entry)
        return sorted(
            result,
            key=lambda entry: (entry.localized_name(locale).casefold(), entry.static_id),
        )

    def validate_placement(
        self,
        static_id: str,
        container_type: ItemContainerType,
        slot_index: int,
        count: int,
    ) -> ItemCatalogEntry:
        self._validate_location_and_count(slot_index, count)
        entry = self.get(static_id)
        if entry.rule_status != "verified" or entry.max_stack is None:
            raise DomainError(
                code="CATALOG_RULE_UNAVAILABLE",
                message="This item's write rules have not been verified.",
                field="static_id",
                details={
                    "static_id": static_id,
                    "rule_status": entry.rule_status,
                    "rule_source": entry.rule_source,
                    "rule_version": entry.rule_version,
                },
            )
        if entry.disabled:
            raise DomainError(
                code="ITEM_DISABLED",
                message="This item is disabled by the verified catalog.",
                field="static_id",
            )
        if not entry.allowed_containers:
            raise DomainError(
                code="CATALOG_RULE_UNAVAILABLE",
                message="This item's write rules have not been verified.",
                field="static_id",
                details={
                    "static_id": static_id,
                    "rule_status": entry.rule_status,
                    "rule_source": entry.rule_source,
                    "rule_version": entry.rule_version,
                },
            )
        if count > entry.max_stack:
            raise DomainError(
                code="MAX_STACK_EXCEEDED",
                message="Item count exceeds the verified maximum stack.",
                field="count",
                details={"requested": count, "max_stack": entry.max_stack},
            )
        if container_type not in entry.allowed_containers:
            raise DomainError(
                code="ITEM_NOT_ALLOWED_IN_CONTAINER",
                message="The item is not allowed in this container.",
                field="container_type",
                details={
                    "static_id": static_id,
                    "container_type": container_type.value,
                },
            )
        if container_type == ItemContainerType.PLAYER_EQUIP_ARMOR:
            allowed_categories = EQUIPMENT_SLOT_CATEGORIES.get(slot_index)
            if (
                allowed_categories is None
                or entry.category not in allowed_categories
            ):
                raise DomainError(
                    code="ITEM_NOT_ALLOWED_IN_EQUIPMENT_SLOT",
                    message="The item category is not allowed in this equipment slot.",
                    field="slot_index",
                    details={
                        "static_id": static_id,
                        "slot_index": slot_index,
                        "category": entry.category,
                        "allowed_categories": sorted(allowed_categories or ()),
                    },
                )
        return entry

    def validate_existing_count_update(
        self,
        static_id: str,
        container_type: ItemContainerType,
        slot_index: int,
        *,
        current_count: int,
        count: int,
    ) -> ItemCatalogEntry | None:
        """Validate an in-place count edit without guessing placement rules.

        A strict positive decrease preserves the already-loaded item identity,
        container and slot while never increasing its stack. Every other count
        edit still requires the complete verified catalog rule.
        """
        self._validate_location_and_count(slot_index, count)
        if (
            isinstance(current_count, int)
            and not isinstance(current_count, bool)
            and current_count > 0
            and count < current_count
        ):
            return self.get_optional(static_id)
        return self.validate_placement(
            static_id,
            container_type,
            slot_index,
            count,
        )

    @staticmethod
    def _validate_location_and_count(slot_index: int, count: int) -> None:
        if isinstance(count, bool) or not isinstance(count, int):
            raise DomainError(
                code="INVALID_ITEM_COUNT",
                message="Item count must be an integer.",
                field="count",
                http_status=400,
            )
        if count <= 0:
            raise DomainError(
                code="INVALID_ITEM_COUNT",
                message="Item count must be greater than zero.",
                field="count",
                details={"requested": count},
                http_status=400,
            )
        if isinstance(slot_index, bool) or not isinstance(slot_index, int) or slot_index < 0:
            raise DomainError(
                code="INVALID_SLOT_INDEX",
                message="slot_index must be a non-negative integer.",
                field="slot_index",
                http_status=400,
            )
