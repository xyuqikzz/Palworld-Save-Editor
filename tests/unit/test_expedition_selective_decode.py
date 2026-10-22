from copy import deepcopy
from types import SimpleNamespace
import io
import logging
from unittest.mock import Mock

import pytest

from palworld_save_tools.archive import FArchiveWriter
from palworld_save_tools.archive import FArchiveReader
from palworld_pal_editor.core.pal_objects import PalObjects
from palworld_pal_editor.core.save_manager import SaveManager
from palworld_pal_editor.utils import LOGGER
from tests.unit.test_expedition_completion import current_expedition, EXPEDITION_ID
from palworld_save_tools.rawdata import map_concrete_model
from palworld_pal_editor.application.character_editor import CharacterEditor
from palworld_pal_editor.domain.commands import UnlockPalExpedition, UnlockAllExpeditionPals
from palworld_pal_editor.domain.errors import DomainError
from tests.unit.test_experimental_levels import editor_for
from tests.unit.test_character_editor import make_pal


def struct_property(value):
    return dict(type="StructProperty", struct_type="StructProperty", struct_id=PalObjects.EMPTY_UUID, id=None, value=value)


def map_property(*, broken_expedition=False, broken_outer=False):
    payload = map_concrete_model.encode_bytes(current_expedition('bbbbbbbb-cccc-dddd-eeee-ffffffffffff'))
    expedition = {
        'MapObjectId': PalObjects.NameProperty('Expedition'),
        'Model': struct_property( {
            'RawData': PalObjects.ArrayProperty('ByteProperty', {'values': [0] * 264}),
        }),
        'ConcreteModel': struct_property( {
            'RawData': PalObjects.ArrayProperty('ByteProperty', {'values': list(b'bad' if broken_expedition else payload)}),
        }),
    }
    unrelated = deepcopy(expedition)
    unrelated['MapObjectId'] = PalObjects.NameProperty('NewUnrelatedModObject')
    unrelated['ConcreteModel']['value']['RawData']['value']['values'] = list(b'opaque concrete')
    unrelated['Model']['value']['RawData']['value']['values'] = list(b'unsupported raw data')
    prop = PalObjects.ArrayProperty('StructProperty', {
        'prop_name': 'MapObjectSaveData', 'prop_type': 'StructProperty',
        'type_name': 'PalMapObjectSaveData', 'id': PalObjects.EMPTY_UUID,
        'values': [unrelated, expedition],
    })
    writer = FArchiveWriter()
    size = writer.property_inner('ArrayProperty', deepcopy(prop))
    raw = writer.bytes()[-size:]
    if broken_outer:
        raw = raw[:-1]
    return dict(array_type='StructProperty', id=None, value=raw, skip_type='ArrayProperty')


def manager_for(prop):
    manager = SaveManager.create_isolated()
    manager.gvas_file = SimpleNamespace(properties={'worldSaveData': {'value': {'MapObjectSaveData': prop}}})
    return manager


def test_unrelated_raw_data_is_preserved_and_does_not_block_expedition():
    prop = map_property()
    original = deepcopy(prop)
    manager = manager_for(prop)
    assert manager.get_expedition_instance_ids() == frozenset({EXPEDITION_ID})
    assert prop == original
    assert manager.complete_active_expeditions() == [EXPEDITION_ID]
    changed = prop['value']
    assert b'unsupported raw data' in changed
    manager.reset_expedition_index()
    assert manager.expedition_records()[0]['start_time'] == 1


@pytest.mark.parametrize('bulk', [False, True])
def test_incomplete_expedition_index_refuses_unlock_without_partial_changes(bulk):
    pal = make_pal()
    pal._pal_param['MapObjectConcreteInstanceIdAssignedToExpedition'] = PalObjects.Guid(EXPEDITION_ID)
    session, editor = editor_for(pal, 'pal')
    session.manager.expedition_has_member = lambda *_: None
    session.manager._dangling_pals = {str(pal.InstanceId): pal}
    original = deepcopy(pal._pal_param)
    base = dict(session_id=session.session_id, expected_revision=0)
    command = UnlockAllExpeditionPals(**base) if bulk else UnlockPalExpedition(**base, pal_id=str(pal.InstanceId))
    with pytest.raises(DomainError) as error:
        editor.execute(command)
    assert error.value.code == 'EXPEDITION_INDEX_UNAVAILABLE'
    assert pal._pal_param == original
    assert session.revision == 0


@pytest.mark.parametrize('kind', ['broken_expedition', 'broken_outer'])
def test_unknown_boundaries_or_broken_expedition_disable_all_writes(kind):
    prop = map_property(**{kind: True})
    original = deepcopy(prop)
    manager = manager_for(prop)
    assert manager.get_expedition_instance_ids() is None
    assert manager.expedition_records() is None
    with pytest.raises(ValueError, match='unavailable'):
        manager.complete_active_expeditions()
    assert prop == original


def test_corrupt_current_expedition_is_not_reinterpreted_as_legacy():
    model = current_expedition('bbbbbbbb-cccc-dddd-eeee-ffffffffffff')
    encoded = bytearray(map_concrete_model.encode_bytes(model))
    # The current-layout zero prefix is followed by FString and member count.
    reader = FArchiveReader(encoded)
    reader.read(36)
    reader.fstring()
    count_offset = reader.data.tell()
    encoded[count_offset:count_offset + 4] = b'\xff' * 4
    with pytest.raises(ValueError, match='member count'):
        map_concrete_model.decode_bytes(FArchiveReader(b''), encoded, 'Expedition')


def test_known_legacy_expedition_is_preserved_but_cannot_authorize_unlock():
    model = current_expedition('bbbbbbbb-cccc-dddd-eeee-ffffffffffff')
    model['expedition_layout'] = 'legacy'
    encoded = map_concrete_model.encode_bytes(deepcopy(model))
    decoded = map_concrete_model.decode_bytes(FArchiveReader(b''), encoded, 'Expedition')
    assert decoded['expedition_layout'] == 'legacy'
    assert map_concrete_model.encode_bytes(deepcopy(decoded)) == encoded
    manager = manager_for(map_property())
    manager._expedition_index_attempted = True
    manager._expedition_records = {EXPEDITION_ID: {'layout': 'legacy', 'member_ids': frozenset()}}
    assert manager.expedition_has_member(EXPEDITION_ID, 'pal') is None


def test_index_failure_log_contains_traceback_type_path_and_local_offset():
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    LOGGER.logger.addHandler(handler)
    try:
        manager = manager_for(map_property(broken_expedition=True))
        assert manager.get_expedition_instance_ids() is None
    finally:
        LOGGER.logger.removeHandler(handler)
    diagnostic = output.getvalue()
    assert 'Traceback' in diagnostic
    assert 'map_object_type=Expedition' in diagnostic
    assert '.MapObjectSaveData[1].ConcreteModel.RawData' in diagnostic
    assert 'offset=0' in diagnostic
    assert 'offset_scope=raw-data-local' in diagnostic


@pytest.mark.parametrize('failure', ['raises', 'unmatched'])
def test_unverified_raw_field_never_authorizes_timer_write(failure):
    prop = map_property()
    original = deepcopy(prop)
    manager = manager_for(prop)
    manager._encode_map_object_raw_data_field = (
        Mock(side_effect=ValueError('unsupported field layout'))
        if failure == 'raises' else Mock(return_value=b'unmatched field')
    )
    records = manager.expedition_records()
    assert records[0]['can_complete'] is False
    assert manager.complete_active_expeditions() == []
    assert prop == original
