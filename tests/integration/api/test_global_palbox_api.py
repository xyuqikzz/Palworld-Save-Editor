from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from palworld_pal_editor.api.global_palbox import global_palbox_blueprint


def _client():
    app = Flask(__name__)
    app.config.update(
        JWT_SECRET_KEY="test-secret-key-that-is-at-least-32-bytes",
        TESTING=True,
    )
    JWTManager(app)
    app.register_blueprint(global_palbox_blueprint, url_prefix="/api/global-palbox")
    with app.app_context():
        token = create_access_token(identity="test-user")
    return app.test_client(), {"Authorization": f"Bearer {token}"}


def _document() -> Mock:
    document = Mock()
    document.summary.return_value = {
        "session_id": "global-session",
        "revision": 2,
        "occupied": 1,
        "free": 959,
    }
    document.pals.return_value = [{"InstanceId": "pal-1", "CharacterID": "GrassBoss"}]
    return document


def test_global_palbox_api_requires_authentication() -> None:
    client, _headers = _client()

    response = client.post("/api/global-palbox/open", json={"path": "save"})

    assert response.status_code == 401


def test_global_palbox_open_returns_isolated_session_payload() -> None:
    client, headers = _client()
    document = _document()

    with patch(
        "palworld_pal_editor.api.global_palbox.GLOBAL_PALBOX_RUNTIME.open",
        return_value=document,
    ) as open_document:
        response = client.post(
            "/api/global-palbox/open",
            headers=headers,
            json={"path": "C:/Pal/GlobalPalStorage.sav"},
        )

    assert response.status_code == 200
    assert response.get_json()["data"] == {
        "session": document.summary.return_value,
        "pals": document.pals.return_value,
    }
    open_document.assert_called_once_with("C:/Pal/GlobalPalStorage.sav")


def test_global_palbox_mutations_forward_session_and_revision() -> None:
    client, headers = _client()
    document = _document()
    document.update_pal.return_value = {
        "revision": 3,
        "pal": {"pal_id": "pal-1", "character_id": "GYM_ElecPanda"},
    }

    with patch(
        "palworld_pal_editor.api.global_palbox.GLOBAL_PALBOX_RUNTIME.get",
        return_value=document,
    ) as get_document:
        response = client.patch(
            "/api/global-palbox/pals/pal-1",
            headers=headers,
            json={
                "session_id": "global-session",
                "expected_revision": 2,
                "values": {"species_id": "GYM_ElecPanda"},
            },
        )

    assert response.status_code == 200
    get_document.assert_called_once_with("global-session")
    document.update_pal.assert_called_once_with(
        pal_id="pal-1",
        expected_revision=2,
        values={"species_id": "GYM_ElecPanda"},
    )


def test_global_palbox_save_returns_refreshed_session() -> None:
    client, headers = _client()
    document = _document()
    document.save.return_value = {"backup_path": "C:/Backups/GlobalPalStorage.sav"}

    with patch(
        "palworld_pal_editor.api.global_palbox.GLOBAL_PALBOX_RUNTIME.get",
        return_value=document,
    ):
        response = client.post(
            "/api/global-palbox/save",
            headers=headers,
            json={"session_id": "global-session", "expected_revision": 2},
        )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["session"] == document.summary.return_value
    document.save.assert_called_once_with(expected_revision=2)


def test_global_palbox_default_source_exposes_steam_and_xgp_capabilities(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = (
        tmp_path
        / "Pal"
        / "Saved"
        / "SaveGames"
        / "76561190000000000"
        / "GlobalPalStorage.sav"
    )
    source.parent.mkdir(parents=True)
    source.write_bytes(b"PlM")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    client, headers = _client()

    response = client.get("/api/global-palbox/default-source", headers=headers)

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["path"] == str(source.resolve())
    assert data["steamDirectFileSupported"] is True
    assert data["wgsWriteBackSupported"] is True


def test_global_palbox_xgp_discovery_and_open_use_the_selected_source() -> None:
    client, headers = _client()
    document = _document()
    sources = [{"source_id": "xgp-source", "platform": "xgp"}]

    with (
        patch(
            "palworld_pal_editor.api.global_palbox.GLOBAL_PALBOX_RUNTIME.discover_xgp",
            return_value=sources,
        ) as discover,
        patch(
            "palworld_pal_editor.api.global_palbox.GLOBAL_PALBOX_RUNTIME.open",
            return_value=document,
        ) as open_document,
    ):
        discovery_response = client.post(
            "/api/global-palbox/discover-xgp",
            headers=headers,
            json={"path": "C:/WGS/User"},
        )
        open_response = client.post(
            "/api/global-palbox/open",
            headers=headers,
            json={"platform": "xgp", "sourceId": "xgp-source"},
        )

    assert discovery_response.status_code == 200
    assert discovery_response.get_json()["data"]["sources"] == sources
    discover.assert_called_once_with("C:/WGS/User")
    assert open_response.status_code == 200
    open_document.assert_called_once_with(platform="xgp", source_id="xgp-source")
