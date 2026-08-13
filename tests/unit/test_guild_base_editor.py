from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest

from palworld_pal_editor.application.guild_base_editor import GuildBaseEditor
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.core.basecamp_data import BaseCampData
from palworld_pal_editor.core.container_data import ContainerData
from palworld_pal_editor.core.group_data import GroupData
from palworld_pal_editor.core.pal_objects import PalObjects, toUUID
from palworld_pal_editor.domain.commands import UpdateGuildBaseCampLevel
from palworld_pal_editor.domain.errors import DomainError


GUILD_ID = toUUID("11111111-1111-1111-1111-111111111111")
BASE_ID = toUUID("33333333-3333-3333-3333-333333333333")
CONTAINER_ID = toUUID("44444444-4444-4444-4444-444444444444")


def _manager():
    group = {
        "key": GUILD_ID,
        "value": {
            "GroupType": PalObjects.EnumProperty(
                "EPalGroupType", "EPalGroupType::Guild"
            ),
            "RawData": PalObjects.ArrayProperty(
                "ByteProperty",
                {
                    "group_id": GUILD_ID,
                    "guild_name": "Builders",
                    "guild_format": "raw",
                    "players": [],
                    "base_ids": [BASE_ID],
                    "base_camp_level": 14,
                    "individual_character_handle_ids": [],
                },
            ),
        },
    }
    camp = {
        "key": BASE_ID,
        "value": {
            "RawData": {
                "value": {
                    "id": BASE_ID,
                    "name": "Snow Base",
                    "group_id_belong_to": GUILD_ID,
                }
            },
            "WorkerDirector": {
                "RawData": {"value": {"container_id": CONTAINER_ID}}
            },
        },
    }
    container = {
        "key": {"ID": PalObjects.Guid(CONTAINER_ID)},
        "value": {
            "Slots": PalObjects.ArrayProperty(
                "StructProperty", {"values": []}
            ),
            "SlotNum": PalObjects.IntProperty(14),
        },
    }
    gvas = SimpleNamespace(
        header=None,
        properties={
            "worldSaveData": {
                "value": {
                    "GroupSaveDataMap": {"value": [group]},
                    "BaseCampSaveData": {"value": [camp]},
                    "CharacterContainerSaveData": {"value": [container]},
                }
            }
        },
    )
    return SimpleNamespace(
        gvas_file=gvas,
        group_data=GroupData(gvas),
        camp_data=BaseCampData(gvas),
        container_data=ContainerData(gvas),
        player_mapping={},
    )


class GuildBaseEditorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = _manager()
        self.session = SaveSession.from_loaded_manager(
            self.manager, Path("synthetic-save")
        )

    def test_expands_guild_base_camp_level(self) -> None:
        result = GuildBaseEditor(self.session).execute(
            UpdateGuildBaseCampLevel(
                session_id=self.session.session_id,
                expected_revision=0,
                guild_id=str(GUILD_ID),
                level=35,
            )
        )

        self.assertEqual(1, result["revision"])
        self.assertEqual(35, result["value"]["level"])
        self.assertEqual(
            35, self.manager.group_data.get_group(GUILD_ID).base_camp_level
        )
        self.assertEqual(
            ["level:GroupSaveDataMap"],
            self.session.changes()[0]["affected_records"],
        )

    def test_lowers_guild_base_camp_level(self) -> None:
        result = GuildBaseEditor(self.session).execute(
            UpdateGuildBaseCampLevel(
                session_id=self.session.session_id,
                expected_revision=0,
                guild_id=str(GUILD_ID),
                level=13,
                confirm_lowering=True,
            )
        )

        self.assertEqual(1, result["revision"])
        self.assertEqual(13, result["value"]["level"])
        self.assertEqual(
            13, self.manager.group_data.get_group(GUILD_ID).base_camp_level
        )

    def test_repairs_out_of_range_guild_base_camp_level(self) -> None:
        group = self.manager.group_data.get_group(GUILD_ID)
        group.set_base_camp_level(60)

        GuildBaseEditor(self.session).execute(
            UpdateGuildBaseCampLevel(
                session_id=self.session.session_id,
                expected_revision=0,
                guild_id=str(GUILD_ID),
                level=35,
                confirm_lowering=True,
            )
        )

        self.assertEqual(35, group.base_camp_level)

    def test_rejects_lowering_without_explicit_confirmation(self) -> None:
        with self.assertRaises(DomainError) as raised:
            GuildBaseEditor(self.session).execute(
                UpdateGuildBaseCampLevel(
                    session_id=self.session.session_id,
                    expected_revision=0,
                    guild_id=str(GUILD_ID),
                    level=13,
                )
            )

        self.assertEqual(
            "BASE_CAMP_LEVEL_LOWER_CONFIRMATION_REQUIRED",
            raised.exception.code,
        )
        self.assertEqual(
            14, self.manager.group_data.get_group(GUILD_ID).base_camp_level
        )

    def test_rejects_target_levels_outside_official_range(self) -> None:
        for level in (0, 36):
            with self.subTest(level=level), self.assertRaises(DomainError) as raised:
                GuildBaseEditor(self.session).execute(
                    UpdateGuildBaseCampLevel(
                        session_id=self.session.session_id,
                        expected_revision=0,
                        guild_id=str(GUILD_ID),
                        level=level,
                    )
                )

            self.assertEqual("INVALID_BASE_CAMP_LEVEL", raised.exception.code)
            self.assertEqual(
                14, self.manager.group_data.get_group(GUILD_ID).base_camp_level
            )

if __name__ == "__main__":
    unittest.main()
