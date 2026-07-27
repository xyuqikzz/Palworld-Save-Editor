<script setup>
import AppIcon from '@/components/modules/AppIcon.vue'
import mapPoints from '@/data/map-points.json'
import { usePalEditorStore } from '@/stores/paleditor'
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

const palStore = usePalEditorStore()
const router = useRouter()
const viewport = ref(null)
const viewportSize = ref({ width: 1, height: 1 })
const zoom = ref(0)
const offset = ref({ x: 0, y: 0 })
const dragging = ref(false)
const pointerState = ref(null)
const mouseWorld = ref(null)
const searchTarget = ref('')
const selectedMarker = ref(null)
const showPlayers = ref(true)
const showBases = ref(true)
const showFastTravel = ref(false)
const layerPanelOpen = ref(true)
const activeMapArea = ref('MainMap')

const IMAGE_SIZE = 8192
const MIN_ZOOM = 0
const ZOOM_FACTOR = 1.3
const MAX_ZOOM = 6 + Math.log(1.5) / Math.log(ZOOM_FACTOR)
const MAX_NATIVE_SCALE = 1
const MAP_ASSET_ROOT = `${import.meta.env.BASE_URL}map/psp`
const MARKER_IMAGES = {
  player: `${MAP_ASSET_ROOT}/t_icon_compass_11.webp`,
  base: `${MAP_ASSET_ROOT}/t_icon_compass_camp.webp`,
  'fast-travel': `${MAP_ASSET_ROOT}/t_icon_compass_fttower.webp`,
}
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

const mapData = computed(() => palStore.MAP_DATA || {})
const activeMapConfig = computed(() => MAP_AREAS[activeMapArea.value])
const bounds = computed(() => (
  activeMapArea.value === 'MainMap'
    ? (mapData.value.bounds || MAP_AREAS.MainMap.bounds)
    : activeMapConfig.value.bounds
))
const players = computed(() => Array.isArray(mapData.value.players) ? mapData.value.players : [])
const bases = computed(() => Array.isArray(mapData.value.bases) ? mapData.value.bases : [])
const unavailableCount = computed(() => (
  (mapData.value.unavailable_player_ids?.length || 0)
  + (mapData.value.unavailable_base_ids?.length || 0)
))

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

function worldToMapPoint(x, y) {
  const current = bounds.value
  return {
    x: ((y - current.min_y) / (current.max_y - current.min_y)) * IMAGE_SIZE,
    y: ((current.max_x - x) / (current.max_x - current.min_x)) * IMAGE_SIZE,
  }
}

function mapToWorldPoint(x, y) {
  const current = bounds.value
  return {
    x: current.max_x - (y / IMAGE_SIZE) * (current.max_x - current.min_x),
    y: current.min_y + (x / IMAGE_SIZE) * (current.max_y - current.min_y),
  }
}

function markerStyle(marker) {
  const point = worldToMapPoint(marker.x, marker.y)
  return {
    left: `${point.x}px`,
    top: `${point.y}px`,
  }
}

function baseAreaStyle(marker) {
  const radius = Number(marker.radius)
  if (!Number.isFinite(radius) || radius <= 0) return null
  const diameter = (
    radius * 2 * IMAGE_SIZE / (bounds.value.max_x - bounds.value.min_x)
  )
  return {
    width: `${diameter}px`,
    height: `${diameter}px`,
  }
}

function pointIsInMapArea(x, y, area) {
  const worldX = Number(x)
  const worldY = Number(y)
  const current = MAP_AREAS[area]?.bounds
  if (!current || !Number.isFinite(worldX) || !Number.isFinite(worldY)) return false
  return (
    worldX >= current.min_x
    && worldX <= current.max_x
    && worldY >= current.min_y
    && worldY <= current.max_y
  )
}

function mapAreaForPosition(x, y) {
  return MAP_AREA_PRIORITY.find(area => pointIsInMapArea(x, y, area)) || null
}

function markersInActiveArea(markers) {
  return markers.filter(marker => (
    mapAreaForPosition(marker.x, marker.y) === activeMapArea.value
  ))
}

const playerMarkers = computed(() => players.value.map(player => ({
  ...player,
  id: `player:${player.player_id}`,
  kind: 'player',
  label: player.name || player.player_id,
})))
const baseMarkers = computed(() => bases.value.map(base => ({
  ...base,
  id: `base:${base.base_id}`,
  kind: 'base',
  label: base.guild_name || palStore.getTranslatedText('Map_Base'),
})))
const fastTravelMarkers = computed(() => mapPoints.fast_travel.map((point, index) => ({
  id: `fast:${index}`,
  kind: 'fast-travel',
  label: palStore.getTranslatedText('Map_FastTravel'),
  x: point[0],
  y: point[1],
  z: null,
})))
const activePlayerMarkers = computed(() => markersInActiveArea(playerMarkers.value))
const activeBaseMarkers = computed(() => markersInActiveArea(baseMarkers.value))
const activeFastTravelMarkers = computed(() => markersInActiveArea(fastTravelMarkers.value))
const activeSaveMarkerCount = computed(() => (
  activePlayerMarkers.value.length + activeBaseMarkers.value.length
))
const visibleMarkers = computed(() => [
  ...(showPlayers.value ? activePlayerMarkers.value : []),
  ...(showBases.value ? activeBaseMarkers.value : []),
  ...(showFastTravel.value ? activeFastTravelMarkers.value : []),
])
const searchableMarkers = computed(() => [
  ...activePlayerMarkers.value,
  ...activeBaseMarkers.value,
])

function markerImage(marker) {
  return MARKER_IMAGES[marker.kind] || MARKER_IMAGES['fast-travel']
}

function markerKindLabel(marker) {
  const key = {
    player: 'Map_Player',
    base: 'Map_Base',
    'fast-travel': 'Map_FastTravel',
  }[marker.kind]
  return palStore.getTranslatedText(key)
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
  selectedMarker.value = null
  searchTarget.value = ''
}

function switchMapArea(area) {
  if (!MAP_AREAS[area] || area === activeMapArea.value) return
  activeMapArea.value = area
  mouseWorld.value = null
  resetView()
}

function focusMarker(marker) {
  if (!marker) return
  if (zoom.value < 3) zoom.value = 3
  const point = worldToMapPoint(marker.x, marker.y)
  offset.value = {
    x: -(point.x - IMAGE_SIZE / 2) * scale.value,
    y: -(point.y - IMAGE_SIZE / 2) * scale.value,
  }
  clampOffset()
  selectedMarker.value = marker
}

function focusSearchTarget() {
  const marker = searchableMarkers.value.find(item => item.id === searchTarget.value)
  if (marker) focusMarker(marker)
}

function selectMarker(marker) {
  selectedMarker.value = marker
  searchTarget.value = searchableMarkers.value.some(item => item.id === marker.id)
    ? marker.id
    : ''
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
  if (event.button !== 0 || event.target.closest('button, input, select, label, a')) return
  dragging.value = true
  pointerState.value = { id: event.pointerId, x: event.clientX, y: event.clientY }
  viewport.value?.setPointerCapture(event.pointerId)
}

function onPointerMove(event) {
  updateMouseWorld(event)
  if (!dragging.value || pointerState.value?.id !== event.pointerId) return
  const dx = event.clientX - pointerState.value.x
  const dy = event.clientY - pointerState.value.y
  pointerState.value = { id: event.pointerId, x: event.clientX, y: event.clientY }
  offset.value = { x: offset.value.x + dx, y: offset.value.y + dy }
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
  return Number.isFinite(Number(value)) ? Number(value).toFixed(2) : '—'
}

function openSelectedPlayer() {
  if (selectedMarker.value?.kind !== 'player') return
  router.push({
    name: 'PlayerEditor',
    params: { playerId: selectedMarker.value.player_id },
  })
}

function openSelectedBase() {
  if (selectedMarker.value?.kind !== 'base') return
  router.push({
    name: 'BaseEditor',
    params: { baseKey: `base:${selectedMarker.value.base_id}` },
  })
}

let resizeObserver = null

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
  await palStore.loadMapData()
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
})
</script>

<template>
  <main class="map-page">
    <section
      ref="viewport"
      class="map-viewport"
      :class="{ 'map-viewport--dragging': dragging }"
      tabindex="0"
      :aria-label="palStore.getTranslatedText('Map_ViewportLabel')"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerUp"
      @wheel.prevent="onWheel"
      @keydown="onMapKeydown"
    >
      <div class="map-stage" :style="stageStyle">
        <img
          :key="activeMapArea"
          class="map-image"
          :src="activeMapConfig.imageUrl"
          alt=""
          aria-hidden="true"
          decoding="async"
          fetchpriority="high"
          draggable="false"
        />

        <template v-for="marker in visibleMarkers" :key="marker.id">
          <span
            v-if="marker.kind === 'base' && zoom >= 4 && baseAreaStyle(marker)"
            class="base-area"
            :style="{ ...markerStyle(marker), ...baseAreaStyle(marker) }"
            aria-hidden="true"
          />
          <span
            class="map-marker-anchor"
            :class="`map-marker-anchor--${marker.kind}`"
            :style="markerStyle(marker)"
          >
            <button
              class="map-marker"
              :class="{ 'map-marker--selected': selectedMarker?.id === marker.id }"
              type="button"
              :aria-label="`${markerKindLabel(marker)} · ${marker.label}`"
              @pointerdown.stop
              @click.stop="selectMarker(marker)"
            >
              <img
                class="map-marker__icon"
                :src="markerImage(marker)"
                alt=""
                aria-hidden="true"
                draggable="false"
              />
              <span
                v-if="marker.kind === 'player' || marker.kind === 'base'"
                class="map-marker__label"
              >
                {{ marker.label }}
              </span>
            </button>
          </span>
        </template>
      </div>

      <nav
        class="map-area-tabs"
        role="tablist"
        :aria-label="palStore.getTranslatedText('Map_AreaTabs')"
      >
        <button
          v-for="area in MAP_AREA_TABS"
          :key="area"
          type="button"
          role="tab"
          :class="{ 'map-area-tabs__tab--active': activeMapArea === area }"
          :aria-selected="activeMapArea === area"
          :tabindex="activeMapArea === area ? 0 : -1"
          @click="switchMapArea(area)"
        >
          {{ palStore.getTranslatedText(MAP_AREAS[area].labelKey) }}
        </button>
      </nav>

      <div class="map-status">
        <span class="map-status__badge">
          <AppIcon name="map" :size="15" />
          {{ palStore.getTranslatedText('Map_Title') }}
        </span>
        <span class="map-status__snapshot">
          {{ palStore.getTranslatedText('Map_SaveSnapshot') }}
        </span>
        <span v-if="unavailableCount" class="map-status__warning">
          {{ palStore.getTranslatedText('Map_UnavailableCount', [unavailableCount]) }}
        </span>
      </div>

      <div v-if="palStore.MAP_LOADING" class="map-state" role="status">
        <span class="map-state__spinner" />
        {{ palStore.getTranslatedText('Map_Loading') }}
      </div>
      <div
        v-else-if="!activeSaveMarkerCount"
        class="map-state"
        role="status"
      >
        {{ palStore.getTranslatedText('Map_AreaEmpty') }}
      </div>

      <div class="zoom-control" :aria-label="palStore.getTranslatedText('Map_ZoomControls')">
        <button
          type="button"
          :aria-label="palStore.getTranslatedText('Map_ZoomIn')"
          :disabled="zoom >= maxUsableZoom"
          @click="setZoom(zoom + 1)"
        >
          <AppIcon name="plus" :size="15" />
        </button>
        <div class="zoom-control__track" aria-hidden="true">
          <span :style="{ height: `${zoomProgress * 100}%` }" />
          <i :style="{ bottom: `${zoomProgress * 100}%` }" />
        </div>
        <button
          type="button"
          :aria-label="palStore.getTranslatedText('Map_ZoomOut')"
          :disabled="zoom <= MIN_ZOOM"
          @click="setZoom(zoom - 1)"
        >
          <span aria-hidden="true">−</span>
        </button>
        <button
          type="button"
          :aria-label="palStore.getTranslatedText('Map_ResetView')"
          @click="resetView"
        >
          <AppIcon name="refresh" :size="14" />
        </button>
      </div>

      <article v-if="selectedMarker" class="map-detail">
        <header>
          <span class="map-detail__kind">{{ markerKindLabel(selectedMarker) }}</span>
          <button
            type="button"
            :aria-label="palStore.getTranslatedText('Map_CloseDetails')"
            @click="selectedMarker = null"
          >
            <AppIcon name="x" :size="17" />
          </button>
        </header>
        <h2>{{ selectedMarker.label }}</h2>
        <dl>
          <div v-if="selectedMarker.kind === 'player' || selectedMarker.kind === 'base'">
            <dt>{{ palStore.getTranslatedText('Map_Guild') }}</dt>
            <dd>{{ selectedMarker.guild_name || palStore.getTranslatedText('Map_NoGuild') }}</dd>
          </div>
          <div v-if="selectedMarker.level != null">
            <dt>{{ palStore.getTranslatedText('Map_Level') }}</dt>
            <dd>{{ selectedMarker.level }}</dd>
          </div>
          <div>
            <dt>{{ palStore.getTranslatedText('Map_Coordinates') }}</dt>
            <dd>
              X {{ formatCoordinate(selectedMarker.x) }} ·
              Y {{ formatCoordinate(selectedMarker.y) }}
            </dd>
          </div>
          <div v-if="selectedMarker.z != null">
            <dt>{{ palStore.getTranslatedText('Map_Altitude') }}</dt>
            <dd>{{ formatCoordinate(selectedMarker.z) }}</dd>
          </div>
          <div v-if="selectedMarker.kind === 'base' && selectedMarker.radius != null">
            <dt>{{ palStore.getTranslatedText('Map_BaseRadius') }}</dt>
            <dd>{{ formatCoordinate(selectedMarker.radius) }}</dd>
          </div>
        </dl>
        <button
          v-if="selectedMarker.kind === 'player'"
          class="map-detail__primary"
          type="button"
          @click="openSelectedPlayer"
        >
          {{ palStore.getTranslatedText('Map_OpenPlayer') }}
        </button>
        <button
          v-else-if="selectedMarker.kind === 'base'"
          class="map-detail__primary"
          type="button"
          @click="openSelectedBase"
        >
          {{ palStore.getTranslatedText('Map_OpenBasePals') }}
        </button>
      </article>

      <aside class="layer-panel" :class="{ 'layer-panel--collapsed': !layerPanelOpen }">
        <button
          class="layer-panel__collapse"
          type="button"
          :aria-label="palStore.getTranslatedText(layerPanelOpen ? 'Map_CollapsePanel' : 'Map_ExpandPanel')"
          :aria-expanded="layerPanelOpen"
          @click="layerPanelOpen = !layerPanelOpen"
        >
          <AppIcon :name="layerPanelOpen ? 'chevron-down' : 'chevron-up'" :size="16" />
        </button>
        <div v-if="layerPanelOpen" class="layer-panel__content">
          <label class="target-select">
            <span class="sr-only">{{ palStore.getTranslatedText('Map_SearchTarget') }}</span>
            <select v-model="searchTarget" @change="focusSearchTarget">
              <option value="">{{ palStore.getTranslatedText('Map_SearchTarget') }}</option>
              <option
                v-for="marker in searchableMarkers"
                :key="marker.id"
                :value="marker.id"
              >
                {{ markerKindLabel(marker) }} · {{ marker.label }}
              </option>
            </select>
          </label>
          <p class="layer-panel__summary">
            {{ palStore.getTranslatedText('Map_VisibleSummary', [visibleMarkers.length]) }}
          </p>
          <label class="layer-toggle">
            <span>{{ palStore.getTranslatedText('Map_ShowFastTravel') }}</span>
            <input v-model="showFastTravel" type="checkbox" />
            <i aria-hidden="true" />
          </label>
          <label class="layer-toggle">
            <span>{{ palStore.getTranslatedText('Map_ShowPlayers') }}</span>
            <input v-model="showPlayers" type="checkbox" />
            <i aria-hidden="true" />
          </label>
          <label class="layer-toggle">
            <span>{{ palStore.getTranslatedText('Map_ShowBases') }}</span>
            <input v-model="showBases" type="checkbox" />
            <i aria-hidden="true" />
          </label>
          <button
            class="layer-panel__refresh"
            type="button"
            :disabled="palStore.MAP_LOADING"
            @click="palStore.loadMapData"
          >
            <AppIcon name="refresh" :size="14" />
            {{ palStore.getTranslatedText('Map_Refresh') }}
          </button>
        </div>
      </aside>

      <div class="map-coordinate" aria-live="polite">
        <span v-if="mouseWorld">
          X {{ formatCoordinate(mouseWorld.x) }} · Y {{ formatCoordinate(mouseWorld.y) }}
        </span>
        <span v-else>{{ palStore.getTranslatedText('Map_MoveForCoordinates') }}</span>
      </div>

      <a
        class="map-attribution"
        href="https://github.com/oMaN-Rod/palworld-save-pal"
        target="_blank"
        rel="noreferrer"
      >
        {{ palStore.getTranslatedText('Map_Attribution') }}
      </a>
    </section>
  </main>
</template>

<style scoped>
.map-page {
  height: 100dvh;
  padding-top: var(--editor-top-offset);
  color: var(--ui-text);
  background: #071925;
}

.map-viewport {
  position: relative;
  height: calc(100dvh - var(--editor-top-offset));
  min-height: 440px;
  overflow: hidden;
  background:
    radial-gradient(circle at 50% 45%, rgba(20, 66, 83, 0.48), transparent 48%),
    #081d29;
  outline: 0;
  cursor: grab;
  touch-action: none;
  user-select: none;
}

.map-viewport:focus-visible {
  box-shadow: 0 0 0 2px var(--ui-accent) inset;
}

.map-viewport--dragging {
  cursor: grabbing;
}

.map-stage {
  position: absolute;
  width: 8192px;
  height: 8192px;
  transform-origin: center;
  will-change: transform;
}

.map-image {
  position: absolute;
  inset: 0;
  display: block;
  width: 8192px;
  height: 8192px;
  object-fit: contain;
  pointer-events: none;
  background: #07121a;
  box-shadow: 0 0 80px rgba(63, 193, 221, 0.18);
  image-rendering: auto;
}

.map-marker-anchor,
.base-area {
  position: absolute;
}

.base-area {
  z-index: 2;
  border: 2px solid rgba(105, 214, 255, 0.75);
  border-radius: 50%;
  background: rgba(44, 159, 214, 0.12);
  box-shadow: 0 0 18px rgba(56, 189, 248, 0.24) inset;
  transform: translate(-50%, -50%);
  pointer-events: none;
}

.map-marker-anchor {
  z-index: 5;
  width: 0;
  height: 0;
}

.map-marker-anchor--base { z-index: 6; }
.map-marker-anchor--player { z-index: 7; }

.map-marker {
  position: absolute;
  left: 0;
  bottom: -16px;
  display: flex;
  align-items: center;
  flex-direction: column;
  padding: 0;
  color: white;
  background: transparent;
  border: 0;
  filter: drop-shadow(0 4px 7px rgba(0, 8, 13, 0.7));
  transform: translate(-50%, 0) scale(var(--marker-inverse-scale));
  transform-origin: center bottom;
}

.map-marker__icon {
  display: block;
  width: 32px;
  height: 32px;
  object-fit: contain;
  filter: drop-shadow(0 3px 5px rgba(0, 8, 13, 0.82));
}

.map-marker__label {
  max-width: 150px;
  margin-bottom: 5px;
  padding: 3px 7px;
  overflow: hidden;
  color: #10202a;
  background: rgba(255, 255, 255, 0.94);
  border-radius: 5px;
  box-shadow: 0 2px 7px rgba(0, 8, 13, 0.5);
  font-size: 10px;
  font-weight: 700;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
  order: -1;
}

.map-marker--selected .map-marker__icon {
  filter:
    drop-shadow(0 0 2px white)
    drop-shadow(0 0 8px #7dd3fc)
    drop-shadow(0 3px 5px rgba(0, 8, 13, 0.82));
}

.map-marker:focus-visible {
  outline: 0;
}

.map-marker:focus-visible .map-marker__icon {
  filter:
    drop-shadow(0 0 2px white)
    drop-shadow(0 0 8px var(--ui-accent));
}

.map-area-tabs {
  position: absolute;
  top: 16px;
  left: 16px;
  z-index: 23;
  display: inline-flex;
  gap: 3px;
  padding: 4px;
  background: rgba(8, 25, 36, 0.9);
  border: 1px solid rgba(185, 227, 242, 0.18);
  border-radius: 11px;
  box-shadow: 0 10px 30px rgba(0, 9, 15, 0.3);
  backdrop-filter: blur(12px);
}

.map-area-tabs button {
  min-height: 30px;
  padding: 0 13px;
  color: var(--ui-text-muted);
  background: transparent;
  border: 0;
  border-radius: 7px;
  font-size: 11px;
  font-weight: 700;
  white-space: nowrap;
}

.map-area-tabs button:hover {
  color: var(--ui-text);
  background: rgba(255, 255, 255, 0.06);
}

.map-area-tabs button:focus-visible {
  outline: 2px solid var(--ui-accent);
  outline-offset: 1px;
}

.map-area-tabs .map-area-tabs__tab--active {
  color: #071925;
  background: var(--ui-accent);
  box-shadow: 0 3px 10px rgba(56, 189, 248, 0.22);
}

.map-status {
  position: absolute;
  top: 62px;
  left: 16px;
  z-index: 20;
  display: flex;
  align-items: center;
  gap: 8px;
  pointer-events: none;
}

.map-status > span {
  display: inline-flex;
  min-height: 30px;
  align-items: center;
  gap: 7px;
  padding: 5px 10px;
  background: rgba(8, 25, 36, 0.86);
  border: 1px solid rgba(185, 227, 242, 0.16);
  border-radius: 999px;
  box-shadow: 0 8px 25px rgba(0, 9, 15, 0.24);
  backdrop-filter: blur(12px);
  font-size: 11px;
  font-weight: 650;
}

.map-status__badge { color: #9bddf8; }
.map-status__snapshot { color: var(--ui-text-secondary); }
.map-status__warning { color: #f2bc68; }

.map-state {
  position: absolute;
  inset: 50% auto auto 50%;
  z-index: 30;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  color: var(--ui-text-secondary);
  background: rgba(8, 25, 36, 0.92);
  border: 1px solid rgba(185, 227, 242, 0.16);
  border-radius: var(--ui-radius-md);
  box-shadow: var(--ui-shadow-md);
  transform: translate(-50%, -50%);
}

.map-state__spinner {
  width: 17px;
  height: 17px;
  border: 2px solid var(--ui-border-strong);
  border-top-color: var(--ui-accent);
  border-radius: 50%;
  animation: map-spin 700ms linear infinite;
}

.zoom-control {
  position: absolute;
  bottom: 54px;
  left: 16px;
  z-index: 20;
  display: flex;
  width: 36px;
  align-items: center;
  flex-direction: column;
  gap: 5px;
  padding: 6px;
  background: rgba(8, 25, 36, 0.86);
  border: 1px solid rgba(185, 227, 242, 0.16);
  border-radius: 12px;
  box-shadow: 0 10px 30px rgba(0, 9, 15, 0.28);
  backdrop-filter: blur(12px);
}

.zoom-control button,
.map-detail header button,
.layer-panel__collapse {
  display: grid;
  width: 24px;
  height: 24px;
  place-items: center;
  padding: 0;
  color: var(--ui-text-secondary);
  background: transparent;
  border: 0;
  border-radius: 6px;
}

.zoom-control button:hover:not(:disabled),
.map-detail header button:hover,
.layer-panel__collapse:hover {
  color: white;
  background: rgba(255, 255, 255, 0.08);
}

.zoom-control button:disabled {
  opacity: 0.32;
}

.zoom-control__track {
  position: relative;
  width: 3px;
  height: 76px;
  margin: 3px 0;
  overflow: visible;
  background: rgba(255, 255, 255, 0.16);
  border-radius: 999px;
}

.zoom-control__track span {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  background: var(--ui-accent);
  border-radius: inherit;
}

.zoom-control__track i {
  position: absolute;
  left: 50%;
  width: 11px;
  height: 11px;
  background: white;
  border: 2px solid var(--ui-accent);
  border-radius: 50%;
  box-shadow: 0 2px 6px rgba(0, 9, 15, 0.45);
  transform: translate(-50%, 50%);
}

.map-detail {
  position: absolute;
  top: 104px;
  left: 16px;
  z-index: 22;
  width: min(300px, calc(100% - 32px));
  padding: 16px;
  color: var(--ui-text);
  background: rgba(12, 31, 43, 0.94);
  border: 1px solid rgba(185, 227, 242, 0.16);
  border-radius: var(--ui-radius-md);
  box-shadow: 0 18px 46px rgba(0, 9, 15, 0.4);
  backdrop-filter: blur(16px);
}

.map-detail header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.map-detail__kind {
  color: var(--ui-accent);
  font-size: 10px;
  font-weight: 750;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.map-detail h2 {
  margin: 6px 0 12px;
  overflow: hidden;
  font-size: 18px;
  letter-spacing: -0.02em;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.map-detail dl {
  display: grid;
  gap: 8px;
  margin: 0;
}

.map-detail dl > div {
  display: grid;
  grid-template-columns: 86px minmax(0, 1fr);
  gap: 8px;
  padding-top: 8px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}

.map-detail dt {
  color: var(--ui-text-muted);
  font-size: 11px;
}

.map-detail dd {
  overflow: hidden;
  margin: 0;
  color: var(--ui-text-secondary);
  font-size: 11px;
  text-align: right;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.map-detail__primary,
.layer-panel__refresh {
  display: inline-flex;
  width: 100%;
  min-height: 34px;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin-top: 14px;
  color: #0a1e2a;
  background: var(--ui-accent);
  border: 1px solid var(--ui-accent);
  border-radius: var(--ui-radius-sm);
  font-size: 11px;
  font-weight: 700;
}

.layer-panel {
  position: absolute;
  right: 16px;
  bottom: 48px;
  z-index: 21;
  width: 274px;
  padding: 8px 14px 14px;
  background: rgba(8, 22, 31, 0.93);
  border: 1px solid rgba(185, 227, 242, 0.14);
  border-radius: 14px;
  box-shadow: 0 18px 46px rgba(0, 9, 15, 0.38);
  backdrop-filter: blur(16px);
}

.layer-panel--collapsed {
  width: 42px;
  padding: 8px;
}

.layer-panel__collapse {
  width: 100%;
  margin-bottom: 4px;
}

.layer-panel--collapsed .layer-panel__collapse {
  margin: 0;
}

.target-select select {
  width: 100%;
  min-height: 34px;
  padding: 0 9px;
  color: var(--ui-text-secondary);
  background: rgba(255, 255, 255, 0.055);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  font-size: 11px;
}

.layer-panel__summary {
  margin: 9px 0 6px;
  color: var(--ui-text-muted);
  font-size: 10px;
}

.layer-toggle {
  display: grid;
  min-height: 34px;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  color: var(--ui-text-secondary);
  font-size: 11px;
  cursor: pointer;
}

.layer-toggle input {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}

.layer-toggle i {
  position: relative;
  width: 31px;
  height: 18px;
  background: rgba(255, 255, 255, 0.14);
  border-radius: 999px;
  transition: background 150ms ease;
}

.layer-toggle i::after {
  position: absolute;
  top: 3px;
  left: 3px;
  width: 12px;
  height: 12px;
  content: "";
  background: white;
  border-radius: 50%;
  transition: transform 150ms ease;
}

.layer-toggle input:checked + i {
  background: var(--ui-accent);
}

.layer-toggle input:checked + i::after {
  transform: translateX(13px);
}

.layer-toggle input:focus-visible + i {
  outline: 2px solid var(--ui-accent);
  outline-offset: 2px;
}

.layer-panel__refresh {
  margin-top: 8px;
  color: var(--ui-text-secondary);
  background: rgba(255, 255, 255, 0.055);
  border-color: rgba(255, 255, 255, 0.12);
}

.layer-panel__refresh:disabled {
  opacity: 0.45;
}

.map-coordinate,
.map-attribution {
  position: absolute;
  bottom: 14px;
  z-index: 20;
  color: rgba(210, 230, 238, 0.72);
  font-size: 10px;
  font-weight: 600;
  text-decoration: none;
  text-shadow: 0 2px 5px #000;
}

.map-coordinate { right: 16px; }
.map-attribution { left: 16px; }
.map-attribution:hover { color: white; }

@keyframes map-spin {
  to { transform: rotate(360deg); }
}

@media (max-width: 720px) {
  .map-area-tabs {
    top: 10px;
    left: 10px;
  }

  .map-status {
    top: 56px;
    left: 10px;
    flex-wrap: wrap;
  }

  .map-status__snapshot {
    display: none !important;
  }

  .map-detail {
    top: 98px;
    left: 10px;
  }

  .zoom-control {
    bottom: 48px;
    left: 10px;
  }

  .layer-panel {
    right: 10px;
    bottom: 42px;
    width: min(260px, calc(100% - 68px));
  }

  .layer-panel--collapsed {
    width: 42px;
  }

  .map-coordinate {
    right: 10px;
  }

  .map-attribution {
    left: 10px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .map-state__spinner { animation: none; }
}
</style>
