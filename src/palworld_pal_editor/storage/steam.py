from __future__ import annotations

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
        if root.is_dir():
            for path in sorted(root.rglob("*.sav")):
                if not path.is_file():
                    continue
                relative = PurePosixPath(path.relative_to(root).as_posix())
                logical_files[relative.as_posix()] = LogicalSaveFile(
                    relative_path=relative,
                    physical_identity=relative.as_posix(),
                    size=path.stat().st_size,
                    sha256=sha256_file(path),
                )
        return OpenedSave(
            source=source,
            workspace=root,
            logical_files=logical_files,
            snapshot=snapshot_tree(root),
            cleanup_required=False,
        )

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
        for relative in changed:
            expected = opened.logical_files.get(relative)
            path = source / Path(relative)
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
            manifest = self._backup(source, backup_path, changed, opened.source.source_id)
            self._fail(request, "after_backup", {"backup_path": str(backup_path)})
            self._fail(request, "before_replace", {"staging_path": str(request.staged_workspace)})
            if target != source:
                os.replace(request.staged_workspace, target)
                progress.append(".")
                self._fail(request, "after_replace", {"path": str(target)})
            else:
                for relative in changed:
                    staged = request.staged_workspace / Path(relative)
                    destination = target / Path(relative)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(staged, destination)
                    progress.append(relative)
                    self._fail(
                        request,
                        "after_replace",
                        {"path": relative, "progress": list(progress)},
                    )
            for relative in changed:
                final = target / Path(relative)
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
            refreshed = self.open(opened.source)
            opened.logical_files = refreshed.logical_files
            opened.snapshot = refreshed.snapshot
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
        changed: tuple[str, ...],
        source_id: str,
    ) -> tuple[dict[str, object], ...]:
        try:
            files_root = backup_path / "files"
            files_root.mkdir(parents=True, exist_ok=False)
            manifest: list[dict[str, object]] = []
            for relative in changed:
                source_file = source / Path(relative)
                backup_file = files_root / Path(relative)
                backup_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_file, backup_file)
                source_hash = sha256_file(source_file)
                if sha256_file(backup_file) != source_hash:
                    raise OSError("Steam backup hash mismatch")
                manifest.append(
                    {
                        "path": relative,
                        "size": source_file.stat().st_size,
                        "sha256": source_hash,
                    }
                )
            with (backup_path / "manifest.json").open(
                "w", encoding="utf-8", newline="\n"
            ) as stream:
                json.dump(
                    {
                        "schema_version": 1,
                        "source_id": source_id,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "files": manifest,
                    },
                    stream,
                    ensure_ascii=False,
                    indent=2,
                )
                stream.write("\n")
            return tuple(manifest)
        except Exception as error:
            raise DomainError(
                code="BACKUP_FAILED",
                message="A complete, verified backup could not be created.",
                details={"backup_path": str(backup_path)},
                http_status=500,
            ) from error

    def _recover(
        self,
        *,
        source: Path,
        target: Path,
        backup_path: Path,
        progress: list[str],
        request: StorageCommitRequest,
    ) -> bool:
        try:
            self._fail(request, "before_recovery", {"progress": list(progress)})
            if target != source:
                if target.exists():
                    return False
                return True
            for relative in reversed(progress):
                backup_file = backup_path / "files" / Path(relative)
                destination = target / Path(relative)
                temporary = destination.with_name(
                    f".{destination.name}.restore-{uuid.uuid4()}"
                )
                shutil.copy2(backup_file, temporary)
                if sha256_file(temporary) != sha256_file(backup_file):
                    raise OSError("Steam restore hash mismatch")
                os.replace(temporary, destination)
            return all(
                sha256_file(target / Path(relative))
                == sha256_file(backup_path / "files" / Path(relative))
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
