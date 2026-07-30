from __future__ import annotations

from copy import deepcopy
import os
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
from palworld_pal_editor.core.pal_entity import PalEntity
from palworld_pal_editor.core.pal_objects import PalObjects, toUUID
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.domain.models import SavePlatform, SaveSource
from palworld_pal_editor.utils.data_provider import DataProvider


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

    def test_select_local_data_is_revision_bound_without_pending_change(
        self,
    ) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "world"
            root.mkdir()
            selected = Path(temporary_directory) / "LocalData.sav"
            selected.write_bytes(b"synthetic-local-data")
            manager = SimpleNamespace(
                gvas_file=SimpleNamespace(header=None),
                player_mapping={},
            )
            session = SaveSession.from_loaded_manager(manager, root)
            SESSION_RUNTIME.replace_for_tests(session)
            capability = SimpleNamespace(
                to_dict=lambda: {
                    "available": True,
                    "reason": None,
                    "format": "WorldMapUISaveDataMap",
                    "maps": ["MainMap", "Tree"],
                }
            )
            document = SimpleNamespace(capability=capability)

            with patch(
                "palworld_pal_editor.application.save_session."
                "LocalDataDocument.open_file",
                return_value=document,
            ):
                response = self.client.post(
                    "/api/save/local-data/select",
                    headers=self.headers,
                    json={
                        "session_id": session.session_id,
                        "expected_revision": 0,
                        "path": str(selected),
                    },
                )

            self.assertEqual(200, response.status_code, response.get_json())
            data = response.get_json()["data"]
            self.assertEqual(1, data["revision"])
            self.assertTrue(data["selection"]["selected"])
            self.assertEqual(str(selected.resolve()), data["selection"]["source"])
            self.assertTrue(
                data["saveCapabilities"]["fogOfWarReset"]["available"]
            )
            self.assertEqual([], session.changes())
            self.assertEqual(0, session.summary().pending_change_count)

    def test_save_backup_failure_returns_only_safe_diagnostics_and_logs_traceback(
        self,
    ) -> None:
        error = DomainError(
            code="BACKUP_FAILED",
            message="A complete, verified backup could not be created.",
            details={
                "backup_path": "D:/safe-backup",
                "phase": "copy_file",
                "failed_file": "Level.sav",
                "os_error_code": 28,
                "os_error_category": "disk_space",
                "retryable": True,
            },
            retryable=True,
            http_status=500,
        )
        with (
            patch(
                "palworld_pal_editor.api.save.SaveWriter.save",
                side_effect=error,
            ),
            patch(
                "palworld_pal_editor.api.save.LOGGER.error"
            ) as log_error,
        ):
            response = self.client.post(
                "/api/save/save",
                headers=self.headers,
                json={
                    "session_id": self.session.session_id,
                    "expected_revision": self.session.revision,
                },
            )

        self.assertEqual(500, response.status_code)
        payload = response.get_json()
        self.assertEqual("BACKUP_FAILED", payload["error"]["code"])
        self.assertEqual(
            {
                "backup_path",
                "phase",
                "failed_file",
                "os_error_code",
                "os_error_category",
                "retryable",
            },
            set(payload["error"]["details"]),
        )
        self.assertNotIn("token", str(payload).casefold())
        self.assertNotIn("credential", str(payload).casefold())
        logged = log_error.call_args.args[0]
        self.assertIn("Save request rejected (BACKUP_FAILED)", logged)
        self.assertIn("Traceback", logged)
        self.assertNotIn("patch_paldata", logged)

    def test_fetch_config_only_reports_nonempty_password(self) -> None:
        for password, expected in ((None, False), ("", False), ("configured", True)):
            with self.subTest(password_state="nonempty" if password else "empty"):
                with patch.object(Config, "password", password):
                    response = self.client.get("/api/save/fetch_config")

                self.assertEqual(200, response.status_code)
                self.assertIs(expected, response.get_json()["data"]["HasPassword"])

    def test_fetch_config_auto_selects_the_latest_valid_steam_world(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            local_app_data = Path(temporary_directory)
            save_games = local_app_data / "Pal" / "Saved" / "SaveGames"
            older_world = save_games / "111" / "WORLD_A"
            latest_world = save_games / "222" / "WORLD_B"
            invalid_world = save_games / "333" / "WORLD_C"

            for world in (older_world, latest_world):
                (world / "Players").mkdir(parents=True)
                (world / "Level.sav").write_bytes(b"save")
            invalid_world.mkdir(parents=True)
            (invalid_world / "Level.sav").write_bytes(b"newer-but-incomplete")

            os.utime(older_world / "Level.sav", ns=(1_000, 1_000))
            os.utime(latest_world / "Level.sav", ns=(2_000, 2_000))
            os.utime(invalid_world / "Level.sav", ns=(3_000, 3_000))

            with (
                patch.object(Config, "path", None),
                patch.dict(os.environ, {"LOCALAPPDATA": str(local_app_data)}),
            ):
                response = self.client.get("/api/save/fetch_config")
                self.assertIsNone(Config.path)

            self.assertEqual(200, response.status_code)
            self.assertEqual(
                str(latest_world.resolve()),
                response.get_json()["data"]["Path"],
            )

    def test_complete_active_expeditions_is_an_atomic_save_command(self) -> None:
        expedition_id = "44444444-5555-6666-7777-888888888888"
        state = {"start_time": 100}
        manager = self.session.manager
        manager.completable_expeditions = lambda: (
            [{"expedition_id": expedition_id}] if state["start_time"] > 1 else []
        )
        manager.expedition_completion_state = lambda _ids: [
            {
                "expedition_id": expedition_id,
                "mission_id": "DUNGEON_SAKURAJIMA",
                "member_count": 56,
                "state": 2,
                "start_time": state["start_time"],
                "can_complete": state["start_time"] > 1,
            }
        ]
        manager.snapshot_expedition_data = lambda: state["start_time"]
        manager.restore_expedition_data = lambda value: state.update(
            start_time=value
        )

        def complete():
            state["start_time"] = 1
            return [expedition_id]

        manager.complete_active_expeditions = complete
        response = self.client.post(
            "/api/save/expeditions/commands",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 0,
                "command": "complete_active_expeditions",
            },
        )

        self.assertEqual(200, response.status_code, response.get_json())
        payload = response.get_json()["data"]
        self.assertEqual(1, payload["revision"])
        self.assertEqual(1, payload["value"]["completed_count"])
        self.assertEqual([expedition_id], payload["value"]["expedition_ids"])
        self.assertEqual("on_next_game_load", payload["value"]["settlement"])
        self.assertEqual(1, state["start_time"])
        self.assertEqual(1, self.session.revision)

    def test_complete_one_expedition_leaves_other_active_targets_unchanged(
        self,
    ) -> None:
        first_id = "44444444-5555-6666-7777-888888888888"
        second_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        state = {first_id: 100, second_id: 200}
        manager = self.session.manager

        def completable(expedition_ids=None):
            wanted = set(expedition_ids or state)
            return [
                {"expedition_id": expedition_id}
                for expedition_id, start_time in state.items()
                if expedition_id in wanted and start_time > 1
            ]

        def completion_state(expedition_ids):
            return [
                {
                    "expedition_id": expedition_id,
                    "mission_id": "DUNGEON_GRASS",
                    "member_count": 5,
                    "state": 2,
                    "start_time": state[expedition_id],
                    "can_complete": state[expedition_id] > 1,
                }
                for expedition_id in expedition_ids
            ]

        manager.completable_expeditions = completable
        manager.expedition_completion_state = completion_state
        manager.snapshot_expedition_data = lambda: deepcopy(state)
        manager.restore_expedition_data = lambda value: (
            state.clear(),
            state.update(value),
        )

        def complete(expedition_ids=None):
            completed = []
            for expedition_id in expedition_ids or state:
                if state[expedition_id] > 1:
                    state[expedition_id] = 1
                    completed.append(expedition_id)
            return completed

        manager.complete_active_expeditions = complete
        response = self.client.post(
            "/api/save/expeditions/commands",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 0,
                "command": "complete_expedition",
                "expedition_id": first_id,
            },
        )

        self.assertEqual(200, response.status_code, response.get_json())
        payload = response.get_json()["data"]
        self.assertEqual([first_id], payload["value"]["expedition_ids"])
        self.assertEqual(1, state[first_id])
        self.assertEqual(200, state[second_id])

    def test_expedition_query_includes_base_guild_members_and_invalid_locks(
        self,
    ) -> None:
        expedition_id = "44444444-5555-6666-7777-888888888888"
        invalid_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        group_id = toUUID("33333333-4444-5555-6666-777777777777")
        owner_id = toUUID("11111111-2222-3333-4444-555555555555")
        container_id = toUUID("22222222-3333-4444-5555-666666666666")
        valid_pal = PalEntity(
            PalObjects.PalSaveParameter(
                toUUID("11111111-aaaa-bbbb-cccc-222222222222"),
                owner_id,
                container_id,
                0,
                group_id,
            )
        )
        invalid_pal = PalEntity(
            PalObjects.PalSaveParameter(
                toUUID("22222222-aaaa-bbbb-cccc-333333333333"),
                owner_id,
                container_id,
                1,
                group_id,
            )
        )
        valid_pal._pal_param[
            "MapObjectConcreteInstanceIdAssignedToExpedition"
        ] = PalObjects.Guid(expedition_id)
        invalid_pal._pal_param[
            "MapObjectConcreteInstanceIdAssignedToExpedition"
        ] = PalObjects.Guid(invalid_id)
        manager = self.session.manager
        manager.player_mapping = {
            str(owner_id): SimpleNamespace(
                PlayerUId=owner_id,
                NickName="Owner",
                _palbox={
                    str(valid_pal.InstanceId): valid_pal,
                    str(invalid_pal.InstanceId): invalid_pal,
                },
            )
        }
        manager.baseworker_mapping = {}
        manager._dangling_pals = {}
        manager.camp_data = SimpleNamespace(
            get_camps=lambda: [
                SimpleNamespace(id="base-1", name="Base One")
            ]
        )
        manager.group_data = SimpleNamespace(
            get_groups=lambda: [
                SimpleNamespace(
                    group_id="guild-1",
                    guild_name="Guild One",
                    base_ids=["base-1"],
                )
            ]
        )
        manager.expedition_records = lambda: [
            {
                "expedition_id": expedition_id,
                "mission_id": "DUNGEON_GRASS",
                "base_id": "base-1",
                "guild_id": "guild-1",
                "members": [
                    {
                        "pal_id": str(valid_pal.InstanceId),
                        "owner_player_uid": str(owner_id),
                    }
                ],
                "state": 2,
                "start_time": 100,
                "active": True,
                "can_complete": True,
            }
        ]
        manager.expedition_assignment_status = lambda pal: (
            "valid" if pal is valid_pal else "invalid"
        )

        response = self.client.get(
            f"/api/save/query/expeditions?session_id={self.session.session_id}",
            headers=self.headers,
        )

        self.assertEqual(200, response.status_code, response.get_json())
        data = response.get_json()["data"]
        self.assertEqual(1, data["active_count"])
        self.assertEqual("Base One", data["expeditions"][0]["base_name"])
        self.assertEqual(1, data["expeditions"][0]["base_number"])
        self.assertEqual("Guild One", data["expeditions"][0]["guild_name"])
        self.assertEqual(
            str(valid_pal.InstanceId).lower(),
            data["expeditions"][0]["members"][0]["pal_id"],
        )
        self.assertEqual(1, data["invalid_locked_count"])
        self.assertEqual(
            str(invalid_pal.InstanceId).lower(),
            data["invalid_locked_pals"][0]["pal_id"],
        )

    def test_heal_all_pals_is_an_atomic_whole_save_command(self) -> None:
        pal = PalEntity(
            PalObjects.PalSaveParameter(
                toUUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"),
                toUUID("11111111-2222-3333-4444-555555555555"),
                toUUID("22222222-3333-4444-5555-666666666666"),
                0,
                toUUID("33333333-4444-5555-6666-777777777777"),
            )
        )
        pal._pal_param["Level"] = PalObjects.ByteProperty(10)
        pal._pal_param["SanityValue"] = PalObjects.FloatProperty(1.0)
        pal.Hp = 1
        pal.FullStomach = 1.0
        pal._pal_param["WorkerSick"] = PalObjects.EnumProperty(
            "EPalBaseCampWorkerSickType",
            "EPalBaseCampWorkerSickType::DepressionSprain",
        )
        manager = self.session.manager
        manager.player_mapping = {
            "owner": SimpleNamespace(_palbox={str(pal.InstanceId): pal})
        }
        manager.baseworker_mapping = {}
        manager._dangling_pals = {}

        response = self.client.post(
            "/api/save/pals/commands",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 0,
                "command": "heal_all_pals",
            },
        )

        self.assertEqual(200, response.status_code, response.get_json())
        payload = response.get_json()["data"]
        self.assertEqual(1, payload["revision"])
        self.assertEqual(1, payload["value"]["healed_count"])
        self.assertEqual(1, payload["value"]["condition"]["fully_healed"])
        self.assertEqual(pal.ComputedMaxHP, pal.Hp)
        self.assertEqual(
            DataProvider.get_pal_stats(pal.DataAccessKey, "FOOD"),
            pal.FullStomach,
        )
        self.assertEqual(100.0, pal.SanityValue)
        self.assertEqual(1, self.session.revision)

    def test_unlock_all_expedition_pals_is_a_whole_save_command(self) -> None:
        expedition_id = "44444444-5555-6666-7777-888888888888"
        pal = PalEntity(
            PalObjects.PalSaveParameter(
                toUUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"),
                toUUID("11111111-2222-3333-4444-555555555555"),
                toUUID("22222222-3333-4444-5555-666666666666"),
                0,
                toUUID("33333333-4444-5555-6666-777777777777"),
            )
        )
        pal._pal_param[
            "MapObjectConcreteInstanceIdAssignedToExpedition"
        ] = PalObjects.Guid(expedition_id)
        manager = self.session.manager
        manager.player_mapping = {
            "owner": SimpleNamespace(_palbox={str(pal.InstanceId): pal})
        }
        manager.baseworker_mapping = {}
        manager._dangling_pals = {}
        manager.expedition_has_member = lambda _expedition_id, _pal_id: False

        response = self.client.post(
            "/api/save/pals/commands",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 0,
                "command": "unlock_all_expedition_pals",
            },
        )

        self.assertEqual(200, response.status_code, response.get_json())
        payload = response.get_json()["data"]
        self.assertEqual(1, payload["revision"])
        self.assertEqual(1, payload["value"]["unlocked_count"])
        self.assertEqual(0, payload["value"]["reverse_member_count"])
        self.assertFalse(pal.IsExpeditionPal)
        self.assertEqual(1, self.session.revision)

    def test_korean_is_exposed_and_accepted_by_save_i18n_endpoints(self) -> None:
        from palworld_pal_editor.config import Config

        response = self.client.get("/api/save/fetch_config")
        self.assertEqual(200, response.status_code)
        self.assertEqual("한국어", response.get_json()["data"]["I18nList"]["ko"])
        self.assertEqual(10, response.get_json()["data"]["MaxSuitabilityLevel"])

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

    def test_refresh_requests_an_explicit_revision_bound_reload(self) -> None:
        with patch.object(
            SESSION_RUNTIME,
            "reload",
            return_value=(self.session, 2),
        ) as reload_session:
            response = self.client.post(
                "/api/save/reload",
                json={
                    "session_id": self.session.session_id,
                    "expected_revision": 0,
                    "discard_changes": True,
                },
                headers=self.headers,
            )

        self.assertEqual(200, response.status_code, response.get_json())
        reload_session.assert_called_once_with(
            self.session.session_id,
            0,
            discard_changes=True,
        )
        payload = response.get_json()["data"]
        self.assertEqual(2, payload["discarded_change_count"])
        self.assertEqual(
            self.session.session_id,
            payload["session"]["session_id"],
        )

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

    def test_local_web_directory_picker_uses_the_native_system_dialog(self) -> None:
        with TemporaryDirectory() as temp, patch(
            "palworld_pal_editor.api.save._select_native_directory",
            return_value=temp,
        ) as select_directory:
            response = self.client.post(
                "/api/save/select-directory",
                json={"path": temp},
                headers=self.headers,
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual(
            {
                "path": str(Path(temp).resolve()),
                "cancelled": False,
            },
            response.get_json()["data"],
        )
        select_directory.assert_called_once_with(str(Path(temp).resolve()))

    def test_local_web_directory_picker_preserves_native_cancellation(self) -> None:
        with patch(
            "palworld_pal_editor.api.save._select_native_directory",
            return_value=None,
        ):
            response = self.client.post(
                "/api/save/select-directory",
                json={},
                headers=self.headers,
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual(
            {"path": None, "cancelled": True},
            response.get_json()["data"],
        )

    def test_remote_web_client_cannot_open_a_dialog_on_the_server(self) -> None:
        with patch(
            "palworld_pal_editor.api.save._select_native_directory",
        ) as select_directory:
            response = self.client.post(
                "/api/save/select-directory",
                json={},
                headers=self.headers,
                environ_base={"REMOTE_ADDR": "192.0.2.10"},
            )

        self.assertEqual(403, response.status_code)
        self.assertEqual(
            "NATIVE_DIALOG_LOCAL_ONLY",
            response.get_json()["error"]["code"],
        )
        select_directory.assert_not_called()

    def test_local_web_directory_picker_reports_system_api_failure(self) -> None:
        with patch(
            "palworld_pal_editor.api.save._select_native_directory",
            side_effect=OSError("injected native picker failure"),
        ):
            response = self.client.post(
                "/api/save/select-directory",
                json={},
                headers=self.headers,
            )

        self.assertEqual(503, response.status_code)
        self.assertEqual(
            "NATIVE_DIALOG_UNAVAILABLE",
            response.get_json()["error"]["code"],
        )

    def test_query_and_performance_endpoints_are_session_scoped(self) -> None:
        response = self.client.get(
            f"/api/save/query/players?session_id={self.session.session_id}",
            headers=self.headers,
        )
        self.assertEqual(200, response.status_code)
        self.assertEqual([], response.get_json()["data"]["players"])

        response = self.client.get(
            f"/api/save/query/overview?session_id={self.session.session_id}",
            headers=self.headers,
        )
        self.assertEqual(200, response.status_code)
        self.assertEqual(0, response.get_json()["data"]["totals"]["pals"])
        self.assertEqual(0, response.get_json()["data"]["anomalies"]["pal_count"])

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
