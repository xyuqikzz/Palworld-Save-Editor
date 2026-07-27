const RUNTIME_FIXED_POINT_SCALE = 1000

function finiteNumber(value) {
  if (value === null || value === undefined || value === '') return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

export function normalizeRuntimeFixedPoint(value) {
  const raw = finiteNumber(value)
  return raw === null ? null : raw / RUNTIME_FIXED_POINT_SCALE
}

function healthValue(displayValue, rawValue) {
  const normalizedDisplayValue = finiteNumber(displayValue)
  if (normalizedDisplayValue !== null) return normalizedDisplayValue
  return normalizeRuntimeFixedPoint(rawValue)
}

function formatHealthValue(value) {
  return value === null ? '—' : String(value)
}

export function formatRuntimeHealth(player) {
  const current = healthValue(player?.hp, player?.hpRaw)
  const maximumCandidate = healthValue(player?.maxHp, player?.maxHpRaw)
  const maximum = maximumCandidate !== null && maximumCandidate > 0
    ? maximumCandidate
    : null
  const percent = current !== null && maximum !== null
    ? Math.max(0, Math.min(100, (current / maximum) * 100))
    : null

  return {
    current,
    maximum,
    label: `${formatHealthValue(current)} / ${formatHealthValue(maximum)}`,
    percent,
  }
}

export function formatRuntimeAttributes(player, inventory) {
  const health = formatRuntimeHealth(player)
  const attributes = player?.attributes || {}
  const result = {
    health,
    stamina: finiteNumber(attributes.stamina),
    attack: finiteNumber(attributes.attack),
    defense: finiteNumber(attributes.defense),
    craftSpeed: finiteNumber(attributes.craftSpeed),
    carryWeight: finiteNumber(inventory?.maximumWeight),
  }

  return {
    ...result,
    partial: health.current === null
      || health.maximum === null
      || [
        result.stamina,
        result.attack,
        result.defense,
        result.craftSpeed,
        result.carryWeight,
      ].some(value => value === null),
  }
}
