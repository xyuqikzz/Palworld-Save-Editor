from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch

from palworld_pal_editor.application.runtime import SessionRuntime
from palworld_pal_editor.domain.errors import DomainError


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


if __name__ == "__main__":
    unittest.main()
