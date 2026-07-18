from __future__ import annotations

import unittest

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from palworld_pal_editor.api.player import player_blueprint
from palworld_pal_editor.application.runtime import SESSION_RUNTIME
from tests.unit.test_dynamic_item_data import make_editor


class DynamicAttributeApiTests(unittest.TestCase):
    def setUp(self) -> None:
        _inventory, self.session, self.manager, self.container_id = make_editor()
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

    def test_read_and_update_expose_only_verified_public_fields(self) -> None:
        response = self.client.get(
            "/api/player/player-dynamic/inventory/COMMON/0/dynamic"
            f"?session_id={self.session.session_id}",
            headers=self.headers,
        )
        self.assertEqual(200, response.status_code)
        data = response.get_json()["data"]
        self.assertEqual("weapon", data["dynamic_kind"])
        self.assertIn("durability", data["writable_fields"])
        container = self.manager.item_container_data.get(self.container_id)
        slot = container.get_occupied(0)
        updated = self.client.post(
            "/api/player/player-dynamic/inventory/commands",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 0,
                "command": "update_dynamic_attributes",
                "container_type": "COMMON",
                "slot_index": 0,
                "expected_static_id": slot.static_id,
                "expected_dynamic_id": slot.dynamic_id,
                "values": {"durability": 91.5, "ammo": 7},
            },
        )
        self.assertEqual(200, updated.status_code)
        attributes = updated.get_json()["data"]["dynamic_item"]["attributes"]
        self.assertEqual(91.5, attributes["durability"])
        self.assertEqual(7, attributes["ammo"])
        self.assertEqual(1, self.session.revision)


if __name__ == "__main__":
    unittest.main()
