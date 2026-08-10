import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync, readdirSync } from 'node:fs'
import { extname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { createMessageDialogController } from '../src/services/message-dialog.js'

const sourceRoot = fileURLToPath(new URL('../src', import.meta.url))

function sourceFiles(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const path = join(directory, entry.name)
    if (entry.isDirectory()) return sourceFiles(path)
    return ['.js', '.vue'].includes(extname(entry.name)) ? [path] : []
  })
}


test('message dialog queues requests and resolves them in order', async () => {
  const dialog = createMessageDialogController()
  const detach = dialog.attachHost()

  const first = dialog.confirmMessage('Apply changes?')
  const second = dialog.showMessage({ message: 'Saved', tone: 'success' })

  assert.equal(dialog.state.current.message, 'Apply changes?')
  assert.equal(dialog.state.current.mode, 'confirm')
  dialog.settle(true)
  assert.equal(await first, true)
  assert.equal(dialog.state.current.message, 'Saved')
  assert.equal(dialog.state.current.tone, 'success')
  dialog.settle(undefined)
  assert.equal(await second, undefined)

  detach()
})


test('message dialog resolves pending requests safely when its host unmounts', async () => {
  const dialog = createMessageDialogController()
  const detach = dialog.attachHost()
  const confirmation = dialog.confirmMessage('Continue?')
  const input = dialog.promptMessage('Path')

  detach()

  assert.equal(await confirmation, false)
  assert.equal(await input, null)
  assert.equal(dialog.state.current, null)
})


test('application code routes native browser dialogs through the global message module', () => {
  const allowedFallback = join(sourceRoot, 'services', 'message-dialog.js')
  const violations = sourceFiles(sourceRoot)
    .filter(path => path !== allowedFallback)
    .filter(path => /\bwindow\.(?:alert|confirm|prompt)\s*\(/.test(readFileSync(path, 'utf8')))
    .map(path => path.slice(sourceRoot.length + 1))

  assert.deepEqual(violations, [])
})
