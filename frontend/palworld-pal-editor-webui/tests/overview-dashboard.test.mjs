import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const sourcePath = relativePath => fileURLToPath(
  new URL(`../src/${relativePath}`, import.meta.url),
)

const appSource = readFileSync(sourcePath('App.vue'), 'utf8')
const routerSource = readFileSync(sourcePath('router/index.js'), 'utf8')
const storeSource = readFileSync(sourcePath('stores/paleditor.js'), 'utf8')
const topBarSource = readFileSync(sourcePath('components/TopBar.vue'), 'utf8')
const overviewSource = readFileSync(sourcePath('views/OverviewView.vue'), 'utf8')

test('a newly loaded or resumed save opens the read-only overview first', () => {
  assert.match(
    routerSource,
    /path:\s*['"]\/overview['"][\s\S]*?name:\s*['"]Overview['"][\s\S]*?requiresSession:\s*true/,
  )
  assert.equal(
    appSource.match(/router\.replace\(\{ name: 'Overview' \}\)/g)?.length,
    2,
    'startup resume and entry-page load must both select the overview',
  )
  assert.match(
    topBarSource,
    /isOverview[\s\S]*?navigate\('Overview'\)[\s\S]*?TopBar_Page_Overview/,
    'the loaded-session navigation must retain a direct overview entry',
  )
})

test('overview statistics use the session-scoped read-only endpoint', () => {
  assert.match(storeSource, /const OVERVIEW_DATA = ref\(null\)/)
  assert.match(storeSource, /async function loadOverview\(\)/)
  assert.match(
    storeSource,
    /\/api\/save\/query\/overview\?session_id=\$\{encodeURIComponent\(SESSION_ID\.value\)\}/,
  )
  assert.match(overviewSource, /onMounted\(\(\) => \{\s*refreshOverview\(\)/)
})

test('overview exposes an atomic whole-save heal action', () => {
  assert.match(
    overviewSource,
    /Overview_HealAllPals_Tooltip[\s\S]*?!Number\(totals\.pals\)[\s\S]*?@click="palStore\.healAllPalsInSave"[\s\S]*?name="medical"[\s\S]*?Overview_HealAllPals/,
  )
  assert.match(
    storeSource,
    /async function healAllPalsInSave\(\)[\s\S]*?Confirm_HealAllPalsInSave[\s\S]*?\/api\/save\/pals\/commands[\s\S]*?command:\s*"heal_all_pals"[\s\S]*?loadOverview\(\)/,
  )
})

test('overview exposes expedition, condition, structure, and distribution diagnostics', () => {
  for (const key of [
    'invalid_assignments',
    'structural_issue_count',
    'sick_pals',
    'fainted_pals',
    'top_species',
    'human_npcs',
    'base_workers',
  ]) {
    assert.match(overviewSource, new RegExp(key))
  }
  assert.match(
    overviewSource,
    /reasonTranslationKeys[\s\S]*?EXPEDITION_ASSIGNMENT_INVALID[\s\S]*?PAL_DETACHED/,
  )
  assert.match(
    overviewSource,
    /\.overview-primary-grid\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1\.7fr\) minmax\(300px,\s*0\.72fr\)/,
    'the main workspace and health diagnostic must use an asymmetric desktop composition',
  )
  assert.match(
    overviewSource,
    /@media \(max-width:\s*760px\)[\s\S]*?\.metric-rail\s*\{[^}]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)/,
    'core statistics must remain readable on narrow windows',
  )
})

test('overview shows the arena world top ten and can switch to the player top ten', () => {
  assert.match(overviewSource, /import \{ getArenaNpcName \} from '@\/data\/arenaNpcNames'/)
  assert.match(overviewSource, /const arenaPlayersOnly = ref\(false\)/)
  assert.match(
    overviewSource,
    /ARENA_LEADERBOARD\.filter\(entry => entry\.rank !== null\)[\s\S]*?rankedEntries\.filter\(entry => entry\.entry_type !== 'npc'\)[\s\S]*?entries\.slice\(0,\s*10\)/,
    'the player view must filter NPC entries before applying the top-ten limit',
  )
  assert.match(
    overviewSource,
    /Promise\.all\(\[[\s\S]*?palStore\.loadOverview\(\)[\s\S]*?palStore\.loadArenaLeaderboard\(\)/,
    'the home refresh must load both overview and arena ranking data',
  )
  assert.match(overviewSource, /Overview_ArenaAllTopTen/)
  assert.match(overviewSource, /Overview_ArenaPlayersTopTen/)
  assert.match(overviewSource, /entry\.rank/)
  assert.match(overviewSource, /entry\.rank_point/)
  assert.match(overviewSource, /arenaDisplayName\(entry\)/)
})
