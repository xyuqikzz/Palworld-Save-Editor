from typing import Any, Sequence

from palworld_save_tools.archive import *


def _dynamic_item_id_reader(reader: FArchiveReader) -> dict[str, UUID]:
    return {
        "created_world_id": reader.guid(),
        "local_id_in_created_world": reader.guid(),
    }


def _dynamic_item_id_writer(
    writer: FArchiveWriter, dynamic_item_id: dict[str, Any]
) -> None:
    writer.guid(dynamic_item_id["created_world_id"])
    writer.guid(dynamic_item_id["local_id_in_created_world"])


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
    reader = parent_reader.internal_copy(bytes(c_bytes), debug=False)
    data = {}
    data["permission"] = {
        "type_a": reader.tarray(lambda r: r.byte()),
        "type_b": reader.tarray(lambda r: r.byte()),
        "item_static_ids": reader.tarray(lambda r: r.fstring()),
    }
    # Palworld 1.0 appends the category permission array and the container's
    # used dynamic-item identifiers.  Older saves legitimately end after the
    # first three permission arrays, so keep the extension versioned by
    # presence rather than manufacturing bytes when it is absent.
    if not reader.eof():
        data["permission"]["item_categories"] = reader.tarray(
            lambda r: r.fstring()
        )
    if not reader.eof():
        data["used_dynamic_item_ids"] = reader.tarray(_dynamic_item_id_reader)
    if not reader.eof():
        data["trailing_unparsed_data"] = [b for b in reader.read_to_end()]
    return data


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
    writer.tarray(lambda w, d: w.byte(d), p["permission"]["type_a"])
    writer.tarray(lambda w, d: w.byte(d), p["permission"]["type_b"])
    writer.tarray(
        lambda w, d: (w.fstring(d), None)[1], p["permission"]["item_static_ids"]
    )
    if "item_categories" in p["permission"]:
        writer.tarray(
            lambda w, d: (w.fstring(d), None)[1],
            p["permission"]["item_categories"],
        )
    if "used_dynamic_item_ids" in p:
        if "item_categories" not in p["permission"]:
            raise ValueError(
                "used_dynamic_item_ids requires the item_categories extension"
            )
        writer.tarray(_dynamic_item_id_writer, p["used_dynamic_item_ids"])
    if "trailing_unparsed_data" in p:
        writer.write(bytes(p["trailing_unparsed_data"]))
    encoded_bytes = writer.bytes()
    return encoded_bytes
