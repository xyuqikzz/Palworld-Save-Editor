import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { fileURLToPath } from 'node:url'
import axios from 'axios'
import { createPinia, setActivePinia } from 'pinia'

globalThis.alert = () => {}
globalThis.window = {
  confirm: () => true,
  prompt: () => null,
}
globalThis.localStorage = {
  getItem: () => null,
  setItem: () => {},
  removeItem: () => {},
}

const { usePalEditorStore } = await import('../src/stores/paleditor.js')
const sourcePath = relativePath => fileURLToPath(
  new URL(`../src/${relativePath}`, import.meta.url),
)

test('save JSON is session-scoped and follows the requested page-navigation order', () => {
  const router = readFileSync(sourcePath('router/index.js'), 'utf8')
  const topBar = readFileSync(sourcePath('components/TopBar.vue'), 'utf8')

  assert.match(
    router,
    /path:\s*['"]\/json-editor['"][\s\S]*?name:\s*['"]JsonEditor['"][\s\S]*?requiresSession:\s*true/,
  )
  const orderedKeys = [
    'TopBar_Page_Return',
    'TopBar_Page_Overview',
    'TopBar_Page_Pals',
    'TopBar_Page_Players',
    'TopBar_Page_Map',
    'TopBar_Page_Guilds',
    'TopBar_Page_Arena',
    'TopBar_Page_Expeditions',
    'TopBar_Page_Json',
  ]
  const positions = orderedKeys.map(key => topBar.indexOf(key))
  assert.equal(positions.every(position => position > 0), true)
  assert.deepEqual(positions, [...positions].sort((left, right) => left - right))
})

test('JSON editor ships Monaco only and keeps the explicit safety boundary', () => {
  const view = readFileSync(sourcePath('views/JsonEditorView.vue'), 'utf8')
  const monaco = readFileSync(
    sourcePath('components/json-editor/MonacoJsonEditor.vue'),
    'utf8',
  )
  const zh = readFileSync(sourcePath('i18n/zh-CN.js'), 'utf8')
  const packageJson = JSON.parse(
    readFileSync(fileURLToPath(new URL('../package.json', import.meta.url)), 'utf8'),
  )

  assert.doesNotMatch(view, /CodeMirror|codemirror/)
  assert.match(view, /MonacoJsonEditor/)
  assert.match(view, /JsonEditor_Acknowledge/)
  assert.match(view, /JsonEditor_ConfirmApply/)
  assert.match(view, /RISK_ACKNOWLEDGEMENT_STORAGE_KEY/)
  assert.match(view, /const acknowledged = ref\(hasAcknowledgedRisk\(\)\)/)
  assert.match(view, /localStorage\?\.setItem\(RISK_ACKNOWLEDGEMENT_STORAGE_KEY, 'true'\)/)
  assert.match(view, /onMounted\(async \(\) => \{\s*if \(acknowledged\.value\) await loadFiles/)
  assert.doesNotMatch(view, /class="json-header"|JsonEditor_Title/)
  assert.match(monaco, /monaco-editor\/esm\/vs\/language\/json/)
  assert.match(
    zh,
    /仅检查 JSON 语法，不验证存档字段值。错误修改可能导致存档损坏或无法加载。请务必先备份存档。不熟悉 JSON 或游戏存档结构的用户请勿编辑。/,
  )
  assert.ok(packageJson.dependencies['monaco-editor'])
  assert.equal(
    Object.keys(packageJson.dependencies).some(
      name => name === 'codemirror' || name.startsWith('@codemirror/'),
    ),
    false,
  )
})

test('JSON editor waits for a file click and locks navigation while it loads', () => {
  const view = readFileSync(sourcePath('views/JsonEditorView.vue'), 'utf8')
  const loadFiles = view.slice(
    view.indexOf('async function loadFiles'),
    view.indexOf('async function loadDocument'),
  )
  const activeBindings = view.match(
    /'file-row--active':\s*!documentLoading\s*&&\s*selectedPath\s*===\s*file\.path/g,
  ) || []

  assert.doesNotMatch(loadFiles, /loadDocument\(/)
  assert.match(view, /documentLoading\.value = true/)
  assert.match(view, /:disabled="navigationLocked"/)
  assert.match(view, /class="editor-loading"/)
  assert.match(view, /loadFiles\(\{ clearSelection: true \}\)/)
  assert.equal(activeBindings.length, 2)
})

test('JSON editor store reads raw text and applies it with the shared revision', async () => {
  setActivePinia(createPinia())
  const store = usePalEditorStore()
  store.SESSION_ID = 'json-session'
  store.SESSION_REVISION = 7

  const calls = []
  axios.get = async (url, options) => {
    calls.push({ method: 'get', url, options })
    if (url.includes('/files')) {
      return {
        data: {
          status: 0,
          data: {
            revision: 7,
            files: [{ path: 'Level.sav', kind: 'level' }],
          },
        },
      }
    }
    return { data: '{"properties":{"Counter":{"value":2}}}' }
  }
  axios.post = async (url, data) => {
    calls.push({ method: 'post', url, data })
    return {
      data: {
        status: 0,
        data: {
          changed: true,
          revision: 8,
          pending_change_count: 1,
        },
      },
    }
  }

  const files = await store.loadJsonEditorFiles()
  const document = await store.loadJsonDocument('Level.sav')
  const result = await store.applyJsonDocument('Level.sav', document)

  assert.equal(files.files[0].path, 'Level.sav')
  assert.equal(document, '{"properties":{"Counter":{"value":2}}}')
  assert.equal(result.revision, 8)
  assert.equal(store.SESSION_REVISION, 8)
  assert.equal(store.PENDING_CHANGE_COUNT, 1)
  assert.match(calls[1].url, /path=Level\.sav/)
  assert.equal(calls[1].options.responseType, 'text')
  assert.match(calls[2].url, /expected_revision=7/)
  assert.equal(calls[2].data, document)
})

test('JSON editor does not display a backend error envelope as editable text', async () => {
  setActivePinia(createPinia())
  const store = usePalEditorStore()
  store.SESSION_ID = 'json-session'

  axios.get = async () => {
    const error = new Error('unprocessable')
    error.response = {
      data: JSON.stringify({
        status: 1,
        data: null,
        msg: 'The selected save file could not be converted.',
        error: { code: 'RAW_JSON_PARSE_FAILED' },
      }, null, 2),
    }
    throw error
  }

  const document = await store.loadJsonDocument('Level.sav')

  assert.equal(document, false)
  assert.equal(store.LAST_ERROR.code, 'RAW_JSON_PARSE_FAILED')
})
