from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import unittest

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from palworld_pal_editor.api.save import save_blueprint
from palworld_pal_editor.application.runtime import SESSION_RUNTIME
from palworld_pal_editor.application.save_session import SaveSession


class SessionApiTests(unittest.TestCase):
    def setUp(self) -> None:
        app = Flask(__name__)
        app.config.update(
            JWT_SECRET_KEY="test-secret-key-that-is-at-least-32-bytes",
            TESTING=True,
        )
        JWTManager(app)
        app.register_blueprint(save_blueprint, url_prefix="/api/save")
        manager = SimpleNamespace(
            gvas_file=SimpleNamespace(header=None),
            player_mapping={},
        )
        self.session = SaveSession.from_loaded_manager(manager, Path("synthetic-save"))
        SESSION_RUNTIME.replace_for_tests(self.session)
        with app.app_context():
            token = create_access_token(identity="test-user")
        self.client = app.test_client()
        self.headers = {"Authorization": f"Bearer {token}"}

    def tearDown(self) -> None:
        SESSION_RUNTIME.replace_for_tests(None)

    def test_session_and_changes_use_stable_envelope(self) -> None:
        response = self.client.get("/api/save/session", headers=self.headers)
        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual(0, payload["status"])
        self.assertEqual(self.session.session_id, payload["data"]["session"]["session_id"])
        self.assertNotIn("properties", str(payload))

        response = self.client.get("/api/save/changes", headers=self.headers)
        self.assertEqual(200, response.status_code)
        self.assertEqual([], response.get_json()["data"]["changes"])

    def test_session_requires_authentication(self) -> None:
        response = self.client.get("/api/save/session")
        self.assertEqual(401, response.status_code)

    def test_unknown_session_returns_machine_readable_error(self) -> None:
        response = self.client.get(
            "/api/save/session?session_id=stale", headers=self.headers
        )
        self.assertEqual(404, response.status_code)
        payload = response.get_json()
        self.assertEqual("SESSION_NOT_FOUND", payload["error"]["code"])
        self.assertNotIn("Traceback", str(payload))

    def test_dirty_session_close_requires_and_honors_explicit_discard(self) -> None:
        state = {"count": 1}
        self.session.apply_atomic(
            session_id=self.session.session_id,
            expected_revision=0,
            command="SyntheticUpdate",
            target={},
            snapshot=lambda: deepcopy(state),
            restore=lambda old: (state.clear(), state.update(old)),
            before=lambda: dict(state),
            mutate=lambda: state.update(count=2),
            validate=lambda: None,
            after=lambda: dict(state),
            affected_records=("synthetic",),
        )
        payload = {
            "session_id": self.session.session_id,
            "expected_revision": 1,
        }

        response = self.client.delete(
            "/api/save/session", json=payload, headers=self.headers
        )
        self.assertEqual(409, response.status_code)
        self.assertEqual(
            "UNSAVED_CHANGES_PRESENT", response.get_json()["error"]["code"]
        )
        self.assertIs(self.session, SESSION_RUNTIME.get())

        response = self.client.delete(
            "/api/save/session",
            json={**payload, "discard_changes": True},
            headers=self.headers,
        )
        self.assertEqual(200, response.status_code)
        self.assertEqual(1, response.get_json()["data"]["discarded_change_count"])

    def test_clean_session_can_be_closed_without_discard(self) -> None:
        response = self.client.delete(
            "/api/save/session",
            json={
                "session_id": self.session.session_id,
                "expected_revision": 0,
                "discard_changes": False,
            },
            headers=self.headers,
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual(0, response.get_json()["data"]["discarded_change_count"])

    def test_query_and_performance_endpoints_are_session_scoped(self) -> None:
        response = self.client.get(
            f"/api/save/query/players?session_id={self.session.session_id}",
            headers=self.headers,
        )
        self.assertEqual(200, response.status_code)
        self.assertEqual([], response.get_json()["data"]["players"])

        response = self.client.get(
            f"/api/save/performance?session_id={self.session.session_id}",
            headers=self.headers,
        )
        self.assertEqual(200, response.status_code)
        self.assertEqual(
            0, response.get_json()["data"]["player_files_loaded"]
        )

        response = self.client.get(
            f"/api/save/query/players?session_id={self.session.session_id}"
            "&sort_by=raw_gvas_path",
            headers=self.headers,
        )
        self.assertEqual(400, response.status_code)
        self.assertEqual(
            "INVALID_SORT_FIELD", response.get_json()["error"]["code"]
        )


if __name__ == "__main__":
    unittest.main()
