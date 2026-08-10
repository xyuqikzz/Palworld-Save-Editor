from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.storage.discovery import XgpSourceCatalog, split_container_name
from tests.wgs_fixture import make_user_directory


def test_current_palworld_level_container_name_maps_to_level_sav() -> None:
    world_id = "A" * 32

    mapping = split_container_name(f"{world_id}-Level-01")

    assert mapping is not None
    assert mapping[0] == world_id
    assert mapping[1].as_posix() == "Level.sav"


def test_slot_variants_have_distinct_redacted_display_names() -> None:
    with TemporaryDirectory() as temp:
        root = Path(temp) / "wgs"
        root.mkdir()
        world_id = "D" * 32
        make_user_directory(
            root,
            "7777777777777777_" + "E" * 32,
            {
                world_id: {"Level.sav": b"main"},
                f"{world_id}-Slot1": {"Level.sav": b"slot-one"},
                f"{world_id}-Slot2": {"Level.sav": b"slot-two"},
            },
        )

        sources = XgpSourceCatalog(roots=(root,)).discover()

        assert len({source.display_name for source in sources}) == 3
        assert any(source.display_name.endswith("Slot 1") for source in sources)
        assert any(source.display_name.endswith("Slot 2") for source in sources)


def test_discovery_returns_every_user_and_world_but_skips_t_and_backups() -> None:
    with TemporaryDirectory() as temp:
        root = Path(temp) / "wgs"
        root.mkdir()
        make_user_directory(
            root,
            "1111111111111111_" + "A" * 32,
            {
                "A" * 32: {"Level.sav": b"world-a"},
                "B" * 32: {"Level.sav": b"world-b"},
            },
        )
        make_user_directory(
            root,
            "2222222222222222_" + "B" * 32,
            {"C" * 32: {"Level.sav": b"world-c"}},
        )
        (root / "t").mkdir()
        (root / "manual.backup.20260720").mkdir()

        catalog = XgpSourceCatalog(roots=(root,))
        first = catalog.discover()
        second = catalog.discover()

        assert [source.world_id for source in first] == ["A" * 32, "B" * 32, "C" * 32]
        assert [source.source_id for source in first] == [source.source_id for source in second]
        assert len({source.source_id for source in first}) == 3
        public = [source.to_public_dict() for source in first]
        assert all("canonical" not in str(item).lower() for item in public)
        assert all("1111111111111111" not in str(item) for item in public)
        assert all(item["platform"] == "xgp" for item in public)


def test_selected_wgs_folder_limits_discovery_to_the_user_chosen_scope() -> None:
    with TemporaryDirectory() as temp:
        root = Path(temp) / "wgs"
        root.mkdir()
        first_user = make_user_directory(
            root,
            "3333333333333333_" + "C" * 32,
            {"D" * 32: {"Level.sav": b"world-d"}},
        )
        make_user_directory(
            root,
            "4444444444444444_" + "D" * 32,
            {"E" * 32: {"Level.sav": b"world-e"}},
        )

        catalog = XgpSourceCatalog(roots=())
        selected_user_sources = catalog.discover_selected(first_user)
        assert [source.world_id for source in selected_user_sources] == ["D" * 32]
        assert (
            catalog.resolve(selected_user_sources[0].source_id).canonical_path
            == first_user.resolve()
        )

        selected_root_sources = catalog.discover_selected(root)
        assert [source.world_id for source in selected_root_sources] == [
            "D" * 32,
            "E" * 32,
        ]


def test_selected_containers_index_discovers_its_wgs_user_scope() -> None:
    with TemporaryDirectory() as temp:
        root = Path(temp) / "wgs"
        root.mkdir()
        user = make_user_directory(
            root,
            "5555555555555555_" + "E" * 32,
            {"F" * 32: {"Level.sav": b"world-f"}},
        )

        sources = XgpSourceCatalog(roots=()).discover_selected(
            user / "containers.index"
        )

        assert [source.world_id for source in sources] == ["F" * 32]
        assert sources[0].canonical_path == user.resolve()


def test_selected_nested_wgs_container_folder_discovers_its_user_scope() -> None:
    with TemporaryDirectory() as temp:
        root = Path(temp) / "wgs"
        root.mkdir()
        user = make_user_directory(
            root,
            "6666666666666666_" + "F" * 32,
            {"A" * 32: {"Level.sav": b"world-a"}},
        )
        nested_container = next(
            path
            for path in user.iterdir()
            if path.is_dir() and (path / "container.1").is_file()
        )

        sources = XgpSourceCatalog(roots=()).discover_selected(nested_container)

        assert [source.world_id for source in sources] == ["A" * 32]
        assert sources[0].canonical_path == user.resolve()


def test_selected_folder_under_excluded_wgs_directory_is_rejected() -> None:
    with TemporaryDirectory() as temp:
        root = Path(temp) / "wgs"
        root.mkdir()
        user = make_user_directory(
            root,
            "7777777777777777_" + "A" * 32,
            {"B" * 32: {"Level.sav": b"world-b"}},
        )
        excluded_child = user / "t" / "nested"
        excluded_child.mkdir(parents=True)

        catalog = XgpSourceCatalog(roots=())
        with pytest.raises(DomainError) as captured:
            catalog.discover_selected(excluded_child)

        assert captured.value.code == "WGS_NOT_FOUND"


def test_selected_folder_without_wgs_slots_is_rejected() -> None:
    with TemporaryDirectory() as temp:
        wrong_folder = Path(temp) / "not-a-wgs-save"
        wrong_folder.mkdir()

        catalog = XgpSourceCatalog(roots=())
        with pytest.raises(DomainError) as captured:
            catalog.discover_selected(wrong_folder)

        assert captured.value.code == "WGS_NOT_FOUND"
