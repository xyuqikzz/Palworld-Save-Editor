<script setup>
import { usePalEditorStore } from '@/stores/paleditor'
import AppIcon from '@/components/modules/AppIcon.vue'
import ElementIcon from '@/components/modules/ElementIcon.vue'
import VariantBadge from '@/components/modules/VariantBadge.vue'
import PalSpeciesPicker from '@/components/modules/PalSpeciesPicker.vue'
import { ref, computed, onMounted, nextTick, watch } from "vue";

const palStore = usePalEditorStore()

const palListContainer = ref(null);
const addSpeciesPicker = ref(null)
const newSpecies = ref('SheepBall')

const constructibleSpecies = computed(() =>
    palStore.PAL_STATIC_DATA_LIST.filter(item => !item.Invalid)
)

function openAddPal() {
    addSpeciesPicker.value?.open()
}

async function addSelectedPal(speciesId) {
    await palStore.addPal(speciesId, 'AUTO')
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
    return Array.from(palStore.PAL_MAP.values()).filter(pal => !palStore.isFilteredPal(pal))
}

function displayNameWithoutVariantEmoji(displayName) {
    return displayName?.replace(/^[👑✨🗼]+/u, '') || ''
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
                <button class="heal-all unlock-expedition"
                    :title="palStore.getTranslatedText(
                        palStore.EXPEDITION_PAL_COUNT === 0
                            ? 'TopBar_Btn_UnlockExpeditionPals_Disabled'
                            : 'TopBar_Btn_UnlockExpeditionPals_Tooltips'
                    )"
                    :disabled="palStore.LOADING_FLAG || palStore.EXPEDITION_PAL_COUNT === 0"
                    @click="palStore.unlockExpeditionPals">
                    <span>{{ palStore.getTranslatedText(
                        palStore.EXPEDITION_PAL_COUNT === 0
                            ? 'TopBar_Btn_UnlockExpeditionPals_Disabled'
                            : 'TopBar_Btn_UnlockExpeditionPals'
                    ) }}</span>
                </button>
                <button class="heal-all" :title="palStore.getTranslatedText('TopBar_Btn_HealAllPals_Tooltips')"
                    :disabled="palStore.LOADING_FLAG || palStore.PAL_MAP.size === 0" @click="palStore.healAllPals">
                    <span>{{ palStore.getTranslatedText('TopBar_Btn_HealAllPals') }}</span>
                </button>
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
                    <span v-if="pal.IsBOSS || pal.IsRarePal" class="pal-variants">
                        <span v-if="pal.IsBOSS" class="pal-variant-label">{{ palStore.getTranslatedText('Variant_Boss') }}</span>
                        <span v-if="pal.IsRarePal" class="pal-variant-label">{{ palStore.getTranslatedText('Variant_Rare') }}</span>
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
        />
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
.heal-all {
    display: inline-flex;
    min-height: 30px;
    align-items: center;
    gap: 5px;
    padding: 0 8px;
    border: 1px solid var(--ui-border);
    border-radius: var(--ui-radius-sm);
    color: var(--ui-accent);
    background: var(--ui-accent-soft);
    font-size: 10px;
    font-weight: 650;
    white-space: nowrap;
}
.heal-all:hover:not(:disabled) { border-color: var(--ui-accent); }
.heal-all:disabled {
    border-color: var(--ui-border);
    color: var(--ui-text-muted);
    background: var(--ui-surface);
    opacity: 0.52;
    cursor: not-allowed;
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
    padding: 8px 0 9px;
    border-bottom: 1px solid var(--ui-border);
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
</style>
