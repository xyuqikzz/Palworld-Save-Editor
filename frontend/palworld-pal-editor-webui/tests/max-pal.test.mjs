import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import axios from 'axios'
import { createPinia, setActivePinia } from 'pinia'

import en from '../src/i18n/en.js'
import fr from '../src/i18n/fr.js'
import ja from '../src/i18n/ja.js'
import ko from '../src/i18n/ko.js'
import zhCN from '../src/i18n/zh-CN.js'

globalThis.alert = () => {}
globalThis.localStorage = {
  getItem: () => null,
  setItem: () => {},
}

const editorSource = readFileSync(
  fileURLToPath(new URL('../src/components/PalEditor.vue', import.meta.url)),
  'utf8',
)
const { usePalEditorStore } = await import('../src/stores/paleditor.js')

test('MAX Pal button is immediately left of export data and fully localized', () => {
  assert.match(
    editorSource,
    /class="max-pal-button"[\s\S]*?maxSelectedPal[\s\S]*?PalEditor_MaxPal[\s\S]*?<button id="dump_btn"/,
  )
  for (const messages of [en, fr, ja, ko, zhCN]) {
    assert.equal(typeof messages.PalEditor_MaxPal, 'string')
    assert.ok(messages.PalEditor_MaxPal.length > 0)
    assert.equal(typeof messages.PalEditor_MaxPal_Tooltip, 'string')
    assert.ok(messages.PalEditor_MaxPal_Tooltip.length > 0)
    assert.equal(typeof messages.PalEditor_TrustBonus_Tooltip, 'string')
    assert.ok(messages.PalEditor_TrustBonus_Tooltip.length > 0)
  }
  assert.equal(zhCN.PalEditor_MaxPal, 'MAX帕鲁')
  assert.match(
    editorSource,
    /PalEditor_TrustBonus_Tooltip[\s\S]*?Editor_Friendship_Level/,
  )
  const friendshipIndex = editorSource.indexOf('Editor_Friendship_Level')
  assert.ok(
    friendshipIndex
      < editorSource.indexOf('v-if="!palStore.SELECTED_PAL_DATA.IsHuman"', friendshipIndex),
    'trust controls must remain available to human NPC Pals',
  )
})

test('MAX Pal sends one domain command with the current safety mode', async () => {
  setActivePinia(createPinia())
  const store = usePalEditorStore()
  const palId = 'pal-max-1'
  const playerId = 'player-max-1'
  const palData = {
    InstanceId: palId,
    DataAccessKey: 'SheepBall',
    Rank: 1,
    PassiveSkillList: [],
    EquipWaza: [],
    MasteredWaza: [],
    Suitabilities: {},
  }
  const palMap = new Map([[palId, palData]])

  store.PAL_MAP = palMap
  store.PLAYER_MAP = new Map([[playerId, { pals: palMap }]])
  store.SELECTED_PLAYER_ID = playerId
  store.SESSION_ID = 'session-max-1'
  store.SESSION_REVISION = 7

  axios.post = async () => ({ data: { status: 0, data: palData } })
  await store.selectPal(palId)

  const requests = []
  axios.post = async (url, data) => {
    requests.push({ url, data: JSON.parse(JSON.stringify(data)) })
    return { data: { status: 1, msg: 'captured by test' } }
  }

  store.HIDE_INVALID_OPTIONS = true
  await store.maxSelectedPal()
  store.HIDE_INVALID_OPTIONS = false
  await store.maxSelectedPal()

  assert.equal(requests.length, 2)
  assert.equal(requests[0].url, `/api/pal/${palId}/commands`)
  assert.deepEqual(requests[0].data, {
    session_id: 'session-max-1',
    expected_revision: 7,
    command: 'max_pal',
    unrestricted: false,
  })
  assert.equal(requests[1].data.unrestricted, true)
})
