from __future__ import annotations

from pathlib import Path

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from palworld_pal_editor.api.save import save_blueprint
from palworld_pal_editor.application.runtime import SESSION_RUNTIME
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.core.character_index import CharacterIndex
from tests.unit.test_structural_pal_editor import GROUP_ID, PAL_ID, make_manager


def _client_with_broken_session():
    app = Flask(__name__)
    app.config.update(
        JWT_SECRET_KEY="test-secret-key-that-is-at-least-32-bytes",
        TESTING=True,
    )
    JWTManager(app)
    app.register_blueprint(save_blueprint, url_prefix="/api/save")
    manager, _player, _pal = make_manager()
    manager.group_data.get_group(GROUP_ID).del_pal(PAL_ID)
    session = SaveSession.from_loaded_manager(
        manager, Path("synthetic-character-reference-repair-api")
    )
    SESSION_RUNTIME.replace_for_tests(session)
    with app.app_context():
        token = create_access_token(identity="test-user")
    return app.test_client(), {"Authorization": f"Bearer {token}"}, session


def test_repair_character_references_is_revision_bound_and_machine_readable() -> None:
    client, headers, session = _client_with_broken_session()
    try:
        response = client.post(
            "/api/save/repair-character-references",
            headers=headers,
            json={
                "session_id": session.session_id,
                "expected_revision": 0,
            },
        )

        assert response.status_code == 200
        payload = response.get_json()
        assert payload["status"] == 0
        assert payload["data"]["revision"] == 1
        assert payload["data"]["repair"]["repair_count"] == 1
        assert CharacterIndex(session.manager).hard_issues() == []
        assert session.summary().pending_change_count == 1

        repeated = client.post(
            "/api/save/repair-character-references",
            headers=headers,
            json={
                "session_id": session.session_id,
                "expected_revision": 1,
            },
        )
        assert repeated.status_code == 409
        assert (
            repeated.get_json()["error"]["code"]
            == "CHARACTER_REFERENCE_REPAIR_UNAVAILABLE"
        )
    finally:
        SESSION_RUNTIME.replace_for_tests(None)


def test_repair_character_references_requires_authentication() -> None:
    client, _headers, _session = _client_with_broken_session()
    try:
        response = client.post(
            "/api/save/repair-character-references",
            json={"session_id": "session", "expected_revision": 0},
        )
        assert response.status_code == 401
    finally:
        SESSION_RUNTIME.replace_for_tests(None)
