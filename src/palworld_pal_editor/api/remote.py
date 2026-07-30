from __future__ import annotations

from time import sleep

from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.remote.local import LOCAL_BRIDGE_DISCOVERY
from palworld_pal_editor.remote.models import RemoteCommand, RemoteConnectionSpec
from palworld_pal_editor.remote.profile import (
    REMOTE_CONNECTION_PROFILE_STORE,
)
from palworld_pal_editor.remote.session import (
    REMOTE_SESSION_RUNTIME,
    RemoteServerSession,
)
from palworld_pal_editor.utils.util import reply


remote_blueprint = Blueprint("remote", __name__)
_LOCAL_CONNECT_RETRY_DELAYS_SECONDS = (0.1, 0.3)
_LOCAL_CONNECT_RETRYABLE_CODES = frozenset(
    {
        "LOCAL_BRIDGE_NOT_FOUND",
        "REMOTE_CONNECTION_FAILED",
        "REMOTE_TIMEOUT",
    }
)


def _domain_error(error: DomainError):
    return reply(1, msg=error.message, error=error.to_dict()), error.http_status


def _json_object() -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise DomainError(
            code="INVALID_REQUEST",
            message="A JSON object is required.",
            http_status=400,
        )
    return payload


def _reject_unknown(payload: dict, allowed: set[str]) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise DomainError(
            code="UNSUPPORTED_COMMAND_FIELD",
            message="The request contains unsupported fields.",
            details={"fields": unknown},
            http_status=400,
        )


def _query_integer(
    name: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw_value = request.args.get(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as error:
        raise DomainError(
            code="REMOTE_PAL_PAGE_INVALID",
            message="The Palbox page parameters are invalid.",
            field=name,
            http_status=400,
        ) from error
    if value < minimum or value > maximum:
        raise DomainError(
            code="REMOTE_PAL_PAGE_INVALID",
            message="The Palbox page parameters are invalid.",
            field=name,
            http_status=400,
        )
    return value


def _open_local_session() -> tuple[RemoteServerSession, dict]:
    for attempt in range(len(_LOCAL_CONNECT_RETRY_DELAYS_SECONDS) + 1):
        session = None
        try:
            spec = LOCAL_BRIDGE_DISCOVERY.discover_spec()
            session = REMOTE_SESSION_RUNTIME.open(spec)
            return session, session.status()
        except DomainError as error:
            if session is not None:
                try:
                    REMOTE_SESSION_RUNTIME.close(session.session_id)
                except DomainError:
                    pass
            if (
                not error.retryable
                or error.code not in _LOCAL_CONNECT_RETRYABLE_CODES
                or attempt == len(_LOCAL_CONNECT_RETRY_DELAYS_SECONDS)
            ):
                raise
            sleep(_LOCAL_CONNECT_RETRY_DELAYS_SECONDS[attempt])
    raise AssertionError("Unreachable local Bridge retry state.")


@remote_blueprint.route("/connect", methods=["POST"])
@jwt_required()
def connect_remote():
    try:
        payload = _json_object()
        _reject_unknown(
            payload,
            {
                "address",
                "username",
                "admin_password",
                "certificate_fingerprint",
                "allow_insecure_local",
                "remember_credential",
            },
        )
        spec = RemoteConnectionSpec.create(
            address=payload.get("address"),
            username=payload.get("username", "admin"),
            admin_password=payload.get("admin_password"),
            certificate_fingerprint=payload.get("certificate_fingerprint"),
            allow_insecure_local=payload.get("allow_insecure_local", False),
        )
        session = REMOTE_SESSION_RUNTIME.open(spec)
        try:
            profile = REMOTE_CONNECTION_PROFILE_STORE.save(
                spec,
                remember_credential=payload.get("remember_credential") is True,
            )
        except DomainError:
            REMOTE_SESSION_RUNTIME.close(session.session_id)
            raise
        return reply(
            0,
            {
                **session.status(),
                "profile": profile.to_dict(),
            },
        )
    except DomainError as error:
        return _domain_error(error)


@remote_blueprint.route("/connect-local", methods=["POST"])
@jwt_required()
def connect_local_game():
    session = None
    try:
        payload = _json_object()
        _reject_unknown(payload, set())
        session, status = _open_local_session()
        if status.get("authoritative") is not True:
            instance_mode = str(status.get("instanceMode") or "unknown")
            REMOTE_SESSION_RUNTIME.close(session.session_id)
            session = None
            if instance_mode == "client":
                raise DomainError(
                    code="LOCAL_BRIDGE_NOT_HOST",
                    message=(
                        "This Palworld process joined another player's "
                        "world. Live management is available only to the host."
                    ),
                    retryable=False,
                    http_status=409,
                )
            raise DomainError(
                code="LOCAL_BRIDGE_NOT_READY",
                message=(
                    "Enter a single-player world or start the multiplayer "
                    "world as host, then try again."
                ),
                retryable=True,
                http_status=409,
            )
        return reply(
            0,
            {
                **status,
                "connection_kind": "local_game",
            },
        )
    except DomainError as error:
        if session is not None:
            try:
                REMOTE_SESSION_RUNTIME.close(session.session_id)
            except DomainError:
                pass
        return _domain_error(error)


@remote_blueprint.route("/profile", methods=["GET"])
@jwt_required()
def get_remote_profile():
    try:
        profile = REMOTE_CONNECTION_PROFILE_STORE.load()
        return reply(
            0,
            {
                "profile": profile.to_dict() if profile else None,
                "credential_storage_available": (
                    REMOTE_CONNECTION_PROFILE_STORE
                    .credential_storage_available
                ),
            },
        )
    except DomainError as error:
        return _domain_error(error)


@remote_blueprint.route("/reconnect", methods=["POST"])
@jwt_required()
def reconnect_remote():
    try:
        payload = _json_object()
        _reject_unknown(payload, set())
        spec = REMOTE_CONNECTION_PROFILE_STORE.reconnect_spec()
        session = REMOTE_SESSION_RUNTIME.open(spec)
        return reply(
            0,
            {
                **session.status(),
                "profile": REMOTE_CONNECTION_PROFILE_STORE.load().to_dict(),
            },
        )
    except DomainError as error:
        return _domain_error(error)


@remote_blueprint.route("/session", methods=["GET"])
@jwt_required()
def get_current_remote_session():
    try:
        return reply(0, REMOTE_SESSION_RUNTIME.current().status())
    except DomainError as error:
        return _domain_error(error)


@remote_blueprint.route("/status", methods=["GET"])
@jwt_required()
def get_remote_status():
    try:
        session = REMOTE_SESSION_RUNTIME.get(request.args.get("session_id"))
        return reply(0, session.status())
    except DomainError as error:
        return _domain_error(error)


@remote_blueprint.route("/players", methods=["GET"])
@remote_blueprint.route("/player-directory", methods=["GET"])
@jwt_required()
def get_remote_players():
    try:
        session = REMOTE_SESSION_RUNTIME.get(request.args.get("session_id"))
        return reply(0, session.players())
    except DomainError as error:
        return _domain_error(error)


@remote_blueprint.route("/guilds", methods=["GET"])
@jwt_required()
def get_remote_guilds():
    try:
        session = REMOTE_SESSION_RUNTIME.get(request.args.get("session_id"))
        return reply(0, session.guilds())
    except DomainError as error:
        return _domain_error(error)


@remote_blueprint.route("/map", methods=["GET"])
@jwt_required()
def get_remote_map():
    try:
        session = REMOTE_SESSION_RUNTIME.get(request.args.get("session_id"))
        return reply(0, session.map_snapshot())
    except DomainError as error:
        return _domain_error(error)


@remote_blueprint.route(
    "/players/<string:player_id>/details",
    methods=["GET"],
)
@jwt_required()
def get_remote_player_details(player_id: str):
    try:
        session = REMOTE_SESSION_RUNTIME.get(request.args.get("session_id"))
        return reply(0, session.player_details(player_id))
    except DomainError as error:
        return _domain_error(error)


@remote_blueprint.route(
    "/players/<string:player_id>/inventory",
    methods=["GET"],
)
@jwt_required()
def get_remote_player_inventory(player_id: str):
    try:
        session = REMOTE_SESSION_RUNTIME.get(request.args.get("session_id"))
        return reply(0, session.player_inventory(player_id))
    except DomainError as error:
        return _domain_error(error)


@remote_blueprint.route(
    "/players/<string:player_id>/pals",
    methods=["GET"],
)
@jwt_required()
def get_remote_player_pals(player_id: str):
    try:
        session = REMOTE_SESSION_RUNTIME.get(request.args.get("session_id"))
        return reply(
            0,
            session.player_pals(
                player_id,
                collection=request.args.get("collection", "palbox"),
                page=_query_integer(
                    "page",
                    default=0,
                    minimum=0,
                    maximum=100000,
                ),
                page_size=_query_integer(
                    "page_size",
                    default=12,
                    minimum=1,
                    maximum=30,
                ),
            ),
        )
    except DomainError as error:
        return _domain_error(error)


@remote_blueprint.route("/commands", methods=["POST"])
@jwt_required()
def execute_remote_command():
    try:
        payload = _json_object()
        _reject_unknown(
            payload,
            {
                "session_id",
                "expected_revision",
                "command_id",
                "operation",
                "target",
                "payload",
            },
        )
        session = REMOTE_SESSION_RUNTIME.get(payload.get("session_id"))
        command = RemoteCommand.create(
            command_id=payload.get("command_id"),
            operation=payload.get("operation"),
            target=payload.get("target", {}),
            payload=payload.get("payload", {}),
            expected_revision=payload.get("expected_revision"),
        )
        return reply(0, session.live_players.execute(command))
    except DomainError as error:
        return _domain_error(error)


@remote_blueprint.route("/disconnect", methods=["POST"])
@jwt_required()
def disconnect_remote():
    try:
        payload = _json_object()
        _reject_unknown(payload, {"session_id"})
        return reply(
            0,
            REMOTE_SESSION_RUNTIME.close(payload.get("session_id")),
        )
    except DomainError as error:
        return _domain_error(error)
