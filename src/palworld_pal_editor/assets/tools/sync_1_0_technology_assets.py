from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from io import BytesIO
import json
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request

from PIL import Image


LANGUAGE_SOURCES = {
    "en": "en",
    "fr": "fr",
    "ja": None,
    "ko": "ko",
    "zh-CN": "zh-Hans",
}
TYPE_LABELS = {
    "en": {"build": "Structures", "item": "Items"},
    "fr": {"build": "Structures", "item": "Objets"},
    "ja": {"build": "建築物", "item": "アイテム"},
    "ko": {"build": "건축물", "item": "아이템"},
    "zh-CN": {"build": "建筑", "item": "道具"},
}
PLACEHOLDER_TEXT = {
    "-",
    "dummy_text",
    "en Text",
    "fr_Text",
    "ja Text",
    "ko Text",
    "ko_Text",
    "zh-hans text",
}
TABLE_NAMES = ("TechnologyName", "ItemName", "MapObjectName")
TECHNOLOGY_PAGE = "https://paldb.cc/en/Technologies"


class TechnologyIconParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.icons: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "div":
            return
        attributes = dict(attrs)
        if "hoverTech" not in (attributes.get("class") or "").split():
            return
        match = re.search(
            r"Technology/([^\s\"'&]+)", attributes.get("data-hover") or ""
        )
        icon_match = re.search(
            r"url\(['\"]?(.*?)['\"]?\)", attributes.get("style") or ""
        )
        if match and icon_match:
            self.icons[match.group(1)] = icon_match.group(1)


def load_data_table(path: Path) -> dict[str, str | None]:
    asset = json.loads(path.read_text(encoding="utf-8"))
    return {
        row["Name"]: row["Value"][0].get("CultureInvariantString")
        for row in asset["Exports"][0]["Table"]["Data"]
    }


def locate_table(directory: Path, table: str, source: str | None) -> Path:
    candidates = []
    for path in directory.glob("*.json"):
        if f"DT_{table}Text_Common" not in path.name:
            continue
        is_localized = "_L10N_" in path.name
        if source is None and not is_localized:
            candidates.append(path)
        elif source is not None and f"_L10N_{source}_" in path.name:
            candidates.append(path)
    if len(candidates) != 1:
        raise ValueError(f"Expected one {table}/{source} table, got {candidates}")
    return candidates[0]


def load_localizations(directory: Path) -> dict[str, dict[str, dict[str, str | None]]]:
    return {
        language: {
            table: load_data_table(locate_table(directory, table, source))
            for table in TABLE_NAMES
        }
        for language, source in LANGUAGE_SOURCES.items()
    }


def add_item_catalog_aliases(
    tables: dict[str, dict[str, dict[str, str | None]]],
    item_catalog: dict[str, dict],
) -> None:
    for internal_name, row in item_catalog.items():
        for language in LANGUAGE_SOURCES:
            localized = row.get("I18n", {}).get(language, {})
            name = localized.get("Name") if isinstance(localized, dict) else None
            if name:
                tables[language]["ItemName"].setdefault(
                    f"ITEM_NAME_{internal_name}", name
                )


def row_properties(row: dict) -> dict[str, object]:
    return {value["Name"]: value.get("Value") for value in row["Value"]}


def array_values(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item["Value"] for item in value if item.get("Value")]


def lookup_text(table: dict[str, str | None], key: str) -> str | None:
    direct = table.get(key)
    if direct:
        return direct
    folded_key = key.casefold()
    return next(
        (value for candidate, value in table.items() if candidate.casefold() == folded_key),
        None,
    )


def resolve_name(
    properties: dict[str, object],
    language: str,
    tables: dict[str, dict[str, dict[str, str | None]]],
) -> str | None:
    text_id = properties["Name"]
    text = lookup_text(tables[language]["TechnologyName"], str(text_id))
    if language == "ja" and (not text or text in PLACEHOLDER_TEXT):
        text = lookup_text(tables["en"]["TechnologyName"], str(text_id))
    if not text and str(text_id).startswith("NAME_RECIPE_"):
        source_id = str(text_id).removeprefix("NAME_RECIPE_")
        text = (
            lookup_text(
                tables[language]["MapObjectName"],
                f"MAPOBJECT_NAME_{source_id}",
            )
            or lookup_text(
                tables[language]["ItemName"],
                f"ITEM_NAME_{source_id}",
            )
        )
    if not text:
        return None

    reference = re.fullmatch(
        r"<(itemName|mapObjectName|mapObjectname) id=\|([^|]+)\|/>", text
    )
    if reference:
        table = "ItemName" if reference.group(1) == "itemName" else "MapObjectName"
        prefix = "ITEM_NAME_" if table == "ItemName" else "MAPOBJECT_NAME_"
        localized = lookup_text(
            tables[language][table], prefix + reference.group(2)
        )
        if not localized and table == "ItemName":
            numbered_id = re.fullmatch(r"(.+?)(\d+)", reference.group(2))
            if numbered_id:
                localized = lookup_text(
                    tables[language][table],
                    prefix + numbered_id.group(1) + "_" + numbered_id.group(2),
                )
        if not localized and table == "ItemName":
            localized = lookup_text(
                tables[language][table], prefix + reference.group(2) + "_1"
            )
        return localized
    return text


def build_technology_data(
    recipe_asset: Path,
    tables: dict[str, dict[str, dict[str, str | None]]],
    existing: dict[str, dict],
) -> dict[str, dict]:
    asset = json.loads(recipe_asset.read_text(encoding="utf-8"))
    rows = asset["Exports"][0]["Table"]["Data"]
    result: dict[str, dict] = {}

    for row in rows:
        internal_name = row["Name"]
        properties = row_properties(row)
        category = "build" if array_values(properties["UnlockBuildObjects"]) else "item"
        i18n = {}
        for language in LANGUAGE_SOURCES:
            name = resolve_name(properties, language, tables)
            existing_localized = (
                existing.get(internal_name, {}).get("I18n", {}).get(language, {})
            )
            if language != "ko" and existing_localized.get("Name"):
                name = existing_localized["Name"]
            if not name or name in PLACEHOLDER_TEXT:
                name = existing_localized.get("Name")
            if not name or name in PLACEHOLDER_TEXT:
                raise ValueError(
                    f"Unable to resolve {internal_name}/{language}/{properties['Name']}"
                )
            i18n[language] = {
                "Name": name,
                "Type": (
                    existing_localized.get("Type")
                    if language != "ko" and existing_localized.get("Type")
                    else TYPE_LABELS[language][category]
                ),
            }

        result[internal_name] = {
            "InternalName": internal_name,
            "Level": properties["LevelCap"],
            "I18n": i18n,
            "BossTechnology": bool(properties["IsBossTechnology"]),
        }

    return result


def technology_icon_urls() -> dict[str, str]:
    source = fetch_bytes(TECHNOLOGY_PAGE).decode("utf-8", errors="replace")
    parser = TechnologyIconParser()
    parser.feed(source)
    return parser.icons


def fetch_bytes(
    url: str, referer: str | None = None, attempts: int = 4, timeout: int = 30
) -> bytes:
    headers = {"User-Agent": "Mozilla/5.0 (Palworld-Save-Editor asset updater)"}
    if referer:
        headers["Referer"] = referer
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except (urllib.error.URLError, OSError, TimeoutError) as error:
            last_error = error
            if attempt < attempts - 1:
                time.sleep(0.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


def sync_icons(
    technology_data: dict[str, dict],
    tech_icons: Path,
    pal_icons: Path,
    icon_urls: dict[str, str] | None = None,
) -> tuple[int, list[str]]:
    tech_icons.mkdir(parents=True, exist_ok=True)
    missing_non_pal = [
        internal_name
        for internal_name in technology_data
        if not internal_name.startswith("SkillUnlock_")
        and not (tech_icons / f"{internal_name}.png").is_file()
    ]
    urls = (icon_urls if icon_urls is not None else technology_icon_urls()) if missing_non_pal else {}
    def download(internal_name: str) -> bool:
        url = urls.get(internal_name)
        if not url:
            return False
        try:
            source = fetch_bytes(
                url, TECHNOLOGY_PAGE, attempts=3, timeout=15
            )
            with Image.open(BytesIO(source)) as image:
                image.convert("RGBA").save(
                    tech_icons / f"{internal_name}.png", "PNG", optimize=True
                )
            return True
        except (urllib.error.URLError, OSError, TimeoutError):
            return False

    downloaded = 0
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(download, internal_name): internal_name
            for internal_name in missing_non_pal
        }
        for future in as_completed(futures):
            if future.result():
                downloaded += 1

    unresolved = []
    for internal_name in technology_data:
        if internal_name.startswith("SkillUnlock_"):
            icon = pal_icons / f"{internal_name[12:]}.png"
        else:
            icon = tech_icons / f"{internal_name}.png"
        if not icon.is_file():
            unresolved.append(internal_name)
    return downloaded, unresolved


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("recipe_asset", type=Path)
    parser.add_argument("localized_asset_directory", type=Path)
    parser.add_argument("tech_data", type=Path)
    parser.add_argument("tech_icons", type=Path)
    parser.add_argument("pal_icons", type=Path)
    parser.add_argument(
        "--icon-urls",
        help="JSON icon URL map path, or - to read it from stdin",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report localization drift without writing files.",
    )
    args = parser.parse_args()

    existing = json.loads(args.tech_data.read_text(encoding="utf-8"))
    tables = load_localizations(args.localized_asset_directory)
    item_data_path = args.tech_data.parent / "item_data.json"
    add_item_catalog_aliases(
        tables,
        json.loads(item_data_path.read_text(encoding="utf-8")),
    )
    technology_data = build_technology_data(args.recipe_asset, tables, existing)
    icon_urls = None
    if args.icon_urls:
        if args.icon_urls == "-":
            icon_urls = json.load(sys.stdin)
        else:
            icon_urls = json.loads(Path(args.icon_urls).read_text(encoding="utf-8"))
    downloaded, unresolved = sync_icons(
        technology_data,
        args.tech_icons,
        args.pal_icons,
        {} if args.check else icon_urls,
    )
    if unresolved:
        raise ValueError("Missing routed icons: " + ", ".join(unresolved))

    has_drift = technology_data != existing
    if not args.check:
        args.tech_data.write_text(
            json.dumps(technology_data, ensure_ascii=False, indent=4) + "\n",
            encoding="utf-8",
        )
    print(f"Official technologies: {len(technology_data)}")
    print(f"Maximum level: {max(row['Level'] for row in technology_data.values())}")
    print(f"Downloaded technology icons: {downloaded}")
    print(f"Localization drift: {has_drift}")
    if args.check and has_drift:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
