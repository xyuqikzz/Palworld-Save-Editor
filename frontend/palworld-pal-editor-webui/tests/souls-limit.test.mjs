import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const store = readFileSync(
  fileURLToPath(new URL('../src/stores/paleditor.js', import.meta.url)),
  'utf8',
)
const editor = readFileSync(
  fileURLToPath(new URL('../src/components/PalEditor.vue', import.meta.url)),
  'utf8',
)

test('soul enhancement sliders switch between configured and cheat maximums', () => {
  assert.match(store, /const MAX_SOULS_LEVEL = ref\(0\)/)
  assert.match(store, /MAX_SOULS_LEVEL\.value = response\.data\.MaxSoulsLevel/)
  assert.doesNotMatch(store, /const MAX_SOULS_LEVEL = 60/)

  const configuredMaxBindings = editor.match(
    /:max="palStore\.HIDE_INVALID_OPTIONS \? palStore\.MAX_SOULS_LEVEL : 255"/g,
  ) ?? []
  assert.equal(configuredMaxBindings.length, 4)

  const ivMaxBindings = editor.match(
    /:max="palStore\.HIDE_INVALID_OPTIONS \? 100 : 255"/g,
  ) ?? []
  assert.equal(ivMaxBindings.length, 4)
})

test('soul enhancement ranks display their game bonus percentages', () => {
  assert.match(editor, /const soulBonusPercent = rank => Number\(rank \|\| 0\) \* 3/)

  const percentageBindings = editor.match(
    /soulBonusPercent\(palStore\.SELECTED_PAL_DATA\.Rank_(?:HP|Attack|Defence|CraftSpeed)\)/g,
  ) ?? []
  assert.equal(percentageBindings.length, 4)

  const soulBonusPercent = rank => Number(rank || 0) * 3
  assert.equal(soulBonusPercent(20), 60)
  assert.equal(soulBonusPercent(30), 90)
})
