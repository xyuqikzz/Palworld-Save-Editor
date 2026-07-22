import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

import en from '../src/i18n/en.js'
import fr from '../src/i18n/fr.js'
import ja from '../src/i18n/ja.js'
import ko from '../src/i18n/ko.js'
import zhCN from '../src/i18n/zh-CN.js'

const picker = await readFile(
  new URL('../src/components/modules/PalSkillPicker.vue', import.meta.url),
  'utf8',
)
const card = await readFile(
  new URL('../src/components/modules/PassiveSkillCard.vue', import.meta.url),
  'utf8',
)

test('gold passive ratings have distinct labels in every interface language', () => {
  assert.match(
    picker,
    /\{ value: '3', label: palStore\.getTranslatedText\('Editor_Passive_Filter_Gold2'\) \}/,
  )
  assert.match(
    picker,
    /\{ value: '2', label: palStore\.getTranslatedText\('Editor_Passive_Filter_Gold1'\) \}/,
  )

  for (const [dictionary, gold1, gold2] of [
    [en, 'Gold 1', 'Gold 2'],
    [fr, 'Or 1', 'Or 2'],
    [ja, '金色1', '金色2'],
    [ko, '금색1', '금색2'],
    [zhCN, '金色1', '金色2'],
  ]) {
    assert.equal(dictionary.Editor_Passive_Filter_Gold1, gold1)
    assert.equal(dictionary.Editor_Passive_Filter_Gold2, gold2)
  }
})

test('rating 2 passives reuse rating 3 gold styling in picker and shared cards', () => {
  assert.match(
    picker,
    /\.pal-passive-option\.is-rank-3 \.pal-passive-option__banner,\s*\.pal-passive-option\.is-rank-2 \.pal-passive-option__banner\s*\{/,
  )
  assert.match(
    picker,
    /\.pal-passive-option\.is-rank-3 \.pal-passive-option__banner strong,\s*\.pal-passive-option\.is-rank-2 \.pal-passive-option__banner strong\s*\{/,
  )
  assert.match(
    picker,
    /\.pal-passive-option\.is-rank-3 \.pal-passive-option__banner img,\s*\.pal-passive-option\.is-rank-2 \.pal-passive-option__banner img\s*\{/,
  )

  assert.match(
    card,
    /\.passive-skill-card\.is-rank-3 \.passive-skill-banner,\s*\.passive-skill-card\.is-rank-2 \.passive-skill-banner\s*\{/,
  )
  assert.match(
    card,
    /\.passive-skill-card\.is-rank-3 \.passive-skill-name,\s*\.passive-skill-card\.is-rank-2 \.passive-skill-name\s*\{/,
  )
  assert.match(
    card,
    /\.passive-skill-card\.is-rank-3 \.passive-rank-icon,\s*\.passive-skill-card\.is-rank-2 \.passive-rank-icon\s*\{/,
  )
})
