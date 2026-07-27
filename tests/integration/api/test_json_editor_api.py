from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from palworld_pal_editor.api.json_editor import json_editor_blueprint
from palworld_pal_editor.application.runtime import SESSION_RUNTIME
from tests.unit.test_raw_json_editor import _session


def _client(session):
    SESSION_RUNTIME.replace_for_tests(session)
    app = Flask(__name__)
    app.config.update(
        JWT_SECRET_KEY="test-secret-key-that-is-at-least-32-bytes",
        TESTING=True,
    )
    JWTManager(app)
    app.register_blueprint(json_editor_blueprint, url_prefix="/api/json-editor")
    with app.app_context():
        token = create_access_token(identity="test-user")
    return app.test_client(), {"Authorization": f"Bearer {token}"}


def test_json_editor_api_lists_reads_and_applies_raw_json() -> None:
    with TemporaryDirectory() as temp:
        session = _session(Path(temp))
        client, headers = _client(session)
        try:
            response = client.get(
                f"/api/json-editor/files?session_id={session.session_id}",
                headers=headers,
            )
            assert response.status_code == 200
            assert response.get_json()["data"]["files"][0]["path"] == "Level.sav"

            response = client.get(
                (
                    "/api/json-editor/document"
                    f"?session_id={session.session_id}&path=Level.sav"
                ),
                headers=headers,
            )
            assert response.status_code == 200
            assert response.mimetype == "application/json"
            document = json.loads(response.get_data(as_text=True))
            assert document["properties"]["Counter"]["value"] == 1
            assert response.headers["X-Palworld-Revision"] == "0"

            document["properties"]["Counter"]["value"] = 9
            response = client.post(
                (
                    "/api/json-editor/document"
                    f"?session_id={session.session_id}"
                    "&expected_revision=0&path=Level.sav"
                ),
                data=json.dumps(document),
                content_type="application/json",
                headers=headers,
            )
            assert response.status_code == 200
            result = response.get_json()["data"]
            assert result["changed"] is True
            assert result["revision"] == 1
            assert session.manager.gvas_file.properties["Counter"]["value"] == 9
        finally:
            SESSION_RUNTIME.replace_for_tests(None)


def test_json_editor_api_reports_precise_syntax_errors() -> None:
    with TemporaryDirectory() as temp:
        session = _session(Path(temp))
        client, headers = _client(session)
        try:
            response = client.post(
                (
                    "/api/json-editor/document"
                    f"?session_id={session.session_id}"
                    "&expected_revision=0&path=Level.sav"
                ),
                data='{\n  "header":',
                content_type="application/json",
                headers=headers,
            )
            assert response.status_code == 400
            error = response.get_json()["error"]
            assert error["code"] == "RAW_JSON_INVALID"
            assert error["details"]["line"] == 2
            assert session.revision == 0
        finally:
            SESSION_RUNTIME.replace_for_tests(None)
