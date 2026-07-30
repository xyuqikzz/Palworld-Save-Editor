from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from palworld_pal_editor.domain.models import SavePlatform, StorageSnapshot


class MigrationMode(StrEnum):
    FULL = "full"
    CHARACTER_ONLY = "character_only"


class MigrationStage(StrEnum):
    ANALYZING = "analyzing"
    BACKING_UP = "backing_up"
    STAGING = "staging"
    MIGRATING = "migrating"
    VALIDATING = "validating"
    COMMITTING = "committing"
    RELOADING = "reloading"
    COMPLETED = "completed"
    RECOVERED = "recovered"
    FAILED = "failed"


@dataclass(frozen=True)
class MigrationPlayer:
    player_uid: str
    instance_id: str
    name: str
    level: int | None
    platform_identity: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "player_uid": self.player_uid,
            "instance_id": self.instance_id,
            "name": self.name,
            "level": self.level,
            "platform_identity": self.platform_identity,
        }


@dataclass(frozen=True)
class MigrationSaveRef:
    platform: SavePlatform
    path: str | None = None
    source_id: str | None = None


@dataclass(frozen=True)
class MigrationRequest:
    mode: MigrationMode
    source: MigrationSaveRef
    target: MigrationSaveRef


@dataclass(frozen=True)
class PlayerMatchCandidate:
    source_player_uid: str
    source_instance_id: str
    target_player_uid: str | None
    target_instance_id: str | None
    evidence: str
    confidence: str
    auto_confirmed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_player_uid": self.source_player_uid,
            "source_instance_id": self.source_instance_id,
            "target_player_uid": self.target_player_uid,
            "target_instance_id": self.target_instance_id,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "auto_confirmed": self.auto_confirmed,
        }


@dataclass(frozen=True)
class PlayerIdentityMapping:
    source_player_uid: str
    source_instance_id: str
    target_player_uid: str
    target_instance_id: str
    evidence: str
    confirmed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_player_uid": self.source_player_uid,
            "source_instance_id": self.source_instance_id,
            "target_player_uid": self.target_player_uid,
            "target_instance_id": self.target_instance_id,
            "evidence": self.evidence,
            "confirmed": self.confirmed,
        }


@dataclass(frozen=True)
class MigrationSaveSummary:
    platform: SavePlatform
    display_name: str
    save_version: str
    players: tuple[MigrationPlayer, ...]
    counts: dict[str, int]
    capabilities: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform.value,
            "display_name": self.display_name,
            "save_version": self.save_version,
            "players": [player.to_dict() for player in self.players],
            "counts": dict(self.counts),
            "capabilities": dict(self.capabilities),
        }


@dataclass(frozen=True)
class MigrationPlan:
    plan_id: str
    revision: int
    mode: MigrationMode
    created_at: datetime
    expires_at: datetime
    source_snapshot: StorageSnapshot
    target_snapshot: StorageSnapshot
    source_summary: MigrationSaveSummary
    target_summary: MigrationSaveSummary
    player_candidates: tuple[PlayerMatchCandidate, ...]
    blockers: tuple[dict[str, Any], ...]
    warnings: tuple[dict[str, Any], ...]
    migration_scope: tuple[str, ...]
    overwritten_scope: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        def snapshot(value: StorageSnapshot) -> dict[str, Any]:
            return {
                "files": [
                    {
                        "path": item.relative_path.as_posix(),
                        "size": item.size,
                        "sha256": item.sha256,
                    }
                    for item in value.files
                ]
            }

        return {
            "plan_id": self.plan_id,
            "revision": self.revision,
            "mode": self.mode.value,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "source_snapshot": snapshot(self.source_snapshot),
            "target_snapshot": snapshot(self.target_snapshot),
            "source_summary": self.source_summary.to_dict(),
            "target_summary": self.target_summary.to_dict(),
            "player_candidates": [
                candidate.to_dict() for candidate in self.player_candidates
            ],
            "blockers": [dict(item) for item in self.blockers],
            "warnings": [dict(item) for item in self.warnings],
            "migration_scope": list(self.migration_scope),
            "overwritten_scope": list(self.overwritten_scope),
        }


@dataclass(frozen=True)
class MigrationResult:
    operation_id: str
    mode: MigrationMode
    status: str
    backup_path: str
    manifest_path: str
    written_files: tuple[str, ...]
    migrated_players: tuple[dict[str, str], ...]
    validation: dict[str, Any]
    recovery_status: str
    progress: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "mode": self.mode.value,
            "status": self.status,
            "backup_path": self.backup_path,
            "manifest_path": self.manifest_path,
            "written_files": list(self.written_files),
            "migrated_players": [dict(item) for item in self.migrated_players],
            "validation": dict(self.validation),
            "recovery_status": self.recovery_status,
            "progress": list(self.progress),
        }
