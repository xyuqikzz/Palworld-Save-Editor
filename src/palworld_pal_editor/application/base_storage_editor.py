from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Callable
import uuid

from palworld_pal_editor.core.base_storage_data import BaseStorageBinding
from palworld_pal_editor.domain.commands import (
    ClearBaseStorageItemSlot,
    ClearItemSlot,
    PutBaseStorageItem,
    PutItem,
    UpdateBaseStorageItemCount,
    UpdateItemCount,
)
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.domain.item_catalog import ItemCatalog
from palworld_pal_editor.domain.models import (
    ItemContainerType,
    ItemSlotView,
)
from palworld_pal_editor.utils.data_provider import DataProvider

from .inventory_editor import InventoryEditor
from .save_session import SaveSession


BASE_STORAGE_TECH_BY_MAP_OBJECT = {
    "container01_iron": "FurnitureSet_6",
    "coolerbox": "CoolerBox",
    "coolerpalfoodbox": "CoolerPalFoodBox",
    "guildchest": "GuildChest",
    "itembooth": "ItemBooth",
    "itemchest": "Infra_ItemChest_Grade_01",
    "itemchest_02": "Infra_ItemChest_Grade_02",
    "itemchest_03": "Infra_ItemChest_Grade_03",
    "itemchest_04": "ItemChest_04",
    "palbooth": "PalBooth",
    "palfoodbox": "PalFoodBox",
    "palmedicinebox": "PalMedicineBox",
    "refrigerator": "Refrigerator",
}


class BaseStorageEditor:
    """Guild/base-scoped view and revision-bound item slot mutations."""

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

    def get_storage(self, guild_id: str, base_id: str) -> dict[str, Any]:
        self._require_owned_base(guild_id, base_id)
        index = self._require_index()
        containers = [
            self._container_view(binding)
            for binding in index.get_base(guild_id, base_id)
        ]
        return {
            "revision": self._session.revision,
            "guild_id": str(guild_id),
            "base_id": str(base_id),
            "status": "available" if index.complete else "read_only",
            "write_status": (
                "available" if index.complete else "index_incomplete"
            ),
            "reason": (
                None
                if index.complete
                else "BASE_STORAGE_INDEX_INCOMPLETE"
            ),
            "issues": [issue.to_dict() for issue in index.issues()],
            "containers": containers,
        }

    def execute(
        self,
        command: (
            UpdateBaseStorageItemCount
            | PutBaseStorageItem
            | ClearBaseStorageItemSlot
        ),
    ) -> dict[str, Any]:
        if (
            not isinstance(command.container_id, str)
            or not command.container_id
        ):
            raise DomainError(
                code="INVALID_FIELD_TYPE",
                message="container_id must be a non-empty string.",
                field="container_id",
                http_status=400,
            )
        if (
            isinstance(command.slot_index, bool)
            or not isinstance(command.slot_index, int)
        ):
            raise DomainError(
                code="INVALID_FIELD_TYPE",
                message="slot_index must be an integer.",
                field="slot_index",
                http_status=400,
            )
        self._session.require_command(
            command.session_id, command.expected_revision
        )
        self._require_owned_base(command.guild_id, command.base_id)
        binding, container = self._require_binding(
            command.guild_id,
            command.base_id,
            command.container_id,
        )
        adapter = _BaseStorageInventoryAdapter(
            self._session,
            binding=binding,
            container=container,
            catalog=self._catalog,
            locale=self._locale,
            id_factory=self._id_factory,
        )
        common = {
            "session_id": command.session_id,
            "expected_revision": command.expected_revision,
            "player_id": command.guild_id,
            "container_type": ItemContainerType.BASE_STORAGE,
            "slot_index": command.slot_index,
        }
        if isinstance(command, UpdateBaseStorageItemCount):
            result = adapter.execute(
                UpdateItemCount(
                    **common,
                    expected_static_id=command.expected_static_id,
                    count=command.count,
                )
            )
        elif isinstance(command, PutBaseStorageItem):
            result = adapter.execute(
                PutItem(
                    **common,
                    static_id=command.static_id,
                    count=command.count,
                    mode=command.mode,
                    dynamic_init=command.dynamic_init,
                )
            )
        elif isinstance(command, ClearBaseStorageItemSlot):
            result = adapter.execute(
                ClearItemSlot(
                    **common,
                    expected_static_id=command.expected_static_id,
                    expected_dynamic_id=command.expected_dynamic_id,
                )
            )
        else:
            raise DomainError(
                code="UNSUPPORTED_COMMAND",
                message="Unsupported base storage command.",
                http_status=400,
            )
        result.update(
            {
                "guild_id": str(command.guild_id),
                "base_id": str(command.base_id),
                "container_id": str(command.container_id),
            }
        )
        return result

    def _require_owned_base(self, guild_id: str, base_id: str):
        manager = self._session.manager
        group_data = getattr(manager, "group_data", None)
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
        camp_data = getattr(manager, "camp_data", None)
        camp = (
            camp_data.get_camp(base_id)
            if camp_data is not None
            else None
        )
        if camp is None:
            raise DomainError(
                code="BASE_CAMP_NOT_FOUND",
                message="Base camp not found.",
                field="base_id",
                details={"base_id": str(base_id)},
                http_status=404,
            )
        if str(camp.owner_group_id).casefold() != str(guild_id).casefold():
            raise DomainError(
                code="BASE_CAMP_OWNERSHIP_VIOLATION",
                message="The base camp does not belong to this guild.",
                field="base_id",
                details={
                    "guild_id": str(guild_id),
                    "base_id": str(base_id),
                },
                http_status=409,
            )
        return camp

    def _require_index(self):
        manager = self._session.manager
        error_type = getattr(manager, "base_storage_error", None)
        if error_type:
            raise DomainError(
                code="BASE_STORAGE_UNSUPPORTED",
                message="This save's base storage mapping is not supported.",
                details={"error_type": error_type},
                http_status=409,
            )
        index = getattr(manager, "base_storage_data", None)
        if index is None:
            raise DomainError(
                code="BASE_STORAGE_UNSUPPORTED",
                message="Base storage mapping is unavailable.",
                http_status=409,
            )
        return index

    def _require_binding(
        self,
        guild_id: str,
        base_id: str,
        container_id: str,
    ) -> tuple[BaseStorageBinding, Any]:
        index = self._require_index()
        if not index.complete:
            raise DomainError(
                code="BASE_STORAGE_INDEX_INCOMPLETE",
                message=(
                    "Base storage writes are disabled because the map object "
                    "index is incomplete."
                ),
                details={
                    "issues": [issue.to_dict() for issue in index.issues()]
                },
                http_status=409,
            )
        binding = index.resolve(guild_id, base_id, container_id)
        if binding is None:
            raise DomainError(
                code="BASE_STORAGE_OWNERSHIP_VIOLATION",
                message=(
                    "The item container is not a persistent storage object "
                    "owned by this guild base."
                ),
                field="container_id",
                details={
                    "guild_id": str(guild_id),
                    "base_id": str(base_id),
                    "container_id": str(container_id),
                },
                http_status=409,
            )
        containers = getattr(
            self._session.manager, "item_container_data", None
        )
        container = (
            containers.get(binding.container_id)
            if containers is not None
            else None
        )
        if container is None:
            raise DomainError(
                code="BASE_STORAGE_CONTAINER_MISSING",
                message="The base storage container is missing from this save.",
                details={"container_id": str(container_id)},
                http_status=409,
            )
        return binding, container

    def _container_view(
        self, binding: BaseStorageBinding
    ) -> dict[str, Any]:
        containers = getattr(
            self._session.manager, "item_container_data", None
        )
        container = (
            containers.get(binding.container_id)
            if containers is not None
            else None
        )
        base = {
            "container_id": str(binding.container_id),
            "map_object_instance_id": str(binding.map_object_instance_id),
            "map_object_type": binding.map_object_type,
            "building_name": self._building_name(binding.map_object_type),
            "usage_type": binding.usage_type,
            "location": binding.location,
        }
        if container is None:
            return {
                **base,
                "status": "unavailable",
                "reason": "BASE_STORAGE_CONTAINER_MISSING",
                "capacity": None,
                "slots": [],
            }
        return {
            **base,
            "status": "available",
            "reason": None,
            "capacity": container.capacity,
            "slots": [
                self._slot_payload(slot_index, slot)
                for slot_index, slot in enumerate(container.dense_slots())
            ],
        }

    def _building_name(self, map_object_type: str) -> str | None:
        tech_key = BASE_STORAGE_TECH_BY_MAP_OBJECT.get(
            map_object_type.casefold()
        )
        if tech_key is None:
            return None
        localized = (
            DataProvider.get_tech_data()
            .get(tech_key, {})
            .get("I18n", {})
        )
        row = localized.get(self._locale) or localized.get("en")
        if not isinstance(row, dict):
            return None
        name = row.get("Name")
        return name if isinstance(name, str) and name else None

    def _slot_payload(self, slot_index: int, slot) -> dict[str, Any]:
        payload = self._slot_view(slot_index, slot).to_dict()
        if payload["state"] != "occupied":
            return payload
        catalog_entry = self._catalog.get_optional(slot.static_id)
        payload["item"]["max_stack"] = (
            catalog_entry.max_stack
            if catalog_entry is not None
            else None
        )
        return payload

    def _slot_view(self, slot_index: int, slot) -> ItemSlotView:
        if slot is None:
            return ItemSlotView(slot_index=slot_index, state="empty")
        catalog_entry = self._catalog.get_optional(slot.static_id)
        dynamic_items = getattr(
            self._session.manager, "dynamic_item_data", None
        )
        return ItemSlotView(
            slot_index=slot_index,
            state="occupied",
            static_id=slot.static_id,
            count=slot.count,
            dynamic_id=slot.dynamic_id,
            dynamic_kind=(
                dynamic_items.kind_for_slot(slot)
                if slot.dynamic_id is not None and dynamic_items is not None
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
            rarity=catalog_entry.rarity if catalog_entry else None,
            icon=catalog_entry.icon if catalog_entry else None,
        )


class _BaseStorageInventoryAdapter(InventoryEditor):
    """Reuse the verified item/dynamic lifecycle with a base-owned target."""

    def __init__(
        self,
        session: SaveSession,
        *,
        binding: BaseStorageBinding,
        container: Any,
        catalog: ItemCatalog,
        locale: str,
        id_factory: Callable[[], Any],
    ) -> None:
        super().__init__(
            session,
            catalog,
            locale=locale,
            id_factory=id_factory,
        )
        self._binding = binding
        self._container = container

    def _resolve_owned_container(
        self, player_id: str, container_type: ItemContainerType
    ):
        if (
            container_type is not ItemContainerType.BASE_STORAGE
            or str(player_id).casefold()
            != str(self._binding.guild_id).casefold()
            or str(self._container.id).casefold()
            != str(self._binding.container_id).casefold()
        ):
            raise DomainError(
                code="BASE_STORAGE_OWNERSHIP_VIOLATION",
                message="The base storage mutation target changed.",
                http_status=409,
            )
        return (
            SimpleNamespace(PlayerUId=self._binding.guild_id),
            self._container,
        )

    @staticmethod
    def _change_command_name(command: str) -> str:
        return {
            "UpdateItemCount": "UpdateBaseStorageItemCount",
            "PutItem": "PutBaseStorageItem",
            "ClearItemSlot": "ClearBaseStorageItemSlot",
            "ClearDynamicItemSlot": "ClearBaseStorageDynamicItemSlot",
        }[command]

    def _change_target(
        self, player, container, command, **extra: Any
    ) -> dict[str, Any]:
        return {
            "guild_id": str(self._binding.guild_id),
            "base_id": str(self._binding.base_id),
            "container_id": str(self._binding.container_id),
            "map_object_instance_id": str(
                self._binding.map_object_instance_id
            ),
            "container_type": ItemContainerType.BASE_STORAGE.value,
            "slot_index": command.slot_index,
            **extra,
        }
