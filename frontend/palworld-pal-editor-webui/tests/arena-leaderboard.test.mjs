import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { fileURLToPath } from 'node:url'
import axios from 'axios'
import { createPinia, setActivePinia } from 'pinia'

globalThis.alert = () => {}
globalThis.window = { confirm: () => true }
globalThis.localStorage = {
  getItem: () => null,
  setItem: () => {},
  removeItem: () => {},
}

const { usePalEditorStore } = await import('../src/stores/paleditor.js')
const {
  ARENA_NPC_NAME_SOURCE_BUILD,
  getArenaNpcName,
} = await import('../src/data/arenaNpcNames.js')
const sourcePath = relativePath => fileURLToPath(
  new URL(`../src/${relativePath}`, import.meta.url),
)

test('arena leaderboard has a session route and a reachable loaded-save toolbar entry', () => {
  const router = readFileSync(sourcePath('router/index.js'), 'utf8')
  const topBar = readFileSync(sourcePath('components/TopBar.vue'), 'utf8')
  const view = readFileSync(sourcePath('views/ArenaLeaderboardView.vue'), 'utf8')

  assert.match(router, /path:\s*['"]\/arena['"][\s\S]*?name:\s*['"]ArenaLeaderboard['"][\s\S]*?requiresSession:\s*true/)
  assert.match(topBar, /@click="navigate\('ArenaLeaderboard'\)"[\s\S]*?TopBar_Page_Arena/)
  assert.match(view, /ArenaRankPoint|ARENA_LEADERBOARD/)
  assert.match(view, /max="2147483647"/)
  assert.match(view, /resetArenaLeaderboard/)
  assert.match(view, /getArenaNpcName/)
  assert.match(view, /Arena_InitializeField/)
  assert.match(view, /field_state === 'missing'/)
  assert.match(view, /const playersOnly = ref\(false\)/)
  assert.match(view, /ARENA_LEADERBOARD\.filter\(entry => !isNpc\(entry\)\)/)
  assert.match(view, /Arena_PlayersOnly/)
  assert.match(view, /<span v-if="isNpc\(entry\)">—<\/span>/)
  assert.doesNotMatch(view, /Arena_ReadOnlyNPC/)
  assert.doesNotMatch(view, /arena-summary|Arena_RankedPlayerCount|Arena_NpcSourceBuild/)
})

test('arena NPC names use the shipped game localization with a safe ID fallback', () => {
  assert.equal(ARENA_NPC_NAME_SOURCE_BUILD, 24088745)
  assert.equal(getArenaNpcName('NAME_DarkTrader', 'zh-CN'), '黑市商人')
  assert.equal(getArenaNpcName('NAME_BattlePaltamer001', 'ja'), 'かけだしパルテイマー')
  assert.equal(getArenaNpcName('NAME_Viking', 'missing-locale'), 'Feybreak Warrior')
  assert.equal(getArenaNpcName('UNKNOWN_NPC', 'zh-CN'), 'UNKNOWN_NPC')
})

test('arena store reads, updates, and advances the shared session revision', async () => {
  setActivePinia(createPinia())
  const store = usePalEditorStore()
  store.SESSION_ID = 'session-arena'
  store.SESSION_REVISION = 4

  axios.get = async url => {
    assert.equal(url, '/api/arena/leaderboard?session_id=session-arena')
    return { data: { status: 0, data: {
      revision: 4,
      entries: [{ player_id: 'player-1', rank: 1, rank_point: 50, writable: true }],
      editable_count: 1,
      ranked_player_count: 1,
      initializable_count: 2,
      unsupported_count: 0,
      npc_count: 100,
      npc_source_build: 24088745,
    } } }
  }
  assert.equal(await store.loadArenaLeaderboard(), true)
  assert.equal(store.ARENA_LEADERBOARD[0].rank_point, 50)
  assert.equal(store.ARENA_RANKED_PLAYER_COUNT, 1)
  assert.equal(store.ARENA_INITIALIZABLE_COUNT, 2)
  assert.equal(store.ARENA_NPC_COUNT, 100)
  assert.equal(store.ARENA_NPC_SOURCE_BUILD, 24088745)

  let command
  axios.post = async (url, data) => {
    command = { url, data: structuredClone(data) }
    return { data: { status: 0, data: {
      revision: 5,
      entries: [{ player_id: 'player-1', rank: 1, rank_point: 900, writable: true }],
      editable_count: 1,
      ranked_player_count: 1,
      initializable_count: 2,
      unsupported_count: 0,
      npc_count: 100,
      npc_source_build: 24088745,
      affected_count: 1,
      skipped_count: 0,
      skipped: [],
    } } }
  }

  const result = await store.setArenaRankPoint('player-1', 900)

  assert.deepEqual(command, {
    url: '/api/arena/commands',
    data: {
      session_id: 'session-arena',
      expected_revision: 4,
      command: 'set_rank_point',
      player_id: 'player-1',
      rank_point: 900,
    },
  })
  assert.equal(result.affected_count, 1)
  assert.equal(store.SESSION_REVISION, 5)
  assert.equal(store.PENDING_CHANGE_COUNT, 1)
  assert.equal(store.ARENA_LEADERBOARD[0].rank_point, 900)
})
