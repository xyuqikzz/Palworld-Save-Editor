from __future__ import annotations

from dataclasses import dataclass


ARENA_NPC_SOURCE_BUILD = 24_088_745
ARENA_WORLD_RANKING_LIMIT = 100

# Extracted from the shipped build 24088745 data table:
# /Game/Pal/DataTable/Arena/DT_ArenaNPCDataTable
_ARENA_NPC_NAME_TEXT_IDS = (
    "NAME_DarkTrader",
    "NAME_Female_Presenter01",
    "NAME_PalPassive_Doctor",
    "NAME_BattlePaltamer006",
    "NAME_MedalTrader",
    "NAME_Male_Soldier02_Invader",
    "NAME_Ninja",
    "NAME_Viking_Elite",
    "NAME_QUEST_SCHOLAR01",
    "NAME_Reward_BossDefeat",
    "PvPVillage002",
    "NAME_BattlePaltamer006",
    "NAME_BattlePaltamer004",
    "PvPVillage003",
    "NAME_BattlePaltamer006",
    "NAME_BattlePaltamer004",
    "NAME_Reward_PalCaptureCount",
    "NAME_BattlePaltamer006",
    "NAME_BattlePaltamer004",
    "SKILLED_PALTAMIER",
    "NAME_Female_Soldier03_Invader",
    "NAME_Female_Soldier03_Invader",
    "Head_of_Village",
    "NAME_BattlePaltamer006",
    "NAME_BattlePaltamer004",
    "NAME_BattlePaltamer005",
    "NAME_Solider",
    "NAME_HUNTER_BOSS",
    "NAME_Viking",
    "NAME_Ninja",
    "NAME_Labmen",
    "NAME_FireCult",
    "NAME_QUEST_RANGER04",
    "NAME_Reward_Emote",
    "NAME_Reward_Paldex",
    "NAME_Recruiter",
    "NAME_BattlePaltamer005",
    "NAME_BattlePaltamer004",
    "NAME_CaravanLeader01",
    "NAME_BattlePaltamer005",
    "NAME_BattlePaltamer004",
    "NAME_PAL_DEALER",
    "NAME_BattlePaltamer005",
    "NAME_BattlePaltamer004",
    "InnkeeperA",
    "NAME_BattlePaltamer005",
    "NAME_BattlePaltamer004",
    "Yamishima_guide5",
    "NAME_BattlePaltamer005",
    "NAME_HUNTER",
    "NAME_BattlePaltamer004",
    "NAME_BattlePaltamer003",
    "NAME_HUNTER",
    "NAME_BattlePaltamer004",
    "NAME_BattlePaltamer003",
    "NAME_HUNTER",
    "NAME_BattlePaltamer004",
    "NAME_BattlePaltamer003",
    "NAME_HUNTER",
    "NAME_BattlePaltamer004",
    "NAME_BattlePaltamer003",
    "NAME_HUNTER",
    "NAME_BattlePaltamer004",
    "NAME_BattlePaltamer003",
    "NAME_HUNTER",
    "NAME_BattlePaltamer004",
    "NAME_BattlePaltamer003",
    "NAME_HUNTER",
    "NAME_BattlePaltamer004",
    "NAME_HUNTER",
    "NAME_BattlePaltamer003",
    "NAME_BattlePaltamer002",
    "NAME_HUNTER",
    "NAME_BattlePaltamer003",
    "NAME_BattlePaltamer002",
    "NAME_HUNTER",
    "NAME_BattlePaltamer003",
    "NAME_BattlePaltamer002",
    "NAME_HUNTER",
    "NAME_BattlePaltamer003",
    "NAME_BattlePaltamer002",
    "NAME_HUNTER",
    "NAME_BattlePaltamer003",
    "NAME_BattlePaltamer002",
    "NAME_HUNTER",
    "NAME_BattlePaltamer002",
    "NAME_BattlePaltamer001",
    "NAME_HUNTER",
    "NAME_BattlePaltamer002",
    "NAME_BattlePaltamer001",
    "NAME_HUNTER",
    "NAME_BattlePaltamer002",
    "NAME_BattlePaltamer001",
    "NAME_HUNTER",
    "NAME_BattlePaltamer002",
    "NAME_BattlePaltamer001",
    "NAME_HUNTER",
    "NAME_BattlePaltamer001",
    "NAME_HUNTER",
    "NAME_BattlePaltamer001",
)


@dataclass(frozen=True)
class ArenaNpcRanking:
    ranking_npc_id: str
    name_text_id: str
    rank_point: int


ARENA_NPC_RANKINGS = tuple(
    ArenaNpcRanking(
        ranking_npc_id=f"Ranking{index}",
        name_text_id=name_text_id,
        rank_point=5_050 - index * 50,
    )
    for index, name_text_id in enumerate(_ARENA_NPC_NAME_TEXT_IDS, start=1)
)
