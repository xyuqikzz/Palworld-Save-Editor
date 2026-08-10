import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import { extname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { NodeTypes, parse as parseTemplate } from '@vue/compiler-dom'
import { parse } from '@vue/compiler-sfc'
import { createPinia, setActivePinia } from 'pinia'

const sourceRoot = fileURLToPath(new URL('../src', import.meta.url))
const storePath = fileURLToPath(new URL('../src/stores/paleditor.js', import.meta.url))
const topBarPath = fileURLToPath(new URL('../src/components/TopBar.vue', import.meta.url))

function vueFiles(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const path = join(directory, entry.name)
    if (entry.isDirectory()) return vueFiles(path)
    return extname(entry.name) === '.vue' ? [path] : []
  })
}

function loadMessages(locale) {
  const path = fileURLToPath(new URL(`../src/i18n/${locale}.js`, import.meta.url))
  const source = readFileSync(path, 'utf8')
    .replace(/^import .*$/gm, '')
    .replace('export default', 'return')
  return Function(source)()
}

function fixedVisibleText(source) {
  const template = parse(source).descriptor.template?.content ?? ''
  const ast = parseTemplate(template)
  const values = []
  const add = value => {
    const text = value.replace(/&(?:[A-Za-z]+|#\d+);/g, '').trim()
    if (/\p{L}{2,}/u.test(text)) values.push(text)
  }
  const addExpressionStrings = expression => {
    for (const match of expression.matchAll(/(["'`])((?:\\.|(?!\1)[\s\S])*)\1/g)) {
      const fixedPart = match[2].replace(/\$\{[^{}]*\}/g, '')
      if (/\s/u.test(fixedPart)) add(fixedPart)
    }
  }
  const visit = node => {
    if (node.type === NodeTypes.TEXT) add(node.content)
    if (node.type === NodeTypes.SIMPLE_EXPRESSION) addExpressionStrings(node.content)
    if (node.type === NodeTypes.COMPOUND_EXPRESSION) {
      for (const child of node.children) {
        if (typeof child === 'string') add(child)
      }
    }
    if (node.type === NodeTypes.INTERPOLATION) visit(node.content)
    if (node.type === NodeTypes.ELEMENT) {
      for (const prop of node.props) {
        if (
          prop.type === NodeTypes.ATTRIBUTE
          && ['alt', 'aria-label', 'content', 'placeholder', 'title'].includes(prop.name)
          && prop.value
        ) add(prop.value.content)
        if (prop.type === NodeTypes.DIRECTIVE && prop.exp) visit(prop.exp)
      }
    }
    if (Array.isArray(node.children)) {
      for (const child of node.children) {
        if (typeof child === 'object') visit(child)
      }
    }
  }
  visit(ast)
  return values
}

test('all Vue user-facing fixed text is provided by i18n', () => {
  const violations = {}
  for (const path of vueFiles(sourceRoot)) {
    const relativePath = path.slice(sourceRoot.length + 1)
    try {
      const values = fixedVisibleText(readFileSync(path, 'utf8'))
      if (values.length) violations[relativePath] = values
    } catch (error) {
      violations[relativePath] = [`TEMPLATE_PARSE_ERROR: ${error.message}`]
    }
  }
  assert.deepEqual(violations, {})
})

test('all supported locales expose the same translation keys', () => {
  const locales = {
    en: loadMessages('en'),
    fr: loadMessages('fr'),
    ja: loadMessages('ja'),
    ko: loadMessages('ko'),
    'zh-CN': loadMessages('zh-CN'),
  }
  const expected = Object.keys(locales.en).sort()
  for (const [locale, messages] of Object.entries(locales)) {
    assert.deepEqual(Object.keys(messages).sort(), expected, `${locale} translation keys differ`)
    for (const [key, value] of Object.entries(messages)) {
      assert.equal(typeof value, 'string', `${locale}.${key} must be a string`)
      assert.notEqual(value.trim(), '', `${locale}.${key} must not be empty`)
    }
  }
})

test('path picker describes loadable directories as complete world saves', () => {
  const expectedLabels = {
    en: 'Complete world save',
    fr: 'Sauvegarde de monde complète',
    ja: '完全なワールドセーブ',
    ko: '완전한 월드 저장',
    'zh-CN': '完整世界存档',
  }

  for (const [locale, expected] of Object.entries(expectedLabels)) {
    assert.equal(loadMessages(locale).PathPicker_SaveFolder, expected)
  }
})

test('the awakened Pal-list marker has no decorative prefix', () => {
  for (const locale of ['en', 'fr', 'ja', 'ko', 'zh-CN']) {
    const marker = loadMessages(locale).PalList_AwakenedMarker
    assert.doesNotMatch(marker, /^[-–—]/, `${locale} awakened marker must not start with a dash`)
  }
})

test('Korean translations are complete translations rather than English placeholders', () => {
  const en = loadMessages('en')
  const ko = loadMessages('ko')
  const intentionallyShared = new Set([
    'EntryView_Period',
    'Editor_IV_HP',
    'Editor_Souls_HP',
    'Common_AppName',
    'Entry_Source_Beta',
    'TopBar_Page_Json',
    'PlayerMap_FogSaveFile',
    'PlayerMap_FastTravelSaveFile',
    'PlayerInventoryCapacity_SaveFile',
  ])
  assert.deepEqual(
    Object.keys(en).filter(key => en[key] === ko[key] && !intentionallyShared.has(key)),
    [],
  )
  for (const key of Object.keys(en)) {
    const expected = [...en[key].matchAll(/\{\{\d+\}\}/g)].map(match => match[0]).sort()
    const actual = [...ko[key].matchAll(/\{\{\d+\}\}/g)].map(match => match[0]).sort()
    assert.deepEqual(actual, expected, `ko.${key} interpolation placeholders differ`)
  }
})

test('non-error store dialogs are provided by i18n', () => {
  const source = readFileSync(storePath, 'utf8')
  assert.doesNotMatch(
    source,
    /window\.confirm\(\s*[`'"]/,
    'window.confirm must receive translated text instead of a fixed string',
  )
  assert.doesNotMatch(
    source,
    /alert\(\s*[`'"]Pal Data Copied to Clipboard![`'"]\s*\)/,
    'successful clipboard feedback must be translated',
  )
})

test('translation lookup is synchronous for every supported locale', async () => {
  globalThis.localStorage = {
    getItem: () => null,
    setItem: () => {},
  }
  const { usePalEditorStore } = await import('../src/stores/paleditor.js')
  setActivePinia(createPinia())
  const store = usePalEditorStore()

  for (const locale of ['en', 'fr', 'ja', 'ko', 'zh-CN']) {
    store.I18n = locale
    assert.notEqual(store.getTranslatedText('Common_Save'), 'I18N_MISSING', locale)
  }
  store.I18n = 'ko'
  assert.equal(store.getTranslatedText('Common_Save'), '저장')
})

test('the document language follows the selected locale', () => {
  const source = readFileSync(topBarPath, 'utf8')
  assert.match(source, /document\.documentElement\.lang = locale \|\| 'en'/)
})

test('the save button has the exact disabled states and explains each one accessibly', () => {
  const source = readFileSync(topBarPath, 'utf8')
  const saveButton = source.match(
    /<button\s+class="op op--primary"[\s\S]*?<\/button>/,
  )?.[0]

  assert.ok(saveButton, 'save button must exist')
  assert.match(
    saveButton,
    /:disabled="palStore\.LOADING_FLAG \|\| !palStore\.PENDING_CHANGE_COUNT"/,
  )
  assert.match(saveButton, /:title="saveButtonHint"/)
  assert.match(saveButton, /:aria-label="saveButtonHint"/)
  assert.match(source, /TopBar_Save_Disabled_Loading/)
  assert.match(source, /TopBar_Save_Disabled_NoChanges/)
})
