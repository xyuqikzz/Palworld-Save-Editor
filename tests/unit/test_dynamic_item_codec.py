from __future__ import annotations

import unittest

from palworld_pal_editor.core.pal_objects import toUUID
from palworld_save_tools.archive import FArchiveReader, FArchiveWriter
from palworld_save_tools.rawdata.dynamic_item import decode_bytes, encode_bytes


WORLD_ID = toUUID("11111111-2222-3333-4444-555555555555")
LOCAL_ID = toUUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


def identity(writer: FArchiveWriter, static_id: str) -> None:
    writer.guid(WORLD_ID)
    writer.guid(LOCAL_ID)
    writer.fstring(static_id)


class DynamicItemCodecTests(unittest.TestCase):
    def decode(self, encoded: bytes):
        decoded = decode_bytes(FArchiveReader(b""), encoded)
        self.assertIsInstance(decoded, dict)
        return decoded

    def test_current_weapon_layout_roundtrips_all_envelope_bytes(self) -> None:
        writer = FArchiveWriter()
        identity(writer, "ChargeLaserRifle_5")
        writer.write(bytes([1, 2, 3, 4]))
        writer.float(876.5)
        writer.i32(17)
        writer.tarray(lambda item_writer, value: item_writer.fstring(value), ["Rare"])
        writer.fstring("variant-marker")
        writer.write(bytes([5, 6, 7, 8]))
        encoded = writer.bytes()

        decoded = self.decode(encoded)

        self.assertEqual("weapon", decoded["type"])
        self.assertEqual([1, 2, 3, 4], decoded["leading_bytes"])
        self.assertEqual(876.5, decoded["durability"])
        self.assertEqual(17, decoded["remaining_bullets"])
        self.assertEqual(["Rare"], decoded["passive_skill_list"])
        self.assertEqual("variant-marker", decoded["unknown_str"])
        self.assertEqual([5, 6, 7, 8], decoded["trailing_bytes"])
        self.assertEqual(encoded, encode_bytes(decoded))

    def test_current_armor_layout_roundtrips_all_envelope_bytes(self) -> None:
        writer = FArchiveWriter()
        identity(writer, "SFArmor_5")
        writer.write(bytes([9, 8, 7, 6]))
        writer.float(543.25)
        writer.write(bytes([5, 4, 3, 2]))
        encoded = writer.bytes()

        decoded = self.decode(encoded)

        self.assertEqual("armor", decoded["type"])
        self.assertEqual([9, 8, 7, 6], decoded["leading_bytes"])
        self.assertEqual(543.25, decoded["durability"])
        self.assertEqual([5, 4, 3, 2], decoded["trailing_bytes"])
        self.assertEqual(encoded, encode_bytes(decoded))

    def test_current_egg_layout_roundtrips_all_envelope_bytes(self) -> None:
        writer = FArchiveWriter()
        identity(writer, "PalEgg_Dark_03")
        writer.write(bytes([4, 3, 2, 1]))
        writer.fstring("NegativeOctopus")
        writer.properties({})
        writer.write(bytes(range(28)))
        encoded = writer.bytes()

        decoded = self.decode(encoded)

        self.assertEqual("egg", decoded["type"])
        self.assertEqual([4, 3, 2, 1], decoded["leading_bytes"])
        self.assertEqual("NegativeOctopus", decoded["character_id"])
        self.assertEqual({}, decoded["object"])
        self.assertEqual(list(range(28)), decoded["trailing_bytes"])
        self.assertEqual(encoded, encode_bytes(decoded))


if __name__ == "__main__":
    unittest.main()
