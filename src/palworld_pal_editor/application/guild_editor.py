from __future__ import annotations

from typing import Any

from palworld_pal_editor.domain.commands import UpdateGuildName, UpdateGuildOwner
from palworld_pal_editor.domain.errors import DomainError

from .save_session import SaveSession


MAX_GUILD_NAME_LENGTH = 24


class GuildEditor:
    """Revision-bound guild mutations against the loaded Level.sav model."""

    def __init__(self, session: SaveSession) -> None:
        self._session = session

    def execute(
        self, command: UpdateGuildName | UpdateGuildOwner
    ) -> dict[str, Any]:
        if isinstance(command, UpdateGuildOwner):
            return self._update_owner(command)
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

    def _update_owner(self, command: UpdateGuildOwner) -> dict[str, Any]:
        if not isinstance(command.player_id, str):
            raise DomainError(
                code="INVALID_FIELD_TYPE",
                message="player_id must be a string.",
                field="player_id",
                http_status=400,
            )
        group = self._require_group(command.guild_id)
        if not group.guild_owner_editable:
            raise DomainError(
                code="COMPATIBILITY_FIELD_MISSING",
                message=(
                    "This save does not expose a verified writable guild "
                    "owner and member-role structure."
                ),
                field="player_id",
                details={"guild_id": str(command.guild_id)},
                http_status=409,
            )
        member_ids = {
            str(player_uid)
            for player_uid, _name, _role in group.guild_members
        }
        if command.player_id not in member_ids:
            raise DomainError(
                code="GUILD_MEMBER_NOT_FOUND",
                message="The selected player is not a saved member of this guild.",
                field="player_id",
                details={
                    "guild_id": str(command.guild_id),
                    "player_id": command.player_id,
                },
                http_status=404,
            )

        def value() -> dict[str, Any]:
            return {
                "guild_id": str(group.group_id),
                "owner_player_id": str(group.admin_player_uid),
                "members": [
                    {
                        "player_id": str(player_uid),
                        "role": role,
                    }
                    for player_uid, _name, role in group.guild_members
                ],
            }

        current = value()
        roles = {
            member["player_id"]: member["role"]
            for member in current["members"]
        }
        if (
            current["owner_player_id"] == command.player_id
            and roles.get(command.player_id) == 1
            and all(
                role != 1
                for player_id, role in roles.items()
                if player_id != command.player_id
            )
        ):
            self._session.require_command(
                command.session_id, command.expected_revision
            )
            return {
                "revision": self._session.revision,
                "change_id": None,
                "value": current,
            }

        try:
            entry = self._session.apply_atomic(
                session_id=command.session_id,
                expected_revision=command.expected_revision,
                command="UpdateGuildOwner",
                target={
                    "guild_id": str(group.group_id),
                    "player_id": command.player_id,
                },
                snapshot=group.snapshot,
                restore=group.restore,
                before=value,
                mutate=lambda: group.set_admin_player_uid(command.player_id),
                validate=lambda: self._validate_owner_postcondition(
                    group, command.player_id
                ),
                after=value,
                affected_records=("level:GroupSaveDataMap",),
            )
        except DomainError:
            raise
        except Exception as error:
            raise DomainError(
                code="GUILD_OWNER_UPDATE_FAILED",
                message="The guild owner could not be updated safely.",
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

    @staticmethod
    def _validate_owner_postcondition(group, expected_player_id: str) -> None:
        if str(group.admin_player_uid) != expected_player_id:
            raise DomainError(
                code="COMMAND_POSTCONDITION_FAILED",
                message="The guild owner did not update as requested.",
                http_status=409,
            )
        roles = {
            str(player_uid): role
            for player_uid, _name, role in group.guild_members
        }
        if roles.get(expected_player_id) != 1 or any(
            role == 1
            for player_id, role in roles.items()
            if player_id != expected_player_id
        ):
            raise DomainError(
                code="COMMAND_POSTCONDITION_FAILED",
                message="The guild member roles are inconsistent with the owner.",
                http_status=409,
            )
