from __future__ import annotations

import copy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from palworld_save_tools.archive import FArchiveReader, UUID
from palworld_save_tools.rawdata import map_concrete_model
from palworld_pal_editor.core.pal_objects import PalObjects
from palworld_pal_editor.core.save_manager import SaveManager
from tests.unit.test_character_editor import make_pal


EXPEDITION_ID = "44444444-5555-6666-7777-888888888888"
OTHER_EXPEDITION_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
OTHER_PAL_ID = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
OWNER_ID = "11111111-2222-3333-4444-555555555555"


def current_expedition(
    pal_id: str,
    *,
    expedition_id: str = EXPEDITION_ID,
    start_time: int = 2_420_130_380_000,
):
    return {
        "instance_id": UUID.from_str(expedition_id),
        "model_instance_id": UUID.from_str(
            "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        ),
        "concrete_model_type": "PalMapObjectCharacterTeamMissionModel",
        "expedition_layout": "current",
        "unknown_prefix": 0,
        "mission_id": "DUNGEON_SAKURAJIMA",
        "members": [
            {
                "owner_player_uid": UUID.from_str(OWNER_ID),
                "instance_id": UUID.from_str(pal_id),
            }
        ],
        "state": 2,
        "start_time": start_time,
        "unknown_bytes": [0, 0, 0, 0],
    }


class ExpeditionCompletionTests(unittest.TestCase):
    def test_current_expedition_codec_roundtrips_members_and_timer(self) -> None:
        pal = make_pal()
        model = current_expedition(str(pal.InstanceId))
        encoded = map_concrete_model.encode_bytes(copy.deepcopy(model))

        decoded = map_concrete_model.decode_bytes(
            FArchiveReader(b""), encoded, "Expedition"
        )

        self.assertEqual("current", decoded["expedition_layout"])
        self.assertEqual("DUNGEON_SAKURAJIMA", decoded["mission_id"])
        self.assertEqual(2, decoded["state"])
        self.assertEqual(model["start_time"], decoded["start_time"])
        self.assertEqual(str(pal.InstanceId), str(decoded["members"][0]["instance_id"]))
        self.assertEqual(encoded, map_concrete_model.encode_bytes(decoded))

    def test_completion_changes_only_the_expedition_timer_payload(self) -> None:
        pal = make_pal()
        model = current_expedition(str(pal.InstanceId))
        payload = map_concrete_model.encode_bytes(copy.deepcopy(model))
        prefix = b"opaque-map-object-prefix"
        suffix = b"opaque-map-object-suffix"
        manager = SaveManager.create_isolated()
        manager.gvas_file = SimpleNamespace(
            properties={
                "worldSaveData": {
                    "value": {
                        "MapObjectSaveData": {
                            "value": prefix + payload + suffix,
                        }
                    }
                }
            }
        )
        manager._expedition_index_attempted = True
        manager._expedition_instance_ids = frozenset({EXPEDITION_ID})
        manager._expedition_records = {
            EXPEDITION_ID: {
                "instance_id": EXPEDITION_ID,
                "layout": "current",
                "mission_id": model["mission_id"],
                "member_ids": frozenset({str(pal.InstanceId).lower()}),
                "state": 2,
                "start_time": model["start_time"],
                "raw_data": model,
                "original_payload": payload,
                "offset": len(prefix),
            }
        }

        completed = manager.complete_active_expeditions()
        changed = manager.snapshot_expedition_data()
        changed_payload = changed[len(prefix) : -len(suffix)]
        decoded = map_concrete_model.decode_bytes(
            FArchiveReader(b""), changed_payload, "Expedition"
        )

        self.assertEqual([EXPEDITION_ID], completed)
        self.assertTrue(changed.startswith(prefix))
        self.assertTrue(changed.endswith(suffix))
        self.assertEqual(len(prefix + payload + suffix), len(changed))
        self.assertEqual(1, decoded["start_time"])
        self.assertEqual(model["mission_id"], decoded["mission_id"])
        self.assertEqual(model["state"], decoded["state"])
        self.assertEqual(model["members"], decoded["members"])

    def test_valid_assignment_requires_active_reverse_membership(self) -> None:
        pal = make_pal()
        pal._pal_param[
            "MapObjectConcreteInstanceIdAssignedToExpedition"
        ] = PalObjects.Guid(EXPEDITION_ID)
        manager = SaveManager.create_isolated()
        manager._expedition_index_attempted = True
        manager._expedition_instance_ids = frozenset({EXPEDITION_ID})
        record = {
            "instance_id": EXPEDITION_ID,
            "layout": "current",
            "mission_id": "DUNGEON_SAKURAJIMA",
            "member_ids": frozenset({str(pal.InstanceId).lower()}),
            "state": 2,
            "start_time": 100,
            "offset": 0,
            "original_payload": b"payload",
        }
        manager._expedition_records = {EXPEDITION_ID: record}

        self.assertEqual("valid", manager.expedition_assignment_status(pal))
        self.assertTrue(manager.expedition_can_complete(pal))

        record["state"] = 1
        self.assertEqual("invalid", manager.expedition_assignment_status(pal))
        self.assertFalse(manager.expedition_can_complete(pal))

    def test_remove_expedition_member_preserves_other_members_and_fields(self) -> None:
        pal = make_pal()
        model = current_expedition(str(pal.InstanceId))
        model["members"].append(
            {
                "owner_player_uid": UUID.from_str(OWNER_ID),
                "instance_id": UUID.from_str(OTHER_PAL_ID),
            }
        )
        model["unknown_bytes"] = [9, 8, 7, 6]
        payload = map_concrete_model.encode_bytes(copy.deepcopy(model))
        field = SaveManager._encode_map_object_raw_data_field(
            payload, "ByteProperty", None
        )
        prefix = b"opaque-prefix"
        suffix = b"opaque-suffix"
        manager = SaveManager.create_isolated()
        manager.gvas_file = SimpleNamespace(
            properties={
                "worldSaveData": {
                    "value": {
                        "MapObjectSaveData": {
                            "array_type": "StructProperty",
                            "id": None,
                            "value": prefix + field + suffix,
                        }
                    }
                }
            }
        )
        manager._expedition_index_attempted = True
        manager._expedition_instance_ids = frozenset({EXPEDITION_ID})
        manager._expedition_records = {
            EXPEDITION_ID: {
                "instance_id": EXPEDITION_ID,
                "layout": "current",
                "mission_id": model["mission_id"],
                "members": (),
                "member_ids": frozenset(
                    {str(pal.InstanceId).lower(), OTHER_PAL_ID}
                ),
                "state": model["state"],
                "start_time": model["start_time"],
                "raw_data": model,
                "original_payload": payload,
                "offset": len(prefix) + len(field) - len(payload),
                "raw_array_type": "ByteProperty",
                "raw_property_id": None,
                "original_field": field,
                "field_offset": len(prefix),
            }
        }

        records = manager._expedition_records

        def load_records():
            if manager.snapshot_expedition_data() != prefix + field + suffix:
                records[EXPEDITION_ID]["member_ids"] = frozenset({OTHER_PAL_ID})
            return records

        with patch.object(
            manager, "_load_expedition_records", side_effect=load_records
        ):
            removed = manager.remove_expedition_members([str(pal.InstanceId)])

            self.assertEqual(
                {EXPEDITION_ID: [str(pal.InstanceId).lower()]},
                removed,
            )
            changed = manager.snapshot_expedition_data()
            self.assertTrue(changed.startswith(prefix))
            self.assertTrue(changed.endswith(suffix))
            field_reader = FArchiveReader(changed[len(prefix) : -len(suffix)])
            self.assertEqual("RawData", field_reader.fstring())
            self.assertEqual("ArrayProperty", field_reader.fstring())
            payload_size = field_reader.u64()
            self.assertEqual("ByteProperty", field_reader.fstring())
            self.assertIsNone(field_reader.optional_guid())
            encoded_size = field_reader.u32()
            encoded_payload = field_reader.read_to_end()
            self.assertEqual(encoded_size + 4, payload_size)
            self.assertEqual(encoded_size, len(encoded_payload))
            decoded = map_concrete_model.decode_bytes(
                FArchiveReader(b""), encoded_payload, "Expedition"
            )
            self.assertEqual(
                [OTHER_PAL_ID],
                [str(member["instance_id"]) for member in decoded["members"]],
            )
            self.assertEqual(model["mission_id"], decoded["mission_id"])
            self.assertEqual(model["state"], decoded["state"])
            self.assertEqual(model["start_time"], decoded["start_time"])
            self.assertEqual(model["unknown_bytes"], decoded["unknown_bytes"])
            self.assertFalse(
                manager.expedition_has_member(EXPEDITION_ID, str(pal.InstanceId))
            )
            self.assertTrue(
                manager.expedition_has_member(EXPEDITION_ID, OTHER_PAL_ID)
            )
        self.assertEqual("DUNGEON_SAKURAJIMA", model["mission_id"])
        self.assertEqual(2, model["state"])
        self.assertEqual(2_420_130_380_000, model["start_time"])
        self.assertEqual([9, 8, 7, 6], model["unknown_bytes"])

    def test_remove_expedition_member_rejects_non_unique_raw_data_field(self) -> None:
        pal = make_pal()
        model = current_expedition(str(pal.InstanceId))
        manager = SaveManager.create_isolated()
        manager.gvas_file = SimpleNamespace(
            properties={
                "worldSaveData": {
                    "value": {
                        "MapObjectSaveData": {
                            "array_type": "StructProperty",
                            "id": None,
                            "value": b"original",
                        }
                    }
                }
            }
        )
        manager._expedition_index_attempted = True
        manager._expedition_instance_ids = frozenset({EXPEDITION_ID})
        manager._expedition_records = {
            EXPEDITION_ID: {
                "instance_id": EXPEDITION_ID,
                "member_ids": frozenset({str(pal.InstanceId).lower()}),
                "raw_data": model,
                "raw_array_type": "ByteProperty",
                "raw_property_id": None,
                "original_field": None,
                "field_offset": None,
            }
        }

        with self.assertRaisesRegex(ValueError, "not uniquely writable"):
            manager.remove_expedition_members([str(pal.InstanceId)])

        self.assertEqual(b"original", manager.snapshot_expedition_data())

    def test_single_completion_does_not_change_another_active_expedition(self) -> None:
        first_pal = make_pal()
        second_pal = make_pal()
        second_pal.InstanceId = OTHER_PAL_ID
        first_model = current_expedition(str(first_pal.InstanceId))
        second_model = current_expedition(
            str(second_pal.InstanceId),
            expedition_id=OTHER_EXPEDITION_ID,
            start_time=2_420_130_480_000,
        )
        first_payload = map_concrete_model.encode_bytes(copy.deepcopy(first_model))
        second_payload = map_concrete_model.encode_bytes(copy.deepcopy(second_model))
        prefix = b"first-prefix"
        separator = b"between-expeditions"
        suffix = b"second-suffix"
        manager = SaveManager.create_isolated()
        manager.gvas_file = SimpleNamespace(
            properties={
                "worldSaveData": {
                    "value": {
                        "MapObjectSaveData": {
                            "value": (
                                prefix
                                + first_payload
                                + separator
                                + second_payload
                                + suffix
                            ),
                        }
                    }
                }
            }
        )
        manager._expedition_index_attempted = True
        manager._expedition_instance_ids = frozenset(
            {EXPEDITION_ID, OTHER_EXPEDITION_ID}
        )
        manager._expedition_records = {
            EXPEDITION_ID: {
                "instance_id": EXPEDITION_ID,
                "layout": "current",
                "mission_id": first_model["mission_id"],
                "members": (),
                "member_ids": frozenset({str(first_pal.InstanceId).lower()}),
                "state": 2,
                "start_time": first_model["start_time"],
                "raw_data": first_model,
                "original_payload": first_payload,
                "offset": len(prefix),
            },
            OTHER_EXPEDITION_ID: {
                "instance_id": OTHER_EXPEDITION_ID,
                "layout": "current",
                "mission_id": second_model["mission_id"],
                "members": (),
                "member_ids": frozenset({str(second_pal.InstanceId).lower()}),
                "state": 2,
                "start_time": second_model["start_time"],
                "raw_data": second_model,
                "original_payload": second_payload,
                "offset": len(prefix) + len(first_payload) + len(separator),
            },
        }

        completed = manager.complete_active_expeditions([EXPEDITION_ID])
        changed = manager.snapshot_expedition_data()
        first_start = len(prefix)
        second_start = first_start + len(first_payload) + len(separator)
        decoded_first = map_concrete_model.decode_bytes(
            FArchiveReader(b""),
            changed[first_start : first_start + len(first_payload)],
            "Expedition",
        )
        decoded_second = map_concrete_model.decode_bytes(
            FArchiveReader(b""),
            changed[second_start : second_start + len(second_payload)],
            "Expedition",
        )

        self.assertEqual([EXPEDITION_ID], completed)
        self.assertEqual(1, decoded_first["start_time"])
        self.assertEqual(second_model["start_time"], decoded_second["start_time"])


if __name__ == "__main__":
    unittest.main()
