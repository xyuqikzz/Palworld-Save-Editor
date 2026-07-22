import { ref, computed, reactive, nextTick, watch } from "vue";
import { defineStore } from "pinia";
import axios from "axios";
import enTranslations from "../i18n/en.js";
import frTranslations from "../i18n/fr.js";
import jaTranslations from "../i18n/ja.js";
import koTranslations from "../i18n/ko.js";
import zhCnTranslations from "../i18n/zh-CN.js";
import { PAL_LIST_SORT_MODES, sortPalList } from "../components/modules/pal-list-sort.js";

const NPC_WEAPON_TRANSLATION_KEYS = Object.freeze({
    AssaultRifle: "PalEditor_NpcWeapon_AssaultRifle",
    BowGun: "PalEditor_NpcWeapon_BowGun",
    FlameThrower: "PalEditor_NpcWeapon_FlameThrower",
    GatlingGun: "PalEditor_NpcWeapon_GatlingGun",
    GiantClub: "PalEditor_NpcWeapon_GiantClub",
    GrenadeLauncher: "PalEditor_NpcWeapon_GrenadeLauncher",
    Handgun: "PalEditor_NpcWeapon_Handgun",
    Katana: "PalEditor_NpcWeapon_Katana",
    LaserRifle: "PalEditor_NpcWeapon_LaserRifle",
    MeleeWeapon: "PalEditor_NpcWeapon_MeleeWeapon",
    MissileLauncher: "PalEditor_NpcWeapon_MissileLauncher",
    None: "PalEditor_NpcWeapon_None",
    RocketLauncher: "PalEditor_NpcWeapon_RocketLauncher",
    Shotgun: "PalEditor_NpcWeapon_Shotgun",
    ThrowObject: "PalEditor_NpcWeapon_ThrowObject",
});

const SAVE_SOURCE_MODE_STORAGE_KEY = "PAL_SAVE_SOURCE_MODE";

function getInitialSaveSourceMode() {
    return localStorage.getItem(SAVE_SOURCE_MODE_STORAGE_KEY) === "xgp"
        ? "xgp"
        : "steam";
}

export const usePalEditorStore = defineStore("paleditor", () => {
    const MAX_LEVEL = 80;
    const MIN_FRIENDSHIP_LEVEL = 0;
    const MAX_FRIENDSHIP_LEVEL = 10;
    const MAX_INVALID_LEVEL = 100;
    const MAX_SOULS_LEVEL = ref(0);
    const MAX_SUITABILITY_LEVEL = ref(10);
    class Player {
        constructor(obj) {
            this.InstanceId = obj.InstanceId || obj.player_id;
            this.NickName = obj.NickName ?? obj.name ?? "";
            this.Level = obj.Level ?? obj.level ?? 1;
            this.GuildId = obj.GuildId ?? obj.guild_id ?? null;
            this.DetailsLoaded = obj.DetailsLoaded ?? obj.details_loaded ?? false;
            this.HasViewingCage = obj.HasViewingCage;
            this.pals = new Map();
            this.UnlockedRecipeTechnologyNames = obj.UnlockedRecipeTechnologyNames;
            this.TechnologyPoint = obj.TechnologyPoint;
            this.bossTechnologyPoint = obj.bossTechnologyPoint;
            this.PlayerAttributes = obj.PlayerAttributes || [];
            this.Inventory = obj.Inventory || { Capacity: 0, Items: [] };
            this.InventoryContainers = obj.InventoryContainers || [];
        }

        levelDown() {
            if (this.Level > 1) {
                this.Level -= 1;
                updatePlayer({ target: { name: "Level", value: this.Level } });
            }
        }

        levelUp() {
            if (
                this.Level < MAX_LEVEL ||
                (!HIDE_INVALID_OPTIONS.value && this.Level < MAX_INVALID_LEVEL)
            ) {
                this.Level += 1;
                updatePlayer({ target: { name: "Level", value: this.Level } });
            }
        }

        maxLevel() {
            this.Level = HIDE_INVALID_OPTIONS.value
                ? MAX_LEVEL
                : MAX_INVALID_LEVEL;
            updatePlayer({ target: { name: "Level", value: this.Level } });
        }

        toggleTech(tech, status) {
            updatePlayer({
                target: {
                    name: "toggle_UnlockedRecipeTechnologyNames",
                    value: {
                        tech: tech,
                        status: status,
                    },
                },
            });
        }
    }

    class PalData {
        constructor(obj) {
            this.InstanceId = obj.InstanceId;
            this.OwnerPlayerUId = obj.OwnerPlayerUId;
            this.group_id = obj.group_id;
            this.SlotIndex = obj.SlotIndex;
            this.OwnerName = obj.OwnerName;
            this.CharacterID = obj.CharacterID;
            this.IconAccessKey = obj.IconAccessKey;
            this.DataAccessKey = obj.DataAccessKey;
            this.DataAccessKeyOG = obj.DataAccessKey;
            this.I18nName = obj.I18nName;
            this.DisplayName = obj.DisplayName;
            this.NickName = obj.NickName;
            this.Gender = obj.Gender;
            this.Level = obj.Level;
            this.FriendshipLevel = Math.max(
                MIN_FRIENDSHIP_LEVEL,
                obj.FriendshipLevel ?? MIN_FRIENDSHIP_LEVEL,
            );

            this.HasBaseVariant = obj.HasBaseVariant;
            this.HasBossVariant = obj.HasBossVariant;
            this.HasTowerVariant = obj.HasTowerVariant;
            this.HasWorkerSick = obj.HasWorkerSick;
            this.IsFaintedPal = obj.IsFaintedPal;
            this.Is_Unref_Pal = obj.Is_Unref_Pal;
            this.in_owner_palbox = obj.in_owner_palbox;

            this.IsHuman = obj.IsHuman;
            this.NpcDefaultWeapon = obj.NpcDefaultWeapon ?? null;
            this.IsBOSS = obj.IsBOSS;
            this.IsRarePal = obj.IsRarePal;
            this.IsTower = obj.IsTower;
            this.IsRAID = obj.IsRAID;
            this.IsPREDATOR = obj.IsPREDATOR;
            this.IsOilrig = obj.IsOilrig;
            this.IsAwakened = Boolean(obj.IsAwakened);
            this.AwakeningStatusMultiplier = obj.AwakeningStatusMultiplier ?? 1.5;
            this.IsExpeditionPal = obj.IsExpeditionPal;
            this.ExpeditionInstanceId = obj.ExpeditionInstanceId;
            this.ExpeditionAssignmentStatus = obj.ExpeditionAssignmentStatus;
            this.ExpeditionCanComplete = Boolean(obj.ExpeditionCanComplete);

            this.ComputedMaxHP = obj.ComputedMaxHP;
            this.ComputedAttack = obj.ComputedAttack;
            this.ComputedDefense = obj.ComputedDefense;
            this.ComputedCraftSpeed = obj.ComputedCraftSpeed;

            this.Rank = obj.Rank;
            this.Rank_HP = obj.Rank_HP;
            this.Rank_Attack = obj.Rank_Attack;
            this.Rank_Defence = obj.Rank_Defence;
            this.Rank_CraftSpeed = obj.Rank_CraftSpeed;

            this.Talent_HP = obj.Talent_HP;
            this.Talent_Melee = obj.Talent_Melee;
            this.Talent_Shot = obj.Talent_Shot;
            this.Talent_Defense = obj.Talent_Defense;

            this.PassiveSkillList = obj.PassiveSkillList;
            this.EquipWaza = obj.EquipWaza;
            this.MasteredWaza = obj.MasteredWaza;
            this.Suitabilities = obj.Suitabilities;
        }

        displaySpecialType() {
            if (this.IsTower) return getTranslatedText("Variant_Tower");
            if (this.IsBOSS) return getTranslatedText("Variant_Boss");
            if (this.IsRarePal) return getTranslatedText("Variant_Rare");
            if (this.IsRAID) return getTranslatedText("Variant_Raid");
            if (this.IsPREDATOR) return getTranslatedText("Variant_Rampaging");
            if (this.IsOilrig) return getTranslatedText("Variant_OilRig");
            return getTranslatedText("Common_NotApplicable");
        }

        getRank() {
            return this.Rank - 1;
        }

        swapTower() {
            this.IsTower = !this.IsTower;
            updatePal({ target: { name: "IsTower", value: this.IsTower } });
        }

        swapBoss() {
            this.IsBOSS = !this.IsBOSS;
            updatePal({ target: { name: "IsBOSS", value: this.IsBOSS } });
        }

        swapRare() {
            this.IsRarePal = !this.IsRarePal;
            updatePal({ target: { name: "IsRarePal", value: this.IsRarePal } });
        }

        swapAwakening() {
            this.IsAwakened = !this.IsAwakened;
            return updatePal({
                target: { name: "IsAwakened", value: this.IsAwakened },
            });
        }

        levelDown() {
            if (this.Level > 1) {
                this.Level -= 1;
                updatePal({ target: { name: "Level", value: this.Level } });
            }
        }

        levelUp() {
            if (
                this.Level < MAX_LEVEL ||
                (!HIDE_INVALID_OPTIONS.value && this.Level < MAX_INVALID_LEVEL)
            ) {
                this.Level += 1;
                updatePal({ target: { name: "Level", value: this.Level } });
            }
        }

        maxLevel() {
            this.Level = HIDE_INVALID_OPTIONS.value
                ? MAX_LEVEL
                : MAX_INVALID_LEVEL;
            updatePal({ target: { name: "Level", value: this.Level } });
        }

        friendshipLevelDown() {
            if (this.FriendshipLevel > MIN_FRIENDSHIP_LEVEL) {
                this.FriendshipLevel -= 1;
                return updatePal({ target: { name: "FriendshipLevel", value: this.FriendshipLevel } });
            }
        }

        friendshipLevelUp() {
            if (this.FriendshipLevel < MAX_FRIENDSHIP_LEVEL) {
                this.FriendshipLevel += 1;
                return updatePal({ target: { name: "FriendshipLevel", value: this.FriendshipLevel } });
            }
        }

        maxFriendshipLevel() {
            this.FriendshipLevel = MAX_FRIENDSHIP_LEVEL;
            return updatePal({ target: { name: "FriendshipLevel", value: this.FriendshipLevel } });
        }

        displayGender() {
            if (this.Gender == "EPalGenderType::Female") {
                return "♀️";
            } else if (this.Gender == "EPalGenderType::Male") {
                return "♂️";
            } else {
                return "";
            }
        }

        swapGender() {
            let gender = HIDE_INVALID_OPTIONS.value ? "NONE" : "EPalGenderType::Female";
            if (this.Gender == "EPalGenderType::Female") {
                gender = "EPalGenderType::Male";
            }
            if (this.Gender == "EPalGenderType::Male") {
                gender = "EPalGenderType::Female";
            }
            updatePal({ target: { name: "Gender", value: gender } });
        }

        pop_PassiveSkillList(e) {
            const skill = e.currentTarget?.name || e.target?.name;
            updatePal({
                target: {
                    name: "pop_PassiveSkillList",
                    value: skill,
                },
            });
        }

        add_PassiveSkillList(skill = PAL_PASSIVE_SELECTED_ITEM.value) {
            if (!PASSIVE_SKILLS.value[skill]) {
                alert("Select a skill first!");
                return;
            }
            if (this.isEquippedPassiveSkill(skill)) {
                return;
            }
            if (
                HIDE_INVALID_OPTIONS.value &&
                this.PassiveSkillList.length >= 4
            ) {
                alert("you can't add more than 4 passive skills");
                return;
            }
            updatePal({
                target: {
                    name: "add_PassiveSkillList",
                    value: skill,
                },
            });
        }

        replacePassiveSkills(skills) {
            updatePal({
                target: {
                    name: "replace_PassiveSkillList",
                    value: [...skills],
                },
            });
        }

        isEquippedPassiveSkill(skill) {
            return this.PassiveSkillList.includes(skill);
        }

        isEquippedSkill(skill) {
            return this.EquipWaza.includes(skill);
        }

        isMasteredSkill(skill) {
            return this.MasteredWaza.includes(skill);
        }

        isEquipSkillFull() {
            return this.EquipWaza.length >= 3;
        }

        pop_EquipWaza(e) {
            const skill = e.currentTarget?.name || e.target?.name;
            updatePal({
                target: {
                    name: "pop_EquipWaza",
                    value: skill,
                },
            });
        }

        add_EquipWaza(skillOrEvent) {
            const skill = typeof skillOrEvent === "string"
                ? skillOrEvent
                : skillOrEvent.currentTarget?.name || skillOrEvent.target?.name;
            updatePal({
                target: {
                    name: "add_EquipWaza",
                    value: skill,
                },
            });
        }

        pop_MasteredWaza(e) {
            const skill = e.currentTarget?.name || e.target?.name;
            updatePal({
                target: {
                    name: "pop_MasteredWaza",
                    value: skill,
                },
            });
        }

        add_MasteredWaza(skill = PAL_ACTIVE_SELECTED_ITEM.value) {
            if (!ACTIVE_SKILLS.value[skill]) {
                alert("Select a skill first!");
                return;
            }
            if (this.isMasteredSkill(skill)) {
                return;
            }
            updatePal({
                target: {
                    name: "add_MasteredWaza",
                    value: skill,
                },
            });
        }

        suitUp(e) {
            try {
                const name = e.currentTarget.name;
                const value = SELECTED_PAL_DATA.value.Suitabilities[name] + 1;
                this.set_Suitability(name, value);
            } catch (error) {
                console.log(error);
                return;
            }
        }

        suitDown(e) {
            try {
                const name = e.currentTarget.name;
                const value = SELECTED_PAL_DATA.value.Suitabilities[name] - 1;
                this.set_Suitability(name, value);
            } catch (error) {
                console.log(error);
                return;
            }
        }

        suitMax(e) {
            try {
                const name = e.currentTarget.name;
                this.set_Suitability(name, MAX_SUITABILITY_LEVEL.value);
            } catch (error) {
                console.log(error);
                return;
            }
        }

        maxAllSuitabilities() {
            try {
                const baseSuitabilities =
                    PAL_STATIC_DATA.value[SELECTED_PAL_DATA.value.DataAccessKey]
                        ?.Suitabilities || {};
                const updates = {};
                for (const [name, value] of Object.entries(this.Suitabilities || {})) {
                    if (
                        HIDE_INVALID_OPTIONS.value
                        && Number(baseSuitabilities[name] || 0) <= 0
                    ) {
                        continue;
                    }
                    if (Number(value) < MAX_SUITABILITY_LEVEL.value) {
                        updates[name] = MAX_SUITABILITY_LEVEL.value;
                    }
                }
                if (!Object.keys(updates).length) return;
                updatePal({
                    target: {
                        name: "set_AllSuitabilities",
                        value: updates,
                    },
                });
            } catch (error) {
                console.log(error);
            }
        }

        maximumEnhancementPayload() {
            const unrestricted = !HIDE_INVALID_OPTIONS.value;
            const ivMax = unrestricted ? 255 : 100;
            const soulMax = unrestricted ? 255 : MAX_SOULS_LEVEL.value;
            const condensationMax = unrestricted ? 255 : 5;
            const values = {
                iv_hp: ivMax,
                iv_shot: ivMax,
                iv_defense: ivMax,
                soul_hp: soulMax,
                soul_attack: soulMax,
                soul_defense: soulMax,
                soul_craft_speed: soulMax,
                condensation: condensationMax,
            };
            if (unrestricted) {
                values.iv_melee = ivMax;
            }

            return { values };
        }

        areAllEnhancementsMax() {
            const { values } = this.maximumEnhancementPayload();
            const propertyNames = {
                iv_hp: "Talent_HP",
                iv_melee: "Talent_Melee",
                iv_shot: "Talent_Shot",
                iv_defense: "Talent_Defense",
                soul_hp: "Rank_HP",
                soul_attack: "Rank_Attack",
                soul_defense: "Rank_Defence",
                soul_craft_speed: "Rank_CraftSpeed",
                condensation: "Rank",
            };
            return Object.entries(values).every(
                ([name, maximum]) =>
                    Number(this[propertyNames[name]] || 0) >= Number(maximum),
            );
        }

        maxAllEnhancements() {
            if (this.areAllEnhancementsMax()) return;
            updatePal({
                target: {
                    name: "set_AllEnhancements",
                    value: this.maximumEnhancementPayload(),
                },
            });
        }

        set_Suitability(name, value) {
            const min =
                PAL_STATIC_DATA.value[SELECTED_PAL_DATA.value.DataAccessKey]
                    ?.Suitabilities[name];
            const max = MAX_SUITABILITY_LEVEL.value;
            if (HIDE_INVALID_OPTIONS.value && min == 0 && value != 0) {
                alert(
                    "Invalid suitability level, You can only modify suitabilities that the Pal is capable of."
                );
                return;
            }
            value = Math.min(Math.max(value, min), max);
            if (value == SELECTED_PAL_DATA.value.Suitabilities[name]) {
                return;
            }
            updatePal({
                target: {
                    name: "set_Suitability",
                    value: { name: name, level: value },
                },
            });
        }

        changeSpecie() {
            updatePal({
                target: {
                    name: "CharacterID",
                    value: this.DataAccessKey,
                },
            });
        }
    }

    const PAL_BASE_WORKER_BTN = ref("PAL_BASE_WORKER_BTN");

    const TECH_LV_DICT = ref({});
    const PASSIVE_SKILLS = ref({});
    const PASSIVE_SKILLS_LIST = ref([]);
    const ACTIVE_SKILLS = ref({});
    const ACTIVE_SKILLS_LIST = ref([]);
    const PAL_STATIC_DATA = ref({});
    const PAL_STATIC_DATA_LIST = ref([]);
    const I18nList = ref({});

    const TranslationKeyMap = ref({
        en: enTranslations,
        fr: frTranslations,
        ja: jaTranslations,
        ko: koTranslations,
        "zh-CN": zhCnTranslations,
    });
    const containerTranslationKeys = Object.freeze({
        AUTO: "Common_Automatic",
        PARTY: "Common_Party",
        PAL_STORAGE: "Common_PalStorage",
        COMMON: "Inventory_Container_Common",
        ESSENTIAL: "Inventory_Container_Essential",
        WEAPON_LOADOUT: "Inventory_Container_WeaponLoadout",
        PLAYER_EQUIP_ARMOR: "Inventory_Container_ArmorEquipment",
        FOOD_EQUIP: "Inventory_Container_FoodEquipment",
    });
    const presetKindTranslationKeys = Object.freeze({
        inventory: "PresetKind_Inventory",
        equipment: "PresetKind_Equipment",
        skills: "PresetKind_Skills",
        pal: "PresetKind_Pal",
    });

    // flags
    const LOADING_FLAG = ref(false);
    const SAVE_LOADED_FLAG = ref(false);
    const HAS_WORKING_PAL_FLAG = ref(false);
    const BASE_PAL_BTN_CLK_FLAG = ref(false);
    const SHOW_PLAYER_EDIT_FLAG = ref(false);
    // const ADD_PAL_RESELECT_CTR = ref(0);
    // const DEL_PAL_RESELECT_CTR = ref(0)
    const UPDATE_PAL_RESELECT_CTR = ref(0);
    const SHOW_UNREF_PAL_FLAG = ref(false);
    const SHOW_OOB_PAL_FLAG = ref(true);
    const HIDE_INVALID_OPTIONS = ref(true);

    const PAL_LIST_SEARCH_KEYWORD = ref("");
    const PAL_QUERY_ORDER = ref([]);
    const PAL_QUERY_ACTIVE = ref(false);

    const IS_PAL_SAVE_PATH = ref(false);

    // data
    const BASE_PAL_MAP = ref(new Map());
    const PLAYER_MAP = ref(new Map());
    const GUILD_TREE = ref([]);
    const PAL_PASSIVE_SELECTED_ITEM = ref("");
    const PAL_ACTIVE_SELECTED_ITEM = ref("");

    // display data
    const SELECTED_PAL_DATA = ref(new Map());
    const SELECTED_PLAYER_DATA = ref(new Map());
    const PAL_MAP = ref(new Map());
    const EXPEDITION_PAL_COUNT = computed(() =>
        Array.from(PAL_MAP.value.values()).filter(pal => pal.IsExpeditionPal).length
    );
    const COMPLETABLE_EXPEDITION_COUNT = computed(() => new Set(
        Array.from(PAL_MAP.value.values())
            .filter(pal => pal.ExpeditionCanComplete && pal.ExpeditionInstanceId)
            .map(pal => pal.ExpeditionInstanceId)
    ).size);

    // selected id
    const SELECTED_PLAYER_ID = ref(null);
    const SELECTED_BASE_KEY = ref(null);
    const SELECTED_BASE_DATA = ref(null);
    const SELECTED_PAL_ID = ref(null);
    const BULK_PLAYER_IDS = ref([]);
    const BULK_PAL_IDS = ref([]);

    // TODO Get rid of this...
    // let SELECTED_PAL_EL = null;

    // Configs
    const VERSION = ref("0.0.0");
    const IS_OFFICIAL_BUILD = ref(false);
    const AVAILABLE_UPDATE = ref(null);
    const I18n = ref(localStorage.getItem("PAL_I18n"));
    const PAL_GAME_SAVE_PATH = ref(localStorage.getItem("PAL_GAME_SAVE_PATH"));
    const HAS_PASSWORD = ref(false);
    const PAL_WRITE_BACK_PATH = ref("");
    const SAVE_SOURCE_MODE = ref(getInitialSaveSourceMode());
    watch(SAVE_SOURCE_MODE, (mode) => {
        if (mode === "steam" || mode === "xgp") {
            localStorage.setItem(SAVE_SOURCE_MODE_STORAGE_KEY, mode);
        }
    }, { immediate: true });
    const XGP_WGS_PATH = ref("");
    const XGP_SOURCES = ref([]);
    const SELECTED_XGP_SOURCE_ID = ref(null);
    const SAVE_PLATFORM = ref("steam");
    const SOURCE_ID = ref(null);
    const SOURCE_DISPLAY_NAME = ref("");
    const SAVE_CAPABILITIES = ref({
        commitOriginal: true,
        exportSteamCopy: true,
        targetPathEditable: true,
        cloudSyncVerified: false,
    });
    const XGP_SAVE_CONFIRMED = ref(false);
    const PATH_CONTEXT = ref(new Map());
    const SESSION_ID = ref(null);
    const SESSION_REVISION = ref(0);
    const PENDING_CHANGE_COUNT = ref(0);
    const SAVE_COMPATIBILITY = ref(null);
    const LAST_ERROR = ref(null);
    const LAST_SAVE_RESULT = ref(null);
    const ITEM_CATALOG_RESULTS = ref([]);
    let lastItemCatalogSearch = null;
    const ITEM_CLIPBOARD = ref(null);
    const PLAYER_MISSIONS = ref({
        missions: [],
        summary: null,
        warnings: [],
        writable: false,
        source: null,
    });
    const MISSION_LOADING = ref(false);

    const SHOW_FILE_PICKER = ref(false);
    const PAL_FILE_PICKER_PATH = ref(PAL_GAME_SAVE_PATH.value);
    const FILE_PICKER_PURPOSE = ref("steam");

    // auth
    let auth_token = "";
    const IS_LOCKED = ref(true);

    async function GET(api) {
        try {
            const response = await axios.get(api, {
                headers: {
                    Authorization: "Bearer " + auth_token,
                },
            });

            return response.data;
        } catch (error) {
            if (error.response) {
                return error.response.data || {
                    status: 1,
                    msg: error.response.statusText + ": " + error.response.status,
                };
            } else if (error.request) {
                alert(
                    `no response from the backend, make sure it is running, error: ${error.request}`
                );
                return false;
            } else {
                alert(`get(): ${error.message}`);
                return false;
            }
        }
    }

    async function POST(api, data) {
        try {
            const response = await axios.post(api, data, {
                headers: { Authorization: "Bearer " + auth_token },
            });

            return response.data;
        } catch (error) {
            if (error.response) {
                return error.response.data || {
                    status: 1,
                    msg: error.response.statusText + ": " + error.response.status,
                };
            } else if (error.request) {
                alert(
                    `no response from the backend, make sure it is running, error: ${error.request}`
                );
                return false;
            } else {
                alert(`post(): ${error.message}`);
                return false;
            }
        }
    }

    async function PATCH(api, data) {
        try {
            const response = await axios.patch(api, data, {
                headers: { Authorization: "Bearer " + auth_token },
            });

            return response.data;
        } catch (error) {
            if (error.response) {
                return error.response.data || {
                    status: 1,
                    msg: error.response.statusText + ": " + error.response.status,
                };
            } else if (error.request) {
                alert(
                    `no response from the backend, make sure it is running, error: ${error.request}`
                );
                return false;
            } else {
                alert(`patch(): ${error.message}`);
                return false;
            }
        }
    }

    async function DELETE(api, data = undefined) {
        try {
            const response = await axios.delete(api, {
                headers: { Authorization: "Bearer " + auth_token },
                data,
            });

            return response.data;
        } catch (error) {
            if (error.response) {
                return error.response.data || {
                    status: 1,
                    msg: error.response.statusText + ": " + error.response.status,
                };
            } else if (error.request) {
                alert(
                    `no response from the backend, make sure it is running, error: ${error.request}`
                );
                return false;
            } else {
                alert(`patch(): ${error.message}`);
                return false;
            }
        }
    }

    function responseRevision(data) {
        return data?.revision ?? data?.change?.revision_after ?? null;
    }

    function acceptResponse(response, context, { command = false } = {}) {
        if (!response || response.status !== 0) {
            const errorCode = response?.error?.code || "REQUEST_FAILED";
            const messageKey = errorCode.startsWith("WGS_") ? errorCode : null;
            const localizedMessage = messageKey
                ? getTranslatedText(messageKey)
                : response?.msg || "The operation failed.";
            LAST_ERROR.value = {
                context,
                message: localizedMessage,
                messageKey,
                code: errorCode,
                details: response?.error?.details || {},
                retryable: Boolean(response?.error?.retryable),
            };
            return false;
        }
        LAST_ERROR.value = null;
        const revision = responseRevision(response.data);
        if (Number.isInteger(revision)) {
            if (command && revision > SESSION_REVISION.value) {
                PENDING_CHANGE_COUNT.value += revision - SESSION_REVISION.value;
            }
            SESSION_REVISION.value = revision;
        }
        return true;
    }

    function applySessionState(data) {
        const session = data.session;
        SESSION_ID.value = session.session_id;
        SESSION_REVISION.value = session.revision;
        PENDING_CHANGE_COUNT.value = session.pending_change_count;
        SAVE_COMPATIBILITY.value = data.compatibility;
        SAVE_PLATFORM.value = session.platform || "steam";
        SAVE_SOURCE_MODE.value = SAVE_PLATFORM.value;
        SOURCE_ID.value = session.sourceId || null;
        SOURCE_DISPLAY_NAME.value = session.sourceDisplayName || "";
        SAVE_CAPABILITIES.value = session.saveCapabilities || {};
        LAST_ERROR.value = null;

        if (SAVE_PLATFORM.value === "steam") {
            const sourcePath = session.source || PAL_GAME_SAVE_PATH.value;
            PAL_GAME_SAVE_PATH.value = sourcePath;
            PAL_WRITE_BACK_PATH.value = sourcePath;
            if (sourcePath) localStorage.setItem("PAL_GAME_SAVE_PATH", sourcePath);
        } else {
            SELECTED_XGP_SOURCE_ID.value = SOURCE_ID.value;
            PAL_WRITE_BACK_PATH.value = SOURCE_DISPLAY_NAME.value;
        }
    }

    async function loadSessionState(data) {
        applySessionState(data);
        await loadPlayers();
        if (IS_LOCKED.value || !SESSION_ID.value) return false;
        await fetchStaticData();
        if (IS_LOCKED.value || !SESSION_ID.value) return false;
        SAVE_LOADED_FLAG.value = true;
        return true;
    }

    async function resumeCurrentSession() {
        const ownsLoadingFlag = !LOADING_FLAG.value;
        reset();
        if (ownsLoadingFlag) LOADING_FLAG.value = true;
        try {
            const response = await GET("/api/save/session");
            if (response === false) return false;
            if (response.status === 0) return await loadSessionState(response.data);
            if (response?.error?.code === "SESSION_NOT_FOUND") {
                LAST_ERROR.value = null;
                return false;
            }
            if (response.status === 2) {
                IS_LOCKED.value = true;
                reset();
                return false;
            }
            acceptResponse(response, "resume-session");
            return false;
        } finally {
            if (ownsLoadingFlag) LOADING_FLAG.value = false;
        }
    }

    async function refreshSessionMetadata() {
        if (!SESSION_ID.value) return false;
        const response = await GET(
            `/api/save/session?session_id=${encodeURIComponent(SESSION_ID.value)}`
        );
        if (!acceptResponse(response, "refresh-session")) return false;
        SESSION_REVISION.value = response.data.session.revision;
        PENDING_CHANGE_COUNT.value = response.data.session.pending_change_count;
        SAVE_COMPATIBILITY.value = response.data.compatibility;
        return true;
    }

    async function auth() {
        let no_set_loading_flag = LOADING_FLAG.value;
        if (!no_set_loading_flag) LOADING_FLAG.value = true;

        const response = await GET("/api/auth/auth");
        if (response === false) return false;

        if (response.status == 0) {
            IS_LOCKED.value = false;
        } else {
            IS_LOCKED.value = true;
            reset();
        }

        if (!no_set_loading_flag) LOADING_FLAG.value = false;
        return response.status == 0;
    }

    async function login(e) {
        let no_set_loading_flag = LOADING_FLAG.value;
        if (!no_set_loading_flag) LOADING_FLAG.value = true;

        const response = await POST("/api/auth/login", {
            password: e.target.value,
        });
        if (response === false) return false;

        if (response.status == 0) {
            IS_LOCKED.value = false;
            auth_token = response.data.access_token;
        } else if (response.status == 2) {
            alert("Wrong Password, Try Again.");
            IS_LOCKED.value = true;
            reset();
        } else {
            alert(`- login - Error occured: ${response.msg}`);
        }

        if (!no_set_loading_flag) LOADING_FLAG.value = false;
        return response.status == 0;
    }

    async function fetch_config() {
        let no_set_loading_flag = LOADING_FLAG.value;
        if (!no_set_loading_flag) LOADING_FLAG.value = true;

        const response = await GET("/api/save/fetch_config");
        if (response === false) return;

        if (response.status == 0) {
            I18nList.value = response.data.I18nList;
            if (!I18n.value || !I18nList.value[I18n.value]) {
                I18n.value = response.data.I18n;
            }
            // TranslationKeyMap[I18n.value] = await import(`../i18n/${I18n.value}.js`)
            if (!PAL_GAME_SAVE_PATH.value) {
                PAL_GAME_SAVE_PATH.value = response.data.Path;
            }
            HAS_PASSWORD.value = response.data.HasPassword;
            VERSION.value = response.data.VERSION;
            IS_OFFICIAL_BUILD.value = response.data.IsOfficialBuild;
            MAX_SOULS_LEVEL.value = response.data.MaxSoulsLevel;
            MAX_SUITABILITY_LEVEL.value = response.data.MaxSuitabilityLevel ?? 10;
        } else if (response.status == 2) {
            alert("Unauthorized Access, Please Login. ");
            IS_LOCKED.value = true;
            reset();
        } else {
            alert(`- fetch_config - Error occured: ${response.msg}`);
        }

        if (!no_set_loading_flag) LOADING_FLAG.value = false;
    }

    function update_path_picker_result(data) {
        IS_PAL_SAVE_PATH.value = data.isPalDir;
        PAL_FILE_PICKER_PATH.value = data.currentPath;
        PATH_CONTEXT.value = new Map(Object.entries(data.children));
        SHOW_FILE_PICKER.value = true;
    }

    async function show_file_picker(purpose = SAVE_SOURCE_MODE.value) {
        let no_set_loading_flag = LOADING_FLAG.value;
        if (!no_set_loading_flag) LOADING_FLAG.value = true;
        FILE_PICKER_PURPOSE.value = purpose === "xgp" ? "xgp" : "steam";

        const nativePicker = window.pywebview?.api?.select_save_directory;
        if (nativePicker) {
            try {
                const selectedPath = await nativePicker(
                    FILE_PICKER_PURPOSE.value === "xgp"
                        ? XGP_WGS_PATH.value
                        : PAL_GAME_SAVE_PATH.value
                );
                if (!selectedPath) {
                    if (!no_set_loading_flag) LOADING_FLAG.value = false;
                    return;
                }

                if (FILE_PICKER_PURPOSE.value === "xgp") {
                    XGP_WGS_PATH.value = selectedPath;
                    PAL_FILE_PICKER_PATH.value = selectedPath;
                    SHOW_FILE_PICKER.value = false;
                    await discoverXgpSources(selectedPath);
                    if (!no_set_loading_flag) LOADING_FLAG.value = false;
                    return;
                }

                const nativeResponse = await POST("/api/save/path", {
                    path: selectedPath,
                });
                if (nativeResponse === false) {
                    if (!no_set_loading_flag) LOADING_FLAG.value = false;
                    return;
                }

                if (nativeResponse.status == 0 && nativeResponse.data.isPalDir) {
                    PAL_GAME_SAVE_PATH.value = nativeResponse.data.currentPath;
                    PAL_FILE_PICKER_PATH.value = nativeResponse.data.currentPath;
                    IS_PAL_SAVE_PATH.value = true;
                    SHOW_FILE_PICKER.value = false;
                } else if (nativeResponse.status == 2) {
                    alert("Unauthorized Access, Please Login. ");
                    IS_LOCKED.value = true;
                    reset();
                } else {
                    alert(getTranslatedText("EntryView_Invalid_Save_Path"));
                }
                if (!no_set_loading_flag) LOADING_FLAG.value = false;
                return;
            } catch (error) {
                console.error("Native save directory picker failed, using web picker.", error);
            }
        }

        let response = undefined;
        if (FILE_PICKER_PURPOSE.value === "xgp") {
            response = await POST("/api/save/browse-directory", {
                path: XGP_WGS_PATH.value || PAL_GAME_SAVE_PATH.value || undefined,
            });
            if (!response || response.status !== 0) {
                response = await POST("/api/save/browse-directory", {});
            }
        } else if (PAL_GAME_SAVE_PATH.value) {
            response = await POST("/api/save/path", {
                path: PAL_GAME_SAVE_PATH.value,
            });
            if (response.status != 0) {
                PAL_GAME_SAVE_PATH.value = undefined;
                localStorage.removeItem("PAL_GAME_SAVE_PATH");
                response = await GET("/api/save/path");
            }
        } else {
            response = await GET("/api/save/path");
        }

        if (response === false) return;

        if (response.status == 0) {
            update_path_picker_result(response.data);
        } else if (response.status == 2) {
            alert("Unauthorized Access, Please Login. ");
            IS_LOCKED.value = true;
            reset();
        } else {
            alert(`- show_file_picker - Error occured: ${response.msg}`);
        }

        if (!no_set_loading_flag) LOADING_FLAG.value = false;
    }

    async function path_back() {
        let no_set_loading_flag = LOADING_FLAG.value;
        if (!no_set_loading_flag) LOADING_FLAG.value = true;

        const response = FILE_PICKER_PURPOSE.value === "xgp"
            ? await POST("/api/save/browse-directory", {
                path: PAL_FILE_PICKER_PATH.value,
                parent: true,
            })
            : await PATCH("/api/save/path");

        if (response === false) return;

        if (response.status == 0) {
            update_path_picker_result(response.data);
        } else if (response.status == 2) {
            alert("Unauthorized Access, Please Login. ");
            IS_LOCKED.value = true;
            reset();
        } else {
            alert(`- show_file_picker - Error occured: ${response.msg}`);
        }

        if (!no_set_loading_flag) LOADING_FLAG.value = false;
    }

    async function update_picker_result(path) {
        let no_set_loading_flag = LOADING_FLAG.value;
        if (!no_set_loading_flag) LOADING_FLAG.value = true;

        const response = await POST(
            FILE_PICKER_PURPOSE.value === "xgp"
                ? "/api/save/browse-directory"
                : "/api/save/path",
            { path }
        );

        if (response === false) return;

        if (response.status == 0) {
            update_path_picker_result(response.data);
        } else if (response.status == 2) {
            alert("Unauthorized Access, Please Login. ");
            IS_LOCKED.value = true;
            reset();
        } else {
            alert(`- show_file_picker - Error occured: ${response.msg}`);
        }

        if (!no_set_loading_flag) LOADING_FLAG.value = false;
    }

    async function updateI18n() {
        let no_set_loading_flag = LOADING_FLAG.value;
        if (!no_set_loading_flag) LOADING_FLAG.value = true;

        const response = await PATCH("/api/save/i18n", { I18n: I18n.value });
        if (response === false) return;

        if (response.status == 0) {
            localStorage.setItem("PAL_I18n", I18n.value);
            const refreshes = [];
            // if on pal editor panel, refresh all translated texts (except for hardcoded ui)
            if (SAVE_LOADED_FLAG.value) {
                PLAYER_MAP.value.forEach((player, playerUId) => {
                    refreshes.push(fetchPlayerPal(playerUId));
                });
                refreshes.push(fetchPlayerPal(
                    PAL_BASE_WORKER_BTN.value,
                    SELECTED_BASE_DATA.value
                ));
                if (SELECTED_PLAYER_ID.value && SESSION_ID.value) {
                    refreshes.push(loadInventory(SELECTED_PLAYER_ID.value));
                    refreshes.push(loadPlayerMissions(SELECTED_PLAYER_ID.value));
                }
            }
            if (lastItemCatalogSearch !== null) {
                refreshes.push(searchItemCatalog(
                    lastItemCatalogSearch.query,
                    lastItemCatalogSearch.containerType
                ));
            }
            if (!IS_LOCKED.value) refreshes.push(fetchStaticData());
            await Promise.all(refreshes);
            syncSelectedPalLocalization();
            syncLastErrorLocalization();
        } else if (response.status == 2) {
            alert("Unauthorized Access, Please Login. ");
            IS_LOCKED.value = true;
            reset();
        } else {
            alert(`- updateI18n - Error occured: ${response.msg}`);
        }
        if (!no_set_loading_flag) LOADING_FLAG.value = false;
    }

    async function fetchStaticData() {
        let no_set_loading_flag = LOADING_FLAG.value;
        if (!no_set_loading_flag) LOADING_FLAG.value = true;
        const passive_skills_raw = await GET("/api/save/passive_skills");
        if (passive_skills_raw === false) return;

        if (passive_skills_raw.status == 0) {
            PASSIVE_SKILLS.value = passive_skills_raw.data.dict;
            PASSIVE_SKILLS_LIST.value = passive_skills_raw.data.arr;
        } else if (passive_skills_raw.status == 2) {
            IS_LOCKED.value = true;
            reset();
        } else {
            alert(
                `- fetchStaticData:passive_skill - Error occured: ${passive_skills_raw.msg}`
            );
        }

        const active_skills_raw = await GET("/api/save/active_skills");
        if (active_skills_raw === false) return;

        if (active_skills_raw.status == 0) {
            ACTIVE_SKILLS.value = active_skills_raw.data.dict;
            ACTIVE_SKILLS_LIST.value = active_skills_raw.data.arr;
        } else if (active_skills_raw.status == 2) {
            IS_LOCKED.value = true;
            reset();
        } else {
            alert(
                `- fetchStaticData:active_skill - Error occured: ${active_skills_raw.msg}`
            );
        }

        const pal_data_raw = await GET("/api/save/pal_data");
        if (pal_data_raw === false) return;

        if (pal_data_raw.status == 0) {
            PAL_STATIC_DATA.value = pal_data_raw.data.dict;
            PAL_STATIC_DATA_LIST.value = pal_data_raw.data.arr;
        } else if (pal_data_raw.status == 2) {
            IS_LOCKED.value = true;
            reset();
        } else {
            alert(
                `- fetchStaticData:pal_data - Error occured: ${pal_data_raw.msg}`
            );
        }

        const tech_data_raw = await GET("/api/save/tech_data");
        if (tech_data_raw === false) return;

        if (tech_data_raw.status == 0) {
            TECH_LV_DICT.value = tech_data_raw.data.techLvDict;
        } else if (tech_data_raw.status == 2) {
            IS_LOCKED.value = true;
            reset();
        } else {
            alert(
                `- fetchStaticData:tech_data - Error occured: ${tech_data_raw.msg}`
            );
        }
        if (!no_set_loading_flag) LOADING_FLAG.value = false;
    }

    function clearEditorSelection() {
        BASE_PAL_BTN_CLK_FLAG.value = false;
        SHOW_PLAYER_EDIT_FLAG.value = false;
        SELECTED_PLAYER_ID.value = null;
        SELECTED_PLAYER_DATA.value = null;
        SELECTED_BASE_KEY.value = null;
        SELECTED_BASE_DATA.value = null;
        SELECTED_PAL_ID.value = null;
        SELECTED_PAL_DATA.value = null;
        PAL_MAP.value = new Map();
        PLAYER_MISSIONS.value = {
            missions: [],
            summary: null,
            warnings: [],
            writable: false,
            source: null,
        };
    }

    function reset() {
        LOADING_FLAG.value = false;
        HAS_WORKING_PAL_FLAG.value = false;
        SAVE_LOADED_FLAG.value = false;
        clearEditorSelection();
        BULK_PLAYER_IDS.value = [];
        BULK_PAL_IDS.value = [];
        SESSION_ID.value = null;
        SESSION_REVISION.value = 0;
        PENDING_CHANGE_COUNT.value = 0;
        SAVE_COMPATIBILITY.value = null;
        LAST_ERROR.value = null;
        LAST_SAVE_RESULT.value = null;
        SAVE_PLATFORM.value = "steam";
        SOURCE_ID.value = null;
        SOURCE_DISPLAY_NAME.value = "";
        SAVE_CAPABILITIES.value = {
            commitOriginal: true,
            exportSteamCopy: true,
            targetPathEditable: true,
            cloudSyncVerified: false,
        };
        XGP_SAVE_CONFIRMED.value = false;
        ITEM_CATALOG_RESULTS.value = [];
        lastItemCatalogSearch = null;
        ITEM_CLIPBOARD.value = null;
        PLAYER_MISSIONS.value = {
            missions: [],
            summary: null,
            warnings: [],
            writable: false,
            source: null,
        };
        MISSION_LOADING.value = false;

        BASE_PAL_MAP.value = new Map();
        PLAYER_MAP.value = new Map();
        GUILD_TREE.value = [];
        PAL_PASSIVE_SELECTED_ITEM.value = "";
        PAL_ACTIVE_SELECTED_ITEM.value = "";

        PAL_LIST_SEARCH_KEYWORD.value = "";
        PAL_QUERY_ORDER.value = [];
        PAL_QUERY_ACTIVE.value = false;
        SHOW_UNREF_PAL_FLAG.value = false;
        SHOW_OOB_PAL_FLAG.value = true;
        PLAYER_MAP.value.clear();
    }

    async function returnToMain() {
        if (!SESSION_ID.value) {
            reset();
            return true;
        }

        const discardChanges = PENDING_CHANGE_COUNT.value > 0;
        if (
            discardChanges &&
            !window.confirm(
                getTranslatedText("Confirm_DiscardChangesAndReturn", [
                    PENDING_CHANGE_COUNT.value,
                ])
            )
        ) {
            return false;
        }

        const noSetLoadingFlag = LOADING_FLAG.value;
        if (!noSetLoadingFlag) LOADING_FLAG.value = true;
        try {
            const response = await DELETE("/api/save/session", {
                session_id: SESSION_ID.value,
                expected_revision: SESSION_REVISION.value,
                discard_changes: discardChanges,
            });
            if (response === false || !acceptResponse(response, "close-session")) {
                return false;
            }
            reset();
            return true;
        } finally {
            if (!noSetLoadingFlag) LOADING_FLAG.value = false;
        }
    }

    function getTranslatedText(translationKey, args = []) {
        const getTranslation = (i18n, translationKey, args) => {
            const i18nData = TranslationKeyMap.value[i18n];
            let translation = i18nData[translationKey]
            if (!translation) {
                console.warn(
                    `Translation key "${translationKey}" not found in "${i18n}" translations.`
                );
                return "I18N_MISSING";
            }
            for (let i = 0; i < args.length; i++) {
                translation = translation.replace(`{{${i}}}`, args[i]);
                console.log(`Replacing {{${i}}} with ${args[i]} in translation: ${translation}`);
            }
            return translation;
        }

        const I18nKey = TranslationKeyMap.value[I18n.value] ? I18n.value : "en";
        return getTranslation(I18nKey, translationKey, args);
    }

    function getNpcWeaponDisplayName(weapon) {
        const internalName = String(weapon || "-");
        const translationKey = NPC_WEAPON_TRANSLATION_KEYS[internalName];
        if (!translationKey) return internalName;
        const localizedName = getTranslatedText(translationKey);
        if (localizedName === internalName) return internalName;
        return getTranslatedText(
            "PalEditor_NpcWeapon_LocalizedOption",
            [localizedName, internalName]
        );
    }

    function getMappedTranslation(value, translationKeys, unknownKey) {
        const translationKey = translationKeys[value];
        return translationKey
            ? getTranslatedText(translationKey)
            : getTranslatedText(unknownKey, [value]);
    }

    function syncSelectedPalLocalization() {
        const selected = SELECTED_PAL_DATA.value;
        if (!selected || !SELECTED_PAL_ID.value) return;

        const refreshed = PAL_MAP.value.get(SELECTED_PAL_ID.value);
        const previousI18nName = selected.I18nName;
        if (
            refreshed
            && (!selected.NickName || selected.NickName === previousI18nName)
        ) {
            selected.NickName = refreshed.NickName;
        }

        const localizedName = PAL_STATIC_DATA.value[selected.DataAccessKey]?.I18n
            || refreshed?.I18nName;
        if (!localizedName) return;

        selected.I18nName = localizedName;
        if (
            refreshed
            && refreshed.DataAccessKey === selected.DataAccessKey
            && refreshed.NickName === selected.NickName
        ) {
            selected.DisplayName = refreshed.DisplayName;
            return;
        }

        const variantPrefix = `${selected.IsRarePal ? "✨" : ""}${selected.IsBOSS ? "👑" : ""}${selected.IsTower ? "🗼" : ""}`;
        const nicknameSuffix = selected.NickName ? ` (${selected.NickName})` : "";
        selected.DisplayName = `${variantPrefix}${localizedName}${nicknameSuffix}`;
    }

    function syncLastErrorLocalization() {
        const messageKey = LAST_ERROR.value?.messageKey;
        if (messageKey) {
            LAST_ERROR.value.message = getTranslatedText(messageKey);
        }
    }

    async function updatePlayer(e) {
        let no_set_loading_flag = LOADING_FLAG.value;
        if (!no_set_loading_flag) LOADING_FLAG.value = true;

        // sometimes we manually construct a "e" target in a very hacked way
        const target = e.currentTarget || e.target;
        let key = target.name;
        let value = target.value;

        if (SELECTED_PLAYER_ID.value == null) {
            alert("Select a player first!");
            return;
        }

        const base = {
            session_id: SESSION_ID.value,
            expected_revision: SESSION_REVISION.value,
        };
        let payload;
        if (key === "NickName") {
            payload = { ...base, command: "update_player_identity", name: value };
        } else if (["Level", "Exp", "TechnologyPoint", "bossTechnologyPoint"].includes(key)) {
            const field = {
                Level: "level",
                Exp: "experience",
                TechnologyPoint: "technology_points",
                bossTechnologyPoint: "boss_technology_points",
            }[key];
            payload = {
                ...base,
                command: "update_player_progression",
                [field]: Number(value),
            };
        } else if (key === "toggle_UnlockedRecipeTechnologyNames") {
            payload = {
                ...base,
                command: "update_player_technology",
                recipe_id: value.tech,
                unlocked: Boolean(value.status),
            };
        } else if (key === "unlock_all_techs") {
            payload = { ...base, command: "update_player_technology", unlock_all: true };
        } else {
            LAST_ERROR.value = {
                context: "update-player",
                code: "UNSUPPORTED_COMMAND_FIELD",
                message: `Unsupported player field: ${key}`,
                details: { key },
            };
            if (!no_set_loading_flag) LOADING_FLAG.value = false;
            return;
        }

        const response = await POST(
            `/api/player/${encodeURIComponent(SELECTED_PLAYER_ID.value)}/commands`,
            payload
        );
        if (response === false) return false;

        if (acceptResponse(response, "update-player", { command: true })) {
            await loadPlayer(SELECTED_PLAYER_ID.value);
        } else if (response.status == 2) {
            alert("Unauthorized Access, Please Login. ");
            IS_LOCKED.value = true;
            reset();
        } else {
            alert(`- updatePlayer - Error occured: ${response.msg}`);
        }
        if (!no_set_loading_flag) LOADING_FLAG.value = false;
        return response.status == 0;
    }

    async function updatePlayerAttributes(attribute = null) {
        if (!SELECTED_PLAYER_ID.value || !SELECTED_PLAYER_DATA.value) return false;
        const attributes = attribute?.key
            ? [attribute]
            : (SELECTED_PLAYER_DATA.value.PlayerAttributes || []);
        const values = Object.fromEntries(
            attributes.map(item => [
                item.key,
                Number(item.rank),
            ])
        );
        if (!Object.keys(values).length) return false;
        const noSetLoadingFlag = LOADING_FLAG.value;
        if (!noSetLoadingFlag) LOADING_FLAG.value = true;
        try {
            const response = await POST(
                `/api/player/${encodeURIComponent(SELECTED_PLAYER_ID.value)}/commands`,
                {
                    session_id: SESSION_ID.value,
                    expected_revision: SESSION_REVISION.value,
                    command: "update_player_attributes",
                    values,
                }
            );
            if (!acceptResponse(response, "update-player-attributes", { command: true })) {
                return false;
            }
            await loadPlayer(SELECTED_PLAYER_ID.value);
            return true;
        } finally {
            if (!noSetLoadingFlag) LOADING_FLAG.value = false;
        }
    }

    async function discoverXgpSources(path = XGP_WGS_PATH.value) {
        const noSetLoadingFlag = LOADING_FLAG.value;
        if (!noSetLoadingFlag) LOADING_FLAG.value = true;
        try {
            XGP_SOURCES.value = [];
            SELECTED_XGP_SOURCE_ID.value = null;
            if (!path) {
                LAST_ERROR.value = {
                    context: "discover-xgp-sources",
                    code: "WGS_NOT_FOUND",
                    message: getTranslatedText("Entry_Xgp_PathRequired"),
                    messageKey: "Entry_Xgp_PathRequired",
                    details: {},
                    retryable: true,
                };
                return false;
            }
            XGP_WGS_PATH.value = path;
            const response = await POST("/api/save/sources", { path });
            if (!acceptResponse(response, "discover-xgp-sources")) return false;
            const sources = response.data.sources || [];
            if (!sources.length) {
                LAST_ERROR.value = {
                    context: "discover-xgp-sources",
                    code: "WGS_NOT_FOUND",
                    message: getTranslatedText("WGS_NOT_FOUND"),
                    messageKey: "WGS_NOT_FOUND",
                    details: {},
                    retryable: true,
                };
                return false;
            }
            XGP_SOURCES.value = sources;
            return true;
        } finally {
            if (!noSetLoadingFlag) LOADING_FLAG.value = false;
        }
    }

    async function checkForUpdate() {
        AVAILABLE_UPDATE.value = null;
        if (!IS_OFFICIAL_BUILD.value) return false;
        try {
            const response = await GET("/api/save/update");
            if (!response || response.status !== 0 || !response.data?.version) return false;
            AVAILABLE_UPDATE.value = {
                version: response.data.version,
                url: response.data.download_page || response.data.download_gh,
            };
            return true;
        } catch {
            return false;
        }
    }

    function skipUpdate() {
        AVAILABLE_UPDATE.value = null;
    }

    async function loadInventory(playerId = SELECTED_PLAYER_ID.value) {
        if (!playerId || !SESSION_ID.value) return false;
        const response = await GET(
            `/api/player/${encodeURIComponent(playerId)}/inventory?session_id=${encodeURIComponent(SESSION_ID.value)}`
        );
        if (!acceptResponse(response, "load-inventory")) return false;
        const player = PLAYER_MAP.value.get(playerId);
        if (player) player.InventoryContainers = response.data.containers || [];
        if (SELECTED_PLAYER_ID.value === playerId && SELECTED_PLAYER_DATA.value) {
            SELECTED_PLAYER_DATA.value.InventoryContainers = response.data.containers || [];
        }
        return true;
    }

    async function loadPlayerMissions(playerId = SELECTED_PLAYER_ID.value) {
        if (!playerId || !SESSION_ID.value) return false;
        MISSION_LOADING.value = true;
        const params = new URLSearchParams({
            session_id: SESSION_ID.value,
            locale: I18n.value || "en",
        });
        try {
            const response = await GET(
                `/api/player/${encodeURIComponent(playerId)}/missions?${params.toString()}`
            );
            if (!acceptResponse(response, "load-player-missions")) return false;
            if (SELECTED_PLAYER_ID.value === playerId) {
                PLAYER_MISSIONS.value = response.data;
            }
            return true;
        } finally {
            MISSION_LOADING.value = false;
        }
    }

    async function previewMissionCommand(operation, missionIds = []) {
        if (!SELECTED_PLAYER_ID.value || !SESSION_ID.value) return null;
        MISSION_LOADING.value = true;
        try {
            const response = await POST(
                `/api/player/${encodeURIComponent(SELECTED_PLAYER_ID.value)}/missions/preview`,
                {
                    session_id: SESSION_ID.value,
                    expected_revision: SESSION_REVISION.value,
                    operation,
                    mission_ids: missionIds,
                }
            );
            if (!acceptResponse(response, "preview-mission-command")) return null;
            return response.data;
        } finally {
            MISSION_LOADING.value = false;
        }
    }

    async function executeMissionCommand(operation, missionIds, previewToken) {
        if (!SELECTED_PLAYER_ID.value || !SESSION_ID.value) return false;
        MISSION_LOADING.value = true;
        try {
            const response = await POST(
                `/api/player/${encodeURIComponent(SELECTED_PLAYER_ID.value)}/missions/commands`,
                {
                    session_id: SESSION_ID.value,
                    expected_revision: SESSION_REVISION.value,
                    operation,
                    mission_ids: missionIds,
                    preview_token: previewToken,
                }
            );
            if (!acceptResponse(response, "execute-mission-command", { command: true })) {
                return false;
            }
            PENDING_CHANGE_COUNT.value = response.data.pending_change_count;
            await loadPlayerMissions(SELECTED_PLAYER_ID.value);
            return true;
        } finally {
            MISSION_LOADING.value = false;
        }
    }

    async function executeInventoryCommand(containerType, slotIndex, command) {
        let no_set_loading_flag = LOADING_FLAG.value;
        if (!no_set_loading_flag) LOADING_FLAG.value = true;
        const response = await POST(
            `/api/player/${encodeURIComponent(SELECTED_PLAYER_ID.value)}/inventory/commands`,
            {
                session_id: SESSION_ID.value,
                expected_revision: SESSION_REVISION.value,
                container_type: containerType,
                slot_index: slotIndex,
                ...command,
            }
        );
        if (response === false) return false;
        if (acceptResponse(response, "inventory-command", { command: true })) {
            await loadInventory();
        } else if (response.status == 2) {
            alert("Unauthorized Access, Please Login. ");
            IS_LOCKED.value = true;
            reset();
        } else {
            alert(`- updateInventoryItem - Error occured: ${response.msg}`);
        }
        if (!no_set_loading_flag) LOADING_FLAG.value = false;
        return response.status === 0;
    }

    async function updateInventoryItem(container, slot) {
        const count = Number(slot.item?.count);
        if (!Number.isInteger(count) || count < 1 || count > 2147483647) {
            LAST_ERROR.value = {
                context: "inventory-command",
                code: "INVALID_ITEM_COUNT",
                message: "Item count must be an integer between 1 and 2147483647.",
                details: { count },
            };
            return false;
        }
        return executeInventoryCommand(container.container_type, slot.slot_index, {
            command: "update_item_count",
            expected_static_id: slot.item.static_id,
            count,
        });
    }

    async function putInventoryItem(container, slot, staticId, count = 1, dynamicInit = null) {
        const command = {
            command: "put_item",
            static_id: staticId,
            count: Number(count),
            mode: "empty_only",
        };
        if (dynamicInit !== null) command.dynamic_init = dynamicInit;
        return executeInventoryCommand(container.container_type, slot.slot_index, command);
    }

    async function clearInventoryItem(container, slot) {
        return executeInventoryCommand(container.container_type, slot.slot_index, {
            command: "clear_item_slot",
            expected_static_id: slot.item.static_id,
            expected_dynamic_id: slot.item.dynamic_id,
        });
    }

    async function searchItemCatalog(query = "", containerType = null) {
        const params = new URLSearchParams({ q: query });
        if (containerType) params.set("container_type", containerType);
        const response = await GET(`/api/player/item_catalog?${params.toString()}`);
        if (!acceptResponse(response, "search-item-catalog")) return [];
        lastItemCatalogSearch = { query, containerType };
        ITEM_CATALOG_RESULTS.value = response.data.items || [];
        return ITEM_CATALOG_RESULTS.value;
    }

    async function copyInventoryItem(container, slot) {
        const response = await POST(
            `/api/player/${encodeURIComponent(SELECTED_PLAYER_ID.value)}/inventory/copy`,
            {
                session_id: SESSION_ID.value,
                expected_revision: SESSION_REVISION.value,
                container_type: container.container_type,
                slot_index: slot.slot_index,
            }
        );
        if (!acceptResponse(response, "copy-inventory-item")) return false;
        ITEM_CLIPBOARD.value = response.data;
        return true;
    }

    async function executeInventoryLayoutCommand(containerType, command) {
        let no_set_loading_flag = LOADING_FLAG.value;
        if (!no_set_loading_flag) LOADING_FLAG.value = true;
        const response = await POST(
            `/api/player/${encodeURIComponent(SELECTED_PLAYER_ID.value)}/inventory/layout/commands`,
            {
                session_id: SESSION_ID.value,
                expected_revision: SESSION_REVISION.value,
                container_type: containerType,
                ...command,
            }
        );
        if (response !== false && acceptResponse(response, "inventory-layout", { command: true })) {
            ITEM_CLIPBOARD.value = null;
            await loadInventory();
        }
        if (!no_set_loading_flag) LOADING_FLAG.value = false;
        return response !== false && response.status === 0;
    }

    async function pasteInventoryItem(container, slot) {
        if (!ITEM_CLIPBOARD.value?.clipboard_token) return false;
        return executeInventoryLayoutCommand(container.container_type, {
            command: "paste_item_slot",
            slot_index: slot.slot_index,
            clipboard_token: ITEM_CLIPBOARD.value.clipboard_token,
        });
    }

    async function sortInventoryContainer(container, sortBy, descending = false) {
        return executeInventoryLayoutCommand(container.container_type, {
            command: "sort_item_container",
            sort_by: sortBy,
            descending,
        });
    }

    async function fillInventorySlots(container, slotIndices, staticId, count, dynamicInit = null) {
        const command = {
            command: "fill_item_slots",
            slot_indices: slotIndices,
            static_id: staticId,
            count: Number(count),
        };
        if (dynamicInit !== null) command.dynamic_init = dynamicInit;
        return executeInventoryLayoutCommand(container.container_type, command);
    }

    async function loadDynamicItemAttributes(container, slot) {
        const response = await GET(
            `/api/player/${encodeURIComponent(SELECTED_PLAYER_ID.value)}/inventory/` +
            `${encodeURIComponent(container.container_type)}/${slot.slot_index}/dynamic?` +
            `session_id=${encodeURIComponent(SESSION_ID.value)}`
        );
        if (!acceptResponse(response, "load-dynamic-attributes")) return null;
        return response.data;
    }

    async function updateDynamicItemAttributes(container, slot, values) {
        return executeInventoryCommand(container.container_type, slot.slot_index, {
            command: "update_dynamic_attributes",
            expected_static_id: slot.item.static_id,
            expected_dynamic_id: slot.item.dynamic_id,
            values,
        });
    }

    async function exportPreset(kind, targetId) {
        const response = await POST("/api/preset/export", {
            session_id: SESSION_ID.value,
            kind,
            target_id: targetId,
        });
        if (!acceptResponse(response, "export-preset")) return null;
        return response.data.preset;
    }

    async function applyPreset(preset, targetIds) {
        const payload = {
            session_id: SESSION_ID.value,
            expected_revision: SESSION_REVISION.value,
            preset,
            target_ids: targetIds,
        };
        const preview = await POST("/api/preset/preview", payload);
        if (!acceptResponse(preview, "preview-preset")) return false;
        const count = preview.data.impact.operation_count;
        const presetKind = getMappedTranslation(
            preset.kind,
            presetKindTranslationKeys,
            "PresetKind_Unknown"
        );
        if (!window.confirm(getTranslatedText(
            "Confirm_ApplyPreset",
            [presetKind, targetIds.length, count]
        ))) return false;
        const response = await POST("/api/preset/apply", {
            ...payload,
            impact_token: preview.data.impact_token,
        });
        if (!acceptResponse(response, "apply-preset", { command: true })) return false;
        if (["inventory", "equipment"].includes(preset.kind)) {
            await loadInventory();
        } else if (SELECTED_PAL_ID.value) {
            await selectPal(SELECTED_PAL_ID.value, true);
        }
        return true;
    }

    async function maxSelectedPal() {
        if (!SELECTED_PAL_ID.value || !SELECTED_PAL_DATA.value) return false;
        const ownsLoadingFlag = !LOADING_FLAG.value;
        if (ownsLoadingFlag) LOADING_FLAG.value = true;
        try {
            const palId = SELECTED_PAL_ID.value;
            const response = await POST(
                `/api/pal/${encodeURIComponent(palId)}/commands`,
                {
                    session_id: SESSION_ID.value,
                    expected_revision: SESSION_REVISION.value,
                    command: "max_pal",
                    unrestricted: !HIDE_INVALID_OPTIONS.value,
                },
            );
            if (!acceptResponse(response, "max-pal", { command: true })) return false;
            await selectPal(palId, true);
            UPDATE_PAL_RESELECT_CTR.value++;
            return true;
        } finally {
            if (ownsLoadingFlag) LOADING_FLAG.value = false;
        }
    }

    async function executeBatchOperations(
        operations,
        {
            confirmBeforePreview = false,
            trackLoading = false,
            confirmationKey = "Confirm_ApplyAtomicBatch",
            confirmationArgs = null,
        } = {}
    ) {
        if (confirmBeforePreview && !window.confirm(getTranslatedText(
            confirmationKey,
            confirmationArgs || [operations.length]
        ))) return false;

        const ownsLoadingFlag = trackLoading && !LOADING_FLAG.value;
        if (ownsLoadingFlag) LOADING_FLAG.value = true;

        try {
            const payload = {
                session_id: SESSION_ID.value,
                expected_revision: SESSION_REVISION.value,
                operations,
            };
            const preview = await POST("/api/batch/preview", payload);
            if (!acceptResponse(preview, "preview-batch")) return false;
            if (!confirmBeforePreview && !window.confirm(getTranslatedText(
                confirmationKey,
                confirmationArgs || [preview.data.impact.operation_count]
            ))) return false;
            const response = await POST("/api/batch/commands", {
                ...payload,
                impact_token: preview.data.impact_token,
            });
            if (!acceptResponse(response, "execute-batch", { command: true })) return false;
            if (SELECTED_PLAYER_ID.value) await loadInventory();
            if (SELECTED_PAL_ID.value) await selectPal(SELECTED_PAL_ID.value, true);
            return true;
        } finally {
            if (ownsLoadingFlag) LOADING_FLAG.value = false;
        }
    }

    async function healAllPals() {
        const operations = Array.from(PAL_MAP.value.keys(), palId => ({
            resource: "pal",
            command: "update_pal_progression",
            pal_id: palId,
            values: { heal: true },
        }));
        if (!operations.length) return false;
        return executeBatchOperations(operations, {
            confirmBeforePreview: true,
            trackLoading: true,
        });
    }

    async function unlockExpeditionPals() {
        const lockedPals = Array.from(PAL_MAP.value.entries()).filter(
            ([, pal]) => pal.IsExpeditionPal
        );
        const operations = lockedPals.map(([palId]) => ({
            resource: "pal",
            command: "unlock_pal_expedition",
            pal_id: palId,
        }));
        if (!operations.length) return false;
        const statusCounts = { valid: 0, invalid: 0, unknown: 0 };
        for (const [, pal] of lockedPals) {
            const status = pal.ExpeditionAssignmentStatus;
            statusCounts[statusCounts[status] === undefined ? "unknown" : status] += 1;
        }
        const succeeded = await executeBatchOperations(operations, {
            confirmBeforePreview: true,
            trackLoading: true,
            confirmationKey: "Confirm_UnlockExpeditionPals",
            confirmationArgs: [
                lockedPals.length,
                statusCounts.valid,
                statusCounts.invalid,
                statusCounts.unknown,
            ],
        });
        if (succeeded) {
            for (const [, pal] of lockedPals) {
                pal.IsExpeditionPal = false;
                pal.ExpeditionInstanceId = null;
                pal.ExpeditionAssignmentStatus = null;
            }
        }
        return succeeded;
    }

    async function completeActiveExpeditions() {
        if (!COMPLETABLE_EXPEDITION_COUNT.value || !SESSION_ID.value) return false;
        if (!window.confirm(getTranslatedText("Confirm_CompleteActiveExpeditions"))) {
            return false;
        }
        const ownsLoadingFlag = !LOADING_FLAG.value;
        if (ownsLoadingFlag) LOADING_FLAG.value = true;
        try {
            const response = await POST("/api/save/expeditions/commands", {
                session_id: SESSION_ID.value,
                expected_revision: SESSION_REVISION.value,
                command: "complete_active_expeditions",
            });
            if (!acceptResponse(response, "complete-active-expeditions", { command: true })) {
                return false;
            }
            const completedIds = new Set(
                (response.data.value?.expedition_ids || [])
                    .map(value => String(value).toLowerCase())
            );
            for (const pal of PAL_MAP.value.values()) {
                if (completedIds.has(String(pal.ExpeditionInstanceId || "").toLowerCase())) {
                    pal.ExpeditionCanComplete = false;
                }
            }
            if (
                SELECTED_PAL_DATA.value?.ExpeditionInstanceId
                && completedIds.has(
                    String(SELECTED_PAL_DATA.value.ExpeditionInstanceId).toLowerCase()
                )
            ) {
                SELECTED_PAL_DATA.value.ExpeditionCanComplete = false;
            }
            return true;
        } finally {
            if (ownsLoadingFlag) LOADING_FLAG.value = false;
        }
    }

    async function cancelSelectedPalExpedition() {
        const pal = SELECTED_PAL_DATA.value;
        if (!SELECTED_PAL_ID.value || !pal?.IsExpeditionPal) return false;

        const confirmationKey = {
            valid: "Confirm_CancelValidExpedition",
            invalid: "Confirm_CancelInvalidExpedition",
            unknown: "Confirm_CancelUnknownExpedition",
        }[pal.ExpeditionAssignmentStatus] || "Confirm_CancelUnknownExpedition";
        if (!window.confirm(getTranslatedText(
            confirmationKey,
            [pal.ExpeditionInstanceId || "-"]
        ))) return false;

        const ownsLoadingFlag = !LOADING_FLAG.value;
        if (ownsLoadingFlag) LOADING_FLAG.value = true;
        try {
            const response = await POST(
                `/api/pal/${encodeURIComponent(SELECTED_PAL_ID.value)}/commands`,
                {
                    session_id: SESSION_ID.value,
                    expected_revision: SESSION_REVISION.value,
                    command: "unlock_pal_expedition",
                }
            );
            if (!acceptResponse(response, "unlock-pal-expedition", { command: true })) {
                return false;
            }
            pal.IsExpeditionPal = false;
            pal.ExpeditionInstanceId = null;
            pal.ExpeditionAssignmentStatus = null;
            return true;
        } finally {
            if (ownsLoadingFlag) LOADING_FLAG.value = false;
        }
    }

    async function loadPlayer(playerUId, updatePal = false) {
        let no_set_loading_flag = LOADING_FLAG.value;
        if (!no_set_loading_flag) LOADING_FLAG.value = true;

        if (SELECTED_PLAYER_ID.value == null) {
            alert("Select a player first!");
            return;
        }

        const response = await POST("/api/player/player_data", {
            PlayerUId: playerUId,
        });
        if (response === false) return;

        if (response.status == 0) {
            const player_obj = new Player(response.data);
            if (!updatePal && PLAYER_MAP.value.has(playerUId)) {
                player_obj.pals = PLAYER_MAP.value.get(playerUId).pals;
            }

            PLAYER_MAP.value.set(playerUId, player_obj);
            await loadInventory(playerUId);

            const pal_id_bk = SELECTED_PAL_ID.value;
            // const pal_data_bk = SELECTED_PAL_DATA.value;
            await selectPlayer(playerUId, true);

            // player id and pal data never changed so this is safe
            // if (!updatePal) await selectPal({ target: SELECTED_PAL_EL });
            if (!updatePal && pal_id_bk) await selectPal(pal_id_bk, true);
        } else if (response.status == 2) {
            alert("Unauthorized Access, Please Login. ");
            IS_LOCKED.value = true;
            reset();
        } else {
            alert(`- loadPlayer - Error occured: ${response.msg}`);
        }

        if (!no_set_loading_flag) LOADING_FLAG.value = false;
    }

    async function loadPlayers() {
        let no_set_loading_flag = LOADING_FLAG.value;
        if (!no_set_loading_flag) LOADING_FLAG.value = true;

        const params = new URLSearchParams({ session_id: SESSION_ID.value });
        const response = await GET("/api/save/query/players?" + params.toString());
        if (response === false) return;

        if (response.status == 0) {
            HAS_WORKING_PAL_FLAG.value = Boolean(response.data.has_working_pal);
            const next = new Map();
            for (let player of response.data.players || []) {
                let p = new Player(player);
                next.set(p.InstanceId, p);
                // console.log(`Found player: ${p.NickName} - ${p.InstanceId}`);
            }
            PLAYER_MAP.value = next;
            GUILD_TREE.value = response.data.guilds || [];

            if (PLAYER_MAP.value.size <= 0 && !HAS_WORKING_PAL_FLAG) {
                alert("No Player Found in the Gamesave");
            }
        } else if (response.status == 2) {
            alert("Unauthorized Access, Please Login. ");
            IS_LOCKED.value = true;
            reset();
        } else {
            alert(`- loadPlayers - Error occured: ${response.msg}`);
        }

        if (!no_set_loading_flag) LOADING_FLAG.value = false;
    }

    async function queryPlayers(filters = {}) {
        const params = new URLSearchParams({ session_id: SESSION_ID.value });
        for (const [key, value] of Object.entries(filters)) {
            if (value !== null && value !== undefined && value !== "") {
                params.set(key, String(value));
            }
        }
        const response = await GET("/api/save/query/players?" + params.toString());
        if (!acceptResponse(response, "query-players")) return false;
        const next = new Map();
        for (const row of response.data.players || []) {
            const existing = PLAYER_MAP.value.get(row.player_id);
            if (existing) {
                existing.NickName = row.name;
                existing.Level = row.level;
                existing.DetailsLoaded = row.details_loaded;
                next.set(row.player_id, existing);
            } else {
                next.set(row.player_id, new Player(row));
            }
        }
        PLAYER_MAP.value = next;
        GUILD_TREE.value = response.data.guilds || [];
        if (
            SELECTED_PLAYER_ID.value &&
            !PLAYER_MAP.value.has(SELECTED_PLAYER_ID.value)
        ) {
            SELECTED_PLAYER_ID.value = null;
            SELECTED_PLAYER_DATA.value = null;
            SELECTED_PAL_ID.value = null;
            SELECTED_PAL_DATA.value = null;
            PAL_MAP.value = new Map();
            SHOW_PLAYER_EDIT_FLAG.value = false;
        }
        return true;
    }

    async function updateGuildName(guildId, name) {
        if (!SESSION_ID.value || !guildId) return false;
        const normalizedName = typeof name === "string" ? name.trim() : "";
        if (!normalizedName || normalizedName.length > 24) return false;
        const ownsLoadingFlag = !LOADING_FLAG.value;
        if (ownsLoadingFlag) LOADING_FLAG.value = true;
        try {
            const response = await POST(
                `/api/save/guilds/${encodeURIComponent(guildId)}/commands`,
                {
                    session_id: SESSION_ID.value,
                    expected_revision: SESSION_REVISION.value,
                    command: "update_guild_name",
                    name: normalizedName,
                }
            );
            if (!acceptResponse(response, "update-guild-name", { command: true })) {
                return false;
            }
            const updated = GUILD_TREE.value.find(
                guild => String(guild.guild_id) === String(guildId)
            );
            if (updated) updated.name = response.data.value?.name ?? normalizedName;
            return true;
        } finally {
            if (ownsLoadingFlag) LOADING_FLAG.value = false;
        }
    }

    async function queryPals(filters = {}) {
        const params = new URLSearchParams({ session_id: SESSION_ID.value });
        for (const [key, value] of Object.entries(filters)) {
            if (value !== null && value !== undefined && value !== "") {
                params.set(key, String(value));
            }
        }
        const response = await GET("/api/save/query/pals?" + params.toString());
        if (!acceptResponse(response, "query-pals")) return false;
        PAL_QUERY_ORDER.value = (response.data.pals || []).map(pal => pal.pal_id);
        PAL_QUERY_ACTIVE.value = true;
        return true;
    }

    function clearPalQuery() {
        PAL_QUERY_ORDER.value = [];
        PAL_QUERY_ACTIVE.value = false;
    }

    async function loadSave() {
        const requestedMode = SAVE_SOURCE_MODE.value;
        const requestedSourceId = SELECTED_XGP_SOURCE_ID.value;
        reset();
        let no_set_loading_flag = LOADING_FLAG.value;
        if (!no_set_loading_flag) LOADING_FLAG.value = true;

        await updateI18n();

        if (requestedMode === "xgp" && !requestedSourceId) {
            LAST_ERROR.value = {
                context: "load-save",
                code: "WGS_WORLD_AMBIGUOUS",
                message: getTranslatedText("Entry_Xgp_SelectRequired"),
                messageKey: "Entry_Xgp_SelectRequired",
                details: {},
                retryable: true,
            };
            if (!no_set_loading_flag) LOADING_FLAG.value = false;
            return false;
        }
        const response = await POST(
            "/api/save/load",
            requestedMode === "xgp"
                ? { sourceId: requestedSourceId }
                : { ReadPath: PAL_GAME_SAVE_PATH.value }
        );
        if (response === false) {
            if (!no_set_loading_flag) LOADING_FLAG.value = false;
            return false;
        }

        let succeeded = false;
        if (response.status == 0) {
            succeeded = await loadSessionState(response.data);
        } else if (response.status == 2) {
            alert("Unauthorized Access, Please Login. ");
            IS_LOCKED.value = true;
            reset();
        } else {
            alert(`- loadSave - Error occured: ${response.msg}`);
        }
        if (!no_set_loading_flag) LOADING_FLAG.value = false;
        return succeeded;
    }

    async function writeSave() {
        let retval = false;
        let no_set_loading_flag = LOADING_FLAG.value;
        if (!no_set_loading_flag) LOADING_FLAG.value = true;
        if (
            SAVE_PLATFORM.value === "xgp"
            && !XGP_SAVE_CONFIRMED.value
            && !window.confirm(getTranslatedText("Confirm_Xgp_Save"))
        ) {
            if (!no_set_loading_flag) LOADING_FLAG.value = false;
            return false;
        }
        const savePayload = {
            session_id: SESSION_ID.value,
            expected_revision: SESSION_REVISION.value,
        };
        if (SAVE_PLATFORM.value !== "xgp") {
            savePayload.WritePath = PAL_WRITE_BACK_PATH.value;
        }
        const response = await POST("/api/save/save", savePayload);
        if (response === false) return;

        if (response.status == 0) {
            LAST_SAVE_RESULT.value = response.data;
            SESSION_REVISION.value = response.data.revision;
            PENDING_CHANGE_COUNT.value = 0;
            LAST_ERROR.value = null;
            if (SAVE_PLATFORM.value === "xgp") XGP_SAVE_CONFIRMED.value = true;
            const Alert_Successful_Save = SAVE_PLATFORM.value === "xgp"
                ? getTranslatedText("Alert_Xgp_Save_Success", [
                    response.data.backup_path || getTranslatedText("Common_NotApplicable"),
                ])
                : getTranslatedText("Alert_Successful_Save").replace(
                    "{{path}}",
                    PAL_WRITE_BACK_PATH.value
                );
            alert(Alert_Successful_Save);
            retval = true;
        } else if (response.status == 2) {
            alert("Unauthorized Access, Please Login. ");
            IS_LOCKED.value = true;
            reset();
        } else {
            acceptResponse(response, "save");
            alert(`- writeSave - Error occured: ${response.msg}`);
        }
        if (!no_set_loading_flag) LOADING_FLAG.value = false;
        return retval;
    }

    async function exportSteamCopy() {
        const targetPath = window.prompt(getTranslatedText("Prompt_Xgp_Export_Target"));
        if (!targetPath) return false;
        const noSetLoadingFlag = LOADING_FLAG.value;
        if (!noSetLoadingFlag) LOADING_FLAG.value = true;
        try {
            const response = await POST("/api/save/export-steam", {
                targetPath,
                session_id: SESSION_ID.value,
                expected_revision: SESSION_REVISION.value,
            });
            if (!acceptResponse(response, "export-steam-copy")) return false;
            alert(getTranslatedText("Alert_Xgp_Export_Success", [targetPath]));
            return true;
        } finally {
            if (!noSetLoadingFlag) LOADING_FLAG.value = false;
        }
    }

    async function fetchPlayerPal(playerUId, baseScope = null) {
        let no_set_loading_flag = LOADING_FLAG.value;
        if (!no_set_loading_flag) LOADING_FLAG.value = true;
        const payload = {
            PlayerUId: playerUId,
        };
        if (playerUId == PAL_BASE_WORKER_BTN.value && baseScope) {
            if (baseScope.base_id) payload.BaseId = baseScope.base_id;
            if (baseScope.guild_id) payload.GuildId = baseScope.guild_id;
            if (baseScope.guild_kind == "no_guild") payload.NoGuild = true;
            if (baseScope.kind == "unmatched") payload.UnmatchedBase = true;
        }
        const response = await POST("/api/player/player_pals", payload);
        if (response === false) return;

        if (response.status == 0) {
            // get old map
            let map =
                playerUId == PAL_BASE_WORKER_BTN.value
                    ? BASE_PAL_MAP.value
                    : PLAYER_MAP.value.get(playerUId).pals;
            // clear old map
            map.clear();
            // insert new data
            for (let pal of response.data) {
                let pal_data = new PalData(pal);
                map.set(pal_data.InstanceId, pal_data);
                // console.log(
                //   `Pal Loaded: ${pal_data.DisplayName} - ${pal_data.InstanceId}`
                // );
            }
        } else if (response.status == 2) {
            alert("Unauthorized Access, Please Login. ");
            IS_LOCKED.value = true;
            reset();
        } else {
            alert(`- fetchPlayerPal - Error occured: ${response.msg}`);
        }
        if (!no_set_loading_flag) LOADING_FLAG.value = false;
    }

    async function fetchPlayerData(playerUId) {
        let no_set_loading_flag = LOADING_FLAG.value;
        if (!no_set_loading_flag) LOADING_FLAG.value = true;

        if (SELECTED_PLAYER_ID.value == null) {
            alert("Select a player first!");
            return;
        }

        const response = await POST("/api/player/player_data", {
            PlayerUId: playerUId,
        });
        if (response === false) return;

        if (response.status == 0) {
            const player_obj = new Player(response.data);
            if (PLAYER_MAP.value.has(playerUId)) {
                player_obj.pals = PLAYER_MAP.value.get(playerUId).pals;
            }
            PLAYER_MAP.value.set(playerUId, player_obj);
            await loadInventory(playerUId);
        } else if (response.status == 2) {
            alert("Unauthorized Access, Please Login. ");
            IS_LOCKED.value = true;
            reset();
        } else {
            alert(`- fetchPlayerData - Error occured: ${response.msg}`);
        }

        if (!no_set_loading_flag) LOADING_FLAG.value = false;
    }

    async function selectPlayer(
        playerUId,
        manual = false,
        selectDefaultPal = false,
    ) {
        let no_set_loading_flag = LOADING_FLAG.value;
        if (!no_set_loading_flag) LOADING_FLAG.value = true;

        // clear selected playerId
        SELECTED_PLAYER_ID.value = null;
        SELECTED_PLAYER_DATA.value = null;
        SELECTED_BASE_KEY.value = null;
        SELECTED_BASE_DATA.value = null;
        BASE_PAL_BTN_CLK_FLAG.value = false;
        SHOW_PLAYER_EDIT_FLAG.value = false;

        // clear pal selection
        SELECTED_PAL_ID.value = null;
        SELECTED_PAL_DATA.value = null;

        // if data not present
        // need to change this in the future, so the pal list properly refreshes (for add / del pal)
        if (
            (playerUId == PAL_BASE_WORKER_BTN.value &&
                BASE_PAL_MAP.value.size == 0) ||
            (playerUId != PAL_BASE_WORKER_BTN.value &&
                PLAYER_MAP.value.get(playerUId).pals.size == 0)
        ) {
            await fetchPlayerPal(playerUId);
        }

        // set the pal_map
        PAL_MAP.value =
            playerUId == PAL_BASE_WORKER_BTN.value
                ? BASE_PAL_MAP.value
                : PLAYER_MAP.value.get(playerUId).pals;

        // properly setup selected player flag
        if (playerUId == PAL_BASE_WORKER_BTN.value) {
            BASE_PAL_BTN_CLK_FLAG.value = true;
        } else {
            SELECTED_PLAYER_ID.value = playerUId;
            if (!manual) {
                await fetchPlayerData(playerUId);
            }
            SHOW_PLAYER_EDIT_FLAG.value = true;
            SELECTED_PLAYER_DATA.value = PLAYER_MAP.value.get(playerUId);
            await loadPlayerMissions(playerUId);
        }

        if (selectDefaultPal) {
            const firstPalId = getDefaultPalId();
            if (firstPalId) await selectPal(firstPalId);
        }

        if (!no_set_loading_flag) LOADING_FLAG.value = false;
    }

    async function selectBase(guild, base, selectDefaultPal = true) {
        let no_set_loading_flag = LOADING_FLAG.value;
        if (!no_set_loading_flag) LOADING_FLAG.value = true;

        SELECTED_PLAYER_ID.value = null;
        SELECTED_PLAYER_DATA.value = null;
        SHOW_PLAYER_EDIT_FLAG.value = false;
        SELECTED_PAL_ID.value = null;
        SELECTED_PAL_DATA.value = null;
        BASE_PAL_BTN_CLK_FLAG.value = true;

        const scope = {
            ...base,
            guild_id: guild.guild_id,
            guild_kind: guild.kind,
        };
        SELECTED_BASE_KEY.value = base.node_id;
        SELECTED_BASE_DATA.value = scope;
        BASE_PAL_MAP.value.clear();
        await fetchPlayerPal(PAL_BASE_WORKER_BTN.value, scope);
        PAL_MAP.value = BASE_PAL_MAP.value;

        if (selectDefaultPal) {
            const firstPalId = getDefaultPalId();
            if (firstPalId) await selectPal(firstPalId);
        }

        if (!no_set_loading_flag) LOADING_FLAG.value = false;
    }

    async function fetchPalData(player, pal) {
        let no_set_loading_flag = LOADING_FLAG.value;
        if (!no_set_loading_flag) LOADING_FLAG.value = true;

        const response = await POST("/api/pal/paldata", {
            PlayerUId: player,
            InstanceId: pal,
        });
        if (response === false) return;

        if (response.status == 0) {
            // construct new pal
            let pal_data = new PalData(response.data);
            // update the pal from the correct pal container
            if (player == PAL_BASE_WORKER_BTN.value) {
                BASE_PAL_MAP.value.set(pal_data.InstanceId, pal_data);
            } else {
                PLAYER_MAP.value
                    .get(player)
                    .pals.set(pal_data.InstanceId, pal_data);
            }
        } else if (response.status == 2) {
            alert("Unauthorized Access, Please Login. ");
            IS_LOCKED.value = true;
            reset();
        } else {
            alert(`- fetchPlayerPal - Error occured: ${response.msg}`);
        }

        if (!no_set_loading_flag) LOADING_FLAG.value = false;
    }

    async function selectPal(palId, manual = false) {
        let no_set_loading_flag = LOADING_FLAG.value;
        if (!no_set_loading_flag) LOADING_FLAG.value = true;

        if (!manual) {
            // SELECTED_PAL_EL = e.target;
            SELECTED_PAL_DATA.value = null;
            SELECTED_PAL_ID.value = null;
        }

        // set selected pal, and print out debug info
        let palData = PAL_MAP.value.get(palId);
        if (palData == null) {
            alert("Failed selecting pal, try again or reload");
            if (!no_set_loading_flag) LOADING_FLAG.value = false;
            return;
        }
        // console.log(`Pal ${palData.DisplayName} - ${palData.InstanceId} selected.`);

        await fetchPalData(
            // get player id, or BASE INDICATION STR
            GET_PAL_OWNER_API_ID(),
            palId
        );

        // Update selected pal id and pal data
        SELECTED_PAL_DATA.value = PAL_MAP.value.get(palId);
        SELECTED_PAL_ID.value = SELECTED_PAL_DATA.value.InstanceId;
        SHOW_PLAYER_EDIT_FLAG.value = false;

        // Scroll to selected pal
        // if (!isElementInViewport(SELECTED_PAL_EL)) {
        //   SELECTED_PAL_EL.scrollIntoView({ behavior: "smooth" });
        // }
        if (!no_set_loading_flag) LOADING_FLAG.value = false;
    }

    function isElementInViewport(el) {
        const rect = el.getBoundingClientRect();
        return (
            rect.top >= 0 &&
            rect.left >= 0 &&
            rect.bottom <=
                (window.innerHeight || document.documentElement.clientHeight) &&
            rect.right <=
                (window.innerWidth || document.documentElement.clientWidth)
        );
    }

    async function updatePal(e) {
        let no_set_loading_flag = LOADING_FLAG.value;
        if (!no_set_loading_flag) LOADING_FLAG.value = true;

        // sometimes we manually construct a "e" target in a very hacked way
        const target = e.currentTarget || e.target;
        let key = target.name;
        let value = target.value;

        if (!SELECTED_PAL_ID.value || !SELECTED_PAL_DATA.value) {
            LAST_ERROR.value = {
                context: "update-pal",
                code: "PAL_NOT_SELECTED",
                message: "Select a Pal first.",
                details: {},
            };
            if (!no_set_loading_flag) LOADING_FLAG.value = false;
            return;
        }
        const base = {
            session_id: SESSION_ID.value,
            expected_revision: SESSION_REVISION.value,
        };
        let endpoint = `/api/pal/${encodeURIComponent(SELECTED_PAL_ID.value)}/commands`;
        let payload;
        if (["NickName", "Gender", "CharacterID", "IsBOSS", "IsTower", "IsRarePal"].includes(key)) {
            const fields = {
                NickName: ["name", value],
                Gender: ["gender", {
                    "EPalGenderType::Male": "male",
                    "EPalGenderType::Female": "female",
                    NONE: "none",
                }[value] || value],
                CharacterID: ["variant", value],
                IsBOSS: ["boss", Boolean(value)],
                IsTower: ["tower", Boolean(value)],
                IsRarePal: ["rare", Boolean(value)],
            };
            const [field, fieldValue] = fields[key];
            payload = { ...base, command: "update_pal_identity", [field]: fieldValue };
        } else if (["Level", "Exp", "FriendshipLevel", "Hp", "FullStomach"].includes(key)) {
            const field = {
                Level: "level",
                Exp: "experience",
                FriendshipLevel: "friendship_level",
                Hp: "health",
                FullStomach: "satiety",
            }[key];
            payload = {
                ...base,
                command: "update_pal_progression",
                values: { [field]: Number(value) },
            };
        } else if (["HasWorkerSick", "IsFaintedPal"].includes(key)) {
            payload = {
                ...base,
                command: "update_pal_progression",
                values: { heal: true },
            };
        } else if (key === "set_AllEnhancements") {
            payload = {
                ...base,
                command: "update_pal_enhancement",
                values: Object.fromEntries(
                    Object.entries(value.values || {}).map(([name, level]) => [
                        name,
                        Number(level),
                    ]),
                ),
            };
        } else if ([
            "Talent_HP", "Talent_Melee", "Talent_Shot", "Talent_Defense",
            "Rank_HP", "Rank_Attack", "Rank_Defence", "Rank_CraftSpeed", "Rank",
            "IsAwakened",
        ].includes(key)) {
            const field = {
                Talent_HP: "iv_hp",
                Talent_Melee: "iv_melee",
                Talent_Shot: "iv_shot",
                Talent_Defense: "iv_defense",
                Rank_HP: "soul_hp",
                Rank_Attack: "soul_attack",
                Rank_Defence: "soul_defense",
                Rank_CraftSpeed: "soul_craft_speed",
                Rank: "condensation",
                IsAwakened: "awakening",
            }[key];
            payload = {
                ...base,
                command: "update_pal_enhancement",
                values: { [field]: key === "IsAwakened" ? Boolean(value) : Number(value) },
            };
        } else if (["set_Suitability", "set_AllSuitabilities"].includes(key)) {
            payload = {
                ...base,
                command: "update_pal_enhancement",
                work_suitability: key === "set_Suitability"
                    ? { [value.name]: Number(value.level) }
                    : Object.fromEntries(
                        Object.entries(value).map(([name, level]) => [name, Number(level)]),
                    ),
            };
        } else if ([
            "add_PassiveSkillList", "pop_PassiveSkillList", "replace_PassiveSkillList", "add_EquipWaza",
            "pop_EquipWaza", "add_MasteredWaza", "pop_MasteredWaza",
        ].includes(key)) {
            const active = [...(SELECTED_PAL_DATA.value.EquipWaza || [])];
            const mastered = [...(SELECTED_PAL_DATA.value.MasteredWaza || [])];
            const passive = [...(SELECTED_PAL_DATA.value.PassiveSkillList || [])];
            if (key === "add_PassiveSkillList") passive.push(value);
            if (key === "pop_PassiveSkillList") {
                const index = passive.indexOf(value);
                if (index >= 0) passive.splice(index, 1);
            }
            if (key === "replace_PassiveSkillList") passive.splice(0, passive.length, ...value);
            if (key === "add_EquipWaza") {
                if (!active.includes(value)) active.push(value);
                if (!mastered.includes(value)) mastered.push(value);
            }
            if (key === "pop_EquipWaza") {
                const index = active.indexOf(value);
                if (index >= 0) active.splice(index, 1);
            }
            if (key === "add_MasteredWaza") {
                if (!mastered.includes(value)) mastered.push(value);
                if (active.length < 3 && !active.includes(value)) active.push(value);
            }
            if (key === "pop_MasteredWaza") {
                const masteredIndex = mastered.indexOf(value);
                if (masteredIndex >= 0) mastered.splice(masteredIndex, 1);
                const activeIndex = active.indexOf(value);
                if (activeIndex >= 0) active.splice(activeIndex, 1);
            }
            payload = {
                ...base,
                command: "update_pal_skills",
                // Passive skill edits must not re-submit the Pal's active skill
                // sets. Older saves can contain an equipped skill that is not
                // present in MasteredWaza; revalidating those unrelated fields
                // makes passive add/remove fail with ACTIVE_SKILL_NOT_MASTERED.
                active: key.includes("Passive") ? null : active,
                mastered: key.includes("Passive") ? null : mastered,
                passive,
            };
        } else if (key === "in_owner_palbox") {
            endpoint = "/api/pal/structural/commands";
            payload = {
                ...base,
                command: SELECTED_PAL_DATA.value.Is_Unref_Pal
                    ? "recover_detached_pal"
                    : "move_pal",
                pal_id: SELECTED_PAL_ID.value,
                target_player_id: SELECTED_PLAYER_ID.value,
                container_type: "AUTO",
            };
        } else {
            LAST_ERROR.value = {
                context: "update-pal",
                code: "UNSUPPORTED_COMMAND_FIELD",
                message: `Unsupported Pal field: ${key}`,
                details: { key },
            };
            if (!no_set_loading_flag) LOADING_FLAG.value = false;
            return;
        }

        if (endpoint === "/api/pal/structural/commands" && payload.command === "move_pal") {
            const preview = await POST("/api/pal/structural/preview", payload);
            if (!acceptResponse(preview, "preview-move-pal")) {
                if (!no_set_loading_flag) LOADING_FLAG.value = false;
                return;
            }
            const destination = preview.data.impact.destination;
            const container = getMappedTranslation(
                destination.container_type,
                containerTranslationKeys,
                "Inventory_Container_Unknown"
            );
            if (!window.confirm(getTranslatedText(
                "Confirm_MovePal",
                [container, destination.slot_index]
            ))) {
                if (!no_set_loading_flag) LOADING_FLAG.value = false;
                return;
            }
            payload.impact_token = preview.data.impact_token;
        }

        const response = await POST(endpoint, payload);
        if (response === false) return;

        if (acceptResponse(response, "update-pal", { command: true })) {
            // A hack way to trigger vue re-rendering.
            // The object is simply too nested that I can't figure out how to have vue properly refresh.
            await selectPal(SELECTED_PAL_ID.value, true);
            UPDATE_PAL_RESELECT_CTR.value++;
        } else if (response.status == 2) {
            alert("Unauthorized Access, Please Login. ");
            IS_LOCKED.value = true;
            reset();
        } else {
            alert(`- updatePal - Error occured: ${response.msg}`);
        }
        if (!no_set_loading_flag) LOADING_FLAG.value = false;
    }

    function GET_PAL_OWNER_API_ID() {
        return BASE_PAL_BTN_CLK_FLAG.value
            ? PAL_BASE_WORKER_BTN.value
            : SELECTED_PLAYER_ID.value;
    }

    async function dumpPalData() {
        let no_set_loading_flag = LOADING_FLAG.value;
        if (!no_set_loading_flag) LOADING_FLAG.value = true;

        const response = await POST("/api/pal/dump_data", {
            PlayerUId: GET_PAL_OWNER_API_ID(),
            PalGuid: SELECTED_PAL_ID.value,
        });

        if (response === false) return;

        if (response.status == 0) {
            const data = response.data;
            await navigator.clipboard.writeText(data);
            alert(getTranslatedText("Alert_PalDataCopied"));
            window.open("https://jsonformatter.curiousconcept.com/");
        } else if (response.status == 2) {
            alert("Unauthorized Access, Please Login. ");
            IS_LOCKED.value = true;
            reset();
        } else {
            alert(`- updatePal - Error occured: ${response.msg}`);
        }

        if (!no_set_loading_flag) LOADING_FLAG.value = false;
    }

    function isFilteredPal(pal) {
        if (
            PAL_QUERY_ACTIVE.value &&
            !PAL_QUERY_ORDER.value.includes(pal.InstanceId)
        ) {
            return true;
        }
        if (!SHOW_UNREF_PAL_FLAG.value && pal.Is_Unref_Pal) {
            return true;
        }
        if (SHOW_UNREF_PAL_FLAG.value && !pal.Is_Unref_Pal) {
            return true;
        }

        // if (SHOW_OOB_PAL_FLAG.value && pal.in_owner_palbox) {
        //   return true
        // }

        if (!SHOW_OOB_PAL_FLAG.value && !pal.in_owner_palbox) {
            return true;
        }

        if (
            PAL_LIST_SEARCH_KEYWORD.value &&
            !pal.DisplayName.toLowerCase().includes(
                PAL_LIST_SEARCH_KEYWORD.value.toLowerCase()
            )
        ) {
            return true;
        }

        return false;
    }

    function getDefaultPalId() {
        const visiblePals = Array.from(PAL_MAP.value.values()).filter(
            (pal) => !isFilteredPal(pal)
        );
        return sortPalList(visiblePals, PAL_LIST_SORT_MODES.CONTAINER)[0]?.InstanceId;
    }

    function getNextElement(map, currKey) {
        let found = false;
        let firstElement = null;
        let isFirstElement = true;
        for (let [key, value] of map) {
            if (isFirstElement) {
                firstElement = { key, value }; // Store the first element
                isFirstElement = false || isFilteredPal(value);
            }
            if (found) {
                if (isFilteredPal(value)) continue;
                return { key, value };
            }
            if (key == currKey) {
                found = true;
            }
        }
        return firstElement;
    }

    async function delPal() {
        let no_set_loading_flag = LOADING_FLAG.value;
        if (!no_set_loading_flag) LOADING_FLAG.value = true;

        const preview = await POST(
            `/api/pal/${encodeURIComponent(SELECTED_PAL_ID.value)}/delete-preview`,
            {
                session_id: SESSION_ID.value,
                expected_revision: SESSION_REVISION.value,
            }
        );
        if (!acceptResponse(preview, "preview-delete-pal")) {
            if (!no_set_loading_flag) LOADING_FLAG.value = false;
            return false;
        }
        const impact = preview.data.impact;
        const referenceCount =
            (impact.container_references?.length || 0) +
            (impact.owner_references?.length || 0) +
            (impact.group_references?.length || 0);
        const confirmed = window.confirm(getTranslatedText(
            "Confirm_DeletePal",
            [referenceCount]
        ));
        if (!confirmed) {
            if (!no_set_loading_flag) LOADING_FLAG.value = false;
            return false;
        }
        const response = await POST("/api/pal/structural/commands", {
            session_id: SESSION_ID.value,
            expected_revision: SESSION_REVISION.value,
            command: "delete_pal",
            pal_id: SELECTED_PAL_ID.value,
            impact_token: preview.data.impact_token,
        });

        if (response === false) return;

        if (acceptResponse(response, "delete-pal", { command: true })) {
            const nextNode = getNextElement(
                PAL_MAP.value,
                SELECTED_PAL_ID.value
            );
            PAL_MAP.value.delete(SELECTED_PAL_DATA.value.InstanceId);
            SELECTED_PAL_ID.value = null;
            // SELECTED_PAL_EL = null;
            SELECTED_PAL_DATA.value = null;
            // ADD_PAL_RESELECT_CTR.value++;
            if (nextNode) {
                SELECTED_PAL_ID.value = nextNode.key;
            }
        } else if (response.status == 2) {
            alert("Unauthorized Access, Please Login. ");
            IS_LOCKED.value = true;
            reset();
        } else {
            alert(`- delPal - Error occured: ${response.msg}`);
        }

        if (!no_set_loading_flag) LOADING_FLAG.value = false;
        return response.status === 0;
    }

    async function addPal(speciesId = "SheepBall", containerType = "AUTO", options = {}) {
        let no_set_loading_flag = LOADING_FLAG.value;
        if (!no_set_loading_flag) LOADING_FLAG.value = true;
        const PlayerUId = GET_PAL_OWNER_API_ID();
        if (PlayerUId == PAL_BASE_WORKER_BTN.value) {
            alert("Adding pals to basecamp is unsupported!");
            return;
        }
        const response = await POST("/api/pal/structural/commands", {
            session_id: SESSION_ID.value,
            expected_revision: SESSION_REVISION.value,
            command: "add_pal",
            player_id: PlayerUId,
            species_id: speciesId,
            container_type: containerType,
            passive: Array.isArray(options.passive) ? [...options.passive] : null,
            max_pal: Boolean(options.maxPal),
            max_work: Boolean(options.maxWork),
            unrestricted: !HIDE_INVALID_OPTIONS.value,
        });

        if (response === false) return;

        if (acceptResponse(response, "add-pal", { command: true })) {
            const palId = response.data.pal.pal_id;
            await fetchPlayerPal(PlayerUId);
            SHOW_PLAYER_EDIT_FLAG.value = false;
            await selectPal(palId);
        } else if (response.status == 2) {
            alert("Unauthorized Access, Please Login. ");
            IS_LOCKED.value = true;
            reset();
        } else {
            alert(`- delPal - Error occured: ${response.msg}`);
        }

        if (!no_set_loading_flag) LOADING_FLAG.value = false;
        return response.status === 0;
    }

    async function dupePal(containerType = "AUTO") {
        let no_set_loading_flag = LOADING_FLAG.value;
        if (!no_set_loading_flag) LOADING_FLAG.value = true;
        const PlayerUId = GET_PAL_OWNER_API_ID();
        if (PlayerUId == PAL_BASE_WORKER_BTN.value) {
            alert("Adding pals to basecamp is unsupported!");
            return;
        }
        const payload = {
            session_id: SESSION_ID.value,
            expected_revision: SESSION_REVISION.value,
            command: "clone_pal",
            target_player_id: PlayerUId,
            source_pal_id: SELECTED_PAL_ID.value,
            container_type: containerType,
        };
        const preview = await POST("/api/pal/structural/preview", payload);
        if (!acceptResponse(preview, "preview-clone-pal")) {
            if (!no_set_loading_flag) LOADING_FLAG.value = false;
            return false;
        }
        const destination = preview.data.impact.destination;
        const container = getMappedTranslation(
            destination.container_type,
            containerTranslationKeys,
            "Inventory_Container_Unknown"
        );
        if (!window.confirm(getTranslatedText(
            "Confirm_ClonePal",
            [container, destination.slot_index]
        ))) {
            if (!no_set_loading_flag) LOADING_FLAG.value = false;
            return false;
        }
        payload.impact_token = preview.data.impact_token;
        const response = await POST("/api/pal/structural/commands", payload);

        if (response === false) return;

        if (acceptResponse(response, "clone-pal", { command: true })) {
            const palId = response.data.pal.pal_id;
            await fetchPlayerPal(PlayerUId);
            await selectPal(palId);
        } else if (response.status == 2) {
            alert("Unauthorized Access, Please Login. ");
            IS_LOCKED.value = true;
            reset();
        } else {
            alert(`- delPal - Error occured: ${response.msg}`);
        }

        if (!no_set_loading_flag) LOADING_FLAG.value = false;
        return response.status === 0;
    }

    function displayPalElement(DataAccessKey) {
        const els = PAL_STATIC_DATA.value[DataAccessKey]?.Elements;
        if (!els) return;

        let str = "";
        for (let e of els) {
            str += displayElement(e);
        }
        return str;
    }

    function displayElement(element) {
        const elementEmojis = {
            Water: "💧",
            Fire: "🔥",
            Dragon: "🐉",
            Grass: "☘️",
            Ground: "🪨",
            Ice: "❄️",
            Electric: "⚡",
            Neutral: "🔵",
            Dark: "🌑",
        };
        return elementEmojis[element] || "";
    }

    function skillIcon(atk) {
        if (ACTIVE_SKILLS.value[atk]?.IsUniqueSkill) return "✨";
        if (ACTIVE_SKILLS.value[atk]?.HasSkillFruit) return "🍐";
        return "";
    }

    function displayRating(rating) {
        if (!rating) return "";
        if (rating == 4) return "🟢";
        if (rating >= 2) return "🟡";
        if (rating < 0) return "🔴";
        return "⚪";
    }

    return {
        MAX_LEVEL,
        MAX_INVALID_LEVEL,
        MAX_SOULS_LEVEL,
        MAX_SUITABILITY_LEVEL,
        MIN_FRIENDSHIP_LEVEL,
        MAX_FRIENDSHIP_LEVEL,

        PAL_PASSIVE_SELECTED_ITEM,
        PAL_ACTIVE_SELECTED_ITEM,
        PAL_BASE_WORKER_BTN,
        PLAYER_MAP,
        GUILD_TREE,
        PAL_MAP,
        EXPEDITION_PAL_COUNT,
        COMPLETABLE_EXPEDITION_COUNT,
        SELECTED_PLAYER_ID,
        SELECTED_PLAYER_DATA,
        SELECTED_BASE_KEY,
        SELECTED_BASE_DATA,
        SELECTED_PAL_ID,
        SELECTED_PAL_DATA,
        BULK_PLAYER_IDS,
        BULK_PAL_IDS,
        LOADING_FLAG,
        SAVE_LOADED_FLAG,
        // ADD_PAL_RESELECT_CTR,
        UPDATE_PAL_RESELECT_CTR,
        SHOW_UNREF_PAL_FLAG,
        SHOW_OOB_PAL_FLAG,
        HIDE_INVALID_OPTIONS,

        PAL_LIST_SEARCH_KEYWORD,
        PAL_QUERY_ORDER,
        PAL_QUERY_ACTIVE,

        IS_LOCKED,
        HAS_PASSWORD,

        PATH_CONTEXT,
        SHOW_FILE_PICKER,
        PAL_FILE_PICKER_PATH,
        IS_PAL_SAVE_PATH,
        FILE_PICKER_PURPOSE,

        SHOW_PLAYER_EDIT_FLAG,
        HAS_WORKING_PAL_FLAG,
        BASE_PAL_BTN_CLK_FLAG,
        PAL_GAME_SAVE_PATH,
        PAL_WRITE_BACK_PATH,
        SAVE_SOURCE_MODE,
        XGP_WGS_PATH,
        XGP_SOURCES,
        SELECTED_XGP_SOURCE_ID,
        SAVE_PLATFORM,
        SOURCE_ID,
        SOURCE_DISPLAY_NAME,
        SAVE_CAPABILITIES,
        SESSION_ID,
        SESSION_REVISION,
        PENDING_CHANGE_COUNT,
        SAVE_COMPATIBILITY,
        LAST_ERROR,
        LAST_SAVE_RESULT,
        ITEM_CATALOG_RESULTS,
        ITEM_CLIPBOARD,
        PLAYER_MISSIONS,
        MISSION_LOADING,
        VERSION,
        IS_OFFICIAL_BUILD,
        AVAILABLE_UPDATE,
        I18n,
        I18nList,
        PAL_STATIC_DATA,
        PAL_STATIC_DATA_LIST,
        PASSIVE_SKILLS,
        PASSIVE_SKILLS_LIST,
        ACTIVE_SKILLS,
        ACTIVE_SKILLS_LIST,
        TECH_LV_DICT,

        getTranslatedText,
        getNpcWeaponDisplayName,

        isElementInViewport,
        isFilteredPal,

        displayPalElement,
        displayElement,
        skillIcon,
        displayRating,

        reset,
        clearEditorSelection,
        returnToMain,
        updateI18n,
        loadSave,
        resumeCurrentSession,
        queryPlayers,
        updateGuildName,
        queryPals,
        clearPalQuery,
        selectPlayer,
        selectBase,
        selectPal,
        updatePal,
        updatePlayer,
        updatePlayerAttributes,
        updateInventoryItem,
        putInventoryItem,
        clearInventoryItem,
        loadInventory,
        loadPlayerMissions,
        previewMissionCommand,
        executeMissionCommand,
        searchItemCatalog,
        copyInventoryItem,
        pasteInventoryItem,
        sortInventoryContainer,
        fillInventorySlots,
        loadDynamicItemAttributes,
        updateDynamicItemAttributes,
        exportPreset,
        applyPreset,
        maxSelectedPal,
        executeBatchOperations,
        healAllPals,
        completeActiveExpeditions,
        unlockExpeditionPals,
        cancelSelectedPalExpedition,
        refreshSessionMetadata,
        writeSave,
        exportSteamCopy,
        discoverXgpSources,
        fetch_config,
        checkForUpdate,
        skipUpdate,
        dumpPalData,
        delPal,
        addPal,
        dupePal,

        login,
        auth,
        show_file_picker,
        update_picker_result,
        path_back
    };
});
