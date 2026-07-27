export const MAX_REMOTE_PASSIVE_SKILLS = 4
export const MAX_REMOTE_PAL_LEVEL = 80
export const MAX_REMOTE_IV = 100
export const MAX_REMOTE_CONDENSATION = 5
export const DEFAULT_REMOTE_SOUL_MAX = 60
export const MAX_REMOTE_UNRESTRICTED_VALUE = 255
export const REMOTE_PAL_GRANT_DRAFT_STORAGE_KEY = 'pal-editor.remote-pal-grant-draft.v1'

const clampInteger = (value, minimum, maximum) => {
  const number = Number(value)
  if (!Number.isFinite(number)) return minimum
  return Math.min(Math.max(Math.trunc(number), minimum), maximum)
}

const normalizePalGrantLevelMaximum = value => (
  clampInteger(value, 1, MAX_REMOTE_PAL_LEVEL)
)

export const createPalGrantLimits = ({
  unrestricted = false,
  soulMaximum = DEFAULT_REMOTE_SOUL_MAX,
} = {}) => ({
  unrestricted: Boolean(unrestricted),
  ivMaximum: unrestricted ? MAX_REMOTE_UNRESTRICTED_VALUE : MAX_REMOTE_IV,
  soulMaximum: unrestricted
    ? MAX_REMOTE_UNRESTRICTED_VALUE
    : clampInteger(soulMaximum, 0, DEFAULT_REMOTE_SOUL_MAX),
  condensationMaximum: unrestricted
    ? MAX_REMOTE_UNRESTRICTED_VALUE
    : MAX_REMOTE_CONDENSATION,
})

const normalizePalGrantLimits = (limits = DEFAULT_REMOTE_SOUL_MAX) => {
  if (typeof limits === 'number') {
    return createPalGrantLimits({ soulMaximum: limits })
  }
  if (
    limits
    && Number.isFinite(Number(limits.ivMaximum))
    && Number.isFinite(Number(limits.soulMaximum))
    && Number.isFinite(Number(limits.condensationMaximum))
  ) {
    return {
      unrestricted: Boolean(limits.unrestricted),
      ivMaximum: clampInteger(
        limits.ivMaximum,
        0,
        MAX_REMOTE_UNRESTRICTED_VALUE,
      ),
      soulMaximum: clampInteger(
        limits.soulMaximum,
        0,
        MAX_REMOTE_UNRESTRICTED_VALUE,
      ),
      condensationMaximum: clampInteger(
        limits.condensationMaximum,
        1,
        MAX_REMOTE_UNRESTRICTED_VALUE,
      ),
    }
  }
  return createPalGrantLimits(limits)
}

export const createPalGrantForm = (previous = {}) => ({
  characterId: typeof previous.characterId === 'string'
    ? previous.characterId
    : '',
  level: Number.isFinite(Number(previous.level))
    ? Math.trunc(Number(previous.level))
    : 1,
  passiveSkills: [...new Set(
    (Array.isArray(previous.passiveSkills) ? previous.passiveSkills : [])
      .filter(skill => typeof skill === 'string' && skill.length > 0),
  )].slice(0, MAX_REMOTE_PASSIVE_SKILLS),
  ivs: {
    hp: Number.isFinite(Number(previous.ivs?.hp))
      ? Math.trunc(Number(previous.ivs.hp))
      : 0,
    shot: Number.isFinite(Number(previous.ivs?.shot))
      ? Math.trunc(Number(previous.ivs.shot))
      : 0,
    defense: Number.isFinite(Number(previous.ivs?.defense))
      ? Math.trunc(Number(previous.ivs.defense))
      : 0,
  },
  enhancements: {
    condensation: Number.isFinite(Number(previous.enhancements?.condensation))
      ? Math.trunc(Number(previous.enhancements.condensation))
      : 1,
    soulHp: Number.isFinite(Number(previous.enhancements?.soulHp))
      ? Math.trunc(Number(previous.enhancements.soulHp))
      : 0,
    soulAttack: Number.isFinite(Number(previous.enhancements?.soulAttack))
      ? Math.trunc(Number(previous.enhancements.soulAttack))
      : 0,
    soulDefense: Number.isFinite(Number(previous.enhancements?.soulDefense))
      ? Math.trunc(Number(previous.enhancements.soulDefense))
      : 0,
    soulCraftSpeed: Number.isFinite(Number(previous.enhancements?.soulCraftSpeed))
      ? Math.trunc(Number(previous.enhancements.soulCraftSpeed))
      : 0,
  },
})

export const replacePalGrantPassiveSkills = (form, skills) => {
  form.passiveSkills = [...new Set(
    (Array.isArray(skills) ? skills : [])
      .filter(skill => typeof skill === 'string' && skill.length > 0),
  )].slice(0, MAX_REMOTE_PASSIVE_SKILLS)
}

export const maximizePalGrantEnhancements = (
  form,
  limits = DEFAULT_REMOTE_SOUL_MAX,
) => {
  const normalizedLimits = normalizePalGrantLimits(limits)
  form.ivs.hp = normalizedLimits.ivMaximum
  form.ivs.shot = normalizedLimits.ivMaximum
  form.ivs.defense = normalizedLimits.ivMaximum
  form.enhancements.condensation = normalizedLimits.condensationMaximum
  form.enhancements.soulHp = normalizedLimits.soulMaximum
  form.enhancements.soulAttack = normalizedLimits.soulMaximum
  form.enhancements.soulDefense = normalizedLimits.soulMaximum
  form.enhancements.soulCraftSpeed = normalizedLimits.soulMaximum
}

export const maximizePalGrantLevel = form => {
  form.level = MAX_REMOTE_PAL_LEVEL
}

export const clampPalGrantForm = (
  form,
  levelMaximum = MAX_REMOTE_PAL_LEVEL,
  limits = DEFAULT_REMOTE_SOUL_MAX,
) => {
  const normalizedLimits = normalizePalGrantLimits(limits)
  form.level = clampInteger(
    form.level,
    1,
    normalizePalGrantLevelMaximum(levelMaximum),
  )
  form.ivs.hp = clampInteger(form.ivs.hp, 0, normalizedLimits.ivMaximum)
  form.ivs.shot = clampInteger(form.ivs.shot, 0, normalizedLimits.ivMaximum)
  form.ivs.defense = clampInteger(
    form.ivs.defense,
    0,
    normalizedLimits.ivMaximum,
  )
  form.enhancements.condensation = clampInteger(
    form.enhancements.condensation,
    1,
    normalizedLimits.condensationMaximum,
  )
  for (const key of ['soulHp', 'soulAttack', 'soulDefense', 'soulCraftSpeed']) {
    form.enhancements[key] = clampInteger(
      form.enhancements[key],
      0,
      normalizedLimits.soulMaximum,
    )
  }
  replacePalGrantPassiveSkills(form, form.passiveSkills)
  return form
}

export const buildPalGrantPayload = (
  form,
  levelMaximum = MAX_REMOTE_PAL_LEVEL,
  limits = DEFAULT_REMOTE_SOUL_MAX,
) => {
  const normalizedLimits = normalizePalGrantLimits(limits)
  return {
    character_id: String(form.characterId || ''),
    level: clampInteger(
      form.level,
      1,
      normalizePalGrantLevelMaximum(levelMaximum),
    ),
    unrestricted: normalizedLimits.unrestricted,
    passiveSkills: [...new Set(form.passiveSkills)].slice(
      0,
      MAX_REMOTE_PASSIVE_SKILLS,
    ),
    ivs: {
      hp: clampInteger(form.ivs.hp, 0, normalizedLimits.ivMaximum),
      shot: clampInteger(form.ivs.shot, 0, normalizedLimits.ivMaximum),
      defense: clampInteger(
        form.ivs.defense,
        0,
        normalizedLimits.ivMaximum,
      ),
    },
    enhancements: {
      condensation: clampInteger(
        form.enhancements.condensation,
        1,
        normalizedLimits.condensationMaximum,
      ),
      soulHp: clampInteger(
        form.enhancements.soulHp,
        0,
        normalizedLimits.soulMaximum,
      ),
      soulAttack: clampInteger(
        form.enhancements.soulAttack,
        0,
        normalizedLimits.soulMaximum,
      ),
      soulDefense: clampInteger(
        form.enhancements.soulDefense,
        0,
        normalizedLimits.soulMaximum,
      ),
      soulCraftSpeed: clampInteger(
        form.enhancements.soulCraftSpeed,
        0,
        normalizedLimits.soulMaximum,
      ),
    },
  }
}
