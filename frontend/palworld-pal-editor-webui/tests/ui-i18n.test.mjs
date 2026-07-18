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

  for (const locale of ['en', 'fr', 'ja', 'zh-CN']) {
    store.I18n = locale
    assert.equal(typeof store.getTranslatedText('Common_AppName'), 'string', locale)
  }
})
