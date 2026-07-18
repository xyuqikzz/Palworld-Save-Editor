from __future__ import annotations

import argparse
import json
from pathlib import Path


ELEMENT_MAP = {
    "Dark": "Dark",
    "Dragon": "Dragon",
    "Earth": "Ground",
    "Electricity": "Electric",
    "Fire": "Fire",
    "Ice": "Ice",
    "Leaf": "Grass",
    "Normal": "Neutral",
    "Water": "Water",
}

SUITABILITY_MAP = {
    "EmitFlame": "EPalWorkSuitability::EmitFlame",
    "Watering": "EPalWorkSuitability::Watering",
    "Seeding": "EPalWorkSuitability::Seeding",
    "GenerateElectricity": "EPalWorkSuitability::GenerateElectricity",
    "Handcraft": "EPalWorkSuitability::Handcraft",
    "Collection": "EPalWorkSuitability::Collection",
    "Deforest": "EPalWorkSuitability::Deforest",
    "Mining": "EPalWorkSuitability::Mining",
    "ProductMedicine": "EPalWorkSuitability::ProductMedicine",
    "Cool": "EPalWorkSuitability::Cool",
    "Transport": "EPalWorkSuitability::Transport",
    "MonsterFarm": "EPalWorkSuitability::MonsterFarm",
}


def convert(source: dict) -> dict:
    internal_name = source["CodeName"]
    elements = [
        ELEMENT_MAP[element]
        for element in source.get("Type", [])
        if element in ELEMENT_MAP
    ]
    scaling = source.get("Scaling", {})
    stats = {
        "HP": scaling["HP"],
        "ATK": scaling["MAG"],
        "DEF": scaling["DEF"],
        "MELEE": scaling["PHY"],
    }
    suitabilities = {
        target: source.get("Suitabilities", {}).get(origin, 0)
        for origin, target in SUITABILITY_MAP.items()
    }
    return {
        "InternalName": internal_name,
        "Elements": elements,
        "Attacks": source.get("Moveset", {}),
        "Stats": stats,
        "I18n": {
            "en": internal_name,
            "zh-CN": internal_name,
            "ja": internal_name,
            "fr": internal_name,
        },
        "Suitabilities": suitabilities,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paledit_data", type=Path)
    parser.add_argument("pal_data", type=Path)
    parser.add_argument("human_data", type=Path)
    args = parser.parse_args()

    pal_data = json.loads(args.pal_data.read_text(encoding="utf-8"))
    human_data = json.loads(args.human_data.read_text(encoding="utf-8"))
    known_names = set(pal_data) | set(human_data)
    imported_names: list[str] = []

    for source_path in sorted((args.paledit_data / "pals").glob("*.json")):
        source = json.loads(source_path.read_text(encoding="utf-8"))
        internal_name = source["CodeName"]
        if internal_name in known_names or source.get("Human", False):
            continue
        pal_data[internal_name] = convert(source)
        imported_names.append(internal_name)

    args.pal_data.write_text(
        json.dumps(pal_data, ensure_ascii=False, indent=4) + "\n",
        encoding="utf-8",
    )
    print(f"Imported {len(imported_names)} entries: {', '.join(imported_names)}")


if __name__ == "__main__":
    main()
