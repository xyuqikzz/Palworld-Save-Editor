<script setup>
import { usePalEditorStore } from '@/stores/paleditor';
import { ref, watch } from 'vue';
import AppIcon from '@/components/modules/AppIcon.vue';

const palStore = usePalEditorStore();
const loadingWidth = ref(0);
const showLoading = ref(false);
const interval = ref(null);

watch(() => palStore.LOADING_FLAG, (isLoading) => {
  if (isLoading) {
    interval.value = setInterval(() => {
      if (loadingWidth.value < 92) loadingWidth.value += Math.random() * 6;
    }, 220);
    showLoading.value = true;
    loadingWidth.value = 4;
    return;
  }

  loadingWidth.value = 100;
  setTimeout(() => {
    showLoading.value = false;
    clearInterval(interval.value);
  }, 180);
});

watch(() => palStore.I18n, async (locale) => {
  document.documentElement.lang = locale || 'en';
  document.title = await palStore.getTranslatedText('Common_AppName');
}, { immediate: true });

const save = () => palStore.writeSave();
const toggleInvalidOptions = () => {
  palStore.HIDE_INVALID_OPTIONS = !palStore.HIDE_INVALID_OPTIONS;
};
</script>

<template>
  <div v-if="showLoading" class="loading-bar" :style="{ width: loadingWidth + '%' }" />
  <header id="topbar">
    <div class="brand" :aria-label="palStore.getTranslatedText('Common_AppName')">
      <img src="@/assets/logo.ico" alt="" width="30" height="30" />
      <span>{{ palStore.getTranslatedText('Common_AppName') }}</span>
    </div>
    <div class="topbar__workspace">
      <template v-if="palStore.SAVE_LOADED_FLAG">
        <span :class="['source-badge', `source-badge--${palStore.SAVE_PLATFORM}`]">
          {{ palStore.getTranslatedText(palStore.SAVE_PLATFORM === 'xgp' ? 'SourceBadge_Xgp' : 'SourceBadge_Steam') }}
        </span>
        <div class="session-state" :title="palStore.getTranslatedText('TopBar_SessionTitle', [palStore.SESSION_ID])">
          <span>r{{ palStore.SESSION_REVISION }}</span>
          <strong v-if="palStore.PENDING_CHANGE_COUNT">
            {{ palStore.getTranslatedText('TopBar_PendingChanges', [palStore.PENDING_CHANGE_COUNT]) }}
          </strong>
          <em v-else>{{ palStore.getTranslatedText('TopBar_Saved') }}</em>
        </div>
        <label class="save-location" :title="palStore.SAVE_PLATFORM === 'xgp' ? palStore.getTranslatedText('TopBar_Xgp_TargetLocked') : ''">
          <span class="sr-only">{{ palStore.getTranslatedText('TopBar_Save_Path') }}</span>
          <input
            v-if="palStore.SAVE_CAPABILITIES.targetPathEditable"
            class="savePath"
            type="text"
            v-model="palStore.PAL_WRITE_BACK_PATH"
            :placeholder="palStore.PAL_GAME_SAVE_PATH"
            :disabled="palStore.LOADING_FLAG"
          />
          <span v-else class="savePath savePath--locked">{{ palStore.SOURCE_DISPLAY_NAME }}</span>
        </label>
        <div class="action-group action-group--primary">
          <button class="op op--primary" @click="save" :disabled="palStore.LOADING_FLAG || !palStore.PENDING_CHANGE_COUNT">
            {{ palStore.getTranslatedText('TopBar_Btn_Save') }}
          </button>
          <button
            v-if="palStore.SAVE_CAPABILITIES.exportSteamCopy"
            class="op op--compact"
            @click="palStore.exportSteamCopy"
            :disabled="palStore.LOADING_FLAG"
          >
            {{ palStore.getTranslatedText('TopBar_ExportSteam') }}
          </button>
          <button class="op op--icon" @click="palStore.loadSave" :disabled="palStore.LOADING_FLAG" :title="palStore.getTranslatedText('TopBar_Btn_Reload')">
            <AppIcon name="refresh" :size="16" />
            <span class="sr-only">{{ palStore.getTranslatedText('TopBar_Btn_Reload') }}</span>
          </button>
          <button class="op op--icon" @click="palStore.returnToMain" :disabled="palStore.LOADING_FLAG" :title="palStore.getTranslatedText('TopBar_Btn_Main_Page')">
            <AppIcon name="back" :size="16" />
            <span class="sr-only">{{ palStore.getTranslatedText('TopBar_Btn_Main_Page') }}</span>
          </button>
        </div>
      </template>
    </div>
    <div class="topbar__right">
      <div v-if="palStore.SAVE_LOADED_FLAG" class="action-group action-group--tools">
        <button
          class="op op--compact"
          :title="palStore.getTranslatedText(
            palStore.COMPLETABLE_EXPEDITION_COUNT === 0
              ? 'TopBar_Btn_CompleteExpeditions_Disabled'
              : 'TopBar_Btn_CompleteExpeditions_Tooltips'
          )"
          :disabled="palStore.LOADING_FLAG || palStore.COMPLETABLE_EXPEDITION_COUNT === 0"
          @click="palStore.completeActiveExpeditions"
        >
          {{ palStore.getTranslatedText(
            palStore.COMPLETABLE_EXPEDITION_COUNT === 0
              ? 'TopBar_Btn_CompleteExpeditions_Disabled'
              : 'TopBar_Btn_CompleteExpeditions'
          ) }}
        </button>
        <button
          class="op op--compact"
          :title="palStore.getTranslatedText(
            palStore.EXPEDITION_PAL_COUNT === 0
              ? 'TopBar_Btn_UnlockExpeditionPals_Disabled'
              : 'TopBar_Btn_UnlockExpeditionPals_Tooltips'
          )"
          :disabled="palStore.LOADING_FLAG || palStore.EXPEDITION_PAL_COUNT === 0"
          @click="palStore.unlockExpeditionPals"
        >
          {{ palStore.getTranslatedText(
            palStore.EXPEDITION_PAL_COUNT === 0
              ? 'TopBar_Btn_UnlockExpeditionPals_Disabled'
              : 'TopBar_Btn_UnlockExpeditionPals'
          ) }}
        </button>
        <button
          class="op op--compact"
          :title="palStore.getTranslatedText('TopBar_Btn_HealAllPals_Tooltips')"
          :disabled="palStore.LOADING_FLAG || palStore.PAL_MAP.size === 0"
          @click="palStore.healAllPals"
        >
          {{ palStore.getTranslatedText('TopBar_Btn_HealAllPals') }}
        </button>
        <button
          :class="['op', 'op--compact', { 'op--active': palStore.SHOW_OOB_PAL_FLAG }]"
          @click="palStore.SHOW_OOB_PAL_FLAG = !palStore.SHOW_OOB_PAL_FLAG"
          :disabled="palStore.LOADING_FLAG"
          :title="palStore.getTranslatedText('TopBar_Pal_OOB_Tooltips')"
        >
          {{ palStore.getTranslatedText('TopBar_Btn_Pal_OOB') }}
        </button>
        <button
          :class="['op', 'op--compact', { 'op--active': palStore.HIDE_INVALID_OPTIONS }]"
          @click="toggleInvalidOptions"
          :disabled="palStore.LOADING_FLAG"
          :title="palStore.getTranslatedText('TopBar_Invalid_Options_Tooltips')"
        >
          {{ palStore.getTranslatedText('TopBar_Btn_Invalid_Options') }}
        </button>
      </div>
      <label class="language-control">
        <span class="sr-only">{{ palStore.getTranslatedText('TopBar_Language') }}</span>
        <select id="languageSelect" v-model="palStore.I18n" @change="palStore.updateI18n" :disabled="palStore.LOADING_FLAG">
          <option :value="key" v-for="translated, key in palStore.I18nList">{{ translated }}</option>
        </select>
      </label>
    </div>
    <div v-if="palStore.LAST_SAVE_RESULT?.backup_path || palStore.LAST_SAVE_RESULT?.recovery_status === 'failed'" class="save-evidence" role="status">
      <span v-if="palStore.LAST_SAVE_RESULT?.backup_path">
        {{ palStore.getTranslatedText('Xgp_Backup_Path') }}: {{ palStore.LAST_SAVE_RESULT.backup_path }}
      </span>
      <span v-if="palStore.LAST_SAVE_RESULT?.recovery_status">
        {{ palStore.getTranslatedText('Xgp_Recovery_Status') }}: {{ palStore.LAST_SAVE_RESULT.recovery_status }}
      </span>
      <span v-if="palStore.SAVE_PLATFORM === 'xgp'">{{ palStore.getTranslatedText('Xgp_Cloud_Unverified') }}</span>
    </div>
  </header>
</template>

<style scoped>
#topbar {
  position: fixed;
  inset: 0 0 auto;
  z-index: 40;
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 8px 16px;
  background: oklch(0.19 0.02 252 / 0.94);
  border-bottom: 1px solid var(--ui-border);
  box-shadow: 0 1px 0 oklch(0.5 0.03 252 / 0.12) inset, var(--ui-shadow-sm);
  backdrop-filter: blur(18px) saturate(1.2);
}

.brand {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 9px;
  color: var(--ui-text);
  font-size: 13px;
  font-weight: 650;
  letter-spacing: -0.01em;
}

.brand img {
  border-radius: 8px;
  box-shadow: 0 2px 8px oklch(0.3 0.04 250 / 0.16);
}

.topbar__workspace {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.topbar__right,
.action-group,
.save-location {
  display: flex;
  align-items: center;
}

.session-state {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 8px;
  color: var(--ui-text-muted);
  font-size: 11px;
  white-space: nowrap;
}
.source-badge {
  flex: 0 0 auto;
  padding: 4px 7px;
  border: 1px solid var(--ui-border-strong);
  border-radius: 999px;
  color: var(--ui-text-muted);
  font-size: 10px;
  font-weight: 700;
}
.source-badge--xgp { color: var(--ui-accent); border-color: var(--ui-accent); background: var(--ui-accent-soft); }
.session-state strong { color: var(--ui-accent); font-weight: 650; }
.session-state em { color: var(--ui-success); font-style: normal; }

.topbar__right { flex: 0 0 auto; gap: 10px; }
.action-group { gap: 4px; }

.save-location {
  min-width: 170px;
  width: min(380px, 32vw);
  height: 36px;
  gap: 8px;
  padding-left: 10px;
  color: var(--ui-text-muted);
  background: var(--ui-surface-raised);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
}

.savePath,
#languageSelect,
.op {
  min-height: 36px;
  border-radius: var(--ui-radius-sm);
  border: 1px solid var(--ui-border);
  font: inherit;
}

.savePath {
  min-width: 0;
  width: 100%;
  padding: 0 8px 0 0;
  background: transparent;
  border: 0;
  border-radius: 0;
  color: var(--ui-text);
  font-size: 12px;
}

.savePath:focus-visible { outline: 0; }
.savePath--locked { display: flex; align-items: center; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.save-location:focus-within { border-color: var(--ui-accent); box-shadow: 0 0 0 3px oklch(0.72 0.14 246 / 0.16); }

#languageSelect {
  max-width: 118px;
  padding: 0 26px 0 9px;
  background: var(--ui-surface);
  color: var(--ui-text);
  font-size: 12px;
}

.op {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 0 10px;
  background: var(--ui-surface);
  color: var(--ui-text-secondary);
  font-size: 12px;
  font-weight: 550;
}

.op--icon { width: 36px; padding: 0; }
.op--compact { padding-inline: 9px; }

.op:hover:not(:disabled) {
  color: var(--ui-text);
  background: var(--ui-surface-hover);
  border-color: var(--ui-border-strong);
}

.op--primary {
  background: var(--ui-accent);
  border-color: var(--ui-accent);
  color: oklch(0.16 0.025 252);
}

.op--primary:hover:not(:disabled) {
  background: var(--ui-accent-strong);
  border-color: var(--ui-accent-strong);
}

.op--active {
  border-color: var(--ui-accent);
  color: var(--ui-accent);
  background: var(--ui-accent-soft);
}

.op:disabled,
.savePath:disabled,
#languageSelect:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.loading-bar {
  position: fixed;
  inset: 0 auto auto 0;
  z-index: 50;
  height: 2px;
  background: var(--ui-accent);
  transition: width 180ms ease-out;
}
.save-evidence {
  position: fixed;
  top: 62px;
  right: 12px;
  display: grid;
  gap: 2px;
  max-width: min(620px, calc(100vw - 24px));
  padding: 8px 10px;
  color: var(--ui-text-secondary);
  background: var(--ui-surface);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
  box-shadow: var(--ui-shadow-md);
  font-size: 10px;
  overflow-wrap: anywhere;
}

@media (max-width: 940px) {
  .brand span { display: none; }
  .action-group--tools .op { width: 36px; padding: 0; font-size: 0; }
  .action-group--tools .op:first-child { font-size: 0; }
  .save-location { width: min(300px, 36vw); }
}

@media (max-width: 680px) {
  #topbar { padding-inline: 10px; gap: 8px; }
  .brand { display: none; }
  .save-location { width: min(220px, 42vw); }
  #languageSelect { width: 76px; }
}

@media (prefers-reduced-motion: reduce) {
  .op, .loading-bar { transition: none; }
}
</style>
