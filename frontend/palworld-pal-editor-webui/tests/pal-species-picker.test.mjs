import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import {
  availablePalElements,
  filterSpeciesOptions,
} from '../src/components/modules/pal-species-filter.js'

const pickerPath = fileURLToPath(
  new URL('../src/components/modules/PalSpeciesPicker.vue', import.meta.url),
)
const palListPath = fileURLToPath(
  new URL('../src/components/PalList.vue', import.meta.url),
)
const saveApiPath = fileURLToPath(
  new URL('../../../src/palworld_pal_editor/api/save.py', import.meta.url),
)
const localePaths = ['en', 'fr', 'ja', 'ko', 'zh-CN'].map(locale => fileURLToPath(
  new URL(`../src/i18n/${locale}.js`, import.meta.url),
))

const options = [
  { InternalName: 'SheepBall', I18n: 'Lamball', SortingKey: 1, Elements: ['Neutral'], IsHuman: false },
  { InternalName: 'Kitsunebi', I18n: 'Foxparks', SortingKey: 5, Elements: ['Fire'], IsHuman: false },
  { InternalName: 'BOSS_FireCult_FlameThrower', I18n: 'Martyr', Elements: [], IsHuman: true },
]

test('species filtering separates Pals and NPCs and filters Pals by element', () => {
  assert.deepEqual(availablePalElements(options), ['Neutral', 'Fire'])
  assert.deepEqual(
    filterSpeciesOptions(options, { category: 'pal', element: 'Fire', query: '' })
      .map(option => option.InternalName),
    ['Kitsunebi'],
  )
  assert.deepEqual(
    filterSpeciesOptions(options, { category: 'npc', element: 'Fire', query: 'martyr' })
      .map(option => option.InternalName),
    ['BOSS_FireCult_FlameThrower'],
  )
  assert.deepEqual(
    filterSpeciesOptions(options, { category: 'pal', query: '#001' })
      .map(option => option.InternalName),
    ['SheepBall'],
  )
})

test('the common species picker renders category tabs and an element filter', () => {
  const source = readFileSync(pickerPath, 'utf8')

  assert.match(source, /class="pal-species-tabs"[\s\S]*?role="tablist"/)
  assert.match(source, /activeCategory === 'pal'[\s\S]*?PalSpeciesPicker_Pals/)
  assert.match(source, /activeCategory === 'npc'[\s\S]*?PalSpeciesPicker_Npcs/)
  assert.match(source, /class="pal-species-element-filters"[\s\S]*?activeElementFilter/)
  assert.match(source, /pal\?\.IsHuman[\s\S]*?pal\.HasIcon[\s\S]*?pal\.InternalName/)

  for (const localePath of localePaths) {
    const locale = readFileSync(localePath, 'utf8')
    assert.match(locale, /PalSpeciesPicker_Pals:/, localePath)
    assert.match(locale, /PalSpeciesPicker_Npcs:/, localePath)
    assert.match(locale, /PalSpeciesPicker_CategoryLabel:/, localePath)
    assert.match(locale, /PalSpeciesPicker_ElementFilterLabel:/, localePath)
  }
})

test('the add flow exposes synchronized NPCs and their dedicated icons', () => {
  const palListSource = readFileSync(palListPath, 'utf8')
  const saveApiSource = readFileSync(saveApiPath, 'utf8')

  assert.doesNotMatch(
    palListSource,
    /constructibleSpecies[\s\S]*?!item\.IsHuman/,
    'the add flow must not discard synchronized NPC rows',
  )
  assert.match(
    saveApiSource,
    /"HasIcon":\s*DataProvider\.has_human_icon\(iname\)/,
    'the static catalog API must expose official NPC icon availability',
  )
})
