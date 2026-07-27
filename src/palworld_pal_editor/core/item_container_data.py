from __future__ import annotations

from copy import deepcopy
from typing import Any, Optional

from palworld_save_tools.archive import UUID
from palworld_save_tools.gvas import GvasFile

from palworld_pal_editor.core.pal_objects import PalObjects, toUUID
from palworld_pal_editor.utils import LOGGER


_MISSING_SLOT_SNAPSHOT_KEY = "__pal_editor_missing_slot__"


def _missing_slot_snapshot() -> dict[str, Any]:
    return {_MISSING_SLOT_SNAPSHOT_KEY: True}


def _is_missing_slot_snapshot(snapshot: dict[str, Any]) -> bool:
    return snapshot == {_MISSING_SLOT_SNAPSHOT_KEY: True}


class ItemContainerSlot:
    MIN_COUNT = 1
    MAX_COUNT = 2_147_483_647

    def __init__(self, slot_data: dict) -> None:
        self._slot_data = slot_data
        self._raw_data = slot_data["RawData"]["value"]

    @property
    def slot_index(self) -> int:
        return self._raw_data["slot_index"]

    @property
    def count(self) -> int:
        return self._raw_data["count"]

    @count.setter
    def count(self, value: int) -> None:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("Item count must be an integer")
        if not self.MIN_COUNT <= value <= self.MAX_COUNT:
            raise ValueError(
                f"Item count must be between {self.MIN_COUNT} and {self.MAX_COUNT}"
            )
        self._raw_data["count"] = value

    @property
    def static_id(self) -> str:
        return self._raw_data["item"]["static_id"]

    @property
    def dynamic_id(self) -> Optional[str]:
        created, local = self._dynamic_parts()
        if created is None or local is None:
            return None
        zero = "00000000-0000-0000-0000-000000000000"
        if created == zero and local == zero:
            return None
        return f"{created}/{local}"

    @property
    def dynamic_created_world_id(self) -> Optional[str]:
        created, _local = self._dynamic_parts()
        return created

    @property
    def dynamic_local_id(self) -> Optional[str]:
        _created, local = self._dynamic_parts()
        return local

    def _dynamic_parts(self) -> tuple[Optional[str], Optional[str]]:
        dynamic = self._raw_data.get("item", {}).get("dynamic_id") or {}
        created = dynamic.get("created_world_id")
        local = dynamic.get("local_id_in_created_world")
        return (
            str(created) if created is not None else None,
            str(local) if local is not None else None,
        )


class ItemContainer:
    def __init__(
        self,
        container_obj: dict,
        *,
        default_slot_template: dict[str, Any] | None = None,
    ) -> None:
        self._container_obj = container_obj
        raw_property = container_obj.get("value", {}).get("RawData")
        self._container_raw_data = (
            raw_property.get("value")
            if isinstance(raw_property, dict)
            else None
        )
        self.capacity = PalObjects.get_BaseType(container_obj["value"]["SlotNum"])
        if (
            isinstance(self.capacity, bool)
            or not isinstance(self.capacity, int)
            or self.capacity < 0
        ):
            raise ValueError("Invalid item container capacity")
        slot_values = container_obj["value"]["Slots"]["value"]["values"]
        self._slot_values = slot_values
        self._slot_template = deepcopy(
            slot_values[0] if slot_values else default_slot_template
        )
        self._all_slots: dict[int, ItemContainerSlot] = {}
        self._detached_slots: dict[int, tuple[int, ItemContainerSlot]] = {}
        for value in slot_values:
            slot = ItemContainerSlot(value)
            if slot.slot_index in self._all_slots:
                raise ValueError(f"Duplicate item slot index: {slot.slot_index}")
            if slot.slot_index < 0 or slot.slot_index >= self.capacity:
                raise ValueError(f"Item slot index out of range: {slot.slot_index}")
            self._all_slots[slot.slot_index] = slot
        self.slots = {
            index: slot
            for index, slot in self._all_slots.items()
            if slot.static_id not in ("", "None")
        }

    def _refresh_occupied(self) -> None:
        self.slots = {
            index: slot
            for index, slot in self._all_slots.items()
            if slot.static_id not in ("", "None")
        }

    @property
    def id(self) -> Optional[UUID]:
        return PalObjects.get_BaseType(self._container_obj["key"]["ID"])

    def snapshot_capacity(self) -> int:
        return self.capacity

    def expand_capacity(self, capacity: int) -> None:
        if capacity < self.capacity:
            raise ValueError("Item container capacity cannot be shrunk")
        self._set_capacity(capacity)

    def restore_capacity(self, capacity: int) -> None:
        self._set_capacity(capacity)

    def capacity_matches_declared(self, expected_capacity: int) -> bool:
        slot_num = self._container_obj.get("value", {}).get("SlotNum")
        return (
            self.capacity == expected_capacity
            and isinstance(slot_num, dict)
            and slot_num.get("type") == "IntProperty"
            and slot_num.get("value") == expected_capacity
        )

    def _set_capacity(self, capacity: int) -> None:
        if (
            isinstance(capacity, bool)
            or not isinstance(capacity, int)
            or capacity < 0
        ):
            raise ValueError("Invalid item container capacity")
        if self._all_slots and max(self._all_slots) >= capacity:
            raise ValueError("Item slot index would exceed the new capacity")
        slot_num = self._container_obj.get("value", {}).get("SlotNum")
        if (
            not isinstance(slot_num, dict)
            or slot_num.get("type") != "IntProperty"
            or isinstance(slot_num.get("value"), bool)
            or not isinstance(slot_num.get("value"), int)
        ):
            raise ValueError("Unsupported item container SlotNum encoding")
        slot_num["value"] = capacity
        self.capacity = capacity

    @property
    def dynamic_reference_layout_complete(self) -> bool:
        raw = self._container_raw_data
        permission = raw.get("permission") if isinstance(raw, dict) else None
        return (
            isinstance(permission, dict)
            and isinstance(permission.get("item_categories"), list)
            and isinstance(raw.get("used_dynamic_item_ids"), list)
            and "trailing_unparsed_data" not in raw
        )

    def iter_used_dynamic_item_ids(self):
        raw = self._container_raw_data
        values = raw.get("used_dynamic_item_ids") if isinstance(raw, dict) else None
        if not isinstance(values, list):
            return
        for value in values:
            if not isinstance(value, dict):
                continue
            created = value.get("created_world_id")
            local = value.get("local_id_in_created_world")
            if created is not None and local is not None:
                yield str(created), str(local)

    def set_count(self, slot_index: int, static_id: str, count: int) -> None:
        slot = self.slots.get(slot_index)
        if slot is None:
            raise KeyError(f"Item slot {slot_index} not found")
        if slot.static_id != static_id:
            raise ValueError(
                f"Item slot {slot_index} changed from {static_id} to {slot.static_id}"
            )
        slot.count = count

    def dense_slots(self) -> list[Optional[ItemContainerSlot]]:
        return [
            self.slots.get(slot_index)
            for slot_index in range(self.capacity)
        ]

    def iter_encoded_slots(self):
        for slot_index in sorted(self._all_slots):
            yield self._all_slots[slot_index]

    def iter_occupied_slots(self):
        for slot_index in sorted(self.slots):
            yield self.slots[slot_index]

    def get_occupied(self, slot_index: int) -> ItemContainerSlot:
        slot = self.slots.get(slot_index)
        if slot is None:
            raise KeyError(f"Item slot {slot_index} is empty or does not exist")
        return slot

    def is_empty(self, slot_index: int) -> bool:
        if isinstance(slot_index, bool) or not isinstance(slot_index, int):
            raise TypeError("slot_index must be an integer")
        if slot_index < 0 or slot_index >= self.capacity:
            raise IndexError(f"Item slot index out of range: {slot_index}")
        slot = self._all_slots.get(slot_index)
        return slot is None or (
            slot.static_id in ("", "None") and slot.dynamic_id is None
        )

    def get_raw_slot(self, slot_index: int) -> ItemContainerSlot:
        if isinstance(slot_index, bool) or not isinstance(slot_index, int):
            raise TypeError("slot_index must be an integer")
        if slot_index < 0 or slot_index >= self.capacity:
            raise IndexError(f"Item slot index out of range: {slot_index}")
        slot = self._all_slots.get(slot_index)
        if slot is None:
            raise KeyError(f"Raw item slot {slot_index} is not encoded in the save")
        return slot

    def snapshot_slot(self, slot_index: int) -> dict[str, Any]:
        self.is_empty(slot_index)
        slot = self._all_slots.get(slot_index)
        if slot is None:
            return _missing_slot_snapshot()
        return deepcopy(slot._raw_data)

    def restore_slot(self, slot_index: int, snapshot: dict[str, Any]) -> None:
        self.is_empty(slot_index)
        if _is_missing_slot_snapshot(snapshot):
            self._remove_encoded_slot(slot_index, detach=False)
            self._detached_slots.pop(slot_index, None)
            self._refresh_occupied()
            return
        slot = self._all_slots.get(slot_index)
        if slot is None:
            detached = self._detached_slots.pop(slot_index, None)
            if detached is not None:
                position, slot = detached
                self._slot_values.insert(
                    min(position, len(self._slot_values)), slot._slot_data
                )
                self._all_slots[slot_index] = slot
            else:
                slot = self._create_slot(slot_index, snapshot)
        raw = slot._raw_data
        raw.clear()
        raw.update(deepcopy(snapshot))
        self._refresh_occupied()

    def snapshot_all(self) -> dict[int, dict[str, Any]]:
        return {
            index: self.snapshot_slot(index)
            for index in range(self.capacity)
        }

    def restore_all(self, snapshots: dict[int, dict[str, Any]]) -> None:
        if set(snapshots) != set(range(self.capacity)):
            raise ValueError("Item container snapshot does not match its capacity")
        for index, snapshot in snapshots.items():
            self.restore_slot(index, snapshot)
        self._refresh_occupied()

    def replace_slot_payload(
        self,
        slot_index: int,
        snapshot: dict[str, Any],
        *,
        dynamic_local_id: str | None = None,
        dynamic_created_world_id: str | None = None,
        slot_metadata: dict[str, Any] | None = None,
    ) -> None:
        if not self.is_empty(slot_index):
            raise ValueError("Target item slot is not empty")
        value = deepcopy(snapshot)
        value["slot_index"] = slot_index
        if dynamic_local_id is not None:
            value["item"]["dynamic_id"]["local_id_in_created_world"] = toUUID(
                dynamic_local_id
            )
        if dynamic_created_world_id is not None:
            value["item"]["dynamic_id"]["created_world_id"] = toUUID(
                dynamic_created_world_id
            )
        target = self._all_slots.get(slot_index)
        if target is None:
            if slot_metadata is None:
                raise ValueError("New sparse item slots require verified metadata")
            value.update(deepcopy(slot_metadata))
            target = self._create_slot(slot_index, value)
        target._raw_data.clear()
        target._raw_data.update(value)
        self._refresh_occupied()

    def reorder_payloads(
        self,
        source_indices: list[int],
        *,
        target_slot_metadata: dict[int, dict[str, Any]] | None = None,
    ) -> None:
        targets = list(range(self.capacity))
        if len(source_indices) != len(targets) or set(source_indices) != set(targets):
            raise ValueError("Item slot reorder must be a complete permutation")
        snapshots = self.snapshot_all()
        for target_index, source_index in zip(targets, source_indices):
            source = snapshots[source_index]
            if _is_missing_slot_snapshot(source):
                self._remove_encoded_slot(target_index, detach=False)
                continue
            value = deepcopy(source)
            value["slot_index"] = target_index
            if target_slot_metadata is not None:
                metadata = target_slot_metadata.get(target_index)
                if metadata is not None:
                    value["permission"] = deepcopy(metadata["permission"])
                    value["trailing_bytes"] = deepcopy(metadata["trailing_bytes"])
            target = self._all_slots.get(target_index)
            if target is None:
                self._create_slot(target_index, value)
            else:
                target._raw_data.clear()
                target._raw_data.update(value)
        self._refresh_occupied()

    def slot_summary(self, slot_index: int) -> dict[str, Any]:
        slot = self.get_occupied(slot_index)
        return {
            "slot_index": slot.slot_index,
            "static_id": slot.static_id,
            "count": slot.count,
            "dynamic_id": slot.dynamic_id,
        }

    def put_plain(
        self,
        slot_index: int,
        static_id: str,
        count: int,
        *,
        replace: bool,
        slot_metadata: dict[str, Any] | None = None,
    ) -> None:
        occupied = not self.is_empty(slot_index)
        slot = self._all_slots.get(slot_index)
        if occupied and not replace:
            raise ValueError("Item slot is already occupied")
        if occupied and slot is not None and slot.dynamic_id is not None:
            raise ValueError("Dynamic item replacement requires lifecycle handling")
        if not occupied and slot is not None and slot.dynamic_id is not None:
            raise ValueError("Empty item slot has a dynamic reference")
        if slot is None:
            if slot_metadata is None:
                raise ValueError("New sparse item slots require verified metadata")
            zero = toUUID("00000000-0000-0000-0000-000000000000")
            slot = self._create_slot(
                slot_index,
                {
                    "slot_index": slot_index,
                    "count": count,
                    "item": {
                        "static_id": static_id,
                        "dynamic_id": {
                            "created_world_id": zero,
                            "local_id_in_created_world": zero,
                        },
                    },
                    **deepcopy(slot_metadata),
                },
            )
        slot._raw_data["item"]["static_id"] = static_id
        slot._raw_data["count"] = count
        self._refresh_occupied()

    def put_dynamic_reference(
        self,
        slot_index: int,
        static_id: str,
        count: int,
        *,
        created_world_id: str,
        local_id: str,
        slot_metadata: dict[str, Any] | None = None,
        replace: bool = False,
    ) -> None:
        if not self.is_empty(slot_index) and not replace:
            raise ValueError("Target item slot is not empty")
        slot = self._all_slots.get(slot_index)
        if slot is None:
            if slot_metadata is None:
                raise ValueError("New sparse item slots require verified metadata")
            zero = toUUID("00000000-0000-0000-0000-000000000000")
            slot = self._create_slot(
                slot_index,
                {
                    "slot_index": slot_index,
                    "count": count,
                    "item": {
                        "static_id": static_id,
                        "dynamic_id": {
                            "created_world_id": zero,
                            "local_id_in_created_world": zero,
                        },
                    },
                    **deepcopy(slot_metadata),
                },
            )
        slot._raw_data["item"]["static_id"] = static_id
        slot._raw_data["item"]["dynamic_id"]["created_world_id"] = toUUID(
            created_world_id
        )
        slot._raw_data["item"]["dynamic_id"]["local_id_in_created_world"] = (
            toUUID(local_id)
        )
        slot._raw_data["count"] = count
        self._refresh_occupied()

    def replace_dynamic_reference_with_plain(
        self,
        slot_index: int,
        static_id: str,
        count: int,
    ) -> None:
        slot = self.get_occupied(slot_index)
        if slot.dynamic_id is None:
            raise ValueError("The target slot does not contain a dynamic reference")
        zero = toUUID("00000000-0000-0000-0000-000000000000")
        slot._raw_data["item"]["static_id"] = static_id
        slot._raw_data["item"]["dynamic_id"]["created_world_id"] = zero
        slot._raw_data["item"]["dynamic_id"]["local_id_in_created_world"] = zero
        slot._raw_data["count"] = count
        self._refresh_occupied()

    def clear_plain(self, slot_index: int) -> None:
        target = self.get_occupied(slot_index)
        if target.dynamic_id is not None:
            raise ValueError("Dynamic item clearing requires lifecycle handling")
        self._clear_using_verified_template(slot_index)

    def clear_dynamic(self, slot_index: int) -> None:
        target = self.get_occupied(slot_index)
        if target.dynamic_id is None:
            raise ValueError("Item slot does not contain a dynamic item")
        self._clear_using_verified_template(slot_index)

    def _clear_using_verified_template(self, slot_index: int) -> None:
        self.get_occupied(slot_index)
        self._remove_encoded_slot(slot_index, detach=True)
        self._refresh_occupied()

    def _remove_encoded_slot(self, slot_index: int, *, detach: bool) -> None:
        target = self._all_slots.get(slot_index)
        if target is None:
            return
        position = self._slot_values.index(target._slot_data)
        self._slot_values.pop(position)
        self._all_slots.pop(slot_index)
        if detach:
            self._detached_slots[slot_index] = (position, target)
        else:
            self._detached_slots.pop(slot_index, None)

    def _create_slot(
        self, slot_index: int, raw_payload: dict[str, Any]
    ) -> ItemContainerSlot:
        if self._slot_template is None:
            raise LookupError(
                "No verified item slot property envelope is available in this save"
            )
        if slot_index in self._all_slots:
            raise ValueError(f"Item slot {slot_index} is already encoded")
        slot_data = deepcopy(self._slot_template)
        raw_property = slot_data.get("RawData")
        if not isinstance(raw_property, dict) or "value" not in raw_property:
            raise ValueError("Item slot template has no RawData property")
        raw_property["value"] = deepcopy(raw_payload)
        slot = ItemContainerSlot(slot_data)
        if slot.slot_index != slot_index:
            raise ValueError("New item slot payload index does not match its target")
        position = next(
            (
                index
                for index, value in enumerate(self._slot_values)
                if ItemContainerSlot(value).slot_index > slot_index
            ),
            len(self._slot_values),
        )
        self._slot_values.insert(position, slot_data)
        self._all_slots[slot_index] = slot
        self._detached_slots.pop(slot_index, None)
        return slot


class ItemContainerData:
    def __init__(self, gvas_file: GvasFile) -> None:
        world_save_data = gvas_file.properties["worldSaveData"]["value"]
        container_property = world_save_data.get("ItemContainerSaveData")
        self.container_map: dict[str, ItemContainer] = {}
        if not container_property:
            LOGGER.info("No Item Container Found")
            return
        container_values = container_property["value"]
        default_slot_template = next(
            (
                deepcopy(slot_value)
                for container_obj in container_values
                for slot_value in container_obj["value"]["Slots"]["value"]["values"]
            ),
            None,
        )
        for container_obj in container_values:
            container = ItemContainer(
                container_obj,
                default_slot_template=default_slot_template,
            )
            if container.id is not None:
                if str(container.id) in self.container_map:
                    raise ValueError(f"Duplicate item container id: {container.id}")
                self.container_map[str(container.id)] = container

    def get(self, container_id: UUID | str) -> Optional[ItemContainer]:
        return self.container_map.get(str(container_id))

    def iter_occupied_slots(self):
        for container_id in sorted(self.container_map):
            container = self.container_map[container_id]
            for slot in container.iter_occupied_slots():
                yield container_id, slot

    @property
    def dynamic_reference_layout_complete(self) -> bool:
        return all(
            container.dynamic_reference_layout_complete
            for container in self.container_map.values()
        )

    def iter_used_dynamic_item_ids(self):
        for container_id in sorted(self.container_map):
            container = self.container_map[container_id]
            for created_world_id, local_id in container.iter_used_dynamic_item_ids():
                yield container_id, created_world_id, local_id
