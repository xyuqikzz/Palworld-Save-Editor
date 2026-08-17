<script setup>
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'

import AppIcon from '@/components/modules/AppIcon.vue'
import PalEditor from '@/components/PalEditor.vue'
import PalList from '@/components/PalList.vue'
import { usePalEditorStore } from '@/stores/paleditor'

const palStore = usePalEditorStore()
const router = useRouter()

onMounted(async () => {
  if (!palStore.GLOBAL_PALBOX_SESSION) {
    await router.replace({ name: 'Entry', query: { source: 'global-palbox' } })
    return
  }
  if (!palStore.PAL_STATIC_DATA_LIST.length) {
    await palStore.fetchStaticData()
  }
  if (!palStore.SELECTED_PAL_ID) {
    const firstPalId = palStore.PAL_MAP.keys().next().value
    if (firstPalId) await palStore.selectPal(firstPalId)
  }
})
</script>

<template>
  <div id="EditorDiv">
    <aside v-if="palStore.GLOBAL_PALBOX_ERROR" class="error-banner" role="alert">
      <span>{{ palStore.GLOBAL_PALBOX_ERROR }}</span>
      <button
        type="button"
        :aria-label="palStore.getTranslatedText('Common_DismissError')"
        @click="palStore.GLOBAL_PALBOX_ERROR = null"
      >
        <AppIcon name="x" :size="17" />
      </button>
    </aside>

    <div id="EditorMain">
      <aside class="selection-column selection-column--global">
        <PalList global-palbox />
      </aside>

      <PalEditor
        v-if="palStore.SELECTED_PAL_ID && palStore.SELECTED_PAL_DATA"
        global-palbox
      />

      <section v-else class="editor-empty">
        <p>{{ palStore.getTranslatedText('GlobalPalbox_SelectHint') }}</p>
      </section>
    </div>
  </div>
</template>

<style scoped>
div#EditorDiv {
  display: flow-root;
  min-height: 100dvh;
  width: 100%;
  overflow-x: clip;
  background: var(--ui-canvas);
}

div#EditorMain {
  display: grid;
  grid-template-columns: minmax(364px, 416px) minmax(0, 1fr);
  align-items: stretch;
  gap: 14px;
  width: 100%;
  margin-top: var(--editor-top-offset);
  margin-inline: 0;
  padding: 0 10px 16px;
  background: var(--ui-canvas);
}

.selection-column {
  display: grid;
  grid-template-rows: minmax(0, 1fr);
  height: var(--sub-height);
  min-width: 0;
  min-height: 0;
  background: var(--ui-canvas);
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
  gap: 12px;
  padding: 10px 12px;
  color: var(--ui-text);
  background: var(--ui-danger-soft);
  border: 1px solid var(--ui-danger);
  border-radius: var(--ui-radius-sm);
}

.error-banner span { color: var(--ui-text); }
.error-banner button { border: 0; color: inherit; background: transparent; }

.editor-empty {
  min-height: var(--sub-height);
  display: grid;
  place-content: center;
  color: var(--ui-text-muted);
  background: var(--ui-surface);
  border: 1px dashed var(--ui-border-strong);
  border-radius: var(--ui-radius-md);
}

@media (max-width: 1120px) {
  div#EditorMain {
    grid-template-columns: minmax(0, 1fr);
    width: 100%;
    min-width: 0;
    margin-inline: 0;
    padding-inline: 10px;
  }

  .selection-column {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: clamp(240px, 34vh, 340px);
    height: auto;
  }
}

@media (max-width: 680px) {
  div#EditorMain { gap: 10px; padding-inline: 8px; }
  .selection-column { grid-auto-rows: clamp(240px, 34vh, 320px); }
}
</style>
