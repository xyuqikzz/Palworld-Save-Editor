from __future__ import annotations

from typing import Any, Iterable

from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.utils.data_provider import DataProvider

from .inventory_editor import InventoryEditor
from .save_session import SaveSession


class SaveQueryService:
    """Read-only search, filter, and sort over domain summaries."""

    PLAYER_SORTS = {"name", "level", "player_id", "pal_count"}
    PAL_SORTS = {
        "name",
        "internal_id",
        "level",
        "gender",
        "owner",
        "container_state",
    }
    ITEM_SORTS = {
        "name",
        "internal_id",
        "category",
        "rarity",
        "container",
        "slot_index",
        "state",
        "dynamic_kind",
    }

    def __init__(self, session: SaveSession, *, locale: str = "en") -> None:
        self._session = session
        self._locale = locale

    def players(
        self,
        *,
        text: str = "",
        min_level: int | None = None,
        max_level: int | None = None,
        sort_by: str = "name",
        descending: bool = False,
    ) -> list[dict[str, Any]]:
        self._validate_sort(sort_by, self.PLAYER_SORTS)
        needle = self._needle(text)
        rows: list[dict[str, Any]] = []
        for player in (self._session.manager.player_mapping or {}).values():
            level = player.Level if player.Level is not None else 1
            row = {
                "player_id": str(player.PlayerUId),
                "instance_id": str(player.InstanceId),
                "name": str(player.NickName or ""),
                "level": level,
                "pal_count": len(player._palbox),
                "details_loaded": bool(getattr(player, "is_loaded", True)),
            }
            if needle and not self._matches(
                needle, row["name"], row["player_id"], row["instance_id"]
            ):
                continue
            if min_level is not None and level < min_level:
                continue
            if max_level is not None and level > max_level:
                continue
            rows.append(row)
        return self._sort(rows, sort_by, descending)

    def pals(
        self,
        *,
        player_id: str | None = None,
        text: str = "",
        element: str | None = None,
        min_level: int | None = None,
        max_level: int | None = None,
        gender: str | None = None,
        boss: bool | None = None,
        rare: bool | None = None,
        owner: str | None = None,
        container_state: str | None = None,
        sort_by: str = "name",
        descending: bool = False,
    ) -> list[dict[str, Any]]:
        self._validate_sort(sort_by, self.PAL_SORTS)
        needle = self._needle(text)
        rows: list[dict[str, Any]] = []
        for pal, owner_id, owner_name in self._pal_candidates(player_id):
            level = pal.Level if pal.Level is not None else 1
            elements = DataProvider.get_pal_elements(pal.DataAccessKey) or []
            state = (
                "detached"
                if pal.is_unreferenced_pal
                else ("owner_container" if pal.in_owner_palbox else "other_container")
            )
            row = {
                "pal_id": str(pal.InstanceId),
                "name": str(pal.DisplayName or pal.DataAccessKey or ""),
                "internal_id": str(pal.DataAccessKey or ""),
                "elements": list(elements),
                "level": level,
                "gender": pal.Gender.value if pal.Gender else None,
                "boss": bool(pal.IsBOSS),
                "rare": bool(pal.IsRarePal),
                "tower": bool(pal.IsTower),
                "owner": owner_name,
                "owner_id": owner_id,
                "container_state": state,
            }
            if needle and not self._matches(
                needle, row["name"], row["internal_id"], row["pal_id"], owner_name
            ):
                continue
            if element is not None and element not in elements:
                continue
            if min_level is not None and level < min_level:
                continue
            if max_level is not None and level > max_level:
                continue
            if gender is not None and row["gender"] != gender:
                continue
            if boss is not None and row["boss"] is not boss:
                continue
            if rare is not None and row["rare"] is not rare:
                continue
            if owner is not None and owner.casefold() not in (
                owner_name or ""
            ).casefold():
                continue
            if container_state is not None and state != container_state:
                continue
            rows.append(row)
        return self._sort(rows, sort_by, descending)

    def items(
        self,
        player_id: str,
        *,
        text: str = "",
        category: str | None = None,
        rarity: int | None = None,
        container: str | None = None,
        state: str | None = None,
        dynamic_kind: str | None = None,
        sort_by: str = "container",
        descending: bool = False,
    ) -> list[dict[str, Any]]:
        self._validate_sort(sort_by, self.ITEM_SORTS)
        needle = self._needle(text)
        inventory = InventoryEditor(
            self._session, locale=self._locale
        ).get_inventory(player_id)
        rows: list[dict[str, Any]] = []
        for container_view in inventory.containers:
            container_name = container_view.container_type.value
            if container is not None and container_name != container:
                continue
            for slot in container_view.slots:
                row = {
                    "container": container_name,
                    "slot_index": slot.slot_index,
                    "state": slot.state,
                    "internal_id": slot.static_id,
                    "name": slot.name,
                    "category": slot.category,
                    "rarity": slot.rarity,
                    "dynamic_kind": slot.dynamic_kind,
                    "count": slot.count,
                }
                if state is not None and row["state"] != state:
                    continue
                if category is not None and row["category"] != category:
                    continue
                if rarity is not None and row["rarity"] != rarity:
                    continue
                if dynamic_kind is not None and row["dynamic_kind"] != dynamic_kind:
                    continue
                if needle and not self._matches(
                    needle, row["name"], row["internal_id"], row["category"]
                ):
                    continue
                rows.append(row)
        return self._sort(rows, sort_by, descending)

    def _pal_candidates(
        self, player_id: str | None
    ) -> Iterable[tuple[Any, str | None, str | None]]:
        manager = self._session.manager
        if player_id is not None:
            player = manager.get_player(player_id)
            if player is None:
                raise DomainError(
                    code="PLAYER_NOT_FOUND",
                    message="Player not found.",
                    field="player_id",
                    http_status=404,
                )
            for pal in player._palbox.values():
                yield pal, str(player.PlayerUId), str(player.NickName or "")
            return
        for player in (manager.player_mapping or {}).values():
            for pal in player._palbox.values():
                yield pal, str(player.PlayerUId), str(player.NickName or "")
        for pal in (manager.baseworker_mapping or {}).values():
            yield pal, None, None
        for pal in (manager._dangling_pals or {}).values():
            yield pal, None, None

    @staticmethod
    def _validate_sort(value: str, allowed: set[str]) -> None:
        if value not in allowed:
            raise DomainError(
                code="INVALID_SORT_FIELD",
                message="The requested sort field is not supported.",
                field="sort_by",
                details={"sort_by": value, "allowed": sorted(allowed)},
                http_status=400,
            )

    @staticmethod
    def _needle(value: str) -> str:
        return str(value or "").strip().casefold()

    @staticmethod
    def _matches(needle: str, *values: Any) -> bool:
        return any(
            needle in str(value).casefold()
            for value in values
            if value is not None
        )

    @staticmethod
    def _sort(rows: list[dict[str, Any]], key: str, descending: bool):
        return sorted(
            rows,
            key=lambda row: (
                row.get(key) is None,
                str(row.get(key) or "").casefold()
                if not isinstance(row.get(key), (int, float))
                else row.get(key),
                str(row.get("player_id") or row.get("pal_id") or ""),
            ),
            reverse=descending,
        )
