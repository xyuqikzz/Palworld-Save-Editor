<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'

const props = defineProps({
  skill: { type: Object, default: null },
  internalName: { type: String, default: '' },
  fallbackDescription: { type: String, default: '' },
  focusable: { type: Boolean, default: true },
})

const rating = computed(() => Number(props.skill?.Rating) || 0)
const rankLevel = computed(() => Math.min(Math.max(Math.abs(rating.value) || 1, 1), 5))
const ratingClass = computed(() => rating.value < 0 ? 'is-negative' : `is-rank-${rankLevel.value}`)
const name = computed(() => props.skill?.I18n?.[0] || props.internalName)
const description = computed(() => props.skill?.I18n?.[1] || props.fallbackDescription || props.internalName)
const rankSrc = computed(() => `/images/Pal/Texture/UI/Main_Menu/T_icon_skillstatus_rank_arrow_0${rankLevel.value}.webp`)
const card = ref(null)
const tooltip = ref(null)

const positionTooltip = () => {
  if (!card.value || !tooltip.value) return
  const cardRect = card.value.getBoundingClientRect()
  const width = Math.min(360, window.innerWidth - 32)
  tooltip.value.style.width = `${width}px`
  const tooltipHeight = tooltip.value.offsetHeight
  const left = Math.min(Math.max(cardRect.left, 16), window.innerWidth - width - 16)
  const top = cardRect.top >= tooltipHeight + 16
    ? cardRect.top - tooltipHeight - 8
    : Math.min(cardRect.bottom + 8, window.innerHeight - tooltipHeight - 16)
  tooltip.value.style.left = `${left}px`
  tooltip.value.style.top = `${Math.max(16, top)}px`
}

const stopFollowing = () => {
  window.removeEventListener('resize', positionTooltip)
  window.removeEventListener('scroll', positionTooltip, true)
}

const showTooltip = () => {
  if (!tooltip.value || !description.value) return
  if (typeof tooltip.value.showPopover === 'function') {
    if (!tooltip.value.matches(':popover-open')) tooltip.value.showPopover()
  } else {
    tooltip.value.classList.add('is-fallback-visible')
  }
  positionTooltip()
  stopFollowing()
  window.addEventListener('resize', positionTooltip)
  window.addEventListener('scroll', positionTooltip, true)
}

const hideTooltip = () => {
  if (!tooltip.value) return
  if (typeof tooltip.value.hidePopover === 'function' && tooltip.value.matches(':popover-open')) {
    tooltip.value.hidePopover()
  }
  tooltip.value.classList.remove('is-fallback-visible')
  stopFollowing()
}

onBeforeUnmount(hideTooltip)
</script>

<template>
  <div
    ref="card"
    :class="['passive-skill-card', 'tooltip-container', ratingClass, { 'is-unknown': !skill }]"
    :tabindex="focusable ? 0 : undefined"
    :aria-label="name"
    @mouseenter="showTooltip"
    @mouseleave="hideTooltip"
    @focusin="showTooltip"
    @focusout="hideTooltip"
  >
    <div class="passive-skill-banner">
      <span class="passive-skill-name">{{ name }}</span>
      <img class="passive-rank-icon" :src="rankSrc" alt="">
    </div>
    <span ref="tooltip" class="passive-skill-tooltip" popover="manual">{{ description }}</span>
  </div>
</template>

<style scoped>
.passive-skill-card {
  position: relative;
  display: flex;
  width: 100%;
  min-width: 0;
  min-height: 40px;
  overflow: visible;
  border-radius: 0;
  transition: filter 160ms ease;
}

.passive-skill-card:hover,
.passive-skill-card:focus-visible { filter: brightness(1.12); }
.passive-skill-card:focus-visible { outline: 2px solid var(--ui-accent); outline-offset: 2px; }

.passive-skill-banner {
  display: flex;
  width: 100%;
  min-height: 40px;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 0 10px;
  overflow: hidden;
  background-color: rgb(0 0 0 / 0.2);
  border: 1px solid #495057;
}

.passive-skill-name {
  min-width: 0;
  overflow: hidden;
  color: #fff;
  font-size: 13px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.passive-rank-icon {
  width: 18px;
  height: 18px;
  flex: 0 0 auto;
  object-fit: contain;
}

.passive-skill-card.is-rank-5 .passive-skill-banner {
  background-image: linear-gradient(to right, rgb(89 187 101 / 24%), rgb(77 9 203 / 48%)), linear-gradient(rgb(17 17 17 / 53.3%), #111), url('/images/Pal/Texture/UI/Main_Menu/T_prt_pal_skill_base_02.webp');
  background-position: center;
  background-size: cover;
  border-color: #c084fc;
}
.passive-skill-card.is-rank-5 .passive-skill-name { color: #e0b0ff; }

.passive-skill-card.is-rank-4 .passive-skill-banner {
  background-image: linear-gradient(to right, rgb(89 187 101 / 24%), rgb(69 67 209 / 48%)), linear-gradient(rgb(17 17 17 / 53.3%), #111), url('/images/Pal/Texture/UI/Main_Menu/T_prt_pal_skill_base_02.webp');
  background-position: center;
  background-size: cover;
  border-color: #68ffd8;
}
.passive-skill-card.is-rank-4 .passive-skill-name { color: #68ffd8; }
.passive-skill-card.is-rank-4 .passive-rank-icon { filter: sepia(1) saturate(100) hue-rotate(75deg); }

.passive-skill-card.is-rank-3 .passive-skill-banner,
.passive-skill-card.is-rank-2 .passive-skill-banner {
  background-image: linear-gradient(rgb(255 221 0 / 12.5%), rgb(255 221 0 / 12.5%)), linear-gradient(rgb(17 17 17 / 53.3%), #111), url('/images/Pal/Texture/UI/Main_Menu/T_prt_pal_skill_base_02.webp');
  background-position: center;
  background-size: cover;
  border-color: #ffdd00;
}
.passive-skill-card.is-rank-3 .passive-skill-name,
.passive-skill-card.is-rank-2 .passive-skill-name { color: #d1d560; }
.passive-skill-card.is-rank-3 .passive-rank-icon,
.passive-skill-card.is-rank-2 .passive-rank-icon { filter: sepia(1) saturate(100) hue-rotate(0deg); }
.passive-skill-card.is-rank-1 .passive-skill-name { color: #fff; }

.passive-skill-card.is-negative .passive-skill-name,
.passive-skill-card.is-negative .passive-skill-tooltip { color: #ff4646; }
.passive-skill-card.is-negative .passive-rank-icon {
  transform: scaleY(-1);
  filter: invert(0.8) sepia(0.9) saturate(74.56) hue-rotate(359deg) brightness(0.95) contrast(1.15);
}

.passive-skill-card.is-unknown .passive-skill-banner { border-color: var(--ui-danger); }
.passive-skill-card.is-unknown .passive-skill-name { color: var(--ui-danger); }

.passive-skill-tooltip {
  position: fixed;
  z-index: 60;
  inset: auto;
  display: none;
  margin: 0;
  padding: 10px 12px;
  color: var(--ui-text);
  background: var(--ui-surface-raised);
  border: 1px solid var(--ui-border-strong);
  border-radius: 8px;
  box-shadow: var(--ui-shadow-md);
  font-size: 12px;
  line-height: 1.45;
  text-align: left;
  white-space: pre-line;
  pointer-events: none;
}

.passive-skill-tooltip:popover-open,
.passive-skill-tooltip.is-fallback-visible { display: block; }

@media (prefers-reduced-motion: reduce) {
  .passive-skill-card,
  .passive-skill-tooltip { transition: none; }
}
</style>
