from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
import json
import mmap
from pathlib import Path
import re
import struct
from typing import Any

try:
    from sync_1_0_item_rules import (
        _read_fname,
        _read_fstring,
        decode_base64,
        parse_unversioned_header,
    )
    from sync_1_0_localized_assets import (
        LANGUAGE_TOKENS,
        fill_missing_with_english,
        load_table,
        replace_reference_tags,
        write_json,
    )
except ImportError:  # pragma: no cover - package-style invocation
    from .sync_1_0_item_rules import (
        _read_fname,
        _read_fstring,
        decode_base64,
        parse_unversioned_header,
    )
    from .sync_1_0_localized_assets import (
        LANGUAGE_TOKENS,
        fill_missing_with_english,
        load_table,
        replace_reference_tags,
        write_json,
    )


BUILD = 24088745
EXPECTED_PASSIVE_TABLE_ROWS = 1905
EXPECTED_EDITABLE_PASSIVES = 114
EXPECTED_REGULAR_PASSIVES = 86
EXPECTED_PAL_ROWS = 753
EXPECTED_HUMAN_ROWS = 433
EXPECTED_HUMAN_ICON_ROWS = 33
EXPECTED_EXP_ROWS = 100
EXPECTED_FRIENDSHIP_ROWS = 14
EXPECTED_WAZA_ROWS = 5772
EXPECTED_WAZA_PALS = 712
EXPECTED_WAZA_ENUM_NAMES = 392
EXPECTED_WAZA_DATA_ROWS = 384
PAL_PARAMETER_STRUCT = "/Script/Pal.PalCharacterParameterDatabaseRow"

# Build 24088745 marks 86 ordinary traits as randomly assignable. These 28
# additional traits are also valid Pal traits, but are obtained from species,
# bosses, mutations, the World Tree, or other special game systems.
SPECIAL_PASSIVE_IDS = frozenset(
    {
        "Legend",
        "Witch",
        "EternalFlame",
        "Invader",
        "ElementBoost_Normal_2_PAL",
        "ElementBoost_Fire_2_PAL",
        "ElementBoost_Aqua_2_PAL",
        "ElementBoost_Thunder_2_PAL",
        "ElementBoost_Leaf_2_PAL",
        "ElementBoost_Ice_2_PAL",
        "ElementBoost_Earth_2_PAL",
        "ElementBoost_Dark_2_PAL",
        "ElementBoost_Dragon_2_PAL",
        "Nushi",
        "Alien",
        "Salvation",
        "WorldTree_ATK",
        "WorldTree_DEF",
        "WorldTree_CraftSpeed",
        "WorldTree_FullStomach",
        "WorldTree_Sanity",
        "WorldTree_MoveSpeed",
        "WorldTree_ATK_DEF",
        "MutationPal_Babysitter",
        "MutationPal_Mutant",
        "MutationPal_Immortal",
        "MutationPal_ExplosionResist",
        "RideJumpCount_Increase2",
    }
)

ELEMENTS = {
    1: "Neutral",
    2: "Fire",
    3: "Water",
    4: "Grass",
    5: "Electricity",
    6: "Ice",
    7: "Ground",
    8: "Dark",
    9: "Dragon",
}
ATTACK_ELEMENTS = {
    0: "",
    1: "Neutral",
    2: "Fire",
    3: "Water",
    4: "Grass",
    5: "Electric",
    6: "Ice",
    7: "Ground",
    8: "Dark",
    9: "Dragon",
}
SUITABILITIES = (
    "EmitFlame",
    "Watering",
    "Seeding",
    "GenerateElectricity",
    "Handcraft",
    "Collection",
    "Deforest",
    "Mining",
    "OilExtraction",
    "ProductMedicine",
    "Cool",
    "Transport",
    "MonsterFarm",
)
BUFF_EFFECTS = {
    3: "b_Attack",
    4: "b_Defense",
    6: "b_CraftSpeed",
    7: "b_MoveSpeed",
}
EXP_FIELDS = (
    "DropEXP",
    "NextEXP",
    "PalNextEXP",
    "TotalEXP",
    "PalTotalEXP",
    "BuildEXP",
    "CraftEXP",
    "PalBuildEXP",
    "PalCraftEXP",
)
PLACEHOLDER_TEXT = {
    "",
    "-",
    "dummy_text",
    "en Text",
    "fr_Text",
    "ja Text",
    "zh-hans text",
}


@dataclass(frozen=True)
class PassiveEffect:
    effect_type: int
    value: float
    target: int


@dataclass(frozen=True)
class PassiveRecord:
    internal_name: str
    rating: int
    weight: int
    override_description_id: str | None
    effects: tuple[PassiveEffect, ...]
    position: int


@dataclass(frozen=True)
class PalRecord:
    internal_name: str
    values: dict[str, Any]


@dataclass(frozen=True)
class WazaDataRecord:
    internal_name: str
    element: str
    cooldown: float
    power: int
    ignore_random_inherit: bool
    position: int


def _asset_payload(asset: dict[str, Any], expected_object_name: str) -> bytes:
    if asset.get("IsUnversioned") is not True:
        raise ValueError(f"{expected_object_name} is not an unversioned asset")
    exports = asset.get("Exports")
    if not isinstance(exports, list) or len(exports) != 1:
        raise ValueError(f"{expected_object_name} must have exactly one export")
    export = exports[0]
    if export.get("ObjectName") != expected_object_name:
        raise ValueError(
            f"Expected {expected_object_name}, got {export.get('ObjectName')}"
        )
    return decode_base64(export.get("Data"), field=f"{expected_object_name} Data")


def _read_passive_prefix(
    data: bytes,
    position: int,
    name_map: list[str],
) -> tuple[PassiveRecord, dict[int, bool], int]:
    internal_name, _ = _read_fname(data, position, name_map)
    offset, state = parse_unversioned_header(data, position + 8)
    if set(state) != set(range(38)):
        raise ValueError("Passive row property schema does not match build 24088745")

    values: dict[int, Any] = {}
    kinds = (
        "int32",
        "int32",
        "fname",
        "fname",
        "uint8",
        "float32",
        "uint8",
        "uint8",
        "float32",
        "uint8",
        "uint8",
        "float32",
        "uint8",
    )
    for property_index, kind in enumerate(kinds):
        if not state[property_index]:
            values[property_index] = None
            continue
        if kind == "int32":
            values[property_index] = struct.unpack_from("<i", data, offset)[0]
            offset += 4
        elif kind == "fname":
            values[property_index], offset = _read_fname(data, offset, name_map)
        elif kind == "float32":
            values[property_index] = struct.unpack_from("<f", data, offset)[0]
            offset += 4
        else:
            values[property_index] = data[offset]
            offset += 1

    rating = int(values[0] or 0)
    weight = int(values[1] or 0)
    if not -10 <= rating <= 10 or not 0 <= weight <= 100_000:
        raise ValueError("Passive rating or weight is outside the verified range")
    effects = tuple(
        PassiveEffect(
            effect_type=int(values[index]),
            value=float(values[index + 1] or 0.0),
            target=int(values[index + 2] or 0),
        )
        for index in (4, 7, 10)
        if values[index] is not None
    )
    override = values[2]
    if override in (None, "None"):
        override = None
    return (
        PassiveRecord(
            internal_name=internal_name,
            rating=rating,
            weight=weight,
            override_description_id=override,
            effects=effects,
            position=position,
        ),
        state,
        offset,
    )


def decode_passive_asset(
    asset: dict[str, Any],
    *,
    expected_count: int = EXPECTED_EDITABLE_PASSIVES,
) -> dict[str, PassiveRecord]:
    name_map = asset.get("NameMap")
    if not isinstance(name_map, list) or not all(
        isinstance(value, str) for value in name_map
    ):
        raise ValueError("Passive asset has an invalid NameMap")
    data = _asset_payload(asset, "DT_PassiveSkill_Main_Common")
    if (
        data[:2] != b"\x00\x03"
        or struct.unpack_from("<i", data, 6)[0] != 0
        or struct.unpack_from("<i", data, 10)[0] != EXPECTED_PASSIVE_TABLE_ROWS
    ):
        raise ValueError("Passive table outer schema does not match build 24088745")

    # Rows are found by their FName followed by the exact 38-property header.
    # For the ordinary rows, properties 13..26 are all absent or serialized as
    # one-byte true flags; property 25 is the assignable flag and property 26
    # is the Lucky-trait flag. The exact count guards against false byte hits.
    candidates: dict[str, list[PassiveRecord]] = {}
    regular: dict[str, PassiveRecord] = {}
    for position in range(14, len(data) - 12):
        try:
            name_index, name_number = struct.unpack_from("<ii", data, position)
            if not 0 <= name_index < len(name_map) or not 0 <= name_number < 100:
                continue
            record, state, offset = _read_passive_prefix(data, position, name_map)
            candidates.setdefault(record.internal_name, []).append(record)
            flags: dict[int, int | None] = {}
            for property_index in range(13, 27):
                if state[property_index]:
                    flags[property_index] = data[offset]
                    offset += 1
                else:
                    flags[property_index] = None
            if all(value in (None, 1) for value in flags.values()) and (
                flags[25] or flags[26]
            ):
                regular[record.internal_name] = record
        except (IndexError, UnicodeError, ValueError, struct.error):
            continue

    if len(regular) != EXPECTED_REGULAR_PASSIVES:
        raise ValueError(
            f"Expected {EXPECTED_REGULAR_PASSIVES} regular Pal traits, "
            f"found {len(regular)}"
        )
    result = dict(regular)
    for internal_name in SPECIAL_PASSIVE_IDS:
        matches = candidates.get(internal_name, [])
        if len(matches) != 1:
            raise ValueError(
                f"Expected one special trait {internal_name}, found {len(matches)}"
            )
        result[internal_name] = matches[0]
    if len(result) != expected_count:
        raise ValueError(f"Expected {expected_count} editable traits, found {len(result)}")
    return result


def _load_pal_schema(mapping_path: Path) -> list[dict[str, Any]]:
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    try:
        properties = mapping["objects"][PAL_PARAMETER_STRUCT]["properties"]
    except (KeyError, TypeError) as error:
        raise ValueError(f"Mapping has no {PAL_PARAMETER_STRUCT} schema") from error
    if len(properties) != 90:
        raise ValueError(
            f"Expected the 90-property build 24088745 Pal schema, got {len(properties)}"
        )
    return properties


def _read_pal_property(
    data: bytes,
    offset: int,
    name_map: list[str],
    property_schema: dict[str, Any],
) -> tuple[Any, int]:
    property_type = property_schema["type"]
    property_name = property_schema["name"]
    if property_type == "NameProperty":
        return _read_fname(data, offset, name_map)
    if property_type == "StrProperty":
        return _read_fstring(data, offset)
    if property_type == "BoolProperty":
        value = data[offset]
        if value != 1:
            raise ValueError(f"Non-zero {property_name} bool is not encoded as 1")
        return True, offset + 1
    if property_type == "EnumProperty":
        # EPalTribeID exceeded 255 in this build and is serialized as uint16.
        if property_name == "Tribe":
            return struct.unpack_from("<H", data, offset)[0], offset + 2
        return data[offset], offset + 1
    if property_type == "FloatProperty":
        return struct.unpack_from("<f", data, offset)[0], offset + 4
    if property_type == "IntProperty":
        return struct.unpack_from("<i", data, offset)[0], offset + 4
    if property_type == "StructProperty" and property_name == "MeshRelativeLocation":
        return struct.unpack_from("<ddd", data, offset), offset + 24
    raise ValueError(f"Unsupported Pal property {property_name}: {property_type}")


def _decode_character_parameter_asset(
    asset: dict[str, Any],
    mapping_path: Path,
    *,
    expected_object_name: str,
    expected_count: int,
    expected_is_pal: bool,
) -> dict[str, PalRecord]:
    name_map = asset.get("NameMap")
    if not isinstance(name_map, list) or not all(
        isinstance(value, str) for value in name_map
    ):
        raise ValueError(f"{expected_object_name} has an invalid NameMap")
    data = _asset_payload(asset, expected_object_name)
    if (
        data[:2] != b"\x00\x03"
        or struct.unpack_from("<i", data, 6)[0] != 0
        or struct.unpack_from("<i", data, 10)[0] != expected_count
    ):
        raise ValueError(
            f"{expected_object_name} outer schema does not match build 24088745"
        )
    properties = _load_pal_schema(mapping_path)

    offset = 14
    result: dict[str, PalRecord] = {}
    for _ in range(expected_count):
        internal_name, offset = _read_fname(data, offset, name_map)
        offset, state = parse_unversioned_header(data, offset)
        if set(state) != set(range(len(properties))):
            raise ValueError(
                f"Unexpected property schema for {expected_object_name} row "
                f"{internal_name}"
            )
        values: dict[str, Any] = {}
        for property_index, property_schema in enumerate(properties):
            property_name = property_schema["name"]
            if not state[property_index]:
                values[property_name] = None
                continue
            values[property_name], offset = _read_pal_property(
                data, offset, name_map, property_schema
            )
        if internal_name in result:
            raise ValueError(f"Duplicate character ID: {internal_name}")
        if bool(values.get("IsPal")) is not expected_is_pal:
            expected_kind = "Pal" if expected_is_pal else "human"
            raise ValueError(
                f"Non-{expected_kind} row found in {expected_object_name}: "
                f"{internal_name}"
            )
        result[internal_name] = PalRecord(internal_name, values)
    if offset != len(data):
        raise ValueError(
            f"{expected_object_name} has {len(data) - offset} unparsed bytes "
            f"after {expected_count} rows"
        )
    return result


def decode_pal_parameter_asset(
    asset: dict[str, Any],
    mapping_path: Path,
    *,
    expected_count: int = EXPECTED_PAL_ROWS,
) -> dict[str, PalRecord]:
    return _decode_character_parameter_asset(
        asset,
        mapping_path,
        expected_object_name="DT_PalMonsterParameter_Common",
        expected_count=expected_count,
        expected_is_pal=True,
    )


def decode_human_parameter_asset(
    asset: dict[str, Any],
    mapping_path: Path,
    *,
    expected_count: int = EXPECTED_HUMAN_ROWS,
) -> dict[str, PalRecord]:
    return _decode_character_parameter_asset(
        asset,
        mapping_path,
        expected_object_name="DT_PalHumanParameter_Common",
        expected_count=expected_count,
        expected_is_pal=False,
    )


def decode_waza_enum(game_executable: Path) -> tuple[str, ...]:
    """Read the authoritative EPalWazaID value order from the game binary."""
    prefix = b"EPalWazaID::"
    with game_executable.open("rb") as executable_file:
        with mmap.mmap(executable_file.fileno(), 0, access=mmap.ACCESS_READ) as data:
            start = data.find(prefix + b"None\0")
            if start < 0:
                raise ValueError("Game executable has no EPalWazaID enum block")
            enum_block = data[start : start + 500_000]
    names = tuple(
        match.group(1).decode("ascii")
        for match in re.finditer(
            rb"EPalWazaID::([A-Za-z0-9_]+)\x00", enum_block
        )
    )
    if (
        len(names) != EXPECTED_WAZA_ENUM_NAMES
        or names[0] != "None"
        or names[-1] != "MAX"
        or len(names) != len(set(names))
    ):
        raise ValueError(
            "EPalWazaID enum does not match Palworld 1.0 Build 24088745: "
            f"found {len(names)} values"
        )
    return names


def decode_waza_master_asset(
    asset: dict[str, Any],
    waza_enum: tuple[str, ...],
    *,
    expected_count: int = EXPECTED_WAZA_ROWS,
) -> dict[str, dict[str, int]]:
    name_map = asset.get("NameMap")
    if not isinstance(name_map, list) or not all(
        isinstance(value, str) for value in name_map
    ):
        raise ValueError("Waza master asset has an invalid NameMap")
    data = _asset_payload(asset, "DT_WazaMasterLevel_Common")
    if (
        data[:2] != b"\x00\x03"
        or struct.unpack_from("<i", data, 6)[0] != 0
        or struct.unpack_from("<i", data, 10)[0] != expected_count
    ):
        raise ValueError("Waza master outer schema does not match build 24088745")

    offset = 14
    result: dict[str, dict[str, int]] = {}
    for _ in range(expected_count):
        _, offset = _read_fname(data, offset, name_map)
        offset, state = parse_unversioned_header(data, offset)
        if set(state) != {0, 1, 2}:
            raise ValueError("Waza master row property schema is invalid")
        pal_id: str | None = None
        waza_id = 0
        level = 0
        if state[0]:
            pal_id, offset = _read_fname(data, offset, name_map)
        if state[1]:
            waza_id = struct.unpack_from("<H", data, offset)[0]
            offset += 2
        if state[2]:
            level = struct.unpack_from("<i", data, offset)[0]
            offset += 4
        if not pal_id or not 0 < waza_id < len(waza_enum) - 1 or level <= 0:
            raise ValueError(
                f"Invalid Waza master row: Pal={pal_id}, Waza={waza_id}, Level={level}"
            )
        internal_name = f"EPalWazaID::{waza_enum[waza_id]}"
        learnset = result.setdefault(pal_id, {})
        if internal_name in learnset:
            raise ValueError(f"Duplicate {internal_name} learnset row for {pal_id}")
        learnset[internal_name] = level
    if offset != len(data):
        raise ValueError(
            f"Waza master has {len(data) - offset} unparsed bytes after its rows"
        )
    if len(result) != EXPECTED_WAZA_PALS:
        raise ValueError(
            f"Expected learnsets for {EXPECTED_WAZA_PALS} Pals, found {len(result)}"
        )
    return result


def decode_waza_data_asset(
    asset: dict[str, Any],
    waza_enum: tuple[str, ...],
    *,
    expected_count: int = EXPECTED_WAZA_DATA_ROWS,
) -> dict[str, WazaDataRecord]:
    """Decode the editor-facing prefix of every official Waza data row."""
    name_map = asset.get("NameMap")
    if not isinstance(name_map, list) or name_map[0] != "NewRow":
        raise ValueError("Waza data asset has an invalid NameMap")
    data = _asset_payload(asset, "DT_WazaDataTable_Common")
    if (
        data[:2] != b"\x00\x03"
        or struct.unpack_from("<i", data, 6)[0] != 0
        or struct.unpack_from("<i", data, 10)[0] != expected_count
    ):
        raise ValueError("Waza data outer schema does not match build 24088745")

    # The suffix of this struct contains several variable-size combat tuning
    # fields which the editor does not expose. Scan for the exact row header and
    # decode properties 0..15, which contain ID, element, inheritance flags,
    # power, and cooldown. The official row count and unique IDs prevent false
    # byte-pattern matches.
    kinds = (
        "uint16",
        "uint8",
        "bool",
        "bool",
        "int32",
        "int32",
        "float32",
        "uint8",
        "bool",
        "int32",
        "int32",
        "int32",
        "float32",
        "uint8",
        "uint8",
        "int32",
    )
    result: dict[str, WazaDataRecord] = {}
    for position in range(14, len(data) - 20):
        candidate: WazaDataRecord | None = None
        try:
            name_index, name_number = struct.unpack_from("<ii", data, position)
            if name_index != 0 or not 0 <= name_number < 10_000:
                continue
            offset, state = parse_unversioned_header(data, position + 8)
            if set(state) != set(range(27)):
                continue
            values: dict[int, Any] = {}
            for property_index, kind in enumerate(kinds):
                if not state[property_index]:
                    values[property_index] = None
                    continue
                if kind == "uint16":
                    values[property_index] = struct.unpack_from(
                        "<H", data, offset
                    )[0]
                    offset += 2
                elif kind in {"uint8", "bool"}:
                    values[property_index] = data[offset]
                    offset += 1
                elif kind == "int32":
                    values[property_index] = struct.unpack_from(
                        "<i", data, offset
                    )[0]
                    offset += 4
                else:
                    values[property_index] = struct.unpack_from(
                        "<f", data, offset
                    )[0]
                    offset += 4
            waza_id = int(values[0] or 0)
            element_id = int(values[1] or 0)
            if not 0 < waza_id < len(waza_enum) - 1:
                continue
            if element_id not in ATTACK_ELEMENTS:
                continue
            if any(values[index] not in (None, 1) for index in (2, 3, 8)):
                continue
            cooldown = float(values[12] or 0.0)
            power = int(values[4] or 0)
            if not 0 <= cooldown <= 10_000 or not 0 <= power <= 100_000:
                continue
            internal_name = f"EPalWazaID::{waza_enum[waza_id]}"
            candidate = WazaDataRecord(
                internal_name=internal_name,
                element=ATTACK_ELEMENTS[element_id],
                cooldown=cooldown,
                power=power,
                ignore_random_inherit=bool(values[2]),
                position=position,
            )
        except (IndexError, ValueError, struct.error):
            continue
        if candidate is None:
            continue
        if candidate.internal_name in result:
            raise ValueError(
                f"Duplicate Waza data row for {candidate.internal_name}"
            )
        result[candidate.internal_name] = candidate
    if len(result) != expected_count:
        raise ValueError(
            f"Expected {expected_count} Waza data rows, found {len(result)}"
        )
    return result


def _localization_context(
    json_root: Path,
) -> tuple[
    dict[str, dict[str, str]],
    dict[str, dict[str, str]],
    dict[str, dict[str, str]],
    dict[str, dict[str, dict[str, str]]],
]:
    skill_names = {
        language: load_table(json_root, language, "DT_SkillNameText_Common")
        for language in LANGUAGE_TOKENS
    }
    skill_descriptions = {
        language: load_table(json_root, language, "DT_SkillDescText_Common")
        for language in LANGUAGE_TOKENS
    }
    pal_names_raw = {
        language: load_table(json_root, language, "DT_PalNameText_Common")
        for language in LANGUAGE_TOKENS
    }
    ui_common = {
        language: load_table(json_root, language, "DT_UI_Common_Text_Common")
        for language in LANGUAGE_TOKENS
    }
    item_names = {
        language: {
            key.removeprefix("ITEM_NAME_"): value
            for key, value in load_table(
                json_root, language, "DT_ItemNameText_Common"
            ).items()
        }
        for language in LANGUAGE_TOKENS
    }
    map_object_names = {
        language: {
            key.removeprefix("MAPOBJECT_NAME_"): value
            for key, value in load_table(
                json_root, language, "DT_MapObjectNameText_Common"
            ).items()
        }
        for language in LANGUAGE_TOKENS
    }
    character_names = {
        language: {
            key.removeprefix("PAL_NAME_"): value
            for key, value in pal_names_raw[language].items()
        }
        for language in LANGUAGE_TOKENS
    }
    active_skill_names = {
        language: {
            key.removeprefix("ACTION_SKILL_"): value
            for key, value in skill_names[language].items()
            if key.startswith("ACTION_SKILL_")
        }
        for language in LANGUAGE_TOKENS
    }
    references = {
        "uiCommon": ui_common,
        "itemName": item_names,
        "mapObjectName": map_object_names,
        "MapObjectName": map_object_names,
        "characterName": character_names,
        "activeSkillName": active_skill_names,
    }
    return skill_names, skill_descriptions, pal_names_raw, references


def _format_effect_value(value: float) -> str:
    return str(int(value)) if value.is_integer() else f"{value:g}"


def _render_passive_description(text: str, record: PassiveRecord) -> str:
    for effect_index, effect in enumerate(record.effects, start=1):
        text = text.replace(
            f"{{EffectValue{effect_index}}}", _format_effect_value(effect.value)
        )
    return text


KOREAN_PASSIVE_EFFECT_LABELS = {
    3: "공격",
    4: "방어",
    6: "작업 속도",
}


def _render_korean_passive_effects(record: PassiveRecord) -> str:
    lines = []
    for effect in record.effects:
        label = KOREAN_PASSIVE_EFFECT_LABELS.get(effect.effect_type)
        if label and effect.target in (1, 3):
            sign = "+" if effect.value >= 0 else ""
            lines.append(f"{label} {sign}{_format_effect_value(effect.value)}%")
    return "\n".join(lines)


def _passive_i18n(
    record: PassiveRecord,
    existing: dict[str, Any],
    skill_names: dict[str, dict[str, str]],
    skill_descriptions: dict[str, dict[str, str]],
    references: dict[str, dict[str, dict[str, str]]],
) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    name_keys = (
        f"PASSIVE_{record.internal_name}",
        f"PASSIVE_PAL_{record.internal_name}",
    )
    description_keys = tuple(
        key
        for key in (
            record.override_description_id,
            f"PASSIVE_PAL_{record.internal_name}",
            f"PASSIVE_{record.internal_name}",
            f"PASSIVE_{record.internal_name}_DESC",
        )
        if key
    )
    old_i18n = existing.get("I18n", {})
    for language in LANGUAGE_TOKENS:
        language_references = {
            reference_type: values[language]
            for reference_type, values in references.items()
        }
        name = next(
            (skill_names[language][key] for key in name_keys if skill_names[language].get(key)),
            "",
        )
        description = next(
            (
                skill_descriptions[language][key]
                for key in description_keys
                if skill_descriptions[language].get(key)
            ),
            "",
        )
        if description:
            description = _render_passive_description(description, record)
        else:
            description = (
                _render_korean_passive_effects(record)
                if language == "ko"
                else ""
            ) or old_i18n.get(language, {}).get("Description", "")
            if record.internal_name == "Rare" and description.count("15") >= 2:
                description = re.sub(r"15(?=\s*%)", "20", description, count=1)
        result[language] = {
            "Name": replace_reference_tags(name, language_references),
            "Description": replace_reference_tags(description, language_references),
        }
    fill_missing_with_english(result)
    if any(not values["Name"] for values in result.values()):
        raise ValueError(f"Missing official name for passive {record.internal_name}")
    if any(not values["Description"] for values in result.values()):
        raise ValueError(
            f"Missing official/generated description for passive {record.internal_name}"
        )
    return result


def build_passive_catalog(
    existing: dict[str, dict[str, Any]],
    records: dict[str, PassiveRecord],
    skill_names: dict[str, dict[str, str]],
    skill_descriptions: dict[str, dict[str, str]],
    references: dict[str, dict[str, dict[str, str]]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for record in sorted(records.values(), key=lambda value: (-value.rating, value.position)):
        buff = {
            "b_Attack": 0.0,
            "b_Defense": 0.0,
            "b_CraftSpeed": 0.0,
            "b_MoveSpeed": 0.0,
        }
        for effect in record.effects:
            buff_key = BUFF_EFFECTS.get(effect.effect_type)
            if buff_key and effect.target in (1, 3):
                buff[buff_key] = round(effect.value / 100.0, 6)
        old = existing.get(record.internal_name, {})
        result[record.internal_name] = {
            "InternalName": record.internal_name,
            "Rating": record.rating,
            "I18n": _passive_i18n(
                record, old, skill_names, skill_descriptions, references
            ),
            "Buff": buff,
        }
    return result


def _attack_i18n(
    record: WazaDataRecord,
    existing: dict[str, Any],
    skill_names: dict[str, dict[str, str]],
    skill_descriptions: dict[str, dict[str, str]],
    references: dict[str, dict[str, dict[str, str]]],
) -> dict[str, dict[str, str]]:
    suffix = record.internal_name.removeprefix("EPalWazaID::")
    localization_key = f"ACTION_SKILL_{suffix}"
    old_i18n = existing.get("I18n", {})
    result: dict[str, dict[str, str]] = {}
    for language in LANGUAGE_TOKENS:
        old_localized = old_i18n.get(language, {})
        language_references = {
            reference_type: values[language]
            for reference_type, values in references.items()
        }
        name = skill_names[language].get(localization_key, "")
        description = skill_descriptions[language].get(localization_key, "")
        result[language] = {
            "Name": replace_reference_tags(
                name or old_localized.get("Name", "") or suffix,
                language_references,
            ),
            "Description": replace_reference_tags(
                description or old_localized.get("Description", ""),
                language_references,
            ),
        }
    fill_missing_with_english(result)
    if any(not values["Name"] for values in result.values()):
        raise ValueError(f"Missing display name for attack {record.internal_name}")
    return result


def skill_fruits_from_item_catalog(
    items: dict[str, dict[str, Any]],
) -> set[str]:
    """Return active skills backed by verified v1.0 SkillCard item rows."""
    expected_source = "Palworld 1.0 DA_StaticItemDataAsset + DT_ItemDataTable_Common"
    expected_version = f"Steam build {BUILD}"
    result: set[str] = set()
    verified_rows = 0
    for item_id, item in items.items():
        if not item_id.startswith("SkillCard_"):
            continue
        rule = item.get("Rule", {})
        if (
            rule.get("Source") != expected_source
            or rule.get("Version") != expected_version
            or rule.get("Status") != "verified"
        ):
            raise ValueError(f"Skill fruit {item_id} is not verified against v1.0")
        verified_rows += 1
        if rule.get("OfficialLegal") and not rule.get("Disabled"):
            result.add(f"EPalWazaID::{item_id.removeprefix('SkillCard_')}")
    if verified_rows != 93 or len(result) != 92:
        raise ValueError(
            "Expected 93 verified SkillCard rows with 92 legal fruits, found "
            f"{verified_rows} rows and {len(result)} legal fruits"
        )
    return result


def build_attack_catalog(
    existing: dict[str, dict[str, Any]],
    records: dict[str, WazaDataRecord],
    skill_fruits: set[str],
    skill_names: dict[str, dict[str, str]],
    skill_descriptions: dict[str, dict[str, str]],
    references: dict[str, dict[str, dict[str, str]]],
) -> dict[str, dict[str, Any]]:
    unknown_skill_fruits = skill_fruits - set(records)
    if unknown_skill_fruits:
        raise ValueError(
            "SkillCard items reference attacks absent from Waza data: "
            f"{sorted(unknown_skill_fruits)}"
        )
    result: dict[str, dict[str, Any]] = {}
    for record in sorted(records.values(), key=lambda value: value.position):
        cooldown: int | float = record.cooldown
        if record.cooldown.is_integer():
            cooldown = int(record.cooldown)
        row = {
            "InternalName": record.internal_name,
            "Element": record.element,
            "CT": cooldown,
            "Power": record.power,
            "I18n": _attack_i18n(
                record,
                existing.get(record.internal_name, {}),
                skill_names,
                skill_descriptions,
                references,
            ),
            "UniqueSkill": record.ignore_random_inherit,
            "SkillFruit": record.internal_name in skill_fruits,
        }
        if not record.element:
            row["Invalid"] = True
        result[record.internal_name] = row
    return result


def _pal_i18n(
    record: PalRecord,
    pal_names: dict[str, dict[str, str]],
) -> dict[str, str]:
    override = record.values.get("OverrideNameTextID")
    name_key = override if override not in (None, "None") else f"PAL_NAME_{record.internal_name}"
    candidate_keys = [name_key]
    shortened_key = name_key
    while "_" in shortened_key.removeprefix("PAL_NAME_"):
        shortened_key = shortened_key.rsplit("_", 1)[0]
        candidate_keys.append(shortened_key)
    english_keys = {key.lower(): key for key in pal_names["en"]}
    resolved_key = next(
        (
            english_keys[key.lower()]
            for key in candidate_keys
            if pal_names["en"].get(english_keys.get(key.lower(), ""))
        ),
        name_key,
    )
    result = {
        language: pal_names[language].get(resolved_key, "")
        for language in LANGUAGE_TOKENS
    }
    english = result["en"] or record.internal_name
    for language in LANGUAGE_TOKENS:
        result[language] = result[language] or english
    return result


def build_pal_catalog(
    records: dict[str, PalRecord],
    pal_names: dict[str, dict[str, str]],
    learnsets: dict[str, dict[str, int]],
) -> dict[str, dict[str, Any]]:
    if set(learnsets) - set(records):
        raise ValueError("Learnsets must be matched to the Pal parameter table first")
    result: dict[str, dict[str, Any]] = {}
    for record in records.values():
        values = record.values
        elements = [
            ELEMENTS[element]
            for element in (values.get("ElementType1"), values.get("ElementType2"))
            if element not in (None, 0)
        ]
        if len(elements) != len(set(elements)):
            raise ValueError(f"Invalid elements for Pal {record.internal_name}: {elements}")
        suffix = values.get("ZukanIndexSuffix") or ""
        result[record.internal_name] = {
            "InternalName": record.internal_name,
            "Elements": elements,
            "Attacks": learnsets.get(record.internal_name, {}),
            "Stats": {
                "HP": int(values.get("Hp") or 0),
                "ATK": int(values.get("ShotAttack") or 0),
                "DEF": int(values.get("Defense") or 0),
                "MELEE": int(values.get("MeleeAttack") or 0),
                "CRAFTSPEED": int(values.get("CraftSpeed") or 0),
                "FOOD": int(values.get("MaxFullStomach") or 0),
            },
            "I18n": _pal_i18n(record, pal_names),
            "SortingKey": {
                "paldeck": f"{int(values.get('ZukanIndex') or 0)}{suffix}"
            },
            "Suitabilities": {
                f"EPalWorkSuitability::{name}": int(
                    values.get(f"WorkSuitability_{name}") or 0
                )
                for name in SUITABILITIES
            },
        }
    return result


def decode_human_icon_ids(
    asset: dict[str, Any],
    *,
    expected_count: int = EXPECTED_HUMAN_ICON_ROWS,
) -> set[str]:
    exports = asset.get("Exports")
    if not isinstance(exports, list) or len(exports) != 1:
        raise ValueError("Human icon asset must have exactly one export")
    export = exports[0]
    if export.get("ObjectName") != "DT_PalBossNPCIcon_Common":
        raise ValueError("Expected DT_PalBossNPCIcon_Common human icon export")
    rows = export.get("Table", {}).get("Data")
    if not isinstance(rows, list) or len(rows) != expected_count:
        raise ValueError(
            f"Expected {expected_count} official human icon rows, got "
            f"{len(rows) if isinstance(rows, list) else 'no table'}"
        )
    result = {row.get("Name") for row in rows if isinstance(row, dict)}
    if None in result or len(result) != expected_count:
        raise ValueError("Human icon table contains missing or duplicate IDs")
    return {str(value) for value in result}


def _human_i18n(
    record: PalRecord,
    human_names: dict[str, dict[str, str]],
    existing: dict[str, Any],
) -> dict[str, str]:
    name_key = record.values.get("OverrideNameTextID")
    old_i18n = existing.get("I18n", {})
    result: dict[str, str] = {}
    for language in LANGUAGE_TOKENS:
        localized = (human_names[language].get(name_key, "") or "").strip()
        if localized in PLACEHOLDER_TEXT:
            localized = str(old_i18n.get(language) or "")
        result[language] = localized
    english = result["en"] or record.internal_name
    for language in LANGUAGE_TOKENS:
        result[language] = result[language] or english
    return result


def build_human_catalog(
    existing: dict[str, dict[str, Any]],
    records: dict[str, PalRecord],
    human_names: dict[str, dict[str, str]],
    icon_ids: set[str],
) -> dict[str, dict[str, Any]]:
    unknown_icons = icon_ids - set(records)
    if unknown_icons:
        raise ValueError(
            f"Human icon table references unknown IDs: {sorted(unknown_icons)}"
        )
    result: dict[str, dict[str, Any]] = {}
    for record in records.values():
        values = record.values
        result[record.internal_name] = {
            "InternalName": record.internal_name,
            "Elements": [],
            "Attacks": {"EPalWazaID::Human_Punch": 1},
            "Human": True,
            "I18n": _human_i18n(
                record,
                human_names,
                existing.get(record.internal_name, {}),
            ),
            "Stats": {
                "HP": int(values.get("Hp") or 0),
                "ATK": int(values.get("ShotAttack") or 0),
                "DEF": int(values.get("Defense") or 0),
                "MELEE": int(values.get("MeleeAttack") or 0),
                "CRAFTSPEED": int(values.get("CraftSpeed") or 0),
                "FOOD": int(values.get("MaxFullStomach") or 0),
            },
            "SortingKey": {"paldeck": ""},
            "Suitabilities": {
                f"EPalWorkSuitability::{name}": int(
                    values.get(f"WorkSuitability_{name}") or 0
                )
                for name in SUITABILITIES
            },
            "HasIcon": record.internal_name in icon_ids,
        }
    return result


def _raw_data_table(
    asset: dict[str, Any],
    *,
    object_name: str,
    row_struct_name: str,
    expected_count: int,
) -> tuple[list[str], bytes]:
    name_map = asset.get("NameMap")
    if not isinstance(name_map, list) or not all(
        isinstance(value, str) for value in name_map
    ):
        raise ValueError(f"{object_name} has an invalid NameMap")
    data = _asset_payload(asset, object_name)
    struct_imports = [
        -(index + 1)
        for index, value in enumerate(asset.get("Imports") or [])
        if value.get("ObjectName") == row_struct_name
    ]
    if len(struct_imports) != 1:
        raise ValueError(f"Expected one {row_struct_name} import")
    if (
        data[:2] != b"\x00\x03"
        or struct.unpack_from("<i", data, 2)[0] != struct_imports[0]
        or struct.unpack_from("<i", data, 6)[0] != 0
        or struct.unpack_from("<i", data, 10)[0] != expected_count
    ):
        raise ValueError(f"{object_name} outer schema does not match build {BUILD}")
    return name_map, data


def decode_exp_asset(
    asset: dict[str, Any],
    *,
    expected_count: int = EXPECTED_EXP_ROWS,
) -> dict[str, dict[str, int]]:
    name_map, data = _raw_data_table(
        asset,
        object_name="DT_PalExpTable",
        row_struct_name="PalExpDatabaseRaw",
        expected_count=expected_count,
    )
    offset = 14
    result: dict[str, dict[str, int]] = {}
    for _ in range(expected_count):
        level, offset = _read_fname(data, offset, name_map)
        offset, state = parse_unversioned_header(data, offset)
        if set(state) != set(range(len(EXP_FIELDS))):
            raise ValueError(f"Unexpected experience schema for level {level}")
        row: dict[str, int] = {}
        for property_index, field in enumerate(EXP_FIELDS):
            if state[property_index]:
                row[field] = struct.unpack_from("<q", data, offset)[0]
                offset += 8
            else:
                row[field] = 0
        if level in result or any(value < 0 for value in row.values()):
            raise ValueError(f"Invalid experience row for level {level}")
        result[level] = row
    expected_levels = {str(level) for level in range(1, expected_count + 1)}
    if set(result) != expected_levels or offset != len(data):
        raise ValueError("Experience table levels or trailing data are invalid")
    return result


def decode_friendship_asset(
    asset: dict[str, Any],
    *,
    expected_count: int = EXPECTED_FRIENDSHIP_ROWS,
) -> dict[str, dict[str, int]]:
    name_map, data = _raw_data_table(
        asset,
        object_name="DT_FriendshipRankTable",
        row_struct_name="PalFriendshipRankDataRow",
        expected_count=expected_count,
    )
    offset = 14
    by_rank: dict[int, dict[str, int]] = {}
    for _ in range(expected_count):
        _, offset = _read_fname(data, offset, name_map)
        offset, state = parse_unversioned_header(data, offset)
        if set(state) != {0, 1}:
            raise ValueError("Unexpected friendship rank schema")
        values: list[int] = []
        for property_index in range(2):
            if state[property_index]:
                values.append(struct.unpack_from("<i", data, offset)[0])
                offset += 4
            else:
                values.append(0)
        rank, required_point = values
        if rank in by_rank:
            raise ValueError(f"Duplicate friendship rank {rank}")
        by_rank[rank] = {"required_point": required_point}
    if set(by_rank) != set(range(-3, 11)) or offset != len(data):
        raise ValueError("Friendship ranks or trailing data are invalid")
    return {str(rank): by_rank[rank] for rank in sorted(by_rank)}


def match_learnsets_to_pals(
    records: dict[str, PalRecord],
    learnsets: dict[str, dict[str, int]],
) -> tuple[dict[str, dict[str, int]], list[str]]:
    """Match harmless historical casing differences across the two game tables."""
    casefolded_ids = {internal_name.casefold(): internal_name for internal_name in records}
    matched: dict[str, dict[str, int]] = {}
    unmatched: list[str] = []
    for source_id, attacks in learnsets.items():
        target_id = casefolded_ids.get(source_id.casefold())
        if target_id is None:
            unmatched.append(source_id)
            continue
        if target_id in matched:
            raise ValueError(f"Multiple Waza master IDs resolve to {target_id}")
        matched[target_id] = attacks
    return matched, sorted(unmatched)


def _diff_summary(
    before: dict[str, Any], after: dict[str, Any]
) -> dict[str, Any]:
    before_keys = set(before)
    after_keys = set(after)
    changed = sorted(
        key for key in before_keys & after_keys if before[key] != after[key]
    )
    return {
        "before": len(before),
        "after": len(after),
        "added": len(after_keys - before_keys),
        "removed": len(before_keys - after_keys),
        "changed": len(changed),
        "added_ids": sorted(after_keys - before_keys),
        "removed_ids": sorted(before_keys - after_keys),
    }


def _read_asset(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Synchronize Pal, human, skill, and progression data from Palworld 1.0 "
            "Build 24088745 game-resource tables."
        )
    )
    parser.add_argument("localization_export_root", type=Path)
    parser.add_argument("passive_asset", type=Path)
    parser.add_argument("pal_parameter_asset", type=Path)
    parser.add_argument("waza_master_asset", type=Path)
    parser.add_argument("waza_data_asset", type=Path)
    parser.add_argument("mapping", type=Path)
    parser.add_argument("game_executable", type=Path)
    parser.add_argument("--human-parameter-asset", type=Path)
    parser.add_argument("--human-icon-asset", type=Path)
    parser.add_argument("--exp-asset", type=Path)
    parser.add_argument("--friendship-asset", type=Path)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report drift and return a non-zero status without writing files.",
    )
    args = parser.parse_args()
    runtime_inputs = (
        args.human_parameter_asset,
        args.human_icon_asset,
        args.exp_asset,
        args.friendship_asset,
    )
    if any(runtime_inputs) and not all(runtime_inputs):
        parser.error(
            "--human-parameter-asset, --human-icon-asset, --exp-asset, and "
            "--friendship-asset must be provided together"
        )

    passive_records = decode_passive_asset(_read_asset(args.passive_asset))
    pal_records = decode_pal_parameter_asset(
        _read_asset(args.pal_parameter_asset), args.mapping
    )
    waza_enum = decode_waza_enum(args.game_executable)
    learnsets = decode_waza_master_asset(
        _read_asset(args.waza_master_asset), waza_enum
    )
    waza_records = decode_waza_data_asset(
        _read_asset(args.waza_data_asset), waza_enum
    )
    matched_learnsets, unmatched_learnset_ids = match_learnsets_to_pals(
        pal_records, learnsets
    )
    json_root = args.localization_export_root / "json"
    skill_names, skill_descriptions, pal_names, references = _localization_context(
        json_root
    )
    passive_path = args.data_root / "pal_passives.json"
    pal_path = args.data_root / "pal_data.json"
    attack_path = args.data_root / "pal_attacks.json"
    item_path = args.data_root / "item_data.json"
    old_passives = json.loads(passive_path.read_text(encoding="utf-8"))
    old_pals = json.loads(pal_path.read_text(encoding="utf-8"))
    old_attacks = json.loads(attack_path.read_text(encoding="utf-8"))
    items = json.loads(item_path.read_text(encoding="utf-8"))
    new_passives = build_passive_catalog(
        old_passives,
        passive_records,
        skill_names,
        skill_descriptions,
        references,
    )
    new_pals = build_pal_catalog(pal_records, pal_names, matched_learnsets)
    new_attacks = build_attack_catalog(
        old_attacks,
        waza_records,
        skill_fruits_from_item_catalog(items),
        skill_names,
        skill_descriptions,
        references,
    )
    catalogs: list[tuple[Path, dict[str, Any], dict[str, Any]]] = [
        (passive_path, old_passives, new_passives),
        (pal_path, old_pals, new_pals),
        (attack_path, old_attacks, new_attacks),
    ]
    used_attacks = {
        attack
        for pal in new_pals.values()
        for attack in pal["Attacks"]
    }
    missing_attacks = sorted(used_attacks - set(new_attacks))
    if missing_attacks:
        raise ValueError(
            f"Official learnsets reference attacks absent from Waza data: {missing_attacks}"
        )
    report = {
        "build": BUILD,
        "source": {
            "passives": "DT_PassiveSkill_Main_Common",
            "pals": "DT_PalMonsterParameter_Common",
            "learnsets": "DT_WazaMasterLevel_Common + EPalWazaID",
            "attacks": (
                "DT_WazaDataTable_Common + EPalWazaID + verified "
                "DT_ItemDataTable_Common SkillCard rows"
            ),
        },
        "learnsets": {
            "source_pals": len(learnsets),
            "matched_pals": len(matched_learnsets),
            "unmatched_ids": unmatched_learnset_ids,
        },
        "passives": _diff_summary(old_passives, new_passives),
        "pals": _diff_summary(old_pals, new_pals),
        "attacks": _diff_summary(old_attacks, new_attacks),
    }

    if all(runtime_inputs):
        human_path = args.data_root / "human_data.json"
        exp_path = args.data_root / "pal_exp_table.json"
        friendship_path = args.data_root / "pal_friendship.json"
        old_humans = json.loads(human_path.read_text(encoding="utf-8"))
        old_exp = json.loads(exp_path.read_text(encoding="utf-8"))
        old_friendship = json.loads(friendship_path.read_text(encoding="utf-8"))
        human_records = decode_human_parameter_asset(
            _read_asset(args.human_parameter_asset), args.mapping
        )
        human_names = {
            language: load_table(json_root, language, "DT_HumanNameText_Common")
            for language in LANGUAGE_TOKENS
        }
        human_icons = decode_human_icon_ids(_read_asset(args.human_icon_asset))
        new_humans = build_human_catalog(
            old_humans,
            human_records,
            human_names,
            human_icons,
        )
        if set(new_humans) & set(new_pals):
            raise ValueError("Human and Pal catalogs contain colliding character IDs")
        new_exp = decode_exp_asset(_read_asset(args.exp_asset))
        new_friendship = decode_friendship_asset(
            _read_asset(args.friendship_asset)
        )
        catalogs.extend(
            [
                (human_path, old_humans, new_humans),
                (exp_path, old_exp, new_exp),
                (friendship_path, old_friendship, new_friendship),
            ]
        )
        report["source"].update(
            {
                "humans": "DT_PalHumanParameter_Common + DT_HumanNameText_Common",
                "human_icons": "DT_PalBossNPCIcon_Common",
                "experience": "DT_PalExpTable",
                "friendship": "DT_FriendshipRankTable",
            }
        )
        report.update(
            {
                "humans": _diff_summary(old_humans, new_humans),
                "experience": _diff_summary(old_exp, new_exp),
                "friendship": _diff_summary(old_friendship, new_friendship),
            }
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))

    has_drift = any(before != after for _, before, after in catalogs)
    if args.check:
        return 1 if has_drift else 0
    for path, _, data in catalogs:
        write_json(path, data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
