<script setup>
import { usePalEditorStore } from '@/stores/paleditor';
import AppIcon from '@/components/modules/AppIcon.vue';
import PathPicker from '@/components/PathPicker.vue';

const palStore = usePalEditorStore();
</script>

<template>
  <main id="entryDiv">
    <PathPicker />
    <section class="entry-shell">
      <header class="entry-intro" aria-labelledby="entry-title">
        <img :alt="palStore.getTranslatedText('Common_AppName')" class="logo" src="@/assets/logo.ico" width="60" height="60" />
        <div class="entry-intro-copy">
          <p class="product-name">{{ palStore.getTranslatedText('Common_AppName') }}</p>
          <h1 id="entry-title">{{ palStore.getTranslatedText('EntryView_Title') }}</h1>
        </div>
        <div class="entry-support-copy">
          <p class="entry-copy">{{ palStore.getTranslatedText('EntryView_Intro') }}</p>
          <p class="free-notice">{{ palStore.getTranslatedText('EntryView_Free_Notice') }}</p>
        </div>
      </header>

      <div class="entry-workspace">
        <div class="source-switch" role="radiogroup" :aria-label="palStore.getTranslatedText('Entry_Source_Label')">
          <label :class="{ active: palStore.SAVE_SOURCE_MODE === 'steam' }">
            <input type="radio" v-model="palStore.SAVE_SOURCE_MODE" value="steam" />
            <span class="source-icon" aria-hidden="true">
              <img src="@/assets/steam.svg" alt="" width="26" height="26" />
            </span>
            <span class="source-label-text">
              <span class="source-name">{{ palStore.getTranslatedText('Entry_Source_Steam') }}</span>
            </span>
          </label>
          <label :class="{ active: palStore.SAVE_SOURCE_MODE === 'xgp' }">
            <input type="radio" v-model="palStore.SAVE_SOURCE_MODE" value="xgp" />
            <span class="source-icon" aria-hidden="true">
              <img src="@/assets/xbox.svg" alt="" width="26" height="26" />
            </span>
            <span class="source-label-text">
              <span class="source-name">{{ palStore.getTranslatedText('Entry_Source_Xgp') }}</span>
              <span class="beta-badge">{{ palStore.getTranslatedText('Entry_Source_Beta') }}</span>
            </span>
          </label>
        </div>

        <section class="entry-panel" aria-labelledby="save-path-heading">
          <div class="panel-heading">
            <h2 id="save-path-heading">{{ palStore.getTranslatedText('EntryView_Save_Path') }}</h2>
            <p>{{ palStore.getTranslatedText(palStore.SAVE_SOURCE_MODE === 'xgp' ? 'Entry_Xgp_Hint' : 'EntryView_Path_Hint') }}</p>
          </div>

          <template v-if="palStore.SAVE_SOURCE_MODE === 'steam'">
            <div class="save-path-row">
              <label class="path-field">
                <span class="sr-only">{{ palStore.getTranslatedText('EntryView_Save_Path') }}</span>
                <input
                  type="text"
                  v-model="palStore.PAL_GAME_SAVE_PATH"
                  :placeholder="palStore.getTranslatedText('EntryView_Path_Example')"
                  :disabled="palStore.LOADING_FLAG"
                />
              </label>
              <button class="button button--quiet" @click="palStore.show_file_picker('steam')" :disabled="palStore.LOADING_FLAG">
                {{ palStore.getTranslatedText('EntryView_BTN_Path_Picker') }}
              </button>
            </div>
            <div class="entry-primary-row">
              <button class="button button--primary" @click="palStore.loadSave" :disabled="palStore.LOADING_FLAG">
                {{ palStore.getTranslatedText('EntryView_BTN_Load') }}
              </button>
            </div>
          </template>

          <template v-else>
            <div class="save-path-row">
              <label class="path-field">
                <span class="sr-only">{{ palStore.getTranslatedText('Entry_Xgp_Folder') }}</span>
                <input
                  type="text"
                  v-model="palStore.XGP_WGS_PATH"
                  :placeholder="palStore.getTranslatedText('Entry_Xgp_Path_Example')"
                  :disabled="palStore.LOADING_FLAG"
                />
              </label>
              <button class="button button--quiet" @click="palStore.show_file_picker('xgp')" :disabled="palStore.LOADING_FLAG">
                {{ palStore.getTranslatedText('Entry_Xgp_Select_Folder') }}
              </button>
            </div>
            <div class="entry-primary-row">
              <button class="button button--primary" @click="palStore.discoverXgpSources()" :disabled="palStore.LOADING_FLAG || !palStore.XGP_WGS_PATH">
                {{ palStore.getTranslatedText('Entry_Xgp_Discover') }}
              </button>
            </div>
            <p
              v-if="palStore.LAST_ERROR?.context === 'discover-xgp-sources'"
              class="entry-error"
              role="alert"
            >
              {{ palStore.LAST_ERROR.message }}
            </p>
            <div class="xgp-sources" v-if="palStore.XGP_SOURCES.length" role="radiogroup" :aria-label="palStore.getTranslatedText('Entry_Xgp_Select')">
              <label v-for="source in palStore.XGP_SOURCES" :key="source.sourceId" class="xgp-source">
                <input type="radio" v-model="palStore.SELECTED_XGP_SOURCE_ID" :value="source.sourceId" />
                <span>
                  <strong>{{ source.displayName }}</strong>
                  <small>{{ source.worldId?.slice(0, 8) }} · {{ new Date(source.updatedAt).toLocaleString() }}</small>
                </span>
                <em>{{ palStore.getTranslatedText(`Entry_Xgp_Status_${source.status}`) }}</em>
              </label>
            </div>
            <p class="path-current" v-else>{{ palStore.getTranslatedText('Entry_Xgp_NoSources') }}</p>
            <button class="button button--primary xgp-load" @click="palStore.loadSave" :disabled="palStore.LOADING_FLAG || !palStore.SELECTED_XGP_SOURCE_ID">
              {{ palStore.getTranslatedText('EntryView_BTN_Load') }}
            </button>
          </template>
        </section>
      </div>

      <footer class="entry-safety">
        <p><AppIcon name="shield" :size="15" />{{ palStore.getTranslatedText('Entry_Safety_Backup') }}</p>
        <p><AppIcon name="file" :size="15" />{{ palStore.getTranslatedText('Entry_Safety_Platforms') }}</p>
      </footer>
    </section>

    <p class="version-info">{{ palStore.VERSION }}</p>
  </main>
</template>

<style scoped>
#entryDiv {
  position: relative;
  width: min(1112px, calc(100vw - 48px));
  min-height: 100dvh;
  margin: 0 auto;
  padding: 104px 0 36px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.entry-shell {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  width: 100%;
  height: clamp(620px, calc(100dvh - 176px), 750px);
  min-height: 0;
  overflow: hidden;
  background: var(--ui-surface);
  border: 1px solid var(--ui-border);
  border-radius: 0;
  box-shadow: var(--ui-shadow-md);
}

.entry-intro {
  display: grid;
  grid-template-columns: 60px minmax(0, 1fr);
  align-items: start;
  gap: 16px;
  padding: 30px 28px 18px;
}

.logo {
  border-radius: 15px;
  box-shadow: 0 1px 0 oklch(0.6 0.03 252 / 0.16) inset, var(--ui-shadow-md);
}

.entry-intro-copy { min-width: 0; }
.entry-support-copy { grid-column: 1 / -1; min-width: 0; }

.product-name {
  margin: 0 0 5px;
  color: var(--ui-accent-strong);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.045em;
  text-transform: uppercase;
}

h1, h2, p { margin: 0; }

h1 {
  color: var(--ui-text);
  max-width: 20ch;
  font-size: clamp(30px, 3vw, 40px);
  line-height: 1.12;
  font-weight: 690;
  letter-spacing: -0.035em;
  text-wrap: balance;
}

.entry-copy {
  max-width: 72ch;
  margin-top: 0;
  color: var(--ui-text-muted);
  font-size: 14px;
  line-height: 1.65;
  text-wrap: pretty;
}

.free-notice {
  display: inline-flex;
  align-items: center;
  margin-top: 8px;
  padding: 4px 9px;
  color: var(--ui-success);
  background: oklch(0.25 0.055 158);
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
}

.entry-workspace {
  display: grid;
  grid-template-columns: 323px minmax(0, 1fr);
  min-height: 0;
  border-top: 1px solid var(--ui-border);
  border-bottom: 1px solid var(--ui-border);
}

.source-switch {
  display: flex;
  flex-direction: column;
  min-width: 0;
  padding: 18px 20px;
  border-right: 1px solid var(--ui-border);
}

.source-switch label {
  position: relative;
  display: grid;
  grid-template-columns: 38px minmax(0, 1fr);
  align-items: center;
  gap: 12px;
  min-height: 64px;
  padding: 0 14px;
  color: var(--ui-text-muted);
  border: 1px solid transparent;
  border-radius: var(--ui-radius-sm);
  cursor: pointer;
}

.source-switch label::before {
  position: absolute;
  inset: 8px auto 8px -1px;
  width: 3px;
  background: transparent;
  border-radius: 0 3px 3px 0;
  content: '';
}

.source-switch label:hover { color: var(--ui-text-secondary); background: var(--ui-surface-raised); }
.source-switch label.active {
  color: var(--ui-text);
  background: var(--ui-accent-soft);
  border-color: var(--ui-accent);
}
.source-switch label.active::before { background: var(--ui-accent); }
.source-switch label:focus-within { outline: 2px solid var(--ui-accent); outline-offset: 2px; }
.source-switch input { position: absolute; opacity: 0; pointer-events: none; }
.source-icon {
  display: grid;
  width: 38px;
  height: 38px;
  place-items: center;
  border-radius: 50%;
}
.source-icon img { display: block; opacity: .88; }
.source-label-text { display: flex; align-items: center; gap: 8px; min-width: 0; }
.source-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 620; }
.beta-badge {
  padding: 2px 6px;
  color: var(--ui-text-secondary);
  background: var(--ui-surface-raised);
  border-radius: 999px;
  font-size: 9px;
  font-weight: 760;
  letter-spacing: .08em;
  line-height: 1.5;
}

.entry-panel {
  display: flex;
  flex-direction: column;
  width: 100%;
  min-height: 0;
  padding: 28px 28px 26px;
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

.save-path-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 118px;
  gap: 10px;
  margin-top: 18px;
}

.path-field { display: block; min-width: 0; }

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

.entry-primary-row { display: flex; justify-content: flex-end; margin-top: 24px; }
.entry-primary-row .button { min-width: 204px; min-height: 44px; }

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
.entry-error {
  margin-top: 10px;
  padding: 9px 11px;
  color: var(--ui-danger, #ff8d8d);
  background: color-mix(in srgb, var(--ui-danger, #ef4444) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--ui-danger, #ef4444) 34%, transparent);
  border-radius: var(--ui-radius-sm);
  font-size: 12px;
  line-height: 1.55;
}
.xgp-load { width: 204px; align-self: flex-end; margin-top: auto; }
.xgp-sources {
  display: grid;
  flex: 1 1 0;
  grid-auto-rows: max-content;
  align-content: start;
  gap: 7px;
  min-height: 0;
  overflow-y: auto;
  margin: 12px 0 14px;
}
.xgp-source {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 10px;
  color: var(--ui-text-secondary);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
  cursor: pointer;
}
.xgp-source:has(input:checked) { border-color: var(--ui-accent); background: var(--ui-accent-soft); }
.xgp-source span { display: grid; gap: 3px; min-width: 0; }
.xgp-source strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; }
.xgp-source small, .xgp-source em { color: var(--ui-text-muted); font-size: 10px; font-style: normal; }
.entry-safety {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  min-height: 68px;
  padding: 0 28px;
  color: var(--ui-text-muted);
  font-size: 11px;
}
.entry-safety p { display: inline-flex; align-items: center; gap: 7px; }
.version-info { color: var(--ui-text-muted); font-size: 11px; letter-spacing: 0.025em; }

@media (max-width: 920px) {
  .entry-workspace { grid-template-columns: 250px minmax(0, 1fr); }
  .source-switch { padding-inline: 12px; }
  .entry-panel { padding-inline: 24px; }
}

@media (max-width: 760px) {
  #entryDiv { width: min(100% - 28px, 640px); padding-top: 82px; }
  .entry-shell { height: auto; min-height: 0; overflow: visible; }
  .entry-intro { grid-template-columns: 56px minmax(0, 1fr); gap: 14px; padding: 22px 20px; }
  .logo { width: 56px; height: 56px; border-radius: 13px; }
  .entry-workspace { grid-template-columns: 1fr; }
  .source-switch {
    display: grid;
    grid-template-columns: 1fr 1fr;
    padding: 12px;
    border-right: 0;
    border-bottom: 1px solid var(--ui-border);
  }
  .source-switch label { min-height: 58px; padding-inline: 10px; }
  .source-icon { display: none; }
  .source-switch label { grid-template-columns: minmax(0, 1fr); gap: 7px; }
  .entry-panel { min-height: 360px; padding: 22px 20px; }
  .save-path-row { grid-template-columns: 1fr; }
  .entry-primary-row .button, .xgp-load { width: 100%; }
  .entry-safety { align-items: flex-start; flex-direction: column; gap: 7px; padding: 12px 20px; }
  h1 { max-width: 22ch; }
}

@media (prefers-reduced-motion: reduce) {
  .button { transition: none; }
}
</style>
