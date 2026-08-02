from __future__ import annotations

import contextlib
from copy import deepcopy
from dataclasses import replace
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import re
import shutil
import tempfile
import unittest

from palworld_pal_editor.application.character_editor import CharacterEditor
from palworld_pal_editor.application.dynamic_attribute_editor import DynamicAttributeEditor
from palworld_pal_editor.application.inventory_editor import InventoryEditor
from palworld_pal_editor.application.inventory_layout_editor import InventoryLayoutEditor
from palworld_pal_editor.application.mission_editor import MissionEditor
from palworld_pal_editor.application.preset_service import PresetService
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.application.save_writer import SaveWriter
from palworld_pal_editor.application.structural_pal_editor import StructuralPalEditor
from palworld_pal_editor.config import Config
from palworld_pal_editor.core.character_index import CharacterIndex
from palworld_pal_editor.core.save_manager import SaveManager
from palworld_pal_editor.domain.commands import (
    AddPal,
    ClearItemSlot,
    ClonePal,
    DeletePal,
    FillItemSlots,
    HealAllPals,
    MovePal,
    PutItem,
    RecoverDetachedPal,
    SortItemContainer,
    UpdateDynamicItemAttributes,
    UpdateItemCount,
    UpdatePlayerIdentity,
    UpdatePlayerProgression,
    UpdatePlayerTechnology,
    UpdatePlayerMissions,
)
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.domain.item_catalog import ItemCatalog
from palworld_pal_editor.domain.models import (
    CharacterContainerType,
    INVENTORY_CONTAINER_FIELDS,
    ItemContainerType,
)
from palworld_pal_editor.utils.data_provider import DataProvider


REQUIRED_FIELDS = frozenset(
    {
        "fixture_id",
        "relative_path",
        "game_version",
        "save_version",
        "platform",
        "sha256",
        "contains_player_files",
        "inventory_aliases",
        "dynamic_item_kinds",
        "provenance",
        "expected_capabilities",
        "expected_invariant_exceptions",
    }
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _save_hashes(root: Path) -> dict[str, str]:
    paths = list(root.glob("*.sav"))
    players = root / "Players"
    if players.is_dir():
        paths.extend(players.glob("*.sav"))
    return {
        path.relative_to(root).as_posix(): _sha256(path)
        for path in sorted(paths)
        if path.is_file()
    }


class RealSaveRoundTripTests(unittest.TestCase):
    """Strict real-save gates; absence of fixtures is an explicit non-pass."""

    fixture_root: Path
    fixtures: list[dict]

    @classmethod
    def setUpClass(cls) -> None:
        configured = os.environ.get("PALWORLD_EDITOR_REAL_FIXTURES")
        if not configured:
            raise unittest.SkipTest(
                "PALWORLD_EDITOR_REAL_FIXTURES is unset; this skip is not a "
                "passing real-save round-trip gate."
            )
        cls.fixture_root = Path(configured).resolve()
        manifest_path = cls.fixture_root / "manifest.local.json"
        if not manifest_path.is_file():
            raise AssertionError(f"Missing real fixture manifest: {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("schema_version") != 1:
            raise AssertionError("Real fixture manifest schema_version must be 1")
        fixtures = manifest.get("fixtures")
        if not isinstance(fixtures, list) or not fixtures:
            raise AssertionError("Real fixture manifest must contain at least one fixture")
        seen_ids: set[str] = set()
        for fixture in fixtures:
            cls._validate_manifest_entry(fixture, seen_ids)
        cls.fixtures = fixtures

    def setUp(self) -> None:
        self._logging_disable = logging.root.manager.disable
        logging.disable(logging.CRITICAL)

    def tearDown(self) -> None:
        logging.disable(self._logging_disable)

    @classmethod
    def _validate_manifest_entry(
        cls, fixture: object, seen_ids: set[str]
    ) -> None:
        if not isinstance(fixture, dict):
            raise AssertionError("Every real fixture entry must be an object")
        missing = REQUIRED_FIELDS - fixture.keys()
        if missing:
            raise AssertionError(f"Real fixture entry is missing: {sorted(missing)}")
        fixture_id = fixture["fixture_id"]
        if not isinstance(fixture_id, str) or not fixture_id or fixture_id in seen_ids:
            raise AssertionError("fixture_id must be non-empty and unique")
        seen_ids.add(fixture_id)
        source = (cls.fixture_root / str(fixture["relative_path"])).resolve()
        if not _is_within(source, cls.fixture_root) or not source.is_dir():
            raise AssertionError(f"Unsafe or missing fixture path: {fixture_id}")
        for key in ("game_version", "save_version", "platform"):
            if not isinstance(fixture[key], str) or not fixture[key]:
                raise AssertionError(f"{fixture_id}: {key} must be non-empty")
        for key in (
            "inventory_aliases",
            "dynamic_item_kinds",
            "expected_invariant_exceptions",
        ):
            if not isinstance(fixture[key], list):
                raise AssertionError(f"{fixture_id}: {key} must be an array")
        if not isinstance(fixture["expected_capabilities"], dict):
            raise AssertionError(f"{fixture_id}: expected_capabilities must be an object")
        candidates = fixture.get("dynamic_attribute_candidates", [])
        if not isinstance(candidates, list) or any(
            not isinstance(value, str) or not value for value in candidates
        ):
            raise AssertionError(
                f"{fixture_id}: dynamic_attribute_candidates must be a string array"
            )
        if not fixture["provenance"]:
            raise AssertionError(f"{fixture_id}: provenance must be documented")
        cls._validate_source_hashes(fixture)

    @classmethod
    def _source_path(cls, fixture: dict) -> Path:
        source = (cls.fixture_root / fixture["relative_path"]).resolve()
        if not _is_within(source, cls.fixture_root):
            raise AssertionError("Fixture path escaped the configured root")
        return source

    @classmethod
    def _validate_source_hashes(cls, fixture: dict) -> dict[str, str]:
        source = cls._source_path(fixture)
        expected = fixture["sha256"]
        if not isinstance(expected, dict) or not expected:
            raise AssertionError(f"{fixture['fixture_id']}: sha256 must be an object")
        normalized = {str(path): str(value).lower() for path, value in expected.items()}
        for relative_path, digest in normalized.items():
            resolved = (source / Path(relative_path)).resolve()
            if not _is_within(resolved, source) or not SHA256_PATTERN.fullmatch(digest):
                raise AssertionError(
                    f"{fixture['fixture_id']}: unsafe path or invalid SHA-256"
                )
        actual = _save_hashes(source)
        if set(actual) != set(normalized):
            raise AssertionError(
                f"{fixture['fixture_id']}: manifest must hash every included .sav"
            )
        if actual != normalized:
            raise AssertionError(f"{fixture['fixture_id']}: source hash mismatch")
        has_players = any(path.startswith("Players/") for path in actual)
        if bool(fixture["contains_player_files"]) != has_players:
            raise AssertionError(
                f"{fixture['fixture_id']}: contains_player_files is inaccurate"
            )
        if "Level.sav" not in actual:
            raise AssertionError(f"{fixture['fixture_id']}: Level.sav is required")
        return actual

    @staticmethod
    def _capable(fixture: dict, name: str) -> bool:
        return fixture["expected_capabilities"].get(name) is True

    @contextlib.contextmanager
    def _quiet(self):
        with (
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            yield

    def _copy_fixture(self, fixture: dict, destination: Path) -> tuple[Path, dict[str, str]]:
        source_hashes = self._validate_source_hashes(fixture)
        source = self._source_path(fixture)
        shutil.copytree(
            source,
            destination,
            ignore=shutil.ignore_patterns(
                ".pwe-backup",
                ".Palworld-Pal-Editor-Backup",
                "Palworld-Pal-Editor-Backup",
                "backup",
            ),
        )
        self.assertEqual(source_hashes, _save_hashes(destination))
        return destination, source_hashes

    def _assert_source_unchanged(
        self, fixture: dict, source_hashes: dict[str, str]
    ) -> None:
        self.assertEqual(source_hashes, self._validate_source_hashes(fixture))

    @staticmethod
    def _open(path: Path) -> SaveSession:
        return SaveSession.open(path, manager=SaveManager.create_isolated())

    def _assert_new_slot_metadata(self, raw: dict) -> None:
        self.assertEqual([], raw["permission"]["type_a"])
        self.assertEqual([], raw["permission"]["type_b"])
        self.assertEqual([], raw["permission"]["item_static_ids"])
        self.assertEqual(0.0, raw["corruption_progress_value"])
        self.assertEqual([0, 0, 0, 0], raw["trailing_bytes"])

    def _select_item_transfer(
        self,
        source: SaveSession,
        target: SaveSession,
        wanted_kind: str,
        *,
        different_player: bool = False,
        single_reference: bool = False,
    ) -> dict:
        catalog = ItemCatalog.load_default()
        source_players = []
        target_players = []
        for session, output in (
            (source, source_players),
            (target, target_players),
        ):
            for player_id in session.manager.player_mapping:
                player = session.load_player(player_id)
                ids = player.resolve_item_container_ids()
                output.append(
                    (
                        str(player_id),
                        [
                            (
                                container_type,
                                session.manager.item_container_data.get(ids.get(field)),
                            )
                            for container_type, field in INVENTORY_CONTAINER_FIELDS.items()
                        ],
                    )
                )

        for source_player_id, source_containers in source_players:
            for source_type, source_container in source_containers:
                if source_container is None:
                    continue
                for source_slot in source_container.iter_occupied_slots():
                    record = (
                        source.manager.dynamic_item_data.get(
                            source_slot.dynamic_local_id
                        )
                        if source_slot.dynamic_id is not None
                        else None
                    )
                    kind = record.kind if record is not None else "none"
                    if (
                        (wanted_kind == "none" and kind != "none")
                        or (wanted_kind == "egg" and kind != "egg")
                        or (
                            wanted_kind == "dynamic"
                            and kind in {"none", "egg"}
                        )
                        or (
                            wanted_kind not in {"none", "egg", "dynamic"}
                            and kind != wanted_kind
                        )
                    ):
                        continue
                    if record is not None:
                        try:
                            source.manager.dynamic_item_data.require_transferable_record(
                                record
                            )
                        except DomainError:
                            continue
                        if single_reference and len(
                            source.manager.dynamic_item_data.references.get(
                                record.local_id, []
                            )
                        ) != 1:
                            continue
                    for target_player_id, target_containers in target_players:
                        if different_player and target_player_id == source_player_id:
                            continue
                        for target_type, target_container in target_containers:
                            if target_container is None:
                                continue
                            encoded = {
                                slot.slot_index
                                for slot in target_container.iter_encoded_slots()
                            }
                            for target_index in range(target_container.capacity):
                                if target_index in encoded:
                                    continue
                                if (
                                    source is target
                                    and source_container is target_container
                                    and source_slot.slot_index == target_index
                                ):
                                    continue
                                try:
                                    catalog.validate_placement(
                                        source_slot.static_id,
                                        target_type,
                                        target_index,
                                        source_slot.count,
                                    )
                                except DomainError:
                                    continue
                                return {
                                    "source_player_id": source_player_id,
                                    "source_type": source_type,
                                    "source_container_id": str(source_container.id),
                                    "source_slot_index": source_slot.slot_index,
                                    "static_id": source_slot.static_id,
                                    "count": source_slot.count,
                                    "kind": kind,
                                    "source_local_id": (
                                        record.local_id if record is not None else None
                                    ),
                                    "source_record": (
                                        deepcopy(record.raw_data)
                                        if record is not None
                                        else None
                                    ),
                                    "target_player_id": target_player_id,
                                    "target_type": target_type,
                                    "target_container_id": str(target_container.id),
                                    "target_slot_index": target_index,
                                }
        self.fail(f"No real {wanted_kind} item transfer candidate")

    def _assert_cloned_dynamic_payload(
        self, source_raw: dict, target_raw: dict
    ) -> None:
        normalized = deepcopy(target_raw)
        normalized["id"]["created_world_id"] = source_raw["id"][
            "created_world_id"
        ]
        normalized["id"]["local_id_in_created_world"] = source_raw["id"][
            "local_id_in_created_world"
        ]
        self.assertEqual(source_raw, normalized)

    def test_real_save_read_lazy_inventory_and_invariants(self) -> None:
        exercised = 0
        for fixture in self.fixtures:
            if not self._capable(fixture, "read"):
                continue
            exercised += 1
            with self.subTest(fixture=fixture["fixture_id"]):
                source_hashes = self._validate_source_hashes(fixture)
                with self._quiet():
                    session = self._open(self._source_path(fixture))
                    self.assertEqual(0, session.manager.player_file_load_count)
                    catalog = ItemCatalog.load_default()
                    editor = InventoryEditor(session, catalog)
                    observed_aliases: set[str] = set()
                    for player_id in session.manager.player_mapping:
                        player = session.load_player(player_id)
                        if "InventoryInfo" in player._player_save_data:
                            observed_aliases.add("InventoryInfo")
                        if "inventoryInfo" in player._player_save_data:
                            observed_aliases.add("inventoryInfo")
                        inventory = editor.get_inventory(str(player_id)).to_dict()
                        self.assertEqual(5, len(inventory["containers"]))
                        for container in inventory["containers"]:
                            self.assertEqual("available", container["status"])
                            self.assertEqual(
                                container["capacity"], len(container["slots"])
                            )
                    issue_codes = [
                        issue.code for issue in session.manager.dynamic_item_data.issues()
                    ] + [
                        issue.code for issue in CharacterIndex(session.manager).hard_issues()
                    ]
                    observed_dynamic_kinds = {
                        record.kind
                        for record in session.manager.dynamic_item_data.records.values()
                    }
                    if self._capable(
                        fixture, "container_dynamic_reference_layout"
                    ):
                        self.assertTrue(
                            session.manager.item_container_data.dynamic_reference_layout_complete
                        )
                        world = session.manager.gvas_file.properties[
                            "worldSaveData"
                        ]["value"]
                        raw_containers = world["ItemContainerSaveData"]["value"]
                        self.assertTrue(raw_containers)
                        for raw_container in raw_containers:
                            raw = raw_container["value"]["RawData"]["value"]
                            self.assertIn("item_categories", raw["permission"])
                            self.assertIn("used_dynamic_item_ids", raw)
                            self.assertNotIn("trailing_unparsed_data", raw)
                self.assertGreater(session.manager.player_file_load_count, 0)
                self.assertEqual(
                    sorted(fixture["expected_invariant_exceptions"]),
                    sorted(issue_codes),
                )
                self.assertEqual(
                    set(fixture["inventory_aliases"]), observed_aliases
                )
                self.assertEqual(
                    set(fixture["dynamic_item_kinds"]), observed_dynamic_kinds
                )
                self._assert_source_unchanged(fixture, source_hashes)
        self.assertGreater(exercised, 0, "No fixture enables the read capability")

    def test_real_save_item_count_decrease_roundtrip(self) -> None:
        exercised = 0
        for fixture in self.fixtures:
            if not self._capable(fixture, "inventory_decrease_roundtrip"):
                continue
            exercised += 1
            with self.subTest(fixture=fixture["fixture_id"]), tempfile.TemporaryDirectory(
                prefix="pal-editor-real-item-"
            ) as temp_name:
                work, source_hashes = self._copy_fixture(
                    fixture, Path(temp_name) / fixture["fixture_id"]
                )
                before = _save_hashes(work)
                with self._quiet():
                    session = self._open(work)
                    candidates = []
                    for player_id in session.manager.player_mapping:
                        player = session.load_player(player_id)
                        ids = player.resolve_item_container_ids()
                        for container_type, field in INVENTORY_CONTAINER_FIELDS.items():
                            container_id = ids.get(field)
                            container = session.manager.item_container_data.get(container_id)
                            if container is None:
                                continue
                            for slot in container.iter_occupied_slots():
                                if slot.dynamic_id is None and slot.count > 1:
                                    candidates.append(
                                        (
                                            slot.count,
                                            str(player_id),
                                            container_type,
                                            str(container_id),
                                            slot.slot_index,
                                            slot.static_id,
                                            list(slot._raw_data.get("trailing_bytes", [])),
                                        )
                                    )
                    self.assertTrue(candidates, "No safe real stack candidate")
                    (
                        old_count,
                        player_id,
                        container_type,
                        container_id,
                        slot_index,
                        static_id,
                        old_tail,
                    ) = min(candidates)
                    editor = InventoryEditor(session, ItemCatalog.load_default())
                    editor.execute(
                        UpdateItemCount(
                            session_id=session.session_id,
                            expected_revision=0,
                            player_id=player_id,
                            container_type=container_type,
                            slot_index=slot_index,
                            expected_static_id=static_id,
                            count=old_count - 1,
                        )
                    )
                    saved = SaveWriter().save(session, work, session.revision)
                    reloaded = self._open(work)
                    reloaded.load_player(player_id)
                    slot = reloaded.manager.item_container_data.get(
                        container_id
                    ).get_occupied(slot_index)
                self.assertEqual(old_count - 1, slot.count)
                self.assertEqual(static_id, slot.static_id)
                self.assertIsNone(slot.dynamic_id)
                self.assertEqual(old_tail, slot._raw_data.get("trailing_bytes", []))
                after = _save_hashes(work)
                changed = sorted(path for path in before if before[path] != after[path])
                self.assertEqual(["Level.sav"], changed)
                self.assertEqual(("Level.sav",), saved.written_files)
                backup = Path(saved.backup_path) / "files" / "Level.sav"
                self.assertEqual(before["Level.sav"], _sha256(backup))
                self.assertTrue(saved.staged_reload_verified)
                self.assertTrue(saved.target_reload_verified)
                self._assert_source_unchanged(fixture, source_hashes)
        self.assertGreater(
            exercised, 0, "No fixture enables inventory_decrease_roundtrip"
        )

    def test_real_save_sparse_inventory_put_roundtrip(self) -> None:
        exercised = 0
        for fixture in self.fixtures:
            if not self._capable(fixture, "inventory_sparse_put_roundtrip"):
                continue
            exercised += 1
            with self.subTest(fixture=fixture["fixture_id"]), tempfile.TemporaryDirectory(
                prefix="pal-editor-real-sparse-inventory-"
            ) as temp_name:
                work, source_hashes = self._copy_fixture(
                    fixture, Path(temp_name) / fixture["fixture_id"]
                )
                before = _save_hashes(work)
                with self._quiet():
                    session = self._open(work)
                    catalog = ItemCatalog.load_default()
                    selected = None
                    for player_id in session.manager.player_mapping:
                        player = session.load_player(player_id)
                        ids = player.resolve_item_container_ids()
                        for container_type, field in INVENTORY_CONTAINER_FIELDS.items():
                            container_id = ids.get(field)
                            container = session.manager.item_container_data.get(container_id)
                            if container is None:
                                continue
                            encoded = {
                                slot.slot_index for slot in container.iter_encoded_slots()
                            }
                            missing = [
                                index
                                for index in range(container.capacity)
                                if index not in encoded
                            ]
                            if not missing:
                                continue
                            for source_slot in container.iter_occupied_slots():
                                if source_slot.dynamic_id is not None:
                                    continue
                                try:
                                    rule = catalog.validate_placement(
                                        source_slot.static_id,
                                        container_type,
                                        missing[0],
                                        1,
                                    )
                                except DomainError:
                                    continue
                                if rule.dynamic_kind == "none":
                                    selected = (
                                        str(player_id),
                                        container_type,
                                        str(container_id),
                                        missing[0],
                                        source_slot.static_id,
                                    )
                                    break
                            if selected:
                                break
                        if selected:
                            break
                    self.assertIsNotNone(selected, "No writable sparse inventory slot")
                    (
                        player_id,
                        container_type,
                        container_id,
                        slot_index,
                        static_id,
                    ) = selected
                    InventoryEditor(session, catalog).execute(
                        PutItem(
                            session_id=session.session_id,
                            expected_revision=0,
                            player_id=player_id,
                            container_type=container_type,
                            slot_index=slot_index,
                            static_id=static_id,
                            count=1,
                        )
                    )
                    created = session.manager.item_container_data.get(
                        container_id
                    ).get_occupied(slot_index)
                    self._assert_new_slot_metadata(created._raw_data)
                    saved = SaveWriter().save(session, work, session.revision)
                    reloaded = self._open(work)
                    reloaded.load_player(player_id)
                    reloaded_slot = reloaded.manager.item_container_data.get(
                        container_id
                    ).get_occupied(slot_index)
                    reloaded.manager.dynamic_item_data.assert_consistent()
                self.assertEqual(static_id, reloaded_slot.static_id)
                self.assertEqual(1, reloaded_slot.count)
                self.assertIsNone(reloaded_slot.dynamic_id)
                self._assert_new_slot_metadata(reloaded_slot._raw_data)
                after = _save_hashes(work)
                changed = sorted(path for path in before if before[path] != after[path])
                self.assertEqual(["Level.sav"], changed)
                self.assertEqual(("Level.sav",), saved.written_files)
                self.assertTrue(saved.staged_reload_verified)
                self.assertTrue(saved.target_reload_verified)
                self._assert_source_unchanged(fixture, source_hashes)
        self.assertGreater(
            exercised, 0, "No fixture enables inventory_sparse_put_roundtrip"
        )

    def test_real_save_dynamic_item_construction_matrix_roundtrip(self) -> None:
        exercised = 0
        for fixture in self.fixtures:
            if not self._capable(fixture, "dynamic_item_construction_roundtrip"):
                continue
            exercised += 1
            with self.subTest(fixture=fixture["fixture_id"]), tempfile.TemporaryDirectory(
                prefix="pal-editor-real-dynamic-construct-"
            ) as temp_name:
                work, source_hashes = self._copy_fixture(
                    fixture, Path(temp_name) / fixture["fixture_id"]
                )
                before = _save_hashes(work)
                constructed = []
                with self._quiet():
                    session = self._open(work)
                    catalog = ItemCatalog.load_default()
                    editor = InventoryEditor(session, catalog)
                    for kind in ("weapon", "armor", "egg"):
                        candidate = self._select_item_transfer(
                            session, session, kind
                        )
                        source_record = candidate["source_record"]
                        if kind == "weapon":
                            dynamic_init = {
                                "record_static_id": source_record["id"]["static_id"],
                                "durability": source_record["durability"],
                                "ammo": source_record["remaining_bullets"],
                                "passive_traits": list(
                                    source_record["passive_skill_list"]
                                ),
                            }
                        elif kind == "armor":
                            dynamic_init = {
                                "record_static_id": source_record["id"]["static_id"],
                                "durability": source_record["durability"],
                            }
                        else:
                            dynamic_init = {
                                "record_static_id": source_record["id"]["static_id"],
                                "character_id": source_record["character_id"],
                            }
                        result = editor.execute(
                            PutItem(
                                session_id=session.session_id,
                                expected_revision=session.revision,
                                player_id=candidate["target_player_id"],
                                container_type=candidate["target_type"],
                                slot_index=candidate["target_slot_index"],
                                static_id=candidate["static_id"],
                                count=candidate["count"],
                                dynamic_init=dynamic_init,
                            )
                        )
                        candidate["target_local_id"] = result["slot"][
                            "dynamic_id"
                        ].rsplit("/", 1)[1]
                        candidate["dynamic_init"] = dynamic_init
                        constructed.append(candidate)
                    saved = SaveWriter().save(session, work, session.revision)
                    reloaded = self._open(work)
                    reloaded.manager.dynamic_item_data.assert_consistent()
                for candidate in constructed:
                    slot = reloaded.manager.item_container_data.get(
                        candidate["target_container_id"]
                    ).get_occupied(candidate["target_slot_index"])
                    record = reloaded.manager.dynamic_item_data.get(
                        candidate["target_local_id"]
                    )
                    self.assertEqual(candidate["static_id"], slot.static_id)
                    self.assertEqual(candidate["kind"], record.kind)
                    self.assertEqual(
                        candidate["dynamic_init"]["record_static_id"],
                        record.static_id,
                    )
                    self.assertEqual(
                        candidate["target_local_id"], slot.dynamic_local_id
                    )
                    self._assert_new_slot_metadata(slot._raw_data)
                    if candidate["kind"] in {"weapon", "armor"}:
                        self._assert_cloned_dynamic_payload(
                            candidate["source_record"], record.raw_data
                        )
                    else:
                        self.assertEqual(
                            candidate["dynamic_init"]["character_id"],
                            record.raw_data["character_id"],
                        )
                        self.assertEqual({}, record.raw_data["object"])
                        self.assertEqual([0] * 28, record.raw_data["trailing_bytes"])
                after = _save_hashes(work)
                changed = sorted(path for path in before if before[path] != after[path])
                self.assertEqual(["Level.sav"], changed)
                self.assertEqual(("Level.sav",), saved.written_files)
                self.assertTrue(saved.staged_reload_verified)
                self.assertTrue(saved.target_reload_verified)
                self._assert_source_unchanged(fixture, source_hashes)
        self.assertGreater(
            exercised, 0, "No fixture enables dynamic_item_construction_roundtrip"
        )

    def test_real_save_dynamic_equipment_preset_roundtrip(self) -> None:
        exercised = 0
        for fixture in self.fixtures:
            if not self._capable(
                fixture, "dynamic_equipment_preset_roundtrip"
            ):
                continue
            exercised += 1
            with self.subTest(fixture=fixture["fixture_id"]), tempfile.TemporaryDirectory(
                prefix="pal-editor-real-dynamic-preset-"
            ) as temp_name:
                work, source_hashes = self._copy_fixture(
                    fixture, Path(temp_name) / fixture["fixture_id"]
                )
                before = _save_hashes(work)
                with self._quiet():
                    session = self._open(work)
                    service = PresetService(session)
                    candidates = []
                    for player_id in session.manager.player_mapping:
                        preset = service.export_inventory(
                            str(player_id), equipment_only=True
                        )
                        operation_count = sum(
                            len(container["slots"])
                            for container in preset["containers"]
                        )
                        dynamic_count = sum(
                            "dynamic_init" in slot
                            for container in preset["containers"]
                            for slot in container["slots"]
                        )
                        if 0 < operation_count <= 1_000:
                            candidates.append(
                                (
                                    operation_count,
                                    -dynamic_count,
                                    str(player_id),
                                    preset,
                                )
                            )
                    self.assertTrue(candidates, "No applicable inventory preset")
                    _count, negative_dynamic_count, player_id, preset = min(
                        candidates
                    )
                    self.assertLess(negative_dynamic_count, 0)
                    preview = service.preview_apply(
                        session_id=session.session_id,
                        expected_revision=0,
                        preset=preset,
                        target_ids=(player_id,),
                    )
                    result = service.apply(
                        session_id=session.session_id,
                        expected_revision=0,
                        preset=preset,
                        target_ids=(player_id,),
                        impact_token=preview["impact_token"],
                    )
                    self.assertEqual(1, result["revision"])
                    self.assertEqual("BatchCommand", session.changes()[0]["command"])
                    saved = SaveWriter().save(session, work, session.revision)
                    reloaded = self._open(work)
                    reloaded.manager.dynamic_item_data.assert_consistent()
                    roundtripped = PresetService(reloaded).export_inventory(
                        player_id, equipment_only=True
                    )
                self.assertEqual(preset, roundtripped)
                after = _save_hashes(work)
                changed = sorted(path for path in before if before[path] != after[path])
                self.assertEqual(["Level.sav"], changed)
                self.assertEqual(("Level.sav",), saved.written_files)
                self.assertTrue(saved.staged_reload_verified)
                self.assertTrue(saved.target_reload_verified)
                self._assert_source_unchanged(fixture, source_hashes)
        self.assertGreater(
            exercised, 0, "No fixture enables dynamic_equipment_preset_roundtrip"
        )

    def test_real_save_dynamic_batch_fill_roundtrip(self) -> None:
        exercised = 0
        for fixture in self.fixtures:
            if not self._capable(fixture, "dynamic_batch_fill_roundtrip"):
                continue
            exercised += 1
            with self.subTest(fixture=fixture["fixture_id"]), tempfile.TemporaryDirectory(
                prefix="pal-editor-real-dynamic-batch-"
            ) as temp_name:
                work, source_hashes = self._copy_fixture(
                    fixture, Path(temp_name) / fixture["fixture_id"]
                )
                before = _save_hashes(work)
                with self._quiet():
                    session = self._open(work)
                    catalog = ItemCatalog.load_default()
                    inventory = InventoryEditor(session, catalog)
                    source = None
                    target = None
                    for player_id in session.manager.player_mapping:
                        session.load_player(str(player_id))
                        view = inventory.get_inventory(str(player_id))
                        common = next(
                            container
                            for container in view.containers
                            if container.container_type == ItemContainerType.COMMON
                        )
                        _player, raw_container = inventory._resolve_owned_container(
                            str(player_id), ItemContainerType.COMMON
                        )
                        if source is None:
                            for slot in common.slots:
                                if slot.state != "occupied" or slot.dynamic_kind != "weapon":
                                    continue
                                raw_slot = raw_container.get_occupied(slot.slot_index)
                                record = session.manager.dynamic_item_data.require_writable_reference(
                                    raw_slot
                                )
                                source = {
                                    "static_id": slot.static_id,
                                    "count": slot.count,
                                    "dynamic_init": session.manager.dynamic_item_data.construction_initializer_for_record(
                                        record
                                    ),
                                }
                                break
                        empty = [
                            slot.slot_index
                            for slot in common.slots
                            if slot.state == "empty"
                        ]
                        if source is not None and len(empty) >= 2:
                            try:
                                for index in empty[:2]:
                                    catalog.validate_placement(
                                        source["static_id"],
                                        ItemContainerType.COMMON,
                                        index,
                                        source["count"],
                                    )
                            except DomainError:
                                continue
                            player = session.manager.get_player(str(player_id))
                            target = {
                                "player_id": str(player_id),
                                "container_id": str(
                                    player.resolve_item_container_ids()[
                                        "CommonContainerId"
                                    ]
                                ),
                                "indices": tuple(empty[:2]),
                            }
                            break
                    self.assertIsNotNone(source, "No constructible dynamic weapon")
                    self.assertIsNotNone(target, "No two-slot dynamic batch target")
                    result = InventoryLayoutEditor(session, catalog).execute(
                        FillItemSlots(
                            session_id=session.session_id,
                            expected_revision=0,
                            player_id=target["player_id"],
                            container_type=ItemContainerType.COMMON,
                            slot_indices=target["indices"],
                            static_id=source["static_id"],
                            count=source["count"],
                            dynamic_init=source["dynamic_init"],
                        )
                    )
                    local_ids = tuple(
                        slot["dynamic_id"].rsplit("/", 1)[1]
                        for slot in result["slots"]
                    )
                    self.assertEqual(2, len(set(local_ids)))
                    saved = SaveWriter().save(session, work, session.revision)
                    reloaded = self._open(work)
                    reloaded.manager.dynamic_item_data.assert_consistent()
                container = reloaded.manager.item_container_data.get(
                    target["container_id"]
                )
                for index, local_id in zip(target["indices"], local_ids):
                    slot = container.get_occupied(index)
                    record = reloaded.manager.dynamic_item_data.get(local_id)
                    self.assertEqual(source["static_id"], slot.static_id)
                    self.assertEqual(local_id, slot.dynamic_local_id)
                    self.assertEqual("weapon", record.kind)
                    self.assertEqual(
                        source["dynamic_init"],
                        reloaded.manager.dynamic_item_data.construction_initializer_for_record(
                            record
                        ),
                    )
                    self._assert_new_slot_metadata(slot._raw_data)
                after = _save_hashes(work)
                changed = sorted(path for path in before if before[path] != after[path])
                self.assertEqual(["Level.sav"], changed)
                self.assertEqual(("Level.sav",), saved.written_files)
                self._assert_source_unchanged(fixture, source_hashes)
        self.assertGreater(
            exercised, 0, "No fixture enables dynamic_batch_fill_roundtrip"
        )

    def test_real_save_equipment_sort_roundtrip(self) -> None:
        exercised = 0
        for fixture in self.fixtures:
            if not self._capable(fixture, "equipment_sort_roundtrip"):
                continue
            exercised += 1
            with self.subTest(fixture=fixture["fixture_id"]), tempfile.TemporaryDirectory(
                prefix="pal-editor-real-equipment-sort-"
            ) as temp_name:
                work, source_hashes = self._copy_fixture(
                    fixture, Path(temp_name) / fixture["fixture_id"]
                )
                before = _save_hashes(work)
                with self._quiet():
                    session = self._open(work)
                    catalog = ItemCatalog.load_default()
                    inventory = InventoryEditor(session, catalog)
                    selected = None
                    for player_id in session.manager.player_mapping:
                        session.load_player(str(player_id))
                        _player, container = inventory._resolve_owned_container(
                            str(player_id), ItemContainerType.PLAYER_EQUIP_ARMOR
                        )
                        try:
                            for slot in container.iter_occupied_slots():
                                catalog.validate_placement(
                                    slot.static_id,
                                    ItemContainerType.PLAYER_EQUIP_ARMOR,
                                    slot.slot_index,
                                    slot.count,
                                )
                        except DomainError:
                            continue
                        accessory_indices = (2, 3, 6, 7)
                        if sum(
                            index in container.slots for index in accessory_indices
                        ) < 2:
                            continue
                        snapshots = container.snapshot_all()
                        occupied = {
                            slot.slot_index: slot
                            for slot in container.iter_occupied_slots()
                        }
                        ordered = sorted(
                            (
                                occupied[index]
                                for index in accessory_indices
                                if index in occupied
                            ),
                            key=lambda slot: (slot.static_id, slot.slot_index),
                        )
                        empty = [
                            index
                            for index in accessory_indices
                            if index not in occupied
                        ]
                        expected_sources = dict(
                            zip(
                                accessory_indices,
                                [slot.slot_index for slot in ordered] + empty,
                            )
                        )
                        player = session.manager.get_player(str(player_id))
                        selected = {
                            "player_id": str(player_id),
                            "container_id": str(
                                player.resolve_item_container_ids()[
                                    "PlayerEquipArmorContainerId"
                                ]
                            ),
                            "snapshots": snapshots,
                            "expected_sources": expected_sources,
                        }
                        break
                    self.assertIsNotNone(selected, "No sortable equipment layout")
                    InventoryLayoutEditor(session, catalog).execute(
                        SortItemContainer(
                            session_id=session.session_id,
                            expected_revision=0,
                            player_id=selected["player_id"],
                            container_type=ItemContainerType.PLAYER_EQUIP_ARMOR,
                            sort_by="internal_id",
                        )
                    )
                    saved = SaveWriter().save(session, work, session.revision)
                    reloaded = self._open(work)
                    reloaded.manager.dynamic_item_data.assert_consistent()
                container = reloaded.manager.item_container_data.get(
                    selected["container_id"]
                )
                for target_index, source_index in selected["expected_sources"].items():
                    source_snapshot = selected["snapshots"][source_index]
                    target_snapshot = container.snapshot_slot(target_index)
                    self.assertEqual(
                        source_snapshot["item"], target_snapshot["item"]
                    )
                    self.assertEqual(
                        source_snapshot["count"], target_snapshot["count"]
                    )
                    self.assertEqual(
                        source_snapshot["corruption_progress_value"],
                        target_snapshot["corruption_progress_value"],
                    )
                    expected_metadata = {
                        "type_a": [3, 4, 10, 13],
                        "type_b": [22],
                        "item_static_ids": [],
                    }
                    self.assertEqual(
                        expected_metadata, target_snapshot["permission"]
                    )
                    self.assertEqual(
                        [0, 0, 0, 0], target_snapshot["trailing_bytes"]
                    )
                after = _save_hashes(work)
                changed = sorted(path for path in before if before[path] != after[path])
                self.assertEqual(["Level.sav"], changed)
                self.assertEqual(("Level.sav",), saved.written_files)
                self._assert_source_unchanged(fixture, source_hashes)
        self.assertGreater(
            exercised, 0, "No fixture enables equipment_sort_roundtrip"
        )

    def test_real_save_dynamic_attribute_roundtrip(self) -> None:
        exercised = 0
        for fixture in self.fixtures:
            if not self._capable(fixture, "dynamic_attribute_roundtrip"):
                continue
            exercised += 1
            with self.subTest(fixture=fixture["fixture_id"]), tempfile.TemporaryDirectory(
                prefix="pal-editor-real-dynamic-"
            ) as temp_name:
                work, source_hashes = self._copy_fixture(
                    fixture, Path(temp_name) / fixture["fixture_id"]
                )
                before = _save_hashes(work)
                allowed_ids = set(fixture.get("dynamic_attribute_candidates", []))
                with self._quiet():
                    session = self._open(work)
                    selected = None
                    for player_id in session.manager.player_mapping:
                        player = session.load_player(player_id)
                        ids = player.resolve_item_container_ids()
                        for container_type, field in INVENTORY_CONTAINER_FIELDS.items():
                            container_id = ids.get(field)
                            container = session.manager.item_container_data.get(container_id)
                            if container is None:
                                continue
                            for slot in container.iter_occupied_slots():
                                if slot.dynamic_id is None:
                                    continue
                                record = session.manager.dynamic_item_data.get(
                                    slot.dynamic_local_id
                                )
                                if (
                                    record is not None
                                    and record.static_id in allowed_ids
                                    and record.kind in {"weapon", "armor"}
                                    and isinstance(record.raw_data.get("durability"), float)
                                    and record.raw_data["durability"] >= 1.0
                                ):
                                    selected = (
                                        str(player_id),
                                        container_type,
                                        str(container_id),
                                        slot,
                                        dict(record.raw_data),
                                    )
                                    break
                            if selected:
                                break
                        if selected:
                            break
                    self.assertIsNotNone(
                        selected, "No manifest-approved dynamic attribute candidate"
                    )
                    player_id, container_type, container_id, slot, raw_before = selected
                    new_durability = raw_before["durability"] - 1.0
                    DynamicAttributeEditor(session).execute(
                        UpdateDynamicItemAttributes(
                            session_id=session.session_id,
                            expected_revision=0,
                            player_id=player_id,
                            container_type=container_type,
                            slot_index=slot.slot_index,
                            expected_static_id=slot.static_id,
                            expected_dynamic_id=slot.dynamic_id,
                            values={"durability": new_durability},
                        )
                    )
                    saved = SaveWriter().save(session, work, session.revision)
                    reloaded = self._open(work)
                    reloaded.load_player(player_id)
                    new_slot = reloaded.manager.item_container_data.get(
                        container_id
                    ).get_occupied(slot.slot_index)
                    raw_after = reloaded.manager.dynamic_item_data.get(
                        new_slot.dynamic_local_id
                    ).raw_data
                self.assertEqual(new_durability, raw_after["durability"])
                self.assertEqual(
                    {key: value for key, value in raw_before.items() if key != "durability"},
                    {key: value for key, value in raw_after.items() if key != "durability"},
                )
                self.assertEqual((), reloaded.manager.dynamic_item_data.issues())
                after = _save_hashes(work)
                changed = sorted(path for path in before if before[path] != after[path])
                self.assertEqual(["Level.sav"], changed)
                self.assertEqual(("Level.sav",), saved.written_files)
                backup = Path(saved.backup_path) / "files" / "Level.sav"
                self.assertEqual(before["Level.sav"], _sha256(backup))
                self._assert_source_unchanged(fixture, source_hashes)
        self.assertGreater(
            exercised, 0, "No fixture enables dynamic_attribute_roundtrip"
        )

    def test_real_save_dynamic_item_delete_roundtrip(self) -> None:
        exercised = 0
        for fixture in self.fixtures:
            if not self._capable(fixture, "dynamic_item_delete_roundtrip"):
                continue
            exercised += 1
            with self.subTest(fixture=fixture["fixture_id"]), tempfile.TemporaryDirectory(
                prefix="pal-editor-real-dynamic-delete-"
            ) as temp_name:
                work, source_hashes = self._copy_fixture(
                    fixture, Path(temp_name) / fixture["fixture_id"]
                )
                before = _save_hashes(work)
                with self._quiet():
                    session = self._open(work)
                    candidates = []
                    for player_id in session.manager.player_mapping:
                        player = session.load_player(player_id)
                        ids = player.resolve_item_container_ids()
                        for container_type, field in INVENTORY_CONTAINER_FIELDS.items():
                            container_id = ids.get(field)
                            container = session.manager.item_container_data.get(
                                container_id
                            )
                            if container is None:
                                continue
                            for slot in container.iter_occupied_slots():
                                if slot.dynamic_id is None:
                                    continue
                                record = session.manager.dynamic_item_data.get(
                                    slot.dynamic_local_id
                                )
                                if (
                                    record is not None
                                    and len(
                                        session.manager.dynamic_item_data.references.get(
                                            record.local_id, []
                                        )
                                    )
                                    == 1
                                ):
                                    candidates.append(
                                        (
                                            str(player_id),
                                            container_type,
                                            str(container_id),
                                            slot.slot_index,
                                            slot.static_id,
                                            slot.dynamic_id,
                                            record.local_id,
                                        )
                                    )
                    self.assertTrue(
                        candidates, "No uniquely referenced dynamic item candidate"
                    )
                    (
                        player_id,
                        container_type,
                        container_id,
                        slot_index,
                        static_id,
                        dynamic_id,
                        local_id,
                    ) = candidates[0]
                    editor = InventoryEditor(session, ItemCatalog.load_default())
                    result = editor.execute(
                        ClearItemSlot(
                            session_id=session.session_id,
                            expected_revision=0,
                            player_id=player_id,
                            container_type=container_type,
                            slot_index=slot_index,
                            expected_static_id=static_id,
                            expected_dynamic_id=dynamic_id,
                        )
                    )
                    self.assertEqual("empty", result["slot"]["state"])
                    self.assertGreater(
                        session.manager.dynamic_item_reference_audit_seconds, 0
                    )
                    SaveWriter().save(session, work, session.revision)
                    reloaded = self._open(work)
                    reloaded_container = reloaded.manager.item_container_data.get(
                        container_id
                    )
                    reloaded.manager.dynamic_item_data.assert_consistent()
                self.assertTrue(reloaded_container.is_empty(slot_index))
                self.assertIsNone(reloaded.manager.dynamic_item_data.get(local_id))
                after = _save_hashes(work)
                changed = sorted(path for path in before if before[path] != after[path])
                self.assertEqual(["Level.sav"], changed)
                self._assert_source_unchanged(fixture, source_hashes)
        self.assertGreater(
            exercised, 0, "No fixture enables dynamic_item_delete_roundtrip"
        )

    def test_real_save_pal_move_roundtrip(self) -> None:
        exercised = 0
        for fixture in self.fixtures:
            if not self._capable(fixture, "pal_move_roundtrip"):
                continue
            exercised += 1
            with self.subTest(fixture=fixture["fixture_id"]), tempfile.TemporaryDirectory(
                prefix="pal-editor-real-pal-"
            ) as temp_name:
                work, source_hashes = self._copy_fixture(
                    fixture, Path(temp_name) / fixture["fixture_id"]
                )
                before = _save_hashes(work)
                with self._quiet():
                    session = self._open(work)
                    editor = StructuralPalEditor(session)
                    selected = None
                    for player_id, player in session.manager.player_mapping.items():
                        player = session.load_player(player_id)
                        party = session.manager.container_data.get_container(
                            player.OtomoCharacterContainerId
                        )
                        storage = session.manager.container_data.get_container(
                            player.PalStorageContainerId
                        )
                        choices = []
                        if party and storage and party.slots and storage.get_empty_slot() != -1:
                            choices.append(
                                (
                                    party.slots,
                                    CharacterContainerType.PAL_STORAGE,
                                    str(storage.ID),
                                )
                            )
                        if party and storage and storage.slots and party.get_empty_slot() != -1:
                            choices.append(
                                (
                                    storage.slots,
                                    CharacterContainerType.PARTY,
                                    str(party.ID),
                                )
                            )
                        for slots, target_type, target_id in choices:
                            for source_slot in slots:
                                command = MovePal(
                                    session_id=session.session_id,
                                    expected_revision=0,
                                    pal_id=str(source_slot.instance_id),
                                    target_player_id=str(player_id),
                                    container_type=target_type,
                                )
                                try:
                                    preview = editor.preview_move(command)
                                except DomainError:
                                    continue
                                selected = (command, preview, target_id)
                                break
                            if selected:
                                break
                        if selected:
                            break
                    self.assertIsNotNone(selected, "No safe real Pal move candidate")
                    command, preview, target_id = selected
                    editor.execute(
                        replace(command, impact_token=preview["impact_token"])
                    )
                    saved = SaveWriter().save(session, work, session.revision)
                    reloaded = self._open(work)
                    index = CharacterIndex(reloaded.manager)
                self.assertEqual([], index.hard_issues())
                moved_pal = index.pals[command.pal_id]
                self.assertEqual(
                    command.container_type.value,
                    moved_pal.owner_container_type,
                )
                references = index.container_references[command.pal_id]
                self.assertEqual(1, len(references))
                self.assertEqual(target_id, references[0].container_id)
                after = _save_hashes(work)
                changed = sorted(path for path in before if before[path] != after[path])
                self.assertEqual(["Level.sav"], changed)
                self.assertEqual(("Level.sav",), saved.written_files)
                backup = Path(saved.backup_path) / "files" / "Level.sav"
                self.assertEqual(before["Level.sav"], _sha256(backup))
                self._assert_source_unchanged(fixture, source_hashes)
        self.assertGreater(exercised, 0, "No fixture enables pal_move_roundtrip")

    def test_real_save_heal_all_pals_roundtrip(self) -> None:
        exercised = 0
        for fixture in self.fixtures:
            if not self._capable(fixture, "pal_move_roundtrip"):
                continue
            exercised += 1
            with self.subTest(fixture=fixture["fixture_id"]), tempfile.TemporaryDirectory(
                prefix="pal-editor-real-heal-"
            ) as temp_name:
                work, source_hashes = self._copy_fixture(
                    fixture, Path(temp_name) / fixture["fixture_id"]
                )
                before = _save_hashes(work)
                with self._quiet():
                    session = self._open(work)
                    target = next(
                        (
                            pal
                            for pal in CharacterIndex(session.manager).pals.values()
                            if pal.ComputedMaxHP
                            and DataProvider.get_pal_stats(
                                pal.DataAccessKey, "FOOD"
                            )
                        ),
                        None,
                    )
                    self.assertIsNotNone(target, "No healable real Pal candidate")
                    target_id = str(target.InstanceId)
                    expected_health = target.ComputedMaxHP
                    expected_satiety = DataProvider.get_pal_stats(
                        target.DataAccessKey, "FOOD"
                    )
                    target.Hp = 0
                    target.FullStomach = 0.0
                    target.SanityValue = 0.0
                    result = CharacterEditor(session).execute(
                        HealAllPals(
                            session_id=session.session_id,
                            expected_revision=session.revision,
                        )
                    )
                    self.assertEqual(
                        len(CharacterIndex(session.manager).pals),
                        result["value"]["healed_count"],
                    )
                    saved = SaveWriter().save(session, work, session.revision)
                    session.close()
                    reloaded = self._open(work)
                    healed = CharacterIndex(reloaded.manager).pals[target_id]
                self.assertEqual(expected_health, healed.Hp)
                self.assertEqual(expected_satiety, healed.FullStomach)
                self.assertEqual(100.0, healed.SanityValue)
                after = _save_hashes(work)
                changed = sorted(path for path in before if before[path] != after[path])
                self.assertEqual(["Level.sav"], changed)
                self.assertEqual(("Level.sav",), saved.written_files)
                self.assertTrue(saved.staged_reload_verified)
                self.assertTrue(saved.target_reload_verified)
                reloaded.close()
                self._assert_source_unchanged(fixture, source_hashes)
        self.assertGreater(exercised, 0, "No fixture enables pal_move_roundtrip")

    def test_real_save_pal_add_clone_delete_roundtrip(self) -> None:
        exercised = 0
        for fixture in self.fixtures:
            if not self._capable(fixture, "pal_add_clone_delete_roundtrip"):
                continue
            exercised += 1
            with self.subTest(fixture=fixture["fixture_id"]), tempfile.TemporaryDirectory(
                prefix="pal-editor-real-pal-structure-"
            ) as temp_name:
                work, source_hashes = self._copy_fixture(
                    fixture, Path(temp_name) / fixture["fixture_id"]
                )
                before = _save_hashes(work)
                with self._quiet():
                    session = self._open(work)
                    editor = StructuralPalEditor(session)
                    selected = None
                    for player_id in session.manager.player_mapping:
                        player = session.load_player(player_id)
                        container = session.manager.container_data.get_container(
                            player.PalStorageContainerId
                        )
                        if container is None or len(container.available_inv_idx_set) < 2:
                            continue
                        for source_pal in CharacterIndex(session.manager).pals.values():
                            clone = ClonePal(
                                session_id=session.session_id,
                                expected_revision=session.revision,
                                source_pal_id=str(source_pal.InstanceId),
                                target_player_id=str(player_id),
                                container_type=CharacterContainerType.PAL_STORAGE,
                            )
                            try:
                                preview = editor.preview_clone(clone)
                            except DomainError:
                                continue
                            selected = (str(player_id), source_pal.CharacterID, clone, preview)
                            break
                        if selected:
                            break
                    self.assertIsNotNone(
                        selected, "No real target with two free Pal slots and cloneable source"
                    )
                    player_id, _species_id, clone, _ = selected
                    added = editor.execute(
                        AddPal(
                            session_id=session.session_id,
                            expected_revision=session.revision,
                            player_id=player_id,
                            species_id="SheepBall",
                            container_type=CharacterContainerType.PAL_STORAGE,
                            passive=("WorldTree_CraftSpeed", "CraftSpeed_up3"),
                            max_pal=True,
                        )
                    )
                    added_pal_id = added["pal"]["pal_id"]
                    clone = replace(clone, expected_revision=session.revision)
                    preview = editor.preview_clone(clone)
                    cloned = editor.execute(
                        replace(clone, impact_token=preview["impact_token"])
                    )
                    cloned_pal_id = cloned["pal"]["pal_id"]
                    first_save = SaveWriter().save(session, work, session.revision)
                    reloaded = self._open(work)
                    reloaded_index = CharacterIndex(reloaded.manager)
                self.assertIn(added_pal_id, reloaded_index.pals)
                self.assertIn(cloned_pal_id, reloaded_index.pals)
                self.assertEqual([], reloaded_index.hard_issues())
                reloaded_added_pal = reloaded_index.pals[added_pal_id]
                self.assertEqual(
                    ["WorldTree_CraftSpeed", "CraftSpeed_up3"],
                    reloaded_added_pal.PassiveSkillList,
                )
                self.assertEqual(
                    Config.max_souls_level,
                    reloaded_added_pal.Rank_CraftSpeed,
                )
                self.assertEqual(10, reloaded_added_pal.FriendshipLevel)
                self.assertEqual(5, reloaded_added_pal.Rank)
                self.assertTrue(
                    all(
                        level == Config.max_suitability_level
                        for level in reloaded_added_pal.WorkSuitabilities.values()
                    )
                )
                first_after = _save_hashes(work)
                first_changed = sorted(
                    path for path in before if before[path] != first_after[path]
                )
                self.assertEqual(sorted(first_save.written_files), first_changed)
                self.assertIn("Level.sav", first_changed)
                self.assertEqual(2, len(first_changed))
                for relative_path in first_save.written_files:
                    backup = Path(first_save.backup_path) / "files" / relative_path
                    self.assertEqual(before[relative_path], _sha256(backup))

                with self._quiet():
                    delete_editor = StructuralPalEditor(reloaded)
                    delete_preview = delete_editor.preview_delete(
                        pal_id=cloned_pal_id,
                        session_id=reloaded.session_id,
                        expected_revision=reloaded.revision,
                    )
                    delete_editor.execute(
                        DeletePal(
                            session_id=reloaded.session_id,
                            expected_revision=reloaded.revision,
                            pal_id=cloned_pal_id,
                            impact_token=delete_preview["impact_token"],
                        )
                    )
                    second_save = SaveWriter().save(
                        reloaded, work, reloaded.revision
                    )
                    final = self._open(work)
                    final_index = CharacterIndex(final.manager)
                self.assertIn(added_pal_id, final_index.pals)
                self.assertNotIn(cloned_pal_id, final_index.pals)
                self.assertEqual([], final_index.hard_issues())
                final_hashes = _save_hashes(work)
                second_changed = sorted(
                    path
                    for path in first_after
                    if first_after[path] != final_hashes[path]
                )
                self.assertEqual(sorted(second_save.written_files), second_changed)
                self.assertIn("Level.sav", second_changed)
                for relative_path in second_save.written_files:
                    backup = Path(second_save.backup_path) / "files" / relative_path
                    self.assertEqual(first_after[relative_path], _sha256(backup))
                self._assert_source_unchanged(fixture, source_hashes)
        self.assertGreater(
            exercised, 0, "No fixture enables pal_add_clone_delete_roundtrip"
        )

    def test_real_save_player_fields_roundtrip(self) -> None:
        exercised = 0
        for fixture in self.fixtures:
            if not self._capable(fixture, "player_field_roundtrip"):
                continue
            exercised += 1
            with self.subTest(fixture=fixture["fixture_id"]), tempfile.TemporaryDirectory(
                prefix="pal-editor-real-player-fields-"
            ) as temp_name:
                work, source_hashes = self._copy_fixture(
                    fixture, Path(temp_name) / fixture["fixture_id"]
                )
                before = _save_hashes(work)
                with self._quiet():
                    session = self._open(work)
                    player_id = str(next(iter(session.manager.player_mapping)))
                    player = session.load_player(player_id)
                    editor = CharacterEditor(session)
                    current = editor._player_progression(player)
                    new_name = "Codex Real QA"
                    new_experience = (
                        current["experience"] + 1
                        if current["experience"] < 9_223_372_036_854_775_807
                        else current["experience"] - 1
                    )
                    new_technology_points = (
                        current["technology_points"] + 1
                        if current["technology_points"] < 65_535
                        else current["technology_points"] - 1
                    )
                    new_boss_points = (
                        current["boss_technology_points"] + 1
                        if current["boss_technology_points"] < 65_535
                        else current["boss_technology_points"] - 1
                    )
                    recipe_id = next(iter(DataProvider.get_tech_data()))
                    recipe_unlocked = recipe_id not in set(
                        player.UnlockedRecipeTechnologyNames or []
                    )
                    editor.execute(
                        UpdatePlayerIdentity(
                            session_id=session.session_id,
                            expected_revision=session.revision,
                            player_id=player_id,
                            name=new_name,
                        )
                    )
                    editor.execute(
                        UpdatePlayerProgression(
                            session_id=session.session_id,
                            expected_revision=session.revision,
                            player_id=player_id,
                            level=current["level"],
                            experience=new_experience,
                            technology_points=new_technology_points,
                            boss_technology_points=new_boss_points,
                        )
                    )
                    editor.execute(
                        UpdatePlayerTechnology(
                            session_id=session.session_id,
                            expected_revision=session.revision,
                            player_id=player_id,
                            recipe_id=recipe_id,
                            unlocked=recipe_unlocked,
                        )
                    )
                    saved = SaveWriter().save(session, work, session.revision)
                    reloaded = self._open(work)
                    reloaded_player = reloaded.load_player(player_id)
                    reloaded_progression = CharacterEditor._player_progression(
                        reloaded_player
                    )
                self.assertEqual(new_name, reloaded_player.NickName)
                self.assertEqual(current["level"], reloaded_progression["level"])
                self.assertEqual(
                    new_experience, reloaded_progression["experience"]
                )
                self.assertEqual(
                    new_technology_points,
                    reloaded_progression["technology_points"],
                )
                self.assertEqual(
                    new_boss_points,
                    reloaded_progression["boss_technology_points"],
                )
                self.assertEqual(
                    recipe_unlocked,
                    recipe_id in set(
                        reloaded_player.UnlockedRecipeTechnologyNames or []
                    ),
                )
                self.assertEqual([], CharacterIndex(reloaded.manager).hard_issues())
                after = _save_hashes(work)
                changed = sorted(path for path in before if before[path] != after[path])
                self.assertEqual(sorted(saved.written_files), changed)
                self.assertIn("Level.sav", changed)
                self.assertEqual(2, len(changed))
                for relative_path in saved.written_files:
                    backup = Path(saved.backup_path) / "files" / relative_path
                    self.assertEqual(before[relative_path], _sha256(backup))
                self._assert_source_unchanged(fixture, source_hashes)
        self.assertGreater(exercised, 0, "No fixture enables player_field_roundtrip")

    def test_real_save_mission_roundtrip_changes_only_player_quest_fields(self) -> None:
        exercised = 0
        for fixture in self.fixtures:
            if not fixture["contains_player_files"]:
                continue
            with self.subTest(fixture=fixture["fixture_id"]), tempfile.TemporaryDirectory(
                prefix="pal-editor-real-missions-"
            ) as temp_name:
                work, source_hashes = self._copy_fixture(
                    fixture, Path(temp_name) / fixture["fixture_id"]
                )
                before_hashes = _save_hashes(work)
                selected = None
                with self._quiet():
                    session = self._open(work)
                    for player_id in session.manager.player_mapping:
                        editor = MissionEditor(session, locale="en")
                        try:
                            view = editor.get_missions(str(player_id))
                        except DomainError:
                            continue
                        if not view["writable"]:
                            continue
                        priority = {"in_progress": 0, "completed": 1, "unaccepted": 2}
                        candidates = sorted(
                            (
                                mission
                                for mission in view["missions"]
                                if mission["status"] in priority
                                and mission["capabilities"]["mark_completed"]
                            ),
                            key=lambda mission: priority[mission["status"]],
                        )
                        if not candidates:
                            continue
                        mission = candidates[0]
                        operation = (
                            "reset_to_unaccepted"
                            if mission["status"] == "completed"
                            else "mark_completed"
                        )
                        expected_status = (
                            "unaccepted"
                            if operation == "reset_to_unaccepted"
                            else "completed"
                        )
                        player = session.load_player(str(player_id))
                        aliases = {
                            "CompletedQuestArray",
                            "OrderedQuestArray",
                            "CompletedQuestArray_FullRelease",
                            "OrderedQuestArray_FullRelease",
                        }
                        other_fields = {
                            key: deepcopy(value)
                            for key, value in player._player_save_data.items()
                            if key not in aliases
                        }
                        command = UpdatePlayerMissions(
                            session_id=session.session_id,
                            expected_revision=session.revision,
                            player_id=str(player_id),
                            operation=operation,
                            mission_ids=(mission["internal_name"],),
                        )
                        preview = editor.preview(command)
                        selected = (
                            str(player_id),
                            mission["internal_name"],
                            expected_status,
                            other_fields,
                            editor,
                            command,
                            preview,
                        )
                        break
                    if selected is None:
                        continue
                    (
                        player_id,
                        mission_id,
                        expected_status,
                        other_fields,
                        editor,
                        command,
                        preview,
                    ) = selected
                    result = editor.execute(
                        replace(command, preview_token=preview["preview_token"])
                    )
                    self.assertEqual(1, result["impact_count"])
                    saved = SaveWriter().save(session, work, session.revision)
                    reloaded = self._open(work)
                    reloaded_player = reloaded.load_player(player_id)
                    final_view = MissionEditor(reloaded, locale="en").get_missions(
                        player_id
                    )
                exercised += 1
                final_status = next(
                    mission["status"]
                    for mission in final_view["missions"]
                    if mission["internal_name"] == mission_id
                )
                self.assertEqual(expected_status, final_status)
                self.assertEqual(
                    other_fields,
                    {
                        key: value
                        for key, value in reloaded_player._player_save_data.items()
                        if key
                        not in {
                            "CompletedQuestArray",
                            "OrderedQuestArray",
                            "CompletedQuestArray_FullRelease",
                            "OrderedQuestArray_FullRelease",
                        }
                    },
                )
                after_hashes = _save_hashes(work)
                changed = sorted(
                    path
                    for path in before_hashes
                    if before_hashes[path] != after_hashes[path]
                )
                self.assertEqual(list(saved.written_files), changed)
                self.assertEqual(1, len(changed))
                self.assertTrue(changed[0].startswith("Players/"))
                backup = Path(saved.backup_path) / "files" / changed[0]
                self.assertEqual(before_hashes[changed[0]], _sha256(backup))
                self._assert_source_unchanged(fixture, source_hashes)
        self.assertGreater(
            exercised,
            0,
            "No configured real fixture exposes writable mission fields",
        )

    def test_real_save_detached_pal_recovery_roundtrip(self) -> None:
        exercised = 0
        for fixture in self.fixtures:
            if not self._capable(fixture, "detached_pal_recovery_roundtrip"):
                continue
            exercised += 1
            with self.subTest(fixture=fixture["fixture_id"]), tempfile.TemporaryDirectory(
                prefix="pal-editor-real-recover-"
            ) as temp_name:
                work, source_hashes = self._copy_fixture(
                    fixture, Path(temp_name) / "save"
                )
                before = _save_hashes(work)
                with self._quiet():
                    session = self._open(work)
                    selected = None
                    index = CharacterIndex(session.manager)
                    for player_id in session.manager.player_mapping:
                        player = session.load_player(player_id)
                        allowed = {
                            str(player.PalStorageContainerId): CharacterContainerType.PAL_STORAGE,
                            str(player.OtomoCharacterContainerId): CharacterContainerType.PARTY,
                        }
                        for pal_id, pal in index.pals.items():
                            refs = index.container_references.get(pal_id, [])
                            if (
                                len(refs) == 1
                                and refs[0].container_id in allowed
                                and str(pal.OwnerPlayerUId) == str(player_id)
                            ):
                                selected = {
                                    "player_id": str(player_id),
                                    "pal_id": pal_id,
                                    "container_type": allowed[refs[0].container_id],
                                    "container_id": refs[0].container_id,
                                    "slot": refs[0].slot_index,
                                    "param": deepcopy(pal._pal_param),
                                }
                                break
                        if selected is not None:
                            break
                    self.assertIsNotNone(selected, "No real personal Pal can be detached")
                    source_container = session.manager.container_data.get_container(
                        selected["container_id"]
                    )
                    source_container.del_pal(selected["pal_id"])
                    detached_index = CharacterIndex(session.manager)
                    self.assertEqual([], detached_index.hard_issues())
                    self.assertTrue(
                        any(
                            issue.code == "PAL_DETACHED"
                            and issue.pal_id == selected["pal_id"]
                            for issue in detached_index.issues
                        )
                    )
                    result = StructuralPalEditor(session).execute(
                        RecoverDetachedPal(
                            session_id=session.session_id,
                            expected_revision=session.revision,
                            pal_id=selected["pal_id"],
                            target_player_id=selected["player_id"],
                            container_type=selected["container_type"],
                            target_slot=selected["slot"],
                        )
                    )
                    self.assertEqual(1, result["change"]["revision_after"])
                    saved = SaveWriter().save(session, work, session.revision)
                    reloaded = self._open(work)
                    final_index = CharacterIndex(reloaded.manager)
                restored = final_index.pals[selected["pal_id"]]
                self.assertEqual(selected["slot"], restored.SlotIndex)
                self.assertEqual(selected["param"], restored._pal_param)
                self.assertEqual([], final_index.hard_issues())
                after = _save_hashes(work)
                changed = sorted(
                    path for path in before if before[path] != after[path]
                )
                self.assertEqual(["Level.sav"], changed)
                self.assertEqual(tuple(changed), saved.written_files)
                backup = Path(saved.backup_path) / "files" / "Level.sav"
                self.assertEqual(before["Level.sav"], _sha256(backup))
                self._assert_source_unchanged(fixture, source_hashes)
        self.assertGreater(
            exercised, 0, "No fixture enables detached_pal_recovery_roundtrip"
        )
