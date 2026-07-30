from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Optional

from palworld_save_tools.archive import FArchiveReader, FArchiveWriter, UUID
from palworld_save_tools.gvas import GvasFile
from palworld_save_tools.paltypes import (
    PALWORLD_CUSTOM_PROPERTIES,
    PALWORLD_TYPE_HINTS,
)
from palworld_save_tools.rawdata import map_concrete_model_module, map_model

from palworld_pal_editor.core.location_data import read_transform_translation


MAP_OBJECT_SAVE_DATA_PATH = ".worldSaveData.MapObjectSaveData"
ITEM_CONTAINER_MODULE = (
    "EPalMapObjectConcreteModelModuleType::ItemContainer"
)
PERSISTENT_STORAGE_USAGE_TYPE = 1
ZERO_UUID = "00000000-0000-0000-0000-000000000000"


@dataclass(frozen=True)
class BaseStorageBinding:
    guild_id: UUID
    base_id: UUID
    map_object_instance_id: UUID
    map_object_type: str
    container_id: UUID
    usage_type: int
    location: Optional[dict[str, float]]


@dataclass(frozen=True)
class BaseStorageIssue:
    code: str
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "details": dict(self.details)}


class BaseStorageData:
    """Selective, read-only index from guild bases to persistent item storage.

    MapObjectSaveData is opaque in the main save model. This index deliberately
    decodes only Model.RawData and ItemContainer module RawData, so an unknown
    concrete model for an unrelated map object cannot block storage discovery.
    """

    def __init__(self, gvas_file: GvasFile) -> None:
        self.source_present = False
        self.complete = True
        self._bindings_by_base: dict[
            tuple[str, str], list[BaseStorageBinding]
        ] = {}
        self._bindings_by_container: dict[
            tuple[str, str, str], BaseStorageBinding
        ] = {}
        self._issues: list[BaseStorageIssue] = []

        world = gvas_file.properties.get("worldSaveData", {}).get("value", {})
        prop = world.get("MapObjectSaveData")
        if prop is None:
            self.source_present = False
            self.complete = False
            self._record_issue("MAP_OBJECT_SAVE_DATA_MISSING")
            return
        self.source_present = True
        entries, reader = self._decode_property(prop)
        self._index_entries(entries, reader)

    def get_base(
        self, guild_id: UUID | str, base_id: UUID | str
    ) -> tuple[BaseStorageBinding, ...]:
        key = (str(guild_id).casefold(), str(base_id).casefold())
        return tuple(self._bindings_by_base.get(key, ()))

    def resolve(
        self,
        guild_id: UUID | str,
        base_id: UUID | str,
        container_id: UUID | str,
    ) -> Optional[BaseStorageBinding]:
        key = (
            str(guild_id).casefold(),
            str(base_id).casefold(),
            str(container_id).casefold(),
        )
        return self._bindings_by_container.get(key)

    def issues(self) -> tuple[BaseStorageIssue, ...]:
        return tuple(self._issues)

    @staticmethod
    def _decode_property(
        prop: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], FArchiveReader]:
        if (
            prop.get("type") == "ArrayProperty"
            and isinstance(prop.get("value"), dict)
            and isinstance(prop["value"].get("values"), list)
            and prop.get("skip_type") != "ArrayProperty"
        ):
            reader = FArchiveReader(
                b"",
                type_hints=PALWORLD_TYPE_HINTS,
                custom_properties=PALWORLD_CUSTOM_PROPERTIES,
            )
            return prop["value"]["values"], reader
        if (
            prop.get("type") != "ArrayProperty"
            or prop.get("skip_type") != "ArrayProperty"
            or not isinstance(prop.get("array_type"), str)
            or not isinstance(prop.get("value"), bytes)
        ):
            raise ValueError("Unsupported MapObjectSaveData encoding")

        writer = FArchiveWriter()
        writer.fstring(prop["array_type"])
        writer.optional_guid(prop.get("id"))
        writer.write(prop["value"])
        reader = FArchiveReader(
            writer.bytes(),
            type_hints=PALWORLD_TYPE_HINTS,
            custom_properties=PALWORLD_CUSTOM_PROPERTIES,
        )
        decoded = reader.property(
            "ArrayProperty",
            len(prop["value"]),
            MAP_OBJECT_SAVE_DATA_PATH,
            nested_caller_path=MAP_OBJECT_SAVE_DATA_PATH,
        )
        if not reader.eof():
            raise ValueError("MapObjectSaveData has trailing data")
        values = decoded.get("value", {}).get("values")
        if not isinstance(values, list):
            raise ValueError("MapObjectSaveData entries are unavailable")
        return values, reader

    def _index_entries(
        self,
        entries: list[dict[str, Any]],
        reader: FArchiveReader,
    ) -> None:
        for entry_index, entry in enumerate(entries):
            try:
                model = self._decode_model(entry, reader)
            except Exception as error:
                self._record_issue(
                    "BASE_STORAGE_MODEL_DECODE_FAILED",
                    entry_index=entry_index,
                    error_type=type(error).__name__,
                )
                continue

            modules = (
                entry.get("ConcreteModel", {})
                .get("value", {})
                .get("ModuleMap", {})
                .get("value", [])
            )
            if not isinstance(modules, list):
                self._record_issue(
                    "BASE_STORAGE_MODULE_MAP_INVALID",
                    entry_index=entry_index,
                )
                continue
            for module_index, module in enumerate(modules):
                if module.get("key") != ITEM_CONTAINER_MODULE:
                    continue
                try:
                    decoded_module = self._decode_item_module(module, reader)
                    self._index_item_module(
                        entry,
                        model,
                        decoded_module,
                        entry_index=entry_index,
                        module_index=module_index,
                    )
                except Exception as error:
                    self._record_issue(
                        "BASE_STORAGE_MODULE_DECODE_FAILED",
                        entry_index=entry_index,
                        module_index=module_index,
                        error_type=type(error).__name__,
                    )

        for bindings in self._bindings_by_base.values():
            bindings.sort(
                key=lambda binding: (
                    binding.map_object_type.casefold(),
                    str(binding.map_object_instance_id),
                    str(binding.container_id),
                )
            )

    @staticmethod
    def _decode_model(
        entry: dict[str, Any], reader: FArchiveReader
    ) -> dict[str, Any]:
        value = (
            entry.get("Model", {})
            .get("value", {})
            .get("RawData", {})
            .get("value")
        )
        if isinstance(value, dict) and "instance_id" in value:
            return value
        if not isinstance(value, dict) or not isinstance(
            value.get("values"), Sequence
        ):
            raise ValueError("Map object Model.RawData is unavailable")
        return map_model.decode_bytes(reader, value["values"])

    @staticmethod
    def _decode_item_module(
        module: dict[str, Any], reader: FArchiveReader
    ) -> dict[str, Any]:
        value = (
            module.get("value", {})
            .get("RawData", {})
            .get("value")
        )
        if isinstance(value, dict) and "target_container_id" in value:
            return value
        if not isinstance(value, dict) or not isinstance(
            value.get("values"), Sequence
        ):
            raise ValueError("ItemContainer RawData is unavailable")
        decoded = map_concrete_model_module.decode_bytes(
            reader,
            value["values"],
            ITEM_CONTAINER_MODULE,
        )
        if not isinstance(decoded, dict):
            raise ValueError("ItemContainer RawData did not decode")
        return decoded

    def _index_item_module(
        self,
        entry: dict[str, Any],
        model: dict[str, Any],
        module: dict[str, Any],
        *,
        entry_index: int,
        module_index: int,
    ) -> None:
        usage_type = module.get("usage_type")
        if usage_type != PERSISTENT_STORAGE_USAGE_TYPE:
            return

        guild_id = model.get("group_id_belong_to")
        base_id = model.get("base_camp_id_belong_to")
        instance_id = model.get("instance_id")
        container_id = module.get("target_container_id")
        guild_unassigned = (
            guild_id is None or str(guild_id).casefold() == ZERO_UUID
        )
        base_unassigned = (
            base_id is None or str(base_id).casefold() == ZERO_UUID
        )
        if guild_unassigned and base_unassigned:
            # Persistent storage can exist outside a guild base (for example,
            # world/vendor objects). It is deliberately outside this index.
            return
        required = {
            "guild_id": guild_id,
            "base_id": base_id,
            "map_object_instance_id": instance_id,
            "container_id": container_id,
        }
        missing = [
            name
            for name, value in required.items()
            if value is None or str(value).casefold() == ZERO_UUID
        ]
        if missing:
            self._record_issue(
                "BASE_STORAGE_BINDING_INCOMPLETE",
                entry_index=entry_index,
                module_index=module_index,
                fields=missing,
            )
            return

        map_object_type = entry.get("MapObjectId", {}).get("value")
        if not isinstance(map_object_type, str) or not map_object_type:
            self._record_issue(
                "BASE_STORAGE_OBJECT_TYPE_MISSING",
                entry_index=entry_index,
                module_index=module_index,
            )
            return

        binding = BaseStorageBinding(
            guild_id=guild_id,
            base_id=base_id,
            map_object_instance_id=instance_id,
            map_object_type=map_object_type,
            container_id=container_id,
            usage_type=usage_type,
            location=read_transform_translation(
                model.get("initital_transform_cache")
            ),
        )
        key = (
            str(guild_id).casefold(),
            str(base_id).casefold(),
            str(container_id).casefold(),
        )
        if key in self._bindings_by_container:
            self._record_issue(
                "BASE_STORAGE_CONTAINER_AMBIGUOUS",
                guild_id=str(guild_id),
                base_id=str(base_id),
                container_id=str(container_id),
            )
            return
        self._bindings_by_container[key] = binding
        self._bindings_by_base.setdefault(key[:2], []).append(binding)

    def _record_issue(self, code: str, **details: Any) -> None:
        self.complete = False
        self._issues.append(BaseStorageIssue(code=code, details=details))
