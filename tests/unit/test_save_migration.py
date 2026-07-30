from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from palworld_pal_editor.application.save_migration import (
    SaveMigration,
    build_player_candidates,
    validate_distinct_paths,
)
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.domain.migration import (
    MigrationMode,
    MigrationPlayer,
    MigrationStage,
    PlayerIdentityMapping,
)
from palworld_pal_editor.domain.models import SavePlatform, StorageSnapshot
from palworld_pal_editor.storage.discovery import SOURCE_CATALOG
from palworld_pal_editor.storage.migration_transaction import (
    MigrationTreeTransaction,
)
from palworld_pal_editor.storage.steam import (
    snapshot_active_steam_tree,
    snapshot_tree,
)


def player(uid: str, instance: str, name: str) -> MigrationPlayer:
    return MigrationPlayer(
        player_uid=uid,
        instance_id=instance,
        name=name,
        level=10,
    )


def test_player_candidates_prefer_unique_name_and_single_player() -> None:
    candidates = build_player_candidates(
        (
            player("source-a", "instance-a", "Alice"),
            player("source-b", "instance-b", "Bob"),
        ),
        (
            player("target-b", "target-instance-b", "Bob"),
            player("target-a", "target-instance-a", "Alice"),
        ),
    )
    assert [(item.source_player_uid, item.target_player_uid) for item in candidates] == [
        ("source-a", "target-a"),
        ("source-b", "target-b"),
    ]
    assert all(item.evidence == "unique_name" for item in candidates)
    assert all(item.auto_confirmed for item in candidates)

    single = build_player_candidates(
        (player("source", "source-instance", ""),),
        (player("target", "target-instance", ""),),
    )
    assert single[0].evidence == "single_player"
    assert single[0].auto_confirmed


def test_duplicate_names_are_not_auto_confirmed() -> None:
    candidates = build_player_candidates(
        (
            player("source-a", "instance-a", "Same"),
            player("source-b", "instance-b", "Same"),
        ),
        (
            player("target-a", "target-instance-a", "Same"),
            player("target-b", "target-instance-b", "Same"),
        ),
    )
    assert len(candidates) == 2
    assert all(item.target_player_uid is None for item in candidates)
    assert all(item.evidence == "ambiguous_name" for item in candidates)
    assert all(not item.auto_confirmed for item in candidates)


def test_mapping_validation_rejects_duplicate_target() -> None:
    mappings = (
        PlayerIdentityMapping(
            source_player_uid="source-a",
            source_instance_id="instance-a",
            target_player_uid="target",
            target_instance_id="target-instance",
            evidence="manual",
            confirmed=True,
        ),
        PlayerIdentityMapping(
            source_player_uid="source-b",
            source_instance_id="instance-b",
            target_player_uid="target",
            target_instance_id="target-instance",
            evidence="manual",
            confirmed=True,
        ),
    )
    with pytest.raises(DomainError) as raised:
        SaveMigration.validate_mappings(
            MigrationMode.CHARACTER_ONLY,
            mappings,
            source_players={
                "source-a": player("source-a", "instance-a", "A"),
                "source-b": player("source-b", "instance-b", "B"),
            },
            target_players={
                "target": player("target", "target-instance", "T"),
            },
        )
    assert raised.value.code == "MIGRATION_PLAYER_MAPPING_DUPLICATE"


def test_full_mapping_allows_unmapped_source_player_ids() -> None:
    assert (
        SaveMigration.validate_mappings(
            MigrationMode.FULL,
            (),
            source_players={
                "source-a": player("source-a", "instance-a", "A"),
            },
            target_players={},
        )
        == ()
    )


def test_same_and_overlapping_paths_are_rejected() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "source"
        source.mkdir()
        child = source / "child"
        child.mkdir()
        with pytest.raises(DomainError) as same:
            validate_distinct_paths(source, source)
        assert same.value.code == "MIGRATION_SAME_SOURCE_TARGET"
        with pytest.raises(DomainError) as overlap:
            validate_distinct_paths(source, child)
        assert overlap.value.code == "MIGRATION_SAME_SOURCE_TARGET"


def test_tree_transaction_copies_unknown_files_and_replaces_complete_tree() -> None:
    with TemporaryDirectory(prefix="pwe-migration-test-") as directory:
        root = Path(directory)
        target = root / "target"
        staged = root / "staged"
        target.mkdir()
        staged.mkdir()
        (target / "delete.me").write_bytes(b"old")
        (target / "rename.old").write_bytes(b"old-name")
        (staged / "rename.new").write_bytes(b"new-name")
        (staged / "unknown.bin").write_bytes(b"\x00\x01unknown")
        expected = snapshot_tree(staged)
        progress: list[str] = []

        result = MigrationTreeTransaction().commit(
            target=target,
            staged=staged,
            expected_target=snapshot_tree(target),
            operation_id="operation",
            progress_callback=progress.append,
        )

        assert progress == ["backing_up", "committing"]
        assert snapshot_tree(target) == expected
        assert not (target / "delete.me").exists()
        assert (target / "rename.new").read_bytes() == b"new-name"
        assert (target / "unknown.bin").read_bytes() == b"\x00\x01unknown"
        assert Path(result.backup_path).is_dir()
        assert Path(result.manifest_path).is_file()


def test_tree_transaction_accepts_the_adapter_snapshot_file_order() -> None:
    with TemporaryDirectory(prefix="pwe-migration-test-") as directory:
        root = Path(directory)
        target = root / "target"
        staged = root / "staged"
        target.mkdir()
        staged.mkdir()
        (target / "WorldOption.sav").write_bytes(b"options")
        (target / "Players").mkdir()
        (target / "Players" / "player.sav").write_bytes(b"player")
        (staged / "Level.sav").write_bytes(b"staged")
        captured = snapshot_tree(target)
        adapter_order = StorageSnapshot(files=tuple(reversed(captured.files)))

        result = MigrationTreeTransaction().commit(
            target=target,
            staged=staged,
            expected_target=adapter_order,
            operation_id="operation",
        )

        assert Path(result.backup_path).is_dir()
        assert (target / "Level.sav").read_bytes() == b"staged"


@pytest.mark.skipif(os.name != "nt", reason="Windows long-path regression")
def test_tree_transaction_excludes_backup_files_beyond_max_path(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    operation_id = "11111111-1111-1111-1111-111111111111"
    backup_container = (
        target.parent / ".Palworld-Pal-Editor-Migration-Backup"
    )
    timestamp_placeholder = "20260101T000000.000000Z"
    projected_files_root = (
        backup_container
        / target.name
        / f"{timestamp_placeholder}-{operation_id}"
        / "files"
    )
    filename = "0B07C718000000000000000000000000.sav"
    projected_without_padding = projected_files_root / "backup" / filename
    padding_length = max(270, len(str(projected_without_padding)) + 2) - (
        len(str(projected_without_padding)) + 1
    )
    relative = Path("backup") / ("x" * padding_length) / filename
    source_file = target / relative
    projected_backup_file = projected_files_root / relative
    assert len(str(source_file)) < 260
    assert len(str(projected_backup_file)) >= 260
    source_file.parent.mkdir(parents=True)
    source_file.write_bytes(b"target")
    before = snapshot_active_steam_tree(target)

    try:
        prepared = MigrationTreeTransaction().prepare_backup(
            target=target,
            expected_target=before,
            operation_id=operation_id,
        )

        assert prepared.manifest_path.is_file()
        MigrationTreeTransaction()._verify_prepared_backup(prepared)
        assert not (
            prepared.backup_path / "files" / relative
        ).exists()
    finally:
        extended_backup = Path("\\\\?\\" + str(backup_container.resolve()))
        if extended_backup.exists():
            shutil.rmtree(extended_backup)


def test_tree_transaction_preserves_internal_backup_without_copying_it(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    staged = tmp_path / "staged"
    target.mkdir()
    staged.mkdir()
    (target / "Level.sav").write_bytes(b"target")
    history = target / "backup" / "world" / "Level.sav"
    history.parent.mkdir(parents=True)
    history.write_bytes(b"historical")
    (staged / "Level.sav").write_bytes(b"staged")

    result = MigrationTreeTransaction().commit(
        target=target,
        staged=staged,
        expected_target=snapshot_active_steam_tree(target),
        operation_id="operation",
    )

    assert (target / "Level.sav").read_bytes() == b"staged"
    assert history.read_bytes() == b"historical"
    assert not (
        Path(result.backup_path)
        / "files"
        / "backup"
        / "world"
        / "Level.sav"
    ).exists()


def test_tree_transaction_restores_preserved_backup_after_commit_failure(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    staged = tmp_path / "staged"
    target.mkdir()
    staged.mkdir()
    (target / "Level.sav").write_bytes(b"target")
    history = target / "backup" / "world" / "Level.sav"
    history.parent.mkdir(parents=True)
    history.write_bytes(b"historical")
    (staged / "Level.sav").write_bytes(b"staged")
    before = snapshot_active_steam_tree(target)

    def fail(stage: str, _context: dict[str, object]) -> None:
        if stage == "after_preserved_directories":
            raise OSError("injected failure after preserving backups")

    with pytest.raises(DomainError) as raised:
        MigrationTreeTransaction(failure_hook=fail).commit(
            target=target,
            staged=staged,
            expected_target=before,
            operation_id="operation",
        )

    assert raised.value.code == "MIGRATION_COMMIT_FAILED"
    assert raised.value.details["recovery_status"] == "restored"
    assert (target / "Level.sav").read_bytes() == b"target"
    assert history.read_bytes() == b"historical"


def test_tree_transaction_restores_target_after_partial_commit_failure() -> None:
    with TemporaryDirectory(prefix="pwe-migration-test-") as directory:
        root = Path(directory)
        target = root / "target"
        staged = root / "staged"
        target.mkdir()
        staged.mkdir()
        (target / "Level.sav").write_bytes(b"target")
        (staged / "Level.sav").write_bytes(b"staged")
        before = snapshot_tree(target)

        def fail(stage: str, _context: dict[str, object]) -> None:
            if stage == "after_target_swap":
                raise OSError("injected commit failure")

        with pytest.raises(DomainError) as raised:
            MigrationTreeTransaction(failure_hook=fail).commit(
                target=target,
                staged=staged,
                expected_target=before,
                operation_id="operation",
            )
        assert raised.value.code == "MIGRATION_COMMIT_FAILED"
        assert raised.value.details["recovery_status"] == "restored"
        assert snapshot_tree(target) == before


def test_tree_transaction_restores_target_when_final_reload_validation_fails() -> None:
    with TemporaryDirectory(prefix="pwe-migration-test-") as directory:
        root = Path(directory)
        target = root / "target"
        staged = root / "staged"
        target.mkdir()
        staged.mkdir()
        (target / "Level.sav").write_bytes(b"target")
        (staged / "Level.sav").write_bytes(b"staged")
        before = snapshot_tree(target)

        def reject_reloaded(_target: Path) -> None:
            raise ValueError("injected final reload failure")

        with pytest.raises(DomainError) as raised:
            MigrationTreeTransaction().commit(
                target=target,
                staged=staged,
                expected_target=before,
                operation_id="operation",
                post_commit_validator=reject_reloaded,
            )

        assert raised.value.code == "MIGRATION_COMMIT_FAILED"
        assert raised.value.details["recovery_status"] == "restored"
        assert snapshot_tree(target) == before


def test_tree_transaction_rejects_a_changed_prepared_backup() -> None:
    with TemporaryDirectory(prefix="pwe-migration-test-") as directory:
        root = Path(directory)
        target = root / "target"
        staged = root / "staged"
        target.mkdir()
        staged.mkdir()
        (target / "Level.sav").write_bytes(b"target")
        (staged / "Level.sav").write_bytes(b"staged")
        before = snapshot_tree(target)
        transaction = MigrationTreeTransaction()
        prepared = transaction.prepare_backup(
            target=target,
            expected_target=before,
            operation_id="operation",
        )
        (prepared.backup_path / "files" / "Level.sav").write_bytes(b"changed")

        with pytest.raises(DomainError) as raised:
            transaction.commit(
                target=target,
                staged=staged,
                expected_target=before,
                operation_id="operation",
                prepared_backup=prepared,
            )

        assert raised.value.code == "MIGRATION_BACKUP_FAILED"
        assert snapshot_tree(target) == before


def test_tree_transaction_stops_when_backup_copy_fails() -> None:
    with TemporaryDirectory(prefix="pwe-migration-test-") as directory:
        root = Path(directory)
        target = root / "target"
        staged = root / "staged"
        target.mkdir()
        staged.mkdir()
        (target / "Level.sav").write_bytes(b"target")
        (staged / "Level.sav").write_bytes(b"staged")
        before = snapshot_tree(target)

        def fail(stage: str, _context: dict[str, object]) -> None:
            if stage == "before_backup_copy":
                raise OSError("injected backup failure")

        with pytest.raises(DomainError) as raised:
            MigrationTreeTransaction(failure_hook=fail).commit(
                target=target,
                staged=staged,
                expected_target=before,
                operation_id="operation",
            )

        assert raised.value.code == "MIGRATION_BACKUP_FAILED"
        assert raised.value.details["phase"] == "backing_up"
        assert raised.value.details["failed_file"] == "Level.sav"
        assert snapshot_tree(target) == before


def test_tree_transaction_stops_when_target_changes_after_backup() -> None:
    with TemporaryDirectory(prefix="pwe-migration-test-") as directory:
        root = Path(directory)
        target = root / "target"
        staged = root / "staged"
        target.mkdir()
        staged.mkdir()
        (target / "Level.sav").write_bytes(b"target")
        (staged / "Level.sav").write_bytes(b"staged")
        before = snapshot_tree(target)
        transaction = MigrationTreeTransaction()
        prepared = transaction.prepare_backup(
            target=target,
            expected_target=before,
            operation_id="operation",
        )
        (target / "Level.sav").write_bytes(b"changed-after-backup")

        with pytest.raises(DomainError) as raised:
            transaction.commit(
                target=target,
                staged=staged,
                expected_target=before,
                operation_id="operation",
                prepared_backup=prepared,
            )

        assert raised.value.code == "MIGRATION_TARGET_CHANGED"
        assert (target / "Level.sav").read_bytes() == b"changed-after-backup"


def test_operation_id_rejects_non_path_safe_value() -> None:
    with pytest.raises(DomainError) as raised:
        SaveMigration.validate_operation_id(" operation ")

    assert raised.value.code == "MIGRATION_OPERATION_INVALID"


def test_operation_status_reports_current_progress() -> None:
    migration = SaveMigration()
    operation_key = ("plan", "operation")

    migration._progress(MigrationStage.STAGING, operation_key)
    migration._progress(MigrationStage.MIGRATING, operation_key)

    assert migration.operation_status(*operation_key) == {
        "plan_id": "plan",
        "operation_id": "operation",
        "stage": "migrating",
        "progress": ["staging", "migrating"],
        "completed": False,
    }


def test_collision_mapping_preserves_unique_ids_and_remaps_collisions() -> None:
    preserved = "11111111-1111-1111-1111-111111111111"
    collided = "22222222-2222-2222-2222-222222222222"

    mapping = SaveMigration._allocate_uuid_mapping(
        (preserved, collided),
        {collided},
    )

    assert mapping[preserved] == preserved
    assert mapping[collided] != collided
    assert mapping[collided] not in {preserved, collided}


def test_xgp_open_uses_the_trusted_source_catalog() -> None:
    source = SimpleNamespace(platform=SavePlatform.XGP)
    opened = object()

    with patch(
        "palworld_pal_editor.application.save_migration.SaveSession.open_storage",
        return_value=opened,
    ) as open_storage:
        assert SaveMigration._open(source, field="source") is opened

    adapter = open_storage.call_args.args[1]
    assert adapter._catalog is SOURCE_CATALOG


def test_steam_migration_snapshot_excludes_existing_backup_history(
    tmp_path: Path,
) -> None:
    (tmp_path / "Level.sav").write_bytes(b"level")
    backup = tmp_path / "backup" / "world"
    backup.mkdir(parents=True)
    (backup / "Level.sav").write_bytes(b"historical")
    adapter_snapshot = StorageSnapshot(
        files=tuple(
            item
            for item in snapshot_tree(tmp_path).files
            if not item.relative_path.as_posix().startswith("backup/")
        )
    )
    session = SimpleNamespace(
        platform=SavePlatform.STEAM,
        workspace=tmp_path,
        opened_save=SimpleNamespace(snapshot=adapter_snapshot),
    )

    migration_snapshot = SaveMigration._snapshot_for_migration(session)
    target_snapshot = SaveMigration._snapshot_for_target(session)

    assert set(migration_snapshot.by_path()) == {"Level.sav"}
    assert target_snapshot == migration_snapshot
