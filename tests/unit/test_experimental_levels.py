from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from palworld_pal_editor.application.character_editor import CharacterEditor
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.core.pal_objects import PalObjects
from palworld_pal_editor.core.player_entity import PlayerEntity
from palworld_pal_editor.domain.commands import UpdatePalProgression, UpdatePlayerProgression
from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.utils.data_provider import DataProvider
from palworld_save_tools.archive import FArchiveReader, FArchiveWriter
from tests.unit.test_character_editor import make_pal


def make_player():
    player = object.__new__(PlayerEntity)
    player._player_key = {'PlayerUId': PalObjects.Guid('11111111-2222-3333-4444-555555555555')}
    player._player_param = {'Level': PalObjects.ByteProperty(10), 'Exp': PalObjects.Int64Property(100), 'UnusedStatusPoint': PalObjects.IntProperty(20)}
    player._player_save_data = {}
    return player


def editor_for(entity, kind):
    manager = SimpleNamespace(gvas_file=SimpleNamespace(header=None),
        player_mapping={str(entity.PlayerUId): entity} if kind == 'player' else {},
        get_player=lambda _: entity, get_pal=lambda _: entity)
    session = SaveSession.from_loaded_manager(manager, Path('synthetic-save'))
    return session, CharacterEditor(session)


@pytest.mark.parametrize('kind', ['player', 'pal'])
@pytest.mark.parametrize('level', [101, 255])
def test_experimental_level_requires_explicit_mode_and_xp_and_roundtrips(kind, level):
    entity = make_player() if kind == 'player' else make_pal()
    session, editor = editor_for(entity, kind)
    base = dict(session_id=session.session_id, expected_revision=0)
    if kind == 'player':
        command = UpdatePlayerProgression(**base, player_id=str(entity.PlayerUId), level=level, experience=123456789, experimental_level=True)
    else:
        command = UpdatePalProgression(**base, pal_id=str(entity.InstanceId), values={'level': level, 'experience': 123456789}, experimental_level=True)
    editor.execute(command)
    assert entity.Level == level
    assert entity.Exp == 123456789
    params = entity._player_param if kind == 'player' else entity._pal_param
    assert params['Level']['type'] == 'ByteProperty'
    writer = FArchiveWriter()
    writer.properties(deepcopy(params))
    reopened = FArchiveReader(writer.bytes()).properties_until_end()
    assert reopened['Level'] == params['Level']
    assert reopened['Exp'] == params['Exp']


@pytest.mark.parametrize('kind', ['player', 'pal'])
@pytest.mark.parametrize('level,mode,xp', [(101, False, 500), (101, True, None), (256, True, 500), (0, True, 500), (True, True, 500), (101, 'true', 500), (101, True, -1), (101, True, 2**63), (101, True, True)])
def test_rejected_experimental_level_does_not_change_entity(kind, level, mode, xp):
    entity = make_player() if kind == 'player' else make_pal()
    params = entity._player_param if kind == 'player' else entity._pal_param
    before = deepcopy(params)
    with pytest.raises(DomainError):
        entity.set_level(level, experimental=mode, experience=xp)
    assert params == before


def test_missing_player_xp_is_reported_without_keyerror():
    assert DataProvider.get_player_level_xp(101) is None


@pytest.mark.parametrize('kind', ['player', 'pal'])
def test_ordinary_setter_still_caps_at_100(kind):
    entity = make_player() if kind == 'player' else make_pal()
    entity.Level = 101
    assert entity.Level == 100
    xp = DataProvider.get_player_level_xp(100) if kind == 'player' else DataProvider.get_pal_level_xp(100)
    assert entity.Exp == xp


@pytest.mark.parametrize('kind', ['player', 'pal'])
@pytest.mark.parametrize('prop', [
    PalObjects.IntProperty(10),
    PalObjects.ByteProperty(10, type='UnknownEnum'),
    {'type': 'ByteProperty', 'value': {'type': 'None'}},
])
def test_unknown_level_schema_is_rejected_without_conversion(kind, prop):
    entity = make_player() if kind == 'player' else make_pal()
    params = entity._player_param if kind == 'player' else entity._pal_param
    params['Level'] = deepcopy(prop)
    before = deepcopy(params)
    with pytest.raises(DomainError) as error:
        entity.set_level(101, experimental=True, experience=123456789)
    assert error.value.code == 'COMPATIBILITY_FIELD_MISSING'
    assert params == before
