import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { parse } from '@vue/compiler-sfc'

const playerEditorPath = fileURLToPath(new URL('../src/components/PlayerEditor.vue', import.meta.url))
const missionEditorPath = fileURLToPath(new URL('../src/components/MissionEditor.vue', import.meta.url))
const inventoryEditorPath = fileURLToPath(new URL('../src/components/InventoryEditor.vue', import.meta.url))
const storePath = fileURLToPath(new URL('../src/stores/paleditor.js', import.meta.url))

test('player editor exposes five independent tabs and keeps mission state mounted', () => {
  const source = readFileSync(playerEditorPath, 'utf8')

  assert.match(source, /PlayerTab_Inventory/)
  assert.match(source, /PlayerTab_Technology/)
  assert.match(source, /PlayerTab_Missions/)
  assert.match(source, /PlayerTab_MapProgress/)
  assert.match(source, /id="player-attributes-tab"/)
  assert.match(
    source,
    /<MissionEditor[\s\S]*?v-show="activeEditorTab === 'missions'"/,
    'mission state must survive tab switches',
  )
  assert.equal(
    source.match(/name="unlock_all_techs"/g)?.length,
    1,
    'unlock-all technology belongs to the technology panel only',
  )
  assert.match(
    source,
    /technology-panel[\s\S]*?technology-actions[\s\S]*?name="unlock_all_techs"/,
  )
})

test('player tabs omit redundant inner titles', () => {
  const playerSource = readFileSync(playerEditorPath, 'utf8')
  const missionSource = readFileSync(missionEditorPath, 'utf8')
  const inventorySource = readFileSync(inventoryEditorPath, 'utf8')

  assert.doesNotMatch(playerSource, /<h2>[\s\S]*?Editor_TechEdit[\s\S]*?<\/h2>/)
  assert.doesNotMatch(missionSource, /<h2>[\s\S]*?Mission_Title[\s\S]*?<\/h2>/)
  assert.doesNotMatch(inventorySource, /<h2[^>]*>[\s\S]*?Editor_Inventory[\s\S]*?<\/h2>/)
})

test('mission editor contains search, filters, status statistics, details, confirmations and all operations', () => {
  const source = readFileSync(missionEditorPath, 'utf8')
  assert.doesNotThrow(() => parse(source), 'MissionEditor.vue must parse')

  for (const value of [
    'searchText',
    'typeFilter',
    'statusFilter',
    'selectedMissionIds',
    'detailMission',
    'confirmationPreview',
    'complete_tracked',
    'complete_all_in_progress',
    'complete_all',
    'reset_all_completed',
    'mark_completed',
    'reset_to_unaccepted',
    'restart_from_beginning',
  ]) {
    assert.match(source, new RegExp(value), `${value} is required`)
  }
  assert.match(source, /overflow-x:\s*auto/, 'the mission table must scroll inside its panel')
  assert.match(source, /@click\.stop="openDetails\(mission\)"/, 'rows must open details')
  assert.match(source, /Mission_WarningRewards/)
  assert.match(source, /Mission_WarningStoryEffects/)
  assert.match(source, /Mission_WarningFollowUp/)
})

test('mission table provides complete-all, current-page selection and status-specific row actions', () => {
  const source = readFileSync(missionEditorPath, 'utf8')

  assert.match(
    source,
    /class="complete-all-button"[\s\S]*?@click="requestPreview\('complete_all', \[\]\)"/,
    'the mission tab must expose a direct complete-all entry that keeps preview confirmation',
  )
  assert.match(source, /:indeterminate="someVisibleSelected && !allVisibleSelected"/)
  assert.match(source, /@change="toggleVisibleSelection"/)
  assert.match(
    source,
    /mission\.status !== 'unaccepted'[\s\S]*?requestPreview\('reset_to_unaccepted'/,
    'accepted missions must expose reset to unaccepted',
  )
  assert.match(
    source,
    /mission\.status !== 'unaccepted'[\s\S]*?requestPreview\('restart_from_beginning'/,
    'accepted missions must expose rollback to the first step',
  )
  assert.doesNotMatch(
    source,
    /\.row-actions\s*\{[^}]*display:\s*flex/,
    'the table cell must retain table-cell layout so its left edge stays aligned',
  )
  assert.match(source, /\.row-actions-inner\s*\{[^}]*display:\s*flex/)
})

test('mission store calls read, preview and confirmed command endpoints and refreshes on locale changes', () => {
  const source = readFileSync(storePath, 'utf8')

  assert.match(source, /async function loadPlayerMissions/)
  assert.match(source, /\/missions\?\$\{params\.toString\(\)\}/)
  assert.match(source, /async function previewMissionCommand/)
  assert.match(source, /\/missions\/preview/)
  assert.match(source, /async function executeMissionCommand/)
  assert.match(source, /\/missions\/commands/)
  assert.match(
    source,
    /updateI18n[\s\S]*?refreshes\.push\(loadPlayerMissions\(SELECTED_PLAYER_ID\.value\)\)/,
  )
  assert.match(source, /PENDING_CHANGE_COUNT\.value = response\.data\.pending_change_count/)
})
