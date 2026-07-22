import json
import re
import sys
import unittest
from pathlib import Path


DATA_ROOT = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "palworld_pal_editor"
    / "assets"
    / "data"
)
LANGUAGES = ("en", "fr", "ja", "ko", "zh-CN")
EFFECT_VALUE_PATTERN = re.compile(r"\{EffectValue\d+\}")
TOOLS_ROOT = DATA_ROOT.parent / "tools"
sys.path.insert(0, str(TOOLS_ROOT))

from sync_1_0_localized_assets import (  # noqa: E402
    preserve_rendered_passive_descriptions,
)
from sync_1_0_pal_assets import (  # noqa: E402
    PassiveEffect,
    PassiveRecord,
    render_skill_i18n_passive_values,
)


class PassiveLocalizationValueTests(unittest.TestCase):
    def test_renderer_supports_the_fourth_passive_effect_slot(self) -> None:
        record = PassiveRecord(
            internal_name="MutationPal_Mutant",
            rating=4,
            weight=100,
            override_description_id="PASSIVE_MutationPal_Mutant_DESC",
            effects=(
                PassiveEffect(157, 50.0, 3),
                PassiveEffect(131, 100.0, 1),
                PassiveEffect(130, 100.0, 1),
                PassiveEffect(4, 25.0, 1),
            ),
            position=0,
        )
        catalog = {
            "Passives": {
                "MutationPal_Mutant": {
                    "I18n": {
                        "zh-CN": {
                            "Description": "恢复+{EffectValue1}%\n防御+{EffectValue4}%"
                        }
                    }
                }
            }
        }

        rendered = render_skill_i18n_passive_values(
            catalog, {record.internal_name: record}
        )

        self.assertEqual(
            "恢复+50%\n防御+25%",
            rendered["Passives"][record.internal_name]["I18n"]["zh-CN"][
                "Description"
            ],
        )

    def test_localization_sync_preserves_rendered_effect_values(self) -> None:
        generated = {
            "Example": {
                "I18n": {"zh-CN": {"Description": "攻击+{EffectValue1}%"}}
            }
        }
        existing = {
            "Example": {"I18n": {"zh-CN": {"Description": "攻击+20%"}}}
        }

        preserve_rendered_passive_descriptions(generated, existing)

        self.assertEqual(
            "攻击+20%", generated["Example"]["I18n"]["zh-CN"]["Description"]
        )

    def test_published_passive_descriptions_have_no_raw_effect_identifiers(self) -> None:
        catalogs = (
            json.loads((DATA_ROOT / "pal_passives.json").read_text(encoding="utf-8")),
            json.loads((DATA_ROOT / "skill_i18n.json").read_text(encoding="utf-8"))[
                "Passives"
            ],
        )

        failures = []
        for catalog in catalogs:
            for internal_name, row in catalog.items():
                for language in LANGUAGES:
                    description = row["I18n"][language]["Description"]
                    if EFFECT_VALUE_PATTERN.search(description):
                        failures.append((internal_name, language, description))

        self.assertEqual([], failures)

    def test_known_build_24088745_passive_values_are_rendered(self) -> None:
        editable = json.loads(
            (DATA_ROOT / "pal_passives.json").read_text(encoding="utf-8")
        )
        localized = json.loads(
            (DATA_ROOT / "skill_i18n.json").read_text(encoding="utf-8")
        )["Passives"]

        self.assertIn(
            "防御力+25%",
            editable["MutationPal_Mutant"]["I18n"]["zh-CN"]["Description"],
        )
        self.assertEqual(
            "攻击+20%\n移动速度提升10%",
            localized["GYM_NAME_Meadow"]["I18n"]["zh-CN"]["Description"],
        )
        self.assertEqual(
            "自身道具掉落量+15%",
            localized["SelfDeathAddItemDrop_up_1"]["I18n"]["zh-CN"][
                "Description"
            ],
        )


if __name__ == "__main__":
    unittest.main()
