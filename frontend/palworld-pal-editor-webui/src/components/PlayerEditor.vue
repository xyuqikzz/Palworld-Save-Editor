<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { usePalEditorStore } from '@/stores/paleditor'
import ItemCard from '@/components/modules/TechCard.vue'
import AppIcon from '@/components/modules/AppIcon.vue'
import InventoryEditor from '@/components/InventoryEditor.vue'
import MissionEditor from '@/components/MissionEditor.vue'
import {
    OFFLINE_PLAYER_TABS,
    PlayerManagementModel,
} from '@/components/modules/player-management-model'

const palStore = usePalEditorStore()
const route = useRoute()
const router = useRouter()
const playerEditorTabs = OFFLINE_PLAYER_TABS
const playerModel = computed(() => (
    PlayerManagementModel.fromOffline(palStore.SELECTED_PLAYER_DATA)
))

const fogClearCapability = computed(() => (
    palStore.SAVE_CAPABILITIES?.fogOfWarClear || {
        available: false,
        reason: 'FOG_OF_WAR_STRUCTURE_UNSUPPORTED',
    }
))
const fogClearReason = computed(() => (
    fogClearCapability.value.available
        ? ''
        : palStore.getTranslatedText(
            fogClearCapability.value.reason || 'FOG_OF_WAR_STRUCTURE_UNSUPPORTED',
        )
))
const fogResetCapability = computed(() => (
    palStore.SAVE_CAPABILITIES?.fogOfWarReset || {
        available: false,
        reason: 'FOG_OF_WAR_STRUCTURE_UNSUPPORTED',
    }
))
const fogResetReason = computed(() => (
    fogResetCapability.value.available
        ? ''
        : palStore.getTranslatedText(
            fogResetCapability.value.reason || 'FOG_OF_WAR_STRUCTURE_UNSUPPORTED',
        )
))
const localDataSelection = computed(() => (
    palStore.SAVE_CAPABILITIES?.localDataSelection || {
        selected: false,
        platform: palStore.SAVE_PLATFORM,
        canSelectFile: palStore.SAVE_PLATFORM === 'steam',
        source: null,
        reason: 'LOCAL_DATA_NOT_SELECTED',
    }
))
const fastTravelCapability = computed(() => (
    palStore.SELECTED_PLAYER_DATA.FastTravelUnlockCapability || {
        available: false,
        reason: 'FAST_TRAVEL_RECORD_DATA_MISSING',
        unlocked_count: null,
        total_count: 0,
    }
))
const fastTravelReason = computed(() => (
    fastTravelCapability.value.available
        ? ''
        : palStore.getTranslatedText(
            fastTravelCapability.value.reason || 'FAST_TRAVEL_STRUCTURE_UNSUPPORTED',
        )
))
const inventoryCapacityCapability = computed(() => (
    palStore.SELECTED_PLAYER_DATA.InventoryCapacityCapability || {
        available: false,
        reason: 'PLAYER_INVENTORY_CONTAINER_MISSING',
        current_capacity: null,
        allowed_capacities: [],
        minimum_capacity: null,
        maximum_capacity: 1000,
        custom_input: true,
        expand_only: false,
    }
))
const inventoryCapacityReason = computed(() => (
    inventoryCapacityCapability.value.available
        ? ''
        : palStore.getTranslatedText(
            inventoryCapacityCapability.value.reason
                || 'PLAYER_INVENTORY_CAPACITY_UNSUPPORTED',
        )
))
const inventoryCapacityTarget = ref(null)
const inventoryCapacityTargetValid = computed(() => {
    const target = Number(inventoryCapacityTarget.value)
    const current = Number(inventoryCapacityCapability.value.current_capacity)
    const minimum = Number(inventoryCapacityCapability.value.minimum_capacity)
    const maximum = Number(inventoryCapacityCapability.value.maximum_capacity)
    return Number.isInteger(target)
        && Number.isInteger(current)
        && Number.isInteger(minimum)
        && Number.isInteger(maximum)
        && target !== current
        && target >= minimum
        && target <= maximum
})

watch(
    inventoryCapacityCapability,
    (capability) => {
        const current = Number(capability.current_capacity)
        const minimum = Number(capability.minimum_capacity)
        const maximum = Number(capability.maximum_capacity)
        if (
            !Number.isInteger(Number(inventoryCapacityTarget.value))
            || Number(inventoryCapacityTarget.value) < minimum
            || Number(inventoryCapacityTarget.value) > maximum
        ) {
            inventoryCapacityTarget.value =
                Number.isInteger(current)
                    && Number.isInteger(minimum)
                    && Number.isInteger(maximum)
                    && minimum <= maximum
                    ? Math.min(Math.max(current, minimum), maximum)
                    : null
        }
    },
    { immediate: true },
)

function requestedEditorTab() {
    const tab = Array.isArray(route.query.tab) ? route.query.tab[0] : route.query.tab
    if (!playerEditorTabs.has(tab)) return 'inventory'
    if (tab === 'attributes' && !palStore.SELECTED_PLAYER_DATA.PlayerAttributes?.length) {
        return 'inventory'
    }
    return tab
}

const activeEditorTab = computed({
    get: requestedEditorTab,
    set: async (tab) => {
        if (!playerEditorTabs.has(tab)) return
        const query = { ...route.query }
        if (tab === 'inventory') delete query.tab
        else query.tab = tab
        await router.replace({ query })
    },
})

watch(
    () => [route.query.tab, palStore.SELECTED_PLAYER_DATA.PlayerAttributes?.length],
    async () => {
        if (route.query.tab && requestedEditorTab() === 'inventory') {
            const query = { ...route.query }
            delete query.tab
            await router.replace({ query })
        }
    },
    { immediate: true },
)

const isMaxLv = () => {
    return palStore.SELECTED_PLAYER_DATA.Level >= (palStore.HIDE_INVALID_OPTIONS ? palStore.MAX_LEVEL : palStore.MAX_INVALID_LEVEL);
};

const isMinLv = () => {
    return palStore.SELECTED_PLAYER_DATA.Level <= 1;
};

const setPlayerAttributeToMaximum = (attribute) => {
    attribute.rank = attribute.max_rank
}

const setAllPlayerAttributesToMaximum = () => {
    for (const attribute of palStore.SELECTED_PLAYER_DATA.PlayerAttributes || []) {
        setPlayerAttributeToMaximum(attribute)
    }
}

const consumableBonusCapability = computed(() => (
    palStore.SELECTED_PLAYER_DATA.PlayerConsumableBonuses || {
        available: false,
        reason: 'PLAYER_CONSUMABLE_BONUS_FIELD_MISSING',
        reduce_only: false,
        values: [],
    }
))
const consumableBonusReason = computed(() => (
    consumableBonusCapability.value.available
        ? ''
        : palStore.getTranslatedText(
            consumableBonusCapability.value.reason
                || 'PLAYER_CONSUMABLE_BONUS_STRUCTURE_UNSUPPORTED',
        )
))
const clearAllConsumableBonuses = () => {
    for (const bonus of consumableBonusCapability.value.values || []) {
        bonus.value = 0
    }
}

const formatAttributeEffect = (value) => {
    if (value === null || value === undefined) return ''
    return Number.isInteger(value) ? String(value) : Number(value).toFixed(1)
}
</script>

<template>
    <div class="PalEditor player-editor-layout">
        <section class="EditorItem item flex-v basicInfo player-summary-card">
            <header class="player-summary-heading">
                <h2>{{ palStore.getTranslatedText("Editor_Basic_Info") }}</h2>
                <div class="player-summary-identity">
                    <strong>{{ playerModel.name }}</strong>
                    <span>{{ palStore.getTranslatedText('Common_LevelWithValue', [playerModel.level]) }}</span>
                </div>
            </header>
            <div class="player-basic-grid">
                <div class="editField">
                    <p class="const">
                        {{ palStore.getTranslatedText("Editor_Nickname") }}
                    </p>
                    <input class="edit" type="text" name="NickName" v-model="palStore.SELECTED_PLAYER_DATA.NickName">
                    <button class="edit" @click="palStore.updatePlayer" name="NickName"
                        :value="palStore.SELECTED_PLAYER_DATA.NickName" :disabled="palStore.LOADING_FLAG" :title="palStore.getTranslatedText('Common_Save')"><AppIcon name="check" /></button>
                </div>
                <div class="editField">
                    <p class="const">
                        {{ palStore.getTranslatedText("Editor_TechPoint") }}
                    </p>
                    <input class="edit" type="number" name="TechnologyPoint" v-model="palStore.SELECTED_PLAYER_DATA.TechnologyPoint" min="0" max="65535">
                    <button class="edit" @click="palStore.updatePlayer" name="TechnologyPoint"
                        :value="palStore.SELECTED_PLAYER_DATA.TechnologyPoint" :disabled="palStore.LOADING_FLAG" :title="palStore.getTranslatedText('Common_Save')"><AppIcon name="check" /></button>
                </div>
                <div class="editField">
                    <p class="const">
                        {{ palStore.getTranslatedText("Editor_BossTechPoint") }}
                    </p>
                    <input class="edit" type="number" name="bossTechnologyPoint" v-model="palStore.SELECTED_PLAYER_DATA.bossTechnologyPoint" min="0" max="65535">
                    <button class="edit" @click="palStore.updatePlayer" name="bossTechnologyPoint"
                        :value="palStore.SELECTED_PLAYER_DATA.bossTechnologyPoint" :disabled="palStore.LOADING_FLAG" :title="palStore.getTranslatedText('Common_Save')"><AppIcon name="check" /></button>
                </div>
                <div class="editField">
                    <p class="const"> {{ palStore.getTranslatedText('Common_LevelShort') }} {{ palStore.SELECTED_PLAYER_DATA.Level }}</p>
                    <button class="edit" @click="palStore.SELECTED_PLAYER_DATA.levelDown" name="Level"
                        :disabled="palStore.LOADING_FLAG || isMinLv()" :title="palStore.getTranslatedText('Common_Decrease')"><AppIcon name="chevron-down" /></button>
                    <button class="edit" @click="palStore.SELECTED_PLAYER_DATA.levelUp" name="Level"
                        :disabled="palStore.LOADING_FLAG || isMaxLv()" :title="palStore.getTranslatedText('Common_Increase')"><AppIcon name="chevron-up" /></button>
                    <button class="edit" @click="palStore.SELECTED_PLAYER_DATA.maxLevel" name="Level"
                        :disabled="palStore.LOADING_FLAG || isMaxLv()" :title="palStore.getTranslatedText('Common_SetMaximum')"><AppIcon name="chevrons-up" /></button>
                </div>
            </div>
        </section>
        <nav
            class="player-editor-tabs"
            role="tablist"
            :aria-label="palStore.getTranslatedText('PlayerEditor_Overview')"
        >
            <button
                id="player-inventory-tab"
                type="button"
                role="tab"
                :class="{ active: activeEditorTab === 'inventory' }"
                :aria-selected="activeEditorTab === 'inventory'"
                aria-controls="player-inventory-panel"
                @click="activeEditorTab = 'inventory'"
            >{{ palStore.getTranslatedText('PlayerTab_Inventory') }}</button>
            <button
                id="player-technology-tab"
                type="button"
                role="tab"
                :class="{ active: activeEditorTab === 'technology' }"
                :aria-selected="activeEditorTab === 'technology'"
                aria-controls="player-technology-panel"
                @click="activeEditorTab = 'technology'"
            >{{ palStore.getTranslatedText('PlayerTab_Technology') }}</button>
            <button
                id="player-missions-tab"
                type="button"
                role="tab"
                :class="{ active: activeEditorTab === 'missions' }"
                :aria-selected="activeEditorTab === 'missions'"
                aria-controls="player-missions-panel"
                @click="activeEditorTab = 'missions'"
            >{{ palStore.getTranslatedText('PlayerTab_Missions') }}</button>
            <button
                v-if="palStore.SELECTED_PLAYER_DATA.PlayerAttributes?.length"
                id="player-attributes-tab"
                type="button"
                role="tab"
                :class="{ active: activeEditorTab === 'attributes' }"
                :aria-selected="activeEditorTab === 'attributes'"
                aria-controls="player-attributes-panel"
                @click="activeEditorTab = 'attributes'"
            >{{ palStore.getTranslatedText('PlayerTab_Attributes') }}</button>
            <button
                id="player-map-progress-tab"
                type="button"
                role="tab"
                :class="{ active: activeEditorTab === 'map-progress' }"
                :aria-selected="activeEditorTab === 'map-progress'"
                aria-controls="player-map-progress-panel"
                @click="activeEditorTab = 'map-progress'"
            >{{ palStore.getTranslatedText('PlayerTab_MapProgress') }}</button>
        </nav>
        <InventoryEditor
            v-show="activeEditorTab === 'inventory'"
            id="player-inventory-panel"
            role="tabpanel"
            aria-labelledby="player-inventory-tab"
        />
        <!-- <div class="EditorItem flex-v item left">
            <p class="cat">
                {{ palStore.getTranslatedText("Editor_IV") }}
            </p>
        </div> -->
        <section
            v-show="activeEditorTab === 'technology'"
            id="player-technology-panel"
            class="EditorItem item left flex-v technology-panel"
            role="tabpanel"
            aria-labelledby="player-technology-tab"
        >
            <header class="technology-actions">
                <button class="edit text" @click="palStore.updatePlayer" name="unlock_all_techs"
                    :disabled="palStore.LOADING_FLAG">{{ palStore.getTranslatedText("Editor_UnlockAllTech") }}</button>
            </header>
            <div class="EditorItem flex-h maxW no-margin">
                <div class="levels-container">
                    <div class="level-row" v-for="(items, level) in palStore.TECH_LV_DICT" :key="level">
                        <div class="level-indicator">
                            {{ palStore.getTranslatedText('Common_LevelWithValue', [level]) }}
                        </div>
                        <div class="cards-row">
                            <ItemCard v-for="item in items" :key="item.InternalName" :item="item" />
                        </div>
                    </div>
                </div>
            </div>
        </section>
        <MissionEditor
            v-show="activeEditorTab === 'missions'"
            id="player-missions-panel"
            role="tabpanel"
            aria-labelledby="player-missions-tab"
        />
        <section
            v-show="activeEditorTab === 'map-progress'"
            id="player-map-progress-panel"
            class="EditorItem player-map-progress-panel"
            role="tabpanel"
            aria-labelledby="player-map-progress-tab"
        >
            <article class="player-map-action">
                <div class="player-map-action__heading">
                    <strong>{{ palStore.getTranslatedText('Map_FogReset_Title') }}</strong>
                    <span
                        class="player-map-action__source"
                        :aria-label="palStore.getTranslatedText('Map_FogReset_Description')"
                        :title="palStore.getTranslatedText('Map_FogReset_Description')"
                    >{{ palStore.getTranslatedText('PlayerMap_RequiredSaveFile') }} <code>{{ palStore.getTranslatedText('PlayerMap_FogSaveFile') }}</code></span>
                    <p
                        v-if="fogClearReason || fogResetReason"
                        id="player-fog-reason"
                        class="player-map-action__reason"
                        role="status"
                    >{{ fogClearReason || fogResetReason }}</p>
                </div>
                <div class="player-map-action__actions">
                    <button
                        type="button"
                        class="player-map-action__button player-map-action__button--wide player-map-action__button--secondary"
                        :disabled="palStore.LOADING_FLAG"
                        :title="localDataSelection.source || palStore.getTranslatedText('PlayerMap_LocalData_Select')"
                        @click="palStore.selectLocalData"
                    >{{ palStore.getTranslatedText(
                        localDataSelection.selected
                            ? 'PlayerMap_LocalData_Reselect'
                            : 'PlayerMap_LocalData_Select'
                    ) }}</button>
                    <button
                        type="button"
                        class="player-map-action__button"
                        :aria-describedby="fogClearReason ? 'player-fog-reason' : undefined"
                        :disabled="palStore.LOADING_FLAG || !fogClearCapability.available"
                        :title="fogClearReason || palStore.getTranslatedText('Map_FogClear_Button')"
                        @click="palStore.clearFogOfWar"
                    >{{ palStore.getTranslatedText('Map_FogClear_Button') }}</button>
                    <button
                        type="button"
                        class="player-map-action__button player-map-action__button--danger"
                        :aria-describedby="fogResetReason ? 'player-fog-reason' : undefined"
                        :disabled="palStore.LOADING_FLAG || !fogResetCapability.available"
                        :title="fogResetReason || palStore.getTranslatedText('Map_FogReset_Button')"
                        @click="palStore.resetFogOfWar"
                    >{{ palStore.getTranslatedText('Map_FogReset_Button') }}</button>
                </div>
            </article>
            <article class="player-map-action">
                <div class="player-map-action__heading">
                    <strong>{{ palStore.getTranslatedText('PlayerMap_FastTravel_Title') }}</strong>
                    <span
                        class="player-map-action__source"
                        :aria-label="palStore.getTranslatedText('PlayerMap_FastTravel_Description')"
                        :title="palStore.getTranslatedText('PlayerMap_FastTravel_Description')"
                    >{{ palStore.getTranslatedText('PlayerMap_RequiredSaveFile') }} <code>{{ palStore.getTranslatedText('PlayerMap_FastTravelSaveFile') }}</code></span>
                    <p
                        v-if="fastTravelReason"
                        id="player-fast-travel-reason"
                        class="player-map-action__reason"
                        role="status"
                    >{{ fastTravelReason }}</p>
                </div>
                <span v-if="fastTravelCapability.available" class="player-map-action__progress">
                    {{ palStore.getTranslatedText('PlayerMap_FastTravel_Progress', [
                        fastTravelCapability.unlocked_count,
                        fastTravelCapability.total_count,
                    ]) }}
                </span>
                <div class="player-map-action__actions player-map-action__actions--single">
                    <button
                        type="button"
                        class="player-map-action__button"
                        :aria-describedby="fastTravelReason ? 'player-fast-travel-reason' : undefined"
                        :disabled="palStore.LOADING_FLAG || !fastTravelCapability.available"
                        :title="fastTravelReason || palStore.getTranslatedText('PlayerMap_FastTravel_Button')"
                        @click="palStore.unlockAllFastTravelPoints"
                    >{{ palStore.getTranslatedText('PlayerMap_FastTravel_Button') }}</button>
                </div>
            </article>
            <article class="player-map-action">
                <div class="player-map-action__heading">
                    <strong>{{ palStore.getTranslatedText('PlayerInventoryCapacity_Title') }}</strong>
                    <span
                        class="player-map-action__source"
                        :title="palStore.getTranslatedText('PlayerInventoryCapacity_Description')"
                    >{{ palStore.getTranslatedText('PlayerMap_RequiredSaveFile') }} <code>{{ palStore.getTranslatedText('PlayerInventoryCapacity_SaveFile') }}</code></span>
                    <p
                        v-if="inventoryCapacityReason"
                        id="player-inventory-capacity-reason"
                        class="player-map-action__reason"
                        role="status"
                    >{{ inventoryCapacityReason }}</p>
                </div>
                <span
                    v-if="inventoryCapacityCapability.current_capacity !== null"
                    class="player-map-action__progress"
                >{{ palStore.getTranslatedText('PlayerInventoryCapacity_Current', [
                    inventoryCapacityCapability.current_capacity,
                ]) }}</span>
                <p class="player-map-action__notice">
                    {{ palStore.getTranslatedText('PlayerInventoryCapacity_PerformanceWarning') }}
                </p>
                <div class="player-map-action__capacity-control">
                    <input
                        v-model.number="inventoryCapacityTarget"
                        type="number"
                        step="1"
                        :min="inventoryCapacityCapability.minimum_capacity"
                        :max="inventoryCapacityCapability.maximum_capacity"
                        :disabled="palStore.LOADING_FLAG || !inventoryCapacityCapability.available"
                        :aria-label="palStore.getTranslatedText('PlayerInventoryCapacity_Target')"
                    >
                    <button
                        type="button"
                        class="player-map-action__button"
                        :aria-describedby="inventoryCapacityReason ? 'player-inventory-capacity-reason' : undefined"
                        :disabled="palStore.LOADING_FLAG
                            || !inventoryCapacityCapability.available
                            || !inventoryCapacityTargetValid"
                        @click="palStore.updatePlayerInventoryCapacity(inventoryCapacityTarget)"
                    >{{ palStore.getTranslatedText('PlayerInventoryCapacity_Button') }}</button>
                </div>
            </article>
        </section>
        <section
            v-show="activeEditorTab === 'attributes'"
            id="player-attributes-panel"
            class="EditorItem player-attributes-card"
            role="tabpanel"
            aria-labelledby="player-attributes-tab"
        >
            <header class="player-attributes-heading">
                <div class="player-attributes-actions">
                    <button
                        type="button"
                        class="attribute-secondary-action"
                        :disabled="palStore.LOADING_FLAG"
                        @click="setAllPlayerAttributesToMaximum"
                    >{{ palStore.getTranslatedText('PlayerAttributes_SetAllMaximum') }}</button>
                    <button
                        type="button"
                        class="attribute-primary-action"
                        :disabled="palStore.LOADING_FLAG"
                        @click="palStore.updatePlayerAttributes()"
                    ><AppIcon name="check" />{{ palStore.getTranslatedText('PlayerAttributes_SaveAll') }}</button>
                </div>
            </header>
            <div class="player-attributes-grid">
                <article
                    v-for="attribute in palStore.SELECTED_PLAYER_DATA.PlayerAttributes"
                    :key="attribute.key"
                    class="player-attribute-item"
                    :title="palStore.getTranslatedText(`PlayerAttribute_${attribute.key}_Description`)"
                >
                    <div class="player-attribute-main">
                        <img
                            :src="`/image/player_attributes/${attribute.icon}`"
                            :alt="palStore.getTranslatedText(`PlayerAttribute_${attribute.key}`)"
                        >
                        <div class="player-attribute-copy">
                            <strong>{{ palStore.getTranslatedText(`PlayerAttribute_${attribute.key}`) }}</strong>
                            <span v-if="attribute.kind === 'base'">
                                {{ palStore.getTranslatedText('PlayerAttributes_CurrentValue') }}
                                {{ attribute.display_value?.toLocaleString() }}
                            </span>
                            <span v-else-if="attribute.effect_percent !== null">
                                {{ palStore.getTranslatedText('PlayerAttributes_Bonus', [formatAttributeEffect(attribute.effect_percent)]) }}
                            </span>
                        </div>
                    </div>
                    <div class="player-attribute-controls">
                        <label class="player-attribute-rank">
                            <span class="sr-only">{{ palStore.getTranslatedText('PlayerAttributes_Rank') }}</span>
                            <input
                                v-model.number="attribute.rank"
                                class="player-attribute-input"
                                type="number"
                                min="0"
                                :max="attribute.max_rank"
                                step="1"
                                :disabled="palStore.LOADING_FLAG"
                                @keydown.enter="palStore.updatePlayerAttributes(attribute)"
                            >
                            <span>/ {{ attribute.max_rank }}</span>
                        </label>
                        <div class="player-attribute-actions">
                            <button
                                type="button"
                                class="player-attribute-max-action"
                                :disabled="palStore.LOADING_FLAG"
                                :title="palStore.getTranslatedText('Common_SetMaximum')"
                                @click="setPlayerAttributeToMaximum(attribute)"
                            >{{ palStore.getTranslatedText('Inventory_Max') }}</button>
                            <button
                                type="button"
                                class="player-attribute-save-action"
                                :disabled="palStore.LOADING_FLAG"
                                :title="palStore.getTranslatedText('Common_Save')"
                                @click="palStore.updatePlayerAttributes(attribute)"
                            ><AppIcon name="check" :size="15" /></button>
                        </div>
                    </div>
                </article>
            </div>
            <section class="player-consumable-bonuses" aria-labelledby="player-consumable-bonuses-title">
                <header class="player-consumable-bonuses__heading">
                    <div>
                        <h3 id="player-consumable-bonuses-title">
                            {{ palStore.getTranslatedText('PlayerConsumableBonuses_Title') }}
                        </h3>
                        <p>{{ palStore.getTranslatedText('PlayerConsumableBonuses_Description') }}</p>
                    </div>
                    <div v-if="consumableBonusCapability.available" class="player-attributes-actions">
                        <button
                            type="button"
                            class="attribute-secondary-action"
                            :disabled="palStore.LOADING_FLAG"
                            @click="clearAllConsumableBonuses"
                        >{{ palStore.getTranslatedText('PlayerConsumableBonuses_ClearAll') }}</button>
                        <button
                            type="button"
                            class="attribute-primary-action"
                            :disabled="palStore.LOADING_FLAG"
                            @click="palStore.updatePlayerConsumableBonuses()"
                        ><AppIcon name="check" />{{ palStore.getTranslatedText('PlayerAttributes_SaveAll') }}</button>
                    </div>
                </header>
                <p v-if="!consumableBonusCapability.available" class="player-consumable-bonuses__unavailable">
                    {{ consumableBonusReason }}
                </p>
                <div v-else class="player-consumable-bonuses__grid">
                    <article
                        v-for="bonus in palStore.SELECTED_PLAYER_DATA.PlayerConsumableBonuses.values"
                        :key="bonus.key"
                        class="player-consumable-bonus"
                    >
                        <img
                            :src="`/image/player_attributes/${bonus.icon}`"
                            :alt="palStore.getTranslatedText(`PlayerAttribute_${bonus.key}`)"
                        >
                        <label>
                            <strong>{{ palStore.getTranslatedText(`PlayerAttribute_${bonus.key}`) }}</strong>
                            <span>
                                {{ palStore.getTranslatedText('PlayerConsumableBonuses_Total', [
                                    Number(bonus.regular_rank) + Number(bonus.value),
                                    bonus.maximum_total,
                                ]) }}
                            </span>
                            <input
                                v-model.number="bonus.value"
                                type="number"
                                min="0"
                                :max="bonus.maximum"
                                step="1"
                                :disabled="palStore.LOADING_FLAG"
                                @keydown.enter="palStore.updatePlayerConsumableBonuses(bonus)"
                            >
                        </label>
                        <button
                            type="button"
                            class="player-attribute-save-action"
                            :disabled="palStore.LOADING_FLAG"
                            :title="palStore.getTranslatedText('Common_Save')"
                            @click="palStore.updatePlayerConsumableBonuses(bonus)"
                        ><AppIcon name="check" :size="15" /></button>
                    </article>
                </div>
            </section>
        </section>
        
    </div>
</template>

<style scoped>
div.no-margin {
    margin: 0;
}
div.no-padding {
    padding: 0;
}
.PalEditor {
    display: flex;
    height: var(--sub-height);
    overflow-y: auto;
    flex-wrap: wrap;
    align-items: flex-start;
    align-content: flex-start;
    gap: .5rem;
}

.EditorItem {
    display: flex;
    flex-shrink: 0;
    background: #484848;
    padding: 1.5rem;
    border-radius: 1rem;
}

.EditorItem.maxW {
    padding: 1rem;
    max-width: var(--editor-panel-width);
}

.inventory-panel {
    width: min(100%, var(--editor-panel-width));
    box-sizing: border-box;
}

.inventory-header {
    width: 100%;
    justify-content: space-between;
    color: #cfd2dc;
}

.inventory-header .cat {
    margin-bottom: .4rem;
}

.inventory-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(310px, 1fr));
    gap: .55rem;
    width: 100%;
    max-height: 34rem;
    overflow-y: auto;
}

.inventory-item {
    display: grid;
    grid-template-columns: 52px minmax(0, 1fr) auto;
    align-items: center;
    gap: .65rem;
    min-width: 0;
    padding: .65rem;
    border: 1px solid #5b5b60;
    border-radius: .75rem;
    background: #333336;
}

.inventory-copy {
    min-width: 0;
    align-items: flex-start;
    flex-direction: column;
}

.inventory-copy strong,
.inventory-copy small,
.inventory-copy p {
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.inventory-copy small {
    color: #9699a3;
}

.inventory-copy p {
    margin: .25rem 0 0;
    color: #c4c6cd;
    font-size: .78rem;
}

.inventory-count {
    gap: .35rem;
}

.inventory-count input {
    width: 6.8rem;
    height: 2rem;
    box-sizing: border-box;
    border: 1px solid #6c6d73;
    border-radius: .45rem;
    background: #242426;
    color: #fff;
    padding: 0 .45rem;
}

.inventory-count button {
    display: grid;
    place-items: center;
    width: 2rem;
    height: 2rem;
    border: 0;
    border-radius: .45rem;
    background: #2c77c2;
    color: #fff;
}

.inventory-count button:disabled {
    background: #696a70;
    cursor: not-allowed;
}

.inventory-empty {
    color: #a9abb2;
}

div.editField {
    /* border-style: dashed;
    border-width: 1px;
    border-color: white; */
    /* width: 100%; */
    /* flex-wrap: nowrap; */
    gap: 5px
}

div.basicInfo {
    position: relative;
    max-width: calc(var(--editor-panel-width) - 380px);
    /* min-width: calc(max(100%,var(--editor-panel-width))); */
}

hr {
    border: 0;
    width: 100%;
    height: 2px;
    background-color: #8a8a8a;
    margin: 20px 0;
}

button {
    cursor: pointer;
}

p.cat {
    margin-top: -.8rem;
    margin-left: -.5rem;
}

div {
    display: flex;
    align-items: center;
}

div.flex-v {
    flex-direction: column;
    gap: .2rem;
}

div.flex-h {
    flex-direction: row;
    gap: .5rem
}

div.left {
    justify-content: flex-start;
    align-items: flex-start;
}

p.const {
    display: flex;
    align-items: center;
    background-color: #272727;
    height: 1.8rem;
    margin: .2rem;
    padding: .2rem .4rem;
    border-radius: .5rem;
    color: rgb(208, 212, 226);
    box-shadow: 2px 2px 10px rgb(38, 38, 38);
}

button.edit {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 2rem;
    height: 2rem;
    padding: 0rem;
    margin: 0rem;
    background-color: #848484;
    color: whitesmoke;
    border: none;
    outline: none;
    border-radius: 0.5rem;
    transition: all 0.15s ease-in-out;
}

button.edit:hover {
    background-color: #9c9c9c;
    box-shadow: 2px 2px 10px rgb(38, 38, 38);
    transition: all 0.15s ease-in-out;
}

button.edit:disabled {
    background-color: #8b8b8b;
    box-shadow: 0 0 0;
    filter: grayscale(100%);
    cursor: not-allowed;
}

button.text {
    width: 100%;
    background-color: #2c77c2;
    padding: 1rem .5rem;
    margin: .2rem;
}

button.text:hover {
    background-color: #18518a;
}

button.text:disabled {
    background-color: #8a8a8a;
    box-shadow: 0 0 0;
    filter: grayscale(100%);
    cursor: not-allowed;
}

button.edit_text {
    width: 5rem;
    background-color: #2c77c2;
    padding: 1rem .5rem;
    margin: .2rem;
}

button.edit_text:hover {
    background-color: #18518a;
}

button.edit_text:disabled {
    background-color: #8a8a8a;
    box-shadow: 0 0 0;
    filter: grayscale(100%);
    cursor: not-allowed;
}

button.del {
    background-color: #ffcece;
}

button.del:hover {
    background-color: #7c0f0f;
}

button.del:disabled {
    background-color: #8a8a8a;
    box-shadow: 0 0 0;
    filter: grayscale(100%);
    cursor: not-allowed;
}

input.edit {
    height: 2rem;
    background-color: #6a6a6c;
    color: whitesmoke;
    border: none;
    outline: none;
    border-radius: 0.5rem;
    font-size: 1.2rem;
    padding-left: 0.7rem;
    padding-right: 0.7rem;
}

input.edit:focus {
    background-color: #b8b8b8;
    color: black;
    /* border: 2px solid #6a6a6c; */
    box-shadow: 2px 2px 10px rgb(38, 38, 38);
}

input.edit::placeholder {
    color: #cccccca2
}

div.spaceBetween {
    display: flex;
    width: 100%;
    justify-content: space-between
}

.tooltip-container {
    position: relative;
    display: inline-block;
}

.tooltip-text {
    visibility: hidden;
    width: 200px;
    background-color: rgba(0, 0, 0, 0.85);
    color: white;
    text-align: center;
    border-radius: 6px;
    padding: 1rem;

    /* Position the tooltip */
    position: absolute;
    z-index: 1;
    bottom: 100%;
    left: 50%;
    margin-left: -60px;
    margin-bottom: .25rem;
}

.tooltip-container:hover .tooltip-text {
    visibility: visible;
}

select.selector {
    display: flex;
    align-items: center;
    background-color: #272727;
    height: 1.8rem;
    margin: .2rem;
    padding: .2rem .4rem;
    border-radius: .5rem;
    color: rgb(208, 212, 226);
    box-shadow: 2px 2px 10px rgb(38, 38, 38);
    /* max-width: 50%; */
}

.levels-container {
    display: flex;
    flex-direction: column;
    max-height: 80vh;
    overflow-y: auto;
    max-width: 100%;
    padding: 8px;
    align-items: flex-start;
}

.level-row {
    display: flex;
    align-items: center;
    max-width: 100%;
}

.level-indicator {
    flex: 0 0 auto;
    justify-content: center;
    min-width: 5rem;
    font-weight: bold;
    margin-right: .5rem;
    color: #fff;
    background-color: #333;
    padding: .5rem;
    border-radius: 8px;
}

.cards-row {
    flex: 1 1 auto;
    display: flex;
    max-width: 900px;
    overflow-x: auto;
}

:global(#EditorMain .PalEditor.player-editor-layout) {
    display: flex;
    width: 100%;
    min-width: 0;
    height: var(--sub-height);
    align-items: stretch;
    align-content: initial;
    flex-direction: column;
    flex-wrap: nowrap;
    gap: 12px;
    padding: 0 4px 24px 0;
    overflow-y: auto;
}

:global(#EditorMain .player-editor-layout > *) {
    width: 100%;
    flex: 0 0 auto;
}

:global(#EditorMain .player-editor-layout > .inventory-editor) {
    flex: 1 0 710px;
    min-height: 710px;
}

.player-editor-tabs {
    display: flex;
    width: 100%;
    gap: 6px;
    padding: 5px;
    box-sizing: border-box;
    border: 1px solid var(--ui-border);
    border-radius: var(--ui-radius-md);
    background: var(--ui-surface);
}

.player-editor-tabs button {
    min-height: 38px;
    padding: 0 16px;
    border: 1px solid transparent;
    border-radius: var(--ui-radius-sm);
    color: var(--ui-text-secondary);
    background: transparent;
    font-size: 12px;
    font-weight: 650;
}

.player-editor-tabs button:hover {
    color: var(--ui-text);
    background: var(--ui-surface-raised);
}

.player-editor-tabs button.active {
    border-color: var(--ui-accent);
    color: var(--ui-text);
    background: var(--ui-accent-soft);
}

.player-editor-tabs button:focus-visible {
    outline: 2px solid var(--ui-accent);
    outline-offset: 1px;
}

:global(#EditorMain .PalEditor.player-editor-layout .EditorItem.player-map-progress-panel) {
    display: flex;
    flex: 0 0 auto;
    width: 100%;
    min-height: 0;
    align-self: flex-start;
    align-items: stretch;
    align-content: flex-start;
    flex-wrap: wrap;
    gap: 12px;
    padding: 16px 18px 18px;
    box-sizing: border-box;
}

.player-map-action {
    display: flex;
    flex: 0 1 320px;
    min-width: 0;
    max-width: 360px;
    flex-direction: column;
    align-items: stretch;
    gap: 14px;
    padding: 14px;
    border: 1px solid var(--ui-border);
    border-radius: 10px;
    background: var(--ui-surface-raised);
}

.player-map-action__heading {
    display: flex;
    min-width: 0;
    align-items: baseline;
    justify-content: space-between;
    gap: 10px;
    flex-wrap: wrap;
}

.player-map-action__heading strong {
    color: var(--ui-text);
    font-size: 14px;
}

.player-map-action__source {
    display: inline-flex;
    align-items: baseline;
    padding: 2px 6px;
    border-radius: 6px;
    color: var(--ui-text);
    background: var(--ui-surface);
    font-size: 11px;
    line-height: 1.4;
}

.player-map-action__source code {
    font-size: inherit;
    font-weight: 700;
}

.player-map-action__progress {
    color: var(--ui-text-muted);
    font-size: 11px;
    line-height: 1.4;
}

.player-map-action__reason {
    width: 100%;
    margin: 0;
    color: #efb36b;
    font-size: 12px;
    line-height: 1.5;
}

.player-map-action__actions {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
    margin-top: auto;
}

.player-map-action__actions--single {
    grid-template-columns: minmax(0, 1fr);
}

.player-map-action__button {
    min-height: 38px;
    padding: 8px 12px;
    border: 1px solid var(--ui-accent);
    border-radius: 8px;
    color: var(--ui-text);
    background: var(--ui-accent-soft);
    font-weight: 700;
}

.player-map-action__button--danger {
    border-color: rgba(250, 168, 125, 0.72);
    background: rgba(178, 70, 47, 0.28);
}

.player-map-action__button--wide {
    grid-column: 1 / -1;
}

.player-map-action__button--secondary {
    border-color: var(--ui-border-strong);
    background: var(--ui-surface);
}

.player-map-action__capacity-control {
    display: grid;
    grid-template-columns: 92px minmax(0, 1fr);
    gap: 8px;
    margin-top: auto;
}

.player-map-action__capacity-control input {
    min-width: 0;
    min-height: 38px;
    padding: 0 10px;
    border: 1px solid var(--ui-border-strong);
    border-radius: 8px;
    color: var(--ui-text);
    background: var(--ui-surface);
}

.player-map-action__notice {
    margin: 0;
    padding: 7px 9px;
    border: 1px solid rgba(239, 179, 107, 0.28);
    border-radius: 7px;
    color: #efb36b;
    background: rgba(239, 179, 107, 0.07);
    font-size: 10px;
    line-height: 1.45;
}

.player-map-action__button:hover:not(:disabled) {
    filter: brightness(1.14);
}

.player-map-action__button:disabled {
    cursor: not-allowed;
    opacity: 0.48;
}

@media (max-width: 820px) {
    .player-map-action {
        flex-basis: 100%;
        max-width: none;
    }
}

:global(#EditorMain .PalEditor.player-editor-layout .EditorItem.basicInfo.player-summary-card) {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    grid-auto-rows: max-content;
    align-items: center;
    align-content: start;
    gap: 12px 16px;
    width: 100%;
    max-width: none;
    padding: 16px 18px 18px;
    flex: 0 0 auto;
}

.player-summary-heading {
    display: flex;
    grid-column: 1 / -1;
    width: 100%;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    padding-bottom: 12px;
    border-bottom: 1px solid var(--ui-border);
}

.player-summary-heading h2 { margin: 0; color: var(--ui-text); font-size: 16px; font-weight: 680; }
.player-summary-identity { display: flex; align-items: baseline; gap: 8px; }
.player-summary-identity strong { color: var(--ui-text); font-size: 14px; font-weight: 650; }
.player-summary-identity span { color: var(--ui-text-muted); font-size: 11px; }

:global(#EditorMain .PalEditor.player-editor-layout .EditorItem.player-attributes-card) {
    display: block;
    width: 100%;
    padding: 16px 18px 18px;
}

.player-attributes-heading {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    margin-bottom: 12px;
}

.player-attributes-actions { display: flex; align-items: center; gap: 8px; }

.player-attributes-actions button {
    display: inline-flex;
    min-height: 36px;
    align-items: center;
    justify-content: center;
    gap: 6px;
    padding: 0 12px;
    border: 1px solid var(--ui-border);
    border-radius: var(--ui-radius-sm);
    color: var(--ui-text);
    font-size: 12px;
    font-weight: 650;
}

.attribute-secondary-action { background: var(--ui-surface-raised); }
.attribute-primary-action { border-color: var(--ui-accent) !important; background: var(--ui-accent); }
.player-attributes-actions button:disabled { opacity: .55; cursor: not-allowed; }

.player-attributes-grid {
    display: grid;
    width: 100%;
    grid-template-columns: repeat(auto-fill, minmax(min(330px, 100%), 1fr));
    gap: 8px;
}

.player-consumable-bonuses {
    display: grid;
    gap: 12px;
    margin-top: 20px;
    padding-top: 18px;
    border-top: 1px solid var(--ui-border);
}

.player-consumable-bonuses__heading {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 16px;
}

.player-consumable-bonuses__heading h3 {
    margin: 0;
    color: var(--ui-text);
    font-size: 13px;
}

.player-consumable-bonuses__heading p,
.player-consumable-bonuses__unavailable {
    margin: 5px 0 0;
    color: var(--ui-text-muted);
    font-size: 11px;
    line-height: 1.5;
}

.player-consumable-bonuses__unavailable {
    padding: 12px;
    background: var(--ui-surface);
    border: 1px solid var(--ui-border);
    border-radius: var(--ui-radius-sm);
}

.player-consumable-bonuses__grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
    gap: 8px;
}

.player-consumable-bonus {
    display: grid;
    grid-template-columns: 34px minmax(0, 1fr) 32px;
    align-items: center;
    gap: 9px;
    padding: 10px;
    background: var(--ui-surface);
    border: 1px solid var(--ui-border);
    border-radius: var(--ui-radius-sm);
}

.player-consumable-bonus > img {
    width: 34px;
    height: 34px;
    object-fit: contain;
}

.player-consumable-bonus label {
    display: grid;
    min-width: 0;
    grid-template-columns: 1fr 64px;
    align-items: center;
    gap: 3px 8px;
}

.player-consumable-bonus strong {
    overflow: hidden;
    color: var(--ui-text);
    font-size: 11px;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.player-consumable-bonus label > span {
    grid-column: 1;
    color: var(--ui-text-muted);
    font-size: 9px;
}

.player-consumable-bonus input {
    box-sizing: border-box;
    width: 64px;
    grid-column: 2;
    grid-row: 1 / span 2;
    padding: 6px 7px;
    color: var(--ui-text);
    background: var(--ui-bg);
    border: 1px solid var(--ui-border-strong);
    border-radius: var(--ui-radius-sm);
    font: inherit;
    font-size: 11px;
}

.player-attribute-item {
    display: flex;
    height: 96px;
    min-width: 0;
    box-sizing: border-box;
    align-items: stretch;
    align-content: space-between;
    flex-wrap: wrap;
    gap: 8px;
    padding: 10px;
    border: 1px solid var(--ui-border);
    border-radius: var(--ui-radius-sm);
    background: var(--ui-surface-raised);
}

.player-attribute-main {
    display: flex;
    min-width: 0;
    flex: 1 0 100%;
    align-items: center;
    gap: 10px;
}

.player-attribute-item img { width: 30px; height: 30px; object-fit: contain; }
.player-attribute-copy { display: flex; min-width: 0; align-items: flex-start; flex-direction: column; gap: 2px; }
.player-attribute-copy strong { max-width: 100%; overflow: hidden; color: var(--ui-text); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.player-attribute-copy span { color: var(--ui-text-muted); font-size: 10px; }

.player-attribute-controls {
    display: flex;
    min-width: 0;
    flex: 1 0 100%;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
}

.player-attribute-rank {
    display: flex;
    min-width: 112px;
    flex: 1 1 144px;
    align-items: center;
    gap: 6px;
    color: var(--ui-text-muted);
    font-size: 11px;
}

.player-attribute-input {
    width: auto;
    min-width: 84px;
    min-height: 32px;
    flex: 1 1 120px;
    box-sizing: border-box;
    padding: 0 9px;
    border: 1px solid var(--ui-border);
    border-radius: 6px;
    background: var(--ui-canvas);
    color: var(--ui-text);
    text-align: right;
}

.player-attribute-input:focus { border-color: var(--ui-accent); outline: 2px solid var(--ui-accent-soft); }
.player-attribute-input:disabled { opacity: .55; }

.player-attribute-actions { display: flex; flex: 0 0 auto; justify-content: flex-end; gap: 6px; }
.player-attribute-max-action,
.player-attribute-save-action {
    min-height: 32px;
    border: 0;
    border-radius: 6px;
    color: var(--ui-text);
    background: var(--ui-accent-soft);
}
.player-attribute-max-action { padding: 0 8px; color: var(--ui-accent); font-size: 10px; font-weight: 700; }
.player-attribute-save-action { display: grid; width: 32px; padding: 0; place-content: center; }
.player-attribute-max-action:hover:not(:disabled),
.player-attribute-save-action:hover:not(:disabled) { color: var(--ui-accent-strong); background: var(--ui-surface); }
.player-attribute-max-action:focus-visible,
.player-attribute-save-action:focus-visible { outline: 2px solid var(--ui-accent); outline-offset: 1px; }
.player-attribute-max-action:disabled,
.player-attribute-save-action:disabled { opacity: .55; cursor: not-allowed; }

.sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
}

.player-basic-grid {
    display: grid;
    min-width: 0;
    grid-template-columns: minmax(260px, 1.35fr) repeat(3, minmax(190px, 1fr));
    gap: 10px;
}

:global(#EditorMain .player-basic-grid .editField) {
    display: grid;
    min-width: 0;
    grid-template-columns: minmax(88px, auto) minmax(0, 1fr) auto;
    align-items: center;
    gap: 6px;
}

:global(#EditorMain .player-basic-grid .editField:last-child) {
    grid-template-columns: minmax(112px, 1fr) repeat(3, auto);
}

:global(#EditorMain .player-basic-grid p.const) {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

:global(#EditorMain .player-basic-grid input.edit) { width: 100%; min-width: 0; }
.player-summary-actions { display: flex; align-items: center; justify-content: flex-end; }
:global(#EditorMain .player-summary-actions button.edit.text) { width: auto; min-height: 36px; margin: 0; padding-inline: 12px; }

:global(#EditorMain .player-editor-layout .technology-panel) {
    display: block;
    width: 100%;
    padding: 18px;
}

.technology-actions {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 12px;
    margin-bottom: 12px;
}

:global(#EditorMain .technology-actions button.edit.text) { width: auto; margin: 0; padding-inline: 12px; }

:global(#EditorMain .player-editor-layout .technology-panel > .EditorItem) {
    width: 100%;
    max-width: none;
    padding: 0;
    background: transparent;
    border: 0;
}

:global(#EditorMain .player-editor-layout .levels-container) { width: 100%; max-width: none; max-height: none; padding: 0; }
:global(#EditorMain .player-editor-layout .level-row) { width: 100%; }
:global(#EditorMain .player-editor-layout .cards-row) { max-width: none; }

@media (max-width: 1480px) {
    .player-basic-grid { grid-template-columns: repeat(2, minmax(260px, 1fr)); }
}

@media (max-width: 920px) {
    :global(#EditorMain .PalEditor.player-editor-layout .EditorItem.basicInfo.player-summary-card) { grid-template-columns: minmax(0, 1fr); }
    .player-basic-grid { grid-template-columns: minmax(0, 1fr); }
    .player-summary-actions { justify-content: flex-start; }
    .player-attributes-actions { width: 100%; }
    .player-attributes-actions button { flex: 1; }
}

@media (max-width: 700px) {
    :global(#EditorMain .player-editor-layout > .inventory-editor) {
        flex: 0 0 auto;
        min-height: 0;
    }
}
</style>
