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
    const palId = "pal-1";
    const playerId = "player-1";
    const palData = {
        InstanceId: palId,
        DataAccessKey: "TestPal",
        Rank: 1,
        PassiveSkillList: [],
        EquipWaza: [],
        MasteredWaza: [],
        Suitabilities: { [suitability]: 2 },
    };
    const palMap = new Map([[palId, palData]]);

    store.PAL_MAP = palMap;
    store.PLAYER_MAP = new Map([[playerId, { pals: palMap }]]);
    store.SELECTED_PLAYER_ID = playerId;
    store.SESSION_ID = "session-1";
    store.SESSION_REVISION = 0;
    store.PAL_STATIC_DATA = {
        TestPal: { Suitabilities: { [suitability]: 1 } },
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

    store.PAL_STATIC_DATA.TestPal.Suitabilities[suitability] = 0;
    commandPayload = undefined;
    assert.doesNotThrow(() => {
        store.SELECTED_PAL_DATA.set_Suitability(suitability, 1);
    });
    assert.equal(commandPayload, undefined);
});
