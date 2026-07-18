from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable
import uuid


@dataclass(frozen=True)
class ChangeEntry:
    change_id: str
    revision_before: int
    revision_after: int
    command: str
    target: dict[str, Any]
    before: dict[str, Any]
    after: dict[str, Any]
    affected_records: tuple[str, ...]
    warnings: tuple[dict[str, Any], ...] = ()
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @classmethod
    def create(
        cls,
        *,
        revision_before: int,
        command: str,
        target: dict[str, Any],
        before: dict[str, Any],
        after: dict[str, Any],
        affected_records: Iterable[str],
        warnings: Iterable[dict[str, Any]] = (),
    ) -> "ChangeEntry":
        return cls(
            change_id=str(uuid.uuid4()),
            revision_before=revision_before,
            revision_after=revision_before + 1,
            command=command,
            target=dict(target),
            before=dict(before),
            after=dict(after),
            affected_records=tuple(affected_records),
            warnings=tuple(dict(warning) for warning in warnings),
        )

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["affected_records"] = list(self.affected_records)
        value["warnings"] = [dict(warning) for warning in self.warnings]
        return value


class ChangeSet:
    def __init__(self) -> None:
        self._entries: list[ChangeEntry] = []
        self._baseline_revision = 0

    def __len__(self) -> int:
        return len(self._entries)

    def append(self, entry: ChangeEntry) -> None:
        expected = (
            self._entries[-1].revision_after
            if self._entries
            else self._baseline_revision
        )
        if entry.revision_before != expected:
            raise ValueError(
                f"Change revision is not contiguous: expected {expected}, "
                f"got {entry.revision_before}"
            )
        self._entries.append(entry)

    def view(self) -> list[dict[str, Any]]:
        return [entry.to_dict() for entry in self._entries]

    def mark_saved(self, through_revision: int) -> None:
        if self._entries and self._entries[-1].revision_after != through_revision:
            raise ValueError("Cannot clear a partially saved ChangeSet")
        self._entries.clear()
        self._baseline_revision = through_revision
