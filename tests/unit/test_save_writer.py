from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from palworld_save_tools.gvas import GvasFile, GvasHeader
from palworld_save_tools.palsav import compress_gvas_to_sav, decompress_sav_to_gvas
from palworld_save_tools.paltypes import PALWORLD_TYPE_HINTS

from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.application.save_writer import SaveWriter
from palworld_pal_editor.core.pal_objects import PalObjects, UUID2HexStr
from palworld_pal_editor.core.save_manager import (
    MAIN_SKIP_PROPERTIES,
    PLAYER_SKIP_PROPERTIES,
)
from palworld_pal_editor.domain.errors import DomainError


def make_gvas(counter: int) -> GvasFile:
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
    gvas.properties = {"Counter": PalObjects.IntProperty(counter)}
    gvas.trailer = b"\x00\x00\x00\x00"
    return gvas


def read_counter(path: Path) -> int:
    raw, _save_type = decompress_sav_to_gvas(path.read_bytes())
    gvas = GvasFile.read(raw, PALWORLD_TYPE_HINTS, MAIN_SKIP_PROPERTIES)
    return gvas.properties["Counter"]["value"]


class SaveWriterTests(unittest.TestCase):
    def make_session(self, root: Path) -> SaveSession:
        gvas = make_gvas(1)
        (root / "Level.sav").write_bytes(
            compress_gvas_to_sav(gvas.write(MAIN_SKIP_PROPERTIES), 0x32, zlib=True)
        )
        manager = SimpleNamespace(
            gvas_file=gvas,
            _compression_times=0x32,
            player_mapping={},
            item_container_data=SimpleNamespace(container_map={}),
        )
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

    def test_verified_backup_staging_reload_and_new_baseline(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp) / "save"
            root.mkdir()
            session = self.make_session(root)
            before = (root / "Level.sav").read_bytes()

            result = SaveWriter().save(session, root, 1)

            self.assertEqual(2, read_counter(root / "Level.sav"))
            self.assertEqual([], session.changes())
            self.assertTrue(result.staged_reload_verified)
            self.assertEqual(("Level.sav",), result.written_files)
            backup = Path(result.backup_path)
            self.assertTrue((backup / "manifest.json").is_file())
            self.assertEqual(1, read_counter(backup / "files" / "Level.sav"))
            self.assertEqual(before, (backup / "files" / "Level.sav").read_bytes())
            self.assertFalse(str(backup).startswith(str(root) + str(Path("/"))))

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
