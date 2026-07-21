import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const palListPath = fileURLToPath(
  new URL('../src/components/PalList.vue', import.meta.url),
)
const localePaths = ['en', 'fr', 'ja', 'ko', 'zh-CN'].map(locale => fileURLToPath(
  new URL(`../src/i18n/${locale}.js`, import.meta.url),
))

test('expedition unlock action is immediately left of heal all', () => {
  const source = readFileSync(palListPath, 'utf8')
  const unlock = source.indexOf('@click="palStore.unlockExpeditionPals"')
  const heal = source.indexOf('@click="palStore.healAllPals"')

  assert.ok(unlock >= 0, 'Pal list must expose the expedition unlock action')
  assert.ok(heal >= 0, 'Pal list must retain the heal-all action')
  assert.ok(unlock < heal, 'Expedition unlock must be left of heal all')
  assert.match(source, /palStore\.EXPEDITION_PAL_COUNT === 0/)
})

test('disabled expedition unlock action visibly explains that there are no targets', () => {
  const source = readFileSync(palListPath, 'utf8')

  assert.match(source, /TopBar_Btn_UnlockExpeditionPals_Disabled/)
  assert.match(source, /\.heal-all:disabled\s*\{[^}]*opacity:/s)
  assert.match(source, /\.heal-all:disabled\s*\{[^}]*cursor:\s*not-allowed/s)
})

test('all supported locales describe the expedition unlock action', () => {
  for (const localePath of localePaths) {
    const source = readFileSync(localePath, 'utf8')
    assert.match(source, /TopBar_Btn_UnlockExpeditionPals:/)
    assert.match(source, /TopBar_Btn_UnlockExpeditionPals_Disabled:/)
    assert.match(source, /TopBar_Btn_UnlockExpeditionPals_Tooltips:/)
  }
})
