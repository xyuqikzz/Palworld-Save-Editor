from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from palworld_pal_editor.api.save import save_blueprint
from palworld_pal_editor.application.runtime import SESSION_RUNTIME
from palworld_pal_editor.application.save_session import SaveSession


def test_map_api_returns_an_authenticated_read_only_save_snapshot() -> None:
    player = SimpleNamespace(
        PlayerUId="player-1",
        NickName="Ari",
        Level=42,
        group_id=None,
        LastLocation={"x": -100.0, "y": 200.0, "z": 30.0},
    )
    manager = SimpleNamespace(
        gvas_file=SimpleNamespace(properties={}, header=None),
        player_mapping={"player-1": player},
        group_data=SimpleNamespace(get_groups=lambda: []),
        camp_data=SimpleNamespace(get_camps=lambda: []),
    )
    session = SaveSession.from_loaded_manager(manager, Path("synthetic-save"))
    SESSION_RUNTIME.replace_for_tests(session)

    app = Flask(__name__)
    app.config.update(
        JWT_SECRET_KEY="test-secret-key-that-is-at-least-32-bytes",
        TESTING=True,
    )
    JWTManager(app)
    app.register_blueprint(save_blueprint, url_prefix="/api/save")
    with app.app_context():
        token = create_access_token(identity="test-user")
    client = app.test_client()

    try:
        unauthorized = client.get(
            f"/api/save/query/map?session_id={session.session_id}"
        )
        assert unauthorized.status_code == 401

        response = client.get(
            f"/api/save/query/map?session_id={session.session_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        payload = response.get_json()["data"]
        assert payload["revision"] == 0
        assert payload["live"] is False
        assert payload["location_source"] == "save_last_transform"
        assert payload["players"][0]["player_id"] == "player-1"
        assert session.revision == 0
        assert session.changes() == []
    finally:
        SESSION_RUNTIME.replace_for_tests(None)
