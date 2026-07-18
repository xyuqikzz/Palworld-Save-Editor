from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from palworld_pal_editor.api.player import player_blueprint
from palworld_pal_editor.application.runtime import SESSION_RUNTIME
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.core.item_container_data import ItemContainerData
from palworld_pal_editor.core.pal_objects import PalObjects, toUUID
from palworld_pal_editor.domain.item_catalog import ItemCatalog
from palworld_pal_editor.domain.models import ItemCatalogEntry, ItemContainerType


class _Player:
    PlayerUId = "player-a"
    InstanceId = "instance-a"
    NickName = "Player A"
    Level = 10

    def __init__(self, container_id) -> None:
        self._container_id = container_id
        self._player_save_data = {"InventoryInfo": {"value": {"synthetic": True}}}

    def resolve_item_container_ids(self):
        return {"CommonContainerId": self._container_id}


def _catalog() -> ItemCatalog:
    return ItemCatalog(
        [
            ItemCatalogEntry(
                static_id="Stone",
                names={"en": "Stone"},
                descriptions={"en": "A stone"},
                category="material",
                rarity=0,
                icon="stone",
                max_stack=9999,
                allowed_containers=(ItemContainerType.COMMON,),
                dynamic_kind="none",
                rule_status="verified",
                rule_source="synthetic-test",
                rule_version="fixture-v1",
            )
        ]
    )


class InventoryApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.container_id = toUUID("11111111-2222-3333-4444-555555555555")
        zero = toUUID("00000000-0000-0000-0000-000000000000")
        self.raw = {
            "slot_index": 0,
            "count": 5,
            "item": {
                "static_id": "Stone",
                "dynamic_id": {
                    "created_world_id": zero,
                    "local_id_in_created_world": zero,
                },
            },
            "trailing_bytes": [1, 2, 3],
        }
        self.empty_raw = {
            "slot_index": 1,
            "count": 0,
            "item": {
                "static_id": "None",
                "dynamic_id": {
                    "created_world_id": zero,
                    "local_id_in_created_world": zero,
                },
            },
            "trailing_bytes": [4, 5, 6],
        }
        spare_empty = {
            "slot_index": 2,
            "count": 0,
            "item": {
                "static_id": "None",
                "dynamic_id": {
                    "created_world_id": zero,
                    "local_id_in_created_world": zero,
                },
            },
            "trailing_bytes": [7, 8, 9],
        }
        gvas = SimpleNamespace(
            properties={
                "worldSaveData": {
                    "value": {
                        "ItemContainerSaveData": {
                            "value": [
                                {
                                    "key": {"ID": PalObjects.Guid(self.container_id)},
                                    "value": {
                                        "SlotNum": PalObjects.IntProperty(3),
                                        "Slots": {
                                            "value": {
                                                "values": [
                                                    {"RawData": {"value": self.raw}},
                                                    {"RawData": {"value": self.empty_raw}},
                                                    {"RawData": {"value": spare_empty}},
                                                ]
                                            }
                                        },
                                    },
                                }
                            ]
                        }
                    }
                }
            },
            header=None,
        )
        player = _Player(self.container_id)
        manager = SimpleNamespace(
            gvas_file=gvas,
            player_mapping={"player-a": player},
            item_container_data=ItemContainerData(gvas),
            get_player=lambda player_id: player if player_id == "player-a" else None,
        )
        self.session = SaveSession.from_loaded_manager(manager, Path("synthetic-save"))
        SESSION_RUNTIME.replace_for_tests(self.session)

        app = Flask(__name__)
        app.config.update(
            JWT_SECRET_KEY="test-secret-key-that-is-at-least-32-bytes",
            TESTING=True,
        )
        JWTManager(app)
        app.register_blueprint(player_blueprint, url_prefix="/api/player")
        with app.app_context():
            token = create_access_token(identity="test-user")
        self.client = app.test_client()
        self.headers = {"Authorization": f"Bearer {token}"}

    def tearDown(self) -> None:
        SESSION_RUNTIME.replace_for_tests(None)

    def test_read_and_update_use_domain_contract(self) -> None:
        with patch.object(ItemCatalog, "load_default", return_value=_catalog()):
            response = self.client.get(
                "/api/player/player-a/inventory", headers=self.headers
            )
            self.assertEqual(200, response.status_code)
            self.assertNotIn(str(self.container_id), str(response.get_json()))

            response = self.client.post(
                "/api/player/player-a/inventory/commands",
                headers=self.headers,
                json={
                    "session_id": self.session.session_id,
                    "expected_revision": 0,
                    "command": "update_item_count",
                    "container_type": "COMMON",
                    "slot_index": 0,
                    "expected_static_id": "Stone",
                    "count": 99,
                },
            )
        self.assertEqual(200, response.status_code)
        self.assertEqual(99, self.raw["count"])
        self.assertEqual([1, 2, 3], self.raw["trailing_bytes"])
        self.assertEqual(1, response.get_json()["data"]["revision"])

        with patch.object(ItemCatalog, "load_default", return_value=_catalog()):
            response = self.client.post(
                "/api/player/player-a/inventory/commands",
                headers=self.headers,
                json={
                    "session_id": self.session.session_id,
                    "expected_revision": 1,
                    "command": "put_item",
                    "container_type": "COMMON",
                    "slot_index": 1,
                    "static_id": "Stone",
                    "count": 3,
                },
            )
        self.assertEqual(200, response.status_code)
        self.assertEqual("Stone", self.empty_raw["item"]["static_id"])

        response = self.client.post(
            "/api/player/player-a/inventory/commands",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 2,
                "command": "clear_item_slot",
                "container_type": "COMMON",
                "slot_index": 0,
                "expected_static_id": "Stone",
                "expected_dynamic_id": None,
            },
        )
        self.assertEqual(200, response.status_code)
        container = self.session.manager.item_container_data.get(self.container_id)
        self.assertTrue(container.is_empty(0))
        self.assertNotIn(0, [slot.slot_index for slot in container.iter_encoded_slots()])
        # The detached record remains intact for transaction rollback.
        self.assertEqual("Stone", self.raw["item"]["static_id"])
        self.assertEqual([1, 2, 3], self.raw["trailing_bytes"])
        self.assertEqual(3, self.session.revision)

    def test_raw_container_id_is_rejected_without_mutation(self) -> None:
        response = self.client.post(
            "/api/player/player-a/inventory/commands",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 0,
                "command": "update_item_count",
                "container_type": "COMMON",
                "container_id": str(self.container_id),
                "slot_index": 0,
                "expected_static_id": "Stone",
                "count": 99,
            },
        )
        self.assertEqual(400, response.status_code)
        self.assertEqual(
            "UNSUPPORTED_COMMAND_FIELD", response.get_json()["error"]["code"]
        )
        self.assertEqual(5, self.raw["count"])
        self.assertEqual(0, self.session.revision)

    def test_copy_paste_and_sort_layout_commands_use_revision_bound_clipboard(self) -> None:
        with patch.object(ItemCatalog, "load_default", return_value=_catalog()):
            copied = self.client.post(
                "/api/player/player-a/inventory/copy",
                headers=self.headers,
                json={
                    "session_id": self.session.session_id,
                    "expected_revision": 0,
                    "container_type": "COMMON",
                    "slot_index": 0,
                },
            )
            self.assertEqual(200, copied.status_code)
            token = copied.get_json()["data"]["clipboard_token"]
            pasted = self.client.post(
                "/api/player/player-a/inventory/layout/commands",
                headers=self.headers,
                json={
                    "session_id": self.session.session_id,
                    "expected_revision": 0,
                    "command": "paste_item_slot",
                    "container_type": "COMMON",
                    "slot_index": 1,
                    "clipboard_token": token,
                },
            )
        self.assertEqual(200, pasted.status_code)
        self.assertEqual("Stone", self.empty_raw["item"]["static_id"])
        self.assertEqual(1, self.session.revision)

        stale = self.client.post(
            "/api/player/player-a/inventory/layout/commands",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 1,
                "command": "paste_item_slot",
                "container_type": "COMMON",
                "slot_index": 2,
                "clipboard_token": token,
            },
        )
        self.assertEqual(409, stale.status_code)
        self.assertEqual("CLIPBOARD_STALE", stale.get_json()["error"]["code"])

        invalid_sort = self.client.post(
            "/api/player/player-a/inventory/layout/commands",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 1,
                "command": "sort_item_container",
                "container_type": "COMMON",
                "sort_by": "raw_payload",
                "descending": False,
            },
        )
        self.assertEqual(400, invalid_sort.status_code)
        self.assertEqual(
            "INVALID_SORT_FIELD", invalid_sort.get_json()["error"]["code"]
        )


if __name__ == "__main__":
    unittest.main()
