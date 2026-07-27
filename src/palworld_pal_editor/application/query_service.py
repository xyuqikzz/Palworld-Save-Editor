from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Iterable

from palworld_pal_editor.core.character_index import CharacterIndex
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.utils.data_provider import DataProvider

from .inventory_editor import InventoryEditor
from .save_session import SaveSession


class SaveQueryService:
    """Read-only search, filter, and sort over domain summaries."""

    WORLD_MAP_BOUNDS = {
        "min_x": -1099400.0,
        "max_x": 349400.0,
        "min_y": -724400.0,
        "max_y": 724400.0,
    }
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

        def guild_chest_summary(
            group_id: str | None, kind: str
        ) -> tuple[str, int | None]:
            if group_id is None or kind not in {"guild", "independent"}:
                return "not_applicable", None
            if getattr(manager, "guild_item_storage_error", None):
                return "unsupported", None
            storage = getattr(manager, "guild_item_storage_data", None)
            binding = storage.get(group_id) if storage is not None else None
            if binding is None:
                return "missing", None
            containers = getattr(manager, "item_container_data", None)
            container = (
                containers.get(binding.container_id)
                if containers is not None
                else None
            )
            if container is None:
                return "container_missing", None
            return "available", container.capacity

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
            guild_chest_status, guild_chest_capacity = guild_chest_summary(
                group_id, kind
            )
            node = {
                "node_id": key,
                "guild_id": group_id,
                "kind": kind,
                "name": name,
                "members": [],
                "bases": [],
                "guild_chest_status": guild_chest_status,
                "guild_chest_capacity": guild_chest_capacity,
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

    def guilds(self) -> list[dict[str, Any]]:
        """Return every persisted guild with its saved members and bases."""
        manager = self._session.manager
        group_data = getattr(manager, "group_data", None)
        groups = list(group_data.get_groups()) if group_data else []
        camp_data = getattr(manager, "camp_data", None)
        camps = list(camp_data.get_camps()) if camp_data else []
        camps_by_id = {str(camp.id): camp for camp in camps}
        loaded_players = {
            str(player.PlayerUId): player
            for player in (
                getattr(manager, "player_mapping", None) or {}
            ).values()
        }
        workers_by_container: dict[str, list[Any]] = defaultdict(list)
        for worker in (
            getattr(manager, "baseworker_mapping", None) or {}
        ).values():
            container_id = str(worker.ContainerId)
            workers_by_container[container_id].append(worker)

        def player_group_id(player) -> str | None:
            value = player.group_id or getattr(
                player, "_unresolved_group_id", None
            )
            return None if value is None else str(value)

        def member_summary(player_id: str, saved_name: str) -> dict[str, Any]:
            player = loaded_players.get(player_id)
            if player is None:
                return {
                    "player_id": player_id,
                    "name": saved_name,
                    "level": None,
                    "pal_count": None,
                    "details_loaded": False,
                }
            return {
                "player_id": player_id,
                "name": str(player.NickName or saved_name),
                "level": player.Level if player.Level is not None else 1,
                "pal_count": len(player._palbox),
                "details_loaded": bool(getattr(player, "is_loaded", True)),
            }

        def worker_summary(worker: Any) -> dict[str, Any]:
            pal_id = str(worker.InstanceId)
            internal_id = str(
                getattr(worker, "DataAccessKey", None)
                or getattr(worker, "CharacterID", None)
                or ""
            )
            gender = getattr(worker, "Gender", None)
            return {
                "pal_id": pal_id,
                "slot_index": getattr(worker, "SlotIndex", None),
                "name": str(
                    getattr(worker, "DisplayName", None)
                    or internal_id
                    or pal_id
                ),
                "nickname": str(getattr(worker, "CustomNickName", None) or ""),
                "internal_id": internal_id,
                "icon_access_key": getattr(worker, "IconAccessKey", None),
                "elements": list(
                    DataProvider.get_pal_elements(internal_id) or []
                ),
                "level": getattr(worker, "Level", None) or 1,
                "gender": getattr(gender, "value", gender),
                "boss": bool(getattr(worker, "IsBOSS", False)),
                "rare": bool(getattr(worker, "IsRarePal", False)),
                "tower": bool(getattr(worker, "IsTower", False)),
                "sick": bool(getattr(worker, "HasWorkerSick", False)),
                "fainted": bool(getattr(worker, "IsFaintedPal", False)),
                "passive_skills": list(
                    getattr(worker, "PassiveSkillList", None) or []
                ),
                "work_suitabilities": dict(
                    getattr(worker, "WorkSuitabilities", None) or {}
                ),
            }

        def base_summary(base_id: str, camp) -> dict[str, Any]:
            if camp is None:
                return {
                    "node_id": f"base:{base_id}",
                    "base_id": base_id,
                    "kind": "missing",
                    "name": "",
                    "worker_count": None,
                    "worker_capacity_status": "base_missing",
                    "worker_capacity": None,
                    "workers": [],
                }
            container_id = (
                None if camp.container_id is None else str(camp.container_id)
            )
            containers = getattr(manager, "container_data", None)
            container = (
                containers.get_container(camp.container_id)
                if containers is not None and camp.container_id is not None
                else None
            )
            if camp.container_id is None:
                capacity_status = "missing"
            elif container is None:
                capacity_status = "container_missing"
            else:
                capacity_status = "available"
            workers = [
                worker_summary(worker)
                for worker in workers_by_container.get(container_id, [])
            ]
            workers.sort(
                key=lambda worker: (
                    worker["slot_index"] is None,
                    worker["slot_index"] or 0,
                    worker["name"].casefold(),
                    worker["pal_id"],
                )
            )
            return {
                "node_id": f"base:{base_id}",
                "base_id": base_id,
                "kind": "base",
                "name": str(camp.name or ""),
                "worker_count": len(workers),
                "worker_capacity_status": capacity_status,
                "worker_capacity": (
                    container.size if container is not None else None
                ),
                "workers": workers,
            }

        def chest_summary(group_id: str) -> tuple[str, int | None]:
            if getattr(manager, "guild_item_storage_error", None):
                return "unsupported", None
            storage = getattr(manager, "guild_item_storage_data", None)
            binding = storage.get(group_id) if storage is not None else None
            if binding is None:
                return "missing", None
            containers = getattr(manager, "item_container_data", None)
            container = (
                containers.get(binding.container_id)
                if containers is not None
                else None
            )
            if container is None:
                return "container_missing", None
            return "available", container.capacity

        result: list[dict[str, Any]] = []
        for group in groups:
            group_id = str(group.group_id)
            saved_members = list(group.players or [])
            members = []
            member_ids: set[str] = set()
            for player_uid, saved_name in saved_members:
                player_id = str(player_uid)
                if player_id in member_ids:
                    continue
                member_ids.add(player_id)
                members.append(member_summary(player_id, str(saved_name or "")))
            for player_id, player in loaded_players.items():
                if (
                    player_id not in member_ids
                    and player_group_id(player) == group_id
                ):
                    member_ids.add(player_id)
                    members.append(member_summary(player_id, ""))
            members.sort(
                key=lambda member: (
                    member["name"].casefold(),
                    member["player_id"],
                )
            )

            base_ids = [str(base_id) for base_id in (group.base_ids or [])]
            known_base_ids = set(base_ids)
            base_ids.extend(
                str(camp.id)
                for camp in camps
                if str(camp.owner_group_id) == group_id
                and str(camp.id) not in known_base_ids
            )
            bases = [
                base_summary(base_id, camps_by_id.get(base_id))
                for base_id in base_ids
            ]
            chest_status, chest_capacity = chest_summary(group_id)
            level = group.base_camp_level
            result.append(
                {
                    "node_id": f"guild:{group_id}",
                    "guild_id": group_id,
                    "kind": (
                        "independent"
                        if group.group_type
                        == "EPalGroupType::IndependentGuild"
                        else "guild"
                    ),
                    "name": str(group.guild_name or ""),
                    "name_editable": isinstance(
                        group._group_param.get("guild_name"), str
                    ),
                    "base_camp_level_status": (
                        "available" if level is not None else "missing"
                    ),
                    "base_camp_level": level,
                    "guild_chest_status": chest_status,
                    "guild_chest_capacity": chest_capacity,
                    "members": members,
                    "member_count": len(members),
                    "bases": bases,
                    "base_count": len(bases),
                }
            )
        return sorted(
            result,
            key=lambda guild: (
                guild["kind"] != "guild",
                guild["name"].casefold(),
                guild["guild_id"],
            ),
        )

    def overview(self) -> dict[str, Any]:
        """Return a read-only, normalized summary of the loaded world."""
        manager = self._session.manager
        pal_contexts: dict[str, dict[str, Any]] = {}

        def add_pal(pal: Any, *, scope: str, owner: Any = None) -> None:
            pal_id = str(pal.InstanceId)
            if pal_id in pal_contexts:
                return
            owner_id = str(owner.PlayerUId) if owner is not None else None
            owner_name = str(owner.NickName or "") if owner is not None else ""
            pal_contexts[pal_id] = {
                "pal": pal,
                "pal_id": pal_id,
                "name": str(pal.DisplayName or pal.DataAccessKey or pal_id),
                "internal_id": str(pal.DataAccessKey or ""),
                "icon_access_key": pal.IconAccessKey or None,
                "level": pal.Level if pal.Level is not None else 1,
                "owner_id": owner_id,
                "owner_name": owner_name,
                "scope": scope,
            }

        players = list((getattr(manager, "player_mapping", None) or {}).values())
        for player in players:
            for pal in player._palbox.values():
                add_pal(pal, scope="player", owner=player)
        for pal in (
            getattr(manager, "baseworker_mapping", None) or {}
        ).values():
            add_pal(pal, scope="base")
        for pal in (getattr(manager, "_dangling_pals", None) or {}).values():
            add_pal(pal, scope="detached")

        group_data = getattr(manager, "group_data", None)
        guilds = list(group_data.get_groups()) if group_data else []
        camp_data = getattr(manager, "camp_data", None)
        bases = list(camp_data.get_camps()) if camp_data else []

        species: Counter[str] = Counter()
        species_meta: dict[str, dict[str, Any]] = {}
        human_npcs = 0
        creature_pals = 0
        boss_pals = 0
        rare_pals = 0
        awakened_pals = 0
        sick_pals = 0
        fainted_pals = 0
        for context in pal_contexts.values():
            pal = context["pal"]
            if bool(pal.IsHuman):
                human_npcs += 1
            else:
                creature_pals += 1
                species_key = context["internal_id"] or context["pal_id"]
                species[species_key] += 1
                species_meta.setdefault(
                    species_key,
                    {
                        "internal_id": context["internal_id"],
                        "name": context["name"],
                        "icon_access_key": context["icon_access_key"],
                    },
                )
            boss_pals += int(bool(pal.IsBOSS))
            rare_pals += int(bool(pal.IsRarePal))
            awakened_pals += int(bool(pal.IsAwakened))
            sick_pals += int(bool(pal.HasWorkerSick))
            fainted_pals += int(bool(pal.IsFaintedPal))

        character_index = getattr(manager, "character_index", None)
        if character_index is None and all(
            hasattr(manager, field)
            for field in (
                "_entities_list",
                "container_data",
                "group_data",
                "player_mapping",
                "baseworker_mapping",
                "_dangling_pals",
            )
        ):
            character_index = CharacterIndex(manager)
        structural_issues = list(
            getattr(character_index, "issues", []) if character_index else []
        )

        issue_counts: Counter[str] = Counter()
        pal_reasons: dict[str, set[str]] = defaultdict(set)
        non_pal_issue_count = 0
        hard_structural_codes: set[str] = set()
        for issue in structural_issues:
            issue_counts[issue.code] += 1
            if not issue.recoverable:
                hard_structural_codes.add(issue.code)
            if issue.pal_id is None:
                non_pal_issue_count += 1
            else:
                pal_reasons[str(issue.pal_id)].add(issue.code)

        expedition_assigned = 0
        invalid_expedition_assignments = 0
        unknown_expedition_assignments = 0
        valid_expedition_ids: set[str] = set()
        assignment_status = getattr(manager, "expedition_assignment_status", None)
        for context in pal_contexts.values():
            pal = context["pal"]
            if not bool(pal.IsExpeditionPal):
                continue
            expedition_assigned += 1
            status = (
                assignment_status(pal)
                if callable(assignment_status)
                else "unknown"
            )
            if status == "valid":
                valid_expedition_ids.add(str(pal.ExpeditionInstanceId))
            elif status == "invalid":
                invalid_expedition_assignments += 1
                issue_counts["EXPEDITION_ASSIGNMENT_INVALID"] += 1
                pal_reasons[context["pal_id"]].add(
                    "EXPEDITION_ASSIGNMENT_INVALID"
                )
            else:
                unknown_expedition_assignments += 1
                issue_counts["EXPEDITION_ASSIGNMENT_UNKNOWN"] += 1
                pal_reasons[context["pal_id"]].add(
                    "EXPEDITION_ASSIGNMENT_UNKNOWN"
                )

        for context in pal_contexts.values():
            pal = context["pal"]
            if bool(pal.HasWorkerSick):
                issue_counts["PAL_SICK"] += 1
                pal_reasons[context["pal_id"]].add("PAL_SICK")
            if bool(pal.IsFaintedPal):
                issue_counts["PAL_FAINTED"] += 1
                pal_reasons[context["pal_id"]].add("PAL_FAINTED")

        expedition_data_available = False
        expedition_record_count = 0
        get_expedition_ids = getattr(manager, "get_expedition_instance_ids", None)
        if callable(get_expedition_ids):
            expedition_ids = get_expedition_ids()
            expedition_data_available = expedition_ids is not None
            expedition_record_count = len(expedition_ids or ())
        completable = getattr(manager, "completable_expeditions", None)
        completable_count = len(completable()) if callable(completable) else 0

        reason_priority = {
            "EXPEDITION_ASSIGNMENT_INVALID": 0,
            "PAL_CONTAINER_REFERENCE_AMBIGUOUS": 1,
            "PAL_SLOT_REFERENCE_MISMATCH": 1,
            "PAL_OWNER_REFERENCE_AMBIGUOUS": 1,
            "PAL_OWNER_REFERENCE_MISMATCH": 1,
            "PAL_GROUP_REFERENCE_AMBIGUOUS": 1,
            "PAL_GROUP_REFERENCE_MISMATCH": 1,
            "DUPLICATE_CHARACTER_RECORD": 1,
            "PAL_RECORD_INDEX_MISMATCH": 1,
            "PAL_DETACHED": 2,
            "EXPEDITION_ASSIGNMENT_UNKNOWN": 3,
            "PAL_FAINTED": 4,
            "PAL_SICK": 5,
        }
        anomaly_preview = []
        for pal_id, codes in pal_reasons.items():
            context = pal_contexts.get(pal_id)
            sorted_codes = sorted(
                codes, key=lambda code: (reason_priority.get(code, 2), code)
            )
            severity = (
                "danger"
                if any(
                    code == "EXPEDITION_ASSIGNMENT_INVALID"
                    or code in hard_structural_codes
                    for code in sorted_codes
                )
                else "warning"
            )
            anomaly_preview.append(
                {
                    "pal_id": pal_id,
                    "name": context["name"] if context else pal_id,
                    "internal_id": context["internal_id"] if context else "",
                    "icon_access_key": (
                        context["icon_access_key"] if context else None
                    ),
                    "level": context["level"] if context else None,
                    "owner_id": context["owner_id"] if context else None,
                    "owner_name": context["owner_name"] if context else "",
                    "scope": context["scope"] if context else "unmanaged",
                    "severity": severity,
                    "reason_codes": sorted_codes,
                }
            )
        anomaly_preview.sort(
            key=lambda row: (
                row["severity"] != "danger",
                reason_priority.get(row["reason_codes"][0], 2),
                row["name"].casefold(),
                row["pal_id"],
            )
        )

        player_preview = sorted(
            (
                {
                    "player_id": str(player.PlayerUId),
                    "name": str(player.NickName or ""),
                    "level": player.Level if player.Level is not None else 1,
                    "pal_count": len(player._palbox),
                }
                for player in players
            ),
            key=lambda row: (
                -row["pal_count"],
                -row["level"],
                row["name"].casefold(),
                row["player_id"],
            ),
        )[:6]

        top_species = []
        for species_key, count in species.most_common(6):
            meta = species_meta[species_key]
            top_species.append({**meta, "count": count})

        return {
            "revision": self._session.revision,
            "totals": {
                "players": len(players),
                "pals": len(pal_contexts),
                "creature_pals": creature_pals,
                "human_npcs": human_npcs,
                "species": len(species),
                "guilds": len(guilds),
                "bases": len(bases),
                "base_workers": len(
                    {
                        str(pal.InstanceId)
                        for pal in (
                            getattr(manager, "baseworker_mapping", None) or {}
                        ).values()
                    }
                ),
            },
            "traits": {
                "boss_pals": boss_pals,
                "rare_pals": rare_pals,
                "awakened_pals": awakened_pals,
            },
            "condition": {
                "sick_pals": sick_pals,
                "fainted_pals": fainted_pals,
            },
            "expeditions": {
                "data_available": expedition_data_available,
                "records": expedition_record_count,
                "active": len(valid_expedition_ids),
                "assigned_pals": expedition_assigned,
                "completable": completable_count,
                "invalid_assignments": invalid_expedition_assignments,
                "unknown_assignments": unknown_expedition_assignments,
            },
            "anomalies": {
                "pal_count": len(pal_reasons),
                "issue_count": sum(issue_counts.values()),
                "structural_issue_count": len(structural_issues),
                "blocking_structural_issue_count": sum(
                    not issue.recoverable for issue in structural_issues
                ),
                "recoverable_structural_issue_count": sum(
                    issue.recoverable for issue in structural_issues
                ),
                "non_pal_issue_count": non_pal_issue_count,
                "index_available": character_index is not None,
                "by_code": [
                    {"code": code, "count": count}
                    for code, count in sorted(
                        issue_counts.items(), key=lambda item: (-item[1], item[0])
                    )
                ],
                "preview": anomaly_preview[:8],
            },
            "top_species": top_species,
            "players": player_preview,
        }

    def expeditions(self) -> dict[str, Any]:
        """Return active expeditions and Pals held by invalid references."""
        manager = self._session.manager
        get_records = getattr(manager, "expedition_records", None)
        records = get_records() if callable(get_records) else None
        data_available = records is not None
        records = records or []

        pals: dict[str, dict[str, Any]] = {}

        def add_pal(pal: Any, *, scope: str, owner: Any = None) -> None:
            pal_id = str(pal.InstanceId).lower()
            if pal_id in pals:
                return
            pals[pal_id] = {
                "pal": pal,
                "pal_id": pal_id,
                "name": str(pal.DisplayName or pal.DataAccessKey or pal_id),
                "internal_id": str(pal.DataAccessKey or ""),
                "icon_access_key": pal.IconAccessKey or None,
                "level": pal.Level if pal.Level is not None else 1,
                "scope": scope,
                "owner_id": (
                    str(owner.PlayerUId) if owner is not None else None
                ),
                "owner_name": (
                    str(owner.NickName or "") if owner is not None else ""
                ),
            }

        for player in (
            getattr(manager, "player_mapping", None) or {}
        ).values():
            for pal in player._palbox.values():
                add_pal(pal, scope="player", owner=player)
        for pal in (
            getattr(manager, "baseworker_mapping", None) or {}
        ).values():
            add_pal(pal, scope="base")
        for pal in (
            getattr(manager, "_dangling_pals", None) or {}
        ).values():
            add_pal(pal, scope="detached")

        camps = {
            str(camp.id).lower(): camp
            for camp in (
                manager.camp_data.get_camps()
                if getattr(manager, "camp_data", None)
                else []
            )
        }
        guilds = {
            str(group.group_id).lower(): group
            for group in (
                manager.group_data.get_groups()
                if getattr(manager, "group_data", None)
                else []
            )
        }
        assignment_status = getattr(
            manager, "expedition_assignment_status", None
        )

        def pal_summary(
            pal_id: str, *, owner_player_uid: str | None = None
        ) -> dict[str, Any]:
            context = pals.get(str(pal_id).lower())
            if context is None:
                return {
                    "pal_id": str(pal_id).lower(),
                    "name": "",
                    "internal_id": "",
                    "icon_access_key": None,
                    "level": None,
                    "scope": "missing",
                    "owner_id": owner_player_uid,
                    "owner_name": "",
                    "assignment_status": "missing",
                }
            pal = context["pal"]
            status = (
                assignment_status(pal)
                if callable(assignment_status)
                else "unknown"
            )
            return {
                key: value
                for key, value in context.items()
                if key != "pal"
            } | {"assignment_status": status or "unassigned"}

        active_expeditions = []
        for record in records:
            if not record.get("active"):
                continue
            base_id = record.get("base_id")
            guild_id = record.get("guild_id")
            base = camps.get(str(base_id).lower()) if base_id else None
            guild = guilds.get(str(guild_id).lower()) if guild_id else None
            base_number = None
            if guild is not None and base_id:
                guild_base_ids = [
                    str(candidate).lower()
                    for candidate in (getattr(guild, "base_ids", None) or [])
                ]
                normalized_base_id = str(base_id).lower()
                if normalized_base_id in guild_base_ids:
                    base_number = guild_base_ids.index(normalized_base_id) + 1
            members = [
                pal_summary(
                    member["pal_id"],
                    owner_player_uid=member.get("owner_player_uid"),
                )
                for member in record.get("members", [])
            ]
            active_expeditions.append(
                {
                    "expedition_id": record["expedition_id"],
                    "mission_id": record.get("mission_id"),
                    "base_id": base_id,
                    "base_name": str(base.name or "") if base else "",
                    "base_number": base_number,
                    "guild_id": guild_id,
                    "guild_name": (
                        str(guild.guild_name or "") if guild else ""
                    ),
                    "state": record.get("state"),
                    "start_time": record.get("start_time"),
                    "can_complete": bool(record.get("can_complete")),
                    "member_count": len(members),
                    "members": members,
                }
            )
        active_expeditions.sort(
            key=lambda row: (
                row["guild_name"].casefold(),
                row["base_number"] or 0,
                row["base_id"] or "",
                row["expedition_id"],
            )
        )

        invalid_locked_pals = []
        unknown_locked_pals = []
        locked_count = 0
        for context in pals.values():
            pal = context["pal"]
            if not bool(pal.IsExpeditionPal):
                continue
            locked_count += 1
            row = pal_summary(context["pal_id"])
            row["expedition_id"] = (
                str(pal.ExpeditionInstanceId).lower()
                if pal.ExpeditionInstanceId is not None
                else None
            )
            if row["assignment_status"] == "invalid":
                invalid_locked_pals.append(row)
            elif row["assignment_status"] == "unknown":
                unknown_locked_pals.append(row)

        locked_sort = lambda row: (
            row["name"].casefold(),
            row["pal_id"],
        )
        invalid_locked_pals.sort(key=locked_sort)
        unknown_locked_pals.sort(key=locked_sort)
        return {
            "data_available": data_available,
            "active_count": len(active_expeditions),
            "completable_count": sum(
                expedition["can_complete"]
                for expedition in active_expeditions
            ),
            "locked_count": locked_count,
            "invalid_locked_count": len(invalid_locked_pals),
            "unknown_locked_count": len(unknown_locked_pals),
            "expeditions": active_expeditions,
            "invalid_locked_pals": invalid_locked_pals,
            "unknown_locked_pals": unknown_locked_pals,
        }

    def map_data(self) -> dict[str, Any]:
        """Return read-only last-known player and base locations for the map."""
        manager = self._session.manager
        group_data = getattr(manager, "group_data", None)
        groups = {
            str(group.group_id): group
            for group in (group_data.get_groups() if group_data else [])
        }
        players: list[dict[str, Any]] = []
        unavailable_players: list[str] = []
        for player in (manager.player_mapping or {}).values():
            player_id = str(player.PlayerUId)
            try:
                location = player.LastLocation
            except Exception:
                location = None
            if location is None:
                unavailable_players.append(player_id)
                continue
            group_id_value = player.group_id or getattr(
                player, "_unresolved_group_id", None
            )
            group_id = None if group_id_value is None else str(group_id_value)
            group = groups.get(group_id) if group_id is not None else None
            players.append(
                {
                    "player_id": player_id,
                    "name": str(player.NickName or ""),
                    "level": player.Level if player.Level is not None else 1,
                    "guild_id": group_id,
                    "guild_name": str(group.guild_name or "") if group else "",
                    **location,
                }
            )

        bases: list[dict[str, Any]] = []
        unavailable_bases: list[str] = []
        camp_data = getattr(manager, "camp_data", None)
        for camp in (camp_data.get_camps() if camp_data else []):
            base_id = str(camp.id)
            try:
                location = camp.location
            except Exception:
                location = None
            if location is None:
                unavailable_bases.append(base_id)
                continue
            group_id = (
                None
                if camp.owner_group_id is None
                else str(camp.owner_group_id)
            )
            group = groups.get(group_id) if group_id is not None else None
            bases.append(
                {
                    "base_id": base_id,
                    "name": str(camp.name or ""),
                    "guild_id": group_id,
                    "guild_name": str(group.guild_name or "") if group else "",
                    "level": group.base_camp_level if group else None,
                    "radius": camp.area_range,
                    **location,
                }
            )

        players.sort(key=lambda row: (row["name"].casefold(), row["player_id"]))
        bases.sort(
            key=lambda row: (
                row["guild_name"].casefold(),
                row["name"].casefold(),
                row["base_id"],
            )
        )
        return {
            "bounds": dict(self.WORLD_MAP_BOUNDS),
            "location_source": "save_last_transform",
            "live": False,
            "players": players,
            "bases": bases,
            "unavailable_player_ids": unavailable_players,
            "unavailable_base_ids": unavailable_bases,
        }

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
