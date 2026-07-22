from __future__ import annotations

from typing import Any

from palworld_pal_editor.domain.commands import UpdateGuildName
from palworld_pal_editor.domain.errors import DomainError

from .save_session import SaveSession


MAX_GUILD_NAME_LENGTH = 24


class GuildEditor:
    """Revision-bound guild mutations against the loaded Level.sav model."""

    def __init__(self, session: SaveSession) -> None:
        self._session = session

    def execute(self, command: UpdateGuildName) -> dict[str, Any]:
        if not isinstance(command, UpdateGuildName):
            raise DomainError(
                code="UNSUPPORTED_COMMAND",
                message="Unsupported guild command.",
                http_status=400,
            )
        self._validate_name(command.name)
        group = self._require_group(command.guild_id)
        current_name = group._group_param.get("guild_name")
        if not isinstance(current_name, str):
            raise DomainError(
                code="COMPATIBILITY_FIELD_MISSING",
                message="This save does not expose a writable guild name field.",
                field="name",
                details={"guild_id": str(command.guild_id)},
                http_status=409,
            )
        value = lambda: {
            "guild_id": str(group.group_id),
            "name": str(group.guild_name or ""),
        }
        if current_name == command.name:
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
                command="UpdateGuildName",
                target={"guild_id": str(group.group_id)},
                snapshot=group.snapshot,
                restore=group.restore,
                before=value,
                mutate=lambda: group.set_guild_name(command.name),
                validate=lambda: self._validate_postcondition(group, command.name),
                after=value,
                affected_records=("level:GroupSaveDataMap",),
            )
        except DomainError:
            raise
        except Exception as error:
            raise DomainError(
                code="GUILD_UPDATE_FAILED",
                message="The guild name could not be updated safely.",
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
    def _validate_name(name: str) -> None:
        if not isinstance(name, str):
            raise DomainError(
                code="INVALID_FIELD_TYPE",
                message="name must be a string.",
                field="name",
                http_status=400,
            )
        if (
            not name.strip()
            or len(name) > MAX_GUILD_NAME_LENGTH
            or any(ord(character) < 32 or ord(character) == 127 for character in name)
        ):
            raise DomainError(
                code="INVALID_GUILD_NAME",
                message="Guild names must contain visible text, be at most 24 characters, and contain no control characters.",
                field="name",
                http_status=400,
            )

    @staticmethod
    def _validate_postcondition(group, expected_name: str) -> None:
        if group._group_param.get("guild_name") != expected_name:
            raise DomainError(
                code="COMMAND_POSTCONDITION_FAILED",
                message="The guild name did not update as requested.",
                http_status=409,
            )
