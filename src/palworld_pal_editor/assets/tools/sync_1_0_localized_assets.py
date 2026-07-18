from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import struct
from typing import Any

try:
    from sync_1_0_item_rules import (
        EXPECTED_ITEM_COUNT,
        _all_hits,
        _read_table_prefix,
        decode_base64,
    )
except ImportError:  # pragma: no cover - package-style invocation
    from .sync_1_0_item_rules import (
        EXPECTED_ITEM_COUNT,
        _all_hits,
        _read_table_prefix,
        decode_base64,
    )


LANGUAGE_TOKENS = {
    "en": "_Pal_Content_L10N_en_",
    "fr": "_Pal_Content_L10N_fr_",
    "ja": "_Pal_Content_Pal_DataTable_Text_",
    "zh-CN": "_Pal_Content_L10N_zh-Hans_",
}

# These are passive IDs that the game exposes as Pal traits but which do not
# share the historical PAL_* naming convention. The existing editable rows
# are also retained only when the current export still contains them.
PAL_PASSIVE_SOURCE_PREFIXES = ("PAL_", "WorldTree_")


def load_table(json_root: Path, language: str, table_name: str) -> dict[str, str]:
    token = LANGUAGE_TOKENS[language]
    matches = [
        path
        for path in json_root.glob(f"*{table_name}.uasset.json")
        if token in path.name
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected one {language} {table_name} export, found {len(matches)}"
        )

    asset = json.loads(matches[0].read_text(encoding="utf-8"))
    rows = asset["Exports"][0]["Table"]["Data"]
    result: dict[str, str] = {}
    for row in rows:
        text_property = next(
            value for value in row["Value"] if value.get("Name") == "TextData"
        )
        result[row["Name"]] = text_property.get("CultureInvariantString") or ""
    return result


def load_item_icons(json_root: Path) -> dict[str, dict[str, str]]:
    matches = list(
        json_root.glob("*Content_Pal_DataTable_Item_DT_ItemIconDataTable_Common.uasset.json")
    )
    if len(matches) != 1:
        raise RuntimeError(f"Expected one item icon export, found {len(matches)}")

    asset = json.loads(matches[0].read_text(encoding="utf-8"))
    rows = asset["Exports"][0]["Table"]["Data"]
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        icon_property = next(
            (value for value in row["Value"] if value.get("Name") == "Icon"), None
        )
        if not icon_property:
            continue
        asset_path = icon_property["Value"]["AssetPath"]
        result[row["Name"]] = {
            "Icon": asset_path["AssetName"],
            "SourcePath": asset_path["PackageName"],
        }
    return result


def load_item_localization_bindings(
    json_root: Path,
    catalog: dict[str, dict[str, Any]],
) -> dict[str, tuple[str | None, str | None, str]]:
    """Map every editor item ID to its official v1.0 text overrides."""
    matches = list(
        json_root.glob("*Content_Pal_DataTable_Item_DT_ItemDataTable_Common.uasset.json")
    )
    if len(matches) != 1:
        raise RuntimeError(f"Expected one item data-table export, found {len(matches)}")
    asset = json.loads(matches[0].read_text(encoding="utf-8"))
    name_map = asset.get("NameMap")
    exports = asset.get("Exports")
    if not isinstance(name_map, list) or not isinstance(exports, list):
        raise ValueError("Item data-table export is incomplete")
    if len(exports) != 1 or exports[0].get("ObjectName") != "DT_ItemDataTable_Common":
        raise ValueError("Expected the DT_ItemDataTable_Common export")
    data = decode_base64(exports[0].get("Data"), field="item data-table Data")
    if (
        data[:2] != b"\x00\x03"
        or struct.unpack_from("<i", data, 6)[0] != 0
        or struct.unpack_from("<i", data, 10)[0] != EXPECTED_ITEM_COUNT
        or len(catalog) != EXPECTED_ITEM_COUNT
    ):
        raise ValueError("Item localization table does not match build 24088745")

    name_indices = {name: index for index, name in enumerate(name_map)}
    result: dict[str, tuple[str | None, str | None, str]] = {}
    row_positions: set[int] = set()
    for static_id, row in catalog.items():
        rule = row.get("Rule")
        if not isinstance(rule, dict) or rule.get("Status") != "verified":
            raise ValueError(f"Item {static_id} has no verified v1.0 rule metadata")
        if static_id in name_indices:
            name_index, name_number = name_indices[static_id], 0
        else:
            numbered_name = re.fullmatch(r"(.+)_(\d+)", static_id)
            if numbered_name is None or numbered_name.group(1) not in name_indices:
                raise ValueError(f"Item {static_id} is missing from the official NameMap")
            name_index = name_indices[numbered_name.group(1)]
            name_number = int(numbered_name.group(2)) + 1

        pattern = struct.pack("<ii", name_index, name_number)
        candidates: list[tuple[int, str | None, str | None, str]] = []
        for position in _all_hits(data, pattern, 14):
            try:
                _, values = _read_table_prefix(data, position, name_map)
                comparisons = {
                    3: rule["GameTypeA"],
                    4: rule["GameTypeB"],
                    6: rule["Rarity"],
                    7: rule["MaxStack"],
                    15: rule["OfficialLegal"],
                }
                if any(
                    int(values[index] or 0) != int(expected)
                    for index, expected in comparisons.items()
                ):
                    continue
                name_key = values[0]
                description_key = values[1]
                item_base_name = values[2]
                if name_key is not None and not str(name_key).startswith("ITEM_NAME_"):
                    continue
                if description_key is not None and not str(description_key).startswith(
                    "ITEM_DESC_"
                ):
                    continue
                if not isinstance(item_base_name, str) or not item_base_name:
                    continue
                candidates.append(
                    (position, name_key, description_key, item_base_name)
                )
            except (IndexError, KeyError, TypeError, ValueError, struct.error):
                continue
        if len(candidates) != 1:
            raise ValueError(
                f"Expected one localization row for {static_id}, found {len(candidates)}"
            )
        position, name_key, description_key, item_base_name = candidates[0]
        if position in row_positions:
            raise ValueError("Two item IDs resolved to the same localization row")
        row_positions.add(position)
        result[static_id] = (name_key, description_key, item_base_name)
    if len(row_positions) != EXPECTED_ITEM_COUNT or min(row_positions) != 14:
        raise ValueError("Item localization mapping does not cover every official row")
    return result


def replace_reference_tags(
    text: str,
    references: dict[str, dict[str, str]],
) -> str:
    def replacement(match: re.Match[str]) -> str:
        reference_type, reference_id = match.group(1), match.group(2)
        return references.get(reference_type, {}).get(reference_id, reference_id)

    text = re.sub(
        r"<(uiCommon|itemName|mapObjectName|MapObjectName|characterName|activeSkillName)\s+"
        r"id=\|([^|]+)\|(?:\s+style=\|[^|]*\|)?\s*/>",
        replacement,
        text,
    )
    text = re.sub(r"<img\b[^>]*/>", "", text)
    text = re.sub(r"</?[^>]+>", "", text)
    return re.sub(r"[ \t]+", " ", text.replace("\r\n", "\n")).strip()


def localized_rows(
    names: dict[str, dict[str, str]],
    descriptions: dict[str, dict[str, str]],
    name_key: str,
    description_keys: tuple[str, ...],
    references: dict[str, dict[str, dict[str, str]]],
) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for language in LANGUAGE_TOKENS:
        name = names[language].get(name_key, "")
        description = next(
            (
                descriptions[language].get(key, "")
                for key in description_keys
                if descriptions[language].get(key)
            ),
            "",
        )
        language_references = {
            reference_type: values[language]
            for reference_type, values in references.items()
        }
        result[language] = {
            "Name": replace_reference_tags(name, language_references),
            "Description": replace_reference_tags(
                description, language_references
            ),
        }
    return result


def localized_item_rows(
    internal_name: str,
    existing: dict[str, Any],
    binding: tuple[str | None, str | None, str],
    names: dict[str, dict[str, str]],
    descriptions: dict[str, dict[str, str]],
    references: dict[str, dict[str, dict[str, str]]],
) -> dict[str, dict[str, str]]:
    override_name_key, override_description_key, item_base_name = binding
    name_keys = tuple(
        dict.fromkeys(
            key
            for key in (
                override_name_key,
                f"ITEM_NAME_{internal_name}",
                f"ITEM_NAME_{item_base_name}",
            )
            if key
        )
    )
    description_keys = tuple(
        dict.fromkeys(
            key
            for key in (
                override_description_key,
                f"ITEM_DESC_{internal_name}",
                f"ITEM_DESC_{item_base_name}",
            )
            if key
        )
    )
    old_i18n = existing.get("I18n", {})
    result: dict[str, dict[str, str]] = {}
    for language in LANGUAGE_TOKENS:
        old_localized = old_i18n.get(language, {})
        name = next(
            (names[language][key] for key in name_keys if names[language].get(key)),
            "",
        )
        description = next(
            (
                descriptions[language][key]
                for key in description_keys
                if descriptions[language].get(key)
            ),
            "",
        )
        language_references = {
            reference_type: values[language]
            for reference_type, values in references.items()
        }
        result[language] = {
            "Name": replace_reference_tags(
                name or old_localized.get("Name", "") or internal_name,
                language_references,
            ),
            "Description": replace_reference_tags(
                description or old_localized.get("Description", ""),
                language_references,
            ),
        }
    fill_missing_with_english(result)
    return result


def fill_missing_with_english(i18n: dict[str, dict[str, str]]) -> None:
    english = i18n["en"]
    for language in LANGUAGE_TOKENS:
        localized = i18n.setdefault(language, {})
        localized["Name"] = localized.get("Name") or english["Name"]
        localized["Description"] = (
            localized.get("Description") or english["Description"]
        )


def passive_ids_from_skill_names(skill_names: dict[str, str]) -> set[str]:
    """Return every passive ID present in the current game localization export."""
    return {
        key.removeprefix("PASSIVE_")
        for key in skill_names
        if key.startswith("PASSIVE_")
    }


def rebuild_pal_passives(
    existing: dict[str, dict[str, Any]],
    localized: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Rebuild editable Pal traits from the current export, dropping stale IDs."""
    source_ids = set(localized)
    editable_ids = {
        internal_name
        for internal_name in source_ids
        if internal_name in existing
        or internal_name.startswith(PAL_PASSIVE_SOURCE_PREFIXES)
    }

    result: dict[str, dict[str, Any]] = {}
    for internal_name in sorted(editable_ids):
        old = existing.get(internal_name, {})
        result[internal_name] = {
            "InternalName": internal_name,
            "Rating": old.get("Rating", 0),
            "I18n": localized[internal_name]["I18n"],
            "Buff": old.get(
                "Buff",
                {
                    "b_Attack": 0.0,
                    "b_Defense": 0.0,
                    "b_CraftSpeed": 0.0,
                    "b_MoveSpeed": 0.0,
                },
            ),
        }
    return result


def write_json(path: Path, data: Any) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync Build 24088745 localized skill and item assets."
    )
    parser.add_argument("export_root", type=Path)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--items-only",
        action="store_true",
        help="Only synchronize item_data.json; leave skill files unchanged.",
    )
    mode.add_argument(
        "--skill-i18n-only",
        action="store_true",
        help="Only synchronize skill_i18n.json; leave editable catalogs unchanged.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report item-localization drift without writing files.",
    )
    args = parser.parse_args()

    json_root = args.export_root / "json"
    skill_names = {
        language: load_table(json_root, language, "DT_SkillNameText_Common")
        for language in LANGUAGE_TOKENS
    }
    skill_descriptions = {
        language: load_table(json_root, language, "DT_SkillDescText_Common")
        for language in LANGUAGE_TOKENS
    }
    item_names_raw = {
        language: load_table(json_root, language, "DT_ItemNameText_Common")
        for language in LANGUAGE_TOKENS
    }
    item_descriptions = {
        language: load_table(json_root, language, "DT_ItemDescriptionText_Common")
        for language in LANGUAGE_TOKENS
    }
    ui_common = {
        language: load_table(json_root, language, "DT_UI_Common_Text_Common")
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
            for key, value in load_table(
                json_root, language, "DT_PalNameText_Common"
            ).items()
        }
        for language in LANGUAGE_TOKENS
    }
    item_icons = load_item_icons(json_root)

    item_names = {
        language: {
            key.removeprefix("ITEM_NAME_"): value
            for key, value in values.items()
        }
        for language, values in item_names_raw.items()
    }
    active_skill_names = {
        language: {
            key.removeprefix("ACTION_SKILL_"): value
            for key, value in values.items()
            if key.startswith("ACTION_SKILL_")
        }
        for language, values in skill_names.items()
    }
    references = {
        "uiCommon": ui_common,
        "itemName": item_names,
        "mapObjectName": map_object_names,
        "MapObjectName": map_object_names,
        "characterName": character_names,
        "activeSkillName": active_skill_names,
    }

    passive_ids = sorted(passive_ids_from_skill_names(skill_names["en"]))
    attack_ids = sorted(
        key.removeprefix("ACTION_SKILL_")
        for key in skill_names["en"]
        if key.startswith("ACTION_SKILL_")
    )

    skill_i18n = {
        "Build": 24088745,
        "Passives": {},
        "Attacks": {},
    }
    for internal_name in passive_ids:
        i18n = localized_rows(
            skill_names,
            skill_descriptions,
            f"PASSIVE_{internal_name}",
            (f"PASSIVE_PAL_{internal_name}", f"PASSIVE_{internal_name}"),
            references,
        )
        fill_missing_with_english(i18n)
        skill_i18n["Passives"][internal_name] = {
            "InternalName": internal_name,
            "I18n": i18n,
        }
    for attack_id in attack_ids:
        internal_name = f"EPalWazaID::{attack_id}"
        i18n = localized_rows(
            skill_names,
            skill_descriptions,
            f"ACTION_SKILL_{attack_id}",
            (f"ACTION_SKILL_{attack_id}",),
            references,
        )
        fill_missing_with_english(i18n)
        skill_i18n["Attacks"][internal_name] = {
            "InternalName": internal_name,
            "I18n": i18n,
        }

    passive_data_path = args.data_root / "pal_passives.json"
    existing_passive_data = json.loads(passive_data_path.read_text(encoding="utf-8"))
    passive_data = rebuild_pal_passives(existing_passive_data, skill_i18n["Passives"])

    attack_data_path = args.data_root / "pal_attacks.json"
    attack_data = json.loads(attack_data_path.read_text(encoding="utf-8"))
    for internal_name, row in attack_data.items():
        official = skill_i18n["Attacks"].get(internal_name)
        if official:
            for language, localized in official["I18n"].items():
                target = row["I18n"].setdefault(language, {})
                target["Name"] = localized["Name"]
                if localized["Description"]:
                    target["Description"] = localized["Description"]
        fill_missing_with_english(row["I18n"])

    item_data_path = args.data_root / "item_data.json"
    existing_item_data = json.loads(item_data_path.read_text(encoding="utf-8"))
    item_bindings = load_item_localization_bindings(json_root, existing_item_data)
    item_data: dict[str, dict[str, Any]] = {}
    for internal_name in sorted(existing_item_data):
        existing = existing_item_data[internal_name]
        i18n = localized_item_rows(
            internal_name,
            existing,
            item_bindings[internal_name],
            item_names_raw,
            item_descriptions,
            references,
        )
        _, _, item_base_name = item_bindings[internal_name]
        icon = item_icons.get(internal_name) or item_icons.get(item_base_name) or {}
        item_data[internal_name] = {
            **existing,
            "InternalName": internal_name,
            "Icon": existing.get("Icon") or icon.get("Icon"),
            "I18n": i18n,
        }

    item_localization_changes = sum(
        existing_item_data[item_id].get("I18n") != row["I18n"]
        for item_id, row in item_data.items()
    )
    if not args.check:
        if args.skill_i18n_only:
            write_json(args.data_root / "skill_i18n.json", skill_i18n)
        else:
            if not args.items_only:
                write_json(args.data_root / "skill_i18n.json", skill_i18n)
                write_json(passive_data_path, passive_data)
                write_json(attack_data_path, attack_data)
            write_json(item_data_path, item_data)
    icon_names = sorted(
        {item["Icon"] for item in item_data.values() if item["Icon"]}
    )
    (args.export_root / "item_icon_names.txt").write_text(
        "\n".join(icon_names) + "\n", encoding="utf-8"
    )

    print(
        json.dumps(
            {
                "passive_localization_rows": len(skill_i18n["Passives"]),
                "active_localization_rows": len(skill_i18n["Attacks"]),
                "validated_passives": len(passive_data),
                "validated_attacks": len(attack_data),
                "items": len(item_data),
                "items_with_icons": len(icon_names),
                "item_localization_changes": item_localization_changes,
                "items_with_localized_names": sum(
                    row["I18n"]["zh-CN"]["Name"] != item_id
                    for item_id, row in item_data.items()
                ),
                "items_with_descriptions": sum(
                    bool(row["I18n"]["zh-CN"]["Description"])
                    for row in item_data.values()
                ),
            },
            ensure_ascii=False,
        )
    )
    return 1 if args.check and item_localization_changes else 0


if __name__ == "__main__":
    raise SystemExit(main())
