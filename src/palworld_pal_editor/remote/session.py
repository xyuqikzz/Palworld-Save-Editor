from __future__ import annotations

from collections.abc import Callable
from threading import RLock
from typing import Any
import uuid

from palworld_pal_editor.domain.errors import DomainError, stale_revision
from palworld_pal_editor.remote.gateway import (
    HttpRemoteBridgeAdapter,
    RemoteBridgePort,
)
from palworld_pal_editor.remote.models import (
    BridgeConnection,
    RemoteCommand,
    RemoteConnectionSpec,
    utc_now_iso,
)


class RemoteServerSession:
    """Authority module for one authenticated server bridge connection."""

    def __init__(
        self,
        *,
        connection: BridgeConnection,
        bridge: RemoteBridgePort,
    ) -> None:
        self._connection = connection
        self._bridge = bridge
        self._session_id = str(uuid.uuid4())
        self._opened_at = utc_now_iso()
        self._revision = connection.revision
        self._capabilities = set(connection.capabilities)
        self._lock = RLock()
        self._completed_commands: dict[
            str, tuple[RemoteCommand, dict[str, Any]]
        ] = {}

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def revision(self) -> int:
        return self._revision

    def summary(self) -> dict[str, Any]:
        return {
            "session_id": self._session_id,
            "revision": self._revision,
            "opened_at": self._opened_at,
            "server": {
                "name": self._connection.server_name,
                "game_version": self._connection.game_version,
                "world_guid": self._connection.world_guid,
                "platform": self._connection.platform,
                "instance_kind": self._connection.instance_kind,
            },
            "bridge": {
                "version": self._connection.bridge_version,
                "protocol_version": self._connection.protocol_version,
                "expires_at": self._connection.expires_at,
            },
            "capabilities": sorted(self._capabilities),
        }

    def status(self) -> dict[str, Any]:
        result = self._bridge.status(self._connection)
        capabilities = result.get("capabilities")
        if (
            isinstance(capabilities, list)
            and all(isinstance(value, str) for value in capabilities)
        ):
            with self._lock:
                self._capabilities = set(capabilities)
        return {
            **result,
            "session": self.summary(),
        }

    def players(self) -> dict[str, Any]:
        return {
            "session_id": self._session_id,
            "revision": self._revision,
            "players": self._bridge.players(self._connection),
        }

    def guilds(self) -> dict[str, Any]:
        self._require_capability("guild.list")
        return {
            "session_id": self._session_id,
            "revision": self._revision,
            "guilds": self._bridge.guilds(self._connection),
        }

    def map_snapshot(self) -> dict[str, Any]:
        self._require_capability("map.read")
        return {
            "session_id": self._session_id,
            "revision": self._revision,
            "sampled_at": utc_now_iso(),
            **self._bridge.map_snapshot(self._connection),
        }

    def player_details(self, player_id: object) -> dict[str, Any]:
        normalized_player_id = self._player_id(player_id)
        self._require_capability("player.details")
        return {
            "session_id": self._session_id,
            "revision": self._revision,
            **self._bridge.player_details(
                self._connection,
                normalized_player_id,
            ),
        }

    def player_inventory(self, player_id: object) -> dict[str, Any]:
        normalized_player_id = self._player_id(player_id)
        self._require_capability("inventory.read")
        return {
            "session_id": self._session_id,
            "revision": self._revision,
            "inventory": self._bridge.inventory(
                self._connection,
                normalized_player_id,
            ),
        }

    def player_pals(
        self,
        player_id: object,
        *,
        collection: str = "palbox",
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        normalized_player_id = self._player_id(player_id)
        if collection not in {"party", "palbox"}:
            raise DomainError(
                code="REMOTE_PAL_COLLECTION_INVALID",
                message="The Pal collection is invalid.",
                field="collection",
                http_status=400,
            )

        if (
            not isinstance(page, int)
            or isinstance(page, bool)
            or page < 0
            or page > 100000
            or not isinstance(page_size, int)
            or isinstance(page_size, bool)
            or page_size < 1
            or page_size > 30
        ):
            raise DomainError(
                code="REMOTE_PAL_PAGE_INVALID",
                message="The Pal page parameters are invalid.",
                field="page",
                http_status=400,
            )
        self._require_capability("pal.list")
        return {
            "session_id": self._session_id,
            "revision": self._revision,
            "pals": self._bridge.pals(
                self._connection,
                normalized_player_id,
                page=page,
                page_size=page_size,
                collection=collection,
            ),
        }

    def execute(self, command: RemoteCommand) -> dict[str, Any]:
        with self._lock:
            previous = self._completed_commands.get(command.command_id)
            if previous is not None:
                previous_command, previous_response = previous
                if (
                    previous_command.operation != command.operation
                    or previous_command.target != command.target
                    or previous_command.payload != command.payload
                ):
                    raise DomainError(
                        code="REMOTE_COMMAND_ID_REUSED",
                        message="The command ID was already used for another operation.",
                        field="command_id",
                        http_status=409,
                    )
                return previous_response

            self._require_revision(command.expected_revision)
            self._require_capability(command.operation)

            result = self._bridge.execute(self._connection, command)
            state = result.get("state")
            if state != "completed":
                raise DomainError(
                    code="REMOTE_COMMAND_FAILED",
                    message=str(
                        result.get("message")
                        or "The remote command did not complete."
                    ),
                    details={
                        "command_id": command.command_id,
                        "state": state,
                    },
                    retryable=state in {"accepted", "running"},
                    http_status=409 if state in {"accepted", "running"} else 422,
                )
            remote_revision = result.get("revision")
            self._revision = (
                remote_revision
                if isinstance(remote_revision, int)
                and not isinstance(remote_revision, bool)
                and remote_revision > self._revision
                else self._revision + 1
            )
            response = {
                **result,
                "session_id": self._session_id,
                "revision": self._revision,
            }
            self._completed_commands[command.command_id] = (command, response)
            return response

    def close(self) -> None:
        self._bridge.disconnect(self._connection)

    def _require_revision(self, expected_revision: int) -> None:
        if expected_revision != self._revision:
            raise stale_revision(expected_revision, self._revision)

    @staticmethod
    def _player_id(player_id: object) -> str:
        if (
            not isinstance(player_id, str)
            or not player_id.strip()
            or len(player_id) > 128
        ):
            raise DomainError(
                code="REMOTE_PLAYER_ID_INVALID",
                message="A valid player ID is required.",
                field="player_id",
                http_status=400,
            )
        return player_id.strip()

    def _require_capability(self, operation: str) -> None:
        if operation not in self._capabilities:
            raise DomainError(
                code="REMOTE_CAPABILITY_UNSUPPORTED",
                message="The remote server does not support this operation.",
                field="operation",
                details={"operation": operation},
                http_status=409,
            )


class RemoteSessionRuntime:
    def __init__(
        self,
        bridge_factory: Callable[[], RemoteBridgePort] | None = None,
    ) -> None:
        self._bridge_factory = bridge_factory or HttpRemoteBridgeAdapter
        self._current: RemoteServerSession | None = None
        self._lock = RLock()

    def open(self, spec: RemoteConnectionSpec) -> RemoteServerSession:
        bridge = self._bridge_factory()
        connection = bridge.connect(spec)
        candidate = RemoteServerSession(connection=connection, bridge=bridge)
        with self._lock:
            previous = self._current
            self._current = candidate
        if previous is not None:
            previous.close()
        return candidate

    def get(self, session_id: object = None) -> RemoteServerSession:
        with self._lock:
            session = self._current
        if (
            session is None
            or not isinstance(session_id, str)
            or session.session_id != session_id
        ):
            raise DomainError(
                code="REMOTE_SESSION_NOT_FOUND",
                message="No matching remote server session is open.",
                field="session_id",
                http_status=404,
            )
        return session

    def current(self) -> RemoteServerSession:
        with self._lock:
            session = self._current
        if session is None:
            raise DomainError(
                code="REMOTE_SESSION_NOT_FOUND",
                message="No remote server session is open.",
                http_status=404,
            )
        return session

    def close(self, session_id: object) -> dict[str, str]:
        session = self.get(session_id)
        with self._lock:
            if self._current is session:
                self._current = None
        session.close()
        return {"session_id": session.session_id}

    def replace_for_tests(
        self, session: RemoteServerSession | None
    ) -> None:
        with self._lock:
            self._current = session

    def replace_bridge_factory_for_tests(
        self, bridge_factory: Callable[[], RemoteBridgePort]
    ) -> None:
        with self._lock:
            self._bridge_factory = bridge_factory
            self._current = None


REMOTE_SESSION_RUNTIME = RemoteSessionRuntime()
