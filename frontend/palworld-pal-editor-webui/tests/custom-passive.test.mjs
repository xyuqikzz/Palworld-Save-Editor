import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

import axios from 'axios'
import { createPinia, setActivePinia } from 'pinia'

globalThis.alert = () => {}
globalThis.confirm = () => true
globalThis.window = { confirm: () => true }
globalThis.localStorage = { getItem: () => null, setItem: () => {} }

const { usePalEditorStore } = await import('../src/stores/paleditor.js')

test('custom passive uses the explicit revision-bound passive-only request', async () => {
  setActivePinia(createPinia())
  const store = usePalEditorStore()
  const palId = 'pal-custom-1'
  const custom = 'OtherMod_FrontendPassive_Exact'
  const pal = {
    InstanceId: palId,
    EquipWaza: ['EPalWazaID::AquaJet'],
    MasteredWaza: [],
    PassiveSkillList: ['OtherMod_ExistingPassive'],
  }
  const player = { pals: new Map([[palId, pal]]) }
  store.SESSION_ID = 'session-custom-1'
  store.SESSION_REVISION = 7
  store.SELECTED_PLAYER_ID = 'player-1'
  store.PLAYER_MAP = new Map([['player-1', player]])
  store.PAL_MAP = player.pals

  let commandUrl = ''
  let commandPayload = null
  axios.post = async (url, data) => {
    if (url.includes('/commands')) {
      commandUrl = url
      commandPayload = data
      pal.PassiveSkillList = [...data.passive]
      return { data: { status: 0, data: { revision: 8 } } }
    }
    if (url === '/api/pal/paldata') {
      return { data: { status: 0, data: pal } }
    }
    throw new Error(`unexpected ${url}`)
  }

  await store.selectPal(palId, true)
  store.HIDE_INVALID_OPTIONS = false
  const accepted = await store.addCustomPassive(custom)

  assert.equal(accepted, true)
  assert.equal(commandUrl, `/api/pal/${palId}/commands`)
  assert.equal(commandPayload.session_id, 'session-custom-1')
  assert.equal(commandPayload.expected_revision, 7)
  assert.equal(commandPayload.command, 'update_pal_skills')
  assert.equal(commandPayload.allow_custom_passive, true)
  assert.equal(commandPayload.unrestricted, true)
  assert.equal(commandPayload.active, null)
  assert.equal(commandPayload.mastered, null)
  assert.deepEqual(commandPayload.passive, [
    'OtherMod_ExistingPassive',
    custom,
  ])
  assert.equal(store.SESSION_REVISION, 8)
})

test('custom passive entry is separate and unknown cards do not invent metadata', async () => {
  const [editor, dialog, card] = await Promise.all([
    readFile(new URL('../src/components/PalEditor.vue', import.meta.url), 'utf8'),
    readFile(
      new URL(
        '../src/components/modules/CustomPassiveDialog.vue',
        import.meta.url,
      ),
      'utf8',
    ),
    readFile(
      new URL(
        '../src/components/modules/PassiveSkillCard.vue',
        import.meta.url,
      ),
      'utf8',
    ),
  ])

  assert.match(editor, /<CustomPassiveDialog[\s\S]*?@add="addCustomPassive"/)
  assert.match(editor, /class="custom-passive-trigger"/)
  assert.match(editor, /<PalSkillPicker[\s\S]*?:options="palStore\.PASSIVE_SKILLS_LIST"/)
  assert.match(editor, /const passivePresetIsAvailable = preset => preset\.skills\.every\(skill => palStore\.PASSIVE_SKILLS\[skill\]\)/)

  assert.match(dialog, /v-model="internalName"[\s\S]*?maxlength="128"/)
  assert.match(dialog, /v-model="riskAccepted"[\s\S]*?type="checkbox"/)
  assert.match(dialog, /PalEditor_CustomPassive_RiskModInstalled/)
  assert.match(dialog, /PalEditor_CustomPassive_RiskSemantics/)
  assert.match(dialog, /PalEditor_CustomPassive_RiskWrongId/)
  assert.match(dialog, /Boolean\(internalName\.value\.trim\(\)\)[\s\S]*?riskAccepted\.value/)

  assert.match(card, /<span v-if="!skill" class="passive-skill-unknown">\{\{ unknownLabel \}\}<\/span>/)
  assert.match(card, /<img v-else class="passive-rank-icon"/)
  assert.doesNotMatch(
    card,
    /props\.fallbackDescription \|\| props\.internalName/,
  )
})
