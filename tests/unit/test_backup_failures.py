from __future__ import annotations

import errno
import json
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

import pytest

from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.domain.models import StorageCommitRequest
from palworld_pal_editor.storage import steam as steam_module
from palworld_pal_editor.storage import xgp as xgp_module
from palworld_pal_editor.storage.discovery import XgpSourceCatalog
from palworld_pal_editor.storage.steam import (
    SteamDirectoryAdapter,
    make_steam_source,
    sha256_file,
    snapshot_tree,
)
from palworld_pal_editor.storage.xgp import XgpWgsAdapter
from tests.wgs_fixture import make_user_directory


@pytest.fixture
def backup_test_root():
    with TemporaryDirectory(prefix="pwe-backup-test-") as temp:
        yield Path(temp)


def _steam_case(base: Path):
    source_root = base / "steam-world"
    (source_root / "Players").mkdir(parents=True)
    (source_root / "Level.sav").write_bytes(b"steam-before")
    (source_root / "WorldOption.sav").write_bytes(b"steam-options")
    (source_root / "OpaqueFuture.bin").write_bytes(b"opaque-future-data")
    adapter = SteamDirectoryAdapter()
    opened = adapter.open(make_steam_source(source_root))
    stage = base / "steam-stage"
    stage.mkdir()
    (stage / "Level.sav").write_bytes(b"steam-after")
    return (
        adapter,
        StorageCommitRequest(
            opened=opened,
            staged_workspace=stage,
            changed_files=(PurePosixPath("Level.sav"),),
            expected_revision=1,
            verify_file=lambda _path, _relative: None,
        ),
        source_root,
        source_root / "Level.sav",
    )


def _wgs_case(base: Path):
    wgs_root = base / "wgs"
    wgs_root.mkdir()
    user_root = make_user_directory(
        wgs_root,
        "1111111111111111_" + "A" * 32,
        {"B" * 32: {"Level.sav": b"wgs-before"}},
    )
    catalog = XgpSourceCatalog(roots=(wgs_root,))
    adapter = XgpWgsAdapter(
        catalog=catalog,
        process_checker=lambda: False,
        workspace_validator=lambda _path: None,
        workspace_root=base / "wgs-workspaces",
        backup_root=base / "wgs-backups",
        stability_delay=0,
    )
    opened = adapter.open(catalog.discover()[0])
    stage = base / "wgs-stage"
    stage.mkdir()
    (stage / "Level.sav").write_bytes(b"wgs-after")
    target = user_root / Path(
        str(opened.storage_metadata["bindings"]["Level.sav"]["payload_relative"])
    )
    return (
        adapter,
        StorageCommitRequest(
            opened=opened,
            staged_workspace=stage,
            changed_files=(PurePosixPath("Level.sav"),),
            expected_revision=1,
            verify_file=lambda _path, _relative: None,
        ),
        user_root,
        target,
    )


def _case(base: Path, platform: str):
    return _steam_case(base) if platform == "steam" else _wgs_case(base)


def _assert_backup_diagnostics(
    error: DomainError,
    *,
    code: str,
    phase: str,
    failed_file: str | None,
    category: str,
    os_error_code: int | None,
) -> None:
    assert error.code == code
    assert error.retryable is True
    assert set(error.details) == {
        "backup_path",
        "phase",
        "failed_file",
        "os_error_code",
        "os_error_category",
        "retryable",
    }
    assert error.details["backup_path"]
    assert error.details["phase"] == phase
    assert error.details["failed_file"] == failed_file
    assert error.details["os_error_code"] == os_error_code
    assert error.details["os_error_category"] == category
    assert error.details["retryable"] is True


def test_steam_backup_covers_complete_source_and_reloads_verified_manifest(
    backup_test_root: Path,
) -> None:
    adapter, request, source_root, _target = _steam_case(backup_test_root)
    before = snapshot_tree(source_root)

    result = adapter.commit(request)

    assert result.backup_path is not None
    manifest_path = result.backup_path / "manifest.json"
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = before.by_path()
    assert {item["path"] for item in document["files"]} == set(expected)
    for relative, snapshot in expected.items():
        backup_file = result.backup_path / "files" / Path(relative)
        assert backup_file.stat().st_size == snapshot.size
        assert sha256_file(backup_file) == snapshot.sha256


@pytest.mark.parametrize(
    "backup_directory_name",
    [
        "Palworld-Pal-Editor-Backup",
        ".Palworld-Pal-Editor-Backup",
    ],
)
def test_steam_backup_excludes_editor_backup_directories(
    backup_test_root: Path,
    backup_directory_name: str,
) -> None:
    source_root = backup_test_root / "steam-world"
    source_root.mkdir()
    (source_root / "Level.sav").write_bytes(b"steam-before")
    legacy_backup = (
        source_root
        / backup_directory_name
        / "2025-04-25_14-02-19"
        / "Players"
    )
    legacy_backup.mkdir(parents=True)
    (legacy_backup / f"{'A' * 32}.sav").write_bytes(b"old-player")
    adapter = SteamDirectoryAdapter()
    opened = adapter.open(make_steam_source(source_root))
    stage = backup_test_root / "steam-stage"
    stage.mkdir()
    (stage / "Level.sav").write_bytes(b"steam-after")
    request = StorageCommitRequest(
        opened=opened,
        staged_workspace=stage,
        changed_files=(PurePosixPath("Level.sav"),),
        expected_revision=1,
        verify_file=lambda _path, _relative: None,
    )

    result = adapter.commit(request)

    assert {item["path"] for item in result.manifest} == {"Level.sav"}
    assert (source_root / "Level.sav").read_bytes() == b"steam-after"


@pytest.mark.parametrize(
    ("platform", "expected_code"),
    [("steam", "BACKUP_FAILED"), ("wgs", "WGS_BACKUP_FAILED")],
)
def test_backup_directory_creation_failure_is_diagnostic_and_precommit(
    backup_test_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
    expected_code: str,
) -> None:
    adapter, request, source_root, _target = _case(backup_test_root, platform)
    before = snapshot_tree(source_root)
    original_mkdir = Path.mkdir

    def fail_backup_files_mkdir(path: Path, *args, **kwargs):
        if path.name == "files":
            raise PermissionError(errno.EACCES, "injected directory denial")
        return original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fail_backup_files_mkdir)

    with pytest.raises(DomainError) as raised:
        adapter.commit(request)

    _assert_backup_diagnostics(
        raised.value,
        code=expected_code,
        phase="create_backup_directory",
        failed_file=None,
        category="permission",
        os_error_code=errno.EACCES,
    )
    assert snapshot_tree(source_root) == before


@pytest.mark.parametrize(
    ("injected_errno", "category"),
    [
        (errno.ENOSPC, "disk_space"),
        (errno.EACCES, "permission"),
        (errno.EBUSY, "file_busy"),
    ],
)
@pytest.mark.parametrize(
    ("platform", "expected_code"),
    [("steam", "BACKUP_FAILED"), ("wgs", "WGS_BACKUP_FAILED")],
)
def test_copy2_os_errors_are_diagnostic_and_never_write_the_target(
    backup_test_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
    expected_code: str,
    injected_errno: int,
    category: str,
) -> None:
    adapter, request, source_root, _target = _case(backup_test_root, platform)
    before = snapshot_tree(source_root)
    module = steam_module if platform == "steam" else xgp_module

    def fail_copy(_source, _destination, *args, **kwargs):
        raise OSError(injected_errno, "injected copy failure")

    monkeypatch.setattr(module.shutil, "copy2", fail_copy)

    with pytest.raises(DomainError) as raised:
        adapter.commit(request)

    _assert_backup_diagnostics(
        raised.value,
        code=expected_code,
        phase="copy_file",
        failed_file=raised.value.details["failed_file"],
        category=category,
        os_error_code=injected_errno,
    )
    assert raised.value.details["failed_file"]
    assert snapshot_tree(source_root) == before


@pytest.mark.parametrize(
    ("platform", "expected_code"),
    [("steam", "BACKUP_FAILED"), ("wgs", "WGS_BACKUP_FAILED")],
)
def test_copy_hash_mismatch_is_diagnostic_and_never_writes_the_target(
    backup_test_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
    expected_code: str,
) -> None:
    adapter, request, source_root, _target = _case(backup_test_root, platform)
    before = snapshot_tree(source_root)
    module = steam_module if platform == "steam" else xgp_module
    original_copy2 = module.shutil.copy2

    def corrupt_copy(source, destination, *args, **kwargs):
        result = original_copy2(source, destination, *args, **kwargs)
        Path(destination).write_bytes(b"corrupted-backup")
        return result

    monkeypatch.setattr(module.shutil, "copy2", corrupt_copy)

    with pytest.raises(DomainError) as raised:
        adapter.commit(request)

    _assert_backup_diagnostics(
        raised.value,
        code=expected_code,
        phase="verify_copy",
        failed_file=raised.value.details["failed_file"],
        category="verification",
        os_error_code=None,
    )
    assert raised.value.details["failed_file"]
    assert snapshot_tree(source_root) == before


@pytest.mark.parametrize(
    ("mode", "injected_errno", "phase", "category"),
    [
        ("write", errno.ENOSPC, "write_manifest", "disk_space"),
        ("read", errno.EACCES, "read_manifest", "permission"),
    ],
)
@pytest.mark.parametrize(
    ("platform", "expected_code"),
    [("steam", "BACKUP_FAILED"), ("wgs", "WGS_BACKUP_FAILED")],
)
def test_manifest_write_or_reload_failure_is_precommit_and_preserves_backup(
    backup_test_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
    expected_code: str,
    mode: str,
    injected_errno: int,
    phase: str,
    category: str,
) -> None:
    adapter, request, source_root, _target = _case(backup_test_root, platform)
    before = snapshot_tree(source_root)
    original_open = Path.open

    def fail_manifest_open(path: Path, *args, **kwargs):
        open_mode = args[0] if args else kwargs.get("mode", "r")
        is_manifest = "manifest.json" in path.name
        if is_manifest and (
            (mode == "write" and "w" in open_mode)
            or (mode == "read" and "r" in open_mode)
        ):
            raise OSError(injected_errno, f"injected manifest {mode} failure")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_manifest_open)

    with pytest.raises(DomainError) as raised:
        adapter.commit(request)

    _assert_backup_diagnostics(
        raised.value,
        code=expected_code,
        phase=phase,
        failed_file="manifest.json",
        category=category,
        os_error_code=injected_errno,
    )
    assert Path(raised.value.details["backup_path"]).is_dir()
    assert snapshot_tree(source_root) == before


@pytest.mark.parametrize(
    "mutation",
    ["change", "disappear", "missing_during_copy"],
)
@pytest.mark.parametrize(
    ("platform", "expected_code"),
    [("steam", "SAVE_TARGET_CHANGED"), ("wgs", "WGS_SOURCE_CHANGED")],
)
def test_source_mutation_during_backup_is_classified_before_target_write(
    backup_test_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
    expected_code: str,
    mutation: str,
) -> None:
    adapter, request, _source_root, target = _case(
        backup_test_root, platform
    )
    module = steam_module if platform == "steam" else xgp_module
    original_copy2 = module.shutil.copy2
    mutated = False

    def mutate_after_copy(source, destination, *args, **kwargs):
        nonlocal mutated
        if not mutated and mutation == "missing_during_copy":
            mutated = True
            Path(source).unlink()
            raise FileNotFoundError(
                errno.ENOENT,
                "source disappeared during copy",
            )
        result = original_copy2(source, destination, *args, **kwargs)
        if not mutated:
            mutated = True
            if mutation == "change":
                Path(source).write_bytes(b"external-source-change")
            else:
                Path(source).unlink()
        return result

    monkeypatch.setattr(module.shutil, "copy2", mutate_after_copy)

    with pytest.raises(DomainError) as raised:
        adapter.commit(request)

    assert raised.value.code == expected_code
    assert raised.value.retryable is True
    assert raised.value.details["phase"] == "verify_source_after_backup"
    assert raised.value.details["failed_file"]
    assert raised.value.details["os_error_category"] == "source_changed"
    assert not target.exists() or target.read_bytes() not in {
        b"steam-after",
        b"wgs-after",
    }
