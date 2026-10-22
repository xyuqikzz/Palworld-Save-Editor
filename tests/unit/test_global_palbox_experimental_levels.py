import pytest

from palworld_pal_editor.application.global_palbox import GlobalPalboxDocument
from palworld_pal_editor.domain.errors import DomainError
from tests.unit.test_global_palbox import _sav, PAL_ID
from tests.wgs_fixture import make_user_directory


@pytest.mark.parametrize('platform', ['steam', 'xgp'])
@pytest.mark.parametrize('level', [101, 255])
def test_global_palbox_experimental_level_save_reopen(tmp_path, platform, level):
    if platform == 'steam':
        source = tmp_path / 'GlobalPalStorage.sav'
        source.write_bytes(_sav())
    else:
        source = make_user_directory(tmp_path / 'wgs', '0' * 16 + '_' + '0' * 32,
            {}, account_files={'GlobalPalStorage': _sav()})
    def open_document():
        return GlobalPalboxDocument.open(source, process_checker=lambda: False, backup_root=tmp_path / 'backups')
    document = open_document()
    for values in [{'level': level}, {'level': level, 'experimental_level': True}, {'level': 256, 'experimental_level': True, 'experience': 123}]:
        with pytest.raises(DomainError):
            document.update_pal(pal_id=PAL_ID, expected_revision=0, values=values)
        assert document.pals()[0]['Level'] == 1
    update = document.update_pal(pal_id=PAL_ID, expected_revision=0,
        values={'level': level, 'experimental_level': True, 'experience': 87654321})
    result = document.save(expected_revision=update['revision'])
    assert result['source_reloaded']
    reopened = open_document()
    pal = next(item for item in reopened.pals() if item['InstanceId'] == PAL_ID)
    assert pal['Level'] == level
    assert pal['Exp'] == 87654321
