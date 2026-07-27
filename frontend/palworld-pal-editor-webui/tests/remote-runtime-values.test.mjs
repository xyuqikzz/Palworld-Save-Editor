import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  formatRuntimeAttributes,
  formatRuntimeHealth,
  normalizeRuntimeFixedPoint,
} from '../src/components/modules/remote-runtime-values.js'

test('runtime fixed-point health uses display units instead of raw milli-units', () => {
  assert.equal(normalizeRuntimeFixedPoint(8815000), 8815)
  assert.equal(normalizeRuntimeFixedPoint(8815500), 8815.5)
})

test('runtime health treats a missing maximum as unknown instead of zero', () => {
  assert.deepEqual(
    formatRuntimeHealth({ hpRaw: 8815000, maxHpRaw: 0 }),
    {
      current: 8815,
      maximum: null,
      label: '8815 / —',
      percent: null,
    },
  )
})

test('runtime attributes use authoritative final player values', () => {
  assert.deepEqual(
    formatRuntimeAttributes(
      {
        hp: 8815,
        maxHp: 10000,
        attributes: {
          stamina: 250,
          attack: 130,
          defense: 507,
          craftSpeed: 120,
        },
      },
      { maximumWeight: 550 },
    ),
    {
      health: {
        current: 8815,
        maximum: 10000,
        label: '8815 / 10000',
        percent: 88.14999999999999,
      },
      stamina: 250,
      attack: 130,
      defense: 507,
      craftSpeed: 120,
      carryWeight: 550,
      partial: false,
    },
  )
})

test('remote management routes every health display through the formatter', () => {
  const viewSource = readFileSync(
    new URL('../src/views/RemoteServerView.vue', import.meta.url),
    'utf8',
  )

  assert.match(viewSource, /import \{ formatRuntimeAttributes \}/)
  assert.match(viewSource, /const runtimeAttributes = computed\(/)
  assert.match(viewSource, /const detailHealth = computed\(/)
  assert.match(viewSource, /value: detailHealth\.value\.label/)
  assert.match(viewSource, /valueOrDash\(runtimeAttributes\.value\.stamina\)/)
  assert.doesNotMatch(viewSource, /value:\s*'—'/)
  assert.doesNotMatch(viewSource, /attribute\.enhancement/)
  assert.match(viewSource, /\{\{ detailHealth\.label \}\}/)
  assert.doesNotMatch(
    viewSource,
    /valueOrDash\(detailPlayer(?:\.value)?\??\.hpRaw\)/,
  )
})

test('live inventory omits the aggregate summary strip from the screenshot', () => {
  const viewSource = readFileSync(
    new URL('../src/views/RemoteServerView.vue', import.meta.url),
    'utf8',
  )
  const inventoryPanel = viewSource.match(
    /<div v-else-if="activeTab === 'inventory'"[\s\S]*?<div v-else-if="activeTab === 'pals'"/,
  )?.[0]

  assert.ok(inventoryPanel)
  assert.doesNotMatch(inventoryPanel, /Remote_InventorySummary/)
  assert.doesNotMatch(inventoryPanel, /<header class="panel-summary">/)
})

test('bridge player details read final stats from the runtime parameter component', () => {
  const runtimeSource = readFileSync(
    new URL(
      '../../../native/pal_editor_bridge/ue4ss/src/palworld_runtime.cpp',
      import.meta.url,
    ),
    'utf8',
  )

  for (const getter of [
    'GetHP',
    'GetMaxHP',
    'GetMaxSP',
    'GetShotAttack',
    'GetDefense',
    'GetCraftSpeed',
  ]) {
    assert.match(runtimeSource, new RegExp(`PalCharacterParameterComponent:${getter}`))
  }
  assert.doesNotMatch(
    runtimeSource,
    /player\["attributes"\]\s*=\s*character\.value\(\s*"enhancements"/,
  )
  assert.match(
    runtimeSource,
    /PalIndividualCharacterParameter:GetMaxHP_withBuff/,
  )
  assert.match(
    runtimeSource,
    /PalIndividualCharacterParameter:GetMaxHP/,
  )
  assert.match(
    runtimeSource,
    /max_hp_raw\s*=\s*individual_max_hp_raw_value\(\s*individual_parameter\s*\)/,
  )
  assert.match(
    runtimeSource,
    /return max_hp_with_buff_raw;/,
  )
})

test('bridge Pal snapshots fall back to the individual maximum-health getters', () => {
  const runtimeSource = readFileSync(
    new URL(
      '../../../native/pal_editor_bridge/ue4ss/src/palworld_runtime.cpp',
      import.meta.url,
    ),
    'utf8',
  )
  const snapshotStart = runtimeSource.indexOf(
    'nlohmann::json character_snapshot(UObject* parameter)',
  )
  const snapshotEnd = runtimeSource.indexOf(
    'nlohmann::json inventory_snapshot(',
    snapshotStart,
  )
  const snapshotSource = runtimeSource.slice(snapshotStart, snapshotEnd)

  assert.ok(snapshotStart >= 0 && snapshotEnd > snapshotStart)
  assert.match(
    snapshotSource,
    /individual_max_hp_raw_value\(parameter\)/,
  )
})
