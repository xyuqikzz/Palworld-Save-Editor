from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from palworld_save_tools.archive import UUID
from palworld_pal_editor.core.pal_objects import PalObjects
from palworld_pal_editor.core.save_manager import SaveManager
from tests.unit.test_character_editor import make_pal


EXPEDITION_ID = "44444444-5555-6666-7777-888888888888"
OTHER_EXPEDITION_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def expedition_object(instance_id: str) -> dict:
    return {
        "MapObjectId": {"value": "Expedition"},
        "ConcreteModel": {
            "value": {
                "RawData": {"value": {"instance_id": UUID.from_str(instance_id)}}
            }
        },
    }


class ExpeditionIndexTests(unittest.TestCase):
    def make_manager(self) -> SaveManager:
        manager = SaveManager.create_isolated()
        manager.gvas_file = SimpleNamespace(
            properties={
                "worldSaveData": {
                    "value": {
                        "MapObjectSaveData": {
                            "skip_type": "ArrayProperty",
                            "array_type": "StructProperty",
                            "id": None,
                            "value": b"synthetic-map-object-data",
                        }
                    }
                }
            }
        )
        manager.reset_expedition_index()
        return manager

    def test_assignment_is_valid_only_when_expedition_object_exists(self) -> None:
        manager = self.make_manager()
        pal = make_pal()
        pal._pal_param[
            "MapObjectConcreteInstanceIdAssignedToExpedition"
        ] = PalObjects.Guid(EXPEDITION_ID)

        decoded = {"value": {"values": [expedition_object(EXPEDITION_ID)]}}
        with patch(
            "palworld_pal_editor.core.save_manager.map_object.decode",
            return_value=decoded,
        ) as decode:
            self.assertEqual("valid", manager.expedition_assignment_status(pal))
            self.assertEqual("valid", manager.expedition_assignment_status(pal))

        decode.assert_called_once()
        PalObjects.set_BaseType(
            pal._pal_param["MapObjectConcreteInstanceIdAssignedToExpedition"],
            OTHER_EXPEDITION_ID,
        )
        self.assertEqual("invalid", manager.expedition_assignment_status(pal))

    def test_assignment_status_is_unknown_when_map_objects_cannot_be_decoded(self) -> None:
        manager = self.make_manager()
        pal = make_pal()
        pal._pal_param[
            "MapObjectConcreteInstanceIdAssignedToExpedition"
        ] = PalObjects.Guid(EXPEDITION_ID)

        with patch(
            "palworld_pal_editor.core.save_manager.map_object.decode",
            side_effect=ValueError("unsupported map object layout"),
        ):
            self.assertEqual("unknown", manager.expedition_assignment_status(pal))
            self.assertEqual("unknown", manager.expedition_assignment_status(pal))

    def test_unassigned_pal_does_not_force_map_object_decode(self) -> None:
        manager = self.make_manager()
        with patch("palworld_pal_editor.core.save_manager.map_object.decode") as decode:
            self.assertIsNone(manager.expedition_assignment_status(make_pal()))
        decode.assert_not_called()


if __name__ == "__main__":
    unittest.main()
