from __future__ import annotations

from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from palworld_pal_editor.application.batch_editor import BatchEditor
from palworld_pal_editor.application.runtime import SESSION_RUNTIME
from palworld_pal_editor.domain.commands import (
    AddPal, ClearItemSlot, ClonePal, DeletePal, MovePal, PutItem,
    RecoverDetachedPal, UnlockPalExpedition, UpdateItemCount, UpdatePalEnhancement,
    UpdatePalIdentity, UpdatePalProgression, UpdatePalSkills,
    UpdatePlayerIdentity, UpdatePlayerProgression, UpdatePlayerTechnology,
    UpdateDynamicItemAttributes,
)
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.domain.models import CharacterContainerType, ItemContainerType
from palworld_pal_editor.utils.util import reply


batch_blueprint = Blueprint("batch", __name__)


def _error(error: DomainError):
    return reply(1, msg=error.message, error=error.to_dict()), error.http_status


def _strict(payload, allowed: set[str]) -> None:
    if not isinstance(payload, dict):
        raise DomainError(
            code="INVALID_REQUEST", message="A JSON object is required.", http_status=400
        )
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise DomainError(
            code="UNSUPPORTED_COMMAND_FIELD",
            message="The request contains unsupported fields.",
            details={"fields": unknown},
            http_status=400,
        )


def _parse_operations(payload: dict, session_id: str, revision: int):
    values = payload.get("operations")
    if not isinstance(values, list):
        raise DomainError(
            code="INVALID_REQUEST",
            message="operations must be an array.",
            field="operations",
            http_status=400,
        )
    parsed = []
    for index, raw in enumerate(values):
        if not isinstance(raw, dict):
            raise DomainError(
                code="INVALID_REQUEST",
                message="Every batch operation must be an object.",
                details={"operation_index": index},
                http_status=400,
            )
        resource, command = raw.get("resource"), raw.get("command")
        base = {"session_id": session_id, "expected_revision": revision}
        try:
            if resource == "inventory":
                common = {"resource", "command", "player_id", "container_type", "slot_index"}
                fields = {
                    "update_item_count": {"expected_static_id", "count"},
                    "put_item": {"static_id", "count", "mode", "dynamic_init"},
                    "clear_item_slot": {"expected_static_id", "expected_dynamic_id"},
                    "update_dynamic_attributes": {
                        "expected_static_id", "expected_dynamic_id", "values",
                    },
                }
                _strict(raw, common | fields[command])
                target = {
                    **base,
                    "player_id": raw.get("player_id"),
                    "container_type": ItemContainerType(raw.get("container_type")),
                    "slot_index": raw.get("slot_index"),
                }
                if command == "update_item_count":
                    value = UpdateItemCount(
                        **target,
                        expected_static_id=raw.get("expected_static_id"),
                        count=raw.get("count"),
                    )
                elif command == "put_item":
                    value = PutItem(
                        **target,
                        static_id=raw.get("static_id"),
                        count=raw.get("count"),
                        mode=raw.get("mode", "empty_only"),
                        dynamic_init=raw.get("dynamic_init"),
                    )
                elif command == "clear_item_slot":
                    value = ClearItemSlot(
                        **target,
                        expected_static_id=raw.get("expected_static_id"),
                        expected_dynamic_id=raw.get("expected_dynamic_id"),
                    )
                else:
                    value = UpdateDynamicItemAttributes(
                        **target,
                        expected_static_id=raw.get("expected_static_id"),
                        expected_dynamic_id=raw.get("expected_dynamic_id"),
                        values=raw.get("values") or {},
                    )
            elif resource == "player":
                common = {"resource", "command", "player_id"}
                fields = {
                    "update_player_identity": {"name"},
                    "update_player_progression": {
                        "level", "experience", "technology_points",
                        "boss_technology_points",
                    },
                    "update_player_technology": {"recipe_id", "unlocked", "unlock_all"},
                }
                _strict(raw, common | fields[command])
                target = {**base, "player_id": raw.get("player_id")}
                if command == "update_player_identity":
                    value = UpdatePlayerIdentity(**target, name=raw.get("name"))
                elif command == "update_player_progression":
                    value = UpdatePlayerProgression(
                        **target,
                        level=raw.get("level"),
                        experience=raw.get("experience"),
                        technology_points=raw.get("technology_points"),
                        boss_technology_points=raw.get("boss_technology_points"),
                    )
                else:
                    value = UpdatePlayerTechnology(
                        **target,
                        recipe_id=raw.get("recipe_id"),
                        unlocked=raw.get("unlocked"),
                        unlock_all=raw.get("unlock_all", False),
                    )
            elif resource == "pal":
                common = {"resource", "command", "pal_id"}
                fields = {
                    "update_pal_identity": {
                        "name", "gender", "variant", "boss", "tower", "rare",
                    },
                    "update_pal_progression": {"values"},
                    "update_pal_skills": {"active", "mastered", "passive"},
                    "update_pal_enhancement": {"values", "work_suitability"},
                    "unlock_pal_expedition": set(),
                }
                _strict(raw, common | fields[command])
                target = {**base, "pal_id": raw.get("pal_id")}
                if command == "update_pal_identity":
                    value = UpdatePalIdentity(
                        **target,
                        name=raw.get("name"), gender=raw.get("gender"),
                        variant=raw.get("variant"), boss=raw.get("boss"),
                        tower=raw.get("tower"), rare=raw.get("rare"),
                    )
                elif command == "update_pal_progression":
                    value = UpdatePalProgression(**target, values=raw.get("values") or {})
                elif command == "update_pal_skills":
                    value = UpdatePalSkills(
                        **target,
                        active=tuple(raw["active"]) if raw.get("active") is not None else None,
                        mastered=tuple(raw["mastered"]) if raw.get("mastered") is not None else None,
                        passive=tuple(raw["passive"]) if raw.get("passive") is not None else None,
                    )
                elif command == "unlock_pal_expedition":
                    value = UnlockPalExpedition(**target)
                else:
                    value = UpdatePalEnhancement(
                        **target,
                        values=raw.get("values") or {},
                        work_suitability=raw.get("work_suitability") or {},
                    )
            elif resource == "structural_pal":
                common = {"resource", "command"}
                fields = {
                    "add_pal": {
                        "player_id", "species_id", "container_type", "target_slot",
                        "passive", "max_pal", "max_work", "unrestricted",
                    },
                    "clone_pal": {"source_pal_id", "target_player_id", "container_type", "target_slot"},
                    "move_pal": {"pal_id", "target_player_id", "container_type", "target_slot"},
                    "delete_pal": {"pal_id", "delete_impact_token"},
                    "recover_detached_pal": {"pal_id", "target_player_id", "container_type", "target_slot"},
                }
                _strict(raw, common | fields[command])
                container_type = CharacterContainerType(raw.get("container_type", "AUTO"))
                if command == "add_pal":
                    value = AddPal(
                        **base, player_id=raw.get("player_id"),
                        species_id=raw.get("species_id"), container_type=container_type,
                        target_slot=raw.get("target_slot"),
                        passive=raw.get("passive"),
                        max_pal=raw.get("max_pal", False),
                        max_work=raw.get("max_work", False),
                        unrestricted=raw.get("unrestricted", False),
                    )
                elif command == "clone_pal":
                    value = ClonePal(
                        **base, source_pal_id=raw.get("source_pal_id"),
                        target_player_id=raw.get("target_player_id"),
                        container_type=container_type, target_slot=raw.get("target_slot"),
                    )
                elif command == "move_pal":
                    value = MovePal(
                        **base, pal_id=raw.get("pal_id"),
                        target_player_id=raw.get("target_player_id"),
                        container_type=container_type, target_slot=raw.get("target_slot"),
                    )
                elif command == "delete_pal":
                    value = DeletePal(
                        **base, pal_id=raw.get("pal_id"),
                        impact_token=raw.get("delete_impact_token"),
                    )
                else:
                    value = RecoverDetachedPal(
                        **base, pal_id=raw.get("pal_id"),
                        target_player_id=raw.get("target_player_id"),
                        container_type=container_type, target_slot=raw.get("target_slot"),
                    )
            else:
                raise KeyError(resource)
        except (KeyError, TypeError, ValueError) as error:
            raise DomainError(
                code="UNSUPPORTED_COMMAND",
                message="The batch contains an unsupported or invalid operation.",
                details={
                    "operation_index": index,
                    "resource": resource,
                    "command": command,
                },
                http_status=400,
            ) from error
        parsed.append(value)
    return tuple(parsed)


@batch_blueprint.route("/preview", methods=["POST"])
@jwt_required()
def preview_batch():
    try:
        payload = request.get_json(silent=True)
        _strict(payload, {"session_id", "expected_revision", "operations"})
        session = SESSION_RUNTIME.get(payload.get("session_id"))
        operations = _parse_operations(
            payload, payload.get("session_id"), payload.get("expected_revision")
        )
        return reply(0, BatchEditor(session).preview(
            session_id=payload.get("session_id"),
            expected_revision=payload.get("expected_revision"),
            operations=operations,
        ))
    except DomainError as error:
        return _error(error)


@batch_blueprint.route("/commands", methods=["POST"])
@jwt_required()
def execute_batch():
    try:
        payload = request.get_json(silent=True)
        _strict(payload, {"session_id", "expected_revision", "operations", "impact_token"})
        session = SESSION_RUNTIME.get(payload.get("session_id"))
        operations = _parse_operations(
            payload, payload.get("session_id"), payload.get("expected_revision")
        )
        return reply(0, BatchEditor(session).execute(
            session_id=payload.get("session_id"),
            expected_revision=payload.get("expected_revision"),
            operations=operations,
            impact_token=payload.get("impact_token"),
        ))
    except DomainError as error:
        return _error(error)
