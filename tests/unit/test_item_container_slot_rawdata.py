from __future__ import annotations

import unittest

from palworld_pal_editor.core.pal_objects import toUUID
from palworld_save_tools.archive import FArchiveReader
from palworld_save_tools.rawdata.item_container_slots import decode_bytes, encode_bytes


class ItemContainerSlotRawDataTests(unittest.TestCase):
    def test_current_slot_layout_roundtrips_permission_corruption_and_tail(self) -> None:
        value = {
            "slot_index": 8,
            "count": 1,
            "item": {
                "static_id": "SphereModule_Sniper2",
                "dynamic_id": {
                    "created_world_id": toUUID(
                        "11111111-2222-3333-4444-555555555555"
                    ),
                    "local_id_in_created_world": toUUID(
                        "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
                    ),
                },
            },
            "permission": {
                "type_a": [3, 4, 10, 13],
                "type_b": [67],
                "item_static_ids": ["SphereModule_Sniper2"],
            },
            "corruption_progress_value": 12.5,
            "trailing_bytes": [0, 0, 0, 0],
        }

        encoded = encode_bytes(value)
        decoded = decode_bytes(FArchiveReader(b""), encoded)

        self.assertEqual(8, decoded["slot_index"])
        self.assertEqual(value["permission"], decoded["permission"])
        self.assertEqual(12.5, decoded["corruption_progress_value"])
        self.assertEqual([0, 0, 0, 0], decoded["trailing_bytes"])
        self.assertEqual(encoded, encode_bytes(decoded))

    def test_legacy_core_only_slot_still_roundtrips(self) -> None:
        value = {
            "slot_index": 0,
            "count": 5,
            "item": {
                "static_id": "Stone",
                "dynamic_id": {
                    "created_world_id": toUUID(
                        "00000000-0000-0000-0000-000000000000"
                    ),
                    "local_id_in_created_world": toUUID(
                        "00000000-0000-0000-0000-000000000000"
                    ),
                },
            },
        }

        encoded = encode_bytes(value)
        decoded = decode_bytes(FArchiveReader(b""), encoded)

        self.assertEqual(value, decoded)
        self.assertEqual(encoded, encode_bytes(decoded))


if __name__ == "__main__":
    unittest.main()
