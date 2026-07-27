from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from palworld_pal_editor.core.pal_objects import PalObjects
from palworld_pal_editor.domain.errors import DomainError

from .arena_npc_catalog import (
    ARENA_NPC_RANKINGS,
    ARENA_NPC_SOURCE_BUILD,
    ARENA_WORLD_RANKING_LIMIT,
    ArenaNpcRanking,
)
from .save_session import SaveSession


ARENA_RANK_POINT_FIELD = "ArenaRankPoint"
MAX_ARENA_RANK_POINT = 2_147_483_647


@dataclass(frozen=True)
class _ArenaBinding:
    player_id: str
    instance_id: str
    name: str
    guild_name: str
    player_params: dict[str, Any] | None
    rank_property: dict[str, Any] | None
    rank_point: int | None
    field_state: str
    capability_error: str | None

    @property
    def writable(self) -> bool:
        return self.field_state in {"present", "missing"}


class ArenaLeaderboardEditor:
    """World-local arena RP reads and revision-bound Level.sav mutations."""

    def __init__(self, session: SaveSession) -> None:
        self._session = session

    def leaderboard(self) -> dict[str, Any]:
        bindings = self._bindings()
        ranked_players = [
            binding for binding in bindings if binding.field_state == "present"
        ]
        candidates = [
            (
                binding.rank_point or 0,
                0,
                binding.name.casefold(),
                binding.player_id,
                binding,
            )
            for binding in ranked_players
        ]
        candidates.extend(
            (
                npc.rank_point,
                1,
                "",
                npc.ranking_npc_id,
                npc,
            )
            for npc in ARENA_NPC_RANKINGS
        )
        candidates.sort(
            key=lambda candidate: (
                -candidate[0],
                candidate[1],
                candidate[2],
                candidate[3],
            )
        )
        top_candidates = candidates[:ARENA_WORLD_RANKING_LIMIT]
        entries: list[dict[str, Any]] = []
        ranked_player_ids: set[str] = set()
        npc_count = 0
        for rank, candidate in enumerate(top_candidates, start=1):
            value = candidate[4]
            if isinstance(value, _ArenaBinding):
                ranked_player_ids.add(value.player_id)
                entries.append(self._entry(value, rank=rank))
            else:
                npc_count += 1
                entries.append(self._npc_entry(value, rank=rank))

        unranked_players = sorted(
            (
                binding
                for binding in bindings
                if binding.player_id not in ranked_player_ids
            ),
            key=lambda binding: (
                {"present": 0, "missing": 1, "unsupported": 2}[
                    binding.field_state
                ],
                -(binding.rank_point or 0),
                binding.name.casefold(),
                binding.player_id,
            ),
        )
        entries.extend(
            self._entry(binding, rank=None) for binding in unranked_players
        )
        initializable_count = sum(
            binding.field_state == "missing" for binding in bindings
        )
        unsupported_count = sum(
            binding.field_state == "unsupported" for binding in bindings
        )
        return {
            "revision": self._session.revision,
            "entries": entries,
            "editable_count": len(ranked_players) + initializable_count,
            "ranked_player_count": len(ranked_players),
            "initializable_count": initializable_count,
            "unsupported_count": unsupported_count,
            "npc_count": npc_count,
            "ranking_limit": ARENA_WORLD_RANKING_LIMIT,
            "npc_source_build": ARENA_NPC_SOURCE_BUILD,
        }

    def set_rank_point(
        self,
        *,
        session_id: str,
        expected_revision: int,
        player_id: str,
        rank_point: int,
    ) -> dict[str, Any]:
        self._validate_rank_point(rank_point)
        binding = self._require_writable_binding(player_id)
        player_params = binding.player_params
        assert player_params is not None
        rank_property = binding.rank_property
        is_initialization = binding.field_state == "missing"

        if not is_initialization and binding.rank_point == rank_point:
            self._session.require_command(session_id, expected_revision)
            return self._result(change_id=None, affected_count=0)

        previous = binding.rank_point

        def restore(value: int | None) -> None:
            if is_initialization:
                player_params.pop(ARENA_RANK_POINT_FIELD, None)
            else:
                assert rank_property is not None
                rank_property["value"] = value

        def value() -> dict[str, Any]:
            current_property = player_params.get(ARENA_RANK_POINT_FIELD)
            return {
                "player_id": binding.player_id,
                "field_present": current_property is not None,
                "arena_rank_point": (
                    current_property.get("value")
                    if isinstance(current_property, dict)
                    else None
                ),
            }

        def mutate() -> None:
            if is_initialization:
                player_params[ARENA_RANK_POINT_FIELD] = PalObjects.IntProperty(
                    rank_point
                )
            else:
                assert rank_property is not None
                rank_property["value"] = rank_point

        entry = self._session.apply_atomic(
            session_id=session_id,
            expected_revision=expected_revision,
            command=(
                "InitializeArenaRankPoint"
                if is_initialization
                else "SetArenaRankPoint"
            ),
            target={"player_id": binding.player_id},
            snapshot=lambda: previous,
            restore=restore,
            before=value,
            mutate=mutate,
            validate=lambda: self._validate_postcondition(
                player_params.get(ARENA_RANK_POINT_FIELD),
                rank_point,
            ),
            after=value,
            affected_records=("level:CharacterSaveParameterMap",),
        )
        return self._result(change_id=entry.change_id, affected_count=1)

    def reset_all(
        self,
        *,
        session_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        bindings = self._bindings()
        writable = [
            binding for binding in bindings if binding.field_state == "present"
        ]
        skipped = [
            {
                "player_id": binding.player_id,
                "capability_error": binding.capability_error,
            }
            for binding in bindings
            if binding.field_state != "present"
        ]
        if not writable:
            raise DomainError(
                code="ARENA_RANK_POINT_UNAVAILABLE",
                message="This save does not expose any supported arena RP fields.",
                details={"skipped": skipped},
                http_status=409,
            )

        changed = [binding for binding in writable if binding.rank_point != 0]
        if not changed:
            self._session.require_command(session_id, expected_revision)
            return self._result(
                change_id=None,
                affected_count=0,
                skipped=skipped,
            )

        snapshot = tuple(
            (binding.rank_property, binding.rank_point) for binding in changed
        )

        def restore(values) -> None:
            for rank_property, value in values:
                rank_property["value"] = value

        def summary() -> dict[str, Any]:
            return {
                "players": [
                    {
                        "player_id": binding.player_id,
                        "arena_rank_point": binding.rank_property.get("value"),
                    }
                    for binding in changed
                ]
            }

        def mutate() -> None:
            for binding in changed:
                binding.rank_property["value"] = 0

        def validate() -> None:
            for binding in changed:
                self._validate_postcondition(binding.rank_property, 0)

        entry = self._session.apply_atomic(
            session_id=session_id,
            expected_revision=expected_revision,
            command="ResetArenaLeaderboard",
            target={"scope": "world", "player_count": len(changed)},
            snapshot=lambda: snapshot,
            restore=restore,
            before=summary,
            mutate=mutate,
            validate=validate,
            after=summary,
            affected_records=("level:CharacterSaveParameterMap",),
        )
        return self._result(
            change_id=entry.change_id,
            affected_count=len(changed),
            skipped=skipped,
        )

    def _result(
        self,
        *,
        change_id: str | None,
        affected_count: int,
        skipped: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        result = self.leaderboard()
        result.update(
            {
                "change_id": change_id,
                "affected_count": affected_count,
                "skipped": skipped or [],
                "skipped_count": len(skipped or []),
            }
        )
        return result

    def _bindings(self) -> list[_ArenaBinding]:
        players = getattr(self._session.manager, "player_mapping", None) or {}
        return [
            self._binding(str(player_id), player)
            for player_id, player in players.items()
        ]

    def _require_writable_binding(self, player_id: str) -> _ArenaBinding:
        if not isinstance(player_id, str) or not player_id:
            raise DomainError(
                code="INVALID_REQUEST",
                message="player_id must be a non-empty string.",
                field="player_id",
                http_status=400,
            )
        players = getattr(self._session.manager, "player_mapping", None) or {}
        player = players.get(player_id)
        if player is None:
            player = next(
                (
                    candidate
                    for candidate in players.values()
                    if str(getattr(candidate, "PlayerUId", "")) == player_id
                ),
                None,
            )
        if player is None:
            raise DomainError(
                code="ARENA_PLAYER_NOT_FOUND",
                message="Arena player not found.",
                field="player_id",
                details={"player_id": player_id},
                http_status=404,
            )
        binding = self._binding(player_id, player)
        if not binding.writable:
            raise DomainError(
                code=binding.capability_error or "ARENA_RANK_POINT_UNSUPPORTED",
                message="This player's ArenaRankPoint field has an unsupported layout.",
                field="rank_point",
                details={"player_id": player_id},
                http_status=409,
            )
        return binding

    def _binding(self, player_id: str, player) -> _ArenaBinding:
        params = getattr(player, "_player_param", None)
        rank_property = None
        capability_error = None
        rank_point = None
        if not isinstance(params, dict):
            field_state = "unsupported"
            capability_error = "ARENA_RANK_POINT_UNSUPPORTED"
        elif ARENA_RANK_POINT_FIELD not in params:
            field_state = "missing"
            capability_error = "ARENA_RANK_POINT_MISSING"
        else:
            rank_property = params.get(ARENA_RANK_POINT_FIELD)
        if (
            isinstance(params, dict)
            and ARENA_RANK_POINT_FIELD in params
            and (
                not isinstance(rank_property, dict)
                or rank_property.get("type") != "IntProperty"
                or isinstance(rank_property.get("value"), bool)
                or not isinstance(rank_property.get("value"), int)
            )
        ):
            field_state = "unsupported"
            capability_error = "ARENA_RANK_POINT_UNSUPPORTED"
        elif isinstance(rank_property, dict):
            field_state = "present"
            rank_point = rank_property["value"]

        return _ArenaBinding(
            player_id=str(getattr(player, "PlayerUId", None) or player_id),
            instance_id=str(getattr(player, "InstanceId", "") or ""),
            name=str(getattr(player, "NickName", "") or ""),
            guild_name=self._guild_name(player),
            player_params=params if isinstance(params, dict) else None,
            rank_property=rank_property if isinstance(rank_property, dict) else None,
            rank_point=rank_point,
            field_state=field_state,
            capability_error=capability_error,
        )

    def _guild_name(self, player) -> str:
        guild_id = getattr(player, "group_id", None)
        group_data = getattr(self._session.manager, "group_data", None)
        if guild_id is None or group_data is None:
            return ""
        group = group_data.get_group(guild_id)
        return str(getattr(group, "guild_name", "") or "") if group else ""

    @staticmethod
    def _entry(binding: _ArenaBinding, *, rank: int | None) -> dict[str, Any]:
        return {
            "entry_id": f"player:{binding.player_id}",
            "entry_type": "player",
            "rank": rank,
            "player_id": binding.player_id,
            "instance_id": binding.instance_id,
            "name": binding.name,
            "guild_name": binding.guild_name,
            "rank_point": binding.rank_point,
            "writable": binding.writable,
            "field_state": binding.field_state,
            "can_initialize": binding.field_state == "missing",
            "capability_error": binding.capability_error,
        }

    @staticmethod
    def _npc_entry(
        npc: ArenaNpcRanking, *, rank: int
    ) -> dict[str, Any]:
        return {
            "entry_id": f"npc:{npc.ranking_npc_id}",
            "entry_type": "npc",
            "rank": rank,
            "ranking_npc_id": npc.ranking_npc_id,
            "name_text_id": npc.name_text_id,
            "player_id": None,
            "instance_id": "",
            "name": "",
            "guild_name": "",
            "rank_point": npc.rank_point,
            "writable": False,
            "field_state": "npc",
            "can_initialize": False,
            "capability_error": None,
        }

    @staticmethod
    def _validate_rank_point(rank_point: int) -> None:
        if (
            isinstance(rank_point, bool)
            or not isinstance(rank_point, int)
            or not 0 <= rank_point <= MAX_ARENA_RANK_POINT
        ):
            raise DomainError(
                code="INVALID_ARENA_RANK_POINT",
                message="rank_point must be an integer from 0 to 2147483647.",
                field="rank_point",
                http_status=400,
            )

    @staticmethod
    def _validate_postcondition(
        rank_property: dict[str, Any] | None, expected: int
    ) -> None:
        if (
            not isinstance(rank_property, dict)
            or rank_property.get("type") != "IntProperty"
            or rank_property.get("value") != expected
        ):
            raise DomainError(
                code="COMMAND_POSTCONDITION_FAILED",
                message="ArenaRankPoint did not update as requested.",
                http_status=409,
            )
