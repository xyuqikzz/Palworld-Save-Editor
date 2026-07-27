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
const expeditionViewPath = fileURLToPath(
  new URL('../src/views/ExpeditionView.vue', import.meta.url),
)
const palEditorPath = fileURLToPath(
  new URL('../src/components/PalEditor.vue', import.meta.url),
)
const palStorePath = fileURLToPath(
  new URL('../src/stores/paleditor.js', import.meta.url),
)
const localePaths = ['en', 'fr', 'ja', 'ko', 'zh-CN'].map(locale => fileURLToPath(
  new URL(`../src/i18n/${locale}.js`, import.meta.url),
))

test('the expedition page puts only expedition batch actions above the active list', () => {
  const source = readFileSync(expeditionViewPath, 'utf8')
  const topBarSource = readFileSync(topBarPath, 'utf8')
  const palListSource = readFileSync(palListPath, 'utf8')
  const complete = source.indexOf('@click="palStore.completeActiveExpeditions"')
  const unlock = source.indexOf('@click="palStore.unlockExpeditionPals"')
  const heal = source.indexOf('@click="palStore.healAllPals"')
  const activeList = source.indexOf('class="expedition-content"')
  const outOfBox = topBarSource.indexOf('Settings_ShowOobPals')

  assert.ok(complete >= 0, 'Expedition page must expose the completion action')
  assert.ok(unlock >= 0, 'Expedition page must expose the unlock action')
  assert.equal(heal, -1, 'Expedition page must not expose the heal-all action')
  assert.ok(outOfBox >= 0, 'Settings must retain the out-of-box filter')
  assert.ok(complete < unlock, 'Expedition completion must precede expedition unlock')
  assert.ok(unlock < activeList, 'Batch actions must appear above the active expedition list')
  assert.doesNotMatch(source, /Expedition_(?:Eyebrow|Title|Description)/)
  assert.match(source, /palStore\.EXPEDITION_PAL_COUNT === 0/)
  assert.doesNotMatch(palListSource, /unlockExpeditionPals|healAllPals/)
})

test('disabled expedition unlock action visibly explains that there are no targets', () => {
  const source = readFileSync(expeditionViewPath, 'utf8')

  assert.match(source, /TopBar_Btn_UnlockExpeditionPals_Disabled/)
  assert.match(source, /\.operation-button:disabled\s*\{[^}]*opacity:\s*0\.45[^}]*cursor:\s*not-allowed/s)
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

test('bulk expedition unlock uses one whole-save command and refreshes expedition data', () => {
  const source = readFileSync(palStorePath, 'utf8')
  const start = source.indexOf('async function unlockExpeditionPals()')
  const end = source.indexOf('function applyCompletedExpeditions', start)
  const unlockSource = source.slice(start, end)

  assert.ok(start >= 0 && end > start)
  assert.match(unlockSource, /\/api\/save\/pals\/commands/)
  assert.match(unlockSource, /command:\s*"unlock_all_expedition_pals"/)
  assert.match(unlockSource, /await loadExpeditions\(\)/)
  assert.doesNotMatch(unlockSource, /executeBatchOperations/)
})

test('expedition page lists every active record with ownership, members, invalid locks, and row completion', () => {
  const source = readFileSync(expeditionViewPath, 'utf8')

  assert.match(source, /palStore\.loadExpeditions/)
  assert.match(source, /palStore\.EXPEDITION_DATA\.expeditions/)
  assert.match(source, /expedition\.guild_name/)
  assert.match(source, /expedition\.base_number/)
  assert.match(source, /expedition\.members/)
  assert.match(source, /invalid_locked_pals/)
  assert.match(source, /unknown_locked_pals/)
  assert.match(source, /palStore\.completeExpedition\(expedition\.expedition_id\)/)
})

test('all supported locales describe expedition ownership and row completion', () => {
  for (const localePath of localePaths) {
    const source = readFileSync(localePath, 'utf8')
    assert.match(source, /Expedition_ActiveTitle:/)
    assert.match(source, /Expedition_InvalidLockedTitle:/)
    assert.match(source, /Expedition_QuickComplete:/)
    assert.match(source, /Confirm_CompleteExpedition:/)
  }
})
