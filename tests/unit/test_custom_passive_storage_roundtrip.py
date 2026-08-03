from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from palworld_save_tools.gvas import GvasFile, GvasHeader
from palworld_save_tools.palsav import (
    compress_gvas_to_sav,
    decompress_sav_to_gvas,
)
from palworld_save_tools.paltypes import PALWORLD_TYPE_HINTS

from palworld_pal_editor.application.character_editor import CharacterEditor
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.application.save_writer import SaveWriter
from palworld_pal_editor.core.pal_objects import PalObjects
from palworld_pal_editor.core.save_manager import MAIN_SKIP_PROPERTIES
from palworld_pal_editor.domain.commands import UpdatePalSkills
from palworld_pal_editor.storage.discovery import XgpSourceCatalog
from palworld_pal_editor.storage.xgp import XgpWgsAdapter
from tests.wgs_fixture import make_user_directory


PLAYER_ID = "11111111-2222-3333-4444-555555555555"
PAL_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
CUSTOM_PASSIVE = "OtherMod_RoundTripPassive_Exact_01"
UNRESTRICTED_PASSIVES = ("Rare", "Rare", "Legend", "Rare", "Legend")


def _gvas() -> GvasFile:
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
            "engine_version_branch": "synthetic-custom-passive-roundtrip",
            "custom_version_format": 3,
            "custom_versions": [],
            "save_game_class_name": "/Script/Pal.PalWorldSaveGame",
        }
    )
    gvas.properties = {
        "PassiveSkillList": PalObjects.ArrayProperty(
            "NameProperty",
            {"values": ["Rare"]},
        )
    }
    gvas.trailer = b"\0\0\0\0"
    return gvas


def _sav() -> bytes:
    return compress_gvas_to_sav(
        _gvas().write(MAIN_SKIP_PROPERTIES),
        0x32,
        zlib=True,
    )


class _SyntheticPal:
    """Binds CharacterEditor to one serialized NameProperty array."""

    InstanceId = PAL_ID
    EquipWaza = ()
    MasteredWaza = ()

    def __init__(self, gvas: GvasFile) -> None:
        self._pal_param = {
            "PassiveSkillList": gvas.properties["PassiveSkillList"]
        }
        self._display_name_cache = {}

    @property
    def PassiveSkillList(self):
        return PalObjects.get_ArrayProperty(
            self._pal_param["PassiveSkillList"]
        )


class _PassiveManager:
    def __init__(self) -> None:
        self.gvas_file = None
        self._compression_times = None
        self.player_mapping = {}
        self.item_container_data = SimpleNamespace(container_map={})
        self.pal = None

    def open(self, path, *, lazy_players=False):
        raw, self._compression_times = decompress_sav_to_gvas(
            (Path(path) / "Level.sav").read_bytes()
        )
        self.gvas_file = GvasFile.read(
            raw,
            PALWORLD_TYPE_HINTS,
            MAIN_SKIP_PROPERTIES,
        )
        self.pal = _SyntheticPal(self.gvas_file)
        return self.gvas_file

    def get_pal(self, pal_id):
        return self.pal if str(pal_id) == str(self.pal.InstanceId) else None


def _edit_save_and_close(
    session: SaveSession,
    *,
    passive: tuple[str, ...] = ("Rare", CUSTOM_PASSIVE),
    allow_custom_passive: bool = True,
    unrestricted: bool = False,
) -> None:
    CharacterEditor(session).execute(
        UpdatePalSkills(
            session_id=session.session_id,
            expected_revision=0,
            pal_id=str(session.manager.pal.InstanceId),
            passive=passive,
            allow_custom_passive=allow_custom_passive,
            unrestricted=unrestricted,
        )
    )
    SaveWriter().save(
        session,
        session.source if session.platform.value == "steam" else None,
        expected_revision=1,
    )
    session.close()


def _assert_reopened_exact(
    session: SaveSession,
    expected: tuple[str, ...] = ("Rare", CUSTOM_PASSIVE),
) -> None:
    assert session.manager.pal.PassiveSkillList == list(expected)
    assert (
        session.manager.pal._pal_param["PassiveSkillList"]["array_type"]
        == "NameProperty"
    )


def test_custom_passive_steam_fixture_open_edit_save_reopen() -> None:
    with TemporaryDirectory() as temp:
        root = Path(temp) / "steam-world"
        root.mkdir()
        (root / "Level.sav").write_bytes(_sav())

        session = SaveSession.open(root, manager=_PassiveManager())
        _edit_save_and_close(session)

        reopened = SaveSession.open(root, manager=_PassiveManager())
        _assert_reopened_exact(reopened)
        reopened.close()


def test_custom_passive_wgs_fixture_open_edit_save_reopen() -> None:
    with TemporaryDirectory() as temp:
        base = Path(temp)
        root = base / "wgs"
        root.mkdir()
        make_user_directory(
            root,
            "1111111111111111_" + "C" * 32,
            {"A" * 32: {"Level.sav": _sav()}},
        )
        catalog = XgpSourceCatalog(roots=(root,))
        source = catalog.discover()[0]
        adapter = XgpWgsAdapter(
            catalog=catalog,
            process_checker=lambda: False,
            workspace_validator=lambda _path: None,
            workspace_root=base / "workspaces",
            backup_root=base / "backups",
            stability_delay=0,
        )

        session = SaveSession.open_storage(
            source,
            adapter,
            manager=_PassiveManager(),
        )
        _edit_save_and_close(session)

        reopened = SaveSession.open_storage(
            source,
            adapter,
            manager=_PassiveManager(),
        )
        _assert_reopened_exact(reopened)
        reopened.close()


def test_unrestricted_passives_steam_fixture_open_edit_save_reopen() -> None:
    with TemporaryDirectory() as temp:
        root = Path(temp) / "steam-world"
        root.mkdir()
        (root / "Level.sav").write_bytes(_sav())

        session = SaveSession.open(root, manager=_PassiveManager())
        _edit_save_and_close(
            session,
            passive=UNRESTRICTED_PASSIVES,
            allow_custom_passive=False,
            unrestricted=True,
        )

        reopened = SaveSession.open(root, manager=_PassiveManager())
        _assert_reopened_exact(reopened, UNRESTRICTED_PASSIVES)
        reopened.close()


def test_unrestricted_passives_wgs_fixture_open_edit_save_reopen() -> None:
    with TemporaryDirectory() as temp:
        base = Path(temp)
        root = base / "wgs"
        root.mkdir()
        make_user_directory(
            root,
            "1111111111111111_" + "C" * 32,
            {"A" * 32: {"Level.sav": _sav()}},
        )
        catalog = XgpSourceCatalog(roots=(root,))
        source = catalog.discover()[0]
        adapter = XgpWgsAdapter(
            catalog=catalog,
            process_checker=lambda: False,
            workspace_validator=lambda _path: None,
            workspace_root=base / "workspaces",
            backup_root=base / "backups",
            stability_delay=0,
        )

        session = SaveSession.open_storage(
            source,
            adapter,
            manager=_PassiveManager(),
        )
        _edit_save_and_close(
            session,
            passive=UNRESTRICTED_PASSIVES,
            allow_custom_passive=False,
            unrestricted=True,
        )

        reopened = SaveSession.open_storage(
            source,
            adapter,
            manager=_PassiveManager(),
        )
        _assert_reopened_exact(reopened, UNRESTRICTED_PASSIVES)
        reopened.close()
