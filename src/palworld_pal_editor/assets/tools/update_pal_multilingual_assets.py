from __future__ import annotations

import argparse
import json
from pathlib import Path


LANGUAGES = ("en", "fr", "ja", "ko", "zh-CN")
ROW_PREFIX = "PAL_NAME_"


def load_names(path: Path) -> dict[str, str]:
    asset = json.loads(path.read_text(encoding="utf-8"))
    exports = asset.get("Exports", [])
    if not exports or exports[0].get("$type", "").split(",", 1)[0].split(".")[-1] != "DataTableExport":
        raise ValueError(f"Not a parsed DataTable export: {path}")

    names: dict[str, str] = {}
    for row in exports[0]["Table"]["Data"]:
        row_name = row["Name"]
        if not row_name.startswith(ROW_PREFIX):
            continue
        value = row["Value"][0].get("CultureInvariantString")
        if value:
            names[row_name[len(ROW_PREFIX) :]] = value
    return names


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pal_data", type=Path)
    for language in LANGUAGES:
        parser.add_argument(f"--{language}", dest=language, type=Path, required=True)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report multilingual Pal-name drift without writing the catalog.",
    )
    args = parser.parse_args()

    localized = {
        language: load_names(getattr(args, language)) for language in LANGUAGES
    }
    official_ids = set.intersection(*(set(names) for names in localized.values()))
    if not official_ids:
        raise RuntimeError("The localized Pal name tables have no common rows")

    pal_data = json.loads(args.pal_data.read_text(encoding="utf-8"))
    original_pal_data = json.loads(args.pal_data.read_text(encoding="utf-8"))
    updated: list[str] = []
    catalog_ids = official_ids & set(pal_data)
    source_only_ids = sorted(official_ids - set(pal_data))
    for internal_name in sorted(catalog_ids):
        i18n = pal_data[internal_name].setdefault("I18n", {})
        before = dict(i18n)
        for language in LANGUAGES:
            i18n[language] = localized[language][internal_name]
        if i18n != before:
            updated.append(internal_name)

    has_drift = pal_data != original_pal_data
    if not args.check:
        args.pal_data.write_text(
            json.dumps(pal_data, ensure_ascii=False, indent=4) + "\n",
            encoding="utf-8",
        )
    print(f"Official rows: {len(official_ids)}")
    print(f"Catalog rows: {len(catalog_ids)}")
    print(f"Source-only rows: {len(source_only_ids)}")
    print(f"Updated translations: {len(updated)}")
    if args.check and has_drift:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
