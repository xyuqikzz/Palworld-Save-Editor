from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import re
from pathlib import Path
import shutil
from tempfile import mkdtemp
from threading import Event, RLock, Thread
from time import monotonic, sleep
from typing import Any, Protocol

from palworld_pal_editor.application.query_service import SaveQueryService
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.application.fast_travel import PlayerFastTravelData
from palworld_pal_editor.application.mission_editor import MissionEditor
from palworld_pal_editor.core.save_manager import SaveManager
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.domain.player_attributes import player_attribute_view
from palworld_pal_editor.remote.gateway import RemoteBridgePort
from palworld_pal_editor.remote.models import BridgeConnection, RemoteCommand


_SNAPSHOT_FILE_PATTERN = re.compile(
    r"(?:Level\.sav|Players/[0-9A-Fa-f]{32}\.sav)"
)
_PLAYER_TARGET_OPERATIONS = (
    "inventory.grant",
    "inventory.item.count.update",
    "inventory.item.dynamic.update",
    "inventory.item.put",
    "pal.enhancement.update",
    "pal.grant",
    "pal.identity.update",
    "pal.progression.update",
    "pal.skills.update",
    "player.attributes.update",
    "player.experience.add",
    "player.fast_travel.update",
    "player.identity.update",
    "player.missions.update",
    "player.progression.update",
    "player.technology.update",
    "player.ban",
    "player.kick",
    "player.unban",
)
_SAVED_SECTIONS = (
    "profile",
    "inventory",
    "technology",
    "missions",
    "attributes",
    "map",
    "party_pals",
    "palbox",
)


def _player_id(row: dict[str, Any]) -> str:
    for key in ("player_uid", "playerId", "playerUid", "player_id"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _player_key(value: str) -> str:
    return re.sub(r"[-{}\s]", "", value).casefold()


def _user_id(row: dict[str, Any]) -> str:
    for key in ("userId", "userid", "user_id"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _positive_level(value: object) -> int | None:
    if (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value > 0
    ):
        return value
    return None


def _map_position(row: dict[str, Any]) -> dict[str, float] | None:
    candidate = row.get("position")
    if not isinstance(candidate, dict):
        candidate = row.get("last_location")
    if not isinstance(candidate, dict):
        candidate = row
    x = candidate.get("x")
    y = candidate.get("y")
    z = candidate.get("z")
    if (
        not isinstance(x, (int, float))
        or isinstance(x, bool)
        or not isinstance(y, (int, float))
        or isinstance(y, bool)
    ):
        return None
    return {
        "x": float(x),
        "y": float(y),
        "z": (
            float(z)
            if isinstance(z, (int, float)) and not isinstance(z, bool)
            else 0.0
        ),
    }


def _utc_from_saved_value(value: object) -> str | None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        return None
    try:
        if value >= 621355968000000000:
            timestamp = (value - 621355968000000000) / 10_000_000
        elif value >= 1_000_000_000:
            timestamp = value
        else:
            return None
        return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


class SavedPlayerAdapter(Protocol):
    @property
    def state(self) -> dict[str, Any]: ...

    def refresh(self) -> None: ...

    def directory(self) -> list[dict[str, Any]]: ...

    def details(self, player_id: str) -> dict[str, Any]: ...

    def map_data(self) -> dict[str, Any]: ...

    def inventory(self, player_id: str) -> dict[str, Any]: ...

    def pals(
        self,
        player_id: str,
        *,
        collection: str,
        page: int,
        page_size: int,
    ) -> dict[str, Any]: ...

    def close(self) -> None: ...


class RemoteSaveSnapshotAdapter:
    """Downloads one short-lived bridge snapshot into a read-only save session."""

    def __init__(
        self,
        bridge: RemoteBridgePort,
        connection: BridgeConnection,
        *,
        capture_timeout_seconds: float = 30.0,
    ) -> None:
        self._bridge = bridge
        self._connection = connection
        self._capture_timeout_seconds = capture_timeout_seconds
        self._lock = RLock()
        self._state: dict[str, Any] = {
            "state": "idle",
            "captured_at": None,
            "last_error": None,
        }
        self._workspace: Path | None = None
        self._session: SaveSession | None = None
        self._closed = False

    @property
    def state(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def refresh(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._state = {
                "state": "capturing",
                "captured_at": None,
                "last_error": None,
            }
        workspace: Path | None = None
        session: SaveSession | None = None
        try:
            snapshot = self._bridge.create_snapshot(self._connection)
            deadline = monotonic() + self._capture_timeout_seconds
            while snapshot.get("state") == "capturing":
                if monotonic() >= deadline:
                    raise DomainError(
                        code="REMOTE_SNAPSHOT_TIMEOUT",
                        message=(
                            "The read-only player snapshot did not finish "
                            "in time."
                        ),
                        retryable=True,
                        http_status=504,
                    )
                sleep(0.1)
                snapshot = self._bridge.snapshot(
                    self._connection, str(snapshot["id"])
                )
            if snapshot.get("state") != "ready":
                raise DomainError(
                    code="REMOTE_SNAPSHOT_FAILED",
                    message=str(
                        snapshot.get("error")
                        or "The read-only player snapshot failed."
                    ),
                    retryable=True,
                    http_status=502,
                )
            manifest = self._validated_manifest(snapshot)
            workspace = Path(mkdtemp(prefix="pal-editor-live-snapshot-"))
            for entry in manifest:
                destination = workspace / Path(entry["name"])
                self._bridge.download_snapshot_file(
                    self._connection,
                    str(snapshot["id"]),
                    entry["file_id"],
                    destination,
                    expected_size=entry["size"],
                    expected_sha256=entry["sha256"],
                )
            session = SaveSession.open(
                workspace,
                manager=SaveManager.create_isolated(),
            )
            with self._lock:
                closed = self._closed
                if closed:
                    previous_session = None
                    previous_workspace = None
                else:
                    previous_session = self._session
                    previous_workspace = self._workspace
                    self._session = session
                    self._workspace = workspace
                    self._state = {
                        "state": "ready",
                        "snapshot_id": str(snapshot["id"]),
                        "captured_at": snapshot.get("capturedAt"),
                        "file_count": len(manifest),
                        "last_error": None,
                    }
            if closed:
                self._dispose(session, workspace)
            else:
                self._dispose(previous_session, previous_workspace)
        except Exception as error:
            self._dispose(session, workspace)
            with self._lock:
                if not self._closed:
                    self._state = {
                        "state": "failed",
                        "captured_at": None,
                        "last_error": (
                            error.message
                            if isinstance(error, DomainError)
                            else str(error)
                        ),
                    }

    @staticmethod
    def _validated_manifest(
        snapshot: dict[str, Any]
    ) -> list[dict[str, Any]]:
        files = snapshot.get("files")
        if (
            not isinstance(files, list)
            or not files
            or len(files) > 10000
        ):
            raise DomainError(
                code="REMOTE_SNAPSHOT_MANIFEST_INVALID",
                message="The bridge snapshot manifest is invalid.",
                retryable=False,
                http_status=502,
            )
        result: list[dict[str, Any]] = []
        names: set[str] = set()
        file_ids: set[str] = set()
        total_size = 0
        for value in files:
            if not isinstance(value, dict):
                raise DomainError(
                    code="REMOTE_SNAPSHOT_MANIFEST_INVALID",
                    message="The bridge snapshot manifest is invalid.",
                    retryable=False,
                    http_status=502,
                )
            name = value.get("name")
            file_id = value.get("fileId")
            size = value.get("size")
            sha256 = value.get("sha256")
            if (
                not isinstance(name, str)
                or _SNAPSHOT_FILE_PATTERN.fullmatch(name) is None
                or not isinstance(file_id, str)
                or re.fullmatch(r"[0-9a-f]{32}", file_id) is None
                or not isinstance(size, int)
                or isinstance(size, bool)
                or size < 0
                or not isinstance(sha256, str)
                or re.fullmatch(r"[0-9a-f]{64}", sha256) is None
                or name in names
                or file_id in file_ids
            ):
                raise DomainError(
                    code="REMOTE_SNAPSHOT_MANIFEST_INVALID",
                    message="The bridge snapshot manifest is invalid.",
                    retryable=False,
                    http_status=502,
                )
            names.add(name)
            file_ids.add(file_id)
            total_size += size
            if total_size > 16 * 1024 * 1024 * 1024:
                raise DomainError(
                    code="REMOTE_SNAPSHOT_TOO_LARGE",
                    message="The bridge snapshot exceeds the download limit.",
                    retryable=False,
                    http_status=413,
                )
            result.append(
                {
                    "name": name,
                    "file_id": file_id,
                    "size": size,
                    "sha256": sha256,
                }
            )
        if "Level.sav" not in names:
            raise DomainError(
                code="REMOTE_SNAPSHOT_MANIFEST_INVALID",
                message="The bridge snapshot does not contain Level.sav.",
                retryable=False,
                http_status=502,
            )
        return result

    def directory(self) -> list[dict[str, Any]]:
        session = self._required_session()
        captured_at = self.state.get("captured_at")
        last_online = self._last_online_by_player(session)
        return [
            {
                **row,
                "online": False,
                "last_online_at": last_online.get(
                    _player_key(row["player_id"])
                ),
                "source": "snapshot",
                "captured_at": captured_at,
                "available_sections": list(_SAVED_SECTIONS),
            }
            for row in SaveQueryService(session).players()
        ]

    def details(self, player_id: str) -> dict[str, Any]:
        session = self._required_session()
        player = session.load_player(player_id)
        missions = MissionEditor(session).get_missions(player_id)
        missions["writable"] = False
        missions["write_reason"] = "snapshot_read_only"
        fast_travel = PlayerFastTravelData.from_player(player)
        fast_travel_capability = fast_travel.capability.to_dict()
        map_progress = {
            "fast_travel": {
                "capability": fast_travel_capability,
                "summary": (
                    fast_travel.summary()
                    if fast_travel_capability["available"]
                    else None
                ),
            },
            "last_location": player.LastLocation,
        }
        technology = {
            "technology_points": player.TechnologyPoint or 0,
            "boss_technology_points": player.bossTechnologyPoint or 0,
            "unlocked": list(
                player.UnlockedRecipeTechnologyNames or []
            ),
        }
        return {
            "player": {
                "player_id": str(player.PlayerUId),
                "playerId": str(player.PlayerUId),
                "instance_id": str(player.InstanceId),
                "name": str(player.NickName or ""),
                "level": player.Level or 1,
                "experience": player.Exp or 0,
                "technology_points": player.TechnologyPoint or 0,
                "technologyPoints": player.TechnologyPoint or 0,
                "boss_technology_points": player.bossTechnologyPoint or 0,
                "unused_status_points": player.UnusedStatusPoint or 0,
                "unusedStatusPoints": player.UnusedStatusPoint or 0,
                "attributes": player_attribute_view(player),
                "unlocked_technology": list(
                    player.UnlockedRecipeTechnologyNames or []
                ),
                "unlockedTechnology": technology["unlocked"],
                "technology": technology,
                "missions": missions,
                "map_progress": map_progress,
                "mapProgress": map_progress,
                "last_location": player.LastLocation,
                "guild_id": (
                    None
                    if player.group_id is None
                    else str(player.group_id)
                ),
                "guildId": (
                    None
                    if player.group_id is None
                    else str(player.group_id)
                ),
                "detailsStatus": "saved",
                "source": "snapshot",
                "captured_at": self.state.get("captured_at"),
                "available_sections": list(_SAVED_SECTIONS),
            }
        }

    def map_data(self) -> dict[str, Any]:
        return SaveQueryService(self._required_session()).map_data()

    def inventory(self, player_id: str) -> dict[str, Any]:
        rows = SaveQueryService(self._required_session()).items(player_id)
        containers: dict[str, dict[str, Any]] = {}
        for row in rows:
            container = containers.setdefault(
                str(row["container"]),
                {"slot_count": 0, "items": []},
            )
            container["slot_count"] = max(
                container["slot_count"],
                row["slot_index"] + 1,
            )
            if row["state"] != "occupied" or not row["internal_id"]:
                continue
            container["items"].append(
                {
                    "slotIndex": row["slot_index"],
                    "itemId": row["internal_id"],
                    "quantity": row["count"],
                    "name": row["name"],
                    "category": row["category"],
                    "rarity": row["rarity"],
                    "dynamicKind": row["dynamic_kind"],
                }
            )
        return {
            "status": "available",
            "source": "snapshot",
            "captured_at": self.state.get("captured_at"),
            "containers": [
                {
                    "type": name,
                    "slotCount": data["slot_count"],
                    "occupiedSlotCount": len(data["items"]),
                    "items": data["items"],
                }
                for name, data in sorted(containers.items())
            ],
        }

    def pals(
        self,
        player_id: str,
        *,
        collection: str,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        player = self._required_session().load_player(player_id)
        wanted_container = (
            "PARTY" if collection == "party" else "PAL_STORAGE"
        )
        container_id = (
            player.OtomoCharacterContainerId
            if collection == "party"
            else player.PalStorageContainerId
        )
        manager = self._required_session().manager
        container_data = getattr(manager, "container_data", None)
        container = (
            container_data.get_container(container_id)
            if container_data is not None and container_id is not None
            else None
        )
        all_rows = []
        for pal in player.get_pals():
            if pal.owner_container_type != wanted_container:
                continue
            slot = pal.SlotId
            gender = pal.Gender
            all_rows.append(
                {
                    "status": "available",
                    "slotIndex": slot[1] if slot else len(all_rows),
                    "instanceId": str(pal.InstanceId),
                    "characterId": str(pal.CharacterID or ""),
                    "dataAccessKey": str(pal.DataAccessKey or ""),
                    "nickname": str(pal.CustomNickName or ""),
                    "level": pal.Level or 1,
                    "experience": pal.Exp or 0,
                    "gender": getattr(gender, "value", gender),
                    "boss": bool(pal.IsBOSS),
                    "rare": 1 if pal.IsRarePal else 0,
                    "rank": pal.Rank,
                    "passiveSkills": list(pal.PassiveSkillList or []),
                    "activeSkills": list(pal.EquipWaza or []),
                    "masteredSkills": list(pal.MasteredWaza or []),
                    "ivs": {
                        "hp": pal.Talent_HP or 0,
                        "melee": pal.Talent_Melee or 0,
                        "shot": pal.Talent_Shot or 0,
                        "defense": pal.Talent_Defense or 0,
                    },
                    "enhancements": {
                        "hp": pal.Rank_HP or 0,
                        "attack": pal.Rank_Attack or 0,
                        "defense": pal.Rank_Defence or 0,
                        "craftSpeed": pal.Rank_CraftSpeed or 0,
                    },
                }
            )
        all_rows.sort(key=lambda row: (row["slotIndex"], row["instanceId"]))
        start = page * page_size
        page_count = (
            (len(all_rows) + page_size - 1) // page_size
            if all_rows
            else 0
        )
        return {
            "status": "available",
            "source": "snapshot",
            "captured_at": self.state.get("captured_at"),
            "collection": collection,
            "pageIndex": page,
            "pageSize": page_size,
            "pageCount": page_count,
            "count": len(all_rows),
            "capacity": (
                container.size if container is not None else len(all_rows)
            ),
            "hasPrevious": page > 0 and page_count > 0,
            "hasNext": page + 1 < page_count,
            "entries": all_rows[start : start + page_size],
        }

    def _required_session(self) -> SaveSession:
        with self._lock:
            session = self._session
        if session is None:
            raise DomainError(
                code="REMOTE_SNAPSHOT_NOT_READY",
                message="The read-only player snapshot is not ready.",
                retryable=True,
                http_status=409,
            )
        return session

    @staticmethod
    def _last_online_by_player(
        session: SaveSession,
    ) -> dict[str, str | None]:
        result: dict[str, str | None] = {}
        group_data = getattr(session.manager, "group_data", None)
        for group in group_data.get_groups() if group_data else ():
            raw = getattr(group, "_group_param", {})
            for member in raw.get("players") or ():
                if not isinstance(member, dict):
                    continue
                uid = member.get("player_uid")
                if uid is None:
                    continue
                info = member.get("player_info") or {}
                result[_player_key(str(uid))] = _utc_from_saved_value(
                    info.get("last_online_real_time")
                )
        return result

    def close(self) -> None:
        with self._lock:
            self._closed = True
            session = self._session
            workspace = self._workspace
            self._session = None
            self._workspace = None
            self._state = {
                "state": "closed",
                "captured_at": None,
                "last_error": None,
            }
        self._dispose(session, workspace)

    @staticmethod
    def _dispose(
        session: SaveSession | None, workspace: Path | None
    ) -> None:
        if session is not None:
            try:
                session.close()
            except Exception:
                pass
        if workspace is not None:
            shutil.rmtree(workspace, ignore_errors=True)


class InMemorySavedPlayerAdapter:
    """Test adapter for the saved-player side of the module seam."""

    def __init__(
        self,
        players: list[dict[str, Any]] | None = None,
    ) -> None:
        self._players = list(players or [])
        self._state = {
            "state": "ready",
            "captured_at": "2026-01-01T00:00:00+00:00",
            "last_error": None,
        }

    @property
    def state(self) -> dict[str, Any]:
        return dict(self._state)

    def refresh(self) -> None:
        return None

    def directory(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._players]

    def details(self, player_id: str) -> dict[str, Any]:
        return {"player": next(
            dict(row)
            for row in self._players
            if _player_key(_player_id(row)) == _player_key(player_id)
        )}

    def map_data(self) -> dict[str, Any]:
        players = []
        for row in self._players:
            position = _map_position(row)
            player_id = _player_id(row)
            if not player_id or position is None:
                continue
            player = {
                "player_id": player_id,
                "name": str(row.get("name") or ""),
                **position,
            }
            level = _positive_level(row.get("level"))
            if level is not None:
                player["level"] = level
            for source_key, target_key in (
                ("guild_id", "guild_id"),
                ("guildId", "guild_id"),
                ("guild_name", "guild_name"),
                ("guildName", "guild_name"),
            ):
                value = row.get(source_key)
                if value and target_key not in player:
                    player[target_key] = value
            players.append(player)
        return {
            "location_source": "save_last_transform",
            "live": False,
            "players": players,
            "bases": [],
            "unavailable_player_ids": [],
            "unavailable_base_ids": [],
        }

    def inventory(self, player_id: str) -> dict[str, Any]:
        return {"status": "available", "containers": []}

    def pals(
        self,
        player_id: str,
        *,
        collection: str,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        return {
            "status": "available",
            "collection": collection,
            "pageIndex": page,
            "pageSize": page_size,
            "pageCount": 0,
            "entries": [],
        }

    def close(self) -> None:
        self._state["state"] = "closed"


class LivePlayerManagement:
    """Deep module combining runtime authority with a read-only save snapshot."""

    def __init__(
        self,
        *,
        bridge: RemoteBridgePort,
        connection: BridgeConnection,
        revision: Callable[[], int],
        execute_command: Callable[[RemoteCommand], dict[str, Any]],
        saved_adapter: SavedPlayerAdapter | None = None,
        start_snapshot: bool = True,
    ) -> None:
        self._bridge = bridge
        self._connection = connection
        self._revision = revision
        self._execute_command = execute_command
        self._capabilities = set(connection.capabilities)
        self._known_user_ids: dict[str, str] = {}
        self._saved = saved_adapter
        if (
            self._saved is None
            and "save.snapshot.read" in self._capabilities
        ):
            self._saved = RemoteSaveSnapshotAdapter(bridge, connection)
        self._stop = Event()
        self._snapshot_thread: Thread | None = None
        if self._saved is not None and start_snapshot:
            self._start_snapshot_refresh()

    def query(self, request: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(request, dict):
            raise DomainError(
                code="INVALID_REQUEST",
                message="A player-management query object is required.",
                http_status=400,
            )
        query = request.get("query")
        if query == "player.directory":
            return self._directory()
        if query == "map.read":
            return self._map_snapshot()
        player_id = self._validated_player_id(request.get("player_id"))
        if query == "player.details":
            return self._player_query(
                player_id,
                runtime_capability="player.details",
                runtime=lambda: self._bridge.player_details(
                    self._connection, player_id
                ),
                saved=lambda adapter: adapter.details(player_id),
                merge_saved_runtime=True,
            )
        if query == "inventory.read":
            return {
                "session_revision": self._revision(),
                "inventory": self._player_query(
                    player_id,
                    runtime_capability="inventory.read",
                    runtime=lambda: self._bridge.inventory(
                        self._connection, player_id
                    ),
                    saved=lambda adapter: adapter.inventory(player_id),
                ),
            }
        if query == "pal.list":
            collection = request.get("collection", "palbox")
            page = request.get("page", 0)
            page_size = request.get("page_size", 12)
            if (
                collection not in {"party", "palbox"}
                or not isinstance(page, int)
                or isinstance(page, bool)
                or page < 0
                or not isinstance(page_size, int)
                or isinstance(page_size, bool)
                or page_size < 1
                or page_size > 30
            ):
                raise DomainError(
                    code="REMOTE_PAL_PAGE_INVALID",
                    message="The Pal page parameters are invalid.",
                    http_status=400,
                )
            return {
                "session_revision": self._revision(),
                "pals": self._player_query(
                    player_id,
                    runtime_capability="pal.list",
                    runtime=lambda: self._bridge.pals(
                        self._connection,
                        player_id,
                        collection=collection,
                        page=page,
                        page_size=page_size,
                    ),
                    saved=lambda adapter: adapter.pals(
                        player_id,
                        collection=collection,
                        page=page,
                        page_size=page_size,
                    ),
                ),
            }
        raise DomainError(
            code="REMOTE_PLAYER_QUERY_UNSUPPORTED",
            message="The player-management query is unsupported.",
            field="query",
            http_status=400,
        )

    def execute(self, command: RemoteCommand) -> dict[str, Any]:
        return self._execute_command(command)

    def update_capabilities(self, capabilities: set[str]) -> None:
        self._capabilities = set(capabilities)

    def _directory(self) -> dict[str, Any]:
        runtime_rows = (
            self._bridge.players(self._connection)
            if "player.list" in self._capabilities
            else []
        )
        saved_rows = (
            self._saved.directory()
            if self._saved is not None
            and self._saved.state.get("state") == "ready"
            else []
        )
        merged: dict[str, dict[str, Any]] = {}
        for row in saved_rows:
            player_id = _player_id(row)
            if not player_id:
                continue
            key = _player_key(player_id)
            known_user_id = self._known_user_ids.get(key, "")
            merged[key] = {
                **row,
                "player_id": player_id,
                "online": False,
                "source": "snapshot",
                **({"userId": known_user_id} if known_user_id else {}),
                "available_sections": list(
                    row.get("available_sections") or _SAVED_SECTIONS
                ),
                "capabilities": self._target_capabilities(
                    online=False,
                    has_user_id=bool(known_user_id),
                ),
            }
        for row in runtime_rows:
            player_id = _player_id(row)
            if not player_id:
                continue
            key = _player_key(player_id)
            previous = merged.get(key, {})
            administrator_user_id = (
                _user_id(row)
                or self._known_user_ids.get(key, "")
                or _user_id(previous)
            )
            if administrator_user_id:
                self._known_user_ids[key] = administrator_user_id
            level = (
                _positive_level(row.get("level"))
                or _positive_level(previous.get("level"))
            )
            merged[key] = {
                **previous,
                **row,
                "player_id": player_id,
                "level": level,
                "online": True,
                **(
                    {"userId": administrator_user_id}
                    if administrator_user_id
                    else {}
                ),
                "source": (
                    "runtime+snapshot" if previous else "runtime"
                ),
                "available_sections": self._runtime_sections(previous),
                "capabilities": self._target_capabilities(
                    online=True,
                    has_user_id=bool(administrator_user_id),
                ),
            }
        players = sorted(
            merged.values(),
            key=lambda row: (
                not row["online"],
                str(row.get("name") or row.get("NickName") or "").casefold(),
                row["player_id"],
            ),
        )
        return {
            "revision": self._revision(),
            "players": players,
            "counts": {
                "all": len(players),
                "online": sum(bool(row["online"]) for row in players),
                "offline": sum(not bool(row["online"]) for row in players),
            },
            "snapshot": (
                self._saved.state
                if self._saved is not None
                else {
                    "state": "unsupported",
                    "captured_at": None,
                    "last_error": (
                        "The connected bridge does not support "
                        "read-only save snapshots."
                    ),
                }
            ),
        }

    def _map_snapshot(self) -> dict[str, Any]:
        if "map.read" not in self._capabilities:
            raise DomainError(
                code="REMOTE_CAPABILITY_UNAVAILABLE",
                message="The connected bridge does not support map reads.",
                field="query",
                http_status=409,
            )
        runtime = self._bridge.map_snapshot(self._connection)
        saved = (
            self._saved.map_data()
            if self._saved is not None
            and self._saved.state.get("state") == "ready"
            else {}
        )
        merged: dict[str, dict[str, Any]] = {}
        for row in saved.get("players", []):
            if not isinstance(row, dict):
                continue
            player_id = _player_id(row)
            position = _map_position(row)
            if not player_id or position is None:
                continue
            player = {
                "player_id": player_id,
                "playerId": player_id,
                "name": str(row.get("name") or ""),
                "position": position,
                **position,
                "positionStatus": "available",
                "positionSource": "save_last_transform",
                "online": False,
                "source": "snapshot",
            }
            level = _positive_level(row.get("level"))
            if level is not None:
                player["level"] = level
            for source_key, target_key in (
                ("guild_id", "guild_id"),
                ("guildId", "guildId"),
                ("guild_name", "guild_name"),
                ("guildName", "guildName"),
            ):
                value = row.get(source_key)
                if value:
                    player[target_key] = value
            merged[_player_key(player_id)] = player

        runtime_players = runtime.get("players")
        for row in (
            runtime_players if isinstance(runtime_players, list) else []
        ):
            if not isinstance(row, dict):
                continue
            player_id = _player_id(row)
            if not player_id:
                continue
            key = _player_key(player_id)
            previous = merged.get(key, {})
            runtime_position = _map_position(row)
            saved_position = _map_position(previous)
            position = runtime_position or saved_position
            player = {
                **previous,
                **row,
                "player_id": player_id,
                "online": True,
                "source": (
                    "runtime+snapshot" if previous else "runtime"
                ),
            }
            level = (
                _positive_level(row.get("level"))
                or _positive_level(previous.get("level"))
            )
            if level is not None:
                player["level"] = level
            else:
                player.pop("level", None)
            if position is not None:
                player.update(
                    {
                        "position": position,
                        **position,
                        "positionStatus": "available",
                        "positionSource": (
                            str(row.get("positionSource") or "pawn")
                            if runtime_position is not None
                            else "save_last_transform"
                        ),
                    }
                )
                player.pop("positionError", None)
            merged[key] = player

        players = sorted(
            merged.values(),
            key=lambda row: (
                not bool(row["online"]),
                str(row.get("name") or "").casefold(),
                str(row.get("player_id") or ""),
            ),
        )
        return {
            **runtime,
            "players": players,
            "presence": {
                "all": len(players),
                "online": sum(bool(row["online"]) for row in players),
                "offline": sum(not bool(row["online"]) for row in players),
            },
            "snapshot": (
                self._saved.state
                if self._saved is not None
                else {
                    "state": "unsupported",
                    "captured_at": None,
                    "last_error": (
                        "The connected bridge does not support "
                        "read-only save snapshots."
                    ),
                }
            ),
        }

    def _player_query(
        self,
        player_id: str,
        *,
        runtime_capability: str,
        runtime: Callable[[], dict[str, Any]],
        saved: Callable[[SavedPlayerAdapter], dict[str, Any]],
        merge_saved_runtime: bool = False,
    ) -> dict[str, Any]:
        online_ids = (
            {
                _player_key(_player_id(row))
                for row in self._bridge.players(self._connection)
                if _player_id(row)
            }
            if "player.list" in self._capabilities
            else set()
        )
        if (
            _player_key(player_id) in online_ids
            and runtime_capability in self._capabilities
        ):
            runtime_result = runtime()
            if (
                merge_saved_runtime
                and self._saved is not None
                and self._saved.state.get("state") == "ready"
            ):
                try:
                    saved_result = saved(self._saved)
                except (DomainError, KeyError, LookupError, ValueError):
                    return runtime_result
                saved_player = saved_result.get("player")
                runtime_player = runtime_result.get("player")
                if isinstance(saved_player, dict) and isinstance(
                    runtime_player, dict
                ):
                    merged_player = {
                        **saved_player,
                        **runtime_player,
                        "source": "runtime+snapshot",
                        "captured_at": saved_player.get("captured_at"),
                    }
                    level = (
                        _positive_level(runtime_player.get("level"))
                        or _positive_level(saved_player.get("level"))
                    )
                    if level is not None:
                        merged_player["level"] = level
                    else:
                        merged_player.pop("level", None)
                    return {
                        **saved_result,
                        **runtime_result,
                        "player": merged_player,
                    }
            return runtime_result
        if (
            self._saved is not None
            and self._saved.state.get("state") == "ready"
        ):
            return saved(self._saved)
        raise DomainError(
            code="REMOTE_OFFLINE_PLAYER_UNSUPPORTED",
            message=(
                "This game version does not support live access to the "
                "selected offline player."
            ),
            details={
                "player_id": player_id,
                "snapshot": (
                    self._saved.state if self._saved is not None else None
                ),
            },
            http_status=409,
        )

    def _runtime_sections(
        self, saved_row: dict[str, Any]
    ) -> list[str]:
        sections = set(saved_row.get("available_sections") or ())
        if "player.details" in self._capabilities:
            sections.add("profile")
        if "inventory.read" in self._capabilities:
            sections.add("inventory")
        if "pal.list" in self._capabilities:
            sections.update({"party_pals", "palbox"})
        return sorted(sections)

    def _target_capabilities(
        self, *, online: bool, has_user_id: bool
    ) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for operation in _PLAYER_TARGET_OPERATIONS:
            if operation not in self._capabilities:
                supported = False
                reason = "capability_unavailable"
            elif operation == "player.unban":
                supported = has_user_id
                reason = (
                    None
                    if supported
                    else "administrator_user_id_unavailable"
                )
            elif operation in {"player.kick", "player.ban"}:
                supported = online and has_user_id
                reason = (
                    None
                    if supported
                    else (
                        "offline_runtime_write_unavailable"
                        if not online
                        else "administrator_user_id_unavailable"
                    )
                )
            else:
                supported = online
                reason = (
                    None
                    if supported
                    else "offline_runtime_write_unavailable"
                )
            result[operation] = {
                "supported": supported,
                "reason": reason,
            }
        return result

    def _start_snapshot_refresh(self) -> None:
        if self._snapshot_thread is not None:
            return

        def refresh() -> None:
            if not self._stop.is_set() and self._saved is not None:
                self._saved.refresh()

        self._snapshot_thread = Thread(
            target=refresh,
            name="pal-editor-live-snapshot",
            daemon=True,
        )
        self._snapshot_thread.start()

    @staticmethod
    def _validated_player_id(value: object) -> str:
        if (
            not isinstance(value, str)
            or not value.strip()
            or len(value) > 128
        ):
            raise DomainError(
                code="REMOTE_PLAYER_ID_INVALID",
                message="A valid player ID is required.",
                field="player_id",
                http_status=400,
            )
        return value.strip()

    def close(self) -> None:
        self._stop.set()
        if self._snapshot_thread is not None:
            self._snapshot_thread.join(timeout=35)
        if self._saved is not None:
            self._saved.close()
