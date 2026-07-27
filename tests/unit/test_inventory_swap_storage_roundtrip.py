from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from palworld_save_tools.gvas import GvasFile
from palworld_save_tools.palsav import compress_gvas_to_sav, decompress_sav_to_gvas
from palworld_save_tools.paltypes import PALWORLD_TYPE_HINTS

from palworld_pal_editor.application.inventory_layout_editor import InventoryLayoutEditor
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.application.save_writer import SaveWriter
from palworld_pal_editor.core.dynamic_item_data import DynamicItemData
from palworld_pal_editor.core.item_container_data import ItemContainerData
from palworld_pal_editor.core.pal_objects import PalObjects
from palworld_pal_editor.core.save_manager import MAIN_SKIP_PROPERTIES
from palworld_pal_editor.domain.commands import SwapItemSlots
from palworld_pal_editor.domain.models import ItemContainerType
from palworld_pal_editor.storage.discovery import XgpSourceCatalog
from palworld_pal_editor.storage.xgp import XgpWgsAdapter
from tests.unit.test_inventory_read import catalog
from tests.unit.test_save_writer import (
    DYNAMIC_CONTAINER_ID,
    ZERO_UUID,
    make_gvas,
)
from tests.wgs_fixture import make_user_directory


RAW_PATH = ".worldSaveData.ItemContainerSaveData.Value.Slots.Slots.RawData"


class _Player:
    PlayerUId = "player-storage"
    InstanceId = "instance-storage"
    NickName = "Storage Player"
    Level = 1
    _player_save_data = {"InventoryInfo": {"value": {"synthetic": True}}}

    def resolve_item_container_ids(self):
        return {"CommonContainerId": DYNAMIC_CONTAINER_ID}


class _Manager:
    def open(self, path, *, lazy_players=False):
        raw, _save_type = decompress_sav_to_gvas((Path(path) / "Level.sav").read_bytes())
        self.gvas_file = GvasFile.read(raw, PALWORLD_TYPE_HINTS, MAIN_SKIP_PROPERTIES)
        self._compression_times = 0x32
        player = _Player()
        self.player_mapping = {player.PlayerUId: player}
        self.item_container_data = ItemContainerData(self.gvas_file)
        self.dynamic_item_data = DynamicItemData(
            self.gvas_file,
            self.item_container_data,
        )
        return self.gvas_file

    def get_player(self, player_id):
        return self.player_mapping.get(player_id)


def _raw_slot(slot_index: int, static_id: str, count: int, trailing: list[int]) -> dict:
    return {
        "RawData": PalObjects.ArrayProperty(
            "ByteProperty",
            {
                "slot_index": slot_index,
                "count": count,
                "item": {
                    "static_id": static_id,
                    "dynamic_id": {
                        "created_world_id": ZERO_UUID,
                        "local_id_in_created_world": ZERO_UUID,
                    },
                },
                "permission": {
                    "type_a": [],
                    "type_b": [],
                    "item_static_ids": [],
                },
                "corruption_progress_value": 0.0,
                "trailing_bytes": trailing,
            },
            RAW_PATH,
        )
    }


def _inventory_gvas() -> GvasFile:
    gvas = make_gvas(1, dangling_dynamic=True)
    world = gvas.properties["worldSaveData"]["value"]
    entry = world["ItemContainerSaveData"]["value"][0]
    entry["value"]["SlotNum"]["value"] = 2
    entry["value"]["Slots"]["value"]["values"] = [
        _raw_slot(0, "Stone", 5, [1, 2, 3]),
        _raw_slot(1, "None", 0, [4, 5, 6]),
    ]
    return gvas


def _sav() -> bytes:
    return compress_gvas_to_sav(
        _inventory_gvas().write(MAIN_SKIP_PROPERTIES),
        0x32,
        zlib=True,
    )


def _swap(session: SaveSession) -> None:
    InventoryLayoutEditor(session, catalog()).execute(
        SwapItemSlots(
            session_id=session.session_id,
            expected_revision=session.revision,
            player_id=_Player.PlayerUId,
            container_type=ItemContainerType.COMMON,
            source_slot_index=0,
            target_slot_index=1,
        )
    )


def _assert_reopened_move(manager: _Manager) -> None:
    container = manager.item_container_data.get(DYNAMIC_CONTAINER_ID)
    assert container.is_empty(0)
    moved = container.get_occupied(1)
    assert moved.static_id == "Stone"
    assert moved.count == 5
    assert moved._raw_data["trailing_bytes"] == [1, 2, 3]
    assert manager.gvas_file.properties["Counter"]["value"] == 1
    manager.dynamic_item_data.assert_consistent()


def test_steam_inventory_swap_save_and_reopen_writes_only_level() -> None:
    with TemporaryDirectory() as temp:
        root = Path(temp) / "steam-save"
        root.mkdir()
        (root / "Level.sav").write_bytes(_sav())
        manager = _Manager()
        manager.open(root)
        session = SaveSession.from_loaded_manager(manager, root)

        _swap(session)
        result = SaveWriter().save(session, root, session.revision)

        reopened = _Manager()
        reopened.open(root)
        _assert_reopened_move(reopened)
        assert result.written_files == ("Level.sav",)
        assert result.staged_reload_verified is True
        assert result.target_reload_verified is True


def test_wgs_inventory_swap_writes_original_slot_and_reopens() -> None:
    with TemporaryDirectory() as temp:
        base = Path(temp)
        wgs_root = base / "wgs"
        wgs_root.mkdir()
        world_id = "A" * 32
        user = make_user_directory(
            wgs_root,
            "1111111111111111_" + "B" * 32,
            {world_id: {"Level.sav": _sav()}},
        )
        catalog_source = XgpSourceCatalog(roots=(wgs_root,))
        adapter = XgpWgsAdapter(
            catalog=catalog_source,
            process_checker=lambda: False,
            workspace_validator=lambda _path: None,
            workspace_root=base / "workspaces",
            backup_root=base / "backups",
            stability_delay=0,
        )
        source = catalog_source.discover()[0]
        opened_binding = source.source_id
        session = SaveSession.open_storage(source, adapter, manager=_Manager())

        _swap(session)
        result = SaveWriter().save(session, None, session.revision)
        session.close()

        reopened_source = next(
            item for item in catalog_source.discover() if item.source_id == opened_binding
        )
        reopened = SaveSession.open_storage(
            reopened_source,
            adapter,
            manager=_Manager(),
        )
        try:
            _assert_reopened_move(reopened.manager)
        finally:
            reopened.close()

        assert user.is_dir()
        assert result.platform == "xgp"
        assert result.written_files == ("Level.sav",)
        assert result.source_reloaded is True
        assert result.target_reload_verified is True
        assert result.cloud_sync_verified is False
        assert result.backup_path is not None and Path(result.backup_path).is_dir()
