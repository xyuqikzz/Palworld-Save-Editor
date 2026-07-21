import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

import axios from 'axios'
import { createPinia, setActivePinia } from 'pinia'

globalThis.alert = () => {}
globalThis.localStorage = {
  getItem: () => null,
  setItem: () => {},
}

const { usePalEditorStore } = await import('../src/stores/paleditor.js')
const releaseUrl = 'https://github.com/xyuqikzz/Palworld-Save-Editor/releases/tag/1.0.0'

function makeStore() {
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

test('the application exposes download and skip choices for an available update', () => {
  const app = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')
  const notice = readFileSync(new URL('../src/components/UpdateNotice.vue', import.meta.url), 'utf8')

  assert.match(app, /palStore\.checkForUpdate\(\)/)
  assert.match(app, /<UpdateNotice\s*\/?>/)
  assert.match(notice, /:href="palStore\.AVAILABLE_UPDATE\.url"/)
  assert.match(notice, /@click="palStore\.skipUpdate"/)
})
