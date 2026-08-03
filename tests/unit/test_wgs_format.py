from __future__ import annotations

import struct
import uuid

import pytest

from palworld_pal_editor.storage.wgs_format import (
    encode_container,
    encode_index,
    encode_palworld_payload,
    normalize_palworld_payload,
    parse_container,
    parse_index,
    select_payload_folder,
    WgsFormatError,
)


def _text(value: str) -> bytes:
    encoded = value.encode("utf-16-le")
    return struct.pack("<I", len(encoded) // 2) + encoded


def _golden_index() -> bytes:
    container_id = uuid.UUID("00112233-4455-6677-8899-aabbccddeeff")
    return b"".join(
        (
            struct.pack("<III", 14, 1, 0xA1B2C3D4),
            _text("PocketpairInc.Palworld_ad4psfrxyesvt!AppPalworldShipping\0"),
            struct.pack("<QI", 133800000000000000, 0x01020304),
            _text("INDEX-ID\0"),
            struct.pack("<Q", 0x1122334455667788),
            _text("ABCDEF0123456789ABCDEF0123456789-Level\0"),
            _text("ABCDEF0123456789ABCDEF0123456789-Level\0"),
            _text("cloud-opaque\0"),
            struct.pack("<BI", 3, 1),
            container_id.bytes_le,
            struct.pack("<QQQ", 133800000100000000, 0x8877665544332211, 12345),
            b"opaque-trailer",
        )
    )


def test_index_golden_roundtrip_preserves_all_bytes_and_unknown_fields() -> None:
    golden = _golden_index()

    parsed = parse_index(golden)

    assert parsed.version == 14
    assert parsed.flag1 == 0xA1B2C3D4
    assert parsed.opaque_bytes == struct.pack("<Q", 0x1122334455667788)
    assert parsed.entries[0].opaque_bytes == struct.pack(
        "<Q", 0x8877665544332211
    )
    assert parsed.entries[0].container_folder == "00112233445566778899AABBCCDDEEFF"
    assert parsed.trailing_bytes == b"opaque-trailer"
    assert encode_index(parsed) == golden


def test_container_golden_roundtrip_and_unique_payload_selection() -> None:
    primary = uuid.UUID("11111111-2222-3333-4444-555555555555")
    secondary = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    name = "Data".encode("utf-16-le").ljust(128, b"\0")
    golden = (
        struct.pack("<II", 4, 1)
        + name
        + primary.bytes_le
        + secondary.bytes_le
        + b"container-opaque"
    )

    parsed = parse_container(golden)

    assert parsed.files[0].name == "Data"
    assert encode_container(parsed) == golden
    assert select_payload_folder(
        parsed.files[0], {secondary.hex.upper()}
    ) == secondary.hex.upper()


def test_format_rejects_truncation_invalid_lengths_and_payload_ambiguity() -> None:
    golden = _golden_index()
    with pytest.raises(WgsFormatError, match="Truncated") as truncated:
        parse_index(golden[:27])
    assert truncated.value.code == "TRUNCATED"

    invalid_length = bytearray(golden)
    invalid_length[12:16] = struct.pack("<I", 0xFFFFFFFF)
    with pytest.raises(WgsFormatError) as length:
        parse_index(bytes(invalid_length))
    assert length.value.code == "INVALID_LENGTH"

    identifier = uuid.UUID("11111111-2222-3333-4444-555555555555")
    raw_name = "Data".encode("utf-16-le").ljust(128, b"\0")
    container = parse_container(
        struct.pack("<II", 4, 1)
        + raw_name
        + identifier.bytes_le
        + identifier.bytes_le
    )
    with pytest.raises(WgsFormatError) as missing:
        select_payload_folder(container.files[0], set())
    assert missing.value.code == "DANGLING_REFERENCE"

    other = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    ambiguous = parse_container(
        struct.pack("<II", 4, 1)
        + raw_name
        + identifier.bytes_le
        + other.bytes_le
    )
    with pytest.raises(WgsFormatError) as duplicate:
        select_payload_folder(
            ambiguous.files[0], {identifier.hex.upper(), other.hex.upper()}
        )
    assert duplicate.value.code == "AMBIGUOUS_REFERENCE"


def test_cnk0_payload_normalization_is_exact_and_direct_payloads_are_unchanged() -> None:
    standard = struct.pack("<II", 100, 20) + b"PlZ2" + b"compressed"
    direct = normalize_palworld_payload(standard)
    assert direct.data == standard
    assert direct.encoding == "direct"
    assert direct.header_prefix == b""
    assert (
        encode_palworld_payload(direct.data, direct.encoding, direct.header_prefix)
        == standard
    )

    opaque_prefix = b"\x32\x5f\x00\x00"
    raw_payload = opaque_prefix + struct.pack("<I", 1) + b"CNK0" + standard
    wrapped = normalize_palworld_payload(raw_payload)
    assert wrapped.data == standard
    assert wrapped.encoding == "cnk0"
    assert wrapped.header_prefix == opaque_prefix
    assert (
        encode_palworld_payload(
            wrapped.data,
            wrapped.encoding,
            wrapped.header_prefix,
        )
        == raw_payload
    )


@pytest.mark.parametrize(
    ("encoding", "header_prefix", "expected_code"),
    (
        ("unknown", b"", "UNSUPPORTED_ENCODING"),
        ("direct", b"\0" * 4, "INVALID_LENGTH"),
        ("cnk0", b"", "INVALID_LENGTH"),
        ("cnk0", b"\0" * 3, "INVALID_LENGTH"),
        ("cnk0", b"\0" * 5, "INVALID_LENGTH"),
    ),
)
def test_payload_encoding_rejects_unknown_or_inconsistent_metadata(
    encoding: str,
    header_prefix: bytes,
    expected_code: str,
) -> None:
    with pytest.raises(WgsFormatError) as raised:
        encode_palworld_payload(b"payload", encoding, header_prefix)
    assert raised.value.code == expected_code


@pytest.mark.parametrize(
    ("payload", "expected_code"),
    (
        (b"\0" * 8 + b"CNK0" + b"short", "TRUNCATED"),
        (
            b"\0" * 4
            + struct.pack("<I", 2)
            + b"CNK0"
            + struct.pack("<II", 100, 20)
            + b"PlZ2compressed",
            "UNSUPPORTED_CNK",
        ),
        (
            b"\0" * 4
            + struct.pack("<I", 1)
            + b"CNK1"
            + struct.pack("<II", 100, 20)
            + b"PlZ2compressed",
            "UNSUPPORTED_CNK",
        ),
        (
            b"\0" * 4
            + struct.pack("<I", 1)
            + b"CNK0"
            + struct.pack("<II", 100, 20)
            + b"BAD2compressed",
            "INVALID_CNK",
        ),
    ),
)
def test_cnk_payload_normalization_rejects_unproven_or_invalid_variants(
    payload: bytes, expected_code: str
) -> None:
    with pytest.raises(WgsFormatError) as raised:
        normalize_palworld_payload(payload)
    assert raised.value.code == expected_code
