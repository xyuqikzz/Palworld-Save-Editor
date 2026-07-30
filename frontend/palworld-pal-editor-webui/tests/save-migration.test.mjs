import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

import axios from 'axios'
import { createPinia, setActivePinia } from 'pinia'

globalThis.alert = () => {}
globalThis.localStorage = {
  getItem: () => null,
  setItem: () => {},
  removeItem: () => {},
}
globalThis.window = {
  confirm: () => true,
  prompt: () => null,
}

const { usePalEditorStore } = await import('../src/stores/paleditor.js')
const view = readFileSync(
  fileURLToPath(new URL('../src/views/SaveMigrationView.vue', import.meta.url)),
  'utf8',
)
const router = readFileSync(
  fileURLToPath(new URL('../src/router/index.js', import.meta.url)),
  'utf8',
)
const storeSource = readFileSync(
  fileURLToPath(new URL('../src/stores/paleditor.js', import.meta.url)),
  'utf8',
)

test('migration UI keeps execution behind blockers and duplicate mappings', () => {
  assert.match(router, /path:\s*['"]\/save-migration['"]/)
  assert.match(view, /plan\.value\.blockers/)
  assert.match(view, /hasDuplicateTargets/)
  assert.doesNotMatch(view, /confirmationsReady/)
  assert.doesNotMatch(view, /target_backup_acknowledged/)
  assert.match(view, /Migration_RuntimeStillRequired/)
  assert.match(view, /Migration_WgsTargetBlocked/)
  assert.match(view, /pickMigrationWgsDirectory/)
  assert.match(view, /Migration_CurrentStage/)
  assert.match(view, /plan\.migration_scope/)
  assert.match(view, /result\.migrated_players/)
  assert.match(view, /result\.written_files/)
  assert.match(view, /player_access_validated/)
  assert.doesNotMatch(view, /preserve_unmapped_source_players/)
  assert.doesNotMatch(view, /identity_binding_complete/)
  assert.match(view, /operation_id:\s*crypto\.randomUUID\(\)/)
  assert.match(storeSource, /\/api\/migration\/status/)
  assert.match(storeSource, /clearMigrationAnalysis/)
})

test('migration page keeps its header below fixed desktop and mobile top bars', () => {
  assert.match(view, /migration-page--loaded/)
  assert.match(view, /padding:\s*96px clamp\(16px,\s*3vw,\s*36px\) 80px/)
  assert.match(view, /\.migration-page--loaded\s*\{\s*padding-top:\s*calc\(var\(--editor-top-offset\) \+ 24px\)/)
  assert.match(view, /@media \(max-width:\s*760px\)[\s\S]*?\.migration-page\s*\{\s*padding:\s*112px 14px 48px/)
  assert.match(view, /\.migration-page--loaded\s*\{\s*padding-top:\s*calc\(var\(--editor-top-offset\) \+ 18px\)/)
})

test('migration store sends analysis and idempotent execution contracts', async () => {
  setActivePinia(createPinia())
  const store = usePalEditorStore()
  const requests = []
  axios.post = async (url, payload) => {
    requests.push({ url, payload })
    if (url === '/api/migration/analyze') {
      return {
        data: {
          status: 0,
          data: {
            plan_id: 'plan',
            blockers: [],
            player_candidates: [],
          },
        },
      }
    }
    return {
      data: {
        status: 0,
        data: {
          status: 'completed',
          backup_path: 'D:/backup',
          manifest_path: 'D:/backup/manifest.json',
          written_files: [],
          validation: { level: 'OFFLINE_VALIDATED' },
        },
      },
    }
  }

  const analyzePayload = {
    mode: 'character_only',
    source: { platform: 'steam', path: 'D:/source' },
    target: { platform: 'steam', path: 'D:/target' },
  }
  const analyzed = await store.analyzeMigration(analyzePayload)
  assert.equal(analyzed.plan_id, 'plan')
  assert.equal(store.MIGRATION_PLAN.plan_id, 'plan')
  assert.deepEqual(requests[0], {
    url: '/api/migration/analyze',
    payload: analyzePayload,
  })

  const executePayload = {
    plan_id: 'plan',
    mappings: [],
    operation_id: 'operation',
  }
  const result = await store.executeMigration(executePayload)
  assert.equal(result.status, 'completed')
  assert.deepEqual(requests[1], {
    url: '/api/migration/execute',
    payload: executePayload,
  })
  assert.equal(store.MIGRATION_STAGE, 'completed')
  assert.equal(store.MIGRATION_RESULT.validation.level, 'OFFLINE_VALIDATED')
})

test('migration directory selection prefers desktop and backend native APIs before prompt', async () => {
  setActivePinia(createPinia())
  const store = usePalEditorStore()
  const nativeCalls = []
  const backendCalls = []
  const promptCalls = []
  let backendResponse = {
    status: 0,
    data: {
      path: 'D:/BackendNativeSave',
      cancelled: false,
    },
  }
  axios.post = async (url, payload) => {
    backendCalls.push({ url, payload })
    return { data: backendResponse }
  }
  window.prompt = (...args) => {
    promptCalls.push(args)
    return 'D:/PromptSave'
  }
  window.pywebview = {
    api: {
      select_save_directory: async (initial) => {
        nativeCalls.push(initial)
        return 'D:/NativeSave'
      },
    },
  }

  assert.equal(await store.pickMigrationPath('D:/Initial'), 'D:/NativeSave')
  assert.deepEqual(nativeCalls, ['D:/Initial'])
  assert.equal(backendCalls.length, 0)
  assert.equal(promptCalls.length, 0)

  window.pywebview.api.select_save_directory = async () => {
    throw new Error('native unavailable')
  }
  assert.equal(await store.pickMigrationPath('D:/Initial'), 'D:/BackendNativeSave')
  assert.deepEqual(backendCalls[0], {
    url: '/api/save/select-directory',
    payload: { path: 'D:/Initial' },
  })
  assert.equal(promptCalls.length, 0)

  window.pywebview.api.select_save_directory = async () => undefined
  assert.equal(await store.pickMigrationPath('D:/Initial'), 'D:/BackendNativeSave')
  assert.equal(backendCalls.length, 2)
  assert.equal(promptCalls.length, 0)

  window.pywebview.api.select_save_directory = async () => null
  assert.equal(await store.pickMigrationPath('D:/Initial'), null)
  assert.equal(backendCalls.length, 2)
  assert.equal(promptCalls.length, 0)

  delete window.pywebview
  assert.equal(await store.pickMigrationPath('D:/Initial'), 'D:/BackendNativeSave')
  assert.equal(backendCalls.length, 3)
  assert.equal(promptCalls.length, 0)

  backendResponse = {
    status: 1,
    error: { code: 'NATIVE_DIALOG_UNAVAILABLE' },
  }
  assert.equal(await store.pickMigrationPath('D:/Initial'), 'D:/PromptSave')
  assert.equal(promptCalls.length, 1)

  backendResponse = {
    status: 0,
    data: {
      path: null,
      cancelled: true,
    },
  }
  assert.equal(await store.pickMigrationPath('D:/Initial'), null)
  assert.equal(promptCalls.length, 1)
})
