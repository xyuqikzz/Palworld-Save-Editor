from __future__ import annotations

import os
from pathlib import Path

from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from palworld_pal_editor.application.global_palbox import (
    GLOBAL_PALBOX_FILENAME,
    GLOBAL_PALBOX_RUNTIME,
    GlobalPalboxDocument,
)
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.storage.steam import _native_path
from palworld_pal_editor.utils.util import reply


global_palbox_blueprint = Blueprint("global_palbox", __name__)


def _error_response(error: DomainError):
    return reply(1, msg=error.message, error=error.to_dict()), error.http_status


def _payload() -> dict:
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        raise DomainError(
            code="INVALID_REQUEST",
            message="The request body must be an object.",
            http_status=400,
        )
    return value


def _required_text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DomainError(
            code="INVALID_REQUEST",
            message=f"{field} is required.",
            field=field,
            http_status=400,
        )
    return value.strip()


def _default_source() -> str | None:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return None
    root = Path(local_app_data) / "Pal" / "Saved" / "SaveGames"
    if not _native_path(root).is_dir():
        return None
    candidates: list[tuple[int, str, Path]] = []
    try:
        for account in _native_path(root).iterdir():
            source = account / GLOBAL_PALBOX_FILENAME
            try:
                if not source.is_file() or source.is_symlink():
                    continue
                stat = source.stat()
                display_path = root / account.name / GLOBAL_PALBOX_FILENAME
                candidates.append(
                    (stat.st_mtime_ns, str(display_path).casefold(), display_path)
                )
            except OSError:
                continue
    except OSError:
        return None
    if not candidates:
        return None
    return str(max(candidates)[2].resolve())


def _session_payload(document: GlobalPalboxDocument) -> dict:
    return {"session": document.summary(), "pals": document.pals()}


@global_palbox_blueprint.route("/default-source", methods=["GET"])
@jwt_required()
def default_source():
    return reply(
        0,
        {
            "path": _default_source(),
            "steamDirectFileSupported": True,
            "wgsWriteBackSupported": True,
        },
    )


@global_palbox_blueprint.route("/discover-xgp", methods=["POST"])
@jwt_required()
def discover_xgp_global_palboxes():
    try:
        payload = _payload()
        selected_path = _required_text(payload.get("path"), field="path")
        return reply(
            0,
            {"sources": GLOBAL_PALBOX_RUNTIME.discover_xgp(selected_path)},
        )
    except DomainError as error:
        return _error_response(error)


@global_palbox_blueprint.route("/catalog", methods=["GET"])
@jwt_required()
def catalog():
    return reply(0, GlobalPalboxDocument.catalog())


@global_palbox_blueprint.route("/open", methods=["POST"])
@jwt_required()
def open_global_palbox():
    try:
        payload = _payload()
        platform = payload.get("platform", "steam")
        document = (
            GLOBAL_PALBOX_RUNTIME.open(
                platform="xgp",
                source_id=_required_text(
                    payload.get("sourceId"),
                    field="sourceId",
                ),
            )
            if platform == "xgp"
            else GLOBAL_PALBOX_RUNTIME.open(
                _required_text(payload.get("path"), field="path")
            )
        )
        return reply(0, _session_payload(document))
    except DomainError as error:
        return _error_response(error)


@global_palbox_blueprint.route("/session", methods=["GET"])
@jwt_required()
def global_palbox_session():
    try:
        document = GLOBAL_PALBOX_RUNTIME.get(
            _required_text(request.args.get("session_id"), field="session_id")
        )
        return reply(0, _session_payload(document))
    except DomainError as error:
        return _error_response(error)


@global_palbox_blueprint.route("/pals/<pal_id>", methods=["PATCH"])
@jwt_required()
def update_global_palbox_pal(pal_id: str):
    try:
        payload = _payload()
        document = GLOBAL_PALBOX_RUNTIME.get(
            _required_text(payload.get("session_id"), field="session_id")
        )
        result = document.update_pal(
            pal_id=pal_id,
            expected_revision=payload.get("expected_revision"),
            values=payload.get("values"),
        )
        return reply(0, result)
    except DomainError as error:
        return _error_response(error)


@global_palbox_blueprint.route("/pals", methods=["POST"])
@jwt_required()
def add_global_palbox_pal():
    try:
        payload = _payload()
        document = GLOBAL_PALBOX_RUNTIME.get(
            _required_text(payload.get("session_id"), field="session_id")
        )
        result = document.add_pal(
            species_id=_required_text(payload.get("species_id"), field="species_id"),
            expected_revision=payload.get("expected_revision"),
        )
        return reply(0, result)
    except DomainError as error:
        return _error_response(error)


@global_palbox_blueprint.route("/pals/<pal_id>/clone", methods=["POST"])
@jwt_required()
def clone_global_palbox_pal(pal_id: str):
    try:
        payload = _payload()
        document = GLOBAL_PALBOX_RUNTIME.get(
            _required_text(payload.get("session_id"), field="session_id")
        )
        return reply(
            0,
            document.clone_pal(
                pal_id=pal_id,
                expected_revision=payload.get("expected_revision"),
            ),
        )
    except DomainError as error:
        return _error_response(error)


@global_palbox_blueprint.route("/pals/<pal_id>", methods=["DELETE"])
@jwt_required()
def delete_global_palbox_pal(pal_id: str):
    try:
        payload = _payload()
        document = GLOBAL_PALBOX_RUNTIME.get(
            _required_text(payload.get("session_id"), field="session_id")
        )
        return reply(
            0,
            document.delete_pal(
                pal_id=pal_id,
                expected_revision=payload.get("expected_revision"),
            ),
        )
    except DomainError as error:
        return _error_response(error)


@global_palbox_blueprint.route("/save", methods=["POST"])
@jwt_required()
def save_global_palbox():
    try:
        payload = _payload()
        document = GLOBAL_PALBOX_RUNTIME.get(
            _required_text(payload.get("session_id"), field="session_id")
        )
        result = document.save(expected_revision=payload.get("expected_revision"))
        return reply(0, {**result, "session": document.summary()})
    except DomainError as error:
        return _error_response(error)


@global_palbox_blueprint.route("/close", methods=["POST"])
@jwt_required()
def close_global_palbox():
    try:
        payload = _payload()
        GLOBAL_PALBOX_RUNTIME.close(
            _required_text(payload.get("session_id"), field="session_id"),
            payload.get("expected_revision"),
            discard_changes=payload.get("discard_changes") is True,
        )
        return reply(0, {"closed": True})
    except DomainError as error:
        return _error_response(error)
