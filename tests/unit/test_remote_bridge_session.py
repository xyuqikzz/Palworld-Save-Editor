from __future__ import annotations

import uuid

import pytest

from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.remote.models import (
    BridgeConnection,
    RemoteCommand,
    RemoteConnectionSpec,
)
from palworld_pal_editor.remote.session import (
    RemoteServerSession,
    RemoteSessionRuntime,
)


class _FakeBridge:
    def __init__(self) -> None:
        self.commands = []
        self.disconnected = False
        self.status_capabilities = [
            "server.status",
            "player.list",
            "guild.list",
            "player.details",
            "inventory.read",
            "pal.list",
            "map.read",
            "inventory.grant",
        ]

    def connect(self, spec):
        return BridgeConnection(
            base_url=spec.base_url,
            token="secret-token",
            protocol_version=1,
            bridge_version="0.1.0",
            server_name="Test Server",
            game_version="1.0.0",
            world_guid="world-guid",
            platform="Win64",
            capabilities=frozenset(
                {
                    "server.status",
                    "player.list",
                    "guild.list",
                    "player.details",
                    "inventory.read",
                    "pal.list",
                    "map.read",
                    "inventory.grant",
                }
            ),
        )

    def status(self, connection):
        return {
            "ready": True,
            "online_player_count": 1,
            "capabilities": self.status_capabilities,
        }

    def players(self, connection):
        return [{"player_uid": "player-1", "name": "One", "level": 10}]

    def guilds(self, connection):
        return [{"guildId": "guild-1", "name": "Guild One"}]

    def map_snapshot(self, connection):
        return {
            "live": True,
            "players": [
                {
                    "playerId": "player-1",
                    "name": "One",
                    "guildId": "guild-1",
                    "position": {"x": 1.0, "y": 2.0, "z": 3.0},
                }
            ],
            "guilds": self.guilds(connection),
        }

    def player_details(self, connection, player_id):
        return {
            "player": {
                "playerId": player_id,
                "name": "One",
                "level": 10,
            },
        }

    def inventory(self, connection, player_id):
        return {"status": "available", "containers": []}

    def pals(self, connection, player_id, *, collection, page, page_size):
        return {
            "status": "available",
            "collection": collection,
            "pageIndex": page,
            "pageSize": page_size,
            "pageCount": 1,
            "entries": [],
        }

    def execute(self, connection, command):
        self.commands.append(command)
        return {
            "commandId": command.command_id,
            "state": "completed",
            "result": {"granted": 1},
        }

    def disconnect(self, connection):
        self.disconnected = True


def _spec() -> RemoteConnectionSpec:
    return RemoteConnectionSpec.create(
        address="http://127.0.0.1:8213",
        username="admin",
        admin_password="do-not-log-this",
        allow_insecure_local=True,
    )


def test_connection_spec_accepts_http_and_https() -> None:
    http_spec = RemoteConnectionSpec.create(
        address="http://example.test:8213",
        admin_password="secret",
    )
    https_spec = RemoteConnectionSpec.create(
        address="https://example.test:8213",
        admin_password="secret",
    )

    assert http_spec.base_url == "http://example.test:8213"
    assert https_spec.base_url == "https://example.test:8213"
    assert _spec().base_url == "http://127.0.0.1:8213"
    assert "secret" not in repr(http_spec)


def test_bridge_login_revision_is_restored_for_reconnects() -> None:
    connection = BridgeConnection.from_payload(
        "http://127.0.0.1:8213",
        {
            "protocolVersion": 1,
            "bridgeVersion": "0.1.0",
            "token": "secret-token",
            "revision": 7,
            "server": {"name": "Test Server"},
            "capabilities": ["server.status"],
        },
    )
    session = RemoteServerSession(connection=connection, bridge=_FakeBridge())

    assert connection.revision == 7
    assert session.summary()["revision"] == 7


def test_remote_session_queries_and_executes_idempotently() -> None:
    bridge = _FakeBridge()
    runtime = RemoteSessionRuntime(lambda: bridge)
    session = runtime.open(_spec())

    assert runtime.current() is session
    assert session.status()["online_player_count"] == 1
    assert session.players()["players"][0]["player_uid"] == "player-1"
    assert session.guilds()["guilds"][0]["name"] == "Guild One"
    assert session.map_snapshot()["players"][0]["position"]["z"] == 3.0
    assert session.player_details("player-1")["player"]["level"] == 10
    assert (
        session.player_inventory("player-1")["inventory"]["status"]
        == "available"
    )
    pals = session.player_pals("player-1", page=0, page_size=12)["pals"]
    assert pals["pageIndex"] == 0
    assert pals["pageSize"] == 12
    assert pals["collection"] == "palbox"

    party = session.player_pals(
        "player-1", collection="party", page=0, page_size=5
    )["pals"]
    assert party["collection"] == "party"
    assert party["pageSize"] == 5


    with pytest.raises(DomainError) as invalid_collection:
        session.player_pals(
            "player-1", collection="unknown", page=0, page_size=5
        )
    assert invalid_collection.value.code == "REMOTE_PAL_COLLECTION_INVALID"
    command_id = str(uuid.uuid4())
    command = RemoteCommand.create(
        command_id=command_id,
        operation="inventory.grant",
        target={"player_uid": "player-1"},
        payload={"item_id": "TestItem", "quantity": 1},
        expected_revision=0,
    )
    first = session.execute(command)
    second = session.execute(
        RemoteCommand.create(
            command_id=command_id,
            operation="inventory.grant",
            target={"player_uid": "player-1"},
            payload={"item_id": "TestItem", "quantity": 1},
            expected_revision=0,
        )
    )

    assert first["revision"] == 1
    assert second == first
    assert len(bridge.commands) == 1

    runtime.close(session.session_id)
    assert bridge.disconnected is True


def test_remote_session_rejects_stale_and_unsupported_commands() -> None:
    bridge = _FakeBridge()
    connection = bridge.connect(_spec())
    session = RemoteServerSession(connection=connection, bridge=bridge)

    with pytest.raises(DomainError) as stale:
        session.execute(
            RemoteCommand.create(
                operation="inventory.grant",
                target={},
                payload={},
                expected_revision=2,
            )
        )
    assert stale.value.code == "STALE_REVISION"

    with pytest.raises(DomainError) as unsupported:
        session.execute(
            RemoteCommand.create(
                operation="pal.delete",
                target={},
                payload={},
                expected_revision=0,
            )
        )
    assert unsupported.value.code == "REMOTE_CAPABILITY_UNSUPPORTED"


def test_remote_session_refreshes_capabilities_after_world_mode_change() -> None:
    bridge = _FakeBridge()
    session = RemoteServerSession(
        connection=bridge.connect(_spec()),
        bridge=bridge,
    )
    bridge.status_capabilities = ["server.status"]

    status = session.status()

    assert status["session"]["capabilities"] == ["server.status"]
    with pytest.raises(DomainError) as unsupported:
        session.execute(
            RemoteCommand.create(
                operation="inventory.grant",
                target={"player_uid": "player-1"},
                payload={"item_id": "TestItem", "quantity": 1},
                expected_revision=0,
            )
        )
    assert unsupported.value.code == "REMOTE_CAPABILITY_UNSUPPORTED"
