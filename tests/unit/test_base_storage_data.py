from __future__ import annotations

from types import SimpleNamespace
import unittest

from palworld_pal_editor.core.base_storage_data import (
    BaseStorageData,
    ITEM_CONTAINER_MODULE,
)
from palworld_pal_editor.core.pal_objects import toUUID


GUILD_ID = toUUID("11111111-1111-1111-1111-111111111111")
BASE_ID = toUUID("22222222-2222-2222-2222-222222222222")
CONTAINER_ID = toUUID("33333333-3333-3333-3333-333333333333")
OBJECT_ID = toUUID("44444444-4444-4444-4444-444444444444")


def map_object(
    *,
    usage_type: int = 1,
    container_id=CONTAINER_ID,
    guild_id=GUILD_ID,
    base_id=BASE_ID,
) -> dict:
    return {
        "MapObjectId": {"value": "ItemChest"},
        "Model": {
            "value": {
                "RawData": {
                    "value": {
                        "instance_id": OBJECT_ID,
                        "group_id_belong_to": guild_id,
                        "base_camp_id_belong_to": base_id,
                        "initital_transform_cache": {
                            "translation": {
                                "x": 1.0,
                                "y": 2.0,
                                "z": 3.0,
                            }
                        },
                    }
                }
            }
        },
        "ConcreteModel": {
            "value": {
                "ModuleMap": {
                    "value": [
                        {
                            "key": ITEM_CONTAINER_MODULE,
                            "value": {
                                "RawData": {
                                    "value": {
                                        "target_container_id": container_id,
                                        "usage_type": usage_type,
                                    }
                                }
                            },
                        }
                    ]
                }
            }
        },
    }


def gvas(entries: list[dict]):
    return SimpleNamespace(
        properties={
            "worldSaveData": {
                "value": {
                    "MapObjectSaveData": {
                        "type": "ArrayProperty",
                        "array_type": "StructProperty",
                        "value": {
                            "values": entries,
                        },
                    }
                }
            }
        }
    )


class BaseStorageDataTests(unittest.TestCase):
    def test_indexes_only_persistent_storage_with_location(self) -> None:
        index = BaseStorageData(
            gvas([map_object(), map_object(usage_type=0)])
        )

        self.assertTrue(index.complete)
        bindings = index.get_base(GUILD_ID, BASE_ID)
        self.assertEqual(1, len(bindings))
        self.assertEqual(CONTAINER_ID, bindings[0].container_id)
        self.assertEqual("ItemChest", bindings[0].map_object_type)
        self.assertEqual(
            {"x": 1.0, "y": 2.0, "z": 3.0},
            bindings[0].location,
        )
        self.assertIs(
            bindings[0],
            index.resolve(GUILD_ID, BASE_ID, CONTAINER_ID),
        )

    def test_duplicate_container_binding_marks_index_incomplete(self) -> None:
        index = BaseStorageData(gvas([map_object(), map_object()]))

        self.assertFalse(index.complete)
        self.assertEqual(
            ["BASE_STORAGE_CONTAINER_AMBIGUOUS"],
            [issue.code for issue in index.issues()],
        )

    def test_incomplete_persistent_binding_fails_closed(self) -> None:
        index = BaseStorageData(
            gvas(
                [
                    map_object(
                        guild_id=toUUID(
                            "00000000-0000-0000-0000-000000000000"
                        )
                    )
                ]
            )
        )

        self.assertFalse(index.complete)
        self.assertEqual((), index.get_base(GUILD_ID, BASE_ID))
        self.assertEqual(
            "BASE_STORAGE_BINDING_INCOMPLETE",
            index.issues()[0].code,
        )


if __name__ == "__main__":
    unittest.main()
