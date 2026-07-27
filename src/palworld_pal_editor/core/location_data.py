from __future__ import annotations

import math
from typing import Any

from palworld_save_tools.archive import FArchiveReader
from palworld_save_tools.paltypes import (
    PALWORLD_CUSTOM_PROPERTIES,
    PALWORLD_TYPE_HINTS,
)


def read_transform_translation(transform: Any) -> dict[str, float] | None:
    """Read a verified Unreal Transform translation without changing the property."""
    if not isinstance(transform, dict):
        return None

    direct = transform.get("translation")
    if isinstance(direct, dict):
        return _finite_vector(direct)

    value = transform.get("value")
    if isinstance(value, dict):
        translation = value.get("Translation")
        if isinstance(translation, dict):
            return _finite_vector(translation.get("value"))

    if (
        transform.get("skip_type") != "StructProperty"
        or transform.get("struct_type") != "Transform"
        or not isinstance(value, bytes)
    ):
        return None

    try:
        reader = FArchiveReader(
            value,
            PALWORLD_TYPE_HINTS,
            PALWORLD_CUSTOM_PROPERTIES,
            debug=False,
            allow_nan=False,
        )
        properties = reader.properties_until_end(".SaveData.LastTransform")
        if not reader.eof():
            return None
    except Exception:
        return None

    translation = properties.get("Translation")
    if not isinstance(translation, dict):
        return None
    return _finite_vector(translation.get("value"))


def _finite_vector(value: Any) -> dict[str, float] | None:
    if not isinstance(value, dict):
        return None
    result: dict[str, float] = {}
    for key in ("x", "y", "z"):
        coordinate = value.get(key)
        if isinstance(coordinate, bool) or not isinstance(coordinate, (int, float)):
            return None
        number = float(coordinate)
        if not math.isfinite(number):
            return None
        result[key] = number
    return result
