import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { fileURLToPath } from 'node:url'
import axios from 'axios'
import { createPinia, setActivePinia } from 'pinia'

globalThis.alert = () => {}
globalThis.localStorage = {
  getItem: () => null,
  setItem: () => {},
  removeItem: () => {},
}
globalThis.window = {}

const { usePalEditorStore } = await import('../src/stores/paleditor.js')

const sourcePath = relativePath => fileURLToPath(
  new URL(`../src/${relativePath}`, import.meta.url),
)

const view = readFileSync(sourcePath('views/GlobalPalboxView.vue'), 'utf8')
const entry = readFileSync(sourcePath('views/EntryView.vue'), 'utf8')
const router = readFileSync(sourcePath('router/index.js'), 'utf8')
const store = readFileSync(sourcePath('stores/paleditor.js'), 'utf8')
const picker = readFileSync(sourcePath('components/PathPicker.vue'), 'utf8')
const topBar = readFileSync(sourcePath('components/TopBar.vue'), 'utf8')
const zhCn = readFileSync(sourcePath('i18n/zh-CN.js'), 'utf8')
const readmeCn = readFileSync(
  fileURLToPath(new URL('../../../README.cn.md', import.meta.url)),
  'utf8',
)

test('Chinese UI consistently names the feature Cross-World Pal Terminal', () => {
  assert.match(zhCn, /GlobalPalbox_Entry:\s*"跨界帕鲁终端"/)
  assert.match(zhCn, /GlobalPalbox_Title:\s*"跨界帕鲁终端"/)
  assert.match(zhCn, /GlobalPalbox_Save:\s*"保存跨界帕鲁终端"/)
  assert.doesNotMatch(zhCn, /全局帕鲁终端|当前全局存档/)
  assert.match(readmeCn, /账号级跨界帕鲁终端/)
  assert.doesNotMatch(readmeCn, /账号级全局帕鲁终端/)
})

test('Global Palbox selection stays in the entry template and opens its own workspace', () => {
  assert.match(router, /path:\s*['"]\/global-palbox['"]/)
  assert.match(entry, /entryEditMode === 'global-palbox'/)
  assert.match(entry, /GlobalPalbox_Platform/)
  assert.match(entry, /openGlobalPalbox/)
  assert.match(entry, /router\.push\(\{ name: 'GlobalPalbox' \}\)/)
  assert.match(view, /import PalList from ['"]@\/components\/PalList\.vue['"]/)
  assert.match(view, /import PalEditor from ['"]@\/components\/PalEditor\.vue['"]/)
  assert.match(view, /id="EditorMain"/)
  assert.match(view, /<PalList\b/)
  assert.match(view, /<PalEditor\b/)
  assert.doesNotMatch(view, /global-editor-fields/)
  assert.doesNotMatch(view, /global-metadata-grid/)
  assert.doesNotMatch(view, /requiresSession/)
})

test('Global Palbox exposes Steam and XGP account storage sources', () => {
  assert.match(entry, /GLOBAL_PALBOX_SOURCE_MODE/)
  assert.match(entry, /GlobalPalbox_Platform/)
  assert.match(entry, /SourceBadge_Xgp/)
  assert.match(store, /global-palbox\/discover-xgp/)
  assert.match(store, /GLOBAL_PALBOX_XGP_PATH/)
})

test('Global Palbox uses the native file picker with an in-app fallback', () => {
  assert.match(store, /select_global_palbox_file/)
  assert.match(entry, /show_file_picker\('global-palbox'\)/)
  assert.match(picker, /globalpalstorage\.sav/)
  assert.match(picker, /GLOBAL_PALBOX_PATH\s*=\s*palStore\.PAL_FILE_PICKER_SELECTION/)
})

test('Global Palbox XGP uses the shared file picker for folders and containers.index', () => {
  assert.match(entry, /show_file_picker\('global-palbox-xgp'\)/)
  assert.doesNotMatch(entry, /pickGlobalPalboxXgpDirectory/)
  assert.match(store, /purpose === "global-palbox-xgp"/)
  assert.match(picker, /isGlobalPalboxXgpPicker/)
  assert.match(
    picker,
    /GLOBAL_PALBOX_XGP_PATH\s*=\s*palStore\.PAL_FILE_PICKER_SELECTION\s*\|\|\s*palStore\.PAL_FILE_PICKER_PATH/,
  )
  assert.match(picker, /discoverGlobalPalboxXgp\(\)/)
})

test('Global Palbox XGP keeps discovery and opening in one compact action row', () => {
  assert.match(
    entry,
    /class="entry-primary-row xgp-entry-actions"[\s\S]*?discoverGlobalPalboxXgp\(\)[\s\S]*?openGlobalPalbox/,
  )
  assert.match(entry, /class="save-path-row xgp-path-row"/)
  assert.match(
    entry,
    /\.xgp-path-row\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+150px/,
  )
  assert.match(
    entry,
    /\.xgp-entry-actions\s*\{[^}]*gap:\s*10px[^}]*margin-top:\s*auto[^}]*padding-top:\s*12px/,
  )
})

test('Global Palbox mutations use their own revisioned API', () => {
  assert.match(store, /\/api\/global-palbox\/open/)
  assert.match(store, /expected_revision:\s*session\.revision/)
  assert.match(store, /\/api\/global-palbox\/save/)
  assert.match(topBar, /saveGlobalPalbox/)
  assert.match(store, /deleteGlobalPalboxPal/)
  assert.match(store, /GLOBAL_PALBOX_SESSION\.value/)
})

test('Global Palbox store advances its isolated revision and clears pending changes on save', async () => {
  setActivePinia(createPinia())
  const store = usePalEditorStore()
  store.GLOBAL_PALBOX_PATH = 'C:\\Pal\\GlobalPalStorage.sav'
  const requests = []
  axios.post = async (url, data) => {
    requests.push({ method: 'POST', url, data })
    if (url.endsWith('/open')) return { data: { status: 0, data: {
      session: {
        session_id: 'global-session', revision: 0, pending_change_count: 0,
        occupied: 1, free: 959, capacity: 960,
      },
      pals: [{
        InstanceId: 'pal-1', CharacterID: 'SheepBall', SlotIndex: 0,
        DisplayName: 'Lamball', NickName: '', Gender: 'EPalGenderType::Male',
        Level: 1, FriendshipLevel: 0, Rank: 1, Suitabilities: {},
        PassiveSkillList: [], EquipWaza: [], MasteredWaza: [],
      }],
    } } }
    return { data: { status: 0, data: {
      session: {
        session_id: 'global-session', revision: 1, pending_change_count: 0,
        occupied: 1, free: 959, capacity: 960,
      },
    } } }
  }
  axios.patch = async (url, data) => {
    requests.push({ method: 'PATCH', url, data })
    return { data: { status: 0, data: {
      revision: 1,
      pal: {
        InstanceId: 'pal-1', CharacterID: 'GYM_ElecPanda', SlotIndex: 0,
        DisplayName: 'Grizzbolt', NickName: '', Gender: 'EPalGenderType::Male',
        Level: 1, FriendshipLevel: 0, Rank: 1, Suitabilities: {},
        PassiveSkillList: [], EquipWaza: [], MasteredWaza: [],
      },
    } } }
  }

  assert.equal(await store.openGlobalPalbox(), true)
  const updated = await store.updateGlobalPalboxPal('pal-1', {
    species_id: 'GYM_ElecPanda',
  })
  assert.equal(updated.InstanceId, 'pal-1')
  assert.equal(updated.CharacterID, 'GYM_ElecPanda')
  assert.equal(store.GLOBAL_PALBOX_SESSION.revision, 1)
  assert.equal(store.GLOBAL_PALBOX_SESSION.pending_change_count, 1)
  assert.equal(await store.saveGlobalPalbox(), true)
  assert.equal(store.GLOBAL_PALBOX_SESSION.pending_change_count, 0)
  assert.deepEqual(requests[1].data, {
    session_id: 'global-session',
    expected_revision: 0,
    values: { species_id: 'GYM_ElecPanda' },
  })
  assert.equal(requests[2].data.expected_revision, 1)
})

test('Global Palbox store prefers the desktop file picker', async () => {
  setActivePinia(createPinia())
  const store = usePalEditorStore()
  globalThis.window.pywebview = { api: {
    select_global_palbox_file: async () => 'C:\\Pal\\GlobalPalStorage.sav',
  } }

  await store.show_file_picker('global-palbox')

  assert.equal(store.GLOBAL_PALBOX_PATH, 'C:\\Pal\\GlobalPalStorage.sav')
  assert.equal(store.SHOW_FILE_PICKER, false)
  globalThis.window.pywebview = undefined
})
