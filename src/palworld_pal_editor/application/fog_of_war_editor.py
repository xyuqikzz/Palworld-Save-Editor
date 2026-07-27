from __future__ import annotations

from typing import Any

from palworld_pal_editor.domain.commands import ClearFogOfWar, ResetFogOfWar
from palworld_pal_editor.domain.errors import DomainError

from .local_data import FOG_CLEAR_CONFIRMATION, FOG_RESET_CONFIRMATION
from .save_session import SaveSession


class FogOfWarEditor:
    """Revision-bound mutation of LocalData.sav exploration masks only."""

    def __init__(self, session: SaveSession) -> None:
        self._session = session

    def execute(
        self,
        command: ClearFogOfWar | ResetFogOfWar,
    ) -> dict[str, Any]:
        if isinstance(command, ClearFogOfWar):
            required_confirmation = FOG_CLEAR_CONFIRMATION
            confirmation_code = "FOG_OF_WAR_CLEAR_CONFIRMATION_REQUIRED"
            confirmation_message = (
                "Explicit confirmation is required before clearing fog and "
                "revealing the full map."
            )
            command_name = "ClearFogOfWar"
            failure_code = "FOG_OF_WAR_CLEAR_FAILED"
            failure_message = "The fog-of-war masks could not be cleared safely."
            operation = "clear"
        elif isinstance(command, ResetFogOfWar):
            required_confirmation = FOG_RESET_CONFIRMATION
            confirmation_code = "FOG_OF_WAR_CONFIRMATION_REQUIRED"
            confirmation_message = (
                "Explicit confirmation is required before re-covering "
                "unexplored areas with fog."
            )
            command_name = "ResetFogOfWar"
            failure_code = "FOG_OF_WAR_RESET_FAILED"
            failure_message = "The fog-of-war masks could not be reset safely."
            operation = "reset"
        else:
            raise DomainError(
                code="UNSUPPORTED_COMMAND",
                message="Unsupported fog-of-war command.",
                http_status=400,
            )

        if command.confirmation != required_confirmation:
            raise DomainError(
                code=confirmation_code,
                message=confirmation_message,
                field="confirmation",
                details={"required": required_confirmation},
                http_status=400,
            )

        self._session.require_local_data_selected()
        document = self._session.local_data
        document.require_resettable()
        no_change = (
            document.is_fully_cleared()
            if operation == "clear"
            else document.is_fully_unexplored()
        )
        if no_change:
            self._session.require_command(
                command.session_id,
                command.expected_revision,
            )
            return {
                "revision": self._session.revision,
                "change_id": None,
                "changed": False,
                "value": document.mask_summary(),
            }

        mutate = (
            document.clear_fog_of_war
            if operation == "clear"
            else document.reset_fog_of_war
        )
        validate = (
            document.validate_clear
            if operation == "clear"
            else document.validate_reset
        )
        try:
            entry = self._session.apply_atomic(
                session_id=command.session_id,
                expected_revision=command.expected_revision,
                command=command_name,
                target={
                    "record": "local_data",
                    "scope": "exploration_mask_only",
                },
                snapshot=document.snapshot_masks,
                restore=document.restore_masks,
                before=document.mask_summary,
                mutate=mutate,
                validate=validate,
                after=document.mask_summary,
                affected_records=("local_data",),
            )
        except DomainError:
            raise
        except Exception as error:
            raise DomainError(
                code=failure_code,
                message=failure_message,
                details={"error_type": type(error).__name__},
                http_status=409,
            ) from error
        return {
            "revision": entry.revision_after,
            "change_id": entry.change_id,
            "changed": True,
            "value": document.mask_summary(),
        }
