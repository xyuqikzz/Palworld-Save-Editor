import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

import en from '../src/i18n/en.js'
import fr from '../src/i18n/fr.js'
import ja from '../src/i18n/ja.js'
import ko from '../src/i18n/ko.js'
import zhCN from '../src/i18n/zh-CN.js'

test('add Pal picker exposes shared passive presets and both maximum options', async () => {
  const list = await readFile(new URL('../src/components/PalList.vue', import.meta.url), 'utf8')
  const picker = await readFile(new URL('../src/components/modules/PalSpeciesPicker.vue', import.meta.url), 'utf8')

  assert.match(list, /createDefaultPassivePresets/)
  assert.match(list, /loadPassivePresets\(globalThis\.localStorage/)
  assert.match(list, /<template #footer>/)
  assert.match(list, /PalEditor_MaxPal/)
  assert.match(list, /PalList_AddMaxWork/)
  assert.match(list, /function updateAddMaxPal\(selected\)[\s\S]*?if \(selected\) addMaxWork\.value = false/)
  assert.match(list, /function updateAddMaxWork\(selected\)[\s\S]*?if \(selected\) addMaxPal\.value = false/)
  assert.match(list, /passive:\s*passivePreset \? \[\.\.\.passivePreset\.skills\] : null/)
  assert.match(picker, /<slot name="footer"/)
  assert.match(picker, /pal-species-dialog__surface\.has-footer/)
})

test('add Pal creation preset labels are fully localized', () => {
  const keys = [
    'PalList_AddPresets_Title',
    'PalList_AddPresets_Description',
    'PalList_AddPassivePreset',
    'PalList_AddPassivePreset_None',
    'PalList_AddPassivePreset_Empty',
    'PalList_AddMaxWork',
    'PalList_AddMaxWork_Tooltip',
  ]
  for (const messages of [en, fr, ja, ko, zhCN]) {
    for (const key of keys) {
      assert.equal(typeof messages[key], 'string')
      assert.ok(messages[key].length > 0)
    }
  }
  assert.equal(zhCN.PalList_AddMaxWork, 'MAX工作')
})
