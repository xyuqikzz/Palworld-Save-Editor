import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { fileURLToPath } from 'node:url'
import axios from 'axios'
import { createPinia, setActivePinia } from 'pinia'

globalThis.alert = () => {}
globalThis.window = { confirm: () => true }
globalThis.localStorage = {
  getItem: () => null,
  setItem: () => {},
  removeItem: () => {},
}

const { usePalEditorStore } = await import('../src/stores/paleditor.js')

const sourcePath = relativePath => fileURLToPath(
  new URL(`../src/${relativePath}`, import.meta.url),
)

const routerSource = readFileSync(sourcePath('router/index.js'), 'utf8')
const appSource = readFileSync(sourcePath('App.vue'), 'utf8')
const storeSource = readFileSync(sourcePath('stores/paleditor.js'), 'utf8')
const editorViewSource = readFileSync(sourcePath('views/EditorView.vue'), 'utf8')
const playerEditorSource = readFileSync(sourcePath('components/PlayerEditor.vue'), 'utf8')
const playerListSource = readFileSync(sourcePath('components/PlayerList.vue'), 'utf8')

test('refresh-safe routes use hash history and address every editor target', () => {
  assert.match(routerSource, /createWebHashHistory/)
  assert.match(routerSource, /path:\s*['"]\/editor['"]/)
  assert.match(routerSource, /path:\s*['"]\/editor\/player\/:playerId['"]/)
  assert.match(routerSource, /path:\s*['"]\/editor\/player\/:playerId\/pal\/:palId['"]/)
  assert.match(routerSource, /path:\s*['"]\/editor\/base\/:baseKey\/pal\/:palId['"]/)
})

test('authenticated startup resumes the backend session before rendering its route', () => {
  assert.match(storeSource, /async function resumeCurrentSession\(\)/)
  assert.match(storeSource, /GET\(["']\/api\/save\/session["']\)/)
  assert.match(appSource, /<RouterView/)
  assert.match(appSource, /resumeCurrentSession\(\)/)
  assert.match(appSource, /BOOTSTRAPPING/)
})

test('editor selection and player subtab are synchronized with the current route', () => {
  assert.match(editorViewSource, /useRoute\(\)/)
  assert.match(editorViewSource, /useRouter\(\)/)
  assert.match(editorViewSource, /SELECTED_PAL_ID/)
  assert.match(editorViewSource, /SELECTED_BASE_KEY/)
  assert.match(playerEditorSource, /route\.query\.tab/)
  assert.match(playerEditorSource, /router\.replace/)
})

test('a player click is not reapplied when its state change synchronizes the route', () => {
  assert.match(playerListSource, /@click="palStore\.selectPlayer\(member\.player_id\)"/)
  assert.match(editorViewSource, /await palStore\.selectPlayer\(playerId, false, false\)/)
  assert.match(editorViewSource, /stateSyncedRoutePath/)
  assert.match(editorViewSource, /consumeStateSyncedRoute\(route\.fullPath\)/)
})

test('refresh rehydrates the current Steam and WGS sessions from the backend', async () => {
  for (const session of [
    {
      platform: 'steam',
      source: 'D:/Pal/SaveA',
      sourceId: 'steam-source',
      sourceDisplayName: 'SaveA',
      saveCapabilities: { targetPathEditable: true },
    },
    {
      platform: 'xgp',
      source: 'Xbox World',
      sourceId: 'xgp-source',
      sourceDisplayName: 'Xbox World',
      saveCapabilities: { targetPathEditable: false },
    },
  ]) {
    setActivePinia(createPinia())
    const store = usePalEditorStore()
    store.IS_LOCKED = false
    const calls = []
    axios.get = async url => {
      calls.push(url)
      if (url === '/api/save/session') {
        return { data: { status: 0, data: {
          session: {
            session_id: `session-${session.platform}`,
            revision: 3,
            pending_change_count: 2,
            ...session,
          },
          compatibility: { compatible: true },
        } } }
      }
      if (url.startsWith('/api/save/query/players?')) {
        return { data: { status: 0, data: {
          players: [{ player_id: 'player-1', name: 'Player', level: 10 }],
          guilds: [],
          has_working_pal: false,
        } } }
      }
      if (url === '/api/save/tech_data') {
        return { data: { status: 0, data: { techLvDict: {} } } }
      }
      return { data: { status: 0, data: { dict: {}, arr: [] } } }
    }

    const resumed = await store.resumeCurrentSession()

    assert.equal(resumed, true, session.platform)
    assert.equal(calls[0], '/api/save/session')
    assert.equal(store.SAVE_LOADED_FLAG, true)
    assert.equal(store.SESSION_ID, `session-${session.platform}`)
    assert.equal(store.SESSION_REVISION, 3)
    assert.equal(store.PENDING_CHANGE_COUNT, 2)
    assert.equal(store.SAVE_SOURCE_MODE, session.platform)
    assert.equal(store.PLAYER_MAP.has('player-1'), true)
    if (session.platform === 'steam') {
      assert.equal(store.PAL_WRITE_BACK_PATH, session.source)
    } else {
      assert.equal(store.SELECTED_XGP_SOURCE_ID, session.sourceId)
      assert.equal(store.PAL_WRITE_BACK_PATH, session.sourceDisplayName)
    }
  }
})
