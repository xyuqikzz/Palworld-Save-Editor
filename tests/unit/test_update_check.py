import unittest
from unittest.mock import patch

from aiohttp import web

from palworld_pal_editor import config


class UpdateCheckTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.release_calls = 0
        app = web.Application()
        app.router.add_get("/releases/latest", self._latest_release)
        app.router.add_get("/releases/tag/1.0.0", self._release_page)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await self.site.start()
        port = self.site._server.sockets[0].getsockname()[1]
        self.base_url = f"http://127.0.0.1:{port}"

    async def asyncTearDown(self) -> None:
        await self.runner.cleanup()

    async def _latest_release(self, _request: web.Request) -> web.Response:
        self.release_calls += 1
        raise web.HTTPFound("/releases/tag/1.0.0")

    async def _release_page(self, _request: web.Request) -> web.Response:
        return web.Response(text="release")

    async def test_release_redirect_finds_update_without_rest_api(self) -> None:
        with (
            patch.object(config, "VERSION", "0.9.0"),
            patch.object(config, "GIT_HASH", "local-test"),
            patch.object(
                config,
                "PROJECT_RELEASES_URL",
                f"{self.base_url}/releases/latest",
            ),
        ):
            update = await config.get_new_version()

        self.assertEqual(
            ("1.0.0", f"{self.base_url}/releases/tag/1.0.0"),
            update,
        )
        self.assertEqual(1, self.release_calls)


if __name__ == "__main__":
    unittest.main()
