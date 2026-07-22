<script setup>
import { usePalEditorStore } from '@/stores/paleditor'
import AppIcon from '@/components/modules/AppIcon.vue'
import ElementIcon from '@/components/modules/ElementIcon.vue'
import VariantBadge from '@/components/modules/VariantBadge.vue'
import PalSpeciesPicker from '@/components/modules/PalSpeciesPicker.vue'
import { PAL_LIST_SORT_MODES, sortPalList } from '@/components/modules/pal-list-sort'
import {
    createDefaultPassivePresets,
    loadPassivePresets,
} from '@/components/modules/passive-presets'
import { ref, computed, onMounted, nextTick, watch } from "vue";
import { useRoute } from 'vue-router';

const palStore = usePalEditorStore()
const route = useRoute()

const palListContainer = ref(null);
const addSpeciesPicker = ref(null)
const newSpecies = ref('SheepBall')
const palListSortMode = ref(PAL_LIST_SORT_MODES.CONTAINER)
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

watch(async () => palStore.SELECTED_PLAYER_ID, async () => {
    await nextTick();
    if (palStore.SHOW_PLAYER_EDIT_FLAG && !palStore.BASE_PAL_BTN_CLK_FLAG) {
        return
    }
    try {
        if (palStore.BASE_PAL_BTN_CLK_FLAG == false) {
            return
        }
        const button = palListContainer.value?.querySelector('button:not(:disabled)');
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

watch(async () => palStore.UPDATE_PAL_RESELECT_CTR, async () => {
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

watch(async () => palStore.SELECTED_PAL_ID, async () => {
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
    await nextTick();
    // TODO Note: this is just a temp fix for pal selection when pal list is refreshed by updatePlayer
    await nextTick();
    await nextTick();
    if (palStore.SHOW_PLAYER_EDIT_FLAG && !palStore.BASE_PAL_BTN_CLK_FLAG) {
        return
    }
    const button = palListContainer.value?.querySelector('button:not(:disabled)');
    if (button) {
        button.click();
    }
});

function get_filtered_pal_list() {
    const pals = Array.from(palStore.PAL_MAP.values()).filter(pal => !palStore.isFilteredPal(pal))
    return sortPalList(pals, palListSortMode.value)
}

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
                <p>{{ palStore.getTranslatedText("PalList_Text") }}</p>
                <span>{{ get_filtered_pal_list().length }}</span>
            </div>
            <div class="panel-actions">
                <button class="add_pal" v-if="!palStore.BASE_PAL_BTN_CLK_FLAG"
                    :title="palStore.getTranslatedText('PalList_AddPalForPlayer', [palStore.PLAYER_MAP.get(palStore.SELECTED_PLAYER_ID).NickName])"
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
            <div class="overflow-container" v-for="pal in get_filtered_pal_list()" :key="pal.InstanceId">
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

.overflow-list {
    display: flex;
    flex-direction: column;
    min-height: 0;
    overflow-y: auto;
    gap: 3px;
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
</style>
