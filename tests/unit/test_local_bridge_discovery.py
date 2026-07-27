from __future__ import annotations

import json

import pytest

from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.remote.local import LocalBridgeDiscovery


class _Protector:
    available = True

    def protect(self, secret: str) -> str:
        return f"protected:{secret}"

    def unprotect(self, payload: str) -> str:
        assert payload == "protected:test-secret"
        return "test-secret"


class _ProcessProbe:
    def __init__(self, matches: bool = True) -> None:
        self._matches = matches

    def matches(
        self,
        *,
        pid: int,
        process_start_time: str,
        executable_path: str,
    ) -> bool:
        assert pid > 0
        assert process_start_time.isdecimal()
        assert executable_path.endswith("Palworld-Win64-Shipping.exe")
        return self._matches


def _write_registration(path, *, pid: int = 1234) -> None:
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "protocolVersion": 1,
                "bridgeVersion": "0.3.0",
                "address": "http://127.0.0.1:49123",
                "username": "local",
                "protectedSecret": "protected:test-secret",
                "pid": pid,
                "processStartTime": str(10_000 + pid),
                "executablePath": (
                    "D:\\Steam\\Palworld\\Pal\\Binaries\\Win64\\"
                    "Palworld-Win64-Shipping.exe"
                ),
                "instanceKind": "local_game",
            }
        ),
        encoding="utf-8",
    )


def test_local_bridge_discovery_returns_verified_loopback_spec(tmp_path) -> None:
    _write_registration(tmp_path / "client-1234.json")
    discovery = LocalBridgeDiscovery(
        tmp_path,
        _Protector(),
        _ProcessProbe(),
    )

    spec = discovery.discover_spec()

    assert spec.base_url == "http://127.0.0.1:49123"
    assert spec.username == "local"
    assert spec.admin_password == "test-secret"
    assert spec.allow_insecure_local is True
    assert "test-secret" not in repr(spec)


def test_local_bridge_discovery_ignores_stale_process_registration(
    tmp_path,
) -> None:
    _write_registration(tmp_path / "client-1234.json")
    discovery = LocalBridgeDiscovery(
        tmp_path,
        _Protector(),
        _ProcessProbe(matches=False),
    )

    with pytest.raises(DomainError) as error:
        discovery.discover_spec()

    assert error.value.code == "LOCAL_BRIDGE_NOT_FOUND"


def test_local_bridge_discovery_rejects_ambiguous_game_instances(
    tmp_path,
) -> None:
    _write_registration(tmp_path / "client-1234.json", pid=1234)
    _write_registration(tmp_path / "client-5678.json", pid=5678)
    discovery = LocalBridgeDiscovery(
        tmp_path,
        _Protector(),
        _ProcessProbe(),
    )

    with pytest.raises(DomainError) as error:
        discovery.discover_spec()

    assert error.value.code == "LOCAL_BRIDGE_AMBIGUOUS"
