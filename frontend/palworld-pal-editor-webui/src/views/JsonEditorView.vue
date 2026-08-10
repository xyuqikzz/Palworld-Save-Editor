<script setup>
import AppIcon from '@/components/modules/AppIcon.vue'
import MonacoJsonEditor from '@/components/json-editor/MonacoJsonEditor.vue'
import { confirmMessage } from '@/services/message-dialog'
import { usePalEditorStore } from '@/stores/paleditor'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRouter } from 'vue-router'

const RISK_ACKNOWLEDGEMENT_STORAGE_KEY = 'PAL_JSON_EDITOR_RISK_ACKNOWLEDGED'

function hasAcknowledgedRisk() {
  try {
    return globalThis.localStorage?.getItem(RISK_ACKNOWLEDGEMENT_STORAGE_KEY) === 'true'
  } catch {
    return false
  }
}

function rememberRiskAcknowledgement() {
  try {
    globalThis.localStorage?.setItem(RISK_ACKNOWLEDGEMENT_STORAGE_KEY, 'true')
  } catch {
    // Keep the editor usable when persistent browser storage is unavailable.
  }
}

const palStore = usePalEditorStore()
const router = useRouter()
const acknowledged = ref(hasAcknowledgedRisk())
const riskAccepted = ref(acknowledged.value)
const files = ref([])
const selectedPath = ref('')
const search = ref('')
const text = ref('')
const baseline = ref('')
const filesLoading = ref(false)
const documentLoading = ref(false)
const loadingPath = ref('')
const failedPath = ref('')
const applying = ref(false)
const formatting = ref(false)
const loadError = ref('')
const staged = ref(false)
const cursor = ref({ line: 1, column: 1 })
const applyError = computed(() => (
  palStore.LAST_ERROR?.context === 'apply-json-document'
    ? palStore.LAST_ERROR
    : null
))
const validation = ref({ state: 'idle', message: '', line: null, column: null })
const byteSize = ref(0)
const worker = new Worker(
  new URL('../workers/jsonSyntax.worker.js', import.meta.url),
  { type: 'module' },
)
const pendingWorkerRequests = new Map()
let workerRequestId = 0
let validationTimer = null

const loading = computed(() => filesLoading.value || documentLoading.value)
const navigationLocked = computed(() => loading.value || applying.value)
const dirty = computed(() => text.value !== baseline.value)
const displayedFile = computed(() => {
  const path = loadingPath.value || failedPath.value || selectedPath.value
  return files.value.find(file => file.path === path) || null
})
const filteredFiles = computed(() => {
  const query = search.value.trim().toLocaleLowerCase()
  if (!query) return files.value
  return files.value.filter(file => (
    file.path.toLocaleLowerCase().includes(query)
    || String(file.player_name || '').toLocaleLowerCase().includes(query)
  ))
})
const worldFiles = computed(() => filteredFiles.value.filter(file => file.kind === 'level'))
const playerFiles = computed(() => filteredFiles.value.filter(file => file.kind === 'player'))

function t(key, args = []) {
  return palStore.getTranslatedText(key, args)
}

function formatBytes(value) {
  const bytes = Number(value) || 0
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function requestWorker(action, source) {
  return new Promise(resolve => {
    const id = ++workerRequestId
    pendingWorkerRequests.set(id, resolve)
    worker.postMessage({ id, action, text: source })
  })
}

worker.onmessage = event => {
  const resolve = pendingWorkerRequests.get(event.data.id)
  if (!resolve) return
  pendingWorkerRequests.delete(event.data.id)
  resolve(event.data)
}

async function validateDocument() {
  const source = text.value
  validation.value = { state: 'checking', message: '', line: null, column: null }
  const result = await requestWorker('validate', source)
  if (source !== text.value) return
  byteSize.value = new Blob([source]).size
  validation.value = result.valid
    ? { state: 'valid', message: '', line: null, column: null }
    : {
        state: 'invalid',
        message: result.message,
        line: result.line,
        column: result.column,
      }
}

function scheduleValidation() {
  clearTimeout(validationTimer)
  validationTimer = setTimeout(validateDocument, 280)
}

watch(text, scheduleValidation)

function clearDocument() {
  clearTimeout(validationTimer)
  selectedPath.value = ''
  loadingPath.value = ''
  failedPath.value = ''
  text.value = ''
  baseline.value = ''
  staged.value = false
  byteSize.value = 0
  cursor.value = { line: 1, column: 1 }
  validation.value = { state: 'idle', message: '', line: null, column: null }
}

async function loadFiles({ clearSelection = false } = {}) {
  if (filesLoading.value || documentLoading.value) return false
  filesLoading.value = true
  loadError.value = ''
  try {
    const result = await palStore.loadJsonEditorFiles()
    if (!result) {
      loadError.value = palStore.LAST_ERROR?.message || t('JsonEditor_LoadError')
      return false
    }
    files.value = result.files || []
    if (
      clearSelection
      || selectedPath.value
      && !files.value.some(file => file.path === selectedPath.value)
    ) {
      clearDocument()
    }
    return true
  } finally {
    filesLoading.value = false
  }
}

async function loadDocument(path, { skipDirtyCheck = false } = {}) {
  if (filesLoading.value || documentLoading.value || applying.value) return
  if (!path || path === selectedPath.value && text.value && !skipDirtyCheck) return
  if (
    !skipDirtyCheck
    && dirty.value
    && !await confirmMessage(t('JsonEditor_DiscardConfirm'))
  ) return

  documentLoading.value = true
  loadingPath.value = path
  failedPath.value = ''
  loadError.value = ''
  try {
    const document = await palStore.loadJsonDocument(path)
    if (document === false) {
      failedPath.value = path
      loadError.value = palStore.LAST_ERROR?.message || t('JsonEditor_LoadError')
      return
    }
    selectedPath.value = path
    text.value = document
    baseline.value = document
    staged.value = false
    cursor.value = { line: 1, column: 1 }
    await validateDocument()
  } finally {
    loadingPath.value = ''
    documentLoading.value = false
  }
}

async function openEditor() {
  if (!riskAccepted.value) return
  acknowledged.value = true
  rememberRiskAcknowledgement()
  await loadFiles({ clearSelection: true })
}

async function formatDocument() {
  if (validation.value.state !== 'valid' || formatting.value) return
  formatting.value = true
  try {
    const result = await requestWorker('format', text.value)
    if (result.valid) text.value = result.text
  } finally {
    formatting.value = false
  }
}

async function applyDocument() {
  if (
    !dirty.value
    || validation.value.state !== 'valid'
    || applying.value
  ) return
  if (!await confirmMessage(t('JsonEditor_ConfirmApply'))) return
  applying.value = true
  try {
    const result = await palStore.applyJsonDocument(selectedPath.value, text.value)
    if (!result) return
    baseline.value = text.value
    staged.value = true
  } finally {
    applying.value = false
  }
}

function returnToEditor() {
  router.push({ name: 'Editor' })
}

onBeforeRouteLeave(async () => {
  if (!dirty.value) return true
  return confirmMessage(t('JsonEditor_DiscardConfirm'))
})

const openedSessionId = ref(palStore.SESSION_ID)
watch(() => palStore.SESSION_ID, async sessionId => {
  if (!acknowledged.value || !sessionId || sessionId === openedSessionId.value) return
  openedSessionId.value = sessionId
  await loadFiles({ clearSelection: true })
})

onMounted(async () => {
  if (acknowledged.value) await loadFiles({ clearSelection: true })
})

onBeforeUnmount(() => {
  clearTimeout(validationTimer)
  worker.terminate()
  pendingWorkerRequests.clear()
})
</script>

<template>
  <main class="json-page">
    <section v-if="!acknowledged" class="risk-gate" aria-labelledby="json-risk-title">
      <div class="risk-gate__icon"><AppIcon name="warning" :size="26" /></div>
      <p class="eyebrow">{{ t('JsonEditor_DangerZone') }}</p>
      <h1 id="json-risk-title">{{ t('JsonEditor_WarningTitle') }}</h1>
      <p class="risk-gate__copy">{{ t('JsonEditor_WarningText') }}</p>
      <label class="risk-check">
        <input v-model="riskAccepted" type="checkbox" />
        <span>{{ t('JsonEditor_Acknowledge') }}</span>
      </label>
      <div class="risk-gate__actions">
        <button class="button button--ghost" type="button" @click="returnToEditor">
          {{ t('JsonEditor_Back') }}
        </button>
        <button
          class="button button--danger"
          type="button"
          :disabled="!riskAccepted"
          @click="openEditor"
        >
          {{ t('JsonEditor_Open') }}
        </button>
      </div>
    </section>

    <template v-else>
      <aside class="warning-banner" role="alert">
        <AppIcon name="warning" :size="19" />
        <div>
          <strong>{{ t('JsonEditor_WarningTitle') }}</strong>
          <p>{{ t('JsonEditor_WarningText') }}</p>
        </div>
      </aside>

      <div class="json-workspace">
        <aside
          :class="['file-panel', { 'file-panel--locked': navigationLocked }]"
          :aria-busy="navigationLocked"
        >
          <div class="file-panel__header">
            <div>
              <span class="panel-label">{{ t('JsonEditor_Files') }}</span>
              <strong>{{ files.length }}</strong>
            </div>
            <button
              class="icon-button"
              type="button"
              :title="t('JsonEditor_Reload')"
              :disabled="navigationLocked"
              @click="loadFiles()"
            >
              <AppIcon name="refresh" :size="15" />
            </button>
          </div>
          <label class="file-search">
            <AppIcon name="search" :size="14" />
            <input
              v-model="search"
              :placeholder="t('JsonEditor_Search')"
              :disabled="navigationLocked"
            />
          </label>

          <div v-if="filesLoading && !files.length" class="panel-state">
            {{ t('JsonEditor_Loading') }}
          </div>
          <div v-else-if="!files.length" class="panel-state">
            {{ t('JsonEditor_NoFiles') }}
          </div>
          <nav v-else class="file-tree" :aria-label="t('JsonEditor_Files')">
            <section v-if="worldFiles.length">
              <h2>{{ t('JsonEditor_WorldFile') }}</h2>
              <button
                v-for="file in worldFiles"
                :key="file.path"
                :class="[
                  'file-row',
                  {
                    'file-row--active': !documentLoading && selectedPath === file.path,
                    'file-row--loading': loadingPath === file.path,
                  },
                ]"
                type="button"
                :disabled="navigationLocked"
                @click="loadDocument(file.path)"
              >
                <AppIcon name="file" :size="15" />
                <span>
                  <strong>{{ file.name }}</strong>
                  <small>{{ formatBytes(file.size) }}</small>
                </span>
              </button>
            </section>
            <section>
              <h2>{{ t('JsonEditor_PlayerFiles') }}</h2>
              <p v-if="!playerFiles.length" class="file-tree__empty">
                {{ t('JsonEditor_NoPlayers') }}
              </p>
              <button
                v-for="file in playerFiles"
                :key="file.path"
                :class="[
                  'file-row',
                  {
                    'file-row--active': !documentLoading && selectedPath === file.path,
                    'file-row--loading': loadingPath === file.path,
                  },
                ]"
                type="button"
                :disabled="navigationLocked"
                @click="loadDocument(file.path)"
              >
                <AppIcon name="file" :size="15" />
                <span>
                  <strong>{{ file.player_name || file.name }}</strong>
                  <small>{{ file.name }} · {{ formatBytes(file.size) }}</small>
                </span>
              </button>
            </section>
          </nav>
        </aside>

        <section class="editor-panel">
          <header class="editor-toolbar">
            <div class="document-title">
              <AppIcon name="file" :size="16" />
              <span>
                <strong>{{ displayedFile?.path || t('JsonEditor_SelectFile') }}</strong>
                <small v-if="documentLoading">{{ t('JsonEditor_Loading') }}</small>
                <small v-else-if="dirty">{{ t('JsonEditor_Unsaved') }}</small>
                <small v-else-if="staged">{{ t('JsonEditor_Staged') }}</small>
              </span>
            </div>
            <div class="editor-actions">
              <button
                class="button button--ghost button--small"
                type="button"
                :disabled="validation.state !== 'valid' || formatting || loading"
                @click="formatDocument"
              >
                {{ formatting ? t('JsonEditor_Formatting') : t('JsonEditor_Format') }}
              </button>
              <button
                class="button button--primary button--small"
                type="button"
                :disabled="!dirty || validation.state !== 'valid' || applying || loading"
                @click="applyDocument"
              >
                {{ applying ? t('JsonEditor_Applying') : t('JsonEditor_Apply') }}
              </button>
            </div>
          </header>

          <div v-if="applyError" class="editor-error editor-error--apply" role="alert">
            <AppIcon name="warning" :size="17" />
            <span>
              <strong>{{ applyError.code }}</strong>
              {{ applyError.message }}
            </span>
            <button
              type="button"
              :aria-label="t('Common_DismissError')"
              @click="palStore.LAST_ERROR = null"
            >
              ×
            </button>
          </div>

          <div v-if="documentLoading" class="editor-loading" role="status">
            <span class="editor-loading__spinner" />
            <strong>{{ t('JsonEditor_Loading') }}</strong>
            <span>{{ displayedFile?.path }}</span>
            <div class="editor-loading__skeleton" aria-hidden="true">
              <i /><i /><i /><i /><i />
            </div>
          </div>
          <div v-else-if="loadError" class="editor-error" role="alert">
            <AppIcon name="warning" :size="17" />
            <span>{{ loadError }}</span>
            <button
              type="button"
              @click="failedPath
                ? loadDocument(failedPath, { skipDirtyCheck: true })
                : loadFiles()"
            >
              {{ t('JsonEditor_Retry') }}
            </button>
          </div>
          <div v-else-if="selectedPath" class="editor-canvas">
            <MonacoJsonEditor
              v-model="text"
              :read-only="loading || applying"
              @cursor="cursor = $event"
            />
          </div>
          <div v-else class="editor-state">{{ t('JsonEditor_SelectFile') }}</div>

          <footer class="status-bar">
            <span
              :class="[
                'syntax-status',
                `syntax-status--${documentLoading ? 'checking' : validation.state}`,
              ]"
            >
              <i />
              <template v-if="documentLoading">{{ t('JsonEditor_Loading') }}</template>
              <template v-else-if="validation.state === 'valid'">{{ t('JsonEditor_SyntaxValid') }}</template>
              <template v-else-if="validation.state === 'invalid'">
                {{ t('JsonEditor_SyntaxInvalid') }}
                <span v-if="validation.line">· {{ validation.line }}:{{ validation.column }}</span>
              </template>
              <template v-else-if="selectedPath">{{ t('JsonEditor_SyntaxChecking') }}</template>
              <template v-else>{{ t('JsonEditor_SelectFile') }}</template>
            </span>
            <span v-if="validation.state === 'invalid'" class="syntax-message" :title="validation.message">
              {{ validation.message }}
            </span>
            <span class="status-spacer" />
            <span>{{ t('JsonEditor_LineColumn', [cursor.line, cursor.column]) }}</span>
            <span>{{ t('JsonEditor_FormatName') }}</span>
            <span>{{ t('JsonEditor_Encoding') }}</span>
            <span>{{ formatBytes(byteSize) }}</span>
          </footer>
        </section>
      </div>

      <p v-if="staged" class="staged-notice" role="status">
        <AppIcon name="check" :size="16" />
        {{ t('JsonEditor_StageHint') }}
      </p>
    </template>
  </main>
</template>

<style scoped>
.json-page {
  box-sizing: border-box;
  min-height: 100dvh;
  padding: var(--editor-top-offset) 16px 18px;
  color: var(--ui-text);
  background: var(--ui-canvas);
}

.risk-gate h1 {
  margin: 3px 0 4px;
  color: var(--ui-text);
  font-size: clamp(24px, 2.2vw, 34px);
  font-weight: 720;
  letter-spacing: -0.035em;
}

.risk-gate p,
.warning-banner p {
  margin: 0;
  color: var(--ui-text-muted);
  font-size: 13px;
  line-height: 1.55;
}

.eyebrow,
.panel-label {
  color: var(--ui-accent);
  font-size: 10px;
  font-weight: 750;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.warning-banner {
  display: flex;
  align-items: flex-start;
  gap: 11px;
  max-width: 1720px;
  margin: 0 auto 12px;
  padding: 11px 14px;
  color: oklch(0.82 0.12 78);
  background: oklch(0.23 0.045 68);
  border: 1px solid oklch(0.48 0.1 72);
  border-radius: var(--ui-radius-md);
}

.warning-banner strong { display: block; margin-bottom: 2px; font-size: 12px; }
.warning-banner p { color: oklch(0.82 0.035 75); }

.json-workspace {
  display: grid;
  grid-template-columns: 248px minmax(0, 1fr);
  max-width: 1720px;
  height: max(560px, calc(100dvh - var(--editor-top-offset) - 172px));
  margin: 0 auto;
  overflow: hidden;
  background: var(--ui-surface);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-lg);
  box-shadow: var(--ui-shadow-md);
}

.file-panel {
  display: flex;
  min-width: 0;
  flex-direction: column;
  background: oklch(0.19 0.018 252);
  border-right: 1px solid var(--ui-border);
}

.file-panel--locked { cursor: progress; }

.file-panel__header,
.editor-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.file-panel__header {
  min-height: 56px;
  padding: 0 12px 0 14px;
}

.file-panel__header > div { display: flex; align-items: baseline; gap: 7px; }
.file-panel__header strong { color: var(--ui-text-muted); font-size: 11px; }

.icon-button {
  display: inline-grid;
  width: 30px;
  height: 30px;
  place-items: center;
  padding: 0;
  color: var(--ui-text-muted);
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--ui-radius-sm);
}

.icon-button:hover:not(:disabled) {
  color: var(--ui-text);
  background: var(--ui-surface-hover);
  border-color: var(--ui-border);
}

.file-search {
  display: flex;
  align-items: center;
  gap: 7px;
  height: 34px;
  margin: 0 10px 10px;
  padding: 0 9px;
  color: var(--ui-text-muted);
  background: var(--ui-surface);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
}

.file-search:focus-within {
  border-color: var(--ui-accent);
  box-shadow: 0 0 0 3px oklch(0.72 0.14 246 / 0.14);
}

.file-search input {
  min-width: 0;
  width: 100%;
  color: var(--ui-text);
  background: transparent;
  border: 0;
  outline: 0;
  font: inherit;
  font-size: 12px;
}

.file-search input:disabled { cursor: progress; }

.file-tree {
  min-height: 0;
  padding: 2px 7px 16px;
  overflow: auto;
}

.file-tree section + section { margin-top: 14px; }
.file-tree h2 {
  margin: 0 7px 6px;
  color: var(--ui-text-muted);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.file-row {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  width: 100%;
  padding: 9px;
  color: var(--ui-text-secondary);
  text-align: left;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--ui-radius-sm);
}

.file-row + .file-row { margin-top: 2px; }
.file-row > svg { margin-top: 2px; }
.file-row > span { min-width: 0; display: grid; gap: 2px; }
.file-row strong,
.file-row small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-row strong { font-size: 12px; font-weight: 600; }
.file-row small { color: var(--ui-text-muted); font-size: 10px; }
.file-row:hover:not(:disabled) { color: var(--ui-text); background: var(--ui-surface-hover); }
.file-row:disabled { cursor: progress; opacity: 0.55; }
.file-row--active {
  color: var(--ui-accent);
  background: var(--ui-accent-soft);
  border-color: oklch(0.5 0.1 246);
}
.file-row--loading {
  color: var(--ui-accent);
  background: oklch(0.24 0.045 246);
  border-color: oklch(0.5 0.1 246);
  opacity: 1 !important;
}

.file-tree__empty,
.panel-state {
  padding: 18px 12px;
  color: var(--ui-text-muted);
  font-size: 11px;
  line-height: 1.5;
}

.editor-panel {
  display: grid;
  min-width: 0;
  min-height: 0;
  grid-template-rows: auto minmax(0, 1fr) auto;
}

.editor-toolbar {
  min-height: 56px;
  gap: 16px;
  padding: 9px 11px 9px 14px;
  background: var(--ui-surface);
  border-bottom: 1px solid var(--ui-border);
}

.document-title {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 9px;
  color: var(--ui-text-secondary);
}

.document-title > span { min-width: 0; display: grid; gap: 1px; }
.document-title strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; }
.document-title small { color: oklch(0.82 0.12 78); font-size: 10px; }
.editor-actions { display: flex; align-items: center; gap: 7px; }

.editor-canvas { min-width: 0; min-height: 0; overflow: hidden; }
.editor-state {
  display: grid;
  place-items: center;
  color: var(--ui-text-muted);
  background: oklch(0.18 0.016 252);
  font-size: 12px;
}

.editor-loading {
  display: grid;
  min-width: 0;
  min-height: 0;
  place-content: center;
  justify-items: center;
  gap: 8px;
  padding: 32px;
  color: var(--ui-text-muted);
  background: oklch(0.18 0.016 252);
  font-size: 11px;
}

.editor-loading strong {
  color: var(--ui-text-secondary);
  font-size: 13px;
  font-weight: 650;
}

.editor-loading__spinner {
  width: 30px;
  height: 30px;
  margin-bottom: 4px;
  border: 3px solid oklch(0.32 0.025 252);
  border-top-color: var(--ui-accent);
  border-radius: 50%;
  animation: json-loading-spin 720ms linear infinite;
}

.editor-loading__skeleton {
  display: grid;
  width: min(460px, 48vw);
  gap: 7px;
  margin-top: 18px;
}

.editor-loading__skeleton i {
  height: 7px;
  background: linear-gradient(
    90deg,
    oklch(0.24 0.02 252) 0%,
    oklch(0.31 0.035 246) 50%,
    oklch(0.24 0.02 252) 100%
  );
  background-size: 220% 100%;
  border-radius: 999px;
  animation: json-loading-shimmer 1.2s ease-in-out infinite;
}

.editor-loading__skeleton i:nth-child(2) { width: 86%; }
.editor-loading__skeleton i:nth-child(3) { width: 94%; }
.editor-loading__skeleton i:nth-child(4) { width: 72%; }
.editor-loading__skeleton i:nth-child(5) { width: 82%; }

.editor-error {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  padding: 18px;
  color: oklch(0.8 0.11 24);
  background: var(--ui-danger-soft);
}

.editor-error button {
  color: inherit;
  background: transparent;
  border: 0;
  text-decoration: underline;
}

.editor-error--apply {
  justify-content: flex-start;
  padding: 9px 12px;
  border-bottom: 1px solid oklch(0.45 0.08 24);
  font-size: 11px;
}

.editor-error--apply span { flex: 1; }
.editor-error--apply strong { margin-right: 6px; }
.editor-error--apply button { font-size: 18px; text-decoration: none; }

.status-bar {
  display: flex;
  min-width: 0;
  min-height: 30px;
  align-items: center;
  gap: 13px;
  padding: 0 12px;
  color: var(--ui-text-muted);
  background: oklch(0.18 0.017 252);
  border-top: 1px solid var(--ui-border);
  font-size: 10px;
}

.syntax-status { display: inline-flex; align-items: center; gap: 6px; }
.syntax-status i { width: 7px; height: 7px; background: var(--ui-text-muted); border-radius: 50%; }
.syntax-status--valid { color: var(--ui-success); }
.syntax-status--valid i { background: var(--ui-success); }
.syntax-status--invalid { color: var(--ui-danger); }
.syntax-status--invalid i { background: var(--ui-danger); }
.syntax-status--checking { color: var(--ui-accent); }
.syntax-status--checking i { background: var(--ui-accent); }
.syntax-message { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--ui-danger); }
.status-spacer { flex: 1; }

.button {
  display: inline-flex;
  min-height: 36px;
  align-items: center;
  justify-content: center;
  gap: 7px;
  padding: 0 12px;
  color: var(--ui-text-secondary);
  background: var(--ui-surface);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
  font: inherit;
  font-size: 12px;
  font-weight: 650;
}

.button:hover:not(:disabled) {
  color: var(--ui-text);
  background: var(--ui-surface-hover);
  border-color: var(--ui-border-strong);
}

.button--small { min-height: 34px; }
.button--primary { color: oklch(0.16 0.025 252); background: var(--ui-accent); border-color: var(--ui-accent); }
.button--primary:hover:not(:disabled) { color: oklch(0.13 0.025 252); background: var(--ui-accent-strong); border-color: var(--ui-accent-strong); }
.button--danger { color: white; background: var(--ui-danger); border-color: var(--ui-danger); }
.button:disabled,
.icon-button:disabled { opacity: 0.45; cursor: not-allowed; }

.risk-gate {
  box-sizing: border-box;
  max-width: 670px;
  margin: max(56px, 8vh) auto 0;
  padding: 34px;
  background: var(--ui-surface);
  border: 1px solid var(--ui-border);
  border-top: 3px solid oklch(0.62 0.14 70);
  border-radius: var(--ui-radius-lg);
  box-shadow: var(--ui-shadow-md);
}

.risk-gate__icon {
  display: grid;
  width: 48px;
  height: 48px;
  margin-bottom: 20px;
  place-items: center;
  color: oklch(0.82 0.12 78);
  background: oklch(0.25 0.05 68);
  border: 1px solid oklch(0.48 0.1 72);
  border-radius: 50%;
}

.risk-gate__copy { max-width: 58ch; margin-top: 13px !important; }
.risk-check {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-top: 24px;
  padding: 13px;
  color: var(--ui-text-secondary);
  background: oklch(0.19 0.018 252);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
  font-size: 12px;
  line-height: 1.5;
}

.risk-check input { margin-top: 2px; accent-color: var(--ui-accent); }
.risk-gate__actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 20px; }
.staged-notice {
  display: flex;
  max-width: 1720px;
  align-items: center;
  gap: 8px;
  margin: 10px auto 0;
  color: var(--ui-success);
  font-size: 11px;
}

@keyframes json-loading-spin {
  to { transform: rotate(360deg); }
}

@keyframes json-loading-shimmer {
  0% { background-position: 100% 0; }
  100% { background-position: -120% 0; }
}

@media (max-width: 920px) {
  .json-workspace {
    grid-template-columns: 190px minmax(0, 1fr);
  }
  .editor-toolbar { align-items: flex-start; flex-direction: column; }
  .editor-actions { width: 100%; overflow-x: auto; }
}

@media (max-width: 680px) {
  .json-page { padding-inline: 10px; }
  .json-workspace {
    height: auto;
    grid-template-columns: 1fr;
  }
  .file-panel { max-height: 220px; border-right: 0; border-bottom: 1px solid var(--ui-border); }
  .editor-panel { height: 620px; }
  .status-bar span:nth-last-child(-n + 3) { display: none; }
  .risk-gate { padding: 24px; }
}

@media (prefers-reduced-motion: reduce) {
  .editor-loading__spinner,
  .editor-loading__skeleton i { animation: none; }
}
</style>
