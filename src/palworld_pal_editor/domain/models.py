from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping


class SavePlatform(StrEnum):
    STEAM = "steam"
    XGP = "xgp"


@dataclass(frozen=True)
class SaveSource:
    platform: SavePlatform
    canonical_path: Path
    source_id: str
    display_name: str
    world_id: str | None = None
    updated_at: datetime | None = None
    status: str = "available"

    def to_public_dict(self) -> dict[str, Any]:
        updated_at = self.updated_at
        if updated_at is not None and updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        return {
            "sourceId": self.source_id,
            "platform": self.platform.value,
            "displayName": self.display_name,
            "worldId": self.world_id[:8].upper() if self.world_id else None,
            "updatedAt": updated_at.isoformat() if updated_at is not None else None,
            "status": self.status,
        }


@dataclass(frozen=True)
class LogicalSaveFile:
    relative_path: PurePosixPath
    physical_identity: str
    size: int
    sha256: str


@dataclass(frozen=True)
class StorageFileSnapshot:
    relative_path: PurePosixPath
    size: int
    mtime_ns: int
    sha256: str


@dataclass(frozen=True)
class StorageSnapshot:
    files: tuple[StorageFileSnapshot, ...]
    world_bindings: tuple[tuple[str, str], ...] = ()

    def by_path(self) -> dict[str, StorageFileSnapshot]:
        return {item.relative_path.as_posix(): item for item in self.files}


@dataclass
class OpenedSave:
    source: SaveSource
    workspace: Path
    logical_files: dict[str, LogicalSaveFile]
    snapshot: StorageSnapshot
    cleanup_required: bool
    storage_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StorageCommitRequest:
    opened: OpenedSave
    staged_workspace: Path
    changed_files: tuple[PurePosixPath, ...]
    expected_revision: int
    target_path: Path | None = None
    verify_file: Callable[[Path, str], Any] | None = None
    failure_hook: Callable[[str, dict[str, Any]], None] | None = None


@dataclass(frozen=True)
class StorageCommitResult:
    platform: SavePlatform
    written_files: tuple[PurePosixPath, ...]
    backup_path: Path | None
    manifest_path: Path | None
    source_reloaded: bool
    recovery_status: str = "not_needed"
    journal_path: Path | None = None
    manifest: tuple[dict[str, Any], ...] = ()


class ItemContainerType(StrEnum):
    COMMON = "COMMON"
    ESSENTIAL = "ESSENTIAL"
    WEAPON_LOADOUT = "WEAPON_LOADOUT"
    PLAYER_EQUIP_ARMOR = "PLAYER_EQUIP_ARMOR"
    FOOD_EQUIP = "FOOD_EQUIP"
    BASE_STORAGE = "BASE_STORAGE"
    GUILD_STORAGE = "GUILD_STORAGE"


class CharacterContainerType(StrEnum):
    AUTO = "AUTO"
    PARTY = "PARTY"
    PAL_STORAGE = "PAL_STORAGE"


INVENTORY_CONTAINER_FIELDS: dict[ItemContainerType, str] = {
    ItemContainerType.COMMON: "CommonContainerId",
    ItemContainerType.ESSENTIAL: "EssentialContainerId",
    ItemContainerType.WEAPON_LOADOUT: "WeaponLoadOutContainerId",
    ItemContainerType.PLAYER_EQUIP_ARMOR: "PlayerEquipArmorContainerId",
    ItemContainerType.FOOD_EQUIP: "FoodEquipContainerId",
}


@dataclass(frozen=True)
class Capability:
    readable: bool
    writable: bool
    reason: str | None = None
    evidence: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "readable": self.readable,
            "writable": self.writable,
            "reason": self.reason,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class SaveCompatibility:
    save_version: str
    field_aliases: dict[str, str]
    capabilities: dict[str, Capability]
    warnings: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "save_version": self.save_version,
            "field_aliases": dict(self.field_aliases),
            "capabilities": {
                name: capability.to_dict()
                for name, capability in self.capabilities.items()
            },
            "warnings": [dict(warning) for warning in self.warnings],
        }


@dataclass(frozen=True)
class SessionSummary:
    session_id: str
    revision: int
    source: str
    opened_at: datetime
    player_count: int
    pending_change_count: int
    platform: SavePlatform = SavePlatform.STEAM
    source_id: str | None = None
    source_display_name: str | None = None
    save_capabilities: Mapping[str, Any] = field(default_factory=dict)
    raw_json_pending: bool = False

    def to_dict(self) -> dict[str, Any]:
        opened_at = self.opened_at
        if opened_at.tzinfo is None:
            opened_at = opened_at.replace(tzinfo=timezone.utc)
        return {
            "session_id": self.session_id,
            "revision": self.revision,
            "source": self.source,
            "opened_at": opened_at.isoformat(),
            "player_count": self.player_count,
            "pending_change_count": self.pending_change_count,
            "platform": self.platform.value,
            "sourceId": self.source_id,
            "sourceDisplayName": self.source_display_name,
            "saveCapabilities": dict(self.save_capabilities),
            "raw_json_pending": self.raw_json_pending,
        }


@dataclass(frozen=True)
class PlayerSummary:
    player_id: str
    instance_id: str
    name: str
    level: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "player_id": self.player_id,
            "instance_id": self.instance_id,
            "name": self.name,
            "level": self.level,
        }


@dataclass(frozen=True)
class ItemCatalogEntry:
    static_id: str
    names: dict[str, str]
    descriptions: dict[str, str]
    category: str
    rarity: int | None
    icon: str | None
    max_stack: int | None
    allowed_containers: tuple[ItemContainerType, ...]
    dynamic_kind: str
    rule_status: str
    rule_source: str | None = None
    rule_version: str | None = None
    disabled: bool = False

    def localized_name(self, locale: str) -> str:
        return self.names.get(locale) or self.names.get("en") or self.static_id

    def localized_description(self, locale: str) -> str:
        return self.descriptions.get(locale) or self.descriptions.get("en") or ""

    def to_dict(self, locale: str = "en") -> dict[str, Any]:
        return {
            "static_id": self.static_id,
            "name": self.localized_name(locale),
            "description": self.localized_description(locale),
            "category": self.category,
            "rarity": self.rarity,
            "icon": self.icon,
            "max_stack": self.max_stack,
            "allowed_containers": [value.value for value in self.allowed_containers],
            "dynamic_kind": self.dynamic_kind,
            "rule_status": self.rule_status,
            "rule_source": self.rule_source,
            "rule_version": self.rule_version,
            "disabled": self.disabled,
        }


@dataclass(frozen=True)
class ItemSlotView:
    slot_index: int
    state: str
    static_id: str | None = None
    count: int | None = None
    dynamic_id: str | None = None
    dynamic_kind: str = "none"
    name: str | None = None
    category: str | None = None
    rarity: int | None = None
    icon: str | None = None

    def to_dict(self) -> dict[str, Any]:
        if self.state == "empty":
            return {"slot_index": self.slot_index, "state": "empty"}
        return {
            "slot_index": self.slot_index,
            "state": "occupied",
            "item": {
                "static_id": self.static_id,
                "count": self.count,
                "dynamic_id": self.dynamic_id,
                "dynamic_kind": self.dynamic_kind,
                "name": self.name,
                "category": self.category or "unknown",
                "rarity": self.rarity,
                "icon": self.icon,
            },
        }


@dataclass(frozen=True)
class ItemContainerView:
    container_type: ItemContainerType
    capacity: int | None
    status: str
    slots: tuple[ItemSlotView, ...]
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "container_type": self.container_type.value,
            "capacity": self.capacity,
            "status": self.status,
            "reason": self.reason,
            "slots": [slot.to_dict() for slot in self.slots],
        }


@dataclass(frozen=True)
class PlayerInventoryView:
    player_id: str
    session_revision: int
    containers: tuple[ItemContainerView, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "player_id": self.player_id,
            "session_revision": self.session_revision,
            "containers": [container.to_dict() for container in self.containers],
        }


@dataclass(frozen=True)
class SaveResult:
    revision: int
    backup_path: str | None
    staging_path: str | None
    written_files: tuple[str, ...]
    manifest: tuple[dict[str, Any], ...]
    staged_reload_verified: bool
    target_reload_verified: bool
    recovered: bool | None = None
    platform: str = SavePlatform.STEAM.value
    manifest_path: str | None = None
    source_reloaded: bool = True
    recovery_status: str = "not_needed"
    journal_path: str | None = None
    cloud_sync_verified: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "revision": self.revision,
            "backup_path": self.backup_path,
            "staging_path": self.staging_path,
            "written_files": list(self.written_files),
            "manifest": [dict(item) for item in self.manifest],
            "staged_reload_verified": self.staged_reload_verified,
            "target_reload_verified": self.target_reload_verified,
            "recovered": self.recovered,
            "platform": self.platform,
            "manifest_path": self.manifest_path,
            "source_reloaded": self.source_reloaded,
            "recovery_status": self.recovery_status,
            "journal_path": self.journal_path,
            "cloud_sync_verified": self.cloud_sync_verified,
        }
