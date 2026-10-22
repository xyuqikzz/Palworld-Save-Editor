"""Level serialization limits; these are not promises of game/MOD support."""

from typing import Any, Callable

from palworld_pal_editor.domain.errors import DomainError

REGULAR_LEVEL_MAX = 80
LEGACY_LEVEL_MAX = 100
BYTE_LEVEL_MAX = 255
EXPERIENCE_MAX = (1 << 63) - 1


def validate_experimental_mode(value: Any) -> None:
    if not isinstance(value, bool):
        raise DomainError(
            code="INVALID_FIELD_TYPE",
            message="experimental_level must be a boolean.",
            field="experimental_level",
            http_status=400,
        )


def resolve_level_experience(
    level: int,
    *,
    experimental: bool = False,
    experience: int | None = None,
    lookup: Callable[[int], int | None],
) -> int:
    validate_experimental_mode(experimental)
    maximum = BYTE_LEVEL_MAX if experimental else LEGACY_LEVEL_MAX
    if isinstance(level, bool) or not isinstance(level, int) or not 1 <= level <= maximum:
        raise DomainError(
            code="VALUE_OUT_OF_RANGE",
            message=f"Level must be between 1 and {maximum} for this editing mode.",
            field="level",
            http_status=400,
        )
    if experience is not None and (
        isinstance(experience, bool)
        or not isinstance(experience, int)
        or not 0 <= experience <= EXPERIENCE_MAX
    ):
        raise DomainError(
            code="VALUE_OUT_OF_RANGE",
            message="Experience must be a non-negative signed 64-bit integer.",
            field="experience",
            http_status=400,
        )
    if level > LEGACY_LEVEL_MAX:
        if experience is None:
            raise DomainError(
                code="MOD_EXPERIENCE_REQUIRED",
                message=(
                    "Experimental levels above 100 require the matching total "
                    "experience from your MOD. No experience curve is inferred."
                ),
                field="experience",
                http_status=400,
            )
        return experience
    value = lookup(level)
    if value is None:
        raise DomainError(
            code="COMPATIBILITY_FIELD_MISSING",
            message="No experience rule exists for this level.",
            field="level",
        )
    return value if experience is None else experience


def validate_level_property(prop: Any) -> None:
    if prop is not None and (
        not isinstance(prop, dict)
        or prop.get("type") != "ByteProperty"
        or not isinstance(prop.get("value"), dict)
        or prop["value"].get("type") != "None"
        or type(prop["value"].get("value")) is not int
        or not 0 <= prop["value"]["value"] <= BYTE_LEVEL_MAX
    ):
        raise DomainError(
            code="COMPATIBILITY_FIELD_MISSING",
            message="Level does not use the supported ByteProperty layout.",
            field="level",
        )
