<script setup>
import { usePalEditorStore } from '@/stores/paleditor'
import AppIcon from '@/components/modules/AppIcon.vue'
import ElementIcon from '@/components/modules/ElementIcon.vue'
import VariantBadge from '@/components/modules/VariantBadge.vue'
import PalSpeciesPicker from '@/components/modules/PalSpeciesPicker.vue'
import {
    groupPalList,
    PAL_LIST_SORT_MODES,
    sortPalList,
} from '@/components/modules/pal-list-sort'
import {
    createDefaultPassivePresets,
    loadPassivePresets,
} from '@/components/modules/passive-presets'
import { ref, computed, onMounted, nextTick, watch } from "vue";
import { useRoute } from 'vue-router';

const palStore = usePalEditorStore()
const route = useRoute()
const props = defineProps({
    globalPalbox: { type: Boolean, default: false },
})

const palListContainer = ref(null);
const addSpeciesPicker = ref(null)
const newSpecies = ref('SheepBall')
const palListSortMode = ref(PAL_LIST_SORT_MODES.CONTAINER)
const expandedPalGroups = ref(new Set(['party']))
const addPalPassivePresets = ref([])
const selectedPassivePresetId = ref('')
const addMaxPal = ref(false)
const addMaxWork = ref(false)

const constructibleSpecies = computed(() =>
    palStore.PAL_STATIC_DATA_LIST.filter(item => !item.Invalid)
)

function loadAddPalPassivePresets() {
    const defaults = createDefaultPassivePresets(
        key => palStore.getTranslatedText(key),
        palStore.PASSIVE_SKILLS_LIST.map(skill => skill.InternalName),
    )
    addPalPassivePresets.value = loadPassivePresets(globalThis.localStorage, defaults).presets
    if (!addPalPassivePresets.value.some(preset => preset.id === selectedPassivePresetId.value)) {
        selectedPassivePresetId.value = ''
    }
}

function openAddPal() {
    loadAddPalPassivePresets()
    addSpeciesPicker.value?.open()
}

async function addSelectedPal(speciesId) {
    const passivePreset = addPalPassivePresets.value.find(
        preset => preset.id === selectedPassivePresetId.value,
    )
    await palStore.addPal(speciesId, 'AUTO', {
        passive: passivePreset ? [...passivePreset.skills] : null,
        maxPal: addMaxPal.value,
        maxWork: addMaxWork.value,
    })
}

async function addGlobalPreset(speciesId) {
    await addSelectedPal(speciesId)
    addSpeciesPicker.value?.close()
}

const passivePresetIsAvailable = preset => (
    preset.skills.every(skill => palStore.PASSIVE_SKILLS[skill])
)

const passivePresetTooltip = preset => preset.skills
    .map(skill => palStore.PASSIVE_SKILLS[skill]?.I18n?.[0] || skill)
    .join(' · ')

function updateAddMaxPal(selected) {
    addMaxPal.value = selected
    if (selected) addMaxWork.value = false
}

function updateAddMaxWork(selected) {
    addMaxWork.value = selected
    if (selected) addMaxPal.value = false
}

function palGroupKey(pal) {
    if (pal?.ContainerType === 'PARTY') return 'party'
    if (pal?.ContainerType === 'PAL_STORAGE') return 'palbox'
    return 'other'
}

function setPalGroupExpanded(groupKey, expanded = true) {
    const next = new Set(expandedPalGroups.value)
    if (expanded) next.add(groupKey)
    else next.delete(groupKey)
    expandedPalGroups.value = next
}

function togglePalGroup(groupKey) {
    setPalGroupExpanded(groupKey, !expandedPalGroups.value.has(groupKey))
}

function isPalGroupExpanded(group) {
    if (props.globalPalbox) return true
    if (group.key === 'base') return true
    return expandedPalGroups.value.has(group.key)
}

function expandSelectedPalGroup(palId) {
    if (!palId || palStore.BASE_PAL_BTN_CLK_FLAG) return
    const pal = palStore.PAL_MAP.get(palId)
    if (pal) setPalGroupExpanded(palGroupKey(pal))
}

function expandFirstPopulatedGroup() {
    if (palStore.BASE_PAL_BTN_CLK_FLAG || palStore.PAL_LIST_SEARCH_KEYWORD) return
    if (visiblePalGroups.value.some(group => (
        group.pals.length && expandedPalGroups.value.has(group.key)
    ))) return
    const firstGroup = visiblePalGroups.value.find(group => group.pals.length)
    if (firstGroup) setPalGroupExpanded(firstGroup.key)
}

watch(() => palStore.SELECTED_PLAYER_ID, async () => {
    expandFirstPopulatedGroup()
    await nextTick();
    if (palStore.SHOW_PLAYER_EDIT_FLAG && !palStore.BASE_PAL_BTN_CLK_FLAG) {
        return
    }
    try {
        if (palStore.BASE_PAL_BTN_CLK_FLAG == false) {
            return
        }
        const button = palListContainer.value?.querySelector('button.pal:not(:disabled)');
        if (button) {
            button.click();
        }
    } catch (error) {
        return
    }
})

// watch(async () => palStore.ADD_PAL_RESELECT_CTR, async () => {
//     await nextTick();
//     try {
//         const button = palListContainer.value.querySelector('button:not(:disabled)');
//         if (button) {
//             button.click();
//         }
//     } catch (error) {
//         return
//     }
// })

watch(() => palStore.UPDATE_PAL_RESELECT_CTR, async () => {
    expandSelectedPalGroup(palStore.SELECTED_PAL_ID)
    await nextTick();
    try {
        const button = palListContainer.value?.querySelector(`button[value="${palStore.SELECTED_PAL_ID}"]`);
        if (button) {
            if (!palStore.isElementInViewport(button)) {
                button.scrollIntoView({ behavior: "smooth" });
            }
        }
    } catch (error) {
        return
    }
})

watch(() => palStore.SELECTED_PAL_ID, async palId => {
    expandSelectedPalGroup(palId)
    await nextTick();
    if (palStore.SHOW_PLAYER_EDIT_FLAG && !palStore.BASE_PAL_BTN_CLK_FLAG) {
        return
    }
    try {
        const button = palListContainer.value?.querySelector(`button[value="${palStore.SELECTED_PAL_ID}"]`);
        if (button) {
            if (palStore.SELECTED_PAL_ID != palStore.SELECTED_PAL_DATA?.InstanceId) {
                palStore.selectPal(palStore.SELECTED_PAL_ID, true)
            }
            if (!palStore.isElementInViewport(button)) {
                button.scrollIntoView({ behavior: "smooth" });
            }
        }
    } catch (error) {
        return
    }
})

onMounted(async () => {
    if (route.name === 'PlayerPalEditor' || route.name === 'BasePalEditor') return;
    expandFirstPopulatedGroup()
    await nextTick();
    // TODO Note: this is just a temp fix for pal selection when pal list is refreshed by updatePlayer
    await nextTick();
    await nextTick();
    if (palStore.SHOW_PLAYER_EDIT_FLAG && !palStore.BASE_PAL_BTN_CLK_FLAG) {
        return
    }
    const button = palListContainer.value?.querySelector('button.pal:not(:disabled)');
    if (button) {
        button.click();
    }
});

const filteredPalList = computed(() => (
    Array.from(palStore.PAL_MAP.values()).filter(pal => !palStore.isFilteredPal(pal))
))

const visiblePalGroups = computed(() => {
    if (props.globalPalbox) {
        return [{
            key: 'global',
            label: palStore.getTranslatedText('GlobalPalbox_Entry'),
            pals: sortPalList(filteredPalList.value, palListSortMode.value),
        }]
    }
    if (palStore.BASE_PAL_BTN_CLK_FLAG) {
        return [{
            key: 'base',
            label: '',
            pals: sortPalList(filteredPalList.value, palListSortMode.value),
        }]
    }

    const groups = groupPalList(filteredPalList.value, palListSortMode.value)
    const visibleGroups = [
        {
            key: 'party',
            label: palStore.getTranslatedText('PalList_Group_Party'),
            pals: groups.party,
        },
        {
            key: 'palbox',
            label: palStore.getTranslatedText('PalList_Group_Palbox'),
            pals: groups.palbox,
        },
    ]
    if (groups.other.length) {
        visibleGroups.push({
            key: 'other',
            label: palStore.getTranslatedText('PalList_Group_Other'),
            pals: groups.other,
        })
    }
    return visibleGroups
})

watch(() => palStore.PAL_LIST_SEARCH_KEYWORD, keyword => {
    if (!keyword) return
    const next = new Set(expandedPalGroups.value)
    next.add('party')
    next.add('palbox')
    next.add('other')
    expandedPalGroups.value = next
})

function displayNameWithoutVariantEmoji(displayName) {
    return displayName?.replace(/^[👑✨🗼]+/u, '') || ''
}

function expeditionStatusKey(pal) {
    return {
        valid: 'Expedition_Status_Valid',
        invalid: 'Expedition_Status_Invalid',
        unknown: 'Expedition_Status_Unknown',
    }[pal.ExpeditionAssignmentStatus] || 'Expedition_Status_Unknown'
}

function expeditionStatusTooltipKey(pal) {
    return `${expeditionStatusKey(pal)}_Tooltip`
}

</script>

<template>
    <aside class="flex list-panel pal-panel">
        <div class="title panel-title">
            <div>
                <p>{{ palStore.getTranslatedText(props.globalPalbox ? "GlobalPalbox_Entry" : "PalList_Text") }}</p>
                <span>{{ filteredPalList.length }}</span>
            </div>
            <div class="panel-actions">
                <button class="add_pal" v-if="!palStore.BASE_PAL_BTN_CLK_FLAG"
                    :title="props.globalPalbox
                        ? palStore.getTranslatedText('GlobalPalbox_AddTitle')
                        : palStore.getTranslatedText('PalList_AddPalForPlayer', [palStore.PLAYER_MAP.get(palStore.SELECTED_PLAYER_ID).NickName])"
                    :disabled="palStore.LOADING_FLAG" @click="openAddPal" name="add_pal"><AppIcon name="plus" :size="16" /></button>
            </div>
        </div>
        <label class="filter-field">
            <span class="sr-only">{{ palStore.getTranslatedText('PalList_Search') }}</span>
            <input class="palFilter" type="search" v-model="palStore.PAL_LIST_SEARCH_KEYWORD" :placeholder="palStore.getTranslatedText('PalList_Search')"
                :disabled="palStore.LOADING_FLAG">
        </label>
        <div class="pal-sort-control" role="group" :aria-label="palStore.getTranslatedText('PalList_SortAriaLabel')">
            <button type="button" :class="{ active: palListSortMode === PAL_LIST_SORT_MODES.CONTAINER }"
                :aria-pressed="palListSortMode === PAL_LIST_SORT_MODES.CONTAINER"
                :disabled="palStore.LOADING_FLAG" @click="palListSortMode = PAL_LIST_SORT_MODES.CONTAINER">
                {{ palStore.getTranslatedText('PalList_Sort_Container') }}
            </button>
            <button type="button" :class="{ active: palListSortMode === PAL_LIST_SORT_MODES.PALDECK }"
                :aria-pressed="palListSortMode === PAL_LIST_SORT_MODES.PALDECK"
                :disabled="palStore.LOADING_FLAG" @click="palListSortMode = PAL_LIST_SORT_MODES.PALDECK">
                {{ palStore.getTranslatedText('PalList_Sort_Paldeck') }}
            </button>
            <button type="button" :class="{ active: palListSortMode === PAL_LIST_SORT_MODES.LEVEL }"
                :aria-pressed="palListSortMode === PAL_LIST_SORT_MODES.LEVEL"
                :disabled="palStore.LOADING_FLAG" @click="palListSortMode = PAL_LIST_SORT_MODES.LEVEL">
                {{ palStore.getTranslatedText('PalList_Sort_Level') }}
            </button>
        </div>

        <div class="overflow-list" ref="palListContainer">
            <section v-for="group in visiblePalGroups" :key="group.key" class="pal-list-group">
                <header v-if="group.label" class="pal-list-group__header">
                    <button type="button" class="pal-list-group__toggle"
                        :aria-expanded="isPalGroupExpanded(group)"
                        :aria-controls="`pal-list-group-${group.key}`"
                        @click="togglePalGroup(group.key)">
                        <AppIcon
                            :class="['pal-list-group__chevron', { expanded: isPalGroupExpanded(group) }]"
                            name="chevron-down"
                            :size="15"
                        />
                        <span class="pal-list-group__name">{{ group.label }}</span>
                        <span class="pal-list-group__count">{{ group.pals.length }}</span>
                    </button>
                </header>
                <div v-if="isPalGroupExpanded(group)" :id="`pal-list-group-${group.key}`"
                    class="pal-list-group__content">
                    <p v-if="!group.pals.length" class="pal-list-group__empty">
                        {{ palStore.getTranslatedText('PalList_Group_Empty') }}
                    </p>
                    <div class="overflow-container" v-for="pal in group.pals" :key="pal.InstanceId">
                        <button
                            :class="['pal', { 'male': pal.displayGender() == '♂️', 'female': pal.displayGender() == '♀️', 'unref': pal.Is_Unref_Pal, 'out_of_container': !pal.in_owner_palbox }]"
                            :value="pal.InstanceId" @click="palStore.selectPal(pal.InstanceId)"
                            :disabled="palStore.SELECTED_PAL_ID == pal.InstanceId || palStore.LOADING_FLAG"
                            :selected="palStore.SELECTED_PAL_ID == pal.InstanceId"
                            :aria-current="palStore.SELECTED_PAL_ID == pal.InstanceId ? 'true' : undefined"
                            >
                            <img :class="['palIcon']" :src="`/image/pals/${pal.IconAccessKey}`" alt="">
                            <span class="pal-label">
                                <VariantBadge v-if="pal.IsTower" kind="tower" :size="14" />
                                <ElementIcon v-for="element in palStore.PAL_STATIC_DATA[pal.DataAccessKey]?.Elements || []"
                                    :key="element" :element="element" :size="14" />
                                <span class="pal-name">{{ displayNameWithoutVariantEmoji(pal.DisplayName) }}</span>
                            </span>
                            <span v-if="pal.IsAwakened" class="pal-awakened-label">
                                {{ palStore.getTranslatedText('PalList_AwakenedMarker') }}
                            </span>
                            <span v-if="pal.IsBOSS || pal.IsRarePal || pal.IsExpeditionPal" class="pal-variants">
                                <span v-if="pal.IsBOSS" class="pal-variant-label is-boss">{{ palStore.getTranslatedText('Variant_Boss') }}</span>
                                <span v-if="pal.IsRarePal" class="pal-variant-label">{{ palStore.getTranslatedText('Variant_Rare') }}</span>
                                <span v-if="pal.IsExpeditionPal"
                                    :class="['pal-expedition-label', `is-${pal.ExpeditionAssignmentStatus || 'unknown'}`]"
                                    :title="palStore.getTranslatedText(expeditionStatusTooltipKey(pal), [pal.ExpeditionInstanceId || '-'])">
                                    {{ palStore.getTranslatedText(expeditionStatusKey(pal)) }}
                                </span>
                            </span>
                        </button>
                    </div>
                </div>
            </section>
        </div>
        <PalSpeciesPicker
            ref="addSpeciesPicker"
            v-model="newSpecies"
            :options="constructibleSpecies"
            :selected-option="palStore.PAL_STATIC_DATA[newSpecies]"
            :disabled="palStore.LOADING_FLAG"
            :title="palStore.getTranslatedText('PalList_ChooseConstructiblePal')"
            :search-placeholder="palStore.getTranslatedText('Editor_Species_Search_Placeholder')"
            :results-label="palStore.getTranslatedText('Editor_Species_Results_Label')"
            :empty-text="palStore.getTranslatedText('Editor_Species_Empty')"
            :close-label="palStore.getTranslatedText('Common_Close')"
            triggerless
            @select="addSelectedPal"
        >
            <template #footer>
                <section class="add-pal-presets" :aria-label="palStore.getTranslatedText('PalList_AddPresets_Title')">
                    <div v-if="props.globalPalbox" class="global-palbox-presets">
                        <span class="add-pal-preset-label">{{ palStore.getTranslatedText('GlobalPalbox_AddHint') }}</span>
                        <div class="add-pal-passive-options">
                            <button type="button" @click="addGlobalPreset('GrassBoss')">{{ palStore.getTranslatedText('GlobalPalbox_PresetZoe') }}</button>
                            <button type="button" @click="addGlobalPreset('GYM_ElecPanda')">{{ palStore.getTranslatedText('GlobalPalbox_PresetZoeGrizzbolt') }}</button>
                            <button type="button" @click="addGlobalPreset('GYM_ElecPanda_Otomo')">{{ palStore.getTranslatedText('GlobalPalbox_PresetGrizzbolt') }}</button>
                        </div>
                    </div>
                    <header>
                        <strong>{{ palStore.getTranslatedText('PalList_AddPresets_Title') }}</strong>
                        <span>{{ palStore.getTranslatedText('PalList_AddPresets_Description') }}</span>
                    </header>
                    <div class="add-pal-preset-row">
                        <span class="add-pal-preset-label">{{ palStore.getTranslatedText('PalList_AddPassivePreset') }}</span>
                        <div class="add-pal-passive-options" role="radiogroup" :aria-label="palStore.getTranslatedText('PalList_AddPassivePreset')">
                            <button type="button" :class="{ 'is-active': selectedPassivePresetId === '' }"
                                :aria-checked="selectedPassivePresetId === ''" role="radio"
                                @click="selectedPassivePresetId = ''">
                                {{ palStore.getTranslatedText('PalList_AddPassivePreset_None') }}
                            </button>
                            <button v-for="preset in addPalPassivePresets" :key="preset.id" type="button"
                                :class="{ 'is-active': selectedPassivePresetId === preset.id }"
                                :aria-checked="selectedPassivePresetId === preset.id" role="radio"
                                :disabled="!passivePresetIsAvailable(preset)"
                                :title="passivePresetIsAvailable(preset) ? passivePresetTooltip(preset) : palStore.getTranslatedText('PalEditor_PassivePreset_Unavailable')"
                                @click="selectedPassivePresetId = preset.id">
                                {{ preset.name }}
                            </button>
                            <span v-if="!addPalPassivePresets.length" class="add-pal-presets-empty">
                                {{ palStore.getTranslatedText('PalList_AddPassivePreset_Empty') }}
                            </span>
                        </div>
                    </div>
                    <div class="add-pal-max-options">
                        <label>
                            <input :checked="addMaxPal" type="checkbox"
                                @change="updateAddMaxPal($event.target.checked)">
                            <span>
                                <strong>{{ palStore.getTranslatedText('PalEditor_MaxPal') }}</strong>
                                <small>{{ palStore.getTranslatedText('PalEditor_MaxPal_Tooltip') }}</small>
                            </span>
                        </label>
                        <label>
                            <input :checked="addMaxWork" type="checkbox"
                                @change="updateAddMaxWork($event.target.checked)">
                            <span>
                                <strong>{{ palStore.getTranslatedText('PalList_AddMaxWork') }}</strong>
                                <small>{{ palStore.getTranslatedText('PalList_AddMaxWork_Tooltip') }}</small>
                            </span>
                        </label>
                    </div>
                </section>
            </template>
        </PalSpeciesPicker>
    </aside>
</template>

<style scoped>
.list-panel {
    display: flex;
    flex-direction: column;
    flex-shrink: 0;
    width: 100%;
    height: 100%;
    min-width: 0;
}

.panel-title,
.panel-title > div:first-child {
    display: flex;
    align-items: center;
    gap: 7px;
}

.panel-title { justify-content: space-between; }
.panel-title span { color: var(--ui-text-muted); font-size: 11px; font-weight: 500; }
.panel-actions { display: flex; align-items: center; gap: 5px; }
.add_pal { display: inline-flex; align-items: center; justify-content: center; }

.add-pal-presets { display: grid; gap: 10px; }
.global-palbox-presets { display: flex; min-width: 0; align-items: center; gap: 9px; }
.add-pal-presets > header { display: flex; align-items: baseline; gap: 9px; }
.add-pal-presets > header strong { color: var(--ui-text); font-size: 13px; font-weight: 700; }
.add-pal-presets > header span { color: var(--ui-text-muted); font-size: 11px; }
.add-pal-preset-row { display: flex; min-width: 0; align-items: center; gap: 9px; }
.add-pal-preset-label { flex: 0 0 auto; color: var(--ui-text-secondary); font-size: 11px; font-weight: 650; }
.add-pal-passive-options { display: flex; min-width: 0; flex: 1 1 auto; flex-wrap: wrap; gap: 6px; }
.add-pal-passive-options button {
    min-height: 29px;
    padding: 0 10px;
    color: var(--ui-text-secondary);
    background: var(--ui-surface);
    border: 1px solid var(--ui-border);
    border-radius: 999px;
    font-size: 11px;
    font-weight: 650;
}
.add-pal-passive-options button:hover:not(:disabled),
.add-pal-passive-options button.is-active { color: var(--ui-accent); border-color: var(--ui-accent); background: var(--ui-accent-soft); }
.add-pal-passive-options button:disabled { cursor: not-allowed; opacity: 0.45; }
.add-pal-presets-empty { align-self: center; color: var(--ui-text-muted); font-size: 11px; }
.add-pal-max-options { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
.add-pal-max-options label {
    display: flex;
    min-width: 0;
    min-height: 48px;
    align-items: center;
    gap: 9px;
    padding: 7px 10px;
    color: var(--ui-text-secondary);
    background: var(--ui-surface);
    border: 1px solid var(--ui-border);
    border-radius: var(--ui-radius-sm);
    cursor: pointer;
}
.add-pal-max-options label:has(input:checked) { color: var(--ui-text); background: var(--ui-accent-soft); border-color: var(--ui-accent); }
.add-pal-max-options input { width: 15px; height: 15px; flex: 0 0 auto; accent-color: var(--ui-accent); }
.add-pal-max-options span { display: grid; min-width: 0; gap: 2px; }
.add-pal-max-options strong { font-size: 12px; font-weight: 700; }
.add-pal-max-options small { overflow: hidden; color: var(--ui-text-muted); font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }

@media (max-width: 680px) {
    .add-pal-preset-row { align-items: flex-start; flex-direction: column; }
    .add-pal-max-options { grid-template-columns: minmax(0, 1fr); }
}

#EditorMain .pal-panel .overflow-list {
    display: flex;
    flex-direction: column;
    min-height: 0;
    overflow-y: auto;
    gap: 8px;
    padding: 8px 6px 10px;
    scrollbar-gutter: stable;
}

.pal-list-group {
    display: flex;
    flex-direction: column;
    flex-shrink: 0;
    min-width: 0;
    gap: 4px;
}

.pal-list-group__header {
    position: sticky;
    z-index: 1;
    top: 0;
    min-width: 0;
    background: var(--ui-surface-raised);
    border-radius: var(--ui-radius-sm);
}

.pal-list-group__toggle {
    display: flex;
    width: 100%;
    min-width: 0;
    min-height: 36px;
    align-items: center;
    gap: 8px;
    padding: 6px 8px;
    color: var(--ui-text-secondary);
    background: transparent;
    border: 0;
    border-radius: inherit;
    font-size: 11px;
    font-weight: 700;
    text-align: left;
}

.pal-list-group__toggle:hover {
    color: var(--ui-text);
    background: var(--ui-surface-hover);
}

.pal-list-group__chevron {
    flex: 0 0 auto;
    transform: rotate(-90deg);
    transition: transform 140ms ease-out;
}

.pal-list-group__chevron.expanded {
    transform: rotate(0deg);
}

.pal-list-group__name {
    min-width: 0;
    flex: 1 1 auto;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.pal-list-group__count {
    flex: 0 0 auto;
    color: var(--ui-text-muted);
    font-variant-numeric: tabular-nums;
    font-weight: 600;
}

.pal-list-group__content {
    display: flex;
    min-width: 0;
    flex-direction: column;
    gap: 3px;
    padding-top: 2px;
}

.pal-list-group__empty {
    margin: 0;
    padding: 12px 10px;
    color: var(--ui-text-muted);
    font-size: 11px;
    text-align: center;
}

.overflow-container {
    display: flex;
    flex-shrink: 0;
    width: 100%;
    min-width: 0;
}

.filter-field {
    display: block;
    padding: 8px 0 6px;
}

.pal-sort-control {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 4px;
    padding: 0 10px 9px;
    border-bottom: 1px solid var(--ui-border);
}

.pal-sort-control button {
    min-width: 0;
    min-height: 28px;
    padding: 0 8px;
    border: 1px solid var(--ui-border);
    border-radius: var(--ui-radius-sm);
    color: var(--ui-text-muted);
    background: var(--ui-surface-raised);
    font-size: 11px;
    font-weight: 650;
}

.pal-sort-control button:hover:not(:disabled) {
    border-color: var(--ui-accent);
    color: var(--ui-text);
}

.pal-sort-control button.active {
    border-color: var(--ui-accent);
    color: var(--ui-accent);
    background: var(--ui-accent-soft);
}

button.pal {
    display: flex;
    align-items: center;
    width: 100%;
    min-width: 0;
    text-align: left;
    white-space: nowrap;
}

button.pal .pal-name {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
}

button.pal .pal-label {
    display: flex;
    flex: 1 1 auto;
    align-items: center;
    min-width: 0;
    gap: 4px;
}

button.pal .pal-variants {
    display: flex;
    flex: 0 0 auto;
    align-items: center;
    gap: 7px;
    margin-left: auto;
    color: var(--ui-text-secondary);
    font-size: 10px;
    font-weight: 700;
}

button.pal .pal-awakened-label {
    flex: 0 0 auto;
    margin: 0 6px 0 5px;
    color: oklch(0.84 0.16 92);
    font-size: 10px;
    font-weight: 760;
}

button.pal .pal-variant-label.is-boss { color: var(--ui-danger); }
button.pal .pal-expedition-label.is-valid { color: var(--ui-success); }
button.pal .pal-expedition-label.is-invalid { color: var(--ui-danger); }
button.pal .pal-expedition-label.is-unknown { color: var(--ui-text-muted); }

@media (prefers-reduced-motion: reduce) {
    .pal-list-group__chevron { transition: none; }
}
</style>
