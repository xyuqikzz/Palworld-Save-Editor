import test from 'node:test'
import assert from 'node:assert/strict'

import axios from 'axios'
import { createPinia, setActivePinia } from 'pinia'

globalThis.alert = () => {}
globalThis.confirm = () => true
globalThis.window = { confirm: () => true }
globalThis.localStorage = {
  getItem: () => null,
  setItem: () => {},
}

const { usePalEditorStore } = await import('../src/stores/paleditor.js')

function makeStore() {
  setActivePinia(createPinia())
  const store = usePalEditorStore()
  const playerId = 'player-1'
  const player = {
    InstanceId: playerId,
    NickName: 'Player',
    pals: new Map(),
    InventoryContainers: [],
  }
  store.SESSION_ID = 'session-1'
  store.SESSION_REVISION = 0
  store.SELECTED_PLAYER_ID = playerId
  store.SELECTED_PLAYER_DATA = player
  store.PLAYER_MAP = new Map([[playerId, player]])
  store.PAL_MAP = player.pals
  return { store, player, playerId }
}

test('trust level clamps loaded negatives and does not decrement below zero', async () => {
  const { store, player, playerId } = makeStore()
  const palId = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
  axios.post = async url => ({
    data: url === '/api/player/player_pals'
      ? {
          status: 0,
          data: [{
            InstanceId: palId,
            FriendshipLevel: -1,
            DataAccessKey: 'KingWhale',
            DisplayName: 'Panthalus',
            PassiveSkillList: [],
            EquipWaza: [],
            MasteredWaza: [],
            Suitabilities: {},
          }],
        }
      : { status: 0, data: { revision: 1 } },
  })

  await store.selectPlayer(playerId, true)
  const pal = player.pals.get(palId)

  assert.equal(pal.FriendshipLevel, 0)
  pal.friendshipLevelDown()
  assert.equal(pal.FriendshipLevel, 0)
})

test('inventory writes use semantic container type and advance session revision', async () => {
  const { store, playerId } = makeStore()
  const calls = []
  axios.post = async (url, data) => {
    calls.push({ url, data: structuredClone(data) })
    return { data: { status: 0, data: { revision: 1, slot: {} } } }
  }
  axios.get = async () => ({
    data: {
      status: 0,
      data: {
        containers: [{ container_type: 'COMMON', status: 'available', slots: [] }],
      },
    },
  })

  await store.updateInventoryItem(
    { container_type: 'COMMON' },
    {
      slot_index: 4,
      item: { static_id: 'Stone', count: 25, dynamic_id: null },
    },
  )

  assert.equal(calls[0].url, `/api/player/${playerId}/inventory/commands`)
  assert.deepEqual(calls[0].data, {
    session_id: 'session-1',
    expected_revision: 0,
    container_type: 'COMMON',
    slot_index: 4,
    command: 'update_item_count',
    expected_static_id: 'Stone',
    count: 25,
  })
  assert.equal('container_id' in calls[0].data, false)
  assert.equal(store.SESSION_REVISION, 1)
  assert.equal(store.PENDING_CHANGE_COUNT, 1)
  assert.equal(store.SELECTED_PLAYER_DATA.InventoryContainers[0].container_type, 'COMMON')
})

test('structural add uses explicit command and refreshes the target Pal', async () => {
  const { store, player, playerId } = makeStore()
  const palId = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
  const calls = []
  axios.post = async (url, data) => {
    calls.push({ url, data: structuredClone(data) })
    if (url === '/api/pal/structural/commands') {
      return {
        data: {
          status: 0,
          data: {
            change: { revision_after: 1 },
            pal: { pal_id: palId },
          },
        },
      }
    }
    if (url === '/api/player/player_pals') {
      return {
        data: {
          status: 0,
          data: [{
            InstanceId: palId,
            DataAccessKey: 'SheepBall',
            DisplayName: 'Lamball',
            PassiveSkillList: [],
            EquipWaza: [],
            MasteredWaza: [],
            Suitabilities: {},
          }],
        },
      }
    }
    return {
      data: {
        status: 0,
        data: {
          InstanceId: palId,
          DataAccessKey: 'SheepBall',
          DisplayName: 'Lamball',
          PassiveSkillList: [],
          EquipWaza: [],
          MasteredWaza: [],
          Suitabilities: {},
        },
      },
    }
  }

  const succeeded = await store.addPal('SheepBall', 'PAL_STORAGE')

  assert.equal(succeeded, true)
  assert.deepEqual(calls[0], {
    url: '/api/pal/structural/commands',
    data: {
      session_id: 'session-1',
      expected_revision: 0,
      command: 'add_pal',
      player_id: playerId,
      species_id: 'SheepBall',
      container_type: 'PAL_STORAGE',
    },
  })
  assert.equal(player.pals.has(palId), true)
  assert.equal(store.SELECTED_PAL_ID, palId)
  assert.equal(store.SESSION_REVISION, 1)
})

test('save sends the exact active revision and clears pending changes', async () => {
  const { store } = makeStore()
  store.SESSION_REVISION = 7
  store.PENDING_CHANGE_COUNT = 3
  store.PAL_WRITE_BACK_PATH = 'D:/synthetic-save'
  await store.getTranslatedText('Alert_Successful_Save')
  let request
  axios.post = async (url, data) => {
    request = { url, data: structuredClone(data) }
    return {
      data: {
        status: 0,
        data: {
          revision: 7,
          backup_path: 'D:/backup',
          written_files: ['Level.sav'],
        },
      },
    }
  }

  const saved = await store.writeSave()

  assert.equal(saved, true)
  assert.deepEqual(request, {
    url: '/api/save/save',
    data: {
      WritePath: 'D:/synthetic-save',
      session_id: 'session-1',
      expected_revision: 7,
    },
  })
  assert.equal(store.PENDING_CHANGE_COUNT, 0)
  assert.equal(store.LAST_SAVE_RESULT.backup_path, 'D:/backup')
})

test('return keeps a dirty session until discard is confirmed and closed', async () => {
  const { store } = makeStore()
  store.SAVE_LOADED_FLAG = true
  store.SESSION_REVISION = 7
  store.PENDING_CHANGE_COUNT = 2
  const originalConfirm = window.confirm
  const calls = []
  axios.delete = async (url, config) => {
    calls.push({ url, data: structuredClone(config.data) })
    return {
      data: {
        status: 0,
        data: { session_id: 'session-1', discarded_change_count: 2 },
      },
    }
  }

  try {
    window.confirm = () => false
    assert.equal(await store.returnToMain(), false)
    assert.equal(calls.length, 0)
    assert.equal(store.SESSION_ID, 'session-1')
    assert.equal(store.SAVE_LOADED_FLAG, true)

    window.confirm = () => true
    assert.equal(await store.returnToMain(), true)
    assert.deepEqual(calls, [{
      url: '/api/save/session',
      data: {
        session_id: 'session-1',
        expected_revision: 7,
        discard_changes: true,
      },
    }])
    assert.equal(store.SESSION_ID, null)
    assert.equal(store.PENDING_CHANGE_COUNT, 0)
    assert.equal(store.SAVE_LOADED_FLAG, false)
  } finally {
    window.confirm = originalConfirm
  }
})

test('inventory clipboard and layout commands stay semantic and revision-bound', async () => {
  const { store, playerId } = makeStore()
  const calls = []
  axios.post = async (url, data) => {
    calls.push({ url, data: structuredClone(data) })
    if (url.endsWith('/inventory/copy')) {
      return { data: { status: 0, data: {
        clipboard_token: 'clipboard-1',
        revision: 0,
        item: { static_id: 'Stone', count: 5, dynamic_kind: 'none' },
      } } }
    }
    return { data: { status: 0, data: { revision: 1, slot: {} } } }
  }
  axios.get = async () => ({ data: { status: 0, data: { containers: [] } } })
  const container = { container_type: 'COMMON' }
  await store.copyInventoryItem(container, { slot_index: 2 })
  await store.pasteInventoryItem(container, { slot_index: 4 })

  assert.equal(calls[0].url, `/api/player/${playerId}/inventory/copy`)
  assert.equal(calls[1].url, `/api/player/${playerId}/inventory/layout/commands`)
  assert.deepEqual(calls[1].data, {
    session_id: 'session-1',
    expected_revision: 0,
    container_type: 'COMMON',
    command: 'paste_item_slot',
    slot_index: 4,
    clipboard_token: 'clipboard-1',
  })
  assert.equal('container_id' in calls[1].data, false)
  assert.equal(store.SESSION_REVISION, 1)
})

test('batch UI previews impact before one atomic execution', async () => {
  const { store } = makeStore()
  const calls = []
  axios.post = async (url, data) => {
    calls.push({ url, data: structuredClone(data) })
    if (url === '/api/batch/preview') {
      return { data: { status: 0, data: {
        impact: { operation_count: 2, atomicity: 'all_or_nothing' },
        impact_token: 'impact-1',
      } } }
    }
    return { data: { status: 0, data: { revision: 1, operation_count: 2 } } }
  }
  axios.get = async () => ({ data: { status: 0, data: { containers: [] } } })
  const operations = [
    { resource: 'pal', command: 'update_pal_progression', pal_id: 'pal-1', values: { heal: true } },
    { resource: 'pal', command: 'update_pal_progression', pal_id: 'pal-2', values: { heal: true } },
  ]
  const succeeded = await store.executeBatchOperations(operations)

  assert.equal(succeeded, true)
  assert.equal(calls[0].url, '/api/batch/preview')
  assert.equal(calls[1].url, '/api/batch/commands')
  assert.equal(calls[1].data.impact_token, 'impact-1')
  assert.deepEqual(calls[1].data.operations, operations)
  assert.equal(store.SESSION_REVISION, 1)
})

test('heal all Pals targets every Pal in the current list without selections', async () => {
  const { store, player } = makeStore()
  player.pals.set('pal-1', {})
  player.pals.set('pal-2', {})
  store.PAL_MAP = player.pals
  const calls = []
  axios.post = async (url, data) => {
    calls.push({ url, data: structuredClone(data) })
    if (url === '/api/batch/preview') {
      return { data: { status: 0, data: {
        impact: { operation_count: 2, atomicity: 'all_or_nothing' },
        impact_token: 'heal-all-impact',
      } } }
    }
    return { data: { status: 0, data: { revision: 1, operation_count: 2 } } }
  }
  axios.get = async () => ({ data: { status: 0, data: { containers: [] } } })

  const succeeded = await store.healAllPals()

  assert.equal(succeeded, true)
  assert.deepEqual(calls[0], {
    url: '/api/batch/preview',
    data: {
      session_id: 'session-1',
      expected_revision: 0,
      operations: [
        { resource: 'pal', command: 'update_pal_progression', pal_id: 'pal-1', values: { heal: true } },
        { resource: 'pal', command: 'update_pal_progression', pal_id: 'pal-2', values: { heal: true } },
      ],
    },
  })
  assert.equal(calls[1].url, '/api/batch/commands')
  assert.equal(calls[1].data.impact_token, 'heal-all-impact')
})

test('heal all confirms immediately before waiting for the batch preview', async () => {
  const { store, player } = makeStore()
  player.pals.set('pal-1', {})
  player.pals.set('pal-2', {})
  store.PAL_MAP = player.pals

  const events = []
  const previousConfirm = window.confirm
  let resolvePreview
  window.confirm = () => {
    events.push('confirm')
    return true
  }
  axios.post = (url) => {
    events.push(url)
    if (url === '/api/batch/preview') {
      return new Promise(resolve => {
        resolvePreview = () => resolve({ data: { status: 0, data: {
          impact: { operation_count: 2, atomicity: 'all_or_nothing' },
          impact_token: 'heal-immediate-impact',
        } } })
      })
    }
    return Promise.resolve({ data: { status: 0, data: { revision: 1, operation_count: 2 } } })
  }
  axios.get = async () => ({ data: { status: 0, data: { containers: [] } } })

  try {
    const pending = store.healAllPals()

    assert.deepEqual(events, ['confirm', '/api/batch/preview'])
    assert.equal(store.LOADING_FLAG, true)

    resolvePreview()
    const succeeded = await pending

    assert.equal(succeeded, true)
    assert.deepEqual(events, ['confirm', '/api/batch/preview', '/api/batch/commands'])
    assert.equal(store.LOADING_FLAG, false)
  } finally {
    window.confirm = previousConfirm
  }
})

test('unlock expedition Pals targets only locked Pals in the current list', async () => {
  const { store, player } = makeStore()
  const lockedPal = { IsExpeditionPal: true }
  const normalPal = { IsExpeditionPal: false }
  player.pals.set('pal-locked', lockedPal)
  player.pals.set('pal-normal', normalPal)
  store.PAL_MAP = player.pals
  const calls = []
  axios.post = async (url, data) => {
    calls.push({ url, data: structuredClone(data) })
    if (url === '/api/batch/preview') {
      return { data: { status: 0, data: {
        impact: { operation_count: 1, atomicity: 'all_or_nothing' },
        impact_token: 'unlock-expedition-impact',
      } } }
    }
    return { data: { status: 0, data: { revision: 1, operation_count: 1 } } }
  }
  axios.get = async () => ({ data: { status: 0, data: { containers: [] } } })

  const succeeded = await store.unlockExpeditionPals()

  assert.equal(succeeded, true)
  assert.deepEqual(calls[0], {
    url: '/api/batch/preview',
    data: {
      session_id: 'session-1',
      expected_revision: 0,
      operations: [
        { resource: 'pal', command: 'unlock_pal_expedition', pal_id: 'pal-locked' },
      ],
    },
  })
  assert.equal(calls[1].url, '/api/batch/commands')
  assert.equal(calls[1].data.impact_token, 'unlock-expedition-impact')
  assert.equal(lockedPal.IsExpeditionPal, false)
  assert.equal(normalPal.IsExpeditionPal, false)
  assert.equal(store.EXPEDITION_PAL_COUNT, 0)
})
