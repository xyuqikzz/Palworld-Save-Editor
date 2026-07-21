from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import hmac
import json
from typing import Any

from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.domain.commands import UpdatePlayerMissions
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.domain.mission_catalog import MissionCatalog


_DIRECT_OPERATIONS = {
    "mark_completed",
    "reset_to_unaccepted",
    "restart_from_beginning",
}
_BULK_OPERATIONS = {
    "complete_tracked",
    "complete_all_in_progress",
    "complete_all",
    "reset_all_completed",
}
_COMPLETION_OPERATIONS = {
    "mark_completed",
    "complete_tracked",
    "complete_all_in_progress",
    "complete_all",
}
_RESET_OPERATIONS = {
    "reset_to_unaccepted",
    "restart_from_beginning",
    "reset_all_completed",
}


@dataclass
class _MissionState:
    completed_key: str | None
    ordered_key: str | None
    completed: list[str]
    ordered: list[dict[str, Any]]
    writable: bool
    reason: str | None = None

    def completed_counts(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for mission_id in self.completed:
            result[mission_id] = result.get(mission_id, 0) + 1
        return result

    def ordered_groups(self) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = {}
        for record in self.ordered:
            mission_id = _record_mission_id(record)
            if mission_id is not None:
                result.setdefault(mission_id, []).append(record)
        return result


def _record_mission_id(record: Any) -> str | None:
    if not isinstance(record, dict):
        return None
    field = record.get("QuestName")
    if not isinstance(field, dict):
        return None
    value = field.get("value")
    return value if isinstance(value, str) and value else None


def _completed_array(values: list[str]) -> dict[str, Any]:
    return {
        "array_type": "NameProperty",
        "id": None,
        "value": {"values": values},
        "type": "ArrayProperty",
    }


def _ordered_array(key: str, values: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "array_type": "StructProperty",
        "id": None,
        "value": {
            "prop_name": key,
            "prop_type": "StructProperty",
            "values": values,
            "type_name": "PalOrderedQuestSaveData",
            "id": "00000000-0000-0000-0000-000000000000",
        },
        "type": "ArrayProperty",
    }


def _status(
    mission_id: str,
    completed_counts: dict[str, int],
    ordered_groups: dict[str, list[dict[str, Any]]],
) -> str:
    completed_count = completed_counts.get(mission_id, 0)
    ordered_count = len(ordered_groups.get(mission_id, ()))
    if completed_count > 1 or ordered_count > 1 or (completed_count and ordered_count):
        return "inconsistent"
    if completed_count:
        return "completed"
    if ordered_count:
        return "in_progress"
    return "unaccepted"


class MissionEditor:
    """Owns mission interpretation, preview consistency, and atomic mutation."""

    def __init__(
        self,
        session: SaveSession,
        *,
        catalog_data: dict[str, Any] | None = None,
        locale: str = "en",
    ) -> None:
        self.session = session
        self.catalog = (
            MissionCatalog(catalog_data)
            if catalog_data is not None
            else MissionCatalog.load_default()
        )
        self.locale = locale

    def get_missions(self, player_id: str, *, locale: str | None = None) -> dict[str, Any]:
        player = self.session.load_player(player_id)
        state = self._read_state(player)
        active_locale = locale or self.locale
        completed_counts = state.completed_counts()
        ordered_groups = state.ordered_groups()
        save_ids = list(completed_counts)
        save_ids.extend(
            mission_id for mission_id in ordered_groups if mission_id not in completed_counts
        )
        mission_ids = list(self.catalog.ids())
        mission_ids.extend(
            mission_id for mission_id in save_ids if mission_id not in set(mission_ids)
        )
        tracked_id = next(
            (
                _record_mission_id(record)
                for record in state.ordered
                if _record_mission_id(record) is not None
                and _status(
                    _record_mission_id(record), completed_counts, ordered_groups
                )
                == "in_progress"
            ),
            None,
        )
        rows = [
            self._mission_row(
                mission_id,
                active_locale,
                state,
                completed_counts,
                ordered_groups,
                tracked_id,
            )
            for mission_id in mission_ids
        ]
        rows.sort(
            key=lambda row: (
                {"main": 0, "sub": 1, "hidden": 2}.get(row["type"], 3),
                row["title"].casefold(),
                row["internal_name"],
            )
        )
        summary = self._summary(rows)
        warnings: list[dict[str, Any]] = []
        if not state.writable:
            warnings.append(
                {
                    "code": state.reason or "MISSION_FIELDS_READ_ONLY",
                    "message": "Mission fields are not safely writable in this save.",
                }
            )
        if summary["by_status"]["inconsistent"]:
            warnings.append(
                {
                    "code": "MISSION_STATE_INCONSISTENT",
                    "count": summary["by_status"]["inconsistent"],
                }
            )
        return {
            "session_id": self.session.session_id,
            "revision": self.session.revision,
            "pending_change_count": len(self.session.changes()),
            "player_id": player_id,
            "locale": active_locale,
            "source": self.catalog.source,
            "field_alias": (
                state.completed_key.removeprefix("CompletedQuestArray")
                if state.completed_key
                else None
            ),
            "writable": state.writable,
            "missions": rows,
            "summary": summary,
            "warnings": warnings,
        }

    def preview(self, command: UpdatePlayerMissions) -> dict[str, Any]:
        self.session.require_command(command.session_id, command.expected_revision)
        return self._build_preview(command)

    def execute(self, command: UpdatePlayerMissions) -> dict[str, Any]:
        self.session.require_command(command.session_id, command.expected_revision)
        preview = self._build_preview(command)
        if not command.preview_token or not hmac.compare_digest(
            command.preview_token, preview["preview_token"]
        ):
            raise DomainError(
                code="MISSION_PREVIEW_STALE",
                message="Mission state changed; preview the operation again.",
                field="preview_token",
                retryable=True,
                http_status=409,
            )
        if preview["conflict_ids"] and command.operation in _DIRECT_OPERATIONS:
            raise DomainError(
                code="MISSION_STATE_CONFLICT",
                message="The selected mission has inconsistent save records.",
                details={"mission_ids": preview["conflict_ids"]},
                http_status=409,
            )
        target_ids = tuple(impact["internal_name"] for impact in preview["impacts"])
        if not target_ids:
            return {
                "session_id": self.session.session_id,
                "revision": self.session.revision,
                "pending_change_count": len(self.session.changes()),
                "operation": command.operation,
                "impact_count": 0,
                "changed": False,
                "change": None,
                "warnings": preview["warnings"],
            }

        player = self.session.load_player(command.player_id)
        state = self._read_state(player, require_writable=True)

        def snapshot() -> dict[str, Any]:
            return deepcopy(player._player_save_data)

        def restore(saved: dict[str, Any]) -> None:
            player._player_save_data.clear()
            player._player_save_data.update(saved)

        def summarize() -> dict[str, Any]:
            current = self._read_state(player, require_writable=True)
            completed_counts = current.completed_counts()
            ordered_groups = current.ordered_groups()
            return {
                "mission_statuses": {
                    mission_id: _status(
                        mission_id, completed_counts, ordered_groups
                    )
                    for mission_id in target_ids
                },
                "completed_record_count": len(current.completed),
                "ordered_record_count": len(current.ordered),
            }

        def mutate() -> None:
            self._materialize_missing_fields(
                player._player_save_data, state, command.operation
            )
            for mission_id in target_ids:
                self._mutate_one(state, mission_id, command.operation)

        def validate() -> None:
            current = self._read_state(player, require_writable=True)
            completed_counts = current.completed_counts()
            ordered_groups = current.ordered_groups()
            expected = (
                "completed"
                if command.operation in _COMPLETION_OPERATIONS
                else (
                    "in_progress"
                    if command.operation == "restart_from_beginning"
                    else "unaccepted"
                )
            )
            invalid = [
                mission_id
                for mission_id in target_ids
                if _status(mission_id, completed_counts, ordered_groups) != expected
            ]
            if invalid:
                raise DomainError(
                    code="MISSION_POSTCONDITION_FAILED",
                    message="Mission state validation failed after mutation.",
                    details={"mission_ids": invalid, "expected_status": expected},
                    http_status=409,
                )

        change = self.session.apply_atomic(
            session_id=command.session_id,
            expected_revision=command.expected_revision,
            command=command.operation,
            target={"player_id": command.player_id, "mission_ids": list(target_ids)},
            snapshot=snapshot,
            restore=restore,
            before=summarize,
            mutate=mutate,
            validate=validate,
            after=summarize,
            affected_records=(f"player_file:{command.player_id}",),
        )
        return {
            "session_id": self.session.session_id,
            "revision": self.session.revision,
            "pending_change_count": len(self.session.changes()),
            "operation": command.operation,
            "impact_count": len(target_ids),
            "changed": True,
            "change": change.to_dict(),
            "warnings": preview["warnings"],
        }

    def _build_preview(self, command: UpdatePlayerMissions) -> dict[str, Any]:
        if command.operation not in _DIRECT_OPERATIONS | _BULK_OPERATIONS:
            raise DomainError(
                code="UNSUPPORTED_MISSION_OPERATION",
                message="Unsupported mission operation.",
                field="operation",
                http_status=400,
            )
        player = self.session.load_player(command.player_id)
        state = self._read_state(player, require_writable=True)
        completed_counts = state.completed_counts()
        ordered_groups = state.ordered_groups()
        all_ids = list(self.catalog.ids())
        for mission_id in (*completed_counts, *ordered_groups):
            if mission_id not in all_ids:
                all_ids.append(mission_id)

        if command.operation in _DIRECT_OPERATIONS:
            if not command.mission_ids:
                raise DomainError(
                    code="MISSION_SELECTION_REQUIRED",
                    message="Select at least one mission.",
                    field="mission_ids",
                    http_status=400,
                )
            if len(set(command.mission_ids)) != len(command.mission_ids):
                raise DomainError(
                    code="DUPLICATE_MISSION_SELECTION",
                    message="mission_ids cannot contain duplicates.",
                    field="mission_ids",
                    http_status=400,
                )
            unknown = [
                mission_id
                for mission_id in command.mission_ids
                if mission_id not in all_ids
            ]
            if unknown:
                raise DomainError(
                    code="UNKNOWN_MISSION",
                    message="The selection contains unknown mission IDs.",
                    field="mission_ids",
                    details={"mission_ids": unknown},
                    http_status=400,
                )
            selected = list(command.mission_ids)
        else:
            if command.mission_ids:
                raise DomainError(
                    code="UNSUPPORTED_COMMAND_FIELD",
                    message="Bulk mission operations select targets on the server.",
                    field="mission_ids",
                    http_status=400,
                )
            selected = self._bulk_targets(
                command.operation, all_ids, completed_counts, ordered_groups, state
            )

        conflict_ids = [
            mission_id
            for mission_id in selected
            if _status(mission_id, completed_counts, ordered_groups) == "inconsistent"
        ]
        if command.operation == "restart_from_beginning":
            unsupported = [
                mission_id
                for mission_id in selected
                if not self._restart_supported(mission_id, state)
            ]
            if unsupported:
                raise DomainError(
                    code="MISSION_RESTART_UNSUPPORTED",
                    message="A verified initial template is unavailable for this mission.",
                    details={"mission_ids": unsupported},
                    http_status=409,
                )
        candidates = [mission_id for mission_id in selected if mission_id not in conflict_ids]
        impacts: list[dict[str, Any]] = []
        for mission_id in candidates:
            before_status = _status(mission_id, completed_counts, ordered_groups)
            after_status = self._target_status(command.operation)
            if before_status == after_status and command.operation != "restart_from_beginning":
                continue
            if command.operation == "restart_from_beginning" and self._is_initial(
                mission_id, state, completed_counts, ordered_groups
            ):
                continue
            presented = self.catalog.present(mission_id, self.locale)
            impacts.append(
                {
                    "internal_name": mission_id,
                    "title": presented["title"],
                    "type": presented["type"],
                    "before_status": before_status,
                    "after_status": after_status,
                }
            )

        warnings: list[dict[str, Any]] = []
        if command.operation in _COMPLETION_OPERATIONS:
            warnings.extend(
                [
                    {"code": "MISSION_REWARDS_NOT_GRANTED"},
                    {"code": "STORY_AND_ACHIEVEMENT_SIDE_EFFECTS_NOT_REPLAYED"},
                ]
            )
        if command.operation in _RESET_OPERATIONS:
            warnings.append({"code": "MISSION_FOLLOW_UP_STATE_NOT_ROLLED_BACK"})
        token_payload = {
            "session_id": self.session.session_id,
            "revision": self.session.revision,
            "player_id": command.player_id,
            "operation": command.operation,
            "selected": selected,
            "impacts": impacts,
            "conflicts": conflict_ids,
            "completed": state.completed,
            "ordered": state.ordered,
        }
        preview_token = hashlib.sha256(
            json.dumps(
                token_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
        ).hexdigest()
        return {
            "session_id": self.session.session_id,
            "revision": self.session.revision,
            "player_id": command.player_id,
            "operation": command.operation,
            "impact_count": len(impacts),
            "impacts": impacts,
            "conflict_ids": conflict_ids,
            "warnings": warnings,
            "preview_token": preview_token,
        }

    def _read_state(self, player: Any, *, require_writable: bool = False) -> _MissionState:
        save_data = getattr(player, "_player_save_data", None)
        if not isinstance(save_data, dict):
            raise DomainError(
                code="MISSION_FIELDS_UNREADABLE",
                message="Player save data is unavailable.",
                http_status=409,
            )
        aliases = (
            ("CompletedQuestArray_FullRelease", "OrderedQuestArray_FullRelease"),
            ("CompletedQuestArray", "OrderedQuestArray"),
        )
        present = [
            pair for pair in aliases if any(field in save_data for field in pair)
        ]
        if len(present) > 1:
            raise DomainError(
                code="MISSION_FIELD_AMBIGUOUS",
                message="Both legacy and FullRelease mission fields are present.",
                http_status=409,
            )
        if not present:
            state = _MissionState(None, None, [], [], False, "MISSION_FIELDS_MISSING")
            if require_writable:
                raise DomainError(
                    code=state.reason,
                    message="Mission fields are absent; this save is read-only for missions.",
                    http_status=409,
                )
            return state
        completed_key, ordered_key = present[0]
        try:
            completed = (
                save_data[completed_key]["value"]["values"]
                if completed_key in save_data
                else []
            )
            ordered = (
                save_data[ordered_key]["value"]["values"]
                if ordered_key in save_data
                else []
            )
        except (KeyError, TypeError) as error:
            raise DomainError(
                code="MISSION_FIELDS_UNREADABLE",
                message="Mission fields use an unsupported save structure.",
                http_status=409,
            ) from error
        if (
            not isinstance(completed, list)
            or not all(isinstance(value, str) and value for value in completed)
            or not isinstance(ordered, list)
            or any(_record_mission_id(record) is None for record in ordered)
        ):
            raise DomainError(
                code="MISSION_FIELDS_UNREADABLE",
                message="Mission fields contain invalid records.",
                http_status=409,
            )
        return _MissionState(
            completed_key, ordered_key, completed, ordered, True, None
        )

    @staticmethod
    def _materialize_missing_fields(
        save_data: dict[str, Any], state: _MissionState, operation: str
    ) -> None:
        if (
            operation in _COMPLETION_OPERATIONS
            and state.completed_key is not None
            and state.completed_key not in save_data
        ):
            save_data[state.completed_key] = _completed_array(state.completed)
        if (
            operation == "restart_from_beginning"
            and state.ordered_key is not None
            and state.ordered_key not in save_data
        ):
            save_data[state.ordered_key] = _ordered_array(
                state.ordered_key, state.ordered
            )

    def _mission_row(
        self,
        mission_id: str,
        locale: str,
        state: _MissionState,
        completed_counts: dict[str, int],
        ordered_groups: dict[str, list[dict[str, Any]]],
        tracked_id: str | None,
    ) -> dict[str, Any]:
        row = self.catalog.present(mission_id, locale)
        status = _status(mission_id, completed_counts, ordered_groups)
        records = ordered_groups.get(mission_id, [])
        record = records[0] if len(records) == 1 else None
        progress = None
        if record is not None:
            integer_map = record.get("IntegerMap", {}).get("value", [])
            string_map = record.get("StringMap", {}).get("value", [])
            progress = {
                "block_index": record.get("BlockIndex", {}).get("value"),
                "integer_counters": {
                    value.get("key"): value.get("value")
                    for value in integer_map
                    if isinstance(value, dict) and isinstance(value.get("key"), str)
                },
                "string_values": {
                    value.get("key"): value.get("value")
                    for value in string_map
                    if isinstance(value, dict) and isinstance(value.get("key"), str)
                },
            }
        writable = state.writable and status != "inconsistent"
        restart_supported = writable and self._restart_supported(mission_id, state)
        row.update(
            {
                "status": status,
                "tracked": mission_id == tracked_id,
                "progress": progress,
                "record_counts": {
                    "completed": completed_counts.get(mission_id, 0),
                    "ordered": len(records),
                },
                "capabilities": {
                    "mark_completed": writable,
                    "reset_to_unaccepted": writable,
                    "restart_from_beginning": restart_supported,
                    "reason": (
                        None
                        if writable and restart_supported
                        else (
                            "MISSION_STATE_INCONSISTENT"
                            if status == "inconsistent"
                            else (
                                state.reason
                                or "MISSION_INITIAL_TEMPLATE_UNVERIFIED"
                            )
                        )
                    ),
                },
            }
        )
        return row

    def _restart_supported(
        self, mission_id: str, state: _MissionState
    ) -> bool:
        if state.ordered_key != "OrderedQuestArray_FullRelease":
            return False
        entry = self.catalog.entry(mission_id)
        capability = entry.get("restart_capability") if entry else None
        return bool(capability and capability.get("supported"))

    @staticmethod
    def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
        statuses = ("completed", "in_progress", "unaccepted", "inconsistent")
        types = ("main", "sub", "hidden")
        return {
            "total": len(rows),
            "by_status": {
                status: sum(row["status"] == status for row in rows)
                for status in statuses
            },
            "by_type": {
                mission_type: sum(row["type"] == mission_type for row in rows)
                for mission_type in types
            },
        }

    @staticmethod
    def _target_status(operation: str) -> str:
        if operation in _COMPLETION_OPERATIONS:
            return "completed"
        if operation == "restart_from_beginning":
            return "in_progress"
        return "unaccepted"

    @staticmethod
    def _bulk_targets(
        operation: str,
        all_ids: list[str],
        completed_counts: dict[str, int],
        ordered_groups: dict[str, list[dict[str, Any]]],
        state: _MissionState,
    ) -> list[str]:
        if operation == "complete_tracked":
            for record in state.ordered:
                mission_id = _record_mission_id(record)
                if mission_id:
                    return [mission_id]
            return []
        if operation == "complete_all_in_progress":
            return [mission_id for mission_id in all_ids if mission_id in ordered_groups]
        if operation == "reset_all_completed":
            return [
                mission_id for mission_id in all_ids if mission_id in completed_counts
            ]
        return [
            mission_id
            for mission_id in all_ids
            if _status(mission_id, completed_counts, ordered_groups) != "completed"
        ]

    @staticmethod
    def _initial_record(mission_id: str, full_release: bool) -> dict[str, Any]:
        counters = (
            [{"key": "CanCompleteFlag_0", "value": 0}] if full_release else []
        )
        return {
            "QuestName": {
                "id": None,
                "value": mission_id,
                "type": "NameProperty",
            },
            "BlockIndex": {"id": None, "value": 0, "type": "IntProperty"},
            "IntegerMap": {
                "key_type": "NameProperty",
                "value_type": "IntProperty",
                "key_struct_type": None,
                "value_struct_type": None,
                "id": None,
                "value": counters,
                "type": "MapProperty",
            },
            "StringMap": {
                "key_type": "NameProperty",
                "value_type": "StrProperty",
                "key_struct_type": None,
                "value_struct_type": None,
                "id": None,
                "value": [],
                "type": "MapProperty",
            },
        }

    def _mutate_one(
        self, state: _MissionState, mission_id: str, operation: str
    ) -> None:
        state.completed[:] = [value for value in state.completed if value != mission_id]
        state.ordered[:] = [
            record
            for record in state.ordered
            if _record_mission_id(record) != mission_id
        ]
        if operation in _COMPLETION_OPERATIONS:
            state.completed.append(mission_id)
        elif operation == "restart_from_beginning":
            state.ordered.append(
                self._initial_record(
                    mission_id,
                    state.ordered_key == "OrderedQuestArray_FullRelease",
                )
            )

    @staticmethod
    def _is_initial(
        mission_id: str,
        state: _MissionState,
        completed_counts: dict[str, int],
        ordered_groups: dict[str, list[dict[str, Any]]],
    ) -> bool:
        if _status(mission_id, completed_counts, ordered_groups) != "in_progress":
            return False
        record = ordered_groups[mission_id][0]
        expected = MissionEditor._initial_record(
            mission_id,
            state.ordered_key == "OrderedQuestArray_FullRelease",
        )
        return record == expected
