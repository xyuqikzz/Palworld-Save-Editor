import test from 'node:test'
import assert from 'node:assert/strict'
import axios from 'axios'
import { createPinia, setActivePinia } from 'pinia'

globalThis.alert = () => {}
globalThis.localStorage = { getItem: () => null, setItem: () => {} }
const { usePalEditorStore } = await import('../src/stores/paleditor.js')

test('experimental level sends explicit mode and exact XP for players, Pals and Global Palbox', async () => {
  setActivePinia(createPinia())
  const store = usePalEditorStore()
  store.SESSION_ID = 'world'
  store.SESSION_REVISION = 3
  store.SELECTED_PLAYER_ID = 'player'
  store.SELECTED_PAL_ID = 'pal'
  const requests = []
  const capture = async (url, data) => {
    requests.push({ url, data: JSON.parse(JSON.stringify(data)) })
    return { data: { status: 1, msg: 'captured' } }
  }
  axios.post = capture
  axios.patch = capture
  await store.setExperimentalLevel('player', 101, 123456)
  await store.setExperimentalLevel('pal', 255, 789012)
  store.GLOBAL_PALBOX_SESSION = { session_id: 'global', revision: 7 }
  await store.setExperimentalLevel('pal', 102, 456789)
  assert.equal(requests.length, 3)
  assert.equal(requests[0].data.experimental_level, true)
  assert.equal(requests[0].data.level, 101)
  assert.equal(requests[0].data.experience, 123456)
  assert.deepEqual(requests[1].data.values, { level: 255, experience: 789012 })
  assert.equal(requests[1].data.experimental_level, true)
  assert.deepEqual(requests[2].data.values, { level: 102, experience: 456789, experimental_level: true })
  assert.equal(requests[2].data.session_id, 'global')
  assert.equal(store.LOADING_FLAG, false)
})

test('experimental level refuses missing, fractional or imprecise input before sending', async () => {
  setActivePinia(createPinia())
  const store = usePalEditorStore()
  store.SESSION_ID = 'world'
  store.SELECTED_PAL_ID = 'pal'
  axios.post = async () => { assert.fail('invalid edit must not be sent') }
  for (const [level, xp] of [[256, 0], [0, 0], [101.5, 5], [101, ''], [101, null], [101, -1], [101, 2**53]]) {
    assert.equal(await store.setExperimentalLevel('pal', level, xp), false)
  }
  assert.equal(store.MAX_LEVEL, 80)
  assert.equal(store.MAX_INVALID_LEVEL, 100)
})


test('unknown expedition references block both single and bulk unlock', async () => {
  setActivePinia(createPinia())
  const store = usePalEditorStore()
  store.SESSION_ID = 'world'
  store.SELECTED_PAL_ID = 'pal'
  const pal = { IsExpeditionPal: true, ExpeditionAssignmentStatus: 'unknown' }
  store.SELECTED_PAL_DATA = pal
  store.PAL_MAP = new Map([['pal', pal]])
  axios.post = async () => { assert.fail('unknown references must not be edited') }
  assert.equal(await store.cancelSelectedPalExpedition(), false)
  assert.equal(await store.unlockExpeditionPals(), false)
  assert.equal(pal.IsExpeditionPal, true)
  assert.equal(store.LAST_ERROR.code, 'EXPEDITION_INDEX_UNAVAILABLE')
})
