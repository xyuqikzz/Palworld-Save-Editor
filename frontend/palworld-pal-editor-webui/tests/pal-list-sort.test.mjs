import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import {
  PAL_LIST_SORT_MODES,
  sortPalList,
} from '../src/components/modules/pal-list-sort.js'

const palListPath = fileURLToPath(
  new URL('../src/components/PalList.vue', import.meta.url),
)

test('Pal list defaults to ascending container slot order', () => {
  const pals = [
    { InstanceId: 'paldeck-001', SlotIndex: 5, Level: 3 },
    { InstanceId: 'paldeck-002', SlotIndex: 1, Level: 50 },
    { InstanceId: 'paldeck-003', SlotIndex: null, Level: 10 },
  ]

  assert.deepEqual(
    sortPalList(pals).map(pal => pal.InstanceId),
    ['paldeck-002', 'paldeck-001', 'paldeck-003'],
  )
  assert.deepEqual(
    pals.map(pal => pal.InstanceId),
    ['paldeck-001', 'paldeck-002', 'paldeck-003'],
    'sorting must not mutate the store-backed Pal list',
  )
})

test('Container slot ties keep the existing paldeck order', () => {
  const palsInPaldeckOrder = [
    { InstanceId: 'paldeck-001', SlotIndex: 2 },
    { InstanceId: 'paldeck-002', SlotIndex: 2 },
    { InstanceId: 'paldeck-003' },
    { InstanceId: 'paldeck-004', SlotIndex: 'invalid' },
  ]

  assert.deepEqual(
    sortPalList(palsInPaldeckOrder, PAL_LIST_SORT_MODES.CONTAINER).map(pal => pal.InstanceId),
    ['paldeck-001', 'paldeck-002', 'paldeck-003', 'paldeck-004'],
  )
})

test('Paldeck order preserves the API order', () => {
  const pals = [
    { InstanceId: 'paldeck-001', SlotIndex: 5 },
    { InstanceId: 'paldeck-002', SlotIndex: 1 },
  ]

  assert.deepEqual(
    sortPalList(pals, PAL_LIST_SORT_MODES.PALDECK).map(pal => pal.InstanceId),
    ['paldeck-001', 'paldeck-002'],
  )
})

test('Level order is descending and falls back to paldeck order for ties', () => {
  const palsInPaldeckOrder = [
    { InstanceId: 'paldeck-001', Level: 25 },
    { InstanceId: 'paldeck-002', Level: 50 },
    { InstanceId: 'paldeck-003', Level: 50 },
    { InstanceId: 'paldeck-004', Level: 10 },
  ]

  assert.deepEqual(
    sortPalList(palsInPaldeckOrder, PAL_LIST_SORT_MODES.LEVEL).map(pal => pal.InstanceId),
    ['paldeck-002', 'paldeck-003', 'paldeck-001', 'paldeck-004'],
  )
})

test('Sort controls are rendered between Pal search and the result list', () => {
  const source = readFileSync(palListPath, 'utf8')
  const searchIndex = source.indexOf('v-model="palStore.PAL_LIST_SEARCH_KEYWORD"')
  const sortIndex = source.indexOf('class="pal-sort-control"')
  const listIndex = source.indexOf('class="overflow-list"')

  assert.ok(searchIndex >= 0, 'the Pal search field must be rendered')
  assert.ok(sortIndex > searchIndex, 'sort controls must be below the Pal search field')
  assert.ok(listIndex > sortIndex, 'sort controls must be above the Pal result list')
  assert.match(source, /const palListSortMode = ref\(PAL_LIST_SORT_MODES\.CONTAINER\)/)
  assert.match(source, /PalList_Sort_Container/)
})
