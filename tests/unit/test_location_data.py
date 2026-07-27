from __future__ import annotations

from types import SimpleNamespace

from palworld_pal_editor.application.query_service import SaveQueryService
from palworld_pal_editor.core.location_data import read_transform_translation
from palworld_save_tools.archive import FArchiveWriter


ZERO_GUID = "00000000-0000-0000-0000-000000000000"


def _struct(struct_type: str, value: dict[str, float]) -> dict:
    return {
        "type": "StructProperty",
        "struct_type": struct_type,
        "struct_id": ZERO_GUID,
        "id": None,
        "value": value,
    }


def _skipped_transform(x: float, y: float, z: float) -> dict:
    writer = FArchiveWriter()
    writer.properties(
        {
            "Rotation": _struct(
                "Quat",
                {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
            ),
            "Translation": _struct("Vector", {"x": x, "y": y, "z": z}),
        }
    )
    return {
        "skip_type": "StructProperty",
        "struct_type": "Transform",
        "value": writer.bytes(),
    }


def test_last_transform_raw_bytes_are_read_without_mutation() -> None:
    transform = _skipped_transform(-231967.5, 190354.75, 2338.25)
    before = transform["value"]

    assert read_transform_translation(transform) == {
        "x": -231967.5,
        "y": 190354.75,
        "z": 2338.25,
    }
    assert transform["value"] == before


def test_transform_variants_and_unknown_data_fail_closed() -> None:
    assert read_transform_translation(
        {
            "value": {
                "Translation": _struct(
                    "Vector",
                    {"x": 10.0, "y": 20.0, "z": 30.0},
                )
            }
        }
    ) == {"x": 10.0, "y": 20.0, "z": 30.0}
    assert read_transform_translation(
        {"translation": {"x": 1, "y": 2, "z": 3}}
    ) == {"x": 1.0, "y": 2.0, "z": 3.0}
    assert read_transform_translation(
        {"translation": {"x": float("nan"), "y": 2, "z": 3}}
    ) is None

    trailing = _skipped_transform(1.0, 2.0, 3.0)
    trailing["value"] += b"\x00"
    assert read_transform_translation(trailing) is None


def test_map_query_reports_last_known_players_bases_and_unavailable_ids() -> None:
    group = SimpleNamespace(
        group_id="guild-1",
        guild_name="Northwind",
        base_camp_level=27,
    )
    player = SimpleNamespace(
        PlayerUId="player-1",
        NickName="Ari",
        Level=42,
        group_id="guild-1",
        LastLocation={"x": -100.0, "y": 200.0, "z": 30.0},
    )
    unavailable_player = SimpleNamespace(
        PlayerUId="player-2",
        NickName="Bo",
        Level=11,
        group_id=None,
        LastLocation=None,
    )
    camp = SimpleNamespace(
        id="base-1",
        name="Cliff Base",
        owner_group_id="guild-1",
        location={"x": -80.0, "y": 220.0, "z": 25.0},
        area_range=3500.0,
    )
    unavailable_camp = SimpleNamespace(
        id="base-2",
        name="Unknown Base",
        owner_group_id=None,
        location=None,
        area_range=None,
    )
    manager = SimpleNamespace(
        player_mapping={"player-1": player, "player-2": unavailable_player},
        group_data=SimpleNamespace(get_groups=lambda: [group]),
        camp_data=SimpleNamespace(get_camps=lambda: [camp, unavailable_camp]),
    )
    service = SaveQueryService(SimpleNamespace(manager=manager))

    result = service.map_data()

    assert result["live"] is False
    assert result["location_source"] == "save_last_transform"
    assert result["players"] == [
        {
            "player_id": "player-1",
            "name": "Ari",
            "level": 42,
            "guild_id": "guild-1",
            "guild_name": "Northwind",
            "x": -100.0,
            "y": 200.0,
            "z": 30.0,
        }
    ]
    assert result["bases"][0]["level"] == 27
    assert result["bases"][0]["radius"] == 3500.0
    assert result["unavailable_player_ids"] == ["player-2"]
    assert result["unavailable_base_ids"] == ["base-2"]
