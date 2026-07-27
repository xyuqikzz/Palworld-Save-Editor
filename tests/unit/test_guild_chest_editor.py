from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import unittest

from palworld_save_tools.archive import FArchiveReader, FArchiveWriter
from palworld_save_tools.paltypes import (
    PALWORLD_CUSTOM_PROPERTIES,
    PALWORLD_TYPE_HINTS,
)

from palworld_pal_editor.application.guild_chest_editor import GuildChestEditor
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.core.group_data import PalGroup
from palworld_pal_editor.core.guild_item_storage_data import GuildItemStorageData
from palworld_pal_editor.core.item_container_data import ItemContainerData
from palworld_pal_editor.core.pal_objects import PalObjects, toUUID
from palworld_pal_editor.domain.commands import UpdateGuildChestCapacity
from palworld_pal_editor.domain.errors import DomainError
from tests.unit.test_inventory_read import container, slot


GUILD_ID = toUUID("11111111-1111-1111-1111-111111111111")
CONTAINER_ID = toUUID("22222222-2222-2222-2222-222222222222")
ZERO = toUUID("00000000-0000-0000-0000-000000000000")
GUILD_EXTRA_PATH = ".worldSaveData.GuildExtraSaveDataMap"
GUILD_STORAGE_RAW_PATH = (
    f"{GUILD_EXTRA_PATH}.Value.GuildItemStorage.RawData"
)


class _Groups:
    def __init__(self, group: PalGroup) -> None:
        self.group = group

    def get_group(self, group_id):
        return self.group if str(group_id) == str(self.group.group_id) else None


def _group() -> PalGroup:
    return PalGroup(
        {
            "value": {
                "RawData": {
                    "value": {
                        "group_id": GUILD_ID,
                        "group_name": "Guild",
                        "guild_name": "Builders",
                        "individual_character_handle_ids": [],
                        "base_ids": [
                            toUUID(
                                "33333333-3333-3333-3333-333333333333"
                            )
                        ],
                    }
                }
            }
        },
        "EPalGroupType::Guild",
    )


def _opaque_guild_extra_property() -> dict:
    decoded = {
        "type": "MapProperty",
        "key_type": "StructProperty",
        "value_type": "StructProperty",
        "key_struct_type": "Guid",
        "value_struct_type": "StructProperty",
        "id": None,
        "value": [
            {
                "key": GUILD_ID,
                "value": {
                    "GuildItemStorage": {
                        "type": "StructProperty",
                        "struct_type": "PalGuildItemStorageSaveData",
                        "struct_id": ZERO,
                        "id": None,
                        "value": {
                            "RawData": {
                                "type": "ArrayProperty",
                                "array_type": "ByteProperty",
                                "id": None,
                                "value": {"container_id": CONTAINER_ID},
                                "custom_type": GUILD_STORAGE_RAW_PATH,
                            }
                        },
                    }
                },
            }
        ],
    }
    writer = FArchiveWriter(custom_properties=PALWORLD_CUSTOM_PROPERTIES)
    writer.property_inner("MapProperty", deepcopy(decoded))
    reader = FArchiveReader(writer.bytes())
    key_type = reader.fstring()
    value_type = reader.fstring()
    property_id = reader.optional_guid()
    return {
        "type": "MapProperty",
        "skip_type": "MapProperty",
        "custom_type": GUILD_EXTRA_PATH,
        "key_type": key_type,
        "value_type": value_type,
        "id": property_id,
        "value": reader.read_to_end(),
    }


def _manager(*, include_guild_extra: bool = True):
    world = {
        "ItemContainerSaveData": {
            "value": [
                container(
                    CONTAINER_ID,
                    [slot(0, "Stone", 12), slot(1, "None", 0)],
                    capacity=54,
                )
            ]
        }
    }
    if include_guild_extra:
        world["GuildExtraSaveDataMap"] = _opaque_guild_extra_property()
    gvas = SimpleNamespace(
        properties={"worldSaveData": {"value": world}},
        header=None,
    )
    item_containers = ItemContainerData(gvas)
    guild_storage = GuildItemStorageData(gvas)
    return SimpleNamespace(
        gvas_file=gvas,
        group_data=_Groups(_group()),
        player_mapping={},
        item_container_data=item_containers,
        guild_item_storage_data=guild_storage,
        guild_item_storage_error=None,
    )


class GuildItemStorageDataTests(unittest.TestCase):
    def test_decodes_guild_to_shared_item_container_from_opaque_map(self) -> None:
        manager = _manager()

        binding = manager.guild_item_storage_data.get(GUILD_ID)

        self.assertIsNotNone(binding)
        self.assertEqual(str(GUILD_ID), str(binding.guild_id))
        self.assertEqual(str(CONTAINER_ID), str(binding.container_id))
        self.assertEqual(
            54,
            manager.item_container_data.get(binding.container_id).capacity,
        )

    def test_missing_guild_extra_map_is_a_supported_empty_index(self) -> None:
        manager = _manager(include_guild_extra=False)

        self.assertFalse(manager.guild_item_storage_data.source_present)
        self.assertIsNone(manager.guild_item_storage_data.get(GUILD_ID))


class GuildChestEditorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = _manager()
        self.session = SaveSession.from_loaded_manager(
            self.manager, Path("synthetic-save")
        )

    def command(self, capacity: int, **overrides) -> UpdateGuildChestCapacity:
        values = {
            "session_id": self.session.session_id,
            "expected_revision": self.session.revision,
            "guild_id": str(GUILD_ID),
            "capacity": capacity,
        }
        values.update(overrides)
        return UpdateGuildChestCapacity(**values)

    def test_expands_only_the_bound_container_as_one_level_change(self) -> None:
        raw_before = bytes(
            self.manager.gvas_file.properties["worldSaveData"]["value"][
                "GuildExtraSaveDataMap"
            ]["value"]
        )
        target = self.manager.item_container_data.get(CONTAINER_ID)

        result = GuildChestEditor(self.session).execute(self.command(90))

        self.assertEqual(90, target.capacity)
        self.assertEqual(
            90, target._container_obj["value"]["SlotNum"]["value"]
        )
        self.assertEqual([0, 1], [
            value.slot_index for value in target.iter_encoded_slots()
        ])
        self.assertEqual(
            raw_before,
            self.manager.gvas_file.properties["worldSaveData"]["value"][
                "GuildExtraSaveDataMap"
            ]["value"],
        )
        self.assertEqual(1, result["revision"])
        self.assertEqual(90, result["value"]["capacity"])
        self.assertEqual(
            ["level:ItemContainerSaveData"],
            self.session.changes()[0]["affected_records"],
        )

    def test_same_capacity_is_a_revision_checked_noop(self) -> None:
        result = GuildChestEditor(self.session).execute(self.command(54))

        self.assertIsNone(result["change_id"])
        self.assertEqual(0, result["revision"])
        self.assertEqual([], self.session.changes())

    def test_rejects_shrinking_and_unverified_oversized_values(self) -> None:
        for capacity, code in (
            (53, "GUILD_CHEST_SHRINK_UNSUPPORTED"),
            (2467, "INVALID_GUILD_CHEST_CAPACITY"),
        ):
            with self.subTest(capacity=capacity), self.assertRaises(
                DomainError
            ) as raised:
                GuildChestEditor(self.session).execute(self.command(capacity))

            self.assertEqual(code, raised.exception.code)
            self.assertEqual(
                54, self.manager.item_container_data.get(CONTAINER_ID).capacity
            )
            self.assertEqual(0, self.session.revision)


if __name__ == "__main__":
    unittest.main()
