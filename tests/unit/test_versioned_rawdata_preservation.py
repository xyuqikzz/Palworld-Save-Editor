from __future__ import annotations

import unittest

from palworld_save_tools.archive import FArchiveReader, UUID
from palworld_save_tools.rawdata import (
    build_process,
    map_concrete_model,
    map_concrete_model_module,
)


GUID_A = UUID.from_str("11111111-2222-3333-4444-555555555555")
GUID_B = UUID.from_str("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
GUID_C = UUID.from_str("12345678-1234-5678-90ab-cdef12345678")


class VersionedRawDataPreservationTests(unittest.TestCase):
    def test_build_process_preserves_newer_version_tail(self) -> None:
        value = {
            "state": 3,
            "id": GUID_A,
            "trailing_unparsed_data": [9, 8, 7, 6],
        }
        encoded = build_process.encode_bytes(value)

        decoded = build_process.decode_bytes(FArchiveReader(b""), encoded)

        self.assertEqual([9, 8, 7, 6], decoded["trailing_unparsed_data"])
        self.assertEqual(encoded, build_process.encode_bytes(decoded))

    def test_concrete_model_preserves_newer_version_tail(self) -> None:
        value = {
            "concrete_model_type": "PalMapObjectBaseCampPoint",
            "instance_id": GUID_A,
            "model_instance_id": GUID_B,
            "base_camp_id": GUID_C,
            "trailing_unparsed_data": [1, 2, 3, 4, 5, 6, 7, 8],
        }
        encoded = map_concrete_model.encode_bytes(value)

        decoded = map_concrete_model.decode_bytes(
            FArchiveReader(b""), encoded, "PalBoxV2"
        )

        self.assertEqual(value["trailing_unparsed_data"], decoded["trailing_unparsed_data"])
        self.assertEqual(encoded, map_concrete_model.encode_bytes(decoded))

    def test_item_container_module_preserves_newer_version_tail(self) -> None:
        module_type = "EPalMapObjectConcreteModelModuleType::ItemContainer"
        value = {
            "target_container_id": GUID_A,
            "slot_attribute_indexes": [],
            "all_slot_attribute": [],
            "drop_item_at_disposed": False,
            "usage_type": 2,
            "trailing_unparsed_data": [4, 3, 2, 1],
        }
        encoded = map_concrete_model_module.encode_bytes(value, module_type)

        decoded = map_concrete_model_module.decode_bytes(
            FArchiveReader(b""), encoded, module_type
        )

        self.assertEqual(value["trailing_unparsed_data"], decoded["trailing_unparsed_data"])
        self.assertEqual(
            encoded,
            map_concrete_model_module.encode_bytes(decoded, module_type),
        )


if __name__ == "__main__":
    unittest.main()
