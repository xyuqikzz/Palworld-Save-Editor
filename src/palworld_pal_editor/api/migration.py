from __future__ import annotations

from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from palworld_pal_editor.application.save_migration import SAVE_MIGRATION
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.domain.migration import (
    MigrationMode,
    MigrationRequest,
    MigrationSaveRef,
    PlayerIdentityMapping,
)
from palworld_pal_editor.domain.models import SavePlatform
from palworld_pal_editor.utils.util import reply


migration_blueprint = Blueprint("migration", __name__)


def _save_ref(value: object, *, field: str) -> MigrationSaveRef:
    if not isinstance(value, dict):
        raise DomainError(
            code=(
                "MIGRATION_SOURCE_INVALID"
                if field == "source"
                else "MIGRATION_TARGET_INVALID"
            ),
            message=f"Migration {field} must be an object.",
            field=field,
            http_status=400,
        )
    try:
        platform = SavePlatform(str(value.get("platform")))
    except ValueError as error:
        raise DomainError(
            code=(
                "MIGRATION_SOURCE_INVALID"
                if field == "source"
                else "MIGRATION_TARGET_INVALID"
            ),
            message=f"Migration {field} platform is invalid.",
            field=field,
            http_status=400,
        ) from error
    return MigrationSaveRef(
        platform=platform,
        path=value.get("path"),
        source_id=value.get("source_id") or value.get("sourceId"),
    )


@migration_blueprint.route("/analyze", methods=["POST"])
@jwt_required()
def analyze_migration():
    payload = request.get_json(silent=True) or {}
    try:
        try:
            mode = MigrationMode(str(payload.get("mode")))
        except ValueError as error:
            raise DomainError(
                code="MIGRATION_MODE_UNSUPPORTED",
                message="Migration mode must be full or character_only.",
                field="mode",
                http_status=400,
            ) from error
        plan = SAVE_MIGRATION.analyze(
            MigrationRequest(
                mode=mode,
                source=_save_ref(payload.get("source"), field="source"),
                target=_save_ref(payload.get("target"), field="target"),
            )
        )
        return reply(0, plan.to_dict())
    except DomainError as error:
        return reply(1, msg=error.message, error=error.to_dict()), error.http_status


@migration_blueprint.route("/execute", methods=["POST"])
@jwt_required()
def execute_migration():
    payload = request.get_json(silent=True) or {}
    try:
        mappings_value = payload.get("mappings")
        if not isinstance(mappings_value, list):
            raise DomainError(
                code="MIGRATION_PLAYER_MAPPING_REQUIRED",
                message="Migration mappings must be an array.",
                field="mappings",
                http_status=400,
            )
        mappings = tuple(
            PlayerIdentityMapping(
                source_player_uid=str(value.get("source_player_uid", "")),
                source_instance_id=str(value.get("source_instance_id", "")),
                target_player_uid=str(value.get("target_player_uid", "")),
                target_instance_id=str(value.get("target_instance_id", "")),
                evidence=str(value.get("evidence", "manual")),
                confirmed=value.get("confirmed") is True,
            )
            for value in mappings_value
            if isinstance(value, dict)
        )
        result = SAVE_MIGRATION.execute(
            str(payload.get("plan_id", "")),
            mappings,
            str(payload.get("operation_id", "")),
        )
        return reply(0, result.to_dict())
    except DomainError as error:
        return reply(1, msg=error.message, error=error.to_dict()), error.http_status


@migration_blueprint.route("/status", methods=["POST"])
@jwt_required()
def migration_status():
    payload = request.get_json(silent=True) or {}
    try:
        status = SAVE_MIGRATION.operation_status(
            str(payload.get("plan_id", "")),
            str(payload.get("operation_id", "")),
        )
        return reply(0, status)
    except DomainError as error:
        return reply(1, msg=error.message, error=error.to_dict()), error.http_status
