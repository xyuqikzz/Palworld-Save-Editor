from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from palworld_pal_editor.application.arena_leaderboard_editor import (
    ArenaLeaderboardEditor,
)
from palworld_pal_editor.application.arena_npc_catalog import (
    ARENA_NPC_RANKINGS,
    ARENA_NPC_SOURCE_BUILD,
    ARENA_WORLD_RANKING_LIMIT,
)
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.core.pal_objects import PalObjects
from palworld_pal_editor.domain.errors import DomainError


class _ArenaPlayer:
    def __init__(
        self,
        player_id: str,
        name: str,
        rank_point: int | None,
        *,
        field_type: str = "IntProperty",
        guild_id: str | None = None,
    ) -> None:
        self.PlayerUId = player_id
        self.InstanceId = f"instance-{player_id}"
        self.NickName = name
        self.group_id = guild_id
        self._player_param = {}
        if rank_point is not None:
            self._player_param["ArenaRankPoint"] = {
                "id": None,
                "type": field_type,
                "value": rank_point,
            }


class _GroupData:
    def __init__(self) -> None:
        self._groups = {
            "guild-1": SimpleNamespace(guild_name="Arena Guild"),
        }

    def get_group(self, guild_id):
        return self._groups.get(guild_id)


def _session(*players: _ArenaPlayer) -> SaveSession:
    manager = SimpleNamespace(
        gvas_file=SimpleNamespace(header=None),
        player_mapping={player.PlayerUId: player for player in players},
        group_data=_GroupData(),
    )
    return SaveSession.from_loaded_manager(manager, Path("synthetic-save"))


def test_leaderboard_merges_game_npcs_and_reports_player_field_states() -> None:
    session = _session(
        _ArenaPlayer("player-b", "Bravo", 120),
        _ArenaPlayer("player-a", "Alpha", 120, guild_id="guild-1"),
        _ArenaPlayer("player-c", "Charlie", 40),
        _ArenaPlayer("player-missing", "Missing", None),
        _ArenaPlayer("player-wrong", "Wrong", 15, field_type="UInt32Property"),
    )

    result = ArenaLeaderboardEditor(session).leaderboard()

    player_entries = [
        entry for entry in result["entries"] if entry["entry_type"] == "player"
    ]
    assert [entry["player_id"] for entry in player_entries] == [
        "player-a",
        "player-b",
        "player-c",
        "player-missing",
        "player-wrong",
    ]
    assert [entry["rank"] for entry in player_entries] == [
        99,
        100,
        None,
        None,
        None,
    ]
    assert player_entries[0]["guild_name"] == "Arena Guild"
    assert player_entries[3]["field_state"] == "missing"
    assert player_entries[3]["writable"] is True
    assert player_entries[3]["can_initialize"] is True
    assert player_entries[3]["capability_error"] == "ARENA_RANK_POINT_MISSING"
    assert player_entries[4]["field_state"] == "unsupported"
    assert player_entries[4]["capability_error"] == "ARENA_RANK_POINT_UNSUPPORTED"
    assert result["entries"][0]["entry_type"] == "npc"
    assert result["entries"][0]["ranking_npc_id"] == "Ranking1"
    assert result["entries"][0]["rank_point"] == 5000
    assert result["editable_count"] == 4
    assert result["ranked_player_count"] == 3
    assert result["initializable_count"] == 1
    assert result["unsupported_count"] == 1
    assert result["npc_count"] == 98
    assert result["ranking_limit"] == 100
    assert result["npc_source_build"] == 24_088_745
    assert result["revision"] == 0


def test_shipped_arena_npc_catalog_matches_build_24088745_boundaries() -> None:
    assert ARENA_NPC_SOURCE_BUILD == 24_088_745
    assert ARENA_WORLD_RANKING_LIMIT == 100
    assert len(ARENA_NPC_RANKINGS) == 100
    assert ARENA_NPC_RANKINGS[0].ranking_npc_id == "Ranking1"
    assert ARENA_NPC_RANKINGS[0].name_text_id == "NAME_DarkTrader"
    assert ARENA_NPC_RANKINGS[0].rank_point == 5000
    assert ARENA_NPC_RANKINGS[-1].ranking_npc_id == "Ranking100"
    assert ARENA_NPC_RANKINGS[-1].name_text_id == "NAME_BattlePaltamer001"
    assert ARENA_NPC_RANKINGS[-1].rank_point == 50
    assert {
        left.rank_point - right.rank_point
        for left, right in zip(ARENA_NPC_RANKINGS, ARENA_NPC_RANKINGS[1:])
    } == {50}


def test_set_rank_point_is_revision_bound_and_records_only_level_change() -> None:
    player = _ArenaPlayer("player-1", "Player One", 50)
    session = _session(player)
    editor = ArenaLeaderboardEditor(session)

    result = editor.set_rank_point(
        session_id=session.session_id,
        expected_revision=0,
        player_id=player.PlayerUId,
        rank_point=900,
    )

    assert PalObjects.get_BaseType(player._player_param["ArenaRankPoint"]) == 900
    assert result["revision"] == 1
    assert result["affected_count"] == 1
    updated = next(
        entry
        for entry in result["entries"]
        if entry.get("player_id") == player.PlayerUId
    )
    assert updated["rank_point"] == 900
    assert updated["rank"] == 83
    assert session.changes()[0]["affected_records"] == [
        "level:CharacterSaveParameterMap"
    ]

    with pytest.raises(DomainError) as raised:
        editor.set_rank_point(
            session_id=session.session_id,
            expected_revision=0,
            player_id=player.PlayerUId,
            rank_point=1,
        )
    assert raised.value.code == "STALE_REVISION"
    assert PalObjects.get_BaseType(player._player_param["ArenaRankPoint"]) == 900


@pytest.mark.parametrize("rank_point", [True, -1, 2_147_483_648, 1.5, "10"])
def test_set_rank_point_rejects_values_outside_nonnegative_int32(rank_point) -> None:
    player = _ArenaPlayer("player-1", "Player One", 50)
    editor = ArenaLeaderboardEditor(_session(player))

    with pytest.raises(DomainError) as raised:
        editor.set_rank_point(
            session_id=editor._session.session_id,
            expected_revision=0,
            player_id=player.PlayerUId,
            rank_point=rank_point,
        )

    assert raised.value.code == "INVALID_ARENA_RANK_POINT"


def test_set_rank_point_creates_verified_int_property_for_a_missing_field() -> None:
    missing = _ArenaPlayer("missing", "Missing", None)
    session = _session(missing)
    editor = ArenaLeaderboardEditor(session)

    result = editor.set_rank_point(
        session_id=session.session_id,
        expected_revision=0,
        player_id="missing",
        rank_point=321,
    )

    assert missing._player_param["ArenaRankPoint"] == PalObjects.IntProperty(321)
    entry = next(
        row for row in result["entries"] if row.get("player_id") == "missing"
    )
    assert entry["field_state"] == "present"
    assert entry["rank_point"] == 321
    assert session.changes()[0]["command"] == "InitializeArenaRankPoint"
    assert session.changes()[0]["before"]["field_present"] is False
    assert session.changes()[0]["after"]["field_present"] is True
    assert session.revision == 1


def test_set_rank_point_refuses_an_unknown_existing_layout() -> None:
    wrong = _ArenaPlayer("wrong", "Wrong", 12, field_type="UInt32Property")
    session = _session(wrong)
    editor = ArenaLeaderboardEditor(session)

    with pytest.raises(DomainError) as wrong_error:
        editor.set_rank_point(
            session_id=session.session_id,
            expected_revision=0,
            player_id="wrong",
            rank_point=1,
        )
    assert wrong_error.value.code == "ARENA_RANK_POINT_UNSUPPORTED"
    assert wrong._player_param["ArenaRankPoint"]["type"] == "UInt32Property"
    assert session.revision == 0


def test_failed_missing_field_initialization_rolls_back_the_new_property(
    monkeypatch,
) -> None:
    missing = _ArenaPlayer("missing", "Missing", None)
    session = _session(missing)
    editor = ArenaLeaderboardEditor(session)

    def fail_validation(_rank_property, _expected):
        raise DomainError(
            code="COMMAND_POSTCONDITION_FAILED",
            message="forced failure",
            http_status=409,
        )

    monkeypatch.setattr(editor, "_validate_postcondition", fail_validation)

    with pytest.raises(DomainError) as raised:
        editor.set_rank_point(
            session_id=session.session_id,
            expected_revision=0,
            player_id="missing",
            rank_point=321,
        )

    assert raised.value.code == "COMMAND_POSTCONDITION_FAILED"
    assert "ArenaRankPoint" not in missing._player_param
    assert session.revision == 0
    assert session.changes() == []


def test_reset_all_changes_supported_rows_and_explicitly_reports_skips() -> None:
    first = _ArenaPlayer("first", "First", 800)
    zero = _ArenaPlayer("zero", "Zero", 0)
    missing = _ArenaPlayer("missing", "Missing", None)
    wrong = _ArenaPlayer("wrong", "Wrong", 12, field_type="UInt32Property")
    session = _session(first, zero, missing, wrong)

    result = ArenaLeaderboardEditor(session).reset_all(
        session_id=session.session_id,
        expected_revision=0,
    )

    assert PalObjects.get_BaseType(first._player_param["ArenaRankPoint"]) == 0
    assert PalObjects.get_BaseType(zero._player_param["ArenaRankPoint"]) == 0
    assert result["affected_count"] == 1
    assert result["skipped_count"] == 2
    assert {row["player_id"] for row in result["skipped"]} == {"missing", "wrong"}
    assert session.revision == 1


def test_reset_all_with_no_writable_arena_fields_fails_without_mutation() -> None:
    missing = _ArenaPlayer("missing", "Missing", None)
    session = _session(missing)

    with pytest.raises(DomainError) as raised:
        ArenaLeaderboardEditor(session).reset_all(
            session_id=session.session_id,
            expected_revision=0,
        )

    assert raised.value.code == "ARENA_RANK_POINT_UNAVAILABLE"
    assert session.revision == 0
