from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest

from palworld_pal_editor.application.base_storage_editor import BaseStorageEditor
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.core.base_storage_data import BaseStorageBinding
from palworld_pal_editor.core.item_container_data import ItemContainerData
from palworld_pal_editor.core.pal_objects import PalObjects, toUUID
from palworld_pal_editor.domain.commands import (
    ClearBaseStorageItemSlot,
    PutBaseStorageItem,
    UpdateBaseStorageItemCount,
)
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.domain.item_catalog import ItemCatalog
from palworld_pal_editor.domain.models import (
    ItemCatalogEntry,
    ItemContainerType,
)


ZERO = toUUID("00000000-0000-0000-0000-000000000000")
GUILD_ID = toUUID("11111111-1111-1111-1111-111111111111")
BASE_ID = toUUID("22222222-2222-2222-2222-222222222222")
CONTAINER_ID = toUUID("33333333-3333-3333-3333-333333333333")
OBJECT_ID = toUUID("44444444-4444-4444-4444-444444444444")


def slot(index: int, static_id: str = "Stone", count: int = 5) -> dict:
    return {
        "RawData": {
            "value": {
                "slot_index": index,
                "count": count,
                "item": {
                    "static_id": static_id,
                    "dynamic_id": {
                        "created_world_id": ZERO,
                        "local_id_in_created_world": ZERO,
                    },
                },
                "permission": {
                    "type_a": [],
                    "type_b": [],
                    "item_static_ids": [],
                },
                "corruption_progress_value": 0.0,
                "trailing_bytes": [0, 0, 0, 0],
            }
        }
    }


def item_container_gvas():
    return SimpleNamespace(
        properties={
            "worldSaveData": {
                "value": {
                    "ItemContainerSaveData": {
                        "value": [
                            {
                                "key": {
                                    "ID": PalObjects.Guid(CONTAINER_ID)
                                },
                                "value": {
                                    "SlotNum": PalObjects.IntProperty(2),
                                    "Slots": {
                                        "value": {
                                            "values": [
                                                slot(0),
                                                slot(1, "None", 0),
                                            ]
                                        }
                                    },
                                },
                            }
                        ]
                    }
                }
            }
        }
    )


def catalog() -> ItemCatalog:
    return ItemCatalog(
        [
            ItemCatalogEntry(
                static_id="Stone",
                names={"en": "Stone"},
                descriptions={"en": "Stone"},
                category="common",
                rarity=0,
                icon="stone",
                max_stack=9999,
                allowed_containers=(ItemContainerType.BASE_STORAGE,),
                dynamic_kind="none",
                rule_status="verified",
                rule_source="synthetic-test",
                rule_version="fixture-v1",
            )
        ]
    )


class _Index:
    complete = True

    def __init__(self) -> None:
        self.binding = BaseStorageBinding(
            guild_id=GUILD_ID,
            base_id=BASE_ID,
            map_object_instance_id=OBJECT_ID,
            map_object_type="ItemChest",
            container_id=CONTAINER_ID,
            usage_type=1,
            location={"x": 1.0, "y": 2.0, "z": 3.0},
        )

    def get_base(self, guild_id, base_id):
        if (
            str(guild_id) == str(GUILD_ID)
            and str(base_id) == str(BASE_ID)
        ):
            return (self.binding,)
        return ()

    def resolve(self, guild_id, base_id, container_id):
        if (
            str(guild_id) == str(GUILD_ID)
            and str(base_id) == str(BASE_ID)
            and str(container_id) == str(CONTAINER_ID)
        ):
            return self.binding
        return None

    def issues(self):
        return ()


class BaseStorageEditorTests(unittest.TestCase):
    def setUp(self) -> None:
        item_data = ItemContainerData(item_container_gvas())
        group = SimpleNamespace(group_id=GUILD_ID)
        camp = SimpleNamespace(
            id=BASE_ID,
            owner_group_id=GUILD_ID,
        )
        manager = SimpleNamespace(
            gvas_file=SimpleNamespace(header=None),
            group_data=SimpleNamespace(
                get_group=lambda guild_id: (
                    group if str(guild_id) == str(GUILD_ID) else None
                )
            ),
            camp_data=SimpleNamespace(
                get_camp=lambda base_id: (
                    camp if str(base_id) == str(BASE_ID) else None
                )
            ),
            base_storage_data=_Index(),
            base_storage_error=None,
            item_container_data=item_data,
            player_mapping={},
        )
        self.session = SaveSession.from_loaded_manager(
            manager, Path("synthetic-save")
        )
        self.editor = BaseStorageEditor(self.session, catalog())
        self.container = item_data.get(CONTAINER_ID)

    def test_reads_dense_slots_for_one_owned_base(self) -> None:
        payload = self.editor.get_storage(str(GUILD_ID), str(BASE_ID))

        self.assertEqual("available", payload["status"])
        self.assertEqual(1, len(payload["containers"]))
        container = payload["containers"][0]
        self.assertEqual(str(CONTAINER_ID), container["container_id"])
        self.assertEqual("ItemChest", container["map_object_type"])
        self.assertEqual("Wooden Chest", container["building_name"])
        self.assertEqual(["occupied", "empty"], [
            value["state"] for value in container["slots"]
        ])
        self.assertEqual(
            9999,
            container["slots"][0]["item"]["max_stack"],
        )

    def test_put_update_and_clear_are_revision_bound(self) -> None:
        put = self.editor.execute(
            PutBaseStorageItem(
                session_id=self.session.session_id,
                expected_revision=0,
                guild_id=str(GUILD_ID),
                base_id=str(BASE_ID),
                container_id=str(CONTAINER_ID),
                slot_index=1,
                static_id="Stone",
                count=3,
            )
        )
        self.assertEqual(1, put["revision"])
        self.assertEqual(3, self.container.get_occupied(1).count)

        update = self.editor.execute(
            UpdateBaseStorageItemCount(
                session_id=self.session.session_id,
                expected_revision=1,
                guild_id=str(GUILD_ID),
                base_id=str(BASE_ID),
                container_id=str(CONTAINER_ID),
                slot_index=1,
                expected_static_id="Stone",
                count=9,
            )
        )
        self.assertEqual(2, update["revision"])
        self.assertEqual(9, self.container.get_occupied(1).count)

        cleared = self.editor.execute(
            ClearBaseStorageItemSlot(
                session_id=self.session.session_id,
                expected_revision=2,
                guild_id=str(GUILD_ID),
                base_id=str(BASE_ID),
                container_id=str(CONTAINER_ID),
                slot_index=1,
                expected_static_id="Stone",
            )
        )
        self.assertEqual(3, cleared["revision"])
        self.assertTrue(self.container.is_empty(1))
        self.assertEqual(
            [
                "PutBaseStorageItem",
                "UpdateBaseStorageItemCount",
                "ClearBaseStorageItemSlot",
            ],
            [
                change["command"]
                for change in self.session.changes()
            ],
        )
        self.assertEqual(
            str(BASE_ID),
            self.session.changes()[0]["target"]["base_id"],
        )

    def test_rejects_container_outside_exact_guild_base_scope(self) -> None:
        with self.assertRaises(DomainError) as context:
            self.editor.execute(
                UpdateBaseStorageItemCount(
                    session_id=self.session.session_id,
                    expected_revision=0,
                    guild_id=str(GUILD_ID),
                    base_id=str(BASE_ID),
                    container_id=(
                        "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
                    ),
                    slot_index=0,
                    expected_static_id="Stone",
                    count=2,
                )
            )

        self.assertEqual(
            "BASE_STORAGE_OWNERSHIP_VIOLATION",
            context.exception.code,
        )
        self.assertEqual(5, self.container.get_occupied(0).count)
        self.assertEqual(0, self.session.revision)

    def test_incomplete_index_allows_read_but_blocks_write(self) -> None:
        self.session.manager.base_storage_data.complete = False

        payload = self.editor.get_storage(str(GUILD_ID), str(BASE_ID))
        self.assertEqual("read_only", payload["status"])

        with self.assertRaises(DomainError) as context:
            self.editor.execute(
                UpdateBaseStorageItemCount(
                    session_id=self.session.session_id,
                    expected_revision=0,
                    guild_id=str(GUILD_ID),
                    base_id=str(BASE_ID),
                    container_id=str(CONTAINER_ID),
                    slot_index=0,
                    expected_static_id="Stone",
                    count=2,
                )
            )
        self.assertEqual(
            "BASE_STORAGE_INDEX_INCOMPLETE",
            context.exception.code,
        )


if __name__ == "__main__":
    unittest.main()
