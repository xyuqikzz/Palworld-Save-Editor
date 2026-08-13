from __future__ import annotations

import unittest

from palworld_pal_editor.core.pal_objects import PalObjects
from palworld_pal_editor.core.player_entity import PlayerEntity
from palworld_pal_editor.domain.player_consumable_bonuses import (
    CONSUMABLE_BONUS_BY_KEY,
    ConsumableBonusStructureError,
    inspect_consumable_bonus_values,
    player_consumable_bonus_view,
    set_consumable_bonus_value,
)
from palworld_pal_editor.domain.player_attributes import PLAYER_ATTRIBUTE_BY_KEY
from palworld_pal_editor.domain.player_attributes import player_attribute_view


class PlayerAttributeDefinitionTests(unittest.TestCase):
    def test_official_caps_and_effect_boundaries(self) -> None:
        self.assertEqual(15, PLAYER_ATTRIBUTE_BY_KEY["capture_power"].max_rank)
        self.assertEqual(20, PLAYER_ATTRIBUTE_BY_KEY["swim_speed"].max_rank)
        self.assertEqual(4, PLAYER_ATTRIBUTE_BY_KEY["sphere_homing"].max_rank)
        self.assertEqual(92, PLAYER_ATTRIBUTE_BY_KEY["move_speed"].max_rank)
        self.assertEqual(
            46.0,
            PLAYER_ATTRIBUTE_BY_KEY["move_speed"].effect_percent(91),
        )
        self.assertEqual(
            50.0,
            PLAYER_ATTRIBUTE_BY_KEY["move_speed"].effect_percent(92),
        )
        self.assertEqual(
            5500,
            PLAYER_ATTRIBUTE_BY_KEY["max_hp"].display_value(50),
        )

    def test_entity_read_is_non_mutating_and_write_is_lazy(self) -> None:
        player = object.__new__(PlayerEntity)
        player._player_param = {}

        self.assertIsNone(player.status_point("泳ぎ速度"))
        self.assertNotIn("GotStatusPointList", player._player_param)
        player.set_status_point("泳ぎ速度", 0)
        self.assertNotIn("GotStatusPointList", player._player_param)

        player.set_status_point("泳ぎ速度", 20)
        statuses = PalObjects.get_ArrayProperty(
            player._player_param["GotStatusPointList"]
        )
        self.assertEqual(1, len(statuses))
        self.assertEqual(20, player.status_point("泳ぎ速度"))

        statuses.append(PalObjects.StatusPointStruct("future-field", 7))
        player.set_status_point("泳ぎ速度", 8)
        self.assertEqual(8, player.status_point("泳ぎ速度"))
        self.assertEqual(7, player.status_point("future-field"))

    def test_consumable_bonus_read_is_non_mutating_and_preserves_unknown_rows(self) -> None:
        player = object.__new__(PlayerEntity)
        player._player_param = {
            "GotStatusPointList": PalObjects.GotStatusPointList(),
            "GotExStatusPointList": PalObjects.GotExStatusPointList()
        }
        regular_rows = PalObjects.get_ArrayProperty(
            player._player_param["GotStatusPointList"]
        )
        rows = PalObjects.get_ArrayProperty(
            player._player_param["GotExStatusPointList"]
        )
        PalObjects.set_BaseType(regular_rows[0]["StatusPoint"], 18)
        PalObjects.set_BaseType(rows[0]["StatusPoint"], 28)
        rows.append(PalObjects.StatusPointStruct("future-field", 7))
        before_unknown = rows[-1].copy()

        values = inspect_consumable_bonus_values(player._player_param)
        view = player_consumable_bonus_view(player)

        self.assertEqual(28, values["max_hp"])
        self.assertTrue(view["available"])
        self.assertFalse(view["reduce_only"])
        self.assertEqual(32, view["values"][0]["maximum"])
        self.assertEqual(46, view["values"][0]["total_rank"])
        self.assertEqual(50, view["values"][0]["maximum_total"])
        attributes = {row["key"]: row for row in player_attribute_view(player)}
        self.assertEqual(22, attributes["max_hp"]["max_rank"])
        self.assertEqual(before_unknown, rows[-1])

        set_consumable_bonus_value(
            player._player_param,
            CONSUMABLE_BONUS_BY_KEY["max_hp"].status_name,
            12,
        )
        self.assertEqual(
            12,
            inspect_consumable_bonus_values(player._player_param)["max_hp"],
        )
        self.assertEqual(before_unknown, rows[-1])

    def test_consumable_bonus_missing_or_duplicate_structure_is_rejected(self) -> None:
        with self.assertRaises(ConsumableBonusStructureError) as missing:
            inspect_consumable_bonus_values({})
        self.assertEqual(
            "PLAYER_CONSUMABLE_BONUS_FIELD_MISSING",
            missing.exception.code,
        )

        prop = PalObjects.GotExStatusPointList()
        rows = PalObjects.get_ArrayProperty(prop)
        rows.append(PalObjects.StatusPointStruct("最大HP", 1))
        with self.assertRaises(ConsumableBonusStructureError) as duplicate:
            inspect_consumable_bonus_values({"GotExStatusPointList": prop})
        self.assertEqual(
            "PLAYER_CONSUMABLE_BONUS_STRUCTURE_UNSUPPORTED",
            duplicate.exception.code,
        )

    def test_consumable_bonus_total_rejects_malformed_regular_attributes(self) -> None:
        player = object.__new__(PlayerEntity)
        player._player_param = {
            "GotStatusPointList": {"type": "IntProperty", "value": 1},
            "GotExStatusPointList": PalObjects.GotExStatusPointList(),
        }

        view = player_consumable_bonus_view(player)

        self.assertFalse(view["available"])
        self.assertEqual("PLAYER_ATTRIBUTE_STRUCTURE_UNSUPPORTED", view["reason"])


if __name__ == "__main__":
    unittest.main()
