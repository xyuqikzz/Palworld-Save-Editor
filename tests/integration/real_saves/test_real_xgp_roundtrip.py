from __future__ import annotations

import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory

import pytest
from palworld_save_tools.gvas import GvasFile
from palworld_save_tools.palsav import compress_gvas_to_sav, decompress_sav_to_gvas
from palworld_save_tools.paltypes import PALWORLD_TYPE_HINTS

from palworld_pal_editor.application.character_editor import CharacterEditor
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.application.save_writer import SaveWriter
from palworld_pal_editor.application.structural_pal_editor import StructuralPalEditor
from palworld_pal_editor.config import Config
from palworld_pal_editor.core.character_index import CharacterIndex
from palworld_pal_editor.core.save_manager import MAIN_SKIP_PROPERTIES
from palworld_pal_editor.core.save_manager import SaveManager
from palworld_pal_editor.domain.commands import AddPal, HealAllPals
from palworld_pal_editor.domain.models import CharacterContainerType
from palworld_pal_editor.domain.models import StorageCommitRequest
from palworld_pal_editor.storage.discovery import XgpSourceCatalog
from palworld_pal_editor.storage.steam import snapshot_tree
from palworld_pal_editor.storage.xgp import XgpWgsAdapter
from palworld_pal_editor.utils.data_provider import DataProvider


REAL_FIXTURE_ENV = "PALWORLD_EDITOR_REAL_XGP_FIXTURES"
COPIED_WGS_USER = "0000000000000000_00000000000000000000000000000000"


def _verify_gvas(path: Path, _relative: str) -> None:
    raw, _compression = decompress_sav_to_gvas(path.read_bytes())
    GvasFile.read(raw, PALWORLD_TYPE_HINTS, MAIN_SKIP_PROPERTIES)


def _copy_xgp_fixture(configured_path: Path, copied_root: Path) -> None:
    if (configured_path / "containers.index").is_file():
        copied_root.mkdir()
        shutil.copytree(configured_path, copied_root / COPIED_WGS_USER)
        return
    shutil.copytree(configured_path, copied_root)


def test_real_xgp_fixture_is_modified_only_after_copy_and_reopened() -> None:
    configured = os.environ.get(REAL_FIXTURE_ENV)
    if not configured:
        pytest.skip(f"{REAL_FIXTURE_ENV} is not configured")
    configured_path = Path(configured).resolve()
    if not configured_path.is_dir():
        pytest.skip(f"{REAL_FIXTURE_ENV} does not name a readable directory")
    authorized_fixture_before = snapshot_tree(configured_path)

    with TemporaryDirectory() as temp:
        base = Path(temp)
        copied_root = base / "wgs"
        _copy_xgp_fixture(configured_path, copied_root)

        catalog = XgpSourceCatalog(roots=(copied_root,))
        sources = catalog.discover()
        if not sources:
            pytest.skip("the configured fixture contains no discoverable Palworld worlds")
        adapter = XgpWgsAdapter(
            catalog=catalog,
            process_checker=lambda: False,
            workspace_root=base / "workspaces",
            backup_root=base / "backups",
            stability_delay=0,
        )
        opened = adapter.open(sources[0])
        copied_before = snapshot_tree(opened.source.canonical_path).by_path()
        level_payload = str(
            opened.storage_metadata["bindings"]["Level.sav"]["payload_relative"]
        )
        raw, compression = decompress_sav_to_gvas(
            (opened.workspace / "Level.sav").read_bytes()
        )
        gvas = GvasFile.read(raw, PALWORLD_TYPE_HINTS, MAIN_SKIP_PROPERTIES)
        timestamp = gvas.properties.get("Timestamp")
        if not isinstance(timestamp, dict) or not isinstance(timestamp.get("value"), int):
            pytest.skip("real fixture Level.sav has no safely incrementable Timestamp")
        timestamp["value"] += 1
        stage = base / "stage"
        stage.mkdir()
        (stage / "Level.sav").write_bytes(
            compress_gvas_to_sav(
                gvas.write(MAIN_SKIP_PROPERTIES), compression
            )
        )

        result = adapter.commit(
            StorageCommitRequest(
                opened=opened,
                staged_workspace=stage,
                changed_files=(Path("Level.sav"),),
                expected_revision=1,
                verify_file=_verify_gvas,
            )
        )

        assert result.source_reloaded is True
        assert result.backup_path is not None and Path(result.backup_path).is_dir()
        assert not str(result.backup_path).startswith(str(copied_root))
        copied_after = snapshot_tree(opened.source.canonical_path).by_path()
        changed = {
            relative
            for relative, before in copied_before.items()
            if copied_after[relative].sha256 != before.sha256
        }
        assert changed == {"containers.index", level_payload}
        adapter.close(opened)
        reopened = adapter.open(sources[0])
        _verify_gvas(reopened.workspace / "Level.sav", "Level.sav")
        adapter.close(reopened)

    assert snapshot_tree(configured_path) == authorized_fixture_before


def test_real_xgp_add_pal_creation_presets_save_and_reopen() -> None:
    configured = os.environ.get(REAL_FIXTURE_ENV)
    if not configured:
        pytest.skip(f"{REAL_FIXTURE_ENV} is not configured")
    configured_path = Path(configured).resolve()
    if not configured_path.is_dir():
        pytest.skip(f"{REAL_FIXTURE_ENV} does not name a readable directory")
    authorized_fixture_before = snapshot_tree(configured_path)

    with TemporaryDirectory() as temp:
        base = Path(temp)
        copied_root = base / "wgs"
        _copy_xgp_fixture(configured_path, copied_root)

        catalog = XgpSourceCatalog(roots=(copied_root,))
        sources = catalog.discover()
        if not sources:
            pytest.skip("the configured fixture contains no discoverable Palworld worlds")
        adapter = XgpWgsAdapter(
            catalog=catalog,
            process_checker=lambda: False,
            workspace_root=base / "workspaces",
            backup_root=base / "backups",
            stability_delay=0,
        )
        session = SaveSession.open_storage(
            sources[0],
            adapter,
            manager=SaveManager.create_isolated(),
        )
        target_player_id = None
        for player_id in session.manager.player_mapping:
            player = session.load_player(player_id)
            container = session.manager.container_data.get_container(
                player.PalStorageContainerId
            )
            if container is not None and container.available_inv_idx_set:
                target_player_id = str(player_id)
                break
        if target_player_id is None:
            session.close()
            pytest.skip("the configured fixture has no player with a free Palbox slot")

        added = StructuralPalEditor(session).execute(
            AddPal(
                session_id=session.session_id,
                expected_revision=session.revision,
                player_id=target_player_id,
                species_id="SalesPerson_Wander",
                container_type=CharacterContainerType.PAL_STORAGE,
                max_pal=True,
            )
        )
        added_pal_id = added["pal"]["pal_id"]
        added_pal = CharacterIndex(session.manager).pals[added_pal_id]
        assert added_pal.owner_container_type == "PAL_STORAGE"
        result = SaveWriter().save(session, None, session.revision)
        assert result.platform == "xgp"
        assert result.source_reloaded is True
        assert result.target_reload_verified is True
        assert result.cloud_sync_verified is False
        assert result.backup_path is not None and Path(result.backup_path).is_dir()
        session.close()

        reopened_sources = catalog.discover()
        reopened_adapter = XgpWgsAdapter(
            catalog=catalog,
            process_checker=lambda: False,
            workspace_root=base / "reopened-workspaces",
            backup_root=base / "reopened-backups",
            stability_delay=0,
        )
        reopened = SaveSession.open_storage(
            reopened_sources[0],
            reopened_adapter,
            manager=SaveManager.create_isolated(),
        )
        pal = CharacterIndex(reopened.manager).pals[added_pal_id]
        assert pal.owner_container_type == "PAL_STORAGE"
        assert pal.IsHuman
        assert pal.FriendshipLevel == 10
        assert pal.Rank_CraftSpeed == Config.max_souls_level
        assert pal.Rank == 5
        assert "bIsAwakening" not in pal._pal_param
        assert pal.WorkSuitabilities
        assert all(
            level == Config.max_suitability_level
            for level in pal.WorkSuitabilities.values()
        )
        reopened.close()

    assert snapshot_tree(configured_path) == authorized_fixture_before


def test_real_xgp_heal_all_pals_save_and_reopen() -> None:
    configured = os.environ.get(REAL_FIXTURE_ENV)
    if not configured:
        pytest.skip(f"{REAL_FIXTURE_ENV} is not configured")
    configured_path = Path(configured).resolve()
    if not configured_path.is_dir():
        pytest.skip(f"{REAL_FIXTURE_ENV} does not name a readable directory")
    authorized_fixture_before = snapshot_tree(configured_path)

    with TemporaryDirectory() as temp:
        base = Path(temp)
        copied_root = base / "wgs"
        _copy_xgp_fixture(configured_path, copied_root)

        catalog = XgpSourceCatalog(roots=(copied_root,))
        sources = catalog.discover()
        if not sources:
            pytest.skip("the configured fixture contains no discoverable Palworld worlds")
        source = sources[0]
        adapter = XgpWgsAdapter(
            catalog=catalog,
            process_checker=lambda: False,
            workspace_root=base / "workspaces",
            backup_root=base / "backups",
            stability_delay=0,
        )
        session = SaveSession.open_storage(
            source,
            adapter,
            manager=SaveManager.create_isolated(),
        )
        target = next(
            (
                pal
                for pal in CharacterIndex(session.manager).pals.values()
                if pal.ComputedMaxHP
                and DataProvider.get_pal_stats(pal.DataAccessKey, "FOOD")
            ),
            None,
        )
        if target is None:
            session.close()
            pytest.skip("the configured fixture contains no healable Pal")
        target_id = str(target.InstanceId)
        expected_health = target.ComputedMaxHP
        expected_satiety = DataProvider.get_pal_stats(target.DataAccessKey, "FOOD")
        target.Hp = 0
        target.FullStomach = 0.0
        target.SanityValue = 0.0

        result = CharacterEditor(session).execute(
            HealAllPals(
                session_id=session.session_id,
                expected_revision=session.revision,
            )
        )
        assert result["value"]["healed_count"] == len(
            CharacterIndex(session.manager).pals
        )
        saved = SaveWriter().save(session, None, session.revision)
        assert saved.platform == "xgp"
        assert saved.source_reloaded is True
        assert saved.target_reload_verified is True
        assert saved.cloud_sync_verified is False
        assert saved.backup_path is not None and Path(saved.backup_path).is_dir()
        session.close()

        reopened_source = next(
            item
            for item in catalog.discover()
            if item.source_id == source.source_id
        )
        reopened_adapter = XgpWgsAdapter(
            catalog=catalog,
            process_checker=lambda: False,
            workspace_root=base / "reopened-workspaces",
            backup_root=base / "reopened-backups",
            stability_delay=0,
        )
        reopened = SaveSession.open_storage(
            reopened_source,
            reopened_adapter,
            manager=SaveManager.create_isolated(),
        )
        healed = CharacterIndex(reopened.manager).pals[target_id]
        assert healed.Hp == expected_health
        assert healed.FullStomach == expected_satiety
        assert healed.SanityValue == 100.0
        reopened.close()

    assert snapshot_tree(configured_path) == authorized_fixture_before
