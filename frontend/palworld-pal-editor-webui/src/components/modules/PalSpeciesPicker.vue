<script setup>
import { computed, nextTick, ref } from 'vue'
import AppIcon from '@/components/modules/AppIcon.vue'
import ElementIcon from '@/components/modules/ElementIcon.vue'
import { usePalEditorStore } from '@/stores/paleditor'
import {
  availablePalElements,
  elementTranslationKey,
  filterSpeciesOptions,
} from '@/components/modules/pal-species-filter'

const palStore = usePalEditorStore()

const props = defineProps({
  modelValue: { type: String, default: '' },
  options: { type: Array, default: () => [] },
  selectedOption: { type: Object, default: null },
  disabled: { type: Boolean, default: false },
  showSelectedIcon: { type: Boolean, default: true },
  showInternalName: { type: Boolean, default: false },
  placeholder: { type: String, default: '' },
  title: { type: String, default: '' },
  searchPlaceholder: { type: String, default: '' },
  resultsLabel: { type: String, default: '' },
  emptyText: { type: String, default: '' },
  closeLabel: { type: String, default: '' },
  triggerless: { type: Boolean, default: false }
})

const emit = defineEmits(['update:modelValue', 'select'])

const dialog = ref(null)
const searchInput = ref(null)
const searchQuery = ref('')
const activeCategory = ref('pal')
const activeElementFilter = ref('all')

const formatPalNumber = value => {
  if (!value) return ''
  const match = String(value).match(/^(\d+)([A-Za-z]*)$/)
  if (!match) return String(value)
  return `${match[1].padStart(3, '0')}${match[2]}`
}

const iconKey = pal => {
  if (pal?.IsHuman) return pal.HasIcon ? pal.InternalName : 'Human'

  let key = pal?.InternalName || ''
  if (/^(?:BOSS|Boss)_/.test(key)) return key.replace(/^(?:BOSS|Boss)_/, '')
  if (key.endsWith('_Oilrig')) return key.replace(/_Oilrig$/, '')

  const specialVariant = key.match(/^(?:RAID|PREDATOR|SUMMON)_(.+?)(?:_\d+.*)?$/)
  if (specialVariant) return specialVariant[1]

  const tower = key.match(/^(GYM_[^_]+)/)
  return tower?.[1] || key
}

const selectedPal = computed(() => (
  props.selectedOption || props.options.find(pal => pal.InternalName === props.modelValue)
))
const placeholderText = computed(() => props.placeholder || palStore.getTranslatedText('Editor_Species_Picker_Title'))
const titleText = computed(() => props.title || palStore.getTranslatedText('Editor_Species_Picker_Title'))
const searchPlaceholderText = computed(() => props.searchPlaceholder || palStore.getTranslatedText('Editor_Species_Search_Placeholder'))
const resultsLabelText = computed(() => props.resultsLabel || palStore.getTranslatedText('Editor_Species_Results_Label'))
const emptyTextValue = computed(() => props.emptyText || palStore.getTranslatedText('Editor_Species_Empty'))
const closeLabelText = computed(() => props.closeLabel || palStore.getTranslatedText('Common_Close'))
const hasPalOptions = computed(() => props.options.some(option => !option.IsHuman))
const hasNpcOptions = computed(() => props.options.some(option => option.IsHuman))
const showCategoryTabs = computed(() => hasPalOptions.value && hasNpcOptions.value)
const palElements = computed(() => availablePalElements(props.options))
const elementLabel = element => palStore.getTranslatedText(elementTranslationKey(element), [element])

const filteredOptions = computed(() => filterSpeciesOptions(props.options, {
  category: activeCategory.value,
  element: activeElementFilter.value,
  query: searchQuery.value,
}))

const setCategory = category => {
  activeCategory.value = category
  activeElementFilter.value = 'all'
}

const open = async () => {
  if (props.disabled || dialog.value?.open) return
  searchQuery.value = ''
  activeElementFilter.value = 'all'
  activeCategory.value = selectedPal.value?.IsHuman && hasNpcOptions.value
    ? 'npc'
    : hasPalOptions.value ? 'pal' : 'npc'
  dialog.value?.showModal()
  await nextTick()
  searchInput.value?.focus()
  dialog.value?.querySelector('.pal-species-option.is-selected')?.scrollIntoView({ block: 'center' })
}

defineExpose({ open })

const close = () => {
  dialog.value?.close()
}

const select = pal => {
  emit('update:modelValue', pal.InternalName)
  emit('select', pal.InternalName)
  close()
}

const closeFromBackdrop = event => {
  if (event.target === dialog.value) close()
}

const focusOption = index => {
  const buttons = dialog.value?.querySelectorAll('.pal-species-option') || []
  if (!buttons.length) return
  const nextIndex = Math.min(Math.max(index, 0), buttons.length - 1)
  buttons[nextIndex]?.focus()
}
</script>

<template>
  <button
    v-if="!triggerless"
    class="pal-species-trigger"
    type="button"
    :disabled="disabled"
    aria-haspopup="dialog"
    @click="open"
  >
    <img
      v-if="showSelectedIcon && selectedPal"
      class="pal-species-trigger__portrait"
      :src="`/image/pals/${iconKey(selectedPal)}`"
      alt=""
      draggable="false"
    >
    <span class="pal-species-trigger__content">
      <span v-if="formatPalNumber(selectedPal?.SortingKey)" class="pal-species-trigger__number">
        #{{ formatPalNumber(selectedPal.SortingKey) }}
      </span>
      <span class="pal-species-trigger__name">
        {{ selectedPal?.I18n || modelValue || placeholderText }}
      </span>
    </span>
    <span v-if="selectedPal?.Elements?.length" class="pal-species-trigger__elements" aria-hidden="true">
      <ElementIcon
        v-for="element in selectedPal.Elements"
        :key="element"
        :element="element"
        :size="18"
      />
    </span>
    <AppIcon name="chevron-down" :size="16" />
  </button>

  <Teleport to="body">
    <dialog
      ref="dialog"
      class="pal-species-dialog"
      :aria-label="titleText"
      @click="closeFromBackdrop"
    >
      <section class="pal-species-dialog__surface">
        <header class="pal-species-dialog__header">
          <div>
            <h2>{{ titleText }}</h2>
            <p>{{ filteredOptions.length }} {{ resultsLabelText }}</p>
          </div>
          <button type="button" class="pal-species-dialog__close" :aria-label="closeLabelText" :title="closeLabelText" @click="close">
            <AppIcon name="x" :size="19" />
          </button>
        </header>

        <nav
          v-if="showCategoryTabs"
          class="pal-species-tabs"
          role="tablist"
          :aria-label="palStore.getTranslatedText('PalSpeciesPicker_CategoryLabel')"
        >
          <button
            type="button"
            role="tab"
            :class="{ 'is-active': activeCategory === 'pal' }"
            :aria-selected="activeCategory === 'pal'"
            @click="setCategory('pal')"
          >
            {{ palStore.getTranslatedText('PalSpeciesPicker_Pals') }}
          </button>
          <button
            type="button"
            role="tab"
            :class="{ 'is-active': activeCategory === 'npc' }"
            :aria-selected="activeCategory === 'npc'"
            @click="setCategory('npc')"
          >
            {{ palStore.getTranslatedText('PalSpeciesPicker_Npcs') }}
          </button>
        </nav>

        <label class="pal-species-search">
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
          v-if="activeCategory === 'pal' && palElements.length"
          class="pal-species-element-filters"
          role="group"
          :aria-label="palStore.getTranslatedText('PalSpeciesPicker_ElementFilterLabel')"
        >
          <button
            type="button"
            class="is-all"
            :class="{ 'is-active': activeElementFilter === 'all' }"
            @click="activeElementFilter = 'all'"
          >
            {{ palStore.getTranslatedText('PalList_AnyElement') }}
          </button>
          <button
            v-for="element in palElements"
            :key="element"
            type="button"
            :class="{ 'is-active': activeElementFilter === element }"
            :title="elementLabel(element)"
            :aria-label="elementLabel(element)"
            @click="activeElementFilter = element"
          >
            <ElementIcon :element="element" :size="20" />
          </button>
        </div>

        <div v-if="filteredOptions.length" class="pal-species-list" role="listbox" :aria-label="titleText">
          <button
            v-for="(pal, index) in filteredOptions"
            :key="pal.InternalName"
            type="button"
            class="pal-species-option"
            :class="{ 'is-selected': pal.InternalName === modelValue }"
            role="option"
            :aria-selected="pal.InternalName === modelValue"
            :title="pal.InternalName"
            @click="select(pal)"
            @keydown.down.prevent="focusOption(index + 1)"
            @keydown.up.prevent="index === 0 ? searchInput?.focus() : focusOption(index - 1)"
          >
            <img
              class="pal-species-option__portrait"
              :src="`/image/pals/${iconKey(pal)}`"
              alt=""
              loading="lazy"
              draggable="false"
            >
            <span class="pal-species-option__content">
              <span class="pal-species-option__heading">
                <span v-if="formatPalNumber(pal.SortingKey)" class="pal-species-option__number">
                  #{{ formatPalNumber(pal.SortingKey) }}
                </span>
                <strong>{{ pal.I18n || pal.InternalName }}</strong>
              </span>
              <span v-if="showInternalName || pal.IsHuman" class="pal-species-option__internal">{{ pal.InternalName }}</span>
            </span>
            <span class="pal-species-option__elements" aria-hidden="true">
              <ElementIcon
                v-for="element in pal.Elements || []"
                :key="element"
                :element="element"
                :size="20"
              />
            </span>
            <AppIcon v-if="pal.InternalName === modelValue" class="pal-species-option__check" name="check" :size="18" />
          </button>
        </div>

        <div v-else class="pal-species-empty">
          <AppIcon name="search" :size="24" />
          <p>{{ emptyTextValue }}</p>
        </div>
      </section>
    </dialog>
  </Teleport>
</template>

<style scoped>
.pal-species-trigger {
  display: flex;
  width: 100%;
  min-width: 0;
  min-height: 42px;
  align-items: center;
  gap: 8px;
  margin: 0;
  padding: 5px 9px 5px 6px;
  color: var(--ui-text);
  background: var(--ui-surface-raised);
  border: 1px solid var(--ui-border-strong);
  border-radius: var(--ui-radius-sm);
  text-align: left;
  transition: color 160ms ease, background-color 160ms ease, border-color 160ms ease;
}

.pal-species-trigger:hover:not(:disabled) {
  background: var(--ui-surface-hover);
  border-color: var(--ui-accent);
}

.pal-species-trigger:focus-visible {
  outline: 2px solid var(--ui-accent);
  outline-offset: 2px;
}

.pal-species-trigger:disabled { opacity: 0.5; }

.pal-species-trigger__portrait {
  width: 30px;
  height: 30px;
  flex: 0 0 auto;
  border-radius: 7px;
  object-fit: contain;
}

.pal-species-trigger__content {
  display: flex;
  min-width: 0;
  align-items: baseline;
  gap: 7px;
}

.pal-species-trigger__number,
.pal-species-option__number {
  flex: 0 0 auto;
  color: var(--ui-text-muted);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.pal-species-trigger__name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pal-species-trigger__elements,
.pal-species-option__elements {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 3px;
}

.pal-species-trigger__elements { margin-left: auto; }
.pal-species-trigger > .app-icon { flex: 0 0 auto; color: var(--ui-text-muted); }

.pal-species-dialog {
  width: min(820px, calc(100vw - 32px));
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

.pal-species-dialog::backdrop { background: oklch(0.08 0.018 252 / 0.76); }

.pal-species-dialog__surface {
  display: grid;
  height: 100%;
  grid-template-rows: auto auto auto auto minmax(0, 1fr);
}

.pal-species-dialog__header {
  display: flex;
  grid-row: 1;
  min-height: 72px;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 18px 12px;
  border-bottom: 1px solid var(--ui-border);
}

.pal-species-tabs {
  display: flex;
  grid-row: 2;
  gap: 4px;
  padding: 10px 18px 0;
  border-bottom: 1px solid var(--ui-border);
}

.pal-species-tabs button {
  min-width: 92px;
  padding: 9px 14px 10px;
  color: var(--ui-text-muted);
  background: transparent;
  border: 0;
  border-bottom: 2px solid transparent;
  font-size: 13px;
  font-weight: 650;
}

.pal-species-tabs button:hover,
.pal-species-tabs button.is-active {
  color: var(--ui-text);
  border-bottom-color: var(--ui-accent);
}

.pal-species-dialog__header h2 {
  margin: 0;
  color: var(--ui-text);
  font-size: 17px;
  font-weight: 680;
  letter-spacing: -0.01em;
}

.pal-species-dialog__header p {
  margin: 3px 0 0;
  color: var(--ui-text-muted);
  font-size: 12px;
}

.pal-species-dialog__close {
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
  transition: color 160ms ease, background-color 160ms ease, border-color 160ms ease;
}

.pal-species-dialog__close:hover {
  color: var(--ui-text);
  background: var(--ui-surface-hover);
  border-color: var(--ui-border);
}

.pal-species-dialog__close:focus-visible,
.pal-species-option:focus-visible {
  outline: 2px solid var(--ui-accent);
  outline-offset: 2px;
}

.pal-species-search {
  display: flex;
  grid-row: 3;
  align-items: center;
  gap: 9px;
  margin: 14px 18px;
  padding: 0 11px;
  color: var(--ui-text-muted);
  background: var(--ui-surface-raised);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
}

.pal-species-search:focus-within {
  color: var(--ui-accent);
  border-color: var(--ui-accent);
  box-shadow: 0 0 0 3px oklch(0.72 0.14 246 / 0.14);
}

.pal-species-search input {
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

.pal-species-search input::placeholder { color: var(--ui-text-muted); opacity: 1; }

.pal-species-list {
  display: grid;
  grid-row: 5;
  min-height: 0;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  align-content: start;
  gap: 6px;
  overflow-y: auto;
  padding: 0 18px 18px;
}

.pal-species-element-filters {
  display: flex;
  grid-row: 4;
  flex-wrap: wrap;
  gap: 7px;
  padding: 0 18px 14px;
}

.pal-species-element-filters button {
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

.pal-species-element-filters button:hover,
.pal-species-element-filters button.is-active {
  background: var(--ui-surface-hover);
  border-color: var(--ui-accent);
}

.pal-species-element-filters button.is-all {
  width: auto;
  min-width: 72px;
  padding: 0 10px;
  font-size: 12px;
  font-weight: 700;
}

.pal-species-option {
  display: flex;
  min-width: 0;
  min-height: 64px;
  align-items: center;
  gap: 10px;
  padding: 8px;
  color: var(--ui-text-secondary);
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--ui-radius-sm);
  text-align: left;
  transition: color 160ms ease, background-color 160ms ease, border-color 160ms ease;
}

.pal-species-option:hover {
  color: var(--ui-text);
  background: var(--ui-surface-hover);
  border-color: var(--ui-border);
}

.pal-species-option.is-selected {
  color: var(--ui-text);
  background: var(--ui-accent-soft);
  border-color: var(--ui-accent);
}

.pal-species-option__portrait {
  width: 46px;
  height: 46px;
  flex: 0 0 auto;
  border-radius: 9px;
  object-fit: contain;
}

.pal-species-option__content {
  display: flex;
  min-width: 0;
  flex: 1 1 auto;
  flex-direction: column;
  gap: 3px;
}

.pal-species-option__heading {
  display: flex;
  min-width: 0;
  align-items: baseline;
  gap: 7px;
}

.pal-species-option__heading strong {
  min-width: 0;
  overflow: hidden;
  color: inherit;
  font-size: 13px;
  font-weight: 620;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pal-species-option__internal {
  overflow: hidden;
  color: var(--ui-text-muted);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pal-species-option__check { flex: 0 0 auto; color: var(--ui-accent); }

.pal-species-empty {
  display: flex;
  grid-row: 5;
  min-height: 220px;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 9px;
  color: var(--ui-text-muted);
}

.pal-species-empty p { margin: 0; }

@media (max-width: 680px) {
  .pal-species-dialog {
    width: calc(100vw - 20px);
    height: calc(100dvh - 20px);
  }

  .pal-species-list { grid-template-columns: minmax(0, 1fr); }
  .pal-species-trigger__elements { display: none; }
}

@media (prefers-reduced-motion: reduce) {
  .pal-species-trigger,
  .pal-species-option,
  .pal-species-dialog__close { transition: none; }
}
</style>
