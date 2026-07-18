from __future__ import annotations

from copy import deepcopy
import math
from typing import Any

from palworld_pal_editor.domain.commands import UpdateDynamicItemAttributes
from palworld_pal_editor.domain.errors import DomainError

from .inventory_editor import InventoryEditor
from .save_session import SaveSession


class DynamicAttributeEditor:
    """Explicit public fields over present, verified dynamic-record keys."""

    SCHEMAS = {
        "weapon": {
            "durability": ("durability", "number"),
            "ammo": ("remaining_bullets", "integer"),
            "passive_traits": ("passive_skill_list", "string_list"),
        },
        "armor": {
            "durability": ("durability", "number"),
            "passive_traits": ("passive_skill_list", "string_list"),
        },
        "accessory": {
            "passive_traits": ("passive_skill_list", "string_list"),
        },
        "shield": {"durability": ("durability", "number")},
        "glider": {"durability": ("durability", "number")},
        "food": {"freshness": ("remaining_time", "number")},
        "egg": {},
    }

    def __init__(self, session: SaveSession) -> None:
        self._session = session

    def get_attributes(
        self,
        *,
        player_id: str,
        container_type,
        slot_index: int,
    ) -> dict[str, Any]:
        _player, _container, _slot, record = self._resolve(
            player_id, container_type, slot_index, None, None
        )
        return self._attribute_view(record)

    def _attribute_view(self, record) -> dict[str, Any]:
        schema = self.SCHEMAS.get(record.kind)
        if schema is None:
            raise DomainError(
                code="DYNAMIC_ITEM_TYPE_READ_ONLY",
                message="This dynamic item type is preserved as read-only.",
                details={"dynamic_kind": record.kind},
            )
        attributes = {
            public_name: deepcopy(record.raw_data[raw_name])
            for public_name, (raw_name, _value_type) in schema.items()
            if raw_name in record.raw_data
        }
        return {
            "dynamic_kind": record.kind,
            "static_id": record.static_id,
            "attributes": attributes,
            "writable_fields": sorted(attributes),
        }

    def execute(self, command: UpdateDynamicItemAttributes) -> dict[str, Any]:
        self._session.require_command(
            command.session_id, command.expected_revision
        )
        player, _container, slot, record = self._resolve(
            command.player_id,
            command.container_type,
            command.slot_index,
            command.expected_static_id,
            command.expected_dynamic_id,
        )
        return self._execute_resolved(
            session_id=command.session_id,
            expected_revision=command.expected_revision,
            command_name="UpdateDynamicItemAttributes",
            target={
                "player_id": str(player.PlayerUId),
                "container_type": command.container_type.value,
                "slot_index": command.slot_index,
                "fields": sorted(command.values),
                "dynamic_kind": record.kind,
            },
            slot=slot,
            record=record,
            values=command.values,
            affected_records=("level:DynamicItemSaveData",),
        )

    def _execute_resolved(
        self,
        *,
        session_id: str,
        expected_revision: int,
        command_name: str,
        target: dict[str, Any],
        slot,
        record,
        values: dict[str, Any],
        affected_records: tuple[str, ...],
    ) -> dict[str, Any]:
        schema = self.SCHEMAS.get(record.kind)
        if schema is None:
            raise DomainError(
                code="DYNAMIC_ITEM_TYPE_READ_ONLY",
                message="This dynamic item type is preserved as read-only.",
                details={"dynamic_kind": record.kind},
            )
        if not values:
            raise DomainError(
                code="EMPTY_COMMAND",
                message="At least one dynamic attribute is required.",
                http_status=400,
            )
        unknown = sorted(set(values) - set(schema))
        if unknown:
            raise DomainError(
                code="UNSUPPORTED_COMMAND_FIELD",
                message="The dynamic item command contains unsupported fields.",
                details={"fields": unknown, "dynamic_kind": record.kind},
                http_status=400,
            )
        normalized = {}
        for public_name, value in values.items():
            raw_name, value_type = schema[public_name]
            if raw_name not in record.raw_data:
                raise DomainError(
                    code="DYNAMIC_ATTRIBUTE_MISSING",
                    message="This save record does not contain the requested attribute.",
                    field=public_name,
                    details={
                        "dynamic_kind": record.kind,
                        "attribute": public_name,
                    },
                )
            normalized[raw_name] = self._validate_value(
                public_name, value, value_type
            )
        before = self._attribute_view(record)
        dynamic_items = self._session.manager.dynamic_item_data

        def restore(snapshot) -> None:
            record.raw_data.clear()
            record.raw_data.update(deepcopy(snapshot))
            dynamic_items._rebuild_records()
            dynamic_items.rebuild_references()

        def mutate() -> None:
            for raw_name, value in normalized.items():
                record.raw_data[raw_name] = deepcopy(value)

        def validate() -> None:
            current = dynamic_items.require_writable_reference(slot)
            if current.local_id != record.local_id:
                raise DomainError(
                    code="INVARIANT_VIOLATION",
                    message="The dynamic item identity changed during editing.",
                    http_status=409,
                )
            dynamic_items.assert_consistent()

        entry = self._session.apply_atomic(
            session_id=session_id,
            expected_revision=expected_revision,
            command=command_name,
            target=target,
            snapshot=lambda: deepcopy(record.raw_data),
            restore=restore,
            before=lambda: before,
            mutate=mutate,
            validate=validate,
            after=lambda: self._attribute_view(record),
            affected_records=affected_records,
        )
        return {
            "revision": self._session.revision,
            "change_id": entry.change_id,
            "dynamic_item": self._attribute_view(record),
        }

    def _resolve(
        self,
        player_id,
        container_type,
        slot_index,
        expected_static_id,
        expected_dynamic_id,
    ):
        player, container = InventoryEditor(
            self._session
        )._resolve_owned_container(player_id, container_type)
        slot, record = self._resolve_slot(
            container,
            slot_index,
            expected_static_id,
            expected_dynamic_id,
        )
        return player, container, slot, record

    def _resolve_slot(
        self,
        container,
        slot_index,
        expected_static_id,
        expected_dynamic_id,
    ):
        try:
            slot = container.get_occupied(slot_index)
        except KeyError as error:
            raise DomainError(
                code="ITEM_SLOT_EMPTY",
                message="The selected item slot is empty.",
                field="slot_index",
                http_status=404,
            ) from error
        if expected_static_id is not None and slot.static_id != expected_static_id:
            raise DomainError(
                code="STALE_SLOT",
                message="The item slot changed; reload before retrying.",
                retryable=True,
                http_status=409,
            )
        if expected_dynamic_id is not None and slot.dynamic_id != expected_dynamic_id:
            raise DomainError(
                code="STALE_SLOT",
                message="The dynamic item identity changed; reload before retrying.",
                retryable=True,
                http_status=409,
            )
        dynamic_items = getattr(self._session.manager, "dynamic_item_data", None)
        if dynamic_items is None:
            raise DomainError(
                code="DYNAMIC_ITEM_INDEX_UNAVAILABLE",
                message="Dynamic item data is not indexed for this save.",
            )
        record = dynamic_items.require_writable_reference(slot)
        return slot, record

    @staticmethod
    def _validate_value(field: str, value: Any, value_type: str):
        if value_type == "number":
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
                or value > 3.402823466e38
            ):
                raise DomainError(
                    code="INVALID_DYNAMIC_ATTRIBUTE",
                    message=f"{field} must be a non-negative finite number.",
                    field=field,
                    http_status=400,
                )
            return value
        if value_type == "integer":
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
                or value > 2_147_483_647
            ):
                raise DomainError(
                    code="INVALID_DYNAMIC_ATTRIBUTE",
                    message=f"{field} must be a non-negative integer.",
                    field=field,
                    http_status=400,
                )
            return value
        if value_type == "string_list":
            if (
                not isinstance(value, list)
                or any(not isinstance(item, str) or not item for item in value)
                or len(value) != len(set(value))
            ):
                raise DomainError(
                    code="INVALID_DYNAMIC_ATTRIBUTE",
                    message=f"{field} must be an array of unique non-empty strings.",
                    field=field,
                    http_status=400,
                )
            return list(value)
        raise RuntimeError(value_type)
