from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
from threading import RLock

from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.domain.models import SavePlatform, SaveSource

from .wgs_format import WgsFormatError, WgsIndex, parse_index


PALWORLD_PACKAGE = "PocketpairInc.Palworld_ad4psfrxyesvt"
_USER_DIRECTORY = re.compile(r"^[0-9A-Fa-f]{16}_[0-9A-Fa-f]{32}$")
_PLAYER_ID = re.compile(
    r"^(?:[0-9A-Fa-f]{32}|[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-"
    r"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12})$"
)
_SLOT_WORLD = re.compile(r"^(?P<world>.+)-Slot(?P<slot>[1-9][0-9]*)$", re.IGNORECASE)


def default_wgs_roots() -> tuple[Path, ...]:
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return ()
    packages = Path(local) / "Packages"
    candidates = [packages / PALWORLD_PACKAGE / "SystemAppData" / "wgs"]
    try:
        candidates.extend(
            package / "SystemAppData" / "wgs"
            for package in packages.glob("PocketpairInc.Palworld_*")
        )
    except OSError:
        pass
    unique: dict[str, Path] = {}
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        unique[str(resolved).casefold()] = resolved
    return tuple(unique.values())


def split_container_name(name: str) -> tuple[str, PurePosixPath] | None:
    # WGS counted UTF-16 strings commonly include their trailing NUL in the
    # encoded length. Keep that byte-for-byte in the format model, but exclude
    # it from Palworld's logical container-name semantics.
    name = name.rstrip("\0")
    level_file_marker = "-Level-01"
    if name.endswith(level_file_marker) and len(name) > len(level_file_marker):
        return name[: -len(level_file_marker)], PurePosixPath("Level.sav")
    for suffix in ("LevelMeta", "LocalData", "WorldOption", "Level"):
        marker = f"-{suffix}"
        if name.endswith(marker) and len(name) > len(marker):
            return name[: -len(marker)], PurePosixPath(f"{suffix}.sav")
    marker = "-Players-"
    if marker in name:
        world_id, player_id = name.rsplit(marker, 1)
        if world_id and _PLAYER_ID.fullmatch(player_id):
            normalized = player_id.replace("-", "").upper()
            return world_id, PurePosixPath("Players") / f"{normalized}.sav"
    return None


def world_bindings(index: WgsIndex) -> dict[str, dict[str, list[int]]]:
    result: dict[str, dict[str, list[int]]] = {}
    for position, entry in enumerate(index.entries):
        mapping = split_container_name(entry.name)
        if mapping is None:
            continue
        world_id, relative_path = mapping
        result.setdefault(world_id, {}).setdefault(relative_path.as_posix(), []).append(
            position
        )
    return result


def _source_id(user_directory: Path, world_id: str) -> str:
    digest = hashlib.sha256()
    digest.update(b"palworld-editor-xgp-source-v1\0")
    digest.update(str(user_directory.resolve()).casefold().encode("utf-8"))
    digest.update(b"\0")
    digest.update(world_id.encode("utf-8"))
    return "xgp-" + digest.hexdigest()


class XgpSourceCatalog:
    """Discovers WGS slots and retains the trusted source-id mapping."""

    def __init__(self, *, roots: tuple[Path, ...] | None = None) -> None:
        selected_roots = default_wgs_roots() if roots is None else roots
        self._default_roots = tuple(path.resolve() for path in selected_roots)
        self._trusted_roots = set(self._default_roots)
        self._lock = RLock()
        self._sources: dict[str, SaveSource] = {}

    @property
    def roots(self) -> tuple[Path, ...]:
        with self._lock:
            return tuple(sorted(self._trusted_roots, key=str))

    def discover(self) -> list[SaveSource]:
        return self._discover_scopes(
            tuple((root, None) for root in self._default_roots)
        )

    def discover_selected(self, selected_path: str | Path) -> list[SaveSource]:
        try:
            selected = Path(selected_path).resolve(strict=True)
        except (OSError, RuntimeError) as error:
            raise DomainError(
                code="WGS_NOT_FOUND",
                message="The selected Game Pass save folder does not exist.",
                field="path",
                retryable=True,
                http_status=404,
            ) from error
        if not selected.is_dir() or self._is_excluded_directory(selected):
            raise DomainError(
                code="WGS_NOT_FOUND",
                message="The selected folder is not an active Game Pass WGS folder.",
                field="path",
                retryable=True,
                http_status=404,
            )
        if (selected / "containers.index").is_file():
            root = selected.parent.resolve()
            scopes = ((root, (selected,)),)
        else:
            root = selected
            scopes = ((root, None),)
        discovered = self._discover_scopes(scopes)
        if not discovered:
            raise DomainError(
                code="WGS_NOT_FOUND",
                message=(
                    "The selected folder contains no readable Palworld "
                    "Game Pass world slots."
                ),
                field="path",
                retryable=True,
                http_status=404,
            )
        with self._lock:
            self._trusted_roots.add(root)
        return discovered

    @staticmethod
    def _is_excluded_directory(path: Path) -> bool:
        folded = path.name.casefold()
        return folded == "t" or "backup" in folded or "temp" in folded

    def _discover_scopes(
        self,
        scopes: tuple[tuple[Path, tuple[Path, ...] | None], ...],
    ) -> list[SaveSource]:
        existing_roots: list[Path] = []
        discovered: list[SaveSource] = []
        first_error: DomainError | None = None
        for root, selected_users in scopes:
            try:
                if not root.is_dir():
                    continue
                existing_roots.append(root)
                user_directories = (
                    list(selected_users)
                    if selected_users is not None
                    else sorted(
                        path
                        for path in root.iterdir()
                        if path.is_dir()
                        and not self._is_excluded_directory(path)
                        and _USER_DIRECTORY.fullmatch(path.name)
                    )
                )
            except PermissionError as error:
                first_error = DomainError(
                    code="WGS_NOT_FOUND",
                    message="The Palworld WGS directory cannot be read.",
                    retryable=True,
                    http_status=403,
                )
                first_error.__cause__ = error
                continue
            except OSError:
                continue
            for user_directory in user_directories:
                index_path = user_directory / "containers.index"
                try:
                    index = parse_index(index_path.read_bytes())
                    bindings = world_bindings(index)
                    updated_at = datetime.fromtimestamp(
                        index_path.stat().st_mtime, timezone.utc
                    )
                except (OSError, WgsFormatError) as error:
                    first_error = DomainError(
                        code="WGS_INDEX_UNSUPPORTED",
                        message="A Palworld WGS index is incomplete or unsupported.",
                        retryable=False,
                        http_status=422,
                    )
                    first_error.__cause__ = error
                    continue
                for world_id, logical in sorted(bindings.items()):
                    if "Level.sav" not in logical:
                        continue
                    ambiguous = any(len(positions) != 1 for positions in logical.values())
                    slot_match = _SLOT_WORLD.fullmatch(world_id)
                    redacted_world_id = (
                        slot_match.group("world") if slot_match is not None else world_id
                    )
                    short_id = redacted_world_id[:8].upper()
                    slot_label = (
                        f" · Slot {slot_match.group('slot')}"
                        if slot_match is not None
                        else ""
                    )
                    discovered.append(
                        SaveSource(
                            platform=SavePlatform.XGP,
                            canonical_path=user_directory.resolve(),
                            source_id=_source_id(user_directory, world_id),
                            display_name=f"Game Pass · World {short_id}{slot_label}",
                            world_id=world_id,
                            updated_at=updated_at,
                            status="ambiguous" if ambiguous else "available",
                        )
                    )
        if not existing_roots:
            raise DomainError(
                code="WGS_NOT_FOUND",
                message="No Palworld Game Pass WGS directory was found.",
                retryable=True,
                http_status=404,
            )
        if not discovered and first_error is not None:
            raise first_error
        discovered.sort(key=lambda source: (source.updated_at or datetime.min.replace(tzinfo=timezone.utc), source.world_id or ""))
        with self._lock:
            self._sources.update(
                {source.source_id: source for source in discovered}
            )
        return discovered

    def resolve(self, source_id: str) -> SaveSource:
        with self._lock:
            source = self._sources.get(source_id)
        if source is None:
            raise DomainError(
                code="WGS_NOT_FOUND",
                message="The selected Game Pass save source is no longer available.",
                field="sourceId",
                retryable=True,
                http_status=404,
            )
        return source


SOURCE_CATALOG = XgpSourceCatalog()
