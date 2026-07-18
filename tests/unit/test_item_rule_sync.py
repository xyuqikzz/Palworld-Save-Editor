from __future__ import annotations

import base64
import struct
import unittest

from palworld_pal_editor.assets.tools.sync_1_0_item_rules import (
    StaticItemRule,
    allowed_containers,
    apply_official_legal_flags,
    build_catalog,
    decode_static_item_asset,
    item_category,
    parse_unversioned_header,
)


def fragment(
    skip: int,
    count: int,
    *,
    last: bool = False,
    has_zeroes: bool = False,
) -> bytes:
    packed = (
        skip
        | (0x80 if has_zeroes else 0)
        | (0x100 if last else 0)
        | (count << 9)
    )
    return struct.pack("<H", packed)


def fname(index: int, number: int = 0) -> bytes:
    return struct.pack("<ii", index, number)


def synthetic_static_asset() -> dict:
    name_map = ["None", "Stone", "/Game/T_Stone", "T_Stone"]
    root = bytearray(fragment(0, 2, last=True))
    root.extend(struct.pack("<ii", 0, 2))
    root.extend(fname(0) + struct.pack("<i", 0))
    root.extend(fname(1) + struct.pack("<i", 2))
    root.extend(bytes(24))

    item = bytearray()
    item.extend(fragment(0, 1))
    item.extend(fragment(1, 8, last=True))
    item.extend(fname(1))
    item.extend(fname(2) + fname(3) + struct.pack("<i", 0))
    item.extend(bytes((5, 23)))
    item.extend(struct.pack("<iiiii", 1, 2, 100, 9999, 7))
    return {
        "IsUnversioned": True,
        "NameMap": name_map,
        "Imports": [
            {"ObjectName": "PalStaticItemDataAsset"},
            {"ObjectName": "PalStaticItemDataBase"},
        ],
        "Exports": [
            {
                "ObjectName": "DA_StaticItemDataAsset",
                "ClassIndex": -1,
                "Data": base64.b64encode(root).decode(),
            },
            {
                "ObjectName": "PalStaticItemDataBase_0",
                "ClassIndex": -2,
                "Data": base64.b64encode(item).decode(),
            },
        ],
    }


def synthetic_item_table(*, legal: bool) -> dict:
    present = {2, 3, 4, 5, 6, 7, 9, 10}
    if legal:
        present.add(15)
    zero_mask = sum(1 << index for index in set(range(53)) - present)
    row = bytearray(fname(0))
    row.extend(fragment(0, 53, last=True, has_zeroes=True))
    row.extend(zero_mask.to_bytes(8, "little"))
    row.extend(fname(1))
    row.extend(bytes((5, 23)))
    row.extend(struct.pack("<iii", 1, 2, 9999))
    row.extend(struct.pack("<ii", 100, 7))
    if legal:
        row.append(1)

    data = bytearray(b"\x00\x03")
    data.extend(struct.pack("<iii", -1, 0, 1))
    data.extend(row)
    return {
        "IsUnversioned": True,
        "NameMap": ["Stone", "T_Stone"],
        "Imports": [{"ObjectName": "PalStaticItemDataStruct"}],
        "Exports": [
            {
                "ObjectName": "DT_ItemDataTable_Common",
                "Data": base64.b64encode(data).decode(),
            }
        ],
    }


class ItemRuleSyncTests(unittest.TestCase):
    def test_unversioned_header_decodes_fragment_skips_and_zero_mask(self) -> None:
        data = (
            fragment(2, 1)
            + fragment(1, 2, last=True, has_zeroes=True)
            + b"\x02"
        )
        offset, state = parse_unversioned_header(data)
        self.assertEqual(5, offset)
        self.assertEqual({2: True, 4: True, 5: False}, state)

    def test_synthetic_official_assets_are_cross_validated(self) -> None:
        static = decode_static_item_asset(
            synthetic_static_asset(), expected_count=1
        )
        self.assertEqual(["Stone"], list(static))
        record = static["Stone"]
        self.assertEqual(9999, record.max_stack)
        self.assertEqual("none", record.dynamic_kind)

        enabled = apply_official_legal_flags(
            synthetic_item_table(legal=True), static, expected_count=1
        )
        disabled = apply_official_legal_flags(
            synthetic_item_table(legal=False), static, expected_count=1
        )
        self.assertTrue(enabled["Stone"].official_legal)
        self.assertFalse(disabled["Stone"].official_legal)

    def test_categories_containers_and_catalog_provenance_are_deterministic(self) -> None:
        self.assertEqual("weapon", item_category(1, 5))
        self.assertEqual("head", item_category(3, 20))
        self.assertEqual("body", item_category(3, 21))
        self.assertEqual("shield", item_category(3, 58))
        self.assertEqual("accessory", item_category(4, 22))
        self.assertEqual("food", item_category(8, 51))
        self.assertEqual("key_item", item_category(9, 65))
        self.assertEqual("glider", item_category(10, 57))
        self.assertEqual("sphere_module", item_category(13, 67))
        self.assertIn("WEAPON_LOADOUT", allowed_containers("weapon"))
        self.assertEqual(("ESSENTIAL",), allowed_containers("key_item"))

        record = StaticItemRule(
            static_id="Stone",
            name_base="Stone",
            name_number=0,
            type_a=5,
            type_b=23,
            rank=1,
            rarity=2,
            price=100,
            max_stack=9999,
            sort_id=7,
            dynamic_class_index=0,
            item_static_class=None,
            icon_package="/Game/T_Stone",
            icon_asset="T_Stone",
            object_class="PalStaticItemDataBase",
            official_legal=True,
        )
        catalog = build_catalog(
            {
                "Stone": {
                    "InternalName": "Stone",
                    "Icon": None,
                    "I18n": {"en": {"Name": "Stone"}},
                }
            },
            {"Stone": record},
        )
        rule = catalog["Stone"]["Rule"]
        self.assertEqual("verified", rule["Status"])
        self.assertEqual("Steam build 24088745", rule["Version"])
        self.assertFalse(rule["Disabled"])
        self.assertTrue(rule["OfficialLegal"])
        self.assertEqual("T_Stone", catalog["Stone"]["Icon"])


if __name__ == "__main__":
    unittest.main()
