from __future__ import annotations

import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory

import pytest
from palworld_save_tools.gvas import GvasFile
from palworld_save_tools.palsav import compress_gvas_to_sav, decompress_sav_to_gvas
from palworld_save_tools.paltypes import PALWORLD_TYPE_HINTS

from palworld_pal_editor.core.save_manager import MAIN_SKIP_PROPERTIES
from palworld_pal_editor.domain.models import StorageCommitRequest
from palworld_pal_editor.storage.discovery import XgpSourceCatalog
from palworld_pal_editor.storage.steam import snapshot_tree
from palworld_pal_editor.storage.xgp import XgpWgsAdapter


REAL_FIXTURE_ENV = "PALWORLD_EDITOR_REAL_XGP_FIXTURES"


def _verify_gvas(path: Path, _relative: str) -> None:
    raw, _compression = decompress_sav_to_gvas(path.read_bytes())
    GvasFile.read(raw, PALWORLD_TYPE_HINTS, MAIN_SKIP_PROPERTIES)


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
        if (configured_path / "containers.index").is_file():
            copied_root.mkdir()
            shutil.copytree(configured_path, copied_root / configured_path.name)
        else:
            shutil.copytree(configured_path, copied_root)

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
        assert result.backup_path is not None and result.backup_path.is_dir()
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
