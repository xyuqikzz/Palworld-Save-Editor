import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const mainCssPath = fileURLToPath(
  new URL('../src/assets/main.css', import.meta.url),
)
const editorViewPath = fileURLToPath(
  new URL('../src/views/EditorView.vue', import.meta.url),
)
const playerEditorPath = fileURLToPath(
  new URL('../src/components/PlayerEditor.vue', import.meta.url),
)
const inventoryEditorPath = fileURLToPath(
  new URL('../src/components/InventoryEditor.vue', import.meta.url),
)

test('editor list panels contain their independently scrollable lists', () => {
  const source = readFileSync(mainCssPath, 'utf8')
  const panelRule = source.match(
    /#EditorMain\s+\.selection-column\s*>\s*\.list-panel\s*\{([^}]*)\}/,
  )

  assert.ok(panelRule, 'editor list panels must define an overflow boundary')
  assert.match(
    panelRule[1],
    /overflow-y:\s*clip/,
    'long Pal lists must not enlarge the document scroll area',
  )
  assert.match(
    panelRule[1],
    /overflow-x:\s*visible/,
    'panel popovers must remain visible outside the narrow list column',
  )
  assert.match(
    panelRule[1],
    /min-height:\s*0/,
    'list panels must be allowed to shrink inside the editor grid',
  )
})

test('editor workspace contains its top offset instead of collapsing it onto the page', () => {
  const source = readFileSync(editorViewPath, 'utf8')
  const workspaceRule = source.match(/div#EditorDiv\s*\{([^}]*)\}/)

  assert.ok(workspaceRule, 'EditorDiv layout rule must exist')
  assert.match(
    workspaceRule[1],
    /display:\s*flow-root/,
    'the editor top margin must stay inside the viewport-height workspace',
  )
})

test('player inventory and technology editors are switched through exclusive tabs', () => {
  const source = readFileSync(playerEditorPath, 'utf8')

  assert.match(source, /role="tablist"/, 'player editor must expose a tab list')
  assert.match(
    source,
    /<InventoryEditor[\s\S]*?v-show="activeEditorTab === 'inventory'"/,
    'inventory editor must only be visible on its tab',
  )
  assert.match(
    source,
    /<section[\s\S]*?v-show="activeEditorTab === 'technology'"[\s\S]*?id="player-technology-panel"/,
    'technology editor must only be visible on its tab',
  )
})

test('occupied inventory slots keep item details and actions on separate rows', () => {
  const source = readFileSync(inventoryEditorPath, 'utf8')

  assert.match(
    source,
    /<div class="slot-main">[\s\S]*?<ItemIcon[\s\S]*?<div class="slot-copy">[\s\S]*?<input[\s\S]*?class="slot-count"[\s\S]*?<\/div>[\s\S]*?<div class="slot-actions">/,
    'item icon, name and count must stay in the primary row before the action row',
  )
  assert.match(
    source,
    /\.slot-main\s*\{[^}]*flex:\s*1 0 100%/,
    'the primary item row must occupy the full slot width',
  )
  assert.match(
    source,
    /\.slot-actions\s*\{[^}]*flex:\s*1 0 100%/,
    'inventory actions must occupy their own row',
  )
})
