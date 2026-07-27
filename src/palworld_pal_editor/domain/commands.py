from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .models import CharacterContainerType, ItemContainerType


@dataclass(frozen=True, kw_only=True)
class SessionCommand:
    session_id: str
    expected_revision: int


@dataclass(frozen=True, kw_only=True)
class ResetFogOfWar(SessionCommand):
    confirmation: str


@dataclass(frozen=True, kw_only=True)
class ClearFogOfWar(SessionCommand):
    confirmation: str


@dataclass(frozen=True, kw_only=True)
class UnlockAllFastTravelPoints(SessionCommand):
    player_id: str
    confirmation: str


@dataclass(frozen=True, kw_only=True)
class UpdatePlayerInventoryCapacity(SessionCommand):
    player_id: str
    capacity: int


@dataclass(frozen=True, kw_only=True)
class UpdateGuildName(SessionCommand):
    guild_id: str
    name: str


@dataclass(frozen=True, kw_only=True)
class UpdateGuildChestCapacity(SessionCommand):
    guild_id: str
    capacity: int


@dataclass(frozen=True, kw_only=True)
class UpdateGuildBaseCampLevel(SessionCommand):
    guild_id: str
    level: int


@dataclass(frozen=True, kw_only=True)
class UpdateItemCount(SessionCommand):
    player_id: str
    container_type: ItemContainerType
    slot_index: int
    expected_static_id: str
    count: int


@dataclass(frozen=True, kw_only=True)
class PutItem(SessionCommand):
    player_id: str
    container_type: ItemContainerType
    slot_index: int
    static_id: str
    count: int
    mode: Literal["empty_only", "replace"] = "empty_only"
    dynamic_init: dict[str, Any] | None = None


@dataclass(frozen=True, kw_only=True)
class ClearItemSlot(SessionCommand):
    player_id: str
    container_type: ItemContainerType
    slot_index: int
    expected_static_id: str
    expected_dynamic_id: str | None = None


@dataclass(frozen=True, kw_only=True)
class PasteItemSlot(SessionCommand):
    player_id: str
    container_type: ItemContainerType
    slot_index: int
    clipboard_token: str


@dataclass(frozen=True, kw_only=True)
class SwapItemSlots(SessionCommand):
    player_id: str
    container_type: ItemContainerType
    source_slot_index: int
    target_slot_index: int


@dataclass(frozen=True, kw_only=True)
class SortItemContainer(SessionCommand):
    player_id: str
    container_type: ItemContainerType
    sort_by: Literal["name", "internal_id", "category", "rarity", "count"]
    descending: bool = False


@dataclass(frozen=True, kw_only=True)
class FillItemSlots(SessionCommand):
    player_id: str
    container_type: ItemContainerType
    slot_indices: tuple[int, ...]
    static_id: str
    count: int
    dynamic_init: dict[str, Any] | None = None


@dataclass(frozen=True, kw_only=True)
class UpdateDynamicItemAttributes(SessionCommand):
    player_id: str
    container_type: ItemContainerType
    slot_index: int
    expected_static_id: str
    expected_dynamic_id: str
    values: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class UpdatePlayerIdentity(SessionCommand):
    player_id: str
    name: str


@dataclass(frozen=True, kw_only=True)
class UpdatePlayerProgression(SessionCommand):
    player_id: str
    level: int | None = None
    experience: int | None = None
    technology_points: int | None = None
    boss_technology_points: int | None = None


@dataclass(frozen=True, kw_only=True)
class UpdatePlayerAttributes(SessionCommand):
    player_id: str
    values: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class UpdatePlayerTechnology(SessionCommand):
    player_id: str
    recipe_id: str | None = None
    unlocked: bool | None = None
    unlock_all: bool = False


@dataclass(frozen=True, kw_only=True)
class UpdatePlayerMissions(SessionCommand):
    player_id: str
    operation: Literal[
        "mark_completed",
        "reset_to_unaccepted",
        "restart_from_beginning",
        "complete_tracked",
        "complete_all_in_progress",
        "complete_all",
        "reset_all_completed",
    ]
    mission_ids: tuple[str, ...] = ()
    preview_token: str | None = None


@dataclass(frozen=True, kw_only=True)
class UpdatePalIdentity(SessionCommand):
    pal_id: str
    name: str | None = None
    gender: str | None = None
    variant: str | None = None
    boss: bool | None = None
    tower: bool | None = None
    rare: bool | None = None


@dataclass(frozen=True, kw_only=True)
class UpdatePalProgression(SessionCommand):
    pal_id: str
    values: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class UpdatePalSkills(SessionCommand):
    pal_id: str
    active: tuple[str, ...] | None = None
    mastered: tuple[str, ...] | None = None
    passive: tuple[str, ...] | None = None
    allow_custom_passive: bool = False


@dataclass(frozen=True, kw_only=True)
class UpdatePalEnhancement(SessionCommand):
    pal_id: str
    values: dict[str, int | bool] = field(default_factory=dict)
    work_suitability: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class MaxPal(SessionCommand):
    pal_id: str
    unrestricted: bool = False


@dataclass(frozen=True, kw_only=True)
class UnlockPalExpedition(SessionCommand):
    pal_id: str


@dataclass(frozen=True, kw_only=True)
class UnlockAllExpeditionPals(SessionCommand):
    pass


@dataclass(frozen=True, kw_only=True)
class HealAllPals(SessionCommand):
    pass


@dataclass(frozen=True, kw_only=True)
class CompleteActiveExpeditions(SessionCommand):
    pass


@dataclass(frozen=True, kw_only=True)
class CompleteExpedition(SessionCommand):
    expedition_id: str


@dataclass(frozen=True, kw_only=True)
class AddPal(SessionCommand):
    player_id: str
    species_id: str
    container_type: CharacterContainerType = CharacterContainerType.AUTO
    target_slot: int | None = None
    passive: tuple[str, ...] | None = None
    max_pal: bool = False
    max_work: bool = False
    unrestricted: bool = False


@dataclass(frozen=True, kw_only=True)
class ClonePal(SessionCommand):
    source_pal_id: str
    target_player_id: str
    container_type: CharacterContainerType = CharacterContainerType.AUTO
    target_slot: int | None = None
    impact_token: str | None = None


@dataclass(frozen=True, kw_only=True)
class MovePal(SessionCommand):
    pal_id: str
    target_player_id: str
    container_type: CharacterContainerType = CharacterContainerType.AUTO
    target_slot: int | None = None
    impact_token: str | None = None


@dataclass(frozen=True, kw_only=True)
class DeletePal(SessionCommand):
    pal_id: str
    impact_token: str


@dataclass(frozen=True, kw_only=True)
class RecoverDetachedPal(SessionCommand):
    pal_id: str
    target_player_id: str
    container_type: CharacterContainerType = CharacterContainerType.AUTO
    target_slot: int | None = None
