import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

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
  store.SESSION_ID = 'session-1'
  return store
}

function palPayload(instanceId = 'pal-1', slotIndex = 0) {
  return {
    InstanceId: instanceId,
    SlotIndex: slotIndex,
    DataAccessKey: 'SheepBall',
    DisplayName: 'Lamball',
    PassiveSkillList: [],
    EquipWaza: [],
    MasteredWaza: [],
    Suitabilities: {},
  }
}

test('selecting a base requests only that base and selects its first container-slot worker', async () => {
  const store = makeStore()
  const calls = []
  axios.post = async (url, data) => {
    calls.push({ url, data: structuredClone(data) })
    return { data: { status: 0, data: url === '/api/player/player_pals'
      ? [palPayload('pal-later', 4), palPayload('pal-first', 1)]
      : palPayload(data.InstanceId, data.InstanceId === 'pal-first' ? 1 : 4) } }
  }

  await store.selectBase(
    { guild_id: 'guild-1', kind: 'guild' },
    { node_id: 'base:base-1', base_id: 'base-1', kind: 'base' },
  )

  assert.deepEqual(calls[0], {
    url: '/api/player/player_pals',
    data: {
      PlayerUId: 'PAL_BASE_WORKER_BTN',
      BaseId: 'base-1',
      GuildId: 'guild-1',
    },
  })
  assert.equal(store.SELECTED_BASE_KEY, 'base:base-1')
  assert.equal(store.BASE_PAL_BTN_CLK_FLAG, true)
  assert.equal(store.PAL_MAP.get('pal-first').SlotIndex, 1)
  assert.equal(store.PAL_MAP.get('pal-later').SlotIndex, 4)
  assert.equal(store.SELECTED_PAL_ID, 'pal-first')
})

test('selecting a player keeps the player editor active without selecting a Pal', async () => {
  const store = makeStore()
  const playerId = 'player-1'
  const pals = new Map([
    ['pal-later', palPayload('pal-later', 4)],
    ['pal-first', palPayload('pal-first', 1)],
  ])
  store.PLAYER_MAP = new Map([[
    playerId,
    { InstanceId: playerId, NickName: 'Player', pals, InventoryContainers: [] },
  ]])
  axios.get = async url => ({ data: {
    status: 0,
    data: url.includes('/inventory') ? { containers: [] } : { missions: [] },
  } })
  axios.post = async (url, data) => ({ data: {
    status: 0,
    data: url === '/api/player/player_data'
      ? { InstanceId: playerId, NickName: 'Player' }
      : palPayload(data.InstanceId, data.InstanceId === 'pal-first' ? 1 : 4),
  } })

  await store.selectPlayer(playerId)

  assert.equal(store.SELECTED_PAL_ID, null)
  assert.equal(store.SELECTED_PAL_DATA, null)
  assert.equal(store.SHOW_PLAYER_EDIT_FLAG, true)
})

test('the no-guild unmatched base keeps its explicit fallback scope', async () => {
  const store = makeStore()
  let request
  axios.post = async (url, data) => {
    if (url === '/api/player/player_pals') request = structuredClone(data)
    return { data: { status: 0, data: [] } }
  }

  await store.selectBase(
    { guild_id: null, kind: 'no_guild' },
    { node_id: 'unmatched-base:no-guild', base_id: null, kind: 'unmatched' },
  )

  assert.deepEqual(request, {
    PlayerUId: 'PAL_BASE_WORKER_BTN',
    NoGuild: true,
    UnmatchedBase: true,
  })
})

test('renaming a guild sends a revision-bound command and updates the tree item', async () => {
  const store = makeStore()
  store.SESSION_REVISION = 3
  store.GUILD_TREE = [{ guild_id: 'guild-1', kind: 'guild', name: 'Builders' }]
  let request
  axios.post = async (url, data) => {
    request = { url, data: structuredClone(data) }
    return { data: { status: 0, data: {
      revision: 4,
      value: { guild_id: 'guild-1', name: 'New Builders' },
    } } }
  }

  const updated = await store.updateGuildName('guild-1', '  New Builders  ')

  assert.equal(updated, true)
  assert.deepEqual(request, {
    url: '/api/save/guilds/guild-1/commands',
    data: {
      session_id: 'session-1',
      expected_revision: 3,
      command: 'update_guild_name',
      name: 'New Builders',
    },
  })
  assert.equal(store.GUILD_TREE[0].name, 'New Builders')
  assert.equal(store.SESSION_REVISION, 4)
  assert.equal(store.PENDING_CHANGE_COUNT, 1)
})

test('the player panel renders guilds as the first tree level', () => {
  const source = fs.readFileSync(new URL('../src/components/PlayerList.vue', import.meta.url), 'utf8')

  assert.match(source, /v-for="guild in palStore\.GUILD_TREE"/)
  assert.match(source, /palStore\.selectBase\(guild, base\)/)
  assert.match(source, /PlayerTree_NoGuild/)
  assert.match(source, /class="guild-name-input"/)
  assert.match(source, /class="guild-edit-action"/)
  assert.match(source, /editingGuildId === guild\.guild_id \? 'check' : 'edit'/)
  assert.doesNotMatch(source, /selectPlayer\(palStore\.PAL_BASE_WORKER_BTN\)/)
  assert.match(source, /\.guild-tree\s*\{[^}]*gap:\s*8px[^}]*padding:\s*8px 6px 10px/s)
})

test('the optional viewing-cage action keeps a stable centered title slot', () => {
  const source = fs.readFileSync(new URL('../src/components/PlayerList.vue', import.meta.url), 'utf8')

  assert.match(source, /class="tooltip-container panel-action-slot"/)
  assert.match(
    source,
    /\.panel-action-slot\s*\{(?=[^}]*width:\s*32px)(?=[^}]*height:\s*32px)(?=[^}]*flex:\s*0 0 32px)[^}]*\}/,
  )
  assert.match(
    source,
    /\.panel-action-slot > button\.playerSettings\s*\{(?=[^}]*display:\s*inline-flex)(?=[^}]*align-items:\s*center)(?=[^}]*justify-content:\s*center)(?=[^}]*width:\s*100%)(?=[^}]*height:\s*100%)[^}]*\}/,
  )
})

test('loading tree items do not all use the selected highlight', () => {
  const source = fs.readFileSync(new URL('../src/components/PlayerList.vue', import.meta.url), 'utf8')

  assert.doesNotMatch(
    source,
    /\.tree-item:disabled\s*,\s*\.tree-item\[selected="true"\]\s*{/,
  )
  assert.match(
    source,
    /\.tree-item\[selected="true"\][^{]*{[^}]*background:\s*var\(--ui-accent-soft\)/s,
  )
})

test('base labels do not expose internal saved template names', () => {
  const source = fs.readFileSync(new URL('../src/components/PlayerList.vue', import.meta.url), 'utf8')

  assert.doesNotMatch(source, /\$\{fallback\}[^\n]*base\.name/)
})
