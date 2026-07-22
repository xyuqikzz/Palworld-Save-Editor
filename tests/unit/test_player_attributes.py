from __future__ import annotations

import unittest

from palworld_pal_editor.core.pal_objects import PalObjects
from palworld_pal_editor.core.player_entity import PlayerEntity
from palworld_pal_editor.domain.player_attributes import PLAYER_ATTRIBUTE_BY_KEY


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


if __name__ == "__main__":
    unittest.main()
