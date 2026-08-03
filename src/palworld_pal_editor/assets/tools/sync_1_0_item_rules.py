from __future__ import annotations

import argparse
import base64
from collections import Counter
from dataclasses import dataclass, replace
import json
from pathlib import Path
import struct
from typing import Any, Iterable


BUILD = 24088745
EXPECTED_ITEM_COUNT = 2466
RULE_SOURCE = (
    "Palworld 1.0 DA_StaticItemDataAsset + DT_ItemDataTable_Common"
)
SUPPORTED_LOCALES = ("en", "fr", "ja", "ko", "zh-CN")
EDITOR_ENABLED_UNOFFICIAL_ITEMS = frozenset({"SkillCard_Psychokinesis"})

_BASE_PROPERTY_OFFSET = {
    "PalStaticItemDataBase": 0,
    "PalStaticArmorItemData": 4,
    "PalStaticWeaponItemData": 4,
    "PalStaticConsumeItemData": 5,
    "PalStaticItem_GrantTechnologyPt": 5,
    "PalStaticItem_Homeward": 5,
    "PalStaticItem_PlayerLamp": 5,
    "PalStaticItem_TreasureMap": 5,
    "PalStaticItem_WorldTreeHolyWater": 5,
}
_DYNAMIC_KIND = {0: "none", -1: "armor", -2: "egg", -3: "weapon"}
_DYNAMIC_IMPORT = {
    -1: "PalDynamicArmorItemDataBase",
    -2: "PalDynamicPalEggItemDataBase",
    -3: "PalDynamicWeaponItemDataBase",
}
_COMMON_CONTAINERS = ("COMMON", "BASE_STORAGE", "GUILD_STORAGE")
_EQUIPMENT_CATEGORIES = {
    "head",
    "body",
    "accessory",
    "shield",
    "glider",
    "sphere_module",
}


@dataclass(frozen=True)
class StaticItemRule:
    static_id: str
    name_base: str
    name_number: int
    type_a: int
    type_b: int
    rank: int
    rarity: int
    price: int
    max_stack: int
    sort_id: int
    dynamic_class_index: int
    item_static_class: str | None
    icon_package: str
    icon_asset: str
    object_class: str
    official_legal: bool = False

    @property
    def dynamic_kind(self) -> str:
        return _DYNAMIC_KIND[self.dynamic_class_index]


def decode_base64(value: object, *, field: str) -> bytes:
    if not isinstance(value, str):
        raise ValueError(f"{field} is not a base64 string")
    try:
        return base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as error:
        raise ValueError(f"{field} is not valid base64") from error


def parse_unversioned_header(
    data: bytes, offset: int = 0
) -> tuple[int, dict[int, bool]]:
    """Return the payload offset and property-index/non-zero map."""
    fragments: list[tuple[list[int], bool]] = []
    current_index = 0
    masked_indices: list[int] = []
    for _ in range(16):
        if offset + 2 > len(data):
            raise ValueError("Unversioned property header ended early")
        packed = struct.unpack_from("<H", data, offset)[0]
        offset += 2
        skip = packed & 0x7F
        has_zeroes = bool(packed & 0x80)
        is_last = bool(packed & 0x100)
        value_count = packed >> 9
        start = current_index + skip
        indices = list(range(start, start + value_count))
        current_index = start + value_count
        fragments.append((indices, has_zeroes))
        if has_zeroes:
            masked_indices.extend(indices)
        if is_last:
            break
    else:
        raise ValueError("Unversioned property header has too many fragments")

    if not masked_indices:
        mask_size = 0
    elif len(masked_indices) <= 8:
        mask_size = 1
    elif len(masked_indices) <= 16:
        mask_size = 2
    else:
        mask_size = ((len(masked_indices) + 31) // 32) * 4
    if offset + mask_size > len(data):
        raise ValueError("Unversioned property zero mask ended early")
    zero_bits = int.from_bytes(data[offset : offset + mask_size], "little")
    offset += mask_size

    state: dict[int, bool] = {}
    mask_index = 0
    for indices, has_zeroes in fragments:
        for property_index in indices:
            is_zero = has_zeroes and bool(zero_bits & (1 << mask_index))
            state[property_index] = not is_zero
            if has_zeroes:
                mask_index += 1
    return offset, state


def _render_fname(name_map: list[str], index: int, number: int) -> str:
    if not 0 <= index < len(name_map):
        raise ValueError(f"FName index {index} is outside the name map")
    if number < 0:
        raise ValueError("FName number must be non-negative")
    base = name_map[index]
    return base if number == 0 else f"{base}_{number - 1}"


def _read_fname(
    data: bytes, offset: int, name_map: list[str]
) -> tuple[str, int]:
    if offset + 8 > len(data):
        raise ValueError("FName ended early")
    index, number = struct.unpack_from("<ii", data, offset)
    return _render_fname(name_map, index, number), offset + 8


def _read_fstring(data: bytes, offset: int) -> tuple[str, int]:
    if offset + 4 > len(data):
        raise ValueError("FString length ended early")
    length = struct.unpack_from("<i", data, offset)[0]
    offset += 4
    if length == 0:
        return "", offset
    if length > 0:
        end = offset + length
        if end > len(data) or data[end - 1] != 0:
            raise ValueError("UTF-8 FString is invalid")
        return data[offset : end - 1].decode("utf-8"), end
    byte_length = -length * 2
    end = offset + byte_length
    if end > len(data) or data[end - 2 : end] != b"\0\0":
        raise ValueError("UTF-16 FString is invalid")
    return data[offset : end - 2].decode("utf-16-le"), end


def _read_soft_object_path(
    data: bytes, offset: int, name_map: list[str]
) -> tuple[tuple[str, str, str], int]:
    package_name, offset = _read_fname(data, offset, name_map)
    asset_name, offset = _read_fname(data, offset, name_map)
    sub_path, offset = _read_fstring(data, offset)
    return (package_name, asset_name, sub_path), offset


def _all_hits(data: bytes, pattern: bytes, start: int = 0) -> Iterable[int]:
    while True:
        hit = data.find(pattern, start)
        if hit < 0:
            return
        yield hit
        start = hit + 1


def _import_name(asset: dict[str, Any], package_index: int) -> str:
    imports = asset.get("Imports")
    if not isinstance(imports, list) or package_index >= 0:
        raise ValueError(f"Expected an import package index, got {package_index}")
    import_index = -package_index - 1
    if not 0 <= import_index < len(imports):
        raise ValueError(f"Import package index {package_index} is invalid")
    name = imports[import_index].get("ObjectName")
    if not isinstance(name, str):
        raise ValueError("Import has no ObjectName")
    return name


def _read_static_base_candidate(
    data: bytes,
    offset: int,
    state: dict[int, bool],
    base_offset: int,
    name_map: list[str],
    *,
    expected_id: str,
    name_base: str,
    name_number: int,
    object_class: str,
) -> StaticItemRule:
    values: dict[int, object | None] = {}
    kinds = (
        "fname",
        "fname",
        "soft_path",
        "uint8",
        "uint8",
        "int32",
        "int32",
        "int32",
        "int32",
        "int32",
        "int32",
    )
    for relative_index, kind in enumerate(kinds):
        if not state.get(base_offset + relative_index, False):
            values[relative_index] = None
            continue
        if kind == "fname":
            values[relative_index], offset = _read_fname(data, offset, name_map)
        elif kind == "soft_path":
            values[relative_index], offset = _read_soft_object_path(
                data, offset, name_map
            )
        elif kind == "uint8":
            if offset >= len(data):
                raise ValueError("Static item byte ended early")
            values[relative_index] = data[offset]
            offset += 1
        else:
            if offset + 4 > len(data):
                raise ValueError("Static item integer ended early")
            values[relative_index] = struct.unpack_from("<i", data, offset)[0]
            offset += 4

    icon = values[2]
    if values[0] != expected_id or not isinstance(icon, tuple):
        raise ValueError("Static item identity does not match the root map")
    icon_package, icon_asset, icon_sub_path = icon
    if (
        not isinstance(icon_package, str)
        or not icon_package.startswith("/")
        or not isinstance(icon_asset, str)
        or not icon_asset
        or icon_sub_path
    ):
        raise ValueError("Static item icon path is not the verified asset form")

    numeric = {
        index: int(values[index] or 0)
        for index in range(3, 11)
    }
    if not 1 <= numeric[3] <= 13 or not 1 <= numeric[4] <= 255:
        raise ValueError("Static item type is outside the verified enum range")
    if not 0 <= numeric[5] <= 9999 or not 0 <= numeric[6] <= 99:
        raise ValueError("Static item rank or rarity is outside the verified range")
    if numeric[7] < 0 or not 1 <= numeric[8] <= 99_999_999:
        raise ValueError("Static item price or maximum stack is invalid")
    if numeric[9] < 0 or numeric[10] not in _DYNAMIC_KIND:
        raise ValueError("Static item sort or dynamic class is invalid")
    item_static_class = values[1]
    if item_static_class is not None and not isinstance(item_static_class, str):
        raise ValueError("Static item base class ID is invalid")
    return StaticItemRule(
        static_id=expected_id,
        name_base=name_base,
        name_number=name_number,
        type_a=numeric[3],
        type_b=numeric[4],
        rank=numeric[5],
        rarity=numeric[6],
        price=numeric[7],
        max_stack=numeric[8],
        sort_id=numeric[9],
        dynamic_class_index=numeric[10],
        item_static_class=item_static_class,
        icon_package=icon_package,
        icon_asset=icon_asset,
        object_class=object_class,
    )


def decode_static_item_asset(
    asset: dict[str, Any], *, expected_count: int = EXPECTED_ITEM_COUNT
) -> dict[str, StaticItemRule]:
    if asset.get("IsUnversioned") is not True:
        raise ValueError("Static item asset is not an unversioned Unreal asset")
    name_map = asset.get("NameMap")
    exports = asset.get("Exports")
    if not isinstance(name_map, list) or not all(
        isinstance(value, str) for value in name_map
    ):
        raise ValueError("Static item asset has an invalid NameMap")
    if not isinstance(exports, list):
        raise ValueError("Static item asset has no Exports array")

    root_candidates = [
        index
        for index, export in enumerate(exports)
        if _import_name(asset, int(export.get("ClassIndex", 0)))
        == "PalStaticItemDataAsset"
    ]
    if len(root_candidates) != 1:
        raise ValueError(
            f"Expected one PalStaticItemDataAsset export, found {root_candidates}"
        )
    root_index = root_candidates[0]
    root = decode_base64(exports[root_index].get("Data"), field="root Data")
    offset, state = parse_unversioned_header(root)
    if state != {0: True, 1: True}:
        raise ValueError("Static item root property schema does not match build 24088745")
    if offset + 8 > len(root):
        raise ValueError("Static item root map ended early")
    removed_count, entry_count = struct.unpack_from("<ii", root, offset)
    offset += 8
    if removed_count != 0 or entry_count != expected_count + 1:
        raise ValueError(
            "Static item root map count does not match the expected Palworld build"
        )

    export_ids: dict[int, tuple[str, str, int]] = {}
    for entry_index in range(entry_count):
        if offset + 12 > len(root):
            raise ValueError("Static item root map entry ended early")
        name_index, name_number, package_index = struct.unpack_from(
            "<iii", root, offset
        )
        offset += 12
        static_id = _render_fname(name_map, name_index, name_number)
        if entry_index == 0:
            if static_id != "None" or package_index != 0:
                raise ValueError("Static item root map sentinel is invalid")
            continue
        export_index = package_index - 1
        if (
            package_index <= 0
            or export_index == root_index
            or not 0 <= export_index < len(exports)
            or export_index in export_ids
        ):
            raise ValueError("Static item root map contains an invalid export reference")
        export_ids[export_index] = (
            static_id,
            name_map[name_index],
            name_number,
        )
    if len(root) - offset != 24:
        raise ValueError("Static item root trailer does not match build 24088745")
    expected_exports = set(range(len(exports))) - {root_index}
    if set(export_ids) != expected_exports or len(export_ids) != expected_count:
        raise ValueError("Static item root map does not cover every item export")

    result: dict[str, StaticItemRule] = {}
    for export_index in sorted(export_ids):
        export = exports[export_index]
        object_class = _import_name(asset, int(export.get("ClassIndex", 0)))
        if object_class not in _BASE_PROPERTY_OFFSET:
            raise ValueError(f"Unsupported static item object class: {object_class}")
        data = decode_base64(
            export.get("Data"), field=f"Exports[{export_index}].Data"
        )
        payload_offset, property_state = parse_unversioned_header(data)
        static_id, name_base, name_number = export_ids[export_index]
        name_index = name_map.index(name_base)
        pattern = struct.pack("<ii", name_index, name_number)
        candidates: list[StaticItemRule] = []
        for hit in _all_hits(data, pattern, payload_offset):
            try:
                candidates.append(
                    _read_static_base_candidate(
                        data,
                        hit,
                        property_state,
                        _BASE_PROPERTY_OFFSET[object_class],
                        name_map,
                        expected_id=static_id,
                        name_base=name_base,
                        name_number=name_number,
                        object_class=object_class,
                    )
                )
            except (IndexError, KeyError, UnicodeError, ValueError, struct.error):
                continue
        if len(candidates) != 1:
            raise ValueError(
                f"Expected one verified base record for {static_id}, found "
                f"{len(candidates)}"
            )
        record = candidates[0]
        expected_dynamic_import = _DYNAMIC_IMPORT.get(record.dynamic_class_index)
        if expected_dynamic_import is not None:
            actual_dynamic_import = _import_name(
                asset, record.dynamic_class_index
            )
            if actual_dynamic_import != expected_dynamic_import:
                raise ValueError(
                    f"{static_id} dynamic class resolves to {actual_dynamic_import}, "
                    f"expected {expected_dynamic_import}"
                )
        if record.static_id in result:
            raise ValueError(f"Duplicate static item ID: {record.static_id}")
        result[record.static_id] = record
    return result


def _read_table_prefix(
    data: bytes, position: int, name_map: list[str]
) -> tuple[dict[int, bool], dict[int, object | None]]:
    offset, state = parse_unversioned_header(data, position + 8)
    if set(state) != set(range(53)):
        raise ValueError("Data-table row schema does not match build 24088745")
    kinds = (
        "fname",
        "fname",
        "fname",
        "uint8",
        "uint8",
        "int32",
        "int32",
        "int32",
        "float32",
        "int32",
        "int32",
        "bool",
        "bool",
        "bool",
        "bool",
        "bool",
    )
    values: dict[int, object | None] = {}
    for property_index, kind in enumerate(kinds):
        if not state[property_index]:
            values[property_index] = None
            continue
        if kind == "fname":
            values[property_index], offset = _read_fname(data, offset, name_map)
        elif kind in {"uint8", "bool"}:
            if offset >= len(data):
                raise ValueError("Data-table byte ended early")
            value = data[offset]
            offset += 1
            if kind == "bool" and value != 1:
                raise ValueError("Non-zero data-table bool is not encoded as 1")
            values[property_index] = value
        elif kind == "float32":
            if offset + 4 > len(data):
                raise ValueError("Data-table float ended early")
            values[property_index] = struct.unpack_from("<f", data, offset)[0]
            offset += 4
        else:
            if offset + 4 > len(data):
                raise ValueError("Data-table integer ended early")
            values[property_index] = struct.unpack_from("<i", data, offset)[0]
            offset += 4
    return state, values


def apply_official_legal_flags(
    asset: dict[str, Any],
    records: dict[str, StaticItemRule],
    *,
    expected_count: int = EXPECTED_ITEM_COUNT,
) -> dict[str, StaticItemRule]:
    if asset.get("IsUnversioned") is not True:
        raise ValueError("Item data table is not an unversioned Unreal asset")
    name_map = asset.get("NameMap")
    exports = asset.get("Exports")
    if not isinstance(name_map, list) or not isinstance(exports, list):
        raise ValueError("Item data table has invalid maps or exports")
    if len(exports) != 1 or exports[0].get("ObjectName") != "DT_ItemDataTable_Common":
        raise ValueError("Expected the DT_ItemDataTable_Common export")
    data = decode_base64(exports[0].get("Data"), field="data-table Data")
    struct_imports = [
        -(index + 1)
        for index, value in enumerate(asset.get("Imports") or [])
        if value.get("ObjectName") == "PalStaticItemDataStruct"
    ]
    if len(struct_imports) != 1:
        raise ValueError("Expected one PalStaticItemDataStruct import")
    if (
        data[:2] != b"\x00\x03"
        or struct.unpack_from("<i", data, 2)[0] != struct_imports[0]
        or struct.unpack_from("<i", data, 6)[0] != 0
        or struct.unpack_from("<i", data, 10)[0] != expected_count
    ):
        raise ValueError("Data-table outer schema does not match build 24088745")
    if len(records) != expected_count:
        raise ValueError("Static record count does not match the item data table")

    name_indices = {name: index for index, name in enumerate(name_map)}
    result: dict[str, StaticItemRule] = {}
    row_positions: set[int] = set()
    for static_id, record in records.items():
        if record.name_base not in name_indices:
            raise ValueError(f"{static_id} is missing from the data-table NameMap")
        pattern = struct.pack(
            "<ii", name_indices[record.name_base], record.name_number
        )
        candidates: list[tuple[int, bool]] = []
        for position in _all_hits(data, pattern, 14):
            try:
                _, values = _read_table_prefix(data, position, name_map)
                comparisons = {
                    3: record.type_a,
                    4: record.type_b,
                    5: record.rank,
                    6: record.rarity,
                    7: record.max_stack,
                    9: record.price,
                    10: record.sort_id,
                }
                if any(int(values[index] or 0) != expected for index, expected in comparisons.items()):
                    continue
                candidates.append((position, bool(values[15])))
            except (IndexError, KeyError, UnicodeError, ValueError, struct.error):
                continue
        if len(candidates) != 1:
            raise ValueError(
                f"Expected one cross-validated data-table row for {static_id}, "
                f"found {len(candidates)}"
            )
        position, official_legal = candidates[0]
        if position in row_positions:
            raise ValueError("Two item IDs resolved to the same data-table row")
        row_positions.add(position)
        result[static_id] = replace(record, official_legal=official_legal)
    if len(row_positions) != expected_count or min(row_positions) != 14:
        raise ValueError("Data-table rows are not a complete unique set")
    return result


def item_category(type_a: int, type_b: int) -> str:
    if type_a in {1, 2}:
        return "weapon"
    if type_a == 3:
        categories = {20: "head", 21: "body", 58: "shield"}
        if type_b not in categories:
            raise ValueError(f"Unsupported armor TypeB value: {type_b}")
        return categories[type_b]
    if type_a == 4:
        return "accessory"
    if type_a == 8:
        return "food"
    if type_a == 9:
        return "key_item"
    if type_a == 10:
        return "glider"
    if type_a == 11:
        return "unsupported"
    if type_a == 13:
        return "sphere_module"
    return "common"


def allowed_containers(category: str) -> tuple[str, ...]:
    if category == "unsupported":
        return ()
    if category == "key_item":
        return ("ESSENTIAL",)
    result = list(_COMMON_CONTAINERS)
    if category == "weapon":
        result.append("WEAPON_LOADOUT")
    elif category in _EQUIPMENT_CATEGORIES:
        result.append("PLAYER_EQUIP_ARMOR")
    elif category == "food":
        result.append("FOOD_EQUIP")
    return tuple(result)


def build_catalog(
    existing: dict[str, Any],
    records: dict[str, StaticItemRule],
    *,
    build: int = BUILD,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for static_id in sorted(records):
        record = records[static_id]
        previous = existing.get(static_id)
        if previous is not None and not isinstance(previous, dict):
            raise ValueError(f"Existing catalog row {static_id} is not an object")
        previous = previous or {}
        internal_name = previous.get("InternalName") or static_id
        if internal_name != static_id:
            raise ValueError(
                f"Existing catalog key {static_id} has InternalName {internal_name}"
            )
        localization_source = previous
        if not localization_source and record.item_static_class:
            inherited = existing.get(record.item_static_class)
            if isinstance(inherited, dict):
                localization_source = inherited
        previous_i18n = localization_source.get("I18n")
        if not isinstance(previous_i18n, dict):
            previous_i18n = {}
        i18n: dict[str, dict[str, str]] = {}
        for locale in SUPPORTED_LOCALES:
            localized = previous_i18n.get(locale)
            if not isinstance(localized, dict):
                localized = {}
            i18n[locale] = {
                "Name": str(localized.get("Name") or static_id),
                "Description": str(localized.get("Description") or ""),
            }
        category = item_category(record.type_a, record.type_b)
        disabled = (
            (
                not record.official_legal
                and static_id not in EDITOR_ENABLED_UNOFFICIAL_ITEMS
            )
            or category == "unsupported"
        )
        result[static_id] = {
            "InternalName": static_id,
            "Icon": previous.get("Icon") or record.icon_asset,
            "I18n": i18n,
            "Rule": {
                "Category": category,
                "Rarity": record.rarity,
                "MaxStack": record.max_stack,
                "AllowedContainers": list(allowed_containers(category)),
                "DynamicKind": record.dynamic_kind,
                "Status": "verified",
                "Source": RULE_SOURCE,
                "Version": f"Steam build {build}",
                "Disabled": disabled,
                "GameTypeA": record.type_a,
                "GameTypeB": record.type_b,
                "OfficialLegal": record.official_legal,
                "ItemStaticClass": record.item_static_class,
            },
        }
    return result


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Cross-validate Palworld 1.0 official item assets and sync strict "
            "write rules into item_data.json."
        )
    )
    parser.add_argument("static_item_asset", type=Path)
    parser.add_argument("item_data_table", type=Path)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--build", type=int, default=BUILD)
    args = parser.parse_args()

    existing = load_json(args.catalog)
    static_records = decode_static_item_asset(load_json(args.static_item_asset))
    records = apply_official_legal_flags(
        load_json(args.item_data_table), static_records
    )
    catalog = build_catalog(existing, records, build=args.build)
    output = args.output or args.catalog
    output.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    summary = {
        "items": len(catalog),
        "official_legal": sum(record.official_legal for record in records.values()),
        "disabled": sum(row["Rule"]["Disabled"] for row in catalog.values()),
        "localized_source_rows": len(set(existing) & set(records)),
        "stale_source_rows": len(set(existing) - set(records)),
        "categories": dict(
            sorted(Counter(row["Rule"]["Category"] for row in catalog.values()).items())
        ),
        "dynamic_kinds": dict(
            sorted(Counter(row["Rule"]["DynamicKind"] for row in catalog.values()).items())
        ),
        "output": str(output),
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
