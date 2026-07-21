from __future__ import annotations

import json
from pathlib import Path
import unittest

from palworld_pal_editor.assets.tools.sync_1_0_mission_assets import (
    LANGUAGES,
    validate_catalog,
)
from palworld_pal_editor.utils.data_provider import DataProvider


class MissionAssetSyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "palworld_pal_editor"
            / "assets"
            / "data"
            / "mission_data.json"
        )
        cls.data = json.loads(path.read_text(encoding="utf-8"))

    def test_build_24088745_catalog_has_unique_authoritative_ids(self) -> None:
        self.assertEqual("24088745", self.data["source"]["build_id"])
        self.assertEqual([], validate_catalog(self.data))
        self.assertEqual(120, self.data["statistics"]["mission_count"])
        self.assertEqual(
            {"main": 57, "sub": 59, "hidden": 4},
            self.data["statistics"]["by_type"],
        )
        self.assertEqual(1, self.data["statistics"]["unmatched_asset_count"])
        self.assertEqual(
            ["Test_UnlockAreaBarriers"],
            self.data["statistics"]["unmatched_asset_ids"],
        )

    def test_every_supported_language_reports_title_coverage_and_fallbacks(self) -> None:
        self.assertEqual(
            set(LANGUAGES), set(self.data["statistics"]["languages"])
        )
        for language in LANGUAGES:
            with self.subTest(language=language):
                statistics = self.data["statistics"]["languages"][language]
                self.assertEqual(116, statistics["title_localized_count"])
                self.assertEqual(4, statistics["title_missing_count"])
                self.assertEqual(4, statistics["title_fallback_count"])

    def test_catalog_includes_keys_descriptions_objectives_and_language_values(self) -> None:
        capture = self.data["missions"]["Main_Capture30Pal"]
        self.assertEqual("QUEST_MAIN_TITLE_CAPTURE_PAL_30", capture["title_key"])
        self.assertEqual("QUEST_MAIN_DESC_CAPTURE_PAL", capture["description_key"])
        self.assertEqual(
            ["QUEST_MAIN_OBJECTIVE_CAPTURE_PAL"], capture["objective_keys"]
        )
        self.assertTrue(capture["restart_capability"]["supported"])
        self.assertFalse(
            self.data["missions"]["Test_UnlockAreaBarriers"]
            ["restart_capability"]["supported"]
        )
        self.assertEqual(
            50,
            self.data["restart_templates"]["evidence"]
            ["full_release_stage_zero_records"],
        )
        self.assertEqual(
            42,
            self.data["restart_templates"]["evidence"]
            ["legacy_stage_zero_records"],
        )
        self.assertFalse(
            self.data["restart_templates"]["pal_ordered_quest_stage_zero_v1"]
            ["legacy"]["supported"]
        )
        for mission_id, mission in self.data["missions"].items():
            with self.subTest(mission_id=mission_id):
                self.assertEqual(set(LANGUAGES), set(mission["i18n"]))
                for translation in mission["i18n"].values():
                    self.assertTrue(translation["title"])
        self.assertEqual(self.data, DataProvider.get_mission_data())
        self.assertTrue(
            DataProvider.get_mission_i18n("Main_Capture30Pal", "zh-CN")["title"]
        )


if __name__ == "__main__":
    unittest.main()
