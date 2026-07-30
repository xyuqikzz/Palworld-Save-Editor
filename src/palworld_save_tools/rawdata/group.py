from typing import Sequence

from palworld_save_tools.archive import *


def player_info_reader(reader: FArchiveReader) -> dict[str, Any]:
    return {
        "player_uid": reader.guid(),
        "player_info": {
            "last_online_real_time": reader.i64(),
            "player_name": reader.fstring(),
        },
    }


def player_info_writer(writer: FArchiveWriter, p: dict[str, Any]) -> None:
    writer.guid(p["player_uid"])
    writer.i64(p["player_info"]["last_online_real_time"])
    writer.fstring(p["player_info"]["player_name"])


def player_info_reader_1_0(reader: FArchiveReader) -> dict[str, Any]:
    player = player_info_reader(reader)
    player["player_info"]["role"] = reader.byte()
    return player


def player_info_writer_1_0(writer: FArchiveWriter, p: dict[str, Any]) -> None:
    player_info_writer(writer, p)
    writer.byte(p["player_info"]["role"])


def role_permission_reader(reader: FArchiveReader) -> dict[str, Any]:
    return {
        "role": reader.byte(),
        "permissions": reader.tarray(lambda archive: archive.byte()),
    }


def role_permission_writer(writer: FArchiveWriter, p: dict[str, Any]) -> None:
    writer.byte(p["role"])
    writer.tarray(
        lambda archive, permission: archive.byte(permission),
        p["permissions"],
    )


def decode_guild_tail(
    parent_reader: FArchiveReader, raw_tail: bytes
) -> dict[str, Any]:
    # Palworld 1.0 added guild markers/chest roles, per-player roles, and role
    # permissions around the existing player array.
    # FVector changed from three float32 values to float64 with UE5 LWC. Try
    # the current 60-byte marker first, then the legacy-width 48-byte form.
    for marker_size in (60, 48):
        reader = parent_reader.internal_copy(raw_tail, debug=False)
        try:
            marker_count = reader.u32()
            if marker_count > 128:
                raise ValueError("implausible guild marker count")
            marker_data = reader.read(marker_count * marker_size)
            if len(marker_data) != marker_count * marker_size:
                raise ValueError("truncated guild marker data")
            allowed_roles = reader.tarray(lambda archive: archive.byte())
            if (
                not 0 < len(allowed_roles) <= 16
                or any(role not in range(1, 5) for role in allowed_roles)
            ):
                raise ValueError("not a Palworld 1.0 guild role array")
            unknown_i32 = reader.i32()
            admin_player_uid = reader.guid()
            players = reader.tarray(player_info_reader_1_0)
            if not players or any(
                not player["player_info"]["player_name"]
                or player["player_info"]["role"] not in range(1, 5)
                for player in players
            ):
                raise ValueError("not a Palworld 1.0 guild player array")
            role_permissions = reader.tarray(role_permission_reader)
            if (
                not 0 < len(role_permissions) <= 16
                or any(
                    permission["role"] not in range(1, 5)
                    or len(permission["permissions"]) > 128
                    for permission in role_permissions
                )
            ):
                raise ValueError("not a Palworld 1.0 guild permission array")
            trailing_bytes = reader.read(4)
            if len(trailing_bytes) != 4 or not reader.eof():
                raise ValueError("unexpected Palworld 1.0 guild trailing data")
            return {
                "guild_format": "1.0",
                "guild_marker_count": marker_count,
                "guild_marker_data": list(marker_data),
                "guild_chest_allowed_roles": allowed_roles,
                "unknown_i32": unknown_i32,
                "admin_player_uid": admin_player_uid,
                "players": players,
                "role_permissions": role_permissions,
                "trailing_bytes": list(trailing_bytes),
            }
        except (EOFError, IndexError, struct.error, UnicodeError, ValueError):
            pass

    reader = parent_reader.internal_copy(raw_tail, debug=False)
    try:
        result = {
            "guild_format": "legacy",
            "unknown_2": reader.byte_list(20),
            "players": reader.tarray(player_info_reader),
            "trailing_bytes": list(reader.read_to_end()),
        }
        if not result["players"]:
            raise ValueError("not a legacy guild player array")
        return result
    except (EOFError, IndexError, struct.error, UnicodeError, ValueError):
        return {
            "guild_format": "raw",
            "players": [],
            "raw_guild_tail": list(raw_tail),
        }


def decode(
    reader: FArchiveReader, type_name: str, size: int, path: str
) -> dict[str, Any]:
    if type_name != "MapProperty":
        raise Exception(f"Expected MapProperty, got {type_name}")
    value = reader.property(type_name, size, path, nested_caller_path=path)
    # Decode the raw bytes and replace the raw data
    group_map = value["value"]
    for group in group_map:
        group_type = group["value"]["GroupType"]["value"]["value"]
        group_bytes = group["value"]["RawData"]["value"]["values"]
        group["value"]["RawData"]["value"] = decode_bytes(
            reader, group_bytes, group_type
        )
    return value


def decode_bytes(
    parent_reader: FArchiveReader, group_bytes: Sequence[int], group_type: str
) -> dict[str, Any]:
    reader = parent_reader.internal_copy(bytes(group_bytes), debug=False)
    group_data = {
        "group_type": group_type,
        "group_id": reader.guid(),
        "group_name": reader.fstring(),
        "individual_character_handle_ids": reader.tarray(instance_id_reader),
    }
    if group_type in [
        "EPalGroupType::Guild",
        "EPalGroupType::IndependentGuild",
        "EPalGroupType::Organization",
    ]:
        group_data |= {"org_type": reader.byte()}
    if group_type == "EPalGroupType::Organization":
        group_data |= {"trailing_bytes": reader.byte_list(12)}

    if group_type == "EPalGroupType::Guild":
        guild: dict[str, Any] = {
            "leading_bytes": reader.byte_list(4),
            "base_ids": reader.tarray(uuid_reader),
            "unknown_1": reader.i32(),
            "base_camp_level": reader.i32(),
            "map_object_instance_ids_base_camp_points": reader.tarray(uuid_reader),
            "guild_name": reader.fstring(),
            "last_guild_name_modifier_player_uid": reader.guid(),
        }
        guild |= decode_guild_tail(reader, reader.read_to_end())
        group_data |= guild
    if group_type == "EPalGroupType::IndependentGuild":
        guild: dict[str, Any] = {
            "base_camp_level": reader.i32(),
            "map_object_instance_ids_base_camp_points": reader.tarray(uuid_reader),
            "guild_name": reader.fstring(),
        }
        group_data |= guild
        indie = {
            "player_uid": reader.guid(),
            "guild_name_2": reader.fstring(),
            "player_info": {
                "last_online_real_time": reader.i64(),
                "player_name": reader.fstring(),
            },
        }
        group_data |= indie
    if not reader.eof():
        group_data["raw_data"] = list(reader.read_to_end())
    return group_data


def encode(
    writer: FArchiveWriter, property_type: str, properties: dict[str, Any]
) -> int:
    if property_type != "MapProperty":
        raise Exception(f"Expected MapProperty, got {property_type}")
    del properties["custom_type"]
    group_map = properties["value"]
    for group in group_map:
        if "values" in group["value"]["RawData"]["value"]:
            continue
        p = group["value"]["RawData"]["value"]
        encoded_bytes = encode_bytes(p)
        group["value"]["RawData"]["value"] = {"values": [b for b in encoded_bytes]}
    return writer.property_inner(property_type, properties)


def encode_bytes(p: dict[str, Any]) -> bytes:
    writer = FArchiveWriter()
    writer.guid(p["group_id"])
    writer.fstring(p["group_name"])
    writer.tarray(instance_id_writer, p["individual_character_handle_ids"])
    if p["group_type"] in [
        "EPalGroupType::Guild",
        "EPalGroupType::IndependentGuild",
        "EPalGroupType::Organization",
    ]:
        writer.byte(p["org_type"])
    if p["group_type"] == "EPalGroupType::Organization":
        writer.write(bytes(p["trailing_bytes"]))
    if p["group_type"] == "EPalGroupType::Guild":
        writer.write(bytes(p["leading_bytes"]))
        writer.tarray(uuid_writer, p["base_ids"])
        writer.i32(p["unknown_1"])
        writer.i32(p["base_camp_level"])
        writer.tarray(uuid_writer, p["map_object_instance_ids_base_camp_points"])
        writer.fstring(p["guild_name"])
        writer.guid(p["last_guild_name_modifier_player_uid"])
        if p.get("guild_format") == "1.0":
            writer.u32(p["guild_marker_count"])
            writer.write(bytes(p["guild_marker_data"]))
            writer.tarray(
                lambda archive, role: archive.byte(role),
                p["guild_chest_allowed_roles"],
            )
            writer.i32(p["unknown_i32"])
            writer.guid(p["admin_player_uid"])
            writer.tarray(player_info_writer_1_0, p["players"])
            writer.tarray(role_permission_writer, p["role_permissions"])
            writer.write(bytes(p["trailing_bytes"]))
        elif p.get("guild_format") == "legacy":
            writer.write(bytes(p["unknown_2"]))
            writer.tarray(player_info_writer, p["players"])
            writer.write(bytes(p["trailing_bytes"]))
        else:
            writer.write(bytes(p["raw_guild_tail"]))
    if p["group_type"] == "EPalGroupType::IndependentGuild":
        writer.i32(p["base_camp_level"])
        writer.tarray(uuid_writer, p["map_object_instance_ids_base_camp_points"])
        writer.fstring(p["guild_name"])
        writer.guid(p["player_uid"])
        writer.fstring(p["guild_name_2"])
        writer.i64(p["player_info"]["last_online_real_time"])
        writer.fstring(p["player_info"]["player_name"])
    if "raw_data" in p:
        writer.write(bytes(p["raw_data"]))
    encoded_bytes = writer.bytes()
    return encoded_bytes
