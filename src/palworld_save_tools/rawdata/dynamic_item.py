from typing import Any, Sequence

from palworld_save_tools.archive import *


def decode(
    reader: FArchiveReader, type_name: str, size: int, path: str
) -> dict[str, Any]:
    if type_name != "ArrayProperty":
        raise Exception(f"Expected ArrayProperty, got {type_name}")
    value = reader.property(type_name, size, path, nested_caller_path=path)
    data_bytes = value["value"]["values"]
    value["value"] = decode_bytes(reader, data_bytes)
    return value


def decode_bytes(
    parent_reader: FArchiveReader, c_bytes: Sequence[int]
) -> Optional[dict[str, Any]]:
    if len(c_bytes) == 0:
        return None
    buf = bytes(c_bytes)
    reader = parent_reader.internal_copy(buf, debug=False)
    data: dict[str, Any] = {}
    data["id"] = {
        "created_world_id": reader.guid(),
        "local_id_in_created_world": reader.guid(),
        "static_id": reader.fstring(),
    }
    payload_start = reader.data.tell()
    decoders = (
        _read_current_egg,
        _read_current_weapon,
        _read_current_armor,
        _read_legacy_egg,
        _read_legacy_weapon,
        _read_legacy_armor,
    )
    for decoder in decoders:
        reader.data.seek(payload_start)
        decoded = _try_payload(reader, decoder)
        if decoded is not None:
            data.update(decoded)
            return data
    reader.data.seek(payload_start)
    data["type"] = "unknown"
    data["trailer"] = [int(b) for b in reader.read_to_end()]
    return data


def _try_payload(reader: FArchiveReader, decoder) -> Optional[dict[str, Any]]:
    try:
        decoded = decoder(reader)
        if not reader.eof():
            raise ValueError("dynamic item payload has trailing bytes")
        return decoded
    except Exception:
        return None


def _read_exact(reader: FArchiveReader, size: int) -> list[int]:
    value = reader.read(size)
    if len(value) != size:
        raise ValueError("dynamic item payload ended early")
    return [int(byte) for byte in value]


def _read_current_egg(reader: FArchiveReader) -> dict[str, Any]:
    return {
        "type": "egg",
        "leading_bytes": _read_exact(reader, 4),
        "character_id": reader.fstring(),
        "object": reader.properties_until_end(),
        "trailing_bytes": _read_exact(reader, 28),
    }


def _read_current_weapon(reader: FArchiveReader) -> dict[str, Any]:
    leading_bytes = _read_exact(reader, 4)
    durability = reader.float()
    remaining_bullets = reader.i32()
    passive_skill_list = reader.tarray(lambda value_reader: value_reader.fstring())
    remaining = reader.size - reader.data.tell()
    if remaining < 4:
        raise ValueError("current weapon payload has no trailer")
    unknown_str = reader.fstring() if remaining > 4 else None
    result = {
        "type": "weapon",
        "leading_bytes": leading_bytes,
        "durability": durability,
        "remaining_bullets": remaining_bullets,
        "passive_skill_list": passive_skill_list,
        "trailing_bytes": _read_exact(reader, 4),
    }
    if unknown_str is not None:
        result["unknown_str"] = unknown_str
    return result


def _read_current_armor(reader: FArchiveReader) -> dict[str, Any]:
    return {
        "type": "armor",
        "leading_bytes": _read_exact(reader, 4),
        "durability": reader.float(),
        "trailing_bytes": _read_exact(reader, 4),
    }


def _read_legacy_egg(reader: FArchiveReader) -> dict[str, Any]:
    return {
        "type": "egg",
        "character_id": reader.fstring(),
        "object": reader.properties_until_end(),
        "unknown_bytes": _read_exact(reader, 4),
        "unknown_id": reader.guid(),
    }


def _read_legacy_weapon(reader: FArchiveReader) -> dict[str, Any]:
    return {
        "type": "weapon",
        "durability": reader.float(),
        "remaining_bullets": reader.i32(),
        "passive_skill_list": reader.tarray(
            lambda value_reader: value_reader.fstring()
        ),
    }


def _read_legacy_armor(reader: FArchiveReader) -> dict[str, Any]:
    return {"type": "armor", "durability": reader.float()}


def encode(
    writer: FArchiveWriter, property_type: str, properties: dict[str, Any]
) -> int:
    if property_type != "ArrayProperty":
        raise Exception(f"Expected ArrayProperty, got {property_type}")
    del properties["custom_type"]
    encoded_bytes = encode_bytes(properties["value"])
    properties["value"] = {"values": [b for b in encoded_bytes]}
    return writer.property_inner(property_type, properties)


def encode_bytes(p: dict[str, Any]) -> bytes:
    if p is None:
        return bytes()
    writer = FArchiveWriter()
    writer.guid(p["id"]["created_world_id"])
    writer.guid(p["id"]["local_id_in_created_world"])
    writer.fstring(p["id"]["static_id"])
    if p["type"] == "unknown":
        writer.write(bytes(p["trailer"]))
    elif p["type"] == "egg":
        if "leading_bytes" in p:
            _write_fixed(writer, p["leading_bytes"], 4, "egg leading bytes")
            writer.fstring(p["character_id"])
            writer.properties(p["object"])
            _write_fixed(writer, p["trailing_bytes"], 28, "egg trailing bytes")
        else:
            writer.fstring(p["character_id"])
            writer.properties(p["object"])
            _write_fixed(writer, p["unknown_bytes"], 4, "legacy egg bytes")
            writer.guid(p["unknown_id"])
    elif p["type"] == "armor":
        if "leading_bytes" in p:
            _write_fixed(writer, p["leading_bytes"], 4, "armor leading bytes")
        writer.float(p["durability"])
        if "leading_bytes" in p:
            _write_fixed(writer, p["trailing_bytes"], 4, "armor trailing bytes")
    elif p["type"] == "weapon":
        if "leading_bytes" in p:
            _write_fixed(writer, p["leading_bytes"], 4, "weapon leading bytes")
        writer.float(p["durability"])
        writer.i32(p["remaining_bullets"])
        writer.tarray(lambda w, d: (w.fstring(d), None)[1], p["passive_skill_list"])
        if "leading_bytes" in p:
            if "unknown_str" in p:
                writer.fstring(p["unknown_str"])
            _write_fixed(writer, p["trailing_bytes"], 4, "weapon trailing bytes")
    else:
        raise ValueError(f"Unsupported dynamic item type: {p['type']}")
    encoded_bytes = writer.bytes()
    return encoded_bytes


def _write_fixed(
    writer: FArchiveWriter,
    value: Sequence[int],
    expected_size: int,
    field: str,
) -> None:
    encoded = bytes(value)
    if len(encoded) != expected_size:
        raise ValueError(f"{field} must contain {expected_size} bytes")
    writer.write(encoded)
