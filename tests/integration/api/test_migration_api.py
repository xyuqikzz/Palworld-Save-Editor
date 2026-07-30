from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from palworld_pal_editor.api.migration import migration_blueprint


def migration_client():
    app = Flask(__name__)
    app.config.update(
        JWT_SECRET_KEY="test-secret-key-that-is-at-least-32-bytes",
        TESTING=True,
    )
    JWTManager(app)
    app.register_blueprint(migration_blueprint, url_prefix="/api/migration")
    with app.app_context():
        token = create_access_token(identity="test-user")
    return app.test_client(), {"Authorization": f"Bearer {token}"}


def test_migration_api_requires_authentication() -> None:
    client, _headers = migration_client()

    response = client.post("/api/migration/analyze", json={})

    assert response.status_code == 401


def test_migration_analyze_rejects_unknown_mode() -> None:
    client, headers = migration_client()

    response = client.post(
        "/api/migration/analyze",
        headers=headers,
        json={"mode": "merge", "source": {}, "target": {}},
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "MIGRATION_MODE_UNSUPPORTED"


def test_migration_analyze_rejects_non_string_path() -> None:
    client, headers = migration_client()

    response = client.post(
        "/api/migration/analyze",
        headers=headers,
        json={
            "mode": "character_only",
            "source": {"platform": "steam", "path": []},
            "target": {"platform": "steam", "path": "target"},
        },
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "MIGRATION_SOURCE_INVALID"


def test_migration_analyze_uses_stable_response_envelope() -> None:
    client, headers = migration_client()
    plan = SimpleNamespace(to_dict=lambda: {"plan_id": "plan", "blockers": []})

    with patch(
        "palworld_pal_editor.api.migration.SAVE_MIGRATION.analyze",
        return_value=plan,
    ) as analyze:
        response = client.post(
            "/api/migration/analyze",
            headers=headers,
            json={
                "mode": "character_only",
                "source": {"platform": "steam", "path": "source"},
                "target": {"platform": "steam", "path": "target"},
            },
        )

    assert response.status_code == 200
    assert response.get_json() == {
        "status": 0,
        "data": {"plan_id": "plan", "blockers": []},
        "msg": None,
    }
    request = analyze.call_args.args[0]
    assert request.mode.value == "character_only"
    assert request.source.path == "source"
    assert request.target.path == "target"


def test_migration_execute_only_requires_an_operation_id() -> None:
    client, headers = migration_client()
    result = SimpleNamespace(to_dict=lambda: {"status": "completed"})

    with patch(
        "palworld_pal_editor.api.migration.SAVE_MIGRATION.execute",
        return_value=result,
    ) as execute:
        response = client.post(
            "/api/migration/execute",
            headers=headers,
            json={
                "plan_id": "plan",
                "mappings": [],
                "operation_id": "operation",
            },
        )

    assert response.status_code == 200
    assert response.get_json()["data"] == {"status": "completed"}
    execute.assert_called_once_with("plan", (), "operation")


def test_migration_status_uses_stable_response_envelope() -> None:
    client, headers = migration_client()
    status = {
        "plan_id": "plan",
        "operation_id": "operation",
        "stage": "validating",
        "progress": ["staging", "migrating", "validating"],
        "completed": False,
    }

    with patch(
        "palworld_pal_editor.api.migration.SAVE_MIGRATION.operation_status",
        return_value=status,
    ) as operation_status:
        response = client.post(
            "/api/migration/status",
            headers=headers,
            json={"plan_id": "plan", "operation_id": "operation"},
        )

    assert response.status_code == 200
    assert response.get_json() == {
        "status": 0,
        "data": status,
        "msg": None,
    }
    operation_status.assert_called_once_with("plan", "operation")
