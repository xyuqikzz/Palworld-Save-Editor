from __future__ import annotations

from typing import Any

from palworld_pal_editor.domain.commands import UpdateGuildChestCapacity
from palworld_pal_editor.domain.errors import DomainError

from .save_session import SaveSession


MAX_GUILD_CHEST_CAPACITY = 2466


class GuildChestEditor:
    """Revision-bound, expand-only guild chest capacity mutations."""

    def __init__(self, session: SaveSession) -> None:
        self._session = session

    def execute(
        self, command: UpdateGuildChestCapacity
    ) -> dict[str, Any]:
        if not isinstance(command, UpdateGuildChestCapacity):
            raise DomainError(
                code="UNSUPPORTED_COMMAND",
                message="Unsupported guild chest command.",
                http_status=400,
            )
        self._validate_capacity(command.capacity)
        self._require_group(command.guild_id)
        container = self._require_container(command.guild_id)
        current_capacity = container.capacity
        if command.capacity < current_capacity:
            raise DomainError(
                code="GUILD_CHEST_SHRINK_UNSUPPORTED",
                message="Guild chest capacity can only be expanded.",
                field="capacity",
                details={"current_capacity": current_capacity},
                http_status=409,
            )

        value = lambda: {
            "guild_id": str(command.guild_id),
            "capacity": container.capacity,
        }
        if command.capacity == current_capacity:
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
                command="UpdateGuildChestCapacity",
                target={"guild_id": str(command.guild_id)},
                snapshot=container.snapshot_capacity,
                restore=container.restore_capacity,
                before=value,
                mutate=lambda: container.expand_capacity(command.capacity),
                validate=lambda: self._validate_postcondition(
                    container, command.capacity
                ),
                after=value,
                affected_records=("level:ItemContainerSaveData",),
            )
        except DomainError:
            raise
        except Exception as error:
            raise DomainError(
                code="GUILD_CHEST_UPDATE_FAILED",
                message="The guild chest capacity could not be updated safely.",
                details={"error_type": type(error).__name__},
                http_status=409,
            ) from error
        return {
            "revision": entry.revision_after,
            "change_id": entry.change_id,
            "value": value(),
        }

    def _require_group(self, guild_id: str) -> None:
        group_data = getattr(self._session.manager, "group_data", None)
        group = (
            group_data.get_group(guild_id)
            if group_data is not None
            else None
        )
        if group is None:
            raise DomainError(
                code="GUILD_NOT_FOUND",
                message="Guild not found.",
                field="guild_id",
                details={"guild_id": str(guild_id)},
                http_status=404,
            )

    def _require_container(self, guild_id: str):
        manager = self._session.manager
        if getattr(manager, "guild_item_storage_error", None):
            raise DomainError(
                code="GUILD_CHEST_UNSUPPORTED",
                message="This save's guild chest mapping is not supported.",
                details={
                    "error_type": manager.guild_item_storage_error,
                },
                http_status=409,
            )
        storage = getattr(manager, "guild_item_storage_data", None)
        binding = storage.get(guild_id) if storage is not None else None
        if binding is None:
            raise DomainError(
                code="GUILD_CHEST_NOT_FOUND",
                message="This guild does not expose a shared item container.",
                details={"guild_id": str(guild_id)},
                http_status=409,
            )
        containers = getattr(manager, "item_container_data", None)
        container = (
            containers.get(binding.container_id)
            if containers is not None
            else None
        )
        if container is None:
            raise DomainError(
                code="GUILD_CHEST_CONTAINER_MISSING",
                message="The guild chest container is missing from this save.",
                details={"guild_id": str(guild_id)},
                http_status=409,
            )
        return container

    @staticmethod
    def _validate_capacity(capacity: int) -> None:
        if isinstance(capacity, bool) or not isinstance(capacity, int):
            raise DomainError(
                code="INVALID_FIELD_TYPE",
                message="capacity must be an integer.",
                field="capacity",
                http_status=400,
            )
        if capacity < 1 or capacity > MAX_GUILD_CHEST_CAPACITY:
            raise DomainError(
                code="INVALID_GUILD_CHEST_CAPACITY",
                message=(
                    "Guild chest capacity must be between 1 and "
                    f"{MAX_GUILD_CHEST_CAPACITY}."
                ),
                field="capacity",
                details={"maximum": MAX_GUILD_CHEST_CAPACITY},
                http_status=400,
            )

    @staticmethod
    def _validate_postcondition(container, expected_capacity: int) -> None:
        matches_declared = getattr(
            container, "capacity_matches_declared", None
        )
        if (
            container.capacity != expected_capacity
            or (
                matches_declared is not None
                and not matches_declared(expected_capacity)
            )
        ):
            raise DomainError(
                code="COMMAND_POSTCONDITION_FAILED",
                message="The guild chest capacity did not update as requested.",
                http_status=409,
            )
