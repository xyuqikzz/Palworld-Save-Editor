import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

import {
    PASSIVE_PRESET_STORAGE_KEY,
    PASSIVE_PRESET_VERSION,
    createDefaultPassivePresets,
    loadPassivePresets,
    removePassivePreset,
    savePassivePresets,
    togglePassivePresetPinned,
    upsertPassivePreset,
} from "../src/components/modules/passive-presets.js";

const createStorage = (initial = {}) => {
    const values = new Map(Object.entries(initial));
    return {
        getItem: (key) => values.has(key) ? values.get(key) : null,
        setItem: (key, value) => values.set(key, value),
        value: (key) => values.get(key),
    };
};

test("passive presets include all localized starters", () => {
    const available = [
        "WorldTree_CraftSpeed",
        "CraftSpeed_up3",
        "CraftSpeed_up2",
        "PAL_Sanity_Down_3",
        "WorldTree_ATK",
        "WorldTree_ATK_DEF",
        "MutationPal_Immortal",
        "CoolTimeReduction_Up_1",
        "WorldTree_MoveSpeed",
        "Stamina_Up_3",
        "MoveSpeed_up_3",
        "MoveSpeed_up_2",
        "MutationPal_Mutant",
        "TrainerATK_UP_1",
        "TrainerDEF_UP_1",
        "ReloadSpeedUp_Passive",
    ];
    const presets = createDefaultPassivePresets((key) => `translated:${key}`, available);

    assert.deepEqual(presets.map((preset) => preset.id), [
        "starter-work",
        "starter-combat",
        "starter-mount",
        "starter-support",
    ]);
    assert.equal(presets[0].name, "translated:PalEditor_PassivePreset_Work");
    assert.equal(presets[1].name, "translated:PalEditor_PassivePreset_Combat");
    assert.equal(presets[2].name, "translated:PalEditor_PassivePreset_Mount");
    assert.equal(presets[3].name, "translated:PalEditor_PassivePreset_Support");
    assert.equal(presets[0].pinned, false);
    assert.deepEqual(presets[0].skills, [
        "WorldTree_CraftSpeed",
        "CraftSpeed_up3",
        "CraftSpeed_up2",
        "PAL_Sanity_Down_3",
    ]);
    assert.deepEqual(presets[1].skills, [
        "WorldTree_ATK",
        "WorldTree_ATK_DEF",
        "MutationPal_Immortal",
        "CoolTimeReduction_Up_1",
    ]);
    assert.deepEqual(presets[2].skills, [
        "WorldTree_MoveSpeed",
        "Stamina_Up_3",
        "MoveSpeed_up_3",
        "MoveSpeed_up_2",
    ]);
    assert.deepEqual(presets[3].skills, [
        "MutationPal_Mutant",
        "TrainerATK_UP_1",
        "TrainerDEF_UP_1",
        "ReloadSpeedUp_Passive",
    ]);
});

test("version 2 starter presets migrate to the current general defaults", () => {
    const storage = createStorage({
        [PASSIVE_PRESET_STORAGE_KEY]: JSON.stringify({
            version: 2,
            presets: [
                {
                    id: "starter-work",
                    name: "工作",
                    skills: ["WorldTree_CraftSpeed", "CraftSpeed_up3", "CraftSpeed_up2", "CraftSpeed_up1"],
                    pinned: true,
                },
                {
                    id: "starter-combat",
                    name: "战斗",
                    skills: ["WorldTree_ATK", "WorldTree_ATK_DEF", "MutationPal_Immortal", "CoolTimeReduction_Up_1"],
                },
                { id: "custom", name: "自定义", skills: ["Legend"] },
            ],
        }),
    });
    const fallback = createDefaultPassivePresets((key) => ({
        PalEditor_PassivePreset_Work: "通用工作",
        PalEditor_PassivePreset_Combat: "通用战斗",
        PalEditor_PassivePreset_Mount: "通用坐骑",
        PalEditor_PassivePreset_Support: "通用辅助",
    })[key]);

    const loaded = loadPassivePresets(storage, fallback);

    assert.deepEqual(loaded.presets[0], { ...fallback[0], pinned: true });
    assert.deepEqual(loaded.presets[1], fallback[1]);
    assert.deepEqual(loaded.presets[2], {
        id: "custom",
        name: "自定义",
        skills: ["Legend"],
        pinned: false,
    });
    assert.deepEqual(loaded.presets.slice(3), fallback.slice(2));
});

test("version 3 presets gain new mount and support defaults without replacing user data", () => {
    const storage = createStorage({
        [PASSIVE_PRESET_STORAGE_KEY]: JSON.stringify({
            version: 3,
            presets: [
                {
                    id: "starter-work",
                    name: "My work preset",
                    skills: ["CraftSpeed_up3"],
                    pinned: true,
                },
                { id: "custom", name: "Custom", skills: ["Legend"] },
            ],
        }),
    });
    const fallback = createDefaultPassivePresets((key) => ({
        PalEditor_PassivePreset_Work: "General work",
        PalEditor_PassivePreset_Combat: "General combat",
        PalEditor_PassivePreset_Mount: "General mount",
        PalEditor_PassivePreset_Support: "General support",
    })[key]);

    const loaded = loadPassivePresets(storage, fallback);

    assert.deepEqual(loaded.presets, [
        {
            id: "starter-work",
            name: "My work preset",
            skills: ["CraftSpeed_up3"],
            pinned: true,
        },
        { id: "custom", name: "Custom", skills: ["Legend"], pinned: false },
        fallback[2],
        fallback[3],
    ]);
});

test("passive preset create, edit, delete, and storage roundtrip are versioned", () => {
    const storage = createStorage();
    let presets = upsertPassivePreset([], {
        id: "custom-work",
        name: "Work",
        skills: ["CraftSpeed_up2"],
    });
    presets = upsertPassivePreset(presets, {
        id: "custom-work",
        name: "Work max",
        skills: ["CraftSpeed_up3", "CraftSpeed_up2"],
    });
    const saved = savePassivePresets(storage, presets);
    const loaded = loadPassivePresets(storage, []);

    assert.deepEqual(loaded, { presets: saved, recovered: false });
    assert.deepEqual(JSON.parse(storage.value(PASSIVE_PRESET_STORAGE_KEY)), {
        version: PASSIVE_PRESET_VERSION,
        presets: saved,
    });

    const removed = removePassivePreset(loaded.presets, "custom-work");
    assert.deepEqual(removed, []);
    assert.deepEqual(savePassivePresets(storage, removed), []);
});

test("invalid local passive presets recover to starter presets", () => {
    const storage = createStorage({ [PASSIVE_PRESET_STORAGE_KEY]: "{broken" });
    const fallback = [{ id: "starter", name: "Work", skills: ["CraftSpeed_up2"], pinned: false }];

    assert.deepEqual(loadPassivePresets(storage, fallback), {
        presets: fallback,
        recovered: true,
    });
    assert.throws(() => upsertPassivePreset([], {
        id: "too-many",
        name: "Too many",
        skills: ["a", "b", "c", "d", "e"],
    }), /INVALID_PRESET/);
});

test("version 1 presets migrate without losing data and can be pinned", () => {
    const storage = createStorage({
        [PASSIVE_PRESET_STORAGE_KEY]: JSON.stringify({
            version: 1,
            presets: [{ id: "legacy", name: "Legacy", skills: ["Legend"] }],
        }),
    });

    const loaded = loadPassivePresets(storage, []);
    assert.deepEqual(loaded, {
        presets: [{ id: "legacy", name: "Legacy", skills: ["Legend"], pinned: false }],
        recovered: false,
    });
    assert.equal(togglePassivePresetPinned(loaded.presets, "legacy")[0].pinned, true);
    assert.equal(togglePassivePresetPinned([{ ...loaded.presets[0], pinned: true }], "legacy")[0].pinned, false);
});

test("preset traits reuse passive cards while pinned presets size to their labels", async () => {
    const editor = await readFile(new URL("../src/components/PalEditor.vue", import.meta.url), "utf8");
    const dialog = await readFile(new URL("../src/components/modules/PassivePresetDialog.vue", import.meta.url), "utf8");
    const quickbarStart = editor.indexOf('<nav\n          v-if="pinnedPassivePresets.length"');
    const quickbar = editor.slice(quickbarStart, editor.indexOf('</nav>', quickbarStart));

    assert.match(editor, /<PassiveSkillCard[\s\S]*?:skill="palStore\.PASSIVE_SKILLS\[skill\]"/);
    assert.match(editor, /\.passive-preset-quickbar\s*\{[^}]*display:\s*flex;[^}]*flex-wrap:\s*wrap/);
    assert.match(editor, /\.passive-preset-quickbar__label\s*\{[^}]*flex:\s*0 0 100%/);
    assert.match(editor, /\.passive-preset-quick-action\s*\{[^}]*width:\s*fit-content;[^}]*max-width:\s*100%;[^}]*flex:\s*0 1 auto/);
    assert.match(quickbar, /class="passive-preset-quick-action__label"/);
    assert.doesNotMatch(quickbar, /PassiveSkillCard/);
    assert.doesNotMatch(editor, /passivePresetDisplay/);
    assert.match(dialog, /class="passive-preset-traits"[\s\S]*?<PassiveSkillCard/);
    assert.match(dialog, /\.passive-preset-traits\s*\{[^}]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)/);
    assert.match(dialog, /class="passive-preset-row__header"[\s\S]*class="passive-preset-row__actions"/);
    assert.match(dialog, /\.passive-preset-dialog\.is-editing\s*\{[^}]*width:\s*min\(1180px/);
    assert.match(dialog, /\.passive-preset-dialog__body\.is-editing\s*\{[^}]*minmax\(520px/);
});

test("passive card tooltips use the top layer instead of clipped ancestors", async () => {
    const card = await readFile(new URL("../src/components/modules/PassiveSkillCard.vue", import.meta.url), "utf8");

    assert.match(card, /popover="manual"/);
    assert.match(card, /showPopover\(\)/);
    assert.match(card, /position:\s*fixed/);
});

test("Pal editor positions enhancement MAX independently and keeps suitability MAX with its section", async () => {
    const source = await readFile(new URL("../src/components/PalEditor.vue", import.meta.url), "utf8");
    const statsStart = source.indexOf('class="EditorItem flex-v item left statsPanel"');
    const statsEnd = source.indexOf('class="EditorItem item flex-v left skillPanel skillsPanel"', statsStart);
    const stats = source.slice(statsStart, statsEnd);
    const suitabilityStart = stats.indexOf('class="stat-group stat-group--suitabilities suitabilityPanel"');
    const suitability = stats.slice(suitabilityStart);
    const passiveHeaderStart = source.indexOf('<section class="skill-section passive-skill-section">');
    const passiveHeaderEnd = source.indexOf('</header>', passiveHeaderStart);
    const passiveHeader = source.slice(passiveHeaderStart, passiveHeaderEnd);

    assert.ok(stats.indexOf('class="edit stats-max-all"') < stats.indexOf('stat-group--iv'));
    assert.ok(suitability.indexOf('class="edit suitability-max-all"') < suitability.indexOf('class="editField skillList"'));
    assert.match(source, /:global\(#EditorMain button\.edit\.stats-max-all\)\s*\{[^}]*position:\s*absolute/);
    assert.ok(passiveHeader.indexOf("PalEditor_PassivePresets") < passiveHeader.indexOf("<PalSkillPicker"));
    assert.ok(source.indexOf('class="passive-preset-quickbar"', passiveHeaderEnd) < source.indexOf('class="skill-item-grid passive-skill-grid"', passiveHeaderEnd));
});
