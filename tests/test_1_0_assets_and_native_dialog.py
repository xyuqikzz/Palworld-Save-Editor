from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import webview


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = PROJECT_ROOT / "src" / "palworld_pal_editor"
ASSET_ROOT = PACKAGE_ROOT / "assets"
SUPPORTED_LANGUAGES = ("en", "fr", "ja", "ko", "zh-CN")
TOOLS_ROOT = ASSET_ROOT / "tools"
sys.path.insert(0, str(TOOLS_ROOT))

from sync_1_0_pal_assets import PalRecord, build_human_catalog  # noqa: E402


class TechnologyAssetTests(unittest.TestCase):
    def test_official_1_0_technology_assets_are_complete(self) -> None:
        data = json.loads(
            (ASSET_ROOT / "data" / "tech_data.json").read_text(encoding="utf-8")
        )

        self.assertEqual(588, len(data))
        self.assertEqual(80, max(row["Level"] for row in data.values()))
        self.assertEqual(66, data["AncientBlastFurnace"]["Level"])
        self.assertEqual(80, data["BeamLauncher"]["Level"])
        self.assertEqual("원시적인 작업대", data["Workbench"]["I18n"]["ko"]["Name"])

        for internal_name, row in data.items():
            for language in SUPPORTED_LANGUAGES:
                localized = row["I18n"][language]
                self.assertTrue(localized["Name"], (internal_name, language))
                self.assertTrue(localized["Type"], (internal_name, language))

            if internal_name.startswith("SkillUnlock_"):
                icon = ASSET_ROOT / "icons" / "pals" / f"{internal_name[12:]}.png"
            else:
                icon = ASSET_ROOT / "icons" / "tech" / f"{internal_name}.png"
            self.assertTrue(icon.is_file(), (internal_name, icon))


class SkillAssetTests(unittest.TestCase):
    def test_1_0_monster_farm_passive_is_fully_localized(self) -> None:
        localized_data = json.loads(
            (ASSET_ROOT / "data" / "skill_i18n.json").read_text(encoding="utf-8")
        )
        editable_data = json.loads(
            (ASSET_ROOT / "data" / "pal_passives.json").read_text(encoding="utf-8")
        )
        internal_name = "WorkSuitabilityAddRank_MonsterFarm_1"

        self.assertEqual(114, len(editable_data))
        self.assertIn(internal_name, localized_data["Passives"])
        self.assertIn(internal_name, editable_data)
        self.assertEqual(3, editable_data[internal_name]["Rating"])
        for language in SUPPORTED_LANGUAGES:
            localized = localized_data["Passives"][internal_name]["I18n"][language]
            self.assertTrue(localized["Name"], language)
            self.assertNotEqual(internal_name, localized["Name"], language)
            self.assertTrue(localized["Description"], language)

        from palworld_pal_editor.config import Config
        from palworld_pal_editor.utils.data_provider import DataProvider

        previous_language = Config.i18n
        try:
            for language in SUPPORTED_LANGUAGES:
                Config.i18n = language
                name, description = DataProvider.get_passive_i18n(internal_name)
                self.assertNotEqual(internal_name, name, language)
                self.assertTrue(description, language)
        finally:
            Config.i18n = previous_language

    def test_1_0_localized_only_passive_catalog_is_complete(self) -> None:
        data = json.loads(
            (ASSET_ROOT / "data" / "skill_i18n.json").read_text(encoding="utf-8")
        )

        self.assertEqual(24088745, data["Build"])
        self.assertEqual(491, len(data["Passives"]))
        self.assertEqual(341, len(data["Attacks"]))
        for section in ("Passives", "Attacks"):
            for internal_name, row in data[section].items():
                for language in SUPPORTED_LANGUAGES:
                    localized = row["I18n"][language]
                    self.assertEqual(
                        set(row["I18n"]["en"]),
                        set(localized),
                        (section, internal_name, language),
                    )
                    self.assertTrue(
                        localized["Name"],
                        (section, internal_name, language),
                    )
        for internal_name in (
            "PAL_ALLAttack_up3",
            "PAL_CorporateSlave",
            "PAL_SpiritualInst",
        ):
            self.assertIn(internal_name, data["Passives"])
            self.assertTrue(data["Passives"][internal_name]["I18n"]["en"]["Name"])

    def test_1_0_passive_values_come_from_the_game_table(self) -> None:
        data = json.loads(
            (ASSET_ROOT / "data" / "pal_passives.json").read_text(encoding="utf-8")
        )

        self.assertEqual(0.20, data["Legend"]["Buff"]["b_MoveSpeed"])
        self.assertEqual(0.20, data["Rare"]["Buff"]["b_CraftSpeed"])
        self.assertEqual(4, data["Salvation"]["Rating"])
        self.assertEqual("전설", data["Legend"]["I18n"]["ko"]["Name"])
        self.assertIn("WorldTree_ATK", data)
        self.assertIn("MutationPal_Babysitter", data)

    def test_1_0_active_skill_table_is_fully_synchronized(self) -> None:
        attacks = json.loads(
            (ASSET_ROOT / "data" / "pal_attacks.json").read_text(encoding="utf-8")
        )
        pals = json.loads(
            (ASSET_ROOT / "data" / "pal_data.json").read_text(encoding="utf-8")
        )

        self.assertEqual(384, len(attacks))
        self.assertEqual(93, sum(row["SkillFruit"] for row in attacks.values()))
        self.assertEqual(25, sum(row.get("Invalid", False) for row in attacks.values()))
        self.assertEqual(40, attacks["EPalWazaID::AquaJet"]["Power"])
        self.assertEqual(50, attacks["EPalWazaID::WaterGun"]["Power"])
        self.assertEqual(12, attacks["EPalWazaID::WaterBall"]["CT"])
        self.assertEqual(200, attacks["EPalWazaID::WaterBall"]["Power"])
        self.assertTrue(attacks["EPalWazaID::Psychokinesis"]["SkillFruit"])
        self.assertEqual("워터 제트", attacks["EPalWazaID::AquaJet"]["I18n"]["ko"]["Name"])

        used_attacks = {
            attack
            for pal in pals.values()
            for attack in pal["Attacks"]
        }
        self.assertLessEqual(used_attacks, set(attacks))
        for internal_name, row in attacks.items():
            for language in SUPPORTED_LANGUAGES:
                self.assertTrue(
                    row["I18n"][language]["Name"],
                    (internal_name, language),
                )


class PalParameterAssetTests(unittest.TestCase):
    def test_1_0_pal_parameter_table_is_fully_synchronized(self) -> None:
        data = json.loads(
            (ASSET_ROOT / "data" / "pal_data.json").read_text(encoding="utf-8")
        )

        self.assertEqual(753, len(data))
        self.assertEqual(100, data["SheepBall"]["Stats"]["FOOD"])
        self.assertEqual(
            70,
            data["SheepBall"]["Attacks"]["EPalWazaID::HolyBlast"],
        )
        self.assertEqual(540, data["Anubis"]["Stats"]["FOOD"])
        self.assertEqual(
            6,
            data["Anubis"]["Suitabilities"][
                "EPalWorkSuitability::Handcraft"
            ],
        )
        self.assertEqual(
            6,
            data["Anubis"]["Suitabilities"]["EPalWorkSuitability::Mining"],
        )
        self.assertEqual(
            4,
            data["Anubis"]["Suitabilities"]["EPalWorkSuitability::Transport"],
        )
        self.assertIn("EPalWorkSuitability::OilExtraction", data["Anubis"]["Suitabilities"])
        self.assertEqual(52, sum(not row["Attacks"] for row in data.values()))
        self.assertNotIn("PyramidTurtle", data)
        self.assertEqual("도로롱", data["SheepBall"]["I18n"]["ko"])
        for internal_name, row in data.items():
            for language in SUPPORTED_LANGUAGES:
                self.assertTrue(row["I18n"][language], (internal_name, language))


class HumanAndProgressionAssetTests(unittest.TestCase):
    def test_human_catalog_uses_official_default_weapon_for_generated_moves(self) -> None:
        records = {
            "ArmedNPC": PalRecord(
                "ArmedNPC",
                {"OverrideNameTextID": "ArmedNPC", "Weapon": 2},
            ),
            "UnarmedNPC": PalRecord(
                "UnarmedNPC",
                {"OverrideNameTextID": "UnarmedNPC", "Weapon": None},
            ),
        }
        human_names = {
            language: {
                "ArmedNPC": "Armed NPC",
                "UnarmedNPC": "Unarmed NPC",
            }
            for language in SUPPORTED_LANGUAGES
        }

        catalog = build_human_catalog({}, records, human_names, set())

        self.assertEqual("Handgun", catalog["ArmedNPC"]["DefaultWeapon"])
        self.assertEqual(
            {"EPalWazaID::Weapon_Use": 1},
            catalog["ArmedNPC"]["Attacks"],
        )
        self.assertEqual("None", catalog["UnarmedNPC"]["DefaultWeapon"])
        self.assertEqual(
            {"EPalWazaID::Human_Punch": 1},
            catalog["UnarmedNPC"]["Attacks"],
        )

    def test_1_0_human_parameter_table_is_fully_synchronized(self) -> None:
        data = json.loads(
            (ASSET_ROOT / "data" / "human_data.json").read_text(encoding="utf-8")
        )

        self.assertEqual(433, len(data))
        self.assertIn("NPC_Dungeon_Shop", data)
        self.assertIn("SorajimaTowerGuide", data)
        self.assertEqual(33, sum(row["HasIcon"] for row in data.values()))
        self.assertEqual(20, data["SorajimaTowerGuide"]["Stats"]["HP"])
        self.assertEqual("Handgun", data["SalesPerson_Wander"]["DefaultWeapon"])
        self.assertEqual(
            {"EPalWazaID::Weapon_Use": 1},
            data["SalesPerson_Wander"]["Attacks"],
        )
        self.assertEqual("GatlingGun", data["Male_DarkTrader02"]["DefaultWeapon"])
        self.assertEqual(
            {"EPalWazaID::Weapon_Use": 1},
            data["Male_DarkTrader02"]["Attacks"],
        )
        for internal_name, row in data.items():
            expected_attack = (
                "EPalWazaID::Human_Punch"
                if row["DefaultWeapon"] == "None"
                else "EPalWazaID::Weapon_Use"
            )
            self.assertEqual(
                {expected_attack: 1},
                row["Attacks"],
                internal_name,
            )
        self.assertEqual(
            "永炎同心会 殉教者",
            data["Arena_FireCult_FlameThrower"]["I18n"]["zh-CN"],
        )
        self.assertEqual(
            "영원한 불꽃의 동지 순교자",
            data["Arena_FireCult_FlameThrower"]["I18n"]["ko"],
        )
        for internal_name, row in data.items():
            self.assertTrue(row["Human"], internal_name)
            self.assertIn(
                "EPalWorkSuitability::OilExtraction",
                row["Suitabilities"],
                internal_name,
            )
            for language in SUPPORTED_LANGUAGES:
                self.assertTrue(row["I18n"][language], (internal_name, language))

    def test_1_0_experience_and_friendship_tables_are_synchronized(self) -> None:
        experience = json.loads(
            (ASSET_ROOT / "data" / "pal_exp_table.json").read_text(
                encoding="utf-8"
            )
        )
        friendship = json.loads(
            (ASSET_ROOT / "data" / "pal_friendship.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(100, len(experience))
        self.assertEqual(10, experience["1"]["DropEXP"])
        self.assertEqual(50, experience["2"]["NextEXP"])
        self.assertEqual(10_582_213, experience["65"]["TotalEXP"])
        self.assertEqual(45_859_908, experience["80"]["TotalEXP"])
        self.assertEqual(382_451_548, experience["100"]["TotalEXP"])
        self.assertEqual(14, len(friendship))
        self.assertEqual(-10_000, friendship["-3"]["required_point"])
        self.assertEqual(200_000, friendship["10"]["required_point"])


class ItemAssetAndInventoryTests(unittest.TestCase):
    def test_1_0_equipment_localization_uses_official_item_table_keys(self) -> None:
        data = json.loads(
            (ASSET_ROOT / "data" / "item_data.json").read_text(encoding="utf-8")
        )
        expected_names = {
            "Glider_Tera": "特级滑翔伞",
            "GrapplingGun": "爪钩枪",
            "Shield_Ultra": "超级护盾",
            "TreasureMap02": "藏宝图",
        }
        self.assertEqual("울트라 방패", data["Shield_Ultra"]["I18n"]["ko"]["Name"])

        for internal_name, expected_name in expected_names.items():
            localized = data[internal_name]["I18n"]["zh-CN"]
            self.assertEqual(expected_name, localized["Name"], internal_name)
            self.assertTrue(localized["Description"], internal_name)

        unlocalized_legal_items = [
            internal_name
            for internal_name, row in data.items()
            if row["Rule"]["OfficialLegal"]
            and row["I18n"]["zh-CN"]["Name"] == internal_name
        ]
        self.assertEqual([], unlocalized_legal_items)
        legal_items_without_descriptions = {
            internal_name
            for internal_name, row in data.items()
            if row["Rule"]["OfficialLegal"]
            and not row["I18n"]["zh-CN"]["Description"]
        }
        self.assertEqual(
            {f"Head{index:03d}" for index in range(1, 18)},
            legal_items_without_descriptions,
        )

    def test_1_0_item_names_descriptions_and_confirmed_icons_are_synced(self) -> None:
        data = json.loads(
            (ASSET_ROOT / "data" / "item_data.json").read_text(encoding="utf-8")
        )

        self.assertEqual(2466, len(data))
        for internal_name, row in data.items():
            for language in SUPPORTED_LANGUAGES:
                self.assertTrue(row["I18n"][language]["Name"], (internal_name, language))
            if row["Icon"]:
                self.assertTrue(
                    (ASSET_ROOT / "icons" / "items" / f'{row["Icon"]}.png').is_file(),
                    (internal_name, row["Icon"]),
                )

        mapped_icons = [row["Icon"] for row in data.values() if row["Icon"]]
        self.assertEqual(2466, len(mapped_icons))
        self.assertEqual(918, len(set(mapped_icons)))

    def test_korean_is_registered_for_runtime_and_cli(self) -> None:
        from palworld_pal_editor.cli import lang
        from palworld_pal_editor.config import Config
        from palworld_pal_editor.utils.data_provider import DataProvider

        self.assertTrue(DataProvider.is_valid_i18n("ko"))
        self.assertEqual("한국어", DataProvider.get_i18n_map()["ko"])

        previous_language = Config.i18n
        try:
            with patch.object(Config, "save_to_file"):
                lang("ko")
            self.assertEqual("ko", Config.i18n)
        finally:
            Config.i18n = previous_language

    def test_lang_argument_accepts_korean_configuration(self) -> None:
        from palworld_pal_editor import __main__ as application_main
        from palworld_pal_editor.config import Config

        previous = {
            key: getattr(Config, key)
            for key in ("i18n", "mode", "port", "debug", "path", "password", "nocli")
        }
        try:
            with (
                patch.object(Config, "load_from_file"),
                patch.object(Config, "save_to_file"),
                patch.object(
                    application_main,
                    "check_or_generate_port",
                    side_effect=lambda port: port,
                ),
                patch.object(
                    sys,
                    "argv",
                    ["palworld-pal-editor", "--lang", "ko", "--mode", "cli"],
                ),
            ):
                application_main.setup_config_from_args()
            self.assertEqual("ko", Config.i18n)
            self.assertEqual("cli", Config.mode)
        finally:
            for key, value in previous.items():
                setattr(Config, key, value)

    def test_rarity_suffix_uses_verified_base_item_metadata(self) -> None:
        from palworld_pal_editor.utils.data_provider import DataProvider

        self.assertEqual("Advanced Bow", DataProvider.get_item_i18n("SFBow_5")[0])
        self.assertEqual("T_itemicon_Weapon_SFBow", DataProvider.get_item_icon("SFBow_5"))

    def test_item_count_update_preserves_slot_identity_and_trailing_data(self) -> None:
        from types import SimpleNamespace

        from palworld_pal_editor.core.item_container_data import ItemContainerData
        from palworld_pal_editor.core.pal_objects import PalObjects, toUUID

        container_id = toUUID("11111111-2222-3333-4444-555555555555")
        raw_data = {
            "slot_index": 3,
            "count": 5,
            "item": {
                "static_id": "Stone",
                "dynamic_id": {
                    "created_world_id": toUUID("00000000-0000-0000-0000-000000000000"),
                    "local_id_in_created_world": toUUID(
                        "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
                    ),
                },
            },
            "trailing_bytes": [1, 2, 3, 4],
        }
        gvas = SimpleNamespace(
            properties={
                "worldSaveData": {
                    "value": {
                        "ItemContainerSaveData": {
                            "value": [
                                {
                                    "key": {"ID": PalObjects.Guid(container_id)},
                                    "value": {
                                        "SlotNum": PalObjects.IntProperty(10),
                                        "Slots": {
                                            "value": {
                                                "values": [
                                                    {"RawData": {"value": raw_data}}
                                                ]
                                            }
                                        },
                                    },
                                }
                            ]
                        }
                    }
                }
            }
        )

        container = ItemContainerData(gvas).get(container_id)
        container.set_count(3, "Stone", 99)
        self.assertEqual(99, raw_data["count"])
        self.assertEqual("Stone", raw_data["item"]["static_id"])
        self.assertEqual([1, 2, 3, 4], raw_data["trailing_bytes"])
        with self.assertRaises(ValueError):
            container.set_count(3, "Wood", 100)
        with self.assertRaises(ValueError):
            container.set_count(3, "Stone", 0)


class NativeDialogTests(unittest.TestCase):
    def test_windows_bridge_mod_download_uses_selected_folder(self) -> None:
        from tempfile import TemporaryDirectory
        from palworld_pal_editor.gui import NativeDialogApi

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "PalEditorBridge-UE4SS-Mod-0.6.1.zip"
            package.write_bytes(b"bridge-package")
            download_root = root / "downloads"
            download_root.mkdir()
            api = NativeDialogApi(
                modern_folder_picker=lambda _initial: str(download_root),
                platform_name="win32",
                bridge_mod_package=package,
            )

            result = api.download_bridge_mod()

            self.assertEqual("completed", result["status"])
            downloaded = Path(result["path"])
            self.assertEqual(download_root.resolve(), downloaded.parent)
            self.assertEqual(package.name, downloaded.name)
            self.assertEqual(package.read_bytes(), downloaded.read_bytes())
            self.assertEqual(64, len(result["sha256"]))

    def test_bridge_mod_download_does_not_overwrite_an_existing_file(self) -> None:
        from tempfile import TemporaryDirectory
        from palworld_pal_editor.gui import NativeDialogApi

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "PalEditorBridge-UE4SS-Mod-0.6.1.zip"
            package.write_bytes(b"new-package")
            download_root = root / "downloads"
            download_root.mkdir()
            existing = download_root / package.name
            existing.write_bytes(b"existing-package")
            api = NativeDialogApi(
                modern_folder_picker=lambda _initial: str(download_root),
                platform_name="win32",
                bridge_mod_package=package,
            )

            result = api.download_bridge_mod()

            self.assertEqual("completed", result["status"])
            self.assertEqual(b"existing-package", existing.read_bytes())
            self.assertNotEqual(existing, Path(result["path"]))
            self.assertEqual(b"new-package", Path(result["path"]).read_bytes())

    def test_bridge_mod_download_is_windows_desktop_only(self) -> None:
        from palworld_pal_editor.gui import NativeDialogApi

        api = NativeDialogApi(platform_name="linux")

        self.assertEqual(
            {"status": "unsupported", "reason": "WINDOWS_DESKTOP_REQUIRED"},
            api.download_bridge_mod(),
        )

    def test_windows_uses_modern_folder_picker(self) -> None:
        from palworld_pal_editor.gui import NativeDialogApi

        received = []
        api = NativeDialogApi(
            modern_folder_picker=lambda initial_directory: received.append(initial_directory)
            or r"D:\PalSave",
            platform_name="win32",
        )
        self.assertEqual(r"D:\PalSave", api.select_save_directory())
        self.assertEqual([""], received)

    def test_system_folder_picker_is_owned_by_the_foreground_window(self) -> None:
        from palworld_pal_editor.windows_dialog import choose_folder

        with (
            patch(
                "palworld_pal_editor.windows_dialog._foreground_window_handle",
                return_value=4242,
            ),
            patch(
                "palworld_pal_editor.windows_dialog._choose_folder_on_sta_thread",
                return_value=r"D:\PalSave",
            ) as picker,
        ):
            self.assertEqual(r"D:\PalSave", choose_folder())

        picker.assert_called_once_with("", 4242)

    def test_windows_falls_back_to_pywebview_when_system_picker_fails(self) -> None:
        from palworld_pal_editor.gui import NativeDialogApi
        from tempfile import TemporaryDirectory

        class FakeWindow:
            def create_file_dialog(self, *args, **kwargs):
                self.calls = (args, kwargs)
                return (r"D:\FallbackSave",)

        def fail_system_picker(_initial_directory):
            raise OSError("system folder picker unavailable")

        with TemporaryDirectory() as initial_directory:
            window = FakeWindow()
            api = NativeDialogApi(
                window_provider=lambda: [window],
                modern_folder_picker=fail_system_picker,
                platform_name="win32",
            )

            self.assertEqual(
                r"D:\FallbackSave",
                api.select_save_directory(initial_directory),
            )
            self.assertEqual(webview.FOLDER_DIALOG, window.calls[0][0])
            self.assertEqual(
                str(Path(initial_directory).resolve()),
                window.calls[1]["directory"],
            )

    def test_windows_system_picker_cancellation_does_not_open_fallback(self) -> None:
        from palworld_pal_editor.gui import NativeDialogApi

        fallback_opened = False

        class FakeWindow:
            def create_file_dialog(self, *args, **kwargs):
                nonlocal fallback_opened
                fallback_opened = True
                return (r"D:\Unexpected",)

        api = NativeDialogApi(
            window_provider=lambda: [FakeWindow()],
            modern_folder_picker=lambda _initial_directory: None,
            platform_name="win32",
        )

        self.assertIsNone(api.select_save_directory())
        self.assertFalse(fallback_opened)

    def test_native_picker_accepts_the_game_pass_starting_folder(self) -> None:
        from tempfile import TemporaryDirectory
        from palworld_pal_editor.gui import NativeDialogApi

        with TemporaryDirectory() as selected:
            received = []
            api = NativeDialogApi(
                modern_folder_picker=lambda initial_directory: received.append(initial_directory)
                or initial_directory,
                platform_name="win32",
            )
            self.assertEqual(str(Path(selected).resolve()), api.select_save_directory(selected))
            self.assertEqual([str(Path(selected).resolve())], received)

    def test_game_pass_picker_selects_the_user_folder_from_the_default_wgs_root(self) -> None:
        from tempfile import TemporaryDirectory
        from palworld_pal_editor.gui import NativeDialogApi

        class FakeWindow:
            def create_file_dialog(self, *args, **kwargs):
                self.calls = (args, kwargs)
                return (kwargs["directory"],)

        with TemporaryDirectory() as temp:
            wgs_root = Path(temp) / "wgs"
            user = wgs_root / ("1" * 16 + "_" + "A" * 32)
            user.mkdir(parents=True)
            (user / "containers.index").write_bytes(b"index")
            window = FakeWindow()
            api = NativeDialogApi(
                window_provider=lambda: [window],
                wgs_root_provider=lambda: (wgs_root,),
                platform_name="linux",
            )

            self.assertEqual(
                str(user.resolve()),
                api.select_xgp_source(),
            )
            self.assertEqual(webview.FOLDER_DIALOG, window.calls[0][0])
            self.assertEqual(str(user.resolve()), window.calls[1]["directory"])

    def test_windows_game_pass_picker_uses_the_system_folder_dialog(self) -> None:
        from tempfile import TemporaryDirectory
        from palworld_pal_editor.gui import NativeDialogApi

        with TemporaryDirectory() as selected:
            received = []
            api = NativeDialogApi(
                modern_folder_picker=lambda initial_directory: received.append(
                    initial_directory
                )
                or initial_directory,
                platform_name="win32",
            )

            self.assertEqual(
                str(Path(selected).resolve()),
                api.select_xgp_source(selected),
            )
            self.assertEqual([str(Path(selected).resolve())], received)

    def test_steam_picker_selects_level_sav_and_returns_its_world_directory(self) -> None:
        from tempfile import TemporaryDirectory
        from palworld_pal_editor.gui import NativeDialogApi

        class FakeWindow:
            def create_file_dialog(self, *args, **kwargs):
                self.calls = (args, kwargs)
                return (str(Path(kwargs["directory"]) / "Level.sav"),)

        with TemporaryDirectory() as temp:
            world = Path(temp) / "World"
            world.mkdir()
            (world / "Level.sav").write_bytes(b"level")
            window = FakeWindow()
            api = NativeDialogApi(window_provider=lambda: [window])

            self.assertEqual(str(world.resolve()), api.select_steam_source(world))
            self.assertEqual(webview.OPEN_DIALOG, window.calls[0][0])
            self.assertEqual(str(world.resolve()), window.calls[1]["directory"])
            self.assertFalse(window.calls[1]["allow_multiple"])
            self.assertEqual(
                ("Palworld world save (Level.sav)",),
                window.calls[1]["file_types"],
            )

    def test_non_windows_keeps_pywebview_fallback(self) -> None:
        from palworld_pal_editor.gui import NativeDialogApi

        class FakeWindow:
            def create_file_dialog(self, *args, **kwargs):
                self.calls = (args, kwargs)
                return (r"D:\PalSave",)

        window = FakeWindow()
        api = NativeDialogApi(
            window_provider=lambda: [window],
            platform_name="linux",
        )
        self.assertEqual(r"D:\PalSave", api.select_save_directory())
        self.assertEqual(webview.FOLDER_DIALOG, window.calls[0][0])

    def test_local_data_picker_selects_one_sav_file(self) -> None:
        from palworld_pal_editor.gui import NativeDialogApi
        from tempfile import TemporaryDirectory

        class FakeWindow:
            def create_file_dialog(self, *args, **kwargs):
                self.calls = (args, kwargs)
                return (r"D:\Profile\LocalData.sav",)

        with TemporaryDirectory() as initial_directory:
            window = FakeWindow()
            api = NativeDialogApi(window_provider=lambda: [window])

            self.assertEqual(
                r"D:\Profile\LocalData.sav",
                api.select_local_data_file(initial_directory),
            )
            self.assertEqual(webview.OPEN_DIALOG, window.calls[0][0])
            self.assertEqual(
                str(Path(initial_directory).resolve()),
                window.calls[1]["directory"],
            )
            self.assertFalse(window.calls[1]["allow_multiple"])
            self.assertEqual(
                ("Palworld LocalData (*.sav)",),
                window.calls[1]["file_types"],
            )

    def test_global_palbox_picker_selects_only_global_storage_file(self) -> None:
        from tempfile import TemporaryDirectory
        from palworld_pal_editor.gui import NativeDialogApi

        class FakeWindow:
            def create_file_dialog(self, *args, **kwargs):
                self.calls = (args, kwargs)
                return (str(Path(kwargs["directory"]) / "GlobalPalStorage.sav"),)

        with TemporaryDirectory() as initial_directory:
            source = Path(initial_directory) / "GlobalPalStorage.sav"
            source.write_bytes(b"global")
            window = FakeWindow()
            api = NativeDialogApi(window_provider=lambda: [window])

            self.assertEqual(
                str(source.resolve()),
                api.select_global_palbox_file(initial_directory),
            )
            self.assertEqual(webview.OPEN_DIALOG, window.calls[0][0])
            self.assertFalse(window.calls[1]["allow_multiple"])
            self.assertEqual(
                ("Palworld Global Palbox (GlobalPalStorage.sav)",),
                window.calls[1]["file_types"],
            )

    def test_frontend_uses_native_picker_when_available(self) -> None:
        source = (
            PROJECT_ROOT
            / "frontend"
            / "palworld-pal-editor-webui"
            / "src"
            / "stores"
            / "paleditor.js"
        ).read_text(encoding="utf-8")
        self.assertIn("const MAX_LEVEL = 80;", source)
        self.assertIn("window.pywebview?.api?.select_save_directory", source)
        self.assertIn("window.pywebview?.api?.select_steam_source", source)
        self.assertIn("window.pywebview?.api?.select_xgp_source", source)
        self.assertIn("window.pywebview?.api?.select_local_data_file", source)
        self.assertIn("window.pywebview?.api?.select_global_palbox_file", source)
        entry_source = (
            PROJECT_ROOT
            / "frontend"
            / "palworld-pal-editor-webui"
            / "src"
            / "views"
            / "EntryView.vue"
        ).read_text(encoding="utf-8")
        self.assertIn("window.pywebview?.api?.download_bridge_mod", entry_source)
        self.assertIn("Remote_ModInstallDialogTitle", entry_source)
        self.assertNotIn("SHOW_DONATE_FLAG", source)
        self.assertNotIn("sorryandfuckyou", source)
        self.assertFalse(
            (PROJECT_ROOT / "frontend" / "palworld-pal-editor-webui" / "src" / "components" / "MarkdownModal.vue").exists()
        )

    def test_work_suitability_and_action_icons_are_updated(self) -> None:
        store_source = (
            PROJECT_ROOT
            / "frontend"
            / "palworld-pal-editor-webui"
            / "src"
            / "stores"
            / "paleditor.js"
        ).read_text(encoding="utf-8")
        pal_editor_source = (
            PROJECT_ROOT
            / "frontend"
            / "palworld-pal-editor-webui"
            / "src"
            / "components"
            / "PalEditor.vue"
        ).read_text(encoding="utf-8")
        icon_component = (
            PROJECT_ROOT
            / "frontend"
            / "palworld-pal-editor-webui"
            / "src"
            / "components"
            / "modules"
            / "AppIcon.vue"
        )

        self.assertIn("const MAX_SUITABILITY_LEVEL = ref(10);", store_source)
        self.assertIn("MAX_SUITABILITY_LEVEL.value = response.data.MaxSuitabilityLevel ?? 10;", store_source)
        self.assertIn("palStore.MAX_SUITABILITY_LEVEL", pal_editor_source)
        self.assertIn("palStore.SELECTED_PAL_DATA.suitMax", pal_editor_source)
        self.assertNotIn("isMaxSuit(key) {\n  return palStore.SELECTED_PAL_DATA.Suitabilities[key] >= 5", pal_editor_source)
        self.assertTrue(icon_component.is_file())
        self.assertIn('<AppIcon name="chevron-up"', pal_editor_source)
        self.assertNotIn(">🔼</button>", pal_editor_source)

    def test_element_icons_and_text_variant_labels(self) -> None:
        frontend = PROJECT_ROOT / "frontend" / "palworld-pal-editor-webui" / "src"
        pal_editor_source = (frontend / "components" / "PalEditor.vue").read_text(encoding="utf-8")
        pal_list_source = (frontend / "components" / "PalList.vue").read_text(encoding="utf-8")
        species_picker_source = (
            frontend / "components" / "modules" / "PalSpeciesPicker.vue"
        ).read_text(encoding="utf-8")

        self.assertTrue((frontend / "components" / "modules" / "ElementIcon.vue").is_file())
        self.assertTrue((frontend / "components" / "modules" / "VariantBadge.vue").is_file())
        self.assertIn("pal-species-option", species_picker_source)
        self.assertIn('v-for="element in pal.Elements || []"', species_picker_source)
        self.assertIn("<ElementIcon", species_picker_source)
        self.assertIn("<PalSpeciesPicker", pal_editor_source)
        self.assertNotIn("displayPalElement(pal.InternalName)", pal_editor_source)
        self.assertIn("displayNameWithoutVariantEmoji", pal_list_source)
        self.assertIn(
            '<span v-if="pal.IsBOSS" class="pal-variant-label is-boss">',
            pal_list_source,
        )
        self.assertIn(
            '<span v-if="pal.IsRarePal" class="pal-variant-label">',
            pal_list_source,
        )
        self.assertIn("getTranslatedText('Variant_Boss')", pal_list_source)
        self.assertIn("getTranslatedText('Variant_Rare')", pal_list_source)
        self.assertNotIn('<VariantBadge v-if="pal.IsBOSS"', pal_list_source)
        self.assertNotIn('<VariantBadge v-if="pal.IsRarePal"', pal_list_source)
        self.assertTrue((ASSET_ROOT / "icons" / "elements" / "Element_Water.png").is_file())

    def test_active_skill_chips_use_element_images(self) -> None:
        pal_editor_source = (
            PROJECT_ROOT
            / "frontend"
            / "palworld-pal-editor-webui"
            / "src"
            / "components"
            / "PalEditor.vue"
        ).read_text(encoding="utf-8")

        self.assertGreaterEqual(
            pal_editor_source.count(
                ':element="palStore.ACTIVE_SKILLS[skill].Element"'
            ),
            4,
        )
        self.assertNotIn(
            "palStore.displayElement(palStore.ACTIVE_SKILLS[skill]?.Element)",
            pal_editor_source,
        )

    def test_active_skill_picker_renders_element_images(self) -> None:
        frontend = (
            PROJECT_ROOT
            / "frontend"
            / "palworld-pal-editor-webui"
            / "src"
        )
        pal_editor_source = (frontend / "components" / "PalEditor.vue").read_text(encoding="utf-8")
        skill_picker_source = (
            frontend / "components" / "modules" / "PalSkillPicker.vue"
        ).read_text(encoding="utf-8")

        self.assertIn("<PalSkillPicker", pal_editor_source)
        self.assertIn('kind="active"', pal_editor_source)
        self.assertIn('class="pal-skill-dialog"', skill_picker_source)
        self.assertIn('<ElementIcon v-if="skill.Element"', skill_picker_source)
        self.assertNotIn('<select class="selector" name="add_MasteredWaza"', pal_editor_source)
        self.assertNotIn("palStore.displayElement(skill.Element)", pal_editor_source)


if __name__ == "__main__":
    unittest.main()
