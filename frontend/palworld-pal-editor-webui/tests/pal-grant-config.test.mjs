import test from 'node:test'
import assert from 'node:assert/strict'
import {
  buildPalGrantPayload,
  createPalGrantForm,
  createPalGrantLimits,
  MAX_REMOTE_PAL_LEVEL,
  maximizePalGrantLevel,
  maximizePalGrantEnhancements,
  replacePalGrantPassiveSkills,
} from '../src/components/modules/pal-grant-config.js'

test('Pal grant payload includes the persistent live Pal fields', () => {
  const form = createPalGrantForm()
  form.characterId = 'SheepBall'
  form.level = 43
  replacePalGrantPassiveSkills(form, ['Legend', 'MuscleBody', 'Legend'])
  form.ivs = { hp: 90, shot: 88, defense: 77 }
  form.enhancements = {
    condensation: 5,
    soulHp: 12,
    soulAttack: 13,
    soulDefense: 14,
    soulCraftSpeed: 15,
  }

  assert.deepEqual(buildPalGrantPayload(form, 80, 60), {
    character_id: 'SheepBall',
    level: 43,
    unrestricted: false,
    passiveSkills: ['Legend', 'MuscleBody'],
    ivs: { hp: 90, shot: 88, defense: 77 },
    enhancements: {
      condensation: 5,
      soulHp: 12,
      soulAttack: 13,
      soulDefense: 14,
      soulCraftSpeed: 15,
    },
  })
})

test('maximum enhancement applies the editor-safe limits', () => {
  const form = createPalGrantForm()
  maximizePalGrantEnhancements(form, 60)

  assert.deepEqual(form.ivs, { hp: 100, shot: 100, defense: 100 })
  assert.deepEqual(form.enhancements, {
    condensation: 5,
    soulHp: 60,
    soulAttack: 60,
    soulDefense: 60,
    soulCraftSpeed: 60,
  })
})
test('cheat options raise IV, soul, and condensation limits without exceeding Pal level 80', () => {
  const limits = createPalGrantLimits({
    unrestricted: true,
    soulMaximum: 60,
  })
  const form = createPalGrantForm()
  form.characterId = 'SheepBall'
  form.level = 100
  maximizePalGrantEnhancements(form, limits)

  assert.equal(MAX_REMOTE_PAL_LEVEL, 80)
  assert.deepEqual(form.ivs, { hp: 255, shot: 255, defense: 255 })
  assert.deepEqual(form.enhancements, {
    condensation: 255,
    soulHp: 255,
    soulAttack: 255,
    soulDefense: 255,
    soulCraftSpeed: 255,
  })
  assert.deepEqual(buildPalGrantPayload(form, 100, limits), {
    character_id: 'SheepBall',
    level: 80,
    unrestricted: true,
    passiveSkills: [],
    ivs: { hp: 255, shot: 255, defense: 255 },
    enhancements: {
      condensation: 255,
      soulHp: 255,
      soulAttack: 255,
      soulDefense: 255,
      soulCraftSpeed: 255,
    },
  })
})

test('Pal grant MAX level action sets level directly to 80', () => {
  const form = createPalGrantForm({ level: 12 })

  maximizePalGrantLevel(form)

  assert.equal(form.level, 80)
})

test('Pal grant form restores and isolates the previous complete selection', () => {
  const previous = {
    characterId: 'SheepBall',
    level: 42,
    passiveSkills: ['Legend', 'MuscleBody'],
    ivs: { hp: 91, shot: 82, defense: 73 },
    enhancements: {
      condensation: 5,
      soulHp: 11,
      soulAttack: 12,
      soulDefense: 13,
      soulCraftSpeed: 14,
    },
  }

  const restored = createPalGrantForm(previous)
  previous.passiveSkills.push('Rare')
  previous.ivs.hp = 0

  assert.deepEqual(restored, {
    characterId: 'SheepBall',
    level: 42,
    passiveSkills: ['Legend', 'MuscleBody'],
    ivs: { hp: 91, shot: 82, defense: 73 },
    enhancements: {
      condensation: 5,
      soulHp: 11,
      soulAttack: 12,
      soulDefense: 13,
      soulCraftSpeed: 14,
    },
  })
})
