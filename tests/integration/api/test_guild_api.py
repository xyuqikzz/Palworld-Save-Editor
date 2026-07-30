from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from palworld_pal_editor.api.save import save_blueprint
from palworld_pal_editor.application.runtime import SESSION_RUNTIME
from palworld_pal_editor.application.save_session import SaveSession
from palworld_pal_editor.core.base_storage_data import BaseStorageBinding
from palworld_pal_editor.core.group_data import PalGroup
from palworld_pal_editor.core.item_container_data import ItemContainerData
from palworld_pal_editor.core.pal_objects import PalObjects, toUUID


GUILD_ID = toUUID("11111111-1111-1111-1111-111111111111")
CHEST_CONTAINER_ID = toUUID("22222222-2222-2222-2222-222222222222")
BASE_ID = toUUID("33333333-3333-3333-3333-333333333333")
WORKER_CONTAINER_ID = toUUID("44444444-4444-4444-4444-444444444444")
OWNER_ID = toUUID("aaaaaaaa-1111-2222-3333-444444444444")
MEMBER_ID = toUUID("bbbbbbbb-1111-2222-3333-444444444444")
BASE_STORAGE_CONTAINER_ID = toUUID(
    "55555555-5555-5555-5555-555555555555"
)
BASE_STORAGE_OBJECT_ID = toUUID(
    "66666666-6666-6666-6666-666666666666"
)
ZERO_ID = toUUID("00000000-0000-0000-0000-000000000000")


class _Groups:
    def __init__(self, group: PalGroup) -> None:
        self.group = group

    def get_group(self, group_id):
        return self.group if str(group_id) == str(self.group.group_id) else None

    def get_groups(self):
        return [self.group]


class _GuildChestContainer:
    def __init__(self) -> None:
        self.capacity = 54

    def snapshot_capacity(self) -> int:
        return self.capacity

    def restore_capacity(self, capacity: int) -> None:
        self.capacity = capacity

    def expand_capacity(self, capacity: int) -> None:
        if capacity < self.capacity:
            raise ValueError("cannot shrink")
        self.capacity = capacity


class _WorkerContainer:
    def __init__(self) -> None:
        self.size = 14
        self.slots = []

    def snapshot_capacity(self) -> int:
        return self.size

    def restore_capacity(self, capacity: int) -> None:
        self.size = capacity

    def expand_capacity(self, capacity: int) -> None:
        if capacity < self.size:
            raise ValueError("cannot shrink")
        self.size = capacity

    def capacity_matches_declared(self, capacity: int) -> bool:
        return self.size == capacity


def _base_storage_item_data() -> ItemContainerData:
    slot = {
        "RawData": {
            "value": {
                "slot_index": 0,
                "count": 5,
                "item": {
                    "static_id": "Stone",
                    "dynamic_id": {
                        "created_world_id": ZERO_ID,
                        "local_id_in_created_world": ZERO_ID,
                    },
                },
                "permission": {
                    "type_a": [],
                    "type_b": [],
                    "item_static_ids": [],
                },
                "corruption_progress_value": 0.0,
                "trailing_bytes": [0, 0, 0, 0],
            }
        }
    }
    gvas = SimpleNamespace(
        properties={
            "worldSaveData": {
                "value": {
                    "ItemContainerSaveData": {
                        "value": [
                            {
                                "key": {
                                    "ID": PalObjects.Guid(
                                        BASE_STORAGE_CONTAINER_ID
                                    )
                                },
                                "value": {
                                    "SlotNum": PalObjects.IntProperty(1),
                                    "Slots": {
                                        "value": {"values": [slot]}
                                    },
                                },
                            }
                        ]
                    }
                }
            }
        }
    )
    return ItemContainerData(gvas)


class GuildApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.group = PalGroup(
            {
                "value": {
                    "RawData": {
                        "value": {
                            "group_id": GUILD_ID,
                            "group_name": "Guild",
                            "guild_name": "Builders",
                            "individual_character_handle_ids": [],
                            "base_ids": [BASE_ID],
                            "base_camp_level": 14,
                            "guild_format": "1.0",
                            "admin_player_uid": OWNER_ID,
                            "players": [
                                {
                                    "player_uid": MEMBER_ID,
                                    "player_info": {
                                        "last_online_real_time": 5,
                                        "player_name": "Member",
                                        "role": 3,
                                    },
                                },
                                {
                                    "player_uid": OWNER_ID,
                                    "player_info": {
                                        "last_online_real_time": 10,
                                        "player_name": "Owner",
                                        "role": 1,
                                    },
                                },
                            ],
                        }
                    }
                }
            },
            "EPalGroupType::Guild",
        )
        self.guild_chest = _GuildChestContainer()
        self.base_storage_items = _base_storage_item_data()
        self.base_storage = self.base_storage_items.get(
            BASE_STORAGE_CONTAINER_ID
        )
        self.base_storage_binding = BaseStorageBinding(
            guild_id=GUILD_ID,
            base_id=BASE_ID,
            map_object_instance_id=BASE_STORAGE_OBJECT_ID,
            map_object_type="ItemChest",
            container_id=BASE_STORAGE_CONTAINER_ID,
            usage_type=1,
            location={"x": 1.0, "y": 2.0, "z": 3.0},
        )
        self.worker_container = _WorkerContainer()
        self.camp = SimpleNamespace(
            id=BASE_ID,
            name="Snow Base",
            owner_group_id=GUILD_ID,
            container_id=WORKER_CONTAINER_ID,
        )
        self.worker = SimpleNamespace(
            InstanceId="worker-one",
            group_id=GUILD_ID,
            ContainerId=WORKER_CONTAINER_ID,
            SlotIndex=0,
            CharacterID="SheepBall",
            DataAccessKey="SheepBall",
            DisplayName="Lamball",
            CustomNickName="Builder",
            IconAccessKey="SheepBall",
            Level=12,
            Gender=SimpleNamespace(value="EPalGenderType::Male"),
            IsBOSS=False,
            IsRarePal=False,
            IsTower=False,
            HasWorkerSick=False,
            IsFaintedPal=False,
            PassiveSkillList=["CraftSpeed_up1"],
            WorkSuitabilities={"EPalWorkSuitability::Handcraft": 2},
        )
        manager = SimpleNamespace(
            gvas_file=SimpleNamespace(properties={}, header=None),
            group_data=_Groups(self.group),
            player_mapping={},
            baseworker_mapping={"worker-one": self.worker},
            camp_data=SimpleNamespace(
                get_camp=lambda base_id: (
                    self.camp if str(base_id) == str(BASE_ID) else None
                ),
                get_camps=lambda: [self.camp],
            ),
            container_data=SimpleNamespace(
                get_container=lambda container_id: (
                    self.worker_container
                    if str(container_id) == str(WORKER_CONTAINER_ID)
                    else None
                )
            ),
            guild_item_storage_data=SimpleNamespace(
                get=lambda group_id: (
                    SimpleNamespace(container_id=CHEST_CONTAINER_ID)
                    if str(group_id) == str(GUILD_ID)
                    else None
                )
            ),
            guild_item_storage_error=None,
            base_storage_data=SimpleNamespace(
                complete=True,
                issues=lambda: (),
                get_base=lambda guild_id, base_id: (
                    (self.base_storage_binding,)
                    if (
                        str(guild_id) == str(GUILD_ID)
                        and str(base_id) == str(BASE_ID)
                    )
                    else ()
                ),
                resolve=lambda guild_id, base_id, container_id: (
                    self.base_storage_binding
                    if (
                        str(guild_id) == str(GUILD_ID)
                        and str(base_id) == str(BASE_ID)
                        and str(container_id)
                        == str(BASE_STORAGE_CONTAINER_ID)
                    )
                    else None
                ),
            ),
            base_storage_error=None,
            item_container_data=SimpleNamespace(
                get=lambda container_id: (
                    self.guild_chest
                    if str(container_id) == str(CHEST_CONTAINER_ID)
                    else (
                        self.base_storage
                        if str(container_id)
                        == str(BASE_STORAGE_CONTAINER_ID)
                        else None
                    )
                )
            ),
        )
        self.session = SaveSession.from_loaded_manager(manager, Path("synthetic-save"))
        SESSION_RUNTIME.replace_for_tests(self.session)

        app = Flask(__name__)
        app.config.update(
            JWT_SECRET_KEY="test-secret-key-that-is-at-least-32-bytes",
            TESTING=True,
        )
        JWTManager(app)
        app.register_blueprint(save_blueprint, url_prefix="/api/save")
        with app.app_context():
            token = create_access_token(identity="test-user")
        self.client = app.test_client()
        self.headers = {"Authorization": f"Bearer {token}"}

    def tearDown(self) -> None:
        SESSION_RUNTIME.replace_for_tests(None)

    def test_update_guild_name_uses_session_revision_contract(self) -> None:
        response = self.client.post(
            f"/api/save/guilds/{GUILD_ID}/commands",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 0,
                "command": "update_guild_name",
                "name": "API Builders",
            },
        )

        self.assertEqual(200, response.status_code, response.get_json())
        payload = response.get_json()["data"]
        self.assertEqual(1, payload["revision"])
        self.assertEqual("API Builders", payload["value"]["name"])
        self.assertEqual("API Builders", self.group.guild_name)

        stale = self.client.post(
            f"/api/save/guilds/{GUILD_ID}/commands",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 0,
                "command": "update_guild_name",
                "name": "Stale Name",
            },
        )
        self.assertEqual(409, stale.status_code)
        self.assertEqual("STALE_REVISION", stale.get_json()["error"]["code"])
        self.assertEqual("API Builders", self.group.guild_name)

    def test_expand_guild_chest_capacity_uses_session_revision_contract(self) -> None:
        response = self.client.post(
            f"/api/save/guilds/{GUILD_ID}/commands",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 0,
                "command": "update_guild_chest_capacity",
                "capacity": 90,
            },
        )

        self.assertEqual(200, response.status_code, response.get_json())
        payload = response.get_json()["data"]
        self.assertEqual(1, payload["revision"])
        self.assertEqual(90, payload["value"]["capacity"])
        self.assertEqual(90, self.guild_chest.capacity)

        stale = self.client.post(
            f"/api/save/guilds/{GUILD_ID}/commands",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 0,
                "command": "update_guild_chest_capacity",
                "capacity": 120,
            },
        )
        self.assertEqual(409, stale.status_code)
        self.assertEqual("STALE_REVISION", stale.get_json()["error"]["code"])
        self.assertEqual(90, self.guild_chest.capacity)

    def test_update_guild_owner_uses_session_revision_contract(self) -> None:
        response = self.client.post(
            f"/api/save/guilds/{GUILD_ID}/commands",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 0,
                "command": "update_guild_owner",
                "player_id": str(MEMBER_ID),
            },
        )

        self.assertEqual(200, response.status_code, response.get_json())
        payload = response.get_json()["data"]
        self.assertEqual(1, payload["revision"])
        self.assertEqual(
            str(MEMBER_ID), payload["value"]["owner_player_id"]
        )
        self.assertEqual(str(MEMBER_ID), str(self.group.admin_player_uid))
        self.assertEqual(
            {
                str(OWNER_ID): 2,
                str(MEMBER_ID): 1,
            },
            {
                str(player_uid): role
                for player_uid, _name, role in self.group.guild_members
            },
        )

    def test_query_guilds_returns_all_saved_guild_details(self) -> None:
        response = self.client.get(
            f"/api/save/query/guilds?session_id={self.session.session_id}",
            headers=self.headers,
        )

        self.assertEqual(200, response.status_code, response.get_json())
        guild = response.get_json()["data"]["guilds"][0]
        self.assertEqual(str(GUILD_ID), guild["guild_id"])
        self.assertEqual(14, guild["base_camp_level"])
        self.assertEqual(1, guild["base_count"])
        self.assertEqual(14, guild["bases"][0]["worker_capacity"])
        self.assertEqual(1, guild["bases"][0]["worker_count"])
        self.assertEqual("worker-one", guild["bases"][0]["workers"][0]["pal_id"])
        self.assertEqual(12, guild["bases"][0]["workers"][0]["level"])
        self.assertEqual(
            ["CraftSpeed_up1"],
            guild["bases"][0]["workers"][0]["passive_skills"],
        )
        self.assertEqual(str(OWNER_ID), guild["owner_player_id"])
        self.assertTrue(guild["owner_editable"])
        self.assertEqual(
            [str(OWNER_ID), str(MEMBER_ID)],
            [member["player_id"] for member in guild["members"]],
        )
        self.assertEqual(
            [1, 3],
            [member["role"] for member in guild["members"]],
        )

    def test_terminal_level_uses_revision_contract(self) -> None:
        level_response = self.client.post(
            f"/api/save/guilds/{GUILD_ID}/commands",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 0,
                "command": "update_base_camp_level",
                "level": 35,
            },
        )

        self.assertEqual(
            200, level_response.status_code, level_response.get_json()
        )
        self.assertEqual(35, self.group.base_camp_level)

    def test_worker_capacity_command_is_not_supported(self) -> None:
        response = self.client.post(
            f"/api/save/guilds/{GUILD_ID}/commands",
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 0,
                "command": "update_base_worker_capacity",
                "base_id": str(BASE_ID),
                "capacity": 60,
            },
        )

        self.assertEqual(
            400, response.status_code, response.get_json()
        )
        self.assertEqual(
            "UNSUPPORTED_COMMAND", response.get_json()["error"]["code"]
        )
        self.assertEqual(14, self.worker_container.size)
        self.assertEqual(0, self.session.revision)

    def test_base_storage_query_and_count_update_use_exact_scope(self) -> None:
        query = self.client.get(
            (
                f"/api/save/guilds/{GUILD_ID}/bases/{BASE_ID}/storage"
                f"?session_id={self.session.session_id}"
            ),
            headers=self.headers,
        )

        self.assertEqual(200, query.status_code, query.get_json())
        data = query.get_json()["data"]
        self.assertEqual("available", data["status"])
        self.assertEqual(
            str(BASE_STORAGE_CONTAINER_ID),
            data["containers"][0]["container_id"],
        )
        self.assertEqual(
            "Stone",
            data["containers"][0]["slots"][0]["item"]["static_id"],
        )

        update = self.client.post(
            (
                f"/api/save/guilds/{GUILD_ID}/bases/{BASE_ID}"
                "/storage/commands"
            ),
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 0,
                "command": "update_item_count",
                "container_id": str(BASE_STORAGE_CONTAINER_ID),
                "slot_index": 0,
                "expected_static_id": "Stone",
                "count": 9,
            },
        )

        self.assertEqual(200, update.status_code, update.get_json())
        self.assertEqual(1, update.get_json()["data"]["revision"])
        self.assertEqual(9, self.base_storage.get_occupied(0).count)
        change = self.session.changes()[0]
        self.assertEqual("UpdateBaseStorageItemCount", change["command"])
        self.assertEqual(str(BASE_ID), change["target"]["base_id"])

    def test_base_storage_rejects_arbitrary_container_and_fields(self) -> None:
        url = (
            f"/api/save/guilds/{GUILD_ID}/bases/{BASE_ID}"
            "/storage/commands"
        )
        response = self.client.post(
            url,
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 0,
                "command": "update_item_count",
                "container_id": str(CHEST_CONTAINER_ID),
                "slot_index": 0,
                "expected_static_id": "Stone",
                "count": 9,
            },
        )
        self.assertEqual(409, response.status_code, response.get_json())
        self.assertEqual(
            "BASE_STORAGE_OWNERSHIP_VIOLATION",
            response.get_json()["error"]["code"],
        )

        unknown = self.client.post(
            url,
            headers=self.headers,
            json={
                "session_id": self.session.session_id,
                "expected_revision": 0,
                "command": "update_item_count",
                "container_id": str(BASE_STORAGE_CONTAINER_ID),
                "slot_index": 0,
                "expected_static_id": "Stone",
                "count": 9,
                "raw_path": "not-allowed",
            },
        )
        self.assertEqual(400, unknown.status_code, unknown.get_json())
        self.assertEqual(
            "UNSUPPORTED_COMMAND_FIELD",
            unknown.get_json()["error"]["code"],
        )


if __name__ == "__main__":
    unittest.main()
