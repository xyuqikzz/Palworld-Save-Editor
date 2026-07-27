from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from palworld_save_tools.gvas import GvasFile
from palworld_save_tools.palsav import decompress_sav_to_gvas
from palworld_save_tools.paltypes import PALWORLD_TYPE_HINTS

from palworld_pal_editor.application.expedition_editor import ExpeditionEditor
from palworld_pal_editor.application.character_editor import CharacterEditor
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.application.save_writer import SaveWriter
from palworld_pal_editor.core.save_manager import MAIN_SKIP_PROPERTIES
from palworld_pal_editor.domain.commands import (
    CompleteExpedition,
    UnlockAllExpeditionPals,
)
from palworld_pal_editor.storage.discovery import XgpSourceCatalog
from palworld_pal_editor.storage.xgp import XgpWgsAdapter
from tests.unit.test_xgp_storage import _gvas, _sav
from tests.wgs_fixture import make_user_directory


EXPEDITION_ID = "44444444-5555-6666-7777-888888888888"


class _ExpeditionManager:
    def __init__(self) -> None:
        self.gvas_file = None
        self._compression_times = 0x32
        self.player_mapping = {}

    def open(self, path, *, lazy_players=False):
        raw, compression = decompress_sav_to_gvas(
            (Path(path) / "Level.sav").read_bytes()
        )
        self.gvas_file = GvasFile.read(
            raw,
            PALWORLD_TYPE_HINTS,
            MAIN_SKIP_PROPERTIES,
        )
        self._compression_times = compression
        return self.gvas_file

    @property
    def _start_time(self) -> int:
        return self.gvas_file.properties["Counter"]["value"]

    @_start_time.setter
    def _start_time(self, value: int) -> None:
        self.gvas_file.properties["Counter"]["value"] = value

    def completable_expeditions(self, expedition_ids=None):
        wanted = set(expedition_ids or [EXPEDITION_ID])
        return (
            [{"expedition_id": EXPEDITION_ID}]
            if EXPEDITION_ID in wanted and self._start_time > 1
            else []
        )

    def expedition_completion_state(self, expedition_ids):
        return [
            {
                "expedition_id": EXPEDITION_ID,
                "mission_id": "DUNGEON_GRASS",
                "member_count": 1,
                "state": 2,
                "start_time": self._start_time,
                "can_complete": self._start_time > 1,
            }
            for expedition_id in expedition_ids
            if expedition_id == EXPEDITION_ID
        ]

    def snapshot_expedition_data(self):
        return self._start_time

    def restore_expedition_data(self, value):
        self._start_time = value

    def complete_active_expeditions(self, expedition_ids=None):
        wanted = set(expedition_ids or [EXPEDITION_ID])
        if EXPEDITION_ID not in wanted or self._start_time <= 1:
            return []
        self._start_time = 1
        return [EXPEDITION_ID]


class _FixtureExpeditionPal:
    InstanceId = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    def __init__(self, counter_property) -> None:
        self._pal_param = counter_property

    @property
    def IsExpeditionPal(self) -> bool:
        return self._pal_param["value"] > 0

    @property
    def ExpeditionInstanceId(self):
        return EXPEDITION_ID if self.IsExpeditionPal else None

    def unlock_expedition(self) -> None:
        self._pal_param["value"] = 0


class _UnlockExpeditionManager(_ExpeditionManager):
    def open(self, path, *, lazy_players=False):
        result = super().open(path, lazy_players=lazy_players)
        pal = _FixtureExpeditionPal(self.gvas_file.properties["Counter"])
        self.player_mapping = {
            "owner": SimpleNamespace(_palbox={pal.InstanceId: pal})
        }
        self.baseworker_mapping = {}
        self._dangling_pals = {}
        return result

    @staticmethod
    def expedition_has_member(_expedition_id, _pal_id):
        return False


def test_expedition_wgs_fixture_open_edit_save_and_reopen() -> None:
    with TemporaryDirectory() as temp:
        base = Path(temp)
        wgs_root = base / "wgs"
        wgs_root.mkdir()
        world_id = "8" * 32
        make_user_directory(
            wgs_root,
            "8888888888888888_" + "A" * 32,
            {
                world_id: {
                    "Level.sav": _sav(_gvas(100)),
                    "Players/" + ("1" * 32) + ".sav": b"player-fixture",
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
        session = SaveSession.open_storage(
            catalog.discover()[0],
            adapter,
            manager=_ExpeditionManager(),
        )

        ExpeditionEditor(session).execute(
            CompleteExpedition(
                session_id=session.session_id,
                expected_revision=0,
                expedition_id=EXPEDITION_ID,
            )
        )
        result = SaveWriter().save(session, None, 1)

        assert result.platform == "xgp"
        assert result.source_reloaded is True
        assert result.cloud_sync_verified is False
        assert Path(result.backup_path).is_dir()
        session.close()

        reopened = SaveSession.open_storage(
            catalog.discover()[0],
            adapter,
            manager=_ExpeditionManager(),
        )
        try:
            assert reopened.manager._start_time == 1
        finally:
            reopened.close()


def test_unlock_expedition_pal_wgs_fixture_open_edit_save_and_reopen() -> None:
    with TemporaryDirectory() as temp:
        base = Path(temp)
        wgs_root = base / "wgs"
        wgs_root.mkdir()
        world_id = "7" * 32
        make_user_directory(
            wgs_root,
            "7777777777777777_" + "B" * 32,
            {
                world_id: {
                    "Level.sav": _sav(_gvas(1)),
                    "Players/" + ("2" * 32) + ".sav": b"player-fixture",
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
        session = SaveSession.open_storage(
            catalog.discover()[0],
            adapter,
            manager=_UnlockExpeditionManager(),
        )

        result = CharacterEditor(session).execute(
            UnlockAllExpeditionPals(
                session_id=session.session_id,
                expected_revision=0,
            )
        )
        saved = SaveWriter().save(session, None, 1)

        assert result["value"]["unlocked_count"] == 1
        assert saved.platform == "xgp"
        assert saved.source_reloaded is True
        assert saved.cloud_sync_verified is False
        assert Path(saved.backup_path).is_dir()
        session.close()

        reopened = SaveSession.open_storage(
            catalog.discover()[0],
            adapter,
            manager=_UnlockExpeditionManager(),
        )
        try:
            pal = next(
                iter(next(iter(reopened.manager.player_mapping.values()))._palbox.values())
            )
            assert pal.IsExpeditionPal is False
        finally:
            reopened.close()
