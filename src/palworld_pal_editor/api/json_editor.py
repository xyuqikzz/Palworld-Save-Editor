from __future__ import annotations

from flask import Blueprint, Response, request
from flask_jwt_extended import jwt_required

from palworld_pal_editor.application.raw_json_editor import RawJsonEditor
from palworld_pal_editor.application.runtime import SESSION_RUNTIME
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.utils.util import reply


json_editor_blueprint = Blueprint("json_editor", __name__)


def _error_response(error: DomainError):
    return reply(1, msg=error.message, error=error.to_dict()), error.http_status


@json_editor_blueprint.route("/files", methods=["GET"])
@jwt_required()
def list_files():
    try:
        session = SESSION_RUNTIME.get(request.args.get("session_id"))
        return reply(
            0,
            {
                "revision": session.revision,
                "files": RawJsonEditor().list_files(session),
                "pending_change_count": len(session.changes()),
                "raw_json_pending": session.raw_json_pending,
            },
        )
    except DomainError as error:
        return _error_response(error)


@json_editor_blueprint.route("/document", methods=["GET"])
@jwt_required()
def get_document():
    try:
        session = SESSION_RUNTIME.get(request.args.get("session_id"))
        document = RawJsonEditor().read_document(
            session,
            request.args.get("path", ""),
        )
        response = Response(
            document.pop("text"),
            status=200,
            content_type="application/json; charset=utf-8",
        )
        response.headers["X-Palworld-Path"] = document["path"]
        response.headers["X-Palworld-Revision"] = str(document["revision"])
        response.headers["X-Palworld-Json-Size"] = str(document["json_size"])
        response.headers["X-Palworld-Gvas-Size"] = str(document["gvas_size"])
        response.headers["X-Palworld-Sha256"] = document["sha256"]
        return response
    except DomainError as error:
        return _error_response(error)


@json_editor_blueprint.route("/document", methods=["POST"])
@jwt_required()
def apply_document():
    raw_revision = request.args.get("expected_revision")
    try:
        try:
            expected_revision = int(raw_revision) if raw_revision is not None else None
        except (TypeError, ValueError) as cause:
            raise DomainError(
                code="INVALID_REVISION",
                message="expected_revision must be an integer.",
                field="expected_revision",
                http_status=400,
            ) from cause
        session = SESSION_RUNTIME.get(request.args.get("session_id"))
        result = RawJsonEditor().apply_document(
            session,
            session_id=request.args.get("session_id", ""),
            expected_revision=expected_revision,
            relative_path=request.args.get("path", ""),
            text=request.get_data(cache=False, as_text=True),
        )
        return reply(0, result)
    except DomainError as error:
        return _error_response(error)
