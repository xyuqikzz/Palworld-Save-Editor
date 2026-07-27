from __future__ import annotations

import unittest

from palworld_save_tools.archive import FArchiveReader, FArchiveWriter, UUID
from palworld_save_tools.paltypes import PALWORLD_TYPE_HINTS


PROPERTY_PARENT_PATH = ".worldSaveData.InvaderDeclarationSaveData"
PROPERTY_PATH = PROPERTY_PARENT_PATH + ".ValidatedStartPointIds"
PROPERTY_VALUE_PATH = PROPERTY_PATH + ".Value"
START_POINT_ID = "04099789-4a41-4a09-f6f1-99985c080bc8"
LOCKER_PROPERTY_PARENT_PATH = ".worldSaveData"
PLAYER_UID = "7e358108-07d8-4c32-bd21-69c77b15f83d"
INSTANCE_ID = "49a8e005-50ab-4b88-86c8-fd768a010cba"


def encoded_guid_set_property() -> bytes:
    writer = FArchiveWriter()
    writer.fstring("ValidatedStartPointIds")
    writer.fstring("SetProperty")
    writer.u64(24)
    writer.fstring("StructProperty")
    writer.optional_guid(None)
    writer.u32(0)
    writer.u32(1)
    writer.guid(UUID.from_str(START_POINT_ID))
    writer.fstring("None")
    return writer.bytes()


def guid_property(value: str) -> dict:
    return {
        "type": "StructProperty",
        "struct_type": "Guid",
        "struct_id": UUID.from_str("00000000-0000-0000-0000-000000000000"),
        "id": None,
        "value": UUID.from_str(value),
    }


def encoded_locker_character_set_property() -> bytes:
    element_writer = FArchiveWriter()
    element_writer.properties(
        {
            "PlayerUId": guid_property(PLAYER_UID),
            "InstanceId": guid_property(INSTANCE_ID),
        }
    )

    payload_writer = FArchiveWriter()
    payload_writer.u32(0)
    payload_writer.u32(1)
    payload_writer.write(element_writer.bytes())
    payload = payload_writer.bytes()

    writer = FArchiveWriter()
    writer.fstring("InLockerCharacterInstanceIDArray")
    writer.fstring("SetProperty")
    writer.u64(len(payload))
    writer.fstring("StructProperty")
    writer.optional_guid(None)
    writer.write(payload)
    writer.fstring("None")
    return writer.bytes()


class ArchiveSetPropertyTests(unittest.TestCase):
    def test_nested_property_set_roundtrips_with_palworld_type_hint(self) -> None:
        encoded = encoded_locker_character_set_property()

        decoded = FArchiveReader(
            encoded, type_hints=PALWORLD_TYPE_HINTS
        ).properties_until_end(LOCKER_PROPERTY_PARENT_PATH)

        prop = decoded["InLockerCharacterInstanceIDArray"]
        self.assertEqual("StructProperty", prop["set_type"])
        self.assertEqual("StructProperty", prop["set_struct_type"])
        element = prop["value"]["values"][0]
        self.assertEqual(PLAYER_UID, str(element["PlayerUId"]["value"]))
        self.assertEqual(INSTANCE_ID, str(element["InstanceId"]["value"]))

        writer = FArchiveWriter()
        writer.properties(decoded)
        self.assertEqual(encoded, writer.bytes())

    def test_guid_set_property_roundtrips_without_treating_guid_as_properties(
        self,
    ) -> None:
        encoded = encoded_guid_set_property()
        type_hints = {PROPERTY_VALUE_PATH: "Guid"}

        decoded = FArchiveReader(encoded, type_hints=type_hints).properties_until_end(
            PROPERTY_PARENT_PATH
        )

        prop = decoded["ValidatedStartPointIds"]
        self.assertEqual("StructProperty", prop["set_type"])
        self.assertEqual("Guid", prop["set_struct_type"])
        self.assertEqual([START_POINT_ID], [str(value) for value in prop["value"]["values"]])

        writer = FArchiveWriter()
        writer.properties(decoded)
        self.assertEqual(encoded, writer.bytes())

    def test_name_set_property_roundtrips_by_declared_element_type(self) -> None:
        expected = {
            "type": "SetProperty",
            "set_type": "NameProperty",
            "set_struct_type": None,
            "id": None,
            "value": {"values": ["Alpha", "Beta"]},
        }
        writer = FArchiveWriter()

        size = writer.property_inner("SetProperty", expected)
        encoded = writer.bytes()
        decoded = FArchiveReader(encoded).property("SetProperty", size, ".Names")

        self.assertEqual(expected, decoded)


if __name__ == "__main__":
    unittest.main()
