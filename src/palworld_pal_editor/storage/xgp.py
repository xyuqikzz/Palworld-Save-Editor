from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import os
import shutil
import sys
import tempfile
import time
from typing import Callable
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

from .discovery import (
    GLOBAL_PALBOX_SCOPE_ID,
    XgpSourceCatalog,
    global_palbox_bindings,
    world_bindings,
)
from .steam import _native_path, sha256_file, snapshot_tree
from .wgs_format import (
    WgsFormatError,
    encode_index,
    encode_palworld_payload,
    normalize_palworld_payload,
    parse_container,
    parse_index,
    select_payload_folder,
)


_FILETIME_EPOCH_OFFSET = 11644473600


def _display_path(path: str | Path) -> Path:
    """Return an ordinary absolute path after Windows extended-path I/O."""
    value = str(path)
    if os.name == "nt":
        if value.startswith("\\\\?\\UNC\\"):
            value = "\\\\" + value[8:]
        elif value.startswith("\\\\?\\"):
            value = value[4:]
    return Path(value).absolute()


def _windows_process_names() -> tuple[str, ...]:
    import ctypes
    from ctypes import wintypes

    class ProcessEntry32W(ctypes.Structure):
        _fields_ = (
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        )

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_snapshot = kernel32.CreateToolhelp32Snapshot
    create_snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    create_snapshot.restype = wintypes.HANDLE
    process_first = kernel32.Process32FirstW
    process_first.argtypes = (wintypes.HANDLE, ctypes.POINTER(ProcessEntry32W))
    process_first.restype = wintypes.BOOL
    process_next = kernel32.Process32NextW
    process_next.argtypes = (wintypes.HANDLE, ctypes.POINTER(ProcessEntry32W))
    process_next.restype = wintypes.BOOL
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL

    snapshot = create_snapshot(0x00000002, 0)
    if snapshot == wintypes.HANDLE(-1).value:
        error_code = ctypes.get_last_error()
        raise OSError(error_code, "CreateToolhelp32Snapshot failed")

    names: list[str] = []
    entry = ProcessEntry32W()
    entry.dwSize = ctypes.sizeof(entry)
    try:
        if not process_first(snapshot, ctypes.byref(entry)):
            error_code = ctypes.get_last_error()
            raise OSError(error_code, "Process32FirstW failed")
        while True:
            names.append(entry.szExeFile)
            if process_next(snapshot, ctypes.byref(entry)):
                continue
            error_code = ctypes.get_last_error()
            if error_code not in (0, 18):
                raise OSError(error_code, "Process32NextW failed")
            break
    finally:
        close_handle(snapshot)
    return tuple(names)


class PalworldProcessChecker:
    PROCESS_NAMES = (
        "Palworld-WinGDK-Shipping.exe",
        "Palworld.exe",
    )

    def __call__(self) -> bool:
        if sys.platform != "win32":
            return False
        try:
            process_names = {name.casefold() for name in _windows_process_names()}
        except Exception as error:
            raise DomainError(
                code="WGS_GAME_RUNNING",
                message="Palworld process state could not be verified safely.",
                retryable=True,
                http_status=409,
            ) from error
        return any(name.casefold() in process_names for name in self.PROCESS_NAMES)


def _validate_workspace(path: Path) -> None:
    from palworld_pal_editor.core.save_manager import SaveManager

    if SaveManager().open(str(path), lazy_players=True) is None:
        raise ValueError("normalized workspace is not a readable Palworld save")


class XgpWgsAdapter:
    """WGS implementation hidden behind the SaveStorage Interface."""

    def __init__(
        self,
        *,
        catalog: XgpSourceCatalog,
        process_checker: Callable[[], bool] | None = None,
        workspace_validator: Callable[[Path], None] | None = None,
        workspace_root: Path | None = None,
        backup_root: Path | None = None,
        stability_delay: float = 0.05,
    ) -> None:
        self._catalog = catalog
        self._process_checker = process_checker or PalworldProcessChecker()
        self._workspace_validator = workspace_validator or _validate_workspace
        self._workspace_root = workspace_root.resolve() if workspace_root else None
        self._backup_root = backup_root.resolve() if backup_root else None
        self._stability_delay = max(0.0, stability_delay)

    def open(self, source: SaveSource) -> OpenedSave:
        self._validate_source(source)
        self._ensure_game_stopped()
        self._recover_incomplete_journals(source)
        workspace: Path | None = None
        try:
            first = self._read_world(source)
            if self._stability_delay:
                time.sleep(self._stability_delay)
            second = self._read_world(source)
            if first[2] != second[2] or first[3] != second[3]:
                raise DomainError(
                    code="WGS_SOURCE_CHANGED",
                    message="The Game Pass save changed while it was being opened.",
                    retryable=True,
                    http_status=409,
                )
            logical_files, metadata, snapshot, bindings_snapshot = second
            if self._workspace_root is not None:
                _native_path(self._workspace_root).mkdir(parents=True, exist_ok=True)
            workspace = _display_path(
                tempfile.mkdtemp(
                    prefix="palworld-editor-xgp-",
                    dir=(
                        str(_native_path(self._workspace_root))
                        if self._workspace_root
                        else None
                    ),
                )
            ).resolve()
            for root in self._catalog.roots:
                try:
                    _native_path(workspace).relative_to(_native_path(root))
                except ValueError:
                    continue
                raise DomainError(
                    code="WGS_STAGE_FAILED",
                    message="The private workspace must be outside the WGS directory.",
                    http_status=500,
                )
            for relative_path, logical in logical_files.items():
                payload_relative = metadata[relative_path]["payload_relative"]
                source_payload = source.canonical_path / Path(payload_relative)
                destination = workspace / Path(relative_path)
                _native_path(destination.parent).mkdir(parents=True, exist_ok=True)
                normalized = normalize_palworld_payload(
                    _native_path(source_payload).read_bytes()
                )
                _native_path(destination).write_bytes(normalized.data)
                if sha256_file(destination) != logical.sha256:
                    raise OSError("workspace extraction hash mismatch")
            try:
                self._workspace_validator(workspace)
            except Exception as error:
                raise DomainError(
                    code="WGS_RELOAD_FAILED",
                    message="The normalized Game Pass save cannot be opened safely.",
                    http_status=422,
                ) from error
            snapshot = type(snapshot)(
                files=snapshot.files,
                world_bindings=bindings_snapshot,
            )
            return OpenedSave(
                source=source,
                workspace=workspace,
                logical_files=logical_files,
                snapshot=snapshot,
                cleanup_required=True,
                storage_metadata={"bindings": metadata},
            )
        except DomainError:
            if workspace is not None:
                shutil.rmtree(_native_path(workspace), ignore_errors=True)
            raise
        except (OSError, WgsFormatError) as error:
            if workspace is not None:
                shutil.rmtree(_native_path(workspace), ignore_errors=True)
            raise DomainError(
                code="WGS_CONTAINER_INCOMPLETE",
                message="The selected Game Pass save has an incomplete container or payload.",
                retryable=True,
                http_status=422,
            ) from error

    def commit(self, request: StorageCommitRequest) -> StorageCommitResult:
        opened = request.opened
        self._validate_source(opened.source)
        self._ensure_game_stopped()
        if request.target_path is not None:
            raise DomainError(
                code="WGS_COMMIT_FAILED",
                message="Game Pass saves can only be committed to their original slot.",
                field="target",
                http_status=400,
            )
        changed = tuple(
            dict.fromkeys(str(path).replace("\\", "/") for path in request.changed_files)
        )
        if not changed:
            return StorageCommitResult(
                platform=SavePlatform.XGP,
                written_files=(),
                backup_path=None,
                manifest_path=None,
                source_reloaded=True,
            )
        for relative_path in changed:
            if relative_path not in opened.logical_files:
                raise DomainError(
                    code="WGS_STAGE_FAILED",
                    message="A changed logical file is not mapped to the selected WGS world.",
                    http_status=422,
                )
            staged = request.staged_workspace / Path(relative_path)
            if not _native_path(staged).is_file():
                raise DomainError(
                    code="WGS_STAGE_FAILED",
                    message="A changed logical file is missing from staging.",
                    http_status=500,
                )
            if request.verify_file is not None:
                try:
                    request.verify_file(staged, relative_path)
                except Exception as error:
                    raise DomainError(
                        code="WGS_STAGE_FAILED",
                        message="A staged Game Pass save failed GVAS verification.",
                        http_status=422,
                    ) from error

        try:
            current = self._read_world(opened.source)
        except DomainError as error:
            if error.code in {
                "WGS_CONTAINER_INCOMPLETE",
                "WGS_WORLD_AMBIGUOUS",
                "WGS_INDEX_UNSUPPORTED",
            }:
                raise DomainError(
                    code="WGS_SOURCE_CHANGED",
                    message="The Game Pass source changed after this session opened.",
                    retryable=True,
                    http_status=409,
                ) from error
            raise
        current_logical, current_metadata, current_snapshot, current_bindings = current
        if (
            current_snapshot.files != opened.snapshot.files
            or current_bindings != opened.snapshot.world_bindings
        ):
            raise DomainError(
                code="WGS_SOURCE_CHANGED",
                message="The Game Pass source changed after this session opened.",
                retryable=True,
                http_status=409,
            )

        backup_path = self._new_backup_path(opened.source)
        manifest_path: Path | None = None
        manifest: tuple[dict[str, object], ...] = ()
        try:
            manifest_path, manifest = self._create_verified_backup(
                opened.source, current_snapshot, backup_path, request
            )
            self._fail(request, "after_backup", {"backup_path": str(backup_path)})
            try:
                stable = self._read_world(opened.source)
            except DomainError as error:
                raise source_changed(
                    code="WGS_SOURCE_CHANGED",
                    message=(
                        "The Game Pass source changed while its backup "
                        "was created."
                    ),
                    backup_path=backup_path,
                    phase="verify_source_after_backup",
                    failed_file=error.details.get("path"),
                ) from error
            except Exception as error:
                raise source_changed(
                    code="WGS_SOURCE_CHANGED",
                    message=(
                        "The Game Pass source changed while its backup "
                        "was created."
                    ),
                    backup_path=backup_path,
                    phase="verify_source_after_backup",
                    failed_file=None,
                    error=error,
                ) from error
            if stable[2].files != current_snapshot.files or stable[3] != current_bindings:
                before_files = current_snapshot.by_path()
                after_files = stable[2].by_path()
                failed_file = next(
                    (
                        relative
                        for relative in sorted(
                            set(before_files) | set(after_files)
                        )
                        if before_files.get(relative)
                        != after_files.get(relative)
                    ),
                    None,
                )
                raise source_changed(
                    code="WGS_SOURCE_CHANGED",
                    message=(
                        "The Game Pass source changed while its backup "
                        "was created."
                    ),
                    backup_path=backup_path,
                    phase="verify_source_after_backup",
                    failed_file=failed_file,
                )
        except DomainError:
            raise
        except Exception as error:
            raise backup_failure(
                code="WGS_BACKUP_FAILED",
                message="A complete verified WGS backup could not be created.",
                backup_path=backup_path,
                phase="verify_source_after_backup",
                failed_file=None,
                error=error,
            ) from error

        candidate_dir = request.staged_workspace / ".wgs-candidates"
        try:
            _native_path(candidate_dir).mkdir(parents=False, exist_ok=False)
            index = parse_index(
                _native_path(
                    opened.source.canonical_path / "containers.index"
                ).read_bytes()
            )
            staged_containers: set[str] = set()
            for relative_path in changed:
                container_relative = str(
                    current_metadata[relative_path]["container_file_relative"]
                )
                if container_relative in staged_containers:
                    continue
                staged_containers.add(container_relative)
                source_container = opened.source.canonical_path / Path(container_relative)
                candidate_container = candidate_dir / Path(container_relative)
                _native_path(candidate_container.parent).mkdir(
                    parents=True, exist_ok=True
                )
                self._fail(
                    request,
                    "before_container_stage",
                    {"path": relative_path},
                )
                shutil.copy2(
                    _native_path(source_container),
                    _native_path(candidate_container),
                )
                parsed_container = parse_container(
                    _native_path(candidate_container).read_bytes()
                )
                if sha256_file(candidate_container) != sha256_file(source_container):
                    raise OSError("container candidate hash mismatch")
                self._fail(
                    request,
                    "after_container_stage",
                    {"path": relative_path, "file_count": len(parsed_container.files)},
                )
            now_filetime = int((time.time() + _FILETIME_EPOCH_OFFSET) * 10_000_000)
            payload_candidates: dict[str, Path] = {}
            for relative_path in changed:
                metadata = current_metadata[relative_path]
                position = int(metadata["index_position"])
                payload_relative = str(metadata["payload_relative"])
                staged = request.staged_workspace / Path(relative_path)
                staged_data = _native_path(staged).read_bytes()
                encoding = metadata.get("payload_encoding")
                prefix_hex = metadata.get("payload_header_prefix")
                if not isinstance(encoding, str) or not isinstance(prefix_hex, str):
                    raise WgsFormatError(
                        "INVALID_METADATA",
                        "The WGS payload encoding metadata is invalid.",
                        0,
                    )
                try:
                    header_prefix = bytes.fromhex(prefix_hex)
                except ValueError as error:
                    raise WgsFormatError(
                        "INVALID_METADATA",
                        "The WGS payload header prefix is not valid hexadecimal.",
                        0,
                    ) from error
                encoded_data = encode_palworld_payload(
                    staged_data,
                    encoding,
                    header_prefix,
                )

                candidate_payload = candidate_dir / Path(payload_relative)
                _native_path(candidate_payload.parent).mkdir(
                    parents=True, exist_ok=True
                )
                self._write_bytes_durable(candidate_payload, encoded_data)
                payload_candidates[relative_path] = candidate_payload

                index = index.replace_entry(
                    position,
                    index.entries[position].with_pending_sync_payload(
                        size=len(encoded_data),
                        modified_filetime=now_filetime,
                    ),
                )
            index = replace(index, modified_filetime=now_filetime)
            index_candidate = candidate_dir / "containers.index"
            self._write_bytes_durable(index_candidate, encode_index(index))
            parse_index(_native_path(index_candidate).read_bytes())
        except DomainError:
            raise
        except Exception as error:
            raise DomainError(
                code="WGS_STAGE_FAILED",
                message="WGS commit candidates could not be staged and verified.",
                details={"backup_path": str(backup_path)},
                http_status=500,
            ) from error

        journal_path = backup_path / "journal.json"
        progress: list[str] = []
        journal = {
            "schema_version": 1,
            "source_id": opened.source.source_id,
            "world_id": opened.source.world_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "planned": [
                str(current_metadata[path]["payload_relative"]) for path in changed
            ]
            + ["containers.index"],
            "candidate_hashes": {
                str(current_metadata[path]["payload_relative"]): sha256_file(
                    payload_candidates[path]
                )
                for path in changed
            }
            | {"containers.index": sha256_file(index_candidate)},
            "replaced": progress,
            "in_flight": None,
            "status": "prepared",
        }
        self._write_json_durable(journal_path, journal)
        self._ensure_game_stopped()

        try:
            for relative_path in changed:
                payload_relative = str(current_metadata[relative_path]["payload_relative"])
                candidate_payload = payload_candidates[relative_path]
                target = opened.source.canonical_path / Path(payload_relative)
                journal["in_flight"] = payload_relative
                self._write_json_durable(journal_path, journal)
                self._fail(request, "before_payload_replace", {"path": relative_path})
                self._replace_from_candidate(candidate_payload, target)
                progress.append(payload_relative)
                journal["in_flight"] = None
                journal["status"] = "committing"
                self._write_json_durable(journal_path, journal)
                self._fail(request, "after_payload_replace", {"path": relative_path})

            journal["in_flight"] = "containers.index"
            self._write_json_durable(journal_path, journal)
            self._fail(request, "before_index_replace", {})
            self._replace_from_candidate(index_candidate, opened.source.canonical_path / "containers.index")
            progress.append("containers.index")
            journal["in_flight"] = None
            journal["status"] = "verifying"
            self._write_json_durable(journal_path, journal)
            self._fail(request, "after_index_replace", {})

            self._ensure_game_stopped()
            self._fail(request, "before_final_reopen", {})
            final = self._read_world(opened.source)
            final_logical, final_metadata, final_snapshot, final_bindings = final
            for relative_path in changed:
                staged_hash = sha256_file(request.staged_workspace / Path(relative_path))
                if final_logical[relative_path].sha256 != staged_hash:
                    raise DomainError(
                        code="WGS_RELOAD_FAILED",
                        message="A committed WGS payload does not match staging.",
                        http_status=500,
                    )
            for relative_path, logical in current_logical.items():
                if relative_path not in changed and final_logical[relative_path].sha256 != logical.sha256:
                    raise DomainError(
                        code="WGS_RELOAD_FAILED",
                        message="An unchanged WGS payload changed during commit.",
                        http_status=500,
                    )
            self._verify_unchanged_physical_files(
                current_snapshot,
                final_snapshot,
                {
                    "containers.index",
                    *(str(current_metadata[path]["payload_relative"]) for path in changed),
                },
            )
            if request.verify_file is not None:
                verify_paths = set(changed)
                if "Level.sav" in final_logical:
                    verify_paths.add("Level.sav")
                with tempfile.TemporaryDirectory(
                    prefix="palworld-wgs-target-verify-"
                ) as verification_temp:
                    verification_root = Path(verification_temp)
                    for relative_path in sorted(verify_paths):
                        payload = opened.source.canonical_path / Path(
                            str(final_metadata[relative_path]["payload_relative"])
                        )
                        normalized = normalize_palworld_payload(
                            _native_path(payload).read_bytes()
                        )
                        verification_path = (
                            verification_root / Path(relative_path)
                        )
                        _native_path(verification_path.parent).mkdir(
                            parents=True,
                            exist_ok=True,
                        )
                        _native_path(verification_path).write_bytes(normalized.data)
                        request.verify_file(
                            verification_path,
                            relative_path,
                        )
            for relative_path in changed:
                workspace_file = opened.workspace / Path(relative_path)
                _native_path(workspace_file.parent).mkdir(parents=True, exist_ok=True)
                shutil.copy2(
                    _native_path(request.staged_workspace / Path(relative_path)),
                    _native_path(workspace_file),
                )
            opened.logical_files = final_logical
            opened.storage_metadata["bindings"] = final_metadata
            opened.snapshot = type(final_snapshot)(
                files=final_snapshot.files,
                world_bindings=final_bindings,
            )
            journal["status"] = "committed"
            journal["in_flight"] = None
            self._write_json_durable(journal_path, journal)
            return StorageCommitResult(
                platform=SavePlatform.XGP,
                written_files=tuple(PurePosixPath(path) for path in changed),
                backup_path=backup_path,
                manifest_path=manifest_path,
                source_reloaded=True,
                recovery_status="not_needed",
                journal_path=journal_path,
                manifest=manifest,
            )
        except Exception as error:
            original_code = (
                error.code
                if isinstance(error, DomainError) and error.code == "WGS_RELOAD_FAILED"
                else "WGS_COMMIT_FAILED"
            )
            recovered = self._recover(
                request=request,
                backup_path=backup_path,
                progress=progress,
                expected_snapshot=current_snapshot,
                journal_path=journal_path,
                journal=journal,
            )
            if not recovered:
                raise DomainError(
                    code="WGS_RECOVERY_FAILED",
                    message="WGS commit failed and automatic recovery could not be verified.",
                    details={
                        "backup_path": str(backup_path),
                        "manifest_path": str(manifest_path),
                        "journal_path": str(journal_path),
                        "recovery_status": "failed",
                    },
                    http_status=500,
                ) from error
            raise DomainError(
                code=original_code,
                message="WGS commit failed; the original source was restored and verified.",
                details={
                    "backup_path": str(backup_path),
                    "manifest_path": str(manifest_path),
                    "journal_path": str(journal_path),
                    "recovery_status": "restored",
                    "recovered": True,
                },
                retryable=True,
                http_status=500,
            ) from error

    def close(self, opened: OpenedSave) -> None:
        if opened.cleanup_required:
            shutil.rmtree(_native_path(opened.workspace), ignore_errors=True)

    def _validate_source(self, source: SaveSource) -> None:
        if source.platform is not SavePlatform.XGP:
            raise DomainError(
                code="WGS_NOT_FOUND",
                message="The selected source is not a Game Pass save.",
                http_status=404,
            )
        trusted = self._catalog.resolve(source.source_id)
        if (
            trusted.canonical_path != source.canonical_path.resolve()
            or trusted.world_id != source.world_id
        ):
            raise DomainError(
                code="WGS_NOT_FOUND",
                message="The selected Game Pass source is not trusted.",
                http_status=404,
            )
        if source.status != "available":
            raise DomainError(
                code="WGS_WORLD_AMBIGUOUS",
                message="The selected Game Pass world has ambiguous container mappings.",
                retryable=True,
                http_status=409,
            )
        if not any(source.canonical_path.parent.resolve() == root for root in self._catalog.roots):
            raise DomainError(
                code="WGS_NOT_FOUND",
                message="The selected Game Pass source is outside the discovered WGS roots.",
                http_status=404,
            )

    def _ensure_game_stopped(self) -> None:
        if self._process_checker():
            raise DomainError(
                code="WGS_GAME_RUNNING",
                message="Palworld must be fully closed before opening or saving Game Pass data.",
                retryable=True,
                http_status=409,
            )

    def _backup_source_root(self, source: SaveSource) -> Path:
        if self._backup_root is not None:
            root = self._backup_root
        else:
            local = os.environ.get("LOCALAPPDATA")
            root = (
                Path(local) / "Palworld-Pal-Editor" / "WgsBackups"
                if local
                else Path(tempfile.gettempdir()) / "Palworld-Pal-Editor-WgsBackups"
            )
        root = root.resolve()
        for wgs_root in self._catalog.roots:
            try:
                root.relative_to(wgs_root)
            except ValueError:
                continue
            raise DomainError(
                code="WGS_BACKUP_FAILED",
                message="The WGS backup directory must be outside WGS.",
                details={
                    "backup_path": str(root / source.source_id),
                    "phase": "validate_backup_location",
                    "failed_file": None,
                    "os_error_code": None,
                    "os_error_category": "unsafe_location",
                    "retryable": False,
                },
                http_status=500,
            )
        return root / source.source_id

    def _new_backup_path(self, source: SaveSource) -> Path:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        transaction_id = uuid.uuid4().hex[:16]
        return self._backup_source_root(source) / f"{timestamp}-{transaction_id}"

    def _recover_incomplete_journals(self, source: SaveSource) -> None:
        source_backups = self._backup_source_root(source)
        native_source_backups = _native_path(source_backups)
        if not native_source_backups.is_dir():
            return
        operation_names = sorted(
            operation.name
            for operation in native_source_backups.iterdir()
            if operation.is_dir() and (operation / "journal.json").is_file()
        )
        for operation_name in operation_names:
            journal_path = source_backups / operation_name / "journal.json"
            manifest_path = journal_path.parent / "manifest.json"
            journal: dict[str, object] | None = None
            try:
                journal = json.loads(
                    _native_path(journal_path).read_text(encoding="utf-8")
                )
                if not isinstance(journal, dict):
                    raise ValueError("WGS journal must be an object")
                status = journal.get("status")
                if status in {"committed", "restored", "abandoned"}:
                    continue
                if status == "recovery_failed":
                    raise ValueError("a previous WGS recovery is unresolved")
                if journal.get("schema_version") != 1:
                    raise ValueError("unsupported WGS journal schema")
                if journal.get("source_id") != source.source_id:
                    raise ValueError("WGS journal source mismatch")
                replaced = self._journal_paths(journal.get("replaced", []))
                in_flight_value = journal.get("in_flight")
                in_flight = (
                    self._journal_paths([in_flight_value])[0]
                    if in_flight_value is not None
                    else None
                )
                if status == "prepared" and not replaced and in_flight is None:
                    journal["status"] = "abandoned"
                    self._write_json_durable(journal_path, journal)
                    continue
                if status not in {"prepared", "committing", "verifying"}:
                    raise ValueError("unknown WGS journal state")

                manifest_document = json.loads(
                    _native_path(manifest_path).read_text(encoding="utf-8")
                )
                if manifest_document.get("source_id") != source.source_id:
                    raise ValueError("WGS backup manifest source mismatch")
                expected_files: list[StorageFileSnapshot] = []
                for item in manifest_document.get("files", []):
                    relative = self._journal_paths([item["path"]])[0]
                    expected_files.append(
                        StorageFileSnapshot(
                            relative_path=PurePosixPath(relative),
                            size=int(item["size"]),
                            mtime_ns=int(item["mtime_ns"]),
                            sha256=str(item["sha256"]),
                        )
                    )
                expected = StorageSnapshot(
                    files=tuple(
                        sorted(expected_files, key=lambda item: item.relative_path)
                    )
                )
                if not expected.files:
                    raise ValueError("WGS backup manifest is empty")
                expected_by_path = expected.by_path()
                if len(expected_by_path) != len(expected.files):
                    raise ValueError("duplicate WGS manifest path")
                current = snapshot_tree(
                    source.canonical_path, reject_symlinks=True
                )
                current_by_path = current.by_path()
                if set(current_by_path) != set(expected_by_path):
                    raise ValueError("WGS file set changed after interrupted commit")

                recovery_paths = list(replaced)
                if in_flight is not None and in_flight not in recovery_paths:
                    recovery_paths.append(in_flight)
                candidates = journal.get("candidate_hashes")
                if not isinstance(candidates, dict):
                    raise ValueError("WGS candidate hashes are missing")
                planned = set(self._journal_paths(journal.get("planned", [])))
                if not set(recovery_paths).issubset(planned):
                    raise ValueError("WGS recovery path was not planned")
                for relative, expected_file in expected_by_path.items():
                    current_file = current_by_path[relative]
                    if relative not in recovery_paths:
                        if current_file != expected_file:
                            raise ValueError(
                                "unrelated WGS file changed after interrupted commit"
                            )
                        continue
                    candidate_hash = candidates.get(relative)
                    if not isinstance(candidate_hash, str) or current_file.sha256 not in {
                        expected_file.sha256,
                        candidate_hash,
                    }:
                        raise ValueError(
                            "interrupted WGS target does not match backup or candidate"
                        )

                for relative in reversed(recovery_paths):
                    backup_file = journal_path.parent / "files" / Path(relative)
                    expected_file = expected_by_path[relative]
                    native_backup_file = _native_path(backup_file)
                    if (
                        not native_backup_file.is_file()
                        or native_backup_file.stat().st_size != expected_file.size
                        or sha256_file(backup_file) != expected_file.sha256
                    ):
                        raise ValueError("WGS recovery backup failed verification")
                    self._replace_from_candidate(
                        backup_file, source.canonical_path / Path(relative)
                    )
                if snapshot_tree(
                    source.canonical_path, reject_symlinks=True
                ).files != expected.files:
                    raise ValueError("interrupted WGS recovery verification failed")
                journal["in_flight"] = None
                journal["status"] = "restored"
                self._write_json_durable(journal_path, journal)
            except DomainError:
                raise
            except Exception as error:
                try:
                    if isinstance(journal, dict):
                        journal["status"] = "recovery_failed"
                        self._write_json_durable(journal_path, journal)
                except Exception:
                    pass
                raise DomainError(
                    code="WGS_RECOVERY_FAILED",
                    message="An interrupted Game Pass save could not be recovered safely.",
                    details={
                        "backup_path": str(journal_path.parent),
                        "manifest_path": str(manifest_path),
                        "journal_path": str(journal_path),
                        "recovery_status": "failed",
                    },
                    http_status=500,
                ) from error

    @staticmethod
    def _journal_paths(values) -> list[str]:
        if not isinstance(values, list):
            raise ValueError("WGS journal paths must be a list")
        result: list[str] = []
        for value in values:
            if not isinstance(value, str):
                raise ValueError("WGS journal path must be text")
            path = PurePosixPath(value.replace("\\", "/"))
            if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
                raise ValueError("unsafe WGS journal path")
            result.append(value)
        return result

    def _create_verified_backup(self, source, snapshot, backup_path, request):
        phase = "create_backup_directory"
        failed_file: str | None = None
        try:
            files_root = backup_path / "files"
            _native_path(files_root).mkdir(parents=True, exist_ok=False)
            manifest: list[dict[str, object]] = []
            for item in snapshot.files:
                relative = item.relative_path.as_posix()
                failed_file = relative
                source_file = source.canonical_path / Path(relative)
                backup_file = files_root / Path(relative)
                phase = "create_backup_directory"
                _native_path(backup_file.parent).mkdir(parents=True, exist_ok=True)
                phase = "copy_file"
                self._fail(request, "before_backup_copy", {"path": relative})
                try:
                    shutil.copy2(
                        _native_path(source_file),
                        _native_path(backup_file),
                    )
                except FileNotFoundError as error:
                    if not _native_path(source_file).is_file():
                        raise source_changed(
                            code="WGS_SOURCE_CHANGED",
                            message=(
                                "The Game Pass source changed while its "
                                "backup was created."
                            ),
                            backup_path=backup_path,
                            phase="verify_source_after_backup",
                            failed_file=relative,
                            error=error,
                        ) from error
                    raise
                try:
                    source_stat = _native_path(source_file).stat()
                    source_hash = sha256_file(source_file)
                except OSError as error:
                    raise source_changed(
                        code="WGS_SOURCE_CHANGED",
                        message=(
                            "The Game Pass source changed while its backup "
                            "was created."
                        ),
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
                        code="WGS_SOURCE_CHANGED",
                        message=(
                            "The Game Pass source changed while its backup "
                            "was created."
                        ),
                        backup_path=backup_path,
                        phase="verify_source_after_backup",
                        failed_file=relative,
                    )
                phase = "verify_copy"
                copied = _native_path(backup_file).stat()
                copied_hash = sha256_file(backup_file)
                if copied.st_size != item.size or copied_hash != item.sha256:
                    raise BackupVerificationError(
                        "WGS backup file verification failed"
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
            try:
                from palworld_pal_editor.config import version_info

                app_version = version_info()
            except Exception:
                app_version = "unknown"
            manifest_path = backup_path / "manifest.json"
            failed_file = "manifest.json"
            document = {
                "schema_version": 1,
                "format_version": "wgs-v14-container-v4",
                "application_version": app_version,
                "source_id": source.source_id,
                "world_id": source.source_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "files": manifest,
            }
            phase = "write_manifest"
            self._write_json_durable(manifest_path, document)
            phase = "read_manifest"
            manifest_text = _native_path(manifest_path).read_text(encoding="utf-8")
            phase = "verify_manifest"
            try:
                loaded = json.loads(manifest_text)
            except (json.JSONDecodeError, TypeError) as error:
                raise BackupVerificationError(
                    "WGS backup manifest could not be parsed"
                ) from error
            if loaded != document:
                raise BackupVerificationError(
                    "WGS backup manifest verification failed"
                )
            return manifest_path, tuple(manifest)
        except DomainError:
            raise
        except Exception as error:
            raise backup_failure(
                code="WGS_BACKUP_FAILED",
                message="A complete verified WGS backup could not be created.",
                backup_path=backup_path,
                phase=phase,
                failed_file=failed_file,
                error=error,
            ) from error

    def _recover(
        self,
        *,
        request,
        backup_path: Path,
        progress: list[str],
        expected_snapshot,
        journal_path: Path,
        journal: dict[str, object],
    ) -> bool:
        try:
            self._fail(request, "before_recovery", {"progress": list(progress)})
            recovery_paths = list(progress)
            in_flight = journal.get("in_flight")
            if isinstance(in_flight, str) and in_flight not in recovery_paths:
                recovery_paths.append(in_flight)
            restored: set[str] = set()
            for relative in reversed(recovery_paths):
                if relative in restored:
                    continue
                restored.add(relative)
                backup_file = backup_path / "files" / Path(relative)
                target = request.opened.source.canonical_path / Path(relative)
                self._replace_from_candidate(backup_file, target)
            if snapshot_tree(
                request.opened.source.canonical_path, reject_symlinks=True
            ).files != expected_snapshot.files:
                raise OSError("recovered WGS tree hash or metadata mismatch")
            journal["in_flight"] = None
            journal["status"] = "restored"
            self._write_json_durable(journal_path, journal)
            return True
        except Exception:
            try:
                journal["status"] = "recovery_failed"
                self._write_json_durable(journal_path, journal)
            except Exception:
                pass
            return False

    def _verify_unchanged_physical_files(self, before, after, allowed: set[str]) -> None:
        before_files = before.by_path()
        after_files = after.by_path()
        if set(before_files) != set(after_files):
            raise DomainError(
                code="WGS_RELOAD_FAILED",
                message="The physical WGS file set changed during commit.",
                http_status=500,
            )
        for relative, expected in before_files.items():
            if relative in allowed:
                continue
            if after_files[relative].sha256 != expected.sha256:
                raise DomainError(
                    code="WGS_RELOAD_FAILED",
                    message="An unrelated WGS physical file changed during commit.",
                    http_status=500,
                )

    def _replace_from_candidate(self, candidate: Path, target: Path) -> None:
        temporary = target.with_name(f".{target.name}.pal-editor-{uuid.uuid4()}.tmp")
        try:
            shutil.copy2(_native_path(candidate), _native_path(temporary))
            if sha256_file(temporary) != sha256_file(candidate):
                raise OSError("same-volume WGS staging hash mismatch")
            with _native_path(temporary).open("r+b") as stream:
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(_native_path(temporary), _native_path(target))
            self._fsync_directory(target.parent)
        finally:
            try:
                _native_path(temporary).unlink(missing_ok=True)
            except OSError:
                pass

    def _write_bytes_durable(self, path: Path, data: bytes) -> None:
        with _native_path(path).open("wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())

    def _write_json_durable(self, path: Path, document: dict[str, object]) -> None:
        temporary = path.with_name(f".{path.name}.{uuid.uuid4()}.tmp")
        with _native_path(temporary).open(
            "w", encoding="utf-8", newline="\n"
        ) as stream:
            json.dump(document, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(_native_path(temporary), _native_path(path))
        self._fsync_directory(path.parent)

    def _fsync_directory(self, path: Path) -> None:
        try:
            descriptor = os.open(_native_path(path), os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(descriptor)
        except OSError:
            pass
        finally:
            os.close(descriptor)

    def _fail(self, request: StorageCommitRequest, stage: str, context: dict[str, object]) -> None:
        if request.failure_hook is not None:
            request.failure_hook(stage, dict(context))

    def _read_world(self, source: SaveSource):
        user = source.canonical_path
        index_path = user / "containers.index"
        try:
            index = parse_index(_native_path(index_path).read_bytes())
        except WgsFormatError as error:
            raise DomainError(
                code="WGS_INDEX_UNSUPPORTED",
                message="The Game Pass container index version or structure is unsupported.",
                http_status=422,
            ) from error
        if not index.package_name.startswith("PocketpairInc.Palworld_"):
            raise DomainError(
                code="WGS_INDEX_UNSUPPORTED",
                message="The WGS index does not belong to Palworld.",
                http_status=422,
            )
        if source.world_id == GLOBAL_PALBOX_SCOPE_ID:
            selected = global_palbox_bindings(index)
        else:
            selected = world_bindings(index).get(source.world_id or "")
        if selected is None:
            raise DomainError(
                code="WGS_SOURCE_CHANGED",
                message="The selected save scope no longer exists in the WGS index.",
                retryable=True,
                http_status=409,
            )
        if any(len(positions) != 1 for positions in selected.values()):
            raise DomainError(
                code="WGS_WORLD_AMBIGUOUS",
                message="The selected world has duplicate logical container mappings.",
                http_status=409,
            )
        physical_entries: dict[
            int, tuple[PurePosixPath, PurePosixPath, tuple[PurePosixPath, ...]]
        ] = {}
        referenced_payloads: set[str] = set()
        for position, entry in enumerate(index.entries):
            container_relative = PurePosixPath(entry.container_folder)
            container_file_relative = (
                container_relative / f"container.{entry.sequence}"
            )
            container_path = user / Path(container_relative.as_posix())
            container_file_path = user / Path(container_file_relative.as_posix())
            try:
                container = parse_container(
                    _native_path(container_file_path).read_bytes()
                )
                available = {
                    path.name.upper()
                    for path in _native_path(container_path).iterdir()
                    if path.is_file()
                    and not path.name.casefold().startswith("container.")
                }
                if not container.files:
                    raise WgsFormatError(
                        "DANGLING_REFERENCE",
                        "A WGS container does not reference any payload.",
                        4,
                    )
                payloads: list[PurePosixPath] = []
                total_size = 0
                for container_file in container.files:
                    payload_name = select_payload_folder(container_file, available)
                    payload_relative = container_relative / payload_name
                    if payload_relative.as_posix() in referenced_payloads:
                        raise WgsFormatError(
                            "DUPLICATE_REFERENCE",
                            "Multiple WGS records reference the same payload.",
                            0,
                        )
                    referenced_payloads.add(payload_relative.as_posix())
                    payloads.append(payload_relative)
                    total_size += _native_path(
                        user / Path(payload_relative.as_posix())
                    ).stat().st_size
                if total_size != entry.size:
                    raise WgsFormatError(
                        "INVALID_LENGTH",
                        "WGS payload size does not match its index record.",
                        0,
                    )
            except (OSError, WgsFormatError) as error:
                raise DomainError(
                    code="WGS_CONTAINER_INCOMPLETE",
                    message="A Game Pass container or payload is incomplete or ambiguous.",
                    retryable=True,
                    http_status=422,
                ) from error
            physical_entries[position] = (
                container_relative,
                container_file_relative,
                tuple(payloads),
            )

        logical_files: dict[str, LogicalSaveFile] = {}
        metadata: dict[str, dict[str, object]] = {}
        for relative_path, positions in sorted(selected.items()):
            position = positions[0]
            entry = index.entries[position]
            container_relative, container_file_relative, payloads = physical_entries[
                position
            ]
            if len(payloads) != 1:
                raise DomainError(
                    code="WGS_CONTAINER_INCOMPLETE",
                    message="A Palworld WGS container must reference exactly one payload.",
                    http_status=422,
                )
            payload_relative = payloads[0]
            payload_name = payload_relative.name
            payload_path = user / Path(payload_relative.as_posix())
            stat = _native_path(payload_path).stat()
            physical_bytes = _native_path(payload_path).read_bytes()
            physical_digest = hashlib.sha256(physical_bytes).hexdigest()
            normalized = normalize_palworld_payload(physical_bytes)
            digest = hashlib.sha256(normalized.data).hexdigest()
            logical = LogicalSaveFile(
                relative_path=PurePosixPath(relative_path),
                physical_identity=(
                    f"{entry.container_folder}/container.{entry.sequence}/{payload_name}"
                ),
                size=len(normalized.data),
                sha256=digest,
            )
            logical_files[relative_path] = logical
            metadata[relative_path] = {
                "index_position": position,
                "container_name": entry.name,
                "container_relative": container_relative.as_posix(),
                "container_file_relative": container_file_relative.as_posix(),
                "payload_relative": payload_relative.as_posix(),
                "payload_encoding": normalized.encoding,
                "payload_header_prefix": normalized.header_prefix.hex(),
                "physical_size": stat.st_size,
                "physical_sha256": physical_digest,
            }
        snapshot = snapshot_tree(user, reject_symlinks=True)
        bindings_snapshot = tuple(
            sorted((relative, logical.physical_identity) for relative, logical in logical_files.items())
        )
        return logical_files, metadata, snapshot, bindings_snapshot
