from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable
import uuid

from palworld_pal_editor.domain.commands import (
    FillItemSlots,
    PasteItemSlot,
    SortItemContainer,
)
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.domain.item_catalog import (
    EQUIPMENT_SLOT_CATEGORIES,
    ItemCatalog,
    new_item_slot_metadata,
)
from palworld_pal_editor.domain.models import ItemContainerType

from .inventory_editor import InventoryEditor
from .save_session import SaveSession


class InventoryLayoutEditor:
    """Server-side domain clipboard and whole-container layout operations."""

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
        if not hasattr(session, "_inventory_clipboards"):
            session._inventory_clipboards = {}

    def copy_slot(
        self,
        *,
        session_id: str,
        expected_revision: int,
        player_id: str,
        container_type: ItemContainerType,
        slot_index: int,
    ) -> dict:
        self._session.require_command(session_id, expected_revision)
        _player, container = InventoryEditor(
            self._session, self._catalog
        )._resolve_owned_container(player_id, container_type)
        try:
            slot = container.get_occupied(slot_index)
        except KeyError as error:
            raise DomainError(
                code="ITEM_SLOT_EMPTY",
                message="The selected item slot is empty.",
                field="slot_index",
                http_status=404,
            ) from error
        dynamic_entry = None
        if slot.dynamic_id is not None:
            dynamic_items = getattr(self._session.manager, "dynamic_item_data", None)
            if dynamic_items is None:
                raise DomainError(
                    code="DYNAMIC_ITEM_INDEX_UNAVAILABLE",
                    message="Dynamic item data is not indexed for this save.",
                )
            record = dynamic_items.require_writable_reference(slot)
            dynamic_items.require_transferable_record(record)
            dynamic_entry = deepcopy(record.entry)
        token = str(uuid.uuid4())
        self._session._inventory_clipboards[token] = {
            "revision": self._session.revision,
            "player_id": str(player_id),
            "container_type": container_type.value,
            "slot_index": slot_index,
            "slot": container.snapshot_slot(slot_index),
            "dynamic_entry": dynamic_entry,
        }
        return {
            "clipboard_token": token,
            "revision": self._session.revision,
            "item": {
                "static_id": slot.static_id,
                "count": slot.count,
                "dynamic_kind": (
                    "none"
                    if slot.dynamic_id is None
                    else dynamic_items.kind_for_slot(slot)
                ),
            },
        }

    def execute(
        self, command: PasteItemSlot | SortItemContainer | FillItemSlots
    ) -> dict:
        self._session.require_command(
            command.session_id, command.expected_revision
        )
        if isinstance(command, PasteItemSlot):
            return self._paste(command)
        if isinstance(command, SortItemContainer):
            return self._sort(command)
        if isinstance(command, FillItemSlots):
            return self._fill(command)
        raise DomainError(
            code="UNSUPPORTED_COMMAND",
            message="Unsupported inventory layout command.",
            http_status=400,
        )

    def _paste(self, command: PasteItemSlot) -> dict:
        clipboard = self._session._inventory_clipboards.get(command.clipboard_token)
        if clipboard is None:
            raise DomainError(
                code="CLIPBOARD_NOT_FOUND",
                message="The item clipboard is unavailable.",
                field="clipboard_token",
                http_status=404,
            )
        if clipboard["revision"] != self._session.revision:
            raise DomainError(
                code="CLIPBOARD_STALE",
                message="The item clipboard was created for an older session revision.",
                field="clipboard_token",
                retryable=True,
                http_status=409,
            )
        player, container = InventoryEditor(
            self._session, self._catalog
        )._resolve_owned_container(command.player_id, command.container_type)
        source = clipboard["slot"]
        self._catalog.validate_placement(
            source["item"]["static_id"],
            command.container_type,
            command.slot_index,
            source["count"],
        )
        if not container.is_empty(command.slot_index):
            raise DomainError(
                code="ITEM_SLOT_OCCUPIED",
                message="Paste requires an empty target slot.",
                field="slot_index",
                http_status=409,
            )
        dynamic_items = getattr(self._session.manager, "dynamic_item_data", None)
        source_local_id = str(
            source["item"]["dynamic_id"]["local_id_in_created_world"]
        )
        has_dynamic = clipboard["dynamic_entry"] is not None
        new_local_id = (
            self._new_dynamic_local_ids(dynamic_items, 1)[0]
            if has_dynamic
            else None
        )

        def snapshot():
            return (
                container.snapshot_slot(command.slot_index),
                dynamic_items.snapshot_values() if has_dynamic else None,
            )

        def restore(state) -> None:
            slot_state, dynamic_state = state
            if dynamic_state is not None:
                dynamic_items.restore_values(dynamic_state)
            container.restore_slot(command.slot_index, slot_state)
            if dynamic_items is not None:
                dynamic_items.rebuild_references()

        def mutate() -> None:
            if has_dynamic:
                if dynamic_items is None:
                    raise DomainError(
                        code="DYNAMIC_ITEM_INDEX_UNAVAILABLE",
                        message="Dynamic item data is not indexed for this save.",
                    )
                dynamic_items.clone_record(source_local_id, new_local_id)
                container.put_dynamic_reference(
                    command.slot_index,
                    source["item"]["static_id"],
                    source["count"],
                    created_world_id=str(
                        source["item"]["dynamic_id"]["created_world_id"]
                    ),
                    local_id=new_local_id,
                    slot_metadata=new_item_slot_metadata(
                        command.container_type, command.slot_index
                    ),
                )
            else:
                container.put_plain(
                    command.slot_index,
                    source["item"]["static_id"],
                    source["count"],
                    replace=False,
                    slot_metadata=new_item_slot_metadata(
                        command.container_type, command.slot_index
                    ),
                )
            if dynamic_items is not None:
                dynamic_items.rebuild_references()

        def validate() -> None:
            pasted = container.get_occupied(command.slot_index)
            if pasted.static_id != source["item"]["static_id"]:
                raise DomainError(
                    code="INVARIANT_VIOLATION",
                    message="The pasted item does not match the clipboard.",
                    http_status=409,
                )
            if dynamic_items is not None:
                dynamic_items.assert_consistent()

        entry = self._session.apply_atomic(
            session_id=command.session_id,
            expected_revision=command.expected_revision,
            command="PasteItemSlot",
            target={
                "player_id": str(player.PlayerUId),
                "container_type": command.container_type.value,
                "slot_index": command.slot_index,
            },
            snapshot=snapshot,
            restore=restore,
            before=lambda: {"slot_index": command.slot_index, "state": "empty"},
            mutate=mutate,
            validate=validate,
            after=lambda: container.slot_summary(command.slot_index),
            affected_records=(
                "level:ItemContainerSaveData",
                *(("level:DynamicItemSaveData",) if has_dynamic else ()),
            ),
        )
        return {
            "revision": self._session.revision,
            "change_id": entry.change_id,
            "slot": container.slot_summary(command.slot_index),
        }

    def _sort(self, command: SortItemContainer) -> dict:
        supported = {"name", "internal_id", "category", "rarity", "count"}
        if command.sort_by not in supported:
            raise DomainError(
                code="INVALID_SORT_FIELD",
                message="sort_by is not supported.",
                field="sort_by",
                details={"supported": sorted(supported)},
                http_status=400,
            )
        if not isinstance(command.descending, bool):
            raise DomainError(
                code="INVALID_SORT_DIRECTION",
                message="descending must be a boolean.",
                field="descending",
                http_status=400,
            )
        player, container = InventoryEditor(
            self._session, self._catalog
        )._resolve_owned_container(command.player_id, command.container_type)
        snapshots = container.snapshot_all()
        occupied = list(container.iter_occupied_slots())

        def sort_value(slot):
            entry = self._catalog.get_optional(slot.static_id)
            values = {
                "name": (
                    entry.localized_name(self._locale) if entry else slot.static_id
                ),
                "internal_id": slot.static_id,
                "category": entry.category if entry else "unknown",
                "rarity": entry.rarity if entry and entry.rarity is not None else -1,
                "count": slot.count,
            }
            return values[command.sort_by]

        if command.container_type == ItemContainerType.PLAYER_EQUIP_ARMOR:
            groups: dict[frozenset[str], list[int]] = {}
            for index in range(container.capacity):
                group = EQUIPMENT_SLOT_CATEGORIES.get(index, frozenset())
                groups.setdefault(group, []).append(index)
            source_indices = list(range(container.capacity))
            occupied_by_index = {slot.slot_index: slot for slot in occupied}
            for indices in groups.values():
                ordered = sorted(
                    (
                        occupied_by_index[index]
                        for index in indices
                        if index in occupied_by_index
                    ),
                    key=lambda slot: (sort_value(slot), slot.slot_index),
                    reverse=command.descending,
                )
                empty_indices = [
                    index for index in indices if index not in occupied_by_index
                ]
                for target_index, source_index in zip(
                    indices,
                    [slot.slot_index for slot in ordered] + empty_indices,
                ):
                    source_indices[target_index] = source_index
        else:
            ordered = sorted(
                occupied,
                key=lambda slot: (sort_value(slot), slot.slot_index),
                reverse=command.descending,
            )
            empty_indices = [
                index for index in sorted(snapshots) if index not in container.slots
            ]
            source_indices = [slot.slot_index for slot in ordered] + empty_indices

        occupied_by_index = {slot.slot_index: slot for slot in occupied}
        for target_index, source_index in enumerate(source_indices):
            source = occupied_by_index.get(source_index)
            if source is not None:
                self._catalog.validate_placement(
                    source.static_id,
                    command.container_type,
                    target_index,
                    source.count,
                )
        target_metadata = (
            {
                index: new_item_slot_metadata(command.container_type, index)
                for index in range(container.capacity)
            }
            if command.container_type == ItemContainerType.PLAYER_EQUIP_ARMOR
            else None
        )

        def validate() -> None:
            if len(container.dense_slots()) != container.capacity:
                raise DomainError(
                    code="INVARIANT_VIOLATION",
                    message="Sorting changed the item container capacity.",
                    http_status=409,
                )
            dynamic_items = getattr(self._session.manager, "dynamic_item_data", None)
            if dynamic_items is not None:
                dynamic_items.assert_consistent()

        entry = self._session.apply_atomic(
            session_id=command.session_id,
            expected_revision=command.expected_revision,
            command="SortItemContainer",
            target={
                "player_id": str(player.PlayerUId),
                "container_type": command.container_type.value,
                "sort_by": command.sort_by,
                "descending": command.descending,
            },
            snapshot=container.snapshot_all,
            restore=container.restore_all,
            before=lambda: {
                "occupied": [
                    container.slot_summary(index) for index in sorted(container.slots)
                ]
            },
            mutate=lambda: container.reorder_payloads(
                source_indices,
                target_slot_metadata=target_metadata,
            ),
            validate=validate,
            after=lambda: {
                "occupied": [
                    container.slot_summary(index) for index in sorted(container.slots)
                ]
            },
            affected_records=("level:ItemContainerSaveData",),
        )
        return {
            "revision": self._session.revision,
            "change_id": entry.change_id,
            "container_type": command.container_type.value,
        }

    def _fill(self, command: FillItemSlots) -> dict:
        player, container = InventoryEditor(
            self._session, self._catalog
        )._resolve_owned_container(command.player_id, command.container_type)
        indices = tuple(command.slot_indices)
        if not indices or len(indices) != len(set(indices)):
            raise DomainError(
                code="INVALID_SLOT_SELECTION",
                message="slot_indices must contain unique target slots.",
                field="slot_indices",
                http_status=400,
            )
        rule = None
        for index in indices:
            rule = self._catalog.validate_placement(
                command.static_id, command.container_type, index, command.count
            )
            if not container.is_empty(index):
                raise DomainError(
                    code="ITEM_SLOT_OCCUPIED",
                    message="Batch fill only writes empty target slots.",
                    details={"slot_index": index},
                    http_status=409,
                )

        creates_dynamic = rule is not None and rule.dynamic_kind != "none"
        dynamic_items = getattr(self._session.manager, "dynamic_item_data", None)
        record_static_id = None
        if creates_dynamic:
            if dynamic_items is None:
                raise DomainError(
                    code="DYNAMIC_ITEM_INDEX_UNAVAILABLE",
                    message="Dynamic item data is not indexed for this save.",
                )
            dynamic_items.prepare_construction(
                command.static_id, rule.dynamic_kind, command.dynamic_init
            )
            record_static_id = command.dynamic_init["record_static_id"]
            self._catalog.validate_dynamic_record_static_id(
                command.static_id, record_static_id, rule.dynamic_kind
            )
        elif command.dynamic_init is not None:
            raise DomainError(
                code="UNSUPPORTED_COMMAND_FIELD",
                message="Plain items do not accept dynamic_init.",
                field="dynamic_init",
                http_status=400,
            )
        new_local_ids = (
            self._new_dynamic_local_ids(dynamic_items, len(indices))
            if creates_dynamic
            else ()
        )

        def snapshot():
            return {
                "slots": container.snapshot_all(),
                "dynamic": (
                    dynamic_items.snapshot_values() if creates_dynamic else None
                ),
            }

        def restore(state) -> None:
            if state["dynamic"] is not None:
                dynamic_items.restore_values(state["dynamic"])
            container.restore_all(state["slots"])
            if dynamic_items is not None:
                dynamic_items.rebuild_references()

        def mutate() -> None:
            for offset, index in enumerate(indices):
                if creates_dynamic:
                    local_id = new_local_ids[offset]
                    dynamic_items.construct_record(
                        static_id=command.static_id,
                        kind=rule.dynamic_kind,
                        dynamic_init=command.dynamic_init,
                        target_local_id=local_id,
                    )
                    container.put_dynamic_reference(
                        index,
                        command.static_id,
                        command.count,
                        created_world_id=(
                            "00000000-0000-0000-0000-000000000000"
                        ),
                        local_id=local_id,
                        replace=False,
                        slot_metadata=new_item_slot_metadata(
                            command.container_type, index
                        ),
                    )
                else:
                    container.put_plain(
                        index,
                        command.static_id,
                        command.count,
                        replace=False,
                        slot_metadata=new_item_slot_metadata(
                            command.container_type, index
                        ),
                    )
            if creates_dynamic:
                dynamic_items.rebuild_references()

        def validate() -> None:
            for offset, index in enumerate(indices):
                slot = container.get_occupied(index)
                if (
                    slot.static_id != command.static_id
                    or slot.count != command.count
                ):
                    raise DomainError(
                        code="INVARIANT_VIOLATION",
                        message="Batch fill produced an invalid item slot.",
                        http_status=409,
                    )
                if creates_dynamic:
                    record = dynamic_items.get(new_local_ids[offset])
                    if (
                        slot.dynamic_local_id != new_local_ids[offset]
                        or record is None
                        or record.kind != rule.dynamic_kind
                        or record.static_id != record_static_id
                    ):
                        raise DomainError(
                            code="INVARIANT_VIOLATION",
                            message="Batch fill produced an invalid dynamic item record.",
                            http_status=409,
                        )
                elif slot.dynamic_id is not None:
                    raise DomainError(
                        code="INVARIANT_VIOLATION",
                        message="Batch fill retained an unexpected dynamic reference.",
                        http_status=409,
                    )
            if creates_dynamic:
                dynamic_items.assert_consistent()

        entry = self._session.apply_atomic(
            session_id=command.session_id,
            expected_revision=command.expected_revision,
            command="FillItemSlots",
            target={
                "player_id": str(player.PlayerUId),
                "container_type": command.container_type.value,
                "slot_indices": list(indices),
            },
            snapshot=snapshot,
            restore=restore,
            before=lambda: {"empty_slots": list(indices)},
            mutate=mutate,
            validate=validate,
            after=lambda: {
                "slots": [container.slot_summary(index) for index in indices]
            },
            affected_records=(
                "level:ItemContainerSaveData",
                *(("level:DynamicItemSaveData",) if creates_dynamic else ()),
            ),
        )
        return {
            "revision": self._session.revision,
            "change_id": entry.change_id,
            "slots": [container.slot_summary(index) for index in indices],
        }

    def _new_dynamic_local_ids(
        self, dynamic_items, count: int
    ) -> tuple[str, ...]:
        generated: list[str] = []
        seen: set[str] = set()
        attempts = max(128, count * 128)
        for _ in range(attempts):
            if len(generated) == count:
                return tuple(generated)
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
                and normalized not in seen
                and dynamic_items.get(normalized) is None
            ):
                generated.append(normalized)
                seen.add(normalized)
        raise DomainError(
            code="DYNAMIC_ITEM_ID_COLLISION",
            message="Unique dynamic item identifiers could not be generated.",
            http_status=409,
        )
