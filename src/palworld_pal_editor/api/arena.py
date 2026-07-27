from __future__ import annotations

from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from palworld_pal_editor.application.arena_leaderboard_editor import (
    ArenaLeaderboardEditor,
)
from palworld_pal_editor.application.runtime import SESSION_RUNTIME
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.utils.util import reply


arena_blueprint = Blueprint("arena", __name__)


def _domain_error(error: DomainError):
    return reply(1, msg=error.message, error=error.to_dict()), error.http_status


@arena_blueprint.route("/leaderboard", methods=["GET"])
@jwt_required()
def get_leaderboard():
    try:
        session = SESSION_RUNTIME.get(request.args.get("session_id"))
        return reply(0, ArenaLeaderboardEditor(session).leaderboard())
    except DomainError as error:
        return _domain_error(error)


@arena_blueprint.route("/commands", methods=["POST"])
@jwt_required()
def execute_arena_command():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _domain_error(
            DomainError(
                code="INVALID_REQUEST",
                message="A JSON object is required.",
                http_status=400,
            )
        )

    command = payload.get("command")
    fields = {
        "set_rank_point": {"player_id", "rank_point"},
        "reset_player": {"player_id"},
        "reset_all": set(),
    }
    if command not in fields:
        return _domain_error(
            DomainError(
                code="UNSUPPORTED_COMMAND",
                message="Unsupported arena command.",
                field="command",
                http_status=400,
            )
        )
    allowed = {"session_id", "expected_revision", "command"} | fields[command]
    unknown = sorted(set(payload) - allowed)
    if unknown:
        return _domain_error(
            DomainError(
                code="UNSUPPORTED_COMMAND_FIELD",
                message="The request contains unsupported fields.",
                details={"fields": unknown},
                http_status=400,
            )
        )

    try:
        session = SESSION_RUNTIME.get(payload.get("session_id"))
        editor = ArenaLeaderboardEditor(session)
        if command == "reset_all":
            result = editor.reset_all(
                session_id=payload.get("session_id"),
                expected_revision=payload.get("expected_revision"),
            )
        else:
            result = editor.set_rank_point(
                session_id=payload.get("session_id"),
                expected_revision=payload.get("expected_revision"),
                player_id=payload.get("player_id"),
                rank_point=(
                    0 if command == "reset_player" else payload.get("rank_point")
                ),
            )
        return reply(0, result)
    except DomainError as error:
        return _domain_error(error)
