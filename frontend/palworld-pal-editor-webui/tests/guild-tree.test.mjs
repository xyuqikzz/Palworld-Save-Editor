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
  store.GUILD_LIST = [{ guild_id: 'guild-1', kind: 'guild', name: 'Builders' }]
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
  assert.equal(store.GUILD_LIST[0].name, 'New Builders')
  assert.equal(store.SESSION_REVISION, 4)
  assert.equal(store.PENDING_CHANGE_COUNT, 1)
})

test('changing a guild owner updates member roles and keeps role order', async () => {
  const store = makeStore()
  store.SESSION_REVISION = 3
  const guild = {
    guild_id: 'guild-1',
    owner_player_id: 'player-owner',
    owner_status: 'available',
    owner_editable: true,
    members: [
      {
        player_id: 'player-member',
        name: 'Member',
        role: 3,
        role_status: 'available',
        owner_eligible: true,
        is_owner: false,
      },
      {
        player_id: 'player-owner',
        name: 'Owner',
        role: 1,
        role_status: 'available',
        owner_eligible: true,
        is_owner: true,
      },
    ],
  }
  store.GUILD_LIST = [structuredClone(guild)]
  store.GUILD_TREE = [structuredClone(guild)]
  let request
  axios.post = async (url, data) => {
    request = { url, data: structuredClone(data) }
    return { data: { status: 0, data: {
      revision: 4,
      value: {
        guild_id: 'guild-1',
        owner_player_id: 'player-member',
        members: [
          { player_id: 'player-owner', role: 2 },
          { player_id: 'player-member', role: 1 },
        ],
      },
    } } }
  }

  assert.equal(
    await store.updateGuildOwner('guild-1', 'player-member'),
    true,
  )
  assert.deepEqual(request, {
    url: '/api/save/guilds/guild-1/commands',
    data: {
      session_id: 'session-1',
      expected_revision: 3,
      command: 'update_guild_owner',
      player_id: 'player-member',
    },
  })
  assert.equal(store.GUILD_LIST[0].owner_player_id, 'player-member')
  assert.deepEqual(
    store.GUILD_LIST[0].members.map(member => [
      member.player_id,
      member.role,
      member.is_owner,
    ]),
    [
      ['player-member', 1, true],
      ['player-owner', 2, false],
    ],
  )
  assert.equal(store.SESSION_REVISION, 4)
  assert.equal(store.PENDING_CHANGE_COUNT, 1)
})

test('expanding a guild chest sends a revision-bound command and updates its capacity', async () => {
  const store = makeStore()
  store.SESSION_REVISION = 4
  store.GUILD_TREE = [{
    guild_id: 'guild-1',
    kind: 'guild',
    name: 'Builders',
    guild_chest_status: 'available',
    guild_chest_capacity: 54,
  }]
  store.GUILD_LIST = [{
    guild_id: 'guild-1',
    kind: 'guild',
    name: 'Builders',
    guild_chest_status: 'available',
    guild_chest_capacity: 54,
  }]
  let request
  axios.post = async (url, data) => {
    request = { url, data: structuredClone(data) }
    return { data: { status: 0, data: {
      revision: 5,
      value: { guild_id: 'guild-1', capacity: 90 },
    } } }
  }

  const updated = await store.updateGuildChestCapacity('guild-1', 90)

  assert.equal(updated, true)
  assert.deepEqual(request, {
    url: '/api/save/guilds/guild-1/commands',
    data: {
      session_id: 'session-1',
      expected_revision: 4,
      command: 'update_guild_chest_capacity',
      capacity: 90,
    },
  })
  assert.equal(store.GUILD_TREE[0].guild_chest_capacity, 90)
  assert.equal(store.GUILD_LIST[0].guild_chest_capacity, 90)
  assert.equal(store.SESSION_REVISION, 5)
  assert.equal(store.PENDING_CHANGE_COUNT, 1)
})

test('terminal level uses a dedicated revision-bound command', async () => {
  const store = makeStore()
  store.SESSION_REVISION = 6
  store.GUILD_LIST = [{
    guild_id: 'guild-1',
    base_camp_level: 14,
  }]
  const calls = []
  axios.post = async (url, data) => {
    calls.push({ url, data: structuredClone(data) })
    return { data: { status: 0, data: {
      revision: 7,
      value: { guild_id: 'guild-1', level: 35 },
    } } }
  }

  assert.equal(await store.updateGuildBaseCampLevel('guild-1', 35), true)

  assert.deepEqual(calls, [
    {
      url: '/api/save/guilds/guild-1/commands',
      data: {
        session_id: 'session-1',
        expected_revision: 6,
        command: 'update_base_camp_level',
        level: 35,
      },
    },
  ])
  assert.equal(store.GUILD_LIST[0].base_camp_level, 35)
  assert.equal(store.SESSION_REVISION, 7)
})

test('base storage is loaded lazily and item count writes keep guild-base scope', async () => {
  const store = makeStore()
  store.SESSION_REVISION = 4
  const calls = []
  let count = 5
  axios.get = async url => {
    calls.push({ method: 'get', url })
    return { data: { status: 0, data: {
      revision: store.SESSION_REVISION,
      guild_id: 'guild-1',
      base_id: 'base-1',
      status: 'available',
      write_status: 'available',
      containers: [{
        container_id: 'container-1',
        status: 'available',
        capacity: 1,
        slots: [{
          slot_index: 0,
          state: 'occupied',
          item: { static_id: 'Stone', count, dynamic_id: null },
        }],
      }],
    } } }
  }
  axios.post = async (url, data) => {
    calls.push({ method: 'post', url, data: structuredClone(data) })
    count = data.count
    return { data: { status: 0, data: {
      revision: 5,
      container_id: 'container-1',
      slot: {
        slot_index: 0,
        static_id: 'Stone',
        count,
        dynamic_id: null,
      },
    } } }
  }

  const loaded = await store.loadBaseStorage('guild-1', 'base-1')
  assert.equal(loaded.containers[0].slots[0].item.count, 5)

  const container = loaded.containers[0]
  const slot = container.slots[0]
  const updated = await store.updateBaseStorageItemCount(
    'guild-1',
    'base-1',
    container,
    slot,
    9,
  )

  assert.equal(updated.containers[0].slots[0].item.count, 9)
  assert.deepEqual(calls[1], {
    method: 'post',
    url: '/api/save/guilds/guild-1/bases/base-1/storage/commands',
    data: {
      session_id: 'session-1',
      expected_revision: 4,
      command: 'update_item_count',
      container_id: 'container-1',
      slot_index: 0,
      expected_static_id: 'Stone',
      count: 9,
    },
  })
  assert.equal(store.SESSION_REVISION, 5)
  assert.equal(
    store.getBaseStorage('guild-1', 'base-1')
      .containers[0].slots[0].item.count,
    9,
  )
})

test('the player panel renders guilds as the first tree level', () => {
  const source = fs.readFileSync(new URL('../src/components/PlayerList.vue', import.meta.url), 'utf8')

  assert.match(source, /v-for="guild in palStore\.GUILD_TREE"/)
  assert.match(source, /palStore\.selectBase\(guild, base\)/)
  assert.match(source, /PlayerTree_NoGuild/)
  assert.doesNotMatch(source, /guild-name-input/)
  assert.doesNotMatch(source, /guild-chest-row/)
  assert.doesNotMatch(source, /updateGuildChestCapacity/)
  assert.doesNotMatch(source, /selectPlayer\(palStore\.PAL_BASE_WORKER_BTN\)/)
  assert.match(source, /\.guild-tree\s*\{[^}]*gap:\s*8px[^}]*padding:\s*8px 6px 10px/s)
})

test('the guild page owns guild, chest, terminal, read-only base capacity, and member controls', () => {
  const source = fs.readFileSync(new URL('../src/views/GuildView.vue', import.meta.url), 'utf8')
  const storeSource = fs.readFileSync(new URL('../src/stores/paleditor.js', import.meta.url), 'utf8')

  assert.match(source, /v-for="guild in palStore\.GUILD_LIST"/)
  assert.match(source, /palStore\.loadGuilds\(\)/)
  assert.match(source, /palStore\.updateGuildName/)
  assert.match(source, /palStore\.updateGuildOwner/)
  assert.match(source, /palStore\.updateGuildChestCapacity/)
  assert.match(source, /palStore\.updateGuildBaseCampLevel/)
  assert.doesNotMatch(source, /updateBaseWorkerCapacity|saveEdit\('workers'|startEdit\('workers'/)
  assert.doesNotMatch(storeSource, /updateBaseWorkerCapacity|update_base_worker_capacity/)
  assert.match(source, /v-for="\(base, index\) in guild\.bases"/)
  assert.match(source, /v-for="member in guild\.members"/)
  assert.match(source, /memberRoleLabel\(member\)/)
  assert.match(source, /Guild_Owner/)
  assert.match(source, /Guild_WorkerCapacityValue/)
  assert.match(source, /BaseStoragePanel/)
  assert.match(source, /Guild_BaseStorage/)
  assert.match(source, /:aria-expanded="isStorageExpanded\(guild, base\)"/)
  assert.match(source, /role="tablist"/)
  assert.match(source, /role="tab"/)
  assert.match(source, /role="tabpanel"/)
  assert.match(source, /activeGuildTab\(guild\) === 'bases'/)
  assert.match(source, /activeGuildTab\(guild\) === 'members'/)
  assert.doesNotMatch(source, /Guild_EditWorkerCapacity|Guild_WorkerCapacityHelp/)
  assert.doesNotMatch(source, /Guild_Page(?:Eyebrow|Title|Description)/)
})

test('the base storage panel exposes add, replace, count, and clear actions', () => {
  const source = fs.readFileSync(
    new URL('../src/components/modules/BaseStoragePanel.vue', import.meta.url),
    'utf8',
  )

  assert.match(source, /palStore\.loadBaseStorage/)
  assert.match(source, /palStore\.putBaseStorageItem/)
  assert.match(source, /palStore\.updateBaseStorageItemCount/)
  assert.match(source, /palStore\.clearBaseStorageItem/)
  assert.match(source, /'empty_only'/)
  assert.match(source, /'replace'/)
  assert.match(source, /ItemPicker/)
  assert.match(source, /dynamicRecordStaticId/)
  assert.match(source, /BASE_STORAGE/)
  assert.match(source, /container\.building_name/)
  assert.doesNotMatch(source, /container\.map_object_type/)
  assert.match(source, /class="storage-container-list"/)
  assert.match(source, /class="storage-slot-grid"/)
  assert.match(source, /class="storage-slot-editor"/)
  assert.match(source, /Inventory_Max/)
  assert.match(source, /@click\.self="clearSlotSelection"/)
  assert.match(source, /grid-template-columns:\s*repeat\(auto-fill,\s*72px\)/)
})

test('each guild base renders its working Pals with hover and keyboard details', () => {
  const source = fs.readFileSync(new URL('../src/views/GuildView.vue', import.meta.url), 'utf8')

  assert.match(source, /v-for="worker in base\.workers"/)
  assert.match(source, /class="worker-pal"/)
  assert.match(source, /tabindex="0"/)
  assert.match(source, /class="worker-pal-tooltip"/)
  assert.match(source, /role="tooltip"/)
  assert.match(source, /worker\.work_suitabilities/)
  assert.match(source, /worker\.passive_skills/)
  assert.match(source, /\.worker-pal:hover \.worker-pal-tooltip/)
  assert.match(source, /\.worker-pal:focus-visible \.worker-pal-tooltip/)
  assert.match(source, /Guild_NoWorkingPals/)
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
