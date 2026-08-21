import { ref, computed, reactive, nextTick, watch } from "vue";
import { defineStore } from "pinia";
import axios from "axios";
import enTranslations from "../i18n/en.js";
import frTranslations from "../i18n/fr.js";
import jaTranslations from "../i18n/ja.js";
import koTranslations from "../i18n/ko.js";
import zhCnTranslations from "../i18n/zh-CN.js";
import { PAL_LIST_SORT_MODES, sortPalList } from "../components/modules/pal-list-sort.js";
import {
    confirmMessage,
    promptMessage,
    showMessage,
} from "../services/message-dialog.js";

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
const SKIP_UPDATE_CHECK_STORAGE_KEY = "PAL_SKIP_UPDATE_CHECK";
const REMOTE_SERVER_ADDRESS_STORAGE_KEY = "PAL_REMOTE_SERVER_ADDRESS";
const REMOTE_CERTIFICATE_FINGERPRINT_STORAGE_KEY =
    "PAL_REMOTE_CERTIFICATE_FINGERPRINT";
const REMOTE_ALLOW_INSECURE_LOCAL_STORAGE_KEY =
    "PAL_REMOTE_ALLOW_INSECURE_LOCAL";
const MAX_UNRESTRICTED_PASSIVE_SKILLS = 255;
const LEGACY_ALERT_MESSAGE_KEYS = Object.freeze({
    "Wrong Password, Try Again.": "MessageDialog_LoginFailed",
    "Unauthorized Access, Please Login.": "MessageDialog_Unauthorized",
    "Select a skill first!": "MessageDialog_SelectSkill",
    "Select a player first!": "MessageDialog_SelectPlayer",
    "No Player Found in the Gamesave": "MessageDialog_NoPlayers",
    "Adding pals to basecamp is unsupported!": "MessageDialog_BasePalUnsupported",
    "Failed selecting pal, try again or reload": "MessageDialog_SelectionFailed",
});
const LEGACY_OPERATION_MESSAGE_KEYS = Object.freeze({
    login: "MessageDialog_LoginFailed",
    fetch_config: "MessageDialog_SettingsFailed",
    updateI18n: "MessageDialog_SettingsFailed",
    show_file_picker: "MessageDialog_PathBrowseFailed",
    loadSave: "MessageDialog_LoadFailed",
    loadPlayer: "MessageDialog_LoadFailed",
    loadPlayers: "MessageDialog_LoadFailed",
    fetchPlayerPal: "MessageDialog_LoadFailed",
    fetchPlayerData: "MessageDialog_LoadFailed",
    fetchStaticData: "MessageDialog_LoadFailed",
    writeSave: "MessageDialog_SaveFailed",
    updatePlayer: "MessageDialog_ChangeFailed",
    updateInventoryItem: "MessageDialog_ChangeFailed",
    updatePal: "MessageDialog_ChangeFailed",
    delPal: "MessageDialog_ChangeFailed",
});
const REMOTE_ERROR_MESSAGE_KEYS = Object.freeze({
    LOCAL_BRIDGE_NOT_FOUND: "Remote_LocalBridgeNotFound",
});
const FOG_CLEAR_CONFIRMATION = "清除迷雾";
const FOG_RESET_CONFIRMATION = "重新覆盖未探索迷雾";
const FAST_TRAVEL_UNLOCK_CONFIRMATION = "解锁所有传送点";
const LOCALIZED_SAVE_ERROR_CODES = new Set([
    "BACKUP_FAILED",
    "FAST_TRAVEL_CATALOG_MISMATCH",
    "FAST_TRAVEL_CONFIRMATION_REQUIRED",
    "FAST_TRAVEL_FIELD_MISSING",
    "FAST_TRAVEL_RECORD_DATA_MISSING",
    "FAST_TRAVEL_RECORD_DATA_UNSUPPORTED",
    "FAST_TRAVEL_STRUCTURE_UNSUPPORTED",
    "FOG_OF_WAR_CLEAR_CONFIRMATION_REQUIRED",
    "FOG_OF_WAR_CONFIRMATION_REQUIRED",
    "FOG_OF_WAR_STRUCTURE_UNSUPPORTED",
    "LOCAL_DATA_NOT_SELECTED",
    "LOCAL_DATA_PATH_REQUIRED",
    "LOCAL_DATA_PATH_NOT_ABSOLUTE",
    "LOCAL_DATA_FILE_REQUIRED",
    "LOCAL_DATA_WGS_SLOT_MISSING",
    "LOCAL_DATA_SELECTION_REQUIRES_CLEAN_SESSION",
    "LOCAL_DATA_STORAGE_UNSUPPORTED",
    "WGS_LOCAL_DATA_EXTERNAL_UNSUPPORTED",
    "EXTERNAL_LOCAL_DATA_TARGET_UNSUPPORTED",
    "LOCAL_DATA_MISSING",
    "LOCAL_DATA_UNREADABLE",
    "PLAYER_INVENTORY_CAPACITY_UNSUPPORTED",
    "PLAYER_INVENTORY_CAPACITY_MAXIMUM_REACHED",
    "PLAYER_INVENTORY_SLOTNUM_UNSUPPORTED",
    "PLAYER_INVENTORY_CONTAINER_MISSING",
    "PLAYER_INVENTORY_SHRINK_UNSUPPORTED",
    "INVALID_PLAYER_INVENTORY_CAPACITY",
    "SAVE_TARGET_CHANGED",
    "NETWORK_NO_RESPONSE",
    "CLIENT_REQUEST_FAILED",
    "CHARACTER_INDEX_INVARIANT_FAILED",
    "CHARACTER_REFERENCE_REPAIR_FAILED",
    "CHARACTER_REFERENCE_REPAIR_UNAVAILABLE",
]);
const SAVE_ERROR_ACTION_KEYS = Object.freeze({
    BACKUP_FAILED: "Save_Backup_Failure_Action",
    WGS_BACKUP_FAILED: "Save_Backup_Failure_Action",
    WGS_GAME_RUNNING: "Save_Wgs_Running_Action",
    SAVE_TARGET_CHANGED: "Save_Source_Changed_Action",
    WGS_SOURCE_CHANGED: "Save_Source_Changed_Action",
    NETWORK_NO_RESPONSE: "Save_Network_No_Response_Action",
    CLIENT_REQUEST_FAILED: "Save_Client_Request_Failed_Action",
});
const SAVE_ERROR_CATEGORY_ACTION_KEYS = Object.freeze({
    path_too_long: "Save_Backup_Path_Too_Long_Action",
});

function getInitialSaveSourceMode() {
    const mode = localStorage.getItem(SAVE_SOURCE_MODE_STORAGE_KEY);
    return ["steam", "xgp", "remote"].includes(mode) ? mode : "steam";
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
            this.PlayerConsumableBonuses = obj.PlayerConsumableBonuses || {
                available: false,
                reason: "PLAYER_CONSUMABLE_BONUS_FIELD_MISSING",
                reduce_only: false,
                values: [],
            };
            this.FastTravelUnlockCapability =
                obj.FastTravelUnlockCapability || {
                    available: false,
                    reason: "FAST_TRAVEL_RECORD_DATA_MISSING",
                    format: null,
                    unlocked_count: null,
                    total_count: 0,
                };
            this.InventoryCapacityCapability =
                obj.InventoryCapacityCapability || {
                    available: false,
                    reason: "PLAYER_INVENTORY_CONTAINER_MISSING",
                    current_capacity: null,
                    allowed_capacities: [],
                    minimum_capacity: null,
                    maximum_capacity: 1000,
                    custom_input: true,
                    expand_only: false,
                };
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
            this.ContainerType = obj.ContainerType ?? "OTHER";

            this.IsHuman = obj.IsHuman;
            this.NpcDefaultWeapon = obj.NpcDefaultWeapon ?? null;
            this.IsBOSS = obj.IsBOSS;
            this.IsRarePal = obj.IsRarePal;
            this.IsTower = obj.IsTower;
            this.IsRAID = obj.IsRAID;
            this.IsPREDATOR = obj.IsPREDATOR;
            this.IsOilrig = obj.IsOilrig;
            this.IsAwakened = Boolean(obj.IsAwakened);
            this.IsImportedCharacter = Boolean(obj.IsImportedCharacter);
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

        removeImportedCharacterTag() {
            return updatePal({
                target: { name: "RemoveImportedCharacterTag", value: true },
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

        pop_PassiveSkillList(skillOrEvent, index = null) {
            const skill = typeof skillOrEvent === "string"
                ? skillOrEvent
                : skillOrEvent?.currentTarget?.name || skillOrEvent?.target?.name;
            updatePal({
                target: {
                    name: "pop_PassiveSkillList",
                    value: Number.isInteger(index) ? { skill, index } : skill,
                },
            });
        }

        add_PassiveSkillList(skill = PAL_PASSIVE_SELECTED_ITEM.value) {
            if (!PASSIVE_SKILLS.value[skill]) {
                alert("Select a skill first!");
                return;
            }
            if (HIDE_INVALID_OPTIONS.value && this.isEquippedPassiveSkill(skill)) {
                return;
            }
            if (
                HIDE_INVALID_OPTIONS.value &&
                this.PassiveSkillList.length >= 4
            ) {
                alert(getTranslatedText("MessageDialog_PassiveSkillLimit", [4]));
                return;
            }
            if (this.PassiveSkillList.length >= MAX_UNRESTRICTED_PASSIVE_SKILLS) {
                alert(getTranslatedText("MessageDialog_PassiveSkillLimit", [
                    MAX_UNRESTRICTED_PASSIVE_SKILLS,
                ]));
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

        async add_MasteredWaza(skill = PAL_ACTIVE_SELECTED_ITEM.value) {
            const skillData = ACTIVE_SKILLS.value[skill];
            if (!skillData) {
                alert("Select a skill first!");
                return;
            }
            if (this.isMasteredSkill(skill)) {
                return;
            }
            if (
                skillData.IsUniqueSkill &&
                !await confirmMessage(
                    getTranslatedText(
                        "Confirm_AddUniqueActiveSkill",
                        [skillData.I18n?.[0] || skill]
                    )
                )
            ) {
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
                alert(getTranslatedText("MessageDialog_InvalidSuitability"));
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
    const GUILD_LIST = ref([]);
    const GUILD_LOADING = ref(false);
    const BASE_STORAGE_BY_BASE = ref({});
    const BASE_STORAGE_LOADING = ref({});
    const PAL_PASSIVE_SELECTED_ITEM = ref("");
    const PAL_ACTIVE_SELECTED_ITEM = ref("");

    // display data
    const SELECTED_PAL_DATA = ref(new Map());
    const SELECTED_PLAYER_DATA = ref(new Map());
    const PAL_MAP = ref(new Map());
    const EXPEDITION_DATA = ref(null);
    const EXPEDITION_LOADING = ref(false);
    const EXPEDITION_PAL_COUNT = computed(() => (
        EXPEDITION_DATA.value?.locked_count
        ?? Array.from(PAL_MAP.value.values()).filter(pal => pal.IsExpeditionPal).length
    ));
    const COMPLETABLE_EXPEDITION_COUNT = computed(() => (
        EXPEDITION_DATA.value?.completable_count
        ?? new Set(
            Array.from(PAL_MAP.value.values())
                .filter(pal => pal.ExpeditionCanComplete && pal.ExpeditionInstanceId)
                .map(pal => pal.ExpeditionInstanceId)
        ).size
    ));

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
    const SKIP_UPDATE_CHECK = ref(
        localStorage.getItem(SKIP_UPDATE_CHECK_STORAGE_KEY) === "true"
    );
    watch(SKIP_UPDATE_CHECK, (skip) => {
        localStorage.setItem(SKIP_UPDATE_CHECK_STORAGE_KEY, String(skip));
        if (skip) AVAILABLE_UPDATE.value = null;
    });
    const I18n = ref(localStorage.getItem("PAL_I18n"));
    const PAL_GAME_SAVE_PATH = ref(localStorage.getItem("PAL_GAME_SAVE_PATH"));
    const GLOBAL_PALBOX_PATH = ref(
        localStorage.getItem("PAL_GLOBAL_PALBOX_PATH") || ""
    );
    const GLOBAL_PALBOX_SOURCE_MODE = ref(
        localStorage.getItem("PAL_GLOBAL_PALBOX_SOURCE_MODE") === "xgp"
            ? "xgp"
            : "steam"
    );
    const GLOBAL_PALBOX_XGP_PATH = ref(
        localStorage.getItem("PAL_GLOBAL_PALBOX_XGP_PATH") || ""
    );
    watch(GLOBAL_PALBOX_PATH, (path) => {
        if (path) localStorage.setItem("PAL_GLOBAL_PALBOX_PATH", path);
        else localStorage.removeItem("PAL_GLOBAL_PALBOX_PATH");
    });
    watch(GLOBAL_PALBOX_SOURCE_MODE, (mode) => {
        localStorage.setItem("PAL_GLOBAL_PALBOX_SOURCE_MODE", mode);
    });
    watch(GLOBAL_PALBOX_XGP_PATH, (path) => {
        if (path) localStorage.setItem("PAL_GLOBAL_PALBOX_XGP_PATH", path);
        else localStorage.removeItem("PAL_GLOBAL_PALBOX_XGP_PATH");
    });
    const HAS_PASSWORD = ref(false);
    const PAL_WRITE_BACK_PATH = ref("");
    const SAVE_SOURCE_MODE = ref(getInitialSaveSourceMode());
    watch(SAVE_SOURCE_MODE, (mode) => {
        if (["steam", "xgp", "remote"].includes(mode)) {
            localStorage.setItem(SAVE_SOURCE_MODE_STORAGE_KEY, mode);
        }
    }, { immediate: true });
    const REMOTE_SERVER_ADDRESS = ref(
        localStorage.getItem(REMOTE_SERVER_ADDRESS_STORAGE_KEY) || ""
    );
    const REMOTE_CERTIFICATE_FINGERPRINT = ref(
        localStorage.getItem(REMOTE_CERTIFICATE_FINGERPRINT_STORAGE_KEY) || ""
    );
    const REMOTE_ALLOW_INSECURE_LOCAL = ref(
        localStorage.getItem(REMOTE_ALLOW_INSECURE_LOCAL_STORAGE_KEY) === "true"
    );
    const REMOTE_REMEMBER_CREDENTIAL = ref(false);
    const REMOTE_CREDENTIAL_SAVED = ref(false);
    const REMOTE_CREDENTIAL_STORAGE_AVAILABLE = ref(false);
    const REMOTE_SESSION_ID = ref(null);
    const REMOTE_SESSION_REVISION = ref(0);
    const REMOTE_SERVER = ref(null);
    const REMOTE_STATUS = ref(null);
    const REMOTE_PLAYERS = ref([]);
    const REMOTE_PLAYER_DIRECTORY = ref(null);
    const REMOTE_GUILDS = ref([]);
    const REMOTE_PLAYER_DETAILS = ref(null);
    const REMOTE_PLAYER_DETAILS_LOADING = ref(false);
    const REMOTE_MAP_DATA = ref(null);
    const REMOTE_MAP_LOADING = ref(false);
    let remotePlayerDetailsRequest = 0;
    let remotePlayerInventoryRequest = 0;
    let remotePlayerPalsRequest = 0;
    let remotePlayerDetailsLoading = false;
    let remotePlayerInventoryLoading = false;
    let remotePlayerPalsLoading = false;
    let remotePlayerDirectoryPollTimer = null;
    const REMOTE_CAPABILITIES = ref([]);
    const REMOTE_LOADING = ref(false);
    const REMOTE_CONNECTED = computed(() => Boolean(REMOTE_SESSION_ID.value));

    function syncRemotePlayerDetailsLoading() {
        REMOTE_PLAYER_DETAILS_LOADING.value = (
            remotePlayerDetailsLoading
            || remotePlayerInventoryLoading
            || remotePlayerPalsLoading
        );
    }

    function remoteDetailsPlayerId(details) {
        return String(
            details?.player?.playerId
            || details?.player?.player_uid
            || details?.player?.player_id
            || "",
        ).trim();
    }

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
        localDataSelection: {
            required: true,
            selected: false,
            platform: "steam",
            canSelectFile: true,
            source: null,
            reason: "LOCAL_DATA_NOT_SELECTED",
        },
        fogOfWarClear: {
            available: false,
            reason: "LOCAL_DATA_NOT_SELECTED",
            format: null,
            maps: [],
        },
        fogOfWarReset: {
            available: false,
            reason: "LOCAL_DATA_NOT_SELECTED",
            format: null,
            maps: [],
        },
    });
    const XGP_SAVE_CONFIRMED = ref(false);
    const PATH_CONTEXT = ref(new Map());
    const SESSION_ID = ref(null);
    const SESSION_REVISION = ref(0);
    const PENDING_CHANGE_COUNT = ref(0);
    const RAW_JSON_PENDING = ref(false);
    const SAVE_COMPATIBILITY = ref(null);
    const LAST_ERROR = ref(null);
    const LAST_SAVE_RESULT = ref(null);
    const MIGRATION_LOADING = ref(false);
    const MIGRATION_STAGE = ref(null);
    const MIGRATION_PLAN = ref(null);
    const MIGRATION_RESULT = ref(null);
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
    const ARENA_LEADERBOARD = ref([]);
    const ARENA_EDITABLE_COUNT = ref(0);
    const ARENA_RANKED_PLAYER_COUNT = ref(0);
    const ARENA_INITIALIZABLE_COUNT = ref(0);
    const ARENA_UNSUPPORTED_COUNT = ref(0);
    const ARENA_NPC_COUNT = ref(0);
    const ARENA_NPC_SOURCE_BUILD = ref(null);
    const ARENA_LOADING = ref(false);
    const MAP_DATA = ref(null);
    const MAP_LOADING = ref(false);
    const OVERVIEW_DATA = ref(null);
    const OVERVIEW_LOADING = ref(false);
    const GLOBAL_PALBOX_SESSION = ref(null);
    const GLOBAL_PALBOX_PALS = ref([]);
    const GLOBAL_PALBOX_CATALOG = ref([]);
    const GLOBAL_PALBOX_XGP_SOURCES = ref([]);
    const SELECTED_GLOBAL_PALBOX_XGP_SOURCE_ID = ref(null);
    const GLOBAL_PALBOX_LOADING = ref(false);
    const GLOBAL_PALBOX_ERROR = ref(null);

    const SHOW_FILE_PICKER = ref(false);
    const PAL_FILE_PICKER_PATH = ref(PAL_GAME_SAVE_PATH.value);
    const PAL_FILE_PICKER_SELECTION = ref(null);
    const FILE_PICKER_PURPOSE = ref("steam");
    const IS_PATH_PICKER_ROOT_VIEW = ref(false);

    // auth
    let auth_token = "";
    const IS_LOCKED = ref(true);

    async function GET(api, options = {}) {
        try {
            const response = await axios.get(api, {
                ...options,
                headers: {
                    ...(options.headers || {}),
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

    async function POST(api, data, { errorContext = null } = {}) {
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
                if (errorContext) {
                    const messageKey = "NETWORK_NO_RESPONSE";
                    const actionKey = SAVE_ERROR_ACTION_KEYS[messageKey];
                    LAST_ERROR.value = {
                        context: errorContext,
                        message: getTranslatedText(messageKey),
                        messageKey,
                        action: getTranslatedText(actionKey),
                        actionKey,
                        code: messageKey,
                        details: {},
                        retryable: true,
                    };
                } else {
                    alert(
                        `no response from the backend, make sure it is running, error: ${error.request}`
                    );
                }
                return false;
            } else {
                if (errorContext) {
                    const messageKey = "CLIENT_REQUEST_FAILED";
                    const actionKey = SAVE_ERROR_ACTION_KEYS[messageKey];
                    LAST_ERROR.value = {
                        context: errorContext,
                        message: getTranslatedText(messageKey),
                        messageKey,
                        action: getTranslatedText(actionKey),
                        actionKey,
                        code: messageKey,
                        details: {},
                        retryable: false,
                    };
                } else {
                    alert(`post(): ${error.message}`);
                }
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
            const errorDetails = response?.error?.details || {};
            const messageKey = (
                errorCode.startsWith("WGS_")
                || errorCode.startsWith("MIGRATION_")
                || LOCALIZED_SAVE_ERROR_CODES.has(errorCode)
            ) ? errorCode : null;
            const actionKey = (
                SAVE_ERROR_CATEGORY_ACTION_KEYS[
                    errorDetails.os_error_category
                ]
                || SAVE_ERROR_ACTION_KEYS[errorCode]
                || null
            );
            const localizedMessage = messageKey
                ? getTranslatedText(messageKey)
                : response?.msg || "The operation failed.";
            LAST_ERROR.value = {
                context,
                message: localizedMessage,
                messageKey,
                action: actionKey ? getTranslatedText(actionKey) : null,
                actionKey,
                code: errorCode,
                details: errorDetails,
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

    function acceptRemoteResponse(response, context) {
        if (!response || response.status !== 0) {
            const errorCode = response?.error?.code || "REMOTE_REQUEST_FAILED";
            const messageKey = REMOTE_ERROR_MESSAGE_KEYS[errorCode] || null;
            const rawMessage = response?.msg || "The remote operation failed.";
            LAST_ERROR.value = {
                context,
                message: messageKey
                    ? getTranslatedText(messageKey)
                    : rawMessage,
                messageKey,
                rawMessage: messageKey ? rawMessage : null,
                code: errorCode,
                details: response?.error?.details || {},
                retryable: Boolean(response?.error?.retryable),
            };
            return false;
        }
        LAST_ERROR.value = null;
        return true;
    }

    function applyRemoteStatus(data) {
        const session = data?.session;
        if (session) {
            REMOTE_SESSION_ID.value = session.session_id;
            REMOTE_SESSION_REVISION.value = session.revision ?? 0;
            REMOTE_SERVER.value = session.server || null;
            REMOTE_CAPABILITIES.value = Array.isArray(session.capabilities)
                ? session.capabilities
                : [];
        }
        REMOTE_STATUS.value = data || null;
    }

    function applyRemoteProfile(profile) {
        if (!profile) return;
        REMOTE_SERVER_ADDRESS.value = profile.address || "";
        REMOTE_CERTIFICATE_FINGERPRINT.value =
            profile.certificate_fingerprint || "";
        REMOTE_ALLOW_INSECURE_LOCAL.value =
            profile.allow_insecure_local === true;
        REMOTE_CREDENTIAL_SAVED.value = profile.credential_saved === true;
        localStorage.setItem(
            REMOTE_SERVER_ADDRESS_STORAGE_KEY,
            REMOTE_SERVER_ADDRESS.value
        );
        localStorage.setItem(
            REMOTE_CERTIFICATE_FINGERPRINT_STORAGE_KEY,
            REMOTE_CERTIFICATE_FINGERPRINT.value
        );
        localStorage.setItem(
            REMOTE_ALLOW_INSECURE_LOCAL_STORAGE_KEY,
            String(REMOTE_ALLOW_INSECURE_LOCAL.value)
        );
    }

    function clearRemoteSession() {
        REMOTE_SESSION_ID.value = null;
        REMOTE_SESSION_REVISION.value = 0;
        REMOTE_SERVER.value = null;
        REMOTE_STATUS.value = null;
        REMOTE_PLAYERS.value = [];
        REMOTE_PLAYER_DIRECTORY.value = null;
        REMOTE_GUILDS.value = [];
        REMOTE_PLAYER_DETAILS.value = null;
        REMOTE_PLAYER_DETAILS_LOADING.value = false;
        REMOTE_MAP_DATA.value = null;
        REMOTE_MAP_LOADING.value = false;
        remotePlayerDetailsRequest += 1;
        remotePlayerInventoryRequest += 1;
        remotePlayerPalsRequest += 1;
        remotePlayerDetailsLoading = false;
        remotePlayerInventoryLoading = false;
        remotePlayerPalsLoading = false;
        if (remotePlayerDirectoryPollTimer) {
            clearTimeout(remotePlayerDirectoryPollTimer);
            remotePlayerDirectoryPollTimer = null;
        }
        REMOTE_CAPABILITIES.value = [];
    }

    async function connectRemote({
        username = "admin",
        adminPassword,
    } = {}) {
        REMOTE_LOADING.value = true;
        try {
            const useSavedCredential =
                !adminPassword && REMOTE_CREDENTIAL_SAVED.value;
            const response = useSavedCredential
                ? await POST("/api/remote/reconnect", {})
                : await POST("/api/remote/connect", {
                    address: REMOTE_SERVER_ADDRESS.value,
                    username,
                    admin_password: adminPassword,
                    remember_credential: true,
                });
            if (!acceptRemoteResponse(response, "remote-connect")) return false;
            applyRemoteStatus(response.data);
            applyRemoteProfile(response.data?.profile || {
                address: REMOTE_SERVER_ADDRESS.value,
                certificate_fingerprint: null,
                allow_insecure_local: false,
                credential_saved: true,
            });
            if (REMOTE_CAPABILITIES.value.includes("player.list")) {
                await loadRemotePlayers();
            }
            if (REMOTE_CAPABILITIES.value.includes("guild.list")) {
                await loadRemoteGuilds();
            }
            return true;
        } finally {
            REMOTE_LOADING.value = false;
        }
    }

    async function connectLocalGame() {
        REMOTE_LOADING.value = true;
        try {
            const response = await POST("/api/remote/connect-local", {});
            if (!acceptRemoteResponse(response, "local-connect")) return false;
            applyRemoteStatus(response.data);
            if (REMOTE_CAPABILITIES.value.includes("player.list")) {
                await loadRemotePlayers();
            }
            if (REMOTE_CAPABILITIES.value.includes("guild.list")) {
                await loadRemoteGuilds();
            }
            return true;
        } finally {
            REMOTE_LOADING.value = false;
        }
    }

    async function loadRemoteProfile() {
        const response = await GET("/api/remote/profile");
        if (response === false) return false;
        if (!acceptRemoteResponse(response, "remote-profile")) return false;
        REMOTE_CREDENTIAL_STORAGE_AVAILABLE.value =
            response.data?.credential_storage_available === true;
        applyRemoteProfile(response.data?.profile);
        return true;
    }

    async function resumeRemoteSession() {
        const response = await GET("/api/remote/session");
        if (response === false) return false;
        if (response.status === 0) {
            applyRemoteStatus(response.data);
            if (REMOTE_CAPABILITIES.value.includes("player.list")) {
                await loadRemotePlayers();
            }
            if (REMOTE_CAPABILITIES.value.includes("guild.list")) {
                await loadRemoteGuilds();
            }
            return true;
        }
        if (response?.error?.code === "REMOTE_SESSION_NOT_FOUND") {
            clearRemoteSession();
            LAST_ERROR.value = null;
            return false;
        }
        acceptRemoteResponse(response, "remote-session");
        return false;
    }

    async function refreshRemoteStatus({ background = false } = {}) {
        if (!REMOTE_SESSION_ID.value) return false;
        const activeSessionId = REMOTE_SESSION_ID.value;
        if (!background) REMOTE_LOADING.value = true;
        try {
            const sessionId = encodeURIComponent(activeSessionId);
            const response = await GET(`/api/remote/status?session_id=${sessionId}`);
            if (REMOTE_SESSION_ID.value !== activeSessionId) return false;
            if (!acceptRemoteResponse(response, "remote-status")) return false;
            const responseRevision = response.data?.session?.revision;
            if (
                Number.isInteger(responseRevision)
                && responseRevision < REMOTE_SESSION_REVISION.value
            ) {
                return false;
            }
            applyRemoteStatus(response.data);
            return true;
        } finally {
            if (!background) REMOTE_LOADING.value = false;
        }
    }

    async function loadRemotePlayers() {
        if (
            !REMOTE_SESSION_ID.value
            || !REMOTE_CAPABILITIES.value.includes("player.list")
        ) {
            REMOTE_PLAYERS.value = [];
            return false;
        }
        const activeSessionId = REMOTE_SESSION_ID.value;
        const sessionId = encodeURIComponent(activeSessionId);
        const response = await GET(
            `/api/remote/player-directory?session_id=${sessionId}`
        );
        if (REMOTE_SESSION_ID.value !== activeSessionId) return false;
        if (!acceptRemoteResponse(response, "remote-players")) return false;
        if (
            Number.isInteger(response.data?.revision)
            && response.data.revision < REMOTE_SESSION_REVISION.value
        ) {
            return false;
        }
        REMOTE_PLAYERS.value = Array.isArray(response.data?.players)
            ? response.data.players
            : [];
        REMOTE_PLAYER_DIRECTORY.value = {
            counts: response.data?.counts || null,
            snapshot: response.data?.snapshot || null,
        };
        if (remotePlayerDirectoryPollTimer) {
            clearTimeout(remotePlayerDirectoryPollTimer);
            remotePlayerDirectoryPollTimer = null;
        }
        if (response.data?.snapshot?.state === "capturing") {
            remotePlayerDirectoryPollTimer = setTimeout(() => {
                remotePlayerDirectoryPollTimer = null;
                if (REMOTE_SESSION_ID.value === activeSessionId) {
                    void loadRemotePlayers();
                }
            }, 500);
        }
        if (Number.isInteger(response.data?.revision)) {
            REMOTE_SESSION_REVISION.value = response.data.revision;
        }
        return true;
    }

    async function loadRemoteGuilds() {
        if (
            !REMOTE_SESSION_ID.value
            || !REMOTE_CAPABILITIES.value.includes("guild.list")
        ) {
            REMOTE_GUILDS.value = [];
            return false;
        }
        const activeSessionId = REMOTE_SESSION_ID.value;
        const sessionId = encodeURIComponent(activeSessionId);
        const response = await GET(`/api/remote/guilds?session_id=${sessionId}`);
        if (REMOTE_SESSION_ID.value !== activeSessionId) return false;
        if (!acceptRemoteResponse(response, "remote-guilds")) return false;
        if (
            Number.isInteger(response.data?.revision)
            && response.data.revision < REMOTE_SESSION_REVISION.value
        ) {
            return false;
        }
        REMOTE_GUILDS.value = Array.isArray(response.data?.guilds)
            ? response.data.guilds
            : [];
        if (Number.isInteger(response.data?.revision)) {
            REMOTE_SESSION_REVISION.value = response.data.revision;
        }
        return true;
    }

    async function loadRemoteMapData() {
        if (
            !REMOTE_SESSION_ID.value
            || !REMOTE_CAPABILITIES.value.includes("map.read")
        ) {
            REMOTE_MAP_DATA.value = null;
            return false;
        }
        if (REMOTE_MAP_LOADING.value) return false;
        const activeSessionId = REMOTE_SESSION_ID.value;
        REMOTE_MAP_LOADING.value = true;
        try {
            const sessionId = encodeURIComponent(activeSessionId);
            const response = await GET(
                `/api/remote/map?session_id=${sessionId}`
            );
            if (REMOTE_SESSION_ID.value !== activeSessionId) return false;
            if (!acceptRemoteResponse(response, "remote-map")) return false;
            if (
                Number.isInteger(response.data?.revision)
                && response.data.revision < REMOTE_SESSION_REVISION.value
            ) {
                return false;
            }
            REMOTE_MAP_DATA.value = response.data || null;
            if (Number.isInteger(response.data?.revision)) {
                REMOTE_SESSION_REVISION.value = response.data.revision;
            }
            return true;
        } finally {
            REMOTE_MAP_LOADING.value = false;
        }
    }

    async function loadRemotePlayerDetails(playerId) {
        const normalizedPlayerId = String(playerId || "").trim();
        const requestId = ++remotePlayerDetailsRequest;
        if (
            !REMOTE_SESSION_ID.value
            || !normalizedPlayerId
            || !(
                REMOTE_CAPABILITIES.value.includes("player.details")
                || REMOTE_CAPABILITIES.value.includes("player.saved.details")
            )
        ) {
            REMOTE_PLAYER_DETAILS.value = null;
            remotePlayerDetailsLoading = false;
            syncRemotePlayerDetailsLoading();
            return false;
        }
        const activeSessionId = REMOTE_SESSION_ID.value;
        remotePlayerDetailsLoading = true;
        syncRemotePlayerDetailsLoading();
        try {
            const sessionId = encodeURIComponent(activeSessionId);
            const encodedPlayerId = encodeURIComponent(normalizedPlayerId);
            const response = await GET(
                `/api/remote/players/${encodedPlayerId}/details?session_id=${sessionId}`
            );
            if (
                REMOTE_SESSION_ID.value !== activeSessionId
                || requestId !== remotePlayerDetailsRequest
            ) return false;
            if (!acceptRemoteResponse(response, "remote-player-details")) {
                REMOTE_PLAYER_DETAILS.value = null;
                return false;
            }
            if (
                Number.isInteger(response.data?.revision)
                && response.data.revision < REMOTE_SESSION_REVISION.value
            ) {
                return false;
            }
            const current = REMOTE_PLAYER_DETAILS.value;
            const currentPlayerId = remoteDetailsPlayerId(current);
            const samePlayer = currentPlayerId === normalizedPlayerId;
            REMOTE_PLAYER_DETAILS.value = {
                ...(samePlayer ? current : {}),
                ...(response.data || {}),
                inventory: samePlayer && current?.inventory
                    ? current.inventory
                    : { status: "deferred", containers: [] },
                pals: samePlayer && current?.pals
                    ? current.pals
                    : {
                        status: "deferred",
                        entries: [],
                        pageIndex: 0,
                        pageSize: 12,
                    },
            };
            if (Number.isInteger(response.data?.revision)) {
                REMOTE_SESSION_REVISION.value = response.data.revision;
            }
            return true;
        } finally {
            if (requestId === remotePlayerDetailsRequest) {
                remotePlayerDetailsLoading = false;
                syncRemotePlayerDetailsLoading();
            }
        }
    }

    async function loadRemotePlayerInventory(playerId, { force = false } = {}) {
        const normalizedPlayerId = String(playerId || "").trim();
        const requestId = ++remotePlayerInventoryRequest;
        if (
            !REMOTE_SESSION_ID.value
            || !normalizedPlayerId
            || !(
                REMOTE_CAPABILITIES.value.includes("inventory.read")
                || REMOTE_CAPABILITIES.value.includes("inventory.saved.read")
            )
        ) {
            remotePlayerInventoryLoading = false;
            syncRemotePlayerDetailsLoading();
            return false;
        }
        if (
            !force
            && remoteDetailsPlayerId(REMOTE_PLAYER_DETAILS.value)
                === normalizedPlayerId
            && REMOTE_PLAYER_DETAILS.value?.revision
                === REMOTE_SESSION_REVISION.value
            && REMOTE_PLAYER_DETAILS.value?.inventory?.status === "available"
        ) {
            return true;
        }
        const activeSessionId = REMOTE_SESSION_ID.value;
        remotePlayerInventoryLoading = true;
        syncRemotePlayerDetailsLoading();
        try {
            const sessionId = encodeURIComponent(activeSessionId);
            const encodedPlayerId = encodeURIComponent(normalizedPlayerId);
            const response = await GET(
                `/api/remote/players/${encodedPlayerId}/inventory?session_id=${sessionId}`
            );
            if (
                REMOTE_SESSION_ID.value !== activeSessionId
                || requestId !== remotePlayerInventoryRequest
                || remoteDetailsPlayerId(REMOTE_PLAYER_DETAILS.value)
                    !== normalizedPlayerId
            ) return false;
            if (!acceptRemoteResponse(response, "remote-player-inventory")) {
                return false;
            }
            REMOTE_PLAYER_DETAILS.value = {
                ...REMOTE_PLAYER_DETAILS.value,
                revision: response.data?.revision
                    ?? REMOTE_PLAYER_DETAILS.value?.revision,
                inventory: response.data?.inventory || {
                    status: "unavailable",
                    containers: [],
                },
            };
            if (Number.isInteger(response.data?.revision)) {
                REMOTE_SESSION_REVISION.value = response.data.revision;
            }
            return true;
        } finally {
            if (requestId === remotePlayerInventoryRequest) {
                remotePlayerInventoryLoading = false;
                syncRemotePlayerDetailsLoading();
            }
        }
    }

    async function loadRemotePlayerPals(
        playerId,
        page = 0,
        { collection = "palbox", force = false, pageSize = 12 } = {},
    ) {
        const normalizedPlayerId = String(playerId || "").trim();
        const normalizedCollection = collection === "party"
            ? "party"
            : "palbox";
        const normalizedPage = Math.max(0, Math.trunc(Number(page) || 0));
        const normalizedPageSize = Math.min(
            30,
            Math.max(1, Math.trunc(Number(pageSize) || 12)),
        );
        const requestId = ++remotePlayerPalsRequest;
        if (
            !REMOTE_SESSION_ID.value
            || !normalizedPlayerId
            || !(
                REMOTE_CAPABILITIES.value.includes("pal.list")
                || REMOTE_CAPABILITIES.value.includes("pal.saved.list")
            )
        ) {
            remotePlayerPalsLoading = false;
            syncRemotePlayerDetailsLoading();
            return false;
        }
        const currentPals = REMOTE_PLAYER_DETAILS.value?.pals;
        if (
            !force
            && remoteDetailsPlayerId(REMOTE_PLAYER_DETAILS.value)
                === normalizedPlayerId
            && REMOTE_PLAYER_DETAILS.value?.revision
                === REMOTE_SESSION_REVISION.value
            && currentPals?.status === "available"
            && currentPals.collection === normalizedCollection
            && currentPals.pageIndex === normalizedPage
            && currentPals.pageSize === normalizedPageSize
        ) {
            return true;
        }
        const activeSessionId = REMOTE_SESSION_ID.value;
        remotePlayerPalsLoading = true;
        syncRemotePlayerDetailsLoading();
        try {
            const sessionId = encodeURIComponent(activeSessionId);
            const encodedPlayerId = encodeURIComponent(normalizedPlayerId);
            const encodedCollection = encodeURIComponent(normalizedCollection);
            const response = await GET(
                `/api/remote/players/${encodedPlayerId}/pals`
                + `?session_id=${sessionId}&collection=${encodedCollection}&page=${normalizedPage}`
                + `&page_size=${normalizedPageSize}`
            );
            if (
                REMOTE_SESSION_ID.value !== activeSessionId
                || requestId !== remotePlayerPalsRequest
                || remoteDetailsPlayerId(REMOTE_PLAYER_DETAILS.value)
                    !== normalizedPlayerId
            ) return false;
            if (!acceptRemoteResponse(response, "remote-player-pals")) {
                return false;
            }
            REMOTE_PLAYER_DETAILS.value = {
                ...REMOTE_PLAYER_DETAILS.value,
                revision: response.data?.revision
                    ?? REMOTE_PLAYER_DETAILS.value?.revision,
                pals: response.data?.pals || {
                    status: "unavailable",
                    entries: [],
                    collection: normalizedCollection,
                },
            };
            if (Number.isInteger(response.data?.revision)) {
                REMOTE_SESSION_REVISION.value = response.data.revision;
            }
            return true;
        } finally {
            if (requestId === remotePlayerPalsRequest) {
                remotePlayerPalsLoading = false;
                syncRemotePlayerDetailsLoading();
            }
        }
    }

    async function executeRemoteCommand({
        operation,
        target = {},
        payload = {},
        commandId = null,
    }) {
        if (!REMOTE_SESSION_ID.value) return false;
        REMOTE_LOADING.value = true;
        try {
            const request = {
                session_id: REMOTE_SESSION_ID.value,
                expected_revision: REMOTE_SESSION_REVISION.value,
                operation,
                target,
                payload,
            };
            if (commandId) request.command_id = commandId;
            const response = await POST("/api/remote/commands", request);
            if (!acceptRemoteResponse(response, "remote-command")) return false;
            if (Number.isInteger(response.data?.revision)) {
                REMOTE_SESSION_REVISION.value = response.data.revision;
            }
            if (response.data?.persistence) {
                REMOTE_STATUS.value = {
                    ...(REMOTE_STATUS.value || {}),
                    persistence: response.data.persistence,
                };
            }
            return response.data;
        } finally {
            REMOTE_LOADING.value = false;
        }
    }

    async function disconnectRemote() {
        if (!REMOTE_SESSION_ID.value) {
            clearRemoteSession();
            return true;
        }
        REMOTE_LOADING.value = true;
        try {
            const response = await POST("/api/remote/disconnect", {
                session_id: REMOTE_SESSION_ID.value,
            });
            if (!acceptRemoteResponse(response, "remote-disconnect")) return false;
            clearRemoteSession();
            return true;
        } finally {
            REMOTE_LOADING.value = false;
        }
    }

    function applySessionState(data) {
        const session = data.session;
        SESSION_ID.value = session.session_id;
        SESSION_REVISION.value = session.revision;
        PENDING_CHANGE_COUNT.value = session.pending_change_count;
        RAW_JSON_PENDING.value = Boolean(session.raw_json_pending);
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

    function localDataPickerInitialPath() {
        return PAL_GAME_SAVE_PATH.value
            || SAVE_CAPABILITIES.value?.localDataSelection?.source
            || undefined;
    }

    function update_path_picker_result(data) {
        IS_PAL_SAVE_PATH.value = data.isPalDir;
        IS_PATH_PICKER_ROOT_VIEW.value = data.isRootView === true;
        PAL_FILE_PICKER_PATH.value = data.currentPath || "";
        PATH_CONTEXT.value = new Map(Object.entries(data.children));
        SHOW_FILE_PICKER.value = true;
        if (["xgp", "local-data", "global-palbox"].includes(FILE_PICKER_PURPOSE.value)) {
            PAL_FILE_PICKER_SELECTION.value = null;
        }
    }

    function setGlobalPalboxError(response) {
        GLOBAL_PALBOX_ERROR.value = response?.msg
            || getTranslatedText("GlobalPalbox_RequestFailed");
        return false;
    }

    function updateGlobalPalboxSessionRevision(revision, pendingDelta = 1) {
        if (!GLOBAL_PALBOX_SESSION.value) return;
        GLOBAL_PALBOX_SESSION.value = {
            ...GLOBAL_PALBOX_SESSION.value,
            revision,
            pending_change_count:
                GLOBAL_PALBOX_SESSION.value.pending_change_count + pendingDelta,
        };
    }

    function setGlobalPalboxPals(pals, selectedPalId = null) {
        GLOBAL_PALBOX_PALS.value = pals || [];
        PAL_MAP.value = new Map(
            GLOBAL_PALBOX_PALS.value.map(raw => {
                const pal = new PalData(raw);
                return [pal.InstanceId, pal];
            })
        );
        BASE_PAL_BTN_CLK_FLAG.value = false;
        SHOW_PLAYER_EDIT_FLAG.value = false;
        const selected = selectedPalId && PAL_MAP.value.has(selectedPalId)
            ? selectedPalId
            : PAL_MAP.value.keys().next().value || null;
        SELECTED_PAL_ID.value = selected;
        SELECTED_PAL_DATA.value = selected ? PAL_MAP.value.get(selected) : null;
    }

    function replaceGlobalPalboxPal(raw) {
        const pal = new PalData(raw);
        const index = GLOBAL_PALBOX_PALS.value.findIndex(
            item => item.InstanceId === pal.InstanceId,
        );
        if (index >= 0) GLOBAL_PALBOX_PALS.value[index] = raw;
        else GLOBAL_PALBOX_PALS.value.push(raw);
        GLOBAL_PALBOX_PALS.value.sort((a, b) => a.SlotIndex - b.SlotIndex);
        PAL_MAP.value.set(pal.InstanceId, pal);
        if (SELECTED_PAL_ID.value === pal.InstanceId) {
            SELECTED_PAL_DATA.value = pal;
        }
        return pal;
    }

    async function initializeGlobalPalbox() {
        GLOBAL_PALBOX_LOADING.value = true;
        GLOBAL_PALBOX_ERROR.value = null;
        try {
            const [catalogResponse, sourceResponse] = await Promise.all([
                GET("/api/global-palbox/catalog"),
                GET("/api/global-palbox/default-source"),
                PAL_STATIC_DATA_LIST.value.length ? true : fetchStaticData(),
            ]);
            if (catalogResponse?.status !== 0) return setGlobalPalboxError(catalogResponse);
            GLOBAL_PALBOX_CATALOG.value = catalogResponse.data || [];
            if (sourceResponse?.status !== 0) return setGlobalPalboxError(sourceResponse);
            if (!GLOBAL_PALBOX_PATH.value && sourceResponse.data?.path) {
                GLOBAL_PALBOX_PATH.value = sourceResponse.data.path;
            }
            return true;
        } finally {
            GLOBAL_PALBOX_LOADING.value = false;
        }
    }

    async function discoverGlobalPalboxXgp(
        path = GLOBAL_PALBOX_XGP_PATH.value,
    ) {
        if (!path) {
            GLOBAL_PALBOX_ERROR.value = getTranslatedText(
                "GlobalPalbox_XgpPathRequired",
            );
            return false;
        }
        GLOBAL_PALBOX_LOADING.value = true;
        LOADING_FLAG.value = true;
        GLOBAL_PALBOX_ERROR.value = null;
        GLOBAL_PALBOX_XGP_SOURCES.value = [];
        SELECTED_GLOBAL_PALBOX_XGP_SOURCE_ID.value = null;
        try {
            GLOBAL_PALBOX_XGP_PATH.value = path;
            const response = await POST("/api/global-palbox/discover-xgp", {
                path,
            });
            if (response?.status !== 0) return setGlobalPalboxError(response);
            GLOBAL_PALBOX_XGP_SOURCES.value = response.data?.sources || [];
            return GLOBAL_PALBOX_XGP_SOURCES.value.length > 0;
        } finally {
            GLOBAL_PALBOX_LOADING.value = false;
            LOADING_FLAG.value = false;
        }
    }

    async function openGlobalPalbox() {
        if (
            GLOBAL_PALBOX_SOURCE_MODE.value === "steam"
            && !GLOBAL_PALBOX_PATH.value
        ) {
            GLOBAL_PALBOX_ERROR.value = getTranslatedText("GlobalPalbox_PathRequired");
            return false;
        }
        if (
            GLOBAL_PALBOX_SOURCE_MODE.value === "xgp"
            && !SELECTED_GLOBAL_PALBOX_XGP_SOURCE_ID.value
        ) {
            GLOBAL_PALBOX_ERROR.value = getTranslatedText(
                "GlobalPalbox_XgpSelectRequired",
            );
            return false;
        }
        GLOBAL_PALBOX_LOADING.value = true;
        LOADING_FLAG.value = true;
        GLOBAL_PALBOX_ERROR.value = null;
        try {
            const response = await POST(
                "/api/global-palbox/open",
                GLOBAL_PALBOX_SOURCE_MODE.value === "xgp"
                    ? {
                        platform: "xgp",
                        sourceId: SELECTED_GLOBAL_PALBOX_XGP_SOURCE_ID.value,
                    }
                    : {
                        platform: "steam",
                        path: GLOBAL_PALBOX_PATH.value,
                    },
            );
            if (response?.status !== 0) return setGlobalPalboxError(response);
            GLOBAL_PALBOX_SESSION.value = response.data.session;
            setGlobalPalboxPals(response.data.pals || []);
            return true;
        } finally {
            GLOBAL_PALBOX_LOADING.value = false;
            LOADING_FLAG.value = false;
        }
    }

    async function updateGlobalPalboxPal(palId, values) {
        const session = GLOBAL_PALBOX_SESSION.value;
        if (!session) return false;
        GLOBAL_PALBOX_LOADING.value = true;
        LOADING_FLAG.value = true;
        GLOBAL_PALBOX_ERROR.value = null;
        try {
            const response = await PATCH(
                `/api/global-palbox/pals/${encodeURIComponent(palId)}`,
                {
                    session_id: session.session_id,
                    expected_revision: session.revision,
                    values,
                },
            );
            if (response?.status !== 0) return setGlobalPalboxError(response);
            const pal = replaceGlobalPalboxPal(response.data.pal);
            updateGlobalPalboxSessionRevision(response.data.revision);
            return pal;
        } finally {
            GLOBAL_PALBOX_LOADING.value = false;
            LOADING_FLAG.value = false;
        }
    }

    function addGlobalPalboxResult(pal, revision) {
        const added = replaceGlobalPalboxPal(pal);
        updateGlobalPalboxSessionRevision(revision);
        GLOBAL_PALBOX_SESSION.value.occupied += 1;
        GLOBAL_PALBOX_SESSION.value.free -= 1;
        return added;
    }

    async function addGlobalPalboxPal(speciesId) {
        const session = GLOBAL_PALBOX_SESSION.value;
        if (!session) return false;
        GLOBAL_PALBOX_LOADING.value = true;
        LOADING_FLAG.value = true;
        GLOBAL_PALBOX_ERROR.value = null;
        try {
            const response = await POST("/api/global-palbox/pals", {
                session_id: session.session_id,
                expected_revision: session.revision,
                species_id: speciesId,
            });
            if (response?.status !== 0) return setGlobalPalboxError(response);
            return addGlobalPalboxResult(response.data.pal, response.data.revision);
        } finally {
            GLOBAL_PALBOX_LOADING.value = false;
            LOADING_FLAG.value = false;
        }
    }

    async function cloneGlobalPalboxPal(palId) {
        const session = GLOBAL_PALBOX_SESSION.value;
        if (!session) return false;
        GLOBAL_PALBOX_LOADING.value = true;
        LOADING_FLAG.value = true;
        GLOBAL_PALBOX_ERROR.value = null;
        try {
            const response = await POST(
                `/api/global-palbox/pals/${encodeURIComponent(palId)}/clone`,
                {
                    session_id: session.session_id,
                    expected_revision: session.revision,
                },
            );
            if (response?.status !== 0) return setGlobalPalboxError(response);
            return addGlobalPalboxResult(response.data.pal, response.data.revision);
        } finally {
            GLOBAL_PALBOX_LOADING.value = false;
            LOADING_FLAG.value = false;
        }
    }

    async function deleteGlobalPalboxPal(palId) {
        const session = GLOBAL_PALBOX_SESSION.value;
        if (!session) return false;
        if (!await confirmMessage(getTranslatedText("GlobalPalbox_DeleteConfirm"))) {
            return false;
        }
        GLOBAL_PALBOX_LOADING.value = true;
        LOADING_FLAG.value = true;
        GLOBAL_PALBOX_ERROR.value = null;
        try {
            const response = await DELETE(
                `/api/global-palbox/pals/${encodeURIComponent(palId)}`,
                {
                    session_id: session.session_id,
                    expected_revision: session.revision,
                },
            );
            if (response?.status !== 0) return setGlobalPalboxError(response);
            GLOBAL_PALBOX_PALS.value = GLOBAL_PALBOX_PALS.value.filter(
                pal => pal.InstanceId !== palId,
            );
            PAL_MAP.value.delete(palId);
            updateGlobalPalboxSessionRevision(response.data.revision);
            GLOBAL_PALBOX_SESSION.value.occupied -= 1;
            GLOBAL_PALBOX_SESSION.value.free += 1;
            return true;
        } finally {
            GLOBAL_PALBOX_LOADING.value = false;
            LOADING_FLAG.value = false;
        }
    }

    async function saveGlobalPalbox() {
        const session = GLOBAL_PALBOX_SESSION.value;
        if (!session) return false;
        if (
            session.platform === "xgp"
            && !await confirmMessage(getTranslatedText("Confirm_Xgp_Save"))
        ) return false;
        GLOBAL_PALBOX_LOADING.value = true;
        LOADING_FLAG.value = true;
        GLOBAL_PALBOX_ERROR.value = null;
        try {
            const response = await POST("/api/global-palbox/save", {
                session_id: session.session_id,
                expected_revision: session.revision,
            });
            if (response?.status !== 0) return setGlobalPalboxError(response);
            GLOBAL_PALBOX_SESSION.value = response.data.session;
            return true;
        } finally {
            GLOBAL_PALBOX_LOADING.value = false;
            LOADING_FLAG.value = false;
        }
    }

    async function closeGlobalPalbox() {
        const session = GLOBAL_PALBOX_SESSION.value;
        if (!session) return true;
        const hasChanges = session.pending_change_count > 0;
        if (
            hasChanges
            && !await confirmMessage(getTranslatedText("GlobalPalbox_DiscardConfirm"))
        ) return false;
        const response = await POST("/api/global-palbox/close", {
            session_id: session.session_id,
            expected_revision: session.revision,
            discard_changes: hasChanges,
        });
        if (response?.status !== 0) return setGlobalPalboxError(response);
        GLOBAL_PALBOX_SESSION.value = null;
        GLOBAL_PALBOX_PALS.value = [];
        PAL_MAP.value = new Map();
        SELECTED_PAL_ID.value = null;
        SELECTED_PAL_DATA.value = null;
        GLOBAL_PALBOX_ERROR.value = null;
        return true;
    }

    function globalPalboxValuesFromEditor(key, value) {
        if (["NickName", "Gender", "CharacterID", "IsBOSS", "IsTower", "IsRarePal"].includes(key)) {
            return {
                NickName: { nickname: value },
                Gender: {
                    gender: {
                        "EPalGenderType::Male": "male",
                        "EPalGenderType::Female": "female",
                        NONE: "none",
                    }[value] || value,
                },
                CharacterID: { species_id: value },
                IsBOSS: { is_boss: Boolean(value) },
                IsTower: { is_tower: Boolean(value) },
                IsRarePal: { is_rare: Boolean(value) },
            }[key];
        }
        if (["Level", "FriendshipLevel"].includes(key)) {
            return {
                [key === "Level" ? "level" : "friendship_level"]: Number(value),
            };
        }
        if (key === "set_AllEnhancements") {
            return Object.fromEntries(
                Object.entries(value.values || {}).map(([name, level]) => [
                    name === "condensation" ? "rank" : name,
                    Number(level),
                ]),
            );
        }
        if ([
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
                Rank: "rank",
                IsAwakened: "is_awakened",
            }[key];
            return { [field]: key === "IsAwakened" ? Boolean(value) : Number(value) };
        }
        if (["set_Suitability", "set_AllSuitabilities"].includes(key)) {
            return {
                work_suitability: key === "set_Suitability"
                    ? { [value.name]: Number(value.level) }
                    : Object.fromEntries(
                        Object.entries(value).map(([name, level]) => [name, Number(level)]),
                    ),
            };
        }
        if ([
            "add_PassiveSkillList", "pop_PassiveSkillList", "replace_PassiveSkillList",
            "add_EquipWaza", "pop_EquipWaza", "add_MasteredWaza", "pop_MasteredWaza",
        ].includes(key)) {
            const active = [...(SELECTED_PAL_DATA.value.EquipWaza || [])];
            const mastered = [...(SELECTED_PAL_DATA.value.MasteredWaza || [])];
            const passive = [...(SELECTED_PAL_DATA.value.PassiveSkillList || [])];
            if (key === "add_PassiveSkillList") passive.push(value);
            if (key === "pop_PassiveSkillList") {
                const index = Number.isInteger(value?.index)
                    && passive[value.index] === value.skill
                    ? value.index
                    : passive.indexOf(value?.skill || value);
                if (index >= 0) passive.splice(index, 1);
            }
            if (key === "replace_PassiveSkillList") {
                passive.splice(0, passive.length, ...value);
            }
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
                const index = mastered.indexOf(value);
                if (index >= 0) mastered.splice(index, 1);
                const activeIndex = active.indexOf(value);
                if (activeIndex >= 0) active.splice(activeIndex, 1);
            }
            return key.includes("Passive")
                ? { passive }
                : { active, mastered };
        }
        return null;
    }

    async function updateGlobalPalboxFromEditor(event) {
        const target = event.currentTarget || event.target;
        const values = globalPalboxValuesFromEditor(target.name, target.value);
        if (!values) {
            GLOBAL_PALBOX_ERROR.value = getTranslatedText(
                "GlobalPalbox_FieldUnsupported",
                [target.name],
            );
            return false;
        }
        return Boolean(await updateGlobalPalboxPal(SELECTED_PAL_ID.value, values));
    }

    async function show_file_picker(purpose = SAVE_SOURCE_MODE.value) {
        let no_set_loading_flag = LOADING_FLAG.value;
        if (!no_set_loading_flag) LOADING_FLAG.value = true;
        FILE_PICKER_PURPOSE.value = purpose === "global-palbox-xgp"
            ? "global-palbox-xgp"
            : purpose === "xgp"
            ? "xgp"
            : purpose === "local-data"
                ? "local-data"
                : purpose === "global-palbox"
                    ? "global-palbox"
                    : "steam";

        // The account-level XGP flow accepts either a folder or containers.index,
        // so it intentionally uses the shared in-app browser instead of a
        // folder-only native dialog.
        const nativePicker = FILE_PICKER_PURPOSE.value === "global-palbox-xgp"
            ? undefined
            : FILE_PICKER_PURPOSE.value === "global-palbox"
            ? window.pywebview?.api?.select_global_palbox_file
            : FILE_PICKER_PURPOSE.value === "xgp"
            ? (window.pywebview?.api?.select_xgp_source
                ?? window.pywebview?.api?.select_save_directory)
            : (window.pywebview?.api?.select_steam_source
                ?? window.pywebview?.api?.select_save_directory);
        if (FILE_PICKER_PURPOSE.value !== "local-data" && nativePicker) {
            try {
                const selectedPath = await nativePicker(
                    FILE_PICKER_PURPOSE.value === "global-palbox"
                        ? GLOBAL_PALBOX_PATH.value
                        : FILE_PICKER_PURPOSE.value === "xgp"
                        ? XGP_WGS_PATH.value
                        : PAL_GAME_SAVE_PATH.value
                );
                if (!selectedPath) {
                    if (!no_set_loading_flag) LOADING_FLAG.value = false;
                    return;
                }

                if (FILE_PICKER_PURPOSE.value === "global-palbox") {
                    GLOBAL_PALBOX_PATH.value = selectedPath;
                    PAL_FILE_PICKER_PATH.value = selectedPath;
                    SHOW_FILE_PICKER.value = false;
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

        const initialPath = FILE_PICKER_PURPOSE.value === "local-data"
            ? localDataPickerInitialPath()
            : FILE_PICKER_PURPOSE.value === "global-palbox-xgp"
                ? GLOBAL_PALBOX_XGP_PATH.value || XGP_WGS_PATH.value || undefined
            : FILE_PICKER_PURPOSE.value === "global-palbox"
                ? GLOBAL_PALBOX_PATH.value || PAL_GAME_SAVE_PATH.value || undefined
                : FILE_PICKER_PURPOSE.value === "xgp"
                ? XGP_WGS_PATH.value || PAL_GAME_SAVE_PATH.value || undefined
                : PAL_GAME_SAVE_PATH.value || undefined;
        let response = await POST("/api/save/browse-directory", {
            path: initialPath,
        });
        if (!response || response.status !== 0) {
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
        if (IS_PATH_PICKER_ROOT_VIEW.value) return;
        let no_set_loading_flag = LOADING_FLAG.value;
        if (!no_set_loading_flag) LOADING_FLAG.value = true;

        const response = await POST("/api/save/browse-directory", {
            path: PAL_FILE_PICKER_PATH.value,
            parent: true,
        });

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

        const response = await POST("/api/save/browse-directory", { path });

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

    async function show_path_picker_roots() {
        let no_set_loading_flag = LOADING_FLAG.value;
        if (!no_set_loading_flag) LOADING_FLAG.value = true;

        const response = await GET("/api/save/browse-roots");
        if (response !== false) {
            if (response.status == 0) {
                update_path_picker_result(response.data);
            } else if (response.status == 2) {
                alert("Unauthorized Access, Please Login. ");
                IS_LOCKED.value = true;
                reset();
            } else {
                alert(`- show_file_picker - Error occured: ${response.msg}`);
            }
        }

        if (!no_set_loading_flag) LOADING_FLAG.value = false;
    }

    async function updateI18n(options = {}) {
        const refreshStaticData = options?.refreshStaticData !== false;
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
                if (OVERVIEW_DATA.value) refreshes.push(loadOverview());
                for (const storage of Object.values(
                    BASE_STORAGE_BY_BASE.value
                )) {
                    if (storage?.guild_id && storage?.base_id) {
                        refreshes.push(loadBaseStorage(
                            storage.guild_id,
                            storage.base_id
                        ));
                    }
                }
            }
            if (lastItemCatalogSearch !== null) {
                refreshes.push(searchItemCatalog(
                    lastItemCatalogSearch.query,
                    lastItemCatalogSearch.containerType
                ));
            }
            if (!IS_LOCKED.value && refreshStaticData) {
                refreshes.push(fetchStaticData());
            }
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
        ARENA_LEADERBOARD.value = [];
        ARENA_EDITABLE_COUNT.value = 0;
        ARENA_RANKED_PLAYER_COUNT.value = 0;
        ARENA_INITIALIZABLE_COUNT.value = 0;
        ARENA_UNSUPPORTED_COUNT.value = 0;
        ARENA_NPC_COUNT.value = 0;
        ARENA_NPC_SOURCE_BUILD.value = null;
        ARENA_LOADING.value = false;
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
        RAW_JSON_PENDING.value = false;
        SAVE_COMPATIBILITY.value = null;
        LAST_ERROR.value = null;
        LAST_SAVE_RESULT.value = null;
        MAP_DATA.value = null;
        MAP_LOADING.value = false;
        OVERVIEW_DATA.value = null;
        OVERVIEW_LOADING.value = false;
        EXPEDITION_DATA.value = null;
        EXPEDITION_LOADING.value = false;
        SAVE_PLATFORM.value = "steam";
        SOURCE_ID.value = null;
        SOURCE_DISPLAY_NAME.value = "";
        SAVE_CAPABILITIES.value = {
            commitOriginal: true,
            exportSteamCopy: true,
            targetPathEditable: true,
            cloudSyncVerified: false,
            localDataSelection: {
                required: true,
                selected: false,
                platform: "steam",
                canSelectFile: true,
                source: null,
                reason: "LOCAL_DATA_NOT_SELECTED",
            },
            fogOfWarClear: {
                available: false,
                reason: "LOCAL_DATA_NOT_SELECTED",
                format: null,
                maps: [],
            },
            fogOfWarReset: {
                available: false,
                reason: "LOCAL_DATA_NOT_SELECTED",
                format: null,
                maps: [],
            },
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
        GUILD_LIST.value = [];
        GUILD_LOADING.value = false;
        BASE_STORAGE_BY_BASE.value = {};
        BASE_STORAGE_LOADING.value = {};
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
            !await confirmMessage(
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

    async function refreshSave() {
        if (!SESSION_ID.value) return false;
        if (!await confirmMessage(getTranslatedText("Confirm_DiscardChangesAndRefresh"))) {
            return false;
        }

        const noSetLoadingFlag = LOADING_FLAG.value;
        if (!noSetLoadingFlag) LOADING_FLAG.value = true;
        try {
            const response = await POST("/api/save/reload", {
                session_id: SESSION_ID.value,
                expected_revision: SESSION_REVISION.value,
                discard_changes: true,
            });
            if (response === false || !acceptResponse(response, "reload-save")) {
                return false;
            }
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

    function alert(message, options = {}) {
        const rawMessage = String(message || "").trim();
        const normalizedExactMessage = rawMessage.replace(/\s+$/, "");
        const exactKey = LEGACY_ALERT_MESSAGE_KEYS[normalizedExactMessage];
        if (exactKey) {
            void showMessage({
                tone: "error",
                message: getTranslatedText(exactKey),
                ...options,
            });
            return;
        }

        const operationMatch = rawMessage.match(
            /^-\s*([^\s:]+)(?::[^-]+)?\s*-\s*Error occured:\s*([\s\S]*)$/i
        );
        if (operationMatch) {
            const operation = operationMatch[1];
            void showMessage({
                tone: "error",
                message: getTranslatedText(
                    LEGACY_OPERATION_MESSAGE_KEYS[operation]
                    || "MessageDialog_RequestFailed"
                ),
                details: operationMatch[2].trim(),
                dismissible: false,
                ...options,
            });
            return;
        }

        const requestFailureMatch = rawMessage.match(
            /^(?:get|post|patch)\(\):\s*([\s\S]*)$/i
        );
        if (requestFailureMatch || rawMessage.startsWith("no response from the backend")) {
            void showMessage({
                tone: "error",
                message: getTranslatedText("MessageDialog_RequestFailed"),
                details: requestFailureMatch?.[1]?.trim() || rawMessage,
                dismissible: false,
                ...options,
            });
            return;
        }

        void showMessage({
            tone: options.tone || "error",
            message: rawMessage || getTranslatedText("MessageDialog_RequestFailed"),
            ...options,
        });
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
        const actionKey = LAST_ERROR.value?.actionKey;
        if (actionKey) {
            LAST_ERROR.value.action = getTranslatedText(actionKey);
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

    async function updatePlayerConsumableBonuses(bonus = null) {
        if (!SELECTED_PLAYER_ID.value || !SELECTED_PLAYER_DATA.value) return false;
        const capability = SELECTED_PLAYER_DATA.value.PlayerConsumableBonuses;
        if (!capability?.available) return false;
        const bonuses = bonus?.key ? [bonus] : (capability.values || []);
        const values = Object.fromEntries(
            bonuses.map(item => [item.key, Number(item.value)])
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
                    command: "update_player_consumable_bonuses",
                    values,
                }
            );
            if (!acceptResponse(
                response,
                "update-player-consumable-bonuses",
                { command: true },
            )) {
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
        if (SKIP_UPDATE_CHECK.value) return false;
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

    async function putInventoryItem(
        container,
        slot,
        staticId,
        count = 1,
        dynamicInit = null,
        mode = "empty_only"
    ) {
        const command = {
            command: "put_item",
            static_id: staticId,
            count: Number(count),
            mode,
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

    async function swapInventorySlots(container, sourceSlotIndex, targetSlotIndex) {
        return executeInventoryLayoutCommand(container.container_type, {
            command: "swap_item_slots",
            source_slot_index: sourceSlotIndex,
            target_slot_index: targetSlotIndex,
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
        if (!await confirmMessage(getTranslatedText(
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
        if (GLOBAL_PALBOX_SESSION.value) {
            const enhancements = SELECTED_PAL_DATA.value.maximumEnhancementPayload().values;
            const { condensation, ...enhancementValues } = enhancements;
            const work_suitability = Object.fromEntries(
                Object.keys(SELECTED_PAL_DATA.value.Suitabilities || {}).map(name => [
                    name,
                    MAX_SUITABILITY_LEVEL.value,
                ]),
            );
            return Boolean(await updateGlobalPalboxPal(
                SELECTED_PAL_ID.value,
                {
                    ...enhancementValues,
                    rank: condensation,
                    level: HIDE_INVALID_OPTIONS.value ? MAX_LEVEL : MAX_INVALID_LEVEL,
                    friendship_level: MAX_FRIENDSHIP_LEVEL,
                    is_awakened: true,
                    work_suitability,
                },
            ));
        }
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
        if (confirmBeforePreview && !await confirmMessage(getTranslatedText(
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
            if (!confirmBeforePreview && !await confirmMessage(getTranslatedText(
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

    async function healAllPalsInSave() {
        const palCount = Number(OVERVIEW_DATA.value?.totals?.pals) || 0;
        if (!palCount || !SESSION_ID.value) return false;
        if (!await confirmMessage(getTranslatedText(
            "Confirm_HealAllPalsInSave",
            [palCount]
        ))) return false;

        const ownsLoadingFlag = !LOADING_FLAG.value;
        if (ownsLoadingFlag) LOADING_FLAG.value = true;
        try {
            const response = await POST("/api/save/pals/commands", {
                session_id: SESSION_ID.value,
                expected_revision: SESSION_REVISION.value,
                command: "heal_all_pals",
            });
            if (!acceptResponse(response, "heal-all-pals-in-save", { command: true })) {
                return false;
            }
            if (SELECTED_PAL_ID.value) {
                await selectPal(SELECTED_PAL_ID.value, true);
            }
            await loadOverview();
            return true;
        } finally {
            if (ownsLoadingFlag) LOADING_FLAG.value = false;
        }
    }

    async function unlockExpeditionPals() {
        const lockedPalMap = new Map(
            Array.from(PAL_MAP.value.entries()).filter(([, pal]) => pal.IsExpeditionPal)
        );
        if (EXPEDITION_DATA.value) {
            for (const expedition of EXPEDITION_DATA.value.expeditions || []) {
                for (const pal of expedition.members || []) {
                    if (pal.assignment_status === "valid") {
                        lockedPalMap.set(pal.pal_id, pal);
                    }
                }
            }
            for (const pal of [
                ...(EXPEDITION_DATA.value.invalid_locked_pals || []),
                ...(EXPEDITION_DATA.value.unknown_locked_pals || []),
            ]) {
                lockedPalMap.set(pal.pal_id, pal);
            }
        }
        const lockedPals = Array.from(lockedPalMap.entries());
        if (!lockedPals.length || !SESSION_ID.value) return false;
        const statusCounts = { valid: 0, invalid: 0, unknown: 0 };
        for (const [, pal] of lockedPals) {
            const status = pal.ExpeditionAssignmentStatus ?? pal.assignment_status;
            statusCounts[statusCounts[status] === undefined ? "unknown" : status] += 1;
        }
        if (!await confirmMessage(getTranslatedText("Confirm_UnlockExpeditionPals", [
            lockedPals.length,
            statusCounts.valid,
            statusCounts.invalid,
            statusCounts.unknown,
        ]))) return false;

        const ownsLoadingFlag = !LOADING_FLAG.value;
        if (ownsLoadingFlag) LOADING_FLAG.value = true;
        try {
            const response = await POST("/api/save/pals/commands", {
                session_id: SESSION_ID.value,
                expected_revision: SESSION_REVISION.value,
                command: "unlock_all_expedition_pals",
            });
            if (!acceptResponse(response, "unlock-expedition-pals", { command: true })) {
                return false;
            }
            for (const [, pal] of lockedPals) {
                pal.IsExpeditionPal = false;
                pal.ExpeditionInstanceId = null;
                pal.ExpeditionAssignmentStatus = null;
                pal.assignment_status = "unassigned";
            }
            if (SELECTED_PAL_ID.value) {
                await selectPal(SELECTED_PAL_ID.value, true);
            }
            await loadExpeditions();
            return true;
        } finally {
            if (ownsLoadingFlag) LOADING_FLAG.value = false;
        }
    }

    function applyCompletedExpeditions(expeditionIds) {
        const completedIds = new Set(
            (expeditionIds || []).map(value => String(value).toLowerCase())
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
        if (EXPEDITION_DATA.value) {
            for (const expedition of EXPEDITION_DATA.value.expeditions || []) {
                if (completedIds.has(String(expedition.expedition_id).toLowerCase())) {
                    expedition.can_complete = false;
                }
            }
            EXPEDITION_DATA.value.completable_count = (
                EXPEDITION_DATA.value.expeditions || []
            ).filter(expedition => expedition.can_complete).length;
        }
    }

    async function completeActiveExpeditions() {
        if (!COMPLETABLE_EXPEDITION_COUNT.value || !SESSION_ID.value) return false;
        if (!await confirmMessage(getTranslatedText("Confirm_CompleteActiveExpeditions"))) {
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
            applyCompletedExpeditions(response.data.value?.expedition_ids);
            return true;
        } finally {
            if (ownsLoadingFlag) LOADING_FLAG.value = false;
        }
    }

    async function completeExpedition(expeditionId) {
        if (!SESSION_ID.value || !expeditionId) return false;
        const expedition = (EXPEDITION_DATA.value?.expeditions || []).find(
            item => String(item.expedition_id).toLowerCase() === String(expeditionId).toLowerCase()
        );
        if (expedition && !expedition.can_complete) return false;
        const baseLabel = expedition?.base_number
            ? getTranslatedText("PlayerTree_BaseNumber", [expedition.base_number])
            : expedition?.base_id || "-";
        if (!await confirmMessage(getTranslatedText("Confirm_CompleteExpedition", [
            expedition?.mission_id || expeditionId,
            baseLabel,
        ]))) {
            return false;
        }
        const ownsLoadingFlag = !LOADING_FLAG.value;
        if (ownsLoadingFlag) LOADING_FLAG.value = true;
        try {
            const response = await POST("/api/save/expeditions/commands", {
                session_id: SESSION_ID.value,
                expected_revision: SESSION_REVISION.value,
                command: "complete_expedition",
                expedition_id: expeditionId,
            });
            if (!acceptResponse(response, "complete-expedition", { command: true })) {
                return false;
            }
            applyCompletedExpeditions(response.data.value?.expedition_ids);
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
        if (!await confirmMessage(getTranslatedText(
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
            await loadExpeditions();
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

    async function loadGuilds() {
        if (!SESSION_ID.value) return false;
        GUILD_LOADING.value = true;
        try {
            const params = new URLSearchParams({
                session_id: SESSION_ID.value,
            });
            const response = await GET(
                `/api/save/query/guilds?${params.toString()}`
            );
            if (!acceptResponse(response, "load-guilds")) return false;
            GUILD_LIST.value = Array.isArray(response.data?.guilds)
                ? response.data.guilds
                : [];
            BASE_STORAGE_BY_BASE.value = {};
            BASE_STORAGE_LOADING.value = {};
            return true;
        } finally {
            GUILD_LOADING.value = false;
        }
    }

    async function loadOverview() {
        if (!SESSION_ID.value) return false;
        OVERVIEW_LOADING.value = true;
        try {
            const response = await GET(
                `/api/save/query/overview?session_id=${encodeURIComponent(SESSION_ID.value)}`
            );
            if (!acceptResponse(response, "load-overview")) return false;
            OVERVIEW_DATA.value = response.data || null;
            return true;
        } finally {
            OVERVIEW_LOADING.value = false;
        }
    }

    async function loadExpeditions() {
        if (!SESSION_ID.value) return false;
        EXPEDITION_LOADING.value = true;
        try {
            const response = await GET(
                `/api/save/query/expeditions?session_id=${encodeURIComponent(SESSION_ID.value)}`
            );
            if (!acceptResponse(response, "load-expeditions")) return false;
            EXPEDITION_DATA.value = response.data || null;
            return true;
        } finally {
            EXPEDITION_LOADING.value = false;
        }
    }

    function applyArenaLeaderboard(data) {
        ARENA_LEADERBOARD.value = Array.isArray(data?.entries) ? data.entries : [];
        ARENA_EDITABLE_COUNT.value = Number(data?.editable_count) || 0;
        ARENA_RANKED_PLAYER_COUNT.value = Number(data?.ranked_player_count) || 0;
        ARENA_INITIALIZABLE_COUNT.value = Number(data?.initializable_count) || 0;
        ARENA_UNSUPPORTED_COUNT.value = Number(data?.unsupported_count) || 0;
        ARENA_NPC_COUNT.value = Number(data?.npc_count) || 0;
        ARENA_NPC_SOURCE_BUILD.value = Number(data?.npc_source_build) || null;
    }

    async function loadArenaLeaderboard() {
        if (!SESSION_ID.value) return false;
        ARENA_LOADING.value = true;
        try {
            const response = await GET(
                `/api/arena/leaderboard?session_id=${encodeURIComponent(SESSION_ID.value)}`
            );
            if (!acceptResponse(response, "load-arena-leaderboard")) return false;
            applyArenaLeaderboard(response.data);
            return true;
        } finally {
            ARENA_LOADING.value = false;
        }
    }

    async function executeArenaCommand(command, values = {}) {
        if (!SESSION_ID.value) return false;
        ARENA_LOADING.value = true;
        try {
            const response = await POST("/api/arena/commands", {
                session_id: SESSION_ID.value,
                expected_revision: SESSION_REVISION.value,
                command,
                ...values,
            });
            if (!acceptResponse(response, `arena-${command}`, { command: true })) {
                return false;
            }
            applyArenaLeaderboard(response.data);
            return response.data;
        } finally {
            ARENA_LOADING.value = false;
        }
    }

    function setArenaRankPoint(playerId, rankPoint) {
        return executeArenaCommand("set_rank_point", {
            player_id: playerId,
            rank_point: rankPoint,
        });
    }

    function resetArenaPlayer(playerId) {
        return executeArenaCommand("reset_player", { player_id: playerId });
    }

    function resetArenaLeaderboard() {
        return executeArenaCommand("reset_all");
    }

    async function loadMapData() {
        if (!SESSION_ID.value) return false;
        MAP_LOADING.value = true;
        try {
            const response = await GET(
                `/api/save/query/map?session_id=${encodeURIComponent(SESSION_ID.value)}`
            );
            if (!acceptResponse(response, "load-map-data")) return false;
            MAP_DATA.value = response.data || null;
            return true;
        } finally {
            MAP_LOADING.value = false;
        }
    }

    async function bindLocalData(selectedPath = null) {
        if (!SESSION_ID.value) return false;
        const ownsLoadingFlag = !LOADING_FLAG.value;
        if (ownsLoadingFlag) LOADING_FLAG.value = true;
        try {
            const payload = {
                session_id: SESSION_ID.value,
                expected_revision: SESSION_REVISION.value,
            };
            if (SAVE_PLATFORM.value === "steam") payload.path = selectedPath;
            const response = await POST("/api/save/local-data/select", payload);
            if (!acceptResponse(response, "select-local-data")) return false;
            SAVE_CAPABILITIES.value = response.data?.saveCapabilities || {};
            return true;
        } finally {
            if (ownsLoadingFlag) LOADING_FLAG.value = false;
        }
    }

    async function confirmLocalDataFileSelection(selectedPath) {
        const normalizedPath = typeof selectedPath === "string"
            ? selectedPath.trim()
            : "";
        if (
            SAVE_PLATFORM.value !== "steam"
            || !/(^|[\\/])LocalData\.sav$/i.test(normalizedPath)
        ) {
            return false;
        }
        const selected = await bindLocalData(normalizedPath);
        if (selected) {
            SHOW_FILE_PICKER.value = false;
            PAL_FILE_PICKER_SELECTION.value = null;
        }
        return selected;
    }

    async function selectLocalData() {
        if (!SESSION_ID.value) return false;
        if (SAVE_PLATFORM.value !== "steam") {
            return bindLocalData();
        }

        const currentSource =
            SAVE_CAPABILITIES.value?.localDataSelection?.source || "";
        const initialPath = PAL_GAME_SAVE_PATH.value || currentSource;
        const nativePicker = window.pywebview?.api?.select_local_data_file;
        if (nativePicker) {
            let selectedPath = null;
            try {
                selectedPath = await nativePicker(initialPath);
            } catch (error) {
                console.error(
                    "Native LocalData picker failed, using web picker.",
                    error,
                );
                await show_file_picker("local-data");
                return SHOW_FILE_PICKER.value;
            }
            if (!selectedPath) return false;
            return bindLocalData(selectedPath);
        }

        await show_file_picker("local-data");
        return SHOW_FILE_PICKER.value;
    }

    async function clearFogOfWar() {
        if (!SESSION_ID.value) return false;
        const capability = SAVE_CAPABILITIES.value?.fogOfWarClear || {};
        if (!capability.available) {
            const reason = capability.reason || "FOG_OF_WAR_STRUCTURE_UNSUPPORTED";
            LAST_ERROR.value = {
                context: "clear-fog-of-war",
                message: getTranslatedText(reason),
                messageKey: reason,
                action: null,
                actionKey: null,
                code: reason,
                details: { capability },
                retryable: false,
            };
            return false;
        }
        if (!await confirmMessage(getTranslatedText("Map_FogClear_Confirm"))) {
            return false;
        }
        const ownsLoadingFlag = !LOADING_FLAG.value;
        if (ownsLoadingFlag) LOADING_FLAG.value = true;
        try {
            const response = await POST(
                "/api/save/local-data/fog-of-war/clear",
                {
                    session_id: SESSION_ID.value,
                    expected_revision: SESSION_REVISION.value,
                    confirmation: FOG_CLEAR_CONFIRMATION,
                }
            );
            if (
                response === false
                || !acceptResponse(
                    response,
                    "clear-fog-of-war",
                    { command: true },
                )
            ) {
                return false;
            }
            alert(getTranslatedText(
                response.data?.changed
                    ? "Map_FogClear_Staged"
                    : "Map_FogClear_AlreadyCleared"
            ), { tone: "success" });
            return true;
        } finally {
            if (ownsLoadingFlag) LOADING_FLAG.value = false;
        }
    }

    async function resetFogOfWar() {
        if (!SESSION_ID.value) return false;
        const capability = SAVE_CAPABILITIES.value?.fogOfWarReset || {};
        if (!capability.available) {
            const reason = capability.reason || "FOG_OF_WAR_STRUCTURE_UNSUPPORTED";
            LAST_ERROR.value = {
                context: "reset-fog-of-war",
                message: getTranslatedText(reason),
                messageKey: reason,
                action: null,
                actionKey: null,
                code: reason,
                details: { capability },
                retryable: false,
            };
            return false;
        }
        if (!await confirmMessage(getTranslatedText("Map_FogReset_Confirm"))) {
            return false;
        }
        const ownsLoadingFlag = !LOADING_FLAG.value;
        if (ownsLoadingFlag) LOADING_FLAG.value = true;
        try {
            const response = await POST(
                "/api/save/local-data/fog-of-war/reset",
                {
                    session_id: SESSION_ID.value,
                    expected_revision: SESSION_REVISION.value,
                    confirmation: FOG_RESET_CONFIRMATION,
                }
            );
            if (
                response === false
                || !acceptResponse(
                    response,
                    "reset-fog-of-war",
                    { command: true },
                )
            ) {
                return false;
            }
            alert(getTranslatedText(
                response.data?.changed
                    ? "Map_FogReset_Staged"
                    : "Map_FogReset_AlreadyReset"
            ), { tone: "success" });
            return true;
        } finally {
            if (ownsLoadingFlag) LOADING_FLAG.value = false;
        }
    }

    async function unlockAllFastTravelPoints() {
        if (!SESSION_ID.value || !SELECTED_PLAYER_ID.value) return false;
        const capability =
            SELECTED_PLAYER_DATA.value?.FastTravelUnlockCapability || {};
        if (!capability.available) {
            const reason =
                capability.reason || "FAST_TRAVEL_STRUCTURE_UNSUPPORTED";
            LAST_ERROR.value = {
                context: "unlock-all-fast-travel-points",
                message: getTranslatedText(reason),
                messageKey: reason,
                action: null,
                actionKey: null,
                code: reason,
                details: { capability },
                retryable: false,
            };
            return false;
        }
        if (!await confirmMessage(getTranslatedText("PlayerMap_FastTravel_Confirm"))) {
            return false;
        }
        const ownsLoadingFlag = !LOADING_FLAG.value;
        if (ownsLoadingFlag) LOADING_FLAG.value = true;
        try {
            const response = await POST(
                `/api/player/${encodeURIComponent(
                    SELECTED_PLAYER_ID.value,
                )}/commands`,
                {
                    session_id: SESSION_ID.value,
                    expected_revision: SESSION_REVISION.value,
                    command: "unlock_all_fast_travel_points",
                    confirmation: FAST_TRAVEL_UNLOCK_CONFIRMATION,
                },
            );
            if (
                response === false
                || !acceptResponse(
                    response,
                    "unlock-all-fast-travel-points",
                    { command: true },
                )
            ) {
                return false;
            }
            if (
                response.data?.value
                && SELECTED_PLAYER_DATA.value?.FastTravelUnlockCapability
            ) {
                Object.assign(
                    SELECTED_PLAYER_DATA.value.FastTravelUnlockCapability,
                    {
                        available: true,
                        reason: null,
                        format: response.data.value.format,
                        unlocked_count: response.data.value.unlocked_count,
                        total_count: response.data.value.total_count,
                    },
                );
            }
            alert(getTranslatedText(
                response.data?.changed
                    ? "PlayerMap_FastTravel_Staged"
                    : "PlayerMap_FastTravel_AlreadyUnlocked",
            ), { tone: "success" });
            return true;
        } finally {
            if (ownsLoadingFlag) LOADING_FLAG.value = false;
        }
    }

    async function updatePlayerInventoryCapacity(capacity) {
        if (!SESSION_ID.value || !SELECTED_PLAYER_ID.value) return false;
        const capability =
            SELECTED_PLAYER_DATA.value?.InventoryCapacityCapability || {};
        const targetCapacity = Number(capacity);
        const currentCapacity = Number(capability.current_capacity);
        const minimumCapacity = Number(capability.minimum_capacity);
        const maximumCapacity = Number(capability.maximum_capacity);
        if (
            !capability.available
            || !Number.isInteger(targetCapacity)
            || !Number.isInteger(currentCapacity)
            || !Number.isInteger(minimumCapacity)
            || !Number.isInteger(maximumCapacity)
            || targetCapacity === currentCapacity
            || targetCapacity < minimumCapacity
            || targetCapacity > maximumCapacity
        ) {
            const reason = capability.reason || "INVALID_PLAYER_INVENTORY_CAPACITY";
            LAST_ERROR.value = {
                context: "update-player-inventory-capacity",
                message: getTranslatedText(reason),
                messageKey: reason,
                action: null,
                actionKey: null,
                code: reason,
                details: { capability, capacity: targetCapacity },
                retryable: false,
            };
            return false;
        }
        if (
            !await confirmMessage(
                getTranslatedText(
                    targetCapacity < currentCapacity
                        ? "PlayerInventoryCapacity_ShrinkConfirm"
                        : "PlayerInventoryCapacity_Confirm",
                    [capability.current_capacity, targetCapacity],
                ),
            )
        ) {
            return false;
        }

        const ownsLoadingFlag = !LOADING_FLAG.value;
        if (ownsLoadingFlag) LOADING_FLAG.value = true;
        try {
            const response = await POST(
                `/api/player/${encodeURIComponent(
                    SELECTED_PLAYER_ID.value,
                )}/commands`,
                {
                    session_id: SESSION_ID.value,
                    expected_revision: SESSION_REVISION.value,
                    command: "update_player_inventory_capacity",
                    capacity: targetCapacity,
                },
            );
            if (
                !acceptResponse(
                    response,
                    "update-player-inventory-capacity",
                    { command: true },
                )
            ) {
                return false;
            }
            if (SELECTED_PLAYER_DATA.value && response.data?.capability) {
                SELECTED_PLAYER_DATA.value.InventoryCapacityCapability = {
                    ...response.data.capability,
                };
            }
            await loadInventory();
            return true;
        } finally {
            if (ownsLoadingFlag) LOADING_FLAG.value = false;
        }
    }

    async function loadJsonEditorFiles() {
        if (!SESSION_ID.value) return false;
        const response = await GET(
            `/api/json-editor/files?session_id=${encodeURIComponent(SESSION_ID.value)}`
        );
        if (!acceptResponse(response, "load-json-editor-files")) return false;
        RAW_JSON_PENDING.value = Boolean(response.data?.raw_json_pending);
        return response.data;
    }

    async function loadJsonDocument(path) {
        if (!SESSION_ID.value || !path) return false;
        const params = new URLSearchParams({
            session_id: SESSION_ID.value,
            path,
        });
        const response = await GET(
            `/api/json-editor/document?${params.toString()}`,
            {
                responseType: "text",
                transformResponse: [value => value],
            }
        );
        if (typeof response === "string") {
            const prefix = response.trimStart().slice(0, 64);
            if (/^\{\s*"(?:data|error|status)"\s*:/.test(prefix)) {
                try {
                    const envelope = JSON.parse(response);
                    acceptResponse(envelope, "load-json-document");
                    return false;
                } catch {
                    // Fall through: malformed envelopes are handled as raw text.
                }
            }
            return response;
        }
        acceptResponse(response, "load-json-document");
        return false;
    }

    async function applyJsonDocument(path, text) {
        if (!SESSION_ID.value || !path) return false;
        const params = new URLSearchParams({
            session_id: SESSION_ID.value,
            expected_revision: String(SESSION_REVISION.value),
            path,
        });
        const response = await POST(
            `/api/json-editor/document?${params.toString()}`,
            text
        );
        if (!acceptResponse(response, "apply-json-document", { command: true })) {
            return false;
        }
        if (response.data?.changed) RAW_JSON_PENDING.value = true;
        return response.data;
    }

    function updateGuildCollections(guildId, update) {
        for (const collection of [GUILD_TREE.value, GUILD_LIST.value]) {
            const guild = collection.find(
                item => String(item.guild_id) === String(guildId)
            );
            if (guild) update(guild);
        }
    }

    function baseStorageKey(guildId, baseId) {
        return `${String(guildId)}:${String(baseId)}`;
    }

    function getBaseStorage(guildId, baseId) {
        return BASE_STORAGE_BY_BASE.value[baseStorageKey(guildId, baseId)] || null;
    }

    function isBaseStorageLoading(guildId, baseId) {
        return Boolean(
            BASE_STORAGE_LOADING.value[baseStorageKey(guildId, baseId)]
        );
    }

    async function loadBaseStorage(guildId, baseId) {
        if (!SESSION_ID.value || !guildId || !baseId) return false;
        const key = baseStorageKey(guildId, baseId);
        BASE_STORAGE_LOADING.value = {
            ...BASE_STORAGE_LOADING.value,
            [key]: true,
        };
        try {
            const params = new URLSearchParams({
                session_id: SESSION_ID.value,
            });
            const response = await GET(
                `/api/save/guilds/${encodeURIComponent(guildId)}` +
                `/bases/${encodeURIComponent(baseId)}/storage?${params.toString()}`
            );
            if (!acceptResponse(response, "load-base-storage")) return false;
            BASE_STORAGE_BY_BASE.value = {
                ...BASE_STORAGE_BY_BASE.value,
                [key]: response.data,
            };
            return response.data;
        } finally {
            BASE_STORAGE_LOADING.value = {
                ...BASE_STORAGE_LOADING.value,
                [key]: false,
            };
        }
    }

    async function executeBaseStorageCommand(guildId, baseId, values) {
        if (
            !SESSION_ID.value
            || !guildId
            || !baseId
            || !values?.container_id
            || !Number.isInteger(Number(values?.slot_index))
        ) {
            return false;
        }
        const key = baseStorageKey(guildId, baseId);
        BASE_STORAGE_LOADING.value = {
            ...BASE_STORAGE_LOADING.value,
            [key]: true,
        };
        try {
            const response = await POST(
                `/api/save/guilds/${encodeURIComponent(guildId)}` +
                `/bases/${encodeURIComponent(baseId)}/storage/commands`,
                {
                    session_id: SESSION_ID.value,
                    expected_revision: SESSION_REVISION.value,
                    ...values,
                    slot_index: Number(values.slot_index),
                }
            );
            if (
                !acceptResponse(
                    response,
                    "base-storage-command",
                    { command: true }
                )
            ) {
                return false;
            }
        } finally {
            BASE_STORAGE_LOADING.value = {
                ...BASE_STORAGE_LOADING.value,
                [key]: false,
            };
        }
        return loadBaseStorage(guildId, baseId);
    }

    function updateBaseStorageItemCount(guildId, baseId, container, slot, count) {
        const normalizedCount = Number(count);
        if (
            slot?.state !== "occupied"
            || !Number.isInteger(normalizedCount)
            || normalizedCount < 1
            || normalizedCount > 2147483647
        ) {
            return false;
        }
        return executeBaseStorageCommand(guildId, baseId, {
            command: "update_item_count",
            container_id: container.container_id,
            slot_index: slot.slot_index,
            expected_static_id: slot.item.static_id,
            count: normalizedCount,
        });
    }

    function putBaseStorageItem(
        guildId,
        baseId,
        container,
        slot,
        staticId,
        count = 1,
        mode = "empty_only",
        dynamicInit = null,
    ) {
        const normalizedCount = Number(count);
        if (
            !staticId
            || !Number.isInteger(normalizedCount)
            || normalizedCount < 1
            || !["empty_only", "replace"].includes(mode)
        ) {
            return false;
        }
        const command = {
            command: "put_item",
            container_id: container.container_id,
            slot_index: slot.slot_index,
            static_id: staticId,
            count: normalizedCount,
            mode,
        };
        if (dynamicInit !== null) command.dynamic_init = dynamicInit;
        return executeBaseStorageCommand(guildId, baseId, command);
    }

    function clearBaseStorageItem(guildId, baseId, container, slot) {
        if (slot?.state !== "occupied") return false;
        return executeBaseStorageCommand(guildId, baseId, {
            command: "clear_item_slot",
            container_id: container.container_id,
            slot_index: slot.slot_index,
            expected_static_id: slot.item.static_id,
            expected_dynamic_id: slot.item.dynamic_id,
        });
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
            updateGuildCollections(
                guildId,
                guild => {
                    guild.name = response.data.value?.name ?? normalizedName;
                }
            );
            return true;
        } finally {
            if (ownsLoadingFlag) LOADING_FLAG.value = false;
        }
    }

    async function updateGuildOwner(guildId, playerId) {
        if (!SESSION_ID.value || !guildId || !playerId) return false;
        const ownsLoadingFlag = !LOADING_FLAG.value;
        if (ownsLoadingFlag) LOADING_FLAG.value = true;
        try {
            const response = await POST(
                `/api/save/guilds/${encodeURIComponent(guildId)}/commands`,
                {
                    session_id: SESSION_ID.value,
                    expected_revision: SESSION_REVISION.value,
                    command: "update_guild_owner",
                    player_id: playerId,
                }
            );
            if (
                !acceptResponse(
                    response,
                    "update-guild-owner",
                    { command: true }
                )
            ) {
                return false;
            }
            const updatedMembers = new Map(
                (response.data.value?.members || []).map(
                    member => [String(member.player_id), member]
                )
            );
            updateGuildCollections(guildId, guild => {
                guild.owner_player_id =
                    response.data.value?.owner_player_id ?? playerId;
                guild.owner_status = "available";
                for (const member of guild.members || []) {
                    const updated = updatedMembers.get(
                        String(member.player_id)
                    );
                    if (updated) {
                        member.role = updated.role;
                        member.role_status = "available";
                    }
                    member.is_owner =
                        String(member.player_id)
                        === String(guild.owner_player_id);
                }
                guild.members?.sort((left, right) => (
                    (left.role ?? 99) - (right.role ?? 99)
                    || String(left.name || "").localeCompare(
                        String(right.name || "")
                    )
                    || String(left.player_id).localeCompare(
                        String(right.player_id)
                    )
                ));
            });
            return true;
        } finally {
            if (ownsLoadingFlag) LOADING_FLAG.value = false;
        }
    }

    async function updateGuildChestCapacity(guildId, capacity) {
        if (!SESSION_ID.value || !guildId) return false;
        const normalizedCapacity = Number(capacity);
        if (
            !Number.isInteger(normalizedCapacity)
            || normalizedCapacity < 1
            || normalizedCapacity > 2466
        ) {
            return false;
        }
        const ownsLoadingFlag = !LOADING_FLAG.value;
        if (ownsLoadingFlag) LOADING_FLAG.value = true;
        try {
            const response = await POST(
                `/api/save/guilds/${encodeURIComponent(guildId)}/commands`,
                {
                    session_id: SESSION_ID.value,
                    expected_revision: SESSION_REVISION.value,
                    command: "update_guild_chest_capacity",
                    capacity: normalizedCapacity,
                }
            );
            if (
                !acceptResponse(
                    response,
                    "update-guild-chest-capacity",
                    { command: true }
                )
            ) {
                return false;
            }
            updateGuildCollections(guildId, guild => {
                guild.guild_chest_capacity =
                    response.data.value?.capacity ?? normalizedCapacity;
                guild.guild_chest_status = "available";
            });
            return true;
        } finally {
            if (ownsLoadingFlag) LOADING_FLAG.value = false;
        }
    }

    async function updateGuildBaseCampLevel(guildId, level) {
        if (!SESSION_ID.value || !guildId) return false;
        const normalizedLevel = Number(level);
        if (
            !Number.isInteger(normalizedLevel)
            || normalizedLevel < 1
            || normalizedLevel > 35
        ) {
            return false;
        }
        const guild = GUILD_LIST.value.find(
            item => String(item.guild_id) === String(guildId)
        ) || GUILD_TREE.value.find(
            item => String(item.guild_id) === String(guildId)
        );
        const currentLevel = Number(guild?.base_camp_level);
        const lowering = Number.isInteger(currentLevel)
            && normalizedLevel < currentLevel;
        if (
            lowering
            && !await confirmMessage(
                getTranslatedText("Confirm_LowerGuildBaseCampLevel", [
                    currentLevel,
                    normalizedLevel,
                ])
            )
        ) {
            return false;
        }
        const ownsLoadingFlag = !LOADING_FLAG.value;
        if (ownsLoadingFlag) LOADING_FLAG.value = true;
        try {
            const response = await POST(
                `/api/save/guilds/${encodeURIComponent(guildId)}/commands`,
                {
                    session_id: SESSION_ID.value,
                    expected_revision: SESSION_REVISION.value,
                    command: "update_base_camp_level",
                    level: normalizedLevel,
                    ...(lowering
                        ? { confirm_base_camp_level_lowering: true }
                        : {}),
                }
            );
            if (
                !acceptResponse(
                    response,
                    "update-guild-base-camp-level",
                    { command: true }
                )
            ) {
                return false;
            }
            updateGuildCollections(guildId, guild => {
                guild.base_camp_level =
                    response.data.value?.level ?? normalizedLevel;
                guild.base_camp_level_status = "available";
            });
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

        await updateI18n({ refreshStaticData: false });

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
        const ownsLoadingFlag = !LOADING_FLAG.value;
        if (ownsLoadingFlag) LOADING_FLAG.value = true;
        try {
            if (
                SAVE_PLATFORM.value === "xgp"
                && !XGP_SAVE_CONFIRMED.value
                && !await confirmMessage(getTranslatedText("Confirm_Xgp_Save"))
            ) {
                return false;
            }
            const savePayload = {
                session_id: SESSION_ID.value,
                expected_revision: SESSION_REVISION.value,
            };
            if (SAVE_PLATFORM.value !== "xgp") {
                savePayload.WritePath = PAL_WRITE_BACK_PATH.value;
            }
            let response = await POST(
                "/api/save/save",
                savePayload,
                { errorContext: "save" },
            );
            if (response === false) return false;

            const repair = response?.error?.details?.repair;
            const repairCount = repair?.repair_count;
            const canRepairMissingGuildHandles = (
                response?.error?.code === "CHARACTER_INDEX_INVARIANT_FAILED"
                && repair?.available === true
                && repair?.kind === "missing_guild_handles"
                && Number.isInteger(repairCount)
                && repairCount > 0
            );
            if (canRepairMissingGuildHandles) {
                const confirmed = await confirmMessage(
                    getTranslatedText(
                        "Confirm_CharacterReferenceRepair",
                        [repairCount],
                    )
                );
                if (!confirmed) {
                    acceptResponse(response, "save");
                    return false;
                }
                const repairResponse = await POST(
                    "/api/save/repair-character-references",
                    {
                        session_id: SESSION_ID.value,
                        expected_revision: SESSION_REVISION.value,
                    },
                    { errorContext: "save-repair" },
                );
                if (repairResponse === false) return false;
                if (
                    !acceptResponse(
                        repairResponse,
                        "save-repair",
                        { command: true },
                    )
                ) {
                    alert(LAST_ERROR.value?.message || repairResponse.msg);
                    return false;
                }
                if (repairResponse.data?.saveCapabilities) {
                    SAVE_CAPABILITIES.value =
                        repairResponse.data.saveCapabilities;
                }
                savePayload.expected_revision = SESSION_REVISION.value;
                response = await POST(
                    "/api/save/save",
                    savePayload,
                    { errorContext: "save" },
                );
                if (response === false) return false;
            }

            if (response.status == 0) {
                LAST_SAVE_RESULT.value = response.data;
                if (response.data.session) {
                    await loadSessionState({
                        session: response.data.session,
                        compatibility: response.data.compatibility,
                    });
                } else {
                    SESSION_REVISION.value = response.data.revision;
                    PENDING_CHANGE_COUNT.value = 0;
                }
                RAW_JSON_PENDING.value = Boolean(
                    response.data.session?.raw_json_pending
                    ?? response.data.raw_json_pending
                );
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
                alert(Alert_Successful_Save, { tone: "success" });
                retval = true;
            } else if (response.status == 2) {
                alert("Unauthorized Access, Please Login. ");
                IS_LOCKED.value = true;
                reset();
            } else {
                acceptResponse(response, "save");
                alert(`- writeSave - Error occured: ${response.msg}`);
            }
            return retval;
        } finally {
            if (ownsLoadingFlag) LOADING_FLAG.value = false;
        }
    }

    async function pickMigrationPath(currentPath = "") {
        const nativePicker = window.pywebview?.api?.select_save_directory;
        if (typeof nativePicker === "function") {
            try {
                const selected = await nativePicker(
                    currentPath || PAL_GAME_SAVE_PATH.value
                );
                if (typeof selected === "string" && selected.trim()) {
                    return selected.trim();
                }
                if (selected === null) return null;
                console.warn(
                    "Native migration directory picker returned no usable path."
                );
            } catch (error) {
                console.error("Native migration directory picker failed.", error);
            }
        }
        const systemResponse = await POST("/api/save/select-directory", {
            path: currentPath || PAL_GAME_SAVE_PATH.value || undefined,
        });
        if (systemResponse?.status === 0) {
            const selected = systemResponse.data?.path;
            if (systemResponse.data?.cancelled === true || selected === null) {
                return null;
            }
            if (typeof selected === "string" && selected.trim()) {
                return selected.trim();
            }
        }
        return await promptMessage(
            getTranslatedText("Migration_PathPrompt"),
            {
                defaultValue: currentPath || PAL_GAME_SAVE_PATH.value || "",
                inputLabel: getTranslatedText("Migration_PathPlaceholder"),
            },
        );
    }

    async function pickMigrationWgsDirectory() {
        const selected = await pickMigrationPath(XGP_WGS_PATH.value || "");
        if (!selected) return false;
        return discoverXgpSources(selected);
    }

    async function analyzeMigration(requestPayload) {
        MIGRATION_LOADING.value = true;
        MIGRATION_STAGE.value = "analyzing";
        MIGRATION_PLAN.value = null;
        MIGRATION_RESULT.value = null;
        LAST_ERROR.value = null;
        try {
            const response = await POST(
                "/api/migration/analyze",
                requestPayload,
                { errorContext: "migration" },
            );
            if (!acceptResponse(response, "migration")) return false;
            MIGRATION_PLAN.value = response.data;
            MIGRATION_STAGE.value = response.data.blockers?.length
                ? "failed"
                : "analyzed";
            return response.data;
        } finally {
            MIGRATION_LOADING.value = false;
        }
    }

    function clearMigrationAnalysis() {
        if (MIGRATION_LOADING.value) return;
        MIGRATION_STAGE.value = null;
        MIGRATION_PLAN.value = null;
        MIGRATION_RESULT.value = null;
        if (LAST_ERROR.value?.context === "migration") {
            LAST_ERROR.value = null;
        }
    }

    async function executeMigration(payload) {
        MIGRATION_LOADING.value = true;
        MIGRATION_STAGE.value = "backing_up";
        MIGRATION_RESULT.value = null;
        LAST_ERROR.value = null;
        let statusRequestInFlight = false;
        const pollStatus = async () => {
            if (statusRequestInFlight) return;
            statusRequestInFlight = true;
            try {
                const response = await POST("/api/migration/status", {
                    plan_id: payload.plan_id,
                    operation_id: payload.confirmation?.operation_id || "",
                });
                if (response?.status === 0 && response.data?.stage) {
                    MIGRATION_STAGE.value = response.data.stage;
                }
            } finally {
                statusRequestInFlight = false;
            }
        };
        let statusTimer = null;
        try {
            const execution = POST(
                "/api/migration/execute",
                payload,
                { errorContext: "migration" },
            );
            statusTimer = setInterval(pollStatus, 250);
            const response = await execution;
            if (!acceptResponse(response, "migration")) {
                MIGRATION_STAGE.value = "failed";
                return false;
            }
            MIGRATION_RESULT.value = response.data;
            MIGRATION_STAGE.value = response.data.status;
            return response.data;
        } finally {
            if (statusTimer !== null) clearInterval(statusTimer);
            MIGRATION_LOADING.value = false;
        }
    }

    async function exportSteamCopy() {
        const targetPath = await promptMessage(getTranslatedText("Prompt_Xgp_Export_Target"));
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
            alert(getTranslatedText("Alert_Xgp_Export_Success", [targetPath]), {
                tone: "success",
            });
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
        if (GLOBAL_PALBOX_SESSION.value) {
            const pal = PAL_MAP.value.get(palId);
            if (!pal) return false;
            SELECTED_PAL_ID.value = palId;
            SELECTED_PAL_DATA.value = pal;
            SHOW_PLAYER_EDIT_FLAG.value = false;
            return true;
        }
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
        if (GLOBAL_PALBOX_SESSION.value) {
            return updateGlobalPalboxFromEditor(e);
        }
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
        if (key === "RemoveImportedCharacterTag" && !await confirmMessage(
            getTranslatedText("Confirm_RemoveImportedCharacterTag")
        )) {
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
        } else if (key === "RemoveImportedCharacterTag") {
            payload = {
                ...base,
                command: "update_pal_enhancement",
                values: { remove_imported: true },
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
                const selectedIndex = Number.isInteger(value?.index)
                    && passive[value.index] === value.skill
                    ? value.index
                    : passive.indexOf(value?.skill || value);
                if (selectedIndex >= 0) passive.splice(selectedIndex, 1);
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
                passive: key.includes("Passive") ? passive : null,
                unrestricted: key.includes("Passive") && !HIDE_INVALID_OPTIONS.value,
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
            if (!await confirmMessage(getTranslatedText(
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

    async function addCustomPassive(internalName) {
        if (!SELECTED_PAL_ID.value || !SELECTED_PAL_DATA.value) {
            LAST_ERROR.value = {
                context: "add-custom-passive",
                code: "PAL_NOT_SELECTED",
                message: "Select a Pal first.",
                details: {},
            };
            return false;
        }

        if (GLOBAL_PALBOX_SESSION.value) {
            return Boolean(await updateGlobalPalboxPal(
                SELECTED_PAL_ID.value,
                {
                    passive: [
                        ...(SELECTED_PAL_DATA.value.PassiveSkillList || []),
                        internalName,
                    ],
                },
            ));
        }

        const passive = [
            ...(SELECTED_PAL_DATA.value.PassiveSkillList || []),
            internalName,
        ];
        const ownsLoadingFlag = !LOADING_FLAG.value;
        if (ownsLoadingFlag) LOADING_FLAG.value = true;
        try {
            const response = await POST(
                `/api/pal/${encodeURIComponent(SELECTED_PAL_ID.value)}/commands`,
                {
                    session_id: SESSION_ID.value,
                    expected_revision: SESSION_REVISION.value,
                    command: "update_pal_skills",
                    active: null,
                    mastered: null,
                    passive,
                    allow_custom_passive: true,
                    unrestricted: !HIDE_INVALID_OPTIONS.value,
                }
            );
            if (!acceptResponse(
                response,
                "add-custom-passive",
                { command: true }
            )) {
                return false;
            }
            await selectPal(SELECTED_PAL_ID.value, true);
            UPDATE_PAL_RESELECT_CTR.value++;
            return true;
        } finally {
            if (ownsLoadingFlag) LOADING_FLAG.value = false;
        }
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
            alert(getTranslatedText("Alert_PalDataCopied"), { tone: "success" });
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
        const sortedPals = sortPalList(
            visiblePals,
            PAL_LIST_SORT_MODES.CONTAINER
        );
        if (!BASE_PAL_BTN_CLK_FLAG.value) {
            const partyPal = sortedPals.find(
                (pal) => pal.ContainerType === "PARTY"
            );
            if (partyPal) return partyPal.InstanceId;
        }
        return sortedPals[0]?.InstanceId;
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
        if (GLOBAL_PALBOX_SESSION.value) {
            const ids = Array.from(PAL_MAP.value.keys());
            const currentIndex = ids.indexOf(SELECTED_PAL_ID.value);
            const nextId = ids[currentIndex + 1] || ids[currentIndex - 1] || null;
            const deleted = await deleteGlobalPalboxPal(SELECTED_PAL_ID.value);
            if (!deleted) return false;
            SELECTED_PAL_ID.value = nextId;
            SELECTED_PAL_DATA.value = nextId ? PAL_MAP.value.get(nextId) : null;
            return true;
        }
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
        const confirmed = await confirmMessage(getTranslatedText(
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
        if (GLOBAL_PALBOX_SESSION.value) {
            const added = await addGlobalPalboxPal(speciesId);
            if (!added) return false;
            const values = {};
            if (Array.isArray(options.passive)) values.passive = [...options.passive];
            if (options.maxPal) {
                Object.assign(values, {
                    level: MAX_LEVEL,
                    iv_hp: 100,
                    iv_melee: 100,
                    iv_shot: 100,
                    iv_defense: 100,
                    soul_hp: MAX_SOULS_LEVEL.value,
                    soul_attack: MAX_SOULS_LEVEL.value,
                    soul_defense: MAX_SOULS_LEVEL.value,
                    soul_craft_speed: MAX_SOULS_LEVEL.value,
                    rank: 5,
                    is_awakened: true,
                });
            }
            if (options.maxWork) {
                values.work_suitability = Object.fromEntries(
                    Object.keys(added.Suitabilities || {}).map(name => [
                        name,
                        MAX_SUITABILITY_LEVEL.value,
                    ]),
                );
            }
            if (Object.keys(values).length) {
                await updateGlobalPalboxPal(added.InstanceId, values);
            }
            await selectPal(added.InstanceId);
            return true;
        }
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
        if (GLOBAL_PALBOX_SESSION.value) {
            const clone = await cloneGlobalPalboxPal(SELECTED_PAL_ID.value);
            if (!clone) return false;
            await selectPal(clone.InstanceId);
            return true;
        }
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
        if (!await confirmMessage(getTranslatedText(
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
        GUILD_LIST,
        GUILD_LOADING,
        BASE_STORAGE_BY_BASE,
        BASE_STORAGE_LOADING,
        PAL_MAP,
        EXPEDITION_DATA,
        EXPEDITION_LOADING,
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
        PAL_FILE_PICKER_SELECTION,
        IS_PAL_SAVE_PATH,
        FILE_PICKER_PURPOSE,
        IS_PATH_PICKER_ROOT_VIEW,

        SHOW_PLAYER_EDIT_FLAG,
        HAS_WORKING_PAL_FLAG,
        BASE_PAL_BTN_CLK_FLAG,
        PAL_GAME_SAVE_PATH,
        GLOBAL_PALBOX_PATH,
        GLOBAL_PALBOX_SOURCE_MODE,
        GLOBAL_PALBOX_XGP_PATH,
        PAL_WRITE_BACK_PATH,
        SAVE_SOURCE_MODE,
        REMOTE_SERVER_ADDRESS,
        REMOTE_CERTIFICATE_FINGERPRINT,
        REMOTE_ALLOW_INSECURE_LOCAL,
        REMOTE_REMEMBER_CREDENTIAL,
        REMOTE_CREDENTIAL_SAVED,
        REMOTE_CREDENTIAL_STORAGE_AVAILABLE,
        REMOTE_SESSION_ID,
        REMOTE_SESSION_REVISION,
        REMOTE_SERVER,
        REMOTE_STATUS,
        REMOTE_PLAYERS,
        REMOTE_PLAYER_DIRECTORY,
        REMOTE_GUILDS,
        REMOTE_PLAYER_DETAILS,
        REMOTE_PLAYER_DETAILS_LOADING,
        REMOTE_MAP_DATA,
        REMOTE_MAP_LOADING,
        REMOTE_CAPABILITIES,
        REMOTE_LOADING,
        REMOTE_CONNECTED,
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
        RAW_JSON_PENDING,
        SAVE_COMPATIBILITY,
        LAST_ERROR,
        LAST_SAVE_RESULT,
        MIGRATION_LOADING,
        MIGRATION_STAGE,
        MIGRATION_PLAN,
        MIGRATION_RESULT,
        ITEM_CATALOG_RESULTS,
        ITEM_CLIPBOARD,
        PLAYER_MISSIONS,
        MISSION_LOADING,
        ARENA_LEADERBOARD,
        ARENA_EDITABLE_COUNT,
        ARENA_RANKED_PLAYER_COUNT,
        ARENA_INITIALIZABLE_COUNT,
        ARENA_UNSUPPORTED_COUNT,
        ARENA_NPC_COUNT,
        ARENA_NPC_SOURCE_BUILD,
        ARENA_LOADING,
        MAP_DATA,
        MAP_LOADING,
        OVERVIEW_DATA,
        OVERVIEW_LOADING,
        GLOBAL_PALBOX_SESSION,
        GLOBAL_PALBOX_PALS,
        GLOBAL_PALBOX_CATALOG,
        GLOBAL_PALBOX_XGP_SOURCES,
        SELECTED_GLOBAL_PALBOX_XGP_SOURCE_ID,
        GLOBAL_PALBOX_LOADING,
        GLOBAL_PALBOX_ERROR,
        VERSION,
        IS_OFFICIAL_BUILD,
        AVAILABLE_UPDATE,
        SKIP_UPDATE_CHECK,
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
        refreshSave,
        updateI18n,
        fetchStaticData,
        loadSave,
        connectLocalGame,
        connectRemote,
        loadRemoteProfile,
        resumeRemoteSession,
        refreshRemoteStatus,
        loadRemotePlayers,
            loadRemoteGuilds,
            loadRemoteMapData,
            loadRemotePlayerDetails,
            loadRemotePlayerInventory,
            loadRemotePlayerPals,
            executeRemoteCommand,
        disconnectRemote,
        resumeCurrentSession,
        queryPlayers,
        loadGuilds,
        getBaseStorage,
        isBaseStorageLoading,
        loadBaseStorage,
        loadOverview,
        loadExpeditions,
        loadArenaLeaderboard,
        setArenaRankPoint,
        resetArenaPlayer,
        resetArenaLeaderboard,
        loadMapData,
        selectLocalData,
        confirmLocalDataFileSelection,
        clearFogOfWar,
        resetFogOfWar,
        unlockAllFastTravelPoints,
        updatePlayerInventoryCapacity,
        loadJsonEditorFiles,
        loadJsonDocument,
        applyJsonDocument,
        updateGuildName,
        updateGuildOwner,
        updateGuildChestCapacity,
        updateGuildBaseCampLevel,
        updateBaseStorageItemCount,
        putBaseStorageItem,
        clearBaseStorageItem,
        queryPals,
        clearPalQuery,
        selectPlayer,
        selectBase,
        selectPal,
        updatePal,
        addCustomPassive,
        updatePlayer,
        updatePlayerAttributes,
        updatePlayerConsumableBonuses,
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
        swapInventorySlots,
        sortInventoryContainer,
        fillInventorySlots,
        loadDynamicItemAttributes,
        updateDynamicItemAttributes,
        exportPreset,
        applyPreset,
        maxSelectedPal,
        executeBatchOperations,
        healAllPals,
        healAllPalsInSave,
        completeActiveExpeditions,
        completeExpedition,
        unlockExpeditionPals,
        cancelSelectedPalExpedition,
        refreshSessionMetadata,
        writeSave,
        pickMigrationPath,
        pickMigrationWgsDirectory,
        analyzeMigration,
        clearMigrationAnalysis,
        executeMigration,
        exportSteamCopy,
        discoverXgpSources,
        initializeGlobalPalbox,
        discoverGlobalPalboxXgp,
        openGlobalPalbox,
        updateGlobalPalboxPal,
        addGlobalPalboxPal,
        cloneGlobalPalboxPal,
        deleteGlobalPalboxPal,
        saveGlobalPalbox,
        closeGlobalPalbox,
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
        show_path_picker_roots,
        update_picker_result,
        path_back
    };
});
