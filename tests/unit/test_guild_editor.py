from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest

from palworld_save_tools.archive import FArchiveReader
from palworld_save_tools.rawdata.group import decode_bytes, encode_bytes

from palworld_pal_editor.application.guild_editor import GuildEditor
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.core.group_data import PalGroup
from palworld_pal_editor.core.pal_objects import PalObjects, toUUID
from palworld_pal_editor.domain.commands import UpdateGuildName
from palworld_pal_editor.domain.errors import DomainError


GUILD_ID = toUUID("11111111-1111-1111-1111-111111111111")


class _Groups:
    def __init__(self, group: PalGroup) -> None:
        self.group = group

    def get_group(self, group_id):
        return self.group if str(group_id) == str(self.group.group_id) else None


def _group(*, name: str = "Builders", include_name_field: bool = True) -> PalGroup:
    raw = {
        "group_id": GUILD_ID,
        "group_name": "Guild",
        "individual_character_handle_ids": [],
        "base_ids": [toUUID("22222222-2222-2222-2222-222222222222")],
    }
    if include_name_field:
        raw["guild_name"] = name
    return PalGroup(
        {"value": {"RawData": {"value": raw}}},
        "EPalGroupType::Guild",
    )


class GuildEditorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.group = _group()
        manager = SimpleNamespace(
            gvas_file=SimpleNamespace(properties={}, header=None),
            group_data=_Groups(self.group),
            player_mapping={},
        )
        self.session = SaveSession.from_loaded_manager(manager, Path("synthetic-save"))

    def command(self, **overrides) -> UpdateGuildName:
        values = {
            "session_id": self.session.session_id,
            "expected_revision": self.session.revision,
            "guild_id": str(GUILD_ID),
            "name": "New Builders",
        }
        values.update(overrides)
        return UpdateGuildName(**values)

    def test_updates_writable_guild_name_as_one_level_change(self) -> None:
        result = GuildEditor(self.session).execute(self.command())

        self.assertEqual("New Builders", self.group.guild_name)
        self.assertEqual(1, result["revision"])
        self.assertEqual("New Builders", result["value"]["name"])
        self.assertEqual(1, self.session.revision)
        self.assertEqual(
            ["level:GroupSaveDataMap"],
            self.session.changes()[0]["affected_records"],
        )

    def test_same_name_is_a_revision_checked_noop(self) -> None:
        result = GuildEditor(self.session).execute(self.command(name="Builders"))

        self.assertIsNone(result["change_id"])
        self.assertEqual(0, result["revision"])
        self.assertEqual([], self.session.changes())

    def test_rejects_missing_writable_field_without_materializing_it(self) -> None:
        group = _group(include_name_field=False)
        self.session.manager.group_data = _Groups(group)

        with self.assertRaises(DomainError) as raised:
            GuildEditor(self.session).execute(self.command())

        self.assertEqual("COMPATIBILITY_FIELD_MISSING", raised.exception.code)
        self.assertNotIn("guild_name", group._group_param)
        self.assertEqual(0, self.session.revision)

    def test_rejects_invalid_name_without_mutating(self) -> None:
        with self.assertRaises(DomainError) as raised:
            GuildEditor(self.session).execute(self.command(name="   "))

        self.assertEqual("INVALID_GUILD_NAME", raised.exception.code)
        self.assertEqual("Builders", self.group.guild_name)
        self.assertEqual(0, self.session.revision)

    def test_renamed_field_survives_the_real_group_raw_codec(self) -> None:
        raw = {
            "group_type": "EPalGroupType::Guild",
            "group_id": GUILD_ID,
            "group_name": "Guild",
            "individual_character_handle_ids": [],
            "org_type": 0,
            "leading_bytes": [0, 0, 0, 0],
            "base_ids": [toUUID("22222222-2222-2222-2222-222222222222")],
            "unknown_1": 0,
            "base_camp_level": 1,
            "map_object_instance_ids_base_camp_points": [],
            "guild_name": "Codec Builders",
            "last_guild_name_modifier_player_uid": PalObjects.EMPTY_UUID,
            "guild_format": "raw",
            "raw_guild_tail": [],
        }

        encoded = encode_bytes(raw)
        decoded = decode_bytes(
            FArchiveReader(encoded), encoded, "EPalGroupType::Guild"
        )

        self.assertEqual("Codec Builders", decoded["guild_name"])
        self.assertEqual(encoded, encode_bytes(decoded))


if __name__ == "__main__":
    unittest.main()
