from __future__ import annotations

from typing import Any

from palworld_pal_editor.domain.commands import UnlockAllFastTravelPoints
from palworld_pal_editor.domain.errors import DomainError

from .fast_travel import FastTravelCapability, PlayerFastTravelData
from .save_session import SaveSession


FAST_TRAVEL_UNLOCK_CONFIRMATION = "解锁所有传送点"


class FastTravelEditor:
    """Revision-bound mutation of one player's fast-travel flags only."""

    def __init__(self, session: SaveSession) -> None:
        self._session = session

    def capability(self, player_id: str) -> FastTravelCapability:
        player = self._session.load_player(player_id)
        return PlayerFastTravelData.from_player(player).capability

    def execute(self, command: UnlockAllFastTravelPoints) -> dict[str, Any]:
        if not isinstance(command, UnlockAllFastTravelPoints):
            raise DomainError(
                code="UNSUPPORTED_COMMAND",
                message="Unsupported fast-travel command.",
                http_status=400,
            )
        if command.confirmation != FAST_TRAVEL_UNLOCK_CONFIRMATION:
            raise DomainError(
                code="FAST_TRAVEL_CONFIRMATION_REQUIRED",
                message="Explicit confirmation is required to unlock all fast-travel points.",
                field="confirmation",
                details={"required": FAST_TRAVEL_UNLOCK_CONFIRMATION},
                http_status=400,
            )
        self._session.require_command(
            command.session_id,
            command.expected_revision,
        )
        player = self._session.load_player(command.player_id)
        document = PlayerFastTravelData.from_player(player)
        document.require_unlockable()
        if document.is_all_unlocked():
            return {
                "revision": self._session.revision,
                "change_id": None,
                "changed": False,
                "value": document.summary(),
            }

        outside_before = document.properties_without_flags()
        non_catalog_before = document.non_catalog_entries()
        try:
            entry = self._session.apply_atomic(
                session_id=command.session_id,
                expected_revision=command.expected_revision,
                command="UnlockAllFastTravelPoints",
                target={
                    "player_id": str(player.PlayerUId),
                    "field": "RecordData.FastTravelPointUnlockFlag",
                },
                snapshot=document.snapshot,
                restore=document.restore,
                before=document.summary,
                mutate=document.unlock_all,
                validate=lambda: self._validate(
                    document,
                    outside_before,
                    non_catalog_before,
                ),
                after=document.summary,
                affected_records=(f"player_file:{player.PlayerUId}",),
            )
        except DomainError:
            raise
        except Exception as error:
            raise DomainError(
                code="FAST_TRAVEL_UNLOCK_FAILED",
                message="The player's fast-travel points could not be unlocked safely.",
                details={"error_type": type(error).__name__},
                http_status=409,
            ) from error
        return {
            "revision": entry.revision_after,
            "change_id": entry.change_id,
            "changed": True,
            "value": document.summary(),
        }

    @staticmethod
    def _validate(
        document: PlayerFastTravelData,
        outside_before: dict[str, Any],
        non_catalog_before: list[dict[str, Any]],
    ) -> None:
        document.validate_all_unlocked()
        if document.non_catalog_entries() != non_catalog_before:
            raise DomainError(
                code="FAST_TRAVEL_UNRELATED_FLAGS_CHANGED",
                message="A non-fast-travel map unlock flag changed unexpectedly.",
                http_status=409,
            )
        if document.properties_without_flags() != outside_before:
            raise DomainError(
                code="FAST_TRAVEL_OUTSIDE_FIELD_CHANGED",
                message="A field outside fast-travel progress changed unexpectedly.",
                http_status=409,
            )
