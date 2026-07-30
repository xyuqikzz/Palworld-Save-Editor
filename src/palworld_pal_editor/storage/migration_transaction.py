from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import shutil
from typing import Any, Callable

from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.domain.models import StorageSnapshot
from palworld_pal_editor.storage.backup_diagnostics import (
    backup_failure,
    source_changed,
)
from palworld_pal_editor.storage.steam import (
    snapshot_active_steam_tree,
    snapshot_tree,
)


_PRESERVED_BACKUP_DIRECTORY_NAMES = frozenset(
    {
        "backup",
        "palworld-pal-editor-backup",
        ".palworld-pal-editor-backup",
    }
)


def _native_path(path: Path) -> Path:
    if os.name != "nt":
        return path
    absolute = os.path.abspath(path)
    if absolute.startswith("\\\\?\\"):
        return Path(absolute)
    if absolute.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + absolute[2:])
    return Path("\\\\?\\" + absolute)


@dataclass(frozen=True)
class MigrationCommitResult:
    backup_path: str
    manifest_path: str
    recovery_status: str


@dataclass(frozen=True)
class MigrationPreparedBackup:
    target: Path
    backup_path: Path
    manifest_path: Path
    expected_target: StorageSnapshot
    operation_id: str


class MigrationTreeTransaction:
    """Active-save Steam transaction used only by SaveMigration."""

    def __init__(
        self,
        *,
        failure_hook: Callable[[str, dict[str, object]], None] | None = None,
    ) -> None:
        self._failure_hook = failure_hook

    def commit(
        self,
        *,
        target: Path,
        staged: Path,
        expected_target: StorageSnapshot,
        operation_id: str,
        prepared_backup: MigrationPreparedBackup | None = None,
        progress_callback: Callable[[str], None] | None = None,
        post_commit_validator: Callable[[Path], None] | None = None,
    ) -> MigrationCommitResult:
        target = target.resolve()
        staged = staged.resolve()
        if not _native_path(target).is_dir() or not _native_path(staged).is_dir():
            raise DomainError(
                code="MIGRATION_COMMIT_FAILED",
                message="The migration target or staged tree is unavailable.",
                details={"phase": "preflight"},
                http_status=500,
            )
        if target.parent != staged.parent:
            raise DomainError(
                code="MIGRATION_COMMIT_FAILED",
                message="The staged tree must be on the target volume.",
                details={"phase": "preflight"},
                http_status=500,
            )
        self._require_snapshot(
            target,
            expected_target,
            code="MIGRATION_TARGET_CHANGED",
            phase="verify_target_before_commit",
        )
        if prepared_backup is None:
            prepared_backup = self.prepare_backup(
                target=target,
                expected_target=expected_target,
                operation_id=operation_id,
                progress_callback=progress_callback,
            )
        elif (
            prepared_backup.target != target
            or prepared_backup.expected_target != expected_target
            or prepared_backup.operation_id != operation_id
        ):
            raise DomainError(
                code="MIGRATION_COMMIT_FAILED",
                message="The prepared target backup does not match this migration.",
                details={"phase": "verify_prepared_backup"},
                http_status=500,
            )
        self._verify_prepared_backup(prepared_backup)
        backup_path = prepared_backup.backup_path
        manifest_path = prepared_backup.manifest_path
        recovery_path = target.parent / f".{target.name}.migration-recovery-{operation_id}"
        old_target_moved = False
        new_target_installed = False
        preserved_directories = self._preserved_backup_directories(target)
        moved_preserved_directories: list[PurePosixPath] = []
        staged_snapshot = snapshot_active_steam_tree(
            _native_path(staged),
            reject_symlinks=True,
        )
        try:
            if progress_callback is not None:
                progress_callback("committing")
            if _native_path(recovery_path).exists():
                raise OSError("Migration recovery path already exists")
            os.replace(_native_path(target), _native_path(recovery_path))
            old_target_moved = True
            self._fail("after_original_move", {"path": target.name})
            os.replace(_native_path(staged), _native_path(target))
            new_target_installed = True
            self._fail("after_target_swap", {"path": target.name})
            for relative in preserved_directories:
                source = recovery_path / Path(relative.as_posix())
                destination = target / Path(relative.as_posix())
                native_destination = _native_path(destination)
                native_destination.parent.mkdir(parents=True, exist_ok=True)
                os.replace(_native_path(source), native_destination)
                moved_preserved_directories.append(relative)
            self._fail(
                "after_preserved_directories",
                {"count": len(moved_preserved_directories)},
            )
            self._require_snapshot(
                target,
                staged_snapshot,
                code="MIGRATION_VALIDATION_FAILED",
                phase="verify_committed_tree",
                backup_path=backup_path,
            )
            self._fail("after_commit_validation", {"path": target.name})
            if post_commit_validator is not None:
                post_commit_validator(target)
        except Exception as error:
            recovered = self._restore(
                target=target,
                recovery_path=recovery_path,
                expected=expected_target,
                old_target_moved=old_target_moved,
                new_target_installed=new_target_installed,
                moved_preserved_directories=tuple(
                    moved_preserved_directories
                ),
            )
            if not recovered:
                raise DomainError(
                    code="MIGRATION_RECOVERY_FAILED",
                    message="Migration commit and automatic recovery both failed.",
                    details={
                        "phase": "committing",
                        "backup_path": str(backup_path),
                        "manifest_path": str(manifest_path),
                        "recovery_status": "failed",
                    },
                    http_status=500,
                ) from error
            raise DomainError(
                code="MIGRATION_COMMIT_FAILED",
                message="Migration commit failed and the target was restored.",
                details={
                    "phase": "committing",
                    "backup_path": str(backup_path),
                    "manifest_path": str(manifest_path),
                    "recovery_status": "restored",
                },
                retryable=True,
                http_status=500,
            ) from error

        shutil.rmtree(_native_path(recovery_path))
        return MigrationCommitResult(
            backup_path=str(backup_path),
            manifest_path=str(manifest_path),
            recovery_status="not_needed",
        )

    def prepare_backup(
        self,
        *,
        target: Path,
        expected_target: StorageSnapshot,
        operation_id: str,
        progress_callback: Callable[[str], None] | None = None,
    ) -> MigrationPreparedBackup:
        target = target.resolve()
        if not _native_path(target).is_dir():
            raise DomainError(
                code="MIGRATION_BACKUP_FAILED",
                message="The migration target is unavailable for backup.",
                details={"phase": "preflight"},
                http_status=500,
            )
        self._require_snapshot(
            target,
            expected_target,
            code="MIGRATION_TARGET_CHANGED",
            phase="verify_target_before_backup",
        )
        backup_path = (
            target.parent
            / ".Palworld-Pal-Editor-Migration-Backup"
            / target.name
            / (
                datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
                + "-"
                + operation_id
            )
        )
        manifest_path = backup_path / "manifest.json"
        try:
            if progress_callback is not None:
                progress_callback("backing_up")
            self._create_verified_backup(
                target=target,
                backup_path=backup_path,
                manifest_path=manifest_path,
                expected=expected_target,
                operation_id=operation_id,
            )
        except DomainError:
            raise
        except Exception as error:
            raise DomainError(
                code="MIGRATION_BACKUP_FAILED",
                message="A verified active target save backup could not be created.",
                details={
                    "phase": "backing_up",
                    "backup_path": str(backup_path),
                    "retryable": True,
                },
                retryable=True,
                http_status=500,
            ) from error
        return MigrationPreparedBackup(
            target=target,
            backup_path=backup_path,
            manifest_path=manifest_path,
            expected_target=expected_target,
            operation_id=operation_id,
        )

    def _verify_prepared_backup(
        self,
        prepared: MigrationPreparedBackup,
    ) -> None:
        expected_files = [
            {
                "path": item.relative_path.as_posix(),
                "size": item.size,
                "sha256": item.sha256,
            }
            for item in prepared.expected_target.files
        ]
        try:
            document = json.loads(
                _native_path(prepared.manifest_path).read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as error:
            raise DomainError(
                code="MIGRATION_BACKUP_FAILED",
                message="The prepared target backup manifest is unavailable.",
                details={
                    "phase": "verify_backup_before_commit",
                    "backup_path": str(prepared.backup_path),
                },
                http_status=500,
            ) from error
        if (
            document.get("schema_version") != 1
            or document.get("operation_id") != prepared.operation_id
            or document.get("files") != expected_files
        ):
            raise DomainError(
                code="MIGRATION_BACKUP_FAILED",
                message="The prepared target backup manifest changed.",
                details={
                    "phase": "verify_backup_before_commit",
                    "backup_path": str(prepared.backup_path),
                },
                http_status=500,
            )
        self._require_snapshot(
            prepared.backup_path / "files",
            prepared.expected_target,
            code="MIGRATION_BACKUP_FAILED",
            phase="verify_backup_before_commit",
            backup_path=prepared.backup_path,
        )

    def _create_verified_backup(
        self,
        *,
        target: Path,
        backup_path: Path,
        manifest_path: Path,
        expected: StorageSnapshot,
        operation_id: str,
    ) -> None:
        files_root = backup_path / "files"
        _native_path(files_root).mkdir(parents=True, exist_ok=False)
        manifest_files: list[dict[str, Any]] = []
        for item in expected.files:
            relative = item.relative_path.as_posix()
            source = target / Path(relative)
            destination = files_root / Path(relative)
            native_source = _native_path(source)
            native_destination = _native_path(destination)
            try:
                native_destination.parent.mkdir(parents=True, exist_ok=True)
                self._fail("before_backup_copy", {"path": relative})
                shutil.copy2(native_source, native_destination)
                copied = snapshot_tree(native_destination.parent).by_path().get(
                    native_destination.name
                )
            except DomainError:
                raise
            except Exception as error:
                if not native_source.is_file():
                    raise source_changed(
                        code="MIGRATION_TARGET_CHANGED",
                        message="The migration target changed while it was backed up.",
                        backup_path=backup_path,
                        phase="backing_up",
                        failed_file=relative,
                        error=error,
                    ) from error
                raise backup_failure(
                    code="MIGRATION_BACKUP_FAILED",
                    message="A target backup file could not be copied and verified.",
                    backup_path=backup_path,
                    phase="backing_up",
                    failed_file=relative,
                    error=error,
                ) from error
            if (
                copied is None
                or copied.size != item.size
                or copied.sha256 != item.sha256
            ):
                raise DomainError(
                    code="MIGRATION_BACKUP_FAILED",
                    message="A target backup file did not pass hash verification.",
                    details={
                        "phase": "verify_backup_file",
                        "failed_file": relative,
                        "backup_path": str(backup_path),
                    },
                    http_status=500,
                )
            manifest_files.append(
                {
                    "path": relative,
                    "size": item.size,
                    "sha256": item.sha256,
                }
            )
        document = {
            "schema_version": 1,
            "operation_id": operation_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "files": manifest_files,
        }
        self._write_json_durable(manifest_path, document)
        reread = json.loads(
            _native_path(manifest_path).read_text(encoding="utf-8")
        )
        if reread != document:
            raise DomainError(
                code="MIGRATION_BACKUP_FAILED",
                message="The migration backup manifest could not be verified.",
                details={
                    "phase": "verify_manifest",
                    "backup_path": str(backup_path),
                },
                http_status=500,
            )
        self._require_snapshot(
            files_root,
            expected,
            code="MIGRATION_BACKUP_FAILED",
            phase="verify_backup_tree",
            backup_path=backup_path,
        )

    @staticmethod
    def _snapshots_match(
        left: StorageSnapshot,
        right: StorageSnapshot,
    ) -> bool:
        return (
            left.world_bindings == right.world_bindings
            and left.by_path() == right.by_path()
        )

    @staticmethod
    def _preserved_backup_directories(
        root: Path,
    ) -> tuple[PurePosixPath, ...]:
        preserved: list[PurePosixPath] = []
        for directory, subdirectories, _filenames in os.walk(
            _native_path(root),
            topdown=True,
            followlinks=False,
        ):
            included: list[str] = []
            for name in sorted(subdirectories):
                path = Path(directory) / name
                if name.casefold() in _PRESERVED_BACKUP_DIRECTORY_NAMES:
                    preserved.append(
                        PurePosixPath(
                            path.relative_to(_native_path(root)).as_posix()
                        )
                    )
                else:
                    included.append(name)
            subdirectories[:] = included
        return tuple(preserved)

    @staticmethod
    def _write_json_durable(path: Path, value: dict[str, Any]) -> None:
        native_path = _native_path(path)
        native_path.parent.mkdir(parents=True, exist_ok=True)
        with native_path.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())

    @staticmethod
    def _require_snapshot(
        root: Path,
        expected: StorageSnapshot,
        *,
        code: str,
        phase: str,
        backup_path: Path | None = None,
    ) -> None:
        try:
            actual = snapshot_active_steam_tree(
                _native_path(root),
                reject_symlinks=True,
            )
        except OSError as error:
            raise DomainError(
                code=code,
                message="The migration file tree changed or could not be verified.",
                details={
                    "phase": phase,
                    **(
                        {"backup_path": str(backup_path)}
                        if backup_path is not None
                        else {}
                    ),
                },
                retryable=True,
                http_status=409,
            ) from error
        if not MigrationTreeTransaction._snapshots_match(actual, expected):
            expected_files = expected.by_path()
            actual_files = actual.by_path()
            changed = next(
                (
                    relative
                    for relative in sorted(set(expected_files) | set(actual_files))
                    if expected_files.get(relative) != actual_files.get(relative)
                ),
                None,
            )
            raise DomainError(
                code=code,
                message="The migration file tree changed after analysis.",
                details={
                    "phase": phase,
                    "failed_file": changed,
                    **(
                        {"backup_path": str(backup_path)}
                        if backup_path is not None
                        else {}
                    ),
                },
                retryable=True,
                http_status=409,
            )

    def _restore(
        self,
        *,
        target: Path,
        recovery_path: Path,
        expected: StorageSnapshot,
        old_target_moved: bool,
        new_target_installed: bool,
        moved_preserved_directories: tuple[PurePosixPath, ...],
    ) -> bool:
        try:
            native_target = _native_path(target)
            native_recovery = _native_path(recovery_path)
            for relative in reversed(moved_preserved_directories):
                source = target / Path(relative.as_posix())
                destination = recovery_path / Path(relative.as_posix())
                native_destination = _native_path(destination)
                native_destination.parent.mkdir(parents=True, exist_ok=True)
                os.replace(_native_path(source), native_destination)
            if new_target_installed and native_target.exists():
                failed_path = (
                    target.parent / f".{target.name}.migration-failed-{os.getpid()}"
                )
                native_failed = _native_path(failed_path)
                if native_failed.exists():
                    shutil.rmtree(native_failed)
                os.replace(native_target, native_failed)
                shutil.rmtree(native_failed)
            if old_target_moved and native_recovery.exists():
                os.replace(native_recovery, native_target)
            self._fail("before_recovery_validation", {"path": target.name})
            return native_target.is_dir() and self._snapshots_match(
                snapshot_active_steam_tree(
                    native_target,
                    reject_symlinks=True,
                ),
                expected,
            )
        except Exception:
            return False

    def _fail(self, stage: str, context: dict[str, object]) -> None:
        if self._failure_hook is not None:
            self._failure_hook(stage, context)
