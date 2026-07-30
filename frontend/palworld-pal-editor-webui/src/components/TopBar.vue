<script setup>
import AppIcon from '@/components/modules/AppIcon.vue'
import { usePalEditorStore } from '@/stores/paleditor'
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const palStore = usePalEditorStore()
const route = useRoute()
const router = useRouter()
const loadingWidth = ref(0)
const showLoading = ref(false)
const interval = ref(null)
const settingsOpen = ref(false)
const settingsButton = ref(null)
const settingsCloseButton = ref(null)

const palRouteNames = new Set([
  'Editor',
  'PlayerPalEditor',
  'BaseEditor',
  'BasePalEditor',
])
const playerRouteNames = new Set(['Players', 'PlayerEditor'])
const isOverview = computed(() => route.name === 'Overview')
const isPalEditor = computed(() => palRouteNames.has(route.name))
const isPlayerEditor = computed(() => playerRouteNames.has(route.name))
const isMap = computed(() => route.name === 'Map')
const isGuilds = computed(() => route.name === 'Guilds')
const isArenaLeaderboard = computed(() => route.name === 'ArenaLeaderboard')
const isExpeditions = computed(() => route.name === 'Expeditions')
const isJsonEditor = computed(() => route.name === 'JsonEditor')
const displayVersion = computed(() => (
  palStore.VERSION.match(/^\d+\.\d+\.\d+/)?.[0] || palStore.VERSION
))
const saveButtonHint = computed(() => {
  if (palStore.LOADING_FLAG) {
    return palStore.getTranslatedText('TopBar_Save_Disabled_Loading')
  }
  if (!palStore.PENDING_CHANGE_COUNT) {
    return palStore.getTranslatedText('TopBar_Save_Disabled_NoChanges')
  }
  return palStore.getTranslatedText('TopBar_Action_Save')
})

watch(() => palStore.LOADING_FLAG, (isLoading) => {
  if (isLoading) {
    interval.value = setInterval(() => {
      if (loadingWidth.value < 92) loadingWidth.value += Math.random() * 6
    }, 220)
    showLoading.value = true
    loadingWidth.value = 4
    return
  }

  loadingWidth.value = 100
  setTimeout(() => {
    showLoading.value = false
    clearInterval(interval.value)
  }, 180)
})

watch(() => palStore.I18n, async (locale) => {
  document.documentElement.lang = locale || 'en'
  document.title = await palStore.getTranslatedText('Common_AppName')
}, { immediate: true })

watch(settingsOpen, async (open) => {
  document.body.classList.toggle('settings-drawer-open', open)
  if (open) {
    await nextTick()
    settingsCloseButton.value?.focus()
  }
})

watch(() => route.fullPath, () => {
  if (settingsOpen.value) closeSettings(false)
})

function save() {
  palStore.writeSave()
}

async function refreshSave() {
  if (await palStore.refreshSave()) {
    window.location.reload()
  }
}

function navigate(name) {
  if (route.name !== name) router.push({ name })
}

async function returnToSaveSelection() {
  if (await palStore.returnToMain()) {
    await router.push({ name: 'Entry' })
  }
}

function openSettings() {
  settingsOpen.value = true
}

function closeSettings(restoreFocus = true) {
  settingsOpen.value = false
  if (restoreFocus) nextTick(() => settingsButton.value?.focus())
}

function onSettingsKeydown(event) {
  if (event.key === 'Escape' && settingsOpen.value) closeSettings()
}

document.addEventListener('keydown', onSettingsKeydown)

onBeforeUnmount(() => {
  clearInterval(interval.value)
  document.removeEventListener('keydown', onSettingsKeydown)
  document.body.classList.remove('settings-drawer-open')
})
</script>

<template>
  <div v-if="showLoading" class="loading-bar" :style="{ width: loadingWidth + '%' }" />
  <header id="topbar" :class="{ 'topbar--loaded': palStore.SAVE_LOADED_FLAG }">
    <div class="topbar__primary">
      <div class="topbar__context">
        <button
          class="brand"
          type="button"
          :class="{ 'brand--clickable': palStore.SAVE_LOADED_FLAG }"
          :tabindex="palStore.SAVE_LOADED_FLAG ? 0 : -1"
          :aria-label="palStore.getTranslatedText('Common_AppName')"
          @click="palStore.SAVE_LOADED_FLAG && returnToSaveSelection()"
        >
          <img src="@/assets/logo.ico" alt="" width="30" height="30" />
          <span>{{ palStore.getTranslatedText('Common_AppName') }}</span>
        </button>

        <template v-if="palStore.SAVE_LOADED_FLAG">
          <span :class="['source-badge', `source-badge--${palStore.SAVE_PLATFORM}`]">
            {{ palStore.getTranslatedText(palStore.SAVE_PLATFORM === 'xgp' ? 'SourceBadge_Xgp' : 'SourceBadge_Steam') }}
          </span>
          <label
            class="save-location"
            :title="palStore.SAVE_PLATFORM === 'xgp' ? palStore.getTranslatedText('TopBar_Xgp_TargetLocked') : palStore.PAL_GAME_SAVE_PATH"
          >
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
        </template>
      </div>

      <div class="topbar__actions">
        <template v-if="palStore.SAVE_LOADED_FLAG">
          <button
            class="op op--primary"
            type="button"
            :disabled="palStore.LOADING_FLAG || !palStore.PENDING_CHANGE_COUNT"
            :title="saveButtonHint"
            :aria-label="saveButtonHint"
            @click="save"
          >
            {{ palStore.getTranslatedText('TopBar_Action_Save') }}
          </button>
          <button
            class="op"
            type="button"
            :title="palStore.getTranslatedText('TopBar_RefreshLatest')"
            :disabled="palStore.LOADING_FLAG"
            @click="refreshSave"
          >
            <AppIcon name="refresh" :size="16" />
            {{ palStore.getTranslatedText('TopBar_Action_Refresh') }}
          </button>
          <button
            v-if="palStore.SAVE_CAPABILITIES.exportSteamCopy"
            class="op"
            type="button"
            :title="palStore.getTranslatedText('TopBar_ExportSteam')"
            :disabled="palStore.LOADING_FLAG"
            @click="palStore.exportSteamCopy"
          >
            {{ palStore.getTranslatedText('TopBar_Action_Export') }}
          </button>
        </template>
        <button
          ref="settingsButton"
          :class="['op', 'op--settings', { 'op--active': settingsOpen }]"
          type="button"
          aria-haspopup="dialog"
          :aria-expanded="settingsOpen"
          aria-controls="settings-drawer"
          @click="openSettings"
        >
          <AppIcon name="settings" :size="16" />
          {{ palStore.getTranslatedText('TopBar_Settings') }}
        </button>
      </div>
    </div>

    <nav
      v-if="palStore.SAVE_LOADED_FLAG"
      class="topbar__nav"
      :aria-label="palStore.getTranslatedText('TopBar_PageNavigation')"
    >
      <button
        class="nav-item nav-item--return"
        type="button"
        :disabled="palStore.LOADING_FLAG"
        @click="returnToSaveSelection"
      >
        <AppIcon name="back" :size="15" />
        {{ palStore.getTranslatedText('TopBar_Page_Return') }}
      </button>
      <button
        :class="['nav-item', { 'nav-item--active': isOverview }]"
        type="button"
        :aria-current="isOverview ? 'page' : undefined"
        :disabled="palStore.LOADING_FLAG"
        @click="navigate('Overview')"
      >
        {{ palStore.getTranslatedText('TopBar_Page_Overview') }}
      </button>
      <button
        :class="['nav-item', { 'nav-item--active': isPalEditor }]"
        type="button"
        :aria-current="isPalEditor ? 'page' : undefined"
        :disabled="palStore.LOADING_FLAG"
        @click="navigate('Editor')"
      >
        {{ palStore.getTranslatedText('TopBar_Page_Pals') }}
      </button>
      <button
        :class="['nav-item', { 'nav-item--active': isPlayerEditor }]"
        type="button"
        :aria-current="isPlayerEditor ? 'page' : undefined"
        :disabled="palStore.LOADING_FLAG"
        @click="navigate('Players')"
      >
        {{ palStore.getTranslatedText('TopBar_Page_Players') }}
      </button>
      <button
        :class="['nav-item', { 'nav-item--active': isMap }]"
        type="button"
        :aria-current="isMap ? 'page' : undefined"
        :disabled="palStore.LOADING_FLAG"
        @click="navigate('Map')"
      >
        {{ palStore.getTranslatedText('TopBar_Page_Map') }}
      </button>
      <button
        :class="['nav-item', { 'nav-item--active': isGuilds }]"
        type="button"
        :aria-current="isGuilds ? 'page' : undefined"
        :disabled="palStore.LOADING_FLAG"
        @click="navigate('Guilds')"
      >
        {{ palStore.getTranslatedText('TopBar_Page_Guilds') }}
      </button>
      <button
        :class="['nav-item', { 'nav-item--active': isArenaLeaderboard }]"
        type="button"
        :aria-current="isArenaLeaderboard ? 'page' : undefined"
        :disabled="palStore.LOADING_FLAG"
        @click="navigate('ArenaLeaderboard')"
      >
        {{ palStore.getTranslatedText('TopBar_Page_Arena') }}
      </button>
      <button
        :class="['nav-item', { 'nav-item--active': isExpeditions }]"
        type="button"
        :aria-current="isExpeditions ? 'page' : undefined"
        :disabled="palStore.LOADING_FLAG"
        @click="navigate('Expeditions')"
      >
        {{ palStore.getTranslatedText('TopBar_Page_Expeditions') }}
      </button>
      <button
        :class="['nav-item', { 'nav-item--active': isJsonEditor }]"
        type="button"
        :aria-current="isJsonEditor ? 'page' : undefined"
        :disabled="palStore.LOADING_FLAG"
        @click="navigate('JsonEditor')"
      >
        {{ palStore.getTranslatedText('TopBar_Page_Json') }}
      </button>
    </nav>

    <div
      v-if="palStore.LAST_SAVE_RESULT?.backup_path || palStore.LAST_SAVE_RESULT?.recovery_status === 'failed'"
      class="save-evidence"
      role="status"
    >
      <span v-if="palStore.LAST_SAVE_RESULT?.backup_path">
        {{ palStore.getTranslatedText('Xgp_Backup_Path') }}: {{ palStore.LAST_SAVE_RESULT.backup_path }}
      </span>
      <span v-if="palStore.LAST_SAVE_RESULT?.recovery_status">
        {{ palStore.getTranslatedText('Xgp_Recovery_Status') }}: {{ palStore.LAST_SAVE_RESULT.recovery_status }}
      </span>
      <span v-if="palStore.SAVE_PLATFORM === 'xgp'">{{ palStore.getTranslatedText('Xgp_Cloud_Unverified') }}</span>
    </div>
  </header>

  <Teleport to="body">
    <div
      v-if="settingsOpen"
      class="settings-scrim"
      aria-hidden="true"
      @click="closeSettings"
    />
    <aside
      id="settings-drawer"
      :class="['settings-drawer', { 'settings-drawer--open': settingsOpen }]"
      role="dialog"
      aria-modal="true"
      :aria-hidden="!settingsOpen"
      :aria-labelledby="settingsOpen ? 'settings-title' : undefined"
    >
      <header class="settings-drawer__header">
        <h2 id="settings-title">{{ palStore.getTranslatedText('Settings_Title') }}</h2>
        <button
          ref="settingsCloseButton"
          class="settings-close"
          type="button"
          :aria-label="palStore.getTranslatedText('Settings_Close')"
          @click="closeSettings"
        >
          <AppIcon name="x" :size="22" />
        </button>
      </header>

      <div class="settings-drawer__body">
        <label class="settings-field settings-field--language">
          <span>{{ palStore.getTranslatedText('TopBar_Language') }}</span>
          <select
            id="languageSelect"
            v-model="palStore.I18n"
            :disabled="palStore.LOADING_FLAG"
            @change="palStore.updateI18n"
          >
            <option v-for="translated, key in palStore.I18nList" :key="key" :value="key">
              {{ translated }}
            </option>
          </select>
        </label>

        <label class="settings-field settings-field--toggle">
          <span>{{ palStore.getTranslatedText('Settings_CheatOptions') }}</span>
          <input
            v-model="palStore.HIDE_INVALID_OPTIONS"
            class="switch-input"
            type="checkbox"
            :true-value="false"
            :false-value="true"
            :disabled="palStore.LOADING_FLAG || (!palStore.SAVE_LOADED_FLAG && !palStore.REMOTE_CONNECTED)"
          />
          <span class="switch" aria-hidden="true"><i /></span>
        </label>

        <label class="settings-field settings-field--toggle">
          <span>{{ palStore.getTranslatedText('Settings_ShowOobPals') }}</span>
          <input
            v-model="palStore.SHOW_OOB_PAL_FLAG"
            class="switch-input"
            type="checkbox"
            :disabled="palStore.LOADING_FLAG || !palStore.SAVE_LOADED_FLAG"
          />
          <span class="switch" aria-hidden="true"><i /></span>
        </label>

        <label class="settings-field settings-field--toggle">
          <span>{{ palStore.getTranslatedText('Settings_SkipUpdateCheck') }}</span>
          <input
            v-model="palStore.SKIP_UPDATE_CHECK"
            class="switch-input"
            type="checkbox"
          />
          <span class="switch" aria-hidden="true"><i /></span>
        </label>
      </div>

      <footer class="settings-drawer__footer">
        {{ palStore.getTranslatedText('Common_AppName') }} {{ displayVersion }}
      </footer>
    </aside>
  </Teleport>
</template>

<style scoped>
#topbar {
  position: fixed;
  inset: 0 0 auto;
  z-index: 40;
  box-sizing: border-box;
  height: 64px;
  color: var(--ui-text);
  background: oklch(0.18 0.021 252 / 0.96);
  border-bottom: 1px solid var(--ui-border);
  box-shadow: 0 1px 0 oklch(0.5 0.03 252 / 0.1) inset, var(--ui-shadow-sm);
  backdrop-filter: blur(18px) saturate(1.2);
}

#topbar.topbar--loaded {
  height: 112px;
}

.topbar__primary {
  display: grid;
  height: 64px;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 16px;
  padding: 10px 16px;
}

.topbar__context,
.topbar__actions {
  display: flex;
  min-width: 0;
  align-items: center;
}

.topbar__context { gap: 10px; }
.topbar__actions { justify-content: flex-end; gap: 8px; }

.brand {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  gap: 9px;
  padding: 0;
  color: var(--ui-text);
  background: transparent;
  border: 0;
  font: inherit;
  font-size: 13px;
  font-weight: 680;
  letter-spacing: -0.01em;
  cursor: default;
}

.brand--clickable { cursor: pointer; }
.brand--clickable:hover span { color: var(--ui-accent); }
.brand:focus-visible { outline: 2px solid var(--ui-accent); outline-offset: 4px; border-radius: var(--ui-radius-sm); }

.brand img {
  border-radius: 8px;
  box-shadow: 0 2px 8px oklch(0.3 0.04 250 / 0.16);
}

.source-badge {
  flex: 0 0 auto;
  padding: 5px 8px;
  color: var(--ui-text-secondary);
  background: var(--ui-surface);
  border: 1px solid var(--ui-border-strong);
  border-radius: var(--ui-radius-sm);
  font-size: 10px;
  font-weight: 700;
}

.source-badge--xgp {
  color: var(--ui-accent);
  background: var(--ui-accent-soft);
  border-color: var(--ui-accent);
}

.save-location {
  flex: 1 1 260px;
  display: flex;
  min-width: 140px;
  width: min(640px, 46vw);
  max-width: 640px;
  height: 38px;
  align-items: center;
  padding: 0 11px;
  color: var(--ui-text-muted);
  background: var(--ui-surface-raised);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
}

.savePath,
.op,
#languageSelect {
  min-height: 36px;
  border-radius: var(--ui-radius-sm);
  border: 1px solid var(--ui-border);
  font: inherit;
}

.savePath {
  min-width: 0;
  width: 100%;
  padding: 0;
  overflow: hidden;
  color: var(--ui-text-secondary);
  background: transparent;
  border: 0;
  border-radius: 0;
  outline: 0;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
}

.savePath--locked { display: flex; align-items: center; }
.save-location:focus-within { border-color: var(--ui-accent); box-shadow: 0 0 0 3px oklch(0.72 0.14 246 / 0.14); }

.op {
  flex: 0 0 auto;
  display: inline-flex;
  min-width: 74px;
  align-items: center;
  justify-content: center;
  gap: 7px;
  padding: 0 14px;
  color: var(--ui-text-secondary);
  background: var(--ui-surface);
  font-size: 12px;
  font-weight: 620;
  line-height: 1.2;
  white-space: nowrap;
}

.op:hover:not(:disabled) {
  color: var(--ui-text);
  background: var(--ui-surface-hover);
  border-color: var(--ui-border-strong);
}

.op--primary {
  color: oklch(0.16 0.025 252);
  background: var(--ui-accent);
  border-color: var(--ui-accent);
}

.op--primary:hover:not(:disabled) {
  color: oklch(0.13 0.025 252);
  background: var(--ui-accent-strong);
  border-color: var(--ui-accent-strong);
}

.op--active {
  color: var(--ui-accent);
  background: var(--ui-accent-soft);
  border-color: var(--ui-accent);
}

.op:disabled,
.savePath:disabled,
#languageSelect:disabled {
  opacity: 0.46;
  cursor: not-allowed;
}

.topbar__nav {
  display: flex;
  height: 48px;
  align-items: stretch;
  gap: 2px;
  padding: 0 16px;
  overflow-x: auto;
  overflow-y: hidden;
  background: oklch(0.185 0.019 252 / 0.94);
  border-top: 1px solid oklch(0.3 0.025 252 / 0.72);
  scrollbar-width: none;
}

.topbar__nav::-webkit-scrollbar { display: none; }

.nav-item {
  position: relative;
  flex: 0 0 auto;
  min-width: 94px;
  padding: 0 18px;
  color: var(--ui-text-muted);
  background: transparent;
  border: 0;
  font: inherit;
  font-size: 12px;
  font-weight: 620;
  white-space: nowrap;
}

.nav-item--return {
  display: inline-flex;
  align-items: center;
  gap: 7px;
}

.nav-item--return::before {
  position: absolute;
  top: 13px;
  right: 0;
  bottom: 13px;
  width: 1px;
  background: var(--ui-border);
  content: "";
}

.nav-item::after {
  position: absolute;
  right: 14px;
  bottom: 0;
  left: 14px;
  height: 3px;
  background: transparent;
  border-radius: 999px 999px 0 0;
  content: "";
}

.nav-item:hover:not(:disabled) { color: var(--ui-text); background: oklch(0.24 0.024 252 / 0.68); }
.nav-item--active { color: var(--ui-accent); }
.nav-item--active::after { background: var(--ui-accent); box-shadow: 0 0 10px oklch(0.72 0.14 246 / 0.38); }
.nav-item:disabled { opacity: 0.45; cursor: not-allowed; }

.loading-bar {
  position: fixed;
  inset: 0 auto auto 0;
  z-index: 80;
  height: 2px;
  background: var(--ui-accent);
  transition: width 180ms ease-out;
}

.save-evidence {
  position: fixed;
  top: calc(var(--editor-top-offset) - 8px);
  right: 12px;
  display: grid;
  gap: 2px;
  max-width: min(620px, calc(100vw - 24px));
  padding: 8px 10px;
  overflow-wrap: anywhere;
  color: var(--ui-text-secondary);
  background: var(--ui-surface);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
  box-shadow: var(--ui-shadow-md);
  font-size: 10px;
}

.settings-scrim {
  position: fixed;
  inset: 64px 0 0;
  z-index: 60;
  background: oklch(0.08 0.015 252 / 0.52);
  backdrop-filter: blur(2px);
}

:global(body.settings-drawer-open) {
  overflow: hidden;
}

.settings-drawer {
  position: fixed;
  top: 64px;
  right: 0;
  bottom: 0;
  z-index: 70;
  display: grid;
  width: min(360px, 100vw);
  grid-template-rows: auto minmax(0, 1fr) auto;
  color: var(--ui-text);
  background: oklch(0.19 0.022 252);
  border-left: 1px solid var(--ui-border);
  box-shadow: -24px 0 60px oklch(0.04 0.02 252 / 0.36);
  opacity: 0;
  transform: translateX(100%);
  pointer-events: none;
  transition: transform 180ms ease-out, opacity 180ms ease-out;
}

.settings-drawer--open {
  opacity: 1;
  transform: translateX(0);
  pointer-events: auto;
}

.settings-drawer__header {
  display: flex;
  min-height: 68px;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px 0 28px;
  border-bottom: 1px solid var(--ui-border);
}

.settings-drawer__header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  letter-spacing: -0.025em;
}

.settings-close {
  display: inline-grid;
  width: 36px;
  height: 36px;
  place-items: center;
  padding: 0;
  color: var(--ui-text-secondary);
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--ui-radius-sm);
}

.settings-close:hover { color: var(--ui-text); background: var(--ui-surface-hover); border-color: var(--ui-border); }

.settings-drawer__body {
  min-height: 0;
  padding: 12px 28px;
  overflow-y: auto;
}

.settings-field {
  display: grid;
  color: var(--ui-text-secondary);
  font-size: 13px;
  font-weight: 600;
}

.settings-field + .settings-field {
  border-top: 1px solid var(--ui-border);
}

.settings-field--language {
  gap: 10px;
  padding: 18px 0 24px;
}

#languageSelect {
  width: 100%;
  padding: 0 34px 0 11px;
  color: var(--ui-text);
  background: var(--ui-surface);
  font-size: 12px;
}

.settings-field--toggle {
  position: relative;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  min-height: 92px;
  gap: 20px;
  cursor: pointer;
}

.switch-input {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  opacity: 0;
}

.switch {
  display: block;
  width: 44px;
  height: 24px;
  padding: 3px;
  background: oklch(0.26 0.025 252);
  border: 1px solid var(--ui-border-strong);
  border-radius: 999px;
  transition: background 150ms ease-out, border-color 150ms ease-out;
}

.switch i {
  display: block;
  width: 16px;
  height: 16px;
  background: var(--ui-text-secondary);
  border-radius: 50%;
  box-shadow: 0 1px 4px oklch(0.04 0.02 252 / 0.45);
  transition: transform 150ms ease-out, background 150ms ease-out;
}

.switch-input:checked + .switch {
  background: var(--ui-accent);
  border-color: var(--ui-accent);
}

.switch-input:checked + .switch i {
  background: white;
  transform: translateX(20px);
}

.switch-input:focus-visible + .switch {
  outline: 2px solid var(--ui-accent);
  outline-offset: 3px;
}

.switch-input:disabled + .switch {
  opacity: 0.4;
  cursor: not-allowed;
}

.settings-drawer__footer {
  margin: 0 28px;
  padding: 22px 0 24px;
  color: var(--ui-text-muted);
  border-top: 1px solid var(--ui-border);
  font-size: 11px;
}

@media (max-width: 920px) {
  .brand span { display: none; }
  .save-location { width: auto; }
}

@media (max-width: 760px) {
  #topbar.topbar--loaded { height: 132px; }

  .topbar__primary {
    height: 88px;
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: 40px 36px;
    gap: 4px;
    padding: 4px 10px 8px;
  }

  .topbar__context { gap: 7px; }
  .topbar__actions { gap: 6px; }
  .save-location { min-width: 0; max-width: none; height: 36px; }
  .op { min-width: 68px; padding-inline: 11px; }
  .topbar__nav { height: 44px; padding-inline: 8px; }
  .nav-item { min-width: 82px; padding-inline: 14px; }
  .settings-scrim { inset-block-start: 88px; }
  .settings-drawer { top: 88px; }
}

@media (max-width: 440px) {
  .source-badge { padding-inline: 6px; }
  .op { min-width: 62px; padding-inline: 9px; }
  .op--settings { min-width: 74px; }
  .settings-drawer { width: 100vw; }
}

@media (prefers-reduced-motion: reduce) {
  .op,
  .loading-bar,
  .settings-drawer,
  .switch,
  .switch i { transition: none; }
}
</style>
