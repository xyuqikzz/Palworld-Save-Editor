from __future__ import annotations

from time import perf_counter
from typing import Callable, Optional

from palworld_save_tools.archive import UUID

from palworld_pal_editor.core.pal_objects import PalObjects
from palworld_pal_editor.core.player_entity import PlayerEntity
from palworld_pal_editor.utils import LOGGER, alphanumeric_key


class LazyPlayerEntity:
    """Level.sav-backed player summary with an on-demand player-file detail."""

    def __init__(
        self,
        group_id,
        player_obj: dict,
        palbox: dict,
        loader: Callable[[], tuple[object, int]],
        *,
        on_loaded: Callable[[str, float], None] | None = None,
    ) -> None:
        object.__setattr__(self, "group_id", group_id)
        object.__setattr__(self, "_player_obj", player_obj)
        object.__setattr__(self, "_player_key", player_obj["key"])
        object.__setattr__(
            self,
            "_player_param",
            player_obj["value"]["RawData"]["value"]["object"]["SaveParameter"][
                "value"
            ],
        )
        object.__setattr__(self, "_palbox", palbox)
        object.__setattr__(self, "_new_palbox", {})
        object.__setattr__(self, "_loader", loader)
        object.__setattr__(self, "_on_loaded", on_loaded)
        object.__setattr__(self, "_loaded_entity", None)

        if not PalObjects.get_BaseType(self._player_param.get("IsPlayer")):
            raise TypeError("LazyPlayerEntity requires a player character record")
        for pal in palbox.values():
            pal.set_owner_player_entity(self)

    @property
    def is_loaded(self) -> bool:
        return self._loaded_entity is not None

    @property
    def PlayerUId(self) -> Optional[UUID]:
        return PalObjects.get_BaseType(self._player_key.get("PlayerUId"))

    @property
    def InstanceId(self) -> Optional[UUID]:
        return PalObjects.get_BaseType(self._player_key.get("InstanceId"))

    @property
    def NickName(self) -> Optional[str]:
        return PalObjects.get_BaseType(self._player_param.get("NickName"))

    @NickName.setter
    def NickName(self, value: str) -> None:
        setattr(self.load_details(), "NickName", value)

    @property
    def Level(self) -> Optional[int]:
        return PalObjects.get_ByteProperty(self._player_param.get("Level"))

    @Level.setter
    def Level(self, value: int) -> None:
        setattr(self.load_details(), "Level", value)

    def load_details(self) -> PlayerEntity:
        loaded = self._loaded_entity
        if loaded is not None:
            return loaded
        started = perf_counter()
        gvas_file, compression_times = self._loader()
        loaded = PlayerEntity(
            self.group_id,
            self._player_obj,
            self._palbox,
            gvas_file,
            compression_times,
        )
        loaded._new_palbox = self._new_palbox
        object.__setattr__(self, "_loaded_entity", loaded)
        for pal in self._palbox.values():
            pal.set_owner_player_entity(self)
        if self._on_loaded is not None:
            self._on_loaded(str(self.PlayerUId), perf_counter() - started)
        return loaded

    def invalidate_details(self) -> bool:
        if self._new_palbox:
            return False
        object.__setattr__(self, "_loaded_entity", None)
        return True

    def add_pal(self, pal_entity) -> bool:
        pal_id = str(pal_entity.InstanceId)
        if pal_id in self._palbox:
            return False
        self._palbox[pal_id] = pal_entity
        if pal_entity.is_new_pal:
            self._new_palbox[pal_id] = pal_entity
        pal_entity.set_owner_player_entity(self)
        return True

    def pop_pal(self, guid: str | UUID):
        normalized = str(guid)
        self._new_palbox.pop(normalized, None)
        return self._palbox.pop(normalized, None)

    def get_pals(self):
        return self._palbox.values()

    def get_pal(self, guid: str | UUID, disable_warning: bool = False):
        normalized = str(guid)
        pal = self._palbox.get(normalized)
        if pal is None and not disable_warning:
            LOGGER.warning(f"Player {self} has no pal {normalized}.")
        return pal

    def get_sorted_pals(self, sorting_key: str = "paldeck"):
        if sorting_key != "paldeck":
            return list(self.get_pals())
        return sorted(
            self.get_pals(),
            key=lambda pal: (
                pal.IsHuman or False,
                alphanumeric_key(pal.PalDeckID),
                pal.IsTower,
                pal.IsBOSS,
                pal.IsRarePal or False,
                pal.Level or 1,
            ),
        )

    def __getattr__(self, name: str):
        return getattr(self.load_details(), name)

    def __setattr__(self, name: str, value) -> None:
        if name.startswith("_") or name == "group_id":
            object.__setattr__(self, name, value)
            return
        descriptor = getattr(type(self), name, None)
        if descriptor is not None and hasattr(descriptor, "__set__"):
            descriptor.__set__(self, value)
            return
        setattr(self.load_details(), name, value)

    def __str__(self) -> str:
        return f"{self.NickName} - {self.PlayerUId} - {self.InstanceId}"

    def __hash__(self) -> int:
        return hash((self.InstanceId, self.PlayerUId))
