import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

import axios from 'axios'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'

globalThis.alert = () => {}
const storage = new Map()
globalThis.localStorage = {
  getItem: key => storage.get(key) ?? null,
  setItem: (key, value) => storage.set(key, String(value)),
}

const { usePalEditorStore } = await import('../src/stores/paleditor.js')
const releaseUrl = 'https://github.com/xyuqikzz/Palworld-Save-Editor/releases/tag/1.0.0'

function makeStore({ skipUpdateCheck = false } = {}) {
  storage.clear()
  if (skipUpdateCheck) storage.set('PAL_SKIP_UPDATE_CHECK', 'true')
  setActivePinia(createPinia())
  const store = usePalEditorStore()
  store.VERSION = '0.9.0-RELEASE-local-test'
  store.IS_OFFICIAL_BUILD = true
  return store
}

function mockAvailableUpdate() {
  axios.get = async url => {
    assert.equal(url, '/api/save/update')
    return {
      data: {
        status: 0,
        data: {
          version: '1.0.0',
          download_page: releaseUrl,
        },
      },
    }
  }
}

test('a newer public GitHub release is offered to official builds', async () => {
  const store = makeStore()
  mockAvailableUpdate()
  globalThis.fetch = async () => {
    throw new Error('the browser must not call the rate-limited GitHub REST API')
  }

  assert.equal(await store.checkForUpdate(), true)
  assert.deepEqual(store.AVAILABLE_UPDATE, {
    version: '1.0.0',
    url: releaseUrl,
  })
})

test('the offered update can be skipped without blocking the application', async () => {
  const store = makeStore()
  mockAvailableUpdate()
  await store.checkForUpdate()

  store.skipUpdate()

  assert.equal(store.AVAILABLE_UPDATE, null)
})

test('update checks are enabled by default and can be persistently disabled', async () => {
  const store = makeStore()
  assert.equal(store.SKIP_UPDATE_CHECK, false)

  store.AVAILABLE_UPDATE = { version: '1.0.0', url: releaseUrl }
  store.SKIP_UPDATE_CHECK = true
  await nextTick()

  assert.equal(storage.get('PAL_SKIP_UPDATE_CHECK'), 'true')
  assert.equal(store.AVAILABLE_UPDATE, null)
})

test('a persisted skip preference prevents update requests', async () => {
  const store = makeStore({ skipUpdateCheck: true })
  let requestCount = 0
  axios.get = async () => {
    requestCount += 1
    throw new Error('update endpoint must not be called')
  }

  assert.equal(await store.checkForUpdate(), false)
  assert.equal(requestCount, 0)
})

test('the application exposes download and skip choices for an available update', () => {
  const app = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')
  const notice = readFileSync(new URL('../src/components/UpdateNotice.vue', import.meta.url), 'utf8')

  assert.match(app, /if \(!palStore\.SKIP_UPDATE_CHECK\) palStore\.checkForUpdate\(\)/)
  assert.match(app, /<UpdateNotice\s*\/?>/)
  assert.match(notice, /:href="palStore\.AVAILABLE_UPDATE\.url"/)
  assert.match(notice, /@click="palStore\.skipUpdate"/)
})
