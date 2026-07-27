from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys
from threading import RLock
from typing import Any, Protocol

from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.remote.models import RemoteConnectionSpec


def _default_profile_path() -> Path:
    if sys.platform == "win32":
        root = os.environ.get("LOCALAPPDATA")
        if root:
            return Path(root) / "Palworld-Pal-Editor" / "remote-connection.json"
    if sys.platform == "darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "Palworld-Pal-Editor"
            / "remote-connection.json"
        )
    root = os.environ.get("XDG_CONFIG_HOME")
    if root:
        return Path(root) / "palworld-pal-editor" / "remote-connection.json"
    return (
        Path.home()
        / ".config"
        / "palworld-pal-editor"
        / "remote-connection.json"
    )


class CredentialProtector(Protocol):
    @property
    def available(self) -> bool: ...

    def protect(self, secret: str) -> str: ...

    def unprotect(self, payload: str) -> str: ...


class WindowsDpapiCredentialProtector:
    """Protect credentials for the current Windows account using DPAPI."""

    def __init__(
        self,
        *,
        entropy: bytes = b"Palworld-Pal-Editor/remote-credential/v1",
        description: str = (
            "Palworld Pal Editor remote administrator credential"
        ),
    ) -> None:
        self._entropy = entropy
        self._description = description

    class _DataBlob(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_byte)),
        ]

    @property
    def available(self) -> bool:
        return sys.platform == "win32"

    @classmethod
    def _blob(cls, value: bytes):
        buffer = ctypes.create_string_buffer(value)
        blob = cls._DataBlob(
            len(value),
            ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)),
        )
        return blob, buffer

    def protect(self, secret: str) -> str:
        if not self.available:
            raise RuntimeError("Windows DPAPI is not available.")
        source, source_buffer = self._blob(secret.encode("utf-8"))
        entropy, entropy_buffer = self._blob(self._entropy)
        output = self._DataBlob()
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
        kernel32.LocalFree.restype = wintypes.HLOCAL
        crypt32.CryptProtectData.argtypes = [
            ctypes.POINTER(self._DataBlob),
            wintypes.LPCWSTR,
            ctypes.POINTER(self._DataBlob),
            wintypes.LPVOID,
            wintypes.LPVOID,
            wintypes.DWORD,
            ctypes.POINTER(self._DataBlob),
        ]
        crypt32.CryptProtectData.restype = wintypes.BOOL
        if not crypt32.CryptProtectData(
            ctypes.byref(source),
            self._description,
            ctypes.byref(entropy),
            None,
            None,
            0x01,
            ctypes.byref(output),
        ):
            raise ctypes.WinError()
        try:
            protected = ctypes.string_at(output.pbData, output.cbData)
            return base64.b64encode(protected).decode("ascii")
        finally:
            kernel32.LocalFree(output.pbData)
            del source_buffer, entropy_buffer

    def unprotect(self, payload: str) -> str:
        if not self.available:
            raise RuntimeError("Windows DPAPI is not available.")
        protected = base64.b64decode(payload, validate=True)
        source, source_buffer = self._blob(protected)
        entropy, entropy_buffer = self._blob(self._entropy)
        output = self._DataBlob()
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
        kernel32.LocalFree.restype = wintypes.HLOCAL
        crypt32.CryptUnprotectData.argtypes = [
            ctypes.POINTER(self._DataBlob),
            ctypes.POINTER(wintypes.LPWSTR),
            ctypes.POINTER(self._DataBlob),
            wintypes.LPVOID,
            wintypes.LPVOID,
            wintypes.DWORD,
            ctypes.POINTER(self._DataBlob),
        ]
        crypt32.CryptUnprotectData.restype = wintypes.BOOL
        if not crypt32.CryptUnprotectData(
            ctypes.byref(source),
            None,
            ctypes.byref(entropy),
            None,
            None,
            0x01,
            ctypes.byref(output),
        ):
            raise ctypes.WinError()
        try:
            return ctypes.string_at(output.pbData, output.cbData).decode("utf-8")
        finally:
            kernel32.LocalFree(output.pbData)
            del source_buffer, entropy_buffer


@dataclass(frozen=True)
class RemoteConnectionProfile:
    address: str
    username: str
    certificate_fingerprint: str | None
    allow_insecure_local: bool
    credential_saved: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "address": self.address,
            "username": self.username,
            "certificate_fingerprint": self.certificate_fingerprint,
            "allow_insecure_local": self.allow_insecure_local,
            "credential_saved": self.credential_saved,
        }


class RemoteConnectionProfileStore:
    def __init__(
        self,
        path: Path | None = None,
        protector: CredentialProtector | None = None,
    ) -> None:
        self._path = path or _default_profile_path()
        self._protector = protector or WindowsDpapiCredentialProtector()
        self._lock = RLock()

    @property
    def credential_storage_available(self) -> bool:
        return self._protector.available

    def load(self) -> RemoteConnectionProfile | None:
        with self._lock:
            data = self._read()
        if data is None:
            return None
        return self._profile_from_data(data)

    def save(
        self,
        spec: RemoteConnectionSpec,
        *,
        remember_credential: bool,
    ) -> RemoteConnectionProfile:
        if remember_credential and not self._protector.available:
            raise DomainError(
                code="REMOTE_CREDENTIAL_STORAGE_UNAVAILABLE",
                message=(
                    "Secure remote credential storage is only available "
                    "for the current Windows account."
                ),
                field="remember_credential",
                http_status=409,
            )
        data: dict[str, Any] = {
            "version": 1,
            "address": spec.base_url,
            "username": spec.username,
            "certificate_fingerprint": spec.certificate_fingerprint,
            "allow_insecure_local": spec.allow_insecure_local,
        }
        if remember_credential:
            try:
                data["protected_admin_password"] = self._protector.protect(
                    spec.admin_password
                )
            except Exception as error:
                raise DomainError(
                    code="REMOTE_CREDENTIAL_SAVE_FAILED",
                    message="The remote administrator credential could not be saved securely.",
                    field="remember_credential",
                    http_status=500,
                ) from error
        with self._lock:
            self._write(data)
        return self._profile_from_data(data)

    def reconnect_spec(self) -> RemoteConnectionSpec:
        with self._lock:
            data = self._read()
        if data is None:
            raise DomainError(
                code="REMOTE_PROFILE_NOT_FOUND",
                message="No saved remote server connection was found.",
                http_status=404,
            )
        protected = data.get("protected_admin_password")
        if not isinstance(protected, str) or not protected:
            raise DomainError(
                code="REMOTE_CREDENTIAL_NOT_SAVED",
                message="Enter the administrator password to reconnect.",
                field="admin_password",
                http_status=409,
            )
        try:
            admin_password = self._protector.unprotect(protected)
        except Exception as error:
            raise DomainError(
                code="REMOTE_CREDENTIAL_READ_FAILED",
                message=(
                    "The saved administrator credential cannot be read "
                    "by the current Windows account."
                ),
                field="admin_password",
                http_status=409,
            ) from error
        return RemoteConnectionSpec.create(
            address=data.get("address"),
            username=data.get("username", "admin"),
            admin_password=admin_password,
            certificate_fingerprint=data.get("certificate_fingerprint"),
            allow_insecure_local=data.get("allow_insecure_local", False),
        )

    def _read(self) -> dict[str, Any] | None:
        if not self._path.exists():
            return None
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise DomainError(
                code="REMOTE_PROFILE_READ_FAILED",
                message="The saved remote server connection could not be read.",
                http_status=500,
            ) from error
        if not isinstance(data, dict) or data.get("version") != 1:
            raise DomainError(
                code="REMOTE_PROFILE_INVALID",
                message="The saved remote server connection is invalid.",
                http_status=500,
            )
        return data

    def _write(self, data: dict[str, Any]) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._path.with_suffix(f"{self._path.suffix}.tmp")
            temporary.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temporary, self._path)
            if sys.platform != "win32":
                self._path.chmod(0o600)
        except OSError as error:
            raise DomainError(
                code="REMOTE_PROFILE_SAVE_FAILED",
                message="The remote server connection could not be saved.",
                http_status=500,
            ) from error

    @staticmethod
    def _profile_from_data(data: dict[str, Any]) -> RemoteConnectionProfile:
        address = data.get("address")
        username = data.get("username", "admin")
        if not isinstance(address, str) or not address:
            raise DomainError(
                code="REMOTE_PROFILE_INVALID",
                message="The saved remote server connection is invalid.",
                http_status=500,
            )
        if not isinstance(username, str) or not username:
            raise DomainError(
                code="REMOTE_PROFILE_INVALID",
                message="The saved remote server connection is invalid.",
                http_status=500,
            )
        fingerprint = data.get("certificate_fingerprint")
        if fingerprint is not None and not isinstance(fingerprint, str):
            raise DomainError(
                code="REMOTE_PROFILE_INVALID",
                message="The saved remote server connection is invalid.",
                http_status=500,
            )
        return RemoteConnectionProfile(
            address=address,
            username=username,
            certificate_fingerprint=fingerprint,
            allow_insecure_local=data.get("allow_insecure_local") is True,
            credential_saved=bool(data.get("protected_admin_password")),
        )


REMOTE_CONNECTION_PROFILE_STORE = RemoteConnectionProfileStore()
