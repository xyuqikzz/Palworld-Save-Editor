from __future__ import annotations

import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory

import pytest

from palworld_pal_editor.application.base_storage_editor import BaseStorageEditor
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.application.save_writer import SaveWriter
from palworld_pal_editor.core.save_manager import SaveManager
from palworld_pal_editor.domain.commands import UpdateBaseStorageItemCount
from palworld_pal_editor.domain.item_catalog import ItemCatalog
from palworld_pal_editor.domain.models import ItemContainerType
from palworld_pal_editor.storage.discovery import XgpSourceCatalog
from palworld_pal_editor.storage.steam import snapshot_tree
from palworld_pal_editor.storage.xgp import XgpWgsAdapter


STEAM_FIXTURE_ENV = "PALWORLD_EDITOR_REAL_BASE_STORAGE_STEAM"
XGP_FIXTURE_ENV = "PALWORLD_EDITOR_REAL_BASE_STORAGE_XGP"
COPIED_WGS_USER = "0000000000000000_00000000000000000000000000000000"


def _candidate(session: SaveSession):
    index = session.manager.base_storage_data
    if index is None or not index.complete:
        return None
    catalog = ItemCatalog.load_default()
    for group in session.manager.group_data.get_groups():
        guild_id = str(group.group_id)
        for camp in session.manager.camp_data.get_owned_camp(group.group_id):
            base_id = str(camp.id)
            for binding in index.get_base(guild_id, base_id):
                container = session.manager.item_container_data.get(
                    binding.container_id
                )
                if container is None:
                    continue
                for slot_index, slot in enumerate(container.dense_slots()):
                    if slot is None or slot.dynamic_id is not None:
                        continue
                    entry = catalog.get_optional(slot.static_id)
                    if (
                        entry is None
                        or entry.rule_status != "verified"
                        or entry.max_stack is None
                        or ItemContainerType.BASE_STORAGE
                        not in entry.allowed_containers
                    ):
                        continue
                    next_count = 1 if slot.count != 1 else 2
                    if next_count > entry.max_stack:
                        continue
                    return {
                        "guild_id": guild_id,
                        "base_id": base_id,
                        "container_id": str(binding.container_id),
                        "slot_index": slot_index,
                        "static_id": slot.static_id,
                        "count": next_count,
                    }
    return None


def _update(session: SaveSession, candidate: dict) -> None:
    BaseStorageEditor(session).execute(
        UpdateBaseStorageItemCount(
            session_id=session.session_id,
            expected_revision=session.revision,
            guild_id=candidate["guild_id"],
            base_id=candidate["base_id"],
            container_id=candidate["container_id"],
            slot_index=candidate["slot_index"],
            expected_static_id=candidate["static_id"],
            count=candidate["count"],
        )
    )


def _assert_reopened(session: SaveSession, candidate: dict) -> None:
    binding = session.manager.base_storage_data.resolve(
        candidate["guild_id"],
        candidate["base_id"],
        candidate["container_id"],
    )
    assert binding is not None
    slot = session.manager.item_container_data.get(
        binding.container_id
    ).get_occupied(candidate["slot_index"])
    assert slot.static_id == candidate["static_id"]
    assert slot.count == candidate["count"]


def test_real_steam_base_storage_open_edit_save_reopen() -> None:
    configured = os.environ.get(STEAM_FIXTURE_ENV)
    if not configured:
        pytest.skip(f"{STEAM_FIXTURE_ENV} is not configured")
    source = Path(configured).resolve()
    if not (source / "Level.sav").is_file():
        pytest.skip(f"{STEAM_FIXTURE_ENV} does not name a Steam world")
    source_before = snapshot_tree(source)

    with TemporaryDirectory(prefix="pal-base-storage-steam-") as temp:
        copied = Path(temp) / "world"
        shutil.copytree(source, copied)
        copied_before = snapshot_tree(copied)
        session = SaveSession.open(
            copied,
            manager=SaveManager.create_isolated(),
        )
        candidate = _candidate(session)
        if candidate is None:
            session.close()
            pytest.skip("the Steam fixture has no writable plain base-storage slot")

        _update(session, candidate)
        result = SaveWriter().save(session, copied, session.revision)
        session.close()

        assert result.platform == "steam"
        assert result.target_reload_verified is True
        assert result.written_files == ("Level.sav",)
        assert snapshot_tree(copied) != copied_before

        reopened = SaveSession.open(
            copied,
            manager=SaveManager.create_isolated(),
        )
        _assert_reopened(reopened, candidate)
        reopened.close()

    assert snapshot_tree(source) == source_before


def _copy_xgp_fixture(source: Path, target: Path) -> None:
    if (source / "containers.index").is_file():
        target.mkdir()
        shutil.copytree(source, target / COPIED_WGS_USER)
    else:
        shutil.copytree(source, target)


def test_real_xgp_base_storage_open_edit_save_reopen() -> None:
    configured = os.environ.get(XGP_FIXTURE_ENV)
    if not configured:
        pytest.skip(f"{XGP_FIXTURE_ENV} is not configured")
    source = Path(configured).resolve()
    if not source.is_dir():
        pytest.skip(f"{XGP_FIXTURE_ENV} does not name a WGS directory")
    source_before = snapshot_tree(source)

    with TemporaryDirectory(prefix="pal-base-storage-xgp-") as temp:
        root = Path(temp)
        copied = root / "wgs"
        _copy_xgp_fixture(source, copied)
        catalog = XgpSourceCatalog(roots=(copied,))
        sources = catalog.discover()
        if not sources:
            pytest.skip("the WGS fixture has no discoverable worlds")

        selected_source = None
        session = None
        candidate = None
        for source_index, value in enumerate(sources):
            candidate_adapter = XgpWgsAdapter(
                catalog=catalog,
                process_checker=lambda: False,
                workspace_root=root / f"workspace-{source_index}",
                backup_root=root / "backups",
                stability_delay=0,
            )
            candidate_session = SaveSession.open_storage(
                value,
                candidate_adapter,
                manager=SaveManager.create_isolated(),
            )
            candidate = _candidate(candidate_session)
            if candidate is not None:
                selected_source = value
                session = candidate_session
                break
            candidate_session.close()
        if session is None or candidate is None:
            pytest.skip("the WGS fixture has no writable plain base-storage slot")

        copied_before = snapshot_tree(selected_source.canonical_path)
        _update(session, candidate)
        result = SaveWriter().save(session, None, session.revision)
        session.close()

        assert result.platform == "xgp"
        assert result.source_reloaded is True
        assert result.target_reload_verified is True
        assert result.cloud_sync_verified is False
        assert result.backup_path is not None
        assert snapshot_tree(selected_source.canonical_path) != copied_before

        reopened_source = next(
            value
            for value in catalog.discover()
            if value.source_id == selected_source.source_id
        )
        reopened_adapter = XgpWgsAdapter(
            catalog=catalog,
            process_checker=lambda: False,
            workspace_root=root / "reopened-workspaces",
            backup_root=root / "reopened-backups",
            stability_delay=0,
        )
        reopened = SaveSession.open_storage(
            reopened_source,
            reopened_adapter,
            manager=SaveManager.create_isolated(),
        )
        _assert_reopened(reopened, candidate)
        reopened.close()

    assert snapshot_tree(source) == source_before
