from __future__ import annotations

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token
import pytest

import palworld_pal_editor.api.remote as remote_api
from palworld_pal_editor.api.remote import remote_blueprint
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.remote.models import BridgeConnection
from palworld_pal_editor.remote.profile import RemoteConnectionProfileStore
from palworld_pal_editor.remote.session import REMOTE_SESSION_RUNTIME


class _FakeBridge:
    def connect(self, spec):
        return BridgeConnection(
            base_url=spec.base_url,
            token="test-token",
            protocol_version=1,
            bridge_version="0.1.0",
            server_name="Remote Test",
            game_version="1.0.0",
            world_guid="test-world",
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
            "authoritative": True,
            "instanceMode": "single_player",
            "online_player_count": 1,
            "capabilities": [
                "server.status",
                "player.list",
                "guild.list",
                "player.details",
                "inventory.read",
                "pal.list",
                "map.read",
                "inventory.grant",
            ],
        }

    def players(self, connection):
        return [{"player_uid": "player-1", "name": "One"}]

    def guilds(self, connection):
        return [
            {
                "guildId": "guild-1",
                "name": "Guild One",
                "onlineMemberCount": 1,
            }
        ]

    def map_snapshot(self, connection):
        return {
            "live": True,
            "authoritative": True,
            "instanceMode": "single_player",
            "players": [
                {
                    "playerId": "player-1",
                    "name": "One",
                    "guildId": "guild-1",
                    "position": {"x": 1.0, "y": 2.0, "z": 3.0},
                    "positionStatus": "available",
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
        return {
            "status": "available",
            "containers": [],
        }

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
        return {
            "commandId": command.command_id,
            "state": "completed",
            "result": {"granted": 1},
        }

    def disconnect(self, connection):
        return None


class _FakeCredentialProtector:
    available = True

    def protect(self, secret):
        assert secret == "server-admin-password"
        return "test-protected-payload"

    def unprotect(self, payload):
        assert payload == "test-protected-payload"
        return "server-admin-password"


class _FakeLocalDiscovery:
    def discover_spec(self):
        from palworld_pal_editor.remote.models import RemoteConnectionSpec

        return RemoteConnectionSpec.create(
            address="http://127.0.0.1:49123",
            username="local",
            admin_password="local-secret",
            allow_insecure_local=True,
        )


def _client(tmp_path, monkeypatch: pytest.MonkeyPatch):
    REMOTE_SESSION_RUNTIME.replace_bridge_factory_for_tests(_FakeBridge)
    profile_store = RemoteConnectionProfileStore(
        tmp_path / "remote-connection.json",
        _FakeCredentialProtector(),
    )
    monkeypatch.setattr(
        remote_api,
        "REMOTE_CONNECTION_PROFILE_STORE",
        profile_store,
    )
    app = Flask(__name__)
    app.config.update(
        JWT_SECRET_KEY="test-secret-key-that-is-at-least-32-bytes",
        TESTING=True,
    )
    JWTManager(app)
    app.register_blueprint(remote_blueprint, url_prefix="/api/remote")
    with app.app_context():
        token = create_access_token(identity="test-user")
    return (
        app.test_client(),
        {"Authorization": f"Bearer {token}"},
        profile_store,
    )


def test_remote_api_connects_persists_resumes_and_executes(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, headers, profile_store = _client(tmp_path, monkeypatch)
    response = client.post(
        "/api/remote/connect",
        headers=headers,
        json={
            "address": "http://127.0.0.1:8213",
            "admin_password": "server-admin-password",
            "allow_insecure_local": True,
            "remember_credential": True,
        },
    )
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["ready"] is True
    session_id = data["session"]["session_id"]
    assert data["profile"]["credential_saved"] is True
    assert "server-admin-password" not in profile_store._path.read_text(
        encoding="utf-8"
    )

    response = client.get("/api/remote/profile", headers=headers)
    assert response.status_code == 200
    assert response.get_json()["data"]["profile"]["address"] == (
        "http://127.0.0.1:8213"
    )

    response = client.get("/api/remote/session", headers=headers)
    assert response.status_code == 200
    assert response.get_json()["data"]["session"]["session_id"] == session_id

    response = client.get(
        f"/api/remote/players?session_id={session_id}",
        headers=headers,
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["players"][0]["name"] == "One"

    response = client.get(
        f"/api/remote/guilds?session_id={session_id}",
        headers=headers,
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["guilds"][0]["name"] == "Guild One"

    response = client.get(
        f"/api/remote/map?session_id={session_id}",
        headers=headers,
    )
    assert response.status_code == 200
    map_data = response.get_json()["data"]
    assert map_data["live"] is True
    assert map_data["players"][0]["position"]["z"] == 3.0
    assert isinstance(map_data["sampled_at"], str)

    response = client.get(
        (
            "/api/remote/players/player-1/details"
            f"?session_id={session_id}"
        ),
        headers=headers,
    )
    assert response.status_code == 200
    details = response.get_json()["data"]
    assert details["player"]["level"] == 10
    assert "inventory" not in details
    assert "pals" not in details

    response = client.get(
        (
            "/api/remote/players/player-1/inventory"
            f"?session_id={session_id}"
        ),
        headers=headers,
    )
    assert response.status_code == 200
    inventory = response.get_json()["data"]["inventory"]
    assert inventory["status"] == "available"

    response = client.get(
        (
            "/api/remote/players/player-1/pals"
            f"?session_id={session_id}&page=0&page_size=12"
        ),
        headers=headers,
    )
    assert response.status_code == 200
    pals = response.get_json()["data"]["pals"]
    assert pals["status"] == "available"
    assert pals["pageIndex"] == 0
    assert pals["collection"] == "palbox"

    response = client.get(
        (
            "/api/remote/players/player-1/pals"
            f"?session_id={session_id}&collection=party&page=0&page_size=5"
        ),
        headers=headers,
    )
    assert response.status_code == 200
    party = response.get_json()["data"]["pals"]
    assert party["collection"] == "party"
    assert party["pageSize"] == 5

    response = client.get(
        (
            "/api/remote/players/player-1/pals"
            f"?session_id={session_id}&collection=unknown&page=0&page_size=5"
        ),
        headers=headers,
    )
    assert response.status_code == 400
    assert (
        response.get_json()["error"]["code"]
        == "REMOTE_PAL_COLLECTION_INVALID"
    )
    assert pals["pageSize"] == 12

    response = client.post(
        "/api/remote/commands",
        headers=headers,
        json={
            "session_id": session_id,
            "expected_revision": 0,
            "operation": "inventory.grant",
            "target": {"player_uid": "player-1"},
            "payload": {"item_id": "TestItem", "quantity": 1},
        },
    )
    assert response.status_code == 200
    result = response.get_json()["data"]
    assert result["revision"] == 1
    assert result["result"]["granted"] == 1


def test_remote_api_accepts_public_plain_http_and_rejects_unknown_fields(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, headers, _ = _client(tmp_path, monkeypatch)
    response = client.post(
        "/api/remote/connect",
        headers=headers,
        json={
            "address": "http://example.test:8213",
            "admin_password": "server-admin-password",
        },
    )
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["profile"]["address"] == "http://example.test:8213"
    assert client.post(
        "/api/remote/disconnect",
        headers=headers,
        json={"session_id": data["session"]["session_id"]},
    ).status_code == 200

    response = client.post(
        "/api/remote/connect",
        headers=headers,
        json={
            "address": "https://example.test:8213",
            "admin_password": "server-admin-password",
            "unexpected": True,
        },
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "UNSUPPORTED_COMMAND_FIELD"


def test_remote_api_reconnects_with_saved_windows_credential(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, headers, _ = _client(tmp_path, monkeypatch)
    response = client.post(
        "/api/remote/connect",
        headers=headers,
        json={
            "address": "http://127.0.0.1:8213",
            "admin_password": "server-admin-password",
            "allow_insecure_local": True,
            "remember_credential": True,
        },
    )
    assert response.status_code == 200
    session_id = response.get_json()["data"]["session"]["session_id"]
    assert client.post(
        "/api/remote/disconnect",
        headers=headers,
        json={"session_id": session_id},
    ).status_code == 200

    response = client.post("/api/remote/reconnect", headers=headers, json={})
    assert response.status_code == 200
    assert response.get_json()["data"]["session"]["server"]["name"] == (
        "Remote Test"
    )


def test_remote_api_connects_only_authoritative_local_game(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, headers, _ = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(
        remote_api,
        "LOCAL_BRIDGE_DISCOVERY",
        _FakeLocalDiscovery(),
    )

    response = client.post(
        "/api/remote/connect-local",
        headers=headers,
        json={},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["connection_kind"] == "local_game"
    assert data["instanceMode"] == "single_player"
    assert data["session"]["server"]["instance_kind"] == ""


def test_remote_api_retries_transient_local_bridge_connection(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _TransientLocalBridge(_FakeBridge):
        connect_attempts = 0

        def connect(self, spec):
            type(self).connect_attempts += 1
            if type(self).connect_attempts == 1:
                raise DomainError(
                    code="REMOTE_CONNECTION_FAILED",
                    message="The remote bridge could not be reached.",
                    retryable=True,
                    http_status=502,
                )
            return super().connect(spec)

    client, headers, _ = _client(tmp_path, monkeypatch)
    REMOTE_SESSION_RUNTIME.replace_bridge_factory_for_tests(
        _TransientLocalBridge
    )
    monkeypatch.setattr(
        remote_api,
        "LOCAL_BRIDGE_DISCOVERY",
        _FakeLocalDiscovery(),
    )
    retry_delays = []
    monkeypatch.setattr(
        remote_api,
        "sleep",
        lambda delay: retry_delays.append(delay),
    )

    response = client.post(
        "/api/remote/connect-local",
        headers=headers,
        json={},
    )

    assert response.status_code == 200
    assert _TransientLocalBridge.connect_attempts == 2
    assert retry_delays == [0.1]


def test_remote_api_rejects_joining_client_local_game(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _ClientBridge(_FakeBridge):
        def status(self, connection):
            return {
                "ready": True,
                "authoritative": False,
                "instanceMode": "client",
                "capabilities": ["server.status"],
            }

    client, headers, _ = _client(tmp_path, monkeypatch)
    REMOTE_SESSION_RUNTIME.replace_bridge_factory_for_tests(_ClientBridge)
    monkeypatch.setattr(
        remote_api,
        "LOCAL_BRIDGE_DISCOVERY",
        _FakeLocalDiscovery(),
    )

    response = client.post(
        "/api/remote/connect-local",
        headers=headers,
        json={},
    )

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "LOCAL_BRIDGE_NOT_HOST"
