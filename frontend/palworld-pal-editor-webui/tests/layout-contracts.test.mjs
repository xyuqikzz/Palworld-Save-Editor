import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const mainCssPath = fileURLToPath(
  new URL('../src/assets/main.css', import.meta.url),
)
const baseCssPath = fileURLToPath(
  new URL('../src/assets/base.css', import.meta.url),
)
const topBarPath = fileURLToPath(
  new URL('../src/components/TopBar.vue', import.meta.url),
)
const entryViewPath = fileURLToPath(
  new URL('../src/views/EntryView.vue', import.meta.url),
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
const palEditorPath = fileURLToPath(
  new URL('../src/components/PalEditor.vue', import.meta.url),
)
const palListPath = fileURLToPath(
  new URL('../src/components/PalList.vue', import.meta.url),
)
const palSkillPickerPath = fileURLToPath(
  new URL('../src/components/modules/PalSkillPicker.vue', import.meta.url),
)
const passiveSkillCardPath = fileURLToPath(
  new URL('../src/components/modules/PassiveSkillCard.vue', import.meta.url),
)
const palSpeciesPickerPath = fileURLToPath(
  new URL('../src/components/modules/PalSpeciesPicker.vue', import.meta.url),
)

test('entry save-source modes share stable workspace dimensions and internal scrolling', () => {
  const source = readFileSync(entryViewPath, 'utf8')
  const shellRule = source.match(/\.entry-shell\s*\{([^}]*)\}/)
  const workspaceRule = source.match(/\.entry-workspace\s*\{([^}]*)\}/)
  const panelRule = source.match(/\.entry-panel\s*\{([^}]*)\}/)
  const sourceListRule = source.match(/\.xgp-sources\s*\{([^}]*)\}/)

  assert.ok(shellRule, 'entry shell layout rule must exist')
  assert.match(
    shellRule[1],
    /grid-template-rows:\s*auto minmax\(0,\s*1fr\) auto[\s\S]*?height:\s*clamp\(620px,\s*calc\(100dvh - 176px\),\s*750px\)[\s\S]*?overflow:\s*hidden/,
    'the homepage shell must keep one responsive height across source modes',
  )
  assert.ok(workspaceRule, 'entry workspace layout rule must exist')
  assert.match(
    workspaceRule[1],
    /grid-template-columns:\s*323px minmax\(0,\s*1fr\)[\s\S]*?min-height:\s*0/,
    'the desktop source navigator and save panel must share one stable workspace row',
  )
  assert.ok(panelRule, 'entry panel layout rule must exist')
  assert.match(
    panelRule[1],
    /display:\s*flex[\s\S]*?width:\s*100%[\s\S]*?min-height:\s*0[\s\S]*?overflow-y:\s*auto/,
    'all source modes must stay inside the fixed workspace and scroll instead of overlapping the footer',
  )
  assert.ok(sourceListRule, 'Game Pass source list layout rule must exist')
  assert.match(
    sourceListRule[1],
    /flex:\s*1 1 0[\s\S]*?grid-auto-rows:\s*max-content[\s\S]*?min-height:\s*0[\s\S]*?overflow-y:\s*auto/,
    'Game Pass source rows must scroll inside the fixed-height workspace without stretching',
  )
  assert.match(source, /@\/assets\/steam\.svg/, 'Steam navigation must use the Steam brand mark')
  assert.match(source, /@\/assets\/xbox\.svg/, 'Game Pass navigation must use the Xbox brand mark')
  assert.match(source, /Entry_Source_Beta/, 'Game Pass navigation must include the BETA badge')
  assert.match(
    source,
    /class="remote-mod-notice" role="note"[\s\S]*?Remote_ModRequiredTitle[\s\S]*?Remote_ModRequiredHint/,
    'live management must warn that PalEditorBridge is installed separately',
  )
  assert.match(source, /Remote_WindowsOnlyTitle/)
  assert.match(source, /class="[^"]*remote-mod-download/)
  assert.match(source, /@click="downloadBridgeMod"/)
  assert.match(source, /window\.pywebview\?\.api\?\.download_bridge_mod/)
  assert.match(source, /modInstallDialog\.value\?\.showModal\(\)/)
  assert.match(source, /class="mod-install-dialog"/)
  assert.match(source, /Remote_ModInstallClientPath/)
  assert.match(source, /Remote_ModInstallXgpClientPath/)
  assert.match(source, /WinGDK/)
  assert.match(source, /Remote_ModInstallServerPath/)
  assert.match(source, /Remote_ModInstallModsPath/)
  assert.doesNotMatch(source, /alert\([^)]*Remote_Mod/)
  assert.match(
    source,
    /\.source-switch\s*\{[^}]*gap:\s*8px/,
    'save-source choices must keep enough space for selected and hover states',
  )
  assert.match(
    source,
    /\.source-switch label:has\(input:focus-visible\)/,
    'save-source focus outlines must only appear for visible keyboard focus',
  )
  assert.doesNotMatch(
    source,
    /\.source-switch label:focus-within/,
    'mouse selection must not leave a second focus outline around the active choice',
  )
})

test('offline and Global Palbox Game Pass panels share one compact source layout', () => {
  const source = readFileSync(entryViewPath, 'utf8')
  const globalStart = source.indexOf(`<template v-if="entryEditMode === 'global-palbox'">`)
  const steamStart = source.indexOf(`<template v-else-if="palStore.SAVE_SOURCE_MODE === 'steam'">`)
  const offlineXgpStart = source.indexOf(`<template v-else-if="palStore.SAVE_SOURCE_MODE === 'xgp'">`)
  const remoteStart = source.indexOf('<template v-else>', offlineXgpStart)
  const globalPanel = source.slice(globalStart, steamStart)
  const offlineXgpPanel = source.slice(offlineXgpStart, remoteStart)

  for (const panel of [globalPanel, offlineXgpPanel]) {
    assert.match(
      panel,
      /class="save-path-row xgp-path-row"/,
      'both Game Pass paths must reserve the same single-line picker width',
    )
    assert.match(
      panel,
      /class="xgp-sources xgp-entry-sources"/,
      'both Game Pass source lists must use the same scrollable spacing',
    )
    assert.match(
      panel,
      /class="entry-primary-row xgp-entry-actions"/,
      'both Game Pass flows must keep discovery and opening in one action row',
    )
  }
  assert.match(
    offlineXgpPanel,
    /class="entry-primary-row xgp-entry-actions"[\s\S]*?discoverXgpSources\(\)[\s\S]*?palStore\.loadSave/,
    'offline Game Pass must keep slot discovery and save loading together',
  )
  assert.match(
    source,
    /\.xgp-path-row\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+150px/,
  )
  assert.match(
    source,
    /\.xgp-entry-actions\s*\{[^}]*gap:\s*10px[^}]*margin-top:\s*auto[^}]*padding-top:\s*12px/,
  )
  assert.doesNotMatch(source, /xgp-load|global-palbox-actions|global-palbox-path-row/)
})

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

test('editor lists keep rows flush while the workspace owns every surrounding gap', () => {
  const mainSource = readFileSync(mainCssPath, 'utf8')
  const viewSource = readFileSync(editorViewPath, 'utf8')

  assert.match(
    mainSource,
    /#EditorMain > \.selection-column > \.flex\s*\{[^}]*padding:\s*10px 0/,
    'list rows must not inherit horizontal panel padding',
  )
  assert.match(
    mainSource,
    /#EditorMain \.title\s*\{[^}]*padding:\s*1px 10px 9px/,
    'only list headings retain a compact horizontal inset',
  )
  assert.match(
    mainSource,
    /#EditorMain \.filter-field\s*\{[^}]*padding-inline:\s*10px/,
    'the search field keeps the same compact inset as the title',
  )
  assert.match(
    viewSource,
    /div#EditorMain\s*\{[^}]*width:\s*100%[^}]*margin-inline:\s*0[^}]*background:\s*var\(--ui-canvas\)/,
    'the editor workspace must paint its own full-width dark canvas',
  )
  assert.match(
    viewSource,
    /div#EditorDiv\s*\{[^}]*overflow-x:\s*clip[^}]*background:\s*var\(--ui-canvas\)/,
    'the page must not expose a differently coloured outer background',
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

test('loaded editor toolbar keeps save actions and page navigation in stable rows', () => {
  const source = readFileSync(topBarPath, 'utf8')
  const baseSource = readFileSync(baseCssPath, 'utf8')
  const viewSource = readFileSync(editorViewPath, 'utf8')

  assert.match(source, /'topbar--loaded': workspaceLoaded/)
  assert.match(source, /palStore\.SAVE_LOADED_FLAG \|\| globalPalboxLoaded\.value/)
  assert.match(
    source,
    /\.op\s*\{[^}]*white-space:\s*nowrap/,
    'toolbar button labels must never collapse into vertical text',
  )
  assert.match(
    source,
    /#topbar\.topbar--loaded\s*\{[^}]*height:\s*112px/,
    'loaded sessions must reserve a fixed primary row and navigation row',
  )
  assert.match(
    source,
    /\.topbar__nav\s*\{[^}]*height:\s*48px[^}]*overflow-x:\s*auto[^}]*overflow-y:\s*hidden/,
    'page navigation must scroll horizontally instead of compressing labels',
  )
  assert.match(
    source,
    /class="nav-item nav-item--return"[\s\S]*?@click="returnToSaveSelection"[\s\S]*?TopBar_Page_Return/,
    'loaded sessions must expose an explicit return action in page navigation',
  )
  assert.match(
    source,
    /async function returnToSaveSelection\(\)[\s\S]*?palStore\.returnToMain\(\)[\s\S]*?router\.push\(\{ name: 'Entry' \}\)/,
    'the return action must close the current session before returning to save selection',
  )
  assert.match(
    source,
    /@media \(max-width:\s*760px\)[\s\S]*?#topbar\.topbar--loaded\s*\{[^}]*height:\s*132px[\s\S]*?\.topbar__primary\s*\{[^}]*grid-template-rows:\s*40px 36px/,
    'narrow windows must give save actions their own compact row',
  )
  assert.match(
    source,
    /settings-drawer[\s\S]*?Settings_SkipUpdateCheck/,
    'secondary preferences must live in the settings drawer',
  )
  assert.match(baseSource, /--editor-top-offset:\s*124px/)
  assert.match(baseSource, /@media \(max-width:\s*760px\)[\s\S]*?--editor-top-offset:\s*140px/)
  assert.match(
    viewSource,
    /@media \(max-width:\s*1120px\)[\s\S]*?div#EditorMain\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)[^}]*width:\s*100%[^}]*min-width:\s*0/,
    'narrow editor windows must use one fluid column instead of a fixed horizontal canvas',
  )
  assert.match(
    viewSource,
    /\.selection-column\s*\{[^}]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)/,
    'player and Pal lists must share the available row before stacking on small screens',
  )
})

test('Pal editor lets the skills background fill the remaining viewport without clipping content', () => {
  const source = readFileSync(palEditorPath, 'utf8')
  const editorRule = source.match(/\.PalEditor\s*\{([^}]*)\}/)
  const skillPanelRule = source.match(/div\.skillPanel\s*\{([^}]*)\}/)

  assert.ok(editorRule, 'PalEditor layout rule must exist')
  assert.ok(skillPanelRule, 'skill panel layout rule must exist')
  assert.doesNotMatch(
    editorRule[1],
    /(?:^|\n)\s*height:\s*var\(--sub-height\)/,
    'PalEditor must not use a fixed viewport height that could clip skill content',
  )
  assert.match(
    editorRule[1],
    /grid-template-rows:\s*max-content minmax\(min-content,\s*1fr\)[\s\S]*?min-height:\s*var\(--sub-height\)[\s\S]*?height:\s*auto[\s\S]*?overflow:\s*visible/,
    'PalEditor must distribute remaining viewport height to its final grid row while allowing content growth',
  )
  assert.match(
    skillPanelRule[1],
    /min-height:\s*100%[\s\S]*?align-self:\s*stretch/,
    'the skills card background must stretch across the remaining grid-row height',
  )
  assert.match(
    source,
    /@media \(max-width:\s*1500px\)\s*\{[\s\S]*?\.PalEditor\s*\{[^}]*grid-template-rows:\s*max-content max-content minmax\(min-content,\s*1fr\)/,
    'the stacked layout must reserve its final flexible row for the skills card',
  )
})

test('Pal identity controls match the standard editor geometry without repeating the summary portrait', () => {
  const source = readFileSync(palEditorPath, 'utf8')
  const pickerSource = readFileSync(palSpeciesPickerPath, 'utf8')

  assert.match(
    source,
    /<img class="pal-summary__portrait"[\s\S]*?:show-selected-icon="false"/,
    'the summary must use a dedicated portrait class while the species field hides its duplicate portrait',
  )
  assert.match(
    pickerSource,
    /showSelectedIcon:\s*\{\s*type:\s*Boolean,\s*default:\s*true\s*\}[\s\S]*?<img\s+v-if="showSelectedIcon && selectedPal"/,
    'the shared picker must support hiding only its selected portrait',
  )
  assert.equal(
    source.match(/class="editField identity-field"/g)?.length,
    2,
    'species and nickname must use the same aligned field structure',
  )
  assert.match(
    source,
    /\.pal-summary__portrait\s*\{[^}]*width:\s*64px[^}]*height:\s*64px/,
    'the dedicated summary portrait must not inherit the compact list icon size',
  )
  assert.match(
    source,
    /:global\(#EditorMain \.basic-fields > \.identity-field\)\s*\{[^}]*grid-template-columns:\s*100px minmax\(0, 1fr\) 32px[^}]*min-height:\s*34px[^}]*gap:\s*6px/,
    'identity labels and controls must use the same compact geometry as the other editor rows',
  )
  assert.match(
    source,
    /:global\(#EditorMain \.identity-field > p\.const\)[\s\S]*?min-height:\s*34px[\s\S]*?height:\s*34px/,
    'identity labels and their editable controls must share the same height',
  )
  assert.doesNotMatch(
    source,
    /identity-field:focus-within|identity-field[^}]*border-left/,
    'identity rows must retain standard independent controls instead of a custom divided surface',
  )
})

test('NPC basic information omits the gender editor', () => {
  const source = readFileSync(palEditorPath, 'utf8')

  assert.match(
    source,
    /<div class="flex-h attribute-row" v-if="!palStore\.SELECTED_PAL_DATA\.IsHuman">\s*<div class="editField" v-if="palStore\.SELECTED_PAL_DATA\.Gender \|\| !palStore\.HIDE_INVALID_OPTIONS">[\s\S]*?Editor_Gender[\s\S]*?<div class="editField">[\s\S]*?Editor_Variant/,
    'gender and Pal-only variant controls must not render for NPC records',
  )
})

test('awakened Pals expose the requested list marker and basic-info editor', () => {
  const editorSource = readFileSync(palEditorPath, 'utf8')
  const listSource = readFileSync(palListPath, 'utf8')

  assert.match(
    listSource,
    /v-if="pal\.IsAwakened" class="pal-awakened-label"[\s\S]*?PalList_AwakenedMarker/,
    'the Pal list must render the awakened marker from the initial summary payload',
  )
  assert.match(
    listSource,
    /\.pal-awakened-label\s*\{[^}]*color:\s*oklch\(0\.84 0\.16 92\)/,
    'the awakened marker must use the requested yellow emphasis',
  )
  assert.match(
    listSource,
    /v-if="pal\.IsBOSS" class="pal-variant-label is-boss"[\s\S]*?Variant_Boss/,
    'the Pal list must give the BOSS marker a dedicated state class',
  )
  assert.match(
    listSource,
    /\.pal-variant-label\.is-boss\s*\{[^}]*color:\s*var\(--ui-danger\)/,
    'the Pal-list BOSS marker must use the semantic red colour',
  )
  assert.match(
    editorSource,
    /class="editField awakening-field"[\s\S]*?Editor_Awakening_Awakened[\s\S]*?Editor_Awakening_NotAwakened[\s\S]*?swapAwakening[\s\S]*?name="IsAwakened"[\s\S]*?<AppIcon name="refresh"/,
    'basic info must present awakening as a standard editable status row',
  )
  assert.doesNotMatch(
    editorSource,
    /Editor_Awakening_Effect|AwakeningStatusMultiplier/,
    'the awakening row must not repeat the IV multiplier and estimate explanation',
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

test('player summary uses content height and keeps its information aligned at the top', () => {
  const source = readFileSync(playerEditorPath, 'utf8')

  assert.match(
    source,
    /<header class="player-summary-heading">[\s\S]*?<h2>[\s\S]*?Editor_Basic_Info[\s\S]*?<div class="player-summary-identity">/,
    'the summary heading must group the title with the current player identity',
  )
  assert.match(
    source,
    /:global\(#EditorMain \.PalEditor\.player-editor-layout \.EditorItem\.basicInfo\.player-summary-card\)\s*\{[^}]*grid-auto-rows:\s*max-content[^}]*align-content:\s*start[^}]*flex:\s*0 0 auto/,
    'the summary card must not grow into unused editor height',
  )
  assert.doesNotMatch(
    source,
    /player-summary-eyebrow/,
    'the summary must not repeat its context above the basic information title',
  )
})

test('player inventory uses the game-style split layout and warehouse-style slot editor', () => {
  const source = readFileSync(inventoryEditorPath, 'utf8')
  const playerSource = readFileSync(playerEditorPath, 'utf8')

  for (const marker of [
    'class="inventory-game-layout"',
    'class="inventory-board"',
    'class="inventory-slot-grid"',
    'v-for="slot in displaySlots"',
    'v-for="container in backpackContainers"',
    'class="equipment-stage"',
    'v-for="section in leftEquipmentSections"',
    'v-for="section in rightEquipmentSections"',
    'class="equipment-bottom"',
    'v-for="section in bottomEquipmentSections"',
    'grid-template-columns: clamp(360px, 36%, 680px) minmax(360px, 1fr);',
    'grid-template-columns: repeat(6, minmax(44px, 1fr));',
    'grid-auto-rows: max-content;',
    'container-type: inline-size;',
    '--inventory-slot-size: clamp(48.5px, calc(6cqw - 11.5px), 101.84px);',
    'width: var(--inventory-slot-size);',
    'grid-template-columns: var(--inventory-slot-size);',
    'grid-template-columns: repeat(2, var(--inventory-slot-size));',
    'grid-auto-columns: var(--inventory-slot-size);',
    'grid-template-columns: repeat(5, var(--inventory-slot-size));',
    'min-height: 710px;',
    'overflow-y: auto;',
    'grid-auto-flow: column;',
    'grid-template-rows: repeat(4, var(--inventory-slot-size));',
    'grid-column: 1 / 3;',
    'grid-row: 1 / 3;',
    'justify-self: end;',
    '<AppIcon v-else-if="slot.state === \'empty\'" class="inventory-slot__plus" name="plus"',
    'const slotButton = event.currentTarget',
    'selectedSlotButton.value = slotButton',
    'function shouldShowQuantity(item)',
    'v-if="shouldShowQuantity(slot.item)"',
    'const selectedCountEditable = computed(() => selectedMaxStack.value > 1)',
    'class="inventory-slot-editor"',
    '<label v-if="selectedCountEditable" class="inventory-slot-editor__count">',
    '<div class="inventory-slot-editor__actions">',
    '.equipment-slot.is-drop-target {',
  ]) {
    assert.ok(source.includes(marker), 'missing inventory-grid marker: ' + marker)
  }
  assert.match(
    source,
    /<button\s+v-if="selectedCountEditable"[\s\S]{0,300}Inventory_SaveCountTitle/,
    'maximum-stack-one items must not render the save-count action',
  )
  assert.match(
    playerSource,
    /\.player-editor-layout > \.inventory-editor[\s\S]{0,100}flex:\s*1 0 710px;[\s\S]{0,100}min-height:\s*710px;/,
    'the inventory must grow into available player-editor viewport height',
  )
  assert.match(source, /grid-template-rows:\s*auto minmax\(0, 1fr\);/)
  assert.doesNotMatch(source, /inventory-board__toolbar/)
  assert.doesNotMatch(source, /v-for="container in containers"|slot-inspector|width:\s*min\(100%,\s*470px\)/)
})

test('enlarged accessory and food sections share one bottom row without colliding with weapons', () => {
  const source = readFileSync(inventoryEditorPath, 'utf8')

  assert.match(
    source,
    /\.equipment-bottom\s*\{[\s\S]{0,260}grid-template-columns:\s*max-content minmax\(0, 1fr\);/,
  )
  assert.match(
    source,
    /\.equipment-bottom\s*\{[\s\S]{0,260}align-items:\s*end;/,
  )
})

test('inventory omits its redundant inner title and keeps editor item names legible', () => {
  const source = readFileSync(inventoryEditorPath, 'utf8')

  assert.doesNotMatch(source, /Editor_Inventory/)
  assert.ok(
    source.includes('.inventory-slot-editor > header strong { font-size: 12px; }'),
    'occupied item names must remain visible in the slot editor header',
  )
})
test('skill sections use consistent item sizing and title-row add actions', () => {
  const source = readFileSync(palEditorPath, 'utf8')
  const pickerSource = readFileSync(palSkillPickerPath, 'utf8')
  const passiveCardSource = readFileSync(passiveSkillCardPath, 'utf8')
  const mainSource = readFileSync(mainCssPath, 'utf8')

  assert.equal(
    source.match(/<header class="skill-section-header">/g)?.length,
    3,
    'passive, equipped, and mastered skill titles must share the same header structure',
  )
  assert.equal(
    source.match(/\sicon-only(?:\s|>)/g)?.length,
    3,
    'every skill section must expose an icon-only add action beside its title',
  )
  assert.match(
    source,
    /\.skill-item-grid\s*\{[^}]*display:\s*grid[^}]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)/,
    'every skill group must render in at most two columns',
  )
  assert.match(
    source,
    /\.skill-section\s*\{[^}]*container-name:\s*skill-section[^}]*container-type:\s*inline-size/,
    'each skill section must expose its own width to responsive item layouts',
  )
  assert.match(
    source,
    /@container\s+skill-section\s*\(max-width:\s*460px\)\s*\{\s*\.skill-item-grid\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)/,
    'passive and active skill items must occupy a full row when their section is too narrow',
  )
  assert.match(
    mainSource,
    /#EditorMain \.EditorItem\.skillsPanel\s*\{[^}]*grid-template-columns:\s*repeat\(3,\s*minmax\(0,\s*1fr\)\)/,
    'the three skill sections must receive equal panel widths',
  )
  assert.match(
    passiveCardSource,
    /\.passive-skill-card\s*\{[^}]*min-height:\s*40px/,
    'passive skill cards must use the compact height',
  )
  assert.match(
    source,
    /\.skill-item-grid\s*\{[^}]*grid-auto-rows:\s*40px[\s\S]*?\.skill-item-row\s*\{[^}]*height:\s*40px/,
    'all skill groups must use the same item row height',
  )
  assert.match(
    pickerSource,
    /:aria-label="iconOnly \? placeholderText : undefined"[\s\S]*?<AppIcon :name="iconOnly \? 'plus' : 'chevron-down'"/,
    'the icon trigger must retain an accessible name and use a plus icon',
  )
  assert.equal(
    source.match(/class="active-skill-element"/g)?.length,
    2,
    'equipped and mastered skill tooltips must keep the element label and icon on one row',
  )
  assert.doesNotMatch(
    source,
    /\{\{ palStore\.ACTIVE_SKILLS\[skill\]\?\.Element \}\}/,
    'skill tooltips must not repeat the internal English element name',
  )
  assert.equal(
    source.match(/class="active-skill-tag"/g)?.length,
    4,
    'unique and skill-fruit states must use text tags in both active skill groups',
  )
  assert.doesNotMatch(source, /✨|🍐/, 'active skill tags must not use decorative icons')
})

test('estimated stats finish the left panel while work suitability remains in the right panel', () => {
  const source = readFileSync(palEditorPath, 'utf8')
  const basicPanelStart = source.indexOf('class="EditorItem item flex-v basicInfo"')
  const statsPanelStart = source.indexOf('class="EditorItem flex-v item left statsPanel"')
  const skillsPanelStart = source.indexOf('class="EditorItem item flex-v left skillPanel skillsPanel"')
  const basicPanelSource = source.slice(basicPanelStart, statsPanelStart)
  const statsPanelSource = source.slice(statsPanelStart, skillsPanelStart)

  assert.ok(
    basicPanelStart >= 0 && statsPanelStart > basicPanelStart && skillsPanelStart > statsPanelStart,
    'the basic, stats, and skill panels must keep their expected order',
  )
  assert.match(
    basicPanelSource,
    /class="estimated-group">\s*<div class="palInfo"/,
    'estimated metrics must render without a title at the bottom of the left basic-info panel',
  )
  assert.doesNotMatch(
    basicPanelSource,
    /Editor_Estimated_Stats/,
    'the estimated metrics area must not render its title',
  )
  assert.match(
    statsPanelSource,
    /stat-group--condenser[\s\S]*?stat-group--suitabilities suitabilityPanel[\s\S]*?Editor_Suitabilities/,
    'work suitability must remain after the condenser in the right panel',
  )
  assert.doesNotMatch(
    statsPanelSource,
    /Editor_Estimated_Stats|class="palInfo"/,
    'the right panel must no longer contain estimated metrics',
  )
  assert.doesNotMatch(
    source,
    /class="EditorItem[^"]*suitabilityPanel/,
    'work suitability must no longer render as a separate full-width card',
  )
  assert.match(
    source,
    /:global\(#EditorMain \.PalEditor > \.EditorItem\.basicInfo\),\s*:global\(#EditorMain \.PalEditor > \.EditorItem\.statsPanel\)\s*\{[^}]*align-self:\s*stretch/,
    'the left basic-info card and right stats card must stretch to the same row height',
  )
  assert.match(
    source,
    /\.estimated-group\s*\{(?=[^}]*display:\s*flex)(?=[^}]*width:\s*100%)(?=[^}]*border-top:\s*1px solid var\(--ui-border\))[^}]*\}/,
    'the left estimated group must keep the existing section spacing and divider',
  )
  assert.match(
    source,
    /\.statsPanel\s*\{(?=[^}]*position:\s*relative)(?=[^}]*container-name:\s*stats-panel)(?=[^}]*container-type:\s*inline-size)(?=[^}]*flex-direction:\s*column)[^}]*\}/,
    'the stats card must expose its actual inline size to responsive descendants',
  )
  assert.match(
    source,
    /\.stat-primary-grid\s*\{(?=[^}]*width:\s*100%)[^}]*grid-template-columns:\s*repeat\(auto-fit,\s*minmax\(min\(100%,\s*260px\),\s*1fr\)\)/,
    'individual values and soul enhancements must wrap when either column would become unreadable',
  )
  assert.match(
    source,
    /@container stats-panel \(max-width:\s*537px\)[\s\S]*?\.stat-group--souls\s*\{(?=[^}]*border-top:\s*1px solid var\(--ui-border\))(?=[^}]*border-left:\s*0)[^}]*\}/,
    'stacked enhancement groups must switch their separator from vertical to horizontal',
  )
  assert.match(
    statsPanelSource,
    /stat-group--condenser[\s\S]*?Editor_Condenser[\s\S]*?<\/p>\s*<div class="editField spaceBetween">/,
    'the condenser level and slider must wrap onto a row below its heading',
  )
  assert.match(
    source,
    /\.suitabilityPanel \.skillList\s*\{[^}]*grid-template-columns:\s*repeat\(3,\s*minmax\(0,\s*1fr\)\)/,
    'work suitability must show three controls per row at the target width',
  )
  assert.match(
    source,
    /:global\(#EditorMain button\.edit\.stats-max-all\)\s*\{(?=[^}]*position:\s*absolute)(?=[^}]*top:\s*18px)(?=[^}]*right:\s*18px)[^}]*\}/,
    'the enhancement MAX action must be positioned at the top-right without taking layout height',
  )
  assert.match(
    statsPanelSource,
    /class="edit stats-max-all"[\s\S]*?PalEditor_MaxAllEnhancements[\s\S]*?maxAllEnhancements/,
    'the stats card must expose one MAX action for all enhancement groups',
  )
  assert.match(
    statsPanelSource,
    /stat-group-header[\s\S]*?Editor_Suitabilities[\s\S]*?class="edit suitability-max-all"[\s\S]*?maxAllSuitabilities/,
    'work suitability must expose its own MAX action in the section heading',
  )
  const statRowRule = source.match(/\.statsPanel \.spaceBetween\s*\{([^}]*)\}/)?.[1] || ''
  assert.match(statRowRule, /display:\s*grid/)
  assert.match(statRowRule, /grid-template-columns:\s*minmax\(0,\s*1fr\) minmax\(120px,\s*46%\)/)
  assert.doesNotMatch(statRowRule, /border/, 'stat rows must use spacing instead of repeated dividers')
  assert.match(
    source,
    /\.stat-group--suitabilities\s*\{[^}]*width:\s*100%/,
    'work suitability must not shrink its localized heading to its min-content width',
  )
})

test('equipped skill picker only offers mastered skills that are not already equipped', () => {
  const source = readFileSync(palEditorPath, 'utf8')

  assert.match(
    source,
    /const equippableMasteredSkills = computed\([\s\S]*?MasteredWaza[\s\S]*?new Set\(palStore\.SELECTED_PAL_DATA\?\.EquipWaza[\s\S]*?\.filter\(skill => !equippedSkills\.has\(skill\)\)/,
    'the equipped picker source must be derived from mastered skills and exclude equipped entries',
  )
  assert.match(
    source,
    /Editor_Equipped_Skills[\s\S]*?<PalSkillPicker[\s\S]*?:options="equippableMasteredSkills"[\s\S]*?@select="palStore\.SELECTED_PAL_DATA\.add_EquipWaza\(\$event\.InternalName\)"/,
    'the equipped title add action must open the mastered-skill picker and equip its selection',
  )
  assert.doesNotMatch(
    source,
    /@click="palStore\.SELECTED_PAL_DATA\.add_EquipWaza"/,
    'mastered rows must no longer expose separate equip buttons',
  )
})
