import assert from 'node:assert/strict'
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

test('first launch defaults to Steam and records the selection', () => {
  const values = installStorage()
  setActivePinia(createPinia())

  const store = usePalEditorStore()

  assert.equal(store.SAVE_SOURCE_MODE, 'steam')
  assert.equal(values.get('PAL_SAVE_SOURCE_MODE'), 'steam')
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
