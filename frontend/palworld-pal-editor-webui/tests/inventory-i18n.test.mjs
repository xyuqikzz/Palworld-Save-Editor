import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const componentPath = fileURLToPath(
  new URL('../src/components/InventoryEditor.vue', import.meta.url),
)
const component = readFileSync(componentPath, 'utf8')

function loadMessages(locale) {
  const path = fileURLToPath(new URL(`../src/i18n/${locale}.js`, import.meta.url))
  const source = readFileSync(path, 'utf8')
    .replace(/^import .*$/gm, '')
    .replace('export default', 'return')
  return Function(source)()
}

const en = loadMessages('en')
const fr = loadMessages('fr')
const ja = loadMessages('ja')
const zhCN = loadMessages('zh-CN')

function visibleEnglishText(template) {
  return [...template.matchAll(/>([^<]+)</g)]
    .map(match => match[1].replace(/\{\{[\s\S]*?\}\}/g, '').trim())
    .filter(text => /[A-Za-z]{2,}/.test(text))
}

function staticEnglishAttributes(template) {
  return [...template.matchAll(/\s(?:aria-label|placeholder|title)="([^"]+)"/g)]
    .map(match => match[1])
    .filter(text => /[A-Za-z]{2,}/.test(text))
}

test('inventory editor localizes every user-facing string in all supported locales', () => {
  const template = component.match(/<template>([\s\S]*)<\/template>/)?.[1] ?? ''

  assert.deepEqual(visibleEnglishText(template), [])
  assert.deepEqual(staticEnglishAttributes(template), [])
  assert.doesNotMatch(component, /new Error\(['"`][A-Za-z]/)
  assert.doesNotMatch(component, /window\.alert\(`[^`]*[A-Za-z]/)

  const referencedKeys = new Set(
    [...component.matchAll(/['"]((?:Inventory_|Editor_Inventory)[A-Za-z0-9_]*)['"]/g)]
      .map(match => match[1]),
  )
  assert.ok(referencedKeys.size > 1, 'inventory editor must use dedicated translation keys')

  const locales = { en, fr, ja, 'zh-CN': zhCN }
  const expectedKeys = Object.keys(en)
    .filter(key => key === 'Editor_Inventory' || key.startsWith('Inventory_'))
    .sort()
  for (const [locale, messages] of Object.entries(locales)) {
    assert.deepEqual(
      Object.keys(messages)
        .filter(key => key === 'Editor_Inventory' || key.startsWith('Inventory_'))
        .sort(),
      expectedKeys,
      `${locale} inventory translation keys differ from English`,
    )
    for (const key of referencedKeys) {
      assert.equal(typeof messages[key], 'string', `${locale} is missing ${key}`)
      assert.notEqual(messages[key].trim(), '', `${locale} has an empty ${key}`)
    }
  }
})
