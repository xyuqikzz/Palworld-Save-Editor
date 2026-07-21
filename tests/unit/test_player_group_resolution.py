from __future__ import annotations

from types import SimpleNamespace
import unittest

from palworld_pal_editor.core.container_data import ContainerData
from palworld_pal_editor.core.group_data import GroupData
from palworld_pal_editor.core.pal_objects import PalObjects, toUUID
from palworld_pal_editor.core.save_manager import SaveManager


PLAYER_ID = toUUID("11111111-1111-1111-1111-111111111111")
PLAYER_INSTANCE_ID = toUUID("22222222-2222-2222-2222-222222222222")
PAL_ID = toUUID("33333333-3333-3333-3333-333333333333")
CONTAINER_ID = toUUID("44444444-4444-4444-4444-444444444444")
GROUP_ID = toUUID("55555555-5555-5555-5555-555555555555")
BASE_ID = toUUID("66666666-6666-6666-6666-666666666666")


def player_object() -> dict:
    value = PalObjects.PalSaveParameter(
        PLAYER_INSTANCE_ID, PLAYER_ID, CONTAINER_ID, 0, GROUP_ID
    )
    value["key"]["PlayerUId"] = PalObjects.Guid(PLAYER_ID)
    parameter = value["value"]["RawData"]["value"]["object"]["SaveParameter"][
        "value"
    ]
    parameter["IsPlayer"] = PalObjects.BoolProperty(True)
    parameter["NickName"] = PalObjects.StrProperty("Synthetic Player")
    return value


def pal_object() -> dict:
    return PalObjects.PalSaveParameter(
        PAL_ID, PLAYER_ID, CONTAINER_ID, 0, GROUP_ID
    )


def synthetic_gvas(
    entities: list[dict], *, include_player_handle: bool = True
) -> SimpleNamespace:
    handles = [PalObjects.individual_character_handle_id(PAL_ID)]
    if include_player_handle:
        handles.insert(
            0,
            PalObjects.individual_character_handle_id(PLAYER_INSTANCE_ID),
        )
    group = {
        "key": GROUP_ID,
        "value": {
            "GroupType": PalObjects.EnumProperty(
                "EPalGroupType", "EPalGroupType::Guild"
            ),
            "RawData": PalObjects.ArrayProperty(
                "ByteProperty",
                {
                    "group_id": GROUP_ID,
                    "guild_name": "Synthetic Guild",
                    "guild_format": "raw",
                    "players": [],
                    "base_ids": [BASE_ID],
                    "individual_character_handle_ids": handles,
                },
            ),
        },
    }
    container = {
        "key": {"ID": PalObjects.Guid(CONTAINER_ID)},
        "value": {
            "Slots": PalObjects.ArrayProperty(
                "StructProperty", {"values": []}
            ),
            "SlotNum": PalObjects.IntProperty(1),
        },
    }
    return SimpleNamespace(
        properties={
            "worldSaveData": {
                "value": {
                    "CharacterSaveParameterMap": {"value": entities},
                    "CharacterContainerSaveData": {"value": [container]},
                    "GroupSaveDataMap": {"value": [group]},
                }
            }
        }
    )


class PlayerGroupResolutionTests(unittest.TestCase):
    def test_raw_guild_tail_uses_verified_character_group_membership(self) -> None:
        entities = [player_object(), pal_object()]
        gvas = synthetic_gvas(entities)
        containers = ContainerData(gvas)
        containers.get_container(CONTAINER_ID).add_pal(PAL_ID, 0)

        manager = SaveManager.create_isolated()
        manager._entities_list = entities
        manager.group_data = GroupData(gvas)
        manager.container_data = containers
        manager._load_entities(lazy_players=True)

        player = manager.player_mapping[str(PLAYER_ID)]
        self.assertEqual("Synthetic Player", player.NickName)
        self.assertEqual([str(PAL_ID)], list(player._palbox))
        self.assertEqual({}, manager._dangling_pals)

    def test_raw_guild_tail_does_not_trust_unverified_group_id(self) -> None:
        entities = [player_object()]
        gvas = synthetic_gvas(entities, include_player_handle=False)

        manager = SaveManager.create_isolated()
        manager._entities_list = entities
        manager.group_data = GroupData(gvas)
        manager.container_data = ContainerData(gvas)
        manager._load_entities(lazy_players=True)

        self.assertEqual({}, manager.player_mapping)


if __name__ == "__main__":
    unittest.main()
