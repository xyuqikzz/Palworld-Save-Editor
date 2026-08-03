import test from 'node:test'
import assert from 'node:assert/strict'

import axios from 'axios'
import { createPinia, setActivePinia } from 'pinia'

globalThis.alert = () => {}
globalThis.confirm = () => true
globalThis.window = { confirm: () => true }
globalThis.localStorage = { getItem: () => null, setItem: () => {} }

const { usePalEditorStore } = await import('../src/stores/paleditor.js')

test('passive skill edits do not revalidate unrelated active skills', async () => {
  setActivePinia(createPinia())
  const store = usePalEditorStore()
  const palId = 'pal-1'
  const pal = {
    InstanceId: palId,
    EquipWaza: ['EPalWazaID::AquaJet'],
    MasteredWaza: [],
    PassiveSkillList: ['Rare'],
  }
  const player = { pals: new Map([[palId, pal]]) }
  store.SESSION_ID = 'session-1'
  store.SESSION_REVISION = 0
  store.SELECTED_PLAYER_ID = 'player-1'
  store.PLAYER_MAP = new Map([['player-1', player]])
  store.PAL_MAP = player.pals

  let resolveSkillRequest
  const skillRequestReceived = new Promise(resolve => {
    resolveSkillRequest = resolve
  })
  axios.post = async (url, data) => {
    if (url.includes('/commands')) {
      resolveSkillRequest(data)
      return { data: { status: 0, data: { revision: 1 } } }
    }
    if (url === '/api/pal/paldata') return { data: { status: 0, data: pal } }
    throw new Error(`unexpected ${url}`)
  }

  await store.selectPal(palId, true)
  store.SELECTED_PAL_DATA.pop_PassiveSkillList({
    target: {},
    currentTarget: { name: 'Rare' },
  })
  const skillRequest = await skillRequestReceived

  assert.equal(skillRequest.active, null)
  assert.equal(skillRequest.mastered, null)
  assert.deepEqual(skillRequest.passive, [])
})

test('cheat mode allows a fifth duplicate passive and marks the request unrestricted', async () => {
  setActivePinia(createPinia())
  const store = usePalEditorStore()
  const palId = 'pal-passive-cheat'
  const pal = {
    InstanceId: palId,
    EquipWaza: [],
    MasteredWaza: [],
    PassiveSkillList: ['Rare', 'Legend', 'Rare', 'Legend'],
  }
  const player = { pals: new Map([[palId, pal]]) }
  store.SESSION_ID = 'session-1'
  store.SESSION_REVISION = 0
  store.SELECTED_PLAYER_ID = 'player-1'
  store.PLAYER_MAP = new Map([['player-1', player]])
  store.PAL_MAP = player.pals
  store.PASSIVE_SKILLS = { Rare: { InternalName: 'Rare' } }
  store.HIDE_INVALID_OPTIONS = false

  let resolveSkillRequest
  const skillRequestReceived = new Promise(resolve => {
    resolveSkillRequest = resolve
  })
  axios.post = async (url, data) => {
    if (url.includes('/commands')) {
      pal.PassiveSkillList = [...data.passive]
      resolveSkillRequest(data)
      return { data: { status: 0, data: { revision: 1 } } }
    }
    if (url === '/api/pal/paldata') return { data: { status: 0, data: pal } }
    throw new Error(`unexpected ${url}`)
  }

  await store.selectPal(palId, true)
  store.SELECTED_PAL_DATA.add_PassiveSkillList('Rare')
  const skillRequest = await skillRequestReceived

  assert.equal(skillRequest.unrestricted, true)
  assert.deepEqual(skillRequest.passive, ['Rare', 'Legend', 'Rare', 'Legend', 'Rare'])
})

test('duplicate passive removal targets the selected occurrence by index', async () => {
  setActivePinia(createPinia())
  const store = usePalEditorStore()
  const palId = 'pal-passive-remove'
  const pal = {
    InstanceId: palId,
    EquipWaza: [],
    MasteredWaza: [],
    PassiveSkillList: ['Rare', 'Legend', 'Rare'],
  }
  const player = { pals: new Map([[palId, pal]]) }
  store.SESSION_ID = 'session-1'
  store.SESSION_REVISION = 0
  store.SELECTED_PLAYER_ID = 'player-1'
  store.PLAYER_MAP = new Map([['player-1', player]])
  store.PAL_MAP = player.pals
  store.HIDE_INVALID_OPTIONS = false

  let resolveSkillRequest
  const skillRequestReceived = new Promise(resolve => {
    resolveSkillRequest = resolve
  })
  axios.post = async (url, data) => {
    if (url.includes('/commands')) {
      resolveSkillRequest(data)
      return { data: { status: 0, data: { revision: 1 } } }
    }
    if (url === '/api/pal/paldata') return { data: { status: 0, data: pal } }
    throw new Error(`unexpected ${url}`)
  }

  await store.selectPal(palId, true)
  store.SELECTED_PAL_DATA.pop_PassiveSkillList('Rare', 2)
  const skillRequest = await skillRequestReceived

  assert.deepEqual(skillRequest.passive, ['Rare', 'Legend'])
  assert.equal(skillRequest.unrestricted, true)
})

test('active skill removal uses the button name when its icon is clicked', async () => {
  setActivePinia(createPinia())
  const store = usePalEditorStore()
  const palId = 'pal-2'
  const pal = {
    InstanceId: palId,
    EquipWaza: ['EPalWazaID::AquaJet', 'EPalWazaID::WaterGun'],
    MasteredWaza: [],
    PassiveSkillList: [],
  }
  const player = { pals: new Map([[palId, pal]]) }
  store.SESSION_ID = 'session-1'
  store.SESSION_REVISION = 0
  store.SELECTED_PLAYER_ID = 'player-1'
  store.PLAYER_MAP = new Map([['player-1', player]])
  store.PAL_MAP = player.pals

  let resolveSkillRequest
  const skillRequestReceived = new Promise(resolve => {
    resolveSkillRequest = resolve
  })
  axios.post = async (url, data) => {
    if (url.includes('/commands')) {
      resolveSkillRequest(data)
      return { data: { status: 0, data: { revision: 1 } } }
    }
    if (url === '/api/pal/paldata') return { data: { status: 0, data: pal } }
    throw new Error(`unexpected ${url}`)
  }

  await store.selectPal(palId, true)
  store.SELECTED_PAL_DATA.pop_EquipWaza({
    target: {},
    currentTarget: { name: 'EPalWazaID::AquaJet' },
  })
  const skillRequest = await skillRequestReceived

  assert.deepEqual(skillRequest.active, ['EPalWazaID::WaterGun'])
  assert.deepEqual(skillRequest.mastered, [])
})

test('equipping from the mastered-skill picker accepts the selected skill id', async () => {
  setActivePinia(createPinia())
  const store = usePalEditorStore()
  const palId = 'pal-3'
  const skillId = 'EPalWazaID::AquaJet'
  const pal = {
    InstanceId: palId,
    EquipWaza: [],
    MasteredWaza: [skillId],
    PassiveSkillList: [],
  }
  const player = { pals: new Map([[palId, pal]]) }
  store.SESSION_ID = 'session-1'
  store.SESSION_REVISION = 0
  store.SELECTED_PLAYER_ID = 'player-1'
  store.PLAYER_MAP = new Map([['player-1', player]])
  store.PAL_MAP = player.pals

  let resolveSkillRequest
  const skillRequestReceived = new Promise(resolve => {
    resolveSkillRequest = resolve
  })
  axios.post = async (url, data) => {
    if (url.includes('/commands')) {
      resolveSkillRequest(data)
      return { data: { status: 0, data: { revision: 1 } } }
    }
    if (url === '/api/pal/paldata') return { data: { status: 0, data: pal } }
    throw new Error(`unexpected ${url}`)
  }

  await store.selectPal(palId, true)
  store.SELECTED_PAL_DATA.add_EquipWaza(skillId)
  const skillRequest = await skillRequestReceived

  assert.deepEqual(skillRequest.active, [skillId])
  assert.deepEqual(skillRequest.mastered, [skillId])
})

test('adding a unique active skill warns before changing the Pal', async () => {
  setActivePinia(createPinia())
  const store = usePalEditorStore()
  const palId = 'pal-4'
  const skillId = 'EPalWazaID::UniqueSkill'
  const pal = {
    InstanceId: palId,
    EquipWaza: [],
    MasteredWaza: [],
    PassiveSkillList: [],
  }
  const player = { pals: new Map([[palId, pal]]) }
  store.SESSION_ID = 'session-1'
  store.SESSION_REVISION = 0
  store.SELECTED_PLAYER_ID = 'player-1'
  store.PLAYER_MAP = new Map([['player-1', player]])
  store.PAL_MAP = player.pals
  store.ACTIVE_SKILLS = {
    [skillId]: {
      InternalName: skillId,
      I18n: ['Unique Skill'],
      IsUniqueSkill: true,
    },
  }

  let confirmMessage = ''
  let commandSent = false
  window.confirm = message => {
    confirmMessage = message
    return false
  }
  axios.post = async url => {
    if (url.includes('/commands')) commandSent = true
    if (url === '/api/pal/paldata') return { data: { status: 0, data: pal } }
    throw new Error(`unexpected ${url}`)
  }

  await store.selectPal(palId, true)
  store.SELECTED_PAL_DATA.add_MasteredWaza(skillId)

  assert.match(confirmMessage, /Unique Skill/)
  assert.equal(commandSent, false)
  assert.deepEqual(store.SELECTED_PAL_DATA.MasteredWaza, [])
})

test('adding a regular active skill does not show the unique-skill warning', async () => {
  setActivePinia(createPinia())
  const store = usePalEditorStore()
  const palId = 'pal-5'
  const skillId = 'EPalWazaID::RegularSkill'
  const pal = {
    InstanceId: palId,
    EquipWaza: [],
    MasteredWaza: [],
    PassiveSkillList: [],
  }
  const player = { pals: new Map([[palId, pal]]) }
  store.SESSION_ID = 'session-1'
  store.SESSION_REVISION = 0
  store.SELECTED_PLAYER_ID = 'player-1'
  store.PLAYER_MAP = new Map([['player-1', player]])
  store.PAL_MAP = player.pals
  store.ACTIVE_SKILLS = {
    [skillId]: {
      InternalName: skillId,
      I18n: ['Regular Skill'],
      IsUniqueSkill: false,
    },
  }

  let confirmCalled = false
  let resolveSkillRequest
  const skillRequestReceived = new Promise(resolve => {
    resolveSkillRequest = resolve
  })
  window.confirm = () => {
    confirmCalled = true
    return true
  }
  axios.post = async (url, data) => {
    if (url.includes('/commands')) {
      resolveSkillRequest(data)
      return { data: { status: 0, data: { revision: 1 } } }
    }
    if (url === '/api/pal/paldata') return { data: { status: 0, data: pal } }
    throw new Error(`unexpected ${url}`)
  }

  await store.selectPal(palId, true)
  store.SELECTED_PAL_DATA.add_MasteredWaza(skillId)
  const skillRequest = await skillRequestReceived

  assert.equal(confirmCalled, false)
  assert.deepEqual(skillRequest.mastered, [skillId])
})
