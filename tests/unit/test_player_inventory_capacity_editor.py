from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from palworld_save_tools.gvas import GvasFile, GvasHeader
from palworld_save_tools.palsav import compress_gvas_to_sav, decompress_sav_to_gvas
from palworld_save_tools.paltypes import PALWORLD_TYPE_HINTS
from palworld_pal_editor.application.inventory_editor import InventoryEditor
from palworld_pal_editor.application.player_inventory_capacity_editor import (
    PlayerInventoryCapacityEditor,
)
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.application.save_writer import SaveWriter
from palworld_pal_editor.core.dynamic_item_data import DynamicItemData
from palworld_pal_editor.core.item_container_data import ItemContainerData
from palworld_pal_editor.core.pal_objects import PalObjects, toUUID
from palworld_pal_editor.core.save_manager import MAIN_SKIP_PROPERTIES
from palworld_pal_editor.domain.commands import UpdatePlayerInventoryCapacity
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.domain.item_catalog import ItemCatalog
from palworld_pal_editor.storage.discovery import XgpSourceCatalog
from palworld_pal_editor.storage.xgp import XgpWgsAdapter
from tests.wgs_fixture import make_user_directory


PLAYER_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
CONTAINER_ID = toUUID("11111111-2222-3333-4444-555555555555")
ZERO_ID = toUUID("00000000-0000-0000-0000-000000000000")


class _Player:
    PlayerUId = PLAYER_ID
    InstanceId = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
    NickName = "Capacity Test"
    Level = 1
    is_loaded = True

    def __init__(self) -> None:
        self._player_save_data = {
            "InventoryInfo": {
                "value": {
                    "CommonContainerId": PalObjects.PalContainerId(
                        CONTAINER_ID
                    )
                }
            }
        }

    def resolve_item_container_ids(self):
        return {"CommonContainerId": CONTAINER_ID}


def _header() -> GvasHeader:
    return GvasHeader.load(
        {
            "magic": 0x53415647,
            "save_game_version": 3,
            "package_file_version_ue4": 522,
            "package_file_version_ue5": 1008,
            "engine_version_major": 5,
            "engine_version_minor": 1,
            "engine_version_patch": 1,
            "engine_version_changelist": 0,
            "engine_version_branch": "synthetic-inventory-capacity-test",
            "custom_version_format": 3,
            "custom_versions": [],
            "save_game_class_name": "/Script/Pal.PalWorldSaveGame",
        }
    )


def _gvas(capacity: int = 54, *, slotnum_type: str = "IntProperty") -> GvasFile:
    slots = PalObjects.ArrayProperty(
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
                            "count": 0,
                            "item": {
                                "static_id": "None",
                                "dynamic_id": {
                                    "created_world_id": ZERO_ID,
                                    "local_id_in_created_world": ZERO_ID,
                                },
                            },
                            "preserved_test_value": 73,
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
    )
    containers = PalObjects.MapProperty(
        "StructProperty",
        "StructProperty",
        "StructProperty",
        "StructProperty",
    )
    slot_num = PalObjects.IntProperty(capacity)
    slot_num["type"] = slotnum_type
    containers["value"].append(
        {
            "key": {"ID": PalObjects.Guid(CONTAINER_ID)},
            "value": {
                "SlotNum": slot_num,
                "Slots": slots,
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
    world = {
        "type": "StructProperty",
        "struct_type": "PalWorldSaveData",
        "struct_id": PalObjects.EMPTY_UUID,
        "id": None,
        "value": {
            "ItemContainerSaveData": containers,
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
        },
    }
    gvas = GvasFile()
    gvas.header = _header()
    gvas.properties = {
        "PreservedCounter": PalObjects.IntProperty(73),
        "worldSaveData": world,
    }
    gvas.trailer = b"\x00\x00\x00\x00"
    return gvas


def _add_plain_slot(
    gvas: GvasFile,
    slot_index: int,
    *,
    static_id: str = "Stone",
    count: int = 1,
) -> GvasFile:
    values = gvas.properties["worldSaveData"]["value"][
        "ItemContainerSaveData"
    ]["value"][0]["value"]["Slots"]["value"]["values"]
    slot = deepcopy(values[0])
    raw = slot["RawData"]["value"]
    raw["slot_index"] = slot_index
    raw["count"] = count
    raw["item"]["static_id"] = static_id
    values.append(slot)
    return gvas


def _manager(gvas: GvasFile):
    player = _Player()
    containers = ItemContainerData(gvas)
    dynamic_items = DynamicItemData(gvas, containers)

    class Manager:
        gvas_file = gvas
        _compression_times = 0x32
        player_mapping = {PLAYER_ID: player}
        item_container_data = containers
        dynamic_item_data = dynamic_items

        @staticmethod
        def get_player(player_id):
            return player if player_id == PLAYER_ID else None

    return Manager()


class _StorageManager:
    def open(self, path, *, lazy_players=False):
        raw, self._compression_times = decompress_sav_to_gvas(
            (Path(path) / "Level.sav").read_bytes()
        )
        self.gvas_file = GvasFile.read(
            raw, PALWORLD_TYPE_HINTS, MAIN_SKIP_PROPERTIES
        )
        player = _Player()
        self.player_mapping = {PLAYER_ID: player}
        self.item_container_data = ItemContainerData(self.gvas_file)
        self.dynamic_item_data = DynamicItemData(
            self.gvas_file, self.item_container_data
        )
        self.get_player = (
            lambda player_id: player if player_id == PLAYER_ID else None
        )
        return self.gvas_file


def _command(session: SaveSession, capacity: int):
    return UpdatePlayerInventoryCapacity(
        session_id=session.session_id,
        expected_revision=session.revision,
        player_id=PLAYER_ID,
        capacity=capacity,
    )


def _sav(gvas: GvasFile) -> bytes:
    return compress_gvas_to_sav(
        gvas.write(MAIN_SKIP_PROPERTIES), 0x32, zlib=True
    )


def _read_level(path: Path) -> GvasFile:
    raw, _save_type = decompress_sav_to_gvas(path.read_bytes())
    return GvasFile.read(raw, PALWORLD_TYPE_HINTS, MAIN_SKIP_PROPERTIES)


def _properties_without_capacity(gvas: GvasFile) -> dict:
    properties = deepcopy(gvas.properties)
    containers = properties["worldSaveData"]["value"][
        "ItemContainerSaveData"
    ]["value"]
    for container in containers:
        container["value"].pop("SlotNum", None)
    return properties


def test_resize_command_expands_dense_inventory_slots(tmp_path: Path) -> None:
    session = SaveSession.from_loaded_manager(_manager(_gvas()), tmp_path)
    editor = PlayerInventoryCapacityEditor(session)

    assert editor.capability(PLAYER_ID) == {
        "available": True,
        "reason": None,
        "current_capacity": 54,
        "allowed_capacities": [60, 90, 120],
        "minimum_capacity": 42,
        "maximum_capacity": 1000,
        "custom_input": True,
        "expand_only": False,
    }
    result = editor.execute(_command(session, 90))

    assert result["changed"] is True
    assert result["revision"] == 1
    assert session.changes()[0]["affected_records"] == [
        "level:ItemContainerSaveData"
    ]
    inventory = InventoryEditor(
        session, catalog=ItemCatalog([])
    ).get_inventory(PLAYER_ID)
    common = next(
        container
        for container in inventory.containers
        if container.container_type.value == "COMMON"
    )
    assert common.capacity == 90
    assert len(common.slots) == 90


@pytest.mark.parametrize("capacity", [42, 45, 54, 55, 121])
def test_growth_progress_capacities_are_supported(
    tmp_path: Path,
    capacity: int,
) -> None:
    session = SaveSession.from_loaded_manager(
        _manager(_gvas(capacity)), tmp_path
    )

    capability = PlayerInventoryCapacityEditor(session).capability(PLAYER_ID)

    assert capability == {
        "available": True,
        "reason": None,
        "current_capacity": capacity,
        "allowed_capacities": [
            preset for preset in (60, 90, 120) if preset != capacity
        ],
        "minimum_capacity": 42,
        "maximum_capacity": 1000,
        "custom_input": True,
        "expand_only": False,
    }


def test_custom_capacity_is_accepted_within_editor_limit(
    tmp_path: Path,
) -> None:
    session = SaveSession.from_loaded_manager(_manager(_gvas()), tmp_path)

    result = PlayerInventoryCapacityEditor(session).execute(
        _command(session, 75)
    )

    assert result["changed"] is True
    assert result["value"]["capacity"] == 75
    assert result["capability"]["minimum_capacity"] == 42
    assert result["capability"]["maximum_capacity"] == 1000


@pytest.mark.parametrize("target", [1, 41, 1001])
def test_capacity_outside_supported_range_is_rejected(
    tmp_path: Path, target: int
) -> None:
    session = SaveSession.from_loaded_manager(_manager(_gvas()), tmp_path)

    with pytest.raises(DomainError) as raised:
        PlayerInventoryCapacityEditor(session).execute(
            _command(session, target)
        )

    assert raised.value.code == "INVALID_PLAYER_INVENTORY_CAPACITY"
    assert session.revision == 0
    assert session.changes() == []


def test_capacity_above_editor_limit_is_rejected(tmp_path: Path) -> None:
    session = SaveSession.from_loaded_manager(_manager(_gvas()), tmp_path)

    with pytest.raises(DomainError) as raised:
        PlayerInventoryCapacityEditor(session).execute(
            _command(session, 1001)
        )

    assert raised.value.code == "INVALID_PLAYER_INVENTORY_CAPACITY"
    assert session.revision == 0


def test_capacity_limit_still_allows_reduction(tmp_path: Path) -> None:
    session = SaveSession.from_loaded_manager(
        _manager(_gvas(1000)), tmp_path
    )

    editor = PlayerInventoryCapacityEditor(session)
    capability = editor.capability(PLAYER_ID)

    assert capability["available"] is True
    assert capability["reason"] is None
    assert capability["current_capacity"] == 1000
    assert capability["minimum_capacity"] == 42
    assert capability["maximum_capacity"] == 1000
    assert editor.execute(_command(session, 999))["value"]["capacity"] == 999


def test_modded_capacity_above_editor_limit_can_be_reduced(
    tmp_path: Path,
) -> None:
    session = SaveSession.from_loaded_manager(
        _manager(_gvas(1001)), tmp_path
    )
    editor = PlayerInventoryCapacityEditor(session)

    assert editor.capability(PLAYER_ID)["available"] is True
    assert editor.execute(_command(session, 1000))["value"]["capacity"] == 1000


def test_shrink_removes_slots_outside_the_new_capacity(tmp_path: Path) -> None:
    gvas = _add_plain_slot(_gvas(90), 41)
    _add_plain_slot(gvas, 89, count=7)
    session = SaveSession.from_loaded_manager(_manager(gvas), tmp_path)
    editor = PlayerInventoryCapacityEditor(session)

    result = editor.execute(_command(session, 42))
    container = session.manager.item_container_data.get(CONTAINER_ID)

    assert result["changed"] is True
    assert result["value"]["capacity"] == 42
    assert container is not None
    assert container.capacity_matches_declared(42)
    assert container.get_occupied(41).static_id == "Stone"
    assert [
        slot.slot_index for slot in container.iter_encoded_slots()
    ] == [0, 41]
    inventory = InventoryEditor(
        session, catalog=ItemCatalog([])
    ).get_inventory(PLAYER_ID)
    common = next(
        container
        for container in inventory.containers
        if container.container_type.value == "COMMON"
    )
    assert len(common.slots) == 42


def test_failed_shrink_restores_removed_slots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gvas = _add_plain_slot(_gvas(90), 89, count=7)
    session = SaveSession.from_loaded_manager(_manager(gvas), tmp_path)
    editor = PlayerInventoryCapacityEditor(session)

    def fail_validation(_container, _capacity) -> None:
        raise DomainError(
            code="INVARIANT_VIOLATION",
            message="forced resize validation failure",
        )

    monkeypatch.setattr(editor, "_validate_postcondition", fail_validation)
    with pytest.raises(DomainError) as raised:
        editor.execute(_command(session, 42))

    container = session.manager.item_container_data.get(CONTAINER_ID)
    assert raised.value.code == "INVARIANT_VIOLATION"
    assert container is not None
    assert container.capacity_matches_declared(90)
    assert container.get_occupied(89).count == 7
    assert session.revision == 0
    assert session.changes() == []


def test_unknown_slotnum_encoding_disables_capacity_capability(
    tmp_path: Path,
) -> None:
    session = SaveSession.from_loaded_manager(
        _manager(_gvas(slotnum_type="Int64Property")), tmp_path
    )
    capability = PlayerInventoryCapacityEditor(session).capability(PLAYER_ID)

    assert capability["available"] is False
    assert capability["reason"] == "PLAYER_INVENTORY_SLOTNUM_UNSUPPORTED"


def test_steam_expand_save_reopen_preserves_unmodified_fields(
    tmp_path: Path,
) -> None:
    root = tmp_path / "steam-world"
    root.mkdir()
    before = _sav(_gvas())
    (root / "Level.sav").write_bytes(before)
    neutral_before = _properties_without_capacity(
        _read_level(root / "Level.sav")
    )
    manager = _StorageManager()
    assert manager.open(root) is not None
    session = SaveSession.from_loaded_manager(manager, root)
    PlayerInventoryCapacityEditor(session).execute(_command(session, 60))

    result = SaveWriter().save(session, root, 1)
    reloaded = _read_level(root / "Level.sav")
    container = ItemContainerData(reloaded).get(CONTAINER_ID)

    assert result.written_files == ("Level.sav",)
    assert container is not None
    assert container.capacity_matches_declared(60)
    assert reloaded.properties["PreservedCounter"]["value"] == 73
    assert _properties_without_capacity(reloaded) == neutral_before
    assert (Path(result.backup_path) / "files" / "Level.sav").read_bytes() == before


def test_steam_shrink_save_reopen_removes_truncated_slots(
    tmp_path: Path,
) -> None:
    root = tmp_path / "steam-world"
    root.mkdir()
    gvas = _add_plain_slot(_gvas(90), 41)
    _add_plain_slot(gvas, 89, count=7)
    before = _sav(gvas)
    (root / "Level.sav").write_bytes(before)
    manager = _StorageManager()
    assert manager.open(root) is not None
    session = SaveSession.from_loaded_manager(manager, root)
    PlayerInventoryCapacityEditor(session).execute(_command(session, 42))

    result = SaveWriter().save(session, root, 1)
    reloaded = _read_level(root / "Level.sav")
    container = ItemContainerData(reloaded).get(CONTAINER_ID)

    assert result.written_files == ("Level.sav",)
    assert container is not None
    assert container.capacity_matches_declared(42)
    assert container.get_occupied(41).static_id == "Stone"
    assert [
        slot.slot_index for slot in container.iter_encoded_slots()
    ] == [0, 41]
    assert reloaded.properties["PreservedCounter"]["value"] == 73
    assert (
        Path(result.backup_path) / "files" / "Level.sav"
    ).read_bytes() == before


def test_wgs_expand_write_back_and_reopen_original_slot() -> None:
    with TemporaryDirectory() as temp:
        base = Path(temp)
        wgs_root = base / "wgs"
        wgs_root.mkdir()
        world_id = "A" * 32
        make_user_directory(
            wgs_root,
            "1111111111111111_" + "B" * 32,
            {world_id: {"Level.sav": _sav(_gvas())}},
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
        session = SaveSession.open_storage(
            source, adapter, manager=_StorageManager()
        )
        PlayerInventoryCapacityEditor(session).execute(_command(session, 120))
        result = SaveWriter().save(session, None, 1)
        session.close()

        reopened = SaveSession.open_storage(
            source, adapter, manager=_StorageManager()
        )
        try:
            container = reopened.manager.item_container_data.get(CONTAINER_ID)
            assert container is not None
            assert container.capacity_matches_declared(120)
            assert reopened.manager.gvas_file.properties[
                "PreservedCounter"
            ]["value"] == 73
            assert result.written_files == ("Level.sav",)
            assert result.target_reload_verified is True
            assert result.cloud_sync_verified is False
        finally:
            reopened.close()


def test_wgs_shrink_write_back_and_reopen_original_slot() -> None:
    with TemporaryDirectory() as temp:
        base = Path(temp)
        wgs_root = base / "wgs"
        wgs_root.mkdir()
        world_id = "A" * 32
        gvas = _add_plain_slot(_gvas(90), 41)
        _add_plain_slot(gvas, 89, count=7)
        make_user_directory(
            wgs_root,
            "1111111111111111_" + "B" * 32,
            {world_id: {"Level.sav": _sav(gvas)}},
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
        session = SaveSession.open_storage(
            source, adapter, manager=_StorageManager()
        )
        PlayerInventoryCapacityEditor(session).execute(_command(session, 42))
        result = SaveWriter().save(session, None, 1)
        session.close()

        reopened = SaveSession.open_storage(
            source, adapter, manager=_StorageManager()
        )
        try:
            container = reopened.manager.item_container_data.get(CONTAINER_ID)
            assert container is not None
            assert container.capacity_matches_declared(42)
            assert container.get_occupied(41).static_id == "Stone"
            assert [
                slot.slot_index for slot in container.iter_encoded_slots()
            ] == [0, 41]
            assert reopened.manager.gvas_file.properties[
                "PreservedCounter"
            ]["value"] == 73
            assert result.written_files == ("Level.sav",)
            assert result.target_reload_verified is True
            assert result.cloud_sync_verified is False
        finally:
            reopened.close()
