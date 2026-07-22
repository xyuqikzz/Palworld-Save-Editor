import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const mainCssPath = fileURLToPath(
  new URL('../src/assets/main.css', import.meta.url),
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
    /display:\s*flex[\s\S]*?width:\s*100%[\s\S]*?min-height:\s*0/,
    'Steam and Game Pass modes must occupy the same flexible panel geometry',
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
    /@media \(max-width:\s*1380px\)\s*\{[\s\S]*?\.PalEditor\s*\{[^}]*grid-template-rows:\s*max-content max-content minmax\(min-content,\s*1fr\)/,
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

test('occupied inventory slots give item details and quantity controls separate rows', () => {
  const source = readFileSync(inventoryEditorPath, 'utf8')

  assert.match(
    source,
    /<div class="slot-main">[\s\S]*?<ItemIcon[\s\S]*?<div class="slot-copy">[\s\S]*?<\/div>[\s\S]*?<\/div>[\s\S]*?<div class="slot-controls">[\s\S]*?<input[\s\S]*?class="slot-count"[\s\S]*?<div class="slot-actions">/,
    'the item identity row must stay separate from the quantity and action controls',
  )
  assert.match(
    source,
    /\.slot-main\s*\{[^}]*flex:\s*1 0 100%/,
    'the primary item row must occupy the full slot width',
  )
  assert.match(
    source,
    /\.slot-controls\s*\{[^}]*flex:\s*1 0 100%[^}]*flex-wrap:\s*wrap/,
    'quantity controls must occupy the full row and wrap on narrow cards',
  )
  assert.match(
    source,
    /\.slot-count\s*\{[^}]*flex:\s*1 1 120px[^}]*max-width:\s*160px/,
    'the quantity input must grow beyond the old fixed-width control',
  )
})

test('inventory omits its redundant inner title and keeps occupied item names legible', () => {
  const source = readFileSync(inventoryEditorPath, 'utf8')

  assert.doesNotMatch(
    source,
    /<h2[^>]*>[\s\S]*?Editor_Inventory[\s\S]*?<\/h2>/,
    'the selected player tab already names the inventory section',
  )
  assert.match(
    source,
    /\.slot-copy strong\s*\{[^}]*color:\s*var\(--ui-text\)/,
    'occupied item names must explicitly use the primary theme text color',
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
    /\.statsPanel\s*\{(?=[^}]*position:\s*relative)[^}]*grid-template-areas:\s*"iv souls"\s*"condenser condenser"\s*"suitabilities suitabilities"/,
    'the stats card must reserve full-width rows for the condenser and work suitability without a MAX layout row',
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
  assert.doesNotMatch(statRowRule, /border/, 'stat rows must use spacing instead of repeated dividers')
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
