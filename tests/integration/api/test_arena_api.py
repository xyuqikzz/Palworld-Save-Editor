from __future__ import annotations

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from palworld_pal_editor.api.arena import arena_blueprint
from palworld_pal_editor.application.runtime import SESSION_RUNTIME
from tests.unit.test_arena_leaderboard_editor import _ArenaPlayer, _session


def _client(session):
    SESSION_RUNTIME.replace_for_tests(session)
    app = Flask(__name__)
    app.config.update(
        JWT_SECRET_KEY="test-secret-key-that-is-at-least-32-bytes",
        TESTING=True,
    )
    JWTManager(app)
    app.register_blueprint(arena_blueprint, url_prefix="/api/arena")
    with app.app_context():
        token = create_access_token(identity="test-user")
    return app.test_client(), {"Authorization": f"Bearer {token}"}


def test_arena_api_lists_and_updates_the_world_leaderboard() -> None:
    session = _session(
        _ArenaPlayer("player-1", "One", 25),
        _ArenaPlayer("player-2", "Two", 10),
    )
    client, headers = _client(session)
    try:
        response = client.get(
            f"/api/arena/leaderboard?session_id={session.session_id}",
            headers=headers,
        )
        assert response.status_code == 200
        payload = response.get_json()["data"]
        player_rows = [
            row for row in payload["entries"] if row["entry_type"] == "player"
        ]
        assert [row["rank_point"] for row in player_rows] == [25, 10]
        assert payload["entries"][0]["ranking_npc_id"] == "Ranking1"
        assert payload["entries"][0]["rank_point"] == 5000
        assert payload["npc_source_build"] == 24_088_745

        response = client.post(
            "/api/arena/commands",
            headers=headers,
            json={
                "session_id": session.session_id,
                "expected_revision": 0,
                "command": "set_rank_point",
                "player_id": "player-2",
                "rank_point": 100,
            },
        )
        assert response.status_code == 200
        payload = response.get_json()["data"]
        assert payload["revision"] == 1
        updated = next(
            row for row in payload["entries"] if row.get("player_id") == "player-2"
        )
        assert updated["rank"] == 99
        assert updated["rank_point"] == 100
    finally:
        SESSION_RUNTIME.replace_for_tests(None)


def test_arena_api_resets_one_or_all_and_rejects_extra_fields() -> None:
    session = _session(
        _ArenaPlayer("player-1", "One", 25),
        _ArenaPlayer("player-2", "Two", 10),
    )
    client, headers = _client(session)
    try:
        response = client.post(
            "/api/arena/commands",
            headers=headers,
            json={
                "session_id": session.session_id,
                "expected_revision": 0,
                "command": "reset_player",
                "player_id": "player-1",
            },
        )
        assert response.status_code == 200
        assert response.get_json()["data"]["affected_count"] == 1

        response = client.post(
            "/api/arena/commands",
            headers=headers,
            json={
                "session_id": session.session_id,
                "expected_revision": 1,
                "command": "reset_all",
            },
        )
        assert response.status_code == 200
        assert response.get_json()["data"]["affected_count"] == 1

        response = client.post(
            "/api/arena/commands",
            headers=headers,
            json={
                "session_id": session.session_id,
                "expected_revision": 2,
                "command": "reset_all",
                "rank_point": 9,
            },
        )
        assert response.status_code == 400
        assert response.get_json()["error"]["code"] == "UNSUPPORTED_COMMAND_FIELD"
    finally:
        SESSION_RUNTIME.replace_for_tests(None)
