import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import {
  groupPalList,
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

test('Pal list groups party and Palbox entries without mislabeling other locations', () => {
  const pals = [
    { InstanceId: 'palbox-002', ContainerType: 'PAL_STORAGE', SlotIndex: 2 },
    { InstanceId: 'party-001', ContainerType: 'PARTY', SlotIndex: 1 },
    { InstanceId: 'other-001', ContainerType: 'OTHER', SlotIndex: 0 },
    { InstanceId: 'palbox-001', ContainerType: 'PAL_STORAGE', SlotIndex: 1 },
  ]

  const groups = groupPalList(pals)

  assert.deepEqual(
    groups.party.map(pal => pal.InstanceId),
    ['party-001'],
  )
  assert.deepEqual(
    groups.palbox.map(pal => pal.InstanceId),
    ['palbox-001', 'palbox-002'],
  )
  assert.deepEqual(
    groups.other.map(pal => pal.InstanceId),
    ['other-001'],
  )
  assert.deepEqual(
    pals.map(pal => pal.InstanceId),
    ['palbox-002', 'party-001', 'other-001', 'palbox-001'],
    'grouping must not mutate the store-backed Pal list',
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

test('Player Pal list renders separate party and Palbox sections', () => {
  const source = readFileSync(palListPath, 'utf8')

  assert.match(source, /groupPalList\(filteredPalList\.value, palListSortMode\.value\)/)
  assert.match(source, /PalList_Group_Party/)
  assert.match(source, /PalList_Group_Palbox/)
  assert.match(source, /v-for="group in visiblePalGroups"/)
  assert.match(source, /v-for="pal in group\.pals"/)
  assert.match(source, /if \(palStore\.BASE_PAL_BTN_CLK_FLAG\)/)
})

test('Player Pal groups are accessible collapsible sections with a compact default', () => {
  const source = readFileSync(palListPath, 'utf8')

  assert.match(source, /const expandedPalGroups = ref\(new Set\(\['party'\]\)\)/)
  assert.match(source, /@click="togglePalGroup\(group\.key\)"/)
  assert.match(source, /:aria-expanded="isPalGroupExpanded\(group\)"/)
  assert.match(source, /:aria-controls="`pal-list-group-\$\{group\.key\}`"/)
  assert.match(source, /v-if="isPalGroupExpanded\(group\)"/)
  assert.match(source, /name="chevron-down"/)
  assert.match(source, /watch\(\(\) => palStore\.PAL_LIST_SEARCH_KEYWORD/)
  assert.match(source, /expandSelectedPalGroup\(palId\)/)
  assert.doesNotMatch(
    source,
    /palListContainer\.value\?\.querySelector\('button:not\(:disabled\)'\)/,
    'group toggle buttons must not be mistaken for Pal-selection buttons',
  )
  assert.match(
    source,
    /palListContainer\.value\?\.querySelector\('button\.pal:not\(:disabled\)'\)/,
  )
})
