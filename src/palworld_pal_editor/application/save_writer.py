from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
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
from palworld_pal_editor.domain.models import SaveResult

from .save_session import SaveSession


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
        target: str | Path,
        expected_revision: int,
    ) -> SaveResult:
        if expected_revision != session.revision:
            raise stale_revision(expected_revision, session.revision)
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

        source = session.source.resolve()
        target_path = Path(target).resolve()
        if target_path != source and target_path.exists():
            raise DomainError(
                code="SAVE_TARGET_ALREADY_EXISTS",
                message="Saving to a different existing directory is not supported safely.",
                field="target",
                details={"target": str(target_path)},
                http_status=409,
            )
        if not target_path.parent.exists():
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
        staging_path = target_path.parent / f".{target_path.name}.pal-editor-staging-{operation_id}"
        backup_manifest: list[dict[str, Any]] = []
        replacement_progress: list[str] = []

        try:
            backup_manifest = self._create_verified_backup(
                source, backup_path, files, session.session_id
            )
            self._fail("after_backup", {"backup_path": str(backup_path)})
            if target_path == source:
                staging_path.mkdir(parents=False, exist_ok=False)
            else:
                shutil.copytree(source, staging_path)
            self._serialize_to_staging(session, staging_path, files)
            self._verify_staged(staging_path, files)
            self._fail("before_replace", {"staging_path": str(staging_path)})

            if target_path != source:
                os.replace(staging_path, target_path)
                replacement_progress.append(".")
                self._fail("after_replace", {"path": str(target_path)})
            else:
                for relative_path in files:
                    staged_file = staging_path / Path(relative_path)
                    target_file = target_path / Path(relative_path)
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(staged_file, target_file)
                    replacement_progress.append(relative_path)
                    self._write_progress(staging_path, replacement_progress)
                    self._fail(
                        "after_replace",
                        {"path": relative_path, "progress": list(replacement_progress)},
                    )
            self._verify_staged(target_path, files)
        except DomainError as error:
            if not replacement_progress:
                raise
            recovered = self._recover(
                source=source,
                target=target_path,
                backup_path=backup_path,
                files=files,
                progress=replacement_progress,
            )
            code = "WRITE_FAILED" if recovered else "RECOVERY_FAILED"
            raise DomainError(
                code=code,
                message=(
                    "Save validation failed and the original files were restored."
                    if recovered
                    else "Save validation and automatic recovery both failed."
                ),
                details={
                    "backup_path": str(backup_path),
                    "staging_path": str(staging_path),
                    "recovered": recovered,
                    "stage_error": error.code,
                },
                retryable=recovered,
                http_status=500,
            ) from error
        except Exception as error:
            recovered = self._recover(
                source=source,
                target=target_path,
                backup_path=backup_path,
                files=files,
                progress=replacement_progress,
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
                    "staging_path": str(staging_path),
                    "recovered": recovered,
                    "stage_error": type(error).__name__,
                },
                retryable=recovered,
                http_status=500,
            ) from error

        session.mark_saved(expected_revision)
        if staging_path.exists():
            shutil.rmtree(staging_path)
        return SaveResult(
            revision=session.revision,
            backup_path=str(backup_path),
            staging_path=None,
            written_files=tuple(files),
            manifest=tuple(backup_manifest),
            staged_reload_verified=True,
            target_reload_verified=True,
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

    def _create_verified_backup(
        self,
        source: Path,
        backup_path: Path,
        files: list[str],
        session_id: str,
    ) -> list[dict[str, Any]]:
        try:
            files_root = backup_path / "files"
            files_root.mkdir(parents=True, exist_ok=False)
            manifest: list[dict[str, Any]] = []
            for relative_path in files:
                source_file = source / Path(relative_path)
                if not source_file.is_file():
                    raise FileNotFoundError(source_file)
                backup_file = files_root / Path(relative_path)
                backup_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_file, backup_file)
                source_hash = _sha256(source_file)
                backup_hash = _sha256(backup_file)
                if source_hash != backup_hash:
                    raise OSError(f"Backup hash mismatch: {relative_path}")
                self._reload_file(backup_file, relative_path)
                manifest.append(
                    {
                        "path": relative_path,
                        "size": source_file.stat().st_size,
                        "sha256": source_hash,
                    }
                )
            manifest_path = backup_path / "manifest.json"
            with manifest_path.open("w", encoding="utf-8", newline="\n") as stream:
                json.dump(
                    {
                        "schema_version": 1,
                        "session_id": session_id,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "files": manifest,
                    },
                    stream,
                    ensure_ascii=False,
                    indent=2,
                )
                stream.write("\n")
            return manifest
        except Exception as error:
            raise DomainError(
                code="BACKUP_FAILED",
                message="A complete, verified backup could not be created.",
                details={"backup_path": str(backup_path)},
                http_status=500,
            ) from error

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

    def _recover(
        self,
        *,
        source: Path,
        target: Path,
        backup_path: Path,
        files: list[str],
        progress: list[str],
    ) -> bool:
        try:
            self._fail("before_recovery", {"progress": list(progress)})
            if target != source:
                if target.exists():
                    return False
                return True
            for relative_path in reversed(progress):
                backup_file = backup_path / "files" / Path(relative_path)
                target_file = target / Path(relative_path)
                restore_temp = target_file.with_name(f".{target_file.name}.restore-{uuid.uuid4()}")
                shutil.copy2(backup_file, restore_temp)
                if _sha256(restore_temp) != _sha256(backup_file):
                    raise OSError("Restore hash mismatch")
                os.replace(restore_temp, target_file)
            for relative_path in progress:
                manifest_hash = _sha256(backup_path / "files" / Path(relative_path))
                if _sha256(target / Path(relative_path)) != manifest_hash:
                    raise OSError("Recovered target hash mismatch")
            return True
        except Exception:
            return False

    def _write_progress(self, staging_path: Path, progress: list[str]) -> None:
        progress_path = staging_path / "replacement-progress.json"
        with progress_path.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump({"replaced": progress}, stream, indent=2)
            stream.write("\n")

    def _fail(self, stage: str, context: dict[str, Any]) -> None:
        if self._failure_hook is not None:
            self._failure_hook(stage, context)
