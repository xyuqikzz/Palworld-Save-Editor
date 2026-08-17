from __future__ import annotations

from typing import Any

from palworld_pal_editor.domain.commands import UpdatePlayerInventoryCapacity
from palworld_pal_editor.domain.errors import DomainError

from .save_session import SaveSession


PLAYER_INVENTORY_CAPACITIES = (60, 90, 120)
MIN_PLAYER_INVENTORY_CAPACITY = 42
MAX_PLAYER_INVENTORY_CAPACITY = 1000


class PlayerInventoryCapacityEditor:
    """Revision-bound resize mutation of the ordinary backpack."""

    def __init__(self, session: SaveSession) -> None:
        self._session = session

    def capability(self, player_id: str) -> dict[str, Any]:
        try:
            _player, container = self._require_container(player_id)
            current = container.capacity
            if current < 1:
                raise DomainError(
                    code="PLAYER_INVENTORY_CAPACITY_UNSUPPORTED",
                    message=(
                        "The ordinary backpack capacity is outside the "
                        "editor's supported resize range."
                    ),
                    details={"current_capacity": current},
                    http_status=409,
                )
            if not container.capacity_matches_declared(current):
                raise DomainError(
                    code="PLAYER_INVENTORY_SLOTNUM_UNSUPPORTED",
                    message=(
                        "The ordinary backpack SlotNum structure is not "
                        "supported safely."
                    ),
                    http_status=409,
                )
            return {
                "available": True,
                "reason": None,
                "current_capacity": current,
                "allowed_capacities": [
                    capacity
                    for capacity in PLAYER_INVENTORY_CAPACITIES
                    if capacity != current
                ],
                "minimum_capacity": MIN_PLAYER_INVENTORY_CAPACITY,
                "maximum_capacity": MAX_PLAYER_INVENTORY_CAPACITY,
                "custom_input": True,
                "expand_only": False,
            }
        except DomainError as error:
            return {
                "available": False,
                "reason": error.code,
                "current_capacity": error.details.get("current_capacity"),
                "allowed_capacities": [],
                "minimum_capacity": None,
                "maximum_capacity": MAX_PLAYER_INVENTORY_CAPACITY,
                "custom_input": True,
                "expand_only": False,
            }

    def execute(self, command: UpdatePlayerInventoryCapacity) -> dict[str, Any]:
        if not isinstance(command, UpdatePlayerInventoryCapacity):
            raise DomainError(
                code="UNSUPPORTED_COMMAND",
                message="Unsupported player inventory capacity command.",
                http_status=400,
            )
        self._validate_capacity(command.capacity)
        player, container = self._require_container(command.player_id)
        current = container.capacity
        if current < 1:
            raise DomainError(
                code="PLAYER_INVENTORY_CAPACITY_UNSUPPORTED",
                message=(
                    "The ordinary backpack capacity is outside the editor's "
                    "supported resize range."
                ),
                details={"current_capacity": current},
                http_status=409,
            )
        if not container.capacity_matches_declared(current):
            raise DomainError(
                code="PLAYER_INVENTORY_SLOTNUM_UNSUPPORTED",
                message=(
                    "The ordinary backpack SlotNum structure is not supported "
                    "safely."
                ),
                http_status=409,
            )
        value = lambda: {
            "player_id": str(player.PlayerUId),
            "container_id": str(container.id),
            "capacity": container.capacity,
        }
        if command.capacity == current:
            self._session.require_command(
                command.session_id, command.expected_revision
            )
            return {
                "revision": self._session.revision,
                "change_id": None,
                "changed": False,
                "value": value(),
                "capability": self.capability(command.player_id),
            }

        try:
            entry = self._session.apply_atomic(
                session_id=command.session_id,
                expected_revision=command.expected_revision,
                command="UpdatePlayerInventoryCapacity",
                target={
                    "player_id": str(player.PlayerUId),
                    "container_id": str(container.id),
                    "container_type": "COMMON",
                },
                snapshot=container.snapshot_resize,
                restore=container.restore_resize,
                before=value,
                mutate=lambda: container.resize_capacity(command.capacity),
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
                code="PLAYER_INVENTORY_CAPACITY_UPDATE_FAILED",
                message=(
                    "The ordinary backpack capacity could not be updated safely."
                ),
                details={"error_type": type(error).__name__},
                http_status=409,
            ) from error
        return {
            "revision": entry.revision_after,
            "change_id": entry.change_id,
            "changed": True,
            "value": value(),
            "capability": self.capability(command.player_id),
        }

    def _require_container(self, player_id: str):
        player = self._session.load_player(player_id)
        try:
            owned = player.resolve_item_container_ids()
        except ValueError as error:
            raise DomainError(
                code="COMPATIBILITY_FIELD_AMBIGUOUS",
                message="The player's inventory aliases conflict.",
                details={"player_id": player_id},
                http_status=409,
            ) from error
        container_id = owned.get("CommonContainerId")
        if container_id is None:
            raise DomainError(
                code="PLAYER_INVENTORY_CONTAINER_MISSING",
                message="The player does not expose an ordinary backpack.",
                details={"player_id": player_id},
                http_status=409,
            )
        containers = getattr(self._session.manager, "item_container_data", None)
        container = containers.get(container_id) if containers is not None else None
        if container is None:
            raise DomainError(
                code="PLAYER_INVENTORY_CONTAINER_MISSING",
                message="The ordinary backpack container is missing.",
                details={
                    "player_id": player_id,
                    "container_id": str(container_id),
                },
                http_status=409,
            )
        return player, container

    @staticmethod
    def _validate_capacity(capacity: int) -> None:
        if isinstance(capacity, bool) or not isinstance(capacity, int):
            raise DomainError(
                code="INVALID_FIELD_TYPE",
                message="capacity must be an integer.",
                field="capacity",
                http_status=400,
            )
        if not (
            MIN_PLAYER_INVENTORY_CAPACITY
            <= capacity
            <= MAX_PLAYER_INVENTORY_CAPACITY
        ):
            raise DomainError(
                code="INVALID_PLAYER_INVENTORY_CAPACITY",
                message=(
                    f"capacity must be between {MIN_PLAYER_INVENTORY_CAPACITY} and "
                    f"{MAX_PLAYER_INVENTORY_CAPACITY}."
                ),
                field="capacity",
                details={
                    "minimum": MIN_PLAYER_INVENTORY_CAPACITY,
                    "maximum": MAX_PLAYER_INVENTORY_CAPACITY,
                    "presets": list(PLAYER_INVENTORY_CAPACITIES),
                },
                http_status=400,
            )

    @staticmethod
    def _validate_postcondition(container, capacity: int) -> None:
        if not container.capacity_matches_declared(capacity):
            raise DomainError(
                code="INVARIANT_VIOLATION",
                message=(
                    "The ordinary backpack does not match its declared "
                    "capacity after resizing."
                ),
                http_status=409,
            )
