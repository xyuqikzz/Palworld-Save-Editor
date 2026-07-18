<script setup>
import { usePalEditorStore } from '@/stores/paleditor';
import PathPicker from '@/components/PathPicker.vue';

const palStore = usePalEditorStore();
</script>

<template>
  <main id="entryDiv">
    <PathPicker />
    <section class="entry-intro" aria-labelledby="entry-title">
      <img :alt="palStore.getTranslatedText('Common_AppName')" class="logo" src="@/assets/logo.ico" width="84" height="84" />
      <div>
        <p class="product-name">{{ palStore.getTranslatedText('Common_AppName') }}</p>
        <h1 id="entry-title">{{ palStore.getTranslatedText('EntryView_Title') }}</h1>
        <p class="entry-copy">{{ palStore.getTranslatedText('EntryView_Intro') }}</p>
      </div>
      <p class="free-notice">{{ palStore.getTranslatedText('EntryView_Free_Notice') }}</p>
    </section>

    <section class="entry-panel" aria-labelledby="save-path-heading">
      <div class="panel-heading">
        <h2 id="save-path-heading">{{ palStore.getTranslatedText('EntryView_Save_Path') }}</h2>
        <p>{{ palStore.getTranslatedText('EntryView_Path_Hint') }}</p>
      </div>
      <label class="path-field">
        <span class="sr-only">{{ palStore.getTranslatedText('EntryView_Save_Path') }}</span>
        <input
          type="text"
          v-model="palStore.PAL_GAME_SAVE_PATH"
          :placeholder="palStore.getTranslatedText('EntryView_Path_Example')"
          :disabled="palStore.LOADING_FLAG"
        />
      </label>
      <div class="entry-actions">
        <button class="button button--quiet" @click="palStore.show_file_picker" :disabled="palStore.LOADING_FLAG">
          {{ palStore.getTranslatedText('EntryView_BTN_Path_Picker') }}
        </button>
        <button class="button button--primary" @click="palStore.loadSave" :disabled="palStore.LOADING_FLAG">
          {{ palStore.getTranslatedText('EntryView_BTN_Load') }}
        </button>
      </div>
      <p class="path-current" v-if="palStore.PAL_GAME_SAVE_PATH">{{ palStore.PAL_GAME_SAVE_PATH }}</p>
    </section>

    <p class="version-info">{{ palStore.VERSION }}</p>
  </main>
</template>

<style scoped>
#entryDiv {
  position: relative;
  width: min(1040px, calc(100vw - 48px));
  min-height: 100dvh;
  margin: 0 auto;
  padding: 96px 0 48px;
  display: grid;
  grid-template-columns: minmax(0, 1.08fr) minmax(380px, 0.92fr);
  align-content: center;
  column-gap: 72px;
  row-gap: 30px;
}

.entry-intro {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 20px;
  max-width: 520px;
}

.logo {
  border-radius: 19px;
  box-shadow: 0 1px 0 oklch(0.6 0.03 252 / 0.16) inset, var(--ui-shadow-md);
}

.product-name {
  margin: 0 0 7px;
  color: var(--ui-accent-strong);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.045em;
  text-transform: uppercase;
}

h1, h2, p { margin: 0; }

h1 {
  color: var(--ui-text);
  max-width: 18ch;
  font-size: clamp(30px, 3.1vw, 42px);
  line-height: 1.12;
  font-weight: 690;
  letter-spacing: -0.035em;
  text-wrap: balance;
}

.entry-copy {
  max-width: 42ch;
  margin-top: 16px;
  color: var(--ui-text-muted);
  font-size: 15px;
  line-height: 1.72;
  text-wrap: pretty;
}

.free-notice {
  display: inline-flex;
  align-items: center;
  padding: 6px 9px;
  color: var(--ui-success);
  background: oklch(0.25 0.055 158);
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
}

.entry-panel {
  align-self: center;
  padding: 26px;
  background: var(--ui-surface);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-lg);
  box-shadow: var(--ui-shadow-md);
}

.panel-heading h2 {
  color: var(--ui-text);
  font-size: 18px;
  font-weight: 680;
  letter-spacing: -0.015em;
}

.panel-heading p,
.path-current {
  margin-top: 6px;
  color: var(--ui-text-muted);
  font-size: 13px;
  line-height: 1.6;
}

.path-field { display: block; margin-top: 20px; }

.path-field input {
  box-sizing: border-box;
  width: 100%;
  min-height: 44px;
  padding: 0 13px;
  color: var(--ui-text);
  background: var(--ui-canvas);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
  font: inherit;
  font-size: 13px;
}

.path-field input:hover:not(:disabled) { border-color: var(--ui-border-strong); }
.path-field input:focus { outline: 0; border-color: var(--ui-accent); box-shadow: 0 0 0 3px oklch(0.72 0.14 246 / 0.16); }

.entry-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 9px; margin-top: 12px; }

.button {
  min-height: 40px;
  padding: 0 14px;
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
  font: inherit;
  cursor: pointer;
  transition: background-color 160ms ease, border-color 160ms ease;
}

.button--quiet { background: var(--ui-surface-raised); color: var(--ui-text-secondary); }
.button--primary { background: var(--ui-accent); border-color: var(--ui-accent); color: oklch(0.16 0.025 252); }
.button:hover:not(:disabled) { border-color: var(--ui-border-strong); background: var(--ui-surface-hover); }
.button--primary:hover:not(:disabled) { background: var(--ui-accent-strong); border-color: var(--ui-accent-strong); }
.button:disabled { opacity: .5; cursor: not-allowed; }

.path-current { overflow-wrap: anywhere; }
.version-info { grid-column: 1 / -1; color: var(--ui-text-muted); font-size: 11px; letter-spacing: 0.025em; }

@media (max-width: 760px) {
  #entryDiv { grid-template-columns: 1fr; gap: 30px; padding-top: 96px; }
  .entry-panel { width: auto; }
  h1 { max-width: 22ch; }
}

@media (prefers-reduced-motion: reduce) {
  .button { transition: none; }
}
</style>
