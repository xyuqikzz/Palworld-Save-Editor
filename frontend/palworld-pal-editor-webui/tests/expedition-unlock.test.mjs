import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const palListPath = fileURLToPath(
  new URL('../src/components/PalList.vue', import.meta.url),
)
const topBarPath = fileURLToPath(
  new URL('../src/components/TopBar.vue', import.meta.url),
)
const palEditorPath = fileURLToPath(
  new URL('../src/components/PalEditor.vue', import.meta.url),
)
const localePaths = ['en', 'fr', 'ja', 'ko', 'zh-CN'].map(locale => fileURLToPath(
  new URL(`../src/i18n/${locale}.js`, import.meta.url),
))

test('global expedition and heal actions are immediately left of out-of-box filter', () => {
  const source = readFileSync(topBarPath, 'utf8')
  const palListSource = readFileSync(palListPath, 'utf8')
  const complete = source.indexOf('@click="palStore.completeActiveExpeditions"')
  const unlock = source.indexOf('@click="palStore.unlockExpeditionPals"')
  const heal = source.indexOf('@click="palStore.healAllPals"')
  const outOfBox = source.indexOf('@click="palStore.SHOW_OOB_PAL_FLAG = !palStore.SHOW_OOB_PAL_FLAG"')

  assert.ok(complete >= 0, 'Top bar must expose the expedition completion action')
  assert.ok(unlock >= 0, 'Top bar must expose the expedition unlock action')
  assert.ok(heal >= 0, 'Top bar must expose the heal-all action')
  assert.ok(outOfBox >= 0, 'Top bar must retain the out-of-box filter')
  assert.ok(complete < unlock, 'Expedition completion must be left of expedition unlock')
  assert.ok(unlock < heal, 'Expedition unlock must be left of heal all')
  assert.ok(heal < outOfBox, 'Both global actions must be left of the out-of-box filter')
  assert.match(source, /palStore\.EXPEDITION_PAL_COUNT === 0/)
  assert.doesNotMatch(palListSource, /unlockExpeditionPals|healAllPals/)
})

test('disabled expedition unlock action visibly explains that there are no targets', () => {
  const source = readFileSync(topBarPath, 'utf8')

  assert.match(source, /TopBar_Btn_UnlockExpeditionPals_Disabled/)
  assert.match(source, /\.op:disabled,[\s\S]*?opacity:\s*0\.5/s)
  assert.match(source, /\.op:disabled,[\s\S]*?cursor:\s*not-allowed/s)
})

test('all supported locales describe the expedition unlock action', () => {
  for (const localePath of localePaths) {
    const source = readFileSync(localePath, 'utf8')
    assert.match(source, /TopBar_Btn_UnlockExpeditionPals:/)
    assert.match(source, /TopBar_Btn_CompleteExpeditions:/)
    assert.match(source, /TopBar_Btn_CompleteExpeditions_Disabled:/)
    assert.match(source, /TopBar_Btn_CompleteExpeditions_Tooltips:/)
    assert.match(source, /Confirm_CompleteActiveExpeditions:/)
    assert.match(source, /TopBar_Btn_UnlockExpeditionPals_Disabled:/)
    assert.match(source, /TopBar_Btn_UnlockExpeditionPals_Tooltips:/)
    assert.match(source, /Expedition_Status_Valid:/)
    assert.match(source, /Expedition_Status_Invalid:/)
    assert.match(source, /Expedition_Status_Unknown:/)
    assert.match(source, /PalEditor_CancelExpedition:/)
    assert.match(source, /Confirm_CancelValidExpedition:/)
  }
})

test('Pal list and detail editor expose expedition status and single-Pal unlock', () => {
  const palListSource = readFileSync(palListPath, 'utf8')
  const palEditorSource = readFileSync(palEditorPath, 'utf8')

  assert.match(palListSource, /ExpeditionAssignmentStatus/)
  assert.match(palListSource, /Expedition_Status_Valid/)
  assert.match(palListSource, /Expedition_Status_Invalid/)
  assert.match(palEditorSource, /cancelSelectedPalExpedition/)
  assert.match(palEditorSource, /PalEditor_CancelExpedition/)
})
