from __future__ import annotations

from palworld_pal_editor.domain.commands import CompleteActiveExpeditions
from palworld_pal_editor.domain.errors import DomainError

from .save_session import SaveSession


class ExpeditionEditor:
    """Atomically request normal in-game settlement of active expeditions."""

    def __init__(self, session: SaveSession) -> None:
        self._session = session

    def execute(self, command: CompleteActiveExpeditions) -> dict:
        self._session.require_command(
            command.session_id, command.expected_revision
        )
        targets = self._session.manager.completable_expeditions()
        if not targets:
            raise DomainError(
                code="NO_ACTIVE_EXPEDITIONS",
                message="No active expedition can be completed safely.",
                http_status=409,
            )
        expedition_ids = tuple(
            target["expedition_id"] for target in targets
        )
        completed_ids: list[str] = []

        def summarize() -> dict:
            values = self._session.manager.expedition_completion_state(
                expedition_ids
            )
            return {"expeditions": values, "count": len(values)}

        def mutate() -> None:
            completed_ids.extend(
                self._session.manager.complete_active_expeditions()
            )

        def validate() -> None:
            if set(completed_ids) != set(expedition_ids):
                raise DomainError(
                    code="EXPEDITION_POSTCONDITION_FAILED",
                    message="Not every active expedition was updated.",
                    http_status=409,
                )
            state = self._session.manager.expedition_completion_state(
                expedition_ids
            )
            if len(state) != len(expedition_ids) or any(
                value["start_time"] != 1
                or value["state"] != 2
                or value["can_complete"]
                for value in state
            ):
                raise DomainError(
                    code="EXPEDITION_POSTCONDITION_FAILED",
                    message="The expedition timer update could not be verified.",
                    http_status=409,
                )

        try:
            entry = self._session.apply_atomic(
                session_id=command.session_id,
                expected_revision=command.expected_revision,
                command="CompleteActiveExpeditions",
                target={"expedition_ids": list(expedition_ids)},
                snapshot=self._session.manager.snapshot_expedition_data,
                restore=self._session.manager.restore_expedition_data,
                before=summarize,
                mutate=mutate,
                validate=validate,
                after=summarize,
                affected_records=("level:MapObjectSaveData",),
            )
        except DomainError:
            raise
        except Exception as error:
            raise DomainError(
                code="EXPEDITION_UPDATE_FAILED",
                message="The active expeditions could not be updated safely.",
                details={"error_type": type(error).__name__},
                http_status=409,
            ) from error

        return {
            "revision": entry.revision_after,
            "change_id": entry.change_id,
            "value": {
                "completed_count": len(completed_ids),
                "expedition_ids": completed_ids,
                "settlement": "on_next_game_load",
            },
        }
