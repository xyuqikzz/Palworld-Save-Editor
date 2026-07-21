<script setup>
import { computed, nextTick, ref } from 'vue'
import AppIcon from '@/components/modules/AppIcon.vue'
import ElementIcon from '@/components/modules/ElementIcon.vue'
import { usePalEditorStore } from '@/stores/paleditor'

const palStore = usePalEditorStore()

const props = defineProps({
  modelValue: { type: String, default: '' },
  options: { type: Array, default: () => [] },
  selectedOption: { type: Object, default: null },
  kind: { type: String, default: 'active', validator: value => ['active', 'passive'].includes(value) },
  disabled: { type: Boolean, default: false },
  iconOnly: { type: Boolean, default: false },
  showInternalName: { type: Boolean, default: false },
  placeholder: { type: String, default: '' },
  title: { type: String, default: '' },
  searchPlaceholder: { type: String, default: '' },
  resultsLabel: { type: String, default: '' },
  emptyText: { type: String, default: '' },
  closeLabel: { type: String, default: '' },
  ratingLabel: { type: String, default: '' },
  powerLabel: { type: String, default: '' },
  cooldownLabel: { type: String, default: '' },
  uniqueLabel: { type: String, default: '' },
  fruitLabel: { type: String, default: '' }
})

const emit = defineEmits(['update:modelValue', 'select'])

const dialog = ref(null)
const searchInput = ref(null)
const searchQuery = ref('')
const passiveRatingFilter = ref('all')
const activeElementFilter = ref('all')

const isActive = computed(() => props.kind === 'active')
const translated = (activeKey, passiveKey = activeKey) => palStore.getTranslatedText(
  isActive.value ? activeKey : passiveKey,
)
const placeholderText = computed(() => props.placeholder || translated('Editor_Select_Active', 'Editor_Select_Passive'))
const titleText = computed(() => props.title || translated('Editor_Active_Picker_Title', 'Editor_Passive_Picker_Title'))
const searchPlaceholderText = computed(() => props.searchPlaceholder || translated('Editor_Active_Search_Placeholder', 'Editor_Passive_Search_Placeholder'))
const resultsLabelText = computed(() => props.resultsLabel || translated('Editor_Active_Results_Label', 'Editor_Passive_Results_Label'))
const emptyTextValue = computed(() => props.emptyText || translated('Editor_Active_Empty', 'Editor_Passive_Empty'))
const closeLabelText = computed(() => props.closeLabel || palStore.getTranslatedText('Common_Close'))
const ratingLabelText = computed(() => props.ratingLabel || palStore.getTranslatedText('Editor_Skill_Rating'))
const powerLabelText = computed(() => props.powerLabel || palStore.getTranslatedText('Common_Power'))
const cooldownLabelText = computed(() => props.cooldownLabel || palStore.getTranslatedText('Common_Cooldown'))
const uniqueLabelText = computed(() => props.uniqueLabel || palStore.getTranslatedText('Editor_Skill_Unique'))
const fruitLabelText = computed(() => props.fruitLabel || palStore.getTranslatedText('Editor_Skill_Fruit'))
const skillName = skill => skill?.I18n?.[0] || skill?.InternalName || ''
const skillDescription = skill => skill?.I18n?.[1] || ''

const ratingClass = rating => {
  if (rating >= 4) return 'is-exceptional'
  if (rating >= 2) return 'is-positive'
  if (rating > 0) return 'is-standard'
  if (rating < 0) return 'is-negative'
  return 'is-neutral'
}

const passiveRankLevel = rating => Math.min(Math.max(Math.abs(Number(rating) || 1), 1), 5)
const passiveRankSrc = rating => `/images/Pal/Texture/UI/Main_Menu/T_icon_skillstatus_rank_arrow_0${passiveRankLevel(rating)}.webp`
const passiveRatingClass = rating => {
  const value = Number(rating) || 0
  return value < 0 ? 'is-negative' : `is-rank-${passiveRankLevel(value)}`
}

const passiveFilters = computed(() => [
  { value: 'all', label: palStore.getTranslatedText('Editor_Passive_Filter_All') },
  { value: '5', label: palStore.getTranslatedText('Editor_Passive_Filter_Rainbow') },
  { value: '4', label: palStore.getTranslatedText('Editor_Passive_Filter_Legend') },
  { value: '3', label: palStore.getTranslatedText('Editor_Passive_Filter_Gold') },
  { value: '2', label: palStore.getTranslatedText('Editor_Passive_Filter_Gold') },
  { value: '1', label: palStore.getTranslatedText('Editor_Passive_Filter_Normal') },
  { value: '-1', label: palStore.getTranslatedText('Editor_Passive_Filter_Negative1') },
  { value: '-2', label: palStore.getTranslatedText('Editor_Passive_Filter_Negative2') },
  { value: '-3', label: palStore.getTranslatedText('Editor_Passive_Filter_Negative3') }
])

const elementKey = element => String(element || '')
  .split('::').pop()
  .replace('EPalElementType_', '')

const activeElements = computed(() => {
  const preferredOrder = ['Neutral', 'Fire', 'Water', 'Electric', 'Grass', 'Ice', 'Ground', 'Dark', 'Dragon']
  const available = new Set(props.options.map(skill => elementKey(skill.Element)).filter(Boolean))
  return preferredOrder.filter(element => available.has(element))
})

const filteredOptions = computed(() => {
  const tokens = searchQuery.value
    .normalize('NFKC')
    .trim()
    .toLocaleLowerCase()
    .split(/\s+/)
    .filter(Boolean)

  return props.options.filter(skill => {
    if (!isActive.value && passiveRatingFilter.value !== 'all'
      && String(skill.Rating) !== passiveRatingFilter.value) return false
    if (isActive.value && activeElementFilter.value !== 'all'
      && elementKey(skill.Element) !== activeElementFilter.value) return false
    if (!tokens.length) return true
    const fields = [
      skillName(skill),
      skillDescription(skill),
      skill.InternalName,
      skill.Element,
      skill.Power,
      skill.CT,
      skill.Rating
    ].filter(value => value !== undefined && value !== null)
      .map(value => String(value).normalize('NFKC').toLocaleLowerCase())

    return tokens.every(token => fields.some(field => field.includes(token)))
  })
})

const open = async () => {
  if (props.disabled || dialog.value?.open) return
  searchQuery.value = ''
  passiveRatingFilter.value = 'all'
  activeElementFilter.value = 'all'
  dialog.value?.showModal()
  await nextTick()
  searchInput.value?.focus()
  dialog.value?.querySelector('.pal-skill-option.is-selected, .pal-passive-option.is-selected')?.scrollIntoView({ block: 'center' })
}

const close = () => {
  dialog.value?.close()
}

const select = skill => {
  emit('update:modelValue', skill.InternalName)
  emit('select', skill)
  close()
}

const closeFromBackdrop = event => {
  if (event.target === dialog.value) close()
}

const focusOption = index => {
  const buttons = dialog.value?.querySelectorAll('.pal-skill-option, .pal-passive-option') || []
  if (!buttons.length) return
  const nextIndex = Math.min(Math.max(index, 0), buttons.length - 1)
  buttons[nextIndex]?.focus()
}
</script>

<template>
  <button
    :class="['pal-skill-trigger', { 'pal-skill-trigger--icon': iconOnly }]"
    type="button"
    :disabled="disabled"
    :aria-label="iconOnly ? placeholderText : undefined"
    :title="iconOnly ? placeholderText : undefined"
    aria-haspopup="dialog"
    @click="open"
  >
    <span v-if="!iconOnly" class="pal-skill-trigger__name">{{ placeholderText }}</span>
    <AppIcon :name="iconOnly ? 'plus' : 'chevron-down'" :size="16" />
  </button>

  <Teleport to="body">
    <dialog
      ref="dialog"
      class="pal-skill-dialog"
      :aria-label="titleText"
      @click="closeFromBackdrop"
    >
      <section class="pal-skill-dialog__surface">
        <header class="pal-skill-dialog__header">
          <div>
            <h2>{{ titleText }}</h2>
            <p aria-live="polite">{{ filteredOptions.length }} {{ resultsLabelText }}</p>
          </div>
          <button type="button" class="pal-skill-dialog__close" :aria-label="closeLabelText" :title="closeLabelText" @click="close">
            <AppIcon name="x" :size="19" />
          </button>
        </header>

        <label class="pal-skill-search">
          <AppIcon name="search" :size="18" />
          <input
            ref="searchInput"
            v-model="searchQuery"
            type="search"
            :aria-label="searchPlaceholderText"
            :placeholder="searchPlaceholderText"
            autocomplete="off"
            spellcheck="false"
            @keydown.down.prevent="focusOption(0)"
          >
        </label>

        <div
          v-if="isActive"
          class="pal-active-element-filters"
          :aria-label="palStore.getTranslatedText('Editor_Active_Filter_Label')"
        >
          <button
            type="button"
            class="pal-active-element-filter is-all"
            :class="{ 'is-active': activeElementFilter === 'all' }"
            @click="activeElementFilter = 'all'"
          >
            {{ palStore.getTranslatedText('Editor_Passive_Filter_All') }}
          </button>
          <button
            v-for="element in activeElements"
            :key="element"
            type="button"
            class="pal-active-element-filter"
            :class="{ 'is-active': activeElementFilter === element }"
            :title="element"
            :aria-label="element"
            @click="activeElementFilter = element"
          >
            <ElementIcon :element="element" :size="20" />
          </button>
        </div>

        <div
          v-if="!isActive"
          class="pal-passive-filters"
          :aria-label="palStore.getTranslatedText('Editor_Passive_Filter_Label')"
        >
          <button
            v-for="filter in passiveFilters"
            :key="filter.value"
            type="button"
            class="pal-passive-filter"
            :class="[filter.value === 'all' ? 'is-all' : passiveRatingClass(Number(filter.value)), { 'is-active': passiveRatingFilter === filter.value }]"
            @click="passiveRatingFilter = filter.value"
          >
            {{ filter.label }}
          </button>
        </div>

        <div v-if="isActive && filteredOptions.length" class="pal-skill-list" role="listbox" :aria-label="titleText">
          <button
            v-for="(skill, index) in filteredOptions"
            :key="skill.InternalName"
            type="button"
            class="pal-skill-option"
            :class="{ 'is-selected': skill.InternalName === modelValue }"
            role="option"
            :aria-selected="skill.InternalName === modelValue"
            :title="skill.InternalName"
            @click="select(skill)"
            @keydown.down.prevent="focusOption(index + 1)"
            @keydown.up.prevent="index === 0 ? searchInput?.focus() : focusOption(index - 1)"
          >
            <span class="pal-skill-option__element" aria-hidden="true">
              <ElementIcon v-if="skill.Element" :element="skill.Element" :size="24" />
            </span>
            <span class="pal-skill-option__content">
              <span class="pal-skill-option__heading">
                <strong>{{ skillName(skill) }}</strong>
                <span v-if="skill.IsUniqueSkill" class="pal-skill-tag">{{ uniqueLabelText }}</span>
                <span v-if="skill.HasSkillFruit" class="pal-skill-tag">{{ fruitLabelText }}</span>
              </span>
              <span v-if="showInternalName" class="pal-skill-option__internal">{{ skill.InternalName }}</span>
              <span class="pal-skill-option__meta">
                <span>{{ powerLabelText }} {{ skill.Power }}</span>
                <span>{{ cooldownLabelText }} {{ skill.CT }}</span>
              </span>
            </span>
            <AppIcon v-if="skill.InternalName === modelValue" class="pal-skill-option__check" name="check" :size="18" />
          </button>
        </div>

        <div v-else-if="filteredOptions.length" class="pal-passive-list" role="listbox" :aria-label="titleText">
          <div
            v-for="(skill, index) in filteredOptions"
            :key="skill.InternalName"
            class="pal-passive-option"
            :class="[{ 'is-selected': skill.InternalName === modelValue }, passiveRatingClass(skill.Rating)]"
            role="option"
            tabindex="0"
            :aria-selected="skill.InternalName === modelValue"
            :title="skill.InternalName"
            @click="select(skill)"
            @keydown.enter.prevent="select(skill)"
            @keydown.space.prevent="select(skill)"
            @keydown.down.prevent="focusOption(index + 1)"
            @keydown.up.prevent="index === 0 ? searchInput?.focus() : focusOption(index - 1)"
          >
            <article class="pal-passive-option__card">
              <header class="pal-passive-option__banner">
                <strong>{{ skillName(skill) }}</strong>
                <img :src="passiveRankSrc(skill.Rating)" alt="">
              </header>
              <p v-if="skillDescription(skill)" class="pal-passive-option__description">
                {{ skillDescription(skill) }}
              </p>
              <p v-if="showInternalName" class="pal-passive-option__internal">{{ skill.InternalName }}</p>
            </article>
            <AppIcon v-if="skill.InternalName === modelValue" class="pal-passive-option__check" name="check" :size="18" />
          </div>
        </div>

        <div v-else class="pal-skill-empty">
          <AppIcon name="search" :size="24" />
          <p>{{ emptyTextValue }}</p>
        </div>
      </section>
    </dialog>
  </Teleport>
</template>

<style scoped>
.pal-skill-trigger {
  display: flex;
  min-width: 220px;
  min-height: 34px;
  flex: 1 1 320px;
  align-items: center;
  gap: 7px;
  margin: 0;
  padding: 5px 9px;
  color: var(--ui-text);
  background: var(--ui-surface-raised);
  border: 1px solid var(--ui-border-strong);
  border-radius: var(--ui-radius-sm);
  text-align: left;
}

.pal-skill-trigger:hover:not(:disabled) {
  background: var(--ui-surface-hover);
  border-color: var(--ui-accent);
}

.pal-skill-trigger:focus-visible {
  outline: 2px solid var(--ui-accent);
  outline-offset: 2px;
}

.pal-skill-trigger:disabled { opacity: 0.5; }

.pal-skill-trigger__name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pal-skill-trigger > .app-icon {
  flex: 0 0 auto;
  margin-left: auto;
  color: var(--ui-text-muted);
}

.pal-skill-trigger.pal-skill-trigger--icon {
  width: 32px;
  min-width: 32px;
  min-height: 32px;
  flex: 0 0 32px;
  justify-content: center;
  padding: 0;
  border-color: var(--ui-border);
}

.pal-skill-trigger.pal-skill-trigger--icon > .app-icon {
  margin-left: 0;
  color: var(--ui-accent);
}

.pal-skill-dialog {
  width: min(860px, calc(100vw - 32px));
  max-width: none;
  height: min(720px, calc(100dvh - 48px));
  max-height: none;
  padding: 0;
  overflow: hidden;
  color: var(--ui-text);
  background: var(--ui-surface);
  border: 0;
  border-radius: var(--ui-radius-md);
  box-shadow: var(--ui-shadow-md);
}

.pal-skill-dialog::backdrop { background: oklch(0.08 0.018 252 / 0.76); }

.pal-skill-dialog__surface {
  display: grid;
  height: 100%;
  grid-template-rows: auto auto auto minmax(0, 1fr);
}

.pal-skill-dialog__header {
  display: flex;
  min-height: 72px;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 18px 12px;
  border-bottom: 1px solid var(--ui-border);
}

.pal-skill-dialog__header h2 {
  margin: 0;
  color: var(--ui-text);
  font-size: 17px;
  font-weight: 680;
  letter-spacing: -0.01em;
}

.pal-skill-dialog__header p {
  margin: 3px 0 0;
  color: var(--ui-text-muted);
  font-size: 12px;
}

.pal-skill-dialog__close {
  display: grid;
  width: 34px;
  height: 34px;
  flex: 0 0 auto;
  place-items: center;
  padding: 0;
  color: var(--ui-text-muted);
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--ui-radius-sm);
}

.pal-skill-dialog__close:hover {
  color: var(--ui-text);
  background: var(--ui-surface-hover);
  border-color: var(--ui-border);
}

.pal-skill-dialog__close:focus-visible,
.pal-skill-option:focus-visible {
  outline: 2px solid var(--ui-accent);
  outline-offset: 2px;
}

.pal-skill-search {
  display: flex;
  align-items: center;
  gap: 9px;
  margin: 14px 18px;
  padding: 0 11px;
  color: var(--ui-text-muted);
  background: var(--ui-surface-raised);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
}

.pal-skill-search:focus-within {
  color: var(--ui-accent);
  border-color: var(--ui-accent);
  box-shadow: 0 0 0 3px oklch(0.72 0.14 246 / 0.14);
}

.pal-skill-search input {
  width: 100%;
  min-width: 0;
  height: 40px;
  padding: 0;
  color: var(--ui-text);
  background: transparent;
  border: 0;
  outline: 0;
  font: inherit;
}

.pal-skill-search input::placeholder { color: var(--ui-text-muted); opacity: 1; }

.pal-skill-list {
  display: grid;
  min-height: 0;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  align-content: start;
  gap: 6px;
  overflow-y: auto;
  padding: 0 18px 18px;
}

.pal-passive-list {
  display: grid;
  min-height: 0;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  align-content: start;
  gap: 14px 12px;
  overflow-y: auto;
  padding: 0 18px 18px;
}

.pal-passive-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  padding: 0 18px 14px;
}

.pal-active-element-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  padding: 0 18px 14px;
}

.pal-active-element-filter {
  display: grid;
  width: 34px;
  height: 34px;
  place-items: center;
  padding: 0;
  color: var(--ui-text-secondary);
  background: rgb(17 17 17 / 72%);
  border: 1px solid var(--ui-border);
  border-radius: 8px;
}

.pal-active-element-filter:hover,
.pal-active-element-filter.is-active {
  background: var(--ui-surface-hover);
  border-color: var(--ui-accent);
}

.pal-active-element-filter.is-all {
  width: auto;
  min-width: 46px;
  padding: 0 10px;
  font-size: 12px;
  font-weight: 700;
}

.pal-passive-filter {
  min-width: 46px;
  height: 34px;
  padding: 0 11px;
  color: var(--filter-color, var(--ui-text-secondary));
  background: rgb(17 17 17 / 72%);
  border: 1px solid var(--ui-border);
  border-radius: 8px;
  font-size: 12px;
  font-weight: 700;
  transition: filter 140ms ease, border-color 140ms ease, background 140ms ease;
}

.pal-passive-filter:hover,
.pal-passive-filter.is-active {
  background: color-mix(in srgb, var(--filter-color, var(--ui-accent)) 18%, #111);
  border-color: var(--filter-color, var(--ui-accent));
  filter: brightness(1.12);
}

.pal-passive-filter.is-all {
  --filter-color: #fff;
  color: #fff;
}

.pal-passive-filter.is-rank-5 { --filter-color: #e0b0ff; }
.pal-passive-filter.is-rank-4 { --filter-color: #68ffd8; }
.pal-passive-filter.is-rank-3,
.pal-passive-filter.is-rank-2 { --filter-color: #d1d560; }
.pal-passive-filter.is-rank-1 { --filter-color: #fff; }
.pal-passive-filter.is-negative { --filter-color: #ff4646; }

.pal-skill-option {
  display: flex;
  min-width: 0;
  min-height: 82px;
  align-items: flex-start;
  gap: 10px;
  padding: 10px;
  color: var(--ui-text-secondary);
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--ui-radius-sm);
  text-align: left;
}

.pal-passive-option {
  position: relative;
  display: block;
  width: 100%;
  min-width: 0;
  height: auto;
  padding: 0;
  color: var(--ui-text-secondary);
  background: rgb(0 0 0 / 18%);
  border: 1px solid var(--ui-border);
  border-radius: 0;
  overflow: visible;
  cursor: pointer;
  text-align: left;
}

.pal-passive-option:hover {
  border-color: var(--ui-border-strong);
  filter: brightness(1.08);
}

.pal-passive-option.is-selected {
  border-color: var(--ui-accent);
  box-shadow: 0 0 0 1px var(--ui-accent);
}

.pal-passive-option:focus-visible {
  outline: 2px solid var(--ui-accent);
  outline-offset: 2px;
}

.pal-passive-option__check {
  position: absolute;
  top: 15px;
  right: 12px;
  margin: 0;
  color: var(--ui-text);
}

.pal-skill-option:hover {
  color: var(--ui-text);
  background: var(--ui-surface-hover);
  border-color: var(--ui-border);
}

.pal-skill-option.is-selected {
  color: var(--ui-text);
  background: var(--ui-accent-soft);
  border-color: var(--ui-accent);
}

.pal-skill-option__element {
  display: grid;
  width: 38px;
  height: 38px;
  flex: 0 0 auto;
  place-items: center;
  background: var(--ui-surface-raised);
  border-radius: 9px;
}

.pal-passive-option__card {
  display: block;
  width: 100%;
  min-width: 0;
  color: #fff;
  text-align: left;
}

.pal-passive-option__banner {
  display: flex;
  box-sizing: border-box;
  min-height: 48px;
  height: 48px;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 0 14px;
  overflow: hidden;
  background-color: rgb(0 0 0 / 0.2);
  border: 1px solid #495057;
  border-left-width: 5px;
}

.pal-passive-option__banner strong {
  min-width: 0;
  overflow: hidden;
  color: #fff;
  font-size: 14px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pal-passive-option__banner img {
  width: 20px;
  height: 20px;
  flex: 0 0 auto;
  object-fit: contain;
}

.pal-passive-option__description {
  display: block;
  margin: 0;
  padding: 8px 12px 10px;
  color: var(--ui-text-secondary);
  font-size: 12px;
  line-height: 1.45;
  white-space: pre-line;
}

.pal-passive-option.is-rank-5 .pal-passive-option__banner {
  background-image: linear-gradient(to right, rgb(89 187 101 / 24%), rgb(77 9 203 / 48%)), linear-gradient(rgb(17 17 17 / 53.3%), #111), url('/images/Pal/Texture/UI/Main_Menu/T_prt_pal_skill_base_02.webp');
  background-size: cover;
  background-position: center;
  border-color: #c084fc;
}

.pal-passive-option.is-rank-5 .pal-passive-option__banner strong { color: #e0b0ff; }

.pal-passive-option.is-rank-4 .pal-passive-option__banner {
  background-image: linear-gradient(to right, rgb(89 187 101 / 24%), rgb(69 67 209 / 48%)), linear-gradient(rgb(17 17 17 / 53.3%), #111), url('/images/Pal/Texture/UI/Main_Menu/T_prt_pal_skill_base_02.webp');
  background-size: cover;
  background-position: center;
  border-color: #68ffd8;
}

.pal-passive-option.is-rank-4 .pal-passive-option__banner strong { color: #68ffd8; }
.pal-passive-option.is-rank-4 .pal-passive-option__banner img { filter: sepia(1) saturate(100) hue-rotate(75deg); }

.pal-passive-option.is-rank-3 .pal-passive-option__banner {
  background-image: linear-gradient(rgb(255 221 0 / 12.5%), rgb(255 221 0 / 12.5%)), linear-gradient(rgb(17 17 17 / 53.3%), #111), url('/images/Pal/Texture/UI/Main_Menu/T_prt_pal_skill_base_02.webp');
  background-size: cover;
  background-position: center;
  border-color: #ffdd00;
}

.pal-passive-option.is-rank-3 .pal-passive-option__banner strong { color: #d1d560; }
.pal-passive-option.is-rank-3 .pal-passive-option__banner img { filter: sepia(1) saturate(100) hue-rotate(0deg); }

.pal-passive-option.is-negative .pal-passive-option__banner strong,
.pal-passive-option.is-negative .pal-passive-option__description,
.pal-passive-option.is-negative .pal-passive-option__internal {
  color: #ff4646;
}

.pal-passive-option.is-negative .pal-passive-option__banner img {
  transform: scaleY(-1);
  filter: invert(0.8) sepia(0.9) saturate(74.56) hue-rotate(359deg) brightness(0.95) contrast(1.15);
}

.pal-skill-rating {
  display: grid;
  width: 38px;
  height: 38px;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 9px;
  font-size: 12px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.pal-skill-rating--compact {
  width: 22px;
  height: 22px;
  border-radius: 6px;
  font-size: 10px;
}

.pal-skill-rating.is-exceptional { color: oklch(0.91 0.08 154); background: oklch(0.29 0.08 154); }
.pal-skill-rating.is-positive { color: oklch(0.93 0.08 92); background: oklch(0.3 0.07 92); }
.pal-skill-rating.is-standard { color: var(--ui-text); background: var(--ui-surface-raised); }
.pal-skill-rating.is-negative { color: oklch(0.88 0.09 24); background: var(--ui-danger-soft); }
.pal-skill-rating.is-neutral { color: var(--ui-text-muted); background: var(--ui-surface-raised); }

.pal-skill-option__content {
  display: flex;
  min-width: 0;
  flex: 1 1 auto;
  flex-direction: column;
  gap: 4px;
}

.pal-skill-option__heading {
  display: flex;
  min-width: 0;
  align-items: center;
  flex-wrap: wrap;
  gap: 5px;
}

.pal-skill-option__heading strong {
  min-width: 0;
  overflow: hidden;
  color: inherit;
  font-size: 13px;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pal-skill-tag {
  padding: 1px 5px;
  color: var(--ui-text-secondary);
  background: var(--ui-surface-raised);
  border: 1px solid var(--ui-border);
  border-radius: 5px;
  font-size: 10px;
  line-height: 1.4;
}

.pal-skill-option__description {
  display: -webkit-box;
  overflow: hidden;
  color: var(--ui-text-muted);
  font-size: 11.5px;
  line-height: 1.45;
  white-space: pre-line;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.pal-skill-option__internal {
  overflow: hidden;
  color: var(--ui-text-muted);
  font-size: 10.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pal-skill-option__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  color: var(--ui-text-secondary);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.pal-skill-option__check { flex: 0 0 auto; margin-top: 9px; color: var(--ui-accent); }

.pal-skill-empty {
  display: flex;
  min-height: 220px;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 9px;
  color: var(--ui-text-muted);
}

.pal-skill-empty p { margin: 0; }

@media (max-width: 680px) {
  .pal-skill-dialog {
    width: calc(100vw - 20px);
    height: calc(100dvh - 20px);
  }

  .pal-skill-list { grid-template-columns: minmax(0, 1fr); }
  .pal-passive-list { grid-template-columns: minmax(0, 1fr); }
  .pal-active-element-filters { padding-inline: 12px; }
  .pal-passive-filters { padding-inline: 12px; }
  .pal-skill-trigger { min-width: min(220px, calc(100vw - 110px)); }
}

@media (prefers-reduced-motion: reduce) {
  .pal-skill-trigger,
  .pal-skill-option,
  .pal-skill-dialog__close { transition: none; }
}
</style>
