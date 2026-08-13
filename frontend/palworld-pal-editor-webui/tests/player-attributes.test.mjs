import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import en from '../src/i18n/en.js'
import fr from '../src/i18n/fr.js'
import ja from '../src/i18n/ja.js'
import ko from '../src/i18n/ko.js'
import zhCN from '../src/i18n/zh-CN.js'

const attributeKeys = [
  'max_hp', 'max_sp', 'attack', 'work_speed', 'carry_weight',
  'capture_power', 'hunger_reduction', 'swim_speed',
  'food_decay_reduction', 'jump_power', 'glider_speed', 'climb_speed',
  'status_ailment_resist', 'stamina_reduction', 'sphere_homing',
  'exp_bonus', 'rainbow_passive_rate', 'move_speed',
]

test('all supported locales expose official player attribute copy', () => {
  for (const translations of [en, fr, ja, ko, zhCN]) {
    assert.ok(translations.PlayerTab_Attributes, 'attribute tab label is missing')
    for (const key of attributeKeys) {
      assert.ok(translations[`PlayerAttribute_${key}`], `${key} name is missing`)
      assert.ok(
        translations[`PlayerAttribute_${key}_Description`],
        `${key} description is missing`,
      )
    }
  }
  assert.equal(zhCN.PlayerAttribute_swim_speed, '游泳能力')
  assert.equal(zhCN.PlayerTab_Attributes, '属性')
  assert.equal(en.PlayerAttribute_sphere_homing, 'Sphere Tracking')
  assert.equal(ja.PlayerAttribute_rainbow_passive_rate, '虹色の幸運')
})

test('player attribute editor uses packaged game icons and the explicit command flow', () => {
  const component = readFileSync(
    fileURLToPath(new URL('../src/components/PlayerEditor.vue', import.meta.url)),
    'utf8',
  )
  const store = readFileSync(
    fileURLToPath(new URL('../src/stores/paleditor.js', import.meta.url)),
    'utf8',
  )
  assert.match(component, /\/image\/player_attributes\/\$\{attribute\.icon\}/)
  assert.match(component, /@click="palStore\.updatePlayerAttributes\(attribute\)"/)
  assert.match(component, /@click="setPlayerAttributeToMaximum\(attribute\)"/)
  assert.match(component, /class="player-attribute-input"/)
  assert.match(component, /class="player-attribute-max-action"/)
  assert.match(component, /class="player-attribute-save-action"/)
  assert.match(
    component,
    /\.player-attribute-item\s*\{[^}]*height:\s*96px[^}]*box-sizing:\s*border-box[^}]*align-content:\s*space-between/,
  )
  assert.match(component, /v-show="activeEditorTab === 'attributes'"/)
  assert.match(component, /getTranslatedText\('PlayerTab_Attributes'\)/)
  assert.doesNotMatch(component, /class="player-attributes-title"/)
  assert.doesNotMatch(component, /getTranslatedText\('PlayerAttributes_Description'\)/)
  assert.ok(
    component.indexOf('id="player-attributes-tab"') > component.indexOf('id="player-missions-tab"'),
    'attributes must be the last player editor tab',
  )
  assert.match(store, /async function updatePlayerAttributes\(attribute = null\)/)
  assert.match(component, /@click="palStore\.updatePlayerAttributes\(\)"/)
  assert.match(store, /const attributes = attribute\?\.key\s*\? \[attribute\]/)
  assert.match(store, /command:\s*"update_player_attributes"/)

  const iconRoot = new URL(
    '../../../src/palworld_pal_editor/assets/icons/player_attributes/',
    import.meta.url,
  )
  for (const key of attributeKeys) {
    assert.ok(existsSync(new URL(`${key}.png`, iconRoot)), `${key} icon is missing`)
  }
})

test('remedy and elixir bonuses use a separate official-total-capped command flow', () => {
  const component = readFileSync(
    fileURLToPath(new URL('../src/components/PlayerEditor.vue', import.meta.url)),
    'utf8',
  )
  const store = readFileSync(
    fileURLToPath(new URL('../src/stores/paleditor.js', import.meta.url)),
    'utf8',
  )

  for (const translations of [en, fr, ja, ko, zhCN]) {
    assert.ok(translations.PlayerConsumableBonuses_Title)
    assert.ok(translations.PlayerConsumableBonuses_Description)
    assert.ok(translations.PLAYER_CONSUMABLE_BONUS_FIELD_MISSING)
    assert.ok(translations.PLAYER_CONSUMABLE_BONUS_STRUCTURE_UNSUPPORTED)
    assert.ok(translations.PLAYER_ATTRIBUTE_STRUCTURE_UNSUPPORTED)
    assert.ok(translations.PLAYER_ATTRIBUTE_TOTAL_EXCEEDED)
  }
  assert.match(component, /PlayerConsumableBonuses\.values/)
  assert.match(component, /:max="bonus\.maximum"/)
  assert.match(component, /bonus\.maximum_total/)
  assert.match(component, /palStore\.updatePlayerConsumableBonuses/)
  assert.match(store, /async function updatePlayerConsumableBonuses\(bonus = null\)/)
  assert.match(store, /command:\s*"update_player_consumable_bonuses"/)
  assert.doesNotMatch(component, /reduce-only/)
})
