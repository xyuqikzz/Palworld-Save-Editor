import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const store = readFileSync(
  fileURLToPath(new URL('../src/stores/paleditor.js', import.meta.url)),
  'utf8',
)
const entry = readFileSync(
  fileURLToPath(new URL('../src/views/EntryView.vue', import.meta.url)),
  'utf8',
)
const topbar = readFileSync(
  fileURLToPath(new URL('../src/components/TopBar.vue', import.meta.url)),
  'utf8',
)
const editor = readFileSync(
  fileURLToPath(new URL('../src/views/EditorView.vue', import.meta.url)),
  'utf8',
)

test('Game Pass discovery requires an explicit slot selection', () => {
  assert.match(store, /async function discoverXgpSources/)
  assert.match(store, /XGP_WGS_PATH/)
  assert.match(entry, /SAVE_SOURCE_MODE/)
  assert.match(entry, /show_file_picker\('xgp'\)/)
  assert.match(entry, /SELECTED_XGP_SOURCE_ID/)
  assert.doesNotMatch(store, /SELECTED_XGP_SOURCE_ID\.value\s*=\s*XGP_SOURCES\.value\[0\]/)
})

test('Game Pass discovery errors are rendered on the entry page', () => {
  assert.match(entry, /LAST_ERROR/)
  assert.match(entry, /discover-xgp-sources/)
  assert.match(entry, /role="alert"/)
})

test('Game Pass save target is locked while Steam export remains separate', () => {
  assert.match(store, /async function exportSteamCopy/)
  assert.match(store, /SAVE_PLATFORM\.value === "xgp"/)
  assert.match(topbar, /SAVE_CAPABILITIES/)
  assert.match(topbar, /exportSteamCopy/)
  assert.match(topbar, /source-badge/)
})

test('Game Pass save confirmation and recovery evidence are surfaced', () => {
  assert.match(store, /Confirm_Xgp_Save/)
  assert.match(topbar, /backup_path/)
  assert.match(topbar, /recovery_status/)
})

test('save errors surface actionable backup diagnostics without conflating network errors', () => {
  assert.match(store, /NETWORK_NO_RESPONSE/)
  assert.match(store, /Save_Backup_Failure_Action/)
  assert.match(editor, /LAST_ERROR\.action/)
  assert.match(editor, /details\?\.backup_path/)
  assert.match(editor, /details\?\.phase/)
  assert.match(editor, /details\?\.failed_file/)
  assert.match(editor, /details\?\.os_error_category/)
})

function installBrowserStubs() {
  const values = new Map()
  globalThis.localStorage = {
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: key => values.delete(key),
  }
  globalThis.window = {
    confirm: () => true,
    prompt: () => null,
  }
  globalThis.alert = () => {}
}

test('discovery clears a stale selection and does not select the first result', async () => {
  installBrowserStubs()
  const [{ createPinia, setActivePinia }, axiosModule, storeModule] = await Promise.all([
    import('pinia'),
    import('axios'),
    import('../src/stores/paleditor.js'),
  ])
  setActivePinia(createPinia())
  const palStore = storeModule.usePalEditorStore()
  palStore.SELECTED_XGP_SOURCE_ID = 'stale-source'
  const requests = []
  axiosModule.default.post = async (url, payload) => {
    requests.push({ url, payload })
    return ({
    data: {
      status: 0,
      data: {
        sources: [
          { sourceId: 'xgp-one', platform: 'xgp', displayName: 'World 1' },
          { sourceId: 'xgp-two', platform: 'xgp', displayName: 'World 2' },
        ],
      },
    },
  })}
  palStore.XGP_WGS_PATH = 'D:/chosen/wgs'

  assert.equal(await palStore.discoverXgpSources(), true)
  assert.deepEqual(requests[0], {
    url: '/api/save/sources',
    payload: { path: 'D:/chosen/wgs' },
  })
  assert.equal(palStore.XGP_SOURCES.length, 2)
  assert.equal(palStore.SELECTED_XGP_SOURCE_ID, null)
})

test('discovery treats an empty result as an invalid Game Pass folder', async () => {
  installBrowserStubs()
  const [{ createPinia, setActivePinia }, axiosModule, storeModule] = await Promise.all([
    import('pinia'),
    import('axios'),
    import('../src/stores/paleditor.js'),
  ])
  setActivePinia(createPinia())
  const palStore = storeModule.usePalEditorStore()
  axiosModule.default.post = async () => ({
    data: { status: 0, data: { sources: [] } },
  })
  palStore.XGP_WGS_PATH = 'D:/wrong-folder'

  assert.equal(await palStore.discoverXgpSources(), false)
  assert.equal(palStore.LAST_ERROR?.context, 'discover-xgp-sources')
  assert.equal(palStore.LAST_ERROR?.code, 'WGS_NOT_FOUND')
})

test('discovery surfaces the structured error returned for an invalid folder', async () => {
  installBrowserStubs()
  const [{ createPinia, setActivePinia }, axiosModule, storeModule] = await Promise.all([
    import('pinia'),
    import('axios'),
    import('../src/stores/paleditor.js'),
  ])
  setActivePinia(createPinia())
  const palStore = storeModule.usePalEditorStore()
  axiosModule.default.post = async () => {
    throw {
      response: {
        data: {
          status: 1,
          error: { code: 'WGS_NOT_FOUND', details: {}, retryable: true },
        },
      },
    }
  }
  palStore.XGP_WGS_PATH = 'D:/wrong-folder'

  assert.equal(await palStore.discoverXgpSources(), false)
  assert.equal(palStore.LAST_ERROR?.context, 'discover-xgp-sources')
  assert.equal(palStore.LAST_ERROR?.code, 'WGS_NOT_FOUND')
  assert.notEqual(palStore.LAST_ERROR?.message, 'WGS_NOT_FOUND')
})

test('writeSave omits target paths for Game Pass but preserves Steam target behavior', async () => {
  installBrowserStubs()
  const [{ createPinia, setActivePinia }, axiosModule, storeModule] = await Promise.all([
    import('pinia'),
    import('axios'),
    import('../src/stores/paleditor.js'),
  ])
  setActivePinia(createPinia())
  const palStore = storeModule.usePalEditorStore()
  const requests = []
  axiosModule.default.post = async (url, payload) => {
    requests.push({ url, payload })
    return {
      data: {
        status: 0,
        data: {
          revision: payload.expected_revision,
          backup_path: 'D:/safe-backup',
          recovery_status: 'not_needed',
        },
      },
    }
  }

  palStore.SESSION_ID = 'session'
  palStore.SESSION_REVISION = 4
  palStore.SAVE_PLATFORM = 'xgp'
  palStore.PAL_WRITE_BACK_PATH = 'D:/must-not-be-sent'
  assert.equal(await palStore.writeSave(), true)
  assert.deepEqual(requests[0], {
    url: '/api/save/save',
    payload: { session_id: 'session', expected_revision: 4 },
  })

  palStore.SAVE_PLATFORM = 'steam'
  palStore.PAL_WRITE_BACK_PATH = 'D:/steam-target'
  assert.equal(await palStore.writeSave(), true)
  assert.equal(requests[1].payload.WritePath, 'D:/steam-target')
})
