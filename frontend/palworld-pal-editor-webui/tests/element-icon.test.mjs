import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const elementIconPath = fileURLToPath(
  new URL('../src/components/modules/ElementIcon.vue', import.meta.url),
)

test('Electricity uses the Element_Electric asset name', () => {
  const source = readFileSync(elementIconPath, 'utf8')

  assert.match(
    source,
    /Electricity:\s*['\"]Electric['\"]/,
    'the Electricity data enum must resolve to the existing Element_Electric.png asset',
  )
})
