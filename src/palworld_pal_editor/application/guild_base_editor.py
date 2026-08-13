from __future__ import annotations

from typing import Any

from palworld_pal_editor.domain.commands import UpdateGuildBaseCampLevel
from palworld_pal_editor.domain.errors import DomainError

from .save_session import SaveSession


MAX_GUILD_BASE_CAMP_LEVEL = 35


class GuildBaseEditor:
    """Revision-bound guild terminal level writes within official limits."""

    def __init__(self, session: SaveSession) -> None:
        self._session = session

    def execute(self, command: UpdateGuildBaseCampLevel) -> dict[str, Any]:
        if isinstance(command, UpdateGuildBaseCampLevel):
            return self._update_level(command)
        raise DomainError(
            code="UNSUPPORTED_COMMAND",
            message="Unsupported guild base command.",
            http_status=400,
        )

    def _update_level(
        self, command: UpdateGuildBaseCampLevel
    ) -> dict[str, Any]:
        self._validate_level(command.level)
        group = self._require_group(command.guild_id)
        current_level = group.base_camp_level
        if current_level is None:
            raise DomainError(
                code="COMPATIBILITY_FIELD_MISSING",
                message="This save does not expose a writable base camp level.",
                field="level",
                details={"guild_id": str(command.guild_id)},
                http_status=409,
            )
        lowering = command.level < current_level
        if lowering and command.confirm_lowering is not True:
            raise DomainError(
                code="BASE_CAMP_LEVEL_LOWER_CONFIRMATION_REQUIRED",
                message=(
                    "Lowering the base camp level may affect Pals stored in "
                    "or assigned through the Palbox. Explicit confirmation "
                    "is required."
                ),
                field="confirm_base_camp_level_lowering",
                details={
                    "current_level": current_level,
                    "target_level": command.level,
                },
                retryable=True,
                http_status=409,
            )
        value = lambda: {
            "guild_id": str(group.group_id),
            "level": group.base_camp_level,
        }
        if command.level == current_level:
            self._session.require_command(
                command.session_id, command.expected_revision
            )
            return {
                "revision": self._session.revision,
                "change_id": None,
                "value": value(),
            }

        try:
            entry = self._session.apply_atomic(
                session_id=command.session_id,
                expected_revision=command.expected_revision,
                command="UpdateGuildBaseCampLevel",
                target={"guild_id": str(group.group_id)},
                snapshot=group.snapshot,
                restore=group.restore,
                before=value,
                mutate=lambda: group.set_base_camp_level(command.level),
                validate=lambda: self._validate_level_postcondition(
                    group, command.level
                ),
                after=value,
                affected_records=("level:GroupSaveDataMap",),
            )
        except DomainError:
            raise
        except Exception as error:
            raise DomainError(
                code="BASE_CAMP_LEVEL_UPDATE_FAILED",
                message="The base camp level could not be updated safely.",
                details={"error_type": type(error).__name__},
                http_status=409,
            ) from error
        return {
            "revision": entry.revision_after,
            "change_id": entry.change_id,
            "value": value(),
        }

    def _require_group(self, guild_id: str):
        group_data = getattr(self._session.manager, "group_data", None)
        group = group_data.get_group(guild_id) if group_data is not None else None
        if group is None:
            raise DomainError(
                code="GUILD_NOT_FOUND",
                message="Guild not found.",
                field="guild_id",
                details={"guild_id": str(guild_id)},
                http_status=404,
            )
        return group

    @staticmethod
    def _validate_level(level: int) -> None:
        if isinstance(level, bool) or not isinstance(level, int):
            raise DomainError(
                code="INVALID_FIELD_TYPE",
                message="level must be an integer.",
                field="level",
                http_status=400,
            )
        if level < 1 or level > MAX_GUILD_BASE_CAMP_LEVEL:
            raise DomainError(
                code="INVALID_BASE_CAMP_LEVEL",
                message=(
                    "Base camp level must be between 1 and "
                    f"{MAX_GUILD_BASE_CAMP_LEVEL}."
                ),
                field="level",
                details={"maximum": MAX_GUILD_BASE_CAMP_LEVEL},
                http_status=400,
            )

    @staticmethod
    def _validate_level_postcondition(group, expected_level: int) -> None:
        if group.base_camp_level != expected_level:
            raise DomainError(
                code="COMMAND_POSTCONDITION_FAILED",
                message="The base camp level did not update as requested.",
                http_status=409,
            )
