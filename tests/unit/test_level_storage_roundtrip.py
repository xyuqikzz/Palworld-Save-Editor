from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from palworld_save_tools.gvas import GvasFile
from palworld_save_tools.palsav import compress_gvas_to_sav, decompress_sav_to_gvas
from palworld_save_tools.paltypes import PALWORLD_TYPE_HINTS
from palworld_pal_editor.application.character_editor import CharacterEditor
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.application.save_writer import SaveWriter
from palworld_pal_editor.core.pal_objects import PalObjects
from palworld_pal_editor.core.save_manager import MAIN_SKIP_PROPERTIES
from palworld_pal_editor.domain.commands import UpdatePalProgression, UpdatePlayerProgression
from palworld_pal_editor.storage.discovery import XgpSourceCatalog
from palworld_pal_editor.storage.xgp import XgpWgsAdapter
from tests.unit.test_custom_passive_storage_roundtrip import _gvas
from tests.unit.test_experimental_levels import make_player
from tests.unit.test_character_editor import make_pal
from tests.wgs_fixture import make_user_directory


class LevelManager:
    def __init__(self, kind):
        self.kind = kind
        self.player_mapping = {}
        self.item_container_data = SimpleNamespace(container_map={})

    def open(self, path, *, lazy_players=False):
        raw, self._compression_times = decompress_sav_to_gvas((Path(path) / 'Level.sav').read_bytes())
        self.gvas_file = GvasFile.read(raw, PALWORLD_TYPE_HINTS, MAIN_SKIP_PROPERTIES)
        self.entity = make_player() if self.kind == 'player' else make_pal()
        if self.kind == 'player':
            self.entity._player_param = self.gvas_file.properties
            self.player_mapping = {str(self.entity.PlayerUId): self.entity}
        else:
            self.entity._pal_param = self.gvas_file.properties
        return self.gvas_file

    def get_player(self, _id):
        return self.entity

    def get_pal(self, _id):
        return self.entity


@pytest.mark.parametrize('platform', ['steam', 'xgp'])
@pytest.mark.parametrize('kind', ['player', 'pal'])
@pytest.mark.parametrize('level', [80, 100, 101, 255])
def test_level_open_edit_save_reopen_preserves_schema_and_unrelated_fields(tmp_path, platform, kind, level):
    gvas = _gvas()
    entity = make_player() if kind == 'player' else make_pal()
    gvas.properties = deepcopy(entity._player_param if kind == 'player' else entity._pal_param)
    gvas.properties['NickName'] = PalObjects.StrProperty('帕鲁😀')
    gvas.properties['FutureOpaqueField'] = PalObjects.ArrayProperty('ByteProperty', {'values': [0, 251, 255, 10]})
    original_gvas = gvas.write(MAIN_SKIP_PROPERTIES)
    baseline = GvasFile.read(original_gvas, PALWORLD_TYPE_HINTS, MAIN_SKIP_PROPERTIES)
    assert baseline.write(MAIN_SKIP_PROPERTIES) == original_gvas
    data = compress_gvas_to_sav(original_gvas, 0x32, zlib=True)
    if platform == 'steam':
        source = tmp_path / 'steam'
        source.mkdir()
        (source / 'Level.sav').write_bytes(data)
        def open_session():
            return SaveSession.open(source, manager=LevelManager(kind))
    else:
        root = tmp_path / 'wgs'
        root.mkdir()
        make_user_directory(root, '1111111111111111_' + 'C' * 32, {'A' * 32: {'Level.sav': data}})
        catalog = XgpSourceCatalog(roots=(root,))
        source = catalog.discover()[0]
        adapter = XgpWgsAdapter(catalog=catalog, process_checker=lambda: False,
            workspace_validator=lambda _: None, workspace_root=tmp_path / 'workspaces',
            backup_root=tmp_path / 'backups', stability_delay=0)
        def open_session():
            return SaveSession.open_storage(source, adapter, manager=LevelManager(kind))
    session = open_session()
    base = dict(session_id=session.session_id, expected_revision=0, experimental_level=level > 100)
    if kind == 'player':
        command = UpdatePlayerProgression(**base, player_id=str(session.manager.entity.PlayerUId), level=level, experience=7654321)
    else:
        command = UpdatePalProgression(**base, pal_id=str(session.manager.entity.InstanceId), values={'level': level, 'experience': 7654321})
    CharacterEditor(session).execute(command)
    result = SaveWriter().save(session, None, expected_revision=1)
    assert result.source_reloaded
    assert result.backup_path
    session.close()
    reopened = open_session()
    try:
        assert reopened.manager.entity.Level == level
        assert reopened.manager.entity.Exp == 7654321
        props = reopened.manager.gvas_file.properties
        assert props['Level']['type'] == 'ByteProperty'
        assert props['Exp']['type'] == 'Int64Property'
        assert props['NickName'] == baseline.properties['NickName']
        assert props['FutureOpaqueField'] == baseline.properties['FutureOpaqueField']
    finally:
        reopened.close()
