from __future__ import annotations

import unittest

from palworld_save_tools.archive import FArchiveReader, UUID
from palworld_save_tools.rawdata.item_container import decode_bytes, encode_bytes


CREATED_WORLD_ID = "11111111-2222-3333-4444-555555555555"
LOCAL_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


class ItemContainerRawDataTests(unittest.TestCase):
    def test_legacy_permission_layout_roundtrips_without_extension(self) -> None:
        value = {
            "permission": {
                "type_a": [1, 2],
                "type_b": [3],
                "item_static_ids": ["Stone"],
            }
        }

        encoded = encode_bytes(value)
        decoded = decode_bytes(FArchiveReader(b""), encoded)

        self.assertEqual(value, decoded)
        self.assertEqual(encoded, encode_bytes(decoded))

    def test_current_layout_decodes_categories_and_used_dynamic_ids(self) -> None:
        value = {
            "permission": {
                "type_a": [],
                "type_b": [],
                "item_static_ids": [],
                "item_categories": ["Weapon", "Armor"],
            },
            "used_dynamic_item_ids": [
                {
                    "created_world_id": UUID.from_str(CREATED_WORLD_ID),
                    "local_id_in_created_world": UUID.from_str(LOCAL_ID),
                }
            ],
        }

        encoded = encode_bytes(value)
        decoded = decode_bytes(FArchiveReader(b""), encoded)

        self.assertEqual(["Weapon", "Armor"], decoded["permission"]["item_categories"])
        self.assertEqual(CREATED_WORLD_ID, str(decoded["used_dynamic_item_ids"][0]["created_world_id"]))
        self.assertEqual(LOCAL_ID, str(decoded["used_dynamic_item_ids"][0]["local_id_in_created_world"]))
        self.assertNotIn("trailing_unparsed_data", decoded)
        self.assertEqual(encoded, encode_bytes(decoded))

    def test_used_dynamic_ids_cannot_be_encoded_without_current_extension(self) -> None:
        value = {
            "permission": {
                "type_a": [],
                "type_b": [],
                "item_static_ids": [],
            },
            "used_dynamic_item_ids": [],
        }

        with self.assertRaisesRegex(ValueError, "item_categories"):
            encode_bytes(value)


if __name__ == "__main__":
    unittest.main()
