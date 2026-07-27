from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass
from pathlib import Path
from struct import iter_unpack
from typing import Any

from palworld_save_tools.gvas import GvasFile
from palworld_save_tools.palsav import compress_gvas_to_sav, decompress_sav_to_gvas
from palworld_save_tools.paltypes import (
    PALWORLD_CUSTOM_PROPERTIES,
    PALWORLD_TYPE_HINTS,
)
from palworld_pal_editor.core.save_manager import skip_decode, skip_encode
from palworld_pal_editor.domain.errors import DomainError


LOCAL_DATA_RELATIVE_PATH = "LocalData.sav"
FOG_CLEAR_CONFIRMATION = "清除迷雾"
FOG_RESET_CONFIRMATION = "重新覆盖未探索迷雾"
# Verified from copied Palworld 1.0 Steam current-format and WGS legacy-format
# LocalData.sav samples: opaque black is unexplored; transparent black is clear.
UNEXPLORED_PIXEL = (0, 0, 0, 255)
CLEARED_PIXEL = (0, 0, 0, 0)

_MAIN_MAP_MASK_BYTES = 4_194_304
_TREE_MAP_MASK_BYTES = 1_048_576
_CURRENT_MAP_LENGTHS = {
    "MainMap": _MAIN_MAP_MASK_BYTES,
    "Tree": _TREE_MAP_MASK_BYTES,
}

LOCAL_DATA_CUSTOM_PROPERTIES = copy.deepcopy(PALWORLD_CUSTOM_PROPERTIES)
# These 1.0 LocalData fields have version-dependent layouts unrelated to the
# fog mask. Preserve their encoded property bodies instead of guessing.
LOCAL_DATA_CUSTOM_PROPERTIES[".SaveData.Local_MaxFriendshipPalIds"] = (
    skip_decode,
    skip_encode,
)
LOCAL_DATA_CUSTOM_PROPERTIES[".SaveData.Local_MapObjectPaintPalette"] = (
    skip_decode,
    skip_encode,
)


@dataclass(frozen=True)
class FogOfWarCapability:
    available: bool
    reason: str | None
    format: str | None
    maps: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "reason": self.reason,
            "format": self.format,
            "maps": list(self.maps),
        }


class LocalDataDocument:
    """Parsed LocalData.sav with a fail-closed fog-mask capability."""

    def __init__(
        self,
        path: Path,
        *,
        gvas_file: GvasFile | None = None,
        compression_type: int | None = None,
        load_error: str | None = None,
    ) -> None:
        self.path = path
        self.gvas_file = gvas_file
        self.compression_type = compression_type
        self.load_error = load_error
        self._capability = self._inspect_capability()

    @classmethod
    def open(cls, workspace: str | Path) -> "LocalDataDocument":
        return cls.open_file(Path(workspace) / LOCAL_DATA_RELATIVE_PATH)

    @classmethod
    def open_file(cls, path: str | Path) -> "LocalDataDocument":
        resolved = Path(path)
        if not resolved.is_file():
            return cls(resolved, load_error="LOCAL_DATA_MISSING")
        try:
            raw_gvas, compression_type = decompress_sav_to_gvas(
                resolved.read_bytes()
            )
            gvas_file = GvasFile.read(
                raw_gvas,
                PALWORLD_TYPE_HINTS,
                LOCAL_DATA_CUSTOM_PROPERTIES,
            )
            return cls(
                resolved,
                gvas_file=gvas_file,
                compression_type=compression_type,
            )
        except Exception:
            return cls(resolved, load_error="LOCAL_DATA_UNREADABLE")

    @property
    def capability(self) -> FogOfWarCapability:
        return self._capability

    def require_resettable(self) -> None:
        if self._capability.available:
            return
        reason = self._capability.reason or "FOG_OF_WAR_STRUCTURE_UNSUPPORTED"
        messages = {
            "LOCAL_DATA_MISSING": (
                "LocalData.sav is missing; fog-of-war masks cannot be changed safely."
            ),
            "LOCAL_DATA_UNREADABLE": (
                "LocalData.sav could not be parsed with a verified structure."
            ),
            "FOG_OF_WAR_STRUCTURE_UNSUPPORTED": (
                "The LocalData.sav fog-of-war structure is unknown or unsupported."
            ),
        }
        raise DomainError(
            code=reason,
            message=messages.get(
                reason,
                "The LocalData.sav fog-of-war capability is unavailable.",
            ),
            details={"capability": self._capability.to_dict()},
            http_status=409,
        )

    def snapshot_masks(self) -> tuple[tuple[str, tuple[int, ...]], ...]:
        self.require_resettable()
        return tuple(
            (name, tuple(mask["value"]["values"]))
            for name, mask in self._mask_bindings()
        )

    def restore_masks(
        self, snapshot: tuple[tuple[str, tuple[int, ...]], ...]
    ) -> None:
        current = {name: mask for name, mask in self._mask_bindings()}
        if set(current) != {name for name, _values in snapshot}:
            raise ValueError("LocalData fog-mask structure changed during restore")
        for name, values in snapshot:
            current[name]["value"]["values"] = tuple(values)

    def mask_summary(self) -> dict[str, Any]:
        self.require_resettable()
        maps = []
        for name, mask in self._mask_bindings():
            values = tuple(mask["value"]["values"])
            mask_bytes = bytes(values)
            unexplored = sum(
                pixel == UNEXPLORED_PIXEL
                for pixel in iter_unpack("4B", mask_bytes)
            )
            cleared = sum(
                pixel == CLEARED_PIXEL
                for pixel in iter_unpack("4B", mask_bytes)
            )
            maps.append(
                {
                    "name": name,
                    "byte_length": len(values),
                    "sha256": hashlib.sha256(bytes(values)).hexdigest(),
                    "unexplored_pixels": unexplored,
                    "cleared_pixels": cleared,
                    "total_pixels": len(values) // 4,
                }
            )
        return {
            "format": self._capability.format,
            "maps": maps,
        }

    def reset_fog_of_war(self) -> None:
        self.require_resettable()
        for _name, mask in self._mask_bindings():
            byte_length = len(mask["value"]["values"])
            mask["value"]["values"] = UNEXPLORED_PIXEL * (byte_length // 4)

    def clear_fog_of_war(self) -> None:
        self.require_resettable()
        for _name, mask in self._mask_bindings():
            byte_length = len(mask["value"]["values"])
            mask["value"]["values"] = CLEARED_PIXEL * (byte_length // 4)

    def is_fully_unexplored(self) -> bool:
        self.require_resettable()
        return all(
            bytes(mask["value"]["values"])
            == bytes(UNEXPLORED_PIXEL) * (len(mask["value"]["values"]) // 4)
            for _name, mask in self._mask_bindings()
        )

    def is_fully_cleared(self) -> bool:
        self.require_resettable()
        return all(
            bytes(mask["value"]["values"])
            == bytes(CLEARED_PIXEL) * (len(mask["value"]["values"]) // 4)
            for _name, mask in self._mask_bindings()
        )

    def validate_reset(self) -> None:
        self.require_resettable()
        for name, mask in self._mask_bindings():
            values = mask["value"]["values"]
            if bytes(values) != bytes(UNEXPLORED_PIXEL) * (len(values) // 4):
                raise DomainError(
                    code="FOG_OF_WAR_RESET_VALIDATION_FAILED",
                    message="A fog-of-war mask did not match the verified reset value.",
                    details={"map": name},
                    http_status=409,
                )

    def validate_clear(self) -> None:
        self.require_resettable()
        for name, mask in self._mask_bindings():
            values = mask["value"]["values"]
            if bytes(values) != bytes(CLEARED_PIXEL) * (len(values) // 4):
                raise DomainError(
                    code="FOG_OF_WAR_CLEAR_VALIDATION_FAILED",
                    message="A fog-of-war mask did not match the verified clear value.",
                    details={"map": name},
                    http_status=409,
                )

    def serialize_bytes(self) -> bytes:
        self.require_resettable()
        if self.gvas_file is None or self.compression_type is None:
            raise ValueError("LocalData.sav is not loaded")
        return compress_gvas_to_sav(
            copy.deepcopy(self.gvas_file).write(LOCAL_DATA_CUSTOM_PROPERTIES),
            self.compression_type,
        )

    def verify_reloaded_file(self, path: str | Path) -> GvasFile:
        reloaded = self.open_file(path)
        reloaded.require_resettable()
        if (
            reloaded.capability.format != self.capability.format
            or reloaded.capability.maps != self.capability.maps
        ):
            raise ValueError("Reloaded LocalData fog-mask structure changed")
        expected_masks = {
            name: bytes(mask["value"]["values"])
            for name, mask in self._mask_bindings()
        }
        reloaded_masks = {
            name: bytes(mask["value"]["values"])
            for name, mask in reloaded._mask_bindings()
        }
        if reloaded_masks != expected_masks:
            raise ValueError("Reloaded LocalData fog-mask values changed")
        if reloaded._properties_without_masks() != self._properties_without_masks():
            raise ValueError("Reloaded LocalData changed fields outside fog masks")
        if reloaded.gvas_file is None:
            raise ValueError("Reloaded LocalData.sav is unavailable")
        return reloaded.gvas_file

    def _inspect_capability(self) -> FogOfWarCapability:
        if self.load_error is not None:
            return FogOfWarCapability(
                available=False,
                reason=self.load_error,
                format=None,
            )
        try:
            bindings = self._mask_bindings()
        except (KeyError, TypeError, ValueError):
            return FogOfWarCapability(
                available=False,
                reason="FOG_OF_WAR_STRUCTURE_UNSUPPORTED",
                format=None,
            )
        return FogOfWarCapability(
            available=True,
            reason=None,
            format=(
                "WorldMapUISaveDataMap"
                if len(bindings) == 2
                else "WorldMapMaskTextureV4"
            ),
            maps=tuple(name for name, _mask in bindings),
        )

    def _save_data(self) -> dict[str, Any]:
        if self.gvas_file is None:
            raise ValueError("LocalData.sav is not loaded")
        save_data = self.gvas_file.properties.get("SaveData")
        if not isinstance(save_data, dict) or save_data.get("type") != "StructProperty":
            raise ValueError("SaveData is not a StructProperty")
        value = save_data.get("value")
        if not isinstance(value, dict):
            raise ValueError("SaveData has no property map")
        return value

    def _mask_bindings(self) -> list[tuple[str, dict[str, Any]]]:
        save_data = self._save_data()
        current = save_data.get("WorldMapUISaveDataMap")
        legacy = save_data.get("WorldMapMaskTextureV4")
        if current is not None and legacy is not None:
            raise ValueError("Fog-mask structure is ambiguous")
        if current is not None:
            return self._current_mask_bindings(current)
        if legacy is not None:
            self._validate_byte_mask(
                legacy,
                expected_length=_MAIN_MAP_MASK_BYTES,
            )
            return [("MainMap", legacy)]
        raise ValueError("Fog-mask property is missing")

    def _current_mask_bindings(
        self, property_value: dict[str, Any]
    ) -> list[tuple[str, dict[str, Any]]]:
        if (
            not isinstance(property_value, dict)
            or property_value.get("type") != "MapProperty"
            or property_value.get("key_type") != "NameProperty"
            or property_value.get("value_type") != "StructProperty"
        ):
            raise ValueError("WorldMapUISaveDataMap has an unsupported layout")
        entries = property_value.get("value")
        if not isinstance(entries, list):
            raise ValueError("WorldMapUISaveDataMap entries are unavailable")
        by_name: dict[str, dict[str, Any]] = {}
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("key"), str):
                raise ValueError("WorldMapUISaveDataMap entry is malformed")
            value = entry.get("value")
            if not isinstance(value, dict):
                raise ValueError("WorldMapUISaveDataMap value is malformed")
            mask = value.get("MaskTextureData")
            if not isinstance(mask, dict) or entry["key"] in by_name:
                raise ValueError("WorldMapUISaveDataMap mask is malformed")
            by_name[entry["key"]] = mask
        if set(by_name) != set(_CURRENT_MAP_LENGTHS):
            raise ValueError("WorldMapUISaveDataMap map set is unverified")
        for name, expected_length in _CURRENT_MAP_LENGTHS.items():
            self._validate_byte_mask(
                by_name[name],
                expected_length=expected_length,
            )
        return [(name, by_name[name]) for name in _CURRENT_MAP_LENGTHS]

    @staticmethod
    def _validate_byte_mask(
        mask: dict[str, Any], *, expected_length: int
    ) -> None:
        if (
            mask.get("type") != "ArrayProperty"
            or mask.get("array_type") != "ByteProperty"
        ):
            raise ValueError("Fog mask is not a byte array")
        value = mask.get("value")
        values = value.get("values") if isinstance(value, dict) else None
        if (
            not isinstance(values, (list, tuple))
            or len(values) != expected_length
            or len(values) % 4 != 0
        ):
            raise ValueError("Fog mask dimensions or bytes are unverified")
        try:
            bytes(values)
        except (TypeError, ValueError, OverflowError) as error:
            raise ValueError("Fog mask contains invalid byte values") from error

    def _properties_without_masks(self) -> dict[str, Any]:
        if self.gvas_file is None:
            raise ValueError("LocalData.sav is not loaded")
        properties = copy.deepcopy(self.gvas_file.properties)
        save_data = properties["SaveData"]["value"]
        if "WorldMapUISaveDataMap" in save_data:
            for entry in save_data["WorldMapUISaveDataMap"]["value"]:
                values = entry["value"]["MaskTextureData"]["value"]["values"]
                entry["value"]["MaskTextureData"]["value"]["values"] = (
                    "<fog-mask>",
                    len(values),
                )
        elif "WorldMapMaskTextureV4" in save_data:
            values = save_data["WorldMapMaskTextureV4"]["value"]["values"]
            save_data["WorldMapMaskTextureV4"]["value"]["values"] = (
                "<fog-mask>",
                len(values),
            )
        return properties
