from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest

from palworld_pal_editor.application.query_service import SaveQueryService
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.core.basecamp_data import BaseCampData
from palworld_pal_editor.core.group_data import GroupData
from palworld_pal_editor.core.pal_objects import PalObjects, toUUID
from palworld_pal_editor.core.save_manager import SaveManager


GUILD_ID = toUUID("11111111-1111-1111-1111-111111111111")
INDEPENDENT_ID = toUUID("22222222-2222-2222-2222-222222222222")
UNKNOWN_ID = toUUID("33333333-3333-3333-3333-333333333333")
BASE_ONE_ID = toUUID("44444444-4444-4444-4444-444444444444")
BASE_TWO_ID = toUUID("55555555-5555-5555-5555-555555555555")
CONTAINER_ONE_ID = toUUID("66666666-6666-6666-6666-666666666666")
CONTAINER_TWO_ID = toUUID("77777777-7777-7777-7777-777777777777")
BASE_THREE_ID = toUUID("88888888-8888-8888-8888-888888888888")
BASE_FOUR_ID = toUUID("99999999-9999-9999-9999-999999999999")
BASE_FIVE_ID = toUUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


class StubGroupData:
    def __init__(self, groups):
        self._groups = groups

    def get_groups(self):
        return list(self._groups)


class StubCampData:
    def __init__(self, camps):
        self._camps = camps
        self._map = {str(camp.id): camp for camp in camps}

    def get_camps(self):
        return list(self._camps)

    def get_camp(self, camp_id):
        return self._map.get(str(camp_id))


def player(player_id: str, name: str, group_id, level: int = 1):
    return SimpleNamespace(
        PlayerUId=player_id,
        InstanceId=f"instance-{player_id}",
        NickName=name,
        Level=level,
        group_id=group_id,
        _palbox={},
        is_loaded=False,
    )


def worker(worker_id: str, group_id, container_id):
    return SimpleNamespace(
        InstanceId=worker_id,
        group_id=group_id,
        ContainerId=container_id,
        SlotIndex=0,
        CharacterID="SheepBall",
        DataAccessKey="SheepBall",
        DisplayName="Lamball",
        CustomNickName="",
        IconAccessKey="SheepBall",
        PalDeckID="001",
        Level=1,
        Gender=SimpleNamespace(value="EPalGenderType::Female"),
        IsBOSS=False,
        IsRarePal=False,
        IsTower=False,
        HasWorkerSick=False,
        IsFaintedPal=False,
        PassiveSkillList=[],
        WorkSuitabilities={
            "EPalWorkSuitability::Handcraft": 1,
            "EPalWorkSuitability::Transport": 1,
        },
    )


class GuildTreeTests(unittest.TestCase):
    def test_independent_guild_is_indexed_as_a_real_group(self) -> None:
        independent = {
            "key": INDEPENDENT_ID,
            "value": {
                "GroupType": PalObjects.EnumProperty(
                    "EPalGroupType", "EPalGroupType::IndependentGuild"
                ),
                "RawData": PalObjects.ArrayProperty(
                    "ByteProperty",
                    {
                        "group_id": INDEPENDENT_ID,
                        "guild_name": "Solo Guild",
                        "player_uid": "solo-player",
                        "player_info": {"player_name": "Solo"},
                        "individual_character_handle_ids": [],
                    },
                ),
            },
        }
        gvas = SimpleNamespace(
            properties={
                "worldSaveData": {
                    "value": {"GroupSaveDataMap": {"value": [independent]}}
                }
            }
        )

        groups = GroupData(gvas)

        group = groups.get_group(INDEPENDENT_ID)
        self.assertEqual("EPalGroupType::IndependentGuild", group.group_type)
        self.assertEqual([("solo-player", "Solo")], group.players)

    def test_empty_guild_is_preserved_for_guild_management(self) -> None:
        empty_guild = {
            "key": GUILD_ID,
            "value": {
                "GroupType": PalObjects.EnumProperty(
                    "EPalGroupType", "EPalGroupType::Guild"
                ),
                "RawData": PalObjects.ArrayProperty(
                    "ByteProperty",
                    {
                        "group_id": GUILD_ID,
                        "guild_name": "Empty Guild",
                        "players": [],
                        "base_ids": [],
                        "individual_character_handle_ids": [],
                    },
                ),
            },
        }
        gvas = SimpleNamespace(
            properties={
                "worldSaveData": {
                    "value": {"GroupSaveDataMap": {"value": [empty_guild]}}
                }
            }
        )

        groups = GroupData(gvas)

        group = groups.get_group(GUILD_ID)
        self.assertEqual("Empty Guild", group.guild_name)
        self.assertEqual([], group.players)
        self.assertEqual([], group.base_ids)

    def test_base_camp_reads_worker_container_from_worker_director(self) -> None:
        camp = {
            "key": BASE_ONE_ID,
            "value": {
                "RawData": {
                    "value": {
                        "id": BASE_ONE_ID,
                        "name": "Snow Base",
                        "group_id_belong_to": GUILD_ID,
                    }
                },
                "WorkerDirector": {
                    "RawData": {"value": {"container_id": CONTAINER_ONE_ID}}
                },
            },
        }
        gvas = SimpleNamespace(
            properties={
                "worldSaveData": {
                    "value": {"BaseCampSaveData": {"value": [camp]}}
                }
            }
        )

        base = BaseCampData(gvas).get_camp(BASE_ONE_ID)

        self.assertEqual(CONTAINER_ONE_ID, base.container_id)
        self.assertEqual(GUILD_ID, base.owner_group_id)

    def test_wrapped_worker_director_keeps_workers_in_five_real_bases(self) -> None:
        base_ids = [
            BASE_ONE_ID,
            BASE_TWO_ID,
            BASE_THREE_ID,
            BASE_FOUR_ID,
            BASE_FIVE_ID,
        ]
        container_ids = [
            CONTAINER_ONE_ID,
            CONTAINER_TWO_ID,
            toUUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            toUUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
            toUUID("dddddddd-dddd-dddd-dddd-dddddddddddd"),
        ]
        camps = [
            {
                "key": base_id,
                "value": {
                    "RawData": {
                        "value": {
                            "id": base_id,
                            "name": f"Base {index + 1}",
                            "group_id_belong_to": GUILD_ID,
                        }
                    },
                    "WorkerDirector": {
                        "value": {
                            "RawData": {
                                "value": {"container_id": container_ids[index]}
                            }
                        }
                    },
                },
            }
            for index, base_id in enumerate(base_ids)
        ]
        gvas = SimpleNamespace(
            properties={
                "worldSaveData": {
                    "value": {"BaseCampSaveData": {"value": camps}}
                }
            }
        )
        guild = SimpleNamespace(
            group_id=GUILD_ID,
            group_type="EPalGroupType::Guild",
            guild_name="Builders",
            base_ids=base_ids,
        )
        workers = {
            f"worker-{index}": worker(
                f"worker-{index}", GUILD_ID, CONTAINER_TWO_ID
            )
            for index in range(7)
        }
        manager = SimpleNamespace(
            gvas_file=gvas,
            player_mapping={},
            baseworker_mapping=workers,
            group_data=StubGroupData([guild]),
            camp_data=BaseCampData(gvas),
        )
        session = SaveSession.from_loaded_manager(manager, Path("synthetic-save"))

        tree = SaveQueryService(session).guild_tree()

        self.assertEqual(1, len(tree))
        self.assertEqual(5, tree[0]["base_count"])
        self.assertEqual(5, len(tree[0]["bases"]))
        self.assertEqual(
            [0, 7, 0, 0, 0],
            [base["worker_count"] for base in tree[0]["bases"]],
        )
        self.assertNotIn("unmatched", [base["kind"] for base in tree[0]["bases"]])

    def test_tree_groups_members_and_workers_by_guild_and_base(self) -> None:
        guild = SimpleNamespace(
            group_id=GUILD_ID,
            group_type="EPalGroupType::Guild",
            guild_name="Builders",
            base_ids=[BASE_TWO_ID, BASE_ONE_ID],
        )
        independent = SimpleNamespace(
            group_id=INDEPENDENT_ID,
            group_type="EPalGroupType::IndependentGuild",
            guild_name="Solo Guild",
            base_ids=[],
        )
        camps = [
            SimpleNamespace(
                id=BASE_ONE_ID,
                name="Snow Base",
                owner_group_id=GUILD_ID,
                container_id=CONTAINER_ONE_ID,
            ),
            SimpleNamespace(
                id=BASE_TWO_ID,
                name="Volcano Base",
                owner_group_id=GUILD_ID,
                container_id=CONTAINER_TWO_ID,
            ),
        ]
        players = {
            "guild-player": player("guild-player", "Builder", GUILD_ID, 50),
            "solo-player": player("solo-player", "Solo", INDEPENDENT_ID, 40),
            "unknown-player": player("unknown-player", "Unknown", None, 30),
            "no-guild-player": player("no-guild-player", "No Guild", None, 20),
        }
        players["unknown-player"]._unresolved_group_id = UNKNOWN_ID
        workers = {
            "base-one-worker": worker(
                "base-one-worker", GUILD_ID, CONTAINER_ONE_ID
            ),
            "unmatched-worker": worker(
                "unmatched-worker", GUILD_ID, "missing-container"
            ),
        }
        manager = SimpleNamespace(
            gvas_file=SimpleNamespace(properties={}),
            player_mapping=players,
            baseworker_mapping=workers,
            group_data=StubGroupData([guild, independent]),
            camp_data=StubCampData(camps),
            guild_item_storage_data=SimpleNamespace(
                get=lambda group_id: (
                    SimpleNamespace(container_id="guild-chest-container")
                    if str(group_id) == str(GUILD_ID)
                    else None
                )
            ),
            guild_item_storage_error=None,
            item_container_data=SimpleNamespace(
                get=lambda container_id: (
                    SimpleNamespace(capacity=90)
                    if container_id == "guild-chest-container"
                    else None
                )
            ),
        )
        session = SaveSession.from_loaded_manager(manager, Path("synthetic-save"))

        tree = SaveQueryService(session).guild_tree()

        builders = next(node for node in tree if node["guild_id"] == str(GUILD_ID))
        self.assertEqual([str(BASE_TWO_ID), str(BASE_ONE_ID), None], [
            base["base_id"] for base in builders["bases"]
        ])
        self.assertEqual([0, 1, 1], [
            base["worker_count"] for base in builders["bases"]
        ])
        self.assertEqual("unmatched", builders["bases"][-1]["kind"])
        self.assertEqual("available", builders["guild_chest_status"])
        self.assertEqual(90, builders["guild_chest_capacity"])
        self.assertEqual("independent", tree[1]["kind"])
        self.assertEqual("missing", tree[1]["guild_chest_status"])
        self.assertIsNone(tree[1]["guild_chest_capacity"])
        self.assertEqual("unknown", tree[2]["kind"])
        self.assertEqual("no_guild", tree[3]["kind"])

        isolated = SaveManager.create_isolated()
        isolated.baseworker_mapping = workers
        isolated.camp_data = manager.camp_data
        self.assertEqual(
            ["base-one-worker"],
            [
                pal.InstanceId
                for pal in isolated.get_working_pals(base_id=BASE_ONE_ID)
            ],
        )
        self.assertEqual(
            ["unmatched-worker"],
            [
                pal.InstanceId
                for pal in isolated.get_working_pals(
                    group_id=GUILD_ID, unmatched_base=True
                )
            ],
        )

    def test_guild_query_keeps_saved_members_and_missing_base_references(self) -> None:
        missing_base_id = toUUID(
            "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
        )
        guild = SimpleNamespace(
            group_id=GUILD_ID,
            group_type="EPalGroupType::Guild",
            guild_name="Builders",
            base_ids=[BASE_ONE_ID, missing_base_id],
            base_camp_level=14,
            players=[
                (toUUID("abababab-abab-abab-abab-abababababab"), "Offline"),
            ],
            _group_param={"guild_name": "Builders"},
        )
        camp = SimpleNamespace(
            id=BASE_ONE_ID,
            name="Snow Base",
            owner_group_id=GUILD_ID,
            container_id=CONTAINER_ONE_ID,
        )
        worker_container = SimpleNamespace(size=30, slots=[object(), object()])
        manager = SimpleNamespace(
            gvas_file=SimpleNamespace(properties={}),
            player_mapping={},
            baseworker_mapping={
                "worker-one": worker(
                    "worker-one", GUILD_ID, CONTAINER_ONE_ID
                ),
                "worker-two": worker(
                    "worker-two", GUILD_ID, CONTAINER_ONE_ID
                ),
            },
            group_data=StubGroupData([guild]),
            camp_data=StubCampData([camp]),
            container_data=SimpleNamespace(
                get_container=lambda container_id: (
                    worker_container
                    if str(container_id) == str(CONTAINER_ONE_ID)
                    else None
                )
            ),
            guild_item_storage_data=None,
            guild_item_storage_error=None,
            item_container_data=None,
        )
        session = SaveSession.from_loaded_manager(manager, Path("synthetic-save"))

        rows = SaveQueryService(session).guilds()

        self.assertEqual(1, len(rows))
        self.assertEqual(14, rows[0]["base_camp_level"])
        self.assertEqual("available", rows[0]["base_camp_level_status"])
        self.assertEqual("Offline", rows[0]["members"][0]["name"])
        self.assertIsNone(rows[0]["members"][0]["level"])
        self.assertEqual(2, rows[0]["base_count"])
        self.assertEqual(30, rows[0]["bases"][0]["worker_capacity"])
        self.assertEqual(2, rows[0]["bases"][0]["worker_count"])
        self.assertEqual(
            ["worker-one", "worker-two"],
            [
                worker["pal_id"]
                for worker in rows[0]["bases"][0]["workers"]
            ],
        )
        worker_row = rows[0]["bases"][0]["workers"][0]
        self.assertEqual("Lamball", worker_row["name"])
        self.assertEqual("SheepBall", worker_row["icon_access_key"])
        self.assertEqual("EPalGenderType::Female", worker_row["gender"])
        self.assertEqual(
            {"EPalWorkSuitability::Handcraft": 1,
             "EPalWorkSuitability::Transport": 1},
            worker_row["work_suitabilities"],
        )
        self.assertEqual("missing", rows[0]["bases"][1]["kind"])
        self.assertEqual([], rows[0]["bases"][1]["workers"])
        self.assertEqual(
            "base_missing",
            rows[0]["bases"][1]["worker_capacity_status"],
        )


if __name__ == "__main__":
    unittest.main()
