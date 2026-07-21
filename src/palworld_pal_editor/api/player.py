from flask import Blueprint, request
from flask_jwt_extended import jwt_required
from palworld_pal_editor.core.player_entity import PlayerEntity
from palworld_pal_editor.application.inventory_editor import InventoryEditor
from palworld_pal_editor.application.character_editor import CharacterEditor
from palworld_pal_editor.application.inventory_layout_editor import InventoryLayoutEditor
from palworld_pal_editor.application.dynamic_attribute_editor import DynamicAttributeEditor
from palworld_pal_editor.application.mission_editor import MissionEditor
from palworld_pal_editor.application.runtime import SESSION_RUNTIME
from palworld_pal_editor.config import Config
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.domain.item_catalog import ItemCatalog
from palworld_pal_editor.domain.models import ItemContainerType
from palworld_pal_editor.domain.commands import (
    ClearItemSlot,
    FillItemSlots,
    PasteItemSlot,
    PutItem,
    SortItemContainer,
    UpdateItemCount,
    UpdateDynamicItemAttributes,
    UpdatePlayerIdentity,
    UpdatePlayerProgression,
    UpdatePlayerTechnology,
    UpdatePlayerMissions,
)
from palworld_pal_editor.utils.util import reply

from palworld_pal_editor.core import SaveManager
from palworld_pal_editor.utils import LOGGER, DataProvider

player_blueprint = Blueprint("player", __name__)


def _domain_error(error: DomainError):
    return (
        reply(1, msg=error.message, error=error.to_dict()),
        error.http_status,
    )


def _mission_command(
    player_id: str, payload, *, require_preview_token: bool
) -> UpdatePlayerMissions:
    if not isinstance(payload, dict):
        raise DomainError(
            code="INVALID_REQUEST",
            message="A JSON object is required.",
            http_status=400,
        )
    allowed = {
        "session_id",
        "expected_revision",
        "operation",
        "mission_ids",
    }
    if require_preview_token:
        allowed.add("preview_token")
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise DomainError(
            code="UNSUPPORTED_COMMAND_FIELD",
            message="The request contains unsupported fields.",
            details={"fields": unknown},
            http_status=400,
        )
    mission_ids = payload.get("mission_ids", [])
    if not isinstance(mission_ids, list) or not all(
        isinstance(mission_id, str) and mission_id for mission_id in mission_ids
    ):
        raise DomainError(
            code="INVALID_REQUEST",
            message="mission_ids must be an array of non-empty strings.",
            field="mission_ids",
            http_status=400,
        )
    return UpdatePlayerMissions(
        session_id=payload.get("session_id"),
        expected_revision=payload.get("expected_revision"),
        player_id=player_id,
        operation=payload.get("operation"),
        mission_ids=tuple(mission_ids),
        preview_token=(payload.get("preview_token") if require_preview_token else None),
    )


@player_blueprint.route("/<player_id>/missions", methods=["GET"])
@jwt_required()
def get_player_missions(player_id: str):
    try:
        session = SESSION_RUNTIME.get(request.args.get("session_id"))
        locale = request.args.get("locale") or Config.i18n
        return reply(
            0,
            MissionEditor(session, locale=locale).get_missions(
                player_id, locale=locale
            ),
        )
    except DomainError as error:
        return _domain_error(error)


@player_blueprint.route("/<player_id>/missions/preview", methods=["POST"])
@jwt_required()
def preview_player_mission_command(player_id: str):
    try:
        command = _mission_command(
            player_id, request.get_json(silent=True), require_preview_token=False
        )
        session = SESSION_RUNTIME.get(command.session_id)
        return reply(0, MissionEditor(session, locale=Config.i18n).preview(command))
    except (TypeError, ValueError) as error:
        return _domain_error(
            DomainError(code="INVALID_REQUEST", message=str(error), http_status=400)
        )
    except DomainError as error:
        return _domain_error(error)


@player_blueprint.route("/<player_id>/missions/commands", methods=["POST"])
@jwt_required()
def execute_player_mission_command(player_id: str):
    try:
        command = _mission_command(
            player_id, request.get_json(silent=True), require_preview_token=True
        )
        session = SESSION_RUNTIME.get(command.session_id)
        return reply(0, MissionEditor(session, locale=Config.i18n).execute(command))
    except (TypeError, ValueError) as error:
        return _domain_error(
            DomainError(code="INVALID_REQUEST", message=str(error), http_status=400)
        )
    except DomainError as error:
        return _domain_error(error)


@player_blueprint.route("/<player_id>/commands", methods=["POST"])
@jwt_required()
def execute_player_command(player_id: str):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _domain_error(
            DomainError(
                code="INVALID_REQUEST",
                message="A JSON object is required.",
                http_status=400,
            )
        )
    common_fields = {"session_id", "expected_revision", "command"}
    command_fields = {
        "update_player_identity": {"name"},
        "update_player_progression": {
            "level",
            "experience",
            "technology_points",
            "boss_technology_points",
        },
        "update_player_technology": {"recipe_id", "unlocked", "unlock_all"},
    }
    command_name = payload.get("command")
    if command_name not in command_fields:
        return _domain_error(
            DomainError(
                code="UNSUPPORTED_COMMAND",
                message="Unsupported player command.",
                field="command",
                http_status=400,
            )
        )
    unknown = sorted(set(payload) - common_fields - command_fields[command_name])
    if unknown:
        return _domain_error(
            DomainError(
                code="UNSUPPORTED_COMMAND_FIELD",
                message="The request contains unsupported fields.",
                details={"fields": unknown},
                http_status=400,
            )
        )
    try:
        session = SESSION_RUNTIME.get(payload.get("session_id"))
        base = {
            "session_id": payload.get("session_id"),
            "expected_revision": payload.get("expected_revision"),
            "player_id": player_id,
        }
        if command_name == "update_player_identity":
            command = UpdatePlayerIdentity(**base, name=payload.get("name"))
        elif command_name == "update_player_progression":
            command = UpdatePlayerProgression(
                **base,
                level=payload.get("level"),
                experience=payload.get("experience"),
                technology_points=payload.get("technology_points"),
                boss_technology_points=payload.get("boss_technology_points"),
            )
        else:
            command = UpdatePlayerTechnology(
                **base,
                recipe_id=payload.get("recipe_id"),
                unlocked=payload.get("unlocked"),
                unlock_all=payload.get("unlock_all", False),
            )
        return reply(0, CharacterEditor(session).execute(command))
    except DomainError as error:
        return _domain_error(error)


@player_blueprint.route("/<player_id>/inventory", methods=["GET"])
@jwt_required()
def get_domain_inventory(player_id: str):
    try:
        session = SESSION_RUNTIME.get(request.args.get("session_id"))
        view = InventoryEditor(session, locale=Config.i18n).get_inventory(player_id)
        return reply(0, view.to_dict())
    except DomainError as error:
        return _domain_error(error)


@player_blueprint.route("/<player_id>/inventory/commands", methods=["POST"])
@jwt_required()
def execute_inventory_command(player_id: str):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _domain_error(
            DomainError(
                code="INVALID_REQUEST",
                message="A JSON object is required.",
                http_status=400,
            )
        )
    common_fields = {
        "session_id",
        "expected_revision",
        "command",
        "container_type",
        "slot_index",
    }
    command_name = payload.get("command")
    command_fields = {
        "update_item_count": {"expected_static_id", "count"},
        "put_item": {"static_id", "count", "mode", "dynamic_init"},
        "clear_item_slot": {"expected_static_id", "expected_dynamic_id"},
        "update_dynamic_attributes": {
            "expected_static_id",
            "expected_dynamic_id",
            "values",
        },
    }
    if command_name not in command_fields:
        return _domain_error(
            DomainError(
                code="UNSUPPORTED_COMMAND",
                message="Unsupported inventory command.",
                field="command",
                http_status=400,
            )
        )
    allowed = common_fields | command_fields[command_name]
    unknown = sorted(set(payload) - allowed)
    if unknown:
        return _domain_error(
            DomainError(
                code="UNSUPPORTED_COMMAND_FIELD",
                message="The request contains unsupported fields.",
                details={"fields": unknown},
                http_status=400,
            )
        )
    try:
        session = SESSION_RUNTIME.get(payload.get("session_id"))
        base = {
            "session_id": payload.get("session_id"),
            "expected_revision": payload.get("expected_revision"),
            "player_id": player_id,
            "container_type": ItemContainerType(payload.get("container_type")),
            "slot_index": payload.get("slot_index"),
        }
        if command_name == "update_item_count":
            command = UpdateItemCount(
                **base,
                expected_static_id=payload.get("expected_static_id"),
                count=payload.get("count"),
            )
        elif command_name == "put_item":
            command = PutItem(
                **base,
                static_id=payload.get("static_id"),
                count=payload.get("count"),
                mode=payload.get("mode", "empty_only"),
                dynamic_init=payload.get("dynamic_init"),
            )
        elif command_name == "clear_item_slot":
            command = ClearItemSlot(
                **base,
                expected_static_id=payload.get("expected_static_id"),
                expected_dynamic_id=payload.get("expected_dynamic_id"),
            )
        else:
            command = UpdateDynamicItemAttributes(
                **base,
                expected_static_id=payload.get("expected_static_id"),
                expected_dynamic_id=payload.get("expected_dynamic_id"),
                values=payload.get("values") or {},
            )
            return reply(
                0,
                DynamicAttributeEditor(session).execute(command),
            )
        return reply(
            0,
            InventoryEditor(session, locale=Config.i18n).execute(command),
        )
    except (TypeError, ValueError) as error:
        return _domain_error(
            DomainError(
                code="INVALID_REQUEST",
                message=str(error),
                http_status=400,
            )
        )
    except DomainError as error:
        return _domain_error(error)


@player_blueprint.route(
    "/<player_id>/inventory/<container_type>/<int:slot_index>/dynamic",
    methods=["GET"],
)
@jwt_required()
def get_dynamic_item_attributes(
    player_id: str, container_type: str, slot_index: int
):
    try:
        session = SESSION_RUNTIME.get(request.args.get("session_id"))
        return reply(
            0,
            DynamicAttributeEditor(session).get_attributes(
                player_id=player_id,
                container_type=ItemContainerType(container_type),
                slot_index=slot_index,
            ),
        )
    except ValueError as error:
        return _domain_error(
            DomainError(
                code="INVALID_CONTAINER_TYPE",
                message=str(error),
                field="container_type",
                http_status=400,
            )
        )
    except DomainError as error:
        return _domain_error(error)


@player_blueprint.route("/<player_id>/inventory/copy", methods=["POST"])
@jwt_required()
def copy_inventory_slot(player_id: str):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _domain_error(
            DomainError(
                code="INVALID_REQUEST",
                message="A JSON object is required.",
                http_status=400,
            )
        )
    unknown = sorted(
        set(payload)
        - {"session_id", "expected_revision", "container_type", "slot_index"}
    )
    if unknown:
        return _domain_error(
            DomainError(
                code="UNSUPPORTED_COMMAND_FIELD",
                message="The request contains unsupported fields.",
                details={"fields": unknown},
                http_status=400,
            )
        )
    try:
        session = SESSION_RUNTIME.get(payload.get("session_id"))
        return reply(
            0,
            InventoryLayoutEditor(session, locale=Config.i18n).copy_slot(
                session_id=payload.get("session_id"),
                expected_revision=payload.get("expected_revision"),
                player_id=player_id,
                container_type=ItemContainerType(payload.get("container_type")),
                slot_index=payload.get("slot_index"),
            ),
        )
    except (TypeError, ValueError) as error:
        return _domain_error(
            DomainError(
                code="INVALID_REQUEST", message=str(error), http_status=400
            )
        )
    except DomainError as error:
        return _domain_error(error)


@player_blueprint.route("/<player_id>/inventory/layout/commands", methods=["POST"])
@jwt_required()
def execute_inventory_layout_command(player_id: str):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _domain_error(
            DomainError(
                code="INVALID_REQUEST",
                message="A JSON object is required.",
                http_status=400,
            )
        )
    command_name = payload.get("command")
    common = {"session_id", "expected_revision", "command", "container_type"}
    fields = {
        "paste_item_slot": {"slot_index", "clipboard_token"},
        "sort_item_container": {"sort_by", "descending"},
        "fill_item_slots": {"slot_indices", "static_id", "count"},
    }
    if command_name not in fields:
        return _domain_error(
            DomainError(
                code="UNSUPPORTED_COMMAND",
                message="Unsupported inventory layout command.",
                field="command",
                http_status=400,
            )
        )
    unknown = sorted(set(payload) - common - fields[command_name])
    if unknown:
        return _domain_error(
            DomainError(
                code="UNSUPPORTED_COMMAND_FIELD",
                message="The request contains unsupported fields.",
                details={"fields": unknown},
                http_status=400,
            )
        )
    try:
        session = SESSION_RUNTIME.get(payload.get("session_id"))
        base = {
            "session_id": payload.get("session_id"),
            "expected_revision": payload.get("expected_revision"),
            "player_id": player_id,
            "container_type": ItemContainerType(payload.get("container_type")),
        }
        if command_name == "paste_item_slot":
            command = PasteItemSlot(
                **base,
                slot_index=payload.get("slot_index"),
                clipboard_token=payload.get("clipboard_token"),
            )
        elif command_name == "sort_item_container":
            command = SortItemContainer(
                **base,
                sort_by=payload.get("sort_by"),
                descending=payload.get("descending", False),
            )
        else:
            slot_indices = payload.get("slot_indices")
            if not isinstance(slot_indices, list):
                raise DomainError(
                    code="INVALID_REQUEST",
                    message="slot_indices must be an array.",
                    field="slot_indices",
                    http_status=400,
                )
            command = FillItemSlots(
                **base,
                slot_indices=tuple(slot_indices),
                static_id=payload.get("static_id"),
                count=payload.get("count"),
                dynamic_init=payload.get("dynamic_init"),
            )
        return reply(
            0,
            InventoryLayoutEditor(session, locale=Config.i18n).execute(command),
        )
    except (TypeError, ValueError) as error:
        return _domain_error(
            DomainError(
                code="INVALID_REQUEST", message=str(error), http_status=400
            )
        )
    except DomainError as error:
        return _domain_error(error)


@player_blueprint.route("/item_catalog", methods=["GET"])
@jwt_required()
def search_item_catalog():
    try:
        container = request.args.get("container_type")
        container_type = ItemContainerType(container) if container else None
        rarity_value = request.args.get("rarity")
        if rarity_value is not None:
            try:
                rarity = int(rarity_value)
            except ValueError as error:
                raise DomainError(
                    code="INVALID_RARITY",
                    message="rarity must be an integer.",
                    field="rarity",
                    http_status=400,
                ) from error
        else:
            rarity = None
        catalog = ItemCatalog.load_default()
        entries = catalog.search(
            text=request.args.get("q", ""),
            category=request.args.get("category"),
            rarity=rarity,
            container_type=container_type,
            dynamic_kind=request.args.get("dynamic_kind"),
            locale=Config.i18n,
        )
        return reply(
            0,
            {
                "items": [entry.to_dict(Config.i18n) for entry in entries],
                "count": len(entries),
            },
        )
    except ValueError as error:
        return _domain_error(
            DomainError(
                code="INVALID_CONTAINER_TYPE",
                message=str(error),
                field="container_type",
                http_status=400,
            )
        )
    except DomainError as error:
        return _domain_error(error)


@player_blueprint.route("/player_pals", methods=["POST"])
@jwt_required()
def get_player_pals():
    id = request.json.get("PlayerUId")
    if id == "PAL_BASE_WORKER_BTN":
        pals = SaveManager().get_working_pals()
    else:
        player_entity = SaveManager().get_player(id)
        if not player_entity:
            return reply(1, None, f"Player {id} Not Found")
        pals = player_entity.get_sorted_pals()

    # I hate this piece of shit
    return reply(
        0,
        [
            {
                "InstanceId": str(pal.InstanceId) if pal.InstanceId else None,
                # "OwnerPlayerUId": str(pal.OwnerPlayerUId) if pal.OwnerPlayerUId else None,
                # "OwnerName": pal.OwnerName or None,
                "IconAccessKey": pal.IconAccessKey or None,
                "DataAccessKey": pal.DataAccessKey or None,
                "I18nName": pal.I18nName or None,
                "DisplayName": pal.DisplayName or None,
                "Gender": pal.Gender.value if pal.Gender else None,
                "IsTower": pal.IsTower or False,
                "IsBOSS": pal.IsBOSS or False,
                "IsRarePal": pal.IsRarePal or False,
                # "NickName": pal.NickName or "",
                # "Level": pal.Level or 1,
                # "Rank": pal.Rank.value if pal.Rank else 1,
                # "Rank_HP": pal.Rank_HP or 0,
                # "Rank_Attack": pal.Rank_Attack or 0,
                # "Rank_Defence": pal.Rank_Defence or 0,
                # "Rank_CraftSpeed": pal.Rank_CraftSpeed or 0,
                # "MaxHP": pal.MaxHP or None,
                # "ComputedAttack": pal.ComputedAttack or None,
                # "ComputedDefense": pal.ComputedDefense or None,
                # "PassiveSkillList": pal.PassiveSkillList or [],
                # "MasteredWaza": pal.MasteredWaza or [],
                # "Talent_HP": pal.Talent_HP or 0,
                # "Talent_Melee": pal.Talent_Melee or 0,
                # "Talent_Shot": pal.Talent_Shot or 0,
                # "Talent_Defense": pal.Talent_Defense or 0,
                "Is_Unref_Pal": pal.is_unreferenced_pal,
                "in_owner_palbox": pal.in_owner_palbox,
            }
            for pal in pals
        ],
    )


@player_blueprint.route("/players_data", methods=["GET"])
@jwt_required()
def get_player_list():
    workingpals = SaveManager().get_working_pals()
    players = SaveManager().get_players()
    if not players:
        return reply(1, None, "No Player Found")
    return reply(
        0,
        {
            "players": [
                player_to_dict(player) for player in SaveManager().get_players()
            ],
            "hasWorkingPal": (True if len(workingpals) else False),
        },
    )


@player_blueprint.route("/player_data", methods=["POST"])
@jwt_required()
def get_player_data():
    PlayerUId = request.json.get("PlayerUId")

    if PlayerUId == "PAL_BASE_WORKER_BTN":
        LOGGER.warning(f"PAL_BASE_WORKER_BTN is not a real player")
        return reply(1, None, f"PAL_BASE_WORKER_BTN is not a real player")

    try:
        player_entity = SESSION_RUNTIME.get().load_player(PlayerUId)
    except DomainError as error:
        return _domain_error(error)
    if not player_entity:
        LOGGER.warning(f"Player {PlayerUId} not exist")
        return reply(1, None, f"Player {PlayerUId} not exist")

    player_dict = player_to_dict(player_entity)
    player_dict["UnlockedRecipeTechnologyNames"] = (
        player_entity.UnlockedRecipeTechnologyNames or []
    )
    try:
        player_dict["Inventory"] = inventory_to_dict(player_entity)
    except (KeyError, TypeError, ValueError) as error:
        LOGGER.warning(f"Unable to include player inventory: {error}")
        player_dict["Inventory"] = {"Capacity": 0, "Items": []}

    return reply(0, player_dict)


def player_to_dict(player: PlayerEntity):
    return {
        "InstanceId": str(player.PlayerUId),
        "NickName": player.NickName or "",
        "Level": player.Level or 1,
        "HasViewingCage": player.has_viewing_cage(),
        "UnlockedRecipeTechnologyNames": [],
        "TechnologyPoint": player.TechnologyPoint or 0,
        "bossTechnologyPoint": player.bossTechnologyPoint or 0,
    }


def inventory_to_dict(player: PlayerEntity):
    container_id = player.CommonItemContainerId
    if container_id is None:
        raise ValueError(f"Player {player.PlayerUId} has no common item container")
    container = SaveManager().item_container_data.get(container_id)
    if container is None:
        raise ValueError(f"Item container {container_id} not found")

    items = []
    for slot in sorted(container.slots.values(), key=lambda item: item.slot_index):
        name, description = DataProvider.get_item_i18n(slot.static_id)
        items.append(
            {
                "SlotIndex": slot.slot_index,
                "InternalName": slot.static_id,
                "Count": slot.count,
                "Name": name,
                "Description": description,
                "Icon": DataProvider.get_item_icon(slot.static_id),
            }
        )
    return {
        "Capacity": container.capacity,
        "Items": items,
    }


@player_blueprint.route("/inventory", methods=["POST"])
@jwt_required()
def get_player_inventory():
    player_uid = request.json.get("PlayerUId")
    player = SaveManager().get_player(player_uid)
    if not player:
        return reply(1, None, f"Player {player_uid} not found")
    try:
        return reply(0, inventory_to_dict(player))
    except (KeyError, TypeError, ValueError) as error:
        LOGGER.warning(f"Unable to read player inventory: {error}")
        return reply(1, None, str(error))


@player_blueprint.route("/inventory", methods=["PATCH"])
@jwt_required()
def patch_player_inventory():
    player_uid = request.json.get("PlayerUId")
    slot_index = request.json.get("SlotIndex")
    static_id = request.json.get("InternalName")
    count = request.json.get("Count")
    try:
        session = SESSION_RUNTIME.get()
        result = InventoryEditor(session, locale=Config.i18n).execute(
            UpdateItemCount(
                session_id=session.session_id,
                expected_revision=request.json.get("ExpectedRevision", session.revision),
                player_id=player_uid,
                container_type=ItemContainerType.COMMON,
                slot_index=slot_index,
                expected_static_id=static_id,
                count=count,
            )
        )
        player = SaveManager().get_player(player_uid)
        return reply(0, inventory_to_dict(player), msg=None)
    except DomainError as error:
        return _domain_error(error)
    except (KeyError, TypeError, ValueError) as error:
        return _domain_error(
            DomainError(
                code="INVALID_REQUEST",
                message=str(error),
                http_status=400,
            )
        )


@player_blueprint.route("/player_data", methods=["PATCH"])
@jwt_required()
def patch_player_data():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _domain_error(
            DomainError(
                code="INVALID_REQUEST",
                message="A JSON object is required.",
                http_status=400,
            )
        )
    player_id = payload.get("PlayerUId")
    key = payload.get("key")
    value = payload.get("value")
    try:
        session = SESSION_RUNTIME.get(payload.get("session_id"))
        base = {
            "session_id": session.session_id,
            "expected_revision": payload.get(
                "ExpectedRevision", payload.get("expected_revision", session.revision)
            ),
            "player_id": player_id,
        }
        if key == "NickName":
            command = UpdatePlayerIdentity(**base, name=value)
        elif key in {
            "Level",
            "Exp",
            "TechnologyPoint",
            "bossTechnologyPoint",
        }:
            field = {
                "Level": "level",
                "Exp": "experience",
                "TechnologyPoint": "technology_points",
                "bossTechnologyPoint": "boss_technology_points",
            }[key]
            command = UpdatePlayerProgression(**base, **{field: value})
        elif key == "toggle_UnlockedRecipeTechnologyNames":
            if not isinstance(value, dict):
                raise DomainError(
                    code="INVALID_REQUEST",
                    message="Technology state must be an object.",
                    http_status=400,
                )
            command = UpdatePlayerTechnology(
                **base,
                recipe_id=value.get("tech"),
                unlocked=value.get("status"),
            )
        elif key == "unlock_all_techs":
            command = UpdatePlayerTechnology(**base, unlock_all=True)
        elif key == "unlock_viewing_cage":
            command = UpdatePlayerTechnology(
                **base, recipe_id="DisplayCharacter", unlocked=True
            )
        else:
            raise DomainError(
                code="UNSUPPORTED_COMMAND_FIELD",
                message="The legacy player field is not writable.",
                field="key",
                details={"key": key},
                http_status=400,
            )
        return reply(0, CharacterEditor(session).execute(command))
    except DomainError as error:
        return _domain_error(error)
