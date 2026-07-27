import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const remoteViewPath = fileURLToPath(
  new URL('../src/views/RemoteServerView.vue', import.meta.url),
)
const storePath = fileURLToPath(
  new URL('../src/stores/paleditor.js', import.meta.url),
)
const remotePalCardPath = fileURLToPath(
  new URL('../src/components/modules/RemotePalCard.vue', import.meta.url),
)

test('remote item and Pal grants reuse the editor catalog modules', () => {
  const source = readFileSync(remoteViewPath, 'utf8')

  assert.match(source, /import ItemPicker from '@\/components\/modules\/ItemPicker\.vue'/)
  assert.match(source, /import RemotePalGrantForm from '@\/components\/modules\/RemotePalGrantForm\.vue'/)
  assert.match(
    source,
    /<ItemPicker[\s\S]*?v-model="itemForm\.itemId"[\s\S]*?:options="palStore\.ITEM_CATALOG_RESULTS"/,
  )
  assert.match(source, /<RemotePalGrantForm[\s\S]*?:pal-options="grantablePals"/)
  assert.match(source, /palStore\.searchItemCatalog\(''\)/)
  assert.match(source, /palStore\.fetchStaticData\(\)/)
  assert.doesNotMatch(
    source,
    /Remote_ItemId[\s\S]{0,160}<input v-model\.trim="itemForm\.itemId"/,
  )
  assert.doesNotMatch(
    source,
    /Remote_PalCharacterId[\s\S]{0,160}<input v-model\.trim="palForm\.characterId"/,
  )
})

test('remote Pal grant exposes shared passive presets and persistent attributes', () => {
  const grantFormPath = fileURLToPath(
    new URL('../src/components/modules/RemotePalGrantForm.vue', import.meta.url),
  )
  const source = readFileSync(grantFormPath, 'utf8')
  const viewSource = readFileSync(remoteViewPath, 'utf8')

  assert.match(source, /import PassivePresetDialog/)
  assert.match(source, /import PassiveSkillCard/)
  assert.match(source, /import PalSkillPicker/)
  assert.match(source, /@apply="applyPassivePreset"/)
  assert.match(source, /const ivControls = computed\(\(\) => \[/)
  assert.match(source, /key: 'hp'/)
  assert.match(source, /key: 'shot'/)
  assert.match(source, /key: 'defense'/)
  assert.match(source, /image: 'max_hp'/)
  assert.match(source, /image: 'attack'/)
  assert.match(source, /image: 'work_speed'/)
  assert.match(source, /`\/image\/player_attributes\/\$\{control\.image\}`/)
  assert.match(source, /v-model\.number="form\.ivs\[control\.key\]"/)
  assert.match(source, /:max="ivMaximum"/)
  assert.match(source, /form\.enhancements\.condensation/)
  assert.match(source, /key: 'soulCraftSpeed'/)
  assert.match(source, /v-model\.number="form\.enhancements\[control\.key\]"/)
  assert.match(source, /:max="soulEnhancementMaximum"/)
  assert.match(source, /:max="condensationMaximum"/)
  assert.match(source, /REMOTE_PAL_GRANT_DRAFT_STORAGE_KEY/)
  assert.match(source, /watch\(\s*form,[\s\S]*?localStorage\.setItem/)
  assert.match(source, /class="remote-pal-grant__layout"/)
  assert.match(source, /class="remote-pal-grant__pal-preview"/)
  assert.match(source, /class="remote-pal-grant__stat-list/)
  assert.match(source, /class="remote-pal-grant__condensation"/)
  assert.match(source, /class="remote-pal-grant__level-max"/)
  assert.match(source, /@click="maximizePalGrantLevel\(form\)"/)
  assert.match(viewSource, /:level-maximum="palStore\.MAX_LEVEL"/)
  assert.doesNotMatch(
    viewSource,
    /:level-maximum="palStore\.HIDE_INVALID_OPTIONS \? palStore\.MAX_LEVEL : palStore\.MAX_INVALID_LEVEL"/,
  )
  assert.match(
    source,
    /v-model\.number="form\.enhancements\.condensation"[\s\S]*?type="range"/,
  )
  assert.doesNotMatch(source, /form\.ivs\.melee/)
})

test('remote item grant requires an actual catalog selection', () => {
  const source = readFileSync(remoteViewPath, 'utf8')

  assert.match(source, /async function grantSelectedItem\(\)/)
  assert.match(source, /if \(!itemForm\.itemId \|\| !selectedPlayerId\.value\) return/)
  assert.match(source, /@submit\.prevent="grantSelectedItem"/)
  assert.match(
    source,
    /:disabled="palStore\.REMOTE_LOADING \|\| !selectedPlayerId \|\| !itemForm\.itemId"/,
  )
})

test('cheat options remain available in a connected remote session', () => {
  const topBarPath = fileURLToPath(
    new URL('../src/components/TopBar.vue', import.meta.url),
  )
  const source = readFileSync(topBarPath, 'utf8')

  assert.match(
    source,
    /:disabled="palStore\.LOADING_FLAG \|\| \(!palStore\.SAVE_LOADED_FLAG && !palStore\.REMOTE_CONNECTED\)"/,
  )
})
test('the store exposes static data loading to remote-only sessions', () => {
  const source = readFileSync(storePath, 'utf8')

  assert.match(source, /return\s*\{[\s\S]*?\bfetchStaticData,[\s\S]*?\bloadSave,/)
})

test('remote commands do not trigger an automatic player-data refresh', () => {
  const viewSource = readFileSync(remoteViewPath, 'utf8')
  const storeSource = readFileSync(storePath, 'utf8')
  const runCommandSource = viewSource.match(
    /async function runCommand\([\s\S]*?\n\}/,
  )?.[0] || ''

  assert.doesNotMatch(runCommandSource, /refreshRemote\(/)
  assert.doesNotMatch(runCommandSource, /loadRemotePlayerDetails\(/)
  assert.doesNotMatch(runCommandSource, /loadRemotePlayerInventory\(/)
  assert.doesNotMatch(runCommandSource, /loadRemotePlayerPals\(/)
  assert.doesNotMatch(runCommandSource, /await refreshRemote\(/)
  assert.match(
    storeSource,
    /async function refreshRemoteStatus\(\{ background = false \} = \{\}\)/,
  )
  assert.match(
    storeSource,
    /responseRevision < REMOTE_SESSION_REVISION\.value/,
  )
})

test('runtime guild, inventory, Party Pal, and Pal Terminal data use selected-player lazy reads', () => {
  const viewSource = readFileSync(remoteViewPath, 'utf8')
  const storeSource = readFileSync(storePath, 'utf8')

  assert.match(storeSource, /const REMOTE_GUILDS = ref\(\[\]\)/)
  assert.match(storeSource, /const REMOTE_PLAYER_DETAILS = ref\(null\)/)
  assert.match(
    storeSource,
    /async function loadRemoteGuilds\(\)[\s\S]*?\/api\/remote\/guilds/,
  )
  assert.match(
    storeSource,
    /async function loadRemotePlayerDetails\(playerId\)[\s\S]*?\/api\/remote\/players\/\$\{encodedPlayerId\}\/details/,
  )
  assert.match(
    storeSource,
    /async function loadRemotePlayerInventory\(playerId[\s\S]*?\/api\/remote\/players\/\$\{encodedPlayerId\}\/inventory/,
  )
  assert.match(
    storeSource,
    /async function loadRemotePlayerPals\(\s*playerId[\s\S]*?\/api\/remote\/players\/\$\{encodedPlayerId\}\/pals/,
  )
  assert.match(
    storeSource,
    /collection=\$\{encodedCollection\}&page=\$\{normalizedPage\}/,
  )
  assert.match(
    viewSource,
    /watch\(selectedPlayerId,[\s\S]*?loadRemotePlayerDetails\(playerIdValue\)/,
  )
  assert.match(
    viewSource,
    /selectRemoteTab\(tab\)[\s\S]*?loadRemotePlayerInventory/,
  )
  assert.match(
    viewSource,
    /selectRemoteTab\(tab\)[\s\S]*?loadRemotePlayerPals/,
  )
  assert.match(viewSource, /activeTab === 'inventory'/)
  assert.match(viewSource, /activeTab === 'pals'/)
  assert.match(viewSource, /inventoryContainers/)
  assert.match(viewSource, /backpackContainers/)
  assert.match(viewSource, /equipmentSections/)
  assert.match(viewSource, /selectedInventoryContainer/)
  assert.match(viewSource, /inventorySlots\(selectedInventoryContainer\)/)
  assert.match(viewSource, /class="inventory-slot-grid"/)
  assert.match(viewSource, /class="equipment-board"/)
  assert.match(viewSource, /class="equipment-stage"/)
  assert.match(viewSource, /class="equipment-model-space"/)
  assert.match(viewSource, /class="equipment-slot-grid"/)
  assert.match(viewSource, /class="runtime-player-level"/)
  assert.match(
    viewSource,
    /<progress v-if="detailHealth\.percent !== null" :value="healthPercent" max="100">/,
  )
  assert.match(viewSource, /T_prt_pal_skill_base_02\.webp/)
  assert.match(viewSource, /class="runtime-attributes"/)
  assert.match(viewSource, /runtimeAbilityRows/)
  assert.match(viewSource, /PlayerAttribute_max_sp/)
  assert.match(viewSource, /palEntries/)
  assert.match(viewSource, /Remote_PalCollectionParty/)
  assert.match(viewSource, /Remote_PalCollectionTerminal/)
  assert.match(viewSource, /<RemotePalCard/)
  assert.doesNotMatch(viewSource, /class="inventory-items"/)
})

test('live Pal tabs hide counts and reveal real details only on hover or focus', () => {
  const viewSource = readFileSync(remoteViewPath, 'utf8')
  const cardSource = readFileSync(remotePalCardPath, 'utf8')
  const tabSource = viewSource.match(
    /<nav class="remote-tabs"[\s\S]*?<\/nav>/,
  )?.[0] || ''

  assert.doesNotMatch(tabSource, /inventory\?\.occupiedSlotCount/)
  assert.doesNotMatch(tabSource, /pals\?\.count/)
  assert.match(viewSource, /const palCollection = ref\('party'\)/)
  assert.match(viewSource, /selectPalCollection\('party'\)/)
  assert.match(viewSource, /selectPalCollection\('palbox'\)/)
  assert.match(viewSource, /:class="`pal-collection--\$\{palCollection\}`"/)

  assert.match(cardSource, /import PassiveSkillCard/)
  assert.match(cardSource, /@mouseenter="openDetail"/)
  assert.match(cardSource, /@focus="openDetail"/)
  assert.match(cardSource, /v-if="detailOpen"/)
  assert.match(cardSource, /role="tooltip"/)
  assert.match(cardSource, /<PassiveSkillCard/)
  assert.match(cardSource, /:skill="palStore\.PASSIVE_SKILLS\[skill\]"/)
})

test('live inventory hides the internal drop buffer and maps armor slots to game equipment regions', () => {
  const source = readFileSync(remoteViewPath, 'utf8')

  assert.match(source, /const visibleBackpackContainerTypes = new Set\(\['COMMON', 'ESSENTIAL'\]\)/)
  assert.doesNotMatch(source, /visibleBackpackContainerTypes = new Set\([^)]*DROP_SLOT/)
  assert.match(source, /key: 'accessory',[\s\S]*?slotIndices: \[2, 3, 6, 7\]/)
  assert.match(source, /key: 'head',[\s\S]*?slotIndices: \[0\]/)
  assert.match(source, /key: 'body',[\s\S]*?slotIndices: \[1\]/)
  assert.match(source, /key: 'shield',[\s\S]*?slotIndices: \[4\]/)
  assert.match(source, /key: 'glider',[\s\S]*?slotIndices: \[5\]/)
  assert.match(source, /key: 'sphere-module',[\s\S]*?slotIndices: \[8\]/)
  assert.match(source, /leftEquipmentSections/)
  assert.match(source, /rightEquipmentSections/)
  assert.match(source, /foodEquipmentSection/)
})

test('inventory and equipment item icons stay centered regardless of intrinsic image size', () => {
  const source = readFileSync(remoteViewPath, 'utf8')

  assert.match(
    source,
    /\.inventory-slot__icon,\s*\.equipment-slot__icon\s*\{[\s\S]*?position:\s*absolute;[\s\S]*?top:\s*50%;[\s\S]*?left:\s*50%;[\s\S]*?width:\s*calc\(100% - 14px\);[\s\S]*?height:\s*calc\(100% - 14px\);[\s\S]*?object-fit:\s*contain;[\s\S]*?transform:\s*translate\(-50%, -50%\);/,
  )
})

test('runtime PascalCase inventory container IDs resolve to known labels', () => {
  const source = readFileSync(remoteViewPath, 'utf8')
  const mappingBody = source.match(
    /const inventoryContainerLabelKeys = Object\.freeze\(\{([\s\S]*?)\}\)/,
  )?.[1]

  assert.ok(mappingBody)
  const mapping = Function(`"use strict"; return ({${mappingBody}})`)()
  assert.equal(mapping.Common, 'Inventory_Container_Common')
  assert.equal(mapping.DropSlot, 'Inventory_Container_DropSlot')
  assert.equal(mapping.Essential, 'Inventory_Container_Essential')
  assert.equal(mapping.WeaponLoadout, 'Inventory_Container_WeaponLoadout')
  assert.equal(mapping.PlayerEquipArmor, 'Inventory_Container_ArmorEquipment')
  assert.equal(mapping.FoodEquip, 'Inventory_Container_FoodEquipment')
})

test('live map uses the runtime bridge snapshot and the save-editor map assets', () => {
  const mapPath = fileURLToPath(
    new URL('../src/components/modules/RemoteRuntimeMap.vue', import.meta.url),
  )
  const viewSource = readFileSync(remoteViewPath, 'utf8')
  const storeSource = readFileSync(storePath, 'utf8')
  const mapSource = readFileSync(mapPath, 'utf8')

  assert.match(viewSource, /import RemoteRuntimeMap/)
  assert.match(viewSource, /can\('map\.read'\)/)
  assert.match(viewSource, /activeTab === 'map'/)
  assert.match(viewSource, /selectRemoteTab\('map'\)/)
  assert.match(viewSource, /RemoteMap_CapabilityUnavailable/)
  assert.doesNotMatch(
    viewSource,
    /<button\s+v-if="can\('map\.read'\)"[\s\S]*?Remote_TabMap/,
  )
  assert.match(viewSource, /@select-player="openMapPlayer"/)
  assert.match(storeSource, /const REMOTE_MAP_DATA = ref\(null\)/)
  assert.match(
    storeSource,
    /async function loadRemoteMapData\(\)[\s\S]*?\/api\/remote\/map/,
  )
  assert.match(mapSource, /t_worldmap\.webp/)
  assert.match(mapSource, /t_treemap\.webp/)
  assert.match(mapSource, /K2_GetActorLocation|positionFor\(player\)/)
  assert.match(mapSource, /REFRESH_INTERVAL_MS = 3000/)
  assert.match(mapSource, /guildFilter/)
  assert.match(mapSource, /player\.guildId \|\| player\.guild_id/)
  assert.match(mapSource, /emit\('select-player'/)
})

test('remote management uses the save-editor workspace design language', () => {
  const source = readFileSync(remoteViewPath, 'utf8')

  assert.match(source, /class="remote-shell"/)
  assert.match(source, /class="remote-source"/)
  assert.match(source, /class="remote-metrics"/)
  assert.match(source, /class="remote-workspace"/)
  assert.match(source, /class="remote-console"/)
  assert.match(source, /class="detail-skeleton"/)
  assert.match(source, /<AppIcon name="overview"/)
  assert.match(source, /<AppIcon name="box"/)
  assert.match(source, /<AppIcon name="paw"/)
  assert.match(source, /border-radius: var\(--ui-radius-lg\)/)
  assert.match(source, /box-shadow: var\(--ui-shadow-sm\)/)
  assert.doesNotMatch(source, /class="remote-page__actions"/)
})
