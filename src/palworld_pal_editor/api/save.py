import os
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
from palworld_pal_editor.application.save_writer import SaveWriter
from palworld_pal_editor.application.query_service import SaveQueryService
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.utils import LOGGER, DataProvider
from palworld_pal_editor.utils.util import get_path_context, reply

save_blueprint = Blueprint("save", __name__)


@save_blueprint.route("/fetch_config", methods=["GET"])
def fetch_config():
    return reply(
        0,
        {
            "I18n": Config.i18n,
            "I18nList": DataProvider.get_i18n_map(),
            "Path": Config.path,
            "HasPassword": Config.password != None,
            "VERSION": version_info(),
            "IsOfficialBuild": is_gh_build(),
            "MaxSoulsLevel": Config.max_souls_level,
        },
    )


@save_blueprint.route("/load", methods=["POST"])
# @LOGGER.api_logger
@jwt_required()
def load():
    path = request.json.get("ReadPath", None)
    path = path or Config.path
    try:
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
        rows = SaveQueryService(session, locale=Config.i18n).players(
            text=request.args.get("q", ""),
            min_level=_optional_int("min_level"),
            max_level=_optional_int("max_level"),
            sort_by=request.args.get("sort_by", "name"),
            descending=_optional_bool("descending") or False,
        )
        return reply(
            0,
            {
                "revision": session.revision,
                "players": rows,
                "has_working_pal": bool(
                    getattr(session.manager, "baseworker_mapping", None)
                ),
            },
        )
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
        result = SaveWriter().save(
            session,
            path or session.source,
            payload.get("expected_revision", session.revision),
        )
        return reply(0, result.to_dict())
    except DomainError as error:
        return (
            reply(1, msg=error.message, error=error.to_dict()),
            error.http_status,
        )
    except Exception:
        stack_trace = traceback.format_exc()
        LOGGER.error(f"Error in patch_paldata {stack_trace}")
        return reply(1, msg="Unexpected error while saving; see the local debug log."), 500


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
        if (
            "BOSS_" in iname
            and DataProvider.boss_has_base_variant(iname)
            or "Boss_" in iname
            and DataProvider.boss_has_base_variant(iname)
        ):
            continue
        data = {
            "InternalName": iname,
            "Elements": pal["Elements"],
            "Invalid": pal.get("Invalid", False),
            "Suitabilities": DataProvider.get_pal_suitabilities(iname),
            "I18n": DataProvider.get_pal_i18n(iname) or iname,
            "SortingKey": DataProvider.get_pal_sorting_key(iname),
            "IsHuman": DataProvider.is_pal_human(iname) or False,
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
@jwt_required()
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
                "download_page": PROJECT_RELEASES_URL,
            },
            msg="New version available.",
        )
    return reply(1, msg="Failed to get new version.")
