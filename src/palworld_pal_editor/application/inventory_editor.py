from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable
import uuid

from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.domain.commands import ClearItemSlot, PutItem, UpdateItemCount
from palworld_pal_editor.domain.item_catalog import ItemCatalog, new_item_slot_metadata
from palworld_pal_editor.domain.models import (
    INVENTORY_CONTAINER_FIELDS,
    ItemContainerType,
    ItemContainerView,
    ItemSlotView,
    PlayerInventoryView,
)

from .save_session import SaveSession


class InventoryEditor:
    def __init__(
        self,
        session: SaveSession,
        catalog: ItemCatalog | None = None,
        *,
        locale: str = "en",
        id_factory: Callable[[], Any] = uuid.uuid4,
    ) -> None:
        self._session = session
        self._catalog = catalog or ItemCatalog.load_default()
        self._locale = locale
        self._id_factory = id_factory

    def get_inventory(self, player_id: str) -> PlayerInventoryView:
        player = self._session.manager.get_player(player_id)
        if player is None:
            raise DomainError(
                code="PLAYER_NOT_FOUND",
                message="Player not found.",
                field="player_id",
                details={"player_id": player_id},
                http_status=404,
            )
        try:
            owned_ids = player.resolve_item_container_ids()
        except ValueError as error:
            raise DomainError(
                code="COMPATIBILITY_FIELD_AMBIGUOUS",
                message="The player's inventory aliases conflict.",
                details={"player_id": player_id},
            ) from error

        containers: list[ItemContainerView] = []
        for container_type, field_name in INVENTORY_CONTAINER_FIELDS.items():
            container_id = owned_ids.get(field_name)
            if container_id is None:
                containers.append(
                    ItemContainerView(
                        container_type=container_type,
                        capacity=None,
                        status="unavailable",
                        slots=(),
                        reason="CONTAINER_FIELD_MISSING",
                    )
                )
                continue
            container = self._session.manager.item_container_data.get(container_id)
            if container is None:
                containers.append(
                    ItemContainerView(
                        container_type=container_type,
                        capacity=None,
                        status="unavailable",
                        slots=(),
                        reason="CONTAINER_NOT_FOUND",
                    )
                )
                continue
            slots: list[ItemSlotView] = []
            dynamic_items = getattr(
                self._session.manager, "dynamic_item_data", None
            )
            for slot_index, slot in enumerate(container.dense_slots()):
                if slot is None:
                    slots.append(ItemSlotView(slot_index=slot_index, state="empty"))
                    continue
                catalog_entry = self._catalog.get_optional(slot.static_id)
                slots.append(
                    ItemSlotView(
                        slot_index=slot_index,
                        state="occupied",
                        static_id=slot.static_id,
                        count=slot.count,
                        dynamic_id=slot.dynamic_id,
                        dynamic_kind=(
                            dynamic_items.kind_for_slot(slot)
                            if slot.dynamic_id is not None
                            and dynamic_items is not None
                            else (
                                catalog_entry.dynamic_kind
                                if catalog_entry is not None
                                else "unknown"
                            )
                        ),
                        name=(
                            catalog_entry.localized_name(self._locale)
                            if catalog_entry is not None
                            else slot.static_id
                        ),
                        category=(
                            catalog_entry.category
                            if catalog_entry is not None
                            else "unknown"
                        ),
                        rarity=(catalog_entry.rarity if catalog_entry else None),
                        icon=(catalog_entry.icon if catalog_entry else None),
                    )
                )
            containers.append(
                ItemContainerView(
                    container_type=container_type,
                    capacity=container.capacity,
                    status="available",
                    slots=tuple(slots),
                )
            )
        return PlayerInventoryView(
            player_id=str(player.PlayerUId),
            session_revision=self._session.revision,
            containers=tuple(containers),
        )

    def execute(self, command: UpdateItemCount | PutItem | ClearItemSlot) -> dict:
        self._session.require_command(
            command.session_id, command.expected_revision
        )
        if isinstance(command, UpdateItemCount):
            return self._update_count(command)
        if isinstance(command, PutItem):
            return self._put_item(command)
        if isinstance(command, ClearItemSlot):
            return self._clear_item(command)
        raise DomainError(
            code="UNSUPPORTED_COMMAND",
            message="Unsupported inventory command.",
            http_status=400,
        )

    def _update_count(self, command: UpdateItemCount) -> dict:
        player, container = self._resolve_owned_container(
            command.player_id, command.container_type
        )
        try:
            slot = container.get_occupied(command.slot_index)
        except KeyError as error:
            raise DomainError(
                code="ITEM_SLOT_EMPTY",
                message="The selected item slot is empty.",
                field="slot_index",
                details={"slot_index": command.slot_index},
                http_status=404,
            ) from error
        if slot.static_id != command.expected_static_id:
            raise DomainError(
                code="STALE_SLOT",
                message="The item slot changed; reload before retrying.",
                field="expected_static_id",
                details={
                    "expected": command.expected_static_id,
                    "actual": slot.static_id,
                },
                retryable=True,
                http_status=409,
            )
        self._catalog.validate_existing_count_update(
            slot.static_id,
            command.container_type,
            command.slot_index,
            current_count=slot.count,
            count=command.count,
        )
        original_dynamic_id = slot.dynamic_id
        original_static_id = slot.static_id
        dynamic_record_before = None
        if original_dynamic_id is not None:
            dynamic_items = getattr(
                self._session.manager, "dynamic_item_data", None
            )
            if dynamic_items is None:
                raise DomainError(
                    code="DYNAMIC_ITEM_INDEX_UNAVAILABLE",
                    message="Dynamic item data is not indexed for this save.",
                )
            dynamic_record = dynamic_items.require_writable_reference(slot)
            dynamic_record_before = deepcopy(dynamic_record.raw_data)

        def validate() -> None:
            updated = container.get_occupied(command.slot_index)
            if updated.static_id != original_static_id:
                raise DomainError(
                    code="INVARIANT_VIOLATION",
                    message="Updating a count changed the static item identity.",
                    http_status=409,
                )
            if updated.dynamic_id != original_dynamic_id:
                raise DomainError(
                    code="INVARIANT_VIOLATION",
                    message="Updating a count changed the dynamic item reference.",
                    http_status=409,
                )
            if updated.count != command.count:
                raise DomainError(
                    code="INVARIANT_VIOLATION",
                    message="The item count did not update as requested.",
                    http_status=409,
                )
            if dynamic_record_before is not None:
                current = dynamic_items.require_writable_reference(updated)
                if current.raw_data != dynamic_record_before:
                    raise DomainError(
                        code="INVARIANT_VIOLATION",
                        message="Updating a count changed dynamic item attributes.",
                        http_status=409,
                    )

        entry = self._session.apply_atomic(
            session_id=command.session_id,
            expected_revision=command.expected_revision,
            command="UpdateItemCount",
            target={
                "player_id": str(player.PlayerUId),
                "container_type": command.container_type.value,
                "slot_index": command.slot_index,
            },
            snapshot=lambda: container.snapshot_slot(command.slot_index),
            restore=lambda state: container.restore_slot(command.slot_index, state),
            before=lambda: container.slot_summary(command.slot_index),
            mutate=lambda: container.set_count(
                command.slot_index, command.expected_static_id, command.count
            ),
            validate=validate,
            after=lambda: container.slot_summary(command.slot_index),
            affected_records=(
                "level:ItemContainerSaveData",
                f"item_container:{command.container_type.value}",
            ),
        )
        return {
            "revision": self._session.revision,
            "change_id": entry.change_id,
            "slot": container.slot_summary(command.slot_index),
        }

    def _put_item(self, command: PutItem) -> dict:
        if command.mode not in ("empty_only", "replace"):
            raise DomainError(
                code="INVALID_PUT_MODE",
                message="mode must be empty_only or replace.",
                field="mode",
                http_status=400,
            )
        player, container = self._resolve_owned_container(
            command.player_id, command.container_type
        )
        entry_rule = self._catalog.validate_placement(
            command.static_id,
            command.container_type,
            command.slot_index,
            command.count,
        )
        creates_dynamic = entry_rule.dynamic_kind != "none"
        dynamic_items = getattr(self._session.manager, "dynamic_item_data", None)
        dynamic_record_static_id = None
        if creates_dynamic and dynamic_items is None:
            raise DomainError(
                code="DYNAMIC_ITEM_INDEX_UNAVAILABLE",
                message="Dynamic item data is not indexed for this save.",
            )
        if creates_dynamic:
            dynamic_items.prepare_construction(
                command.static_id,
                entry_rule.dynamic_kind,
                command.dynamic_init,
            )
            dynamic_record_static_id = command.dynamic_init["record_static_id"]
            self._catalog.validate_dynamic_record_static_id(
                command.static_id,
                dynamic_record_static_id,
                entry_rule.dynamic_kind,
            )
        elif command.dynamic_init is not None:
            raise DomainError(
                code="UNSUPPORTED_COMMAND_FIELD",
                message="Plain items do not accept dynamic_init.",
                field="dynamic_init",
                http_status=400,
            )
        try:
            occupied = not container.is_empty(command.slot_index)
        except (IndexError, TypeError) as error:
            raise DomainError(
                code="SLOT_LAYOUT_UNVERIFIED",
                message="This slot is outside the verified container layout.",
                field="slot_index",
            ) from error
        raw_slot = container.get_raw_slot(command.slot_index) if occupied else None
        if occupied and command.mode == "empty_only":
            raise DomainError(
                code="ITEM_SLOT_OCCUPIED",
                message="The selected item slot is already occupied.",
                field="slot_index",
                http_status=409,
            )
        old_record = None
        if occupied and raw_slot is not None and raw_slot.dynamic_id is not None:
            if dynamic_items is None:
                raise DomainError(
                    code="DYNAMIC_ITEM_INDEX_UNAVAILABLE",
                    message="Dynamic item data is not indexed for this save.",
                )
            old_record = dynamic_items.require_removable_reference(raw_slot)
        new_local_id = (
            self._new_dynamic_local_id(dynamic_items) if creates_dynamic else None
        )
        touches_dynamic = creates_dynamic or old_record is not None
        before_summary = (
            container.slot_summary(command.slot_index)
            if occupied
            else {"slot_index": command.slot_index, "state": "empty"}
        )

        def snapshot():
            return {
                "slot": container.snapshot_slot(command.slot_index),
                "dynamic": (
                    dynamic_items.snapshot_values() if touches_dynamic else None
                ),
            }

        def restore(state) -> None:
            if state["dynamic"] is not None:
                dynamic_items.restore_values(state["dynamic"])
            container.restore_slot(command.slot_index, state["slot"])
            if dynamic_items is not None:
                dynamic_items.rebuild_references()

        def mutate() -> None:
            if creates_dynamic:
                dynamic_items.construct_record(
                    static_id=command.static_id,
                    kind=entry_rule.dynamic_kind,
                    dynamic_init=command.dynamic_init,
                    target_local_id=new_local_id,
                )
                container.put_dynamic_reference(
                    command.slot_index,
                    command.static_id,
                    command.count,
                    created_world_id="00000000-0000-0000-0000-000000000000",
                    local_id=new_local_id,
                    replace=occupied,
                    slot_metadata=new_item_slot_metadata(
                        command.container_type, command.slot_index
                    ),
                )
            elif old_record is not None:
                container.replace_dynamic_reference_with_plain(
                    command.slot_index,
                    command.static_id,
                    command.count,
                )
            else:
                container.put_plain(
                    command.slot_index,
                    command.static_id,
                    command.count,
                    replace=command.mode == "replace",
                    slot_metadata=new_item_slot_metadata(
                        command.container_type, command.slot_index
                    ),
                )
            if touches_dynamic:
                dynamic_items.rebuild_references()
                if (
                    old_record is not None
                    and not dynamic_items.references.get(old_record.local_id)
                ):
                    dynamic_items.delete_unreferenced(old_record.local_id)

        def validate() -> None:
            updated = container.get_occupied(command.slot_index)
            if (
                updated.static_id != command.static_id
                or updated.count != command.count
            ):
                raise DomainError(
                    code="INVARIANT_VIOLATION",
                    message="Item placement produced an invalid slot.",
                    http_status=409,
                )
            if creates_dynamic:
                record = dynamic_items.get(new_local_id)
                if (
                    updated.dynamic_local_id != new_local_id
                    or record is None
                    or record.kind != entry_rule.dynamic_kind
                    or record.static_id != dynamic_record_static_id
                ):
                    raise DomainError(
                        code="INVARIANT_VIOLATION",
                        message="Dynamic item placement produced an invalid record.",
                        http_status=409,
                    )
            elif updated.dynamic_id is not None:
                raise DomainError(
                    code="INVARIANT_VIOLATION",
                    message="Plain item placement retained a dynamic reference.",
                    http_status=409,
                )
            if dynamic_items is not None:
                dynamic_items.assert_consistent()

        entry = self._session.apply_atomic(
            session_id=command.session_id,
            expected_revision=command.expected_revision,
            command="PutItem",
            target={
                "player_id": str(player.PlayerUId),
                "container_type": command.container_type.value,
                "slot_index": command.slot_index,
                "mode": command.mode,
            },
            snapshot=snapshot,
            restore=restore,
            before=lambda: before_summary,
            mutate=mutate,
            validate=validate,
            after=lambda: container.slot_summary(command.slot_index),
            affected_records=(
                "level:ItemContainerSaveData",
                *(("level:DynamicItemSaveData",) if touches_dynamic else ()),
                f"item_container:{command.container_type.value}",
            ),
        )
        return {
            "revision": self._session.revision,
            "change_id": entry.change_id,
            "slot": container.slot_summary(command.slot_index),
        }

    def _new_dynamic_local_id(self, dynamic_items) -> str:
        for _ in range(128):
            value = str(self._id_factory())
            try:
                normalized = str(uuid.UUID(value))
            except (ValueError, TypeError, AttributeError) as error:
                raise DomainError(
                    code="INVALID_GENERATED_ID",
                    message="The dynamic item ID generator returned an invalid UUID.",
                    http_status=409,
                ) from error
            if (
                normalized != "00000000-0000-0000-0000-000000000000"
                and dynamic_items.get(normalized) is None
            ):
                return normalized
        raise DomainError(
            code="DYNAMIC_ITEM_ID_COLLISION",
            message="A unique dynamic item identifier could not be generated.",
            http_status=409,
        )

    def _clear_item(self, command: ClearItemSlot) -> dict:
        player, container = self._resolve_owned_container(
            command.player_id, command.container_type
        )
        try:
            slot = container.get_occupied(command.slot_index)
        except KeyError as error:
            raise DomainError(
                code="ITEM_SLOT_EMPTY",
                message="The selected item slot is already empty.",
                field="slot_index",
                http_status=404,
            ) from error
        if slot.static_id != command.expected_static_id or (
            command.expected_dynamic_id != slot.dynamic_id
        ):
            raise DomainError(
                code="STALE_SLOT",
                message="The item slot changed; reload before retrying.",
                retryable=True,
                http_status=409,
            )
        if slot.dynamic_id is not None:
            return self._clear_dynamic_item(command, player, container, slot)
        try:
            entry = self._session.apply_atomic(
                session_id=command.session_id,
                expected_revision=command.expected_revision,
                command="ClearItemSlot",
                target={
                    "player_id": str(player.PlayerUId),
                    "container_type": command.container_type.value,
                    "slot_index": command.slot_index,
                },
                snapshot=lambda: container.snapshot_slot(command.slot_index),
                restore=lambda state: container.restore_slot(command.slot_index, state),
                before=lambda: container.slot_summary(command.slot_index),
                mutate=lambda: container.clear_plain(command.slot_index),
                validate=lambda: self._validate_empty(container, command.slot_index),
                after=lambda: {"slot_index": command.slot_index, "state": "empty"},
                affected_records=(
                    "level:ItemContainerSaveData",
                    f"item_container:{command.container_type.value}",
                ),
            )
        except LookupError as error:
            raise DomainError(
                code="EMPTY_SLOT_ENCODING_UNVERIFIED",
                message="No verified empty-slot encoding is available in this container.",
            ) from error
        return {
            "revision": self._session.revision,
            "change_id": entry.change_id,
            "slot": {"slot_index": command.slot_index, "state": "empty"},
        }

    def _clear_dynamic_item(self, command, player, container, slot) -> dict:
        dynamic_items = getattr(
            self._session.manager, "dynamic_item_data", None
        )
        if dynamic_items is None:
            raise DomainError(
                code="DYNAMIC_ITEM_INDEX_UNAVAILABLE",
                message="Dynamic item data is not indexed for this save.",
            )
        record = dynamic_items.require_removable_reference(slot)
        remaining_reference_count = (
            len(dynamic_items.references.get(record.local_id, [])) - 1
        )

        def snapshot():
            return (
                container.snapshot_slot(command.slot_index),
                dynamic_items.snapshot_values(),
            )

        def restore(state) -> None:
            slot_state, dynamic_state = state
            dynamic_items.restore_values(dynamic_state)
            container.restore_slot(command.slot_index, slot_state)
            dynamic_items.rebuild_references()

        def mutate() -> None:
            container.clear_dynamic(command.slot_index)
            dynamic_items.rebuild_references()
            if not dynamic_items.references.get(record.local_id):
                dynamic_items.delete_unreferenced(record.local_id)

        def validate() -> None:
            self._validate_empty(container, command.slot_index)
            record_still_exists = dynamic_items.get(record.local_id) is not None
            if record_still_exists != (remaining_reference_count > 0):
                raise DomainError(
                    code="INVARIANT_VIOLATION",
                    message="Clearing the reference left an invalid dynamic record lifecycle.",
                    http_status=409,
                )
            dynamic_items.assert_consistent()

        try:
            entry = self._session.apply_atomic(
                session_id=command.session_id,
                expected_revision=command.expected_revision,
                command="ClearDynamicItemSlot",
                target={
                    "player_id": str(player.PlayerUId),
                    "container_type": command.container_type.value,
                    "slot_index": command.slot_index,
                    "dynamic_kind": record.kind,
                },
                snapshot=snapshot,
                restore=restore,
                before=lambda: container.slot_summary(command.slot_index),
                mutate=mutate,
                validate=validate,
                after=lambda: {
                    "slot_index": command.slot_index,
                    "state": "empty",
                },
                affected_records=(
                    "level:ItemContainerSaveData",
                    "level:DynamicItemSaveData",
                    f"item_container:{command.container_type.value}",
                ),
            )
        except LookupError as error:
            raise DomainError(
                code="EMPTY_SLOT_ENCODING_UNVERIFIED",
                message="No verified empty-slot encoding is available in this container.",
            ) from error
        return {
            "revision": self._session.revision,
            "change_id": entry.change_id,
            "slot": {"slot_index": command.slot_index, "state": "empty"},
        }

    @staticmethod
    def _validate_empty(container, slot_index: int) -> None:
        if not container.is_empty(slot_index):
            raise DomainError(
                code="INVARIANT_VIOLATION",
                message="Clearing an item did not produce a valid empty slot.",
                http_status=409,
            )

    def _resolve_owned_container(self, player_id: str, container_type: ItemContainerType):
        player = self._session.manager.get_player(player_id)
        if player is None:
            raise DomainError(
                code="PLAYER_NOT_FOUND",
                message="Player not found.",
                field="player_id",
                details={"player_id": player_id},
                http_status=404,
            )
        try:
            owned_ids = player.resolve_item_container_ids()
        except ValueError as error:
            raise DomainError(
                code="COMPATIBILITY_FIELD_AMBIGUOUS",
                message="The player's inventory aliases conflict.",
            ) from error
        field_name = INVENTORY_CONTAINER_FIELDS.get(container_type)
        if field_name is None:
            raise DomainError(
                code="INVALID_PLAYER_CONTAINER_TYPE",
                message="This container type is not a player inventory.",
                field="container_type",
                http_status=400,
            )
        container_id = owned_ids.get(field_name)
        if container_id is None:
            raise DomainError(
                code="CONTAINER_NOT_FOUND",
                message="The player does not own this container type.",
                field="container_type",
                details={"container_type": container_type.value},
                http_status=404,
            )
        container = self._session.manager.item_container_data.get(container_id)
        if container is None:
            raise DomainError(
                code="CONTAINER_OWNERSHIP_VIOLATION",
                message="The player-owned container cannot be resolved.",
                field="container_type",
                details={"container_type": container_type.value},
                http_status=409,
            )
        return player, container
