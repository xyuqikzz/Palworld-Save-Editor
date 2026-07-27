from __future__ import annotations

from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

from palworld_pal_editor.domain.models import SavePlatform, SaveSource
from palworld_pal_editor.storage import steam
from palworld_pal_editor.storage.steam import SteamDirectoryAdapter


def test_steam_adapter_opens_existing_directory_as_logical_workspace() -> None:
    with TemporaryDirectory() as temp:
        root = Path(temp) / "world"
        players = root / "Players"
        players.mkdir(parents=True)
        (root / "Level.sav").write_bytes(b"level")
        (players / f"{'A' * 32}.sav").write_bytes(b"player")
        source = SaveSource(
            platform=SavePlatform.STEAM,
            canonical_path=root.resolve(),
            source_id="steam-test",
            display_name="Steam test world",
        )

        opened = SteamDirectoryAdapter().open(source)

        assert opened.workspace == root.resolve()
        assert opened.cleanup_required is False
        assert set(opened.logical_files) == {"Level.sav", f"Players/{'A' * 32}.sav"}
        assert opened.logical_files["Level.sav"].sha256

        SteamDirectoryAdapter().close(opened)
        assert root.is_dir()


def test_steam_adapter_ignores_backup_saves_and_hashes_active_saves_once(
    monkeypatch,
) -> None:
    with TemporaryDirectory() as temp:
        root = Path(temp) / "world"
        players = root / "Players"
        players.mkdir(parents=True)
        (root / "Level.sav").write_bytes(b"level")
        player_name = f"{'A' * 32}.sav"
        (players / player_name).write_bytes(b"player")
        backup = root / "BaCkUp"
        (backup / "Players").mkdir(parents=True)
        (backup / "Level.sav").write_bytes(b"old-level")
        (backup / "Players" / player_name).write_bytes(b"old-player")
        source = SaveSource(
            platform=SavePlatform.STEAM,
            canonical_path=root.resolve(),
            source_id="steam-test",
            display_name="Steam test world",
        )
        hashed_paths: list[str] = []
        original_sha256_file = steam.sha256_file
        resolved_root = root.resolve()

        def record_sha256(path: Path) -> str:
            hashed_paths.append(path.relative_to(resolved_root).as_posix())
            return original_sha256_file(path)

        monkeypatch.setattr(steam, "sha256_file", record_sha256)

        opened = SteamDirectoryAdapter().open(source)

        expected_paths = {"Level.sav", f"Players/{player_name}"}
        assert set(opened.logical_files) == expected_paths
        assert set(opened.snapshot.by_path()) == expected_paths
        assert Counter(hashed_paths) == Counter(
            {relative_path: 1 for relative_path in expected_paths}
        )
