from __future__ import annotations

import argparse
import base64
from collections import Counter, deque
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
from typing import Any, Iterable


LANGUAGE_MARKERS = {
    "en": "_Pal_Content_L10N_en_",
    "fr": "_Pal_Content_L10N_fr_",
    "ko": "_Pal_Content_L10N_ko_",
    "zh-CN": "_Pal_Content_L10N_zh-Hans_",
}
LANGUAGES = ("en", "fr", "ja", "ko", "zh-CN")
QUEST_ROOT = "/Game/Pal/Blueprint/Quest/"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "data" / "mission_data.json"


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_quest_table(path: Path) -> list[dict[str, Any]]:
    asset = _json(path)
    names = asset["NameMap"]
    raw = base64.b64decode(asset["Exports"][0]["Data"])
    if len(raw) < 14 or raw[:2] != b"\x00\x03":
        raise RuntimeError("DT_PalQuestData uses an unsupported export format")
    row_count = struct.unpack_from("<I", raw, 10)[0]
    offset = 14
    rows: list[dict[str, Any]] = []
    for row_index in range(row_count):
        try:
            name_index, name_number = struct.unpack_from("<ii", raw, offset)
            offset += 8
            mission_id = names[name_index]
            header = raw[offset : offset + 4]
            special_header = header[:2] == b"\x00\x07"
            if header[:3] == b"\x80\x07\x04":
                offset += 4
            elif special_header:
                offset += 3
            else:
                raise RuntimeError(f"unsupported unversioned header {header.hex()}")
            package_index, package_number, class_index, class_number = struct.unpack_from(
                "<iiii", raw, offset
            )
            offset += 16
            subpath_length = struct.unpack_from("<i", raw, offset)[0]
            offset += 4
            if subpath_length != 0:
                raise RuntimeError("non-empty quest asset subpaths are unsupported")
            if special_header:
                offset += 1
            if name_number or package_number or class_number:
                raise RuntimeError("numbered FNames are unsupported in DT_PalQuestData")
            rows.append(
                {
                    "internal_name": mission_id,
                    "asset_path": names[package_index],
                    "asset_class": names[class_index],
                }
            )
        except (IndexError, struct.error, RuntimeError) as error:
            raise RuntimeError(
                f"Unable to decode DT_PalQuestData row {row_index}"
            ) from error
    if offset != len(raw):
        raise RuntimeError(
            f"DT_PalQuestData decode drift: consumed {offset} of {len(raw)} bytes"
        )
    ids = [row["internal_name"] for row in rows]
    if len(ids) != len(set(ids)):
        duplicates = sorted(
            mission_id for mission_id, count in Counter(ids).items() if count > 1
        )
        raise RuntimeError(f"Duplicate mission IDs: {duplicates}")
    return rows


def load_blueprints(directory: Path) -> tuple[dict[str, list[str]], str]:
    packages: dict[str, list[str]] = {}
    hashes: list[str] = []
    for path in sorted(directory.glob("*.uasset.json")):
        asset = _json(path)
        names = asset.get("NameMap")
        if not isinstance(names, list):
            continue
        hashes.append(f"{path.name}:{_sha256(path)}")
        for value in names:
            if not isinstance(value, str) or not value.startswith(QUEST_ROOT):
                continue
            expected_name = (
                value.removeprefix(QUEST_ROOT).replace("/", "_")
                + ".uasset.json"
            )
            if expected_name == path.name:
                if value in packages:
                    raise RuntimeError(f"Duplicate Blueprint package export: {value}")
                packages[value] = [str(item) for item in names if isinstance(item, str)]
    manifest_hash = hashlib.sha256("\n".join(hashes).encode("utf-8")).hexdigest()
    return packages, manifest_hash


def _load_text_table(path: Path) -> dict[str, str]:
    asset = _json(path)
    rows = asset["Exports"][0]["Table"]["Data"]
    result: dict[str, str] = {}
    for row in rows:
        text_property = next(
            value for value in row["Value"] if value.get("Name") == "TextData"
        )
        result[row["Name"]] = text_property.get("CultureInvariantString") or ""
    return result


def load_localizations(directory: Path) -> tuple[dict[str, dict[str, str]], str]:
    matches = sorted(directory.glob("*DT_UI_Common_Text_Common.uasset.json"))
    paths: dict[str, Path] = {}
    for path in matches:
        language = next(
            (
                locale
                for locale, marker in LANGUAGE_MARKERS.items()
                if marker in path.name
            ),
            None,
        )
        if language is None and "_Pal_Content_Pal_DataTable_Text_" in path.name:
            language = "ja"
        if language is None:
            continue
        if language in paths:
            raise RuntimeError(f"Multiple UI text tables found for {language}")
        paths[language] = path
    missing = [language for language in LANGUAGES if language not in paths]
    if missing:
        raise RuntimeError(f"Missing localized UI text tables: {missing}")
    data = {language: _load_text_table(paths[language]) for language in LANGUAGES}
    manifest = hashlib.sha256(
        "\n".join(
            f"{language}:{paths[language].name}:{_sha256(paths[language])}"
            for language in LANGUAGES
        ).encode("utf-8")
    ).hexdigest()
    return data, manifest


def _mission_type(mission_id: str) -> str:
    if mission_id.startswith("Main_"):
        return "main"
    if mission_id.startswith("Sub_"):
        return "sub"
    return "hidden"


def _key_kind(value: str) -> str | None:
    folded = value.casefold()
    if not folded.startswith("quest_"):
        return None
    if "_title_" in folded or "_questname_" in folded:
        return "title"
    if "_desc_" in folded:
        return "description"
    if "_objective_" in folded or "_questobject_" in folded:
        return "objective"
    return None


def _tokens(value: str) -> tuple[str, ...]:
    expanded = re.sub(r"([a-z])([A-Z])", r"\1_\2", value)
    expanded = re.sub(r"([A-Za-z])(\d)", r"\1_\2", expanded)
    expanded = re.sub(r"(\d)([A-Za-z])", r"\1_\2", expanded)
    ignored = {
        "quest",
        "main",
        "sub",
        "title",
        "questname",
        "desc",
        "inprogress",
        "objective",
        "questobject",
        "bp",
        "palquest",
        "data",
    }
    return tuple(
        token
        for token in re.split(r"[^a-z0-9]+", expanded.casefold())
        if token and token not in ignored
    )


def _match_score(mission_id: str, key: str) -> tuple[float, float, int]:
    mission_tokens = _tokens(mission_id)
    key_tokens = _tokens(key)
    mission_set = set(mission_tokens)
    key_set = set(key_tokens)
    union = mission_set | key_set
    jaccard = len(mission_set & key_set) / len(union) if union else 0.0
    sequence = SequenceMatcher(None, "".join(mission_tokens), "".join(key_tokens)).ratio()
    return (jaccard, sequence, -abs(len(mission_tokens) - len(key_tokens)))


def _choose_best(mission_id: str, candidates: Iterable[str]) -> str | None:
    values = list(dict.fromkeys(candidates))
    if not values:
        return None
    return max(values, key=lambda value: (_match_score(mission_id, value), value))


def _ordered_closure(
    root_package: str, packages: dict[str, list[str]]
) -> tuple[list[str], list[str]]:
    queue = deque([root_package])
    seen: set[str] = set()
    keys: list[str] = []
    dependencies: list[str] = []
    while queue:
        package = queue.popleft()
        if package in seen:
            continue
        seen.add(package)
        names = packages.get(package)
        if names is None:
            continue
        dependencies.append(package)
        for value in names:
            if _key_kind(value) and value not in keys:
                keys.append(value)
            if value in packages and value not in seen:
                queue.append(value)
    return keys, dependencies


def build_catalog(
    *,
    quest_table: Path,
    blueprint_dir: Path,
    localized_assets: Path,
    build_id: str,
) -> dict[str, Any]:
    rows = parse_quest_table(quest_table)
    packages, blueprint_hash = load_blueprints(blueprint_dir)
    localizations, localization_hash = load_localizations(localized_assets)
    all_title_keys = [
        key for key in localizations["en"] if _key_kind(key) == "title"
    ]
    missions: dict[str, Any] = {}
    unmatched_assets: list[str] = []
    for row in rows:
        mission_id = row["internal_name"]
        keys, dependencies = _ordered_closure(row["asset_path"], packages)
        if row["asset_path"] not in packages:
            unmatched_assets.append(mission_id)
        title_candidates = [key for key in keys if _key_kind(key) == "title"]
        title_key = _choose_best(mission_id, title_candidates)
        if title_key is None:
            matched = _choose_best(mission_id, all_title_keys)
            if matched is not None and _match_score(mission_id, matched)[0] >= 0.75:
                title_key = matched
        description_key = _choose_best(
            mission_id, (key for key in keys if _key_kind(key) == "description")
        )
        objective_keys = [
            key for key in keys if _key_kind(key) == "objective"
        ]
        translations: dict[str, Any] = {}
        for language in LANGUAGES:
            table = localizations[language]
            direct_title = table.get(title_key, "") if title_key else ""
            fallback_title = (
                direct_title
                or (localizations["en"].get(title_key, "") if title_key else "")
                or mission_id
            )
            direct_description = (
                table.get(description_key, "") if description_key else ""
            )
            fallback_description = direct_description or (
                localizations["en"].get(description_key, "")
                if description_key
                else ""
            )
            objectives = [
                table.get(key, "") or localizations["en"].get(key, "") or key
                for key in objective_keys
            ]
            translations[language] = {
                "title": fallback_title,
                "description": fallback_description,
                "objectives": objectives,
                "title_fallback": not bool(direct_title),
            }
        missions[mission_id] = {
            "internal_name": mission_id,
            "type": _mission_type(mission_id),
            "asset_path": row["asset_path"],
            "asset_class": row["asset_class"],
            "title_key": title_key,
            "description_key": description_key,
            "objective_keys": objective_keys,
            "dependencies": dependencies,
            "restart_capability": {
                "supported": row["asset_path"] in packages,
                "reason": (
                    None
                    if row["asset_path"] in packages
                    else "MISSION_INITIAL_TEMPLATE_UNVERIFIED"
                ),
                "template": (
                    "pal_ordered_quest_stage_zero_v1"
                    if row["asset_path"] in packages
                    else None
                ),
            },
            "i18n": translations,
        }

    language_statistics = {}
    for language in LANGUAGES:
        direct = sum(
            not mission["i18n"][language]["title_fallback"]
            for mission in missions.values()
        )
        language_statistics[language] = {
            "title_localized_count": direct,
            "title_missing_count": len(missions) - direct,
            "title_fallback_count": len(missions) - direct,
        }
    by_type = Counter(mission["type"] for mission in missions.values())
    result = {
        "schema_version": 1,
        "source": {
            "build_id": str(build_id),
            "quest_table": "Pal/Content/Pal/DataTable/Quest/DT_PalQuestData",
            "quest_blueprint_root": "Pal/Content/Pal/Blueprint/Quest",
            "localized_text_table": (
                "Pal/Content/{L10N/<locale>/}Pal/DataTable/Text/"
                "DT_UI_Common_Text_Common"
            ),
            "quest_table_sha256": _sha256(quest_table),
            "blueprint_manifest_sha256": blueprint_hash,
            "localization_manifest_sha256": localization_hash,
            "extraction": "repak plus UAssetAPI JSON export",
        },
        "statistics": {
            "mission_count": len(missions),
            "by_type": {
                "main": by_type["main"],
                "sub": by_type["sub"],
                "hidden": by_type["hidden"],
            },
            "unmatched_asset_count": len(unmatched_assets),
            "unmatched_asset_ids": unmatched_assets,
            "languages": language_statistics,
        },
        "restart_templates": {
            "evidence": {
                "build_id": str(build_id),
                "method": "read-only player-save structure inspection",
                "full_release_stage_zero_records": 50,
                "result": "all observed FullRelease stage-zero records used CanCompleteFlag_0=0",
                "legacy_stage_zero_records": 42,
                "legacy_result": "29 empty maps and 13 DeliveredCount=0 maps; no universal legacy restart template",
            },
            "pal_ordered_quest_stage_zero_v1": {
                "legacy": {
                    "supported": False,
                    "reason": "MISSION_INITIAL_TEMPLATE_UNVERIFIED",
                },
                "full_release": {
                    "supported": True,
                    "block_index": 0,
                    "integer_map": [{"key": "CanCompleteFlag_0", "value": 0}],
                    "string_map": [],
                },
            },
        },
        "missions": missions,
    }
    result["content_sha256"] = hashlib.sha256(
        json.dumps(missions, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return result


def validate_catalog(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missions = data.get("missions")
    if not isinstance(missions, dict):
        return ["missions must be an object"]
    statistics = data.get("statistics") or {}
    if statistics.get("mission_count") != len(missions):
        errors.append("statistics.mission_count does not match missions")
    if len(missions) != len(set(missions)):
        errors.append("mission IDs are not unique")
    actual_by_type = Counter(
        mission.get("type") for mission in missions.values() if isinstance(mission, dict)
    )
    if statistics.get("by_type") != {
        "main": actual_by_type["main"],
        "sub": actual_by_type["sub"],
        "hidden": actual_by_type["hidden"],
    }:
        errors.append("statistics.by_type does not match missions")
    expected_content_hash = hashlib.sha256(
        json.dumps(missions, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    if data.get("content_sha256") != expected_content_hash:
        errors.append("content_sha256 does not match missions")
    for mission_id, mission in missions.items():
        if mission.get("internal_name") != mission_id:
            errors.append(f"internal_name mismatch: {mission_id}")
        if mission.get("type") not in {"main", "sub", "hidden"}:
            errors.append(f"invalid mission type: {mission_id}")
        restart = mission.get("restart_capability")
        if not isinstance(restart, dict) or not isinstance(
            restart.get("supported"), bool
        ):
            errors.append(f"invalid restart capability: {mission_id}")
        translations = mission.get("i18n") or {}
        if set(translations) != set(LANGUAGES):
            errors.append(f"incomplete languages: {mission_id}")
    return errors


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Synchronize the Build-scoped Palworld mission catalog."
    )
    parser.add_argument("--quest-table", type=Path)
    parser.add_argument("--blueprint-dir", type=Path)
    parser.add_argument("--localized-assets", type=Path)
    parser.add_argument("--build-id", default="24088745")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    source_values = (args.quest_table, args.blueprint_dir, args.localized_assets)
    if any(source_values) and not all(source_values):
        print(
            "--quest-table, --blueprint-dir and --localized-assets must be used together",
            file=sys.stderr,
        )
        return 2
    if all(source_values):
        generated = build_catalog(
            quest_table=args.quest_table,
            blueprint_dir=args.blueprint_dir,
            localized_assets=args.localized_assets,
            build_id=args.build_id,
        )
        if args.check:
            if not args.output.exists():
                print(f"Missing generated catalog: {args.output}", file=sys.stderr)
                return 1
            current = _json(args.output)
            if current != generated:
                print("Mission catalog drift detected", file=sys.stderr)
                return 1
        else:
            args.output.write_text(
                json.dumps(generated, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
    else:
        if not args.check:
            print("Source arguments are required unless --check is used", file=sys.stderr)
            return 2
        if not args.output.exists():
            print(f"Missing generated catalog: {args.output}", file=sys.stderr)
            return 1
        errors = validate_catalog(_json(args.output))
        if errors:
            print("\n".join(errors), file=sys.stderr)
            return 1
    data = _json(args.output)
    stats = data["statistics"]
    print(
        json.dumps(
            {
                "build_id": data["source"]["build_id"],
                "mission_count": stats["mission_count"],
                "by_type": stats["by_type"],
                "languages": stats["languages"],
                "status": "ok",
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
