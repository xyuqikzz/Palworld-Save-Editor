from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from palworld_pal_editor.core.pal_objects import PalObjects, StatusName
from palworld_pal_editor.domain.player_attributes import PLAYER_ATTRIBUTE_BY_KEY


@dataclass(frozen=True)
class PlayerConsumableBonusDefinition:
    key: str
    status_name: str
    icon: str

    @property
    def maximum_total(self) -> int:
        return PLAYER_ATTRIBUTE_BY_KEY[self.key].max_rank


PLAYER_CONSUMABLE_BONUS_DEFINITIONS = (
    PlayerConsumableBonusDefinition("max_hp", StatusName.MaxHP, "max_hp"),
    PlayerConsumableBonusDefinition("max_sp", StatusName.MaxSP, "max_sp"),
    PlayerConsumableBonusDefinition("attack", StatusName.Attack, "attack"),
    PlayerConsumableBonusDefinition(
        "carry_weight", StatusName.CarryWeight, "carry_weight"
    ),
    PlayerConsumableBonusDefinition(
        "work_speed", StatusName.WorkSpeed, "work_speed"
    ),
)
CONSUMABLE_BONUS_BY_KEY = {
    definition.key: definition
    for definition in PLAYER_CONSUMABLE_BONUS_DEFINITIONS
}
_CONSUMABLE_BONUS_KEY_BY_STATUS = {
    definition.status_name: definition.key
    for definition in PLAYER_CONSUMABLE_BONUS_DEFINITIONS
}


class ConsumableBonusStructureError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def inspect_consumable_bonus_values(
    player_param: dict[str, Any],
) -> dict[str, int]:
    prop = player_param.get("GotExStatusPointList")
    if prop is None:
        raise ConsumableBonusStructureError(
            "PLAYER_CONSUMABLE_BONUS_FIELD_MISSING",
            "This player save does not contain Remedy or Elixir bonus data.",
        )
    if (
        not isinstance(prop, dict)
        or prop.get("type") != "ArrayProperty"
        or prop.get("array_type") != "StructProperty"
    ):
        raise ConsumableBonusStructureError(
            "PLAYER_CONSUMABLE_BONUS_STRUCTURE_UNSUPPORTED",
            "The Remedy or Elixir bonus structure is unsupported.",
        )
    metadata = prop.get("value")
    if (
        not isinstance(metadata, dict)
        or metadata.get("prop_name") != "GotExStatusPointList"
        or metadata.get("prop_type") != "StructProperty"
        or metadata.get("type_name") != "PalGotStatusPoint"
    ):
        raise ConsumableBonusStructureError(
            "PLAYER_CONSUMABLE_BONUS_STRUCTURE_UNSUPPORTED",
            "The Remedy or Elixir bonus structure is unsupported.",
        )
    rows = metadata.get("values")
    if not isinstance(rows, list):
        raise ConsumableBonusStructureError(
            "PLAYER_CONSUMABLE_BONUS_STRUCTURE_UNSUPPORTED",
            "The Remedy or Elixir bonus structure is unsupported.",
        )

    values: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ConsumableBonusStructureError(
                "PLAYER_CONSUMABLE_BONUS_STRUCTURE_UNSUPPORTED",
                "The Remedy or Elixir bonus structure is unsupported.",
            )
        name_prop = row.get("StatusName")
        point_prop = row.get("StatusPoint")
        status_name = PalObjects.get_BaseType(name_prop)
        if status_name not in _CONSUMABLE_BONUS_KEY_BY_STATUS:
            continue
        if (
            not isinstance(name_prop, dict)
            or name_prop.get("type") != "NameProperty"
            or not isinstance(point_prop, dict)
            or point_prop.get("type") != "IntProperty"
        ):
            raise ConsumableBonusStructureError(
                "PLAYER_CONSUMABLE_BONUS_STRUCTURE_UNSUPPORTED",
                "The Remedy or Elixir bonus structure is unsupported.",
            )
        point = PalObjects.get_BaseType(point_prop)
        if isinstance(point, bool) or not isinstance(point, int) or point < 0:
            raise ConsumableBonusStructureError(
                "PLAYER_CONSUMABLE_BONUS_STRUCTURE_UNSUPPORTED",
                "The Remedy or Elixir bonus structure is unsupported.",
            )
        key = _CONSUMABLE_BONUS_KEY_BY_STATUS[status_name]
        if key in values:
            raise ConsumableBonusStructureError(
                "PLAYER_CONSUMABLE_BONUS_STRUCTURE_UNSUPPORTED",
                "The Remedy or Elixir bonus structure contains duplicate fields.",
            )
        values[key] = point

    if set(values) != set(CONSUMABLE_BONUS_BY_KEY):
        raise ConsumableBonusStructureError(
            "PLAYER_CONSUMABLE_BONUS_STRUCTURE_UNSUPPORTED",
            "The Remedy or Elixir bonus structure is incomplete.",
        )
    return values


def set_consumable_bonus_value(
    player_param: dict[str, Any], status_name: str, value: int
) -> None:
    inspect_consumable_bonus_values(player_param)
    rows = PalObjects.get_ArrayProperty(player_param["GotExStatusPointList"])
    for row in rows:
        if PalObjects.get_BaseType(row.get("StatusName")) == status_name:
            PalObjects.set_BaseType(row["StatusPoint"], value)
            return
    raise ConsumableBonusStructureError(
        "PLAYER_CONSUMABLE_BONUS_STRUCTURE_UNSUPPORTED",
        "The Remedy or Elixir bonus field is missing.",
    )


def regular_attribute_rank(player_param: dict[str, Any], status_name: str) -> int:
    prop = player_param.get("GotStatusPointList")
    if prop is None:
        return 0
    if (
        not isinstance(prop, dict)
        or prop.get("type") != "ArrayProperty"
        or prop.get("array_type") != "StructProperty"
    ):
        raise ConsumableBonusStructureError(
            "PLAYER_ATTRIBUTE_STRUCTURE_UNSUPPORTED",
            "The regular player attribute structure is unsupported.",
        )
    metadata = prop.get("value")
    if (
        not isinstance(metadata, dict)
        or metadata.get("prop_name") != "GotStatusPointList"
        or metadata.get("prop_type") != "StructProperty"
        or metadata.get("type_name") != "PalGotStatusPoint"
        or not isinstance(metadata.get("values"), list)
    ):
        raise ConsumableBonusStructureError(
            "PLAYER_ATTRIBUTE_STRUCTURE_UNSUPPORTED",
            "The regular player attribute structure is unsupported.",
        )

    result = None
    for row in metadata["values"]:
        if not isinstance(row, dict):
            continue
        name_prop = row.get("StatusName")
        if PalObjects.get_BaseType(name_prop) != status_name:
            continue
        point_prop = row.get("StatusPoint")
        point = PalObjects.get_BaseType(point_prop)
        if (
            not isinstance(name_prop, dict)
            or name_prop.get("type") != "NameProperty"
            or not isinstance(point_prop, dict)
            or point_prop.get("type") != "IntProperty"
            or isinstance(point, bool)
            or not isinstance(point, int)
            or point < 0
            or result is not None
        ):
            raise ConsumableBonusStructureError(
                "PLAYER_ATTRIBUTE_STRUCTURE_UNSUPPORTED",
                "The regular player attribute structure is unsupported.",
            )
        result = point
    return result or 0


def player_consumable_bonus_view(player) -> dict[str, Any]:
    try:
        values = inspect_consumable_bonus_values(player._player_param)
        regular_values = {
            definition.key: regular_attribute_rank(
                player._player_param, definition.status_name
            )
            for definition in PLAYER_CONSUMABLE_BONUS_DEFINITIONS
        }
    except ConsumableBonusStructureError as error:
        return {
            "available": False,
            "reason": error.code,
            "reduce_only": False,
            "values": [],
        }
    result = []
    for definition in PLAYER_CONSUMABLE_BONUS_DEFINITIONS:
        regular = regular_values[definition.key]
        bonus = values[definition.key]
        result.append(
            {
                "key": definition.key,
                "value": bonus,
                "regular_rank": regular,
                "total_rank": regular + bonus,
                "maximum": max(0, definition.maximum_total - regular),
                "maximum_total": definition.maximum_total,
                "icon": definition.icon,
            }
        )
    return {
        "available": True,
        "reason": None,
        "reduce_only": False,
        "values": result,
    }
