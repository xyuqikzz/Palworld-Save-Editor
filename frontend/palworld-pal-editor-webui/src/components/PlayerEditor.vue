<script setup>
import { ref } from 'vue'
import { usePalEditorStore } from '@/stores/paleditor'
import ItemCard from '@/components/modules/TechCard.vue'
import AppIcon from '@/components/modules/AppIcon.vue'
import InventoryEditor from '@/components/InventoryEditor.vue'
import MissionEditor from '@/components/MissionEditor.vue'

const palStore = usePalEditorStore()
const activeEditorTab = ref('inventory')

const isMaxLv = () => {
    return palStore.SELECTED_PLAYER_DATA.Level >= (palStore.HIDE_INVALID_OPTIONS ? palStore.MAX_LEVEL : palStore.MAX_INVALID_LEVEL);
};

const isMinLv = () => {
    return palStore.SELECTED_PLAYER_DATA.Level <= 1;
};
</script>

<template>
    <div class="PalEditor player-editor-layout">
        <section class="EditorItem item flex-v basicInfo player-summary-card">
            <header class="player-summary-heading">
                <h2>{{ palStore.getTranslatedText("Editor_Basic_Info") }}</h2>
                <div class="player-summary-identity">
                    <strong>{{ palStore.SELECTED_PLAYER_DATA.NickName }}</strong>
                    <span>{{ palStore.getTranslatedText('Common_LevelWithValue', [palStore.SELECTED_PLAYER_DATA.Level]) }}</span>
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
}
</style>
