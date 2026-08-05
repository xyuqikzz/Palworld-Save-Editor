import test from "node:test";
import assert from "node:assert/strict";

import axios from "axios";
import { createPinia, setActivePinia } from "pinia";

globalThis.alert = () => {};
globalThis.localStorage = {
    getItem: () => null,
    setItem: () => {},
};

const { usePalEditorStore } = await import("../src/stores/paleditor.js");

test("work suitability buttons use the button name when an SVG child is clicked", async () => {
    setActivePinia(createPinia());
    const store = usePalEditorStore();
    const suitability = "EPalWorkSuitability::Handcraft";
    const unavailableSuitability = "EPalWorkSuitability::Mining";
    const palId = "pal-1";
    const playerId = "player-1";
    const palData = {
        InstanceId: palId,
        DataAccessKey: "TestPal",
        Rank: 1,
        PassiveSkillList: [],
        EquipWaza: [],
        MasteredWaza: [],
        Suitabilities: { [suitability]: 2, [unavailableSuitability]: 0 },
    };
    const palMap = new Map([[palId, palData]]);

    store.PAL_MAP = palMap;
    store.PLAYER_MAP = new Map([[playerId, { pals: palMap }]]);
    store.SELECTED_PLAYER_ID = playerId;
    store.SESSION_ID = "session-1";
    store.SESSION_REVISION = 0;
    store.PAL_STATIC_DATA = {
        TestPal: { Suitabilities: { [suitability]: 1, [unavailableSuitability]: 0 } },
    };

    axios.post = async () => ({ data: { status: 0, data: palData } });
    await store.selectPal(palId);

    let commandPayload;
    axios.post = async (_url, data) => {
        commandPayload = JSON.parse(JSON.stringify(data));
        return { data: { status: 1, msg: "captured by test" } };
    };

    store.SELECTED_PAL_DATA.suitUp({
        target: {},
        currentTarget: { name: suitability },
    });
    await Promise.resolve();

    assert.equal(commandPayload.command, "update_pal_enhancement");
    assert.deepEqual(commandPayload.work_suitability, { [suitability]: 3 });

    store.SELECTED_PAL_DATA.suitDown({
        target: {},
        currentTarget: { name: suitability },
    });
    await Promise.resolve();

    assert.deepEqual(commandPayload.work_suitability, { [suitability]: 1 });

    store.MAX_SUITABILITY_LEVEL = 12;
    store.SELECTED_PAL_DATA.suitMax({
        target: {},
        currentTarget: { name: suitability },
    });
    await Promise.resolve();

    assert.deepEqual(commandPayload.work_suitability, { [suitability]: 12 });

    store.SELECTED_PAL_DATA.maxAllSuitabilities();
    await Promise.resolve();

    assert.deepEqual(commandPayload.work_suitability, { [suitability]: 12 });

    store.HIDE_INVALID_OPTIONS = false;
    store.SELECTED_PAL_DATA.maxAllSuitabilities();
    await Promise.resolve();

    assert.deepEqual(commandPayload.work_suitability, {
        [suitability]: 12,
        [unavailableSuitability]: 12,
    });

    store.HIDE_INVALID_OPTIONS = true;
    store.MAX_SOULS_LEVEL = 20;
    store.SELECTED_PAL_DATA.maxAllEnhancements();
    await Promise.resolve();

    assert.equal(commandPayload.command, "update_pal_enhancement");
    assert.deepEqual(commandPayload.values, {
        iv_hp: 100,
        iv_shot: 100,
        iv_defense: 100,
        soul_hp: 20,
        soul_attack: 20,
        soul_defense: 20,
        soul_craft_speed: 20,
        condensation: 5,
    });
    assert.equal(Object.hasOwn(commandPayload, "work_suitability"), false);

    store.HIDE_INVALID_OPTIONS = false;
    store.SELECTED_PAL_DATA.maxAllEnhancements();
    await Promise.resolve();

    assert.deepEqual(commandPayload.values, {
        iv_hp: 255,
        iv_shot: 255,
        iv_defense: 255,
        soul_hp: 255,
        soul_attack: 255,
        soul_defense: 255,
        soul_craft_speed: 255,
        condensation: 255,
        iv_melee: 255,
    });
    assert.equal(Object.hasOwn(commandPayload, "work_suitability"), false);

    store.SELECTED_PAL_DATA.replacePassiveSkills(["Rare", "Legend"]);
    await Promise.resolve();

    assert.equal(commandPayload.command, "update_pal_skills");
    assert.equal(commandPayload.active, null);
    assert.equal(commandPayload.mastered, null);
    assert.deepEqual(commandPayload.passive, ["Rare", "Legend"]);

    store.HIDE_INVALID_OPTIONS = true;
    store.PAL_STATIC_DATA.TestPal.Suitabilities[suitability] = 0;
    commandPayload = undefined;
    assert.doesNotThrow(() => {
        store.SELECTED_PAL_DATA.set_Suitability(suitability, 1);
    });
    assert.equal(commandPayload, undefined);
});
