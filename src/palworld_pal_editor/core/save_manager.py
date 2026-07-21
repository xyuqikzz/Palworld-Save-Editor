import copy
import contextlib
from datetime import datetime
import io
from pathlib import Path
import shutil
import traceback
from typing import Optional
import uuid
from time import perf_counter

from palworld_save_tools.gvas import GvasFile
from palworld_save_tools.archive import FArchiveReader, FArchiveWriter, UUID
from palworld_save_tools.palsav import compress_gvas_to_sav, decompress_sav_to_gvas
from palworld_save_tools.paltypes import PALWORLD_CUSTOM_PROPERTIES, PALWORLD_TYPE_HINTS

from palworld_pal_editor.core.basecamp_data import BaseCampData

from palworld_pal_editor.core.container_data import ContainerData
from palworld_pal_editor.core.character_index import CharacterIndex
from palworld_pal_editor.core.item_container_data import ItemContainerData
from palworld_pal_editor.core.dynamic_item_data import DynamicItemData

from palworld_pal_editor.core.pal_objects import PalObjects, UUID2HexStr, toUUID
from palworld_pal_editor.core.player_entity import PlayerEntity
from palworld_pal_editor.core.lazy_player_entity import LazyPlayerEntity
from palworld_pal_editor.core.pal_entity import PalEntity
from palworld_pal_editor.utils import LOGGER, alphanumeric_key
from palworld_pal_editor.core.group_data import GroupData
from palworld_pal_editor.config import ASSETS_PATH


def skip_decode(reader: FArchiveReader, type_name: str, size: int, path: str):
    if type_name == "ArrayProperty":
        array_type = reader.fstring()
        value = {
            "skip_type": type_name,
            "array_type": array_type,
            "id": reader.optional_guid(),
            "value": reader.read(size),
        }
    elif type_name == "MapProperty":
        key_type = reader.fstring()
        value_type = reader.fstring()
        _id = reader.optional_guid()
        value = {
            "skip_type": type_name,
            "key_type": key_type,
            "value_type": value_type,
            "id": _id,
            "value": reader.read(size),
        }
    elif type_name == "StructProperty":
        value = {
            "skip_type": type_name,
            "struct_type": reader.fstring(),
            "struct_id": reader.guid(),
            "id": reader.optional_guid(),
            "value": reader.read(size),
        }
    else:
        raise Exception(
            f"Expected ArrayProperty or MapProperty or StructProperty, got {type_name} in {path}"
        )
    return value


def skip_encode(writer: FArchiveWriter, property_type: str, properties: dict) -> int:
    if "skip_type" not in properties:
        if properties["custom_type"] in PALWORLD_CUSTOM_PROPERTIES is not None:
            return PALWORLD_CUSTOM_PROPERTIES[properties["custom_type"]][1](
                writer, property_type, properties
            )
        else:
            # Never be run to here
            return writer.property_inner(writer, property_type, properties)
    if property_type == "ArrayProperty":
        del properties["custom_type"]
        del properties["skip_type"]
        writer.fstring(properties["array_type"])
        writer.optional_guid(properties.get("id", None))
        writer.write(properties["value"])
        return len(properties["value"])
    elif property_type == "MapProperty":
        del properties["custom_type"]
        del properties["skip_type"]
        writer.fstring(properties["key_type"])
        writer.fstring(properties["value_type"])
        writer.optional_guid(properties.get("id", None))
        writer.write(properties["value"])
        return len(properties["value"])
    elif property_type == "StructProperty":
        del properties["custom_type"]
        del properties["skip_type"]
        writer.fstring(properties["struct_type"])
        writer.guid(properties["struct_id"])
        writer.optional_guid(properties.get("id", None))
        writer.write(properties["value"])
        return len(properties["value"])
    else:
        raise Exception(
            f"Expected ArrayProperty or MapProperty or StructProperty, got {property_type}"
        )


MAIN_SKIP_PROPERTIES = copy.deepcopy(PALWORLD_CUSTOM_PROPERTIES)
MAIN_SKIP_PROPERTIES[".worldSaveData.MapObjectSaveData"] = (skip_decode, skip_encode)
MAIN_SKIP_PROPERTIES[".worldSaveData.FoliageGridSaveDataMap"] = (skip_decode, skip_encode)
MAIN_SKIP_PROPERTIES[".worldSaveData.MapObjectSpawnerInStageSaveData"] = (skip_decode, skip_encode)
MAIN_SKIP_PROPERTIES[".worldSaveData.WorkSaveData"] = (skip_decode, skip_encode)
MAIN_SKIP_PROPERTIES[".worldSaveData.DungeonSaveData"] = (skip_decode, skip_encode)
MAIN_SKIP_PROPERTIES[".worldSaveData.EnemyCampSaveData"] = (skip_decode, skip_encode)
MAIN_SKIP_PROPERTIES[".worldSaveData.CharacterParameterStorageSaveData"] = (skip_decode, skip_encode)

MAIN_SKIP_PROPERTIES[".worldSaveData.InvaderSaveData"] = (skip_decode, skip_encode)
MAIN_SKIP_PROPERTIES[".worldSaveData.DungeonPointMarkerSaveData"] = (skip_decode, skip_encode)
MAIN_SKIP_PROPERTIES[".worldSaveData.GameTimeSaveData"] = (skip_decode, skip_encode)
MAIN_SKIP_PROPERTIES[".worldSaveData.FixedWeaponDestroySaveData"] = (skip_decode, skip_encode)

MAIN_SKIP_PROPERTIES[".worldSaveData.OilrigSaveData"] = (skip_decode, skip_encode)
MAIN_SKIP_PROPERTIES[".worldSaveData.SupplySaveData"] = (skip_decode, skip_encode)

MAIN_SKIP_PROPERTIES[".worldSaveData.RandomizerSaveData"] = (skip_decode, skip_encode)
MAIN_SKIP_PROPERTIES[".worldSaveData.GuildExtraSaveDataMap"] = (skip_decode, skip_encode)

PLAYER_SKIP_PROPERTIES = copy.deepcopy(PALWORLD_CUSTOM_PROPERTIES)
PLAYER_SKIP_PROPERTIES[".SaveData.PlayerCharacterMakeData"] = (skip_decode, skip_encode)
PLAYER_SKIP_PROPERTIES[".SaveData.LastTransform"] = (skip_decode, skip_encode)
# PLAYER_SKIP_PROPERTIES[".SaveData.RecordData"] = (skip_decode, skip_encode)

class SaveManager:
    # Although these are class attrs, SaveManager itself is singleton so it should be fine?
    _instance = None
    _file_path: Optional[Path]
    _raw_gvas: Optional[bytes]
    _compression_times: Optional[int]

    gvas_file: Optional[GvasFile]
    _entities_list: Optional[list[dict]]

    player_mapping: Optional[dict[str, PlayerEntity]]
    baseworker_mapping: Optional[dict[str, PalEntity]]
    _dangling_pals: Optional[dict[str, PalEntity]]
    
    container_data: Optional[ContainerData]
    item_container_data: Optional[ItemContainerData]
    dynamic_item_data: Optional[DynamicItemData]
    group_data: Optional[GroupData]
    camp_data: Optional[BaseCampData]

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "initialized"):
            self.initialized = True

    @classmethod
    def create_isolated(cls) -> "SaveManager":
        """Create an independent manager for an explicitly secondary save."""
        instance = object.__new__(cls)
        cls.__init__(instance)
        return instance
                
    def open(self, file_path: str, *, lazy_players: bool = False) -> Optional[GvasFile]:
        self._file_path = Path(file_path).resolve()
        self.player_file_load_count = 0
        self.player_file_load_seconds = {}
        self._lazy_players = lazy_players
        open_started = perf_counter()

        level_sav_path = self._file_path / "Level.sav"

        if not level_sav_path.exists():
            LOGGER.error(f"Save file does not exist: {level_sav_path}.")
            return None

        LOGGER.info(f"Opening {level_sav_path}")
        with level_sav_path.open("rb") as file:
            data = file.read()

            try:
                LOGGER.info("Decompressing sav")
                self._raw_gvas, self._compression_times = decompress_sav_to_gvas(data)

                # LOGGER.info("Compressing Main GVAS file")
                # sav_data = compress_gvas_to_sav(
                #     self._raw_gvas, 
                #     # self._compression_times, 
                #     0x32,
                #     True
                # )

                # with level_sav_path.open("wb") as file:
                #     file.write(sav_data)

                # return
            except Exception as e:
                LOGGER.error(f"Caught Exception: palworld_save_tools::palsav::decompress_sav_to_gvas: {e}")
                return None

            LOGGER.info("Reading GVAS file")
            self.gvas_file = GvasFile.read(
                self._raw_gvas, PALWORLD_TYPE_HINTS, MAIN_SKIP_PROPERTIES
            )

            PalObjects.TIME = PalObjects.get_BaseType(self.gvas_file.properties.get("Timestamp")) or PalObjects.TIME

            try:
                self.group_data = GroupData(self.gvas_file)
            except Exception as e:
                LOGGER.error(f"Error parsing group data: {e}")
                return None
            
            try:
                self.camp_data = BaseCampData(self.gvas_file)
            except Exception as e:
                LOGGER.error(f"Error parsing base camp data: {e}")
                return None
            
            try:
                self.container_data = ContainerData(self.gvas_file)
            except Exception as e:
                LOGGER.error(f"Error parsing container data: {e}")
                return None

            try:
                self.item_container_data = ItemContainerData(self.gvas_file)
            except Exception as e:
                LOGGER.error(f"Error parsing item container data: {e}")
                return None

            try:
                self.dynamic_item_data = DynamicItemData(
                    self.gvas_file,
                    self.item_container_data,
                    reference_scope_verifier=(
                        self._audit_dynamic_item_reference_scope
                    ),
                )
            except Exception as e:
                LOGGER.error(f"Error indexing dynamic item data: {e}")
                return None

            try:
                self._entities_list = self.gvas_file.properties["worldSaveData"]["value"]["CharacterSaveParameterMap"]["value"]
            except Exception as e:
                LOGGER.error(f"Unable to retrieve pal data: {e}")
                return None

            self._load_entities(lazy_players=lazy_players)
            self.character_index = CharacterIndex(self)

            if self.character_index.hard_issues():
                LOGGER.warning(
                    "Character reference inconsistencies detected; structural writes "
                    "will remain disabled until they are resolved."
                )

            self.open_seconds = perf_counter() - open_started
            LOGGER.info("Done")
        return self.gvas_file

    def _audit_dynamic_item_reference_scope(
        self, local_id: str, expected_level_occurrences: int
    ) -> bool:
        """Prove that a dynamic ID has no opaque reference before deletion."""
        if (
            self._raw_gvas is None
            or self._file_path is None
            or self.item_container_data is None
            or not self.item_container_data.dynamic_reference_layout_complete
        ):
            return False
        try:
            needle = UUID.from_str(local_id).raw_bytes
        except (ValueError, AttributeError):
            return False
        started = perf_counter()
        if self._raw_gvas.count(needle) != expected_level_occurrences:
            self.dynamic_item_reference_audit_seconds = perf_counter() - started
            return False

        paths = list(self._file_path.glob("*.sav"))
        players = self._file_path / "Players"
        if players.is_dir():
            paths.extend(players.glob("*.sav"))
        try:
            for path in sorted(paths):
                if path.name == "Level.sav":
                    continue
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
                    io.StringIO()
                ):
                    raw, _compression = decompress_sav_to_gvas(path.read_bytes())
                if needle in raw:
                    self.dynamic_item_reference_audit_seconds = (
                        perf_counter() - started
                    )
                    return False
        except Exception as error:
            LOGGER.warning(
                "Dynamic item reference audit could not inspect every save file: %s",
                error,
            )
            self.dynamic_item_reference_audit_seconds = perf_counter() - started
            return False
        self.dynamic_item_reference_audit_seconds = perf_counter() - started
        return True

    def save(self, file_path: str) -> bool:
        if self.gvas_file is None:
            LOGGER.error("No gvas_file stored in save manager, aborting")
            return False
        if self._compression_times is None:
            LOGGER.warning("_compression_times is None, aborting")
            return False

        output_path = Path(file_path).resolve() 

        if not output_path.exists():
            LOGGER.warning(f"Path does not exist: {output_path}")
            if output_path.parent.exists():
                output_path.mkdir(parents=True, exist_ok=True)
                LOGGER.debug(f"Path {output_path} created")
            else:
                LOGGER.error(f"Parent path {output_path.parent} does not exist, skipping")
                return False
            
        file_path: Path = output_path / "Level.sav"

        if output_path.exists():
            BK_FOLDER_NAME = "Palworld-Pal-Editor-Backup"
            backup_dir = output_path / BK_FOLDER_NAME / f"{datetime.now().strftime(r'%Y-%m-%d_%H-%M-%S')}"
            try:
                if output_path.exists():
                    LOGGER.info(f"Saving backup of {output_path} to {backup_dir}")
                    shutil.copytree(self._file_path, backup_dir, 
                                    ignore=lambda dir, files: [f for f in files if not f == "Players" and not f.endswith('.sav')])
                else:
                    LOGGER.info(f"No existing directory to backup: {output_path}")
            except Exception as e:
                LOGGER.error(f"Error backing up directory: {e}")
                return False

        LOGGER.info("Saving Player Data...")
        for player in self.player_mapping.values():
            self.save_player_sav(player, output_path)

        LOGGER.info("Saving Level.sav...")
        gvas_file = copy.deepcopy(self.gvas_file)
        LOGGER.info("Compressing Main GVAS file")
        sav_data = compress_gvas_to_sav(
            gvas_file.write(MAIN_SKIP_PROPERTIES), 
            self._compression_times,
        )

        LOGGER.info(f"Saving to {file_path}")
        with file_path.open("wb") as file:
            file.write(sav_data)
        LOGGER.info(f"Saved to {file_path}")
        return True
    
    def load_player_sav(self, player_uid: str | UUID) -> GvasFile:
        player_path: Path = self._file_path / "Players" / f"{UUID2HexStr(player_uid)}.sav"
        LOGGER.info(f"Loading Player SAV: {player_path}")
        if not player_path.exists():
            LOGGER.error(f"Player SAV {str(player_path.absolute())} not exist")
            raise Exception(f"Player SAV {str(player_path.absolute())} not exist")
        with player_path.open("rb") as player_file:
            player_data = player_file.read()
        raw_gvas, compression_times = decompress_sav_to_gvas(player_data)
        player_gvas_file = GvasFile.read(raw_gvas, PALWORLD_TYPE_HINTS, PLAYER_SKIP_PROPERTIES)
        return player_gvas_file, compression_times

    def _record_player_file_load(self, player_uid: str, elapsed: float) -> None:
        self.player_file_load_count += 1
        self.player_file_load_seconds[str(player_uid)] = elapsed

    def _resolve_player_group_id(self, entity: dict, player_uid: str) -> Optional[UUID]:
        group_id = self.group_data.get_player_group_id(player_uid)
        if group_id is not None:
            return group_id

        raw_data = entity.get("value", {}).get("RawData", {}).get("value", {})
        declared_group_id = raw_data.get("group_id")
        group = self.group_data.get_group(declared_group_id)
        instance_id = PalObjects.get_BaseType(
            entity.get("key", {}).get("InstanceId")
        )
        if (
            group is None
            or group.guild_format != "raw"
            or instance_id is None
            or not group.has_pal(instance_id)
        ):
            return None

        LOGGER.warning(
            f"Guild player data is opaque; resolved player {player_uid} from "
            "its verified character group handle"
        )
        return group.group_id
    
    
    def save_player_sav(self, player_entity: PlayerEntity, save_path: Optional[Path] = None) -> bool:
        if player_entity.PlayerGVAS is None:
            return False

        player_entity.save_new_pal_records()
        gvas_file, compression_times = player_entity.PlayerGVAS
        output_path = (save_path or self._file_path) / "Players"
        if not output_path.exists() and output_path.parent.exists():
            LOGGER.warning(f"Player path does not exist: {output_path}")
            output_path.mkdir(parents=True, exist_ok=True)
            LOGGER.info(f"Player path {output_path} created")

        player_path: Path = output_path / f"{UUID2HexStr(player_entity.PlayerUId)}.sav"

        LOGGER.info(f"Compressing Player {player_entity} GVAS file")
        player_gvas_file = copy.deepcopy(gvas_file)
        sav_data = compress_gvas_to_sav(
            player_gvas_file.write(PLAYER_SKIP_PROPERTIES), compression_times
        )

        LOGGER.info(f"Saving to {player_path}")
        with player_path.open("wb") as file:
            file.write(sav_data)
        LOGGER.info(f"Saved to {player_path}")
        return True
    
    def _load_entities(self, *, lazy_players: bool = False):
        self.player_mapping = {}
        self._dangling_pals = {}
        self.baseworker_mapping = {}
        temp_player_pal_mapping: dict[str, dict[str, PalEntity]] = {}
        for entity in self._entities_list:
            entity_struct = entity["value"]["RawData"]["value"]["object"]["SaveParameter"]
            if entity_struct['struct_type'] != 'PalIndividualCharacterSaveParameter':
                LOGGER.warning(f"Non-player/pal data found in CharacterSaveParameterMap, skipping {entity}")
                continue

            entity_param: dict = entity_struct['value']
            try: 
                if PalObjects.get_BaseType(entity_param.get("IsPlayer")):
                    uid_str = str(PalObjects.get_BaseType(entity["key"].get("PlayerUId")))
                    nickname = str(PalObjects.get_BaseType(entity_param.get("NickName")))
                    LOGGER.info(f"Players found: {nickname} - {uid_str}")
                    if uid_str in self.player_mapping:
                        LOGGER.error(f"Duplicated player found: \n\t{self.player_mapping[uid_str]}, skipping...")
                        continue
                    
                    group_id = self._resolve_player_group_id(entity, uid_str)

                    if group_id is None:
                        LOGGER.warning(f"Player {uid_str} has no guild id")
                        continue

                    palbox = temp_player_pal_mapping.pop(uid_str, {})
                    if lazy_players:
                        player_entity = LazyPlayerEntity(
                            group_id,
                            entity,
                            palbox,
                            lambda player_id=uid_str: self.load_player_sav(player_id),
                            on_loaded=self._record_player_file_load,
                        )
                    else:
                        started = perf_counter()
                        player_gvas_file, player_compress_times = self.load_player_sav(uid_str)
                        self._record_player_file_load(
                            uid_str, perf_counter() - started
                        )
                        player_entity = PlayerEntity(
                            group_id,
                            entity,
                            palbox,
                            player_gvas_file,
                            player_compress_times,
                        )
                
                    self.player_mapping[uid_str] = player_entity
                    LOGGER.info(f"Player Object Created: {player_entity}")
                else:
                    pal_entity = PalEntity(entity)
                    container_id, slot_idx = pal_entity.SlotId
                    group_id = pal_entity.group_id
                    # is_unref_pal = not self.group_data.get_group(group_id).has_pal(pal_entity.InstanceId)
                    pal_container = self.container_data.get_container(container_id)
                    is_unref_pal = (not pal_container) or (not pal_container.has_pal(pal_entity.InstanceId))
                    if is_unref_pal:
                        LOGGER.info(f"Likely Ghost Pal: {pal_entity}")
                    pal_entity.is_unreferenced_pal = is_unref_pal

                    owner = pal_entity.OwnerPlayerUId
                    if owner:
                        owner_str = str(owner)
                        if owner_str in self.player_mapping:
                            self.player_mapping[owner_str].add_pal(pal_entity)
                        else:
                            temp_player_pal_mapping.setdefault(owner_str, dict())[str(pal_entity.InstanceId)] = pal_entity
                        LOGGER.info(f"Found pal: {pal_entity}")

                    else:
                        if pal_entity.OldOwnerPlayerUIds:
                            self.baseworker_mapping[str(pal_entity.InstanceId)] = pal_entity
                            continue
                        self._dangling_pals[str(pal_entity.InstanceId)] = pal_entity
                        LOGGER.error(f"Found dangling pal object: {pal_entity}, skipping")
                        continue

            except Exception as e:
                LOGGER.error(f"Error occured while init'in object: {e}, skipping")
                continue

        
        for player in self.player_mapping.values():
            LOGGER.newline()
            LOGGER.info(f"{player}")
            sorted_palbox = player.get_sorted_pals()
            for pal in sorted_palbox:
                LOGGER.info(f"\t{pal}")
        
        LOGGER.newline()
        LOGGER.info("Pals possibly working at the base: ")
        for pal in self.get_working_pals():
            LOGGER.info(f"\t{pal}")

        LOGGER.newline()
        LOGGER.info("Dangling Pals (No OwnerID and OldOwnerID): ")
        for pal in self._dangling_pals.values():
            LOGGER.warning(f"\t{pal}")

        for uid_str in temp_player_pal_mapping:
            pal_list = temp_player_pal_mapping[uid_str]
            LOGGER.newline()
            LOGGER.warning(f"Found dangling pals owned by non-existing user {uid_str}")
            for pal in pal_list.values():
                self._dangling_pals[str(pal.InstanceId)] = pal
                LOGGER.warning(f"\t{pal}")

    def get_players(self) -> list[PlayerEntity]:
        return self.player_mapping.values()
    
    def get_player(self, guid: UUID | str) -> Optional[PlayerEntity]:
        if guid is None: return
        guid = str(guid)
        if guid in self.player_mapping:
            player = self.player_mapping[guid]
            return player
        # LOGGER.warning(f"Player {guid} not exist")

    def get_players_by_name(self, name: str) -> list[PlayerEntity]:
        return [player for player in self.get_players() if player.NickName == name]
    
    def get_working_pal(self, guid: UUID | str) -> Optional[PalEntity]:
        return self.baseworker_mapping.get(str(guid), None)

    def get_pal(self, guid: UUID | str) -> Optional[PalEntity]:
        guid = str(guid)
        if guid in self.baseworker_mapping:
            return self.baseworker_mapping[guid]
        if guid in self._dangling_pals:
            return self._dangling_pals[guid]
        for player in self.get_players():
            if pal := player.get_pal(guid, disable_warning=True):
                return pal

        LOGGER.warning(f"Can't find pal {guid}")

    def get_working_pals(self) -> list[PalEntity]:
        return sorted(self.baseworker_mapping.values(), key=lambda pal: (alphanumeric_key(pal.PalDeckID), pal.Level or 1))

    
    def move_pal(self, pal_id: UUID | str, target_container_ids: list[UUID | str]) -> bool:
        pal_entity = self.get_pal(pal_id)
        if not pal_entity: raise Exception("Pal Not Found") 

        pal_container = None
        for id in target_container_ids:
            if container := self.container_data.get_container(id):
                if container.get_empty_slot() != -1:
                    pal_container = container
                    break

        if pal_container is None:
            LOGGER.info("No Empty Pal Slot")
            return False

        if pal_container.has_pal(pal_id):
            raise Exception("Pal already in the target container.")
        
        old_container = self.container_data.get_container(pal_entity.ContainerId)
        old_container.del_pal(pal_id)

        if (slot_idx := pal_container.add_pal(pal_id)) == -1:
            return False

        pal_entity.SlotId = (pal_container.ID, slot_idx)
        return True
    
    def delete_pal(self, guid: str | UUID) -> bool:
        popped_pal = None
        if guid in self.baseworker_mapping:
            popped_pal = self.baseworker_mapping.pop(guid)
        elif guid in self._dangling_pals:
            popped_pal = self._dangling_pals.pop(guid)
        else:
            for player in self.get_players():
                if popped_pal := player.pop_pal(guid):
                    break
        if not popped_pal:
            LOGGER.warning(f"Can't find pal {guid}")
            return False
        try:
            if pal_group := self.group_data.get_group(popped_pal.group_id):
                pal_group.del_pal(popped_pal.InstanceId)
            if pal_container := self.container_data.get_container(popped_pal.ContainerId):
                pal_container.del_pal(popped_pal.InstanceId)
            self._entities_list.remove(popped_pal._pal_obj)
        except:
            LOGGER.warning(f"Error Deleting PAL {guid}: {traceback.format_exc()}")
            return False
        LOGGER.info(f"DELETED PAL {guid}")
        return True
    
    def heal_all_pals(self):
        for pal in self.baseworker_mapping.values():
            pal.heal_pal()
        for pal in self._dangling_pals.values():
            pal.heal_pal()
        for player in self.get_players():
            for pal in player._palbox.values():
                pal.heal_pal() 
    
    def add_pal(self, player_uid: str | UUID, pal_obj: dict = None) -> Optional[PalEntity]:
        player = self.get_player(player_uid)
        if player is None:
            LOGGER.warning(f"Player {player_uid} not found")
            return None
        
        player_container_ids = [player.OtomoCharacterContainerId, player.PalStorageContainerId]
        
        pal_container = None
        for id in player_container_ids:
            if (container := self.container_data.get_container(id)) is not None:
                if container.get_empty_slot() != -1:
                    pal_container = container
                    break

        if pal_container is None:
            LOGGER.info("No Empty Pal Slot")
            return None
        
        pal_instanceId = toUUID(str(uuid.uuid4()))
        group_id = player.group_id
        group = self.group_data.get_group(group_id)

        while pal_container.has_pal(pal_instanceId) or group.has_pal(pal_instanceId):
            pal_instanceId = toUUID(str(uuid.uuid4()))

        try:
            if (slot_idx := pal_container.add_pal(pal_instanceId)) == -1:
                return None
            container_id = pal_container.ID
            group.add_pal(pal_instanceId)
            
            if not pal_obj:
                pal_obj = PalObjects.PalSaveParameter(pal_instanceId, player_uid, container_id, slot_idx, group_id)
                pal_entity = PalEntity(pal_obj)
            else:
                pal_obj = copy.deepcopy(pal_obj)
                pal_entity = PalEntity(pal_obj)
                pal_entity.InstanceId = pal_instanceId
                pal_entity.SlotId = (container_id, slot_idx)
                # I don't know why some captured pals have PlayerUId, 
                # But having non-empty ID will cause the game to hide the duped pal
                pal_entity.PlayerUId = PalObjects.EMPTY_UUID
                # It seems the item container id is not necessarily referenced in the ItemContainerSaveData
                # so just assign a randomly for now.
                pal_entity._pal_param["EquipItemContainerId"] = PalObjects.PalContainerId(str(uuid.uuid4()))
                # pal_entity._pal_param.pop("EquipItemContainerId", None)
                # remove expedition status
                pal_entity._pal_param.pop("MapObjectConcreteInstanceIdAssignedToExpedition", None)
                pal_entity.NickName = "!!!DUPED PAL!!!"

            pal_entity.is_new_pal = True

            if not player.add_pal(pal_entity):
                raise Exception("Duplicated Pal ID, Try Again!")
            self._entities_list.append(pal_obj)
        except:
            LOGGER.error(f"Failed adding pal: {traceback.format_exc()}")
            return None
        LOGGER.info(f"Added Pal {pal_entity} to Player {player}")
        return pal_entity
