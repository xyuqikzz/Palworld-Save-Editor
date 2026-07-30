from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
import uuid
from time import perf_counter

from palworld_pal_editor.core.save_manager import SaveManager
from palworld_pal_editor.core.character_index import CharacterIndex
from palworld_pal_editor.domain.change_set import ChangeEntry, ChangeSet
from palworld_pal_editor.domain.errors import DomainError, stale_revision
from palworld_pal_editor.domain.models import (
    Capability,
    OpenedSave,
    PlayerSummary,
    SaveCompatibility,
    SavePlatform,
    SaveSource,
    SessionSummary,
)
from palworld_pal_editor.storage.base import SaveStorage
from palworld_pal_editor.storage.steam import SteamDirectoryAdapter, make_steam_source

from .local_data import LOCAL_DATA_RELATIVE_PATH, LocalDataDocument


class SaveSession:
    """Authority boundary for one loaded save and its in-memory changes."""

    def __init__(
        self,
        manager: SaveManager,
        source: Path,
        *,
        storage: SaveStorage | None = None,
        opened: OpenedSave | None = None,
    ) -> None:
        self._manager = manager
        if opened is None:
            active_storage = storage or SteamDirectoryAdapter()
            opened = active_storage.open(make_steam_source(source))
        else:
            active_storage = storage or SteamDirectoryAdapter()
        self._storage = active_storage
        self._opened = opened
        self._source = opened.source.canonical_path.resolve()
        self._workspace = opened.workspace.resolve()
        self._session_id = str(uuid.uuid4())
        self._opened_at = datetime.now(timezone.utc)
        self._revision = 0
        self._changes = ChangeSet()
        self._active_batch: dict[str, Any] | None = None
        self._raw_json_pending = False
        self._operation_seconds: dict[str, list[float]] = {}
        self._local_data = LocalDataDocument.open(self._workspace)
        self._local_data_selected = False
        self._local_data_source: Path | None = None
        self._compatibility = self._inspect_compatibility()
        self._dynamic_item_issue_baseline = (
            self._snapshot_dynamic_item_issue_fingerprints()
        )
        self._file_baseline = self._snapshot_file_metadata()

    @classmethod
    def open(
        cls, source: str | Path, *, manager: SaveManager | None = None
    ) -> "SaveSession":
        resolved = Path(source).resolve()
        active_manager = manager or SaveManager()
        storage = SteamDirectoryAdapter()
        opened = storage.open(make_steam_source(resolved))
        started = perf_counter()
        if active_manager.open(str(opened.workspace), lazy_players=True) is None:
            storage.close(opened)
            raise DomainError(
                code="INVALID_SAVE_PATH",
                message="The selected directory is not a readable Palworld save.",
                field="source",
                details={"source": str(resolved)},
                http_status=400,
            )
        session = cls(
            active_manager,
            resolved,
            storage=storage,
            opened=opened,
        )
        session._open_seconds = perf_counter() - started
        return session

    @classmethod
    def open_storage(
        cls,
        source: SaveSource,
        storage: SaveStorage,
        *,
        manager: SaveManager | None = None,
    ) -> "SaveSession":
        opened = storage.open(source)
        active_manager = manager or SaveManager()
        started = perf_counter()
        try:
            if active_manager.open(str(opened.workspace), lazy_players=True) is None:
                raise DomainError(
                    code="INVALID_SAVE_PATH",
                    message="The selected source is not a readable Palworld save.",
                    field="sourceId",
                    http_status=400,
                )
            session = cls(
                active_manager,
                source.canonical_path,
                storage=storage,
                opened=opened,
            )
            session._open_seconds = perf_counter() - started
            return session
        except Exception:
            storage.close(opened)
            raise

    @classmethod
    def from_loaded_manager(
        cls, manager: SaveManager, source: str | Path
    ) -> "SaveSession":
        if getattr(manager, "gvas_file", None) is None:
            raise ValueError("SaveManager is not loaded")
        return cls(manager, Path(source))

    @property
    def manager(self) -> SaveManager:
        return self._manager

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def revision(self) -> int:
        return self._revision

    @property
    def dynamic_item_issue_baseline(self) -> tuple[str, ...]:
        return self._dynamic_item_issue_baseline

    @property
    def batch_active(self) -> bool:
        """Whether an already-previewed outer batch owns the current mutation."""
        return self._active_batch is not None

    @property
    def raw_json_pending(self) -> bool:
        return self._raw_json_pending

    @property
    def source(self) -> Path:
        return self._source

    @property
    def workspace(self) -> Path:
        return self._workspace

    @property
    def platform(self) -> SavePlatform:
        return self._opened.source.platform

    @property
    def source_id(self) -> str:
        return self._opened.source.source_id

    @property
    def source_display_name(self) -> str:
        return self._opened.source.display_name

    @property
    def storage(self) -> SaveStorage:
        return self._storage

    @property
    def opened_save(self) -> OpenedSave:
        return self._opened

    @property
    def local_data(self) -> LocalDataDocument:
        return self._local_data

    @property
    def local_data_selected(self) -> bool:
        return self._local_data_selected

    @property
    def local_data_selection(self) -> dict[str, Any]:
        selected_path = self._local_data_source
        return {
            "required": True,
            "selected": self._local_data_selected,
            "platform": self.platform.value,
            "canSelectFile": self.platform is SavePlatform.STEAM,
            "source": (
                str(selected_path)
                if selected_path is not None
                and self.platform is SavePlatform.STEAM
                else (
                    self.source_display_name
                    if self._local_data_selected
                    else None
                )
            ),
            "reason": (
                None if self._local_data_selected else "LOCAL_DATA_NOT_SELECTED"
            ),
        }

    @property
    def save_capabilities(self) -> dict[str, Any]:
        fog_capability = (
            self._local_data.capability.to_dict()
            if self._local_data_selected
            else {
                "available": False,
                "reason": "LOCAL_DATA_NOT_SELECTED",
                "format": None,
                "maps": [],
            }
        )
        return {
            "commitOriginal": True,
            "exportSteamCopy": True,
            "targetPathEditable": self.platform is SavePlatform.STEAM,
            "cloudSyncVerified": False,
            "localDataSelection": self.local_data_selection,
            "fogOfWarClear": dict(fog_capability),
            "fogOfWarReset": dict(fog_capability),
        }

    def select_local_data(
        self,
        *,
        session_id: str,
        expected_revision: int,
        path: str | Path | None = None,
    ) -> dict[str, Any]:
        self.require_command(session_id, expected_revision)
        if self.changes():
            raise DomainError(
                code="LOCAL_DATA_SELECTION_REQUIRES_CLEAN_SESSION",
                message=(
                    "Save or discard pending changes before selecting "
                    "LocalData.sav."
                ),
                http_status=409,
            )

        if self.platform is SavePlatform.STEAM:
            if not isinstance(path, (str, Path)) or not str(path).strip():
                raise DomainError(
                    code="LOCAL_DATA_PATH_REQUIRED",
                    message="Select the LocalData.sav file to edit.",
                    field="path",
                    http_status=400,
                )
            candidate = Path(path)
            if not candidate.is_absolute():
                raise DomainError(
                    code="LOCAL_DATA_PATH_NOT_ABSOLUTE",
                    message="The LocalData.sav path must be absolute.",
                    field="path",
                    http_status=400,
                )
            candidate = candidate.resolve()
            if candidate.name.casefold() != LOCAL_DATA_RELATIVE_PATH.casefold():
                raise DomainError(
                    code="LOCAL_DATA_FILE_REQUIRED",
                    message="The selected file must be named LocalData.sav.",
                    field="path",
                    details={"path": str(candidate)},
                    http_status=400,
                )
            if not candidate.is_file():
                raise DomainError(
                    code="LOCAL_DATA_MISSING",
                    message="The selected LocalData.sav file does not exist.",
                    field="path",
                    details={"path": str(candidate)},
                    http_status=404,
                )
            if not isinstance(self._storage, SteamDirectoryAdapter):
                raise DomainError(
                    code="LOCAL_DATA_STORAGE_UNSUPPORTED",
                    message="This Steam storage adapter cannot bind LocalData.sav.",
                    http_status=409,
                )
            document = LocalDataDocument.open_file(candidate)
            self._storage.bind_logical_file(
                self._opened,
                LOCAL_DATA_RELATIVE_PATH,
                candidate,
            )
            selected_source = candidate
        else:
            if path not in (None, ""):
                raise DomainError(
                    code="WGS_LOCAL_DATA_EXTERNAL_UNSUPPORTED",
                    message=(
                        "Game Pass can only use LocalData.sav from the WGS slot "
                        "that was opened."
                    ),
                    field="path",
                    http_status=400,
                )
            if LOCAL_DATA_RELATIVE_PATH not in self._opened.logical_files:
                raise DomainError(
                    code="LOCAL_DATA_WGS_SLOT_MISSING",
                    message=(
                        "The opened Game Pass slot does not contain a mapped "
                        "LocalData.sav payload."
                    ),
                    http_status=409,
                )
            selected_source = self._workspace / LOCAL_DATA_RELATIVE_PATH
            if not selected_source.is_file():
                raise DomainError(
                    code="LOCAL_DATA_WGS_SLOT_MISSING",
                    message=(
                        "The opened Game Pass slot did not normalize "
                        "LocalData.sav into the private workspace."
                    ),
                    http_status=409,
                )
            document = LocalDataDocument.open_file(selected_source)

        self._local_data = document
        self._local_data_selected = True
        self._local_data_source = selected_source
        self._revision += 1
        self._changes.mark_saved(self._revision)
        self._file_baseline = self._snapshot_file_metadata()
        return {
            "revision": self._revision,
            "selection": self.local_data_selection,
            "saveCapabilities": self.save_capabilities,
        }

    def require_local_data_selected(self) -> None:
        if self._local_data_selected:
            return
        raise DomainError(
            code="LOCAL_DATA_NOT_SELECTED",
            message="Select LocalData.sav before changing fog-of-war masks.",
            details={"capability": self.local_data_selection},
            http_status=409,
        )

    def summary(self) -> SessionSummary:
        players = getattr(self._manager, "player_mapping", None) or {}
        return SessionSummary(
            session_id=self._session_id,
            revision=self._revision,
            source=(
                str(self._source)
                if self.platform is SavePlatform.STEAM
                else self.source_display_name
            ),
            opened_at=self._opened_at,
            player_count=len(players),
            pending_change_count=len(self._changes),
            platform=self.platform,
            source_id=self.source_id,
            source_display_name=self.source_display_name,
            save_capabilities=self.save_capabilities,
            raw_json_pending=self.raw_json_pending,
        )

    def close(self) -> None:
        self._storage.close(self._opened)

    def compatibility(self) -> SaveCompatibility:
        return self._compatibility

    def refresh_compatibility(self) -> SaveCompatibility:
        self._compatibility = self._inspect_compatibility()
        return self._compatibility

    def changes(self) -> list[dict[str, Any]]:
        return self._changes.view()

    def list_players(self) -> list[PlayerSummary]:
        players = getattr(self._manager, "player_mapping", None) or {}
        result = [
            PlayerSummary(
                player_id=str(player.PlayerUId),
                instance_id=str(player.InstanceId),
                name=str(player.NickName or ""),
                level=player.Level,
            )
            for player in players.values()
        ]
        return sorted(result, key=lambda player: (player.name.casefold(), player.player_id))

    def load_player(self, player_id: str):
        player = self._manager.get_player(player_id)
        if player is None:
            raise DomainError(
                code="PLAYER_NOT_FOUND",
                message="Player not found.",
                field="player_id",
                details={"player_id": player_id},
                http_status=404,
            )
        loader = getattr(player, "load_details", None)
        if loader is not None:
            loader()
        self._compatibility = self._inspect_compatibility()
        return player

    def invalidate_player_cache(self, player_id: str) -> None:
        pending = any(
            f"player_file:{player_id}" in change.get("affected_records", [])
            for change in self.changes()
        )
        if pending:
            raise DomainError(
                code="PLAYER_CACHE_DIRTY",
                message="Player details with pending changes cannot be evicted.",
                details={"player_id": player_id},
                http_status=409,
            )
        player = self._manager.get_player(player_id)
        if player is None:
            raise DomainError(
                code="PLAYER_NOT_FOUND",
                message="Player not found.",
                field="player_id",
                http_status=404,
            )
        invalidate = getattr(player, "invalidate_details", None)
        if invalidate is not None and not invalidate():
            raise DomainError(
                code="PLAYER_CACHE_DIRTY",
                message="Player details contain unsaved structural records.",
                details={"player_id": player_id},
                http_status=409,
            )

    def performance_metrics(self) -> dict[str, Any]:
        players = getattr(self._manager, "player_mapping", None) or {}
        loaded = sum(
            1 for player in players.values() if getattr(player, "is_loaded", True)
        )
        return {
            "open_seconds": getattr(
                self, "_open_seconds", getattr(self._manager, "open_seconds", None)
            ),
            "player_file_count": len(players),
            "player_files_loaded": loaded,
            "player_file_reads": getattr(
                self._manager, "player_file_load_count", loaded
            ),
            "player_load_seconds": dict(
                getattr(self._manager, "player_file_load_seconds", {})
            ),
            "operation_seconds": {
                name: {
                    "count": len(samples),
                    "last": samples[-1],
                    "total": sum(samples),
                    "max": max(samples),
                }
                for name, samples in sorted(self._operation_seconds.items())
                if samples
            },
        }

    def record_operation_seconds(self, name: str, seconds: float) -> None:
        """Record measured application work without changing domain state."""
        if not isinstance(name, str) or not name or seconds < 0:
            return
        self._operation_seconds.setdefault(name, []).append(float(seconds))

    def require_command(
        self,
        session_id: str,
        expected_revision: int,
        *,
        allow_raw_json: bool = False,
    ) -> None:
        if session_id != self._session_id:
            raise DomainError(
                code="SESSION_NOT_FOUND",
                message="The save session is no longer active.",
                field="session_id",
                http_status=404,
            )
        if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
            raise DomainError(
                code="INVALID_REVISION",
                message="expected_revision must be an integer.",
                field="expected_revision",
                http_status=400,
            )
        if expected_revision != self._revision:
            raise stale_revision(expected_revision, self._revision)

    def apply_atomic(
        self,
        *,
        session_id: str,
        expected_revision: int,
        command: str,
        target: dict[str, Any],
        snapshot: Callable[[], Any],
        restore: Callable[[Any], None],
        before: Callable[[], dict[str, Any]],
        mutate: Callable[[], None],
        validate: Callable[[], None],
        after: Callable[[], dict[str, Any]],
        affected_records: Iterable[str],
        allow_raw_json: bool = False,
    ) -> ChangeEntry:
        self.require_command(
            session_id,
            expected_revision,
            allow_raw_json=allow_raw_json,
        )
        state = snapshot()
        before_summary = deepcopy(before())
        try:
            mutate()
            validate()
            after_summary = deepcopy(after())
            entry = ChangeEntry.create(
                revision_before=self._revision,
                command=command,
                target=target,
                before=before_summary,
                after=after_summary,
                affected_records=affected_records,
            )
            if self._active_batch is not None:
                self._active_batch["mutations"].append((restore, state, entry))
                return entry
            self._changes.append(entry)
            self._revision += 1
            return entry
        except Exception:
            restore(state)
            raise

    def mark_raw_json_pending(self) -> None:
        self._raw_json_pending = True

    def run_batch(
        self,
        *,
        session_id: str,
        expected_revision: int,
        command: str,
        target: dict[str, Any],
        mutate: Callable[[], list[Any]],
        validate: Callable[[], None],
    ) -> tuple[ChangeEntry, list[Any]]:
        self.require_command(session_id, expected_revision)
        if self._active_batch is not None:
            raise DomainError(
                code="NESTED_BATCH_UNSUPPORTED",
                message="A batch command cannot contain another batch command.",
                http_status=409,
            )
        context: dict[str, Any] = {"mutations": []}
        self._active_batch = context
        try:
            results = mutate()
            validate()
            inner_entries = [value[2] for value in context["mutations"]]
            if not inner_entries:
                raise DomainError(
                    code="EMPTY_BATCH",
                    message="A batch command must contain at least one operation.",
                    http_status=400,
                )
            affected_records = tuple(
                dict.fromkeys(
                    record
                    for entry in inner_entries
                    for record in entry.affected_records
                )
            )
            entry = ChangeEntry.create(
                revision_before=self._revision,
                command=command,
                target=target,
                before={
                    "operation_count": len(inner_entries),
                    "operations": [
                        {
                            "command": value.command,
                            "target": value.target,
                            "before": value.before,
                        }
                        for value in inner_entries
                    ],
                },
                after={
                    "operation_count": len(inner_entries),
                    "operations": [
                        {
                            "command": value.command,
                            "target": value.target,
                            "after": value.after,
                        }
                        for value in inner_entries
                    ],
                },
                affected_records=affected_records,
            )
            self._changes.append(entry)
            self._revision += 1
            return entry, results
        except Exception:
            for restore, state, _entry in reversed(context["mutations"]):
                restore(state)
            raise
        finally:
            self._active_batch = None

    def mark_saved(self, expected_revision: int) -> None:
        if expected_revision != self._revision:
            raise stale_revision(expected_revision, self._revision)
        self._changes.mark_saved(expected_revision)
        self._raw_json_pending = False
        self._dynamic_item_issue_baseline = (
            self._snapshot_dynamic_item_issue_fingerprints()
        )
        self._file_baseline = self._snapshot_file_metadata()

    def file_unchanged_since_open(self, relative_path: str) -> bool:
        resolver = getattr(self._storage, "logical_source_path", None)
        if callable(resolver):
            logical = self._opened.logical_files.get(relative_path)
            if logical is None:
                return False
            try:
                path = resolver(self._opened, relative_path)
                from palworld_pal_editor.storage.steam import sha256_file

                return path.is_file() and sha256_file(path) == logical.sha256
            except OSError:
                return False
        expected = self._file_baseline.get(relative_path)
        path = self._workspace / Path(relative_path)
        if expected is None:
            return not path.exists()
        try:
            stat = path.stat()
        except OSError:
            return False
        return expected == (stat.st_size, stat.st_mtime_ns)

    def _snapshot_file_metadata(self) -> dict[str, tuple[int, int]]:
        if not self._workspace.exists():
            return {}
        result: dict[str, tuple[int, int]] = {}
        for path in self._workspace.rglob("*.sav"):
            if not path.is_file():
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            result[path.relative_to(self._workspace).as_posix()] = (
                stat.st_size,
                stat.st_mtime_ns,
            )
        return result

    def _snapshot_dynamic_item_issue_fingerprints(self) -> tuple[str, ...]:
        dynamic_items = getattr(self._manager, "dynamic_item_data", None)
        snapshot = getattr(dynamic_items, "issue_fingerprints", None)
        if snapshot is None:
            return ()
        return tuple(snapshot())

    def _inspect_compatibility(self) -> SaveCompatibility:
        gvas = getattr(self._manager, "gvas_file", None)
        header = getattr(gvas, "header", None)
        if header is None:
            version = "unknown"
        else:
            version = (
                f"gvas-{header.save_game_version}/"
                f"ue-{header.engine_version_major}.{header.engine_version_minor}."
                f"{header.engine_version_patch}-{header.engine_version_changelist}"
            )

        aliases: dict[str, str] = {}
        warnings: list[dict[str, Any]] = []
        inventory_readable = True
        inventory_writable = True
        players = getattr(self._manager, "player_mapping", None) or {}
        for player_id, player in players.items():
            if not getattr(player, "is_loaded", True):
                aliases[str(player_id)] = "deferred"
                continue
            save_data = getattr(player, "_player_save_data", {})
            upper = save_data.get("InventoryInfo")
            lower = save_data.get("inventoryInfo")
            if upper is None and lower is None:
                inventory_readable = False
                inventory_writable = False
                warnings.append(
                    {"code": "INVENTORY_INFO_MISSING", "player_id": str(player_id)}
                )
                continue
            if upper is not None and lower is not None:
                aliases[str(player_id)] = "InventoryInfo+inventoryInfo"
                if upper != lower:
                    inventory_writable = False
                    warnings.append(
                        {
                            "code": "COMPATIBILITY_FIELD_AMBIGUOUS",
                            "player_id": str(player_id),
                        }
                    )
            else:
                aliases[str(player_id)] = (
                    "InventoryInfo" if upper is not None else "inventoryInfo"
                )

        character_index = getattr(self._manager, "character_index", None)
        if character_index is None and all(
            hasattr(self._manager, field)
            for field in (
                "_entities_list",
                "container_data",
                "group_data",
                "baseworker_mapping",
                "_dangling_pals",
            )
        ):
            character_index = CharacterIndex(self._manager)
        character_issues = (
            character_index.hard_issues() if character_index is not None else []
        )
        warnings.extend(issue.to_dict() for issue in character_issues)

        capabilities = {
            "inventory.read": Capability(
                readable=inventory_readable,
                writable=False,
                reason=None if inventory_readable else "INVENTORY_INFO_MISSING",
                evidence="loaded-player-fields",
            ),
            "inventory.write.static": Capability(
                readable=inventory_readable,
                writable=False,
                reason=(
                    "REAL_SAVE_RULE_EVIDENCE_REQUIRED"
                    if inventory_writable
                    else "COMPATIBILITY_FIELD_AMBIGUOUS"
                ),
                evidence="field-alias-inspection",
            ),
            "inventory.write.dynamic.create": Capability(
                readable=inventory_readable,
                writable=False,
                reason="DYNAMIC_ITEM_CREATE_UNVERIFIED",
                evidence=None,
            ),
            "pal.structural_edit": Capability(
                readable=True,
                writable=not character_issues and character_index is not None,
                reason=(
                    None
                    if not character_issues and character_index is not None
                    else "CHARACTER_INDEX_INVARIANT_FAILED"
                ),
                evidence=(
                    "character-record-container-owner-group-index"
                    if character_index is not None
                    else None
                ),
            ),
        }
        base_storage = getattr(self._manager, "base_storage_data", None)
        base_storage_error = getattr(
            self._manager, "base_storage_error", None
        )
        base_storage_readable = (
            base_storage is not None and base_storage_error is None
        )
        base_storage_complete = bool(
            base_storage_readable and base_storage.complete
        )
        if base_storage is not None:
            warnings.extend(
                issue.to_dict() for issue in base_storage.issues()
            )
        capabilities["base_storage.read"] = Capability(
            readable=base_storage_readable,
            writable=False,
            reason=(
                None
                if base_storage_readable
                else "BASE_STORAGE_UNSUPPORTED"
            ),
            evidence=(
                "selective-map-object-item-container-index"
                if base_storage_readable
                else None
            ),
        )
        capabilities["base_storage.write.static"] = Capability(
            readable=base_storage_readable,
            writable=base_storage_complete,
            reason=(
                None
                if base_storage_complete
                else (
                    "BASE_STORAGE_INDEX_INCOMPLETE"
                    if base_storage_readable
                    else "BASE_STORAGE_UNSUPPORTED"
                )
            ),
            evidence=(
                "guild-base-container-binding-and-item-catalog"
                if base_storage_complete
                else None
            ),
        )
        dynamic_items = getattr(self._manager, "dynamic_item_data", None)
        if dynamic_items is not None:
            dynamic_issues = [
                {
                    "code": issue.code,
                    "details": issue.details,
                }
                for issue in dynamic_items.issues()
            ]
            warnings.extend(dynamic_issues)
            dynamic_consistent = not dynamic_issues
            capabilities["inventory.read.dynamic"] = Capability(
                readable=True,
                writable=False,
                reason=None if dynamic_consistent else "DYNAMIC_ITEM_INVARIANT_FAILED",
                evidence="decoded-dynamic-item-index",
            )
            capabilities["inventory.write.dynamic.count"] = Capability(
                readable=True,
                writable=dynamic_consistent,
                reason=None if dynamic_consistent else "DYNAMIC_ITEM_INVARIANT_FAILED",
                evidence="slot-record-identity-check",
            )
            capabilities["inventory.write.dynamic.delete"] = Capability(
                readable=True,
                writable=(
                    dynamic_consistent and dynamic_items.reference_scope_complete
                ),
                reason=(
                    None
                    if dynamic_consistent and dynamic_items.reference_scope_complete
                    else "DYNAMIC_ITEM_REFERENCE_SCOPE_UNVERIFIED"
                ),
                evidence=(
                    "complete-dynamic-reference-index"
                    if dynamic_items.reference_scope_complete
                    else "item-container-reference-index-only"
                ),
            )
            capabilities["base_storage.write.dynamic.count"] = Capability(
                readable=base_storage_readable,
                writable=base_storage_complete and dynamic_consistent,
                reason=(
                    None
                    if base_storage_complete and dynamic_consistent
                    else (
                        "DYNAMIC_ITEM_INVARIANT_FAILED"
                        if base_storage_complete
                        else "BASE_STORAGE_INDEX_INCOMPLETE"
                    )
                ),
                evidence=(
                    "base-container-slot-record-identity-check"
                    if base_storage_complete and dynamic_consistent
                    else None
                ),
            )
            capabilities["base_storage.write.dynamic.delete"] = Capability(
                readable=base_storage_readable,
                writable=(
                    base_storage_complete
                    and dynamic_consistent
                    and dynamic_items.reference_scope_complete
                ),
                reason=(
                    None
                    if (
                        base_storage_complete
                        and dynamic_consistent
                        and dynamic_items.reference_scope_complete
                    )
                    else (
                        "BASE_STORAGE_INDEX_INCOMPLETE"
                        if not base_storage_complete
                        else "DYNAMIC_ITEM_REFERENCE_SCOPE_UNVERIFIED"
                    )
                ),
                evidence=(
                    "complete-dynamic-reference-index"
                    if (
                        base_storage_complete
                        and dynamic_consistent
                        and dynamic_items.reference_scope_complete
                    )
                    else None
                ),
            )
        return SaveCompatibility(
            save_version=version,
            field_aliases=aliases,
            capabilities=capabilities,
            warnings=tuple(warnings),
        )
