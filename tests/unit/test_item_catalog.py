from __future__ import annotations

from dataclasses import replace
import unittest

from palworld_pal_editor.domain.errors import DomainError
from palworld_pal_editor.domain.item_catalog import (
    ItemCatalog,
    new_item_slot_metadata,
)
from palworld_pal_editor.domain.models import ItemCatalogEntry, ItemContainerType


def entry(
    static_id: str,
    *,
    name: str,
    category: str,
    max_stack: int | None,
    containers: tuple[ItemContainerType, ...],
    status: str = "verified",
    disabled: bool = False,
) -> ItemCatalogEntry:
    return ItemCatalogEntry(
        static_id=static_id,
        names={"en": name, "zh-CN": f"中-{name}"},
        descriptions={"en": f"Description {name}"},
        category=category,
        rarity=1,
        icon=None,
        max_stack=max_stack,
        allowed_containers=containers,
        dynamic_kind="none",
        rule_status=status,
        rule_source="synthetic-test",
        rule_version="fixture-v1",
        disabled=disabled,
    )


class ItemCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = ItemCatalog(
            [
                entry(
                    "Stone",
                    name="Stone",
                    category="material",
                    max_stack=9999,
                    containers=(ItemContainerType.COMMON,),
                ),
                entry(
                    "Sword",
                    name="Sword",
                    category="weapon",
                    max_stack=1,
                    containers=(ItemContainerType.WEAPON_LOADOUT,),
                ),
            ]
        )

    def test_search_uses_name_internal_id_and_category(self) -> None:
        self.assertEqual("Stone", self.catalog.search(text="中-Stone")[0].static_id)
        self.assertEqual("Sword", self.catalog.search(text="swo")[0].static_id)
        self.assertEqual(
            ["Stone"],
            [item.static_id for item in self.catalog.search(category="material")],
        )

    def test_psychokinesis_skill_fruit_is_searchable_and_placeable(self) -> None:
        catalog = ItemCatalog.load_default()

        result = catalog.search(
            text="Psycho Gravity",
            container_type=ItemContainerType.COMMON,
            locale="en",
        )

        self.assertEqual(["SkillCard_Psychokinesis"], [item.static_id for item in result])
        self.assertFalse(result[0].disabled)
        catalog.validate_placement(
            "SkillCard_Psychokinesis",
            ItemContainerType.COMMON,
            0,
            1,
        )

    def test_max_stack_and_container_are_verified(self) -> None:
        self.catalog.validate_placement("Stone", ItemContainerType.COMMON, 0, 9999)
        with self.assertRaises(DomainError) as too_many:
            self.catalog.validate_placement("Stone", ItemContainerType.COMMON, 0, 10000)
        self.assertEqual("MAX_STACK_EXCEEDED", too_many.exception.code)
        with self.assertRaises(DomainError) as wrong_container:
            self.catalog.validate_placement(
                "Stone", ItemContainerType.WEAPON_LOADOUT, 0, 1
            )
        self.assertEqual("ITEM_NOT_ALLOWED_IN_CONTAINER", wrong_container.exception.code)

    def test_non_integer_boolean_zero_and_unknown_rules_are_rejected(self) -> None:
        for count in (True, 1.5, "1", 0, -1):
            with self.subTest(count=count), self.assertRaises(DomainError):
                self.catalog.validate_placement(
                    "Stone", ItemContainerType.COMMON, 0, count
                )
        unknown = ItemCatalog(
            [
                entry(
                    "Mystery",
                    name="Mystery",
                    category="unknown",
                    max_stack=None,
                    containers=(),
                    status="unknown",
                )
            ]
        )
        with self.assertRaises(DomainError) as unavailable:
            unknown.validate_placement("Mystery", ItemContainerType.COMMON, 0, 1)
        self.assertEqual("CATALOG_RULE_UNAVAILABLE", unavailable.exception.code)

    def test_rule_free_existing_stack_can_only_decrease(self) -> None:
        unknown = ItemCatalog(
            [
                entry(
                    "Mystery",
                    name="Mystery",
                    category="unknown",
                    max_stack=None,
                    containers=(),
                    status="unknown",
                )
            ]
        )

        unknown.validate_existing_count_update(
            "Mystery", ItemContainerType.COMMON, 2, current_count=10, count=9
        )
        for count in (10, 11):
            with self.subTest(count=count), self.assertRaises(DomainError) as raised:
                unknown.validate_existing_count_update(
                    "Mystery",
                    ItemContainerType.COMMON,
                    2,
                    current_count=10,
                    count=count,
                )
            self.assertEqual("CATALOG_RULE_UNAVAILABLE", raised.exception.code)

    def test_equipment_slots_are_category_specific(self) -> None:
        equipment = ItemCatalog(
            [
                entry(
                    category,
                    name=category,
                    category=category,
                    max_stack=1,
                    containers=(ItemContainerType.PLAYER_EQUIP_ARMOR,),
                )
                for category in (
                    "head",
                    "body",
                    "accessory",
                    "shield",
                    "glider",
                    "sphere_module",
                )
            ]
        )
        valid = {
            0: "head",
            1: "body",
            2: "accessory",
            3: "accessory",
            4: "shield",
            5: "glider",
            6: "accessory",
            7: "accessory",
            8: "sphere_module",
        }
        for slot_index, category in valid.items():
            with self.subTest(slot_index=slot_index, category=category):
                equipment.validate_placement(
                    category,
                    ItemContainerType.PLAYER_EQUIP_ARMOR,
                    slot_index,
                    1,
                )
        for slot_index, category in ((0, "body"), (2, "head"), (9, "accessory")):
            with self.subTest(slot_index=slot_index, category=category):
                with self.assertRaises(DomainError) as raised:
                    equipment.validate_placement(
                        category,
                        ItemContainerType.PLAYER_EQUIP_ARMOR,
                        slot_index,
                        1,
                    )
                self.assertEqual(
                    "ITEM_NOT_ALLOWED_IN_EQUIPMENT_SLOT", raised.exception.code
                )

    def test_new_equipment_slot_metadata_matches_current_save_schema(self) -> None:
        expected_type_b = {0: 20, 1: 21, 2: 22, 3: 22, 4: 58, 5: 57, 6: 22, 7: 22, 8: 67}
        for slot_index, permission_type_b in expected_type_b.items():
            with self.subTest(slot_index=slot_index):
                metadata = new_item_slot_metadata(
                    ItemContainerType.PLAYER_EQUIP_ARMOR, slot_index
                )
                self.assertEqual([3, 4, 10, 13], metadata["permission"]["type_a"])
                self.assertEqual([permission_type_b], metadata["permission"]["type_b"])
                self.assertEqual([], metadata["permission"]["item_static_ids"])
                self.assertEqual(0.0, metadata["corruption_progress_value"])
                self.assertEqual([0, 0, 0, 0], metadata["trailing_bytes"])

        with self.assertRaises(DomainError) as raised:
            new_item_slot_metadata(ItemContainerType.PLAYER_EQUIP_ARMOR, 9)
        self.assertEqual("ITEM_NOT_ALLOWED_IN_EQUIPMENT_SLOT", raised.exception.code)

    def test_dynamic_record_id_allows_only_verified_accessory_variants(self) -> None:
        hp_1 = replace(
            entry(
                "Accessory_HP_1",
                name="HP 1",
                category="accessory",
                max_stack=1,
                containers=(ItemContainerType.COMMON,),
            ),
            dynamic_kind="armor",
        )
        hp_3 = replace(
            hp_1,
            static_id="Accessory_HP_3",
            names={"en": "HP 3"},
            disabled=True,
        )
        attack_3 = replace(
            hp_3,
            static_id="Accessory_AT_3",
            names={"en": "Attack 3"},
        )
        catalog = ItemCatalog([hp_1, hp_3, attack_3])

        selected = catalog.validate_dynamic_record_static_id(
            "Accessory_HP_1", "Accessory_HP_3", "armor"
        )

        self.assertEqual("Accessory_HP_3", selected.static_id)
        with self.assertRaises(DomainError) as raised:
            catalog.validate_dynamic_record_static_id(
                "Accessory_HP_1", "Accessory_AT_3", "armor"
            )
        self.assertEqual("DYNAMIC_RECORD_ITEM_MISMATCH", raised.exception.code)

    def test_disabled_items_are_hidden_by_default_and_rejected_explicitly(self) -> None:
        disabled = ItemCatalog(
            [
                entry(
                    "DebugItem",
                    name="Debug item",
                    category="common",
                    max_stack=1,
                    containers=(ItemContainerType.COMMON,),
                    disabled=True,
                )
            ]
        )
        self.assertEqual([], disabled.search())
        self.assertEqual(
            ["DebugItem"],
            [item.static_id for item in disabled.search(include_disabled=True)],
        )
        with self.assertRaises(DomainError) as raised:
            disabled.validate_placement(
                "DebugItem", ItemContainerType.COMMON, 0, 1
            )
        self.assertEqual("ITEM_DISABLED", raised.exception.code)

    def test_default_catalog_is_cross_validated_for_palworld_1_0(self) -> None:
        catalog = ItemCatalog.load_default()
        all_items = catalog.search(include_disabled=True)
        self.assertEqual(2466, len(all_items))
        self.assertEqual(1892, sum(not item.disabled for item in all_items))
        self.assertTrue(
            all(
                item.rule_status == "verified"
                and item.rule_version == "Steam build 24088745"
                and item.max_stack is not None
                for item in all_items
            )
        )
        money = catalog.get("Money")
        self.assertEqual(99_999_999, money.max_stack)
        self.assertIn(ItemContainerType.COMMON, money.allowed_containers)
        self.assertTrue(catalog.get("PalSphere_Debug").disabled)


if __name__ == "__main__":
    unittest.main()
