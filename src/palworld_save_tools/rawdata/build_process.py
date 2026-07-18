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
    parent_reader: FArchiveReader, b_bytes: Sequence[int]
) -> dict[str, Any]:
    reader = parent_reader.internal_copy(bytes(b_bytes), debug=False)
    data = {
        "state": reader.byte(),
        "id": reader.guid(),
    }
    if not reader.eof():
        # Newer saves append build-process fields that this editor does not
        # mutate. Preserve them byte-for-byte so unrelated map-object data is
        # not discarded while ownership evidence is decoded.
        data["trailing_unparsed_data"] = [int(b) for b in reader.read_to_end()]
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
    writer = FArchiveWriter()
    writer.byte(p["state"])
    writer.guid(p["id"])
    if "trailing_unparsed_data" in p:
        writer.write(bytes(p["trailing_unparsed_data"]))
    encoded_bytes = writer.bytes()
    return encoded_bytes
