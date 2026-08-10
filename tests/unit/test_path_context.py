from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path

from palworld_pal_editor.utils.util import (
    get_filesystem_root_context,
    get_path_context,
)


def test_path_context_uses_level_save_time_for_palworld_directories(
    tmp_path: Path,
) -> None:
    world = tmp_path / "WORLD_A"
    players = world / "Players"
    players.mkdir(parents=True)
    level = world / "Level.sav"
    level.write_bytes(b"level")
    os.utime(world, (1_700_000_000, 1_700_000_000))
    os.utime(level, (1_800_000_000, 1_800_000_000))

    context = get_path_context(tmp_path)
    entry = context["children"][str(world.resolve())]

    assert entry["isDir"] is True
    assert entry["isPalDir"] is True
    assert entry["modifiedAt"] == datetime.fromtimestamp(
        1_800_000_000, timezone.utc
    ).isoformat()
    assert context["isRootView"] is False


def test_filesystem_root_context_returns_navigable_roots() -> None:
    context = get_filesystem_root_context()

    assert context["currentPath"] == ""
    assert context["isPalDir"] is False
    assert context["isRootView"] is True
    assert context["children"]
    assert all(entry["isDir"] for entry in context["children"].values())
    assert all(entry["isRoot"] for entry in context["children"].values())
    assert all(entry["modifiedAt"] is None for entry in context["children"].values())
