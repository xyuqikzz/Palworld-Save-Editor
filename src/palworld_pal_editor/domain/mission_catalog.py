from __future__ import annotations

from copy import deepcopy
import json
from typing import Any

from palworld_pal_editor.config import ASSETS_PATH


class MissionCatalog:
    """Read-only Build-scoped mission metadata and localized presentation."""

    _default: "MissionCatalog | None" = None

    def __init__(self, data: dict[str, Any]) -> None:
        missions = data.get("missions")
        if not isinstance(missions, dict):
            raise ValueError("mission catalog must contain a missions object")
        self._data = deepcopy(data)
        self._missions = missions

    @classmethod
    def load_default(cls) -> "MissionCatalog":
        if cls._default is None:
            path = ASSETS_PATH / "assets" / "data" / "mission_data.json"
            cls._default = cls(json.loads(path.read_text(encoding="utf-8")))
        return cls._default

    @property
    def source(self) -> dict[str, Any]:
        return deepcopy(self._data.get("source", {}))

    def ids(self) -> tuple[str, ...]:
        return tuple(self._missions)

    def contains(self, mission_id: str) -> bool:
        return mission_id in self._missions

    def entry(self, mission_id: str) -> dict[str, Any] | None:
        value = self._missions.get(mission_id)
        return deepcopy(value) if value is not None else None

    def present(self, mission_id: str, locale: str) -> dict[str, Any]:
        entry = self.entry(mission_id)
        if entry is None:
            return {
                "internal_name": mission_id,
                "type": "hidden",
                "asset_path": None,
                "title": mission_id,
                "description": "",
                "objectives": [],
                "title_key": None,
                "description_key": None,
                "objective_keys": [],
                "localization_fallback": True,
                "catalog_missing": True,
            }
        translations = entry.get("i18n") or {}
        localized = translations.get(locale)
        used_locale = locale
        if not isinstance(localized, dict):
            localized = translations.get("en")
            used_locale = "en"
        if not isinstance(localized, dict):
            localized = {}
            used_locale = "internal"
        title = localized.get("title") or mission_id
        return {
            "internal_name": mission_id,
            "type": entry.get("type", "hidden"),
            "asset_path": entry.get("asset_path"),
            "title": title,
            "description": localized.get("description") or "",
            "objectives": list(localized.get("objectives") or []),
            "title_key": entry.get("title_key"),
            "description_key": entry.get("description_key"),
            "objective_keys": list(entry.get("objective_keys") or []),
            "localization_fallback": bool(
                localized.get("title_fallback") or used_locale != locale
            ),
            "catalog_missing": False,
        }
