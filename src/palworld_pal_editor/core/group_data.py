from copy import deepcopy
from typing import Optional
from palworld_save_tools.gvas import GvasFile
from palworld_save_tools.archive import UUID

from palworld_pal_editor.core.pal_objects import PalObjects
from palworld_pal_editor.utils import LOGGER


GUILD_ROLE_VALUES = frozenset({1, 2, 3, 4})


class PalGroup:
    def __init__(self, group_obj: dict, group_type: str):
        self._group_obj: dict = group_obj
        self._group_param: dict = group_obj["value"]["RawData"]["value"]
        self._group_type = group_type

        self.instance_map = {}
        self.player_map = {}

        for instance in self.individual_character_handle_ids or []:
            self.instance_map[str(instance["instance_id"])] = instance

        for player in self.players or []:
            self.player_map[str(player[0])] = player

    def snapshot(self) -> dict:
        return deepcopy(self._group_param)

    def restore(self, snapshot: dict) -> None:
        self._group_param.clear()
        self._group_param.update(deepcopy(snapshot))
        self._rebuild_index()

    def _rebuild_index(self) -> None:
        self.instance_map = {
            str(instance["instance_id"]): instance
            for instance in self.individual_character_handle_ids or []
        }
        self.player_map = {
            str(player[0]): player for player in self.players or []
        }

    def __str__(self) -> str:
        lines = []
        lines.append(f"{self.guild_name} - {self.group_id}")
        for player in self.players if self.players else []:
            lines.append(f"\n\t{str(player[0])} - {str(player[1])}")
        return "\t".join(lines)

    def add_pal(self, instanceId: UUID | str) -> bool:
        if self.has_pal(instanceId):
            LOGGER.warning("Pal ID already exists")
            return False

        new_handle = PalObjects.individual_character_handle_id(instanceId)
        self.instance_map[str(instanceId)] = new_handle
        match self.individual_character_handle_ids:
            case None:
                self._group_param["individual_character_handle_ids"] = [new_handle]
            case _:
                self.individual_character_handle_ids.append(new_handle)
        # if self.individual_character_handle_ids is None:
        #     self._group_param["individual_character_handle_ids"] = []
        # self.individual_character_handle_ids.append(new_handle)
        return True

    def del_pal(self, instanceId: UUID | str):
        if not self.has_pal(instanceId):
            LOGGER.warning(f"Pal {instanceId} not exist in group {self.guild_name}")
            return
        handle = self.instance_map.pop(str(instanceId))
        match self.individual_character_handle_ids:
            case None:
                pass
            case _:
                self.individual_character_handle_ids.remove(handle)

    def has_pal(self, instanceId: UUID | str) -> bool:
        return str(instanceId) in self.instance_map

    def has_player(self, playerUId: UUID | str) -> bool:
        return str(playerUId) in self.player_map

    @property
    def group_id(self) -> Optional[UUID]:
        return self._group_param.get("group_id")

    @property
    def individual_character_handle_ids(self) -> Optional[list[dict]]:
        return self._group_param.get("individual_character_handle_ids")

    @property
    def base_ids(self) -> Optional[list[UUID]]:
        return self._group_param.get("base_ids")

    @property
    def guild_name(self) -> Optional[str]:
        return (
            self._group_param.get("guild_name")
            or self._group_param.get("guild_name_2")
            or self._group_param.get("group_name")
        )

    def set_guild_name(self, name: str) -> None:
        current = self._group_param.get("guild_name")
        if not isinstance(current, str):
            raise ValueError("Guild name field is unavailable")
        self._group_param["guild_name"] = name

    @property
    def admin_player_uid(self) -> Optional[UUID]:
        value = self._group_param.get("admin_player_uid")
        return value if isinstance(value, UUID) else None

    @property
    def guild_members(self) -> list[tuple[UUID, str, int | None]]:
        if self.group_type == "EPalGroupType::IndependentGuild":
            return [
                (player_uid, player_name, None)
                for player_uid, player_name in (self.players or [])
            ]
        result = []
        for player_data in self._group_param.get("players") or []:
            player_info = player_data.get("player_info") or {}
            role = player_info.get("role")
            result.append(
                (
                    player_data["player_uid"],
                    player_info.get("player_name") or "",
                    (
                        role
                        if isinstance(role, int)
                        and not isinstance(role, bool)
                        and role in GUILD_ROLE_VALUES
                        else None
                    ),
                )
            )
        return result

    @property
    def guild_owner_editable(self) -> bool:
        members = self.guild_members
        return (
            self.guild_format == "1.0"
            and self.admin_player_uid is not None
            and bool(members)
            and all(role in GUILD_ROLE_VALUES for _, _, role in members)
        )

    def set_admin_player_uid(self, player_uid: UUID | str) -> None:
        if not self.guild_owner_editable:
            raise ValueError("Guild owner field is unavailable")
        target = next(
            (
                member
                for member in self._group_param.get("players") or []
                if str(member.get("player_uid")) == str(player_uid)
            ),
            None,
        )
        if target is None:
            raise ValueError("Guild member does not exist")
        for member in self._group_param["players"]:
            player_info = member["player_info"]
            if member is target:
                player_info["role"] = 1
            elif player_info["role"] == 1:
                player_info["role"] = 2
        self._group_param["admin_player_uid"] = target["player_uid"]

    @property
    def group_type(self) -> str:
        return self._group_type

    @property
    def guild_format(self) -> Optional[str]:
        return self._group_param.get("guild_format")

    @property
    def base_camp_level(self) -> Optional[int]:
        value = self._group_param.get("base_camp_level")
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    def set_base_camp_level(self, level: int) -> None:
        current = self._group_param.get("base_camp_level")
        if isinstance(current, bool) or not isinstance(current, int):
            raise ValueError("Base camp level field is unavailable")
        self._group_param["base_camp_level"] = level

    @property
    def players(self) -> Optional[list[tuple[UUID, str]]]:
        if self.group_type == "EPalGroupType::IndependentGuild":
            player_uid = self._group_param.get("player_uid")
            if not player_uid:
                return []
            player_info = self._group_param.get("player_info") or {}
            return [(player_uid, player_info.get("player_name") or "")]
        return [
            (player_data["player_uid"], player_data["player_info"]["player_name"])
            for player_data in self._group_param.get("players") or []
        ]


class GroupData:
    def __init__(self, gvas_file: GvasFile) -> None:
        self.group_map = {}
        self._wsd = gvas_file.properties["worldSaveData"]["value"]
        if "GroupSaveDataMap" not in self._wsd:
            LOGGER.info("No Group Found")
            return
        self._GSDM = self._wsd["GroupSaveDataMap"]

        for group in self._GSDM["value"]:
            group_id: UUID = group.get("key")
            if not group_id:
                continue

            group_type = PalObjects.get_EnumProperty(
                group.get("value", {}).get("GroupType")
            )
            if group_type not in {
                "EPalGroupType::Guild",
                "EPalGroupType::IndependentGuild",
            }:
                continue

            try:
                group_entity = PalGroup(group, group_type)
            except Exception as e:
                raise ValueError(f"Invalid guild group: {e}") from e

            key = str(group_id)
            if key in self.group_map:
                raise ValueError(f"Duplicate guild group id: {key}")
            self.group_map[key] = group_entity
            LOGGER.info(f"Guild Found: {group_entity}")

    def get_group(self, group_id: UUID | str) -> Optional[PalGroup]:
        return self.group_map.get(str(group_id))

    def get_groups(self) -> list[PalGroup]:
        return list(self.group_map.values())

    def get_player_group_id(self, player_uid: UUID | str) -> Optional[UUID]:
        for group in self.get_groups():
            if group.has_player(player_uid):
                return group.group_id
        return None
