from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlayerAttributeDefinition:
    key: str
    status_name: str
    kind: str
    max_rank: int
    icon: str
    base_value: int | None = None
    value_per_rank: int | None = None
    effect_per_rank: float | None = None
    effect_overrides: tuple[float, ...] = ()

    def display_value(self, rank: int) -> int | None:
        if self.base_value is None or self.value_per_rank is None:
            return None
        return self.base_value + self.value_per_rank * rank

    def effect_percent(self, rank: int) -> float | None:
        if rank <= 0:
            return 0.0 if self.kind == "relic" and self.key != "capture_power" else None
        if self.effect_overrides:
            return self.effect_overrides[rank - 1]
        if self.effect_per_rank is None:
            return None
        return self.effect_per_rank * rank

    def view(self, rank: int) -> dict[str, object]:
        return {
            "key": self.key,
            "kind": self.kind,
            "rank": rank,
            "max_rank": self.max_rank,
            "display_value": self.display_value(rank),
            "effect_percent": self.effect_percent(rank),
            "icon": self.icon,
        }


# Save-field names and relic rank effects were verified against the current
# Palworld Build 24088745 resources. The five base values use the game's
# displayed player-stat formulas; relic effects come from
# DT_PlayerStatusRankMasterDataTable.
PLAYER_ATTRIBUTE_DEFINITIONS = (
    PlayerAttributeDefinition(
        "max_hp", "最大HP", "base", 50, "max_hp", 500, 100
    ),
    PlayerAttributeDefinition(
        "max_sp", "最大SP", "base", 50, "max_sp", 100, 10
    ),
    PlayerAttributeDefinition(
        "attack", "攻撃力", "base", 50, "attack", 100, 2
    ),
    PlayerAttributeDefinition(
        "work_speed", "作業速度", "base", 50, "work_speed", 100, 50
    ),
    PlayerAttributeDefinition(
        "carry_weight", "所持重量", "base", 50, "carry_weight", 300, 50
    ),
    PlayerAttributeDefinition(
        "capture_power", "捕獲率", "relic", 15, "capture_power"
    ),
    PlayerAttributeDefinition(
        "hunger_reduction", "空腹率低減", "relic", 20, "hunger_reduction",
        effect_per_rank=2.5,
    ),
    PlayerAttributeDefinition(
        "swim_speed", "泳ぎ速度", "relic", 20, "swim_speed",
        effect_per_rank=5.0,
    ),
    PlayerAttributeDefinition(
        "food_decay_reduction", "食料腐敗低減", "relic", 20,
        "food_decay_reduction", effect_per_rank=2.5,
    ),
    PlayerAttributeDefinition(
        "jump_power", "ジャンプ力", "relic", 20, "jump_power",
        effect_per_rank=2.5,
    ),
    PlayerAttributeDefinition(
        "glider_speed", "滑空速度", "relic", 20, "glider_speed",
        effect_per_rank=1.5,
    ),
    PlayerAttributeDefinition(
        "climb_speed", "崖登り速度", "relic", 20, "climb_speed",
        effect_per_rank=5.0,
    ),
    PlayerAttributeDefinition(
        "status_ailment_resist", "状態異常耐性", "relic", 20,
        "status_ailment_resist", effect_per_rank=2.5,
    ),
    PlayerAttributeDefinition(
        "stamina_reduction", "スタミナ消費軽減", "relic", 20,
        "stamina_reduction", effect_per_rank=2.5,
    ),
    PlayerAttributeDefinition(
        "sphere_homing", "パルスフィアホーミング", "relic", 4,
        "sphere_homing", effect_per_rank=25.0,
    ),
    PlayerAttributeDefinition(
        "exp_bonus", "経験値ボーナス", "relic", 4, "exp_bonus",
        effect_overrides=(12.0, 25.0, 37.0, 50.0),
    ),
    PlayerAttributeDefinition(
        "rainbow_passive_rate", "虹パッシブ率", "relic", 4,
        "rainbow_passive_rate", effect_per_rank=1.0,
    ),
    PlayerAttributeDefinition(
        "move_speed", "移動速度アップ", "relic", 92, "move_speed",
        effect_overrides=tuple(rank * 0.5 for rank in range(1, 91))
        + (46.0, 50.0),
    ),
)

PLAYER_ATTRIBUTE_BY_KEY = {
    definition.key: definition for definition in PLAYER_ATTRIBUTE_DEFINITIONS
}


def player_attribute_view(player) -> list[dict[str, object]]:
    try:
        from palworld_pal_editor.domain.player_consumable_bonuses import (
            inspect_consumable_bonus_values,
        )

        consumable_bonuses = inspect_consumable_bonus_values(
            player._player_param
        )
    except (AttributeError, ValueError):
        consumable_bonuses = {}

    result = []
    for definition in PLAYER_ATTRIBUTE_DEFINITIONS:
        view = definition.view(
            player.status_point(definition.status_name) or 0
        )
        if definition.kind == "base" and definition.key in consumable_bonuses:
            view["max_rank"] = max(
                0,
                definition.max_rank - consumable_bonuses[definition.key],
            )
        result.append(view)
    return result
