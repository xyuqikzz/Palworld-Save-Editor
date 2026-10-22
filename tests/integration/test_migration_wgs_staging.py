from __future__ import annotations

from dataclasses import replace
from functools import partial
from pathlib import Path

import pytest

import palworld_pal_editor.application.save_migration as migration_module
from palworld_pal_editor.application.save_migration import SaveMigration
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.core.pal_objects import PalObjects
from palworld_pal_editor.core.save_manager import SaveManager
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.domain.migration import (
    MigrationMode,
    MigrationRequest,
    MigrationSaveRef,
)
from palworld_pal_editor.domain.models import SavePlatform
from palworld_pal_editor.storage.discovery import XgpSourceCatalog
from palworld_pal_editor.storage.migration_transaction import MigrationTreeTransaction
from palworld_pal_editor.storage.steam import snapshot_tree
from palworld_pal_editor.storage.wgs_format import encode_index, parse_index
from palworld_pal_editor.storage.xgp import XgpWgsAdapter
from tests.unit.test_xgp_storage import _gvas, _sav
from tests.wgs_fixture import make_user_directory


def world_bytes(counter: int) -> bytes:
    gvas = _gvas(counter)
    gvas.properties['worldSaveData']['value']['CharacterSaveParameterMap'] = (
        PalObjects.MapProperty(
            'StructProperty', 'StructProperty', 'StructProperty', 'StructProperty'
        )
    )
    return _sav(gvas)


def migration_fixture(tmp_path, monkeypatch, platform):
    files = {'Level.sav': world_bytes(7), 'WorldOption.sav': _sav(_gvas(9))}
    target = tmp_path / 'target'
    target.mkdir()
    (target / 'Level.sav').write_bytes(world_bytes(1))
    (target / 'target-only.txt').write_text('replaced by full migration')
    if platform is SavePlatform.STEAM:
        source = tmp_path / 'source'
        source.mkdir()
        for name, data in files.items():
            (source / name).write_bytes(data)
        reference = MigrationSaveRef(platform, path=str(source))
    else:
        wgs_root = tmp_path / 'wgs'
        source = make_user_directory(
            wgs_root, '1' * 16 + '_' + 'C' * 32,
            {'A' * 32: files, 'B' * 32: {'Level.sav': world_bytes(99)}},
        )
        catalog = XgpSourceCatalog(roots=(wgs_root,))
        selected = next(s for s in catalog.discover() if s.world_id == 'A' * 32)
        reference = MigrationSaveRef(platform, source_id=selected.source_id)
        monkeypatch.setattr(migration_module, 'SOURCE_CATALOG', catalog)
        monkeypatch.setattr(
            migration_module, 'XgpWgsAdapter', partial(
                XgpWgsAdapter, process_checker=lambda: False,
                workspace_root=tmp_path / 'workspaces',
                backup_root=tmp_path / 'backups', stability_delay=0,
            ),
        )
    request = MigrationRequest(
        MigrationMode.FULL, reference,
        MigrationSaveRef(SavePlatform.STEAM, path=str(target)),
    )
    return source, target, files, request


@pytest.mark.parametrize('platform', [SavePlatform.STEAM, SavePlatform.XGP])
def test_full_migration_copies_selected_logical_world_and_reopens(
    tmp_path, monkeypatch, platform,
):
    source, target, files, request = migration_fixture(tmp_path, monkeypatch, platform)
    original_source = snapshot_tree(source)
    migration = SaveMigration()
    plan = migration.analyze(request)
    assert not plan.blockers

    result = migration.execute(plan.plan_id, (), 'logical-world')

    assert result.status == 'completed'
    assert result.validation['target_reload'] is True
    assert snapshot_tree(source) == original_source
    assert set(snapshot_tree(target).by_path()) == set(files)
    assert (target / 'WorldOption.sav').read_bytes() == files['WorldOption.sav']
    reopened = SaveSession.open(target, manager=SaveManager.create_isolated())
    try:
        assert reopened.manager.gvas_file.properties['Counter']['value'] == 7
    finally:
        reopened.close()


def test_wgs_metadata_change_still_blocks_full_migration(tmp_path, monkeypatch):
    source, target, _files, request = migration_fixture(
        tmp_path, monkeypatch, SavePlatform.XGP,
    )
    migration = SaveMigration()
    plan = migration.analyze(request)
    target_before = snapshot_tree(target)
    index_path = source / 'containers.index'
    index = parse_index(index_path.read_bytes())
    index_path.write_bytes(encode_index(replace(index, flag2=index.flag2 + 1)))

    with pytest.raises(DomainError) as error:
        migration.execute(plan.plan_id, (), 'changed-wgs-metadata')

    assert error.value.code == 'MIGRATION_SOURCE_CHANGED'
    assert snapshot_tree(target) == target_before


@pytest.mark.parametrize('platform', [SavePlatform.STEAM, SavePlatform.XGP])
def test_full_migration_restores_target_after_commit_failure(
    tmp_path, monkeypatch, platform,
):
    source, target, _files, request = migration_fixture(tmp_path, monkeypatch, platform)
    source_before = snapshot_tree(source)
    target_before = snapshot_tree(target)

    def fail_after_swap(stage, _context):
        if stage == 'after_target_swap':
            raise OSError('injected commit failure')

    migration = SaveMigration(transaction_factory=lambda: MigrationTreeTransaction(
        failure_hook=fail_after_swap,
    ))
    plan = migration.analyze(request)
    with pytest.raises(DomainError) as error:
        migration.execute(plan.plan_id, (), 'recover-logical-world')

    assert error.value.code == 'MIGRATION_COMMIT_FAILED'
    assert error.value.details['recovery_status'] == 'restored'
    assert snapshot_tree(target) == target_before
    assert snapshot_tree(source) == source_before


@pytest.mark.parametrize('change', ['content', 'extra_file', 'missing_file'])
def test_changed_normalized_wgs_workspace_cannot_be_staged(
    tmp_path, monkeypatch, change,
):
    source, _target, _files, request = migration_fixture(
        tmp_path, monkeypatch, SavePlatform.XGP,
    )
    original_source = snapshot_tree(source)
    resolved = SaveMigration._resolve_ref(request.source, field='source')
    session = SaveMigration._open(resolved, field='source')
    try:
        if change == 'content':
            (session.workspace / 'Level.sav').write_bytes(world_bytes(100))
        elif change == 'extra_file':
            (session.workspace / 'unexpected.sav').write_bytes(world_bytes(100))
        else:
            (session.workspace / 'WorldOption.sav').unlink()

        with pytest.raises(DomainError) as error:
            SaveMigration._snapshot_for_staging(session)

        assert error.value.code == 'MIGRATION_STAGE_FAILED'
        assert error.value.details['phase'] == 'staging'
        assert snapshot_tree(source) == original_source
    finally:
        session.close()
