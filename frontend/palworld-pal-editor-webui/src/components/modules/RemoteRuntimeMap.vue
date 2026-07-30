<script setup>
import AppIcon from '@/components/modules/AppIcon.vue'
import mapPoints from '@/data/map-points.json'
import { usePalEditorStore } from '@/stores/paleditor'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const emit = defineEmits(['select-player'])
const palStore = usePalEditorStore()
const viewport = ref(null)
const viewportSize = ref({ width: 1, height: 1 })
const zoom = ref(0)
const offset = ref({ x: 0, y: 0 })
const dragging = ref(false)
const pointerState = ref(null)
const mouseWorld = ref(null)
const selectedMarkerId = ref('')
const searchTarget = ref('')
const guildFilter = ref('')
const showFastTravel = ref(false)
const showLabels = ref(true)
const autoRefresh = ref(true)
const activeMapArea = ref('MainMap')

const IMAGE_SIZE = 8192
const MIN_ZOOM = 0
const ZOOM_FACTOR = 1.3
const MAX_ZOOM = 6 + Math.log(1.5) / Math.log(ZOOM_FACTOR)
const MAX_NATIVE_SCALE = 1
const REFRESH_INTERVAL_MS = 3000
const MAP_ASSET_ROOT = `${import.meta.env.BASE_URL}map/psp`
const PLAYER_MARKER_IMAGE = `${MAP_ASSET_ROOT}/t_icon_compass_11.webp`
const FAST_TRAVEL_MARKER_IMAGE = `${MAP_ASSET_ROOT}/t_icon_compass_fttower.webp`
const MAP_AREAS = Object.freeze({
  MainMap: {
    imageUrl: `${MAP_ASSET_ROOT}/t_worldmap.webp`,
    labelKey: 'Map_Area_MainMap',
    bounds: {
      min_x: -1099400,
      max_x: 349400,
      min_y: -724400,
      max_y: 724400,
    },
  },
  Tree: {
    imageUrl: `${MAP_ASSET_ROOT}/t_treemap.webp`,
    labelKey: 'Map_Area_Tree',
    bounds: {
      min_x: 347351.5,
      max_x: 689148.5,
      min_y: -818197,
      max_y: -476400,
    },
  },
})
const MAP_AREA_TABS = Object.freeze(['MainMap', 'Tree'])
const MAP_AREA_PRIORITY = Object.freeze(['Tree', 'MainMap'])

const mapData = computed(() => palStore.REMOTE_MAP_DATA || {})
const rawPlayers = computed(() => (
  Array.isArray(mapData.value.players) ? mapData.value.players : []
))
const rawGuilds = computed(() => (
  Array.isArray(mapData.value.guilds) ? mapData.value.guilds : []
))
const activeMapConfig = computed(() => MAP_AREAS[activeMapArea.value])
const bounds = computed(() => activeMapConfig.value.bounds)
const fitScale = computed(() => Math.max(
  0.05,
  Math.min(
    Math.max(1, viewportSize.value.width - 32) / IMAGE_SIZE,
    Math.max(1, viewportSize.value.height - 32) / IMAGE_SIZE,
  ),
))
const maxUsableZoom = computed(() => {
  const available = Math.floor(
    Math.log(MAX_NATIVE_SCALE / fitScale.value) / Math.log(ZOOM_FACTOR),
  )
  return Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, available))
})
const scale = computed(() => fitScale.value * (ZOOM_FACTOR ** zoom.value))
const inverseScale = computed(() => 1 / scale.value)
const zoomProgress = computed(() => (
  maxUsableZoom.value > 0 ? zoom.value / maxUsableZoom.value : 0
))
const stageStyle = computed(() => ({
  left: `${(viewportSize.value.width / 2) + offset.value.x}px`,
  top: `${(viewportSize.value.height / 2) + offset.value.y}px`,
  transform: `translate(-50%, -50%) scale(${scale.value})`,
  '--marker-inverse-scale': inverseScale.value,
}))

function playerId(player) {
  return player.playerId
    || player.player_uid
    || player.playerUid
    || player.userId
    || player.uid
    || ''
}

function playerGuildId(player) {
  return player.guildId || player.guild_id || ''
}

function guildId(guild) {
  return guild.guildId || guild.guild_id || ''
}

function guildName(guild) {
  return guild.name || guild.guildName || guildId(guild)
}

function positionFor(player) {
  const position = player.position && typeof player.position === 'object'
    ? player.position
    : player
  const x = Number(position.x)
  const y = Number(position.y)
  const z = Number(position.z)
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null
  return { x, y, z: Number.isFinite(z) ? z : null }
}

function playerPresenceKey(player) {
  return player.online === true
    ? 'RemoteMap_PlayerOnline'
    : 'RemoteMap_PlayerOffline'
}

function playerLabel(player) {
  const id = playerId(player)
  const name = player.name || player.nickname || id
  const status = palStore.getTranslatedText(playerPresenceKey(player))
  return `${name}${palStore.getTranslatedText('RemoteMap_PlayerLabelOpen')}${status}${palStore.getTranslatedText('RemoteMap_PlayerLabelClose')}`
}

function positionSourceKey(player) {
  return player.positionSource === 'save_last_transform'
    ? 'RemoteMap_SavedSource'
    : 'RemoteMap_PawnSource'
}

const guildById = computed(() => new Map(
  rawGuilds.value
    .map(guild => [guildId(guild), guild])
    .filter(([id]) => id),
))
const guildRows = computed(() => {
  const rows = new Map(guildById.value)
  rawPlayers.value.forEach(player => {
    const id = playerGuildId(player)
    if (!id || rows.has(id)) return
    rows.set(id, {
      guildId: id,
      name: player.guildName || id,
      onlineMemberCount: 0,
    })
  })
  return Array.from(rows.values()).sort((left, right) => (
    guildName(left).localeCompare(guildName(right))
  ))
})
const playerMarkers = computed(() => rawPlayers.value.flatMap(player => {
  const position = positionFor(player)
  if (!position) return []
  const id = playerId(player)
  const linkedGuildId = playerGuildId(player)
  const guild = guildById.value.get(linkedGuildId)
  return [{
    ...player,
    ...position,
    id: `player:${id}`,
    playerId: id,
    label: playerLabel(player),
    guildId: linkedGuildId,
    guildName: player.guildName || (guild ? guildName(guild) : ''),
    kind: 'player',
  }]
}))
const unavailablePositionCount = computed(() => (
  Math.max(0, rawPlayers.value.length - playerMarkers.value.length)
))

function pointIsInMapArea(x, y, area) {
  const current = MAP_AREAS[area]?.bounds
  return Boolean(
    current
    && Number.isFinite(x)
    && Number.isFinite(y)
    && x >= current.min_x
    && x <= current.max_x
    && y >= current.min_y
    && y <= current.max_y
  )
}

function mapAreaForPosition(x, y) {
  return MAP_AREA_PRIORITY.find(area => pointIsInMapArea(x, y, area)) || null
}

const playersOutsideKnownAreas = computed(() => (
  playerMarkers.value.filter(marker => !mapAreaForPosition(marker.x, marker.y)).length
))
const activePlayerMarkers = computed(() => playerMarkers.value.filter(marker => (
  mapAreaForPosition(marker.x, marker.y) === activeMapArea.value
  && (!guildFilter.value || marker.guildId === guildFilter.value)
)))
const fastTravelMarkers = computed(() => mapPoints.fast_travel.flatMap((point, index) => {
  const x = Number(point[0])
  const y = Number(point[1])
  if (mapAreaForPosition(x, y) !== activeMapArea.value) return []
  return [{
    id: `fast:${index}`,
    kind: 'fast-travel',
    label: palStore.getTranslatedText('Map_FastTravel'),
    x,
    y,
  }]
}))
const visibleMarkers = computed(() => [
  ...activePlayerMarkers.value,
  ...(showFastTravel.value ? fastTravelMarkers.value : []),
])
const selectedMarker = computed(() => (
  playerMarkers.value.find(marker => marker.id === selectedMarkerId.value) || null
))
const sampledAt = computed(() => {
  const value = mapData.value.sampled_at
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleTimeString()
})

function guildHue(id) {
  let hash = 0
  for (const char of String(id || 'none')) {
    hash = ((hash * 31) + char.charCodeAt(0)) >>> 0
  }
  return hash % 360
}

function markerStyle(marker) {
  const current = bounds.value
  const point = {
    x: ((marker.y - current.min_y) / (current.max_y - current.min_y)) * IMAGE_SIZE,
    y: ((current.max_x - marker.x) / (current.max_x - current.min_x)) * IMAGE_SIZE,
  }
  return {
    left: `${point.x}px`,
    top: `${point.y}px`,
    '--guild-hue': guildHue(marker.guildId),
  }
}

function mapToWorldPoint(x, y) {
  const current = bounds.value
  return {
    x: current.max_x - (y / IMAGE_SIZE) * (current.max_x - current.min_x),
    y: current.min_y + (x / IMAGE_SIZE) * (current.max_y - current.min_y),
  }
}

function clampOffset() {
  const displayedWidth = IMAGE_SIZE * scale.value
  const displayedHeight = IMAGE_SIZE * scale.value
  const maxX = Math.max(40, (displayedWidth - viewportSize.value.width) / 2 + 72)
  const maxY = Math.max(40, (displayedHeight - viewportSize.value.height) / 2 + 72)
  offset.value = {
    x: Math.max(-maxX, Math.min(maxX, offset.value.x)),
    y: Math.max(-maxY, Math.min(maxY, offset.value.y)),
  }
}

function setZoom(nextZoom, anchor = null) {
  const next = Math.max(MIN_ZOOM, Math.min(maxUsableZoom.value, nextZoom))
  if (next === zoom.value) return
  const oldScale = scale.value
  let vector = null
  if (anchor) {
    vector = {
      x: anchor.x - (viewportSize.value.width / 2) - offset.value.x,
      y: anchor.y - (viewportSize.value.height / 2) - offset.value.y,
    }
  }
  zoom.value = next
  if (vector) {
    const ratio = scale.value / oldScale
    offset.value = {
      x: offset.value.x + vector.x * (1 - ratio),
      y: offset.value.y + vector.y * (1 - ratio),
    }
  }
  clampOffset()
}

function resetView() {
  zoom.value = MIN_ZOOM
  offset.value = { x: 0, y: 0 }
}

function switchMapArea(area) {
  if (!MAP_AREAS[area] || activeMapArea.value === area) return
  activeMapArea.value = area
  mouseWorld.value = null
  resetView()
}

function focusMarker(marker) {
  if (!marker) return
  const area = mapAreaForPosition(marker.x, marker.y)
  if (!area) return
  if (activeMapArea.value !== area) activeMapArea.value = area
  nextTick(() => {
    zoom.value = Math.min(3, maxUsableZoom.value)
    const current = bounds.value
    const point = {
      x: ((marker.y - current.min_y) / (current.max_y - current.min_y)) * IMAGE_SIZE,
      y: ((current.max_x - marker.x) / (current.max_x - current.min_x)) * IMAGE_SIZE,
    }
    offset.value = {
      x: -(point.x - IMAGE_SIZE / 2) * scale.value,
      y: -(point.y - IMAGE_SIZE / 2) * scale.value,
    }
    selectedMarkerId.value = marker.id
    clampOffset()
  })
}

function focusSearchTarget() {
  focusMarker(playerMarkers.value.find(marker => marker.id === searchTarget.value))
}

function updateMouseWorld(event) {
  const rect = viewport.value?.getBoundingClientRect()
  if (!rect) return
  const mapX = (
    IMAGE_SIZE / 2
    + (event.clientX - rect.left - viewportSize.value.width / 2 - offset.value.x) / scale.value
  )
  const mapY = (
    IMAGE_SIZE / 2
    + (event.clientY - rect.top - viewportSize.value.height / 2 - offset.value.y) / scale.value
  )
  if (mapX < 0 || mapY < 0 || mapX > IMAGE_SIZE || mapY > IMAGE_SIZE) {
    mouseWorld.value = null
    return
  }
  mouseWorld.value = mapToWorldPoint(mapX, mapY)
}

function onPointerDown(event) {
  if (event.button !== 0 || event.target.closest('button, input, select, label')) return
  dragging.value = true
  pointerState.value = { id: event.pointerId, x: event.clientX, y: event.clientY }
  viewport.value?.setPointerCapture(event.pointerId)
}

function onPointerMove(event) {
  updateMouseWorld(event)
  if (!dragging.value || pointerState.value?.id !== event.pointerId) return
  offset.value = {
    x: offset.value.x + event.clientX - pointerState.value.x,
    y: offset.value.y + event.clientY - pointerState.value.y,
  }
  pointerState.value = { id: event.pointerId, x: event.clientX, y: event.clientY }
  clampOffset()
}

function onPointerUp(event) {
  if (pointerState.value?.id !== event.pointerId) return
  dragging.value = false
  pointerState.value = null
  if (viewport.value?.hasPointerCapture(event.pointerId)) {
    viewport.value.releasePointerCapture(event.pointerId)
  }
}

function onWheel(event) {
  const rect = viewport.value?.getBoundingClientRect()
  if (!rect) return
  setZoom(
    zoom.value + (event.deltaY < 0 ? 1 : -1),
    { x: event.clientX - rect.left, y: event.clientY - rect.top },
  )
}

function onMapKeydown(event) {
  const amount = event.shiftKey ? 80 : 36
  if (event.key === '+' || event.key === '=') setZoom(zoom.value + 1)
  else if (event.key === '-') setZoom(zoom.value - 1)
  else if (event.key === 'Home') resetView()
  else if (event.key === 'ArrowLeft') offset.value.x += amount
  else if (event.key === 'ArrowRight') offset.value.x -= amount
  else if (event.key === 'ArrowUp') offset.value.y += amount
  else if (event.key === 'ArrowDown') offset.value.y -= amount
  else return
  event.preventDefault()
  clampOffset()
}

function formatCoordinate(value) {
  return Number.isFinite(Number(value)) ? Number(value).toFixed(1) : '—'
}

function refreshNow() {
  return palStore.loadRemoteMapData()
}

watch(autoRefresh, enabled => {
  if (enabled && !palStore.REMOTE_MAP_DATA) refreshNow()
})

let resizeObserver = null
let refreshTimer = null

onMounted(async () => {
  resizeObserver = new ResizeObserver(entries => {
    const box = entries[0]?.contentRect
    if (!box) return
    viewportSize.value = { width: box.width, height: box.height }
    nextTick(() => {
      zoom.value = Math.min(zoom.value, maxUsableZoom.value)
      clampOffset()
    })
  })
  if (viewport.value) resizeObserver.observe(viewport.value)
  await refreshNow()
  refreshTimer = window.setInterval(() => {
    if (autoRefresh.value) refreshNow()
  }, REFRESH_INTERVAL_MS)
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  if (refreshTimer !== null) window.clearInterval(refreshTimer)
})
</script>

<template>
  <section class="runtime-map-shell">
    <header class="runtime-map-header">
      <div>
        <span class="runtime-map-header__icon"><AppIcon name="map" :size="19" /></span>
        <div>
          <small>{{ palStore.getTranslatedText('RemoteMap_DataScope') }}</small>
          <h3>{{ palStore.getTranslatedText('Remote_TabMap') }}</h3>
        </div>
      </div>
      <dl>
        <div>
          <dt>{{ palStore.getTranslatedText('RemoteMap_PositionSummary') }}</dt>
          <dd>{{ playerMarkers.length }} / {{ rawPlayers.length }}</dd>
        </div>
        <div>
          <dt>{{ palStore.getTranslatedText('RemoteMap_LastSample') }}</dt>
          <dd>{{ sampledAt }}</dd>
        </div>
      </dl>
    </header>

    <div class="runtime-map-layout">
      <div
        ref="viewport"
        class="runtime-map-viewport"
        :class="{ 'is-dragging': dragging }"
        tabindex="0"
        :aria-label="palStore.getTranslatedText('Map_ViewportLabel')"
        @pointerdown="onPointerDown"
        @pointermove="onPointerMove"
        @pointerup="onPointerUp"
        @pointercancel="onPointerUp"
        @wheel.prevent="onWheel"
        @keydown="onMapKeydown"
      >
        <div class="runtime-map-stage" :style="stageStyle">
          <img
            :key="activeMapArea"
            class="runtime-map-image"
            :src="activeMapConfig.imageUrl"
            alt=""
            aria-hidden="true"
            decoding="async"
            draggable="false"
          >

          <span
            v-for="marker in visibleMarkers"
            :key="marker.id"
            class="runtime-marker-anchor"
            :class="`runtime-marker-anchor--${marker.kind}`"
            :style="markerStyle(marker)"
          >
            <button
              class="runtime-marker"
              :class="{
                selected: selectedMarkerId === marker.id,
                'is-offline': marker.online !== true,
              }"
              type="button"
              :aria-label="marker.label"
              @pointerdown.stop
              @click.stop="marker.kind === 'player' && (selectedMarkerId = marker.id)"
            >
              <img
                :src="marker.kind === 'player' ? PLAYER_MARKER_IMAGE : FAST_TRAVEL_MARKER_IMAGE"
                alt=""
                aria-hidden="true"
                draggable="false"
              >
              <span v-if="marker.kind === 'player' && showLabels">{{ marker.label }}</span>
            </button>
          </span>
        </div>

        <nav class="runtime-map-areas" role="tablist" :aria-label="palStore.getTranslatedText('Map_AreaTabs')">
          <button
            v-for="area in MAP_AREA_TABS"
            :key="area"
            type="button"
            role="tab"
            :class="{ active: activeMapArea === area }"
            :aria-selected="activeMapArea === area"
            @click="switchMapArea(area)"
          >
            {{ palStore.getTranslatedText(MAP_AREAS[area].labelKey) }}
          </button>
        </nav>

        <div class="runtime-map-status">
          <span><i />{{ palStore.getTranslatedText('RemoteMap_PlayerOnline') }}</span>
          <b>{{ mapData.presence?.online ?? 0 }}</b>
          <span class="is-offline">
            <i />{{ palStore.getTranslatedText('RemoteMap_PlayerOffline') }}
          </span>
          <b>{{ mapData.presence?.offline ?? 0 }}</b>
        </div>

        <div v-if="palStore.REMOTE_MAP_LOADING && !palStore.REMOTE_MAP_DATA" class="runtime-map-state">
          <span />
          {{ palStore.getTranslatedText('Map_Loading') }}
        </div>
        <div v-else-if="!activePlayerMarkers.length" class="runtime-map-state">
          {{ palStore.getTranslatedText('RemoteMap_NoPositions') }}
        </div>

        <div class="runtime-zoom">
          <button type="button" :disabled="zoom >= maxUsableZoom" @click="setZoom(zoom + 1)">
            <AppIcon name="plus" :size="14" />
          </button>
          <div aria-hidden="true">
            <span :style="{ height: `${zoomProgress * 100}%` }" />
            <i :style="{ bottom: `${zoomProgress * 100}%` }" />
          </div>
          <button type="button" :disabled="zoom <= MIN_ZOOM" @click="setZoom(zoom - 1)">−</button>
          <button type="button" @click="resetView"><AppIcon name="refresh" :size="13" /></button>
        </div>

        <article v-if="selectedMarker" class="runtime-map-detail">
          <header>
            <span>{{ palStore.getTranslatedText('Map_Player') }}</span>
            <button type="button" @click="selectedMarkerId = ''">
              <AppIcon name="x" :size="16" />
            </button>
          </header>
          <h4>{{ selectedMarker.label }}</h4>
          <p>{{ selectedMarker.guildName || palStore.getTranslatedText('RemoteMap_NoGuild') }}</p>
          <dl>
            <div>
              <dt>{{ palStore.getTranslatedText('Common_Level') }}</dt>
              <dd>{{ selectedMarker.level ?? '—' }}</dd>
            </div>
            <div>
              <dt>{{ palStore.getTranslatedText('Map_Coordinates') }}</dt>
              <dd>X {{ formatCoordinate(selectedMarker.x) }} · Y {{ formatCoordinate(selectedMarker.y) }}</dd>
            </div>
            <div>
              <dt>{{ palStore.getTranslatedText('Map_Altitude') }}</dt>
              <dd>{{ formatCoordinate(selectedMarker.z) }}</dd>
            </div>
            <div>
              <dt>{{ palStore.getTranslatedText('RemoteMap_PositionSource') }}</dt>
              <dd>{{ palStore.getTranslatedText(positionSourceKey(selectedMarker)) }}</dd>
            </div>
          </dl>
          <button type="button" class="runtime-map-detail__primary" @click="emit('select-player', selectedMarker.playerId)">
            {{ palStore.getTranslatedText('RemoteMap_OpenPlayer') }}
          </button>
        </article>

        <div class="runtime-map-coordinate">
          <span v-if="mouseWorld">
            X {{ formatCoordinate(mouseWorld.x) }} · Y {{ formatCoordinate(mouseWorld.y) }}
          </span>
          <span v-else>{{ palStore.getTranslatedText('Map_MoveForCoordinates') }}</span>
        </div>
      </div>

      <aside class="runtime-map-sidebar">
        <section class="runtime-map-controls">
          <label>
            <span>{{ palStore.getTranslatedText('Map_SearchTarget') }}</span>
            <select v-model="searchTarget" @change="focusSearchTarget">
              <option value="">{{ palStore.getTranslatedText('Map_SearchTarget') }}</option>
              <option v-for="marker in playerMarkers" :key="marker.id" :value="marker.id">
                {{ marker.label }}
              </option>
            </select>
          </label>
          <label>
            <span>{{ palStore.getTranslatedText('RemoteMap_GuildFilter') }}</span>
            <select v-model="guildFilter">
              <option value="">{{ palStore.getTranslatedText('RemoteMap_AllGuilds') }}</option>
              <option v-for="guild in guildRows" :key="guildId(guild)" :value="guildId(guild)">
                {{ guildName(guild) }}
              </option>
            </select>
          </label>
          <label class="runtime-toggle">
            <span>{{ palStore.getTranslatedText('RemoteMap_AutoRefresh') }}</span>
            <input v-model="autoRefresh" type="checkbox">
            <i />
          </label>
          <label class="runtime-toggle">
            <span>{{ palStore.getTranslatedText('Map_ShowFastTravel') }}</span>
            <input v-model="showFastTravel" type="checkbox">
            <i />
          </label>
          <label class="runtime-toggle">
            <span>{{ palStore.getTranslatedText('Map_ShowLabels') }}</span>
            <input v-model="showLabels" type="checkbox">
            <i />
          </label>
          <button type="button" :disabled="palStore.REMOTE_MAP_LOADING" @click="refreshNow">
            <AppIcon name="refresh" :size="14" />
            {{ palStore.getTranslatedText('Map_Refresh') }}
          </button>
        </section>

        <section class="runtime-guilds">
          <header>
            <div>
              <small>{{ palStore.getTranslatedText('Remote_Guild') }}</small>
              <h4>{{ palStore.getTranslatedText('RemoteMap_GuildsTitle') }}</h4>
            </div>
            <b>{{ guildRows.length }}</b>
          </header>
          <div class="runtime-guild-list">
            <button
              v-for="guild in guildRows"
              :key="guildId(guild)"
              type="button"
              :class="{ active: guildFilter === guildId(guild) }"
              @click="guildFilter = guildFilter === guildId(guild) ? '' : guildId(guild)"
            >
              <i :style="{ '--guild-hue': guildHue(guildId(guild)) }" />
              <span>
                <strong>{{ guildName(guild) }}</strong>
                <small>{{ guildId(guild) }}</small>
              </span>
              <b>{{ guild.onlineMemberCount ?? guild.onlineMembers?.length ?? 0 }}</b>
            </button>
          </div>
        </section>

        <p v-if="unavailablePositionCount" class="runtime-map-warning">
          <AppIcon name="warning" :size="14" />
          {{ palStore.getTranslatedText('RemoteMap_PositionUnavailable', [unavailablePositionCount]) }}
        </p>
        <p v-if="playersOutsideKnownAreas" class="runtime-map-warning">
          <AppIcon name="warning" :size="14" />
          {{ palStore.getTranslatedText('RemoteMap_OutsideArea', [playersOutsideKnownAreas]) }}
        </p>
      </aside>
    </div>
  </section>
</template>

<style scoped>
.runtime-map-shell {
  overflow: hidden;
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-md);
  background: var(--ui-surface);
}

.runtime-map-header {
  display: flex;
  min-height: 72px;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--ui-border);
  background:
    linear-gradient(90deg, color-mix(in oklch, var(--ui-accent), transparent 91%), transparent 38%),
    var(--ui-surface-raised);
}

.runtime-map-header > div,
.runtime-map-header dl {
  display: flex;
  align-items: center;
  gap: 11px;
}

.runtime-map-header__icon {
  display: grid;
  width: 38px;
  height: 38px;
  place-items: center;
  color: var(--ui-accent);
  border: 1px solid color-mix(in oklch, var(--ui-accent), transparent 68%);
  border-radius: var(--ui-radius-sm);
  background: color-mix(in oklch, var(--ui-accent), transparent 90%);
}

.runtime-map-header small,
.runtime-guilds small {
  color: var(--ui-accent);
  font-size: 9px;
  font-weight: 750;
  letter-spacing: .08em;
  text-transform: uppercase;
}

.runtime-map-header h3,
.runtime-guilds h4 {
  margin: 2px 0 0;
  font-size: 16px;
}

.runtime-map-header dl { margin: 0; }
.runtime-map-header dl div {
  min-width: 104px;
  padding-left: 13px;
  border-left: 1px solid var(--ui-border);
}
.runtime-map-header dt {
  color: var(--ui-text-muted);
  font-size: 9px;
  text-transform: uppercase;
}
.runtime-map-header dd {
  margin: 3px 0 0;
  font-size: 13px;
  font-weight: 700;
}

.runtime-map-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 268px;
  min-height: 650px;
}

.runtime-map-viewport {
  position: relative;
  min-width: 0;
  min-height: 650px;
  overflow: hidden;
  cursor: grab;
  outline: none;
  background: #081116;
  touch-action: none;
  user-select: none;
}

.runtime-map-viewport:focus-visible {
  box-shadow: inset 0 0 0 2px var(--ui-accent);
}
.runtime-map-viewport.is-dragging { cursor: grabbing; }

.runtime-map-stage {
  position: absolute;
  width: 8192px;
  height: 8192px;
  transform-origin: center;
  will-change: transform;
}

.runtime-map-image {
  display: block;
  width: 100%;
  height: 100%;
  pointer-events: none;
}

.runtime-marker-anchor {
  position: absolute;
  z-index: 3;
  width: 0;
  height: 0;
  --guild-color: hsl(var(--guild-hue) 72% 58%);
}

.runtime-marker {
  position: absolute;
  display: grid;
  width: calc(30px * var(--marker-inverse-scale));
  height: calc(30px * var(--marker-inverse-scale));
  padding: 0;
  place-items: center;
  transform: translate(-50%, -50%);
  color: white;
  border: 0;
  border-radius: 50%;
  background: transparent;
  cursor: pointer;
}

.runtime-marker img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  filter:
    drop-shadow(0 0 calc(3px * var(--marker-inverse-scale)) var(--guild-color))
    drop-shadow(0 calc(2px * var(--marker-inverse-scale)) calc(3px * var(--marker-inverse-scale)) #000);
}

.runtime-marker.selected::before {
  position: absolute;
  inset: calc(-4px * var(--marker-inverse-scale));
  border: calc(2px * var(--marker-inverse-scale)) solid var(--guild-color);
  border-radius: 50%;
  content: '';
  animation: marker-pulse 1.4s ease-in-out infinite;
}
.runtime-marker.is-offline img {
  opacity: .72;
  filter:
    grayscale(.76)
    drop-shadow(0 calc(2px * var(--marker-inverse-scale)) calc(3px * var(--marker-inverse-scale)) #000);
}

.runtime-marker span {
  position: absolute;
  top: calc(31px * var(--marker-inverse-scale));
  max-width: calc(180px * var(--marker-inverse-scale));
  padding: calc(3px * var(--marker-inverse-scale)) calc(7px * var(--marker-inverse-scale));
  overflow: hidden;
  color: #f1fbff;
  background: rgb(5 12 16 / .84);
  border: calc(1px * var(--marker-inverse-scale)) solid rgb(255 255 255 / .18);
  border-radius: calc(4px * var(--marker-inverse-scale));
  font-size: calc(11px * var(--marker-inverse-scale));
  font-weight: 700;
  line-height: 1.2;
  text-overflow: ellipsis;
  text-shadow: 0 1px 2px #000;
  white-space: nowrap;
}

.runtime-marker-anchor--fast-travel { z-index: 1; }
.runtime-marker-anchor--fast-travel .runtime-marker {
  width: calc(18px * var(--marker-inverse-scale));
  height: calc(18px * var(--marker-inverse-scale));
  pointer-events: none;
}

.runtime-map-areas {
  position: absolute;
  z-index: 6;
  top: 14px;
  left: 50%;
  display: flex;
  padding: 3px;
  transform: translateX(-50%);
  border: 1px solid rgb(255 255 255 / .16);
  border-radius: 7px;
  background: rgb(5 14 19 / .86);
  backdrop-filter: blur(10px);
}
.runtime-map-areas button {
  min-width: 88px;
  min-height: 31px;
  color: #a7bac3;
  border: 0;
  border-radius: 4px;
  background: transparent;
  font-size: 11px;
  font-weight: 700;
}
.runtime-map-areas button.active {
  color: #eafaff;
  background: rgb(84 165 190 / .32);
}

.runtime-map-status {
  position: absolute;
  z-index: 5;
  top: 14px;
  left: 14px;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 8px 10px;
  color: #b8cbd4;
  border: 1px solid rgb(255 255 255 / .14);
  border-radius: 6px;
  background: rgb(5 14 19 / .84);
  font-size: 11px;
  backdrop-filter: blur(10px);
}
.runtime-map-status span {
  display: flex;
  align-items: center;
  gap: 5px;
  color: #a9ecce;
  font-weight: 750;
}
.runtime-map-status span i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #43d68c;
  box-shadow: 0 0 9px #43d68c;
}
.runtime-map-status span.is-offline { color: #a8b6bc; }
.runtime-map-status span.is-offline i {
  background: #76868d;
  box-shadow: none;
}
.runtime-map-status b { color: white; }

.runtime-map-state {
  position: absolute;
  z-index: 4;
  top: 50%;
  left: 50%;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 13px;
  transform: translate(-50%, -50%);
  color: #b9cbd2;
  border: 1px solid rgb(255 255 255 / .12);
  border-radius: 6px;
  background: rgb(5 14 19 / .82);
  font-size: 12px;
}
.runtime-map-state > span {
  width: 14px;
  height: 14px;
  border: 2px solid rgb(255 255 255 / .18);
  border-top-color: #62bdda;
  border-radius: 50%;
  animation: spin .8s linear infinite;
}

.runtime-zoom {
  position: absolute;
  z-index: 6;
  right: 14px;
  bottom: 43px;
  display: grid;
  width: 34px;
  padding: 4px;
  border: 1px solid rgb(255 255 255 / .15);
  border-radius: 6px;
  background: rgb(5 14 19 / .86);
}
.runtime-zoom button {
  display: grid;
  width: 26px;
  height: 27px;
  padding: 0;
  place-items: center;
  color: white;
  border: 0;
  background: transparent;
}
.runtime-zoom button:disabled { opacity: .32; }
.runtime-zoom > div {
  position: relative;
  width: 3px;
  height: 68px;
  margin: 5px auto;
  background: rgb(255 255 255 / .17);
}
.runtime-zoom > div span {
  position: absolute;
  bottom: 0;
  width: 100%;
  background: #5dc1de;
}
.runtime-zoom > div i {
  position: absolute;
  left: 50%;
  width: 9px;
  height: 9px;
  transform: translate(-50%, 50%);
  border: 2px solid #c8f5ff;
  border-radius: 50%;
  background: #287a95;
}

.runtime-map-detail {
  position: absolute;
  z-index: 7;
  top: 58px;
  left: 14px;
  width: min(280px, calc(100% - 28px));
  padding: 13px;
  color: #deedf2;
  border: 1px solid rgb(255 255 255 / .16);
  border-radius: 7px;
  background: rgb(5 14 19 / .91);
  box-shadow: 0 15px 40px rgb(0 0 0 / .32);
  backdrop-filter: blur(12px);
}
.runtime-map-detail header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.runtime-map-detail header span {
  color: #62c3df;
  font-size: 9px;
  font-weight: 750;
  letter-spacing: .08em;
  text-transform: uppercase;
}
.runtime-map-detail header button {
  color: #a9bdc5;
  border: 0;
  background: transparent;
}
.runtime-map-detail h4 {
  margin: 6px 0 2px;
  font-size: 17px;
}
.runtime-map-detail > p {
  margin: 0 0 10px;
  color: #91aab5;
  font-size: 11px;
}
.runtime-map-detail dl {
  display: grid;
  gap: 7px;
  margin: 0;
}
.runtime-map-detail dl div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding-top: 7px;
  border-top: 1px solid rgb(255 255 255 / .09);
}
.runtime-map-detail dt {
  color: #829aa5;
  font-size: 10px;
}
.runtime-map-detail dd {
  margin: 0;
  font-family: var(--ui-font-mono);
  font-size: 10px;
  text-align: right;
}
.runtime-map-detail__primary {
  width: 100%;
  min-height: 32px;
  margin-top: 11px;
  color: #061217;
  border: 0;
  border-radius: 5px;
  background: #61c1de;
  font-size: 11px;
  font-weight: 750;
}

.runtime-map-coordinate {
  position: absolute;
  z-index: 5;
  right: 14px;
  bottom: 12px;
  padding: 5px 8px;
  color: #9db1ba;
  border-radius: 4px;
  background: rgb(5 14 19 / .76);
  font-family: var(--ui-font-mono);
  font-size: 9px;
}

.runtime-map-sidebar {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 12px;
  padding: 13px;
  border-left: 1px solid var(--ui-border);
  background: var(--ui-surface-muted);
}

.runtime-map-controls,
.runtime-guilds {
  padding: 12px;
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
  background: var(--ui-surface);
}
.runtime-map-controls {
  display: grid;
  gap: 10px;
}
.runtime-map-controls > label:not(.runtime-toggle) {
  display: grid;
  gap: 5px;
}
.runtime-map-controls > label > span {
  color: var(--ui-text-muted);
  font-size: 9px;
  font-weight: 700;
  text-transform: uppercase;
}
.runtime-map-controls select {
  width: 100%;
  min-height: 34px;
  padding: 0 9px;
  color: var(--ui-text);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-xs);
  background: var(--ui-surface-muted);
  font-size: 11px;
}
.runtime-map-controls > button {
  display: flex;
  min-height: 34px;
  align-items: center;
  justify-content: center;
  gap: 7px;
  color: var(--ui-accent);
  border: 1px solid color-mix(in oklch, var(--ui-accent), transparent 62%);
  border-radius: var(--ui-radius-xs);
  background: color-mix(in oklch, var(--ui-accent), transparent 91%);
  font-size: 11px;
  font-weight: 700;
}
.runtime-map-controls > button:disabled { opacity: .5; }

.runtime-toggle {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
}
.runtime-toggle input {
  position: absolute;
  opacity: 0;
}
.runtime-toggle i {
  position: relative;
  width: 30px;
  height: 17px;
  border: 1px solid var(--ui-border-strong);
  border-radius: 10px;
  background: var(--ui-surface-muted);
}
.runtime-toggle i::after {
  position: absolute;
  top: 3px;
  left: 3px;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--ui-text-muted);
  content: '';
  transition: transform .16s ease, background .16s ease;
}
.runtime-toggle input:checked + i {
  border-color: color-mix(in oklch, var(--ui-accent), transparent 35%);
  background: color-mix(in oklch, var(--ui-accent), transparent 80%);
}
.runtime-toggle input:checked + i::after {
  transform: translateX(13px);
  background: var(--ui-accent);
}

.runtime-guilds {
  min-height: 0;
  flex: 1;
}
.runtime-guilds > header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 9px;
}
.runtime-guilds > header b {
  display: grid;
  min-width: 26px;
  height: 26px;
  place-items: center;
  color: var(--ui-accent);
  border-radius: 5px;
  background: color-mix(in oklch, var(--ui-accent), transparent 88%);
  font-size: 11px;
}
.runtime-guild-list {
  display: grid;
  max-height: 260px;
  gap: 5px;
  overflow: auto;
}
.runtime-guild-list button {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  padding: 8px;
  color: var(--ui-text);
  border: 1px solid transparent;
  border-radius: var(--ui-radius-xs);
  background: var(--ui-surface-muted);
  text-align: left;
}
.runtime-guild-list button.active {
  border-color: color-mix(in oklch, var(--ui-accent), transparent 55%);
  background: color-mix(in oklch, var(--ui-accent), transparent 90%);
}
.runtime-guild-list button > i {
  width: 8px;
  height: 24px;
  border-radius: 3px;
  --guild-color: hsl(var(--guild-hue) 72% 58%);
  background: var(--guild-color);
  box-shadow: 0 0 9px color-mix(in srgb, var(--guild-color), transparent 45%);
}
.runtime-guild-list button > span {
  min-width: 0;
}
.runtime-guild-list strong,
.runtime-guild-list small {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.runtime-guild-list strong { font-size: 11px; }
.runtime-guild-list small {
  margin-top: 2px;
  color: var(--ui-text-muted);
  font-family: var(--ui-font-mono);
  font-size: 8px;
  text-transform: none;
}
.runtime-guild-list button > b {
  color: var(--ui-text-secondary);
  font-size: 11px;
}

.runtime-map-warning {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  margin: 0;
  padding: 9px 10px;
  color: var(--ui-warning);
  border: 1px solid color-mix(in oklch, var(--ui-warning), transparent 70%);
  border-radius: var(--ui-radius-xs);
  background: color-mix(in oklch, var(--ui-warning), transparent 93%);
  font-size: 10px;
  line-height: 1.45;
}

@keyframes spin { to { transform: rotate(360deg); } }
@keyframes marker-pulse {
  50% { opacity: .42; transform: scale(1.28); }
}

@media (max-width: 980px) {
  .runtime-map-layout { grid-template-columns: minmax(0, 1fr); }
  .runtime-map-sidebar {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    border-top: 1px solid var(--ui-border);
    border-left: 0;
  }
}

@media (max-width: 700px) {
  .runtime-map-header { align-items: flex-start; flex-direction: column; }
  .runtime-map-header dl { width: 100%; }
  .runtime-map-header dl div { flex: 1; }
  .runtime-map-layout,
  .runtime-map-viewport { min-height: 540px; }
  .runtime-map-sidebar { grid-template-columns: minmax(0, 1fr); }
  .runtime-map-status { top: 58px; }
}

@media (prefers-reduced-motion: reduce) {
  .runtime-marker.selected::before { animation: none; }
  .runtime-toggle i::after { transition: none; }
}
</style>
