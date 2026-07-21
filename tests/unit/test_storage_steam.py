from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from palworld_pal_editor.domain.models import SavePlatform, SaveSource
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
