from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field
from typing import Any


WGS_ERROR_CODES = frozenset(
    {
        "WGS_NOT_FOUND",
        "WGS_USER_AMBIGUOUS",
        "WGS_INDEX_UNSUPPORTED",
        "WGS_CONTAINER_INCOMPLETE",
        "WGS_WORLD_AMBIGUOUS",
        "WGS_SOURCE_CHANGED",
        "WGS_GAME_RUNNING",
        "WGS_BACKUP_FAILED",
        "WGS_STAGE_FAILED",
        "WGS_COMMIT_FAILED",
        "WGS_RECOVERY_FAILED",
        "WGS_RELOAD_FAILED",
        "WGS_CLOUD_SYNC_UNVERIFIED",
    }
)


@dataclass(eq=False)
class DomainError(Exception):
    """Expected, machine-readable rejection from a save-editor Interface."""

    code: str
    message: str
    field: str | None = None
    details: dict[str, Any] = dataclass_field(default_factory=dict)
    retryable: bool = False
    http_status: int = 422

    def __post_init__(self) -> None:
        Exception.__init__(self, self.message)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "code": self.code,
            "retryable": self.retryable,
        }
        if self.field is not None:
            result["field"] = self.field
        if self.details:
            result["details"] = self.details
        return result


def stale_revision(expected: int, actual: int) -> DomainError:
    return DomainError(
        code="STALE_REVISION",
        message="The save session changed; reload before retrying.",
        field="expected_revision",
        details={"expected": expected, "actual": actual},
        retryable=True,
        http_status=409,
    )
