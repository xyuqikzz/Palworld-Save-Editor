from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from palworld_pal_editor.utils.util import reply

from palworld_pal_editor.application.character_editor import CharacterEditor
from palworld_pal_editor.application.structural_pal_editor import StructuralPalEditor
from palworld_pal_editor.application.runtime import SESSION_RUNTIME
from palworld_pal_editor.core import SaveManager, PalEntity
from palworld_pal_editor.domain.commands import (
    AddPal,
    ClonePal,
    DeletePal,
    MovePal,
    RecoverDetachedPal,
    UnlockPalExpedition,
    UpdatePalEnhancement,
    UpdatePalIdentity,
    UpdatePalProgression,
    UpdatePalSkills,
)
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.domain.models import CharacterContainerType
from palworld_pal_editor.utils import LOGGER

pal_blueprint = Blueprint("pal", __name__)


def _domain_error(error: DomainError):
    return (
        reply(1, msg=error.message, error=error.to_dict()),
        error.http_status,
    )


def _character_container_type(value):
    try:
        return CharacterContainerType(value or CharacterContainerType.AUTO)
    except (ValueError, TypeError) as error:
        raise DomainError(
            code="INVALID_CONTAINER_TYPE",
            message="container_type is not supported.",
            field="container_type",
            http_status=400,
        ) from error


@pal_blueprint.route("/structural/commands", methods=["POST"])
@jwt_required()
def execute_structural_pal_command():
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
        "add_pal": {"player_id", "species_id", "container_type", "target_slot"},
        "clone_pal": {
            "source_pal_id",
            "target_player_id",
            "container_type",
            "target_slot",
            "impact_token",
        },
        "move_pal": {
            "pal_id",
            "target_player_id",
            "container_type",
            "target_slot",
            "impact_token",
        },
        "delete_pal": {"pal_id", "impact_token"},
        "recover_detached_pal": {
            "pal_id",
            "target_player_id",
            "container_type",
            "target_slot",
        },
    }
    command_name = payload.get("command")
    if command_name not in command_fields:
        return _domain_error(
            DomainError(
                code="UNSUPPORTED_COMMAND",
                message="Unsupported structural Pal command.",
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
        }
        if command_name == "add_pal":
            command = AddPal(
                **base,
                player_id=payload.get("player_id"),
                species_id=payload.get("species_id"),
                container_type=_character_container_type(
                    payload.get("container_type")
                ),
                target_slot=payload.get("target_slot"),
            )
        elif command_name == "clone_pal":
            command = ClonePal(
                **base,
                source_pal_id=payload.get("source_pal_id"),
                target_player_id=payload.get("target_player_id"),
                container_type=_character_container_type(
                    payload.get("container_type")
                ),
                target_slot=payload.get("target_slot"),
                impact_token=payload.get("impact_token"),
            )
        elif command_name == "move_pal":
            command = MovePal(
                **base,
                pal_id=payload.get("pal_id"),
                target_player_id=payload.get("target_player_id"),
                container_type=_character_container_type(
                    payload.get("container_type")
                ),
                target_slot=payload.get("target_slot"),
                impact_token=payload.get("impact_token"),
            )
        elif command_name == "delete_pal":
            command = DeletePal(
                **base,
                pal_id=payload.get("pal_id"),
                impact_token=payload.get("impact_token"),
            )
        else:
            command = RecoverDetachedPal(
                **base,
                pal_id=payload.get("pal_id"),
                target_player_id=payload.get("target_player_id"),
                container_type=_character_container_type(
                    payload.get("container_type")
                ),
                target_slot=payload.get("target_slot"),
            )
        return reply(0, StructuralPalEditor(session).execute(command))
    except DomainError as error:
        return _domain_error(error)


@pal_blueprint.route("/structural/preview", methods=["POST"])
@jwt_required()
def preview_structural_pal_command():
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
        "clone_pal": {
            "source_pal_id",
            "target_player_id",
            "container_type",
            "target_slot",
        },
        "move_pal": {
            "pal_id",
            "target_player_id",
            "container_type",
            "target_slot",
        },
    }
    command_name = payload.get("command")
    if command_name not in command_fields:
        return _domain_error(
            DomainError(
                code="UNSUPPORTED_COMMAND",
                message="Only clone_pal and move_pal support this preview endpoint.",
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
            "target_player_id": payload.get("target_player_id"),
            "container_type": _character_container_type(
                payload.get("container_type")
            ),
            "target_slot": payload.get("target_slot"),
        }
        editor = StructuralPalEditor(session)
        if command_name == "clone_pal":
            result = editor.preview_clone(
                ClonePal(
                    **base,
                    source_pal_id=payload.get("source_pal_id"),
                )
            )
        else:
            result = editor.preview_move(
                MovePal(
                    **base,
                    pal_id=payload.get("pal_id"),
                )
            )
        return reply(0, result)
    except DomainError as error:
        return _domain_error(error)


@pal_blueprint.route("/<pal_id>/delete-preview", methods=["POST"])
@jwt_required()
def preview_delete_pal(pal_id: str):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _domain_error(
            DomainError(
                code="INVALID_REQUEST",
                message="A JSON object is required.",
                http_status=400,
            )
        )
    unknown = sorted(set(payload) - {"session_id", "expected_revision"})
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
        result = StructuralPalEditor(session).preview_delete(
            pal_id=pal_id,
            session_id=payload.get("session_id"),
            expected_revision=payload.get("expected_revision"),
        )
        return reply(0, result)
    except DomainError as error:
        return _domain_error(error)


@pal_blueprint.route("/<pal_id>/commands", methods=["POST"])
@jwt_required()
def execute_pal_command(pal_id: str):
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
        "update_pal_identity": {"name", "gender", "variant", "boss", "tower", "rare"},
        "update_pal_progression": {"values"},
        "update_pal_skills": {"active", "mastered", "passive"},
        "update_pal_enhancement": {"values", "work_suitability"},
        "unlock_pal_expedition": set(),
    }
    command_name = payload.get("command")
    if command_name not in command_fields:
        return _domain_error(
            DomainError(
                code="UNSUPPORTED_COMMAND",
                message="Unsupported Pal command.",
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
            "pal_id": pal_id,
        }
        if command_name == "update_pal_identity":
            command = UpdatePalIdentity(
                **base,
                name=payload.get("name"),
                gender=payload.get("gender"),
                variant=payload.get("variant"),
                boss=payload.get("boss"),
                tower=payload.get("tower"),
                rare=payload.get("rare"),
            )
        elif command_name == "update_pal_progression":
            command = UpdatePalProgression(
                **base, values=payload.get("values", {})
            )
        elif command_name == "update_pal_skills":
            command = UpdatePalSkills(
                **base,
                active=payload.get("active"),
                mastered=payload.get("mastered"),
                passive=payload.get("passive"),
            )
        elif command_name == "unlock_pal_expedition":
            command = UnlockPalExpedition(**base)
        else:
            command = UpdatePalEnhancement(
                **base,
                values=payload.get("values", {}),
                work_suitability=payload.get("work_suitability", {}),
            )
        return reply(0, CharacterEditor(session).execute(command))
    except DomainError as error:
        return _domain_error(error)


# Update Pal Data
@pal_blueprint.route("/paldata", methods=["PATCH"])
@jwt_required()
def patch_paldata():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _domain_error(
            DomainError(
                code="INVALID_REQUEST",
                message="A JSON object is required.",
                http_status=400,
            )
        )
    pal_id = payload.get("PalGuid")
    key = payload.get("key")
    value = payload.get("value")
    try:
        session = SESSION_RUNTIME.get(payload.get("session_id"))
        pal = session.manager.get_pal(pal_id)
        if pal is None:
            raise DomainError(
                code="PAL_NOT_FOUND",
                message="Pal not found.",
                field="PalGuid",
                http_status=404,
            )
        base = {
            "session_id": session.session_id,
            "expected_revision": payload.get(
                "ExpectedRevision", payload.get("expected_revision", session.revision)
            ),
            "pal_id": str(pal.InstanceId),
        }
        if key == "NickName":
            command = UpdatePalIdentity(**base, name=value)
        elif key == "Gender":
            gender = {
                "EPalGenderType::Male": "male",
                "EPalGenderType::Female": "female",
                "NONE": "none",
            }.get(value, value)
            command = UpdatePalIdentity(**base, gender=gender)
        elif key == "CharacterID":
            command = UpdatePalIdentity(**base, variant=value)
        elif key in {"IsBOSS", "IsTower", "IsRarePal"}:
            field = {
                "IsBOSS": "boss",
                "IsTower": "tower",
                "IsRarePal": "rare",
            }[key]
            command = UpdatePalIdentity(**base, **{field: value})
        elif key in {
            "Level",
            "Exp",
            "FriendshipLevel",
            "Hp",
            "FullStomach",
        }:
            field = {
                "Level": "level",
                "Exp": "experience",
                "FriendshipLevel": "friendship_level",
                "Hp": "health",
                "FullStomach": "satiety",
            }[key]
            command = UpdatePalProgression(**base, values={field: value})
        elif key in {"HasWorkerSick", "IsFaintedPal"}:
            command = UpdatePalProgression(**base, values={"heal": True})
        elif key in {
            "Talent_HP",
            "Talent_Melee",
            "Talent_Shot",
            "Talent_Defense",
            "Rank_HP",
            "Rank_Attack",
            "Rank_Defence",
            "Rank_CraftSpeed",
            "Rank",
        }:
            field = {
                "Talent_HP": "iv_hp",
                "Talent_Melee": "iv_melee",
                "Talent_Shot": "iv_shot",
                "Talent_Defense": "iv_defense",
                "Rank_HP": "soul_hp",
                "Rank_Attack": "soul_attack",
                "Rank_Defence": "soul_defense",
                "Rank_CraftSpeed": "soul_craft_speed",
                "Rank": "condensation",
            }[key]
            command = UpdatePalEnhancement(**base, values={field: value})
        elif key == "set_Suitability":
            if not isinstance(value, dict):
                raise DomainError(
                    code="INVALID_REQUEST",
                    message="Work suitability must be an object.",
                    http_status=400,
                )
            command = UpdatePalEnhancement(
                **base,
                work_suitability={value.get("name"): value.get("level")},
            )
        elif key in {
            "add_PassiveSkillList",
            "pop_PassiveSkillList",
            "add_EquipWaza",
            "pop_EquipWaza",
            "add_MasteredWaza",
            "pop_MasteredWaza",
        }:
            active = list(pal.EquipWaza or [])
            mastered = list(pal.MasteredWaza or [])
            passive = list(pal.PassiveSkillList or [])
            if key == "add_PassiveSkillList":
                passive.append(value)
            elif key == "pop_PassiveSkillList":
                if value not in passive:
                    raise DomainError(
                        code="SKILL_NOT_ASSIGNED",
                        message="The passive skill is not assigned.",
                        http_status=409,
                    )
                passive.remove(value)
            elif key == "add_EquipWaza":
                active.append(value)
                if value not in mastered:
                    mastered.append(value)
            elif key == "pop_EquipWaza":
                if value not in active:
                    raise DomainError(
                        code="SKILL_NOT_ASSIGNED",
                        message="The active skill is not assigned.",
                        http_status=409,
                    )
                active.remove(value)
            elif key == "add_MasteredWaza":
                mastered.append(value)
                if len(active) < 3 and value not in active:
                    active.append(value)
            else:
                if value not in mastered:
                    raise DomainError(
                        code="SKILL_NOT_ASSIGNED",
                        message="The mastered skill is not assigned.",
                        http_status=409,
                    )
                mastered.remove(value)
                if value in active:
                    active.remove(value)
            command = UpdatePalSkills(
                **base,
                active=tuple(active),
                mastered=tuple(mastered),
                passive=tuple(passive),
            )
        elif key == "in_owner_palbox":
            target_player_id = payload.get("PlayerUId")
            if not target_player_id or target_player_id == "PAL_BASE_WORKER_BTN":
                raise DomainError(
                    code="PLAYER_NOT_FOUND",
                    message="A target player is required.",
                    field="PlayerUId",
                    http_status=404,
                )
            if pal.is_unreferenced_pal:
                structural_command = RecoverDetachedPal(
                    session_id=base["session_id"],
                    expected_revision=base["expected_revision"],
                    pal_id=base["pal_id"],
                    target_player_id=target_player_id,
                )
            else:
                structural_command = MovePal(
                    session_id=base["session_id"],
                    expected_revision=base["expected_revision"],
                    pal_id=base["pal_id"],
                    target_player_id=target_player_id,
                )
            return reply(
                0, StructuralPalEditor(session).execute(structural_command)
            )
        elif key == "heal_all_pals":
            raise DomainError(
                code="BULK_COMMAND_REQUIRED",
                message="This legacy action must use its atomic bulk command.",
                field="key",
                http_status=409,
            )
        else:
            raise DomainError(
                code="UNSUPPORTED_COMMAND_FIELD",
                message="The legacy Pal field is not writable.",
                field="key",
                details={"key": key},
                http_status=400,
            )
        return reply(0, CharacterEditor(session).execute(command))
    except DomainError as error:
        return _domain_error(error)


# Get Pal Data
@pal_blueprint.route("/paldata", methods=["POST"])
@jwt_required()
def paldata():
    InstanceId = request.json.get("InstanceId")
    PlayerUId = request.json.get("PlayerUId")
    if PlayerUId == "PAL_BASE_WORKER_BTN":
        pal = SaveManager().get_working_pal(InstanceId)
        LOGGER.info(f"Get BASE WORKER {pal}")
    else:
        try:
            player = SaveManager().get_player(PlayerUId)
            pal = player.get_pal(InstanceId)
            LOGGER.info(f"Get {player.NickName}'s pal: {pal}")
        except:
            pass
    if pal:
        return reply(
            0,
            _pal_data(pal),
        )
    LOGGER.warning(
        f"Failed Getting Pal with PlayerID: {PlayerUId}, PalID: {InstanceId}"
    )
    return reply(
        1, None, f"Failed Getting Pal with PlayerID: {PlayerUId}, PalID: {InstanceId}"
    )


# Just some dumb shit
def _pal_data(pal: PalEntity):
    return {
        "InstanceId": str(pal.InstanceId) if pal.InstanceId else None,
        "OwnerPlayerUId": (str(pal.OwnerPlayerUId) if pal.OwnerPlayerUId else None),
        "group_id": str(pal.group_id) if pal.group_id else None,
        "SlotIndex": pal.SlotIndex,
        "OwnerName": pal.OwnerName or None,
        "CharacterID": pal.CharacterID,
        "IconAccessKey": pal.IconAccessKey or None,
        "DataAccessKey": pal.DataAccessKey or None,
        "I18nName": pal.I18nName or None,
        "DisplayName": pal.DisplayName or None,
        "NickName": pal.NickName or "",
        "Gender": pal.Gender.value if pal.Gender else None,
        "Level": pal.Level or 1,
        "FriendshipLevel": pal.FriendshipLevel or 0,
        "HasBaseVariant": pal.HasBaseVariant,
        "HasBossVariant": pal.HasBossVariant,
        "HasTowerVariant": pal.HasTowerVariant,
        "HasWorkerSick": pal.HasWorkerSick,
        "IsFaintedPal": pal.IsFaintedPal,
        "Is_Unref_Pal": pal.is_unreferenced_pal,
        "in_owner_palbox": pal.in_owner_palbox,
        "IsHuman": pal.IsHuman,
        "IsBOSS": pal.IsBOSS or False,
        "IsRarePal": pal.IsRarePal or False,
        "IsTower": pal.IsTower or False,
        "IsRAID": pal.IsRAID or False,
        "IsPREDATOR": pal.IsPREDATOR or False,
        "IsOilrig": pal.IsOilrig or False,
        "IsExpeditionPal": pal.IsExpeditionPal,
        "ComputedMaxHP": pal.ComputedMaxHP or None,
        "ComputedAttack": pal.ComputedAttack or None,
        "ComputedDefense": pal.ComputedDefense or None,
        "ComputedCraftSpeed": pal.ComputedCraftSpeed or None,
        "Rank": pal.Rank if pal.Rank else 1,
        "Rank_HP": pal.Rank_HP or 0,
        "Rank_Attack": pal.Rank_Attack or 0,
        "Rank_Defence": pal.Rank_Defence or 0,
        "Rank_CraftSpeed": pal.Rank_CraftSpeed or 0,
        "Talent_HP": pal.Talent_HP or 0,
        "Talent_Melee": pal.Talent_Melee or 0,
        "Talent_Shot": pal.Talent_Shot or 0,
        "Talent_Defense": pal.Talent_Defense or 0,
        "PassiveSkillList": pal.PassiveSkillList or [],
        "EquipWaza": pal.EquipWaza or [],
        "MasteredWaza": pal.MasteredWaza or [],
        "Suitabilities": pal.WorkSuitabilities or {},
    }


@pal_blueprint.route("/dump_data", methods=["POST"])
@jwt_required()
def dump_data():
    PalGuid = request.json.get("PalGuid")
    PlayerUId = request.json.get("PlayerUId")
    if PlayerUId == "PAL_BASE_WORKER_BTN":
        pal = SaveManager().get_working_pal(PalGuid)
        LOGGER.info(f"Get BASE WORKER {pal}")
    else:
        try:
            player = SaveManager().get_player(PlayerUId)
            pal = player.get_pal(PalGuid)
            LOGGER.info(f"Get {player.NickName}'s pal: {pal}")
        except:
            pass
    if pal:
        return reply(0, pal.dump_obj())
    LOGGER.warning(f"Failed Getting Pal with PlayerID: {PlayerUId}, PalID: {PalGuid}")
    return reply(
        1, None, f"Failed Getting Pal with PlayerID: {PlayerUId}, PalID: {PalGuid}"
    )


@pal_blueprint.route("/pal/<pal_id>", methods=["DELETE"])
@jwt_required()
def delete_pal(pal_id):
    payload = request.get_json(silent=True) or {}
    try:
        session = SESSION_RUNTIME.get(payload.get("session_id"))
        command = DeletePal(
            session_id=session.session_id,
            expected_revision=payload.get(
                "expected_revision", session.revision
            ),
            pal_id=pal_id,
            impact_token=payload.get("impact_token"),
        )
        return reply(0, StructuralPalEditor(session).execute(command))
    except DomainError as error:
        return _domain_error(error)


@pal_blueprint.route("/add_pal", methods=["POST"])
@jwt_required()
def add_pal():
    payload = request.get_json(silent=True) or {}
    PlayerUId = payload.get("PlayerUId")
    if PlayerUId == "PAL_BASE_WORKER_BTN":
        return _domain_error(
            DomainError(
                code="PAL_LOCATION_UNSUPPORTED",
                message="Directly adding a Pal to a base requires the base-container command.",
                field="PlayerUId",
                http_status=409,
            )
        )
    try:
        session = SESSION_RUNTIME.get(payload.get("session_id"))
        command = AddPal(
            session_id=session.session_id,
            expected_revision=payload.get(
                "expected_revision", session.revision
            ),
            player_id=PlayerUId,
            species_id=payload.get("species_id", "SheepBall"),
            container_type=_character_container_type(
                payload.get("container_type")
            ),
            target_slot=payload.get("target_slot"),
        )
        return reply(0, StructuralPalEditor(session).execute(command))
    except DomainError as error:
        return _domain_error(error)


@pal_blueprint.route("/dupe_pal", methods=["POST"])
@jwt_required()
def dupe_pal():
    payload = request.get_json(silent=True) or {}
    PalGuid = payload.get("PalGuid")
    PlayerUId = payload.get("PlayerUId")
    if PlayerUId == "PAL_BASE_WORKER_BTN":
        return _domain_error(
            DomainError(
                code="PAL_LOCATION_UNSUPPORTED",
                message="Directly cloning a Pal to a base requires the base-container command.",
                field="PlayerUId",
                http_status=409,
            )
        )
    try:
        session = SESSION_RUNTIME.get(payload.get("session_id"))
        command = ClonePal(
            session_id=session.session_id,
            expected_revision=payload.get(
                "expected_revision", session.revision
            ),
            source_pal_id=PalGuid,
            target_player_id=PlayerUId,
            container_type=_character_container_type(
                payload.get("container_type")
            ),
            target_slot=payload.get("target_slot"),
        )
        return reply(0, StructuralPalEditor(session).execute(command))
    except DomainError as error:
        return _domain_error(error)
