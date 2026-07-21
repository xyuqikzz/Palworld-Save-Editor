import unittest
from unittest.mock import AsyncMock, patch

from flask import Flask
from flask_jwt_extended import JWTManager

from palworld_pal_editor.api.save import save_blueprint


class UpdateApiTests(unittest.TestCase):
    def setUp(self) -> None:
        app = Flask(__name__)
        app.config.update(
            JWT_SECRET_KEY="test-secret-key-that-is-at-least-32-bytes",
            TESTING=True,
        )
        JWTManager(app)
        app.register_blueprint(save_blueprint, url_prefix="/api/save")
        self.client = app.test_client()

    def test_update_metadata_is_available_before_login(self) -> None:
        release_url = (
            "https://github.com/xyuqikzz/Palworld-Save-Editor/"
            "releases/tag/1.0.0"
        )
        with patch(
            "palworld_pal_editor.api.save.get_new_version",
            new=AsyncMock(return_value=("1.0.0", release_url)),
        ):
            response = self.client.get("/api/save/update")

        self.assertEqual(200, response.status_code)
        self.assertEqual(
            {
                "version": "1.0.0",
                "download_gh": release_url,
                "download_page": release_url,
            },
            response.get_json()["data"],
        )


if __name__ == "__main__":
    unittest.main()
