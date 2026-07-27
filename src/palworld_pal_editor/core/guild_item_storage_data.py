from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from palworld_save_tools.archive import (
    FArchiveReader,
    FArchiveWriter,
    UUID,
)
from palworld_save_tools.gvas import GvasFile
from palworld_save_tools.paltypes import (
    PALWORLD_CUSTOM_PROPERTIES,
    PALWORLD_TYPE_HINTS,
)


GUILD_EXTRA_SAVE_DATA_PATH = ".worldSaveData.GuildExtraSaveDataMap"


@dataclass(frozen=True)
class GuildItemStorageBinding:
    guild_id: UUID
    container_id: UUID


class GuildItemStorageData:
    """Read-only guild-to-container index over the opaque guild-extra map."""

    def __init__(self, gvas_file: GvasFile) -> None:
        self.source_present = False
        self._bindings: dict[str, GuildItemStorageBinding] = {}
        world = gvas_file.properties.get("worldSaveData", {}).get("value", {})
        prop = world.get("GuildExtraSaveDataMap")
        if prop is None:
            return
        self.source_present = True
        decoded = self._decode_property(prop)
        for entry in decoded.get("value", []):
            self._index_entry(entry)

    def get(
        self, guild_id: UUID | str
    ) -> Optional[GuildItemStorageBinding]:
        return self._bindings.get(str(guild_id).casefold())

    def get_bindings(self) -> list[GuildItemStorageBinding]:
        return list(self._bindings.values())

    @staticmethod
    def _decode_property(prop: dict[str, Any]) -> dict[str, Any]:
        if (
            prop.get("type") == "MapProperty"
            and isinstance(prop.get("value"), list)
        ):
            return prop
        if (
            prop.get("type") != "MapProperty"
            or prop.get("skip_type") != "MapProperty"
            or prop.get("key_type") != "StructProperty"
            or prop.get("value_type") != "StructProperty"
            or not isinstance(prop.get("value"), bytes)
        ):
            raise ValueError("Unsupported GuildExtraSaveDataMap encoding")

        writer = FArchiveWriter()
        writer.fstring(prop["key_type"])
        writer.fstring(prop["value_type"])
        writer.optional_guid(prop.get("id"))
        writer.write(prop["value"])
        reader = FArchiveReader(
            writer.bytes(),
            type_hints=PALWORLD_TYPE_HINTS,
            custom_properties=PALWORLD_CUSTOM_PROPERTIES,
        )
        decoded = reader.property(
            "MapProperty",
            len(prop["value"]),
            GUILD_EXTRA_SAVE_DATA_PATH,
        )
        if not reader.eof():
            raise ValueError("GuildExtraSaveDataMap has trailing data")
        return decoded

    def _index_entry(self, entry: dict[str, Any]) -> None:
        guild_id = entry.get("key")
        if guild_id is None:
            raise ValueError("Guild item storage entry has no guild id")
        storage = entry.get("value", {}).get("GuildItemStorage")
        if storage is None:
            return
        raw_data = (
            storage.get("value", {})
            .get("RawData", {})
            .get("value")
        )
        if not isinstance(raw_data, dict):
            raise ValueError("Guild item storage entry has no readable RawData")
        container_id = raw_data.get("container_id")
        if container_id is None:
            raise ValueError("Guild item storage entry has no container id")
        key = str(guild_id).casefold()
        if key in self._bindings:
            raise ValueError(f"Duplicate guild item storage id: {guild_id}")
        self._bindings[key] = GuildItemStorageBinding(
            guild_id=guild_id,
            container_id=container_id,
        )
