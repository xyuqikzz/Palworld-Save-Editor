from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from palworld_save_tools.gvas import GvasFile

from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.domain.fast_travel_catalog import (
    FAST_TRAVEL_POINT_IDS,
    FAST_TRAVEL_POINT_ID_SET,
)


FAST_TRAVEL_FIELD = "FastTravelPointUnlockFlag"
FAST_TRAVEL_FORMAT = "MapProperty<NameProperty,BoolProperty>"


class _FastTravelStructureError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class FastTravelCapability:
    available: bool
    reason: str | None
    format: str | None
    unlocked_count: int | None = None
    total_count: int = len(FAST_TRAVEL_POINT_IDS)

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "reason": self.reason,
            "format": self.format,
            "unlocked_count": self.unlocked_count,
            "total_count": self.total_count,
        }


class PlayerFastTravelData:
    """Strict view over one player's authoritative fast-travel flag map."""

    def __init__(self, save_data: Any) -> None:
        self._save_data = save_data
        self._capability = self._inspect_capability()

    @classmethod
    def from_player(cls, player: Any) -> "PlayerFastTravelData":
        return cls(getattr(player, "_player_save_data", None))

    @classmethod
    def from_gvas(cls, gvas_file: GvasFile) -> "PlayerFastTravelData":
        save_data = gvas_file.properties.get("SaveData")
        if not isinstance(save_data, dict) or save_data.get("type") != "StructProperty":
            return cls(None)
        return cls(save_data.get("value"))

    @property
    def capability(self) -> FastTravelCapability:
        return self._capability

    def require_unlockable(self) -> None:
        if self._capability.available:
            return
        reason = self._capability.reason or "FAST_TRAVEL_STRUCTURE_UNSUPPORTED"
        messages = {
            "FAST_TRAVEL_RECORD_DATA_MISSING": (
                "The selected player has no RecordData fast-travel structure."
            ),
            "FAST_TRAVEL_RECORD_DATA_UNSUPPORTED": (
                "The selected player's RecordData structure is unknown or unsupported."
            ),
            "FAST_TRAVEL_FIELD_MISSING": (
                "The selected player has no verified fast-travel flag map."
            ),
            "FAST_TRAVEL_STRUCTURE_UNSUPPORTED": (
                "The selected player's fast-travel flag map is unknown or unsupported."
            ),
            "FAST_TRAVEL_CATALOG_MISMATCH": (
                "The selected player contains fast-travel IDs outside the verified catalog."
            ),
        }
        raise DomainError(
            code=reason,
            message=messages.get(
                reason,
                "Fast-travel editing is unavailable for the selected player.",
            ),
            details={"capability": self._capability.to_dict()},
            http_status=409,
        )

    def snapshot(self) -> dict[str, Any]:
        self.require_unlockable()
        return deepcopy(self._save_data)

    def restore(self, snapshot: dict[str, Any]) -> None:
        if not isinstance(self._save_data, dict):
            raise ValueError("Player save data is unavailable during restore")
        self._save_data.clear()
        self._save_data.update(deepcopy(snapshot))
        self._capability = self._inspect_capability()

    def summary(self) -> dict[str, Any]:
        self.require_unlockable()
        entries = self._entries()
        return {
            "format": FAST_TRAVEL_FORMAT,
            "unlocked_count": sum(
                entry["value"] is True
                for entry in entries
                if entry["key"] in FAST_TRAVEL_POINT_ID_SET
            ),
            "total_count": len(FAST_TRAVEL_POINT_IDS),
            "all_unlocked": self.is_all_unlocked(),
        }

    def is_all_unlocked(self) -> bool:
        self.require_unlockable()
        flags = {entry["key"]: entry["value"] for entry in self._entries()}
        return all(flags.get(point_id) is True for point_id in FAST_TRAVEL_POINT_IDS)

    def unlock_all(self) -> None:
        self.require_unlockable()
        entries = self._entries()
        by_id = {entry["key"]: entry for entry in entries}
        for point_id in FAST_TRAVEL_POINT_IDS:
            entry = by_id.get(point_id)
            if entry is None:
                entries.append({"key": point_id, "value": True})
            else:
                entry["value"] = True
        self._capability = self._inspect_capability()

    def validate_all_unlocked(self) -> None:
        self.require_unlockable()
        flags = {entry["key"]: entry["value"] for entry in self._entries()}
        if not all(flags.get(point_id) is True for point_id in FAST_TRAVEL_POINT_IDS):
            raise DomainError(
                code="FAST_TRAVEL_UNLOCK_VALIDATION_FAILED",
                message="The fast-travel flag map did not match the verified catalog.",
                http_status=409,
            )

    def non_catalog_entries(self) -> list[dict[str, Any]]:
        self.require_unlockable()
        return deepcopy(
            [
                entry
                for entry in self._entries()
                if entry["key"] not in FAST_TRAVEL_POINT_ID_SET
            ]
        )

    def properties_without_flags(self) -> dict[str, Any]:
        self.require_unlockable()
        properties = deepcopy(self._save_data)
        flag = properties["RecordData"]["value"][FAST_TRAVEL_FIELD]
        flag["value"] = "<fast-travel-flags>"
        return properties

    def verify_reloaded(self, reloaded: "PlayerFastTravelData") -> None:
        self.require_unlockable()
        reloaded.require_unlockable()
        reloaded.validate_all_unlocked()
        if reloaded._entries() != self._entries():
            raise ValueError("Reloaded player fast-travel flag map changed")
        if reloaded.properties_without_flags() != self.properties_without_flags():
            raise ValueError("Reloaded player save changed fields outside fast travel")

    def _inspect_capability(self) -> FastTravelCapability:
        try:
            entries = self._entries()
        except _FastTravelStructureError as error:
            return FastTravelCapability(
                available=False,
                reason=error.code,
                format=None,
            )
        return FastTravelCapability(
            available=True,
            reason=None,
            format=FAST_TRAVEL_FORMAT,
            unlocked_count=sum(
                entry["value"] is True
                for entry in entries
                if entry["key"] in FAST_TRAVEL_POINT_ID_SET
            ),
        )

    def _entries(self) -> list[dict[str, Any]]:
        if not isinstance(self._save_data, dict):
            raise _FastTravelStructureError("FAST_TRAVEL_RECORD_DATA_MISSING")
        record = self._save_data.get("RecordData")
        if record is None:
            raise _FastTravelStructureError("FAST_TRAVEL_RECORD_DATA_MISSING")
        if (
            not isinstance(record, dict)
            or record.get("type") != "StructProperty"
            or record.get("struct_type") != "PalLoggedinPlayerSaveDataRecordData"
            or not isinstance(record.get("value"), dict)
        ):
            raise _FastTravelStructureError("FAST_TRAVEL_RECORD_DATA_UNSUPPORTED")
        flag = record["value"].get(FAST_TRAVEL_FIELD)
        if flag is None:
            raise _FastTravelStructureError("FAST_TRAVEL_FIELD_MISSING")
        if (
            not isinstance(flag, dict)
            or flag.get("type") != "MapProperty"
            or flag.get("key_type") != "NameProperty"
            or flag.get("value_type") != "BoolProperty"
            or not isinstance(flag.get("value"), list)
        ):
            raise _FastTravelStructureError("FAST_TRAVEL_STRUCTURE_UNSUPPORTED")
        entries = flag["value"]
        seen: set[str] = set()
        for entry in entries:
            if (
                not isinstance(entry, dict)
                or set(entry) != {"key", "value"}
                or not isinstance(entry.get("key"), str)
                or not isinstance(entry.get("value"), bool)
                or entry["key"] in seen
            ):
                raise _FastTravelStructureError(
                    "FAST_TRAVEL_STRUCTURE_UNSUPPORTED"
                )
            seen.add(entry["key"])
        return entries
