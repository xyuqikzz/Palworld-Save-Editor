from __future__ import annotations

import pytest

from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.remote.live_player_management import (
    InMemorySavedPlayerAdapter,
    LivePlayerManagement,
    RemoteSaveSnapshotAdapter,
)
from palworld_pal_editor.remote.models import BridgeConnection


class _RuntimeBridge:
    def __init__(self):
        self.online = True

    def players(self, connection):
        if not self.online:
            return []
        return [
            {
                "playerId": "{AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA}",
                "name": "Runtime One",
                "level": 25,
                "userId": "steam_test",
            }
        ]

    def player_details(self, connection, player_id):
        return {
            "player": {
                "playerId": player_id,
                "name": "Runtime One",
                "level": 25,
            }
        }

    def inventory(self, connection, player_id):
        return {"status": "available", "containers": [], "source": "runtime"}

    def pals(self, connection, player_id, *, collection, page, page_size):
        return {
            "status": "available",
            "collection": collection,
            "pageIndex": page,
            "pageSize": page_size,
            "pageCount": 0,
            "entries": [],
            "source": "runtime",
        }

    def map_snapshot(self, connection):
        return {
            "live": True,
            "authoritative": True,
            "players": [
                {
                    "playerId": (
                        "{AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA}"
                    ),
                    "name": "Runtime One",
                    "level": 0,
                    "guildId": "guild-one",
                    "position": {"x": 10.0, "y": 20.0, "z": 30.0},
                    "positionStatus": "available",
                    "positionSource": "pawn",
                }
            ],
            "guilds": [{"guildId": "guild-one", "name": "One Guild"}],
        }


def _connection() -> BridgeConnection:
    return BridgeConnection(
        base_url="http://127.0.0.1:8213",
        token="test-token",
        protocol_version=1,
        bridge_version="0.6.1",
        server_name="Test",
        game_version="1.0",
        world_guid="world",
        platform="Win64",
        capabilities=frozenset(
            {
                "player.list",
                "player.details",
                "inventory.read",
                "pal.list",
                "inventory.grant",
                "player.ban",
                "player.kick",
                "player.unban",
                "map.read",
                "save.snapshot.read",
            }
        ),
    )


def _management() -> LivePlayerManagement:
    saved = InMemorySavedPlayerAdapter(
        [
            {
                "player_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "name": "Saved One",
                "level": 20,
                "online": False,
                "source": "snapshot",
                "last_location": {"x": 1.0, "y": 2.0, "z": 3.0},
                "available_sections": ["profile", "inventory"],
            },
            {
                "player_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                "name": "Offline Two",
                "level": 10,
                "online": False,
                "source": "snapshot",
                "last_location": {"x": 4.0, "y": 5.0, "z": 6.0},
                "available_sections": ["profile", "inventory"],
            },
        ]
    )
    return LivePlayerManagement(
        bridge=_RuntimeBridge(),
        connection=_connection(),
        revision=lambda: 7,
        execute_command=lambda command: {"state": "completed"},
        saved_adapter=saved,
        start_snapshot=False,
    )


def test_directory_merges_runtime_over_snapshot_by_player_uid() -> None:
    management = _management()

    result = management.query({"query": "player.directory"})

    assert result["revision"] == 7
    assert result["counts"] == {"all": 2, "online": 1, "offline": 1}
    assert result["players"][0]["name"] == "Runtime One"
    assert result["players"][0]["source"] == "runtime+snapshot"
    assert result["players"][0]["capabilities"]["inventory.grant"] == {
        "supported": True,
        "reason": None,
    }
    assert result["players"][1]["name"] == "Offline Two"
    assert result["players"][1]["capabilities"]["inventory.grant"] == {
        "supported": False,
        "reason": "offline_runtime_write_unavailable",
    }


def test_directory_keeps_saved_level_when_runtime_level_is_invalid() -> None:
    class _ZeroLevelRuntimeBridge(_RuntimeBridge):
        def players(self, connection):
            rows = super().players(connection)
            rows[0]["level"] = 0
            return rows

        def player_details(self, connection, player_id):
            result = super().player_details(connection, player_id)
            result["player"]["level"] = 0
            return result

    saved = InMemorySavedPlayerAdapter(
        [
            {
                "player_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "name": "Saved One",
                "level": 77,
            }
        ]
    )
    management = LivePlayerManagement(
        bridge=_ZeroLevelRuntimeBridge(),
        connection=_connection(),
        revision=lambda: 7,
        execute_command=lambda command: {"state": "completed"},
        saved_adapter=saved,
        start_snapshot=False,
    )

    player = management.query({"query": "player.directory"})["players"][0]
    details = management.query(
        {
            "query": "player.details",
            "player_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        }
    )["player"]

    assert player["online"] is True
    assert player["source"] == "runtime+snapshot"
    assert player["level"] == 77
    assert details["source"] == "runtime+snapshot"
    assert details["level"] == 77


def test_map_merges_runtime_and_saved_positions_with_presence() -> None:
    management = _management()

    result = management.query({"query": "map.read"})

    assert result["live"] is True
    assert result["players"] == [
        {
            "playerId": (
                "{AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA}"
            ),
            "player_id": (
                "{AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA}"
            ),
            "name": "Runtime One",
            "level": 20,
            "guildId": "guild-one",
            "position": {"x": 10.0, "y": 20.0, "z": 30.0},
            "x": 10.0,
            "y": 20.0,
            "z": 30.0,
            "positionStatus": "available",
            "positionSource": "pawn",
            "online": True,
            "source": "runtime+snapshot",
        },
        {
            "player_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "playerId": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "name": "Offline Two",
            "level": 10,
            "position": {"x": 4.0, "y": 5.0, "z": 6.0},
            "x": 4.0,
            "y": 5.0,
            "z": 6.0,
            "positionStatus": "available",
            "positionSource": "save_last_transform",
            "online": False,
            "source": "snapshot",
        },
    ]
    assert result["presence"] == {"all": 2, "online": 1, "offline": 1}
    assert result["snapshot"]["state"] == "ready"


def test_directory_retains_verified_user_id_for_unban_after_player_leaves() -> None:
    runtime = _RuntimeBridge()
    saved = InMemorySavedPlayerAdapter(
        [
            {
                "player_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "name": "Saved One",
                "online": False,
                "source": "snapshot",
                "available_sections": ["profile"],
            }
        ]
    )
    management = LivePlayerManagement(
        bridge=runtime,
        connection=_connection(),
        revision=lambda: 7,
        execute_command=lambda command: {"state": "completed"},
        saved_adapter=saved,
        start_snapshot=False,
    )

    online = management.query({"query": "player.directory"})["players"][0]
    assert online["userId"] == "steam_test"
    assert online["capabilities"]["player.ban"]["supported"] is True

    runtime.online = False
    offline = management.query({"query": "player.directory"})["players"][0]

    assert offline["online"] is False
    assert offline["userId"] == "steam_test"
    assert offline["capabilities"]["player.kick"]["supported"] is False
    assert offline["capabilities"]["player.ban"]["supported"] is False
    assert offline["capabilities"]["player.unban"] == {
        "supported": True,
        "reason": None,
    }


def test_queries_prefer_runtime_online_and_snapshot_offline() -> None:
    management = _management()

    online = management.query(
        {
            "query": "player.details",
            "player_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        }
    )
    offline = management.query(
        {
            "query": "player.details",
            "player_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        }
    )

    assert online["player"]["name"] == "Runtime One"
    assert offline["player"]["name"] == "Offline Two"


def test_saved_directory_remains_available_without_runtime_player_list() -> None:
    class _SnapshotOnlyBridge:
        def players(self, connection):
            raise AssertionError("runtime players must remain capability-gated")

    saved = InMemorySavedPlayerAdapter(
        [
            {
                "player_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                "name": "Offline Two",
            }
        ]
    )
    connection = BridgeConnection(
        base_url="http://127.0.0.1:8213",
        token="test-token",
        protocol_version=1,
        bridge_version="0.6.1",
        server_name="Test",
        game_version="1.0",
        world_guid="world",
        platform="Win64",
        capabilities=frozenset({"save.snapshot.read"}),
    )
    management = LivePlayerManagement(
        bridge=_SnapshotOnlyBridge(),
        connection=connection,
        revision=lambda: 3,
        execute_command=lambda command: {"state": "completed"},
        saved_adapter=saved,
        start_snapshot=False,
    )

    directory = management.query({"query": "player.directory"})
    details = management.query(
        {
            "query": "player.details",
            "player_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        }
    )

    assert directory["counts"] == {"all": 1, "online": 0, "offline": 1}
    assert details["player"]["name"] == "Offline Two"


def test_snapshot_manifest_rejects_paths_and_requires_level() -> None:
    valid_file = {
        "fileId": "a" * 32,
        "name": "Level.sav",
        "size": 1,
        "sha256": "b" * 64,
    }
    assert RemoteSaveSnapshotAdapter._validated_manifest(
        {"files": [valid_file]}
    )[0]["name"] == "Level.sav"

    with pytest.raises(DomainError) as traversal:
        RemoteSaveSnapshotAdapter._validated_manifest(
            {
                "files": [
                    valid_file,
                    {
                        "fileId": "c" * 32,
                        "name": "../Players/evil.sav",
                        "size": 1,
                        "sha256": "d" * 64,
                    },
                ]
            }
        )
    assert traversal.value.code == "REMOTE_SNAPSHOT_MANIFEST_INVALID"

    with pytest.raises(DomainError) as no_level:
        RemoteSaveSnapshotAdapter._validated_manifest(
            {
                "files": [
                    {
                        "fileId": "c" * 32,
                        "name": f"Players/{'D' * 32}.sav",
                        "size": 1,
                        "sha256": "d" * 64,
                    }
                ]
            }
        )
    assert no_level.value.code == "REMOTE_SNAPSHOT_MANIFEST_INVALID"
