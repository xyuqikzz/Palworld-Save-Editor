from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit
import uuid

from palworld_pal_editor.domain.errors import DomainError


REMOTE_PROTOCOL_VERSION = 1
DEFAULT_REMOTE_BRIDGE_PORT = 8213
_FINGERPRINT_RE = re.compile(r"^[0-9A-F]{64}$")


def normalize_certificate_fingerprint(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    normalized = value.replace(":", "").replace(" ", "").upper()
    if not _FINGERPRINT_RE.fullmatch(normalized):
        raise DomainError(
            code="REMOTE_CERTIFICATE_FINGERPRINT_INVALID",
            message="The certificate fingerprint must be a SHA-256 fingerprint.",
            field="certificate_fingerprint",
            http_status=400,
        )
    return normalized


@dataclass(frozen=True)
class RemoteConnectionSpec:
    base_url: str
    username: str
    admin_password: str = field(repr=False)
    certificate_fingerprint: str | None = None
    allow_insecure_local: bool = False

    @classmethod
    def create(
        cls,
        *,
        address: object,
        admin_password: object,
        username: object = "admin",
        certificate_fingerprint: object = None,
        allow_insecure_local: object = False,
    ) -> "RemoteConnectionSpec":
        if not isinstance(address, str) or not address.strip():
            raise DomainError(
                code="REMOTE_ADDRESS_REQUIRED",
                message="A remote server address is required.",
                field="address",
                http_status=400,
            )
        if not isinstance(admin_password, str) or not admin_password:
            raise DomainError(
                code="REMOTE_ADMIN_PASSWORD_REQUIRED",
                message="The Palworld administrator password is required.",
                field="admin_password",
                http_status=400,
            )
        if not isinstance(username, str) or not username.strip():
            raise DomainError(
                code="REMOTE_USERNAME_INVALID",
                message="The administrator username is required.",
                field="username",
                http_status=400,
            )
        if not isinstance(allow_insecure_local, bool):
            raise DomainError(
                code="REMOTE_INSECURE_FLAG_INVALID",
                message="allow_insecure_local must be a boolean.",
                field="allow_insecure_local",
                http_status=400,
            )

        raw_address = address.strip()
        if "://" not in raw_address:
            raw_address = f"https://{raw_address}"
        parsed = urlsplit(raw_address)
        if parsed.scheme not in {"https", "http"} or not parsed.hostname:
            raise DomainError(
                code="REMOTE_ADDRESS_INVALID",
                message="The remote server address must use HTTP or HTTPS.",
                field="address",
                http_status=400,
            )
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise DomainError(
                code="REMOTE_ADDRESS_INVALID",
                message="Credentials, query strings, and fragments are not allowed in the address.",
                field="address",
                http_status=400,
            )
        if parsed.path not in {"", "/"}:
            raise DomainError(
                code="REMOTE_ADDRESS_INVALID",
                message="The remote server address must not contain a path.",
                field="address",
                http_status=400,
            )
        try:
            port = parsed.port or DEFAULT_REMOTE_BRIDGE_PORT
        except ValueError as error:
            raise DomainError(
                code="REMOTE_PORT_INVALID",
                message="The remote bridge port is invalid.",
                field="address",
                http_status=400,
            ) from error
        if not 1 <= port <= 65535:
            raise DomainError(
                code="REMOTE_PORT_INVALID",
                message="The remote bridge port is invalid.",
                field="address",
                http_status=400,
            )

        host = parsed.hostname
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        base_url = urlunsplit((parsed.scheme, f"{host}:{port}", "", "", ""))
        fingerprint = normalize_certificate_fingerprint(
            certificate_fingerprint
            if isinstance(certificate_fingerprint, str)
            else None
        )
        if certificate_fingerprint is not None and not isinstance(
            certificate_fingerprint, str
        ):
            raise DomainError(
                code="REMOTE_CERTIFICATE_FINGERPRINT_INVALID",
                message="The certificate fingerprint must be a string.",
                field="certificate_fingerprint",
                http_status=400,
            )
        return cls(
            base_url=base_url,
            username=username.strip(),
            admin_password=admin_password,
            certificate_fingerprint=fingerprint,
            allow_insecure_local=allow_insecure_local,
        )


@dataclass(frozen=True)
class BridgeConnection:
    base_url: str
    token: str = field(repr=False)
    protocol_version: int
    bridge_version: str
    server_name: str
    game_version: str
    world_guid: str
    platform: str
    capabilities: frozenset[str]
    instance_kind: str = ""
    expires_at: str | None = None
    revision: int = 0

    @classmethod
    def from_payload(
        cls, base_url: str, payload: object
    ) -> "BridgeConnection":
        if not isinstance(payload, dict):
            raise _protocol_error("The bridge login response must be an object.")
        protocol_version = payload.get("protocolVersion")
        if protocol_version != REMOTE_PROTOCOL_VERSION:
            raise DomainError(
                code="REMOTE_PROTOCOL_MISMATCH",
                message="The remote bridge protocol version is not supported.",
                details={
                    "expected": REMOTE_PROTOCOL_VERSION,
                    "actual": protocol_version,
                },
                http_status=409,
            )
        token = payload.get("token")
        server = payload.get("server")
        capabilities = payload.get("capabilities")
        revision = payload.get("revision", 0)
        if (
            not isinstance(token, str)
            or not token
            or not isinstance(server, dict)
            or not isinstance(capabilities, list)
            or any(not isinstance(value, str) for value in capabilities)
            or not isinstance(revision, int)
            or isinstance(revision, bool)
            or revision < 0
        ):
            raise _protocol_error("The bridge login response is incomplete.")
        return cls(
            base_url=base_url,
            token=token,
            protocol_version=protocol_version,
            bridge_version=str(payload.get("bridgeVersion") or ""),
            server_name=str(server.get("name") or ""),
            game_version=str(server.get("gameVersion") or ""),
            world_guid=str(server.get("worldGuid") or ""),
            platform=str(server.get("platform") or ""),
            capabilities=frozenset(capabilities),
            instance_kind=str(server.get("instanceKind") or ""),
            expires_at=(
                str(payload["expiresAt"]) if payload.get("expiresAt") else None
            ),
            revision=revision,
        )


@dataclass(frozen=True)
class RemoteCommand:
    command_id: str
    operation: str
    target: dict[str, Any]
    payload: dict[str, Any]
    expected_revision: int

    @classmethod
    def create(
        cls,
        *,
        operation: object,
        target: object,
        payload: object,
        expected_revision: object,
        command_id: object = None,
    ) -> "RemoteCommand":
        if not isinstance(operation, str) or not operation.strip():
            raise DomainError(
                code="REMOTE_OPERATION_REQUIRED",
                message="A remote operation is required.",
                field="operation",
                http_status=400,
            )
        if not isinstance(target, dict):
            raise DomainError(
                code="REMOTE_TARGET_INVALID",
                message="The remote command target must be an object.",
                field="target",
                http_status=400,
            )
        if not isinstance(payload, dict):
            raise DomainError(
                code="REMOTE_PAYLOAD_INVALID",
                message="The remote command payload must be an object.",
                field="payload",
                http_status=400,
            )
        if isinstance(expected_revision, bool) or not isinstance(
            expected_revision, int
        ):
            raise DomainError(
                code="INVALID_REVISION",
                message="expected_revision must be an integer.",
                field="expected_revision",
                http_status=400,
            )
        normalized_command_id = (
            str(uuid.uuid4()) if command_id is None else str(command_id)
        )
        try:
            uuid.UUID(normalized_command_id)
        except (ValueError, AttributeError) as error:
            raise DomainError(
                code="REMOTE_COMMAND_ID_INVALID",
                message="command_id must be a UUID.",
                field="command_id",
                http_status=400,
            ) from error
        return cls(
            command_id=normalized_command_id,
            operation=operation.strip(),
            target=dict(target),
            payload=dict(payload),
            expected_revision=expected_revision,
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "protocolVersion": REMOTE_PROTOCOL_VERSION,
            "commandId": self.command_id,
            "operation": self.operation,
            "target": self.target,
            "payload": self.payload,
            "expectedRevision": self.expected_revision,
        }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _protocol_error(message: str) -> DomainError:
    return DomainError(
        code="REMOTE_PROTOCOL_INVALID",
        message=message,
        retryable=False,
        http_status=502,
    )
