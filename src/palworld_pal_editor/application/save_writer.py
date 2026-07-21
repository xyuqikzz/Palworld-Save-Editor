from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from typing import Any, Callable
import uuid

from palworld_save_tools.gvas import GvasFile
from palworld_save_tools.palsav import compress_gvas_to_sav, decompress_sav_to_gvas
from palworld_save_tools.paltypes import PALWORLD_TYPE_HINTS

from palworld_pal_editor.core.item_container_data import ItemContainerData
from palworld_pal_editor.core.character_index import (
    CharacterIndex,
    inspect_decoded_character_graph,
)
from palworld_pal_editor.core.dynamic_item_data import DynamicItemData
from palworld_pal_editor.core.pal_objects import UUID2HexStr
from palworld_pal_editor.core.save_manager import MAIN_SKIP_PROPERTIES, PLAYER_SKIP_PROPERTIES
from palworld_pal_editor.domain.errors import DomainError, stale_revision
from palworld_pal_editor.domain.models import (
    SavePlatform,
    SaveResult,
    StorageCommitRequest,
)

from .save_session import SaveSession


class SaveWriter:
    """Verified backup, staging, replacement, and recovery for one SaveSession."""

    def __init__(
        self,
        *,
        failure_hook: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self._failure_hook = failure_hook

    def save(
        self,
        session: SaveSession,
        target: str | Path | None,
        expected_revision: int,
    ) -> SaveResult:
        if expected_revision != session.revision:
            raise stale_revision(expected_revision, session.revision)
        target_path = Path(target).resolve() if target is not None else None
        if session.platform is SavePlatform.XGP and target_path is not None:
            raise DomainError(
                code="WGS_COMMIT_FAILED",
                message="Game Pass saves can only be written back to the original slot.",
                field="target",
                http_status=400,
            )
        changes = session.changes()
        if not changes:
            return SaveResult(
                revision=session.revision,
                backup_path=None,
                staging_path=None,
                written_files=(),
                manifest=(),
                staged_reload_verified=True,
                target_reload_verified=True,
                platform=session.platform.value,
                source_reloaded=True,
                cloud_sync_verified=(
                    False if session.platform is SavePlatform.XGP else None
                ),
            )
        self._validate_global_invariants(session)
        files = self._modified_files(session)
        for relative_path in files:
            if not session.file_unchanged_since_open(relative_path):
                raise DomainError(
                    code="SAVE_TARGET_CHANGED",
                    message="A save file changed on disk after this session opened.",
                    details={"path": relative_path},
                    retryable=True,
                    http_status=409,
                )

        operation_id = str(uuid.uuid4())
        if session.platform is SavePlatform.STEAM:
            target_path = target_path or session.source.resolve()
            staging_path = (
                target_path.parent
                / f".{target_path.name}.pal-editor-staging-{operation_id}"
            )
        else:
            staging_path = Path(
                tempfile.mkdtemp(prefix=f"palworld-editor-stage-{operation_id}-")
            ).resolve()
        try:
            if session.platform is SavePlatform.STEAM:
                if target_path == session.source.resolve():
                    staging_path.mkdir(parents=False, exist_ok=False)
                else:
                    shutil.copytree(session.workspace, staging_path)
            self._serialize_to_staging(session, staging_path, files)
            self._verify_staged(staging_path, files)
            commit = session.storage.commit(
                StorageCommitRequest(
                    opened=session.opened_save,
                    staged_workspace=staging_path,
                    changed_files=tuple(PurePosixPath(path) for path in files),
                    expected_revision=expected_revision,
                    target_path=target_path,
                    verify_file=self._reload_file,
                    failure_hook=self._failure_hook,
                )
            )
        except DomainError as error:
            if session.platform is SavePlatform.XGP and error.code in {
                "SERIALIZATION_FAILED",
                "STAGED_RELOAD_FAILED",
            }:
                raise DomainError(
                    code="WGS_STAGE_FAILED",
                    message="The changed Game Pass save could not be staged and verified.",
                    details={"staging_path": str(staging_path)},
                    http_status=500,
                ) from error
            raise

        session.mark_saved(expected_revision)
        if staging_path.exists():
            shutil.rmtree(staging_path)
        return SaveResult(
            revision=session.revision,
            backup_path=str(commit.backup_path) if commit.backup_path else None,
            staging_path=None,
            written_files=tuple(path.as_posix() for path in commit.written_files),
            manifest=commit.manifest,
            staged_reload_verified=True,
            target_reload_verified=commit.source_reloaded,
            platform=commit.platform.value,
            manifest_path=(
                str(commit.manifest_path) if commit.manifest_path else None
            ),
            source_reloaded=commit.source_reloaded,
            recovery_status=commit.recovery_status,
            journal_path=str(commit.journal_path) if commit.journal_path else None,
            cloud_sync_verified=(
                False if commit.platform is SavePlatform.XGP else None
            ),
        )

    def export_steam_copy(
        self,
        session: SaveSession,
        target: str | Path,
        expected_revision: int,
    ) -> SaveResult:
        if expected_revision != session.revision:
            raise stale_revision(expected_revision, session.revision)
        target_path = Path(target).resolve()
        if target_path.exists() or not target_path.parent.is_dir():
            raise DomainError(
                code="INVALID_SAVE_TARGET",
                message="The Steam export target must be a new directory with an existing parent.",
                field="target",
                http_status=409,
            )
        staging = target_path.parent / f".{target_path.name}.steam-export-{uuid.uuid4()}"
        try:
            shutil.copytree(session.workspace, staging)
            files = self._modified_files(session) if session.changes() else []
            if files:
                self._validate_global_invariants(session)
                self._serialize_to_staging(session, staging, files)
                self._verify_staged(staging, files)
            os.replace(staging, target_path)
            self._verify_staged(target_path, files or ["Level.sav"])
        except Exception as error:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            if isinstance(error, DomainError):
                raise
            raise DomainError(
                code="WGS_STAGE_FAILED" if session.platform is SavePlatform.XGP else "WRITE_FAILED",
                message="The Steam-format copy could not be exported safely.",
                http_status=500,
            ) from error
        return SaveResult(
            revision=session.revision,
            backup_path=None,
            staging_path=None,
            written_files=tuple(files),
            manifest=(),
            staged_reload_verified=True,
            target_reload_verified=True,
            platform=SavePlatform.STEAM.value,
            source_reloaded=False,
            recovery_status="not_needed",
        )

    def _modified_files(self, session: SaveSession) -> list[str]:
        files: set[str] = set()
        for change in session.changes():
            for record in change.get("affected_records", []):
                if record.startswith("level:"):
                    files.add("Level.sav")
                elif record.startswith("player_file:"):
                    player_id = record.split(":", 1)[1]
                    files.add(f"Players/{UUID2HexStr(player_id)}.sav")
        if not files:
            raise DomainError(
                code="INVARIANT_VIOLATION",
                message="Pending changes do not identify any save file.",
                http_status=409,
            )
        return sorted(files)

    def _validate_global_invariants(self, session: SaveSession) -> None:
        manager = session.manager
        containers = getattr(manager, "item_container_data", None)
        if containers is not None:
            for container in containers.container_map.values():
                dense = container.dense_slots()
                if len(dense) != container.capacity:
                    raise DomainError(
                        code="INVARIANT_VIOLATION",
                        message="An item container does not match its declared capacity.",
                        http_status=409,
                    )
        dynamic_items = getattr(manager, "dynamic_item_data", None)
        if dynamic_items is not None:
            dynamic_items.assert_consistent()
        if all(
            hasattr(manager, field)
            for field in (
                "_entities_list",
                "container_data",
                "group_data",
                "player_mapping",
                "baseworker_mapping",
                "_dangling_pals",
            )
        ):
            issues = CharacterIndex(manager).hard_issues()
            if issues:
                raise DomainError(
                    code="CHARACTER_INDEX_INVARIANT_FAILED",
                    message="Character records and their references are inconsistent.",
                    details={
                        "issues": [issue.to_dict() for issue in issues]
                    },
                    http_status=409,
                )

    def _serialize_to_staging(
        self, session: SaveSession, staging_path: Path, files: list[str]
    ) -> None:
        manager = session.manager
        try:
            for relative_path in files:
                output = staging_path / Path(relative_path)
                output.parent.mkdir(parents=True, exist_ok=True)
                if relative_path == "Level.sav":
                    gvas = deepcopy(manager.gvas_file)
                    data = compress_gvas_to_sav(
                        gvas.write(MAIN_SKIP_PROPERTIES), manager._compression_times
                    )
                else:
                    player_hex = Path(relative_path).stem
                    player = next(
                        (
                            value
                            for value in manager.player_mapping.values()
                            if UUID2HexStr(value.PlayerUId) == player_hex
                        ),
                        None,
                    )
                    if player is None or player.PlayerGVAS is None:
                        raise KeyError(relative_path)
                    player_gvas, compression_times = player.PlayerGVAS
                    data = compress_gvas_to_sav(
                        deepcopy(player_gvas).write(PLAYER_SKIP_PROPERTIES),
                        compression_times,
                    )
                with output.open("wb") as stream:
                    stream.write(data)
                self._fail("after_serialize", {"path": relative_path})
        except Exception as error:
            raise DomainError(
                code="SERIALIZATION_FAILED",
                message="The modified save files could not be serialized.",
                details={"staging_path": str(staging_path)},
                http_status=500,
            ) from error

    def _verify_staged(self, root: Path, files: list[str]) -> None:
        try:
            for relative_path in files:
                self._reload_file(root / Path(relative_path), relative_path)
        except Exception as error:
            raise DomainError(
                code="STAGED_RELOAD_FAILED",
                message="A staged save file could not be reloaded.",
                details={"root": str(root)},
                http_status=500,
            ) from error

    def _reload_file(self, path: Path, relative_path: str) -> GvasFile:
        raw, _compression = decompress_sav_to_gvas(path.read_bytes())
        properties = MAIN_SKIP_PROPERTIES if relative_path == "Level.sav" else PLAYER_SKIP_PROPERTIES
        gvas = GvasFile.read(raw, PALWORLD_TYPE_HINTS, properties)
        if relative_path == "Level.sav":
            world = gvas.properties.get("worldSaveData")
            if world is not None:
                containers = ItemContainerData(gvas)
                DynamicItemData(gvas, containers).assert_consistent()
                character_issues = [
                    issue
                    for issue in inspect_decoded_character_graph(gvas)
                    if not issue.recoverable
                ]
                if character_issues:
                    raise DomainError(
                        code="CHARACTER_INDEX_INVARIANT_FAILED",
                        message="Reloaded character references are inconsistent.",
                        details={
                            "issues": [
                                issue.to_dict() for issue in character_issues
                            ]
                        },
                        http_status=409,
                    )
        return gvas

    def _fail(self, stage: str, context: dict[str, Any]) -> None:
        if self._failure_hook is not None:
            self._failure_hook(stage, context)
