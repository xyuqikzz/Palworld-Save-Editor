from __future__ import annotations

from copy import deepcopy
import errno
import os
from pathlib import Path
import shutil
import tempfile
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from palworld_save_tools.archive import UUID
from palworld_save_tools.gvas import GvasFile, GvasHeader
from palworld_save_tools.palsav import compress_gvas_to_sav, decompress_sav_to_gvas
from palworld_save_tools.paltypes import PALWORLD_TYPE_HINTS

from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.application.save_writer import SaveWriter
from palworld_pal_editor.core.dynamic_item_data import DynamicItemData
from palworld_pal_editor.core.item_container_data import ItemContainerData
from palworld_pal_editor.core.pal_objects import (
    PalObjects,
    UUID2HexStr,
    toUUID,
)
from palworld_pal_editor.core.save_manager import (
    MAIN_SKIP_PROPERTIES,
    PLAYER_SKIP_PROPERTIES,
)
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.storage.discovery import XgpSourceCatalog
from palworld_pal_editor.storage import steam as steam_storage
from palworld_pal_editor.storage.xgp import XgpWgsAdapter
from tests.wgs_fixture import make_user_directory


START_POINT_ID = "04099789-4a41-4a09-f6f1-99985c080bc8"
LOCKER_PLAYER_UID = "7e358108-07d8-4c32-bd21-69c77b15f83d"
LOCKER_INSTANCE_ID = "49a8e005-50ab-4b88-86c8-fd768a010cba"
DYNAMIC_CONTAINER_ID = toUUID("11111111-2222-3333-4444-555555555555")
DANGLING_LOCAL_ID = toUUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
ZERO_UUID = toUUID("00000000-0000-0000-0000-000000000000")


def set_property_world_data() -> dict:
    return {
        "type": "StructProperty",
        "struct_type": "PalWorldSaveData",
        "struct_id": PalObjects.EMPTY_UUID,
        "id": None,
        "value": {
            "InLockerCharacterInstanceIDArray": {
                "type": "SetProperty",
                "set_type": "StructProperty",
                "set_struct_type": "StructProperty",
                "id": None,
                "value": {
                    "values": [
                        {
                            "PlayerUId": PalObjects.Guid(LOCKER_PLAYER_UID),
                            "InstanceId": PalObjects.Guid(LOCKER_INSTANCE_ID),
                        }
                    ]
                },
            },
            "InvaderDeclarationSaveData": {
                "type": "StructProperty",
                "struct_type": "PalInvaderDeclarationSaveData",
                "struct_id": PalObjects.EMPTY_UUID,
                "id": None,
                "value": {
                    "ValidatedStartPointIds": {
                        "type": "SetProperty",
                        "set_type": "StructProperty",
                        "set_struct_type": "Guid",
                        "id": None,
                        "value": {"values": [UUID.from_str(START_POINT_ID)]},
                    }
                },
            }
        },
    }


def add_dangling_dynamic_reference(world: dict) -> None:
    item_containers = PalObjects.MapProperty(
        "StructProperty",
        "StructProperty",
        "StructProperty",
        "StructProperty",
    )
    item_containers["value"].append(
        {
            "key": {"ID": PalObjects.Guid(DYNAMIC_CONTAINER_ID)},
            "value": {
                "SlotNum": PalObjects.IntProperty(1),
                "Slots": PalObjects.ArrayProperty(
                    "StructProperty",
                    {
                        "prop_name": "Slots",
                        "prop_type": "StructProperty",
                        "values": [
                            {
                                "RawData": PalObjects.ArrayProperty(
                                    "ByteProperty",
                                    {
                                        "slot_index": 0,
                                        "count": 1,
                                        "item": {
                                            "static_id": "Weapon_Test",
                                            "dynamic_id": {
                                                "created_world_id": ZERO_UUID,
                                                "local_id_in_created_world": DANGLING_LOCAL_ID,
                                            },
                                        },
                                    },
                                    (
                                        ".worldSaveData.ItemContainerSaveData."
                                        "Value.Slots.Slots.RawData"
                                    ),
                                )
                            }
                        ],
                        "type_name": "PalItemSlot",
                        "id": PalObjects.EMPTY_UUID,
                    },
                ),
                "RawData": PalObjects.ArrayProperty(
                    "ByteProperty",
                    {
                        "permission": {
                            "type_a": [],
                            "type_b": [],
                            "item_static_ids": [],
                            "item_categories": [],
                        },
                        "used_dynamic_item_ids": [],
                    },
                    ".worldSaveData.ItemContainerSaveData.Value.RawData",
                ),
            },
        }
    )
    world["value"].update(
        {
            "ItemContainerSaveData": item_containers,
            "DynamicItemSaveData": PalObjects.ArrayProperty(
                "StructProperty",
                {
                    "prop_name": "DynamicItemSaveData",
                    "prop_type": "StructProperty",
                    "values": [],
                    "type_name": "PalDynamicItemSaveData",
                    "id": PalObjects.EMPTY_UUID,
                },
            ),
        }
    )


def make_gvas(counter: int, *, dangling_dynamic: bool = False) -> GvasFile:
    gvas = GvasFile()
    gvas.header = GvasHeader.load(
        {
            "magic": 0x53415647,
            "save_game_version": 3,
            "package_file_version_ue4": 522,
            "package_file_version_ue5": 1008,
            "engine_version_major": 5,
            "engine_version_minor": 1,
            "engine_version_patch": 1,
            "engine_version_changelist": 0,
            "engine_version_branch": "synthetic-test",
            "custom_version_format": 3,
            "custom_versions": [],
            "save_game_class_name": "/Script/Pal.PalWorldSaveGame",
        }
    )
    world = set_property_world_data()
    if dangling_dynamic:
        add_dangling_dynamic_reference(world)
    gvas.properties = {
        "Counter": PalObjects.IntProperty(counter),
        "worldSaveData": world,
    }
    gvas.trailer = b"\x00\x00\x00\x00"
    return gvas


def read_counter(path: Path) -> int:
    raw, _save_type = decompress_sav_to_gvas(path.read_bytes())
    gvas = GvasFile.read(raw, PALWORLD_TYPE_HINTS, MAIN_SKIP_PROPERTIES)
    return gvas.properties["Counter"]["value"]


def read_start_point_ids(path: Path) -> tuple[str, ...]:
    raw, _save_type = decompress_sav_to_gvas(path.read_bytes())
    gvas = GvasFile.read(raw, PALWORLD_TYPE_HINTS, MAIN_SKIP_PROPERTIES)
    values = gvas.properties["worldSaveData"]["value"][
        "InvaderDeclarationSaveData"
    ]["value"]["ValidatedStartPointIds"]["value"]["values"]
    return tuple(str(value) for value in values)


def read_locker_character_ids(path: Path) -> tuple[tuple[str, str], ...]:
    raw, _save_type = decompress_sav_to_gvas(path.read_bytes())
    gvas = GvasFile.read(raw, PALWORLD_TYPE_HINTS, MAIN_SKIP_PROPERTIES)
    values = gvas.properties["worldSaveData"]["value"][
        "InLockerCharacterInstanceIDArray"
    ]["value"]["values"]
    return tuple(
        (str(value["PlayerUId"]["value"]), str(value["InstanceId"]["value"]))
        for value in values
    )


def read_dynamic_issue_codes(path: Path) -> tuple[str, ...]:
    raw, _save_type = decompress_sav_to_gvas(path.read_bytes())
    gvas = GvasFile.read(raw, PALWORLD_TYPE_HINTS, MAIN_SKIP_PROPERTIES)
    item_containers = ItemContainerData(gvas)
    return tuple(
        issue.code for issue in DynamicItemData(gvas, item_containers).issues()
    )


class SaveWriterTests(unittest.TestCase):
    def make_session(
        self, root: Path, *, dangling_dynamic: bool = False
    ) -> SaveSession:
        initial_gvas = make_gvas(1, dangling_dynamic=dangling_dynamic)
        (root / "Level.sav").write_bytes(
            compress_gvas_to_sav(
                initial_gvas.write(MAIN_SKIP_PROPERTIES), 0x32, zlib=True
            )
        )
        raw, _save_type = decompress_sav_to_gvas((root / "Level.sav").read_bytes())
        gvas = GvasFile.read(raw, PALWORLD_TYPE_HINTS, MAIN_SKIP_PROPERTIES)
        item_containers = ItemContainerData(gvas)
        manager = SimpleNamespace(
            gvas_file=gvas,
            _compression_times=0x32,
            player_mapping={},
            item_container_data=item_containers,
        )
        if dangling_dynamic:
            manager.dynamic_item_data = DynamicItemData(gvas, item_containers)
        session = SaveSession.from_loaded_manager(manager, root)

        def restore(properties):
            gvas.properties.clear()
            gvas.properties.update(deepcopy(properties))

        session.apply_atomic(
            session_id=session.session_id,
            expected_revision=0,
            command="SyntheticLevelUpdate",
            target={"counter": 2},
            snapshot=lambda: deepcopy(gvas.properties),
            restore=restore,
            before=lambda: {"counter": gvas.properties["Counter"]["value"]},
            mutate=lambda: gvas.properties["Counter"].update(value=2),
            validate=lambda: None,
            after=lambda: {"counter": gvas.properties["Counter"]["value"]},
            affected_records=("level:Synthetic",),
        )
        return session

    def test_consumable_bonus_staged_postcondition_targets_unique_player(self) -> None:
        player_id = "11111111-2222-3333-4444-555555555555"
        record = PalObjects.PalSaveParameter(
            "22222222-3333-4444-5555-666666666666",
            player_id,
            "33333333-4444-5555-6666-777777777777",
            0,
            "44444444-5555-6666-7777-888888888888",
        )
        record["key"]["PlayerUId"] = PalObjects.Guid(player_id)
        parameter = record["value"]["RawData"]["value"]["object"][
            "SaveParameter"
        ]["value"]
        parameter["IsPlayer"] = PalObjects.BoolProperty(True)
        bonus_rows = PalObjects.get_ArrayProperty(parameter["GotExStatusPointList"])
        PalObjects.set_BaseType(bonus_rows[0]["StatusPoint"], 12)
        gvas = SimpleNamespace(
            properties={
                "worldSaveData": {
                    "value": {"CharacterSaveParameterMap": {"value": [record]}}
                }
            }
        )
        session = SimpleNamespace(
            changes=lambda: [
                {
                    "command": "UpdatePlayerConsumableBonuses",
                    "target": {"player_id": player_id},
                    "after": {"max_hp": 12},
                },
                {
                    "command": "UpdatePlayerConsumableBonuses",
                    "target": {"player_id": player_id},
                    "after": {"max_sp": 0},
                },
            ]
        )

        SaveWriter()._verify_change_postconditions(
            session, {"Level.sav": gvas}
        )

        regular_rows = PalObjects.get_ArrayProperty(
            parameter["GotStatusPointList"]
        )
        PalObjects.set_BaseType(regular_rows[0]["StatusPoint"], 39)
        with self.assertRaisesRegex(ValueError, "official maximum"):
            SaveWriter()._verify_change_postconditions(
                session, {"Level.sav": gvas}
            )

        PalObjects.set_BaseType(regular_rows[0]["StatusPoint"], 0)
        PalObjects.set_BaseType(bonus_rows[0]["StatusPoint"], 11)
        with self.assertRaisesRegex(ValueError, "do not match staging"):
            SaveWriter()._verify_change_postconditions(
                session, {"Level.sav": gvas}
            )

    def test_unrelated_save_preserves_preexisting_dangling_dynamic_reference(
        self,
    ) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp) / "save"
            root.mkdir()
            session = self.make_session(root, dangling_dynamic=True)

            result = SaveWriter().save(session, root, 1)

            self.assertEqual(2, read_counter(root / "Level.sav"))
            self.assertEqual(
                ("DYNAMIC_ITEM_REFERENCE_DANGLING",),
                read_dynamic_issue_codes(root / "Level.sav"),
            )
            self.assertTrue(result.staged_reload_verified)

    @unittest.skipUnless(os.name == "nt", "Windows extended-path regression")
    def test_steam_save_writer_stages_and_reopens_beyond_max_path(self) -> None:
        temp_root = Path(tempfile.mkdtemp(prefix="pwe-save-writer-longpath-")).resolve()
        try:
            target_parent = temp_root
            desired_parent_length = 233
            index = 0
            while len(str(target_parent)) + 31 <= desired_parent_length - 8:
                index += 1
                target_parent /= f"segment-{index:02d}-" + "x" * 19
            remaining = desired_parent_length - len(str(target_parent)) - 1
            target_parent /= "x" * remaining
            root = target_parent / "save"
            steam_storage._native_path(root).mkdir(parents=True)

            self.assertLess(len(str(root / "Level.sav")), 260)
            projected_staging = root.parent / (
                f".{root.name}.pal-editor-staging-" + "0" * 36
            )
            self.assertGreater(len(str(projected_staging)), 260)
            session = self.make_session(root)

            result = SaveWriter().save(session, root, 1)

            backup_file = Path(result.backup_path) / "files" / "Level.sav"
            self.assertGreater(len(str(backup_file)), 260)
            self.assertEqual(
                1,
                read_counter(steam_storage._native_path(backup_file)),
            )
            self.assertEqual(2, read_counter(root / "Level.sav"))
            self.assertEqual(
                2,
                read_counter(
                    steam_storage._native_path(root / "Level.sav")
                ),
            )
        finally:
            native_temp_root = steam_storage._native_path(temp_root)
            if native_temp_root.exists():
                shutil.rmtree(native_temp_root)

    def test_save_rejects_new_dangling_dynamic_reference(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp) / "save"
            root.mkdir()
            session = self.make_session(root)
            manager = session.manager
            add_dangling_dynamic_reference(
                manager.gvas_file.properties["worldSaveData"]
            )
            manager.item_container_data = ItemContainerData(manager.gvas_file)
            manager.dynamic_item_data = DynamicItemData(
                manager.gvas_file, manager.item_container_data
            )

            with self.assertRaises(DomainError) as raised:
                SaveWriter().save(session, root, 1)

            self.assertEqual(
                "DYNAMIC_ITEM_REFERENCE_DANGLING", raised.exception.code
            )

    def test_xgp_unrelated_save_preserves_preexisting_dangling_reference(
        self,
    ) -> None:
        with TemporaryDirectory() as temp:
            base = Path(temp)
            wgs_root = base / "wgs"
            wgs_root.mkdir()
            world_id = "A" * 32
            make_user_directory(
                wgs_root,
                "1111111111111111_" + "B" * 32,
                {
                    world_id: {
                        "Level.sav": compress_gvas_to_sav(
                            make_gvas(1, dangling_dynamic=True).write(
                                MAIN_SKIP_PROPERTIES
                            ),
                            0x32,
                            zlib=True,
                        )
                    }
                },
            )
            catalog = XgpSourceCatalog(roots=(wgs_root,))
            adapter = XgpWgsAdapter(
                catalog=catalog,
                process_checker=lambda: False,
                workspace_validator=lambda _path: None,
                workspace_root=base / "workspaces",
                backup_root=base / "backups",
                stability_delay=0,
            )

            class Manager:
                def open(self, path, *, lazy_players=False):
                    raw, _save_type = decompress_sav_to_gvas(
                        (Path(path) / "Level.sav").read_bytes()
                    )
                    self.gvas_file = GvasFile.read(
                        raw, PALWORLD_TYPE_HINTS, MAIN_SKIP_PROPERTIES
                    )
                    self._compression_times = 0x32
                    self.player_mapping = {}
                    self.item_container_data = ItemContainerData(
                        self.gvas_file
                    )
                    self.dynamic_item_data = DynamicItemData(
                        self.gvas_file, self.item_container_data
                    )
                    return self.gvas_file

            source = catalog.discover()[0]
            session = SaveSession.open_storage(
                source, adapter, manager=Manager()
            )
            gvas = session.manager.gvas_file

            def restore(properties):
                gvas.properties.clear()
                gvas.properties.update(deepcopy(properties))

            session.apply_atomic(
                session_id=session.session_id,
                expected_revision=0,
                command="SyntheticLevelUpdate",
                target={"counter": 2},
                snapshot=lambda: deepcopy(gvas.properties),
                restore=restore,
                before=lambda: {"counter": gvas.properties["Counter"]["value"]},
                mutate=lambda: gvas.properties["Counter"].update(value=2),
                validate=lambda: None,
                after=lambda: {"counter": gvas.properties["Counter"]["value"]},
                affected_records=("level:Synthetic",),
            )

            result = SaveWriter().save(session, None, 1)
            session.close()
            reopened = SaveSession.open_storage(
                source, adapter, manager=Manager()
            )
            try:
                self.assertEqual(
                    2, reopened.manager.gvas_file.properties["Counter"]["value"]
                )
                self.assertEqual(
                    ("DYNAMIC_ITEM_REFERENCE_DANGLING",),
                    tuple(
                        issue.code
                        for issue in reopened.manager.dynamic_item_data.issues()
                    ),
                )
                self.assertTrue(result.target_reload_verified)
                self.assertFalse(result.cloud_sync_verified)
            finally:
                reopened.close()

    def test_verified_backup_staging_reload_and_new_baseline(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp) / "save"
            root.mkdir()
            session = self.make_session(root)
            before = (root / "Level.sav").read_bytes()

            result = SaveWriter().save(session, root, 1)

            self.assertEqual(2, read_counter(root / "Level.sav"))
            self.assertEqual(
                (START_POINT_ID,), read_start_point_ids(root / "Level.sav")
            )
            self.assertEqual(
                ((LOCKER_PLAYER_UID, LOCKER_INSTANCE_ID),),
                read_locker_character_ids(root / "Level.sav"),
            )
            self.assertEqual([], session.changes())
            self.assertTrue(result.staged_reload_verified)
            self.assertEqual(("Level.sav",), result.written_files)
            backup = Path(result.backup_path)
            self.assertTrue((backup / "manifest.json").is_file())
            self.assertEqual(1, read_counter(backup / "files" / "Level.sav"))
            self.assertEqual(
                (START_POINT_ID,),
                read_start_point_ids(backup / "files" / "Level.sav"),
            )
            self.assertEqual(
                ((LOCKER_PLAYER_UID, LOCKER_INSTANCE_ID),),
                read_locker_character_ids(backup / "files" / "Level.sav"),
            )
            self.assertEqual(before, (backup / "files" / "Level.sav").read_bytes())
            self.assertFalse(str(backup).startswith(str(root) + str(Path("/"))))

    def test_backup_failure_stops_before_target_write_and_keeps_pending_changes(
        self,
    ) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp) / "save"
            root.mkdir()
            session = self.make_session(root)
            before = (root / "Level.sav").read_bytes()

            def fail(stage, _context):
                if stage == "before_backup_copy":
                    raise OSError(errno.ENOSPC, "synthetic disk full")

            with self.assertRaises(DomainError) as raised:
                SaveWriter(failure_hook=fail).save(session, root, 1)

            self.assertEqual("BACKUP_FAILED", raised.exception.code)
            self.assertEqual(
                "copy_file", raised.exception.details["phase"]
            )
            self.assertEqual(
                "disk_space",
                raised.exception.details["os_error_category"],
            )
            self.assertEqual(before, (root / "Level.sav").read_bytes())
            self.assertEqual(1, len(session.changes()))
            self.assertEqual(1, session.revision)
            self.assertTrue(
                Path(raised.exception.details["backup_path"]).is_dir()
            )

    def test_replace_failure_restores_original_and_keeps_changes(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp) / "save"
            root.mkdir()
            session = self.make_session(root)
            before = (root / "Level.sav").read_bytes()

            def fail(stage, _context):
                if stage == "after_replace":
                    raise OSError("synthetic replacement failure")

            with self.assertRaises(DomainError) as raised:
                SaveWriter(failure_hook=fail).save(session, root, 1)

            self.assertEqual("WRITE_FAILED", raised.exception.code)
            self.assertTrue(raised.exception.details["recovered"])
            self.assertEqual(before, (root / "Level.sav").read_bytes())
            self.assertEqual(1, len(session.changes()))
            self.assertEqual(1, session.revision)
            self.assertTrue(Path(raised.exception.details["backup_path"]).is_dir())
            self.assertTrue(Path(raised.exception.details["staging_path"]).is_dir())

    def test_level_and_player_files_roundtrip_in_one_verified_save(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp) / "save"
            players = root / "Players"
            players.mkdir(parents=True)
            player_id = "11111111-2222-3333-4444-555555555555"
            player_path = players / f"{UUID2HexStr(player_id)}.sav"
            level_gvas = make_gvas(1)
            player_gvas = make_gvas(10)
            (root / "Level.sav").write_bytes(
                compress_gvas_to_sav(
                    level_gvas.write(MAIN_SKIP_PROPERTIES), 0x32, zlib=True
                )
            )
            player_path.write_bytes(
                compress_gvas_to_sav(
                    player_gvas.write(PLAYER_SKIP_PROPERTIES), 0x32, zlib=True
                )
            )
            player = SimpleNamespace(
                PlayerUId=player_id,
                PlayerGVAS=(player_gvas, 0x32),
            )
            manager = SimpleNamespace(
                gvas_file=level_gvas,
                _compression_times=0x32,
                player_mapping={player_id: player},
                item_container_data=SimpleNamespace(container_map={}),
            )
            session = SaveSession.from_loaded_manager(manager, root)

            def restore(state):
                level_value, player_value = state
                level_gvas.properties["Counter"]["value"] = level_value
                player_gvas.properties["Counter"]["value"] = player_value

            session.apply_atomic(
                session_id=session.session_id,
                expected_revision=0,
                command="SyntheticCharacterUpdate",
                target={"player_id": player_id},
                snapshot=lambda: (
                    level_gvas.properties["Counter"]["value"],
                    player_gvas.properties["Counter"]["value"],
                ),
                restore=restore,
                before=lambda: {"level": 1, "player": 10},
                mutate=lambda: (
                    level_gvas.properties["Counter"].update(value=2),
                    player_gvas.properties["Counter"].update(value=20),
                ),
                validate=lambda: None,
                after=lambda: {"level": 2, "player": 20},
                affected_records=(
                    "level:CharacterSaveParameterMap",
                    f"player_file:{player_id}",
                ),
            )

            result = SaveWriter().save(session, root, 1)

            self.assertEqual(2, read_counter(root / "Level.sav"))
            self.assertEqual(20, read_counter(player_path))
            self.assertEqual(
                ("Level.sav", f"Players/{player_path.name}"),
                result.written_files,
            )
            backup_files = Path(result.backup_path) / "files"
            self.assertEqual(1, read_counter(backup_files / "Level.sav"))
            self.assertEqual(10, read_counter(backup_files / "Players" / player_path.name))


if __name__ == "__main__":
    unittest.main()
