from __future__ import annotations

import errno
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from palworld_pal_editor.domain.errors import DomainError


class BackupVerificationError(Exception):
    """A copied file or manifest did not match the verified source snapshot."""


_DISK_SPACE_ERRNOS = {
    value
    for value in (
        getattr(errno, "ENOSPC", None),
        getattr(errno, "EDQUOT", None),
        getattr(errno, "EFBIG", None),
    )
    if value is not None
}
_PERMISSION_ERRNOS = {
    value
    for value in (
        getattr(errno, "EACCES", None),
        getattr(errno, "EPERM", None),
        getattr(errno, "EROFS", None),
    )
    if value is not None
}
_FILE_BUSY_ERRNOS = {
    value
    for value in (
        getattr(errno, "EBUSY", None),
        getattr(errno, "ETXTBSY", None),
    )
    if value is not None
}
_SOURCE_MISSING_ERRNOS = {
    value
    for value in (
        getattr(errno, "ENOENT", None),
        getattr(errno, "ENOTDIR", None),
    )
    if value is not None
}

_WINDOWS_DISK_SPACE_CODES = {39, 112}
_WINDOWS_PERMISSION_CODES = {5, 19, 65, 1314}
_WINDOWS_FILE_BUSY_CODES = {32, 33}
_WINDOWS_SOURCE_MISSING_CODES = {2, 3}


def _safe_relative_file(value: str | PurePosixPath | None) -> str | None:
    if value is None:
        return None
    raw_value = str(value)
    path = PurePosixPath(raw_value.replace("\\", "/"))
    windows_path = PureWindowsPath(raw_value)
    if (
        path.is_absolute()
        or windows_path.is_absolute()
        or windows_path.drive
        or ".." in path.parts
    ):
        return None
    return path.as_posix()


def os_error_diagnostic(
    error: BaseException,
    *,
    default_category: str = "io_error",
) -> tuple[int | None, str]:
    if isinstance(error, BackupVerificationError):
        return None, "verification"
    if not isinstance(error, OSError):
        return None, default_category

    windows_code = getattr(error, "winerror", None)
    error_code = windows_code if isinstance(windows_code, int) else error.errno
    if windows_code in _WINDOWS_DISK_SPACE_CODES or error.errno in _DISK_SPACE_ERRNOS:
        return error_code, "disk_space"
    if windows_code in _WINDOWS_PERMISSION_CODES or error.errno in _PERMISSION_ERRNOS:
        return error_code, "permission"
    if windows_code in _WINDOWS_FILE_BUSY_CODES or error.errno in _FILE_BUSY_ERRNOS:
        return error_code, "file_busy"
    if (
        windows_code in _WINDOWS_SOURCE_MISSING_CODES
        or error.errno in _SOURCE_MISSING_ERRNOS
    ):
        return error_code, "source_missing"
    return error_code, default_category


def backup_failure(
    *,
    code: str,
    message: str,
    backup_path: Path,
    phase: str,
    failed_file: str | PurePosixPath | None,
    error: BaseException,
) -> DomainError:
    error_code, category = os_error_diagnostic(error)
    retryable = True
    return DomainError(
        code=code,
        message=message,
        details={
            "backup_path": str(backup_path),
            "phase": phase,
            "failed_file": _safe_relative_file(failed_file),
            "os_error_code": error_code,
            "os_error_category": category,
            "retryable": retryable,
        },
        retryable=retryable,
        http_status=500,
    )


def source_changed(
    *,
    code: str,
    message: str,
    backup_path: Path | None,
    phase: str,
    failed_file: str | PurePosixPath | None,
    error: BaseException | None = None,
) -> DomainError:
    error_code, _category = (
        os_error_diagnostic(error)
        if error is not None
        else (None, "source_changed")
    )
    details: dict[str, Any] = {
        "phase": phase,
        "failed_file": _safe_relative_file(failed_file),
        "os_error_code": error_code,
        "os_error_category": "source_changed",
        "retryable": True,
    }
    if backup_path is not None:
        details["backup_path"] = str(backup_path)
    return DomainError(
        code=code,
        message=message,
        details=details,
        retryable=True,
        http_status=409,
    )
