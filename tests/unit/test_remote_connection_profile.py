from __future__ import annotations

import json

from palworld_pal_editor.remote.models import RemoteConnectionSpec
from palworld_pal_editor.remote.profile import RemoteConnectionProfileStore


class _Protector:
    available = True

    def protect(self, secret: str) -> str:
        assert secret == "do-not-store-plaintext"
        return "protected-value"

    def unprotect(self, payload: str) -> str:
        assert payload == "protected-value"
        return "do-not-store-plaintext"


def test_profile_round_trip_keeps_password_out_of_json(tmp_path) -> None:
    path = tmp_path / "remote-connection.json"
    store = RemoteConnectionProfileStore(path, _Protector())
    spec = RemoteConnectionSpec.create(
        address="http://127.0.0.1:8213",
        username="admin",
        admin_password="do-not-store-plaintext",
        allow_insecure_local=True,
    )

    profile = store.save(spec, remember_credential=True)

    assert profile.credential_saved is True
    assert "do-not-store-plaintext" not in path.read_text(encoding="utf-8")
    assert store.reconnect_spec() == spec


def test_saving_profile_without_credential_removes_previous_secret(
    tmp_path,
) -> None:
    path = tmp_path / "remote-connection.json"
    store = RemoteConnectionProfileStore(path, _Protector())
    spec = RemoteConnectionSpec.create(
        address="http://127.0.0.1:8213",
        admin_password="do-not-store-plaintext",
        allow_insecure_local=True,
    )
    store.save(spec, remember_credential=True)

    profile = store.save(spec, remember_credential=False)

    assert profile.credential_saved is False
    assert "protected_admin_password" not in json.loads(
        path.read_text(encoding="utf-8")
    )
