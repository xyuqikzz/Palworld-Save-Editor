import os
from ipaddress import ip_address
from pathlib import Path
import traceback
from flask import Blueprint, request
from flask_jwt_extended import jwt_required
import asyncio

from palworld_pal_editor.config import (
    PROGRAM_PATH,
    PROJECT_RELEASES_URL,
    Config,
    version_info,
    is_gh_build,
    get_new_version,
)
from palworld_pal_editor.core import SaveManager
from palworld_pal_editor.application.runtime import SESSION_RUNTIME
from palworld_pal_editor.application.character_reference_repair import (
    CharacterReferenceRepairer,
)
from palworld_pal_editor.domain.models import SavePlatform
from palworld_pal_editor.storage.discovery import SOURCE_CATALOG
from palworld_pal_editor.application.save_writer import SaveWriter
from palworld_pal_editor.application.query_service import SaveQueryService
from palworld_pal_editor.application.character_editor import CharacterEditor
from palworld_pal_editor.application.expedition_editor import ExpeditionEditor
from palworld_pal_editor.application.guild_base_editor import GuildBaseEditor
from palworld_pal_editor.application.guild_editor import GuildEditor
from palworld_pal_editor.application.guild_chest_editor import GuildChestEditor
from palworld_pal_editor.application.base_storage_editor import BaseStorageEditor
from palworld_pal_editor.application.fog_of_war_editor import FogOfWarEditor
from palworld_pal_editor.domain.commands import (
    ClearFogOfWar,
    CompleteActiveExpeditions,
    CompleteExpedition,
    HealAllPals,
    RepairMissingGuildHandles,
    ResetFogOfWar,
    UnlockAllExpeditionPals,
    UpdateGuildBaseCampLevel,
    UpdateGuildChestCapacity,
    UpdateGuildName,
    UpdateGuildOwner,
    ClearBaseStorageItemSlot,
    PutBaseStorageItem,
    UpdateBaseStorageItemCount,
)
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.utils import LOGGER, DataProvider
from palworld_pal_editor.utils.util import (
    get_filesystem_root_context,
    get_path_context,
    reply,
)

save_blueprint = Blueprint("save", __name__)

_SAVE_DIAGNOSTIC_ERROR_CODES = frozenset(
    {
        "BACKUP_FAILED",
        "RECOVERY_FAILED",
        "SAVE_TARGET_CHANGED",
        "WGS_BACKUP_FAILED",
        "WGS_COMMIT_FAILED",
        "WGS_GAME_RUNNING",
        "WGS_RECOVERY_FAILED",
        "WGS_RELOAD_FAILED",
        "WGS_SOURCE_CHANGED",
        "WRITE_FAILED",
    }
)


def _request_is_loopback() -> bool:
    try:
        return ip_address(request.remote_addr or "").is_loopback
    except ValueError:
        return False


def _select_native_directory(initial_directory: str) -> str | None:
    if os.name != "nt":
        raise OSError("The native Windows folder picker is unavailable.")
    from palworld_pal_editor.windows_dialog import choose_folder

    return choose_folder(initial_directory)


def _native_picker_initial_directory(requested_path: object) -> str:
    for candidate in (requested_path, Config.path, PROGRAM_PATH):
        if not isinstance(candidate, (str, os.PathLike)):
            continue
        try:
            resolved = Path(candidate).resolve(strict=True)
        except (OSError, RuntimeError, ValueError):
            continue
        if resolved.is_dir():
            return str(resolved)
    return ""


def _default_steam_save_path() -> str | None:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return None

    save_games = Path(local_app_data) / "Pal" / "Saved" / "SaveGames"
    if not save_games.is_dir():
        return None

    candidates: list[tuple[int, str, Path]] = []
    try:
        level_saves = save_games.glob("*/*/Level.sav")
        for level_save in level_saves:
            world_path = level_save.parent
            if not (world_path / "Players").is_dir():
                continue
            try:
                modified_at = level_save.stat().st_mtime_ns
                resolved_path = world_path.resolve()
            except OSError:
                continue
            candidates.append(
                (modified_at, str(resolved_path).casefold(), resolved_path)
            )
    except OSError:
        return None

    if not candidates:
        return None
    return str(max(candidates, key=lambda candidate: candidate[:2])[2])


@save_blueprint.route("/fetch_config", methods=["GET"])
def fetch_config():
    return reply(
        0,
        {
            "I18n": Config.i18n,
            "I18nList": DataProvider.get_i18n_map(),
            "Path": Config.path or _default_steam_save_path(),
            "HasPassword": bool(Config.password),
            "VERSION": version_info(),
            "IsOfficialBuild": is_gh_build(),
            "MaxSoulsLevel": Config.max_souls_level,
            "MaxSuitabilityLevel": Config.max_suitability_level,
        },
    )


@save_blueprint.route("/load", methods=["POST"])
# @LOGGER.api_logger
@jwt_required()
def load():
    payload = request.get_json(silent=True) or {}
    path = payload.get("ReadPath") or payload.get("path")
    source_id = payload.get("sourceId")
    if path and source_id:
        error = DomainError(
            code="INVALID_REQUEST",
            message="ReadPath and sourceId are mutually exclusive.",
            http_status=400,
        )
        return reply(1, msg=error.message, error=error.to_dict()), error.http_status
    path = path or (None if source_id else Config.path)
    try:
        if source_id:
            session = SESSION_RUNTIME.open_source(source_id)
            return reply(
                0,
                {
                    "session": session.summary().to_dict(),
                    "compatibility": session.compatibility().to_dict(),
                },
            )
        if path:
            session = SESSION_RUNTIME.open(path)
            Config.path = path
            Config.save_to_file(PROGRAM_PATH / "config.json")
            return reply(
                0,
                {
                    "session": session.summary().to_dict(),
                    "compatibility": session.compatibility().to_dict(),
                },
            )
    except DomainError as error:
        return (
            reply(1, msg=error.message, error=error.to_dict()),
            error.http_status,
        )
    except Exception as e:
        stack_trace = traceback.format_exc()
        LOGGER.error(f"Error Loading Save {stack_trace}")
        return reply(
            1,
            msg=f"Error occored during loading, please make sure both the editor and your game save is up to date! Check debug console for further details.",
        )

    LOGGER.warning(f"Failed to load, check path: {path}")
    return reply(1, None, f"Failed to load, check path: {path}")


@save_blueprint.route("/sources", methods=["GET", "POST"])
@jwt_required()
def discover_sources():
    try:
        if request.method == "POST":
            payload = request.get_json(silent=True)
            if not isinstance(payload, dict) or not payload.get("path"):
                raise DomainError(
                    code="INVALID_REQUEST",
                    message="A Game Pass WGS folder path is required.",
                    field="path",
                    http_status=400,
                )
            sources = SOURCE_CATALOG.discover_selected(payload["path"])
        else:
            sources = SOURCE_CATALOG.discover()
        return reply(
            0,
            {"sources": [source.to_public_dict() for source in sources]},
        )
    except DomainError as error:
        return reply(1, msg=error.message, error=error.to_dict()), error.http_status


@save_blueprint.route("/browse-directory", methods=["POST"])
@jwt_required()
def browse_directory():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        error = DomainError(
            code="INVALID_REQUEST",
            message="The request body must be a JSON object.",
            http_status=400,
        )
        return reply(1, msg=error.message, error=error.to_dict()), error.http_status
    raw_path = payload.get("path") or Config.path or str(PROGRAM_PATH)
    try:
        current_path = Path(raw_path).resolve(strict=True)
        if (
            current_path.is_file()
            and current_path.name.casefold() == "containers.index"
        ):
            current_path = current_path.parent
        if payload.get("parent") is True:
            parent_path = current_path.parent.resolve(strict=True)
            if parent_path == current_path:
                return reply(0, get_filesystem_root_context())
            current_path = parent_path
        if not current_path.is_dir():
            raise OSError("not a directory")
        return reply(0, get_path_context(current_path))
    except (OSError, RuntimeError, ValueError) as cause:
        error = DomainError(
            code="INVALID_SAVE_PATH",
            message="The selected directory cannot be read.",
            field="path",
            http_status=400,
        )
        error.__cause__ = cause
        return reply(1, msg=error.message, error=error.to_dict()), error.http_status


@save_blueprint.route("/browse-roots", methods=["GET"])
@jwt_required()
def browse_roots():
    return reply(0, get_filesystem_root_context())


@save_blueprint.route("/select-directory", methods=["POST"])
@jwt_required()
def select_directory():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        error = DomainError(
            code="INVALID_REQUEST",
            message="The request body must be a JSON object.",
            http_status=400,
        )
        return reply(1, msg=error.message, error=error.to_dict()), error.http_status
    if not _request_is_loopback():
        error = DomainError(
            code="NATIVE_DIALOG_LOCAL_ONLY",
            message="The system directory picker is only available to local clients.",
            http_status=403,
        )
        return reply(1, msg=error.message, error=error.to_dict()), error.http_status

    initial_directory = _native_picker_initial_directory(payload.get("path"))
    try:
        selected = _select_native_directory(initial_directory)
        if selected is None:
            return reply(0, {"path": None, "cancelled": True})
        selected_path = Path(selected).resolve(strict=True)
        if not selected_path.is_dir():
            raise OSError("The native picker returned a non-directory path.")
        return reply(
            0,
            {
                "path": str(selected_path),
                "cancelled": False,
            },
        )
    except (OSError, RuntimeError, ValueError):
        LOGGER.warning(
            "The local web system directory picker failed; the client may "
            f"use its fallback: {traceback.format_exc()}"
        )
        error = DomainError(
            code="NATIVE_DIALOG_UNAVAILABLE",
            message="The system directory picker is unavailable.",
            http_status=503,
        )
        return reply(1, msg=error.message, error=error.to_dict()), error.http_status


@save_blueprint.route("/session", methods=["GET"])
@jwt_required()
def get_session():
    try:
        session = SESSION_RUNTIME.get(request.args.get("session_id"))
        return reply(
            0,
            {
                "session": session.summary().to_dict(),
                "compatibility": session.compatibility().to_dict(),
            },
        )
    except DomainError as error:
        return (
            reply(1, msg=error.message, error=error.to_dict()),
            error.http_status,
        )


@save_blueprint.route("/session", methods=["DELETE"])
@jwt_required()
def close_session():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        error = DomainError(
            code="INVALID_REQUEST",
            message="The request body must be a JSON object.",
            http_status=400,
        )
        return reply(1, msg=error.message, error=error.to_dict()), error.http_status
    try:
        result = SESSION_RUNTIME.close(
            payload.get("session_id"),
            payload.get("expected_revision"),
            discard_changes=payload.get("discard_changes", False),
        )
        return reply(0, result)
    except DomainError as error:
        return (
            reply(1, msg=error.message, error=error.to_dict()),
            error.http_status,
        )


@save_blueprint.route("/reload", methods=["POST"])
@jwt_required()
def reload_session():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        error = DomainError(
            code="INVALID_REQUEST",
            message="The request body must be a JSON object.",
            http_status=400,
        )
        return reply(1, msg=error.message, error=error.to_dict()), error.http_status
    try:
        session, discarded_change_count = SESSION_RUNTIME.reload(
            payload.get("session_id"),
            payload.get("expected_revision"),
            discard_changes=payload.get("discard_changes", False),
        )
        return reply(
            0,
            {
                "session": session.summary().to_dict(),
                "compatibility": session.compatibility().to_dict(),
                "discarded_change_count": discarded_change_count,
            },
        )
    except DomainError as error:
        return (
            reply(1, msg=error.message, error=error.to_dict()),
            error.http_status,
        )
    except Exception:
        stack_trace = traceback.format_exc()
        LOGGER.error(f"Error refreshing save {stack_trace}")
        return reply(
            1,
            msg="Unexpected error while refreshing; see the local debug log.",
        ), 500


@save_blueprint.route("/changes", methods=["GET"])
@jwt_required()
def get_changes():
    try:
        session = SESSION_RUNTIME.get(request.args.get("session_id"))
        return reply(
            0,
            {
                "session_id": session.session_id,
                "revision": session.revision,
                "changes": session.changes(),
            },
        )
    except DomainError as error:
        return (
            reply(1, msg=error.message, error=error.to_dict()),
            error.http_status,
        )


@save_blueprint.route("/guilds/<guild_id>/commands", methods=["POST"])
@jwt_required()
def execute_guild_command(guild_id: str):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        error = DomainError(
            code="INVALID_REQUEST",
            message="A JSON object is required.",
            http_status=400,
        )
        return reply(1, msg=error.message, error=error.to_dict()), error.http_status
    command_name = payload.get("command")
    command_fields = {
        "update_guild_name": {"name"},
        "update_guild_owner": {"player_id"},
        "update_guild_chest_capacity": {"capacity"},
        "update_base_camp_level": {
            "level",
            "confirm_base_camp_level_lowering",
        },
    }
    if command_name not in command_fields:
        error = DomainError(
            code="UNSUPPORTED_COMMAND",
            message="Unsupported guild command.",
            field="command",
            http_status=400,
        )
        return reply(1, msg=error.message, error=error.to_dict()), error.http_status
    allowed = {
        "session_id",
        "expected_revision",
        "command",
        *command_fields[command_name],
    }
    unknown = sorted(set(payload) - allowed)
    if unknown:
        error = DomainError(
            code="UNSUPPORTED_COMMAND_FIELD",
            message="The request contains unsupported fields.",
            details={"fields": unknown},
            http_status=400,
        )
        return reply(1, msg=error.message, error=error.to_dict()), error.http_status
    try:
        session = SESSION_RUNTIME.get(payload.get("session_id"))
        if command_name == "update_guild_name":
            result = GuildEditor(session).execute(
                UpdateGuildName(
                    session_id=payload.get("session_id"),
                    expected_revision=payload.get("expected_revision"),
                    guild_id=guild_id,
                    name=payload.get("name"),
                )
            )
        elif command_name == "update_guild_owner":
            result = GuildEditor(session).execute(
                UpdateGuildOwner(
                    session_id=payload.get("session_id"),
                    expected_revision=payload.get("expected_revision"),
                    guild_id=guild_id,
                    player_id=payload.get("player_id"),
                )
            )
        elif command_name == "update_guild_chest_capacity":
            result = GuildChestEditor(session).execute(
                UpdateGuildChestCapacity(
                    session_id=payload.get("session_id"),
                    expected_revision=payload.get("expected_revision"),
                    guild_id=guild_id,
                    capacity=payload.get("capacity"),
                )
            )
        else:
            result = GuildBaseEditor(session).execute(
                UpdateGuildBaseCampLevel(
                    session_id=payload.get("session_id"),
                    expected_revision=payload.get("expected_revision"),
                    guild_id=guild_id,
                    level=payload.get("level"),
                    confirm_lowering=(
                        payload.get("confirm_base_camp_level_lowering") is True
                    ),
                )
            )
        return reply(0, result)
    except DomainError as error:
        return reply(1, msg=error.message, error=error.to_dict()), error.http_status


@save_blueprint.route(
    "/guilds/<guild_id>/bases/<base_id>/storage",
    methods=["GET"],
)
@jwt_required()
def get_base_storage(guild_id: str, base_id: str):
    try:
        session = SESSION_RUNTIME.get(request.args.get("session_id"))
        return reply(
            0,
            BaseStorageEditor(
                session,
                locale=Config.i18n,
            ).get_storage(guild_id, base_id),
        )
    except DomainError as error:
        return reply(
            1, msg=error.message, error=error.to_dict()
        ), error.http_status


@save_blueprint.route(
    "/guilds/<guild_id>/bases/<base_id>/storage/commands",
    methods=["POST"],
)
@jwt_required()
def execute_base_storage_command(guild_id: str, base_id: str):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        error = DomainError(
            code="INVALID_REQUEST",
            message="A JSON object is required.",
            http_status=400,
        )
        return reply(
            1, msg=error.message, error=error.to_dict()
        ), error.http_status
    command_name = payload.get("command")
    common_fields = {
        "session_id",
        "expected_revision",
        "command",
        "container_id",
        "slot_index",
    }
    command_fields = {
        "update_item_count": {"expected_static_id", "count"},
        "put_item": {
            "static_id",
            "count",
            "mode",
            "dynamic_init",
        },
        "clear_item_slot": {
            "expected_static_id",
            "expected_dynamic_id",
        },
    }
    if command_name not in command_fields:
        error = DomainError(
            code="UNSUPPORTED_COMMAND",
            message="Unsupported base storage command.",
            field="command",
            http_status=400,
        )
        return reply(
            1, msg=error.message, error=error.to_dict()
        ), error.http_status
    unknown = sorted(
        set(payload) - common_fields - command_fields[command_name]
    )
    if unknown:
        error = DomainError(
            code="UNSUPPORTED_COMMAND_FIELD",
            message="The request contains unsupported fields.",
            details={"fields": unknown},
            http_status=400,
        )
        return reply(
            1, msg=error.message, error=error.to_dict()
        ), error.http_status
    try:
        session = SESSION_RUNTIME.get(payload.get("session_id"))
        common = {
            "session_id": payload.get("session_id"),
            "expected_revision": payload.get("expected_revision"),
            "guild_id": guild_id,
            "base_id": base_id,
            "container_id": payload.get("container_id"),
            "slot_index": payload.get("slot_index"),
        }
        if command_name == "update_item_count":
            command = UpdateBaseStorageItemCount(
                **common,
                expected_static_id=payload.get("expected_static_id"),
                count=payload.get("count"),
            )
        elif command_name == "put_item":
            command = PutBaseStorageItem(
                **common,
                static_id=payload.get("static_id"),
                count=payload.get("count"),
                mode=payload.get("mode", "empty_only"),
                dynamic_init=payload.get("dynamic_init"),
            )
        else:
            command = ClearBaseStorageItemSlot(
                **common,
                expected_static_id=payload.get("expected_static_id"),
                expected_dynamic_id=payload.get("expected_dynamic_id"),
            )
        return reply(
            0,
            BaseStorageEditor(
                session,
                locale=Config.i18n,
            ).execute(command),
        )
    except (TypeError, ValueError) as error:
        domain_error = DomainError(
            code="INVALID_REQUEST",
            message=str(error),
            http_status=400,
        )
        return reply(
            1,
            msg=domain_error.message,
            error=domain_error.to_dict(),
        ), domain_error.http_status
    except DomainError as error:
        return reply(
            1, msg=error.message, error=error.to_dict()
        ), error.http_status


@save_blueprint.route("/expeditions/commands", methods=["POST"])
@jwt_required()
def execute_expedition_command():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        error = DomainError(
            code="INVALID_REQUEST",
            message="A JSON object is required.",
            http_status=400,
        )
        return reply(1, msg=error.message, error=error.to_dict()), error.http_status
    command_name = payload.get("command")
    command_fields = {
        "complete_active_expeditions": set(),
        "complete_expedition": {"expedition_id"},
    }
    if command_name not in command_fields:
        error = DomainError(
            code="UNSUPPORTED_COMMAND",
            message="Unsupported expedition command.",
            field="command",
            http_status=400,
        )
        return reply(1, msg=error.message, error=error.to_dict()), error.http_status
    allowed = {
        "session_id",
        "expected_revision",
        "command",
        *command_fields[command_name],
    }
    unknown = sorted(set(payload) - allowed)
    if unknown:
        error = DomainError(
            code="UNSUPPORTED_COMMAND_FIELD",
            message="The request contains unsupported fields.",
            details={"fields": unknown},
            http_status=400,
        )
        return reply(1, msg=error.message, error=error.to_dict()), error.http_status
    expedition_id = payload.get("expedition_id")
    if command_name == "complete_expedition" and (
        not isinstance(expedition_id, str) or not expedition_id.strip()
    ):
        error = DomainError(
            code="INVALID_FIELD",
            message="A non-empty expedition_id is required.",
            field="expedition_id",
            http_status=400,
        )
        return reply(1, msg=error.message, error=error.to_dict()), error.http_status
    try:
        session = SESSION_RUNTIME.get(payload.get("session_id"))
        command = (
            CompleteExpedition(
                session_id=payload.get("session_id"),
                expected_revision=payload.get("expected_revision"),
                expedition_id=expedition_id.strip(),
            )
            if command_name == "complete_expedition"
            else CompleteActiveExpeditions(
                session_id=payload.get("session_id"),
                expected_revision=payload.get("expected_revision"),
            )
        )
        result = ExpeditionEditor(session).execute(
            command
        )
        return reply(0, result)
    except DomainError as error:
        return reply(1, msg=error.message, error=error.to_dict()), error.http_status


@save_blueprint.route("/pals/commands", methods=["POST"])
@jwt_required()
def execute_global_pal_command():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        error = DomainError(
            code="INVALID_REQUEST",
            message="A JSON object is required.",
            http_status=400,
        )
        return reply(1, msg=error.message, error=error.to_dict()), error.http_status
    allowed = {"session_id", "expected_revision", "command"}
    unknown = sorted(set(payload) - allowed)
    if unknown:
        error = DomainError(
            code="UNSUPPORTED_COMMAND_FIELD",
            message="The request contains unsupported fields.",
            details={"fields": unknown},
            http_status=400,
        )
        return reply(1, msg=error.message, error=error.to_dict()), error.http_status
    command_types = {
        "heal_all_pals": HealAllPals,
        "unlock_all_expedition_pals": UnlockAllExpeditionPals,
    }
    command_type = command_types.get(payload.get("command"))
    if command_type is None:
        error = DomainError(
            code="UNSUPPORTED_COMMAND",
            message="Unsupported global Pal command.",
            field="command",
            http_status=400,
        )
        return reply(1, msg=error.message, error=error.to_dict()), error.http_status
    try:
        session = SESSION_RUNTIME.get(payload.get("session_id"))
        result = CharacterEditor(session).execute(
            command_type(
                session_id=payload.get("session_id"),
                expected_revision=payload.get("expected_revision"),
            )
        )
        return reply(0, result)
    except DomainError as error:
        return reply(1, msg=error.message, error=error.to_dict()), error.http_status


def _optional_int(name: str):
    value = request.args.get(name)
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError as error:
        raise DomainError(
            code="INVALID_FILTER",
            message=f"{name} must be an integer.",
            field=name,
            http_status=400,
        ) from error


def _optional_bool(name: str):
    value = request.args.get(name)
    if value is None or value == "":
        return None
    if value.casefold() in {"true", "1"}:
        return True
    if value.casefold() in {"false", "0"}:
        return False
    raise DomainError(
        code="INVALID_FILTER",
        message=f"{name} must be true or false.",
        field=name,
        http_status=400,
    )


@save_blueprint.route("/query/players", methods=["GET"])
@jwt_required()
def query_players():
    try:
        session = SESSION_RUNTIME.get(request.args.get("session_id"))
        service = SaveQueryService(session, locale=Config.i18n)
        rows = service.players(
            text=request.args.get("q", ""),
            min_level=_optional_int("min_level"),
            max_level=_optional_int("max_level"),
            sort_by=request.args.get("sort_by", "name"),
            descending=_optional_bool("descending") or False,
        )
        guild_tree = service.guild_tree(
            player_ids={row["player_id"] for row in rows}
        )
        return reply(
            0,
            {
                "revision": session.revision,
                "players": rows,
                "guilds": guild_tree,
                "has_working_pal": bool(
                    getattr(session.manager, "baseworker_mapping", None)
                ),
            },
        )
    except DomainError as error:
        return reply(1, msg=error.message, error=error.to_dict()), error.http_status


@save_blueprint.route("/query/overview", methods=["GET"])
@jwt_required()
def query_overview():
    try:
        session = SESSION_RUNTIME.get(request.args.get("session_id"))
        return reply(
            0,
            SaveQueryService(session, locale=Config.i18n).overview(),
        )
    except DomainError as error:
        return reply(1, msg=error.message, error=error.to_dict()), error.http_status


@save_blueprint.route("/query/guilds", methods=["GET"])
@jwt_required()
def query_guilds():
    try:
        session = SESSION_RUNTIME.get(request.args.get("session_id"))
        return reply(
            0,
            {
                "revision": session.revision,
                "guilds": SaveQueryService(
                    session, locale=Config.i18n
                ).guilds(),
            },
        )
    except DomainError as error:
        return reply(1, msg=error.message, error=error.to_dict()), error.http_status


@save_blueprint.route("/query/expeditions", methods=["GET"])
@jwt_required()
def query_expeditions():
    try:
        session = SESSION_RUNTIME.get(request.args.get("session_id"))
        data = SaveQueryService(
            session, locale=Config.i18n
        ).expeditions()
        return reply(0, {"revision": session.revision, **data})
    except DomainError as error:
        return reply(1, msg=error.message, error=error.to_dict()), error.http_status


@save_blueprint.route("/query/pals", methods=["GET"])
@jwt_required()
def query_pals():
    try:
        session = SESSION_RUNTIME.get(request.args.get("session_id"))
        rows = SaveQueryService(session, locale=Config.i18n).pals(
            player_id=request.args.get("player_id"),
            text=request.args.get("q", ""),
            element=request.args.get("element"),
            min_level=_optional_int("min_level"),
            max_level=_optional_int("max_level"),
            gender=request.args.get("gender"),
            boss=_optional_bool("boss"),
            rare=_optional_bool("rare"),
            owner=request.args.get("owner"),
            container_state=request.args.get("container_state"),
            sort_by=request.args.get("sort_by", "name"),
            descending=_optional_bool("descending") or False,
        )
        return reply(0, {"revision": session.revision, "pals": rows})
    except DomainError as error:
        return reply(1, msg=error.message, error=error.to_dict()), error.http_status


@save_blueprint.route("/query/map", methods=["GET"])
@jwt_required()
def query_map():
    try:
        session = SESSION_RUNTIME.get(request.args.get("session_id"))
        data = SaveQueryService(session, locale=Config.i18n).map_data()
        return reply(0, {"revision": session.revision, **data})
    except DomainError as error:
        return reply(1, msg=error.message, error=error.to_dict()), error.http_status


@save_blueprint.route("/local-data/select", methods=["POST"])
@jwt_required()
def select_local_data():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        error = DomainError(
            code="INVALID_REQUEST",
            message="A JSON object is required.",
            http_status=400,
        )
        return reply(1, msg=error.message, error=error.to_dict()), error.http_status
    unknown = sorted(
        set(payload) - {"session_id", "expected_revision", "path"}
    )
    if unknown:
        error = DomainError(
            code="UNSUPPORTED_COMMAND_FIELD",
            message="The request contains unsupported fields.",
            details={"fields": unknown},
            http_status=400,
        )
        return reply(1, msg=error.message, error=error.to_dict()), error.http_status
    try:
        session = SESSION_RUNTIME.get(payload.get("session_id"))
        result = session.select_local_data(
            session_id=payload.get("session_id"),
            expected_revision=payload.get("expected_revision"),
            path=payload.get("path"),
        )
        return reply(0, result)
    except DomainError as error:
        return reply(1, msg=error.message, error=error.to_dict()), error.http_status


@save_blueprint.route("/local-data/fog-of-war/clear", methods=["POST"])
@jwt_required()
def clear_fog_of_war():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        error = DomainError(
            code="INVALID_REQUEST",
            message="A JSON object is required.",
            http_status=400,
        )
        return reply(1, msg=error.message, error=error.to_dict()), error.http_status
    try:
        session = SESSION_RUNTIME.get(payload.get("session_id"))
        result = FogOfWarEditor(session).execute(
            ClearFogOfWar(
                session_id=payload.get("session_id"),
                expected_revision=payload.get("expected_revision"),
                confirmation=payload.get("confirmation"),
            )
        )
        return reply(0, result)
    except DomainError as error:
        return reply(1, msg=error.message, error=error.to_dict()), error.http_status


@save_blueprint.route("/local-data/fog-of-war/reset", methods=["POST"])
@jwt_required()
def reset_fog_of_war():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        error = DomainError(
            code="INVALID_REQUEST",
            message="A JSON object is required.",
            http_status=400,
        )
        return reply(1, msg=error.message, error=error.to_dict()), error.http_status
    try:
        session = SESSION_RUNTIME.get(payload.get("session_id"))
        result = FogOfWarEditor(session).execute(
            ResetFogOfWar(
                session_id=payload.get("session_id"),
                expected_revision=payload.get("expected_revision"),
                confirmation=payload.get("confirmation"),
            )
        )
        return reply(0, result)
    except DomainError as error:
        return reply(1, msg=error.message, error=error.to_dict()), error.http_status


@save_blueprint.route("/query/items", methods=["GET"])
@jwt_required()
def query_items():
    try:
        session = SESSION_RUNTIME.get(request.args.get("session_id"))
        rows = SaveQueryService(session, locale=Config.i18n).items(
            request.args.get("player_id", ""),
            text=request.args.get("q", ""),
            category=request.args.get("category"),
            rarity=_optional_int("rarity"),
            container=request.args.get("container"),
            state=request.args.get("state"),
            dynamic_kind=request.args.get("dynamic_kind"),
            sort_by=request.args.get("sort_by", "container"),
            descending=_optional_bool("descending") or False,
        )
        return reply(0, {"revision": session.revision, "items": rows})
    except DomainError as error:
        return reply(1, msg=error.message, error=error.to_dict()), error.http_status


@save_blueprint.route("/performance", methods=["GET"])
@jwt_required()
def performance_metrics():
    try:
        session = SESSION_RUNTIME.get(request.args.get("session_id"))
        return reply(0, session.performance_metrics())
    except DomainError as error:
        return reply(1, msg=error.message, error=error.to_dict()), error.http_status


@save_blueprint.route("/save", methods=["POST"])
@jwt_required()
def save():
    payload = request.get_json(silent=True) or {}
    path = payload.get("WritePath", None)
    try:
        session = SESSION_RUNTIME.get(payload.get("session_id"))
        raw_json_pending = session.raw_json_pending
        target = path if path is not None else (
            session.source if session.platform is SavePlatform.STEAM else None
        )
        result = SaveWriter().save(
            session,
            target,
            payload.get("expected_revision", session.revision),
        )
        data = result.to_dict()
        data["raw_json_pending"] = session.raw_json_pending
        if raw_json_pending:
            try:
                if session.platform is SavePlatform.XGP:
                    reloaded = SESSION_RUNTIME.open_source(session.source_id)
                else:
                    reloaded = SESSION_RUNTIME.open(target or session.source)
            except Exception:
                LOGGER.warning(
                    "Raw JSON save was committed, but the structured editor "
                    "could not reopen the user-modified document.\n"
                    f"{traceback.format_exc()}"
                )
                data["editor_session_reloaded"] = False
            else:
                data["editor_session_reloaded"] = True
                data["session"] = reloaded.summary().to_dict()
                data["compatibility"] = reloaded.compatibility().to_dict()
        return reply(0, data)
    except DomainError as error:
        if error.code in _SAVE_DIAGNOSTIC_ERROR_CODES:
            LOGGER.error(
                "Save request rejected "
                f"({error.code})\n{traceback.format_exc()}"
            )
        return (
            reply(1, msg=error.message, error=error.to_dict()),
            error.http_status,
        )
    except Exception:
        LOGGER.error(
            "Unexpected error while saving save data\n"
            f"{traceback.format_exc()}"
        )
        return reply(1, msg="Unexpected error while saving; see the local debug log."), 500


@save_blueprint.route("/repair-character-references", methods=["POST"])
@jwt_required()
def repair_character_references():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        error = DomainError(
            code="INVALID_REQUEST",
            message="A JSON object is required.",
            http_status=400,
        )
        return reply(1, msg=error.message, error=error.to_dict()), error.http_status
    try:
        session = SESSION_RUNTIME.get(payload.get("session_id"))
        result = CharacterReferenceRepairer(session).execute(
            RepairMissingGuildHandles(
                session_id=payload.get("session_id"),
                expected_revision=payload.get("expected_revision"),
            )
        )
        return reply(0, result)
    except DomainError as error:
        return reply(1, msg=error.message, error=error.to_dict()), error.http_status


@save_blueprint.route("/export-steam", methods=["POST"])
@jwt_required()
def export_steam_copy():
    payload = request.get_json(silent=True) or {}
    try:
        target = payload.get("targetPath") or payload.get("WritePath")
        if not target:
            raise DomainError(
                code="INVALID_SAVE_TARGET",
                message="A Steam export target directory is required.",
                field="targetPath",
                http_status=400,
            )
        session = SESSION_RUNTIME.get(payload.get("session_id"))
        result = SaveWriter().export_steam_copy(
            session,
            target,
            payload.get("expected_revision", session.revision),
        )
        return reply(0, result.to_dict())
    except DomainError as error:
        return reply(1, msg=error.message, error=error.to_dict()), error.http_status


@save_blueprint.route("/passive_skills", methods=["GET"])
@jwt_required()
def get_passive_skills():
    passives_raw = DataProvider.get_sorted_passives()
    passive_dict = {}
    passive_arr = []
    for passive in passives_raw:
        data = {
            "InternalName": passive["InternalName"],
            "I18n": DataProvider.get_passive_i18n(passive["InternalName"])
            or (passive["InternalName"], passive["InternalName"]),
            "Rating": passive["Rating"],
        }
        passive_dict[passive["InternalName"]] = data
        passive_arr.append(data)
    for internal_name in DataProvider.get_localized_only_passives():
        name, description = DataProvider.get_passive_i18n(internal_name) or (
            internal_name,
            "",
        )
        passive_dict[internal_name] = {
            "InternalName": internal_name,
            "I18n": (name, description),
            "Rating": 0,
            "LocalizedOnly": True,
        }

    return reply(0, {"dict": passive_dict, "arr": passive_arr})


@save_blueprint.route("/active_skills", methods=["GET"])
@jwt_required()
def get_active_skills():
    attacks_raw = DataProvider.get_sorted_attacks()
    atk_dict = {}
    atk_arr = []
    for attack in attacks_raw:
        # if attack.get("Invalid", None):
        #     continue
        data = {
            "InternalName": attack["InternalName"],
            # "I18n": f'[{displayElement(attack["Element"])}] ' \
            #         f'{"🍐" if DataProvider.has_skill_fruit(attack["InternalName"]) else ""}' \
            #         f'{"✨"if DataProvider.is_unique_attacks(attack["InternalName"]) else ""}' \
            #         f'{DataProvider.get_attack_i18n(attack["InternalName"]) or attack["InternalName"]}',
            "I18n": list(
                DataProvider.get_attack_i18n(attack["InternalName"])
                or [attack["InternalName"], ""]
            ),
            "HasSkillFruit": DataProvider.has_skill_fruit(attack["InternalName"]),
            "IsUniqueSkill": DataProvider.is_unique_attacks(attack["InternalName"]),
            "Power": attack["Power"],
            "Element": attack["Element"],
            "CT": attack["CT"],
            "Invalid": attack.get("Invalid", False),
        }
        if data["Invalid"]:
            data["I18n"][0] = "⚠️ " + data["I18n"][0]
        atk_dict[attack["InternalName"]] = data
        atk_arr.append(data)
    for internal_name in DataProvider.get_localized_only_attacks():
        name, description = DataProvider.get_attack_i18n(internal_name) or (
            internal_name,
            "",
        )
        atk_dict[internal_name] = {
            "InternalName": internal_name,
            "I18n": [name, description],
            "HasSkillFruit": False,
            "IsUniqueSkill": False,
            "Power": 0,
            "Element": "Neutral",
            "CT": 0,
            "Invalid": True,
            "LocalizedOnly": True,
        }
    return reply(0, {"dict": atk_dict, "arr": atk_arr})


@save_blueprint.route("/i18n", methods=["PATCH"])
# @jwt_required()
def update_i18n():
    i18n_code = request.json.get("I18n", None)
    if DataProvider.is_valid_i18n(i18n_code):
        Config.i18n = i18n_code
        return reply(0)
    LOGGER.warning(
        f"I18n code {i18n_code} not available. Select from {DataProvider.get_i18n_options()}"
    )
    return reply(1, None, f"I18n code {i18n_code} not available.")


@save_blueprint.route("/pal_data", methods=["GET"])
@jwt_required()
def get_pal_data():
    pals_raw = DataProvider.get_sorted_pals()
    pal_dict = {}
    pal_arr = []
    for pal in pals_raw:
        iname = pal["InternalName"]
        if DataProvider.get_constructible_pal_id(iname) != iname:
            continue
        if (
            not DataProvider.is_pal_human(iname)
            and ("BOSS_" in iname or "Boss_" in iname)
            and DataProvider.boss_has_base_variant(iname)
        ):
            continue
        data = {
            "InternalName": iname,
            "Elements": pal["Elements"],
            "Invalid": pal.get("Invalid", False),
            "Suitabilities": DataProvider.get_pal_suitabilities(iname),
            "I18n": DataProvider.get_pal_i18n(iname) or iname,
            "SortingKey": DataProvider.get_constructible_pal_sorting_key(iname),
            "IsHuman": DataProvider.is_pal_human(iname) or False,
            "HasIcon": DataProvider.has_human_icon(iname),
            "DefaultWeapon": pal.get("DefaultWeapon"),
        }
        pal_dict[iname] = data
        pal_arr.append(data)
    return reply(0, {"dict": pal_dict, "arr": pal_arr})


@save_blueprint.route("/tech_data", methods=["GET"])
@jwt_required()
def get_tech_data():
    tech_data = DataProvider.get_tech_data()
    tech_lv_dict: dict[str, list] = {}
    for tech in tech_data:
        lv = DataProvider.get_tech_lv(tech)
        lv_arr = tech_lv_dict.get(lv, [])
        data = {
            "InternalName": tech,
            "I18n": DataProvider.get_tech_i18n(tech),
            "BossTechnology": DataProvider.is_boss_tech(tech),
        }
        lv_arr.append(data)
        tech_lv_dict[lv] = lv_arr

    return reply(0, {"techLvDict": tech_lv_dict})


@save_blueprint.route("/path", methods=["GET"])
@jwt_required()
def get_path():
    try:
        current_path = Path(Config.path).resolve()
        if not current_path.exists():
            raise Exception(f"Path {current_path} not exist.")
    except:
        pal_local_path = (
            Path(os.environ.get("LOCALAPPDATA", "/")) / "Pal" / "Saved" / "SaveGames"
        )
        if pal_local_path.exists():
            current_path = pal_local_path
        else:
            current_path = PROGRAM_PATH

    old_path = Config.path
    Config.path = str(current_path)

    try:
        return reply(0, get_path_context(current_path))
    except:
        Config.path = old_path
        LOGGER.error(traceback.format_exc())
        return reply(1, msg=f"Error, cannot open path {current_path}.")


@save_blueprint.route("path", methods=["POST"])
@jwt_required()
def update_path():
    path = Path(request.json.get("path")).resolve()
    if not path.exists():
        return reply(1, msg="Path Not Found")

    old_path = Config.path
    Config.path = str(path)

    try:
        return reply(0, get_path_context(path))
    except:
        Config.path = old_path
        LOGGER.error(traceback.format_exc())
        return reply(1, msg=f"Error, cannot open path {path}.")


@save_blueprint.route("path", methods=["PATCH"])
@jwt_required()
def path_back():
    path = Path(Config.path).parent.resolve()
    old_path = Config.path
    Config.path = str(path)

    try:
        return reply(0, get_path_context(path))
    except:
        Config.path = old_path
        LOGGER.error(traceback.format_exc())
        return reply(1, msg=f"Error, cannot open path {path}.")


@save_blueprint.route("update", methods=["GET"])
def has_update():
    try:
        version = asyncio.run(get_new_version())
    except RuntimeError:
        loop = asyncio.get_event_loop()
        version = loop.run_until_complete(get_new_version())
    if version is not None:
        return reply(
            0,
            {
                "version": version[0],
                "download_gh": version[1],
                "download_page": version[1],
            },
            msg="New version available.",
        )
    return reply(1, msg="Failed to get new version.")
