from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import shutil
from copy import deepcopy
from types import SimpleNamespace

import pytest
from palworld_save_tools.archive import UUID
from palworld_save_tools.gvas import GvasFile, GvasHeader
from palworld_save_tools.palsav import compress_gvas_to_sav, decompress_sav_to_gvas
from palworld_save_tools.paltypes import PALWORLD_TYPE_HINTS

from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.application.save_writer import SaveWriter
from palworld_pal_editor.core.pal_objects import PalObjects
from palworld_pal_editor.core.save_manager import MAIN_SKIP_PROPERTIES
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.domain.models import StorageCommitRequest
from palworld_pal_editor.storage.discovery import XgpSourceCatalog
from palworld_pal_editor.storage.steam import sha256_file, snapshot_tree
from palworld_pal_editor.storage.wgs_format import (
    parse_container,
    parse_index,
    select_payload_folder,
)
from palworld_pal_editor.storage.xgp import PalworldProcessChecker, XgpWgsAdapter
import palworld_pal_editor.storage.xgp as xgp_module
from tests.wgs_fixture import make_user_directory


START_POINT_ID = "04099789-4a41-4a09-f6f1-99985c080bc8"
LOCKER_PLAYER_UID = "7e358108-07d8-4c32-bd21-69c77b15f83d"
LOCKER_INSTANCE_ID = "49a8e005-50ab-4b88-86c8-fd768a010cba"


def _set_property_world_data() -> dict:
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


def _gvas(counter: int) -> GvasFile:
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
            "engine_version_branch": "synthetic-wgs-test",
            "custom_version_format": 3,
            "custom_versions": [],
            "save_game_class_name": "/Script/Pal.PalWorldSaveGame",
        }
    )
    gvas.properties = {
        "Counter": PalObjects.IntProperty(counter),
        "worldSaveData": _set_property_world_data(),
    }
    gvas.trailer = b"\0\0\0\0"
    return gvas


def _sav(gvas: GvasFile) -> bytes:
    return compress_gvas_to_sav(gvas.write(MAIN_SKIP_PROPERTIES), 0x32, zlib=True)


def _read_gvas(path: Path) -> GvasFile:
    raw, _compression = decompress_sav_to_gvas(path.read_bytes())
    return GvasFile.read(raw, PALWORLD_TYPE_HINTS, MAIN_SKIP_PROPERTIES)


def _counter(path: Path) -> int:
    return _read_gvas(path).properties["Counter"]["value"]


def _start_point_ids(path: Path) -> tuple[str, ...]:
    values = _read_gvas(path).properties["worldSaveData"]["value"][
        "InvaderDeclarationSaveData"
    ]["value"]["ValidatedStartPointIds"]["value"]["values"]
    return tuple(str(value) for value in values)


def _locker_character_ids(path: Path) -> tuple[tuple[str, str], ...]:
    values = _read_gvas(path).properties["worldSaveData"]["value"][
        "InLockerCharacterInstanceIDArray"
    ]["value"]["values"]
    return tuple(
        (str(value["PlayerUId"]["value"]), str(value["InstanceId"]["value"]))
        for value in values
    )


def _cnk0_payload(sav: bytes) -> bytes:
    return b"\x32\x5f\x00\x00" + (1).to_bytes(4, "little") + b"CNK0" + sav


def test_process_checker_fails_closed_when_processes_cannot_be_enumerated(
    monkeypatch,
) -> None:
    monkeypatch.setattr(xgp_module.sys, "platform", "win32")

    def unavailable():
        raise OSError("process enumeration unavailable")

    monkeypatch.setattr(xgp_module, "_windows_process_names", unavailable)
    with pytest.raises(DomainError) as raised:
        PalworldProcessChecker()()
    assert raised.value.code == "WGS_GAME_RUNNING"


def test_process_checker_detects_palworld_from_native_process_names(monkeypatch) -> None:
    monkeypatch.setattr(xgp_module.sys, "platform", "win32")
    monkeypatch.setattr(
        xgp_module,
        "_windows_process_names",
        lambda: ("explorer.exe", "PALWORLD-WINGDK-SHIPPING.EXE"),
    )

    assert PalworldProcessChecker()() is True


def test_xgp_open_maps_payloads_to_private_steam_style_workspace_and_cleans_it() -> None:
    with TemporaryDirectory() as temp:
        root = Path(temp) / "wgs"
        root.mkdir()
        world_id = "A" * 32
        player_id = "B" * 32
        make_user_directory(
            root,
            "1111111111111111_" + "C" * 32,
            {
                world_id: {
                    "Level.sav": b"level-bytes",
                    "LevelMeta.sav": b"meta-bytes",
                    f"Players/{player_id}.sav": b"player-bytes",
                }
            },
        )
        catalog = XgpSourceCatalog(roots=(root,))
        source = catalog.discover()[0]
        adapter = XgpWgsAdapter(
            catalog=catalog,
            process_checker=lambda: False,
            workspace_validator=lambda _path: None,
            stability_delay=0,
        )

        opened = adapter.open(source)

        assert opened.workspace.parent != root
        assert (opened.workspace / "Level.sav").read_bytes() == b"level-bytes"
        assert (opened.workspace / "LevelMeta.sav").read_bytes() == b"meta-bytes"
        assert (opened.workspace / "Players" / f"{player_id}.sav").read_bytes() == b"player-bytes"
        assert set(opened.logical_files) == {
            "Level.sav",
            "LevelMeta.sav",
            f"Players/{player_id}.sav",
        }
        assert opened.cleanup_required is True

        workspace = opened.workspace
        adapter.close(opened)
        assert not workspace.exists()


def test_xgp_open_normalizes_current_cnk0_level_payload() -> None:
    with TemporaryDirectory() as temp:
        base = Path(temp)
        root = base / "wgs"
        root.mkdir()
        standard_level = _sav(_gvas(7))
        user = make_user_directory(
            root,
            "1212121212121212_" + "C" * 32,
            {"A" * 32: {"Level.sav": _cnk0_payload(standard_level)}},
            level_container_suffix="Level-01",
        )
        catalog = XgpSourceCatalog(roots=(root,))
        adapter = XgpWgsAdapter(
            catalog=catalog,
            process_checker=lambda: False,
            workspace_validator=lambda _path: None,
            workspace_root=base / "workspaces",
            backup_root=base / "backups",
            stability_delay=0,
        )

        opened = adapter.open(catalog.discover()[0])

        assert (opened.workspace / "Level.sav").read_bytes() == standard_level
        assert _counter(opened.workspace / "Level.sav") == 7
        binding = opened.storage_metadata["bindings"]["Level.sav"]
        assert binding["payload_encoding"] == "cnk0"
        physical = user / Path(str(binding["payload_relative"]))
        assert physical.read_bytes() == _cnk0_payload(standard_level)


def test_xgp_open_rejects_truncated_cnk0_payload() -> None:
    with TemporaryDirectory() as temp:
        base = Path(temp)
        root = base / "wgs"
        root.mkdir()
        make_user_directory(
            root,
            "1313131313131313_" + "D" * 32,
            {"B" * 32: {"Level.sav": _cnk0_payload(b"truncated")}},
            level_container_suffix="Level-01",
        )
        catalog = XgpSourceCatalog(roots=(root,))
        adapter = XgpWgsAdapter(
            catalog=catalog,
            process_checker=lambda: False,
            workspace_validator=lambda _path: None,
            workspace_root=base / "workspaces",
            backup_root=base / "backups",
            stability_delay=0,
        )

        with pytest.raises(DomainError) as raised:
            adapter.open(catalog.discover()[0])

        assert raised.value.code == "WGS_CONTAINER_INCOMPLETE"


def test_xgp_open_validates_unknown_indexed_container_references() -> None:
    with TemporaryDirectory() as temp:
        base = Path(temp)
        root = base / "wgs"
        root.mkdir()
        user = make_user_directory(
            root,
            "EFEFEFEFEFEFEFEF_" + "3" * 32,
            {
                "8" * 32: {
                    "Level.sav": b"level",
                    "OpaqueFuture.bin": b"unknown",
                }
            },
        )
        index = parse_index((user / "containers.index").read_bytes())
        unknown = next(
            entry for entry in index.entries if "OpaqueFuture" in entry.name
        )
        container_dir = user / unknown.container_folder
        container = parse_container(
            (container_dir / f"container.{unknown.sequence}").read_bytes()
        )
        available = {
            path.name.upper()
            for path in container_dir.iterdir()
            if path.is_file() and not path.name.startswith("container.")
        }
        payload = select_payload_folder(container.files[0], available)
        (container_dir / payload).unlink()

        catalog = XgpSourceCatalog(roots=(root,))
        adapter = XgpWgsAdapter(
            catalog=catalog,
            process_checker=lambda: False,
            workspace_validator=lambda _path: None,
            workspace_root=base / "workspaces",
            backup_root=base / "backups",
            stability_delay=0,
        )
        with pytest.raises(DomainError) as raised:
            adapter.open(catalog.discover()[0])
        assert raised.value.code == "WGS_CONTAINER_INCOMPLETE"


def test_xgp_commit_updates_only_changed_payload_and_index_with_verified_backup() -> None:
    with TemporaryDirectory() as temp:
        base = Path(temp)
        root = base / "wgs"
        root.mkdir()
        world_id = "A" * 32
        player_id = "B" * 32
        user = make_user_directory(
            root,
            "1111111111111111_" + "C" * 32,
            {
                world_id: {
                    "Level.sav": b"level-before",
                    f"Players/{player_id}.sav": b"player-before",
                    "OpaqueFuture.bin": b"unknown-container-before",
                }
            },
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
        opened = adapter.open(source)
        before = snapshot_tree(user).by_path()
        player_payload = opened.storage_metadata["bindings"][f"Players/{player_id}.sav"][
            "payload_relative"
        ]
        level_payload = opened.storage_metadata["bindings"]["Level.sav"][
            "payload_relative"
        ]
        stage = base / "stage"
        stage.mkdir()
        (stage / "Level.sav").write_bytes(b"level-after-and-larger")

        result = adapter.commit(
            StorageCommitRequest(
                opened=opened,
                staged_workspace=stage,
                changed_files=(Path("Level.sav"),),
                expected_revision=1,
                verify_file=lambda _path, _relative: None,
            )
        )

        after = snapshot_tree(user).by_path()
        assert (user / Path(level_payload)).read_bytes() == b"level-after-and-larger"
        assert (user / Path(player_payload)).read_bytes() == b"player-before"
        assert after[player_payload].sha256 == before[player_payload].sha256
        unchanged = set(before) - {"containers.index", level_payload}
        assert all(after[path].sha256 == before[path].sha256 for path in unchanged)
        assert result.source_reloaded is True
        assert result.recovery_status == "not_needed"
        assert result.backup_path is not None
        assert not str(result.backup_path).startswith(str(root))
        assert result.manifest_path is not None and result.manifest_path.is_file()
        assert (result.backup_path / "files" / "containers.index").is_file()


def test_xgp_commit_replaces_cnk0_level_with_verified_standard_payload() -> None:
    with TemporaryDirectory() as temp:
        base = Path(temp)
        root = base / "wgs"
        root.mkdir()
        world_id = "C" * 32
        player_id = "D" * 32
        original_level = _sav(_gvas(1))
        player_payload = _sav(_gvas(11))
        user = make_user_directory(
            root,
            "1414141414141414_" + "E" * 32,
            {
                world_id: {
                    "Level.sav": _cnk0_payload(original_level),
                    f"Players/{player_id}.sav": player_payload,
                }
            },
            level_container_suffix="Level-01",
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
        opened = adapter.open(source)
        before = snapshot_tree(user).by_path()
        assert _start_point_ids(opened.workspace / "Level.sav") == (
            START_POINT_ID,
        )
        assert _locker_character_ids(opened.workspace / "Level.sav") == (
            (LOCKER_PLAYER_UID, LOCKER_INSTANCE_ID),
        )
        level_relative = str(
            opened.storage_metadata["bindings"]["Level.sav"]["payload_relative"]
        )
        player_relative = str(
            opened.storage_metadata["bindings"][f"Players/{player_id}.sav"][
                "payload_relative"
            ]
        )
        edited_gvas = _read_gvas(opened.workspace / "Level.sav")
        edited_gvas.properties["Counter"]["value"] = 2
        replacement = _sav(edited_gvas)
        stage = base / "stage"
        stage.mkdir()
        (stage / "Level.sav").write_bytes(replacement)

        adapter.commit(
            StorageCommitRequest(
                opened=opened,
                staged_workspace=stage,
                changed_files=(Path("Level.sav"),),
                expected_revision=1,
                verify_file=lambda path, _relative: _counter(path),
            )
        )

        after = snapshot_tree(user).by_path()
        assert (user / Path(level_relative)).read_bytes() == replacement
        assert _counter(user / Path(level_relative)) == 2
        assert after[player_relative].sha256 == before[player_relative].sha256
        adapter.close(opened)
        reopened = adapter.open(source)
        assert _counter(reopened.workspace / "Level.sav") == 2
        assert _start_point_ids(reopened.workspace / "Level.sav") == (
            START_POINT_ID,
        )
        assert _locker_character_ids(reopened.workspace / "Level.sav") == (
            (LOCKER_PLAYER_UID, LOCKER_INSTANCE_ID),
        )
        adapter.close(reopened)


def test_xgp_payload_failure_restores_the_entire_fixture_byte_for_byte() -> None:
    with TemporaryDirectory() as temp:
        base = Path(temp)
        root = base / "wgs"
        root.mkdir()
        world_id = "D" * 32
        user = make_user_directory(
            root,
            "3333333333333333_" + "E" * 32,
            {world_id: {"Level.sav": b"original-level"}},
        )
        catalog = XgpSourceCatalog(roots=(root,))
        adapter = XgpWgsAdapter(
            catalog=catalog,
            process_checker=lambda: False,
            workspace_validator=lambda _path: None,
            workspace_root=base / "workspaces",
            backup_root=base / "backups",
            stability_delay=0,
        )
        opened = adapter.open(catalog.discover()[0])
        original = snapshot_tree(user)
        stage = base / "stage"
        stage.mkdir()
        (stage / "Level.sav").write_bytes(b"replacement-level")

        def fail(stage_name, _context):
            if stage_name == "after_payload_replace":
                raise OSError("injected payload failure")

        with pytest.raises(DomainError) as raised:
            adapter.commit(
                StorageCommitRequest(
                    opened=opened,
                    staged_workspace=stage,
                    changed_files=(Path("Level.sav"),),
                    expected_revision=1,
                    verify_file=lambda _path, _relative: None,
                    failure_hook=fail,
                )
            )

        assert raised.value.code == "WGS_COMMIT_FAILED"
        assert raised.value.details["recovery_status"] == "restored"
        assert snapshot_tree(user) == original
        assert Path(raised.value.details["manifest_path"]).is_file()
        assert Path(raised.value.details["journal_path"]).is_file()


def test_save_writer_uses_xgp_adapter_commit_and_refreshes_session_revision() -> None:
    with TemporaryDirectory() as temp:
        base = Path(temp)
        root = base / "wgs"
        root.mkdir()
        world_id = "F" * 32
        gvas = _gvas(1)
        make_user_directory(
            root,
            "4444444444444444_" + "A" * 32,
            {world_id: {"Level.sav": _sav(gvas)}},
        )
        catalog = XgpSourceCatalog(roots=(root,))
        adapter = XgpWgsAdapter(
            catalog=catalog,
            process_checker=lambda: False,
            workspace_validator=lambda _path: None,
            workspace_root=base / "workspaces",
            backup_root=base / "backups",
            stability_delay=0,
        )

        class Manager:
            def __init__(self):
                self.gvas_file = gvas
                self._compression_times = 0x32
                self.player_mapping = {}
                self.item_container_data = SimpleNamespace(container_map={})

            def open(self, _path, *, lazy_players=False):
                return self.gvas_file

        session = SaveSession.open_storage(
            catalog.discover()[0], adapter, manager=Manager()
        )

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
            before=lambda: {"counter": 1},
            mutate=lambda: gvas.properties["Counter"].update(value=2),
            validate=lambda: None,
            after=lambda: {"counter": 2},
            affected_records=("level:Synthetic",),
        )

        result = SaveWriter().save(session, None, 1)

        payload_relative = session.opened_save.storage_metadata["bindings"]["Level.sav"][
            "payload_relative"
        ]
        assert _counter(session.source / Path(payload_relative)) == 2
        assert result.platform == "xgp"
        assert result.source_reloaded is True
        assert result.cloud_sync_verified is False
        assert session.revision == 1
        assert session.changes() == []

        with pytest.raises(DomainError) as invalid_target:
            SaveWriter().save(session, base / "not-a-wgs-target", 1)
        assert invalid_target.value.code == "WGS_COMMIT_FAILED"


@pytest.mark.parametrize(
    "failure_stage",
    ["after_payload_replace", "before_index_replace", "after_index_replace", "before_final_reopen"],
)
def test_recoverable_commit_failures_restore_exact_source(failure_stage: str) -> None:
    with TemporaryDirectory() as temp:
        base = Path(temp)
        root = base / "wgs"
        root.mkdir()
        user = make_user_directory(
            root,
            "5555555555555555_" + "B" * 32,
            {"1" * 32: {"Level.sav": b"before"}},
        )
        catalog = XgpSourceCatalog(roots=(root,))
        adapter = XgpWgsAdapter(
            catalog=catalog,
            process_checker=lambda: False,
            workspace_validator=lambda _path: None,
            workspace_root=base / "workspaces",
            backup_root=base / "backups",
            stability_delay=0,
        )
        opened = adapter.open(catalog.discover()[0])
        original = snapshot_tree(user)
        stage = base / "stage"
        stage.mkdir()
        (stage / "Level.sav").write_bytes(b"after")

        def fail(stage_name, _context):
            if stage_name == failure_stage:
                raise OSError(f"injected {failure_stage}")

        with pytest.raises(DomainError) as raised:
            adapter.commit(
                StorageCommitRequest(
                    opened=opened,
                    staged_workspace=stage,
                    changed_files=(Path("Level.sav"),),
                    expected_revision=1,
                    verify_file=lambda _path, _relative: None,
                    failure_hook=fail,
                )
            )

        assert raised.value.code in {"WGS_COMMIT_FAILED", "WGS_RELOAD_FAILED"}
        assert raised.value.details["recovery_status"] == "restored"
        assert snapshot_tree(user) == original


@pytest.mark.parametrize("failure_stage", ["after_payload_replace", "after_index_replace"])
def test_next_open_recovers_a_process_interrupted_after_replace(
    failure_stage: str,
) -> None:
    with TemporaryDirectory() as temp:
        base = Path(temp)
        root = base / "wgs"
        root.mkdir()
        user = make_user_directory(
            root,
            "ABABABABABABABAB_" + "1" * 32,
            {"6" * 32: {"Level.sav": b"before"}},
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
        opened = adapter.open(source)
        original = snapshot_tree(user)
        stage = base / "stage"
        stage.mkdir()
        (stage / "Level.sav").write_bytes(b"after")

        def terminate(stage_name, _context):
            if stage_name == failure_stage:
                raise SystemExit(f"injected process termination at {failure_stage}")

        with pytest.raises(SystemExit):
            adapter.commit(
                StorageCommitRequest(
                    opened=opened,
                    staged_workspace=stage,
                    changed_files=(Path("Level.sav"),),
                    expected_revision=1,
                    verify_file=lambda _path, _relative: None,
                    failure_hook=terminate,
                )
            )

        assert snapshot_tree(user) != original
        recovered = adapter.open(source)
        assert snapshot_tree(user) == original
        journals = list((base / "backups").rglob("journal.json"))
        assert len(journals) == 1
        assert '"status": "restored"' in journals[0].read_text(encoding="utf-8")
        adapter.close(recovered)


def test_write_ahead_in_flight_record_recovers_replace_before_progress_update() -> None:
    with TemporaryDirectory() as temp:
        base = Path(temp)
        root = base / "wgs"
        root.mkdir()
        user = make_user_directory(
            root,
            "CDCDCDCDCDCDCDCD_" + "2" * 32,
            {"7" * 32: {"Level.sav": b"before"}},
        )
        catalog = XgpSourceCatalog(roots=(root,))
        source = catalog.discover()[0]

        class InterruptedAdapter(XgpWgsAdapter):
            interrupted = False

            def _replace_from_candidate(self, candidate, target):
                super()._replace_from_candidate(candidate, target)
                if not self.interrupted and target.name != "containers.index":
                    self.interrupted = True
                    raise SystemExit("terminated after replace before progress update")

        interrupted = InterruptedAdapter(
            catalog=catalog,
            process_checker=lambda: False,
            workspace_validator=lambda _path: None,
            workspace_root=base / "workspaces",
            backup_root=base / "backups",
            stability_delay=0,
        )
        opened = interrupted.open(source)
        original = snapshot_tree(user)
        stage = base / "stage"
        stage.mkdir()
        (stage / "Level.sav").write_bytes(b"after")

        with pytest.raises(SystemExit):
            interrupted.commit(
                StorageCommitRequest(
                    opened=opened,
                    staged_workspace=stage,
                    changed_files=(Path("Level.sav"),),
                    expected_revision=1,
                    verify_file=lambda _path, _relative: None,
                )
            )

        recovery = XgpWgsAdapter(
            catalog=catalog,
            process_checker=lambda: False,
            workspace_validator=lambda _path: None,
            workspace_root=base / "workspaces",
            backup_root=base / "backups",
            stability_delay=0,
        )
        recovered = recovery.open(source)
        assert snapshot_tree(user) == original
        recovery.close(recovered)


@pytest.mark.parametrize(
    ("failure_stage", "expected_code"),
    [
        ("before_backup_copy", "WGS_BACKUP_FAILED"),
        ("after_container_stage", "WGS_STAGE_FAILED"),
    ],
)
def test_precommit_failures_never_change_source(
    failure_stage: str, expected_code: str
) -> None:
    with TemporaryDirectory() as temp:
        base = Path(temp)
        root = base / "wgs"
        root.mkdir()
        user = make_user_directory(
            root,
            "6666666666666666_" + "C" * 32,
            {"2" * 32: {"Level.sav": b"before"}},
        )
        catalog = XgpSourceCatalog(roots=(root,))
        adapter = XgpWgsAdapter(
            catalog=catalog,
            process_checker=lambda: False,
            workspace_validator=lambda _path: None,
            workspace_root=base / "workspaces",
            backup_root=base / "backups",
            stability_delay=0,
        )
        opened = adapter.open(catalog.discover()[0])
        original = snapshot_tree(user)
        stage = base / "stage"
        stage.mkdir()
        (stage / "Level.sav").write_bytes(b"after")

        def fail(stage_name, _context):
            if stage_name == failure_stage:
                raise OSError(f"injected {failure_stage}")

        with pytest.raises(DomainError) as raised:
            adapter.commit(
                StorageCommitRequest(
                    opened=opened,
                    staged_workspace=stage,
                    changed_files=(Path("Level.sav"),),
                    expected_revision=1,
                    verify_file=lambda _path, _relative: None,
                    failure_hook=fail,
                )
            )

        assert raised.value.code == expected_code
        assert snapshot_tree(user) == original


def test_source_change_and_running_game_are_rejected_before_writing() -> None:
    with TemporaryDirectory() as temp:
        base = Path(temp)
        root = base / "wgs"
        root.mkdir()
        user = make_user_directory(
            root,
            "7777777777777777_" + "D" * 32,
            {"3" * 32: {"Level.sav": b"before"}},
        )
        catalog = XgpSourceCatalog(roots=(root,))
        source = catalog.discover()[0]
        running = XgpWgsAdapter(
            catalog=catalog,
            process_checker=lambda: True,
            workspace_validator=lambda _path: None,
            stability_delay=0,
        )
        with pytest.raises(DomainError) as game:
            running.open(source)
        assert game.value.code == "WGS_GAME_RUNNING"

        adapter = XgpWgsAdapter(
            catalog=catalog,
            process_checker=lambda: False,
            workspace_validator=lambda _path: None,
            workspace_root=base / "workspaces",
            backup_root=base / "backups",
            stability_delay=0,
        )
        opened = adapter.open(source)
        payload_relative = opened.storage_metadata["bindings"]["Level.sav"][
            "payload_relative"
        ]
        (user / Path(payload_relative)).write_bytes(b"external-change")
        stage = base / "stage"
        stage.mkdir()
        (stage / "Level.sav").write_bytes(b"editor-change")
        with pytest.raises(DomainError) as changed:
            adapter.commit(
                StorageCommitRequest(
                    opened=opened,
                    staged_workspace=stage,
                    changed_files=(Path("Level.sav"),),
                    expected_revision=1,
                    verify_file=lambda _path, _relative: None,
                )
            )
        assert changed.value.code == "WGS_SOURCE_CHANGED"


def test_game_starting_after_backup_is_rejected_before_the_first_replace() -> None:
    with TemporaryDirectory() as temp:
        base = Path(temp)
        root = base / "wgs"
        root.mkdir()
        user = make_user_directory(
            root,
            "9999999999999999_" + "F" * 32,
            {"5" * 32: {"Level.sav": b"before"}},
        )
        checks = iter((False, False, True))
        catalog = XgpSourceCatalog(roots=(root,))
        adapter = XgpWgsAdapter(
            catalog=catalog,
            process_checker=lambda: next(checks),
            workspace_validator=lambda _path: None,
            workspace_root=base / "workspaces",
            backup_root=base / "backups",
            stability_delay=0,
        )
        opened = adapter.open(catalog.discover()[0])
        original = snapshot_tree(user)
        stage = base / "stage"
        stage.mkdir()
        (stage / "Level.sav").write_bytes(b"after")

        with pytest.raises(DomainError) as raised:
            adapter.commit(
                StorageCommitRequest(
                    opened=opened,
                    staged_workspace=stage,
                    changed_files=(Path("Level.sav"),),
                    expected_revision=1,
                    verify_file=lambda _path, _relative: None,
                )
            )

        assert raised.value.code == "WGS_GAME_RUNNING"
        assert snapshot_tree(user) == original


def test_recovery_failure_keeps_backup_manifest_journal_and_reports_highest_error() -> None:
    with TemporaryDirectory() as temp:
        base = Path(temp)
        root = base / "wgs"
        root.mkdir()
        make_user_directory(
            root,
            "8888888888888888_" + "E" * 32,
            {"4" * 32: {"Level.sav": b"before"}},
        )
        catalog = XgpSourceCatalog(roots=(root,))
        adapter = XgpWgsAdapter(
            catalog=catalog,
            process_checker=lambda: False,
            workspace_validator=lambda _path: None,
            workspace_root=base / "workspaces",
            backup_root=base / "backups",
            stability_delay=0,
        )
        opened = adapter.open(catalog.discover()[0])
        stage = base / "stage"
        stage.mkdir()
        (stage / "Level.sav").write_bytes(b"after")

        def fail(stage_name, _context):
            if stage_name in {"after_payload_replace", "before_recovery"}:
                raise OSError(f"injected {stage_name}")

        with pytest.raises(DomainError) as raised:
            adapter.commit(
                StorageCommitRequest(
                    opened=opened,
                    staged_workspace=stage,
                    changed_files=(Path("Level.sav"),),
                    expected_revision=1,
                    verify_file=lambda _path, _relative: None,
                    failure_hook=fail,
                )
            )

        assert raised.value.code == "WGS_RECOVERY_FAILED"
        assert raised.value.details["recovery_status"] == "failed"
        assert Path(raised.value.details["backup_path"]).is_dir()
        assert Path(raised.value.details["manifest_path"]).is_file()
        assert Path(raised.value.details["journal_path"]).is_file()
        assert stage.is_dir()
