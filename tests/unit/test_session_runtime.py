from __future__ import annotations

from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from palworld_pal_editor.application.runtime import SessionRuntime
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.domain.models import SavePlatform, SaveSource
import palworld_pal_editor.storage.xgp as xgp_module


class _Session:
    def __init__(self, session_id: str, source: str, *, dirty: bool = False) -> None:
        self.session_id = session_id
        self.source = Path(source).resolve()
        self._dirty = dirty
        self.revision = 1 if dirty else 0

    def changes(self):
        return [{"change": True}] if self._dirty else []

    def require_command(self, session_id: str, expected_revision: int) -> None:
        if session_id != self.session_id:
            raise DomainError("SESSION_NOT_FOUND", "session not found", http_status=404)
        if expected_revision != self.revision:
            raise DomainError("STALE_REVISION", "stale revision", http_status=409)


class SessionRuntimeTests(unittest.TestCase):
    def test_current_session_is_addressable_by_default_and_id(self) -> None:
        runtime = SessionRuntime()
        current = _Session("current", "save-a")

        with patch(
            "palworld_pal_editor.application.runtime.SaveSession.open",
            return_value=current,
        ):
            self.assertIs(current, runtime.open("save-a"))

        self.assertIs(current, runtime.get())
        self.assertIs(current, runtime.get("current"))
        with self.assertRaises(DomainError) as missing:
            runtime.get("missing")
        self.assertEqual("SESSION_NOT_FOUND", missing.exception.code)

    def test_dirty_current_session_blocks_reopen(self) -> None:
        runtime = SessionRuntime()
        runtime.replace_for_tests(_Session("current", "save-a", dirty=True))

        with self.assertRaises(DomainError) as unsaved:
            runtime.open("save-b")
        self.assertEqual("UNSAVED_CHANGES_PRESENT", unsaved.exception.code)

    def test_dirty_current_session_resumes_when_reopening_same_source(self) -> None:
        runtime = SessionRuntime()
        current = _Session("current", "save-a", dirty=True)
        runtime.replace_for_tests(current)

        with patch(
            "palworld_pal_editor.application.runtime.SaveSession.open"
        ) as open_session:
            resumed = runtime.open("save-a")

        self.assertIs(current, resumed)
        open_session.assert_not_called()

    def test_dirty_session_requires_explicit_discard_before_close(self) -> None:
        runtime = SessionRuntime()
        current = _Session("current", "save-a", dirty=True)
        runtime.replace_for_tests(current)

        with self.assertRaises(DomainError) as unsaved:
            runtime.close("current", 1)
        self.assertEqual("UNSAVED_CHANGES_PRESENT", unsaved.exception.code)
        self.assertIs(current, runtime.get())

        result = runtime.close("current", 1, discard_changes=True)
        self.assertEqual(1, result["discarded_change_count"])
        with self.assertRaises(DomainError) as missing:
            runtime.get()
        self.assertEqual("SESSION_NOT_FOUND", missing.exception.code)

        reopened = _Session("reopened", "save-b")
        with patch(
            "palworld_pal_editor.application.runtime.SaveSession.open",
            return_value=reopened,
        ):
            self.assertIs(reopened, runtime.open("save-b"))

    def test_clean_session_closes_without_discard_confirmation(self) -> None:
        runtime = SessionRuntime()
        runtime.replace_for_tests(_Session("current", "save-a"))

        result = runtime.close("current", 0)

        self.assertEqual(0, result["discarded_change_count"])
        with self.assertRaises(DomainError):
            runtime.get()

    def test_dirty_steam_discard_then_xgp_open_does_not_depend_on_tasklist(self) -> None:
        source = SaveSource(
            platform=SavePlatform.XGP,
            canonical_path=Path("xgp-save").resolve(),
            source_id="xgp-source",
            display_name="Game Pass test save",
            world_id="A" * 32,
        )
        runtime = SessionRuntime(
            source_catalog=SimpleNamespace(resolve=lambda _source_id: source)
        )
        runtime.replace_for_tests(_Session("steam", "steam-save", dirty=True))
        runtime.close("steam", 1, discard_changes=True)

        def open_storage(_source, storage):
            storage._ensure_game_stopped()
            return _Session("xgp", "xgp-save")

        with (
            patch(
                "palworld_pal_editor.application.runtime.SaveSession.open_storage",
                side_effect=open_storage,
            ),
            patch.object(xgp_module.sys, "platform", "win32"),
            patch.object(
                subprocess,
                "run",
                side_effect=OSError("tasklist unavailable"),
            ),
            patch.object(
                xgp_module,
                "_windows_process_names",
                return_value=("explorer.exe",),
                create=True,
            ),
        ):
            opened = runtime.open_source("xgp-source")

        self.assertEqual("xgp", opened.session_id)


if __name__ == "__main__":
    unittest.main()
