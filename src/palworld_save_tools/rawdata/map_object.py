from typing import Any, Sequence

from palworld_save_tools.archive import *
from palworld_save_tools.rawdata import (
    build_process,
    connector,
    map_concrete_model,
    map_concrete_model_module,
    map_model,
)


def decode(
    reader: FArchiveReader, type_name: str, size: int, path: str,
    *, expedition_only: bool = False,
) -> dict[str, Any]:
    if type_name != "ArrayProperty":
        raise Exception(f"Expected ArrayProperty, got {type_name}")
    value = reader.property(type_name, size, path, nested_caller_path=path)
    if expedition_only and not reader.eof():
        raise ValueError(f"MapObjectSaveData trailing bytes at offset={reader.data.tell()}")
    for index, map_object in enumerate(value["value"]["values"]):
        if expedition_only:
            object_id = map_object.get("MapObjectId", {}).get("value")
            if not isinstance(object_id, str) or not object_id:
                raise ValueError(f"Missing map object type: path={path}[{index}]")
            if object_id != "Expedition":
                # The outer property parser already consumed all record boundaries.
                # Unknown bounded RawData remains opaque; never scan for boundaries.
                continue
            for field, codec in (("Model", map_model), ("ConcreteModel", map_concrete_model)):
                field_path = f"{path}[{index}].{field}.RawData"
                previous = reader.context_path
                reader.context_path = field_path
                try:
                    prop = map_object[field]["value"]["RawData"]
                    if prop.get("array_type") != "ByteProperty":
                        raise ValueError("Expected bounded ByteProperty RawData")
                    payload = prop["value"]["values"]
                    args = (object_id,) if field == "ConcreteModel" else ()
                    prop["value"] = codec.decode_bytes(reader, payload, *args)
                except Exception as error:
                    error.add_note(
                        f"map_object_type={object_id}, path={field_path}, "
                        "offset_scope=raw-data-local; outer property parsed completely"
                    )
                    raise
                finally:
                    reader.context_path = previous
            continue
        # Decode Model
        map_object["Model"]["value"]["RawData"]["value"] = map_model.decode_bytes(
            reader, map_object["Model"]["value"]["RawData"]["value"]["values"]
        )
        # Decode Model.Connector
        map_object["Model"]["value"]["Connector"]["value"]["RawData"]["value"] = (
            connector.decode_bytes(
                reader,
                map_object["Model"]["value"]["Connector"]["value"]["RawData"]["value"][
                    "values"
                ],
            )
        )
        # Decode Model.BuildProcess
        map_object["Model"]["value"]["BuildProcess"]["value"]["RawData"]["value"] = (
            build_process.decode_bytes(
                reader,
                map_object["Model"]["value"]["BuildProcess"]["value"]["RawData"][
                    "value"
                ]["values"],
            )
        )
        # Decode ConcreteModel
        map_object_id = map_object["MapObjectId"]["value"]
        map_object["ConcreteModel"]["value"]["RawData"]["value"] = (
            map_concrete_model.decode_bytes(
                reader,
                map_object["ConcreteModel"]["value"]["RawData"]["value"]["values"],
                map_object_id,
            )
        )
        # Decode ConcreteModel.ModuleMap
        for module in map_object["ConcreteModel"]["value"]["ModuleMap"]["value"]:
            module_type = module["key"]
            module_bytes = module["value"]["RawData"]["value"]["values"]
            module["value"]["RawData"]["value"] = (
                map_concrete_model_module.decode_bytes(
                    reader,
                    module_bytes,
                    module_type,
                )
            )
    return value


def encode(
    writer: FArchiveWriter, property_type: str, properties: dict[str, Any]
) -> int:
    if property_type != "ArrayProperty":
        raise Exception(f"Expected ArrayProperty, got {property_type}")
    del properties["custom_type"]

    for map_object in properties["value"]["values"]:
        # Encode Model
        if "values" not in map_object["Model"]["value"]["RawData"]["value"]:
            map_object["Model"]["value"]["RawData"]["value"] = {
                "values": map_model.encode_bytes(
                    map_object["Model"]["value"]["RawData"]["value"]
                )
            }
        # Encode Model.Connector
        if (
            "values"
            not in map_object["Model"]["value"]["Connector"]["value"]["RawData"][
                "value"
            ]
        ):
            map_object["Model"]["value"]["Connector"]["value"]["RawData"]["value"] = {
                "values": connector.encode_bytes(
                    map_object["Model"]["value"]["Connector"]["value"]["RawData"][
                        "value"
                    ],
                )
            }
        # Encode Model.BuildProcess
        if (
            "values"
            not in map_object["Model"]["value"]["BuildProcess"]["value"]["RawData"][
                "value"
            ]
        ):
            map_object["Model"]["value"]["BuildProcess"]["value"]["RawData"][
                "value"
            ] = {
                "values": build_process.encode_bytes(
                    map_object["Model"]["value"]["BuildProcess"]["value"]["RawData"][
                        "value"
                    ],
                )
            }
        # Encode ConcreteModel
        if "values" not in map_object["ConcreteModel"]["value"]["RawData"]["value"]:
            map_object["ConcreteModel"]["value"]["RawData"]["value"] = {
                "values": map_concrete_model.encode_bytes(
                    map_object["ConcreteModel"]["value"]["RawData"]["value"],
                )
            }
        # Encode ConcreteModel.ModuleMap
        for module in map_object["ConcreteModel"]["value"]["ModuleMap"]["value"]:
            if "values" not in module["value"]["RawData"]["value"]:
                module_type = module["key"]
                module["value"]["RawData"]["value"] = {
                    "values": map_concrete_model_module.encode_bytes(
                        module["value"]["RawData"]["value"],
                        module_type,
                    )
                }

    return writer.property_inner(property_type, properties)
