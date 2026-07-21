const PREFERRED_ELEMENT_ORDER = [
  'Neutral',
  'Fire',
  'Water',
  'Electricity',
  'Grass',
  'Ice',
  'Ground',
  'Dark',
  'Dragon',
]

const ELEMENT_TRANSLATION_KEYS = {
  Neutral: 'Element_Neutral',
  Fire: 'Element_Fire',
  Water: 'Element_Water',
  Electricity: 'Element_Electric',
  Grass: 'Element_Leaf',
  Ice: 'Element_Ice',
  Ground: 'Element_Earth',
  Dark: 'Element_Dark',
  Dragon: 'Element_Dragon',
}

const normalizedTokens = query => String(query || '')
  .normalize('NFKC')
  .trim()
  .toLocaleLowerCase()
  .split(/\s+/)
  .filter(Boolean)

const formatPalNumber = value => {
  if (!value) return ''
  const numeric = Number(value)
  return Number.isFinite(numeric) ? `#${String(numeric).padStart(3, '0')}` : String(value)
}

export const characterCategory = option => option?.IsHuman ? 'npc' : 'pal'

export const elementTranslationKey = element => (
  ELEMENT_TRANSLATION_KEYS[element] || 'Element_Unknown'
)

export function availablePalElements(options) {
  const available = new Set(
    options
      .filter(option => characterCategory(option) === 'pal')
      .flatMap(option => option.Elements || [])
      .filter(Boolean),
  )
  const preferred = PREFERRED_ELEMENT_ORDER.filter(element => available.delete(element))
  return [...preferred, ...[...available].sort()]
}

export function filterSpeciesOptions(
  options,
  { category = 'pal', element = 'all', query = '' } = {},
) {
  const tokens = normalizedTokens(query)

  return options.filter(option => {
    if (characterCategory(option) !== category) return false
    if (category === 'pal' && element !== 'all'
      && !(option.Elements || []).includes(element)) return false
    if (!tokens.length) return true

    const fields = [
      option.I18n,
      option.InternalName,
      option.SortingKey,
      formatPalNumber(option.SortingKey),
      ...(option.Elements || []),
    ]
      .filter(Boolean)
      .map(value => String(value).normalize('NFKC').toLocaleLowerCase())

    return tokens.every(token => fields.some(field => field.includes(token)))
  })
}
