from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sys
from typing import Protocol

from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.remote.models import (
    REMOTE_PROTOCOL_VERSION,
    RemoteConnectionSpec,
)
from palworld_pal_editor.remote.profile import (
    CredentialProtector,
    WindowsDpapiCredentialProtector,
)


_LOCAL_BRIDGE_ENTROPY = b"Palworld-Pal-Editor/local-bridge/v1"
_SUPPORTED_CLIENT_EXECUTABLES = {
    "palworld-win64-shipping.exe",
    "palworld-wingdk-shipping.exe",
}
_MAX_REGISTRATION_BYTES = 16 * 1024


def _default_instance_directory() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    if sys.platform == "win32" and root:
        return Path(root) / "Palworld-Pal-Editor" / "bridge-instances"
    return (
        Path.home()
        / ".config"
        / "palworld-pal-editor"
        / "bridge-instances"
    )


class ProcessProbe(Protocol):
    def matches(
        self,
        *,
        pid: int,
        process_start_time: str,
        executable_path: str,
    ) -> bool: ...


class WindowsProcessProbe:
    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

    def matches(
        self,
        *,
        pid: int,
        process_start_time: str,
        executable_path: str,
    ) -> bool:
        if sys.platform != "win32":
            return False

        kernel32 = ctypes.windll.kernel32
        kernel32.OpenProcess.argtypes = [
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
        ]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.GetProcessTimes.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
        ]
        kernel32.GetProcessTimes.restype = wintypes.BOOL
        kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(
            self._PROCESS_QUERY_LIMITED_INFORMATION,
            False,
            pid,
        )
        if not handle:
            return False
        try:
            created = wintypes.FILETIME()
            exited = wintypes.FILETIME()
            kernel = wintypes.FILETIME()
            user = wintypes.FILETIME()
            if not kernel32.GetProcessTimes(
                handle,
                ctypes.byref(created),
                ctypes.byref(exited),
                ctypes.byref(kernel),
                ctypes.byref(user),
            ):
                return False
            actual_start_time = str(
                (created.dwHighDateTime << 32) | created.dwLowDateTime
            )
            if actual_start_time != process_start_time:
                return False

            capacity = wintypes.DWORD(32768)
            path_buffer = ctypes.create_unicode_buffer(capacity.value)
            if not kernel32.QueryFullProcessImageNameW(
                handle,
                0,
                path_buffer,
                ctypes.byref(capacity),
            ):
                return False
            return os.path.normcase(os.path.abspath(path_buffer.value)) == (
                os.path.normcase(os.path.abspath(executable_path))
            )
        finally:
            kernel32.CloseHandle(handle)


class LocalBridgeDiscovery:
    """Resolve one live, same-user Palworld client Bridge registration."""

    def __init__(
        self,
        instance_directory: Path | None = None,
        protector: CredentialProtector | None = None,
        process_probe: ProcessProbe | None = None,
    ) -> None:
        self._instance_directory = (
            instance_directory or _default_instance_directory()
        )
        self._protector = protector or WindowsDpapiCredentialProtector(
            entropy=_LOCAL_BRIDGE_ENTROPY,
            description="Palworld Pal Editor local bridge credential",
        )
        self._process_probe = process_probe or WindowsProcessProbe()

    def discover_spec(self) -> RemoteConnectionSpec:
        matches: list[RemoteConnectionSpec] = []
        if self._instance_directory.is_dir():
            registrations = sorted(
                self._instance_directory.glob("client-*.json"),
                key=lambda path: path.stat().st_mtime_ns,
                reverse=True,
            )
        else:
            registrations = []

        for path in registrations:
            spec = self._read_live_registration(path)
            if spec is not None:
                matches.append(spec)

        if not matches:
            raise DomainError(
                code="LOCAL_BRIDGE_NOT_FOUND",
                message=(
                    "No running Palworld single-player or host Bridge "
                    "was found for the current Windows account."
                ),
                retryable=True,
                http_status=404,
            )
        if len(matches) > 1:
            raise DomainError(
                code="LOCAL_BRIDGE_AMBIGUOUS",
                message=(
                    "More than one running Palworld client Bridge was found. "
                    "Close the extra game instance and try again."
                ),
                retryable=True,
                http_status=409,
            )
        return matches[0]

    def _read_live_registration(
        self,
        path: Path,
    ) -> RemoteConnectionSpec | None:
        try:
            if path.stat().st_size > _MAX_REGISTRATION_BYTES:
                return None
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if (
            not isinstance(data, dict)
            or data.get("version") != 1
            or data.get("protocolVersion") != REMOTE_PROTOCOL_VERSION
        ):
            return None

        pid = data.get("pid")
        process_start_time = data.get("processStartTime")
        executable_path = data.get("executablePath")
        protected_secret = data.get("protectedSecret")
        if (
            isinstance(pid, bool)
            or not isinstance(pid, int)
            or pid <= 0
            or not isinstance(process_start_time, str)
            or not process_start_time.isdecimal()
            or not isinstance(executable_path, str)
            or not executable_path
            or Path(executable_path).name.casefold()
            not in _SUPPORTED_CLIENT_EXECUTABLES
            or not isinstance(protected_secret, str)
            or not protected_secret
        ):
            return None
        if not self._process_probe.matches(
            pid=pid,
            process_start_time=process_start_time,
            executable_path=executable_path,
        ):
            return None
        try:
            secret = self._protector.unprotect(protected_secret)
        except Exception as error:
            raise DomainError(
                code="LOCAL_BRIDGE_CREDENTIAL_INVALID",
                message=(
                    "The local Bridge credential cannot be read by the "
                    "current Windows account."
                ),
                retryable=False,
                http_status=409,
            ) from error

        return RemoteConnectionSpec.create(
            address=data.get("address"),
            username=data.get("username"),
            admin_password=secret,
            allow_insecure_local=True,
        )


LOCAL_BRIDGE_DISCOVERY = LocalBridgeDiscovery()
