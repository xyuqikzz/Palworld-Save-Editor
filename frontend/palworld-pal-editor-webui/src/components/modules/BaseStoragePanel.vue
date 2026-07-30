<script setup>
import AppIcon from '@/components/modules/AppIcon.vue'
import ItemIcon from '@/components/modules/ItemIcon.vue'
import ItemPicker from '@/components/modules/ItemPicker.vue'
import PalSpeciesPicker from '@/components/modules/PalSpeciesPicker.vue'
import { usePalEditorStore } from '@/stores/paleditor'
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from 'vue'

const props = defineProps({
  guildId: { type: String, required: true },
  baseId: { type: String, required: true },
})

const palStore = usePalEditorStore()
const picker = ref(null)
const pendingContainer = ref(null)
const pendingSlot = ref(null)
const pendingMode = ref('empty_only')
const selectedStaticId = ref('')
const addCount = ref(1)
const dynamicRecordStaticId = ref('')
const dynamicDurability = ref(0)
const dynamicAmmo = ref(0)
const dynamicPassiveTraits = ref('')
const eggCharacterId = ref('')
const selectedContainerId = ref('')
const selectedSlotIndex = ref(null)
const selectedSlotButton = ref(null)
const editorPanel = ref(null)
const editorStyle = ref({ visibility: 'hidden' })
const countDraft = ref(1)

const tr = (key, args = []) => palStore.getTranslatedText(key, args)
const storage = computed(() => (
  palStore.getBaseStorage(props.guildId, props.baseId)
))
const loading = computed(() => (
  palStore.isBaseStorageLoading(props.guildId, props.baseId)
))
const writable = computed(() => (
  storage.value?.write_status === 'available'
))
const activeContainer = computed(() => (
  storage.value?.containers?.find(
    container => container.container_id === selectedContainerId.value,
  ) || storage.value?.containers?.[0] || null
))
const selectedSlot = computed(() => (
  activeContainer.value?.slots?.find(
    slot => slot.slot_index === selectedSlotIndex.value,
  ) || null
))
const selectedMaxStack = computed(() => Math.max(
  1,
  Number(selectedSlot.value?.item?.max_stack)
    || Number(selectedSlot.value?.item?.count)
    || 1,
))
const countDraftValid = computed(() => {
  const count = Number(countDraft.value)
  return Number.isInteger(count)
    && count >= 1
    && count <= selectedMaxStack.value
})
const selectedCatalogItem = computed(() => (
  palStore.ITEM_CATALOG_RESULTS.find(
    item => item.static_id === selectedStaticId.value,
  ) || null
))
const dynamicKind = computed(() => (
  selectedCatalogItem.value?.dynamic_kind || 'none'
))
const eggSpecies = computed(() => palStore.PAL_STATIC_DATA_LIST.filter(
  item => !item.Invalid && !item.IsHuman,
))
const selectedEggSpecies = computed(() => (
  palStore.PAL_STATIC_DATA[eggCharacterId.value] || null
))
const dynamicInitializerValid = computed(() => {
  if (dynamicKind.value === 'none') return true
  if (!dynamicRecordStaticId.value.trim()) return false
  if (dynamicKind.value === 'egg') return Boolean(eggCharacterId.value)
  if (
    !Number.isFinite(Number(dynamicDurability.value))
    || Number(dynamicDurability.value) < 0
  ) return false
  return dynamicKind.value !== 'weapon'
    || (
      Number.isInteger(Number(dynamicAmmo.value))
      && Number(dynamicAmmo.value) >= 0
    )
})

function shortId(value) {
  return value ? String(value).slice(-8) : ''
}

function containerName(container) {
  return container.building_name
    || tr('Guild_BaseStorageBuildingUnknown')
}

function occupiedCount(container) {
  return (container.slots || []).filter(slot => slot.state === 'occupied').length
}

function selectContainer(container) {
  selectedContainerId.value = container.container_id
  clearSlotSelection()
}

function isSelectedSlot(container, slot) {
  return selectedContainerId.value === container.container_id
    && selectedSlotIndex.value === slot.slot_index
}

function slotAriaLabel(slot) {
  if (slot.state === 'empty') {
    return tr('Guild_BaseStorageEmptySlotAria', [slot.slot_index + 1])
  }
  return tr('Guild_BaseStorageOccupiedSlotAria', [
    slot.slot_index + 1,
    slot.item.name || slot.item.static_id,
    slot.item.count,
  ])
}

function selectSlot(container, slot, event) {
  if (slot.state === 'empty') {
    clearSlotSelection()
    openPicker(container, slot, 'empty_only')
    return
  }
  selectedContainerId.value = container.container_id
  selectedSlotIndex.value = slot.slot_index
  selectedSlotButton.value = event.currentTarget
  countDraft.value = slot.item.count
  positionEditor()
  nextTick(() => {
    const input = editorPanel.value?.querySelector('input[type="number"]')
    input?.focus()
    input?.select()
  })
}

function clearSlotSelection() {
  selectedSlotIndex.value = null
  selectedSlotButton.value = null
  editorStyle.value = { visibility: 'hidden' }
}

function setMaxCount() {
  countDraft.value = selectedMaxStack.value
}

function positionEditor() {
  if (!selectedSlot.value || !selectedSlotButton.value) return
  nextTick(() => {
    const anchor = selectedSlotButton.value
    const panel = editorPanel.value
    if (!anchor || !panel) return
    const anchorRect = anchor.getBoundingClientRect()
    const panelWidth = panel.offsetWidth || 272
    const panelHeight = panel.offsetHeight || 190
    const viewportGap = 12
    const anchorGap = 10
    let left = anchorRect.right + anchorGap
    if (left + panelWidth > window.innerWidth - viewportGap) {
      left = anchorRect.left - panelWidth - anchorGap
    }
    left = Math.max(
      viewportGap,
      Math.min(left, window.innerWidth - panelWidth - viewportGap),
    )
    const top = Math.max(
      viewportGap,
      Math.min(
        anchorRect.top,
        window.innerHeight - panelHeight - viewportGap,
      ),
    )
    editorStyle.value = {
      left: `${Math.round(left)}px`,
      top: `${Math.round(top)}px`,
      visibility: 'visible',
    }
  })
}

async function saveCount() {
  if (
    !activeContainer.value
    || !selectedSlot.value
    || !countDraftValid.value
  ) return
  const count = Number(countDraft.value)
  const result = await palStore.updateBaseStorageItemCount(
    props.guildId,
    props.baseId,
    activeContainer.value,
    selectedSlot.value,
    count,
  )
  if (result) {
    countDraft.value = count
    positionEditor()
  }
}

async function openPicker(container, slot, mode) {
  if (!writable.value || loading.value) return
  pendingContainer.value = container
  pendingSlot.value = slot
  pendingMode.value = mode
  selectedStaticId.value = ''
  addCount.value = 1
  await palStore.searchItemCatalog('', 'BASE_STORAGE')
  selectedStaticId.value = palStore.ITEM_CATALOG_RESULTS[0]?.static_id || ''
  picker.value?.open()
}

function buildDynamicInit() {
  const recordStaticId = dynamicRecordStaticId.value.trim()
  if (dynamicKind.value === 'weapon') {
    return {
      record_static_id: recordStaticId,
      durability: Number(dynamicDurability.value),
      ammo: Number(dynamicAmmo.value),
      passive_traits: dynamicPassiveTraits.value
        .split(',')
        .map(value => value.trim())
        .filter(Boolean),
    }
  }
  if (dynamicKind.value === 'armor') {
    return {
      record_static_id: recordStaticId,
      durability: Number(dynamicDurability.value),
    }
  }
  if (dynamicKind.value === 'egg') {
    return {
      record_static_id: recordStaticId,
      character_id: eggCharacterId.value,
    }
  }
  return null
}

async function confirmPut({ item, quantity }) {
  if (
    !pendingContainer.value
    || !pendingSlot.value
    || !dynamicInitializerValid.value
  ) return
  const result = await palStore.putBaseStorageItem(
    props.guildId,
    props.baseId,
    pendingContainer.value,
    pendingSlot.value,
    item.static_id,
    quantity,
    pendingMode.value,
    buildDynamicInit(),
  )
  pendingContainer.value = null
  pendingSlot.value = null
  if (result) clearSlotSelection()
}

async function clearSlot() {
  if (
    !activeContainer.value
    || !selectedSlot.value
    || !writable.value
    || loading.value
    || !window.confirm(tr('Guild_BaseStorageDeleteConfirm'))
  ) return
  const result = await palStore.clearBaseStorageItem(
    props.guildId,
    props.baseId,
    activeContainer.value,
    selectedSlot.value,
  )
  if (result) clearSlotSelection()
}

function handleDocumentPointerDown(event) {
  if (selectedSlotIndex.value === null) return
  if (
    event.target.closest('.storage-slot-editor')
    || event.target.closest('.storage-slot')
  ) return
  clearSlotSelection()
}

function handleDocumentKeydown(event) {
  if (event.key === 'Escape') clearSlotSelection()
}

watch(selectedStaticId, staticId => {
  dynamicRecordStaticId.value = staticId || ''
  dynamicDurability.value = 0
  dynamicAmmo.value = 0
  dynamicPassiveTraits.value = ''
  eggCharacterId.value = ''
})

watch(
  () => storage.value?.containers,
  containers => {
    const values = containers || []
    if (
      !values.some(
        container => container.container_id === selectedContainerId.value,
      )
    ) {
      selectedContainerId.value = values[0]?.container_id || ''
      clearSlotSelection()
    }
  },
  { immediate: true },
)

watch(
  () => storage.value?.revision,
  () => {
    if (selectedSlot.value?.state !== 'occupied') {
      clearSlotSelection()
      return
    }
    positionEditor()
  },
)

onMounted(async () => {
  document.addEventListener('pointerdown', handleDocumentPointerDown)
  document.addEventListener('keydown', handleDocumentKeydown)
  window.addEventListener('resize', positionEditor)
  window.addEventListener('scroll', positionEditor, true)
  await Promise.all([
    palStore.loadBaseStorage(props.guildId, props.baseId),
    palStore.searchItemCatalog('', 'BASE_STORAGE'),
  ])
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', handleDocumentPointerDown)
  document.removeEventListener('keydown', handleDocumentKeydown)
  window.removeEventListener('resize', positionEditor)
  window.removeEventListener('scroll', positionEditor, true)
})
</script>

<template>
  <section class="base-storage-panel">
    <div v-if="loading && !storage" class="base-storage-state" aria-busy="true">
      <AppIcon name="refresh" :size="16" />
      {{ tr('Guild_BaseStorageLoading') }}
    </div>

    <div v-else-if="!storage" class="base-storage-state is-warning">
      {{ tr('Guild_BaseStorageUnavailable') }}
    </div>

    <template v-else>
      <div v-if="storage.reason" class="base-storage-state is-warning">
        <AppIcon name="activity" :size="16" />
        {{ tr(storage.reason) }}
      </div>

      <div v-if="!storage.containers?.length" class="base-storage-state">
        <AppIcon name="box" :size="16" />
        {{ tr('Guild_BaseStorageEmpty') }}
      </div>

      <div v-else class="storage-workspace">
        <aside
          class="storage-container-list"
          :aria-label="tr('Guild_BaseStorageContainerList')"
        >
          <button
            v-for="(container, containerIndex) in storage.containers"
            :key="container.container_id"
            type="button"
            :class="[
              'storage-container-item',
              { 'is-active': activeContainer?.container_id === container.container_id },
            ]"
            :title="containerName(container)"
            @click="selectContainer(container)"
          >
            <span class="storage-container-item__icon">
              <AppIcon name="box" :size="17" />
            </span>
            <span class="storage-container-item__copy">
              <strong>{{ containerName(container) }}</strong>
              <small>
                {{ tr('Guild_BaseStorageContainerNumber', [containerIndex + 1]) }}
              </small>
            </span>
            <span class="storage-container-item__count">
              {{ occupiedCount(container) }}/{{ container.capacity ?? '—' }}
            </span>
          </button>
        </aside>

        <section
          v-if="activeContainer"
          class="storage-content"
          @click.self="clearSlotSelection"
        >
          <header class="storage-content__header">
            <div>
              <strong>{{ containerName(activeContainer) }}</strong>
              <small :title="activeContainer.container_id">
                {{ tr('Guild_BaseStorageSlotSummary', [
                  occupiedCount(activeContainer),
                  activeContainer.capacity ?? '—',
                ]) }}
                · {{ shortId(activeContainer.container_id) }}
              </small>
            </div>
          </header>

          <p
            v-if="activeContainer.status !== 'available'"
            class="base-storage-state is-warning"
          >
            {{ tr(activeContainer.reason || 'Guild_BaseStorageUnavailable') }}
          </p>

          <div
            v-else
            class="storage-slot-grid"
            role="grid"
            :aria-label="tr('Guild_BaseStorageGridLabel', [
              containerName(activeContainer),
            ])"
            @click.self="clearSlotSelection"
          >
            <button
              v-for="slot in activeContainer.slots"
              :key="slot.slot_index"
              type="button"
              :class="[
                'storage-slot',
                {
                  'is-empty': slot.state === 'empty',
                  'is-selected': isSelectedSlot(activeContainer, slot),
                },
              ]"
              role="gridcell"
              :aria-label="slotAriaLabel(slot)"
              :aria-selected="isSelectedSlot(activeContainer, slot)"
              :data-slot-selected="isSelectedSlot(activeContainer, slot)"
              :disabled="slot.state === 'empty' && (!writable || loading)"
              @click="selectSlot(activeContainer, slot, $event)"
            >
              <template v-if="slot.state === 'occupied'">
                <ItemIcon
                  :icon="slot.item.icon"
                  :name="slot.item.name"
                  :size="42"
                />
                <span class="storage-slot__count">
                  {{ slot.item.count }}
                </span>
              </template>
              <AppIcon v-else name="plus" :size="20" />
            </button>
          </div>
        </section>
      </div>
    </template>

    <Teleport to="body">
      <section
        v-if="selectedSlot?.state === 'occupied'"
        ref="editorPanel"
        class="storage-slot-editor"
        :style="editorStyle"
        role="group"
        :aria-label="tr('Guild_BaseStorageEditItem', [
          selectedSlot.item.name || selectedSlot.item.static_id,
        ])"
      >
        <header>
          <ItemIcon
            :icon="selectedSlot.item.icon"
            :name="selectedSlot.item.name"
            :size="36"
          />
          <div>
            <strong>{{ selectedSlot.item.name || selectedSlot.item.static_id }}</strong>
            <small>{{ selectedSlot.item.static_id }}</small>
          </div>
          <button
            type="button"
            class="storage-slot-editor__close"
            :title="tr('Common_Close')"
            :aria-label="tr('Common_Close')"
            @click="clearSlotSelection"
          >
            <AppIcon name="x" :size="16" />
          </button>
        </header>

        <label class="storage-slot-editor__count">
          <span>
            {{ tr('Inventory_Count') }}
            <small>
              {{ tr('Inventory_ItemPicker_MaxStack', [selectedMaxStack]) }}
            </small>
          </span>
          <span>
            <input
              v-model.number="countDraft"
              type="number"
              min="1"
              :max="selectedMaxStack"
              step="1"
              :disabled="!writable || loading"
              @keydown.enter.prevent="saveCount"
            >
            <button
              type="button"
              :disabled="!writable || loading"
              @click="setMaxCount"
            >
              {{ tr('Inventory_Max') }}
            </button>
          </span>
        </label>

        <div class="storage-slot-editor__actions">
          <button
            type="button"
            :disabled="!writable || loading || !countDraftValid"
            @click="saveCount"
          >
            <AppIcon name="check" :size="15" />
            {{ tr('Inventory_SaveCountTitle') }}
          </button>
          <button
            type="button"
            :disabled="!writable || loading"
            @click="openPicker(activeContainer, selectedSlot, 'replace')"
          >
            <AppIcon name="edit" :size="15" />
            {{ tr('Guild_BaseStorageReplace') }}
          </button>
          <button
            type="button"
            class="is-danger"
            :disabled="!writable || loading"
            @click="clearSlot"
          >
            <AppIcon name="trash" :size="15" />
            {{ tr('Inventory_ClearSlotTitle') }}
          </button>
        </div>
      </section>
    </Teleport>

    <ItemPicker
      ref="picker"
      v-model="selectedStaticId"
      v-model:quantity="addCount"
      :options="palStore.ITEM_CATALOG_RESULTS"
      :selected-option="selectedCatalogItem"
      :disabled="loading || !writable"
      :confirm-disabled="!dynamicInitializerValid"
      trigger-hidden
      show-quantity
      @confirm="confirmPut"
    >
      <template #details>
        <div
          v-if="selectedCatalogItem && dynamicKind !== 'none'"
          class="storage-dynamic-fields"
        >
          <header>
            <strong>{{ tr('Guild_BaseStorageDynamicCreate') }}</strong>
            <small>{{ tr('Inventory_IndependentDynamicRecord') }}</small>
          </header>
          <label>
            <span>{{ tr('Inventory_RecordItemId') }}</span>
            <input
              v-model="dynamicRecordStaticId"
              autocomplete="off"
              spellcheck="false"
            >
          </label>
          <label v-if="dynamicKind === 'weapon' || dynamicKind === 'armor'">
            <span>{{ tr('Inventory_Durability') }}</span>
            <input v-model.number="dynamicDurability" type="number" min="0" step="any">
          </label>
          <label v-if="dynamicKind === 'weapon'">
            <span>{{ tr('Inventory_LoadedAmmo') }}</span>
            <input v-model.number="dynamicAmmo" type="number" min="0" step="1">
          </label>
          <label v-if="dynamicKind === 'weapon'">
            <span>{{ tr('Inventory_PassiveTraits') }}</span>
            <input
              v-model="dynamicPassiveTraits"
              :placeholder="tr('Inventory_PassiveTraitsPlaceholder')"
            >
          </label>
          <label v-if="dynamicKind === 'egg'" class="is-wide">
            <span>{{ tr('Inventory_EggSpecies') }}</span>
            <PalSpeciesPicker
              v-model="eggCharacterId"
              :options="eggSpecies"
              :selected-option="selectedEggSpecies"
              :disabled="loading"
              show-internal-name
              :title="tr('Inventory_SelectEggSpecies')"
              :placeholder="tr('Inventory_EggSpeciesPlaceholder')"
            />
          </label>
          <p v-if="!dynamicInitializerValid">
            {{ tr('Inventory_DynamicRequired') }}
          </p>
        </div>
      </template>
    </ItemPicker>
  </section>
</template>

<style scoped>
.base-storage-panel {
  display: grid;
  gap: 10px;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--ui-border);
}

.base-storage-state {
  display: flex;
  align-items: center;
  gap: 7px;
  margin: 0;
  padding: 10px;
  color: var(--ui-text-muted);
  background: var(--ui-surface);
  border-radius: var(--ui-radius-sm);
  font-size: 11px;
}

.base-storage-state.is-warning {
  color: var(--ui-danger);
  background: var(--ui-danger-soft);
}

.storage-workspace {
  display: grid;
  grid-template-columns: 196px minmax(0, 1fr);
  min-height: 230px;
  background: var(--ui-surface);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
}

.storage-container-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px;
  background: var(--ui-surface-raised);
  border-right: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm) 0 0 var(--ui-radius-sm);
}

.storage-container-item {
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-height: 48px;
  padding: 6px 8px;
  color: var(--ui-text-secondary);
  text-align: left;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 7px;
}

.storage-container-item:hover {
  color: var(--ui-text);
  background: var(--ui-surface-hover);
}

.storage-container-item:focus-visible {
  outline: 2px solid var(--ui-accent);
  outline-offset: 1px;
}

.storage-container-item.is-active {
  color: var(--ui-text);
  background: var(--ui-accent-soft);
  border-color: color-mix(in srgb, var(--ui-accent) 42%, var(--ui-border));
}

.storage-container-item__icon {
  display: inline-grid;
  width: 30px;
  height: 30px;
  place-content: center;
  color: var(--ui-text-muted);
  background: var(--ui-surface);
  border-radius: 7px;
}

.storage-container-item.is-active .storage-container-item__icon {
  color: var(--ui-accent);
}

.storage-container-item__copy {
  display: grid;
  min-width: 0;
  gap: 2px;
}

.storage-container-item__copy strong,
.storage-container-item__copy small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.storage-container-item__copy strong {
  font-size: 10.5px;
}

.storage-container-item__copy small,
.storage-container-item__count {
  color: var(--ui-text-muted);
  font-size: 9px;
}

.storage-container-item__count {
  font-variant-numeric: tabular-nums;
}

.storage-content {
  min-width: 0;
  padding: 10px;
}

.storage-content__header {
  display: flex;
  align-items: center;
  min-height: 38px;
  margin-bottom: 8px;
  padding: 0 2px 8px;
  border-bottom: 1px solid var(--ui-border);
}

.storage-content__header > div {
  display: grid;
  min-width: 0;
  gap: 2px;
}

.storage-content__header strong,
.storage-content__header small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.storage-content__header strong {
  font-size: 12px;
}

.storage-content__header small {
  color: var(--ui-text-muted);
  font-size: 9.5px;
}

.storage-slot-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, 72px);
  grid-auto-rows: 72px;
  align-content: start;
  gap: 8px;
  min-height: 164px;
}

.storage-slot {
  position: relative;
  display: grid;
  width: 72px;
  height: 72px;
  place-content: center;
  padding: 5px;
  color: var(--ui-text);
  background: var(--ui-surface-raised);
  border: 1px solid var(--ui-border);
  border-radius: 8px;
  outline: 0;
  transition:
    border-color 150ms ease,
    background-color 150ms ease,
    transform 150ms ease;
}

.storage-slot:hover:not(:disabled) {
  background: var(--ui-surface-hover);
  border-color: color-mix(in srgb, var(--ui-accent) 48%, var(--ui-border));
  transform: translateY(-1px);
}

.storage-slot:focus-visible,
.storage-slot.is-selected {
  border-color: var(--ui-accent);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--ui-accent) 24%, transparent);
}

.storage-slot.is-selected {
  background: var(--ui-accent-soft);
}

.storage-slot.is-empty {
  color: var(--ui-text-muted);
  background: transparent;
  border-style: dashed;
}

.storage-slot__count {
  position: absolute;
  right: 5px;
  bottom: 4px;
  min-width: 20px;
  padding: 2px 5px;
  color: var(--ui-text);
  text-align: center;
  background: var(--ui-surface);
  border-radius: 999px;
  font-size: 9px;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
}

.storage-slot-editor {
  position: fixed;
  z-index: 120;
  display: grid;
  width: 272px;
  gap: 12px;
  padding: 12px;
  color: var(--ui-text);
  background: var(--ui-surface);
  border: 1px solid var(--ui-border-strong);
  border-radius: var(--ui-radius-sm);
  box-shadow: 0 4px 8px color-mix(in srgb, #000 24%, transparent);
}

.storage-slot-editor > header {
  display: flex;
  align-items: center;
  gap: 9px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--ui-border);
}

.storage-slot-editor > header > div {
  display: grid;
  min-width: 0;
  flex: 1 1 auto;
  gap: 2px;
}

.storage-slot-editor > header strong,
.storage-slot-editor > header small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.storage-slot-editor > header strong {
  font-size: 12px;
}

.storage-slot-editor > header small {
  color: var(--ui-text-muted);
  font-size: 9px;
}

.storage-slot-editor__close {
  display: inline-grid;
  width: 28px;
  height: 28px;
  flex: 0 0 28px;
  place-content: center;
  color: var(--ui-text-muted);
  background: transparent;
  border: 0;
  border-radius: 6px;
}

.storage-slot-editor__close:hover,
.storage-slot-editor__close:focus-visible {
  color: var(--ui-text);
  background: var(--ui-surface-hover);
}

.storage-slot-editor__count {
  display: grid;
  gap: 5px;
}

.storage-slot-editor__count > span {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  color: var(--ui-text-secondary);
  font-size: 10px;
  font-weight: 700;
}

.storage-slot-editor__count small {
  color: var(--ui-text-muted);
  font-size: 9px;
  font-weight: 500;
}

.storage-slot-editor__count input {
  min-width: 0;
  height: 34px;
  flex: 1 1 auto;
  padding: 0 8px;
  color: var(--ui-text);
  background: var(--ui-canvas);
  border: 1px solid var(--ui-border-strong);
  border-radius: 6px;
  font: inherit;
  font-variant-numeric: tabular-nums;
}

.storage-slot-editor__count input:focus {
  border-color: var(--ui-accent);
  outline: 0;
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--ui-accent) 22%, transparent);
}

.storage-slot-editor__count button {
  height: 34px;
  padding: 0 10px;
  color: var(--ui-accent);
  background: var(--ui-accent-soft);
  border: 0;
  border-radius: 6px;
  font-size: 10px;
  font-weight: 800;
}

.storage-slot-editor__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.storage-slot-editor__actions button {
  display: inline-flex;
  min-height: 32px;
  flex: 1 1 auto;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 0 9px;
  color: var(--ui-accent);
  background: var(--ui-accent-soft);
  border: 0;
  border-radius: 6px;
  font-size: 9.5px;
  font-weight: 700;
}

.storage-slot-editor__actions button.is-danger {
  color: var(--ui-danger);
  background: var(--ui-danger-soft);
}

.storage-slot-editor button:disabled {
  cursor: not-allowed;
  opacity: .55;
}

.storage-dynamic-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  padding: 10px;
  background: var(--ui-accent-soft);
  border: 1px solid var(--ui-accent);
  border-radius: var(--ui-radius-sm);
}

.storage-dynamic-fields header,
.storage-dynamic-fields .is-wide,
.storage-dynamic-fields p {
  grid-column: 1 / -1;
}

.storage-dynamic-fields header {
  display: grid;
  gap: 2px;
}

.storage-dynamic-fields header small,
.storage-dynamic-fields label span {
  color: var(--ui-text-muted);
  font-size: 10px;
}

.storage-dynamic-fields label {
  display: grid;
  gap: 4px;
  font-size: 11px;
}

.storage-dynamic-fields input {
  min-height: 34px;
  padding: 0 8px;
  color: var(--ui-text);
  background: var(--ui-surface);
  border: 1px solid var(--ui-border);
  border-radius: 6px;
}

.storage-dynamic-fields p {
  margin: 0;
  color: var(--ui-danger);
  font-size: 10px;
}

@media (max-width: 720px) {
  .storage-workspace {
    grid-template-columns: 1fr;
  }

  .storage-container-list {
    overflow-x: auto;
    flex-direction: row;
    border-right: 0;
    border-bottom: 1px solid var(--ui-border);
    border-radius: var(--ui-radius-sm) var(--ui-radius-sm) 0 0;
  }

  .storage-container-item {
    width: 184px;
    flex: 0 0 184px;
  }
}

@media (max-width: 620px) {
  .storage-slot-editor {
    right: 12px !important;
    bottom: 12px;
    left: 12px !important;
    top: auto !important;
    width: auto;
    visibility: visible !important;
  }

  .storage-dynamic-fields {
    grid-template-columns: 1fr;
  }
}

@media (prefers-reduced-motion: reduce) {
  .storage-slot {
    transition: none;
  }
}
</style>
