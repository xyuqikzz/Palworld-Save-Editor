import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const picker = readFileSync(
  fileURLToPath(new URL('../src/components/modules/ItemPicker.vue', import.meta.url)),
  'utf8',
)
const inventory = readFileSync(
  fileURLToPath(new URL('../src/components/InventoryEditor.vue', import.meta.url)),
  'utf8',
)

test('large item catalog is selected through a searchable detail dialog', () => {
  assert.match(inventory, /<ItemPicker\b/)
  assert.doesNotMatch(inventory, /<select\s+v-model="selectedStaticId"/)

  assert.match(picker, /<dialog\b/)
  assert.match(picker, /type="search"/)
  assert.match(picker, /v-model="categoryFilter"/)
  assert.match(picker, /v-model="dynamicKindFilter"/)
  assert.match(picker, /v-model="rarityFilter"/)
  assert.match(picker, /item\.description/)
  assert.match(picker, /item\.static_id/)
  assert.match(picker, /item\.max_stack/)
  assert.match(picker, /resultLimit \+= PAGE_SIZE/)
})
