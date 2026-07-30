from __future__ import annotations

from collections.abc import Iterator
import hashlib
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import uuid

from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.domain.models import (
    LogicalSaveFile,
    OpenedSave,
    SavePlatform,
    SaveSource,
    StorageCommitRequest,
    StorageCommitResult,
    StorageFileSnapshot,
    StorageSnapshot,
)
from palworld_pal_editor.storage.backup_diagnostics import (
    BackupVerificationError,
    backup_failure,
    source_changed,
)

_STEAM_BACKUP_DIRECTORY_NAMES = frozenset(
    {
        "backup",
        "palworld-pal-editor-backup",
        ".palworld-pal-editor-backup",
    }
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot_tree(root: Path, *, reject_symlinks: bool = False) -> StorageSnapshot:
    files: list[StorageFileSnapshot] = []
    if root.is_dir():
        for path in sorted(root.rglob("*")):
            if reject_symlinks and path.is_symlink():
                raise OSError("Symbolic links are not allowed in a WGS source tree")
            if not path.is_file():
                continue
            stat = path.stat()
            files.append(
                StorageFileSnapshot(
                    relative_path=PurePosixPath(path.relative_to(root).as_posix()),
                    size=stat.st_size,
                    mtime_ns=stat.st_mtime_ns,
                    sha256=sha256_file(path),
                )
            )
    return StorageSnapshot(files=tuple(files))


def make_steam_source(path: str | Path) -> SaveSource:
    resolved = Path(path).resolve()
    digest = hashlib.sha256(
        ("palworld-editor-steam-source-v1\0" + str(resolved).casefold()).encode(
            "utf-8"
        )
    ).hexdigest()
    return SaveSource(
        platform=SavePlatform.STEAM,
        canonical_path=resolved,
        source_id="steam-" + digest,
        display_name=resolved.name or "Steam save",
    )


def _iter_steam_source_files(
    root: Path,
    *,
    reject_symlinks: bool = False,
) -> Iterator[Path]:
    for directory, subdirectories, filenames in os.walk(root, topdown=True):
        included_directories: list[str] = []
        for name in sorted(subdirectories):
            if name.casefold() in _STEAM_BACKUP_DIRECTORY_NAMES:
                continue
            path = Path(directory) / name
            if reject_symlinks and path.is_symlink():
                raise OSError("Symbolic links are not allowed in a Steam source tree")
            included_directories.append(name)
        subdirectories[:] = included_directories
        for filename in sorted(filenames):
            path = Path(directory) / filename
            if reject_symlinks and path.is_symlink():
                raise OSError("Symbolic links are not allowed in a Steam source tree")
            if path.is_file():
                yield path


def snapshot_active_steam_tree(
    root: Path,
    *,
    reject_symlinks: bool = False,
) -> StorageSnapshot:
    files: list[StorageFileSnapshot] = []
    if root.is_dir():
        for path in _iter_steam_source_files(
            root,
            reject_symlinks=reject_symlinks,
        ):
            stat = path.stat()
            files.append(
                StorageFileSnapshot(
                    relative_path=PurePosixPath(
                        path.relative_to(root).as_posix()
                    ),
                    size=stat.st_size,
                    mtime_ns=stat.st_mtime_ns,
                    sha256=sha256_file(path),
                )
            )
    return StorageSnapshot(files=tuple(files))


def _snapshot_steam_source(root: Path) -> StorageSnapshot:
    return snapshot_active_steam_tree(root)


def _first_snapshot_difference(
    expected: StorageSnapshot,
    actual: StorageSnapshot,
) -> str | None:
    expected_files = expected.by_path()
    actual_files = actual.by_path()
    for relative in sorted(set(expected_files) | set(actual_files)):
        if expected_files.get(relative) != actual_files.get(relative):
            return relative
    return None


def _verify_steam_source_unchanged(
    source: Path,
    expected: StorageSnapshot,
    *,
    backup_path: Path | None,
    phase: str,
) -> None:
    try:
        actual = _snapshot_steam_source(source)
    except OSError as error:
        raise source_changed(
            code="SAVE_TARGET_CHANGED",
            message="The Steam save source changed during backup.",
            backup_path=backup_path,
            phase=phase,
            failed_file=None,
            error=error,
        ) from error
    failed_file = _first_snapshot_difference(expected, actual)
    if failed_file is not None:
        raise source_changed(
            code="SAVE_TARGET_CHANGED",
            message="The Steam save source changed during backup.",
            backup_path=backup_path,
            phase=phase,
            failed_file=failed_file,
        )


class SteamDirectoryAdapter:
    """Steam directory Adapter at the SaveStorage seam."""

    def open(self, source: SaveSource) -> OpenedSave:
        if source.platform is not SavePlatform.STEAM:
            raise DomainError(
                code="INVALID_SAVE_SOURCE",
                message="Steam storage received a non-Steam source.",
                http_status=400,
            )
        root = source.canonical_path.resolve()
        logical_files: dict[str, LogicalSaveFile] = {}
        snapshot = _snapshot_steam_source(root)
        for item in snapshot.files:
            relative = item.relative_path
            if Path(relative.as_posix()).suffix.casefold() == ".sav":
                logical_files[relative.as_posix()] = LogicalSaveFile(
                    relative_path=relative,
                    physical_identity=relative.as_posix(),
                    size=item.size,
                    sha256=item.sha256,
                )
        return OpenedSave(
            source=source,
            workspace=root,
            logical_files=logical_files,
            snapshot=snapshot,
            cleanup_required=False,
        )

    def bind_logical_file(
        self,
        opened: OpenedSave,
        relative_path: str,
        physical_path: str | Path,
    ) -> None:
        if opened.source.platform is not SavePlatform.STEAM:
            raise DomainError(
                code="INVALID_SAVE_SOURCE",
                message="Only Steam sessions can bind an external logical file.",
                http_status=400,
            )
        relative = PurePosixPath(str(relative_path).replace("\\", "/"))
        physical = Path(physical_path).resolve()
        if not physical.is_file():
            raise DomainError(
                code="LOCAL_DATA_MISSING",
                message="The selected logical save file does not exist.",
                details={"path": str(physical)},
                http_status=404,
            )
        stat = physical.stat()
        opened.logical_files[relative.as_posix()] = LogicalSaveFile(
            relative_path=relative,
            physical_identity=str(physical),
            size=stat.st_size,
            sha256=sha256_file(physical),
        )
        external = opened.storage_metadata.setdefault(
            "external_logical_files", {}
        )
        default_path = (
            opened.source.canonical_path.resolve() / Path(relative.as_posix())
        )
        if physical == default_path:
            external.pop(relative.as_posix(), None)
        else:
            external[relative.as_posix()] = str(physical)

    @staticmethod
    def logical_source_path(opened: OpenedSave, relative_path: str) -> Path:
        external = opened.storage_metadata.get("external_logical_files", {})
        bound = external.get(relative_path) if isinstance(external, dict) else None
        if bound:
            return Path(bound).resolve()
        return opened.source.canonical_path.resolve() / Path(relative_path)

    @classmethod
    def _backup_file_path(
        cls,
        opened: OpenedSave,
        backup_path: Path,
        relative_path: str,
    ) -> Path:
        external = opened.storage_metadata.get("external_logical_files", {})
        if isinstance(external, dict) and relative_path in external:
            return backup_path / "files" / "__external__" / Path(relative_path)
        return backup_path / "files" / Path(relative_path)

    def commit(self, request: StorageCommitRequest) -> StorageCommitResult:
        opened = request.opened
        source = opened.source.canonical_path.resolve()
        target = (request.target_path or source).resolve()
        changed = tuple(
            dict.fromkeys(str(path).replace("\\", "/") for path in request.changed_files)
        )
        if not changed:
            return StorageCommitResult(
                platform=SavePlatform.STEAM,
                written_files=(),
                backup_path=None,
                manifest_path=None,
                source_reloaded=True,
            )
        _verify_steam_source_unchanged(
            source,
            opened.snapshot,
            backup_path=None,
            phase="verify_source_before_backup",
        )
        external = opened.storage_metadata.get("external_logical_files", {})
        if (
            target != source
            and isinstance(external, dict)
            and any(relative in external for relative in changed)
        ):
            raise DomainError(
                code="EXTERNAL_LOCAL_DATA_TARGET_UNSUPPORTED",
                message=(
                    "A selected external LocalData.sav can only be written "
                    "back to its original file."
                ),
                field="target",
                http_status=409,
            )
        for relative in changed:
            expected = opened.logical_files.get(relative)
            path = self.logical_source_path(opened, relative)
            if expected is None or not path.is_file() or sha256_file(path) != expected.sha256:
                raise DomainError(
                    code="SAVE_TARGET_CHANGED",
                    message="A save file changed on disk after this session opened.",
                    details={"path": relative},
                    retryable=True,
                    http_status=409,
                )
        staged_hashes = {
            relative: sha256_file(request.staged_workspace / Path(relative))
            for relative in changed
        }
        if target != source and target.exists():
            raise DomainError(
                code="SAVE_TARGET_ALREADY_EXISTS",
                message="Saving to a different existing directory is not supported safely.",
                field="target",
                http_status=409,
            )
        if not target.parent.exists():
            raise DomainError(
                code="INVALID_SAVE_TARGET",
                message="The target parent directory does not exist.",
                field="target",
                http_status=400,
            )

        operation_id = str(uuid.uuid4())
        backup_path = (
            source.parent
            / ".Palworld-Pal-Editor-Backup"
            / source.name
            / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')}-{operation_id}"
        )
        manifest_path = backup_path / "manifest.json"
        progress: list[str] = []
        manifest: tuple[dict[str, object], ...] = ()
        try:
            manifest = self._backup(
                source,
                backup_path,
                opened.snapshot,
                opened.source.source_id,
                request,
                opened,
            )
            self._fail(request, "after_backup", {"backup_path": str(backup_path)})
            _verify_steam_source_unchanged(
                source,
                opened.snapshot,
                backup_path=backup_path,
                phase="verify_source_after_backup",
            )
        except DomainError:
            raise
        except Exception as error:
            raise backup_failure(
                code="BACKUP_FAILED",
                message="A complete, verified backup could not be created.",
                backup_path=backup_path,
                phase="verify_source_after_backup",
                failed_file=None,
                error=error,
            ) from error

        try:
            self._fail(request, "before_replace", {"staging_path": str(request.staged_workspace)})
            _verify_steam_source_unchanged(
                source,
                opened.snapshot,
                backup_path=backup_path,
                phase="verify_source_before_write",
            )
            for relative in changed:
                expected = opened.logical_files.get(relative)
                current = self.logical_source_path(opened, relative)
                if (
                    expected is None
                    or not current.is_file()
                    or sha256_file(current) != expected.sha256
                ):
                    raise source_changed(
                        code="SAVE_TARGET_CHANGED",
                        message=(
                            "A save file changed on disk after the verified "
                            "backup was created."
                        ),
                        backup_path=backup_path,
                        phase="verify_source_before_write",
                        failed_file=relative,
                    )
            if target != source:
                os.replace(request.staged_workspace, target)
                progress.append(".")
                self._fail(request, "after_replace", {"path": str(target)})
            else:
                for relative in changed:
                    staged = request.staged_workspace / Path(relative)
                    destination = self.logical_source_path(opened, relative)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(staged, destination)
                    progress.append(relative)
                    self._fail(
                        request,
                        "after_replace",
                        {"path": relative, "progress": list(progress)},
                    )
            for relative in changed:
                final = (
                    self.logical_source_path(opened, relative)
                    if target == source
                    else target / Path(relative)
                )
                if sha256_file(final) != staged_hashes[relative]:
                    raise OSError("Steam target hash mismatch")
                if request.verify_file is not None:
                    request.verify_file(final, relative)
        except DomainError:
            if not progress:
                raise
            recovered = self._recover(
                source=source,
                target=target,
                backup_path=backup_path,
                progress=progress,
                request=request,
                opened=opened,
            )
            raise DomainError(
                code="WRITE_FAILED" if recovered else "RECOVERY_FAILED",
                message=(
                    "Save validation failed and the original files were restored."
                    if recovered
                    else "Save validation and automatic recovery both failed."
                ),
                details={
                    "backup_path": str(backup_path),
                    "manifest_path": str(manifest_path),
                    "staging_path": str(request.staged_workspace),
                    "recovered": recovered,
                    "recovery_status": "restored" if recovered else "failed",
                },
                retryable=recovered,
                http_status=500,
            )
        except Exception as error:
            recovered = self._recover(
                source=source,
                target=target,
                backup_path=backup_path,
                progress=progress,
                request=request,
                opened=opened,
            )
            code = "WRITE_FAILED" if recovered else "RECOVERY_FAILED"
            raise DomainError(
                code=code,
                message=(
                    "Save failed and the original files were restored."
                    if recovered
                    else "Save and automatic recovery both failed."
                ),
                details={
                    "backup_path": str(backup_path),
                    "manifest_path": str(manifest_path),
                    "staging_path": str(request.staged_workspace),
                    "recovered": recovered,
                    "recovery_status": "restored" if recovered else "failed",
                },
                retryable=recovered,
                http_status=500,
            ) from error

        if target == source:
            external_bindings = dict(
                opened.storage_metadata.get("external_logical_files", {})
            )
            refreshed = self.open(opened.source)
            opened.logical_files = refreshed.logical_files
            opened.snapshot = refreshed.snapshot
            opened.storage_metadata = refreshed.storage_metadata
            for relative, physical_path in external_bindings.items():
                self.bind_logical_file(opened, relative, physical_path)
        return StorageCommitResult(
            platform=SavePlatform.STEAM,
            written_files=tuple(PurePosixPath(path) for path in changed),
            backup_path=backup_path,
            manifest_path=manifest_path,
            source_reloaded=True,
            manifest=manifest,
        )

    def close(self, opened: OpenedSave) -> None:
        return None

    def _backup(
        self,
        source: Path,
        backup_path: Path,
        snapshot: StorageSnapshot,
        source_id: str,
        request: StorageCommitRequest,
        opened: OpenedSave,
    ) -> tuple[dict[str, object], ...]:
        phase = "create_backup_directory"
        failed_file: str | None = None
        try:
            files_root = backup_path / "files"
            files_root.mkdir(parents=True, exist_ok=False)
            manifest: list[dict[str, object]] = []
            for item in snapshot.files:
                relative = item.relative_path.as_posix()
                failed_file = relative
                source_file = source / Path(relative)
                backup_file = files_root / Path(relative)
                phase = "create_backup_directory"
                backup_file.parent.mkdir(parents=True, exist_ok=True)
                phase = "copy_file"
                self._fail(request, "before_backup_copy", {"path": relative})
                try:
                    shutil.copy2(source_file, backup_file)
                except FileNotFoundError as error:
                    if not source_file.is_file():
                        raise source_changed(
                            code="SAVE_TARGET_CHANGED",
                            message=(
                                "The Steam save source changed during "
                                "backup."
                            ),
                            backup_path=backup_path,
                            phase="verify_source_after_backup",
                            failed_file=relative,
                            error=error,
                        ) from error
                    raise
                try:
                    source_stat = source_file.stat()
                    source_hash = sha256_file(source_file)
                except OSError as error:
                    raise source_changed(
                        code="SAVE_TARGET_CHANGED",
                        message="The Steam save source changed during backup.",
                        backup_path=backup_path,
                        phase="verify_source_after_backup",
                        failed_file=relative,
                        error=error,
                    ) from error
                if (
                    source_stat.st_size != item.size
                    or source_hash != item.sha256
                ):
                    raise source_changed(
                        code="SAVE_TARGET_CHANGED",
                        message="The Steam save source changed during backup.",
                        backup_path=backup_path,
                        phase="verify_source_after_backup",
                        failed_file=relative,
                    )
                phase = "verify_copy"
                copied = backup_file.stat()
                if (
                    copied.st_size != item.size
                    or sha256_file(backup_file) != item.sha256
                ):
                    raise BackupVerificationError(
                        "Steam backup file verification failed"
                    )
                self._fail(request, "after_backup_copy", {"path": relative})
                manifest.append(
                    {
                        "path": relative,
                        "size": item.size,
                        "mtime_ns": item.mtime_ns,
                        "sha256": item.sha256,
                    }
                )
            external = opened.storage_metadata.get(
                "external_logical_files", {}
            )
            if isinstance(external, dict):
                for relative, physical_path in sorted(external.items()):
                    logical = opened.logical_files.get(relative)
                    if logical is None:
                        raise BackupVerificationError(
                            "External logical file metadata is missing"
                        )
                    failed_file = relative
                    source_file = Path(physical_path).resolve()
                    backup_file = self._backup_file_path(
                        opened, backup_path, relative
                    )
                    phase = "create_backup_directory"
                    backup_file.parent.mkdir(parents=True, exist_ok=True)
                    phase = "copy_file"
                    self._fail(
                        request,
                        "before_backup_copy",
                        {"path": relative, "external": True},
                    )
                    shutil.copy2(source_file, backup_file)
                    source_stat = source_file.stat()
                    source_hash = sha256_file(source_file)
                    if (
                        source_stat.st_size != logical.size
                        or source_hash != logical.sha256
                    ):
                        raise source_changed(
                            code="SAVE_TARGET_CHANGED",
                            message=(
                                "The selected external save file changed "
                                "during backup."
                            ),
                            backup_path=backup_path,
                            phase="verify_source_after_backup",
                            failed_file=relative,
                        )
                    phase = "verify_copy"
                    if (
                        backup_file.stat().st_size != logical.size
                        or sha256_file(backup_file) != logical.sha256
                    ):
                        raise BackupVerificationError(
                            "External Steam backup verification failed"
                        )
                    self._fail(
                        request,
                        "after_backup_copy",
                        {"path": relative, "external": True},
                    )
                    manifest.append(
                        {
                            "path": relative,
                            "backup_path": (
                                PurePosixPath("__external__")
                                / PurePosixPath(relative)
                            ).as_posix(),
                            "source_path": str(source_file),
                            "external": True,
                            "size": logical.size,
                            "mtime_ns": source_stat.st_mtime_ns,
                            "sha256": logical.sha256,
                        }
                    )
            failed_file = "manifest.json"
            manifest_path = backup_path / failed_file
            document = {
                "schema_version": 1,
                "source_id": source_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "files": manifest,
            }
            phase = "write_manifest"
            self._write_json_durable(manifest_path, document)
            phase = "read_manifest"
            manifest_text = manifest_path.read_text(encoding="utf-8")
            phase = "verify_manifest"
            try:
                loaded = json.loads(manifest_text)
            except (json.JSONDecodeError, TypeError) as error:
                raise BackupVerificationError(
                    "Steam backup manifest could not be parsed"
                ) from error
            if loaded != document:
                raise BackupVerificationError(
                    "Steam backup manifest verification failed"
                )
            return tuple(manifest)
        except DomainError:
            raise
        except Exception as error:
            raise backup_failure(
                code="BACKUP_FAILED",
                message="A complete, verified backup could not be created.",
                backup_path=backup_path,
                phase=phase,
                failed_file=failed_file,
                error=error,
            ) from error

    def _write_json_durable(
        self,
        path: Path,
        document: dict[str, object],
    ) -> None:
        temporary = path.with_name(
            f".{path.name}.{uuid.uuid4()}.tmp"
        )
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(document, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        self._fsync_directory(path.parent)

    def _fsync_directory(self, path: Path) -> None:
        try:
            descriptor = os.open(path, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(descriptor)
        except OSError:
            pass
        finally:
            os.close(descriptor)

    def _recover(
        self,
        *,
        source: Path,
        target: Path,
        backup_path: Path,
        progress: list[str],
        request: StorageCommitRequest,
        opened: OpenedSave,
    ) -> bool:
        try:
            self._fail(request, "before_recovery", {"progress": list(progress)})
            if target != source:
                if target.exists():
                    return False
                return True
            for relative in reversed(progress):
                backup_file = self._backup_file_path(
                    opened, backup_path, relative
                )
                destination = self.logical_source_path(opened, relative)
                temporary = destination.with_name(
                    f".{destination.name}.restore-{uuid.uuid4()}"
                )
                shutil.copy2(backup_file, temporary)
                if sha256_file(temporary) != sha256_file(backup_file):
                    raise OSError("Steam restore hash mismatch")
                os.replace(temporary, destination)
            return all(
                sha256_file(self.logical_source_path(opened, relative))
                == sha256_file(
                    self._backup_file_path(opened, backup_path, relative)
                )
                for relative in progress
            )
        except Exception:
            return False

    def _fail(
        self,
        request: StorageCommitRequest,
        stage: str,
        context: dict[str, object],
    ) -> None:
        if request.failure_hook is not None:
            request.failure_hook(stage, dict(context))
