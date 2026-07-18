from __future__ import annotations

import unittest
from unittest.mock import patch

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from palworld_pal_editor.api.batch import batch_blueprint
from palworld_pal_editor.application.runtime import SESSION_RUNTIME
from palworld_pal_editor.domain.item_catalog import ItemCatalog

from tests.unit import test_inventory_read as inventory_fixtures


class BatchApiTests(unittest.TestCase):
    def setUp(self) -> None:
        inventory, ids, manager = (
            inventory_fixtures.InventoryReadTests().make_editor()
        )
        self.session = inventory._session
        self.ids = ids
        self.manager = manager
        SESSION_RUNTIME.replace_for_tests(self.session)

        app = Flask(__name__)
        app.config.update(
            JWT_SECRET_KEY="test-secret-key-that-is-at-least-32-bytes",
            TESTING=True,
        )
        JWTManager(app)
        app.register_blueprint(batch_blueprint, url_prefix="/api/batch")
        with app.app_context():
            token = create_access_token(identity="test-user")
        self.client = app.test_client()
        self.headers = {"Authorization": f"Bearer {token}"}

    def tearDown(self) -> None:
        SESSION_RUNTIME.replace_for_tests(None)

    def operations(self):
        return [
            {
                "resource": "inventory",
                "command": "update_item_count",
                "player_id": "player-a",
                "container_type": "COMMON",
                "slot_index": 1,
                "expected_static_id": "Stone",
                "count": 10,
            },
            {
                "resource": "inventory",
                "command": "put_item",
                "player_id": "player-a",
                "container_type": "COMMON",
                "slot_index": 0,
                "static_id": "Stone",
                "count": 20,
            },
        ]

    def test_preview_and_atomic_execute_use_one_revision(self) -> None:
        payload = {
            "session_id": self.session.session_id,
            "expected_revision": 0,
            "operations": self.operations(),
        }
        preview = self.client.post(
            "/api/batch/preview", headers=self.headers, json=payload
        )
        self.assertEqual(200, preview.status_code)
        self.assertEqual(
            "all_or_nothing",
            preview.get_json()["data"]["impact"]["atomicity"],
        )
        payload["impact_token"] = preview.get_json()["data"]["impact_token"]
        with patch.object(
            ItemCatalog, "load_default", return_value=inventory_fixtures.catalog()
        ):
            response = self.client.post(
                "/api/batch/commands", headers=self.headers, json=payload
            )
        self.assertEqual(200, response.status_code)
        self.assertEqual(1, response.get_json()["data"]["revision"])
        self.assertEqual(1, len(self.session.changes()))

    def test_raw_container_id_and_stale_preview_are_rejected(self) -> None:
        operations = self.operations()
        operations[0]["container_id"] = str(self.ids["CommonContainerId"])
        response = self.client.post(
            "/api/batch/preview",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 0,
                "operations": operations,
            },
        )
        self.assertEqual(400, response.status_code)
        self.assertEqual(
            "UNSUPPORTED_COMMAND_FIELD", response.get_json()["error"]["code"]
        )


if __name__ == "__main__":
    unittest.main()
