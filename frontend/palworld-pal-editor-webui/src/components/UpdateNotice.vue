<script setup>
import { usePalEditorStore } from '@/stores/paleditor';

const palStore = usePalEditorStore();
</script>

<template>
  <aside
    v-if="palStore.AVAILABLE_UPDATE"
    class="update-notice"
    role="status"
    aria-live="polite"
  >
    <strong>
      {{ palStore.getTranslatedText('EntryView_Update_Notice', [palStore.AVAILABLE_UPDATE.version]) }}
    </strong>
    <div class="update-actions">
      <a
        :href="palStore.AVAILABLE_UPDATE.url"
        target="_blank"
        rel="noopener noreferrer"
        @click="palStore.skipUpdate"
      >
        {{ palStore.getTranslatedText('EntryView_Update_Download') }}
      </a>
      <button type="button" @click="palStore.skipUpdate">
        {{ palStore.getTranslatedText('EntryView_Update_Skip') }}
      </button>
    </div>
  </aside>
</template>

<style scoped>
.update-notice {
  position: fixed;
  z-index: 39;
  inset: 72px 16px auto auto;
  width: min(420px, calc(100vw - 32px));
  box-sizing: border-box;
  display: grid;
  gap: 12px;
  padding: 14px 16px;
  color: var(--ui-text);
  background: var(--ui-surface);
  border: 1px solid var(--ui-border-strong);
  border-radius: var(--ui-radius-md);
  box-shadow: var(--ui-shadow-md);
}

.update-notice strong {
  font-size: 13px;
  line-height: 1.5;
}

.update-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.update-actions a,
.update-actions button {
  min-height: 34px;
  box-sizing: border-box;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0 12px;
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
  font: inherit;
  font-size: 12px;
  text-decoration: none;
  cursor: pointer;
}

.update-actions a {
  color: oklch(0.16 0.025 252);
  background: var(--ui-accent);
  border-color: var(--ui-accent);
}

.update-actions button {
  color: var(--ui-text-secondary);
  background: var(--ui-surface-raised);
}

.update-actions a:hover { background: var(--ui-accent-strong); }
.update-actions button:hover { color: var(--ui-text); background: var(--ui-surface-hover); }
</style>
