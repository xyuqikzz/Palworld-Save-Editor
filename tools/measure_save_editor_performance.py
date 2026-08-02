from __future__ import annotations

import argparse
import contextlib
import ctypes
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import platform
import shutil
import statistics
import sys
import tempfile
from time import perf_counter, process_time
import tracemalloc

from palworld_pal_editor.application.inventory_editor import InventoryEditor
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.application.save_writer import SaveWriter
from palworld_pal_editor.core.character_index import CharacterIndex
from palworld_pal_editor.core.save_manager import SaveManager
from palworld_pal_editor.domain.commands import UpdateItemCount
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.domain.item_catalog import ItemCatalog
from palworld_pal_editor.domain.models import INVENTORY_CONTAINER_FIELDS


@contextlib.contextmanager
def _silenced():
    saved_stdout_fd = os.dup(1)
    saved_stderr_fd = os.dup(2)
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    captured_stdout = io.StringIO()
    captured_stderr = io.StringIO()
    try:
        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2(devnull_fd, 1)
        os.dup2(devnull_fd, 2)
        with (
            contextlib.redirect_stdout(captured_stdout),
            contextlib.redirect_stderr(captured_stderr),
        ):
            yield
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2(saved_stdout_fd, 1)
        os.dup2(saved_stderr_fd, 2)
        os.close(devnull_fd)
        os.close(saved_stdout_fd)
        os.close(saved_stderr_fd)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _percentile(samples: list[float], percentile: float) -> float:
    ordered = sorted(samples)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _sample_summary(samples: list[float]) -> dict[str, object]:
    return {
        "samples_seconds": samples,
        "median_seconds": statistics.median(samples),
        "p95_seconds": _percentile(samples, 0.95),
    }


def _directory_bytes(path: Path) -> int:
    return sum(value.stat().st_size for value in path.rglob("*") if value.is_file())


def _peak_working_set_bytes() -> int | None:
    if platform.system() != "Windows":
        return None

    class ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    psapi.GetProcessMemoryInfo.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ProcessMemoryCounters),
        ctypes.c_ulong,
    ]
    psapi.GetProcessMemoryInfo.restype = ctypes.c_int
    counters = ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    ok = psapi.GetProcessMemoryInfo(
        kernel32.GetCurrentProcess(),
        ctypes.byref(counters),
        counters.cb,
    )
    return int(counters.PeakWorkingSetSize) if ok else None


def _copy_fixture(source: Path, destination: Path) -> Path:
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
    return destination


def _open(path: Path) -> SaveSession:
    return SaveSession.open(path, manager=SaveManager.create_isolated())


def _select_count_candidate(session: SaveSession):
    catalog = ItemCatalog.load_default()
    for player_id in session.manager.player_mapping:
        player = session.load_player(player_id)
        identifiers = player.resolve_item_container_ids()
        for container_type, field_name in INVENTORY_CONTAINER_FIELDS.items():
            container = session.manager.item_container_data.get(
                identifiers.get(field_name)
            )
            if container is None:
                continue
            for slot in container.iter_occupied_slots():
                if slot.dynamic_id is not None or slot.count < 2:
                    continue
                try:
                    catalog.validate_existing_count_update(
                        slot.static_id,
                        container_type,
                        slot.slot_index,
                        current_count=slot.count,
                        count=slot.count - 1,
                    )
                except DomainError:
                    continue
                return str(player_id), container_type, slot
    raise RuntimeError("No real plain stack supports a safe count decrease")


def _measure_save(source: Path, operation_count: int) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix=f"pal-editor-perf-{operation_count}-") as name:
        work = _copy_fixture(source, Path(name) / "save")
        with _silenced():
            session = _open(work)
            player_id, container_type, slot = _select_count_candidate(session)
            editor = InventoryEditor(session)
            original = slot.count
            for index in range(operation_count):
                current = original if index % 2 == 0 else original - 1
                target = original - 1 if index % 2 == 0 else original
                editor.execute(
                    UpdateItemCount(
                        session_id=session.session_id,
                        expected_revision=session.revision,
                        player_id=player_id,
                        container_type=container_type,
                        slot_index=slot.slot_index,
                        expected_static_id=slot.static_id,
                        count=target,
                    )
                )
                if current == target:
                    raise AssertionError("Performance mutation did not change state")
        observed: dict[str, int] = {}

        def observe(stage: str, context: dict) -> None:
            if stage == "after_backup":
                observed["backup_bytes"] = _directory_bytes(
                    Path(context["backup_path"])
                )
            elif stage == "before_replace":
                observed["staging_bytes"] = _directory_bytes(
                    Path(context["staging_path"])
                )

        started = perf_counter()
        with _silenced():
            result = SaveWriter(failure_hook=observe).save(
                session, work, session.revision
            )
        elapsed = perf_counter() - started
        with _silenced():
            reloaded = _open(work)
            if CharacterIndex(reloaded.manager).hard_issues():
                raise AssertionError("Saved performance fixture has character issues")
        return {
            "operation_count": operation_count,
            "save_seconds": elapsed,
            "written_files": list(result.written_files),
            "backup_bytes": observed["backup_bytes"],
            "staging_bytes": observed["staging_bytes"],
        }


def _measure_save_series(
    source: Path, operation_count: int, sample_count: int = 3
) -> dict[str, object]:
    measurements = [
        _measure_save(source, operation_count) for _ in range(sample_count)
    ]
    written_files = measurements[0]["written_files"]
    if any(value["written_files"] != written_files for value in measurements[1:]):
        raise AssertionError("Save performance samples wrote different file sets")
    return {
        "operation_count": operation_count,
        **_sample_summary([value["save_seconds"] for value in measurements]),
        "written_files": written_files,
        "backup_bytes": [value["backup_bytes"] for value in measurements],
        "staging_bytes": [value["staging_bytes"] for value in measurements],
    }


def measure(fixture_root: Path, fixture_id: str | None) -> dict[str, object]:
    manifest = json.loads(
        (fixture_root / "manifest.local.json").read_text(encoding="utf-8")
    )
    fixtures = manifest["fixtures"]
    fixture = next(
        (
            value
            for value in fixtures
            if fixture_id is None or value["fixture_id"] == fixture_id
        ),
        None,
    )
    if fixture is None:
        raise RuntimeError("Requested fixture was not found")
    source = (fixture_root / fixture["relative_path"]).resolve()
    if not source.is_dir():
        raise RuntimeError("Fixture directory does not exist")

    logging.disable(logging.CRITICAL)
    tracemalloc.start()
    open_wall_started = perf_counter()
    open_cpu_started = process_time()
    with _silenced():
        session = _open(source)
    open_wall = perf_counter() - open_wall_started
    open_cpu = process_time() - open_cpu_started
    _current, open_python_peak = tracemalloc.get_traced_memory()
    at_open = session.performance_metrics()

    list_samples = []
    for _ in range(20):
        started = perf_counter()
        players = session.list_players()
        list_samples.append(perf_counter() - started)
    if not players:
        raise RuntimeError("Fixture has no players")
    player_id = players[0].player_id

    reads_before = session.manager.player_file_load_count
    with _silenced():
        started = perf_counter()
        session.load_player(player_id)
        cold_detail = perf_counter() - started
        reads_after_cold = session.manager.player_file_load_count
        warm_samples = []
        for _ in range(20):
            started = perf_counter()
            session.load_player(player_id)
            warm_samples.append(perf_counter() - started)
    reads_after_warm = session.manager.player_file_load_count

    inventory = InventoryEditor(session)
    inventory_samples = []
    with _silenced():
        for _ in range(20):
            started = perf_counter()
            inventory_view = inventory.get_inventory(player_id)
            inventory_samples.append(perf_counter() - started)

    _current, read_python_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    save_measurements = [
        _measure_save_series(source, count) for count in (1, 10, 100)
    ]
    result = {
        "schema_version": 3,
        "fixture": {
            "fixture_id": fixture["fixture_id"],
            "game_version": fixture["game_version"],
            "save_version": fixture["save_version"],
            "level_sha256": _sha256(source / "Level.sav"),
            "level_bytes": (source / "Level.sav").stat().st_size,
        },
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "processor": platform.processor(),
        },
        "open": {
            "wall_seconds": open_wall,
            "cpu_seconds": open_cpu,
            "player_file_count": at_open["player_file_count"],
            "player_files_loaded": at_open["player_files_loaded"],
            "player_file_reads": at_open["player_file_reads"],
            "python_peak_bytes": open_python_peak,
        },
        "player_summary": {
            **_sample_summary(list_samples),
            "result_count": len(players),
        },
        "player_detail": {
            "cold_seconds": cold_detail,
            "warm": _sample_summary(warm_samples),
            "reads_before": reads_before,
            "reads_after_cold": reads_after_cold,
            "reads_after_warm": reads_after_warm,
        },
        "five_container_inventory": {
            **_sample_summary(inventory_samples),
            "container_count": len(inventory_view.containers),
        },
        "save_changesets": save_measurements,
        "memory": {
            "read_phase_python_peak_bytes": read_python_peak,
            "process_peak_working_set_bytes": _peak_working_set_bytes(),
        },
    }
    return result


def compare_to_baseline(
    result: dict[str, object],
    baseline: dict[str, object],
    *,
    max_time_ratio: float,
    max_memory_ratio: float,
) -> dict[str, object]:
    if baseline.get("schema_version") != result.get("schema_version"):
        raise RuntimeError("Performance baseline schema does not match")
    for field in ("fixture_id", "level_sha256"):
        if baseline["fixture"][field] != result["fixture"][field]:
            raise RuntimeError(f"Performance baseline fixture {field} does not match")

    def get(value: dict[str, object], path: tuple[str, ...]):
        current = value
        for key in path:
            current = current[key]
        return current

    time_metric_paths = {
        "open.wall_seconds": ("open", "wall_seconds"),
        "open.cpu_seconds": ("open", "cpu_seconds"),
        "player_summary.median_seconds": ("player_summary", "median_seconds"),
        "player_summary.p95_seconds": ("player_summary", "p95_seconds"),
        "player_detail.cold_seconds": ("player_detail", "cold_seconds"),
        "player_detail.warm.median_seconds": (
            "player_detail",
            "warm",
            "median_seconds",
        ),
        "player_detail.warm.p95_seconds": (
            "player_detail",
            "warm",
            "p95_seconds",
        ),
        "five_container_inventory.median_seconds": (
            "five_container_inventory",
            "median_seconds",
        ),
        "five_container_inventory.p95_seconds": (
            "five_container_inventory",
            "p95_seconds",
        ),
    }
    time_metrics = {
        name: (get(result, path), get(baseline, path))
        for name, path in time_metric_paths.items()
    }
    result_saves = {
        value["operation_count"]: value for value in result["save_changesets"]
    }
    baseline_saves = {
        value["operation_count"]: value for value in baseline["save_changesets"]
    }
    for operation_count in (1, 10, 100):
        for statistic in ("median_seconds", "p95_seconds"):
            key = f"save_changesets.{operation_count}.{statistic}"
            time_metrics[key] = (
                result_saves[operation_count][statistic],
                baseline_saves[operation_count][statistic],
            )
    memory_metrics = {
        "open.python_peak_bytes": (
            result["open"]["python_peak_bytes"],
            baseline["open"]["python_peak_bytes"],
        ),
        "memory.read_phase_python_peak_bytes": (
            result["memory"]["read_phase_python_peak_bytes"],
            baseline["memory"]["read_phase_python_peak_bytes"],
        ),
        "memory.process_peak_working_set_bytes": (
            result["memory"]["process_peak_working_set_bytes"],
            baseline["memory"]["process_peak_working_set_bytes"],
        ),
    }
    ratios: dict[str, float] = {}
    violations: list[dict[str, object]] = []
    invariant_paths = {
        "open.player_file_count": ("open", "player_file_count"),
        "open.player_files_loaded": ("open", "player_files_loaded"),
        "open.player_file_reads": ("open", "player_file_reads"),
        "player_summary.result_count": ("player_summary", "result_count"),
        "player_detail.reads_before": ("player_detail", "reads_before"),
        "player_detail.reads_after_cold": (
            "player_detail",
            "reads_after_cold",
        ),
        "player_detail.reads_after_warm": (
            "player_detail",
            "reads_after_warm",
        ),
        "five_container_inventory.container_count": (
            "five_container_inventory",
            "container_count",
        ),
    }
    for name, path in invariant_paths.items():
        observed = get(result, path)
        expected = get(baseline, path)
        if observed != expected:
            violations.append(
                {
                    "metric": name,
                    "baseline": expected,
                    "observed": observed,
                    "kind": "invariant",
                }
            )
    for operation_count in (1, 10, 100):
        for field in ("written_files", "backup_bytes", "staging_bytes"):
            observed = result_saves[operation_count][field]
            expected = baseline_saves[operation_count][field]
            if observed != expected:
                violations.append(
                    {
                        "metric": f"save_changesets.{operation_count}.{field}",
                        "baseline": expected,
                        "observed": observed,
                        "kind": "invariant",
                    }
                )
    for threshold, metrics in (
        (max_time_ratio, time_metrics),
        (max_memory_ratio, memory_metrics),
    ):
        for name, (observed, expected) in metrics.items():
            if observed is None or expected is None or expected <= 0:
                raise RuntimeError(f"Performance metric {name} is not comparable")
            ratio = observed / expected
            ratios[name] = ratio
            if ratio > threshold:
                violations.append(
                    {
                        "metric": name,
                        "baseline": expected,
                        "observed": observed,
                        "ratio": ratio,
                        "maximum_ratio": threshold,
                    }
                )
    return {
        "max_time_ratio": max_time_ratio,
        "max_memory_ratio": max_memory_ratio,
        "ratios": ratios,
        "violations": violations,
        "passed": not violations,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--fixture-id")
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--max-time-ratio", type=float, default=2.0)
    parser.add_argument("--max-memory-ratio", type=float, default=1.25)
    args = parser.parse_args()
    result = measure(args.fixtures.resolve(), args.fixture_id)
    if args.baseline is not None:
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        result["regression_check"] = compare_to_baseline(
            result,
            baseline,
            max_time_ratio=args.max_time_ratio,
            max_memory_ratio=args.max_memory_ratio,
        )
    print("PERFORMANCE_BASELINE_JSON")
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    if args.baseline is not None and not result["regression_check"]["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
