from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import unittest

from palworld_pal_editor.application.mission_editor import MissionEditor
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.domain.commands import UpdatePlayerMissions
from palworld_pal_editor.domain.errors import DomainError


def _name_array(values: list[str]) -> dict:
    return {
        "array_type": "NameProperty",
        "id": None,
        "value": {"values": list(values)},
        "type": "ArrayProperty",
    }


def _ordered_record(
    mission_id: str,
    *,
    block_index: int = 0,
    counters: list[dict] | None = None,
) -> dict:
    return {
        "QuestName": {"id": None, "value": mission_id, "type": "NameProperty"},
        "BlockIndex": {"id": None, "value": block_index, "type": "IntProperty"},
        "IntegerMap": {
            "key_type": "NameProperty",
            "value_type": "IntProperty",
            "key_struct_type": None,
            "value_struct_type": None,
            "id": None,
            "value": list(counters or []),
            "type": "MapProperty",
        },
        "StringMap": {
            "key_type": "NameProperty",
            "value_type": "StrProperty",
            "key_struct_type": None,
            "value_struct_type": None,
            "id": None,
            "value": [],
            "type": "MapProperty",
        },
    }


def _ordered_array(records: list[dict]) -> dict:
    return {
        "array_type": "StructProperty",
        "id": None,
        "value": {
            "prop_name": "OrderedQuestArray_FullRelease",
            "prop_type": "StructProperty",
            "values": records,
            "type_name": "PalOrderedQuestSaveData",
            "id": "00000000-0000-0000-0000-000000000000",
        },
        "type": "ArrayProperty",
    }


class _Player:
    PlayerUId = "mission-player"
    InstanceId = "mission-instance"
    NickName = "Mission Tester"
    Level = 20

    def __init__(self) -> None:
        self._player_save_data = {
            "CompletedQuestArray_FullRelease": _name_array(
                ["Main_Complete", "Main_Conflict", "Main_Conflict"]
            ),
            "OrderedQuestArray_FullRelease": _ordered_array(
                [
                    _ordered_record(
                        "Sub_Progress",
                        block_index=4,
                        counters=[{"key": "CanCompleteFlag_0", "value": 3}],
                    ),
                    _ordered_record("Main_Conflict"),
                ]
            ),
            "InventoryInfo": {"value": {"sentinel": "untouched"}},
            "TechnologyPoint": {"id": None, "value": 9, "type": "IntProperty"},
        }


def _catalog() -> dict:
    def entry(mission_id: str, mission_type: str, title: str) -> dict:
        return {
            "internal_name": mission_id,
            "type": mission_type,
            "asset_path": f"/Game/Quest/{mission_id}",
            "title_key": f"TITLE_{mission_id}",
            "description_key": None,
            "objective_keys": [],
            "restart_capability": {
                "supported": True,
                "reason": None,
                "template": "pal_ordered_quest_stage_zero_v1",
            },
            "i18n": {
                "en": {
                    "title": title,
                    "description": "",
                    "objectives": [],
                    "title_fallback": False,
                },
                "zh-CN": {
                    "title": f"中-{title}",
                    "description": "",
                    "objectives": [],
                    "title_fallback": False,
                },
            },
        }

    result = {
        "schema_version": 1,
        "source": {"build_id": "synthetic"},
        "missions": {
            "Main_Complete": entry("Main_Complete", "main", "Complete"),
            "Sub_Progress": entry("Sub_Progress", "sub", "Progress"),
            "Main_Unaccepted": entry("Main_Unaccepted", "main", "Unaccepted"),
            "Main_Conflict": entry("Main_Conflict", "main", "Conflict"),
        },
    }
    result["missions"]["Main_Unaccepted"]["restart_capability"] = {
        "supported": False,
        "reason": "MISSION_INITIAL_TEMPLATE_UNVERIFIED",
        "template": None,
    }
    return result


class MissionEditorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.player = _Player()
        manager = SimpleNamespace(
            gvas_file=SimpleNamespace(header=None),
            player_mapping={self.player.PlayerUId: self.player},
            get_player=lambda player_id: (
                self.player if player_id == self.player.PlayerUId else None
            ),
        )
        self.session = SaveSession.from_loaded_manager(manager, Path("synthetic-save"))
        self.editor = MissionEditor(self.session, catalog_data=_catalog(), locale="en")

    def command(
        self,
        operation: str,
        mission_ids: tuple[str, ...] = (),
        *,
        revision: int | None = None,
        preview_token: str | None = None,
    ) -> UpdatePlayerMissions:
        return UpdatePlayerMissions(
            session_id=self.session.session_id,
            expected_revision=(self.session.revision if revision is None else revision),
            player_id=self.player.PlayerUId,
            operation=operation,
            mission_ids=mission_ids,
            preview_token=preview_token,
        )

    def test_read_model_classifies_all_statuses_and_localizes_titles(self) -> None:
        view = self.editor.get_missions(self.player.PlayerUId, locale="zh-CN")
        by_id = {mission["internal_name"]: mission for mission in view["missions"]}

        self.assertEqual("completed", by_id["Main_Complete"]["status"])
        self.assertEqual("in_progress", by_id["Sub_Progress"]["status"])
        self.assertEqual("unaccepted", by_id["Main_Unaccepted"]["status"])
        self.assertEqual("inconsistent", by_id["Main_Conflict"]["status"])
        self.assertEqual("中-Progress", by_id["Sub_Progress"]["title"])
        self.assertTrue(by_id["Sub_Progress"]["tracked"])
        self.assertEqual(4, by_id["Sub_Progress"]["progress"]["block_index"])
        self.assertEqual(
            {"completed": 1, "in_progress": 1, "unaccepted": 1, "inconsistent": 1},
            view["summary"]["by_status"],
        )

    def test_mark_completed_requires_preview_and_changes_only_quest_fields(self) -> None:
        before_other = {
            key: deepcopy(value)
            for key, value in self.player._player_save_data.items()
            if "QuestArray" not in key
        }
        preview = self.editor.preview(
            self.command("mark_completed", ("Sub_Progress",))
        )
        result = self.editor.execute(
            self.command(
                "mark_completed",
                ("Sub_Progress",),
                preview_token=preview["preview_token"],
            )
        )

        view = self.editor.get_missions(self.player.PlayerUId)
        status = {
            mission["internal_name"]: mission["status"]
            for mission in view["missions"]
        }
        self.assertEqual("completed", status["Sub_Progress"])
        self.assertEqual(before_other, {
            key: value
            for key, value in self.player._player_save_data.items()
            if "QuestArray" not in key
        })
        self.assertEqual(1, self.session.revision)
        self.assertEqual(1, result["revision"])
        self.assertEqual(
            [f"player_file:{self.player.PlayerUId}"],
            result["change"]["affected_records"],
        )

    def test_restart_reconstructs_verified_full_release_initial_record(self) -> None:
        preview = self.editor.preview(
            self.command("restart_from_beginning", ("Main_Complete",))
        )
        result = self.editor.execute(
            self.command(
                "restart_from_beginning",
                ("Main_Complete",),
                preview_token=preview["preview_token"],
            )
        )

        self.assertEqual(1, result["impact_count"])
        records = self.player._player_save_data[
            "OrderedQuestArray_FullRelease"
        ]["value"]["values"]
        record = next(
            value for value in records if value["QuestName"]["value"] == "Main_Complete"
        )
        self.assertEqual(0, record["BlockIndex"]["value"])
        self.assertEqual(
            [{"key": "CanCompleteFlag_0", "value": 0}],
            record["IntegerMap"]["value"],
        )
        self.assertEqual([], record["StringMap"]["value"])

    def test_bulk_command_is_one_atomic_revision_and_excludes_conflicts(self) -> None:
        preview = self.editor.preview(self.command("complete_all"))
        self.assertEqual(["Main_Conflict"], preview["conflict_ids"])
        result = self.editor.execute(
            self.command("complete_all", preview_token=preview["preview_token"])
        )

        self.assertEqual(1, self.session.revision)
        self.assertEqual(2, result["impact_count"])
        self.assertEqual(1, len(self.session.changes()))
        self.assertEqual("complete_all", self.session.changes()[0]["command"])

    def test_invalid_token_stale_revision_and_ambiguous_alias_are_non_mutating(self) -> None:
        before = deepcopy(self.player._player_save_data)
        with self.assertRaises(DomainError) as raised:
            self.editor.execute(
                self.command(
                    "reset_to_unaccepted",
                    ("Main_Complete",),
                    preview_token="invalid",
                )
            )
        self.assertEqual("MISSION_PREVIEW_STALE", raised.exception.code)
        self.assertEqual(before, self.player._player_save_data)

        preview = self.editor.preview(
            self.command("reset_to_unaccepted", ("Main_Complete",))
        )
        with self.assertRaises(DomainError) as raised:
            self.editor.execute(
                self.command(
                    "reset_to_unaccepted",
                    ("Main_Complete",),
                    revision=1,
                    preview_token=preview["preview_token"],
                )
            )
        self.assertEqual("STALE_REVISION", raised.exception.code)
        self.assertEqual(before, self.player._player_save_data)

        self.player._player_save_data["CompletedQuestArray"] = _name_array([])
        with self.assertRaises(DomainError) as raised:
            self.editor.preview(
                self.command("reset_to_unaccepted", ("Main_Complete",))
            )
        self.assertEqual("MISSION_FIELD_AMBIGUOUS", raised.exception.code)

    def test_restart_without_a_verified_catalog_template_is_rejected(self) -> None:
        before = deepcopy(self.player._player_save_data)
        with self.assertRaises(DomainError) as raised:
            self.editor.preview(
                self.command("restart_from_beginning", ("Main_Unaccepted",))
            )
        self.assertEqual("MISSION_RESTART_UNSUPPORTED", raised.exception.code)
        self.assertEqual(before, self.player._player_save_data)

    def test_legacy_restart_is_disabled_because_initial_counter_maps_diverge(self) -> None:
        save_data = self.player._player_save_data
        completed = save_data.pop("CompletedQuestArray_FullRelease")
        ordered = save_data.pop("OrderedQuestArray_FullRelease")
        ordered["value"]["prop_name"] = "OrderedQuestArray"
        save_data["CompletedQuestArray"] = completed
        save_data["OrderedQuestArray"] = ordered

        view = self.editor.get_missions(self.player.PlayerUId)
        mission = next(
            row for row in view["missions"] if row["internal_name"] == "Sub_Progress"
        )
        self.assertFalse(mission["capabilities"]["restart_from_beginning"])
        with self.assertRaises(DomainError) as raised:
            self.editor.preview(
                self.command("restart_from_beginning", ("Sub_Progress",))
            )
        self.assertEqual("MISSION_RESTART_UNSUPPORTED", raised.exception.code)

    def test_missing_empty_ordered_field_is_readable_and_materialized_on_restart(self) -> None:
        save_data = self.player._player_save_data
        save_data.pop("OrderedQuestArray_FullRelease")

        view = self.editor.get_missions(self.player.PlayerUId)

        self.assertTrue(view["writable"])
        self.assertNotIn("OrderedQuestArray_FullRelease", save_data)
        preview = self.editor.preview(
            self.command("restart_from_beginning", ("Main_Complete",))
        )
        self.assertNotIn("OrderedQuestArray_FullRelease", save_data)
        self.editor.execute(
            self.command(
                "restart_from_beginning",
                ("Main_Complete",),
                preview_token=preview["preview_token"],
            )
        )

        ordered = save_data["OrderedQuestArray_FullRelease"]
        self.assertEqual("StructProperty", ordered["array_type"])
        self.assertEqual(
            "OrderedQuestArray_FullRelease", ordered["value"]["prop_name"]
        )
        self.assertEqual(
            ["Main_Complete"],
            [
                record["QuestName"]["value"]
                for record in ordered["value"]["values"]
            ],
        )

    def test_missing_empty_completed_field_is_materialized_on_completion(self) -> None:
        save_data = self.player._player_save_data
        save_data.pop("CompletedQuestArray_FullRelease")

        view = self.editor.get_missions(self.player.PlayerUId)

        self.assertTrue(view["writable"])
        self.assertNotIn("CompletedQuestArray_FullRelease", save_data)
        preview = self.editor.preview(
            self.command("mark_completed", ("Sub_Progress",))
        )
        self.assertNotIn("CompletedQuestArray_FullRelease", save_data)
        self.editor.execute(
            self.command(
                "mark_completed",
                ("Sub_Progress",),
                preview_token=preview["preview_token"],
            )
        )

        completed = save_data["CompletedQuestArray_FullRelease"]
        self.assertEqual("NameProperty", completed["array_type"])
        self.assertEqual(["Sub_Progress"], completed["value"]["values"])


if __name__ == "__main__":
    unittest.main()
