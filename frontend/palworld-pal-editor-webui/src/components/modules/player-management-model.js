const firstValue = (source, keys, fallback = null) => {
  for (const key of keys) {
    const value = source?.[key]
    if (value !== undefined && value !== null) return value
  }
  return fallback
}

export const PLAYER_MANAGEMENT_SECTIONS = Object.freeze([
  'profile',
  'inventory',
  'technology',
  'missions',
  'map-progress',
  'attributes',
  'party-pals',
  'palbox',
  'actions',
])

export const OFFLINE_PLAYER_TABS = new Set([
  'inventory',
  'technology',
  'missions',
  'map-progress',
  'attributes',
])

export const LIVE_PLAYER_TABS = new Set([
  'overview',
  'inventory',
  'pals',
  'actions',
])

export function playerManagementId(player) {
  return String(firstValue(
    player,
    [
      'player_id',
      'player_uid',
      'playerUid',
      'playerId',
      'InstanceId',
      'userId',
      'uid',
    ],
    '',
  ) || '')
}

export function playerManagementName(player) {
  return String(firstValue(
    player,
    ['name', 'nickname', 'NickName'],
    playerManagementId(player),
  ) || '')
}

export class PlayerManagementModel {
  constructor({
    raw,
    source,
    online,
    availableSections,
    capabilities,
  }) {
    this.raw = raw
    this.id = playerManagementId(raw)
    this.name = playerManagementName(raw)
    this.level = Number(firstValue(raw, ['level', 'Level'], 1)) || 1
    this.experience = Number(firstValue(raw, ['experience', 'Exp'], 0)) || 0
    this.technologyPoints = Number(firstValue(
      raw,
      ['technology_points', 'technologyPoints', 'TechnologyPoint'],
      0,
    )) || 0
    this.bossTechnologyPoints = Number(firstValue(
      raw,
      ['boss_technology_points', 'bossTechnologyPoints', 'bossTechnologyPoint'],
      0,
    )) || 0
    this.attributes = firstValue(
      raw,
      ['attributes', 'PlayerAttributes'],
      [],
    )
    this.unlockedTechnology = firstValue(
      raw,
      [
        'unlocked_technology',
        'unlockedTechnology',
        'UnlockedRecipeTechnologyNames',
      ],
      [],
    )
    this.missions = firstValue(raw, ['missions'], null)
    this.mapProgress = firstValue(
      raw,
      ['map_progress', 'mapProgress', 'FastTravelUnlockCapability'],
      null,
    )
    this.source = source
    this.online = online
    this.availableSections = availableSections
    this.capabilities = capabilities
  }

  static fromOffline(player) {
    return new PlayerManagementModel({
      raw: player || {},
      source: 'offline-save',
      online: false,
      availableSections: PLAYER_MANAGEMENT_SECTIONS.filter(
        section => section !== 'actions',
      ),
      capabilities: {},
    })
  }

  static fromLive(player) {
    const raw = player || {}
    return new PlayerManagementModel({
      raw,
      source: raw.source || 'runtime',
      online: raw.online !== false,
      availableSections: raw.available_sections || [],
      capabilities: raw.capabilities || {},
    })
  }
}
