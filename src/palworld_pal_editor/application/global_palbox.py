from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import shutil
from threading import RLock
import tempfile
from typing import Callable
import uuid

from palworld_save_tools.gvas import GvasFile
from palworld_save_tools.palsav import compress_gvas_to_sav, decompress_sav_to_gvas
from palworld_save_tools.paltypes import (
    PALWORLD_CUSTOM_PROPERTIES,
    PALWORLD_TYPE_HINTS,
)

from palworld_pal_editor.core.pal_entity import PalEntity
from palworld_pal_editor.core.pal_objects import PalGender, PalObjects, toUUID
from palworld_pal_editor.domain.errors import DomainError, stale_revision
from palworld_pal_editor.domain.models import OpenedSave, SaveSource, StorageCommitRequest
from palworld_pal_editor.storage.discovery import XgpSourceCatalog
from palworld_pal_editor.storage.steam import _native_path, sha256_file
from palworld_pal_editor.storage.xgp import PalworldProcessChecker, XgpWgsAdapter
from palworld_pal_editor.utils.data_provider import DataProvider


GLOBAL_PALBOX_FILENAME = "GlobalPalStorage.sav"
GLOBAL_PALBOX_CLASS = "/Script/Pal.PalGlobalPalStorageSaveGame"
GLOBAL_PALBOX_ARRAY_TYPE = "PalGlobalPalStorageSaveParameter"
ZERO_GUID = "00000000-0000-0000-0000-000000000000"


@dataclass(frozen=True)
class _FileFingerprint:
    size: int
    mtime_ns: int
    sha256: str


def _fingerprint(path: Path) -> _FileFingerprint:
    native = _native_path(path)
    stat = native.stat()
    return _FileFingerprint(
        size=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
        sha256=sha256_file(path),
    )


def _global_entry_pal(entry: dict) -> PalEntity:
    return PalEntity(
        {
            "key": entry["InstanceId"]["value"],
            "value": {
                "RawData": {
                    "value": {
                        "object": {"SaveParameter": entry["SaveParameter"]}
                    }
                }
            },
        }
    )


class GlobalPalboxDocument:
    """One direct-file Global Palbox session with verified transactional save."""

    def __init__(
        self,
        *,
        source: Path,
        gvas: GvasFile,
        compression: int,
        baseline: _FileFingerprint,
        process_checker: Callable[[], bool],
        backup_root: Path | None,
        platform: str = "steam",
        opened_storage: OpenedSave | None = None,
        storage_adapter: XgpWgsAdapter | None = None,
    ) -> None:
        self._source = source
        self._gvas = gvas
        self._compression = compression
        self._baseline = baseline
        self._process_checker = process_checker
        self._backup_root = backup_root.resolve() if backup_root else None
        self._platform = platform
        self._opened_storage = opened_storage
        self._storage_adapter = storage_adapter
        self._session_id = str(uuid.uuid4())
        self._revision = 0
        self._changes: list[dict] = []
        self._validate_structure()

    @classmethod
    def open(
        cls,
        source: str | Path,
        *,
        process_checker: Callable[[], bool] | None = None,
        backup_root: Path | None = None,
    ) -> "GlobalPalboxDocument":
        path = Path(source).resolve()
        if path.is_dir() or path.name.casefold() == "containers.index":
            selected = path.parent if path.name.casefold() == "containers.index" else path
            user = XgpSourceCatalog._find_selected_user_directory(selected)
            if user is None:
                raise DomainError(
                    code="GLOBAL_PALBOX_WGS_NOT_FOUND",
                    message="Select a Game Pass user folder containing containers.index.",
                    field="path",
                    retryable=True,
                    http_status=404,
                )
            catalog = XgpSourceCatalog(roots=(user.parent.resolve(),))
            sources = catalog.discover_global_palboxes_selected(user)
            if len(sources) != 1 or sources[0].status != "available":
                raise DomainError(
                    code="GLOBAL_PALBOX_WGS_AMBIGUOUS",
                    message="The selected Game Pass account has ambiguous Global Palbox data.",
                    field="path",
                    retryable=True,
                    http_status=409,
                )
            return cls.open_xgp(
                sources[0],
                catalog=catalog,
                process_checker=process_checker,
                backup_root=backup_root,
            )
        if path.name.casefold() != GLOBAL_PALBOX_FILENAME.casefold():
            raise DomainError(
                code="GLOBAL_PALBOX_FILE_REQUIRED",
                message="Select GlobalPalStorage.sav.",
                field="path",
                http_status=400,
            )
        native = _native_path(path)
        if not native.is_file() or native.is_symlink():
            raise DomainError(
                code="GLOBAL_PALBOX_NOT_FOUND",
                message="The selected Global Palbox file is unavailable.",
                field="path",
                retryable=True,
                http_status=404,
            )
        checker = process_checker or PalworldProcessChecker()
        if checker():
            raise DomainError(
                code="GLOBAL_PALBOX_GAME_RUNNING",
                message="Palworld must be fully closed before opening the Global Palbox.",
                retryable=True,
                http_status=409,
            )
        data = native.read_bytes()
        if data.startswith(b"CNK"):
            raise DomainError(
                code="GLOBAL_PALBOX_WGS_DIRECTORY_REQUIRED",
                message=(
                    "Select the Game Pass/WGS user directory containing "
                    "containers.index instead of an individual container payload."
                ),
                field="path",
                http_status=400,
            )
        try:
            raw, compression = decompress_sav_to_gvas(data)
            gvas = GvasFile.read(
                raw,
                PALWORLD_TYPE_HINTS,
                PALWORLD_CUSTOM_PROPERTIES,
                allow_nan=False,
            )
        except Exception as error:
            raise DomainError(
                code="GLOBAL_PALBOX_FORMAT_UNSUPPORTED",
                message="The selected Global Palbox format could not be read safely.",
                http_status=422,
            ) from error
        return cls(
            source=path,
            gvas=gvas,
            compression=compression,
            baseline=_fingerprint(path),
            process_checker=checker,
            backup_root=backup_root,
        )

    @classmethod
    def open_xgp(
        cls,
        source: SaveSource,
        *,
        catalog: XgpSourceCatalog,
        process_checker: Callable[[], bool] | None = None,
        backup_root: Path | None = None,
    ) -> "GlobalPalboxDocument":
        checker = process_checker or PalworldProcessChecker()

        def validate_workspace(workspace: Path) -> None:
            candidate = cls.open(
                workspace / GLOBAL_PALBOX_FILENAME,
                process_checker=lambda: False,
                backup_root=backup_root,
            )
            candidate.close()

        adapter = XgpWgsAdapter(
            catalog=catalog,
            process_checker=checker,
            workspace_validator=validate_workspace,
            backup_root=backup_root,
        )
        opened = adapter.open(source)
        try:
            document = cls.open(
                opened.workspace / GLOBAL_PALBOX_FILENAME,
                process_checker=lambda: False,
                backup_root=backup_root,
            )
        except Exception:
            adapter.close(opened)
            raise
        document._process_checker = checker
        document._platform = "xgp"
        document._opened_storage = opened
        document._storage_adapter = adapter
        return document

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def revision(self) -> int:
        return self._revision

    @property
    def source(self) -> Path:
        if self._opened_storage is not None:
            return self._opened_storage.source.canonical_path
        return self._source

    @property
    def source_identity(self) -> str:
        if self._opened_storage is not None:
            return self._opened_storage.source.source_id
        return str(self._source).casefold()

    def close(self) -> None:
        if self._storage_adapter is not None and self._opened_storage is not None:
            self._storage_adapter.close(self._opened_storage)
            self._opened_storage = None
            self._storage_adapter = None

    def _values(self) -> list[dict]:
        return self._gvas.properties["SaveParameterArray"]["value"]["values"]

    @staticmethod
    def _character_id(entry: dict) -> str | None:
        field = entry.get("SaveParameter", {}).get("value", {}).get("CharacterID")
        value = PalObjects.get_BaseType(field)
        return value if isinstance(value, str) else None

    @classmethod
    def _is_empty(cls, entry: dict) -> bool:
        return cls._character_id(entry) in {None, "", "None"}

    @staticmethod
    def _instance_id(entry: dict):
        return PalObjects.get_BaseType(
            entry.get("InstanceId", {}).get("value", {}).get("InstanceId")
        )

    def _validate_structure(self) -> None:
        if self._gvas.header.save_game_class_name != GLOBAL_PALBOX_CLASS:
            raise DomainError(
                code="GLOBAL_PALBOX_FORMAT_UNSUPPORTED",
                message="The selected file is not a Global Palbox save.",
                http_status=422,
            )
        array = self._gvas.properties.get("SaveParameterArray")
        value = array.get("value") if isinstance(array, dict) else None
        values = value.get("values") if isinstance(value, dict) else None
        if (
            not isinstance(array, dict)
            or array.get("type") != "ArrayProperty"
            or array.get("array_type") != "StructProperty"
            or not isinstance(value, dict)
            or value.get("type_name") != GLOBAL_PALBOX_ARRAY_TYPE
            or not isinstance(values, list)
            or not values
        ):
            self._unsupported_structure()

        instance_ids: set[str] = set()
        containers: set[str] = set()
        for entry in values:
            save_parameter = entry.get("SaveParameter") if isinstance(entry, dict) else None
            external_id = entry.get("InstanceId") if isinstance(entry, dict) else None
            parameter = save_parameter.get("value") if isinstance(save_parameter, dict) else None
            external_value = external_id.get("value") if isinstance(external_id, dict) else None
            if (
                not isinstance(parameter, dict)
                or save_parameter.get("type") != "StructProperty"
                or save_parameter.get("struct_type")
                != "PalIndividualCharacterSaveParameter"
                or not isinstance(external_value, dict)
                or external_id.get("type") != "StructProperty"
                or external_id.get("struct_type") != "PalInstanceID"
            ):
                self._unsupported_structure()
            if self._is_empty(entry):
                continue
            instance_id = self._instance_id(entry)
            slot = PalObjects.get_PalCharacterSlotId(parameter.get("SlotId"))
            if (
                instance_id is None
                or str(instance_id) == ZERO_GUID
                or slot is None
                or slot[1] < 0
                or not DataProvider.in_pal_data(self._character_id(entry))
            ):
                self._unsupported_structure()
            instance_key = str(instance_id)
            if instance_key in instance_ids:
                self._unsupported_structure()
            instance_ids.add(instance_key)
            containers.add(str(slot[0]))
        if len(containers) > 1:
            self._unsupported_structure()

    @staticmethod
    def _unsupported_structure() -> None:
        raise DomainError(
            code="GLOBAL_PALBOX_STRUCTURE_UNSUPPORTED",
            message="The Global Palbox uses an unknown slot or Pal structure.",
            http_status=422,
        )

    def _require_revision(self, expected_revision: int) -> None:
        if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
            raise DomainError(
                code="INVALID_REQUEST",
                message="expected_revision must be an integer.",
                field="expected_revision",
                http_status=400,
            )
        if expected_revision != self._revision:
            raise stale_revision(expected_revision, self._revision)

    def _find_entry(self, pal_id: str) -> dict:
        for entry in self._values():
            if not self._is_empty(entry) and str(self._instance_id(entry)) == str(pal_id):
                return entry
        raise DomainError(
            code="GLOBAL_PALBOX_PAL_NOT_FOUND",
            message="The selected Global Palbox Pal was not found.",
            field="pal_id",
            http_status=404,
        )

    def _empty_entry(self) -> dict | None:
        return next((entry for entry in self._values() if self._is_empty(entry)), None)

    def _container_id(self):
        for entry in self._values():
            if self._is_empty(entry):
                continue
            slot = PalObjects.get_PalCharacterSlotId(
                entry["SaveParameter"]["value"].get("SlotId")
            )
            if slot is not None:
                return slot[0]
        return toUUID(str(uuid.uuid4()))

    def _next_slot(self, container_id) -> int:
        used = {
            slot[1]
            for entry in self._values()
            if not self._is_empty(entry)
            for slot in [
                PalObjects.get_PalCharacterSlotId(
                    entry["SaveParameter"]["value"].get("SlotId")
                )
            ]
            if slot is not None and str(slot[0]) == str(container_id)
        }
        slot = 0
        while slot in used:
            slot += 1
        return slot

    @staticmethod
    def _pal_summary(pal: PalEntity) -> dict:
        icon_access_key = pal.IconAccessKey
        if icon_access_key == "skin-None":
            icon_access_key = pal.DataAccessKey
        return {
            "InstanceId": str(pal.InstanceId),
            "OwnerPlayerUId": (
                str(pal.OwnerPlayerUId) if pal.OwnerPlayerUId else None
            ),
            "group_id": str(pal.group_id) if pal.group_id else None,
            "SlotIndex": pal.SlotIndex,
            "OwnerName": None,
            "CharacterID": pal.CharacterID,
            "IconAccessKey": icon_access_key,
            "DataAccessKey": pal.DataAccessKey,
            "I18nName": pal.I18nName,
            "DisplayName": pal.DisplayName,
            "NickName": pal.CustomNickName or "",
            "Gender": pal.Gender.value if pal.Gender else None,
            "Level": pal.Level or 1,
            "FriendshipLevel": pal.FriendshipLevel or 0,
            "HasBaseVariant": pal.HasBaseVariant,
            "HasBossVariant": pal.HasBossVariant,
            "HasTowerVariant": pal.HasTowerVariant,
            "HasWorkerSick": pal.HasWorkerSick,
            "IsFaintedPal": pal.IsFaintedPal,
            "Is_Unref_Pal": False,
            "in_owner_palbox": True,
            "ContainerType": "PAL_STORAGE",
            "IsHuman": pal.IsHuman,
            "NpcDefaultWeapon": (
                DataProvider.get_npc_default_weapon(pal.CharacterID)
                if pal.IsHuman
                else None
            ),
            "IsBOSS": bool(pal.IsBOSS),
            "IsRarePal": bool(pal.IsRarePal),
            "IsTower": bool(pal.IsTower),
            "IsRAID": bool(pal.IsRAID),
            "IsPREDATOR": bool(pal.IsPREDATOR),
            "IsOilrig": bool(pal.IsOilrig),
            "IsAwakened": pal.IsAwakened,
            "AwakeningStatusMultiplier": pal.AWAKENING_STATUS_MULTIPLIER,
            "IsExpeditionPal": False,
            "ExpeditionInstanceId": None,
            "ExpeditionAssignmentStatus": None,
            "ExpeditionCanComplete": False,
            "ComputedMaxHP": pal.ComputedMaxHP,
            "ComputedAttack": pal.ComputedAttack,
            "ComputedDefense": pal.ComputedDefense,
            "ComputedCraftSpeed": pal.ComputedCraftSpeed,
            "Rank": pal.Rank or 1,
            "Rank_HP": pal.Rank_HP or 0,
            "Rank_Attack": pal.Rank_Attack or 0,
            "Rank_Defence": pal.Rank_Defence or 0,
            "Rank_CraftSpeed": pal.Rank_CraftSpeed or 0,
            "Talent_HP": pal.Talent_HP or 0,
            "Talent_Melee": pal.Talent_Melee or 0,
            "Talent_Shot": pal.Talent_Shot or 0,
            "Talent_Defense": pal.Talent_Defense or 0,
            "PassiveSkillList": list(pal.PassiveSkillList or []),
            "EquipWaza": list(pal.EquipWaza or []),
            "MasteredWaza": list(pal.MasteredWaza or []),
            "Suitabilities": dict(pal.WorkSuitabilities or {}),
        }

    def pals(self) -> list[dict]:
        pals = [
            self._pal_summary(_global_entry_pal(entry))
            for entry in self._values()
            if not self._is_empty(entry)
        ]
        return sorted(
            pals,
            key=lambda pal: (pal["SlotIndex"], pal["InstanceId"]),
        )

    def summary(self) -> dict:
        capacity = len(self._values())
        occupied = sum(not self._is_empty(entry) for entry in self._values())
        source = self.source
        return {
            "session_id": self._session_id,
            "revision": self._revision,
            "source": str(source),
            "source_display_name": (
                self._opened_storage.source.display_name
                if self._opened_storage is not None
                else str(source)
            ),
            "platform": self._platform,
            "capacity": capacity,
            "occupied": occupied,
            "free": capacity - occupied,
            "pending_change_count": len(self._changes),
            "capabilities": {
                "commitOriginal": True,
                "steamDirectFile": self._platform == "steam",
                "wgsWriteBack": self._platform == "xgp",
                "cloudSyncVerified": False,
            },
        }

    @staticmethod
    def catalog() -> list[dict]:
        return [
            {
                "InternalName": item["InternalName"],
                "I18n": DataProvider.get_pal_i18n(item["InternalName"]),
                "Elements": list(item.get("Elements") or []),
                "SortingKey": DataProvider.get_pal_sorting_key(item["InternalName"]),
                "IsHuman": bool(item.get("Human")),
                "HasIcon": bool(item.get("HasIcon")),
                "DefaultWeapon": item.get("DefaultWeapon"),
            }
            for item in DataProvider.get_sorted_pals()
            if item.get("InternalName")
        ]

    def _record_change(self, command: str, before: dict | None, after: dict | None) -> int:
        self._revision += 1
        self._changes.append(
            {
                "command": command,
                "before": before,
                "after": after,
                "revision": self._revision,
            }
        )
        return self._revision

    def update_pal(
        self,
        *,
        pal_id: str,
        expected_revision: int,
        values: dict,
    ) -> dict:
        self._require_revision(expected_revision)
        if not isinstance(values, dict) or not values:
            raise DomainError(
                code="INVALID_REQUEST",
                message="At least one Global Palbox field is required.",
                field="values",
                http_status=400,
            )
        allowed = {
            "species_id",
            "nickname",
            "gender",
            "level",
            "friendship_level",
            "rank",
            "is_boss",
            "is_tower",
            "is_rare",
            "is_awakened",
            "iv_hp",
            "iv_melee",
            "iv_shot",
            "iv_defense",
            "soul_hp",
            "soul_attack",
            "soul_defense",
            "soul_craft_speed",
            "work_suitability",
            "passive",
            "active",
            "mastered",
        }
        unknown = sorted(set(values) - allowed)
        if unknown:
            raise DomainError(
                code="UNSUPPORTED_COMMAND_FIELD",
                message="The request contains unsupported Global Palbox fields.",
                details={"fields": unknown},
                http_status=400,
            )
        entry = self._find_entry(pal_id)
        pal = _global_entry_pal(entry)
        before_parameter = deepcopy(pal._pal_param)
        before = self._pal_summary(pal)
        try:
            species_id = values.get("species_id")
            if species_id is not None:
                if not isinstance(species_id, str) or not DataProvider.in_pal_data(species_id):
                    raise DomainError(
                        code="GLOBAL_PALBOX_SPECIES_UNKNOWN",
                        message="The selected Pal or NPC species is not in the local catalog.",
                        field="species_id",
                        http_status=400,
                    )
                pal.CharacterID = species_id
            if "nickname" in values:
                nickname = values["nickname"]
                if (
                    not isinstance(nickname, str)
                    or len(nickname) > 24
                    or any(ord(character) < 32 or ord(character) == 127 for character in nickname)
                ):
                    raise DomainError(
                        code="INVALID_CHARACTER_NAME",
                        message="Nicknames must be at most 24 characters and contain no control characters.",
                        field="nickname",
                        http_status=400,
                    )
                pal.NickName = nickname
            if "gender" in values:
                gender = values["gender"]
                if gender not in {"male", "female", "none"}:
                    raise DomainError(
                        code="INVALID_GENDER",
                        message="gender must be male, female, or none.",
                        field="gender",
                        http_status=400,
                    )
                genderless = pal.IsHuman or pal.IsOtomoTower
                if genderless != (gender == "none"):
                    raise DomainError(
                        code="INVALID_GENDER",
                        message="The selected species uses a different gender structure.",
                        field="gender",
                        http_status=400,
                    )
                pal.Gender = {
                    "male": PalGender.MALE,
                    "female": PalGender.FEMALE,
                    "none": "NONE",
                }[gender]
            if "level" in values:
                level = values["level"]
                if (
                    isinstance(level, bool)
                    or not isinstance(level, int)
                    or not 1 <= level <= 100
                    or DataProvider.get_pal_level_xp(level) is None
                ):
                    raise DomainError(
                        code="VALUE_OUT_OF_RANGE",
                        message="The Global Palbox level is outside the supported range.",
                        field="level",
                        http_status=400,
                    )
                pal.Level = level
            if "friendship_level" in values:
                friendship = values["friendship_level"]
                if (
                    isinstance(friendship, bool)
                    or not isinstance(friendship, int)
                    or not 0 <= friendship <= 255
                ):
                    raise DomainError(
                        code="VALUE_OUT_OF_RANGE",
                        message="The friendship level must be between 0 and 255.",
                        field="friendship_level",
                        http_status=400,
                    )
                pal.FriendshipLevel = friendship
            if "rank" in values:
                rank = values["rank"]
                if isinstance(rank, bool) or not isinstance(rank, int) or not 1 <= rank <= 255:
                    raise DomainError(
                        code="VALUE_OUT_OF_RANGE",
                        message="The condensation rank must be between 1 and 255.",
                        field="rank",
                        http_status=400,
                    )
                pal.Rank = rank
            for field, attribute in {
                "is_boss": "IsBOSS",
                "is_tower": "IsTower",
                "is_rare": "IsRarePal",
                "is_awakened": "IsAwakened",
            }.items():
                if field not in values:
                    continue
                enabled = values[field]
                if not isinstance(enabled, bool):
                    raise DomainError(
                        code="INVALID_REQUEST",
                        message=f"{field} must be a boolean.",
                        field=field,
                        http_status=400,
                    )
                setattr(pal, attribute, enabled)
            for field, attribute in {
                "iv_hp": "Talent_HP",
                "iv_melee": "Talent_Melee",
                "iv_shot": "Talent_Shot",
                "iv_defense": "Talent_Defense",
                "soul_hp": "Rank_HP",
                "soul_attack": "Rank_Attack",
                "soul_defense": "Rank_Defence",
                "soul_craft_speed": "Rank_CraftSpeed",
            }.items():
                if field not in values:
                    continue
                value = values[field]
                if (
                    isinstance(value, bool)
                    or not isinstance(value, int)
                    or not 0 <= value <= 255
                ):
                    raise DomainError(
                        code="VALUE_OUT_OF_RANGE",
                        message=f"{field} must be between 0 and 255.",
                        field=field,
                        http_status=400,
                    )
                setattr(pal, attribute, value)
            if "work_suitability" in values:
                suitability = values["work_suitability"]
                known = DataProvider.get_pal_suitabilities(pal.DataAccessKey) or {}
                if not isinstance(suitability, dict):
                    raise DomainError(
                        code="INVALID_REQUEST",
                        message="work_suitability must be an object.",
                        field="work_suitability",
                        http_status=400,
                    )
                for name, level in suitability.items():
                    if (
                        name not in known
                        or isinstance(level, bool)
                        or not isinstance(level, int)
                        or not 0 <= level <= 255
                    ):
                        raise DomainError(
                            code="VALUE_OUT_OF_RANGE",
                            message="A work suitability value is unsupported.",
                            field="work_suitability",
                            details={"name": name, "level": level},
                            http_status=400,
                        )
                    pal.set_WorkSuitability(name, level)
            passive = values.get("passive")
            if passive is not None:
                if (
                    not isinstance(passive, list)
                    or len(passive) > 16
                    or any(
                        not isinstance(skill, str)
                        or not DataProvider.has_passive_skill(skill)
                        for skill in passive
                    )
                ):
                    raise DomainError(
                        code="INVALID_REQUEST",
                        message="The passive skill list is unsupported.",
                        field="passive",
                        http_status=400,
                    )
                parameter = pal._pal_param
                parameter["PassiveSkillList"] = PalObjects.ArrayProperty(
                    "NameProperty", {"values": list(passive)}
                )
            mastered = values.get("mastered")
            active = values.get("active")
            if mastered is not None or active is not None:
                next_mastered = list(
                    mastered if mastered is not None else pal.MasteredWaza or []
                )
                next_active = list(active if active is not None else pal.EquipWaza or [])
                if (
                    len(next_active) > 3
                    or any(
                        not isinstance(skill, str)
                        or not DataProvider.has_attack(skill)
                        for skill in next_mastered + next_active
                    )
                    or any(skill not in next_mastered for skill in next_active)
                ):
                    raise DomainError(
                        code="INVALID_REQUEST",
                        message="The active skill lists are unsupported.",
                        field="active",
                        http_status=400,
                    )
                parameter = pal._pal_param
                parameter["MasteredWaza"] = PalObjects.ArrayProperty(
                    "EnumProperty", {"values": next_mastered}
                )
                parameter["EquipWaza"] = PalObjects.ArrayProperty(
                    "EnumProperty", {"values": next_active}
                )
            after = self._pal_summary(pal)
            self._validate_structure()
        except Exception:
            pal._pal_param.clear()
            pal._pal_param.update(before_parameter)
            raise
        revision = self._record_change("update_global_pal", before, after)
        return {"revision": revision, "pal": after}

    def add_pal(self, *, species_id: str, expected_revision: int) -> dict:
        self._require_revision(expected_revision)
        if not isinstance(species_id, str) or not DataProvider.in_pal_data(species_id):
            raise DomainError(
                code="GLOBAL_PALBOX_SPECIES_UNKNOWN",
                message="The selected Pal or NPC species is not in the local catalog.",
                field="species_id",
                http_status=400,
            )
        entry = self._empty_entry()
        if entry is None:
            raise DomainError(
                code="GLOBAL_PALBOX_FULL",
                message="The Global Palbox has no free slots; change or delete an existing entry first.",
                http_status=409,
            )
        before = deepcopy(entry)
        try:
            container_id = self._container_id()
            slot_index = self._next_slot(container_id)
            instance_id = toUUID(str(uuid.uuid4()))
            parameter = entry["SaveParameter"]["value"]
            parameter["CharacterID"] = PalObjects.NameProperty(species_id)
            PalObjects.set_BaseType(
                entry["InstanceId"]["value"]["InstanceId"], instance_id
            )
            if "SlotId" not in parameter:
                parameter["SlotId"] = PalObjects.PalCharacterSlotId(
                    slot_index, container_id
                )
            else:
                PalObjects.set_PalCharacterSlotId(
                    parameter["SlotId"], container_id, slot_index
                )
            pal = _global_entry_pal(entry)
            pal.CharacterID = species_id
            pal.Level = 1
            after = self._pal_summary(pal)
            self._validate_structure()
        except Exception:
            entry.clear()
            entry.update(before)
            raise
        revision = self._record_change("add_global_pal", None, after)
        return {"revision": revision, "pal": after}

    def clone_pal(self, *, pal_id: str, expected_revision: int) -> dict:
        self._require_revision(expected_revision)
        source = self._find_entry(pal_id)
        target = self._empty_entry()
        if target is None:
            raise DomainError(
                code="GLOBAL_PALBOX_FULL",
                message="The Global Palbox has no free slots.",
                http_status=409,
            )
        before = deepcopy(target)
        try:
            target["SaveParameter"]["value"] = deepcopy(
                source["SaveParameter"]["value"]
            )
            container_id = self._container_id()
            slot_index = self._next_slot(container_id)
            instance_id = toUUID(str(uuid.uuid4()))
            PalObjects.set_BaseType(
                target["InstanceId"]["value"]["InstanceId"], instance_id
            )
            PalObjects.set_PalCharacterSlotId(
                target["SaveParameter"]["value"]["SlotId"],
                container_id,
                slot_index,
            )
            pal = _global_entry_pal(target)
            after = self._pal_summary(pal)
            self._validate_structure()
        except Exception:
            target.clear()
            target.update(before)
            raise
        revision = self._record_change("clone_global_pal", None, after)
        return {"revision": revision, "pal": after}

    def delete_pal(self, *, pal_id: str, expected_revision: int) -> dict:
        self._require_revision(expected_revision)
        entry = self._find_entry(pal_id)
        before_entry = deepcopy(entry)
        before = self._pal_summary(_global_entry_pal(entry))
        blank = self._empty_entry()
        try:
            if blank is not None:
                entry["SaveParameter"]["value"] = deepcopy(
                    blank["SaveParameter"]["value"]
                )
            else:
                parameter = entry["SaveParameter"]["value"]
                PalObjects.set_BaseType(parameter["CharacterID"], "None")
                slot = PalObjects.get_PalCharacterSlotId(parameter.get("SlotId"))
                container_id = slot[0] if slot is not None else toUUID(ZERO_GUID)
                PalObjects.set_PalCharacterSlotId(
                    parameter["SlotId"], container_id, -1
                )
            PalObjects.set_BaseType(
                entry["InstanceId"]["value"]["InstanceId"], toUUID(ZERO_GUID)
            )
            self._validate_structure()
        except Exception:
            entry.clear()
            entry.update(before_entry)
            raise
        revision = self._record_change("delete_global_pal", before, None)
        return {"revision": revision, "deleted_pal_id": str(pal_id)}

    def _semantic_fingerprint(self, gvas: GvasFile | None = None) -> str:
        document = gvas or self._gvas
        return hashlib.sha256(
            document.write(PALWORLD_CUSTOM_PROPERTIES)
        ).hexdigest()

    def _serialized(self) -> bytes:
        return compress_gvas_to_sav(
            self._gvas.write(PALWORLD_CUSTOM_PROPERTIES),
            self._compression,
        )

    @classmethod
    def _reload_bytes(cls, data: bytes) -> tuple[GvasFile, int]:
        raw, compression = decompress_sav_to_gvas(data)
        return (
            GvasFile.read(
                raw,
                PALWORLD_TYPE_HINTS,
                PALWORLD_CUSTOM_PROPERTIES,
                allow_nan=False,
            ),
            compression,
        )

    def _resolved_backup_root(self) -> Path:
        if self._backup_root is not None:
            return self._backup_root
        local = os.environ.get("LOCALAPPDATA")
        root = (
            Path(local) / "Palworld-Pal-Editor" / "GlobalPalboxBackups"
            if local
            else Path(os.environ.get("TEMP") or self._source.parent)
            / "Palworld-Pal-Editor-GlobalPalboxBackups"
        )
        token = hashlib.sha256(str(self._source).casefold().encode("utf-8")).hexdigest()[:16]
        return root / token

    def _create_backup(self) -> tuple[Path, Path]:
        operation = (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "-"
            + uuid.uuid4().hex[:16]
        )
        directory = self._resolved_backup_root() / operation
        backup = directory / GLOBAL_PALBOX_FILENAME
        manifest = directory / "manifest.json"
        try:
            _native_path(directory).mkdir(parents=True, exist_ok=False)
            shutil.copy2(_native_path(self._source), _native_path(backup))
            if sha256_file(backup) != self._baseline.sha256:
                raise OSError("Global Palbox backup hash mismatch")
            document = {
                "schema_version": 1,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "source_sha256": self._baseline.sha256,
                "source_size": self._baseline.size,
                "file": GLOBAL_PALBOX_FILENAME,
            }
            _native_path(manifest).write_text(
                json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            if json.loads(_native_path(manifest).read_text(encoding="utf-8")) != document:
                raise OSError("Global Palbox backup manifest verification failed")
            return backup, manifest
        except Exception as error:
            raise DomainError(
                code="GLOBAL_PALBOX_BACKUP_FAILED",
                message="A complete verified Global Palbox backup could not be created.",
                details={"backup_path": str(directory)},
                retryable=True,
                http_status=500,
            ) from error

    def _restore(self, backup: Path) -> bool:
        temporary = self._source.with_name(
            f".{self._source.name}.{uuid.uuid4().hex}.restore"
        )
        try:
            shutil.copy2(_native_path(backup), _native_path(temporary))
            os.replace(_native_path(temporary), _native_path(self._source))
            return sha256_file(self._source) == self._baseline.sha256
        except Exception:
            return False
        finally:
            try:
                _native_path(temporary).unlink(missing_ok=True)
            except OSError:
                pass

    def _save_xgp(
        self,
        *,
        expected_revision: int,
        candidate_data: bytes,
        expected_semantics: str,
    ) -> dict:
        if self._storage_adapter is None or self._opened_storage is None:
            raise DomainError(
                code="GLOBAL_PALBOX_WGS_NOT_FOUND",
                message="The Game Pass Global Palbox session is unavailable.",
                http_status=404,
            )

        def verify_file(path: Path, relative_path: str) -> None:
            if relative_path != GLOBAL_PALBOX_FILENAME:
                raise ValueError("unexpected Global Palbox logical file")
            candidate = GlobalPalboxDocument.open(
                path,
                process_checker=lambda: False,
                backup_root=self._backup_root,
            )
            try:
                if candidate._semantic_fingerprint() != expected_semantics:
                    raise ValueError("Global Palbox staged semantics changed")
            finally:
                candidate.close()

        with tempfile.TemporaryDirectory(
            prefix="palworld-global-palbox-xgp-stage-"
        ) as temporary:
            staged_workspace = Path(temporary)
            staged_file = staged_workspace / GLOBAL_PALBOX_FILENAME
            _native_path(staged_file).write_bytes(candidate_data)
            result = self._storage_adapter.commit(
                StorageCommitRequest(
                    opened=self._opened_storage,
                    staged_workspace=staged_workspace,
                    changed_files=(PurePosixPath(GLOBAL_PALBOX_FILENAME),),
                    expected_revision=expected_revision,
                    verify_file=verify_file,
                )
            )

        reloaded_file = self._opened_storage.workspace / GLOBAL_PALBOX_FILENAME
        reloaded_gvas, reloaded_compression = self._reload_bytes(
            _native_path(reloaded_file).read_bytes()
        )
        reloaded = GlobalPalboxDocument(
            source=reloaded_file,
            gvas=reloaded_gvas,
            compression=reloaded_compression,
            baseline=_fingerprint(reloaded_file),
            process_checker=self._process_checker,
            backup_root=self._backup_root,
        )
        if reloaded._semantic_fingerprint() != expected_semantics:
            raise DomainError(
                code="GLOBAL_PALBOX_RELOAD_FAILED",
                message="The committed Game Pass Global Palbox could not be verified.",
                details={"backup_path": str(result.backup_path)},
                http_status=500,
            )
        self._gvas = reloaded._gvas
        self._compression = reloaded._compression
        self._baseline = _fingerprint(reloaded_file)
        self._changes.clear()
        return {
            "session_id": self._session_id,
            "revision": self._revision,
            "platform": "xgp",
            "backup_path": str(result.backup_path) if result.backup_path else None,
            "manifest_path": (
                str(result.manifest_path) if result.manifest_path else None
            ),
            "source_reloaded": result.source_reloaded,
            "recovery_status": result.recovery_status,
            "journal_path": str(result.journal_path) if result.journal_path else None,
            "cloud_sync_verified": False,
        }

    def save(self, *, expected_revision: int) -> dict:
        self._require_revision(expected_revision)
        if not self._changes:
            raise DomainError(
                code="GLOBAL_PALBOX_NO_CHANGES",
                message="The Global Palbox has no pending changes.",
                http_status=409,
            )
        if self._process_checker():
            raise DomainError(
                code="GLOBAL_PALBOX_GAME_RUNNING",
                message="Palworld must be fully closed before saving the Global Palbox.",
                retryable=True,
                http_status=409,
            )
        if _fingerprint(self._source) != self._baseline:
            raise DomainError(
                code="GLOBAL_PALBOX_SOURCE_CHANGED",
                message="The Global Palbox changed after this session opened.",
                retryable=True,
                http_status=409,
            )
        candidate_data = self._serialized()
        try:
            candidate_gvas, candidate_compression = self._reload_bytes(candidate_data)
            candidate = GlobalPalboxDocument(
                source=self._source,
                gvas=candidate_gvas,
                compression=candidate_compression,
                baseline=self._baseline,
                process_checker=self._process_checker,
                backup_root=self._backup_root,
            )
            expected_semantics = self._semantic_fingerprint()
            if candidate._semantic_fingerprint() != expected_semantics:
                raise ValueError("Global Palbox candidate semantic mismatch")
        except DomainError:
            raise
        except Exception as error:
            raise DomainError(
                code="GLOBAL_PALBOX_SERIALIZATION_FAILED",
                message="The modified Global Palbox could not be serialized and reopened.",
                http_status=422,
            ) from error

        if self._platform == "xgp":
            return self._save_xgp(
                expected_revision=expected_revision,
                candidate_data=candidate_data,
                expected_semantics=expected_semantics,
            )

        backup, manifest = self._create_backup()
        if _fingerprint(self._source) != self._baseline:
            raise DomainError(
                code="GLOBAL_PALBOX_SOURCE_CHANGED",
                message="The Global Palbox changed while its backup was created.",
                details={"backup_path": str(backup)},
                retryable=True,
                http_status=409,
            )

        temporary = self._source.with_name(
            f".{self._source.name}.{uuid.uuid4().hex}.tmp"
        )
        replaced = False
        try:
            with _native_path(temporary).open("wb") as stream:
                stream.write(candidate_data)
                stream.flush()
                os.fsync(stream.fileno())
            if self._process_checker():
                raise DomainError(
                    code="GLOBAL_PALBOX_GAME_RUNNING",
                    message=(
                        "Palworld started while the Global Palbox save was "
                        "being prepared. Close it and retry."
                    ),
                    retryable=True,
                    http_status=409,
                )
            if _fingerprint(self._source) != self._baseline:
                raise DomainError(
                    code="GLOBAL_PALBOX_SOURCE_CHANGED",
                    message=(
                        "The Global Palbox changed immediately before "
                        "replacement."
                    ),
                    details={"backup_path": str(backup)},
                    retryable=True,
                    http_status=409,
                )
            os.replace(_native_path(temporary), _native_path(self._source))
            replaced = True
            reloaded = GlobalPalboxDocument.open(
                self._source,
                process_checker=lambda: False,
                backup_root=self._backup_root,
            )
            if reloaded._semantic_fingerprint() != expected_semantics:
                raise ValueError("Committed Global Palbox semantic mismatch")
            self._gvas = reloaded._gvas
            self._compression = reloaded._compression
            self._baseline = _fingerprint(self._source)
            self._changes.clear()
            return {
                "session_id": self._session_id,
                "revision": self._revision,
                "platform": "steam",
                "backup_path": str(backup),
                "manifest_path": str(manifest),
                "source_reloaded": True,
                "recovery_status": "not_needed",
            }
        except DomainError as error:
            if not replaced and error.code in {
                "GLOBAL_PALBOX_GAME_RUNNING",
                "GLOBAL_PALBOX_SOURCE_CHANGED",
            }:
                raise
            recovered = replaced and self._restore(backup)
            if replaced and not recovered:
                raise DomainError(
                    code="GLOBAL_PALBOX_RECOVERY_FAILED",
                    message="Global Palbox save failed and the original file could not be restored safely.",
                    details={
                        "backup_path": str(backup),
                        "manifest_path": str(manifest),
                        "recovery_status": "failed",
                    },
                    http_status=500,
                ) from error
            raise DomainError(
                code="GLOBAL_PALBOX_SAVE_FAILED",
                message=(
                    "Global Palbox save failed before replacement."
                    if not replaced
                    else "Global Palbox save failed; the original file was restored and verified."
                ),
                details={
                    "backup_path": str(backup),
                    "manifest_path": str(manifest),
                    "recovery_status": "restored" if recovered else "not_needed",
                },
                retryable=True,
                http_status=500,
            ) from error
        except Exception as error:
            recovered = replaced and self._restore(backup)
            if replaced and not recovered:
                raise DomainError(
                    code="GLOBAL_PALBOX_RECOVERY_FAILED",
                    message="Global Palbox save failed and the original file could not be restored safely.",
                    details={
                        "backup_path": str(backup),
                        "manifest_path": str(manifest),
                        "recovery_status": "failed",
                    },
                    http_status=500,
                ) from error
            raise DomainError(
                code="GLOBAL_PALBOX_SAVE_FAILED",
                message=(
                    "Global Palbox save failed before replacement."
                    if not replaced
                    else "Global Palbox save failed; the original file was restored and verified."
                ),
                details={
                    "backup_path": str(backup),
                    "manifest_path": str(manifest),
                    "recovery_status": "restored" if recovered else "not_needed",
                },
                retryable=True,
                http_status=500,
            ) from error
        finally:
            try:
                _native_path(temporary).unlink(missing_ok=True)
            except OSError:
                pass


class GlobalPalboxRuntime:
    def __init__(self) -> None:
        self._lock = RLock()
        self._current: GlobalPalboxDocument | None = None
        self._xgp_catalog = XgpSourceCatalog()

    def discover_xgp(self, selected_path: str | Path | None = None) -> list[dict]:
        sources = (
            self._xgp_catalog.discover_global_palboxes_selected(selected_path)
            if selected_path is not None
            else self._xgp_catalog.discover_global_palboxes()
        )
        return [source.to_public_dict() for source in sources]

    def open(
        self,
        source: str | Path | None = None,
        *,
        platform: str = "steam",
        source_id: str | None = None,
    ) -> GlobalPalboxDocument:
        if platform == "xgp":
            if not source_id:
                raise DomainError(
                    code="INVALID_REQUEST",
                    message="sourceId is required for a Game Pass Global Palbox.",
                    field="sourceId",
                    http_status=400,
                )
            xgp_source = self._xgp_catalog.resolve(source_id)
            requested_identity = xgp_source.source_id
        else:
            if source is None:
                raise DomainError(
                    code="INVALID_REQUEST",
                    message="path is required for a Steam Global Palbox.",
                    field="path",
                    http_status=400,
                )
            direct_source = Path(source).resolve()
            requested_identity = str(direct_source).casefold()
        with self._lock:
            current = self._current
            if current is not None and current.summary()["pending_change_count"]:
                if current.source_identity == requested_identity:
                    return current
                raise DomainError(
                    code="UNSAVED_CHANGES_PRESENT",
                    message="Save or discard the current Global Palbox changes first.",
                    http_status=409,
                )
        candidate = (
            GlobalPalboxDocument.open_xgp(
                xgp_source,
                catalog=self._xgp_catalog,
            )
            if platform == "xgp"
            else GlobalPalboxDocument.open(direct_source)
        )
        with self._lock:
            previous = self._current
            self._current = candidate
        if previous is not None and previous is not candidate:
            previous.close()
        return candidate

    def get(self, session_id: str | None = None) -> GlobalPalboxDocument:
        with self._lock:
            current = self._current
        if current is None or (
            session_id is not None and current.session_id != session_id
        ):
            raise DomainError(
                code="GLOBAL_PALBOX_SESSION_NOT_FOUND",
                message="No matching Global Palbox session is open.",
                field="session_id",
                http_status=404,
            )
        return current

    def close(self, session_id: str, expected_revision: int, *, discard_changes: bool) -> None:
        current = self.get(session_id)
        current._require_revision(expected_revision)
        if current.summary()["pending_change_count"] and not discard_changes:
            raise DomainError(
                code="UNSAVED_CHANGES_PRESENT",
                message="Confirm that the Global Palbox changes should be discarded.",
                http_status=409,
            )
        with self._lock:
            if self._current is current:
                self._current = None
        current.close()

    def replace_for_tests(self, document: GlobalPalboxDocument | None) -> None:
        with self._lock:
            self._current = document


GLOBAL_PALBOX_RUNTIME = GlobalPalboxRuntime()
