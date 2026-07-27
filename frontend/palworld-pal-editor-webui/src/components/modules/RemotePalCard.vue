<script setup>
import { computed, nextTick, ref } from 'vue'
import AppIcon from '@/components/modules/AppIcon.vue'
import PassiveSkillCard from '@/components/modules/PassiveSkillCard.vue'
import { palSpeciesIconKey } from '@/components/modules/pal-species-filter'
import { usePalEditorStore } from '@/stores/paleditor'

const props = defineProps({
  entry: { type: Object, required: true },
  pal: { type: Object, required: true },
  layout: { type: String, default: 'palbox' },
})

const palStore = usePalEditorStore()
const trigger = ref(null)
const detailOpen = ref(false)
const detailPosition = ref({ top: 8, left: 8 })

const name = computed(() => (
  props.entry.nickname
  || props.pal.I18n
  || props.pal.Name
  || props.entry.characterId
  || palStore.getTranslatedText('Remote_PalUnknown')
))
const portraitSource = computed(() => (
  props.entry.characterId
    ? `/image/pals/${palSpeciesIconKey(props.pal)}`
    : ''
))
const healthPercent = computed(() => {
  const current = Number(props.entry.hp)
  const maximum = Number(props.entry.maxHp)
  if (!Number.isFinite(current) || !Number.isFinite(maximum) || maximum <= 0) return 0
  return Math.max(0, Math.min(100, (current / maximum) * 100))
})
const detailId = computed(() => `remote-pal-detail-${String(
  props.entry.instanceId || props.entry.slotIndex || 'unknown'
).replace(/[^a-zA-Z0-9_-]/g, '-')}`)

function translated(key) {
  return palStore.getTranslatedText(key)
}

function valueOrDash(value) {
  return value === null || value === undefined || value === '' ? '—' : value
}

function positionDetail() {
  const element = trigger.value
  if (!element) return
  const rect = element.getBoundingClientRect()
  const width = Math.min(320, Math.max(240, window.innerWidth - 16))
  const estimatedHeight = Math.min(520, window.innerHeight - 16)
  const rightSpace = window.innerWidth - rect.right
  const preferredLeft = rightSpace >= width + 12
    ? rect.right + 10
    : rect.left - width - 10
  detailPosition.value = {
    top: Math.max(8, Math.min(rect.top - 22, window.innerHeight - estimatedHeight - 8)),
    left: Math.max(8, Math.min(preferredLeft, window.innerWidth - width - 8)),
  }
}

async function openDetail() {
  detailOpen.value = true
  await nextTick()
  positionDetail()
}

function closeDetail() {
  detailOpen.value = false
}
</script>

<template>
  <button
    ref="trigger"
    type="button"
    class="remote-pal-card"
    :class="`remote-pal-card--${layout}`"
    :aria-describedby="detailOpen ? detailId : undefined"
    @mouseenter="openDetail"
    @mouseleave="closeDetail"
    @focus="openDetail"
    @blur="closeDetail"
    @keydown.esc="closeDetail"
  >
    <span class="remote-pal-card__portrait">
      <AppIcon v-if="!portraitSource" name="paw" :size="18" />
      <img v-else :src="portraitSource" :alt="name" draggable="false">
    </span>
    <span v-if="layout === 'party'" class="remote-pal-card__party-copy">
      <span class="remote-pal-card__party-heading">
        <strong>{{ name }}</strong>
        <small>{{ translated('Common_LevelShort') }}{{ valueOrDash(entry.level) }}</small>
      </span>
      <span class="remote-pal-card__health-track" aria-hidden="true">
        <span :style="{ width: `${healthPercent}%` }" />
      </span>
      <small class="remote-pal-card__health-value">
        {{ valueOrDash(entry.hp) }} / {{ valueOrDash(entry.maxHp) }}
      </small>
    </span>
    <template v-else>
      <span class="remote-pal-card__level">{{ translated('Common_LevelShort') }}{{ valueOrDash(entry.level) }}</span>
      <span class="remote-pal-card__name">{{ name }}</span>
    </template>
  </button>

  <Teleport to="body">
    <section
      v-if="detailOpen"
      :id="detailId"
      class="remote-pal-detail"
      :style="{ top: `${detailPosition.top}px`, left: `${detailPosition.left}px` }"
      role="tooltip"
    >
      <header class="remote-pal-detail__header">
        <span class="remote-pal-detail__level">
          <small>{{ translated('Remote_Level') }}</small>
          <strong>{{ valueOrDash(entry.level) }}</strong>
        </span>
        <span class="remote-pal-detail__identity">
          <strong>{{ name }}</strong>
          <small>{{ entry.characterId || '—' }}</small>
        </span>
        <span v-if="Number(entry.rare) > 0" class="remote-pal-detail__rare">
          {{ '★'.repeat(Math.min(4, Number(entry.rare))) }}
        </span>
      </header>

      <div class="remote-pal-detail__vitals">
        <span class="remote-pal-detail__portrait">
          <AppIcon v-if="!portraitSource" name="paw" :size="24" />
          <img v-else :src="portraitSource" alt="" draggable="false">
        </span>
        <span class="remote-pal-detail__vital-bars">
          <span class="remote-pal-detail__health-track">
            <span :style="{ width: `${healthPercent}%` }" />
          </span>
          <small>
            {{ translated('Remote_StatHp') }} {{ valueOrDash(entry.hp) }} / {{ valueOrDash(entry.maxHp) }}
          </small>
          <small v-if="entry.rank !== null && entry.rank !== undefined">
            {{ translated('Remote_Rank') }} {{ entry.rank }}
          </small>
        </span>
      </div>

      <div class="remote-pal-detail__stat-columns">
        <section>
          <h4>{{ translated('Remote_IVs') }}</h4>
          <dl>
            <div><dt>{{ translated('Remote_StatHp') }}</dt><dd>{{ valueOrDash(entry.ivs?.hp) }}</dd></div>
            <div><dt>{{ translated('Remote_StatMelee') }}</dt><dd>{{ valueOrDash(entry.ivs?.melee) }}</dd></div>
            <div><dt>{{ translated('Remote_StatShot') }}</dt><dd>{{ valueOrDash(entry.ivs?.shot) }}</dd></div>
            <div><dt>{{ translated('Remote_StatDefense') }}</dt><dd>{{ valueOrDash(entry.ivs?.defense) }}</dd></div>
          </dl>
        </section>
        <section>
          <h4>{{ translated('Remote_Enhancements') }}</h4>
          <dl>
            <div><dt>{{ translated('Remote_StatHp') }}</dt><dd>{{ valueOrDash(entry.enhancements?.hp) }}</dd></div>
            <div><dt>{{ translated('Remote_StatAttack') }}</dt><dd>{{ valueOrDash(entry.enhancements?.attack) }}</dd></div>
            <div><dt>{{ translated('Remote_StatDefense') }}</dt><dd>{{ valueOrDash(entry.enhancements?.defense) }}</dd></div>
            <div><dt>{{ translated('Remote_StatWork') }}</dt><dd>{{ valueOrDash(entry.enhancements?.craftSpeed) }}</dd></div>
          </dl>
        </section>
      </div>

      <section class="remote-pal-detail__passives">
        <h4>{{ translated('Editor_Passive_Skills') }}</h4>
        <div v-if="entry.passiveSkills?.length" class="remote-pal-detail__passive-list">
          <PassiveSkillCard
            v-for="skill in entry.passiveSkills"
            :key="skill"
            :skill="palStore.PASSIVE_SKILLS[skill]"
            :internal-name="skill"
            :unknown-label="translated('PalEditor_CustomPassive_UnknownBadge')"
            :focusable="false"
          />
        </div>
        <small v-else>—</small>
      </section>
    </section>
  </Teleport>
</template>

<style scoped>
.remote-pal-card {
  position: relative;
  display: grid;
  min-width: 0;
  margin: 0;
  color: var(--ui-text);
  font: inherit;
  text-align: left;
  background: var(--ui-surface);
  border: 1px solid var(--ui-border);
  cursor: default;
  transition: border-color 140ms ease, background-color 140ms ease, transform 140ms ease;
}

.remote-pal-card:hover,
.remote-pal-card:focus-visible {
  z-index: 1;
  background: var(--ui-surface-hover);
  border-color: var(--ui-accent);
  outline: none;
  transform: translateY(-1px);
}

.remote-pal-card--party {
  width: 100%;
  grid-template-columns: 62px minmax(0, 1fr);
  align-items: center;
  gap: 10px;
  min-height: 72px;
  padding: 5px 10px 5px 6px;
  border-radius: 8px;
}

.remote-pal-card--palbox {
  place-items: center;
  gap: 3px;
  min-height: 88px;
  padding: 7px 5px 5px;
  border-radius: 10px;
}

.remote-pal-card__portrait {
  position: relative;
  display: inline-grid;
  place-items: center;
  width: 56px;
  height: 56px;
  overflow: hidden;
  color: var(--ui-text-muted);
  background: var(--ui-canvas);
  border: 1px solid var(--ui-border);
  border-radius: 50%;
}

.remote-pal-card--palbox .remote-pal-card__portrait {
  width: 52px;
  height: 52px;
}

.remote-pal-card__portrait img,
.remote-pal-detail__portrait img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.remote-pal-card__party-copy,
.remote-pal-card__party-heading {
  display: grid;
  min-width: 0;
}

.remote-pal-card__party-copy { gap: 4px; }
.remote-pal-card__party-heading { grid-template-columns: minmax(0, 1fr) auto; gap: 8px; }
.remote-pal-card__party-heading strong,
.remote-pal-card__name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.remote-pal-card__party-heading strong { font-size: 12px; }
.remote-pal-card__party-heading small,
.remote-pal-card__health-value,
.remote-pal-card__level { color: var(--ui-text-muted); font-size: 9px; }
.remote-pal-card__health-value { text-align: right; }

.remote-pal-card__health-track,
.remote-pal-detail__health-track {
  display: block;
  height: 5px;
  overflow: hidden;
  background: color-mix(in srgb, var(--ui-danger) 35%, var(--ui-canvas));
  border-radius: 999px;
}

.remote-pal-card__health-track > span,
.remote-pal-detail__health-track > span {
  display: block;
  height: 100%;
  background: var(--ui-success);
  border-radius: inherit;
}

.remote-pal-card__level { position: absolute; top: 5px; left: 6px; }
.remote-pal-card__name { width: 100%; color: var(--ui-text-secondary); font-size: 9px; text-align: center; }

.remote-pal-detail {
  position: fixed;
  z-index: 4200;
  display: grid;
  width: min(320px, calc(100vw - 16px));
  max-height: calc(100vh - 16px);
  gap: 12px;
  padding: 14px;
  overflow: auto;
  color: var(--ui-text);
  background: color-mix(in srgb, var(--ui-surface) 96%, #071017);
  border: 1px solid var(--ui-accent);
  border-radius: 10px;
  box-shadow: 0 16px 44px rgb(0 0 0 / 38%);
  pointer-events: none;
}

.remote-pal-detail::before {
  position: absolute;
  inset: 5px;
  border: 1px solid color-mix(in srgb, var(--ui-accent) 24%, transparent);
  border-radius: 7px;
  content: '';
  pointer-events: none;
}

.remote-pal-detail__header {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: end;
  gap: 10px;
  padding-bottom: 9px;
  border-bottom: 1px solid var(--ui-border);
}

.remote-pal-detail__level { display: grid; min-width: 44px; }
.remote-pal-detail__level small { color: var(--ui-text-muted); font-size: 7px; letter-spacing: 0.08em; }
.remote-pal-detail__level strong { font-size: 27px; font-weight: 500; line-height: 1; }
.remote-pal-detail__identity { display: grid; min-width: 0; gap: 3px; }
.remote-pal-detail__identity strong,
.remote-pal-detail__identity small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.remote-pal-detail__identity strong { font-size: 14px; }
.remote-pal-detail__identity small { color: var(--ui-text-muted); font-size: 8px; }
.remote-pal-detail__rare { color: #f3a82e; font-size: 10px; }

.remote-pal-detail__vitals {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  align-items: center;
  gap: 12px;
}

.remote-pal-detail__portrait {
  display: inline-grid;
  place-items: center;
  width: 72px;
  height: 72px;
  overflow: hidden;
  color: var(--ui-text-muted);
  background: var(--ui-canvas);
  border: 1px solid var(--ui-border-strong);
  border-radius: 50%;
}

.remote-pal-detail__vital-bars { display: grid; gap: 6px; }
.remote-pal-detail__vital-bars small { color: var(--ui-text-secondary); font-size: 9px; }
.remote-pal-detail__health-track { height: 7px; }

.remote-pal-detail__stat-columns {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.remote-pal-detail__stat-columns section,
.remote-pal-detail__passives {
  padding: 9px;
  background: var(--ui-canvas);
  border: 1px solid var(--ui-border);
  border-radius: 8px;
}

.remote-pal-detail h4 {
  margin: 0 0 7px;
  color: var(--ui-text-muted);
  font-size: 8px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.remote-pal-detail dl { display: grid; gap: 4px; margin: 0; }
.remote-pal-detail dl div { display: flex; justify-content: space-between; gap: 8px; }
.remote-pal-detail dt { color: var(--ui-text-muted); font-size: 8px; }
.remote-pal-detail dd { margin: 0; font-size: 9px; font-weight: 700; }
.remote-pal-detail__passive-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 5px; }
.remote-pal-detail__passives > small { color: var(--ui-text-muted); }

@media (max-width: 720px) {
  .remote-pal-card--party { min-height: 66px; }
  .remote-pal-detail__passive-list { grid-template-columns: 1fr; }
}
</style>
