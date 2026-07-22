from __future__ import annotations

import copy
from types import SimpleNamespace
import unittest

from palworld_save_tools.archive import FArchiveReader, UUID
from palworld_save_tools.rawdata import map_concrete_model
from palworld_pal_editor.core.pal_objects import PalObjects
from palworld_pal_editor.core.save_manager import SaveManager
from tests.unit.test_character_editor import make_pal


EXPEDITION_ID = "44444444-5555-6666-7777-888888888888"
OWNER_ID = "11111111-2222-3333-4444-555555555555"


def current_expedition(pal_id: str, *, start_time: int = 2_420_130_380_000):
    return {
        "instance_id": UUID.from_str(EXPEDITION_ID),
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


if __name__ == "__main__":
    unittest.main()
