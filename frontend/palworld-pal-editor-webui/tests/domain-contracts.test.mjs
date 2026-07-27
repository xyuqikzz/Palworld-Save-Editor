import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

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

test('human NPC trust uses the same progression command and refreshes the bonus field', async () => {
  const { store, player, playerId } = makeStore()
  const palId = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
  const npcData = {
    InstanceId: palId,
    IsHuman: true,
    FriendshipLevel: 4,
    DataAccessKey: 'SalesPerson_Wander',
    DisplayName: 'Wandering Merchant',
    PassiveSkillList: [],
    EquipWaza: ['EPalWazaID::Weapon_Use'],
    MasteredWaza: ['EPalWazaID::Weapon_Use'],
    Suitabilities: {},
  }
  axios.post = async url => ({
    data: url === '/api/player/player_pals'
      ? { status: 0, data: [npcData] }
      : { status: 0, data: {} },
  })
  await store.selectPlayer(playerId, true)
  store.SELECTED_PAL_ID = palId
  store.SELECTED_PAL_DATA = player.pals.get(palId)

  const calls = []
  axios.post = async (url, data) => {
    calls.push({ url, data: structuredClone(data) })
    if (url === `/api/pal/${palId}/commands`) {
      return { data: { status: 0, data: {
        revision: 1,
        value: { friendship_level: 5 },
      } } }
    }
    return { data: { status: 0, data: {
      ...npcData,
      FriendshipLevel: 5,
    } } }
  }

  await store.SELECTED_PAL_DATA.friendshipLevelUp()

  const command = calls.find(call => call.url === `/api/pal/${palId}/commands`)
  assert.deepEqual(command.data, {
    session_id: 'session-1',
    expected_revision: 0,
    command: 'update_pal_progression',
    values: { friendship_level: 5 },
  })
  assert.equal(store.SELECTED_PAL_DATA.IsHuman, true)
  assert.equal(store.SELECTED_PAL_DATA.FriendshipLevel, 5)
  assert.equal(store.SESSION_REVISION, 1)
})

test('awakening sends a boolean enhancement command and refreshes the Pal detail', async () => {
  const { store, player, playerId } = makeStore()
  const palId = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
  const calls = []
  axios.post = async (url, data) => {
    calls.push({ url, data: structuredClone(data) })
    if (url === '/api/player/player_pals') {
      return { data: { status: 0, data: [{
        InstanceId: palId,
        IsAwakened: false,
        DataAccessKey: 'SheepBall',
        DisplayName: 'Lamball',
        PassiveSkillList: [],
        EquipWaza: [],
        MasteredWaza: [],
        Suitabilities: {},
      }] } }
    }
    if (url === `/api/pal/${palId}/commands`) {
      return { data: { status: 0, data: {
        revision: 1,
        value: { awakening: true },
      } } }
    }
    if (url === '/api/pal/paldata') {
      return { data: { status: 0, data: {
        InstanceId: palId,
        IsAwakened: true,
        AwakeningStatusMultiplier: 1.5,
        DataAccessKey: 'SheepBall',
        DisplayName: 'Lamball',
        PassiveSkillList: [],
        EquipWaza: [],
        MasteredWaza: [],
        Suitabilities: {},
      } } }
    }
    return { data: { status: 0, data: {} } }
  }

  await store.selectPlayer(playerId, true)
  store.SELECTED_PAL_ID = palId
  store.SELECTED_PAL_DATA = player.pals.get(palId)
  await store.SELECTED_PAL_DATA.swapAwakening()

  const command = calls.find(call => call.url === `/api/pal/${palId}/commands`)
  assert.deepEqual(command.data, {
    session_id: 'session-1',
    expected_revision: 0,
    command: 'update_pal_enhancement',
    values: { awakening: true },
  })
  assert.equal(store.SELECTED_PAL_DATA.IsAwakened, true)
  assert.equal(store.SELECTED_PAL_DATA.AwakeningStatusMultiplier, 1.5)
})

test('NPC weapon is displayed from catalog metadata without edit controls', () => {
  const componentSource = readFileSync(
    new URL('../src/components/PalEditor.vue', import.meta.url),
    'utf8',
  )
  const storeSource = readFileSync(
    new URL('../src/stores/paleditor.js', import.meta.url),
    'utf8',
  )

  assert.match(componentSource, /getNpcWeaponDisplayName\(palStore\.SELECTED_PAL_DATA\.NpcDefaultWeapon\)/)
  assert.doesNotMatch(componentSource, /NpcWeaponSelection|updateNpcWeapon|npc-weapon-apply|NpcWeapon_Warning/)
  assert.doesNotMatch(storeSource, /function updateNpcWeapon|command:\s*["']update_npc_weapon["']/)
})

test('NPC weapon names are localized while preserving the catalog identifier', () => {
  const { store } = makeStore()
  store.I18n = 'zh-CN'

  assert.equal(store.getNpcWeaponDisplayName('GatlingGun'), '加特林机枪（GatlingGun）')
  assert.equal(store.getNpcWeaponDisplayName('None'), '徒手（None）')
  assert.equal(store.getNpcWeaponDisplayName('UnknownWeapon'), 'UnknownWeapon')
})

test('inventory writes use semantic container type and advance session revision', async () => {
  const { store, playerId } = makeStore()
  const calls = []
  axios.post = async (url, data) => {
    calls.push({ url, data: structuredClone(data) })
    const revision = data.command === 'swap_item_slots' ? 2 : 1
    return { data: { status: 0, data: { revision, slot: {} } } }
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

test('structural add sends creation presets in one command and refreshes the target Pal', async () => {
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

  store.HIDE_INVALID_OPTIONS = false
  const succeeded = await store.addPal('SheepBall', 'PAL_STORAGE', {
    passive: ['WorldTree_CraftSpeed', 'CraftSpeed_up3'],
    maxPal: false,
    maxWork: true,
  })

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
      passive: ['WorldTree_CraftSpeed', 'CraftSpeed_up3'],
      max_pal: false,
      max_work: true,
      unrestricted: true,
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
    const revision = data.command === 'swap_item_slots' ? 2 : 1
    return { data: { status: 0, data: { revision, slot: {} } } }
  }
  axios.get = async () => ({ data: { status: 0, data: { containers: [] } } })
  const container = { container_type: 'COMMON' }
  await store.copyInventoryItem(container, { slot_index: 2 })
  await store.pasteInventoryItem(container, { slot_index: 4 })
  assert.equal(store.SESSION_REVISION, 1)
  await store.swapInventorySlots(container, 4, 1)

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
  assert.equal(calls[2].url, `/api/player/${playerId}/inventory/layout/commands`)
  assert.deepEqual(calls[2].data, {
    session_id: 'session-1',
    expected_revision: 1,
    container_type: 'COMMON',
    command: 'swap_item_slots',
    source_slot_index: 4,
    target_slot_index: 1,
  })
  assert.equal('container_id' in calls[2].data, false)
  assert.equal(store.SESSION_REVISION, 2)
})

test('inventory editor keeps the restored card layout and accessible move behavior', () => {
  const source = readFileSync(
    new URL('../src/components/InventoryEditor.vue', import.meta.url),
    'utf8',
  )
  for (const marker of [
    "'slot-card'",
    'grid-template-columns: repeat(auto-fill, minmax(min(330px, 100%), 1fr));',
    `:draggable="slot.state === 'occupied' && !palStore.LOADING_FLAG"`,
    '@drop="onDrop($event, selectedContainer, slot)"',
    '@keydown="onSlotKeydown($event, selectedContainer, slot)"',
    'sourceContainerType === container?.container_type',
    'swapInventorySlots',
  ]) {
    assert.ok(source.includes(marker), 'missing restored inventory behavior: ' + marker)
  }
  assert.doesNotMatch(source, /inventory-game-layout|equipment-stage/)
  for (const action of [
    'updateInventoryItem',
    'copyInventoryItem',
    'clearInventoryItem',
    'pasteInventoryItem',
    'toggleDynamicEditor',
  ]) {
    assert.match(source, new RegExp(action))
  }
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

test('unlock all expedition Pals uses one whole-save command and refreshes expeditions', async () => {
  const { store, player } = makeStore()
  const lockedPal = { IsExpeditionPal: true }
  const normalPal = { IsExpeditionPal: false }
  player.pals.set('pal-locked', lockedPal)
  player.pals.set('pal-normal', normalPal)
  store.PAL_MAP = player.pals
  const calls = []
  axios.post = async (url, data) => {
    calls.push({ url, data: structuredClone(data) })
    return { data: { status: 0, data: {
      revision: 1,
      value: { unlocked_count: 1 },
    } } }
  }
  const getCalls = []
  axios.get = async url => {
    getCalls.push(url)
    return { data: { status: 0, data: {
      revision: 1,
      active_count: 0,
      completable_count: 0,
      locked_count: 0,
      expeditions: [],
      invalid_locked_pals: [],
      unknown_locked_pals: [],
    } } }
  }

  const succeeded = await store.unlockExpeditionPals()

  assert.equal(succeeded, true)
  assert.deepEqual(calls, [{
    url: '/api/save/pals/commands',
    data: {
      session_id: 'session-1',
      expected_revision: 0,
      command: 'unlock_all_expedition_pals',
    },
  }])
  assert.deepEqual(getCalls, [
    '/api/save/query/expeditions?session_id=session-1',
  ])
  assert.equal(lockedPal.IsExpeditionPal, false)
  assert.equal(normalPal.IsExpeditionPal, false)
  assert.equal(store.EXPEDITION_PAL_COUNT, 0)
})

test('complete expeditions uses the global save command and disables completed targets', async () => {
  const { store, player } = makeStore()
  const expeditionId = '44444444-5555-6666-7777-888888888888'
  const expeditionPal = {
    IsExpeditionPal: true,
    ExpeditionInstanceId: expeditionId,
    ExpeditionAssignmentStatus: 'valid',
    ExpeditionCanComplete: true,
  }
  player.pals.set('pal-expedition', expeditionPal)
  store.PAL_MAP = player.pals
  const calls = []
  const previousConfirm = window.confirm
  window.confirm = () => true
  axios.post = async (url, data) => {
    calls.push({ url, data: structuredClone(data) })
    return { data: { status: 0, data: {
      revision: 1,
      value: { completed_count: 1, expedition_ids: [expeditionId] },
    } } }
  }

  try {
    assert.equal(store.COMPLETABLE_EXPEDITION_COUNT, 1)
    const succeeded = await store.completeActiveExpeditions()

    assert.equal(succeeded, true)
    assert.deepEqual(calls, [{
      url: '/api/save/expeditions/commands',
      data: {
        session_id: 'session-1',
        expected_revision: 0,
        command: 'complete_active_expeditions',
      },
    }])
    assert.equal(expeditionPal.ExpeditionCanComplete, false)
    assert.equal(store.COMPLETABLE_EXPEDITION_COUNT, 0)
    assert.equal(store.SESSION_REVISION, 1)
  } finally {
    window.confirm = previousConfirm
  }
})

test('single expedition completion targets only the selected expedition', async () => {
  const { store } = makeStore()
  const firstId = '44444444-5555-6666-7777-888888888888'
  const secondId = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
  axios.get = async () => ({ data: { status: 0, data: {
    revision: 0,
    active_count: 2,
    completable_count: 2,
    locked_count: 2,
    expeditions: [
      { expedition_id: firstId, mission_id: 'DUNGEON_GRASS', base_name: 'Base One', can_complete: true, members: [] },
      { expedition_id: secondId, mission_id: 'DUNGEON_DESERT', base_name: 'Base Two', can_complete: true, members: [] },
    ],
    invalid_locked_pals: [],
    unknown_locked_pals: [],
  } } })
  await store.loadExpeditions()
  const calls = []
  axios.post = async (url, data) => {
    calls.push({ url, data: structuredClone(data) })
    return { data: { status: 0, data: {
      revision: 1,
      value: { completed_count: 1, expedition_ids: [firstId] },
    } } }
  }
  const previousConfirm = window.confirm
  window.confirm = () => true

  try {
    const succeeded = await store.completeExpedition(firstId)

    assert.equal(succeeded, true)
    assert.deepEqual(calls, [{
      url: '/api/save/expeditions/commands',
      data: {
        session_id: 'session-1',
        expected_revision: 0,
        command: 'complete_expedition',
        expedition_id: firstId,
      },
    }])
    assert.equal(store.EXPEDITION_DATA.expeditions[0].can_complete, false)
    assert.equal(store.EXPEDITION_DATA.expeditions[1].can_complete, true)
    assert.equal(store.COMPLETABLE_EXPEDITION_COUNT, 1)
  } finally {
    window.confirm = previousConfirm
  }
})

test('single expedition unlock confirms coordinated removal and clears the selected Pal status', async () => {
  const { store, player } = makeStore()
  const palId = 'pal-expedition'
  const pal = {
    InstanceId: palId,
    IsExpeditionPal: true,
    ExpeditionInstanceId: '44444444-5555-6666-7777-888888888888',
    ExpeditionAssignmentStatus: 'valid',
  }
  player.pals.set(palId, pal)
  store.PAL_MAP = player.pals
  store.SELECTED_PAL_ID = palId
  store.SELECTED_PAL_DATA = pal
  const confirmations = []
  const calls = []
  const previousConfirm = window.confirm
  window.confirm = message => {
    confirmations.push(message)
    return true
  }
  axios.post = async (url, data) => {
    calls.push({ url, data: structuredClone(data) })
    return { data: { status: 0, data: { revision: 1, value: { expedition_locked: false } } } }
  }
  axios.get = async url => {
    assert.equal(url, '/api/save/query/expeditions?session_id=session-1')
    return { data: { status: 0, data: {
      revision: 1,
      active_count: 0,
      completable_count: 0,
      locked_count: 0,
      expeditions: [],
      invalid_locked_pals: [],
      unknown_locked_pals: [],
    } } }
  }

  try {
    const succeeded = await store.cancelSelectedPalExpedition()

    assert.equal(succeeded, true)
    assert.equal(confirmations.length, 1)
    assert.deepEqual(calls[0], {
      url: `/api/pal/${palId}/commands`,
      data: {
        session_id: 'session-1',
        expected_revision: 0,
        command: 'unlock_pal_expedition',
      },
    })
    assert.equal(pal.IsExpeditionPal, false)
    assert.equal(pal.ExpeditionInstanceId, null)
    assert.equal(pal.ExpeditionAssignmentStatus, null)
    assert.equal(store.SESSION_REVISION, 1)
  } finally {
    window.confirm = previousConfirm
  }
})
