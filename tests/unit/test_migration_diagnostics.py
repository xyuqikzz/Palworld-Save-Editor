from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from palworld_pal_editor.application.save_migration import SaveMigration
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.domain.migration import MigrationMode, MigrationRequest
from palworld_pal_editor.domain.models import SavePlatform, StorageSnapshot


def test_unexpected_execute_failure_marks_failed_and_closes_source():
    migration = SaveMigration()
    migration._plans['plan'] = SimpleNamespace(
        plan=SimpleNamespace(expires_at=datetime.now(timezone.utc) + timedelta(minutes=5), blockers=()),
        source=object(), target=object(),
    )
    source = Mock()
    with patch.object(migration, '_open', side_effect=[source, RuntimeError('target parse failed')]):
        with pytest.raises(DomainError) as error:
            migration.execute('plan', (), 'operation')
    assert error.value.code == 'MIGRATION_STAGE_FAILED'
    assert isinstance(error.value.__cause__, RuntimeError)
    assert migration.operation_status('plan', 'operation')['stage'] == 'failed'
    source.close.assert_called_once()


def test_staged_player_load_failure_reports_exact_step_and_never_serializes(tmp_path):
    migration = SaveMigration()
    session = Mock()
    session.manager.player_mapping = {'player-fixture': object()}
    session.load_player.side_effect = ValueError('Unknown type: None (.)')
    with patch('palworld_pal_editor.application.save_migration.SaveSession.open', return_value=session), patch.object(migration, '_serialize_manager') as serialize:
        with pytest.raises(DomainError) as error:
            migration._migrate_full(tmp_path, ())
    assert error.value.details['step'] == 'load_player'
    assert error.value.details['player_id'] == 'player-fixture'
    assert error.value.details['phase'] == 'migrating'
    serialize.assert_not_called()
    session.close.assert_called_once()


@pytest.mark.parametrize('source_version,target_version,target_platform,code', [
    ('unknown', 'v1', SavePlatform.STEAM, 'MIGRATION_VERSION_UNSUPPORTED'),
    ('v1', 'unknown', SavePlatform.STEAM, 'MIGRATION_VERSION_UNSUPPORTED'),
    ('v1', 'v2', SavePlatform.STEAM, 'MIGRATION_VERSION_UNSUPPORTED'),
    ('v1', 'v1', SavePlatform.XGP, 'MIGRATION_WGS_TARGET_UNSUPPORTED'),
])
def test_analyze_and_execute_keep_version_and_wgs_target_guards(tmp_path, source_version, target_version, target_platform, code):
    transaction = Mock()
    migration = SaveMigration(transaction_factory=transaction)
    source = SimpleNamespace(canonical_path=tmp_path / 'source', platform=SavePlatform.STEAM)
    target = SimpleNamespace(canonical_path=tmp_path / 'target', platform=target_platform)
    source_session, target_session = Mock(), Mock()
    summaries = [SimpleNamespace(save_version=version, players=()) for version in [source_version, target_version]]
    with patch.object(migration, '_resolve_ref', side_effect=[source, target]), patch.object(migration, '_open', side_effect=[source_session, target_session]) as opened, patch.object(migration, '_summary', side_effect=summaries), patch.object(migration, '_snapshot_for_migration', return_value=StorageSnapshot(files=())), patch.object(migration, '_snapshot_for_target', return_value=StorageSnapshot(files=())), patch('palworld_pal_editor.application.save_migration.validate_dps_tree'):
        plan = migration.analyze(MigrationRequest(MigrationMode.CHARACTER_ONLY, source, target))
        assert code in [blocker['code'] for blocker in plan.blockers]
        opened.reset_mock()
        with pytest.raises(DomainError) as error:
            migration.execute(plan.plan_id, (), 'guard-test')
        assert error.value.code == code
        opened.assert_not_called()
    transaction.assert_not_called()
    source_session.close.assert_called_once()
    target_session.close.assert_called_once()
