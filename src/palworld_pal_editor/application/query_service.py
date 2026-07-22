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
            tree_group_id = player.group_id or getattr(
                player, "_unresolved_group_id", None
            )
            row = {
                "player_id": str(player.PlayerUId),
                "instance_id": str(player.InstanceId),
                "name": str(player.NickName or ""),
                "level": level,
                "pal_count": len(player._palbox),
                "guild_id": (
                    None if tree_group_id is None else str(tree_group_id)
                ),
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

    def guild_tree(
        self, *, player_ids: set[str] | None = None
    ) -> list[dict[str, Any]]:
        manager = self._session.manager
        group_data = getattr(manager, "group_data", None)
        camp_data = getattr(manager, "camp_data", None)
        known_groups = {
            str(group.group_id): group
            for group in (group_data.get_groups() if group_data else [])
        }
        nodes: dict[str, dict[str, Any]] = {}

        def normalized_group_id(value) -> str | None:
            return None if value is None else str(value)

        def ensure_node(group_id: str | None) -> dict[str, Any]:
            key = "no-guild" if group_id is None else f"guild:{group_id}"
            if key in nodes:
                return nodes[key]
            group = known_groups.get(group_id) if group_id is not None else None
            if group is None:
                kind = "no_guild" if group_id is None else "unknown"
                name = ""
                base_order: list[str] = []
            else:
                kind = (
                    "independent"
                    if group.group_type == "EPalGroupType::IndependentGuild"
                    else "guild"
                )
                name = str(group.guild_name or "")
                base_order = [str(base_id) for base_id in group.base_ids or []]
            node = {
                "node_id": key,
                "guild_id": group_id,
                "kind": kind,
                "name": name,
                "members": [],
                "bases": [],
                "_base_order": base_order,
            }
            nodes[key] = node
            return node

        for group_id in known_groups:
            ensure_node(group_id)

        for player in (manager.player_mapping or {}).values():
            player_id = str(player.PlayerUId)
            if player_ids is not None and player_id not in player_ids:
                continue
            tree_group_id = player.group_id or getattr(
                player, "_unresolved_group_id", None
            )
            ensure_node(normalized_group_id(tree_group_id))["members"].append(
                {
                    "player_id": player_id,
                    "name": str(player.NickName or ""),
                    "level": player.Level if player.Level is not None else 1,
                    "pal_count": len(player._palbox),
                }
            )

        camps = list(camp_data.get_camps()) if camp_data else []
        workers = list((getattr(manager, "baseworker_mapping", None) or {}).values())
        workers_by_container: dict[str, list[Any]] = {}
        for worker in workers:
            workers_by_container.setdefault(str(worker.ContainerId), []).append(worker)

        matched_worker_ids: set[str] = set()
        for camp in camps:
            group_id = normalized_group_id(camp.owner_group_id)
            container_id = (
                None if camp.container_id is None else str(camp.container_id)
            )
            base_workers = workers_by_container.get(container_id, [])
            matched_worker_ids.update(str(worker.InstanceId) for worker in base_workers)
            ensure_node(group_id)["bases"].append(
                {
                    "node_id": f"base:{camp.id}",
                    "base_id": str(camp.id),
                    "kind": "base",
                    "name": str(camp.name or ""),
                    "worker_count": len(base_workers),
                }
            )

        unmatched_counts: dict[str | None, int] = {}
        for worker in workers:
            if str(worker.InstanceId) in matched_worker_ids:
                continue
            group_id = normalized_group_id(worker.group_id)
            unmatched_counts[group_id] = unmatched_counts.get(group_id, 0) + 1
        for group_id, count in unmatched_counts.items():
            node = ensure_node(group_id)
            node["bases"].append(
                {
                    "node_id": f"unmatched-base:{node['node_id']}",
                    "base_id": None,
                    "kind": "unmatched",
                    "name": "",
                    "worker_count": count,
                }
            )

        kind_order = {"guild": 0, "independent": 1, "unknown": 2, "no_guild": 3}
        result = []
        for node in nodes.values():
            if not node["members"] and not node["bases"]:
                continue
            node["members"].sort(
                key=lambda member: (member["name"].casefold(), member["player_id"])
            )
            base_order = {
                base_id: index for index, base_id in enumerate(node.pop("_base_order"))
            }
            node["bases"].sort(
                key=lambda base: (
                    base["kind"] == "unmatched",
                    base_order.get(base["base_id"], len(base_order)),
                    base["name"].casefold(),
                    base["base_id"] or "",
                )
            )
            node["member_count"] = len(node["members"])
            node["base_count"] = sum(
                base["kind"] == "base" for base in node["bases"]
            )
            result.append(node)
        return sorted(
            result,
            key=lambda node: (
                kind_order[node["kind"]],
                node["name"].casefold(),
                node["guild_id"] or "",
            ),
        )

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
