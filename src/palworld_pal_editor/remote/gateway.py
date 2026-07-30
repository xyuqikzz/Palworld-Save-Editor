from __future__ import annotations

import hashlib
from pathlib import Path
import re
from typing import Any, Protocol
from urllib.parse import quote
import warnings

import requests
from requests.adapters import HTTPAdapter
from urllib3.exceptions import InsecureRequestWarning

from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.remote.models import (
    BridgeConnection,
    REMOTE_PROTOCOL_VERSION,
    RemoteCommand,
    RemoteConnectionSpec,
)


class RemoteBridgePort(Protocol):
    def connect(self, spec: RemoteConnectionSpec) -> BridgeConnection: ...

    def status(self, connection: BridgeConnection) -> dict[str, Any]: ...

    def players(self, connection: BridgeConnection) -> list[dict[str, Any]]: ...

    def guilds(self, connection: BridgeConnection) -> list[dict[str, Any]]: ...

    def map_snapshot(
        self, connection: BridgeConnection
    ) -> dict[str, Any]: ...

    def player_details(
        self,
        connection: BridgeConnection,
        player_id: str,
    ) -> dict[str, Any]: ...

    def inventory(
        self,
        connection: BridgeConnection,
        player_id: str,
    ) -> dict[str, Any]: ...

    def pals(
        self,
        connection: BridgeConnection,
        player_id: str,
        *,
        collection: str,
        page: int,
        page_size: int,
    ) -> dict[str, Any]: ...

    def create_snapshot(
        self, connection: BridgeConnection
    ) -> dict[str, Any]: ...

    def snapshot(
        self,
        connection: BridgeConnection,
        snapshot_id: str,
    ) -> dict[str, Any]: ...

    def download_snapshot_file(
        self,
        connection: BridgeConnection,
        snapshot_id: str,
        file_id: str,
        destination: Path,
        *,
        expected_size: int,
        expected_sha256: str,
    ) -> None: ...

    def execute(
        self, connection: BridgeConnection, command: RemoteCommand
    ) -> dict[str, Any]: ...

    def disconnect(self, connection: BridgeConnection) -> None: ...


class _FingerprintAdapter(HTTPAdapter):
    def __init__(self, fingerprint: str) -> None:
        self._fingerprint = fingerprint
        super().__init__()

    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        pool_kwargs["assert_fingerprint"] = self._fingerprint
        return super().init_poolmanager(
            connections, maxsize, block=block, **pool_kwargs
        )


class HttpRemoteBridgeAdapter:
    """HTTPS adapter for the Pal Editor Bridge v1 protocol."""

    def __init__(self, *, timeout_seconds: float = 10.0) -> None:
        self._timeout_seconds = timeout_seconds
        self._session = requests.Session()
        self._fingerprint: str | None = None

    def connect(self, spec: RemoteConnectionSpec) -> BridgeConnection:
        if spec.certificate_fingerprint:
            self._fingerprint = spec.certificate_fingerprint
            self._session.mount(
                f"{spec.base_url}/",
                _FingerprintAdapter(spec.certificate_fingerprint),
            )
        payload = self._request(
            "POST",
            f"{spec.base_url}/v1/auth/login",
            json={
                "protocolVersion": REMOTE_PROTOCOL_VERSION,
                "username": spec.username,
                "adminPassword": spec.admin_password,
            },
        )
        return BridgeConnection.from_payload(spec.base_url, payload)

    def status(self, connection: BridgeConnection) -> dict[str, Any]:
        payload = self._request(
            "GET",
            f"{connection.base_url}/v1/status",
            token=connection.token,
        )
        if not isinstance(payload, dict):
            raise _protocol_error("The bridge status response must be an object.")
        return payload

    def players(self, connection: BridgeConnection) -> list[dict[str, Any]]:
        payload = self._request(
            "GET",
            f"{connection.base_url}/v1/players",
            token=connection.token,
        )
        if not isinstance(payload, dict) or not isinstance(
            payload.get("players"), list
        ):
            raise _protocol_error("The bridge player response is invalid.")
        if any(not isinstance(row, dict) for row in payload["players"]):
            raise _protocol_error("The bridge player response is invalid.")
        return payload["players"]

    def guilds(self, connection: BridgeConnection) -> list[dict[str, Any]]:
        payload = self._request(
            "GET",
            f"{connection.base_url}/v1/guilds",
            token=connection.token,
        )
        if not isinstance(payload, dict) or not isinstance(
            payload.get("guilds"), list
        ):
            raise _protocol_error("The bridge guild response is invalid.")
        if any(not isinstance(row, dict) for row in payload["guilds"]):
            raise _protocol_error("The bridge guild response is invalid.")
        return payload["guilds"]

    def map_snapshot(
        self, connection: BridgeConnection
    ) -> dict[str, Any]:
        payload = self._request(
            "GET",
            f"{connection.base_url}/v1/map",
            token=connection.token,
        )
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("players"), list)
            or not isinstance(payload.get("guilds"), list)
            or any(not isinstance(row, dict) for row in payload["players"])
            or any(not isinstance(row, dict) for row in payload["guilds"])
        ):
            raise _protocol_error("The bridge map response is invalid.")
        return payload

    def player_details(
        self,
        connection: BridgeConnection,
        player_id: str,
    ) -> dict[str, Any]:
        encoded_player_id = quote(player_id, safe="")
        payload = self._request(
            "GET",
            (
                f"{connection.base_url}/v1/player-details"
                f"?playerId={encoded_player_id}"
            ),
            token=connection.token,
        )
        if not isinstance(payload, dict):
            raise _protocol_error(
                "The bridge player-detail response is invalid."
            )
        if not isinstance(payload.get("player"), dict):
            raise _protocol_error(
                "The bridge player-detail response is invalid."
            )
        return payload

    def inventory(
        self,
        connection: BridgeConnection,
        player_id: str,
    ) -> dict[str, Any]:
        encoded_player_id = quote(player_id, safe="")
        payload = self._request(
            "GET",
            (
                f"{connection.base_url}/v1/player-inventory"
                f"?playerId={encoded_player_id}"
            ),
            token=connection.token,
        )
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("containers"), list)
        ):
            raise _protocol_error(
                "The bridge inventory response is invalid."
            )
        return payload

    def pals(
        self,
        connection: BridgeConnection,
        player_id: str,
        *,
        collection: str,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        encoded_player_id = quote(player_id, safe="")
        encoded_collection = quote(collection, safe="")
        payload = self._request(
            "GET",
            (
                f"{connection.base_url}/v1/player-pals"
                f"?playerId={encoded_player_id}"
                f"&collection={encoded_collection}&page={page}&pageSize={page_size}"
            ),
            token=connection.token,
        )
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("entries"), list)
            or not isinstance(payload.get("pageIndex"), int)
            or not isinstance(payload.get("pageSize"), int)
            or not isinstance(payload.get("pageCount"), int)
        ):
            raise _protocol_error(
                "The bridge Pal response is invalid."
            )
        return payload

    def execute(
        self, connection: BridgeConnection, command: RemoteCommand
    ) -> dict[str, Any]:
        payload = self._request(
            "POST",
            f"{connection.base_url}/v1/commands",
            token=connection.token,
            json=command.to_payload(),
        )
        if not isinstance(payload, dict):
            raise _protocol_error("The bridge command response must be an object.")
        if payload.get("commandId") != command.command_id:
            raise _protocol_error("The bridge returned a different command ID.")
        return payload

    def create_snapshot(
        self, connection: BridgeConnection
    ) -> dict[str, Any]:
        payload = self._request(
            "POST",
            f"{connection.base_url}/v1/snapshots",
            token=connection.token,
            json={"scope": "players"},
        )
        return self._snapshot_payload(payload)

    def snapshot(
        self,
        connection: BridgeConnection,
        snapshot_id: str,
    ) -> dict[str, Any]:
        normalized_snapshot_id = self._opaque_id(
            snapshot_id, field="snapshot_id"
        )
        payload = self._request(
            "GET",
            (
                f"{connection.base_url}/v1/snapshots/"
                f"{normalized_snapshot_id}"
            ),
            token=connection.token,
        )
        return self._snapshot_payload(payload)

    def download_snapshot_file(
        self,
        connection: BridgeConnection,
        snapshot_id: str,
        file_id: str,
        destination: Path,
        *,
        expected_size: int,
        expected_sha256: str,
    ) -> None:
        normalized_snapshot_id = self._opaque_id(
            snapshot_id, field="snapshot_id"
        )
        normalized_file_id = self._opaque_id(file_id, field="file_id")
        if (
            not isinstance(expected_size, int)
            or isinstance(expected_size, bool)
            or expected_size < 0
            or expected_size > 16 * 1024 * 1024 * 1024
            or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256)
        ):
            raise _protocol_error(
                "The bridge snapshot file metadata is invalid."
            )
        headers = {
            "Accept": "application/octet-stream",
            "Authorization": f"Bearer {connection.token}",
        }
        verify_tls = self._fingerprint is None
        try:
            with warnings.catch_warnings():
                if not verify_tls:
                    warnings.simplefilter("ignore", InsecureRequestWarning)
                with self._session.get(
                    (
                        f"{connection.base_url}/v1/snapshots/"
                        f"{normalized_snapshot_id}/files/"
                        f"{normalized_file_id}"
                    ),
                    headers=headers,
                    timeout=self._timeout_seconds,
                    verify=verify_tls,
                    stream=True,
                ) as response:
                    if response.status_code in {401, 403}:
                        raise DomainError(
                            code="REMOTE_AUTH_FAILED",
                            message=(
                                "The Palworld administrator credentials "
                                "were rejected."
                            ),
                            retryable=False,
                            http_status=401,
                        )
                    if not response.ok:
                        raise DomainError(
                            code="REMOTE_SNAPSHOT_DOWNLOAD_FAILED",
                            message=(
                                "The bridge snapshot file could not be "
                                "downloaded."
                            ),
                            retryable=response.status_code >= 500,
                            http_status=(
                                response.status_code
                                if 400 <= response.status_code <= 599
                                else 502
                            ),
                        )
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    digest = hashlib.sha256()
                    size = 0
                    with destination.open("xb") as output:
                        for chunk in response.iter_content(1024 * 1024):
                            if not chunk:
                                continue
                            size += len(chunk)
                            if size > expected_size:
                                raise _protocol_error(
                                    "The bridge snapshot file exceeded "
                                    "its declared size."
                                )
                            digest.update(chunk)
                            output.write(chunk)
        except requests.exceptions.SSLError as error:
            raise DomainError(
                code="REMOTE_TLS_FAILED",
                message=(
                    "The remote bridge TLS certificate could not be verified."
                ),
                retryable=False,
                http_status=502,
            ) from error
        except requests.exceptions.Timeout as error:
            raise DomainError(
                code="REMOTE_TIMEOUT",
                message="The remote bridge did not respond in time.",
                retryable=True,
                http_status=504,
            ) from error
        except requests.exceptions.ConnectionError as error:
            raise DomainError(
                code="REMOTE_CONNECTION_FAILED",
                message="The remote bridge could not be reached.",
                retryable=True,
                http_status=502,
            ) from error
        if size != expected_size or digest.hexdigest() != expected_sha256:
            destination.unlink(missing_ok=True)
            raise DomainError(
                code="REMOTE_SNAPSHOT_HASH_MISMATCH",
                message=(
                    "The downloaded snapshot file did not match its "
                    "declared SHA-256."
                ),
                retryable=True,
                http_status=502,
            )

    @staticmethod
    def _opaque_id(value: object, *, field: str) -> str:
        if not isinstance(value, str) or not re.fullmatch(
            r"[0-9a-f]{32}", value
        ):
            raise _protocol_error(
                f"The bridge {field.replace('_', ' ')} is invalid."
            )
        return value

    @staticmethod
    def _snapshot_payload(payload: object) -> dict[str, Any]:
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("id"), str)
            or not isinstance(payload.get("state"), str)
            or not isinstance(payload.get("files"), list)
        ):
            raise _protocol_error(
                "The bridge snapshot response is invalid."
            )
        return payload

    def disconnect(self, connection: BridgeConnection) -> None:
        try:
            self._request(
                "POST",
                f"{connection.base_url}/v1/auth/logout",
                token=connection.token,
            )
        except DomainError:
            pass
        finally:
            self._session.close()

    def _request(
        self,
        method: str,
        url: str,
        *,
        token: str | None = None,
        json: dict[str, Any] | None = None,
    ) -> object:
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        verify_tls = self._fingerprint is None
        try:
            with warnings.catch_warnings():
                if not verify_tls:
                    warnings.simplefilter("ignore", InsecureRequestWarning)
                response = self._session.request(
                    method,
                    url,
                    headers=headers,
                    json=json,
                    timeout=self._timeout_seconds,
                    verify=verify_tls,
                )
        except requests.exceptions.SSLError as error:
            raise DomainError(
                code="REMOTE_TLS_FAILED",
                message="The remote bridge TLS certificate could not be verified.",
                retryable=False,
                http_status=502,
            ) from error
        except requests.exceptions.Timeout as error:
            raise DomainError(
                code="REMOTE_TIMEOUT",
                message="The remote bridge did not respond in time.",
                retryable=True,
                http_status=504,
            ) from error
        except requests.exceptions.ConnectionError as error:
            raise DomainError(
                code="REMOTE_CONNECTION_FAILED",
                message="The remote bridge could not be reached.",
                retryable=True,
                http_status=502,
            ) from error
        try:
            payload = response.json()
        except ValueError as error:
            raise _protocol_error(
                "The remote bridge returned a non-JSON response."
            ) from error
        if response.status_code in {401, 403}:
            raise DomainError(
                code="REMOTE_AUTH_FAILED",
                message="The Palworld administrator credentials were rejected.",
                retryable=False,
                http_status=401,
            )
        if not response.ok:
            message = (
                payload.get("message")
                if isinstance(payload, dict)
                else "The remote bridge rejected the request."
            )
            error = payload.get("error") if isinstance(payload, dict) else None
            raise DomainError(
                code=(
                    str(error.get("code"))
                    if isinstance(error, dict) and error.get("code")
                    else "REMOTE_BRIDGE_REJECTED"
                ),
                message=str(message or "The remote bridge rejected the request."),
                details=(
                    error.get("details", {})
                    if isinstance(error, dict)
                    and isinstance(error.get("details", {}), dict)
                    else {}
                ),
                retryable=response.status_code >= 500,
                http_status=(
                    response.status_code
                    if 400 <= response.status_code <= 599
                    else 502
                ),
            )
        return payload


def _protocol_error(message: str) -> DomainError:
    return DomainError(
        code="REMOTE_PROTOCOL_INVALID",
        message=message,
        retryable=False,
        http_status=502,
    )
