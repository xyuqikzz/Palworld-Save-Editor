import struct

import pytest

from palworld_save_tools.archive import FArchiveReader, FArchiveWriter


@pytest.mark.parametrize("payload,reason", [
    (struct.pack('<i', 3) + b'a\xfb\0', 'non-ASCII'),
    (struct.pack('<i', 3) + b'abx', 'terminator'),
    (struct.pack('<i', -2) + b'a\0xx', 'terminator'),
    (struct.pack('<i', 100) + b'a\0', 'remaining'),
    (struct.pack('<i', -(2**31)), 'remaining'),
    (b'\x01\x00', 'length prefix'),
])
def test_invalid_fstring_reports_offset_path_and_reason(payload, reason):
    reader = FArchiveReader(b'prefix' + payload)
    reader.read(6)
    with pytest.raises(ValueError) as error:
        reader.properties_until_end('.worldSaveData')
    message = str(error.value)
    assert 'offset=6' in message
    assert '.worldSaveData' in message
    assert reason in message


def test_invalid_property_string_reports_field_and_declared_length():
    writer = FArchiveWriter()
    writer.fstring('NickName')
    writer.fstring('StrProperty')
    writer.u64(7)
    writer.optional_guid(None)
    writer.write(struct.pack('<i', 3) + b'a\xfb\0')
    with pytest.raises(ValueError) as error:
        FArchiveReader(writer.bytes()).properties_until_end('.Player')
    assert '.Player.NickName' in str(error.value)
    assert 'declared_length=3' in str(error.value)
    assert 'byte_offset=' in str(error.value)
    assert isinstance(error.value.__cause__, UnicodeDecodeError)


@pytest.mark.parametrize('value', ['', 'ASCII', '帕鲁', '😀', '\ud800'])
def test_supported_fstrings_roundtrip_without_byte_changes(value):
    writer = FArchiveWriter()
    writer.fstring(value)
    original = writer.bytes()
    decoded = FArchiveReader(original).fstring()
    assert decoded == value
    rewritten = FArchiveWriter()
    rewritten.fstring(decoded)
    assert rewritten.bytes() == original
