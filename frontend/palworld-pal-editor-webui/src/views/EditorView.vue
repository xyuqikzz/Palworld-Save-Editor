<script setup>
import PalList from '@/components/PalList.vue';
import PlayerList from '@/components/PlayerList.vue';
import PalEditor from '@/components/PalEditor.vue';
import PlayerEditor from '@/components/PlayerEditor.vue';
import { usePalEditorStore } from '@/stores/paleditor'
const palStore = usePalEditorStore()
</script>

<template>
    <div id="EditorDiv">
        <aside v-if="palStore.LAST_ERROR" class="error-banner" role="alert">
            <div>
                <strong>{{ palStore.LAST_ERROR.code }}</strong>
                <span>{{ palStore.LAST_ERROR.message }}</span>
            </div>
            <button @click="palStore.LAST_ERROR = null" :aria-label="palStore.getTranslatedText('Common_DismissError')">×</button>
        </aside>
        <div id="EditorMain">
            <aside class="selection-column">
                <PlayerList></PlayerList>
                <PalList v-if="palStore.SELECTED_PLAYER_ID || palStore.BASE_PAL_BTN_CLK_FLAG"></PalList>
            </aside>
            <PlayerEditor v-if="palStore.SHOW_PLAYER_EDIT_FLAG"></PlayerEditor>
            <PalEditor v-else-if="palStore.SELECTED_PAL_ID && palStore.SELECTED_PAL_DATA"></PalEditor>
            <section v-else class="editor-empty">
                <p>{{ palStore.getTranslatedText('Editor_Select_Target') }}</p>
            </section>
        </div>
    </div>
</template>
<style scoped>
div#EditorDiv {
    display: flow-root;
    min-height: 100dvh;
    width: 100%;
}

div#EditorMain {
    display: grid;
    grid-template-columns: minmax(280px, 320px) minmax(0, 1fr);
    align-items: stretch;
    gap: 14px;
    width: calc(100vw - 20px);
    margin-top: var(--editor-top-offset);
    margin-inline: 10px;
    padding-bottom: 16px;
}

.selection-column {
    display: grid;
    grid-template-rows: minmax(148px, 24vh) minmax(0, 1fr);
    gap: 12px;
    height: var(--sub-height);
    min-width: 0;
    min-height: 0;
}

.selection-column :deep(.list-panel) {
    height: 100%;
    min-height: 0;
}

.error-banner {
    position: fixed;
    z-index: 20;
    top: calc(var(--editor-top-offset) + 4px);
    right: 14px;
    display: flex;
    max-width: min(520px, calc(100vw - 28px));
    align-items: center;
    gap: 14px;
    padding: 10px 12px;
    border: 1px solid var(--ui-danger);
    border-radius: var(--ui-radius-sm);
    background: var(--ui-danger-soft);
    box-shadow: var(--ui-shadow-md);
}
.error-banner div { display: grid; gap: 2px; }
.error-banner strong { color: var(--ui-danger); font-size: 11px; }
.error-banner span { color: var(--ui-text); }
.error-banner button { border: 0; color: var(--ui-text); background: transparent; font-size: 20px; }

.editor-empty {
    min-height: var(--sub-height);
    display: grid;
    place-content: center;
    justify-items: center;
    gap: 10px;
    margin: 0;
    background: var(--ui-surface);
    border: 1px dashed var(--ui-border-strong);
    border-radius: var(--ui-radius-md);
    color: var(--ui-text-muted);
}

.editor-empty p { margin: 0; }

@media (max-width: 1120px) {
    div#EditorMain {
        grid-template-columns: 288px minmax(720px, 1fr);
        width: max-content;
        min-width: calc(100vw - 24px);
        margin-inline: 12px;
    }
    div#EditorDiv { overflow-x: auto; }
}
</style>
