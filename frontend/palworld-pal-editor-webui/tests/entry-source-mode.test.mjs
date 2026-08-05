import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import axios from 'axios'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'

globalThis.alert = () => {}
globalThis.window = { confirm: () => true }

const { usePalEditorStore } = await import('../src/stores/paleditor.js')

function installStorage(initialValues = {}) {
  const values = new Map(Object.entries(initialValues))
  globalThis.localStorage = {
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: key => values.delete(key),
  }
  return values
}

test('first launch defaults to offline Steam editing and records the platform', () => {
  const values = installStorage()
  setActivePinia(createPinia())

  const store = usePalEditorStore()

  assert.equal(store.SAVE_SOURCE_MODE, 'steam')
  assert.equal(values.get('PAL_SAVE_SOURCE_MODE'), 'steam')
})

test('entry page separates editing mode from the offline platform switch and keeps migration in the left tabs', async () => {
  const source = await readFile(
    new URL('../src/views/EntryView.vue', import.meta.url),
    'utf8',
  )

  assert.match(source, /Entry_Source_Offline/)
  assert.match(source, /Entry_Source_Online/)
  assert.match(source, /entryEditMode === 'offline'/)
  assert.match(source, /class="offline-platform-switch"/)
  assert.match(source, /selectOfflineSourceMode\('steam'\)/)
  assert.match(source, /selectOfflineSourceMode\('xgp'\)/)
  assert.match(source, /@\/assets\/steam\.svg/)
  assert.match(source, /@\/assets\/xbox\.svg/)
  assert.match(
    source,
    /value="migration"[\s\S]*Migration_Entry[\s\S]*Entry_Source_Beta/,
  )

  const safetyFooter = source.match(/<footer class="entry-safety">([\s\S]*?)<\/footer>/)?.[1]
  assert.ok(safetyFooter)
  assert.doesNotMatch(safetyFooter, /Migration_Entry/)

  const zhCn = await readFile(
    new URL('../src/i18n/zh-CN.js', import.meta.url),
    'utf8',
  )
  assert.match(zhCn, /Entry_Platform_Xgp:\s*"Game Pass"/)
})

test('later launches restore the previously selected source', async () => {
  const values = installStorage({ PAL_SAVE_SOURCE_MODE: 'xgp' })
  setActivePinia(createPinia())

  const store = usePalEditorStore()

  assert.equal(store.SAVE_SOURCE_MODE, 'xgp')
  store.SAVE_SOURCE_MODE = 'steam'
  await nextTick()
  assert.equal(values.get('PAL_SAVE_SOURCE_MODE'), 'steam')
})

test('later launches can restore the remote server source', () => {
  installStorage({ PAL_SAVE_SOURCE_MODE: 'remote' })
  setActivePinia(createPinia())

  const store = usePalEditorStore()

  assert.equal(store.SAVE_SOURCE_MODE, 'remote')
})

test('Game Pass picker can select containers.index directly', async () => {
  const [storeSource, pickerSource] = await Promise.all([
    readFile(new URL('../src/stores/paleditor.js', import.meta.url), 'utf8'),
    readFile(new URL('../src/components/PathPicker.vue', import.meta.url), 'utf8'),
  ])

  assert.match(storeSource, /select_xgp_source/)
  assert.match(pickerSource, /filename\.toLowerCase\(\) === 'containers\.index'/)
  assert.match(
    pickerSource,
    /XGP_WGS_PATH = palStore\.PAL_FILE_PICKER_SELECTION[\s\S]*?PAL_FILE_PICKER_PATH/,
  )
})

test('remote login saves the password by default without exposing it to local storage', async () => {
  const values = installStorage()
  setActivePinia(createPinia())
  axios.post = async (url, payload) => {
    assert.equal(url, '/api/remote/connect')
    assert.equal(payload.admin_password, 'server-secret')
    assert.equal(payload.remember_credential, true)
    assert.equal('certificate_fingerprint' in payload, false)
    assert.equal('allow_insecure_local' in payload, false)
    return { data: { status: 0, data: {
      ready: true,
      gameReady: true,
      runtimeCommandsReady: false,
      session: {
        session_id: 'remote-session',
        revision: 0,
        server: { name: 'Test server', game_version: 'test' },
        capabilities: ['server.status'],
      },
    } } }
  }

  const store = usePalEditorStore()
  store.REMOTE_SERVER_ADDRESS = 'http://127.0.0.1:8213'
  const connected = await store.connectRemote({
    adminPassword: 'server-secret',
  })

  assert.equal(connected, true)
  assert.equal(store.REMOTE_CONNECTED, true)
  assert.equal(store.REMOTE_SERVER.name, 'Test server')
  assert.equal(values.get('PAL_REMOTE_SERVER_ADDRESS'), 'http://127.0.0.1:8213')
  assert.equal([...values.values()].includes('server-secret'), false)
})

test('local game connection uses automatic discovery without a password', async () => {
  const values = installStorage()
  setActivePinia(createPinia())
  axios.post = async (url, payload) => {
    assert.equal(url, '/api/remote/connect-local')
    assert.deepEqual(payload, {})
    return { data: { status: 0, data: {
      ready: true,
      authoritative: true,
      instanceMode: 'listen_server',
      session: {
        session_id: 'local-session',
        revision: 0,
        server: { name: 'Palworld Local Game', instance_kind: 'local_game' },
        capabilities: ['server.status', 'player.list'],
      },
    } } }
  }
  axios.get = async url => {
    assert.match(url, /^\/api\/remote\/players\?session_id=/)
    return { data: { status: 0, data: {
      revision: 0,
      players: [],
    } } }
  }

  const store = usePalEditorStore()
  const connected = await store.connectLocalGame()

  assert.equal(connected, true)
  assert.equal(store.REMOTE_CONNECTED, true)
  assert.equal(store.REMOTE_STATUS.instanceMode, 'listen_server')
  assert.equal([...values.values()].includes('local-secret'), false)
})

test('successful remote connection leaves the entry page for the remote workspace', async () => {
  const [entrySource, routerSource, remoteSource] = await Promise.all([
    readFile(new URL('../src/views/EntryView.vue', import.meta.url), 'utf8'),
    readFile(new URL('../src/router/index.js', import.meta.url), 'utf8'),
    readFile(new URL('../src/views/RemoteServerView.vue', import.meta.url), 'utf8'),
  ])

  assert.match(entrySource, /await router\.push\(\{ name: 'RemoteServer' \}\)/)
  assert.doesNotMatch(
    entrySource,
    /Remote_CertificateFingerprint|Remote_AllowInsecureLocal|Remote_RememberCredential/,
  )
  assert.match(routerSource, /path: '\/remote'/)
  assert.match(routerSource, /requiresRemoteSession: true/)
  assert.match(remoteSource, /executeRemoteCommand/)
  assert.match(remoteSource, /disconnectRemote/)
})

test('first launch fills the Steam world detected by the backend', async () => {
  installStorage()
  setActivePinia(createPinia())
  axios.get = async url => {
    assert.equal(url, '/api/save/fetch_config')
    return { data: { status: 0, data: {
      I18n: 'en',
      I18nList: { en: 'English' },
      Path: 'C:\\Users\\Player\\AppData\\Local\\Pal\\Saved\\SaveGames\\123\\WORLD',
      HasPassword: false,
      VERSION: 'test',
      IsOfficialBuild: false,
      MaxSoulsLevel: 60,
      MaxSuitabilityLevel: 10,
    } } }
  }

  const store = usePalEditorStore()
  await store.fetch_config()

  assert.equal(
    store.PAL_GAME_SAVE_PATH,
    'C:\\Users\\Player\\AppData\\Local\\Pal\\Saved\\SaveGames\\123\\WORLD',
  )
})
