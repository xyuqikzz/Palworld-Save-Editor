from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from palworld_pal_editor.api.save import save_blueprint
from palworld_pal_editor.application.runtime import SESSION_RUNTIME
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.config import Config
from palworld_pal_editor.domain.models import SavePlatform, SaveSource


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
        self.assertEqual("steam", payload["data"]["session"]["platform"])
        self.assertTrue(payload["data"]["session"]["sourceId"].startswith("steam-"))
        self.assertTrue(payload["data"]["session"]["saveCapabilities"]["exportSteamCopy"])
        self.assertNotIn("properties", str(payload))

        response = self.client.get("/api/save/changes", headers=self.headers)
        self.assertEqual(200, response.status_code)
        self.assertEqual([], response.get_json()["data"]["changes"])

    def test_session_requires_authentication(self) -> None:
        response = self.client.get("/api/save/session")
        self.assertEqual(401, response.status_code)

    def test_korean_is_exposed_and_accepted_by_save_i18n_endpoints(self) -> None:
        from palworld_pal_editor.config import Config

        response = self.client.get("/api/save/fetch_config")
        self.assertEqual(200, response.status_code)
        self.assertEqual("한국어", response.get_json()["data"]["I18nList"]["ko"])

        previous_language = Config.i18n
        try:
            response = self.client.patch(
                "/api/save/i18n",
                json={"I18n": "ko"},
            )
            self.assertEqual(200, response.status_code)
            self.assertEqual(0, response.get_json()["status"])
            self.assertEqual("ko", Config.i18n)
        finally:
            Config.i18n = previous_language

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

    def test_loading_same_save_after_refresh_resumes_dirty_session(self) -> None:
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

        with (
            patch(
                "palworld_pal_editor.api.save.Config.path",
                str(self.session.source),
            ),
            patch("palworld_pal_editor.api.save.Config.save_to_file"),
        ):
            response = self.client.post(
                "/api/save/load",
                json={"ReadPath": str(self.session.source)},
                headers=self.headers,
            )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual(0, payload["status"])
        self.assertEqual(
            self.session.session_id, payload["data"]["session"]["session_id"]
        )
        self.assertEqual(1, payload["data"]["session"]["revision"])
        self.assertEqual(1, payload["data"]["session"]["pending_change_count"])

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

    def test_source_discovery_is_sanitized_and_load_inputs_are_mutually_exclusive(self) -> None:
        source = SaveSource(
            platform=SavePlatform.XGP,
            canonical_path=Path("sensitive-user-directory").resolve(),
            source_id="xgp-opaque",
            display_name="Game Pass · World ABCD1234",
            world_id="ABCD1234" + "0" * 24,
        )
        with patch(
            "palworld_pal_editor.api.save.SOURCE_CATALOG.discover",
            return_value=[source],
        ):
            response = self.client.get("/api/save/sources", headers=self.headers)
        self.assertEqual(200, response.status_code)
        public = response.get_json()["data"]["sources"][0]
        self.assertEqual("xgp-opaque", public["sourceId"])
        self.assertEqual("ABCD1234", public["worldId"])
        self.assertNotIn("canonical", str(public).lower())
        self.assertNotIn("sensitive-user-directory", str(public))

        response = self.client.post(
            "/api/save/load",
            json={"ReadPath": "steam", "sourceId": "xgp-opaque"},
            headers=self.headers,
        )
        self.assertEqual(400, response.status_code)
        self.assertEqual("INVALID_REQUEST", response.get_json()["error"]["code"])

    def test_xgp_source_discovery_is_scoped_to_the_selected_folder(self) -> None:
        source = SaveSource(
            platform=SavePlatform.XGP,
            canonical_path=Path("selected-user-directory").resolve(),
            source_id="xgp-selected",
            display_name="Game Pass · World CAFE1234",
            world_id="CAFE1234" + "0" * 24,
        )
        with patch(
            "palworld_pal_editor.api.save.SOURCE_CATALOG.discover_selected",
            return_value=[source],
        ) as discover:
            response = self.client.post(
                "/api/save/sources",
                json={"path": "D:/chosen/wgs"},
                headers=self.headers,
            )

        self.assertEqual(200, response.status_code)
        discover.assert_called_once_with("D:/chosen/wgs")
        self.assertEqual(
            "xgp-selected",
            response.get_json()["data"]["sources"][0]["sourceId"],
        )

    def test_xgp_source_discovery_rejects_a_folder_without_save_slots(self) -> None:
        with TemporaryDirectory() as temp:
            response = self.client.post(
                "/api/save/sources",
                json={"path": temp},
                headers=self.headers,
            )

        self.assertEqual(404, response.status_code)
        payload = response.get_json()
        self.assertEqual(1, payload["status"])
        self.assertEqual("WGS_NOT_FOUND", payload["error"]["code"])

    def test_directory_browser_does_not_change_the_configured_steam_path(self) -> None:
        with TemporaryDirectory() as temp:
            original = Config.path
            Config.path = "unchanged-steam-path"
            try:
                response = self.client.post(
                    "/api/save/browse-directory",
                    json={"path": temp},
                    headers=self.headers,
                )
                self.assertEqual(200, response.status_code)
                self.assertEqual(Path(temp).resolve(), Path(response.get_json()["data"]["currentPath"]))
                self.assertEqual("unchanged-steam-path", Config.path)
            finally:
                Config.path = original

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
