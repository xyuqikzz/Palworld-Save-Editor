from __future__ import annotations

from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from palworld_pal_editor.application.preset_service import PresetService
from palworld_pal_editor.application.runtime import SESSION_RUNTIME
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.utils.util import reply


preset_blueprint = Blueprint("preset", __name__)


def _domain_error(error: DomainError):
    return reply(1, msg=error.message, error=error.to_dict()), error.http_status


def _payload(allowed: set[str]) -> dict:
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        raise DomainError(
            code="INVALID_REQUEST",
            message="A JSON object is required.",
            http_status=400,
        )
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise DomainError(
            code="UNSUPPORTED_COMMAND_FIELD",
            message="The request contains unsupported fields.",
            details={"fields": unknown},
            http_status=400,
        )
    return value


def _targets(value) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) or not item for item in value)
    ):
        raise DomainError(
            code="INVALID_PRESET_TARGETS",
            message="target_ids must be an array of non-empty IDs.",
            field="target_ids",
            http_status=400,
        )
    return tuple(value)


@preset_blueprint.route("/export", methods=["POST"])
@jwt_required()
def export_preset():
    try:
        payload = _payload({"session_id", "kind", "target_id"})
        session = SESSION_RUNTIME.get(payload.get("session_id"))
        kind = payload.get("kind")
        target_id = payload.get("target_id")
        if not isinstance(target_id, str) or not target_id:
            raise DomainError(
                code="INVALID_PRESET_TARGETS",
                message="target_id must be a non-empty ID.",
                field="target_id",
                http_status=400,
            )
        service = PresetService(session)
        if kind == "inventory":
            preset = service.export_inventory(target_id)
        elif kind == "equipment":
            preset = service.export_inventory(target_id, equipment_only=True)
        elif kind == "skills":
            preset = service.export_skills(target_id)
        elif kind == "pal":
            preset = service.export_pal(target_id)
        else:
            raise DomainError(
                code="PRESET_KIND_UNSUPPORTED",
                message="The preset kind is not supported.",
                field="kind",
                http_status=400,
            )
        return reply(0, {"preset": preset})
    except DomainError as error:
        return _domain_error(error)


@preset_blueprint.route("/preview", methods=["POST"])
@jwt_required()
def preview_preset():
    try:
        payload = _payload(
            {"session_id", "expected_revision", "preset", "target_ids"}
        )
        session = SESSION_RUNTIME.get(payload.get("session_id"))
        result = PresetService(session).preview_apply(
            session_id=payload.get("session_id"),
            expected_revision=payload.get("expected_revision"),
            preset=payload.get("preset"),
            target_ids=_targets(payload.get("target_ids")),
        )
        return reply(0, result)
    except DomainError as error:
        return _domain_error(error)


@preset_blueprint.route("/apply", methods=["POST"])
@jwt_required()
def apply_preset():
    try:
        payload = _payload(
            {
                "session_id",
                "expected_revision",
                "preset",
                "target_ids",
                "impact_token",
            }
        )
        session = SESSION_RUNTIME.get(payload.get("session_id"))
        result = PresetService(session).apply(
            session_id=payload.get("session_id"),
            expected_revision=payload.get("expected_revision"),
            preset=payload.get("preset"),
            target_ids=_targets(payload.get("target_ids")),
            impact_token=payload.get("impact_token"),
        )
        return reply(0, result)
    except DomainError as error:
        return _domain_error(error)
