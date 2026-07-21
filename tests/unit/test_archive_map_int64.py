from __future__ import annotations

import unittest

from palworld_save_tools.archive import FArchiveReader, FArchiveWriter


PROPERTY_PATH = (
    ".worldSaveData.LevelObjectRecoverPartySaveData.Value."
    "PlayerLastUsedTimes"
)


class ArchiveMapInt64Tests(unittest.TestCase):
    def test_reader_supports_int64_map_values(self) -> None:
        writer = FArchiveWriter()
        writer.fstring("NameProperty")
        writer.fstring("Int64Property")
        writer.optional_guid(None)
        writer.u32(0)
        writer.u32(1)
        writer.fstring("player-id")
        writer.i64(-5_000_000_000)
        encoded = writer.bytes()

        decoded = FArchiveReader(encoded).property(
            "MapProperty", len(encoded), PROPERTY_PATH
        )

        self.assertEqual("Int64Property", decoded["value_type"])
        self.assertEqual(
            [{"key": "player-id", "value": -5_000_000_000}], decoded["value"]
        )

    def test_int64_map_values_roundtrip(self) -> None:
        expected = {
            "type": "MapProperty",
            "key_type": "NameProperty",
            "value_type": "Int64Property",
            "key_struct_type": None,
            "value_struct_type": None,
            "id": None,
            "value": [{"key": "player-id", "value": 5_000_000_000}],
        }
        writer = FArchiveWriter()

        size = writer.property_inner("MapProperty", expected)
        encoded = writer.bytes()
        decoded = FArchiveReader(encoded).property(
            "MapProperty", size, PROPERTY_PATH
        )

        self.assertEqual(expected, decoded)


if __name__ == "__main__":
    unittest.main()
