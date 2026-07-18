from __future__ import annotations

from pathlib import Path
from threading import RLock

from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.domain.errors import DomainError


class SessionRuntime:
    """The currently open save session."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._current: SaveSession | None = None
        self._sessions: dict[str, SaveSession] = {}

    def open(self, source: str | Path) -> SaveSession:
        with self._lock:
            if self._current is not None and self._current.changes():
                raise DomainError(
                    code="UNSAVED_CHANGES_PRESENT",
                    message="Save or discard the current changes before opening another save.",
                    http_status=409,
                )
        candidate = SaveSession.open(source)
        with self._lock:
            if self._current is not None:
                self._sessions.pop(self._current.session_id, None)
            self._current = candidate
            self._sessions[candidate.session_id] = candidate
            return candidate

    def get(self, session_id: str | None = None) -> SaveSession:
        with self._lock:
            session = (
                self._current
                if session_id is None
                else self._sessions.get(session_id)
            )
        if session is None:
            raise DomainError(
                code="SESSION_NOT_FOUND",
                message="No matching save session is open.",
                field="session_id",
                http_status=404,
            )
        return session

    def close(
        self,
        session_id: str,
        expected_revision: int,
        *,
        discard_changes: bool = False,
    ) -> dict[str, int | str]:
        """Close the active session, explicitly discarding in-memory changes."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session is not self._current:
                raise DomainError(
                    code="SESSION_NOT_FOUND",
                    message="No matching save session is open.",
                    field="session_id",
                    http_status=404,
                )
            if not isinstance(discard_changes, bool):
                raise DomainError(
                    code="INVALID_REQUEST",
                    message="discard_changes must be a boolean.",
                    field="discard_changes",
                    http_status=400,
                )

            session.require_command(session_id, expected_revision)
            pending_change_count = len(session.changes())
            if pending_change_count and not discard_changes:
                raise DomainError(
                    code="UNSAVED_CHANGES_PRESENT",
                    message=(
                        "Confirm that the current changes should be discarded "
                        "before closing the save."
                    ),
                    details={"pending_change_count": pending_change_count},
                    http_status=409,
                )

            self._sessions.pop(session_id, None)
            self._current = None
            return {
                "session_id": session_id,
                "discarded_change_count": pending_change_count,
            }

    def replace_for_tests(self, session: SaveSession | None) -> None:
        with self._lock:
            self._current = session
            self._sessions = (
                {session.session_id: session} if session is not None else {}
            )


SESSION_RUNTIME = SessionRuntime()
