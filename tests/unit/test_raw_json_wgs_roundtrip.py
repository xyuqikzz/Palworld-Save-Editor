from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from palworld_save_tools.gvas import GvasFile
from palworld_save_tools.palsav import compress_gvas_to_sav, decompress_sav_to_gvas
from palworld_save_tools.paltypes import PALWORLD_TYPE_HINTS

from palworld_pal_editor.application.raw_json_editor import RawJsonEditor
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.application.save_writer import SaveWriter
from palworld_pal_editor.core.lazy_player_entity import LazyPlayerEntity
from palworld_pal_editor.core.pal_objects import UUID2HexStr
from palworld_pal_editor.core.save_manager import (
    MAIN_SKIP_PROPERTIES,
    PLAYER_SKIP_PROPERTIES,
)
from palworld_pal_editor.storage.discovery import XgpSourceCatalog
from palworld_pal_editor.storage.xgp import XgpWgsAdapter
from tests.unit.test_raw_json_editor import (
    PLAYER_GROUP_ID,
    PLAYER_ID,
    _player_gvas,
    _player_object,
)
from tests.unit.test_xgp_storage import _gvas, _sav
from tests.wgs_fixture import make_user_directory


class _Manager:
    def __init__(self) -> None:
        self.gvas_file = None
        self._compression_times = 0x32
        self.player_mapping = {}
        self.item_container_data = SimpleNamespace(container_map={})
        self.get_player = lambda player_id: self.player_mapping.get(str(player_id))

    def open(self, path, *, lazy_players=False):
        root = Path(path)
        raw, compression = decompress_sav_to_gvas(
            (root / "Level.sav").read_bytes()
        )
        self.gvas_file = GvasFile.read(
            raw,
            PALWORLD_TYPE_HINTS,
            MAIN_SKIP_PROPERTIES,
        )
        self._compression_times = compression
        player_path = root / "Players" / f"{UUID2HexStr(PLAYER_ID)}.sav"
        self.player_mapping = {}
        if player_path.is_file():
            def load_player():
                player_raw, player_compression = decompress_sav_to_gvas(
                    player_path.read_bytes()
                )
                return (
                    GvasFile.read(
                        player_raw,
                        PALWORLD_TYPE_HINTS,
                        PLAYER_SKIP_PROPERTIES,
                    ),
                    player_compression,
                )

            self.player_mapping[str(PLAYER_ID)] = LazyPlayerEntity(
                PLAYER_GROUP_ID,
                _player_object(),
                {},
                load_player,
            )
        return self.gvas_file


def test_raw_json_wgs_fixture_open_edit_save_and_reopen() -> None:
    with TemporaryDirectory() as temp:
        base = Path(temp)
        wgs_root = base / "wgs"
        wgs_root.mkdir()
        world_id = "9" * 32
        make_user_directory(
            wgs_root,
            "9999999999999999_" + "A" * 32,
            {world_id: {"Level.sav": _sav(_gvas(1))}},
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
        source = catalog.discover()[0]
        session = SaveSession.open_storage(source, adapter, manager=_Manager())
        editor = RawJsonEditor()

        document = json.loads(editor.read_document(session, "Level.sav")["text"])
        document["properties"]["Counter"]["value"] = 4
        editor.apply_document(
            session,
            session_id=session.session_id,
            expected_revision=0,
            relative_path="Level.sav",
            text=json.dumps(document),
        )
        result = SaveWriter().save(session, None, 1)

        assert result.platform == "xgp"
        assert result.source_reloaded is True
        assert result.cloud_sync_verified is False
        assert Path(result.backup_path).is_dir()
        assert not str(result.backup_path).startswith(str(wgs_root))
        session.close()

        reopened = SaveSession.open_storage(
            catalog.discover()[0],
            adapter,
            manager=_Manager(),
        )
        try:
            reopened_document = json.loads(
                editor.read_document(reopened, "Level.sav")["text"]
            )
            assert reopened_document["properties"]["Counter"]["value"] == 4
        finally:
            reopened.close()


def test_raw_json_wgs_player_file_open_edit_save_and_reopen() -> None:
    with TemporaryDirectory() as temp:
        base = Path(temp)
        wgs_root = base / "wgs"
        wgs_root.mkdir()
        world_id = "8" * 32
        player_path = f"Players/{UUID2HexStr(PLAYER_ID)}.sav"
        player_payload = compress_gvas_to_sav(
            _player_gvas().write(PLAYER_SKIP_PROPERTIES),
            0x32,
            zlib=True,
        )
        make_user_directory(
            wgs_root,
            "8888888888888888_" + "B" * 32,
            {
                world_id: {
                    "Level.sav": _sav(_gvas(1)),
                    player_path: player_payload,
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
            manager=_Manager(),
        )
        editor = RawJsonEditor()

        document = json.loads(editor.read_document(session, player_path)["text"])
        document["properties"]["Counter"]["value"] = 12
        editor.apply_document(
            session,
            session_id=session.session_id,
            expected_revision=0,
            relative_path=player_path,
            text=json.dumps(document),
        )
        result = SaveWriter().save(session, None, 1)

        assert result.platform == "xgp"
        assert result.source_reloaded is True
        session.close()

        reopened = SaveSession.open_storage(
            catalog.discover()[0],
            adapter,
            manager=_Manager(),
        )
        try:
            reopened_document = json.loads(
                editor.read_document(reopened, player_path)["text"]
            )
            assert reopened_document["properties"]["Counter"]["value"] == 12
        finally:
            reopened.close()
