import test from 'node:test'
import assert from 'node:assert/strict'

import axios from 'axios'
import { createPinia, setActivePinia } from 'pinia'

globalThis.alert = () => {}
globalThis.window = { confirm: () => true }
globalThis.localStorage = {
  getItem: () => null,
  setItem: () => {},
}

const { usePalEditorStore } = await import('../src/stores/paleditor.js')

test('language switching refreshes loaded inventory and the current item catalog search', async () => {
  setActivePinia(createPinia())
  const store = usePalEditorStore()
  const playerId = 'player-1'
  const player = {
    InstanceId: playerId,
    pals: new Map(),
    InventoryContainers: [{
      container_type: 'EQUIPMENT',
      slots: [{
        slot_index: 0,
        state: 'occupied',
        item: { static_id: 'Shield_Ultra', name: 'Ultra Shield' },
      }],
    }],
  }
  store.SESSION_ID = 'session-1'
  store.SELECTED_PLAYER_ID = playerId
  store.SELECTED_PLAYER_DATA = player
  store.PLAYER_MAP = new Map([[playerId, player]])
  store.SAVE_LOADED_FLAG = true
  store.IS_LOCKED = false
  store.I18n = 'en'

  let backendLocale = 'en'
  const catalogRequests = []
  axios.patch = async (url, data) => {
    assert.equal(url, '/api/save/i18n')
    backendLocale = data.I18n
    return { data: { status: 0 } }
  }
  axios.post = async url => {
    if (url === '/api/player/player_pals') {
      return { data: { status: 0, data: [] } }
    }
    throw new Error(`unexpected POST ${url}`)
  }
  axios.get = async url => {
    if (url.startsWith('/api/player/item_catalog?')) {
      catalogRequests.push(url)
      return {
        data: {
          status: 0,
          data: {
            items: [{
              static_id: 'Shield_Ultra',
              name: backendLocale === 'zh-CN' ? '超级护盾' : 'Ultra Shield',
            }],
          },
        },
      }
    }
    if (url.startsWith(`/api/player/${playerId}/inventory?`)) {
      return {
        data: {
          status: 0,
          data: {
            containers: [{
              container_type: 'EQUIPMENT',
              slots: [{
                slot_index: 0,
                state: 'occupied',
                item: {
                  static_id: 'Shield_Ultra',
                  name: backendLocale === 'zh-CN' ? '超级护盾' : 'Ultra Shield',
                },
              }],
            }],
          },
        },
      }
    }
    if (url === '/api/save/passive_skills') {
      return { data: { status: 0, data: { dict: {}, arr: [] } } }
    }
    if (url === '/api/save/active_skills') {
      return { data: { status: 0, data: { dict: {}, arr: [] } } }
    }
    if (url === '/api/save/pal_data') {
      return { data: { status: 0, data: { dict: {}, arr: [] } } }
    }
    if (url === '/api/save/tech_data') {
      return { data: { status: 0, data: { techLvDict: {} } } }
    }
    throw new Error(`unexpected GET ${url}`)
  }

  await store.searchItemCatalog('shield', 'EQUIPMENT')
  store.I18n = 'zh-CN'
  await store.updateI18n()

  assert.equal(store.ITEM_CATALOG_RESULTS[0].name, '超级护盾')
  assert.equal(
    store.SELECTED_PLAYER_DATA.InventoryContainers[0].slots[0].item.name,
    '超级护盾',
  )
  assert.deepEqual(catalogRequests, [
    '/api/player/item_catalog?q=shield&container_type=EQUIPMENT',
    '/api/player/item_catalog?q=shield&container_type=EQUIPMENT',
  ])
})
