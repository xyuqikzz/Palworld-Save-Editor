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
from palworld_pal_editor.domain.commands import UpdateGuildName, UpdateGuildOwner
from palworld_pal_editor.domain.errors import DomainError


GUILD_ID = toUUID("11111111-1111-1111-1111-111111111111")
OWNER_ID = toUUID("aaaaaaaa-1111-2222-3333-444444444444")
MEMBER_ID = toUUID("bbbbbbbb-1111-2222-3333-444444444444")


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


def _role_group(*, guild_format: str = "1.0") -> PalGroup:
    return PalGroup(
        {
            "value": {
                "RawData": {
                    "value": {
                        "group_id": GUILD_ID,
                        "group_name": "Guild",
                        "guild_name": "Builders",
                        "guild_format": guild_format,
                        "admin_player_uid": OWNER_ID,
                        "individual_character_handle_ids": [],
                        "base_ids": [],
                        "players": [
                            {
                                "player_uid": OWNER_ID,
                                "player_info": {
                                    "last_online_real_time": 10,
                                    "player_name": "Owner",
                                    "role": 1,
                                },
                            },
                            {
                                "player_uid": MEMBER_ID,
                                "player_info": {
                                    "last_online_real_time": 5,
                                    "player_name": "Member",
                                    "role": 3,
                                },
                            },
                        ],
                    }
                }
            }
        },
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

    def owner_command(self, **overrides) -> UpdateGuildOwner:
        values = {
            "session_id": self.session.session_id,
            "expected_revision": self.session.revision,
            "guild_id": str(GUILD_ID),
            "player_id": str(MEMBER_ID),
        }
        values.update(overrides)
        return UpdateGuildOwner(**values)

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

    def test_updates_owner_and_normalizes_leader_roles_as_one_level_change(
        self,
    ) -> None:
        self.group = _role_group()
        self.session.manager.group_data = _Groups(self.group)

        result = GuildEditor(self.session).execute(self.owner_command())

        self.assertEqual(str(MEMBER_ID), str(self.group.admin_player_uid))
        self.assertEqual(
            {
                str(OWNER_ID): 2,
                str(MEMBER_ID): 1,
            },
            {
                str(player_uid): role
                for player_uid, _name, role in self.group.guild_members
            },
        )
        self.assertEqual(str(MEMBER_ID), result["value"]["owner_player_id"])
        self.assertEqual(1, result["revision"])
        self.assertEqual(
            ["level:GroupSaveDataMap"],
            self.session.changes()[0]["affected_records"],
        )

    def test_owner_update_rejects_legacy_layout_without_mutating(self) -> None:
        self.group = _role_group(guild_format="legacy")
        self.session.manager.group_data = _Groups(self.group)

        with self.assertRaises(DomainError) as raised:
            GuildEditor(self.session).execute(self.owner_command())

        self.assertEqual(
            "COMPATIBILITY_FIELD_MISSING", raised.exception.code
        )
        self.assertEqual(str(OWNER_ID), str(self.group.admin_player_uid))
        self.assertEqual(0, self.session.revision)

    def test_owner_update_rejects_player_outside_saved_guild(self) -> None:
        self.group = _role_group()
        self.session.manager.group_data = _Groups(self.group)

        with self.assertRaises(DomainError) as raised:
            GuildEditor(self.session).execute(
                self.owner_command(
                    player_id="cccccccc-1111-2222-3333-444444444444"
                )
            )

        self.assertEqual("GUILD_MEMBER_NOT_FOUND", raised.exception.code)
        self.assertEqual(str(OWNER_ID), str(self.group.admin_player_uid))
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

    def test_owner_and_roles_survive_the_palworld_1_0_group_codec(self) -> None:
        raw = {
            "group_type": "EPalGroupType::Guild",
            "group_id": GUILD_ID,
            "group_name": "Guild",
            "individual_character_handle_ids": [],
            "org_type": 0,
            "leading_bytes": [0, 0, 0, 0],
            "base_ids": [],
            "unknown_1": 0,
            "base_camp_level": 1,
            "map_object_instance_ids_base_camp_points": [],
            "guild_name": "Codec Builders",
            "last_guild_name_modifier_player_uid": PalObjects.EMPTY_UUID,
            "guild_format": "1.0",
            "guild_marker_count": 0,
            "guild_marker_data": [],
            "guild_chest_allowed_roles": [1, 2, 3],
            "unknown_i32": 0,
            "admin_player_uid": MEMBER_ID,
            "players": [
                {
                    "player_uid": OWNER_ID,
                    "player_info": {
                        "last_online_real_time": 10,
                        "player_name": "Owner",
                        "role": 2,
                    },
                },
                {
                    "player_uid": MEMBER_ID,
                    "player_info": {
                        "last_online_real_time": 5,
                        "player_name": "Member",
                        "role": 1,
                    },
                },
            ],
            "role_permissions": [
                {"role": 2, "permissions": [0, 3, 4]},
                {"role": 3, "permissions": [4]},
                {"role": 4, "permissions": []},
            ],
            "trailing_bytes": [0, 0, 0, 0],
        }

        encoded = encode_bytes(raw)
        decoded = decode_bytes(
            FArchiveReader(encoded), encoded, "EPalGroupType::Guild"
        )

        self.assertEqual("1.0", decoded["guild_format"])
        self.assertEqual(str(MEMBER_ID), str(decoded["admin_player_uid"]))
        self.assertEqual(
            [2, 1],
            [player["player_info"]["role"] for player in decoded["players"]],
        )
        self.assertEqual(raw["role_permissions"], decoded["role_permissions"])
        self.assertEqual(encoded, encode_bytes(decoded))


if __name__ == "__main__":
    unittest.main()
