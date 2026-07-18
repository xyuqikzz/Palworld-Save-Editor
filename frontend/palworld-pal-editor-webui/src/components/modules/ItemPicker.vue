<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { usePalEditorStore } from '@/stores/paleditor'
import AppIcon from '@/components/modules/AppIcon.vue'
import ItemIcon from '@/components/modules/ItemIcon.vue'

const palStore = usePalEditorStore()

const props = defineProps({
  modelValue: { type: String, default: '' },
  options: { type: Array, default: () => [] },
  selectedOption: { type: Object, default: null },
  disabled: { type: Boolean, default: false },
  triggerHidden: { type: Boolean, default: false },
  showQuantity: { type: Boolean, default: false },
  quantity: { type: Number, default: 1 },
  confirmDisabled: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'update:quantity', 'confirm'])

const PAGE_SIZE = 80
const dialog = ref(null)
const searchInput = ref(null)
const searchQuery = ref('')
const categoryFilter = ref('')
const dynamicKindFilter = ref('')
const rarityFilter = ref('')
const resultLimit = ref(PAGE_SIZE)

const categoryLabelKeys = Object.freeze({
  accessory: 'Inventory_Category_Accessory',
  body: 'Inventory_Category_Body',
  common: 'Inventory_Category_Common',
  food: 'Inventory_Category_Food',
  glider: 'Inventory_Category_Glider',
  head: 'Inventory_Category_Head',
  key_item: 'Inventory_Category_KeyItem',
  shield: 'Inventory_Category_Shield',
  sphere_module: 'Inventory_Category_SphereModule',
  unsupported: 'Inventory_Category_Unsupported',
  weapon: 'Inventory_Category_Weapon',
})
const dynamicKindLabelKeys = Object.freeze({
  none: 'Inventory_DynamicKind_Plain',
  weapon: 'Inventory_DynamicKind_Weapon',
  armor: 'Inventory_DynamicKind_Armor',
  accessory: 'Inventory_DynamicKind_Accessory',
  shield: 'Inventory_DynamicKind_Shield',
  glider: 'Inventory_DynamicKind_Glider',
  food: 'Inventory_DynamicKind_Food',
  egg: 'Inventory_DynamicKind_Egg',
})

const tr = (key, args = []) => palStore.getTranslatedText(key, args)
const categoryLabel = value => tr(
  categoryLabelKeys[value] || 'Inventory_Category_Unknown',
  categoryLabelKeys[value] ? [] : [String(value ?? '')],
)
const dynamicKindLabel = value => tr(
  dynamicKindLabelKeys[value] || 'Inventory_DynamicKind_Unknown',
  dynamicKindLabelKeys[value] ? [] : [String(value ?? '')],
)

const selectedItem = computed(() => (
  props.selectedOption || props.options.find(item => item.static_id === props.modelValue)
))
const quantityMax = computed(() => Math.max(1, Number(selectedItem.value?.max_stack) || 1))
const categories = computed(() => [...new Set(
  props.options.map(item => item.category).filter(Boolean),
)].sort((left, right) => categoryLabel(left).localeCompare(categoryLabel(right))))
const dynamicKinds = computed(() => [...new Set(
  props.options.map(item => item.dynamic_kind).filter(Boolean),
)].sort((left, right) => dynamicKindLabel(left).localeCompare(dynamicKindLabel(right))))
const rarities = computed(() => [...new Set(
  props.options.map(item => item.rarity).filter(value => value !== null && value !== undefined),
)].sort((left, right) => left - right))

const filteredOptions = computed(() => {
  const tokens = searchQuery.value
    .normalize('NFKC')
    .trim()
    .toLocaleLowerCase()
    .split(/\s+/)
    .filter(Boolean)

  return props.options.filter(item => {
    if (categoryFilter.value && item.category !== categoryFilter.value) return false
    if (dynamicKindFilter.value && item.dynamic_kind !== dynamicKindFilter.value) return false
    if (rarityFilter.value !== '' && String(item.rarity ?? '') !== rarityFilter.value) return false
    if (!tokens.length) return true

    const fields = [
      item.name,
      item.static_id,
      item.description,
      categoryLabel(item.category),
      dynamicKindLabel(item.dynamic_kind),
      item.rarity,
    ].filter(value => value !== null && value !== undefined)
      .map(value => String(value).normalize('NFKC').toLocaleLowerCase())

    return tokens.every(token => fields.some(field => field.includes(token)))
  })
})
const visibleOptions = computed(() => filteredOptions.value.slice(0, resultLimit.value))
const hasMore = computed(() => visibleOptions.value.length < filteredOptions.value.length)

watch([searchQuery, categoryFilter, dynamicKindFilter, rarityFilter], () => {
  resultLimit.value = PAGE_SIZE
})

const open = async () => {
  if (props.disabled || dialog.value?.open) return
  searchQuery.value = ''
  categoryFilter.value = ''
  dynamicKindFilter.value = ''
  rarityFilter.value = ''
  const selectedIndex = props.options.findIndex(item => item.static_id === props.modelValue)
  resultLimit.value = Math.max(PAGE_SIZE, selectedIndex + 1)
  dialog.value?.showModal()
  await nextTick()
  searchInput.value?.focus()
  dialog.value?.querySelector('.item-picker-option.is-selected')?.scrollIntoView({ block: 'center' })
}

const close = () => dialog.value?.close()
const select = item => {
  emit('update:modelValue', item.static_id)
  if (props.showQuantity) {
    emit('update:quantity', 1)
  } else {
    close()
  }
}
const setMaxQuantity = () => emit('update:quantity', quantityMax.value)
const confirmSelection = () => {
  if (!selectedItem.value) return
  emit('confirm', { item: selectedItem.value, quantity: Math.min(Math.max(1, Number(props.quantity) || 1), quantityMax.value) })
  close()
}
const closeFromBackdrop = event => {
  if (event.target === dialog.value) close()
}
const focusOption = index => {
  const buttons = dialog.value?.querySelectorAll('.item-picker-option') || []
  if (!buttons.length) return
  const nextIndex = Math.min(Math.max(index, 0), buttons.length - 1)
  buttons[nextIndex]?.focus()
}
defineExpose({ open, close })
</script>

<template>
  <button
    v-if="!triggerHidden"
    type="button"
    class="item-picker-trigger"
    :disabled="disabled"
    aria-haspopup="dialog"
    @click="open"
  >
    <ItemIcon
      v-if="selectedItem"
      :icon="selectedItem.icon"
      :name="selectedItem.name"
      :size="40"
    />
    <span v-else class="item-picker-trigger__empty">
      <AppIcon name="search" :size="18" />
    </span>
    <span class="item-picker-trigger__copy">
      <strong>{{ selectedItem?.name || tr('Inventory_SelectItem') }}</strong>
      <small v-if="selectedItem">{{ selectedItem.static_id }}</small>
      <small v-if="selectedItem" class="item-picker-trigger__meta">
        {{ categoryLabel(selectedItem.category) }} · {{ dynamicKindLabel(selectedItem.dynamic_kind) }}
      </small>
    </span>
    <span class="item-picker-trigger__action">
      {{ tr('Inventory_ItemPicker_Change') }}
      <AppIcon name="chevron-down" :size="16" />
    </span>
  </button>

  <Teleport to="body">
    <dialog
      ref="dialog"
      class="item-picker-dialog"
      :aria-label="tr('Inventory_ItemPicker_Title')"
      @click="closeFromBackdrop"
    >
      <section class="item-picker-dialog__surface">
        <header class="item-picker-dialog__header">
          <div>
            <p>{{ tr('Inventory_ItemPicker_Eyebrow') }}</p>
            <h2>{{ tr('Inventory_ItemPicker_Title') }}</h2>
          </div>
          <button type="button" class="item-picker-dialog__close" :title="tr('Common_Close')" :aria-label="tr('Common_Close')" @click="close">
            <AppIcon name="x" :size="19" />
          </button>
        </header>

        <div class="item-picker-tools">
          <label class="item-picker-search">
            <AppIcon name="search" :size="18" />
            <input
              ref="searchInput"
              v-model="searchQuery"
              type="search"
              :placeholder="tr('Inventory_ItemPicker_Search')"
              :aria-label="tr('Inventory_ItemPicker_Search')"
              autocomplete="off"
              spellcheck="false"
              @keydown.down.prevent="focusOption(0)"
            >
          </label>
          <div class="item-picker-filters">
            <select v-model="categoryFilter" :aria-label="tr('Inventory_ItemPicker_CategoryFilter')">
              <option value="">{{ tr('Inventory_ItemPicker_AllCategories') }}</option>
              <option v-for="category in categories" :key="category" :value="category">{{ categoryLabel(category) }}</option>
            </select>
            <select v-model="dynamicKindFilter" :aria-label="tr('Inventory_ItemPicker_TypeFilter')">
              <option value="">{{ tr('Inventory_ItemPicker_AllTypes') }}</option>
              <option v-for="kind in dynamicKinds" :key="kind" :value="kind">{{ dynamicKindLabel(kind) }}</option>
            </select>
            <select v-model="rarityFilter" :aria-label="tr('Inventory_ItemPicker_RarityFilter')">
              <option value="">{{ tr('Inventory_ItemPicker_AllRarities') }}</option>
              <option v-for="rarity in rarities" :key="rarity" :value="String(rarity)">
                {{ tr('Inventory_ItemPicker_RarityValue', [rarity]) }}
              </option>
            </select>
          </div>
          <p class="item-picker-result-count" aria-live="polite">
            {{ tr('Inventory_ItemPicker_ResultCount', [filteredOptions.length, options.length]) }}
          </p>
        </div>

        <div v-if="visibleOptions.length" class="item-picker-list" role="listbox" :aria-label="tr('Inventory_ItemPicker_Title')">
          <button
            v-for="(item, index) in visibleOptions"
            :key="item.static_id"
            type="button"
            class="item-picker-option"
            :class="{ 'is-selected': item.static_id === modelValue }"
            role="option"
            :aria-selected="item.static_id === modelValue"
            @click="select(item)"
            @keydown.down.prevent="focusOption(index + 1)"
            @keydown.up.prevent="index === 0 ? searchInput?.focus() : focusOption(index - 1)"
          >
            <ItemIcon :icon="item.icon" :name="item.name" :size="52" />
            <span class="item-picker-option__copy">
              <span class="item-picker-option__heading">
                <strong>{{ item.name || item.static_id }}</strong>
                <span v-if="item.rarity !== null && item.rarity !== undefined" class="item-picker-badge">
                  {{ tr('Inventory_ItemPicker_RarityValue', [item.rarity]) }}
                </span>
              </span>
              <code>{{ item.static_id }}</code>
              <span class="item-picker-option__description">
                {{ item.description || tr('Inventory_ItemPicker_NoDescription') }}
              </span>
              <span class="item-picker-option__meta">
                <span>{{ categoryLabel(item.category) }}</span>
                <span>{{ dynamicKindLabel(item.dynamic_kind) }}</span>
                <span>{{ tr('Inventory_ItemPicker_MaxStack', [item.max_stack ?? '—']) }}</span>
              </span>
            </span>
            <AppIcon v-if="item.static_id === modelValue" class="item-picker-option__check" name="check" :size="18" />
          </button>
          <button v-if="hasMore" type="button" class="item-picker-load-more" @click="resultLimit += PAGE_SIZE">
            {{ tr('Inventory_ItemPicker_LoadMore', [filteredOptions.length - visibleOptions.length]) }}
          </button>
        </div>

        <div v-else class="item-picker-empty">
          <AppIcon name="search" :size="26" />
          <strong>{{ tr('Inventory_ItemPicker_Empty') }}</strong>
          <span>{{ tr('Inventory_ItemPicker_EmptyHint') }}</span>
        </div>

        <footer v-if="showQuantity" class="item-picker-dialog__footer">
          <div class="item-picker-quantity" :class="{ 'is-disabled': !selectedItem }">
            <div class="item-picker-quantity__label">
              <span>{{ tr('Inventory_Count') }}</span>
              <small>{{ tr('Inventory_ItemPicker_MaxStack', [selectedItem?.max_stack ?? 1]) }}</small>
            </div>
            <div class="item-picker-quantity__control">
              <input
                :value="quantity"
                type="number"
                min="1"
                :max="quantityMax"
                step="1"
                :disabled="!selectedItem"
                :aria-label="tr('Inventory_Count')"
                @input="emit('update:quantity', Math.min(Math.max(1, Number($event.target.value) || 1), quantityMax))"
              >
              <button type="button" class="item-picker-max" :disabled="!selectedItem" @click="setMaxQuantity">{{ tr('Inventory_Max') }}</button>
            </div>
          </div>
          <slot name="details" :item="selectedItem" />
          <div class="item-picker-dialog__actions">
            <button type="button" class="item-picker-cancel" @click="close">{{ tr('Common_Close') }}</button>
            <button type="button" class="item-picker-confirm" :disabled="!selectedItem || confirmDisabled" @click="confirmSelection">{{ tr('Inventory_Add') }}</button>
          </div>
        </footer>
      </section>
    </dialog>
  </Teleport>
</template>

<style scoped>
.item-picker-trigger {
  display: grid;
  width: 100%;
  min-width: 0;
  min-height: 58px;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 7px 10px 7px 7px;
  color: var(--ui-text);
  background: var(--ui-surface-raised);
  border: 1px solid var(--ui-border-strong);
  border-radius: var(--ui-radius-sm);
  text-align: left;
}

.item-picker-trigger:hover:not(:disabled) {
  background: var(--ui-surface-hover);
  border-color: var(--ui-accent);
}

.item-picker-trigger__empty {
  display: grid;
  width: 40px;
  height: 40px;
  place-content: center;
  color: var(--ui-text-muted);
  background: var(--ui-surface);
  border-radius: 8px;
}

.item-picker-trigger__copy { display: grid; min-width: 0; gap: 1px; }
.item-picker-trigger__copy strong,
.item-picker-trigger__copy small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.item-picker-trigger__copy strong { font-size: 13px; font-weight: 650; }
.item-picker-trigger__copy small { color: var(--ui-text-muted); font-size: 10.5px; }
.item-picker-trigger__meta { color: var(--ui-text-secondary) !important; }
.item-picker-trigger__action { display: flex; align-items: center; gap: 5px; color: var(--ui-accent); font-size: 11px; font-weight: 650; }

.item-picker-dialog {
  width: min(1040px, calc(100vw - 32px));
  max-width: none;
  height: min(780px, calc(100dvh - 40px));
  max-height: none;
  padding: 0;
  overflow: hidden;
  color: var(--ui-text);
  background: var(--ui-surface);
  border: 1px solid var(--ui-border-strong);
  border-radius: var(--ui-radius-md);
  box-shadow: var(--ui-shadow-md);
}

.item-picker-dialog::backdrop { background: oklch(0.08 0.018 252 / 0.8); }
.item-picker-dialog__surface { display: grid; height: 100%; grid-template-rows: auto auto minmax(0, 1fr) auto; }
.item-picker-dialog__header { display: flex; min-height: 78px; align-items: center; justify-content: space-between; gap: 16px; padding: 15px 18px; border-bottom: 1px solid var(--ui-border); }
.item-picker-dialog__header p { margin: 0 0 2px; color: var(--ui-accent); font-size: 10px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
.item-picker-dialog__header h2 { margin: 0; font-size: 18px; font-weight: 680; letter-spacing: -.01em; }
.item-picker-dialog__close { display: grid; width: 36px; height: 36px; place-content: center; padding: 0; color: var(--ui-text-muted); background: transparent; border: 1px solid transparent; border-radius: var(--ui-radius-sm); }
.item-picker-dialog__close:hover { color: var(--ui-text); background: var(--ui-surface-hover); border-color: var(--ui-border); }

.item-picker-tools { display: grid; grid-template-columns: minmax(260px, 1fr) auto; gap: 10px 14px; padding: 14px 18px; border-bottom: 1px solid var(--ui-border); }
.item-picker-search { display: flex; min-width: 0; align-items: center; gap: 9px; padding: 0 11px; color: var(--ui-text-muted); background: var(--ui-surface-raised); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-sm); }
.item-picker-search:focus-within { color: var(--ui-accent); border-color: var(--ui-accent); box-shadow: 0 0 0 3px oklch(0.72 0.14 246 / 0.14); }
.item-picker-search input { width: 100%; min-width: 0; height: 40px; padding: 0; color: var(--ui-text); background: transparent; border: 0; outline: 0; }
.item-picker-search input::placeholder { color: var(--ui-text-muted); }
.item-picker-filters { display: flex; gap: 6px; }
.item-picker-filters select { min-width: 130px; height: 40px; padding: 0 30px 0 9px; color: var(--ui-text-secondary); background: var(--ui-surface-raised); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-sm); }
.item-picker-result-count { grid-column: 1 / -1; margin: -2px 0 0; color: var(--ui-text-muted); font-size: 11px; }

.item-picker-list { display: grid; min-height: 0; grid-template-columns: repeat(2, minmax(0, 1fr)); align-content: start; gap: 7px; overflow-y: auto; padding: 14px 18px 18px; }
.item-picker-option { display: grid; min-width: 0; min-height: 112px; grid-template-columns: auto minmax(0, 1fr) auto; align-items: start; gap: 11px; padding: 11px; color: var(--ui-text-secondary); background: transparent; border: 1px solid var(--ui-border); border-radius: var(--ui-radius-sm); text-align: left; }
.item-picker-option:hover { color: var(--ui-text); background: var(--ui-surface-hover); border-color: var(--ui-border-strong); }
.item-picker-option.is-selected { color: var(--ui-text); background: var(--ui-accent-soft); border-color: var(--ui-accent); }
.item-picker-option__copy { display: grid; min-width: 0; gap: 3px; }
.item-picker-option__heading { display: flex; min-width: 0; align-items: center; gap: 6px; }
.item-picker-option__heading strong { min-width: 0; overflow: hidden; font-size: 13px; font-weight: 650; text-overflow: ellipsis; white-space: nowrap; }
.item-picker-option code { overflow: hidden; color: var(--ui-text-muted); font: 10.5px/1.4 ui-monospace, "Cascadia Code", Consolas, monospace; text-overflow: ellipsis; white-space: nowrap; }
.item-picker-option__description { display: -webkit-box; overflow: hidden; color: var(--ui-text-muted); font-size: 11px; line-height: 1.4; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.item-picker-option__meta { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 2px; color: var(--ui-text-secondary); font-size: 10px; }
.item-picker-option__meta span,
.item-picker-badge { padding: 1px 5px; background: var(--ui-surface-raised); border: 1px solid var(--ui-border); border-radius: 5px; }
.item-picker-badge { flex: 0 0 auto; color: var(--ui-accent); font-size: 10px; }
.item-picker-option__check { margin-top: 17px; color: var(--ui-accent); }
.item-picker-load-more { grid-column: 1 / -1; min-height: 38px; color: var(--ui-accent); background: var(--ui-accent-soft); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-sm); }
.item-picker-empty { display: flex; min-height: 260px; align-items: center; justify-content: center; flex-direction: column; gap: 6px; color: var(--ui-text-muted); }
.item-picker-empty strong { color: var(--ui-text-secondary); font-size: 13px; }
.item-picker-empty span { font-size: 11px; }
.item-picker-dialog__footer { display: grid; grid-template-columns: minmax(220px, 1fr) minmax(0, 1.7fr) auto; align-items: end; gap: 12px; padding: 12px 18px 16px; border-top: 1px solid var(--ui-border); background: var(--ui-surface-raised); }
.item-picker-quantity { display: grid; gap: 5px; }
.item-picker-quantity__label { display: flex; align-items: baseline; justify-content: space-between; color: var(--ui-text-secondary); font-size: 11px; }
.item-picker-quantity__label small { color: var(--ui-text-muted); font-size: 10px; }
.item-picker-quantity__control { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 6px; }
.item-picker-quantity input { min-height: 38px; padding: 0 10px; color: var(--ui-text); background: var(--ui-canvas); border: 1px solid var(--ui-border-strong); border-radius: var(--ui-radius-sm); font-weight: 700; }
.item-picker-max,
.item-picker-cancel,
.item-picker-confirm { min-height: 38px; padding: 0 14px; border: 1px solid var(--ui-border); border-radius: var(--ui-radius-sm); color: var(--ui-text-secondary); background: var(--ui-surface); font-size: 11px; font-weight: 700; }
.item-picker-max { color: var(--ui-accent); background: var(--ui-accent-soft); border-color: transparent; }
.item-picker-dialog__actions { display: flex; gap: 6px; }
.item-picker-confirm { color: white; background: var(--ui-accent-strong); border-color: transparent; }
.item-picker-cancel:hover:not(:disabled),
.item-picker-max:hover:not(:disabled),
.item-picker-confirm:hover:not(:disabled) { filter: brightness(1.08); }
.item-picker-quantity.is-disabled { opacity: .55; }

@media (max-width: 760px) {
  .item-picker-dialog { width: calc(100vw - 20px); height: calc(100dvh - 20px); }
  .item-picker-tools { grid-template-columns: minmax(0, 1fr); }
  .item-picker-filters { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .item-picker-filters select { min-width: 0; }
  .item-picker-list { grid-template-columns: minmax(0, 1fr); }
  .item-picker-trigger__action { font-size: 0; }
  .item-picker-dialog__footer { grid-template-columns: minmax(0, 1fr); }
  .item-picker-dialog__actions { justify-content: stretch; }
  .item-picker-dialog__actions button { flex: 1; }
}

@media (prefers-reduced-motion: reduce) {
  .item-picker-trigger,
  .item-picker-option,
  .item-picker-dialog__close { transition: none; }
}
</style>
