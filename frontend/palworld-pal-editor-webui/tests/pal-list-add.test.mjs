import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const palListPath = fileURLToPath(
  new URL('../src/components/PalList.vue', import.meta.url),
)
const palSpeciesPickerPath = fileURLToPath(
  new URL('../src/components/modules/PalSpeciesPicker.vue', import.meta.url),
)

test('Pal add action centers its icon and opens the species dialog directly', () => {
  const source = readFileSync(palListPath, 'utf8')
  const pickerSource = readFileSync(palSpeciesPickerPath, 'utf8')

  assert.match(
    source,
    /\.add_pal\s*\{[^}]*display:\s*inline-flex[^}]*align-items:\s*center[^}]*justify-content:\s*center/,
    'the plus icon must be centered by the add button',
  )
  assert.match(
    source,
    /@click="openAddPal"/,
    'the add button must use the flow that opens the species dialog',
  )
  assert.match(
    source,
    /<PalSpeciesPicker[\s\S]*?ref="addSpeciesPicker"/,
    'the add flow must keep a reference to the species picker',
  )
  assert.match(
    source,
    /function openAddPal\(\)\s*\{\s*loadAddPalPassivePresets\(\)\s*addSpeciesPicker\.value\?\.open\(\)\s*\}/,
    'one click must load shared presets and immediately open the already-mounted species picker',
  )
  assert.match(
    source,
    /<PalSpeciesPicker[\s\S]*?triggerless[\s\S]*?@select="addSelectedPal"/,
    'the add flow must hide the intermediate trigger and submit the selected species',
  )
  assert.match(
    pickerSource,
    /defineExpose\(\{\s*open,\s*close\s*\}\)/,
    'the species picker must expose its dialog controls to the add flow',
  )
})

test('selecting a species immediately adds it with automatic placement and creation options', () => {
  const source = readFileSync(palListPath, 'utf8')
  const pickerSource = readFileSync(palSpeciesPickerPath, 'utf8')

  assert.match(
    source,
    /async function addSelectedPal\(speciesId\)[\s\S]*?await palStore\.addPal\(speciesId,\s*'AUTO',\s*\{[\s\S]*?passive:[\s\S]*?maxPal:[\s\S]*?maxWork:[\s\S]*?\}\)/,
    'the selected species must be added immediately using automatic placement and the selected presets',
  )
  assert.match(
    pickerSource,
    /emit\('select',\s*pal\.InternalName\)/,
    'the picker must report the selected species to the add flow',
  )
  assert.doesNotMatch(source, /add-popover|add-confirm/, 'the intermediate add card must not be rendered')
  assert.doesNotMatch(source, /targetContainer|Common_Destination/, 'the destination must not be configurable')
})
