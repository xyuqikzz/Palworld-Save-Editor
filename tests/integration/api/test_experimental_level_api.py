from types import SimpleNamespace

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from palworld_pal_editor.api.pal import pal_blueprint
from palworld_pal_editor.api.player import player_blueprint
from palworld_pal_editor.application.runtime import SESSION_RUNTIME
from tests.unit.test_experimental_levels import make_player, make_pal, editor_for


@pytest.mark.parametrize('kind', ['player', 'pal'])
def test_experimental_level_api_requires_mode_and_experience(kind):
    entity = make_player() if kind == 'player' else make_pal()
    session, _ = editor_for(entity, kind)
    SESSION_RUNTIME.replace_for_tests(session)
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY='test-secret-key-that-is-at-least-32-bytes')
    JWTManager(app)
    app.register_blueprint(player_blueprint, url_prefix='/api/player')
    app.register_blueprint(pal_blueprint, url_prefix='/api/pal')
    with app.app_context():
        token = create_access_token(identity='test')
    client = app.test_client()
    target_id = str(entity.PlayerUId if kind == 'player' else entity.InstanceId)
    endpoint = f'/api/{kind}/{target_id}/commands'
    def request(mode, xp):
        values = {'level': 101}
        if xp is not None:
            values['experience'] = xp
        payload = dict(session_id=session.session_id, expected_revision=0,
            command=f'update_{kind}_progression', experimental_level=mode)
        payload.update(values if kind == 'player' else {'values': values})
        return client.post(endpoint, headers={'Authorization': f'Bearer {token}'}, json=payload)
    try:
        for mode, xp in [(False, 123), (True, None), ('true', 123)]:
            assert request(mode, xp).status_code == 400
            assert entity.Level == 10
            assert session.revision == 0
        response = request(True, 123456)
        assert response.status_code == 200, response.get_json()
        assert entity.Level == 101
        assert entity.Exp == 123456
        assert session.revision == 1
    finally:
        SESSION_RUNTIME.replace_for_tests(None)
