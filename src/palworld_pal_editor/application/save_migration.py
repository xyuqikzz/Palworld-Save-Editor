from __future__ import annotations

import contextlib
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import io
import os
from pathlib import Path
import re
import shutil
from threading import RLock
from typing import Any, Callable, Iterable
import uuid

from palworld_save_tools.archive import UUID
from palworld_save_tools.palsav import compress_gvas_to_sav, decompress_sav_to_gvas

from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.application.dps_migration import (
    import_character_dps,
    rewrite_full_dps_tree,
    validate_dps_tree,
)
from palworld_pal_editor.core.character_index import CharacterIndex
from palworld_pal_editor.core.container_data import ContainerData
from palworld_pal_editor.core.dynamic_item_data import DynamicItemData
from palworld_pal_editor.core.item_container_data import ItemContainerData
from palworld_pal_editor.core.pal_entity import PalEntity
from palworld_pal_editor.core.pal_objects import PalObjects, UUID2HexStr, toUUID
from palworld_pal_editor.core.save_manager import (
    MAIN_SKIP_PROPERTIES,
    PLAYER_SKIP_PROPERTIES,
    SaveManager,
)
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.domain.migration import (
    MigrationMode,
    MigrationPlan,
    MigrationPlayer,
    MigrationRequest,
    MigrationResult,
    MigrationSaveRef,
    MigrationSaveSummary,
    MigrationStage,
    PlayerIdentityMapping,
    PlayerMatchCandidate,
)
from palworld_pal_editor.domain.models import (
    SavePlatform,
    SaveSource,
    StorageSnapshot,
)
from palworld_pal_editor.storage.discovery import SOURCE_CATALOG
from palworld_pal_editor.storage.migration_transaction import (
    MigrationPreparedBackup,
    MigrationTreeTransaction,
)
from palworld_pal_editor.storage.steam import make_steam_source, snapshot_tree
from palworld_pal_editor.storage.xgp import XgpWgsAdapter


PLAN_TTL = timedelta(minutes=30)
_PLAYER_UID_FIELDS = frozenset(
    {
        "playeruid",
        "player_uid",
        "ownerplayeruid",
        "owner_player_uid",
        "oldownerplayeruids",
        "old_owner_player_uids",
        "adminplayeruid",
        "admin_player_uid",
        "lastguildnamemodifierplayeruid",
        "last_guild_name_modifier_player_uid",
        "lastnicknamemodifierplayeruid",
        "sellerplayeruid",
        "seller_player_uid",
        "private_lock_player_uid",
        "build_player_uid",
    }
)
_ZERO_UUID = "00000000-0000-0000-0000-000000000000"
_OPERATION_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")


@dataclass
class _StoredPlan:
    plan: MigrationPlan
    source: SaveSource
    target: SaveSource


def validate_distinct_paths(source: Path, target: Path) -> None:
    source = source.resolve()
    target = target.resolve()
    try:
        same = os.path.samefile(source, target)
    except OSError:
        same = os.path.normcase(str(source)) == os.path.normcase(str(target))
    if same or source in target.parents or target in source.parents:
        raise DomainError(
            code="MIGRATION_SAME_SOURCE_TARGET",
            message="Source and target saves must be distinct, non-overlapping locations.",
            details={"phase": "analyzing"},
            http_status=400,
        )


def build_player_candidates(
    source_players: tuple[MigrationPlayer, ...],
    target_players: tuple[MigrationPlayer, ...],
) -> tuple[PlayerMatchCandidate, ...]:
    target_by_platform: dict[str, list[MigrationPlayer]] = {}
    target_by_name: dict[str, list[MigrationPlayer]] = {}
    source_name_count: dict[str, int] = {}
    for player in target_players:
        if player.platform_identity:
            target_by_platform.setdefault(player.platform_identity, []).append(player)
        if player.name.strip():
            target_by_name.setdefault(player.name.strip().casefold(), []).append(player)
    for player in source_players:
        if player.name.strip():
            key = player.name.strip().casefold()
            source_name_count[key] = source_name_count.get(key, 0) + 1

    result: list[PlayerMatchCandidate] = []
    for source in source_players:
        target: MigrationPlayer | None = None
        evidence = "manual_required"
        confidence = "none"
        if source.platform_identity:
            matches = target_by_platform.get(source.platform_identity, [])
            if len(matches) == 1:
                target = matches[0]
                evidence = "platform_identity"
                confidence = "high"
        name_key = source.name.strip().casefold()
        if target is None and name_key:
            matches = target_by_name.get(name_key, [])
            if source_name_count.get(name_key) == 1 and len(matches) == 1:
                target = matches[0]
                evidence = "unique_name"
                confidence = "medium"
            elif matches:
                evidence = "ambiguous_name"
                confidence = "none"
        if (
            target is None
            and len(source_players) == 1
            and len(target_players) == 1
        ):
            target = target_players[0]
            evidence = "single_player"
            confidence = "low"
        result.append(
            PlayerMatchCandidate(
                source_player_uid=source.player_uid,
                source_instance_id=source.instance_id,
                target_player_uid=target.player_uid if target else None,
                target_instance_id=target.instance_id if target else None,
                evidence=evidence,
                confidence=confidence,
                auto_confirmed=target is not None,
            )
        )
    return tuple(result)


class SaveMigration:
    """Two-save analysis and fail-closed migration transaction."""

    def __init__(
        self,
        *,
        transaction_factory: Callable[[], MigrationTreeTransaction] | None = None,
        progress_callback: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self._plans: dict[str, _StoredPlan] = {}
        self._results: dict[tuple[str, str], MigrationResult] = {}
        self._operations_in_progress: set[tuple[str, str]] = set()
        self._operation_progress: dict[
            tuple[str, str],
            dict[str, Any],
        ] = {}
        self._lock = RLock()
        self._transaction_factory = transaction_factory or MigrationTreeTransaction
        self._progress_callback = progress_callback

    def analyze(self, request: MigrationRequest) -> MigrationPlan:
        self._progress(MigrationStage.ANALYZING)
        source = self._resolve_ref(request.source, field="source")
        target = self._resolve_ref(request.target, field="target")
        validate_distinct_paths(source.canonical_path, target.canonical_path)
        source_session: SaveSession | None = None
        target_session: SaveSession | None = None
        try:
            source_session = self._open(source, field="source")
            target_session = self._open(target, field="target")
            source_summary = self._summary(source_session)
            target_summary = self._summary(target_session)
            blockers: list[dict[str, Any]] = []
            warnings: list[dict[str, Any]] = [
                {
                    "code": "MIGRATION_OFFLINE_VALIDATION_ONLY",
                    "message": (
                        "The editor can verify offline structure only; game load, "
                        "restart persistence, and cloud synchronization remain unverified."
                    ),
                }
            ]
            if target.platform is SavePlatform.XGP:
                blockers.append(
                    {
                        "code": "MIGRATION_WGS_TARGET_UNSUPPORTED",
                        "message": (
                            "The current WGS adapter cannot safely commit a complete "
                            "logical file-set replacement."
                        ),
                    }
                )
            if source_summary.save_version == "unknown" or (
                target_summary.save_version == "unknown"
            ):
                blockers.append(
                    {
                        "code": "MIGRATION_VERSION_UNSUPPORTED",
                        "message": "One selected save has no supported version evidence.",
                    }
                )
            elif source_summary.save_version != target_summary.save_version:
                blockers.append(
                    {
                        "code": "MIGRATION_VERSION_UNSUPPORTED",
                        "message": (
                            "The selected saves use different versions and no "
                            "verified migration upgrade path is available."
                        ),
                    }
                )
            try:
                validate_dps_tree(source_session.workspace)
                if request.mode is MigrationMode.CHARACTER_ONLY:
                    validate_dps_tree(target_session.workspace)
            except DomainError as error:
                if error.code != "MIGRATION_DPS_UNSUPPORTED":
                    raise
                blockers.append(
                    {
                        "code": error.code,
                        "message": error.message,
                        "details": dict(error.details),
                    }
                )
            now = datetime.now(timezone.utc)
            plan = MigrationPlan(
                plan_id=str(uuid.uuid4()),
                revision=1,
                mode=request.mode,
                created_at=now,
                expires_at=now + PLAN_TTL,
                source_snapshot=self._snapshot_for_migration(source_session),
                target_snapshot=self._snapshot_for_target(target_session),
                source_summary=source_summary,
                target_summary=target_summary,
                player_candidates=build_player_candidates(
                    source_summary.players,
                    target_summary.players,
                ),
                blockers=tuple(blockers),
                warnings=tuple(warnings),
                migration_scope=(
                    (
                        "source_world",
                        "source_guilds",
                        "source_bases",
                        "source_buildings",
                        "source_containers",
                        "source_pals",
                        "source_dimensional_pal_storage",
                        "all_source_players",
                    )
                    if request.mode is MigrationMode.FULL
                    else (
                        "selected_player_progress",
                        "selected_player_inventory",
                        "selected_player_party",
                        "selected_player_palbox",
                        "selected_player_dimensional_pal_storage",
                    )
                ),
                overwritten_scope=(
                    ("target_world", "all_target_players")
                    if request.mode is MigrationMode.FULL
                    else ("selected_target_players",)
                ),
            )
            with self._lock:
                self._plans[plan.plan_id] = _StoredPlan(plan, source, target)
            return plan
        finally:
            if source_session is not None:
                source_session.close()
            if target_session is not None:
                target_session.close()

    def execute(
        self,
        plan_id: str,
        mappings: tuple[PlayerIdentityMapping, ...],
        operation_id: str,
    ) -> MigrationResult:
        self.validate_operation_id(operation_id)
        operation_key = (plan_id, operation_id)
        owned_stage: Path | None = None
        prepared_backup: MigrationPreparedBackup | None = None
        with self._lock:
            previous = self._results.get(operation_key)
            if previous is not None:
                return previous
            if operation_key in self._operations_in_progress:
                raise DomainError(
                    code="MIGRATION_OPERATION_IN_PROGRESS",
                    message="This migration operation is already in progress.",
                    retryable=True,
                    http_status=409,
                )
            stored = self._plans.get(plan_id)
            if stored is None:
                raise DomainError(
                    code="MIGRATION_PLAN_STALE",
                    message="The migration plan no longer exists.",
                    retryable=True,
                    http_status=409,
                )
            self._operations_in_progress.add(operation_key)
        try:
            if datetime.now(timezone.utc) >= stored.plan.expires_at:
                raise DomainError(
                    code="MIGRATION_PLAN_STALE",
                    message="The migration plan expired; analyze both saves again.",
                    retryable=True,
                    http_status=409,
                )
            if stored.plan.blockers:
                blocker = stored.plan.blockers[0]
                raise DomainError(
                    code=str(blocker["code"]),
                    message=str(blocker["message"]),
                    details={"blockers": list(stored.plan.blockers)},
                    http_status=409,
                )
            source_session = self._open(stored.source, field="source")
            target_session = self._open(stored.target, field="target")
            try:
                self._require_current_snapshot(
                    source_session,
                    stored.plan.source_snapshot,
                    "MIGRATION_SOURCE_CHANGED",
                )
                self._require_current_snapshot(
                    target_session,
                    stored.plan.target_snapshot,
                    "MIGRATION_TARGET_CHANGED",
                    complete_tree=True,
                )
                validated = self.validate_mappings(
                    stored.plan.mode,
                    mappings,
                    source_players={
                        item.player_uid: item
                        for item in stored.plan.source_summary.players
                    },
                    target_players={
                        item.player_uid: item
                        for item in stored.plan.target_summary.players
                    },
                )
                target_path = stored.target.canonical_path.resolve()
                if stored.target.platform is not SavePlatform.STEAM:
                    raise DomainError(
                        code="MIGRATION_WGS_TARGET_UNSUPPORTED",
                        message=(
                            "The current WGS adapter cannot safely commit this "
                            "logical file-set replacement."
                        ),
                        http_status=409,
                    )
                transaction = self._transaction_factory()
                prepared_backup = transaction.prepare_backup(
                    target=target_path,
                    expected_target=stored.plan.target_snapshot,
                    operation_id=operation_id,
                    progress_callback=lambda stage: self._progress(
                        MigrationStage(stage),
                        operation_key,
                    ),
                )
                stage = (
                    target_path.parent
                    / (
                        f".{target_path.name}.migration-staging-"
                        f"{operation_id}"
                    )
                )
                if stage.exists():
                    raise DomainError(
                        code="MIGRATION_STAGE_FAILED",
                        message="The migration staging directory already exists.",
                        details={"phase": "staging"},
                        http_status=500,
                    )
                owned_stage = stage
                self._progress(MigrationStage.STAGING, operation_key)
                authority = (
                    source_session
                    if stored.plan.mode is MigrationMode.FULL
                    else target_session
                )
                self._copy_snapshot_tree(
                    authority.workspace,
                    self._snapshot_for_migration(authority),
                    stage,
                )
                self._progress(MigrationStage.MIGRATING, operation_key)
                if stored.plan.mode is MigrationMode.FULL:
                    self._migrate_full(stage, validated)
                else:
                    self._migrate_characters(
                        source_session,
                        stage,
                        validated,
                    )
                self._progress(MigrationStage.VALIDATING, operation_key)
                staged_session = SaveSession.open(
                    stage,
                    manager=SaveManager.create_isolated(),
                )
                try:
                    self._validate_staged(
                        stored.plan,
                        staged_session,
                        validated,
                    )
                finally:
                    staged_session.close()
                staged_snapshot = snapshot_tree(stage, reject_symlinks=True)
                written_files = self._changed_files(
                    stored.plan.target_snapshot,
                    staged_snapshot,
                )

                def validate_committed(_target: Path) -> None:
                    self._progress(MigrationStage.RELOADING, operation_key)
                    reloaded = SaveSession.open(
                        target_path,
                        manager=SaveManager.create_isolated(),
                    )
                    try:
                        self._validate_staged(
                            stored.plan,
                            reloaded,
                            validated,
                        )
                    finally:
                        reloaded.close()

                committed = transaction.commit(
                    target=target_path,
                    staged=stage,
                    expected_target=stored.plan.target_snapshot,
                    operation_id=operation_id,
                    prepared_backup=prepared_backup,
                    progress_callback=lambda stage: self._progress(
                        MigrationStage(stage),
                        operation_key,
                    ),
                    post_commit_validator=validate_committed,
                )
                self._progress(MigrationStage.COMPLETED, operation_key)
                progress = tuple(
                    self._operation_progress[operation_key]["progress"]
                )
                result = MigrationResult(
                    operation_id=operation_id,
                    mode=stored.plan.mode,
                    status="completed",
                    backup_path=committed.backup_path,
                    manifest_path=committed.manifest_path,
                    written_files=written_files,
                    migrated_players=tuple(
                        {
                            "source_player_uid": item.source_player_uid,
                            "target_player_uid": item.target_player_uid,
                            "instance_id": (
                                item.source_instance_id
                                if stored.plan.mode is MigrationMode.FULL
                                else item.target_instance_id
                            ),
                        }
                        for item in validated
                    ),
                    validation={
                        "level": "OFFLINE_VALIDATED",
                        "staged_reload": True,
                        "target_reload": True,
                        "game_load_validated": False,
                        "player_access_validated": False,
                        "restart_persistence_validated": False,
                        "wgs_cloud_sync_validated": False,
                    },
                    recovery_status=committed.recovery_status,
                    progress=progress,
                )
                with self._lock:
                    self._results[operation_key] = result
                return result
            finally:
                source_session.close()
                target_session.close()
        except DomainError as error:
            self._progress(MigrationStage.FAILED, operation_key)
            if prepared_backup is not None:
                error.details.setdefault(
                    "backup_path",
                    str(prepared_backup.backup_path),
                )
                error.details.setdefault(
                    "manifest_path",
                    str(prepared_backup.manifest_path),
                )
            raise
        finally:
            if owned_stage is not None and owned_stage.exists():
                expected_prefix = (
                    f".{stored.target.canonical_path.resolve().name}."
                    "migration-staging-"
                )
                if (
                    owned_stage.resolve().parent
                    == stored.target.canonical_path.resolve().parent
                    and owned_stage.name.startswith(expected_prefix)
                ):
                    shutil.rmtree(owned_stage)
            with self._lock:
                self._operations_in_progress.discard(operation_key)

    def operation_status(
        self,
        plan_id: str,
        operation_id: str,
    ) -> dict[str, Any]:
        operation_key = (plan_id, operation_id)
        with self._lock:
            progress = self._operation_progress.get(operation_key)
            result = self._results.get(operation_key)
            if progress is None and result is None:
                raise DomainError(
                    code="MIGRATION_PLAN_STALE",
                    message="The migration operation is not available.",
                    retryable=True,
                    http_status=404,
                )
            return {
                "plan_id": plan_id,
                "operation_id": operation_id,
                "stage": (
                    result.status
                    if result is not None
                    else progress["stage"]
                ),
                "progress": (
                    list(result.progress)
                    if result is not None
                    else list(progress["progress"])
                ),
                "completed": result is not None,
            }

    @staticmethod
    def validate_operation_id(operation_id: str) -> None:
        if (
            operation_id != operation_id.strip()
            or _OPERATION_ID_PATTERN.fullmatch(operation_id) is None
        ):
            raise DomainError(
                code="MIGRATION_OPERATION_INVALID",
                message="A valid migration operation ID is required.",
                http_status=400,
            )

    @staticmethod
    def validate_mappings(
        mode: MigrationMode,
        mappings: tuple[PlayerIdentityMapping, ...],
        *,
        source_players: dict[str, MigrationPlayer],
        target_players: dict[str, MigrationPlayer],
    ) -> tuple[PlayerIdentityMapping, ...]:
        if not mappings and mode is not MigrationMode.FULL:
            raise DomainError(
                code="MIGRATION_PLAYER_MAPPING_REQUIRED",
                message="At least one confirmed player mapping is required.",
                http_status=400,
            )
        source_ids: set[str] = set()
        target_ids: set[str] = set()
        for mapping in mappings:
            if not mapping.confirmed:
                raise DomainError(
                    code="MIGRATION_PLAYER_MAPPING_REQUIRED",
                    message="Every selected player mapping must be confirmed.",
                    http_status=400,
                )
            source = source_players.get(mapping.source_player_uid)
            target = target_players.get(mapping.target_player_uid)
            if target is None:
                raise DomainError(
                    code="MIGRATION_PLAYER_TARGET_MISSING",
                    message="A mapped target player no longer exists.",
                    details={"target_player_uid": mapping.target_player_uid},
                    http_status=409,
                )
            if source is None or source.instance_id != mapping.source_instance_id:
                raise DomainError(
                    code="MIGRATION_PLAYER_MAPPING_REQUIRED",
                    message="A mapped source identity does not match the analyzed save.",
                    http_status=409,
                )
            if target.instance_id != mapping.target_instance_id:
                raise DomainError(
                    code="MIGRATION_PLAYER_TARGET_MISSING",
                    message="A mapped target identity changed after analysis.",
                    http_status=409,
                )
            if mapping.source_player_uid in source_ids or (
                mapping.target_player_uid in target_ids
            ):
                raise DomainError(
                    code="MIGRATION_PLAYER_MAPPING_DUPLICATE",
                    message="Player mappings must be one-to-one.",
                    http_status=400,
                )
            source_ids.add(mapping.source_player_uid)
            target_ids.add(mapping.target_player_uid)
        return mappings

    def _migrate_full(
        self,
        stage: Path,
        mappings: tuple[PlayerIdentityMapping, ...],
    ) -> None:
        session = SaveSession.open(stage, manager=SaveManager.create_isolated())
        try:
            manager = session.manager
            for player_id in list(manager.player_mapping):
                session.load_player(player_id)
            uid_mapping = {
                item.source_player_uid: item.target_player_uid for item in mappings
            }
            self._rewrite_group_player_handles(
                manager.gvas_file.properties,
                uid_mapping,
            )
            self._rewrite_known_player_uids(
                manager.gvas_file.properties,
                uid_mapping,
            )
            for player in manager.player_mapping.values():
                self._rewrite_known_player_uids(
                    player._gvas_file.properties,
                    uid_mapping,
                )
            players_dir = stage / "Players"
            for item in mappings:
                old_path = players_dir / f"{UUID2HexStr(item.source_player_uid)}.sav"
                new_path = players_dir / f"{UUID2HexStr(item.target_player_uid)}.sav"
                if old_path != new_path and old_path.exists():
                    old_path.unlink()
            self._serialize_manager(manager, stage)
            self._audit_removed_player_uids(stage, uid_mapping, manager)
            rewrite_full_dps_tree(stage, uid_mapping)
        except DomainError:
            raise
        except Exception as error:
            raise DomainError(
                code="MIGRATION_STAGE_FAILED",
                message="The full migration could not be serialized safely.",
                details={"phase": "migrating"},
                http_status=500,
            ) from error
        finally:
            session.close()

    def _migrate_characters(
        self,
        source_session: SaveSession,
        stage: Path,
        mappings: tuple[PlayerIdentityMapping, ...],
    ) -> None:
        target_session = SaveSession.open(stage, manager=SaveManager.create_isolated())
        try:
            source_manager = source_session.manager
            target_manager = target_session.manager
            dps_imports: list[tuple[PlayerIdentityMapping, str]] = []
            for mapping in mappings:
                source = source_session.load_player(mapping.source_player_uid)
                target = target_session.load_player(mapping.target_player_uid)
                target_dynamic_issues = (
                    target_manager.dynamic_item_data.issue_fingerprints()
                )
                target_item_ids = target.resolve_item_container_ids()
                target_otomo_id = target.OtomoCharacterContainerId
                target_storage_id = target.PalStorageContainerId
                source_item_ids = source.resolve_item_container_ids()
                source_personal_pals = self._personal_pals(
                    source_manager,
                    source,
                )
                target_personal_pals = self._personal_pals(
                    target_manager,
                    target,
                )

                source_equip_ids = self._pal_equip_container_ids(
                    source_personal_pals
                )
                target_equip_ids = self._pal_equip_container_ids(
                    target_personal_pals
                )
                source_personal_item_ids = {
                    str(value)
                    for value in source_item_ids.values()
                    if value is not None
                } | set(source_equip_ids)
                target_personal_item_ids = {
                    str(value)
                    for value in target_item_ids.values()
                    if value is not None
                } | set(target_equip_ids)
                self._require_character_subgraph_supported(
                    source_manager,
                    source,
                    source_personal_pals,
                    source_personal_item_ids,
                    target_manager,
                    target,
                    target_personal_pals,
                    target_personal_item_ids,
                )

                source_dynamic_ids = self._personal_dynamic_ids(
                    source_manager,
                    source_personal_item_ids,
                )
                target_dynamic_ids = self._personal_dynamic_ids(
                    target_manager,
                    target_personal_item_ids,
                )
                self._require_personal_dynamic_ownership(
                    target_manager,
                    target_personal_item_ids,
                    target_dynamic_ids,
                )

                target_group = (
                    target_manager.group_data.get_group(target.group_id)
                    if target.group_id is not None
                    else None
                )
                source_group_id = (
                    None if source.group_id is None else str(source.group_id)
                )
                target_group_id = (
                    None if target_group is None else str(target_group.group_id)
                )

                target_old_pal_ids = {
                    str(pal.InstanceId) for pal in target_personal_pals
                }
                used_pal_ids = {
                    str(PalObjects.get_BaseType(entity.get("key", {}).get("InstanceId")))
                    for entity in target_manager._entities_list
                    if PalObjects.get_BaseType(entity.get("key", {}).get("InstanceId"))
                    is not None
                } - target_old_pal_ids
                pal_mapping = self._allocate_uuid_mapping(
                    (str(pal.InstanceId) for pal in source_personal_pals),
                    used_pal_ids,
                )

                all_target_container_ids = (
                    set(target_manager.item_container_data.container_map)
                    | set(target_manager.container_data.container_map)
                )
                removable_target_equip_ids = {
                    container_id
                    for container_id in target_equip_ids
                    if target_manager.item_container_data.get(container_id) is not None
                }
                self._require_equip_containers_unshared(
                    target_manager,
                    target_personal_pals,
                    removable_target_equip_ids,
                )
                used_container_ids = (
                    all_target_container_ids - removable_target_equip_ids
                )
                container_mapping: dict[str, str] = {}
                for field, source_id in source_item_ids.items():
                    target_id = target_item_ids.get(field)
                    if source_id is None or target_id is None:
                        raise DomainError(
                            code="MIGRATION_REFERENCE_UNSUPPORTED",
                            message="A player inventory container layout is incomplete.",
                            details={"field": field},
                            http_status=409,
                        )
                    container_mapping[str(source_id)] = str(target_id)
                for source_id, target_id in (
                    (source.OtomoCharacterContainerId, target_otomo_id),
                    (source.PalStorageContainerId, target_storage_id),
                ):
                    if source_id is None or target_id is None:
                        raise DomainError(
                            code="MIGRATION_REFERENCE_UNSUPPORTED",
                            message="A player Pal container layout is incomplete.",
                            http_status=409,
                        )
                    container_mapping[str(source_id)] = str(target_id)
                equip_mapping = self._allocate_uuid_mapping(
                    source_equip_ids,
                    used_container_ids,
                )
                container_mapping.update(equip_mapping)

                target_dynamic_records = set(
                    target_manager.dynamic_item_data.records
                )
                dynamic_mapping = self._allocate_uuid_mapping(
                    source_dynamic_ids,
                    target_dynamic_records,
                )

                identity_mapping = {
                    mapping.source_player_uid: mapping.target_player_uid,
                    mapping.source_instance_id: mapping.target_instance_id,
                    **container_mapping,
                    **pal_mapping,
                    **dynamic_mapping,
                }
                if source_group_id is not None:
                    identity_mapping[source_group_id] = (
                        target_group_id or _ZERO_UUID
                    )
                dps_imports.append((mapping, str(target_storage_id)))

                for pal in target_personal_pals:
                    if not target_manager.delete_pal(str(pal.InstanceId)):
                        raise DomainError(
                            code="MIGRATION_REFERENCE_UNSUPPORTED",
                            message="The target personal Pal graph could not be removed safely.",
                            details={"pal_instance_id": str(pal.InstanceId)},
                            http_status=409,
                        )
                self._remove_item_containers(
                    target_manager,
                    removable_target_equip_ids,
                )

                target._player_param.clear()
                target._player_param.update(deepcopy(source._player_param))
                target._gvas_file = deepcopy(source._gvas_file)
                target._gvas_compression_times = source._gvas_compression_times
                target._player_save_data = target._gvas_file.properties["SaveData"][
                    "value"
                ]
                identity = target._player_save_data.get("IndividualId", {}).get(
                    "value", {}
                )
                self._set_uuid(identity.get("PlayerUId"), mapping.target_player_uid)
                self._set_uuid(identity.get("InstanceId"), mapping.target_instance_id)

                for field, source_id in source_item_ids.items():
                    target_id = target_item_ids.get(field)
                    source_container = source_manager.item_container_data.get(source_id)
                    target_container = target_manager.item_container_data.get(target_id)
                    if source_container is None or target_container is None:
                        raise DomainError(
                            code="MIGRATION_REFERENCE_UNSUPPORTED",
                            message="A player inventory container cannot be resolved.",
                            details={"field": field},
                            http_status=409,
                        )
                    target_container._container_obj["value"] = deepcopy(
                        source_container._container_obj["value"]
                    )
                    self._rewrite_uuid_values(
                        target_container._container_obj["value"],
                        identity_mapping,
                    )

                target_item_values = self._item_container_values(target_manager)
                for source_equip_id, target_equip_id in equip_mapping.items():
                    source_container = source_manager.item_container_data.get(
                        source_equip_id
                    )
                    if source_container is None:
                        continue
                    cloned_container = deepcopy(source_container._container_obj)
                    self._set_uuid(
                        cloned_container.get("key", {}).get("ID"),
                        target_equip_id,
                    )
                    self._rewrite_uuid_values(
                        cloned_container,
                        identity_mapping,
                    )
                    target_item_values.append(cloned_container)

                for source_id, target_id in (
                    (source.OtomoCharacterContainerId, target_otomo_id),
                    (source.PalStorageContainerId, target_storage_id),
                ):
                    source_container = source_manager.container_data.get_container(
                        source_id
                    )
                    target_container = target_manager.container_data.get_container(
                        target_id
                    )
                    if source_container is None or target_container is None:
                        raise DomainError(
                            code="MIGRATION_REFERENCE_UNSUPPORTED",
                            message="A player Pal container cannot be resolved.",
                            http_status=409,
                        )
                    target_container._container_obj["value"] = deepcopy(
                        source_container._container_obj["value"]
                    )
                    self._rewrite_uuid_values(
                        target_container._container_obj["value"],
                        identity_mapping,
                    )

                self._rewrite_uuid_values(
                    target._player_param,
                    identity_mapping,
                )
                self._rewrite_uuid_values(
                    target._gvas_file.properties,
                    identity_mapping,
                )

                target_manager.container_data = ContainerData(
                    target_manager.gvas_file
                )
                target_manager.item_container_data = ItemContainerData(
                    target_manager.gvas_file
                )
                target_manager.dynamic_item_data = DynamicItemData(
                    target_manager.gvas_file,
                    target_manager.item_container_data,
                    reference_scope_verifier=(
                        target_manager._audit_dynamic_item_reference_scope
                    ),
                )
                for old_dynamic_id in sorted(target_dynamic_ids):
                    if old_dynamic_id in target_manager.dynamic_item_data.records:
                        target_manager.dynamic_item_data.delete_unreferenced(
                            old_dynamic_id
                        )
                for source_dynamic_id, target_dynamic_id in dynamic_mapping.items():
                    record = source_manager.dynamic_item_data.get(source_dynamic_id)
                    if record is None:
                        raise DomainError(
                            code="MIGRATION_REFERENCE_UNSUPPORTED",
                            message="A personal dynamic item record is missing.",
                            details={"dynamic_item_id": source_dynamic_id},
                            http_status=409,
                        )
                    source_manager.dynamic_item_data.require_transferable_record(
                        record
                    )
                    target_manager.dynamic_item_data.insert_cloned_record(
                        record.entry,
                        target_local_id=target_dynamic_id,
                        target_created_world_id=record.created_world_id,
                    )

                for source_pal in source_personal_pals:
                    source_pal_id = str(source_pal.InstanceId)
                    imported = PalEntity(deepcopy(source_pal._pal_obj))
                    source_equip_id = PalObjects.get_PalContainerId(
                        imported._pal_param.get("EquipItemContainerId")
                    )
                    target_equip_id = (
                        equip_mapping.get(str(source_equip_id))
                        if source_equip_id is not None
                        else str(uuid.uuid4())
                    )
                    imported.assign_clone_identity(
                        pal_mapping[source_pal_id],
                        target_equip_id,
                    )
                    self._rewrite_uuid_values(
                        imported._pal_obj,
                        identity_mapping,
                    )
                    self._bind_imported_pal(
                        imported,
                        target,
                        target_group,
                    )
                    imported.is_new_pal = False
                    if not target.add_pal(imported):
                        raise DomainError(
                            code="MIGRATION_ID_COLLISION_UNRESOLVED",
                            message="An imported personal Pal identifier still collides.",
                            details={"pal_instance_id": str(imported.InstanceId)},
                            http_status=409,
                        )
                    target_manager._entities_list.append(imported._pal_obj)
                    if target_group is not None and not target_group.add_pal(
                        imported.InstanceId
                    ):
                        raise DomainError(
                            code="MIGRATION_ID_COLLISION_UNRESOLVED",
                            message="An imported Pal could not be indexed in the target guild.",
                            details={"pal_instance_id": str(imported.InstanceId)},
                            http_status=409,
                        )

                target_manager.dynamic_item_data.assert_no_new_issues(
                    target_dynamic_issues
                )
            self._serialize_manager(
                target_manager,
                stage,
                player_ids={item.target_player_uid for item in mappings},
            )
            world_pal_ids = {
                str(
                    PalObjects.get_BaseType(
                        entity.get("key", {}).get("InstanceId")
                    )
                )
                for entity in target_manager._entities_list
                if PalObjects.get_BaseType(
                    entity.get("key", {}).get("InstanceId")
                )
                is not None
            }
            for mapping, target_storage_id in dps_imports:
                import_character_dps(
                    source_session.workspace,
                    stage,
                    source_player_uid=mapping.source_player_uid,
                    target_player_uid=mapping.target_player_uid,
                    target_pal_storage_id=target_storage_id,
                    used_pal_ids=world_pal_ids,
                )
        except DomainError:
            raise
        except Exception as error:
            raise DomainError(
                code="MIGRATION_STAGE_FAILED",
                message="The selected character subgraph could not be migrated safely.",
                details={"phase": "migrating"},
                http_status=500,
            ) from error
        finally:
            target_session.close()

    @classmethod
    def _require_character_subgraph_supported(
        cls,
        source_manager: SaveManager,
        source: Any,
        source_pals: tuple[PalEntity, ...],
        source_item_ids: set[str],
        target_manager: SaveManager,
        target: Any,
        target_pals: tuple[PalEntity, ...],
        target_item_ids: set[str],
    ) -> None:
        for manager, player, pals, item_ids in (
            (source_manager, source, source_pals, source_item_ids),
            (target_manager, target, target_pals, target_item_ids),
        ):
            for container_id in (
                player.OtomoCharacterContainerId,
                player.PalStorageContainerId,
            ):
                container = manager.container_data.get_container(container_id)
                if container is None:
                    raise DomainError(
                        code="MIGRATION_REFERENCE_UNSUPPORTED",
                        message="A personal Pal container is missing.",
                        http_status=409,
                    )
                indexed = {
                    str(slot.instance_id)
                    for slot in container.slots
                    if str(slot.instance_id) != _ZERO_UUID
                }
                owned = {
                    str(pal.InstanceId)
                    for pal in pals
                    if str(pal.ContainerId) == str(container_id)
                }
                if indexed != owned:
                    raise DomainError(
                        code="MIGRATION_REFERENCE_UNSUPPORTED",
                        message="A personal Pal container has unresolved character references.",
                        details={"container_id": str(container_id)},
                        http_status=409,
                    )
            for container_id in item_ids:
                container = manager.item_container_data.get(container_id)
                if container is None:
                    if container_id in cls._pal_equip_container_ids(pals):
                        continue
                    raise DomainError(
                        code="MIGRATION_REFERENCE_UNSUPPORTED",
                        message="A personal item container is missing.",
                        details={"container_id": container_id},
                        http_status=409,
                    )
            if manager.dynamic_item_data is None:
                raise DomainError(
                    code="MIGRATION_REFERENCE_UNSUPPORTED",
                    message="Dynamic item data could not be indexed.",
                    http_status=409,
                )

    @staticmethod
    def _personal_pals(
        manager: SaveManager,
        player: Any,
    ) -> tuple[PalEntity, ...]:
        result: list[PalEntity] = []
        seen: set[str] = set()
        for container_id in (
            player.OtomoCharacterContainerId,
            player.PalStorageContainerId,
        ):
            container = manager.container_data.get_container(container_id)
            if container is None:
                raise DomainError(
                    code="MIGRATION_REFERENCE_UNSUPPORTED",
                    message="A personal Pal container is missing.",
                    http_status=409,
                )
            for slot in sorted(container.slots, key=lambda item: item.inv_idx):
                pal_id = str(slot.instance_id)
                if pal_id == _ZERO_UUID:
                    continue
                if pal_id in seen:
                    raise DomainError(
                        code="MIGRATION_REFERENCE_UNSUPPORTED",
                        message="A personal Pal is referenced by more than one container slot.",
                        details={"pal_instance_id": pal_id},
                        http_status=409,
                    )
                pal = player._palbox.get(pal_id)
                if pal is None or str(pal.ContainerId) != str(container_id):
                    raise DomainError(
                        code="MIGRATION_REFERENCE_UNSUPPORTED",
                        message="A personal Pal reference cannot be resolved.",
                        details={"pal_instance_id": pal_id},
                        http_status=409,
                    )
                seen.add(pal_id)
                result.append(pal)
        return tuple(result)

    @staticmethod
    def _pal_equip_container_ids(
        pals: Iterable[PalEntity],
    ) -> set[str]:
        result: set[str] = set()
        for pal in pals:
            container_id = PalObjects.get_PalContainerId(
                pal._pal_param.get("EquipItemContainerId")
            )
            if container_id is not None and str(container_id) != _ZERO_UUID:
                result.add(str(container_id))
        return result

    @staticmethod
    def _personal_dynamic_ids(
        manager: SaveManager,
        personal_container_ids: set[str],
    ) -> set[str]:
        dynamic = manager.dynamic_item_data
        if dynamic is None:
            raise DomainError(
                code="MIGRATION_REFERENCE_UNSUPPORTED",
                message="Dynamic item data could not be indexed.",
                http_status=409,
            )
        result: dict[str, str] = {}
        for container_id in personal_container_ids:
            container = manager.item_container_data.get(container_id)
            if container is None:
                continue
            identifiers = [
                (
                    slot.dynamic_created_world_id,
                    slot.dynamic_local_id,
                )
                for slot in container.iter_occupied_slots()
                if slot.dynamic_id is not None
            ]
            identifiers.extend(container.iter_used_dynamic_item_ids() or ())
            for created_world_id, local_id in identifiers:
                if (
                    created_world_id is None
                    or local_id is None
                    or local_id == _ZERO_UUID
                ):
                    raise DomainError(
                        code="MIGRATION_REFERENCE_UNSUPPORTED",
                        message="A personal dynamic item reference is invalid.",
                        details={"container_id": container_id},
                        http_status=409,
                    )
                previous = result.setdefault(local_id, created_world_id)
                if previous != created_world_id:
                    raise DomainError(
                        code="MIGRATION_REFERENCE_UNSUPPORTED",
                        message="A dynamic item identifier uses conflicting world identities.",
                        details={"dynamic_item_id": local_id},
                        http_status=409,
                    )
        for local_id, created_world_id in result.items():
            record = dynamic.get(local_id)
            if record is None or record.created_world_id != created_world_id:
                raise DomainError(
                    code="MIGRATION_REFERENCE_UNSUPPORTED",
                    message="A personal dynamic item record cannot be resolved.",
                    details={"dynamic_item_id": local_id},
                    http_status=409,
                )
            dynamic.require_transferable_record(record)
        return set(result)

    @staticmethod
    def _require_personal_dynamic_ownership(
        manager: SaveManager,
        personal_container_ids: set[str],
        local_ids: set[str],
    ) -> None:
        dynamic = manager.dynamic_item_data
        dynamic.rebuild_references()
        for local_id in local_ids:
            references = dynamic.references.get(local_id, [])
            if not references or any(
                reference.container_id not in personal_container_ids
                for reference in references
            ):
                raise DomainError(
                    code="MIGRATION_REFERENCE_UNSUPPORTED",
                    message="A target dynamic item is shared outside the selected character graph.",
                    details={"dynamic_item_id": local_id},
                    http_status=409,
                )
            if not manager._audit_dynamic_item_reference_scope(
                local_id,
                1 + len(references),
            ):
                raise DomainError(
                    code="MIGRATION_REFERENCE_UNSUPPORTED",
                    message="A target dynamic item has an opaque reference outside the verified character graph.",
                    details={"dynamic_item_id": local_id},
                    http_status=409,
                )

    @staticmethod
    def _allocate_uuid_mapping(
        source_ids: Iterable[str],
        used_ids: set[str],
    ) -> dict[str, str]:
        used = {str(value) for value in used_ids}
        result: dict[str, str] = {}
        for source_id in source_ids:
            normalized = str(source_id)
            if normalized in result:
                continue
            target_id = normalized
            if target_id == _ZERO_UUID or target_id in used:
                target_id = str(uuid.uuid4())
                while target_id in used:
                    target_id = str(uuid.uuid4())
            result[normalized] = target_id
            used.add(target_id)
        return result

    @staticmethod
    def _require_equip_containers_unshared(
        manager: SaveManager,
        removed_pals: tuple[PalEntity, ...],
        removable_ids: set[str],
    ) -> None:
        if not removable_ids:
            return
        removed_pal_ids = {str(pal.InstanceId) for pal in removed_pals}
        for entity in manager._entities_list:
            instance_id = PalObjects.get_BaseType(
                entity.get("key", {}).get("InstanceId")
            )
            if instance_id is None or str(instance_id) in removed_pal_ids:
                continue
            parameter = (
                entity.get("value", {})
                .get("RawData", {})
                .get("value", {})
                .get("object", {})
                .get("SaveParameter", {})
                .get("value", {})
            )
            equip_id = PalObjects.get_PalContainerId(
                parameter.get("EquipItemContainerId")
            )
            if equip_id is not None and str(equip_id) in removable_ids:
                raise DomainError(
                    code="MIGRATION_REFERENCE_UNSUPPORTED",
                    message="A target Pal equipment container is shared outside the selected character graph.",
                    details={"container_id": str(equip_id)},
                    http_status=409,
                )
        for player in manager.player_mapping.values():
            direct_ids = {
                str(value)
                for value in player.resolve_item_container_ids().values()
                if value is not None
            }
            shared = direct_ids & removable_ids
            if shared:
                raise DomainError(
                    code="MIGRATION_REFERENCE_UNSUPPORTED",
                    message="A target Pal equipment container collides with a player inventory container.",
                    details={"container_ids": sorted(shared)},
                    http_status=409,
                )

    @staticmethod
    def _item_container_values(manager: SaveManager) -> list[dict[str, Any]]:
        value = (
            manager.gvas_file.properties.get("worldSaveData", {})
            .get("value", {})
            .get("ItemContainerSaveData", {})
            .get("value")
        )
        if not isinstance(value, list):
            raise DomainError(
                code="MIGRATION_REFERENCE_UNSUPPORTED",
                message="ItemContainerSaveData does not use the supported layout.",
                http_status=409,
            )
        return value

    @classmethod
    def _remove_item_containers(
        cls,
        manager: SaveManager,
        container_ids: set[str],
    ) -> None:
        if not container_ids:
            return
        values = cls._item_container_values(manager)
        retained: list[dict[str, Any]] = []
        removed: set[str] = set()
        for container in values:
            container_id = PalObjects.get_BaseType(
                container.get("key", {}).get("ID")
            )
            normalized = None if container_id is None else str(container_id)
            if normalized in container_ids:
                removed.add(normalized)
            else:
                retained.append(container)
        if removed != container_ids:
            raise DomainError(
                code="MIGRATION_REFERENCE_UNSUPPORTED",
                message="A target Pal equipment container could not be removed safely.",
                details={"missing_container_ids": sorted(container_ids - removed)},
                http_status=409,
            )
        values[:] = retained

    @staticmethod
    def _bind_imported_pal(
        pal: PalEntity,
        target_player: Any,
        target_group: Any | None,
    ) -> None:
        owner_id = target_player.PlayerUId
        owner_property = pal._pal_param.get("OwnerPlayerUId")
        if owner_property is None:
            pal._pal_param["OwnerPlayerUId"] = PalObjects.Guid(owner_id)
        else:
            PalObjects.set_BaseType(owner_property, owner_id)
        old_owners = pal.OldOwnerPlayerUIds
        if old_owners is None:
            pal._pal_param["OldOwnerPlayerUIds"] = PalObjects.ArrayProperty(
                "StructProperty",
                {
                    "prop_name": "OldOwnerPlayerUIds",
                    "prop_type": "StructProperty",
                    "values": [toUUID(owner_id)],
                    "type_name": "Guid",
                    "id": PalObjects.EMPTY_UUID,
                },
            )
        else:
            old_owners[:] = [toUUID(owner_id)]
        if "LastNickNameModifierPlayerUid" in pal._pal_param:
            PalObjects.set_BaseType(
                pal._pal_param["LastNickNameModifierPlayerUid"],
                owner_id,
            )
        raw_data = pal._pal_obj["value"]["RawData"]["value"]
        if target_group is None:
            raw_data.pop("group_id", None)
        else:
            raw_data["group_id"] = toUUID(target_group.group_id)
        pal.set_owner_player_entity(target_player)

    @staticmethod
    def _audit_removed_player_uids(
        root: Path,
        mapping: dict[str, str],
        manager: SaveManager,
    ) -> None:
        target_ids = {str(value) for value in mapping.values()}
        removed = {
            str(source_id)
            for source_id, target_id in mapping.items()
            if str(source_id) != str(target_id)
            and str(source_id) not in target_ids
        }
        if not removed:
            return
        needles = {
            player_id: UUID.from_str(player_id).raw_bytes
            for player_id in removed
        }
        parsed: dict[str, Any] = {"Level.sav": manager.gvas_file.properties}
        for player in manager.player_mapping.values():
            if getattr(player, "PlayerGVAS", None) is None:
                continue
            parsed[
                f"Players/{UUID2HexStr(player.PlayerUId)}.sav"
            ] = player._gvas_file.properties
        for relative, properties in parsed.items():
            path = root / Path(relative)
            try:
                with contextlib.redirect_stdout(io.StringIO()), (
                    contextlib.redirect_stderr(io.StringIO())
                ):
                    raw, _compression = decompress_sav_to_gvas(path.read_bytes())
            except Exception as error:
                raise DomainError(
                    code="MIGRATION_REFERENCE_UNSUPPORTED",
                    message="A staged save file could not be audited for opaque player references.",
                    details={"file": relative},
                    http_status=409,
                ) from error
            for player_id, needle in needles.items():
                expected_visible = SaveMigration._count_uuid_occurrences(
                    properties,
                    player_id,
                )
                if raw.count(needle) != expected_visible:
                    raise DomainError(
                        code="MIGRATION_REFERENCE_UNSUPPORTED",
                        message="An opaque reference to a replaced player identity remains.",
                        details={
                            "file": relative,
                            "player_uid": player_id,
                            "visible_occurrences": expected_visible,
                            "raw_occurrences": raw.count(needle),
                        },
                        http_status=409,
                    )

    @staticmethod
    def _count_uuid_occurrences(value: Any, expected: str) -> int:
        if isinstance(value, UUID):
            return int(str(value) == expected)
        if isinstance(value, dict):
            return sum(
                SaveMigration._count_uuid_occurrences(child, expected)
                for child in value.values()
            )
        if isinstance(value, (list, tuple)):
            return sum(
                SaveMigration._count_uuid_occurrences(child, expected)
                for child in value
            )
        return 0

    def _validate_staged(
        self,
        plan: MigrationPlan,
        session: SaveSession,
        mappings: tuple[PlayerIdentityMapping, ...],
    ) -> None:
        players = {item.player_id: item for item in session.list_players()}
        for mapping in mappings:
            expected_instance = (
                mapping.source_instance_id
                if plan.mode is MigrationMode.FULL
                else mapping.target_instance_id
            )
            player = players.get(mapping.target_player_uid)
            if player is None or player.instance_id != expected_instance:
                raise DomainError(
                    code="MIGRATION_VALIDATION_FAILED",
                    message="A migrated player identity failed staged validation.",
                    details={
                        "phase": "validating",
                        "target_player_uid": mapping.target_player_uid,
                    },
                    http_status=500,
                )
            session.load_player(mapping.target_player_uid)
        if CharacterIndex(session.manager).hard_issues():
            raise DomainError(
                code="MIGRATION_VALIDATION_FAILED",
                message="The migrated character graph contains hard errors.",
                details={"phase": "validating"},
                http_status=500,
            )
        dps_saves = validate_dps_tree(session.workspace)
        player_ids = set(players)
        world_pal_ids = {
            str(
                PalObjects.get_BaseType(
                    entity.get("key", {}).get("InstanceId")
                )
            )
            for entity in session.manager._entities_list
            if PalObjects.get_BaseType(
                entity.get("key", {}).get("InstanceId")
            )
            is not None
        }
        for dps_save in dps_saves:
            if dps_save.player_uid not in player_ids:
                raise DomainError(
                    code="MIGRATION_VALIDATION_FAILED",
                    message=(
                        "A dimensional Pal storage file has no matching staged player."
                    ),
                    details={
                        "phase": "validating",
                        "player_uid": dps_save.player_uid,
                    },
                    http_status=500,
                )
            collision = sorted(dps_save.active_pal_ids() & world_pal_ids)
            if collision:
                raise DomainError(
                    code="MIGRATION_VALIDATION_FAILED",
                    message=(
                        "A dimensional Pal identity collides with the staged world."
                    ),
                    details={
                        "phase": "validating",
                        "pal_instance_ids": collision,
                    },
                    http_status=500,
                )
        if plan.mode is MigrationMode.CHARACTER_ONLY:
            dps_by_player = {item.player_uid: item for item in dps_saves}
            for mapping in mappings:
                dps_save = dps_by_player.get(mapping.target_player_uid)
                if dps_save is None:
                    continue
                target_player = session.load_player(mapping.target_player_uid)
                storage_id = target_player.PalStorageContainerId
                if storage_id is None:
                    raise DomainError(
                        code="MIGRATION_VALIDATION_FAILED",
                        message=(
                            "A migrated player has no dimensional Pal storage target."
                        ),
                        details={
                            "phase": "validating",
                            "player_uid": mapping.target_player_uid,
                        },
                        http_status=500,
                    )
                if any(
                    record.owner_player_uid != mapping.target_player_uid
                    or record.old_owner_player_uids
                    != (mapping.target_player_uid,)
                    or record.last_nickname_modifier_player_uid
                    != mapping.target_player_uid
                    or record.container_id != str(storage_id)
                    for record in dps_save.active_records()
                ):
                    raise DomainError(
                        code="MIGRATION_VALIDATION_FAILED",
                        message=(
                            "A migrated dimensional Pal storage identity failed validation."
                        ),
                        details={
                            "phase": "validating",
                            "player_uid": mapping.target_player_uid,
                        },
                        http_status=500,
                    )
        summary = self._summary(session)
        authority = (
            plan.source_summary
            if plan.mode is MigrationMode.FULL
            else plan.target_summary
        )
        invariant_keys = (
            ("players", "groups", "bases", "characters", "character_containers")
            if plan.mode is MigrationMode.FULL
            else (
                "players",
                "groups",
                "bases",
                "character_containers",
            )
        )
        mismatched = {
            key: {
                "expected": authority.counts.get(key),
                "actual": summary.counts.get(key),
            }
            for key in invariant_keys
            if authority.counts.get(key) != summary.counts.get(key)
        }
        if mismatched:
            raise DomainError(
                code="MIGRATION_VALIDATION_FAILED",
                message="The migrated save failed mode-level semantic validation.",
                details={"phase": "validating", "mismatched_counts": mismatched},
                http_status=500,
            )

    @staticmethod
    def _serialize_manager(
        manager: SaveManager,
        root: Path,
        *,
        player_ids: set[str] | None = None,
    ) -> None:
        players_dir = root / "Players"
        players_dir.mkdir(parents=True, exist_ok=True)
        for key, player in manager.player_mapping.items():
            if player_ids is not None and key not in player_ids:
                continue
            if getattr(player, "PlayerGVAS", None) is None:
                continue
            player.save_new_pal_records()
            gvas, compression = player.PlayerGVAS
            data = compress_gvas_to_sav(
                deepcopy(gvas).write(PLAYER_SKIP_PROPERTIES),
                compression,
            )
            path = players_dir / f"{UUID2HexStr(player.PlayerUId)}.sav"
            path.write_bytes(data)
        level = compress_gvas_to_sav(
            deepcopy(manager.gvas_file).write(MAIN_SKIP_PROPERTIES),
            manager._compression_times,
        )
        (root / "Level.sav").write_bytes(level)

    @classmethod
    def _rewrite_known_player_uids(
        cls,
        value: Any,
        mapping: dict[str, str],
        *,
        player_context: bool = False,
    ) -> None:
        if isinstance(value, dict):
            for key, child in list(value.items()):
                context = str(key).replace("-", "_").casefold() in _PLAYER_UID_FIELDS
                if context:
                    value[key] = cls._rewrite_uuid_node(child, mapping)
                else:
                    cls._rewrite_known_player_uids(
                        child,
                        mapping,
                        player_context=False,
                    )
        elif isinstance(value, list):
            for index, child in enumerate(value):
                if player_context:
                    value[index] = cls._rewrite_uuid_node(child, mapping)
                else:
                    cls._rewrite_known_player_uids(child, mapping)

    @classmethod
    def _rewrite_group_player_handles(
        cls,
        properties: dict[str, Any],
        mapping: dict[str, str],
    ) -> None:
        groups = (
            properties.get("worldSaveData", {})
            .get("value", {})
            .get("GroupSaveDataMap", {})
            .get("value")
        )
        if not isinstance(groups, list):
            return
        for group in groups:
            raw = (
                group.get("value", {})
                .get("RawData", {})
                .get("value", {})
            )
            handles = raw.get("individual_character_handle_ids")
            if not isinstance(handles, list):
                continue
            for handle in handles:
                if not isinstance(handle, dict):
                    continue
                normalized = cls._try_uuid(handle.get("guid"))
                if normalized in mapping:
                    handle["guid"] = toUUID(mapping[normalized])

    @classmethod
    def _rewrite_uuid_node(cls, value: Any, mapping: dict[str, str]) -> Any:
        if isinstance(value, dict):
            if "value" in value and cls._try_uuid(value.get("value")) in mapping:
                cls._set_uuid(value, mapping[cls._try_uuid(value["value"])])
                return value
            for key, child in list(value.items()):
                value[key] = cls._rewrite_uuid_node(child, mapping)
            return value
        if isinstance(value, list):
            for index, child in enumerate(value):
                value[index] = cls._rewrite_uuid_node(child, mapping)
            return value
        normalized = cls._try_uuid(value)
        return toUUID(mapping[normalized]) if normalized in mapping else value

    @classmethod
    def _rewrite_uuid_values(cls, value: Any, mapping: dict[str, str]) -> None:
        if isinstance(value, dict):
            for key, child in list(value.items()):
                value[key] = cls._rewrite_uuid_node(child, mapping)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                value[index] = cls._rewrite_uuid_node(child, mapping)

    @staticmethod
    def _set_uuid(property_value: Any, value: str) -> None:
        if not isinstance(property_value, dict):
            raise DomainError(
                code="MIGRATION_REFERENCE_UNSUPPORTED",
                message="A required UUID field uses an unsupported structure.",
                http_status=409,
            )
        PalObjects.set_BaseType(property_value, toUUID(value))

    @staticmethod
    def _try_uuid(value: Any) -> str | None:
        try:
            return str(uuid.UUID(str(value)))
        except (ValueError, TypeError, AttributeError):
            return None

    @staticmethod
    def _copy_snapshot_tree(
        source: Path,
        snapshot: StorageSnapshot,
        destination: Path,
    ) -> None:
        destination.mkdir(parents=False, exist_ok=False)
        try:
            for item in snapshot.files:
                source_file = source / Path(item.relative_path.as_posix())
                target_file = destination / Path(item.relative_path.as_posix())
                target_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_file, target_file)
            copied = snapshot_tree(destination, reject_symlinks=True)
            if (
                copied.world_bindings != snapshot.world_bindings
                or copied.by_path() != snapshot.by_path()
            ):
                raise OSError("staged copy hash mismatch")
        except Exception as error:
            if destination.exists():
                shutil.rmtree(destination)
            raise DomainError(
                code="MIGRATION_STAGE_FAILED",
                message="The authoritative save tree could not be staged.",
                details={"phase": "staging"},
                http_status=500,
            ) from error

    @staticmethod
    def _changed_files(
        before: StorageSnapshot,
        after: StorageSnapshot,
    ) -> tuple[str, ...]:
        left = before.by_path()
        right = after.by_path()
        return tuple(
            path
            for path in sorted(set(left) | set(right))
            if left.get(path) != right.get(path)
        )

    @staticmethod
    def _snapshot_for_migration(session: SaveSession) -> StorageSnapshot:
        return session.opened_save.snapshot

    @staticmethod
    def _snapshot_for_target(session: SaveSession) -> StorageSnapshot:
        return session.opened_save.snapshot

    @classmethod
    def _require_current_snapshot(
        cls,
        session: SaveSession,
        expected: StorageSnapshot,
        code: str,
        *,
        complete_tree: bool = False,
    ) -> None:
        current = (
            cls._snapshot_for_target(session)
            if complete_tree
            else cls._snapshot_for_migration(session)
        )
        if current != expected:
            raise DomainError(
                code=code,
                message="A selected save changed after migration analysis.",
                details={"phase": "preflight"},
                retryable=True,
                http_status=409,
            )

    @staticmethod
    def _summary(session: SaveSession) -> MigrationSaveSummary:
        manager = session.manager
        players = tuple(
            MigrationPlayer(
                player_uid=item.player_id,
                instance_id=item.instance_id,
                name=item.name,
                level=item.level,
            )
            for item in session.list_players()
        )
        groups = list(manager.group_data.get_groups()) if manager.group_data else []
        bases = (
            len(getattr(manager.camp_data, "camp_map", {}) or {})
            if manager.camp_data is not None
            else 0
        )
        counts = {
            "players": len(players),
            "groups": len(groups),
            "bases": bases,
            "characters": len(manager._entities_list or []),
            "character_containers": len(
                getattr(manager.container_data, "container_map", {}) or {}
            ),
            "item_containers": len(
                getattr(manager.item_container_data, "container_map", {}) or {}
            ),
            "dynamic_items": len(
                getattr(manager.dynamic_item_data, "records", {}) or {}
            ),
        }
        compatibility = session.compatibility()
        return MigrationSaveSummary(
            platform=session.platform,
            display_name=session.source_display_name,
            save_version=compatibility.save_version,
            players=players,
            counts=counts,
            capabilities={
                key: value.to_dict()
                for key, value in compatibility.capabilities.items()
            },
        )

    @staticmethod
    def _resolve_ref(reference: MigrationSaveRef, *, field: str) -> SaveSource:
        try:
            if reference.platform is SavePlatform.STEAM:
                if not isinstance(reference.path, str) or not reference.path.strip():
                    raise ValueError("missing path")
                path = Path(reference.path).resolve(strict=True)
                if not path.is_dir() or not (path / "Level.sav").is_file():
                    raise ValueError("invalid Steam world directory")
                return make_steam_source(path)
            if reference.platform is SavePlatform.XGP:
                if (
                    not isinstance(reference.source_id, str)
                    or not reference.source_id.strip()
                ):
                    raise ValueError("missing source id")
                return SOURCE_CATALOG.resolve(reference.source_id)
        except (OSError, ValueError, DomainError) as error:
            if isinstance(error, DomainError):
                raise
            raise DomainError(
                code=(
                    "MIGRATION_SOURCE_INVALID"
                    if field == "source"
                    else "MIGRATION_TARGET_INVALID"
                ),
                message=f"The selected migration {field} is invalid.",
                field=field,
                http_status=400,
            ) from error
        raise DomainError(
            code="MIGRATION_MODE_UNSUPPORTED",
            message="The selected save platform is not supported.",
            field=field,
            http_status=400,
        )

    @staticmethod
    def _open(source: SaveSource, *, field: str) -> SaveSession:
        try:
            if source.platform is SavePlatform.STEAM:
                return SaveSession.open(
                    source.canonical_path,
                    manager=SaveManager.create_isolated(),
                )
            return SaveSession.open_storage(
                source,
                XgpWgsAdapter(catalog=SOURCE_CATALOG),
                manager=SaveManager.create_isolated(),
            )
        except DomainError:
            raise
        except Exception as error:
            raise DomainError(
                code=(
                    "MIGRATION_SOURCE_INVALID"
                    if field == "source"
                    else "MIGRATION_TARGET_INVALID"
                ),
                message=f"The selected migration {field} could not be opened.",
                field=field,
                http_status=400,
            ) from error

    def _progress(
        self,
        stage: MigrationStage,
        operation_key: tuple[str, str] | None = None,
    ) -> None:
        if operation_key is not None:
            with self._lock:
                current = self._operation_progress.setdefault(
                    operation_key,
                    {"stage": stage.value, "progress": []},
                )
                current["stage"] = stage.value
                if (
                    not current["progress"]
                    or current["progress"][-1] != stage.value
                ):
                    current["progress"].append(stage.value)
        if self._progress_callback is not None:
            self._progress_callback(stage.value, {})


SAVE_MIGRATION = SaveMigration()
