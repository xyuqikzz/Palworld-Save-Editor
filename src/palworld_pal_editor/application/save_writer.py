from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from typing import Any, Callable
import uuid

from palworld_save_tools.gvas import GvasFile
from palworld_save_tools.palsav import compress_gvas_to_sav, decompress_sav_to_gvas
from palworld_save_tools.paltypes import PALWORLD_TYPE_HINTS

from palworld_pal_editor.core.group_data import GroupData
from palworld_pal_editor.core.item_container_data import ItemContainerData
from palworld_pal_editor.core.character_index import (
    CharacterIndex,
    inspect_decoded_character_graph,
)
from palworld_pal_editor.core.dynamic_item_data import DynamicItemData
from palworld_pal_editor.core.guild_item_storage_data import GuildItemStorageData
from palworld_pal_editor.core.pal_objects import UUID2HexStr
from palworld_pal_editor.core.save_manager import MAIN_SKIP_PROPERTIES, PLAYER_SKIP_PROPERTIES
from palworld_pal_editor.domain.errors import DomainError, stale_revision
from palworld_pal_editor.domain.models import (
    SavePlatform,
    SaveResult,
    StorageCommitRequest,
)

from .local_data import LOCAL_DATA_RELATIVE_PATH, LocalDataDocument
from .fast_travel import PlayerFastTravelData
from .save_session import SaveSession


class SaveWriter:
    """Verified backup, staging, replacement, and recovery for one SaveSession."""

    def __init__(
        self,
        *,
        failure_hook: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self._failure_hook = failure_hook

    def save(
        self,
        session: SaveSession,
        target: str | Path | None,
        expected_revision: int,
    ) -> SaveResult:
        if expected_revision != session.revision:
            raise stale_revision(expected_revision, session.revision)
        target_path = Path(target).resolve() if target is not None else None
        if session.platform is SavePlatform.XGP and target_path is not None:
            raise DomainError(
                code="WGS_COMMIT_FAILED",
                message="Game Pass saves can only be written back to the original slot.",
                field="target",
                http_status=400,
            )
        changes = session.changes()
        if not changes:
            return SaveResult(
                revision=session.revision,
                backup_path=None,
                staging_path=None,
                written_files=(),
                manifest=(),
                staged_reload_verified=True,
                target_reload_verified=True,
                platform=session.platform.value,
                source_reloaded=True,
                cloud_sync_verified=(
                    False if session.platform is SavePlatform.XGP else None
                ),
            )
        self._validate_global_invariants(session)
        files = self._modified_files(session)
        for relative_path in files:
            if not session.file_unchanged_since_open(relative_path):
                raise DomainError(
                    code="SAVE_TARGET_CHANGED",
                    message="A save file changed on disk after this session opened.",
                    details={"path": relative_path},
                    retryable=True,
                    http_status=409,
                )

        operation_id = str(uuid.uuid4())
        if session.platform is SavePlatform.STEAM:
            target_path = target_path or session.source.resolve()
            staging_path = (
                target_path.parent
                / f".{target_path.name}.pal-editor-staging-{operation_id}"
            )
        else:
            staging_path = Path(
                tempfile.mkdtemp(prefix=f"palworld-editor-stage-{operation_id}-")
            ).resolve()
        try:
            if session.platform is SavePlatform.STEAM:
                if target_path == session.source.resolve():
                    staging_path.mkdir(parents=False, exist_ok=False)
                else:
                    shutil.copytree(session.workspace, staging_path)
            self._serialize_to_staging(session, staging_path, files)
            self._verify_staged(staging_path, files, session=session)
            commit = session.storage.commit(
                StorageCommitRequest(
                    opened=session.opened_save,
                    staged_workspace=staging_path,
                    changed_files=tuple(PurePosixPath(path) for path in files),
                    expected_revision=expected_revision,
                    target_path=target_path,
                    verify_file=lambda path, relative_path: (
                        self._reload_session_file(
                            session, path, relative_path
                        )
                    ),
                    failure_hook=self._failure_hook,
                )
            )
        except DomainError as error:
            if session.platform is SavePlatform.XGP and error.code in {
                "SERIALIZATION_FAILED",
                "STAGED_RELOAD_FAILED",
            }:
                raise DomainError(
                    code="WGS_STAGE_FAILED",
                    message="The changed Game Pass save could not be staged and verified.",
                    details={"staging_path": str(staging_path)},
                    http_status=500,
                ) from error
            raise

        session.mark_saved(expected_revision)
        if staging_path.exists():
            shutil.rmtree(staging_path)
        return SaveResult(
            revision=session.revision,
            backup_path=str(commit.backup_path) if commit.backup_path else None,
            staging_path=None,
            written_files=tuple(path.as_posix() for path in commit.written_files),
            manifest=commit.manifest,
            staged_reload_verified=True,
            target_reload_verified=commit.source_reloaded,
            platform=commit.platform.value,
            manifest_path=(
                str(commit.manifest_path) if commit.manifest_path else None
            ),
            source_reloaded=commit.source_reloaded,
            recovery_status=commit.recovery_status,
            journal_path=str(commit.journal_path) if commit.journal_path else None,
            cloud_sync_verified=(
                False if commit.platform is SavePlatform.XGP else None
            ),
        )

    def export_steam_copy(
        self,
        session: SaveSession,
        target: str | Path,
        expected_revision: int,
    ) -> SaveResult:
        if expected_revision != session.revision:
            raise stale_revision(expected_revision, session.revision)
        target_path = Path(target).resolve()
        if target_path.exists() or not target_path.parent.is_dir():
            raise DomainError(
                code="INVALID_SAVE_TARGET",
                message="The Steam export target must be a new directory with an existing parent.",
                field="target",
                http_status=409,
            )
        staging = target_path.parent / f".{target_path.name}.steam-export-{uuid.uuid4()}"
        try:
            shutil.copytree(session.workspace, staging)
            files = self._modified_files(session) if session.changes() else []
            if files:
                self._validate_global_invariants(session)
                self._serialize_to_staging(session, staging, files)
                self._verify_staged(staging, files, session=session)
            os.replace(staging, target_path)
            self._verify_staged(
                target_path,
                files or ["Level.sav"],
                session=session if files else None,
            )
        except Exception as error:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            if isinstance(error, DomainError):
                raise
            raise DomainError(
                code="WGS_STAGE_FAILED" if session.platform is SavePlatform.XGP else "WRITE_FAILED",
                message="The Steam-format copy could not be exported safely.",
                http_status=500,
            ) from error
        return SaveResult(
            revision=session.revision,
            backup_path=None,
            staging_path=None,
            written_files=tuple(files),
            manifest=(),
            staged_reload_verified=True,
            target_reload_verified=True,
            platform=SavePlatform.STEAM.value,
            source_reloaded=False,
            recovery_status="not_needed",
        )

    def _modified_files(self, session: SaveSession) -> list[str]:
        files: set[str] = set()
        for change in session.changes():
            for record in change.get("affected_records", []):
                if record.startswith("level:"):
                    files.add("Level.sav")
                elif record.startswith("player_file:"):
                    player_id = record.split(":", 1)[1]
                    files.add(f"Players/{UUID2HexStr(player_id)}.sav")
                elif record == "local_data":
                    files.add(LOCAL_DATA_RELATIVE_PATH)
        if not files:
            raise DomainError(
                code="INVARIANT_VIOLATION",
                message="Pending changes do not identify any save file.",
                http_status=409,
            )
        return sorted(files)

    def _validate_global_invariants(self, session: SaveSession) -> None:
        manager = session.manager
        containers = getattr(manager, "item_container_data", None)
        if containers is not None:
            for container in containers.container_map.values():
                dense = container.dense_slots()
                if len(dense) != container.capacity:
                    raise DomainError(
                        code="INVARIANT_VIOLATION",
                        message="An item container does not match its declared capacity.",
                        http_status=409,
                    )
        character_containers = getattr(manager, "container_data", None)
        if character_containers is not None:
            for container in character_containers.container_map.values():
                if not container.capacity_matches_declared(container.size):
                    raise DomainError(
                        code="INVARIANT_VIOLATION",
                        message=(
                            "A character container does not match its "
                            "declared capacity."
                        ),
                        http_status=409,
                    )
        dynamic_items = getattr(manager, "dynamic_item_data", None)
        if dynamic_items is not None:
            dynamic_items.assert_no_new_issues(
                session.dynamic_item_issue_baseline
            )
        if all(
            hasattr(manager, field)
            for field in (
                "_entities_list",
                "container_data",
                "group_data",
                "player_mapping",
                "baseworker_mapping",
                "_dangling_pals",
            )
        ):
            issues = CharacterIndex(manager).hard_issues()
            if issues:
                raise DomainError(
                    code="CHARACTER_INDEX_INVARIANT_FAILED",
                    message="Character records and their references are inconsistent.",
                    details={
                        "issues": [issue.to_dict() for issue in issues]
                    },
                    http_status=409,
                )

    def _serialize_to_staging(
        self, session: SaveSession, staging_path: Path, files: list[str]
    ) -> None:
        manager = session.manager
        try:
            for relative_path in files:
                output = staging_path / Path(relative_path)
                output.parent.mkdir(parents=True, exist_ok=True)
                if relative_path == "Level.sav":
                    gvas = deepcopy(manager.gvas_file)
                    data = compress_gvas_to_sav(
                        gvas.write(MAIN_SKIP_PROPERTIES), manager._compression_times
                    )
                elif relative_path == LOCAL_DATA_RELATIVE_PATH:
                    data = session.local_data.serialize_bytes()
                else:
                    player_hex = Path(relative_path).stem
                    player = next(
                        (
                            value
                            for value in manager.player_mapping.values()
                            if UUID2HexStr(value.PlayerUId) == player_hex
                        ),
                        None,
                    )
                    if player is None or player.PlayerGVAS is None:
                        raise KeyError(relative_path)
                    player_gvas, compression_times = player.PlayerGVAS
                    data = compress_gvas_to_sav(
                        deepcopy(player_gvas).write(PLAYER_SKIP_PROPERTIES),
                        compression_times,
                    )
                with output.open("wb") as stream:
                    stream.write(data)
                self._fail("after_serialize", {"path": relative_path})
        except Exception as error:
            raise DomainError(
                code="SERIALIZATION_FAILED",
                message="The modified save files could not be serialized.",
                details={"staging_path": str(staging_path)},
                http_status=500,
            ) from error

    def _verify_staged(
        self,
        root: Path,
        files: list[str],
        *,
        session: SaveSession | None = None,
    ) -> None:
        try:
            reloaded: dict[str, GvasFile] = {}
            for relative_path in files:
                path = root / Path(relative_path)
                reloaded[relative_path] = (
                    self._reload_session_file(session, path, relative_path)
                    if session is not None
                    else self._reload_file(path, relative_path)
                )
            if session is not None:
                self._verify_change_postconditions(session, reloaded)
        except Exception as error:
            raise DomainError(
                code="STAGED_RELOAD_FAILED",
                message="A staged save file could not be reloaded.",
                details={"root": str(root)},
                http_status=500,
            ) from error

    def _verify_change_postconditions(
        self,
        session: SaveSession,
        reloaded: dict[str, GvasFile],
    ) -> None:
        chest_expected: dict[str, int] = {}
        level_expected: dict[str, int] = {}
        player_inventory_expected: dict[str, int] = {}
        for change in session.changes():
            command = change.get("command")
            target = change.get("target", {})
            after = change.get("after", {})
            guild_id = target.get("guild_id")
            if command == "UpdateGuildChestCapacity":
                capacity = after.get("capacity")
                if (
                    not isinstance(guild_id, str)
                    or isinstance(capacity, bool)
                    or not isinstance(capacity, int)
                ):
                    raise ValueError("Invalid guild chest change postcondition")
                chest_expected[guild_id] = capacity
            elif command == "UpdateGuildBaseCampLevel":
                level = after.get("level")
                if (
                    not isinstance(guild_id, str)
                    or isinstance(level, bool)
                    or not isinstance(level, int)
                ):
                    raise ValueError("Invalid base camp level postcondition")
                level_expected[guild_id] = level
            elif command == "UpdatePlayerInventoryCapacity":
                container_id = target.get("container_id")
                capacity = after.get("capacity")
                if (
                    not isinstance(container_id, str)
                    or isinstance(capacity, bool)
                    or not isinstance(capacity, int)
                ):
                    raise ValueError(
                        "Invalid player inventory capacity postcondition"
                    )
                player_inventory_expected[container_id] = capacity
        if not (
            chest_expected
            or level_expected
            or player_inventory_expected
        ):
            return

        level = reloaded.get("Level.sav")
        if level is None:
            raise ValueError("Guild changes require a reloaded Level.sav")
        if chest_expected:
            guild_storage = GuildItemStorageData(level)
            item_containers = ItemContainerData(level)
            for guild_id, capacity in chest_expected.items():
                binding = guild_storage.get(guild_id)
                if binding is None:
                    raise ValueError("Reloaded guild chest mapping is missing")
                container = item_containers.get(binding.container_id)
                if (
                    container is None
                    or not container.capacity_matches_declared(capacity)
                ):
                    raise ValueError(
                        "Reloaded guild chest capacity does not match staging"
                    )
        if player_inventory_expected:
            item_containers = ItemContainerData(level)
            for container_id, capacity in player_inventory_expected.items():
                container = item_containers.get(container_id)
                if (
                    container is None
                    or not container.capacity_matches_declared(capacity)
                ):
                    raise ValueError(
                        "Reloaded player inventory capacity does not match staging"
                    )
        if level_expected:
            groups = GroupData(level)
            for guild_id, expected_level in level_expected.items():
                group = groups.get_group(guild_id)
                if (
                    group is None
                    or group.base_camp_level != expected_level
                ):
                    raise ValueError(
                        "Reloaded base camp level does not match staging"
                    )
    def _reload_session_file(
        self,
        session: SaveSession,
        path: Path,
        relative_path: str,
    ) -> GvasFile:
        if relative_path == LOCAL_DATA_RELATIVE_PATH:
            return session.local_data.verify_reloaded_file(path)
        allowed_dynamic_item_issues = (
            session.dynamic_item_issue_baseline
            if relative_path == "Level.sav"
            else ()
        )
        reloaded = self._reload_file(
            path,
            relative_path,
            allowed_dynamic_item_issues=allowed_dynamic_item_issues,
        )
        self._verify_fast_travel_reload(session, relative_path, reloaded)
        return reloaded

    @staticmethod
    def _verify_fast_travel_reload(
        session: SaveSession,
        relative_path: str,
        reloaded: GvasFile,
    ) -> None:
        if not relative_path.startswith("Players/"):
            return
        player_hex = Path(relative_path).stem
        player_id = next(
            (
                change.get("target", {}).get("player_id")
                for change in session.changes()
                if change.get("command") == "UnlockAllFastTravelPoints"
                and isinstance(change.get("target"), dict)
                and isinstance(change["target"].get("player_id"), str)
                and UUID2HexStr(change["target"]["player_id"]) == player_hex
            ),
            None,
        )
        if player_id is None:
            return
        player = session.manager.get_player(player_id)
        if player is None:
            raise ValueError("Fast-travel player is no longer loaded")
        current = PlayerFastTravelData.from_player(player)
        current.verify_reloaded(PlayerFastTravelData.from_gvas(reloaded))

    def _reload_file(
        self,
        path: Path,
        relative_path: str,
        *,
        allowed_dynamic_item_issues: tuple[str, ...] = (),
    ) -> GvasFile:
        if relative_path == LOCAL_DATA_RELATIVE_PATH:
            document = LocalDataDocument.open_file(path)
            document.require_resettable()
            if document.gvas_file is None:
                raise ValueError("LocalData.sav did not reload")
            return document.gvas_file
        raw, _compression = decompress_sav_to_gvas(path.read_bytes())
        properties = MAIN_SKIP_PROPERTIES if relative_path == "Level.sav" else PLAYER_SKIP_PROPERTIES
        gvas = GvasFile.read(raw, PALWORLD_TYPE_HINTS, properties)
        if relative_path == "Level.sav":
            world = gvas.properties.get("worldSaveData")
            if world is not None:
                containers = ItemContainerData(gvas)
                DynamicItemData(gvas, containers).assert_no_new_issues(
                    allowed_dynamic_item_issues
                )
                character_issues = [
                    issue
                    for issue in inspect_decoded_character_graph(gvas)
                    if not issue.recoverable
                ]
                if character_issues:
                    raise DomainError(
                        code="CHARACTER_INDEX_INVARIANT_FAILED",
                        message="Reloaded character references are inconsistent.",
                        details={
                            "issues": [
                                issue.to_dict() for issue in character_issues
                            ]
                        },
                        http_status=409,
                    )
        return gvas

    def _fail(self, stage: str, context: dict[str, Any]) -> None:
        if self._failure_hook is not None:
            self._failure_hook(stage, context)
