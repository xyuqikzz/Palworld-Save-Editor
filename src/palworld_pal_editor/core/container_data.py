import heapq
from copy import deepcopy
from typing import Optional
from palworld_save_tools.gvas import GvasFile
from palworld_save_tools.archive import UUID

from palworld_pal_editor.core.pal_objects import PalObjects, toUUID
from palworld_pal_editor.utils import LOGGER


class PalContainer:
    def __init__(self, container_obj: dict) -> None:
        self._container_obj: dict = container_obj

        self._slots_data: list = PalObjects.get_ArrayProperty(
            self._container_obj["value"]["Slots"]
        )

        if self.ID is None or self._slots_data is None:
            raise Exception("Invalid Container")

        self.size: int = PalObjects.get_BaseType(self._container_obj["value"]["SlotNum"])
        if isinstance(self.size, bool) or not isinstance(self.size, int) or self.size < 0:
            raise Exception(f"Container {self.ID} Size Unknown")
        self._rebuild_index()


    def __len__(self):
        return len(self.slots)
    
    def __str__(self) -> str:
        return f"{self.ID} - {len(self)}"

    @property
    def ID(self) -> Optional[UUID]:
        return PalObjects.get_BaseType(self._container_obj.get("key", {}).get("ID"))

    def _rebuild_index(self) -> None:
        self.slots = [ContainerSlot(slot_dict) for slot_dict in self._slots_data]
        available = set(range(self.size))
        seen_instances: set[str] = set()
        for slot in self.slots:
            if slot.inv_idx not in available:
                raise ValueError(
                    f"Duplicate or out-of-range character slot: {slot.inv_idx}"
                )
            available.remove(slot.inv_idx)
            instance_id = str(slot.instance_id)
            if instance_id in seen_instances:
                raise ValueError(
                    f"Duplicate Pal instance in character container: {instance_id}"
                )
            seen_instances.add(instance_id)
        self.available_inv_idx_set = list(available)
        heapq.heapify(self.available_inv_idx_set)

    def snapshot(self) -> list[dict]:
        return deepcopy(self._slots_data)

    def restore(self, snapshot: list[dict]) -> None:
        self._slots_data[:] = deepcopy(snapshot)
        self._rebuild_index()

    def _new_slot(self, target_inv_idx: int | None = None) -> Optional[int]:
        slotidx = self.get_empty_slot()
        if slotidx == -1:
            return
        inv_slot = self.get_empty_inv_slot(target_inv_idx)
        if inv_slot == -1:
            return
        self._slots_data.append(PalObjects.ContainerSlotData(inv_slot))
        return slotidx

    def _del_slot(self, slotidx: int):
        if slotidx >= len(self._slots_data):
            return
        slot = self._slots_data.pop(slotidx)
        heapq.heappush(self.available_inv_idx_set, PalObjects.get_BaseType(slot.get("SlotIndex")))

    def add_pal(
        self, pal_id: UUID | str, target_inv_idx: int | None = None
    ) -> int:
        if self.has_pal(pal_id):
            return -1
        
        if (slot_idx := self._new_slot(target_inv_idx)) is None:
            return -1
        
        slot = ContainerSlot(self._slots_data[slot_idx])
        slot.instance_id = pal_id
        self.slots.append(slot)

        LOGGER.info(f"Pal {pal_id} add to container {self.ID} @ {slot.inv_idx} ")
        return slot.inv_idx

    def del_pal(self, pal_id: UUID):
        slot_idx = self.get_pal_idx(pal_id)
        if slot_idx is None or slot_idx < 0:
            LOGGER.warning(
                    f"Can't find PalID on del_pal: {str(pal_id)}."
                )
            return
        if not self.has_pal(pal_id, slot_idx):
            if slot_idx < len(self.slots):
                LOGGER.warning(
                    f"Unmatched Pal Guid on del_pal: expect {str(self.slots[slot_idx].instance_id)} got {str(pal_id)}."
                )
            return

        self.slots[slot_idx].clear() # unnecessary since 0.3.3
        self.slots.pop(slot_idx)
        self._del_slot(slot_idx)
        

    def get_pal_idx(self, pal_id: UUID | str) -> Optional[int]:
        for i in range(0, len(self.slots)):
            if str(self.slots[i].instance_id) == str(pal_id):
                return i
        return None

    def has_pal(self, pal_id: UUID | str, slot_idx: Optional[int] = None) -> bool:
        if slot_idx is not None:
            if slot_idx >= len(self.slots):
                return False
            return str(self.slots[slot_idx].instance_id) == str(pal_id)
        else:
            for slot in self.slots:
                if str(slot.instance_id) == str(pal_id):
                    return True
            return False

    # def reorder_pals(self, pal_ids: list[UUID | str]):
    #     id_num = len(pal_ids)
    #     for i in range(0, len(self.slots)):
    #         slot = self.slots[i]
    #         if i < id_num:
    #             slot.instance_id = pal_ids[i]
    #         else:
    #             slot.clear()

    def get_empty_slot(self) -> int:
        """
        Return: slot idx, or -1 if full
        """
        # for i in range(0, len(self.slots)):
        #     if self.slots[i].isEmpty:
        #         return i
        # return -1
        if len(self.slots) < self.size:
            return len(self.slots)
        return -1
    
    def get_empty_inv_slot(self, target_inv_idx: int | None = None) -> int:
        if target_inv_idx is not None:
            if (
                isinstance(target_inv_idx, bool)
                or not isinstance(target_inv_idx, int)
                or target_inv_idx < 0
                or target_inv_idx >= self.size
                or target_inv_idx not in self.available_inv_idx_set
            ):
                return -1
            self.available_inv_idx_set.remove(target_inv_idx)
            heapq.heapify(self.available_inv_idx_set)
            return target_inv_idx
        if self.available_inv_idx_set:
            return heapq.heappop(self.available_inv_idx_set)
        return -1


class ContainerSlot:
    def __init__(self, slot_data: dict) -> None:
        self._slot_data: dict = slot_data
        self._slot_raw_data: dict = slot_data["RawData"]["value"]

    # def __eq__(self, __value: object) -> bool:
    #     if not isinstance(__value, ContainerSlot):
    #         return False
    #     return UUID.__eq__(self.instance_id, __value.instance_id)

    # def __hash__(self) -> int:
    #     return hash(str(self.instance_id))

    @property
    def isEmpty(self) -> bool:
        id = self.instance_id or PalObjects.EMPTY_UUID
        return id == PalObjects.EMPTY_UUID

    @property
    def instance_id(self) -> Optional[UUID]:
        return self._slot_raw_data.get("instance_id")

    @property
    def inv_idx(self) -> int:
        return PalObjects.get_BaseType(self._slot_data.get('SlotIndex'))

    @instance_id.setter
    def instance_id(self, id: UUID | str):
        self._slot_raw_data["instance_id"] = toUUID(id)

    def clear(self):
        self.instance_id = PalObjects.EMPTY_UUID


class ContainerData:
    def __init__(self, gvas_file: GvasFile) -> None:
        self.container_map = {}

        self._wsd = gvas_file.properties["worldSaveData"]["value"]
        if "CharacterContainerSaveData" not in self._wsd:
            LOGGER.info("No Container Found")
            return
        self._CCSD: dict = self._wsd["CharacterContainerSaveData"]

        for container in self._CCSD["value"]:
            try:
                container_entity = PalContainer(container)
            except Exception as e:
                raise ValueError(f"Invalid character container: {e}") from e

            key = str(container_entity.ID)
            if key in self.container_map:
                raise ValueError(f"Duplicate character container id: {key}")
            self.container_map[key] = container_entity
            LOGGER.info(f"Container Found: {container_entity}")

    def get_container(self, id: UUID | str) -> Optional[PalContainer]:
        return self.container_map.get(str(id))

    def get_containers(self) -> list[PalContainer]:
        return self.container_map.values()
