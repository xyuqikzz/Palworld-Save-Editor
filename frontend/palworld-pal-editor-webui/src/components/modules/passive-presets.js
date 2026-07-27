export const PASSIVE_PRESET_STORAGE_KEY = "PAL_PASSIVE_PRESETS_V1";
export const PASSIVE_PRESET_VERSION = 4;
export const MAX_PASSIVE_PRESET_SKILLS = 4;
export const MAX_PASSIVE_PRESET_NAME_LENGTH = 40;

const DEFAULT_PRESET_DEFINITIONS = [
    {
        id: "starter-work",
        nameKey: "PalEditor_PassivePreset_Work",
        skills: [
            "WorldTree_CraftSpeed",
            "CraftSpeed_up3",
            "CraftSpeed_up2",
            "PAL_Sanity_Down_3",
        ],
    },
    {
        id: "starter-combat",
        nameKey: "PalEditor_PassivePreset_Combat",
        skills: [
            "WorldTree_ATK",
            "WorldTree_ATK_DEF",
            "MutationPal_Immortal",
            "CoolTimeReduction_Up_1",
        ],
    },
    {
        id: "starter-mount",
        nameKey: "PalEditor_PassivePreset_Mount",
        skills: [
            "WorldTree_MoveSpeed",
            "Stamina_Up_3",
            "MoveSpeed_up_3",
            "MoveSpeed_up_2",
        ],
    },
    {
        id: "starter-support",
        nameKey: "PalEditor_PassivePreset_Support",
        skills: [
            "MutationPal_Mutant",
            "TrainerATK_UP_1",
            "TrainerDEF_UP_1",
            "ReloadSpeedUp_Passive",
        ],
    },
];

const VERSION_4_DEFAULT_PRESET_IDS = new Set(["starter-mount", "starter-support"]);

const LEGACY_DEFAULT_PRESETS = {
    "starter-work": {
        names: ["工作", "Work", "作業", "仕事", "작업", "Travail"],
        skills: ["WorldTree_CraftSpeed", "CraftSpeed_up3", "CraftSpeed_up2", "CraftSpeed_up1"],
    },
    "starter-combat": {
        names: ["战斗", "Combat", "戦闘", "전투"],
        skills: ["WorldTree_ATK", "PAL_ALLAttack_up3", "Legend", "PAL_ALLAttack_up2"],
    },
};

const clonePreset = (preset) => ({
    id: preset.id,
    name: preset.name,
    skills: [...preset.skills],
    pinned: Boolean(preset.pinned),
});

function normalizePreset(preset) {
    if (!preset || typeof preset !== "object" || Array.isArray(preset)) {
        throw new TypeError("INVALID_PRESET");
    }
    const id = String(preset.id || "").trim();
    const name = String(preset.name || "").trim();
    if (!id || !name || name.length > MAX_PASSIVE_PRESET_NAME_LENGTH) {
        throw new TypeError("INVALID_PRESET");
    }
    if (!Array.isArray(preset.skills)) {
        throw new TypeError("INVALID_PRESET");
    }
    const skills = [...new Set(preset.skills.map((skill) => String(skill || "").trim()))]
        .filter(Boolean);
    if (skills.length !== preset.skills.length || skills.length > MAX_PASSIVE_PRESET_SKILLS) {
        throw new TypeError("INVALID_PRESET");
    }
    return { id, name, skills, pinned: Boolean(preset.pinned) };
}

export function createDefaultPassivePresets(translate, availableSkillIds = null) {
    const available = availableSkillIds ? new Set(availableSkillIds) : null;
    return DEFAULT_PRESET_DEFINITIONS
        .filter((preset) => !available || preset.skills.every((skill) => available.has(skill)))
        .map((preset) => ({
            id: preset.id,
            name: translate(preset.nameKey),
            skills: [...preset.skills],
            pinned: false,
        }));
}

export function loadPassivePresets(storage, fallbackPresets) {
    const fallback = fallbackPresets.map(clonePreset);
    try {
        const raw = storage?.getItem(PASSIVE_PRESET_STORAGE_KEY);
        if (raw === null || raw === undefined || raw === "") {
            return { presets: fallback, recovered: false };
        }
        const payload = JSON.parse(raw);
        if (
            !payload
            || ![1, 2, 3, PASSIVE_PRESET_VERSION].includes(payload.version)
            || !Array.isArray(payload.presets)
        ) {
            throw new TypeError("INVALID_PRESET_STORAGE");
        }
        const fallbackById = new Map(fallback.map((preset) => [preset.id, preset]));
        const presets = payload.presets.map(normalizePreset).map((preset) => {
            if (payload.version >= 3) return preset;
            const legacy = LEGACY_DEFAULT_PRESETS[preset.id];
            const current = fallbackById.get(preset.id);
            if (!legacy || !current) return preset;

            const hasLegacyName = legacy.names.includes(preset.name);
            const hasLegacySkills = legacy.skills.every((skill, index) => preset.skills[index] === skill);
            const hasCurrentSkills = current.skills.every((skill, index) => preset.skills[index] === skill);
            if (hasLegacyName && (hasLegacySkills || hasCurrentSkills)) {
                return { ...clonePreset(current), pinned: preset.pinned };
            }
            if (hasLegacySkills) {
                return { ...preset, skills: [...current.skills] };
            }
            return preset;
        });
        if (payload.version < PASSIVE_PRESET_VERSION) {
            const existingIds = new Set(presets.map((preset) => preset.id));
            fallback
                .filter((preset) => (
                    VERSION_4_DEFAULT_PRESET_IDS.has(preset.id)
                    && !existingIds.has(preset.id)
                ))
                .forEach((preset) => presets.push(clonePreset(preset)));
        }
        if (new Set(presets.map((preset) => preset.id)).size !== presets.length) {
            throw new TypeError("DUPLICATE_PRESET_ID");
        }
        return { presets, recovered: false };
    } catch {
        return { presets: fallback, recovered: true };
    }
}

export function savePassivePresets(storage, presets) {
    const normalized = presets.map(normalizePreset);
    if (new Set(normalized.map((preset) => preset.id)).size !== normalized.length) {
        throw new TypeError("DUPLICATE_PRESET_ID");
    }
    if (typeof storage?.setItem !== "function") {
        throw new TypeError("PRESET_STORAGE_UNAVAILABLE");
    }
    storage.setItem(PASSIVE_PRESET_STORAGE_KEY, JSON.stringify({
        version: PASSIVE_PRESET_VERSION,
        presets: normalized,
    }));
    return normalized.map(clonePreset);
}

export function upsertPassivePreset(presets, draft) {
    const normalized = normalizePreset(draft);
    const next = presets.map(clonePreset);
    const index = next.findIndex((preset) => preset.id === normalized.id);
    if (index >= 0) next.splice(index, 1, normalized);
    else next.push(normalized);
    return next;
}

export function removePassivePreset(presets, presetId) {
    return presets
        .filter((preset) => preset.id !== presetId)
        .map(clonePreset);
}

export function togglePassivePresetPinned(presets, presetId) {
    return presets.map((preset) => ({
        ...clonePreset(preset),
        pinned: preset.id === presetId ? !preset.pinned : Boolean(preset.pinned),
    }));
}
