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
    PlayerSummary,
    SaveCompatibility,
    SessionSummary,
)


class SaveSession:
    """Authority boundary for one loaded save and its in-memory changes."""

    def __init__(self, manager: SaveManager, source: Path) -> None:
        self._manager = manager
        self._source = source.resolve()
        self._session_id = str(uuid.uuid4())
        self._opened_at = datetime.now(timezone.utc)
        self._revision = 0
        self._changes = ChangeSet()
        self._active_batch: dict[str, Any] | None = None
        self._operation_seconds: dict[str, list[float]] = {}
        self._compatibility = self._inspect_compatibility()
        self._file_baseline = self._snapshot_file_metadata()

    @classmethod
    def open(
        cls, source: str | Path, *, manager: SaveManager | None = None
    ) -> "SaveSession":
        resolved = Path(source).resolve()
        active_manager = manager or SaveManager()
        started = perf_counter()
        if active_manager.open(str(resolved), lazy_players=True) is None:
            raise DomainError(
                code="INVALID_SAVE_PATH",
                message="The selected directory is not a readable Palworld save.",
                field="source",
                details={"source": str(resolved)},
                http_status=400,
            )
        session = cls(active_manager, resolved)
        session._open_seconds = perf_counter() - started
        return session

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
    def batch_active(self) -> bool:
        """Whether an already-previewed outer batch owns the current mutation."""
        return self._active_batch is not None

    @property
    def source(self) -> Path:
        return self._source

    def summary(self) -> SessionSummary:
        players = getattr(self._manager, "player_mapping", None) or {}
        return SessionSummary(
            session_id=self._session_id,
            revision=self._revision,
            source=str(self._source),
            opened_at=self._opened_at,
            player_count=len(players),
            pending_change_count=len(self._changes),
        )

    def compatibility(self) -> SaveCompatibility:
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

    def require_command(self, session_id: str, expected_revision: int) -> None:
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
    ) -> ChangeEntry:
        self.require_command(session_id, expected_revision)
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
        self._file_baseline = self._snapshot_file_metadata()

    def file_unchanged_since_open(self, relative_path: str) -> bool:
        expected = self._file_baseline.get(relative_path)
        path = self._source / Path(relative_path)
        if expected is None:
            return not path.exists()
        try:
            stat = path.stat()
        except OSError:
            return False
        return expected == (stat.st_size, stat.st_mtime_ns)

    def _snapshot_file_metadata(self) -> dict[str, tuple[int, int]]:
        if not self._source.exists():
            return {}
        result: dict[str, tuple[int, int]] = {}
        for path in self._source.rglob("*.sav"):
            if not path.is_file():
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            result[path.relative_to(self._source).as_posix()] = (
                stat.st_size,
                stat.st_mtime_ns,
            )
        return result

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
        return SaveCompatibility(
            save_version=version,
            field_aliases=aliases,
            capabilities=capabilities,
            warnings=tuple(warnings),
        )
