<script setup>
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from 'vue'
import { usePalEditorStore } from '@/stores/paleditor'
import AppIcon from '@/components/modules/AppIcon.vue'
import ItemIcon from '@/components/modules/ItemIcon.vue'
import ItemPicker from '@/components/modules/ItemPicker.vue'
import PalSpeciesPicker from '@/components/modules/PalSpeciesPicker.vue'

const palStore = usePalEditorStore()
const selectedContainerType = ref('COMMON')
const selectedSlotIndex = ref(null)
const selectedStaticId = ref('')
const addCount = ref(1)
const pendingContainer = ref(null)
const pendingSlot = ref(null)
const pendingMode = ref('empty_only')
const addPicker = ref(null)
const dynamicRecordStaticId = ref('')
const dynamicDurability = ref(0)
const dynamicAmmo = ref(0)
const dynamicPassiveTraits = ref('')
const eggCharacterId = ref('')
const dynamicEditors = ref({})
const draggedContainerType = ref(null)
const draggedSlotIndex = ref(null)
const dragOverContainerType = ref(null)
const dragOverSlotIndex = ref(null)
const moveSourceContainerType = ref(null)
const moveSourceSlotIndex = ref(null)
const moveStatus = ref('')
const selectedSlotContainerType = ref(null)
const selectedSlotButton = ref(null)
const editorPanel = ref(null)
const editorStyle = ref({ visibility: 'hidden' })
const countDraft = ref(1)
const itemMaxStacks = ref(new Map())

const containerLabelKeys = Object.freeze({
  COMMON: 'Inventory_Container_Common',
  ESSENTIAL: 'Inventory_Container_Essential',
  WEAPON_LOADOUT: 'Inventory_Container_WeaponLoadout',
  PLAYER_EQUIP_ARMOR: 'Inventory_Container_ArmorEquipment',
  FOOD_EQUIP: 'Inventory_Container_FoodEquipment',
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
const dynamicFieldLabelKeys = Object.freeze({
  ammo: 'Inventory_DynamicField_Ammo',
  durability: 'Inventory_DynamicField_Durability',
  freshness: 'Inventory_DynamicField_Freshness',
  passive_traits: 'Inventory_DynamicField_PassiveTraits',
})
const backpackContainerTypes = new Set(['COMMON', 'ESSENTIAL'])
const equipmentSectionDefinitions = Object.freeze([
  {
    key: 'weapon',
    containerType: 'WEAPON_LOADOUT',
    side: 'left',
    labelKey: 'Inventory_Category_Weapon',
  },
  {
    key: 'accessory',
    containerType: 'PLAYER_EQUIP_ARMOR',
    side: 'bottom',
    slotIndices: [2, 3, 6, 7],
    labelKey: 'Inventory_Category_Accessory',
  },
  {
    key: 'head',
    containerType: 'PLAYER_EQUIP_ARMOR',
    side: 'right',
    slotIndices: [0],
    labelKey: 'Inventory_Category_Head',
  },
  {
    key: 'body',
    containerType: 'PLAYER_EQUIP_ARMOR',
    side: 'right',
    slotIndices: [1],
    labelKey: 'Inventory_Category_Body',
  },
  {
    key: 'shield',
    containerType: 'PLAYER_EQUIP_ARMOR',
    side: 'right',
    slotIndices: [4],
    labelKey: 'Inventory_Category_Shield',
  },
  {
    key: 'glider',
    containerType: 'PLAYER_EQUIP_ARMOR',
    side: 'right',
    slotIndices: [5],
    labelKey: 'Inventory_Category_Glider',
  },
  {
    key: 'sphere-module',
    containerType: 'PLAYER_EQUIP_ARMOR',
    side: 'right',
    slotIndices: [8],
    labelKey: 'Inventory_Category_SphereModule',
  },
  {
    key: 'food',
    containerType: 'FOOD_EQUIP',
    side: 'bottom',
    labelKey: 'Inventory_Category_Food',
  },
])

const tr = (key, args = []) => palStore.getTranslatedText(key, args)
const localizedLabel = (keys, value, fallbackKey) => (
  tr(keys[value] || fallbackKey, keys[value] ? [] : [String(value ?? '')])
)
const containerLabel = value => localizedLabel(
  containerLabelKeys,
  value,
  'Inventory_Container_Unknown',
)
const dynamicKindLabel = value => localizedLabel(
  dynamicKindLabelKeys,
  value,
  'Inventory_DynamicKind_Unknown',
)
const categoryLabel = value => localizedLabel(
  categoryLabelKeys,
  value,
  'Inventory_Category_Unknown',
)
const dynamicFieldLabel = value => localizedLabel(
  dynamicFieldLabelKeys,
  value,
  'Inventory_DynamicField_Unknown',
)

const containers = computed(() => palStore.SELECTED_PLAYER_DATA?.InventoryContainers || [])
const backpackContainers = computed(() => containers.value.filter(
  container => backpackContainerTypes.has(container.container_type),
))
const selectedContainer = computed(() =>
  backpackContainers.value.find(
    container => container.container_type === selectedContainerType.value,
  ) || backpackContainers.value[0] || null
)
const visibleSlots = computed(() => selectedContainer.value?.slots || [])
const displaySlots = computed(() => {
  const slots = visibleSlots.value
  if (selectedContainer.value?.container_type !== 'ESSENTIAL') return slots
  const retainedSlots = slots.filter(slot => slot.state === 'occupied')
  const emptySlot = slots.find(slot => slot.state === 'empty')
  return emptySlot ? [...retainedSlots, emptySlot] : retainedSlots
})
const selectedSlotContainer = computed(() => containers.value.find(
  container => container.container_type === selectedSlotContainerType.value,
) || null)
const selectedSlot = computed(() => (
  selectedSlotContainer.value?.slots?.find(
    slot => slot.slot_index === selectedSlotIndex.value,
  ) || null
))
const equipmentSections = computed(() => equipmentSectionDefinitions.map(definition => {
  const container = containers.value.find(
    candidate => candidate.container_type === definition.containerType,
  ) || null
  const slots = container?.slots || []
  return {
    ...definition,
    container,
    slots: definition.slotIndices
      ? definition.slotIndices.map(slotIndex => (
        slots.find(slot => slot.slot_index === slotIndex)
          || { slot_index: slotIndex, state: 'unavailable' }
      ))
      : slots,
  }
}))
const leftEquipmentSections = computed(() => equipmentSections.value.filter(
  section => section.side === 'left',
))
const rightEquipmentSections = computed(() => equipmentSections.value.filter(
  section => section.side === 'right',
))
const bottomEquipmentSections = computed(() => equipmentSections.value.filter(
  section => section.side === 'bottom',
))
const selectedCatalogItem = computed(() =>
  palStore.ITEM_CATALOG_RESULTS.find(item => item.static_id === selectedStaticId.value)
)
const dynamicKind = computed(() => selectedCatalogItem.value?.dynamic_kind || 'none')
const eggSpecies = computed(() => palStore.PAL_STATIC_DATA_LIST.filter(
  item => !item.Invalid && !item.IsHuman,
))
const selectedEggSpecies = computed(() => palStore.PAL_STATIC_DATA[eggCharacterId.value] || null)
const dynamicInitializerValid = computed(() => {
  if (dynamicKind.value === 'none') return true
  if (!dynamicRecordStaticId.value.trim()) return false
  if (dynamicKind.value === 'egg') return Boolean(eggCharacterId.value)
  if (!Number.isFinite(Number(dynamicDurability.value)) || Number(dynamicDurability.value) < 0) return false
  return dynamicKind.value !== 'weapon'
    || (Number.isInteger(Number(dynamicAmmo.value)) && Number(dynamicAmmo.value) >= 0)
})
const occupiedCount = container => (container?.slots || []).filter(slot => slot.state === 'occupied').length
const selectedMaxStack = computed(() => itemMaxStack(selectedSlot.value?.item?.static_id))
const selectedCountEditable = computed(() => selectedMaxStack.value > 1)
const countDraftValid = computed(() => {
  const count = Number(countDraft.value)
  return Number.isInteger(count) && count >= 1 && count <= selectedMaxStack.value
})
const isSlotAvailable = (container, slot) => (
  container?.status === 'available' && (slot?.state === 'occupied' || slot?.state === 'empty')
)
const supportsSlotMove = container => Boolean(
  container && container.container_type !== 'ESSENTIAL',
)
const isMoveSource = (container, slot) => (
  moveSourceContainerType.value === container?.container_type
  && moveSourceSlotIndex.value === slot?.slot_index
)
const isDropTarget = (container, slot) => (
  dragOverContainerType.value === container?.container_type
  && dragOverSlotIndex.value === slot?.slot_index
)
const isSelectedSlot = (container, slot) => (
  selectedSlotContainerType.value === container?.container_type
  && selectedSlotIndex.value === slot?.slot_index
)

async function loadCatalog(containerType = selectedContainerType.value) {
  const results = await palStore.searchItemCatalog('', containerType)
  const nextMaxStacks = new Map(itemMaxStacks.value)
  for (const item of results) {
    const maxStack = Number(item.max_stack)
    if (Number.isFinite(maxStack) && maxStack >= 1) {
      nextMaxStacks.set(item.static_id, maxStack)
    }
  }
  itemMaxStacks.value = nextMaxStacks
  if (!results.some(item => item.static_id === selectedStaticId.value)) {
    selectedStaticId.value = results[0]?.static_id || ''
  }
}

async function addToSlot(slot) {
  if (!pendingContainer.value || !selectedStaticId.value || !dynamicInitializerValid.value) return
  return palStore.putInventoryItem(
    pendingContainer.value,
    slot,
    selectedStaticId.value,
    addCount.value,
    buildDynamicInit(),
    pendingMode.value,
  )
}

function itemMaxStack(staticId) {
  return Math.max(
    1,
    Number(itemMaxStacks.value.get(staticId))
      || Number(palStore.ITEM_CATALOG_RESULTS.find(item => item.static_id === staticId)?.max_stack)
      || 1,
  )
}

function shouldShowQuantity(item) {
  if (!item) return false
  if (itemMaxStacks.value.has(item.static_id)) return itemMaxStack(item.static_id) > 1
  return Number(item.count) > 1
}

function itemRarity(item) {
  const rarity = Number(
    item?.rarity
      ?? palStore.ITEM_CATALOG_RESULTS.find(
        catalogItem => catalogItem.static_id === item?.static_id,
      )?.rarity,
  )
  return Number.isFinite(rarity)
    ? Math.max(0, Math.min(5, Math.trunc(rarity)))
    : 0
}

function slotAriaLabel(slot) {
  if (slot.state === 'empty') {
    return tr('Inventory_EmptySlotAriaLabel', [slot.slot_index + 1])
  }
  if (slot.state !== 'occupied') return tr('Inventory_ContainerUnavailable')
  return tr('Inventory_SlotAriaLabel', [
    slot.slot_index + 1,
    slot.item.name || slot.item.static_id,
    slot.item.count,
  ])
}

async function openAddDialog(container, slot, mode = 'empty_only') {
  clearSlotSelection()
  pendingContainer.value = container
  pendingSlot.value = slot
  pendingMode.value = mode
  selectedStaticId.value = ''
  addCount.value = 1
  await loadCatalog(container.container_type)
  addPicker.value?.open()
}

async function confirmAdd({ item, quantity }) {
  selectedStaticId.value = item.static_id
  addCount.value = quantity
  if (pendingSlot.value && dynamicInitializerValid.value) {
    await addToSlot(pendingSlot.value)
  }
  pendingContainer.value = null
  pendingSlot.value = null
  pendingMode.value = 'empty_only'
}

async function pasteIntoPendingSlot() {
  if (
    pendingMode.value !== 'empty_only'
    || !pendingContainer.value
    || !pendingSlot.value
    || !palStore.ITEM_CLIPBOARD
  ) return
  const pasted = await palStore.pasteInventoryItem(
    pendingContainer.value,
    pendingSlot.value,
  )
  if (pasted) {
    addPicker.value?.close()
    pendingContainer.value = null
    pendingSlot.value = null
    pendingMode.value = 'empty_only'
  }
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

async function toggleDynamicEditor(slot) {
  const key = String(slot.slot_index)
  if (dynamicEditors.value[key]) {
    const next = { ...dynamicEditors.value }
    delete next[key]
    dynamicEditors.value = next
    positionEditor()
    return
  }
  const data = await palStore.loadDynamicItemAttributes(selectedSlotContainer.value, slot)
  if (!data) return
  const values = Object.fromEntries(Object.entries(data.attributes).map(([field, value]) => [
    field,
    Array.isArray(value) ? value.join(', ') : value,
  ]))
  dynamicEditors.value = {
    ...dynamicEditors.value,
    [key]: { ...data, original: data.attributes, values },
  }
  positionEditor()
}

async function saveDynamic(slot) {
  const panel = dynamicEditors.value[String(slot.slot_index)]
  const values = Object.fromEntries(Object.entries(panel.values).map(([field, value]) => {
    if (Array.isArray(panel.original[field])) {
      return [field, String(value).split(',').map(item => item.trim()).filter(Boolean)]
    }
    return [field, Number(value)]
  }))
  if (await palStore.updateDynamicItemAttributes(selectedSlotContainer.value, slot, values)) {
    dynamicEditors.value = {}
  }
}

function clearMoveState(message = '') {
  draggedContainerType.value = null
  draggedSlotIndex.value = null
  dragOverContainerType.value = null
  dragOverSlotIndex.value = null
  moveSourceContainerType.value = null
  moveSourceSlotIndex.value = null
  moveStatus.value = message
}

function activateContainer(container, slotIndex = null) {
  if (!container || container.status !== 'available') return false
  if (selectedSlotContainerType.value !== container.container_type) {
    dynamicEditors.value = {}
    selectedStaticId.value = ''
    clearSlotSelection()
  }
  selectedSlotContainerType.value = container.container_type
  selectedSlotIndex.value = slotIndex
  return true
}

async function moveSlot(container, sourceSlotIndex, targetSlotIndex) {
  if (
    palStore.LOADING_FLAG
    || container?.status !== 'available'
    || !supportsSlotMove(container)
    || sourceSlotIndex === null
    || sourceSlotIndex === targetSlotIndex
  ) return false
  activateContainer(container, targetSlotIndex)
  const moved = await palStore.swapInventorySlots(
    container,
    sourceSlotIndex,
    targetSlotIndex,
  )
  if (moved) {
    clearSlotSelection()
    dynamicEditors.value = {}
    clearMoveState(tr('Inventory_MoveCompleted', [sourceSlotIndex + 1, targetSlotIndex + 1]))
  } else {
    clearMoveState(tr('Inventory_MoveFailed'))
  }
  return moved
}

async function selectSlot(container, slot) {
  if (!isSlotAvailable(container, slot)) return
  if (moveSourceSlotIndex.value !== null) {
    if (
      moveSourceContainerType.value === container.container_type
      && moveSourceSlotIndex.value !== slot.slot_index
    ) {
      await moveSlot(container, moveSourceSlotIndex.value, slot.slot_index)
      return
    }
    if (moveSourceContainerType.value !== container.container_type) {
      clearMoveState(tr('Inventory_MoveCancelled'))
    }
  }
  activateContainer(container, slot.slot_index)
}

function toggleMoveSource(container, slot) {
  if (
    !supportsSlotMove(container)
    || !isSlotAvailable(container, slot)
    || slot.state !== 'occupied'
    || palStore.LOADING_FLAG
  ) return
  if (isMoveSource(container, slot)) {
    clearMoveState(tr('Inventory_MoveCancelled'))
    return
  }
  activateContainer(container, slot.slot_index)
  moveSourceContainerType.value = container.container_type
  moveSourceSlotIndex.value = slot.slot_index
  moveStatus.value = tr('Inventory_MovePicked', [slot.slot_index + 1])
}

function onDragStart(event, container, slot) {
  if (
    !supportsSlotMove(container)
    || !isSlotAvailable(container, slot)
    || slot.state !== 'occupied'
    || palStore.LOADING_FLAG
  ) {
    event.preventDefault()
    return
  }
  clearSlotSelection()
  activateContainer(container, slot.slot_index)
  draggedContainerType.value = container.container_type
  draggedSlotIndex.value = slot.slot_index
  moveSourceContainerType.value = null
  moveSourceSlotIndex.value = null
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', JSON.stringify({
      container_type: container.container_type,
      slot_index: slot.slot_index,
    }))
  }
}

function onDragOver(event, container, slot) {
  if (
    !supportsSlotMove(container)
    || draggedContainerType.value !== container?.container_type
    || draggedSlotIndex.value === null
    || draggedSlotIndex.value === slot.slot_index
    || !isSlotAvailable(container, slot)
  ) return
  event.preventDefault()
  dragOverContainerType.value = container.container_type
  dragOverSlotIndex.value = slot.slot_index
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'move'
}

function onDragLeave(event, container, slot) {
  if (
    !event.currentTarget.contains(event.relatedTarget)
    && isDropTarget(container, slot)
  ) {
    dragOverContainerType.value = null
    dragOverSlotIndex.value = null
  }
}

async function onDrop(event, container, slot) {
  event.preventDefault()
  let transferred = null
  try {
    transferred = JSON.parse(event.dataTransfer?.getData('text/plain') || 'null')
  } catch {
    transferred = null
  }
  const sourceContainerType = draggedContainerType.value ?? transferred?.container_type ?? null
  const transferredSlotIndex = Number(transferred?.slot_index)
  const sourceSlotIndex = draggedSlotIndex.value
    ?? (Number.isInteger(transferredSlotIndex) ? transferredSlotIndex : null)
  dragOverContainerType.value = null
  dragOverSlotIndex.value = null
  if (
    supportsSlotMove(container)
    && sourceContainerType === container?.container_type
    && sourceSlotIndex !== null
    && sourceSlotIndex !== slot.slot_index
  ) {
    await moveSlot(container, sourceSlotIndex, slot.slot_index)
  } else {
    draggedContainerType.value = null
    draggedSlotIndex.value = null
  }
}

function onDragEnd() {
  draggedContainerType.value = null
  draggedSlotIndex.value = null
  dragOverContainerType.value = null
  dragOverSlotIndex.value = null
}

async function onSlotKeydown(event, container, slot) {
  if (event.key === 'Escape' && moveSourceSlotIndex.value !== null) {
    event.preventDefault()
    clearMoveState(tr('Inventory_MoveCancelled'))
    return
  }
  if (!supportsSlotMove(container)) return
  if (event.key !== ' ' && event.key !== 'Spacebar') return
  event.preventDefault()
  if (moveSourceSlotIndex.value === null) {
    toggleMoveSource(container, slot)
    return
  }
  if (isMoveSource(container, slot)) {
    clearMoveState(tr('Inventory_MoveCancelled'))
    return
  }
  if (moveSourceContainerType.value === container?.container_type) {
    await moveSlot(container, moveSourceSlotIndex.value, slot.slot_index)
  }
}

function clearSlotSelection() {
  selectedSlotContainerType.value = null
  selectedSlotIndex.value = null
  selectedSlotButton.value = null
  dynamicEditors.value = {}
  editorStyle.value = { visibility: 'hidden' }
}

function positionEditor() {
  if (!selectedSlot.value || !selectedSlotButton.value) return
  nextTick(() => {
    const anchor = selectedSlotButton.value
    const panel = editorPanel.value
    if (!anchor || !panel) return
    const anchorRect = anchor.getBoundingClientRect()
    const panelWidth = panel.offsetWidth || 304
    const panelHeight = panel.offsetHeight || 250
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
      Math.min(anchorRect.top, window.innerHeight - panelHeight - viewportGap),
    )
    editorStyle.value = {
      left: `${Math.round(left)}px`,
      top: `${Math.round(top)}px`,
      visibility: 'visible',
    }
  })
}

async function onSlotClick(event, container, slot) {
  if (!isSlotAvailable(container, slot) || palStore.LOADING_FLAG) return
  const slotButton = event.currentTarget
  const movePending = moveSourceSlotIndex.value !== null
  if (movePending) {
    await selectSlot(container, slot)
    return
  }
  if (slot.state === 'empty') {
    await openAddDialog(container, slot)
    return
  }
  await loadCatalog(container.container_type)
  await selectSlot(container, slot)
  selectedSlotButton.value = slotButton
  countDraft.value = slot.item.count
  positionEditor()
  nextTick(() => {
    const input = editorPanel.value?.querySelector('input[type="number"]')
    input?.focus()
    input?.select()
  })
}

function setMaxCount() {
  countDraft.value = selectedMaxStack.value
}

async function saveCount() {
  if (!selectedSlotContainer.value || !selectedSlot.value || !countDraftValid.value) return
  const slot = {
    ...selectedSlot.value,
    item: {
      ...selectedSlot.value.item,
      count: Number(countDraft.value),
    },
  }
  if (await palStore.updateInventoryItem(selectedSlotContainer.value, slot)) {
    positionEditor()
  }
}

async function copySelectedSlot() {
  if (!selectedSlotContainer.value || !selectedSlot.value) return
  await palStore.copyInventoryItem(selectedSlotContainer.value, selectedSlot.value)
}

async function clearSelectedSlot() {
  if (
    !selectedSlotContainer.value
    || !selectedSlot.value
    || !window.confirm(tr('Guild_BaseStorageDeleteConfirm'))
  ) return
  if (await palStore.clearInventoryItem(selectedSlotContainer.value, selectedSlot.value)) {
    clearSlotSelection()
  }
}

function handleDocumentPointerDown(event) {
  if (selectedSlotIndex.value === null) return
  if (
    event.target.closest('.inventory-slot-editor')
    || event.target.closest('.inventory-slot')
    || event.target.closest('.equipment-slot')
  ) return
  clearSlotSelection()
}

function handleDocumentKeydown(event) {
  if (event.key === 'Escape') clearSlotSelection()
}

watch(selectedContainerType, () => {
  clearSlotSelection()
  dynamicEditors.value = {}
  selectedStaticId.value = ''
  loadCatalog()
})
watch(() => selectedSlotContainer.value?.slots, slots => {
  const currentSlots = slots || []
  if (!currentSlots.some(slot => slot.slot_index === selectedSlotIndex.value)) {
    clearSlotSelection()
    return
  }
  if (selectedSlot.value?.state !== 'occupied') clearSlotSelection()
  else positionEditor()
}, { immediate: true })
watch(backpackContainers, currentContainers => {
  if (
    currentContainers.length
    && !currentContainers.some(container => container.container_type === selectedContainerType.value)
  ) {
    selectedContainerType.value = currentContainers[0].container_type
  }
}, { immediate: true })
watch(selectedStaticId, staticId => {
  dynamicRecordStaticId.value = staticId || ''
  dynamicDurability.value = 0
  dynamicAmmo.value = 0
  dynamicPassiveTraits.value = ''
  eggCharacterId.value = ''
})
onMounted(() => {
  document.addEventListener('pointerdown', handleDocumentPointerDown)
  document.addEventListener('keydown', handleDocumentKeydown)
  window.addEventListener('resize', positionEditor)
  window.addEventListener('scroll', positionEditor, true)
  loadCatalog()
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', handleDocumentPointerDown)
  document.removeEventListener('keydown', handleDocumentKeydown)
  window.removeEventListener('resize', positionEditor)
  window.removeEventListener('scroll', positionEditor, true)
})
</script>

<template>
  <section class="inventory-editor">
    <div class="inventory-game-layout">
      <div class="inventory-board">
        <nav class="container-tabs" :aria-label="tr('Inventory_ContainersAriaLabel')">
          <button
            v-for="container in backpackContainers"
            :key="container.container_type"
            type="button"
            :class="{ active: selectedContainerType === container.container_type }"
            :disabled="palStore.LOADING_FLAG"
            @click="selectedContainerType = container.container_type"
          >
            <span>{{ containerLabel(container.container_type) }}</span>
            <small>{{ occupiedCount(container) }}/{{ container.capacity ?? '—' }}</small>
          </button>
        </nav>

        <p v-if="!selectedContainer" class="inventory-message">{{ tr('Inventory_NoMetadata') }}</p>
        <p v-else-if="selectedContainer.status !== 'available'" class="inventory-message inventory-message--warning">
          {{ selectedContainer.reason || tr('Inventory_ContainerUnavailable') }}
        </p>
        <div
          v-else
          class="inventory-slot-grid"
          role="grid"
          :aria-label="containerLabel(selectedContainer.container_type)"
        >
          <button
            v-for="slot in displaySlots"
            :key="slot.slot_index"
            type="button"
            role="gridcell"
            :draggable="supportsSlotMove(selectedContainer) && slot.state === 'occupied' && !palStore.LOADING_FLAG"
            :disabled="!isSlotAvailable(selectedContainer, slot) || palStore.LOADING_FLAG"
            :aria-label="slotAriaLabel(slot)"
            :aria-selected="isSelectedSlot(selectedContainer, slot)"
            :data-slot-selected="isSelectedSlot(selectedContainer, slot)"
            :class="[
              'inventory-slot',
              slot.state === 'occupied' && `inventory-slot--rarity-${itemRarity(slot.item)}`,
              {
                'is-empty': slot.state === 'empty',
                'is-selected': isSelectedSlot(selectedContainer, slot),
                'is-dragging': draggedContainerType === selectedContainer.container_type && draggedSlotIndex === slot.slot_index,
                'is-drop-target': isDropTarget(selectedContainer, slot),
                'is-move-source': isMoveSource(selectedContainer, slot),
              },
            ]"
            :title="slot.state === 'occupied' ? `${slot.item.name || slot.item.static_id} · ${slot.item.static_id}` : ''"
            @click="onSlotClick($event, selectedContainer, slot)"
            @keydown="onSlotKeydown($event, selectedContainer, slot)"
            @dragstart="onDragStart($event, selectedContainer, slot)"
            @dragover="onDragOver($event, selectedContainer, slot)"
            @dragleave="onDragLeave($event, selectedContainer, slot)"
            @drop="onDrop($event, selectedContainer, slot)"
            @dragend="onDragEnd"
          >
            <span class="inventory-slot__index">{{ slot.slot_index + 1 }}</span>
            <template v-if="slot.state === 'occupied'">
              <ItemIcon
                class="inventory-slot__icon"
                :icon="slot.item.icon"
                :name="slot.item.name"
                :size="68"
              />
              <b v-if="shouldShowQuantity(slot.item)" class="inventory-slot__quantity">{{ slot.item.count }}</b>
            </template>
            <AppIcon v-else-if="slot.state === 'empty'" class="inventory-slot__plus" name="plus" :size="20" />
            <AppIcon v-else class="inventory-slot__warning" name="warning" :size="18" />
          </button>
        </div>
      </div>

      <section class="equipment-board" :aria-label="tr('Inventory_Container_ArmorEquipment')">
        <div class="equipment-stage">
          <div class="equipment-side equipment-side--left">
            <section
              v-for="section in leftEquipmentSections"
              :key="section.key"
              :class="['equipment-section', `equipment-section--${section.key}`]"
            >
              <h3>{{ tr(section.labelKey) }}</h3>
              <p v-if="!section.container || section.container.status !== 'available'" class="equipment-section__warning">
                {{ section.container?.reason || tr(section.container ? 'Inventory_ContainerUnavailable' : 'Inventory_NoMetadata') }}
              </p>
              <div v-else class="equipment-slot-grid" role="grid" :aria-label="tr(section.labelKey)">
                <button
                  v-for="slot in section.slots"
                  :key="slot.slot_index"
                  type="button"
                  role="gridcell"
                  :draggable="supportsSlotMove(section.container) && slot.state === 'occupied' && !palStore.LOADING_FLAG"
                  :disabled="!isSlotAvailable(section.container, slot) || palStore.LOADING_FLAG"
                  :aria-label="slotAriaLabel(slot)"
                  :aria-selected="isSelectedSlot(section.container, slot)"
                  :class="[
                    'equipment-slot',
                    slot.state === 'occupied' && `inventory-slot--rarity-${itemRarity(slot.item)}`,
                    {
                      'is-empty': slot.state === 'empty',
                      'is-selected': isSelectedSlot(section.container, slot),
                      'is-dragging': draggedContainerType === section.container?.container_type && draggedSlotIndex === slot.slot_index,
                      'is-drop-target': isDropTarget(section.container, slot),
                      'is-move-source': isMoveSource(section.container, slot),
                    },
                  ]"
                  :title="slot.state === 'occupied' ? `${slot.item.name || slot.item.static_id} · ${slot.item.static_id}` : ''"
                  @click="onSlotClick($event, section.container, slot)"
                  @keydown="onSlotKeydown($event, section.container, slot)"
                  @dragstart="onDragStart($event, section.container, slot)"
                  @dragover="onDragOver($event, section.container, slot)"
                  @dragleave="onDragLeave($event, section.container, slot)"
                  @drop="onDrop($event, section.container, slot)"
                  @dragend="onDragEnd"
                >
                  <span class="equipment-slot__index">{{ slot.slot_index + 1 }}</span>
                  <template v-if="slot.state === 'occupied'">
                    <ItemIcon class="equipment-slot__icon" :icon="slot.item.icon" :name="slot.item.name" :size="68" />
                    <b v-if="shouldShowQuantity(slot.item)" class="equipment-slot__quantity">{{ slot.item.count }}</b>
                  </template>
                  <AppIcon v-else-if="slot.state === 'empty'" class="equipment-slot__plus" name="plus" :size="18" />
                  <AppIcon v-else class="equipment-slot__warning" name="warning" :size="16" />
                </button>
              </div>
            </section>
          </div>

          <div class="equipment-stage__model" aria-hidden="true" />

          <div class="equipment-side equipment-side--right">
            <section
              v-for="section in rightEquipmentSections"
              :key="section.key"
              :class="['equipment-section', `equipment-section--${section.key}`]"
            >
              <h3>{{ tr(section.labelKey) }}</h3>
              <p v-if="!section.container || section.container.status !== 'available'" class="equipment-section__warning">
                {{ section.container?.reason || tr(section.container ? 'Inventory_ContainerUnavailable' : 'Inventory_NoMetadata') }}
              </p>
              <div v-else class="equipment-slot-grid" role="grid" :aria-label="tr(section.labelKey)">
                <button
                  v-for="slot in section.slots"
                  :key="slot.slot_index"
                  type="button"
                  role="gridcell"
                  :draggable="supportsSlotMove(section.container) && slot.state === 'occupied' && !palStore.LOADING_FLAG"
                  :disabled="!isSlotAvailable(section.container, slot) || palStore.LOADING_FLAG"
                  :aria-label="slotAriaLabel(slot)"
                  :aria-selected="isSelectedSlot(section.container, slot)"
                  :class="[
                    'equipment-slot',
                    slot.state === 'occupied' && `inventory-slot--rarity-${itemRarity(slot.item)}`,
                    {
                      'is-empty': slot.state === 'empty',
                      'is-selected': isSelectedSlot(section.container, slot),
                      'is-dragging': draggedContainerType === section.container?.container_type && draggedSlotIndex === slot.slot_index,
                      'is-drop-target': isDropTarget(section.container, slot),
                      'is-move-source': isMoveSource(section.container, slot),
                    },
                  ]"
                  :title="slot.state === 'occupied' ? `${slot.item.name || slot.item.static_id} · ${slot.item.static_id}` : ''"
                  @click="onSlotClick($event, section.container, slot)"
                  @keydown="onSlotKeydown($event, section.container, slot)"
                  @dragstart="onDragStart($event, section.container, slot)"
                  @dragover="onDragOver($event, section.container, slot)"
                  @dragleave="onDragLeave($event, section.container, slot)"
                  @drop="onDrop($event, section.container, slot)"
                  @dragend="onDragEnd"
                >
                  <span class="equipment-slot__index">{{ slot.slot_index + 1 }}</span>
                  <template v-if="slot.state === 'occupied'">
                    <ItemIcon class="equipment-slot__icon" :icon="slot.item.icon" :name="slot.item.name" :size="68" />
                    <b v-if="shouldShowQuantity(slot.item)" class="equipment-slot__quantity">{{ slot.item.count }}</b>
                  </template>
                  <AppIcon v-else-if="slot.state === 'empty'" class="equipment-slot__plus" name="plus" :size="18" />
                  <AppIcon v-else class="equipment-slot__warning" name="warning" :size="16" />
                </button>
              </div>
            </section>
          </div>

          <div v-if="bottomEquipmentSections.length" class="equipment-bottom">
            <section
              v-for="section in bottomEquipmentSections"
              :key="section.key"
              :class="['equipment-section', `equipment-section--${section.key}`]"
            >
              <h3>{{ tr(section.labelKey) }}</h3>
              <p v-if="!section.container || section.container.status !== 'available'" class="equipment-section__warning">
                {{ section.container?.reason || tr(section.container ? 'Inventory_ContainerUnavailable' : 'Inventory_NoMetadata') }}
              </p>
              <div v-else class="equipment-slot-grid" role="grid" :aria-label="tr(section.labelKey)">
                <button
                  v-for="slot in section.slots"
                  :key="slot.slot_index"
                  type="button"
                  role="gridcell"
                  :draggable="supportsSlotMove(section.container) && slot.state === 'occupied' && !palStore.LOADING_FLAG"
                  :disabled="!isSlotAvailable(section.container, slot) || palStore.LOADING_FLAG"
                  :aria-label="slotAriaLabel(slot)"
                  :aria-selected="isSelectedSlot(section.container, slot)"
                  :class="[
                    'equipment-slot',
                    slot.state === 'occupied' && `inventory-slot--rarity-${itemRarity(slot.item)}`,
                    {
                      'is-empty': slot.state === 'empty',
                      'is-selected': isSelectedSlot(section.container, slot),
                      'is-dragging': draggedContainerType === section.container?.container_type && draggedSlotIndex === slot.slot_index,
                      'is-drop-target': isDropTarget(section.container, slot),
                      'is-move-source': isMoveSource(section.container, slot),
                    },
                  ]"
                  :title="slot.state === 'occupied' ? `${slot.item.name || slot.item.static_id} · ${slot.item.static_id}` : ''"
                  @click="onSlotClick($event, section.container, slot)"
                  @keydown="onSlotKeydown($event, section.container, slot)"
                  @dragstart="onDragStart($event, section.container, slot)"
                  @dragover="onDragOver($event, section.container, slot)"
                  @dragleave="onDragLeave($event, section.container, slot)"
                  @drop="onDrop($event, section.container, slot)"
                  @dragend="onDragEnd"
                >
                  <span class="equipment-slot__index">{{ slot.slot_index + 1 }}</span>
                  <template v-if="slot.state === 'occupied'">
                    <ItemIcon class="equipment-slot__icon" :icon="slot.item.icon" :name="slot.item.name" :size="68" />
                    <b v-if="shouldShowQuantity(slot.item)" class="equipment-slot__quantity">{{ slot.item.count }}</b>
                  </template>
                  <AppIcon v-else-if="slot.state === 'empty'" class="equipment-slot__plus" name="plus" :size="18" />
                  <AppIcon v-else class="equipment-slot__warning" name="warning" :size="16" />
                </button>
              </div>
            </section>
          </div>
        </div>
      </section>
    </div>
    <p v-if="moveStatus" class="move-status" aria-live="polite">{{ moveStatus }}</p>

    <Teleport to="body">
      <section
        v-if="selectedSlot?.state === 'occupied'"
        ref="editorPanel"
        class="inventory-slot-editor"
        :style="editorStyle"
        role="group"
        :aria-label="slotAriaLabel(selectedSlot)"
      >
        <header>
          <ItemIcon
            :icon="selectedSlot.item.icon"
            :name="selectedSlot.item.name"
            :size="38"
          />
          <div>
            <strong>{{ selectedSlot.item.name || selectedSlot.item.static_id }}</strong>
            <small>{{ selectedSlot.item.static_id }}</small>
          </div>
          <button
            type="button"
            class="inventory-slot-editor__close"
            :title="tr('Common_Close')"
            :aria-label="tr('Common_Close')"
            @click="clearSlotSelection"
          >
            <AppIcon name="x" :size="16" />
          </button>
        </header>

        <label v-if="selectedCountEditable" class="inventory-slot-editor__count">
          <span>
            {{ tr('Inventory_Count') }}
            <small>{{ tr('Inventory_ItemPicker_MaxStack', [selectedMaxStack]) }}</small>
          </span>
          <span>
            <input
              v-model.number="countDraft"
              type="number"
              min="1"
              :max="selectedMaxStack"
              step="1"
              :disabled="palStore.LOADING_FLAG"
              :aria-label="tr('Inventory_ItemCountAriaLabel')"
              @keydown.enter.prevent="saveCount"
            >
            <button type="button" :disabled="palStore.LOADING_FLAG" @click="setMaxCount">
              {{ tr('Inventory_Max') }}
            </button>
          </span>
        </label>

        <div class="inventory-slot-editor__actions">
          <button
            v-if="selectedCountEditable"
            type="button"
            :disabled="palStore.LOADING_FLAG || !countDraftValid"
            @click="saveCount"
          >
            <AppIcon name="check" :size="15" />
            {{ tr('Inventory_SaveCountTitle') }}
          </button>
          <button
            type="button"
            :disabled="palStore.LOADING_FLAG"
            @click="openAddDialog(selectedSlotContainer, selectedSlot, 'replace')"
          >
            <AppIcon name="edit" :size="15" />
            {{ tr('Guild_BaseStorageReplace') }}
          </button>
          <button
            type="button"
            :disabled="palStore.LOADING_FLAG"
            @click="copySelectedSlot"
          >
            <AppIcon name="copy" :size="15" />
            {{ tr('Inventory_CopySlotTitle') }}
          </button>
          <button
            v-if="supportsSlotMove(selectedSlotContainer)"
            type="button"
            :class="{ active: isMoveSource(selectedSlotContainer, selectedSlot) }"
            :disabled="palStore.LOADING_FLAG"
            @click="toggleMoveSource(selectedSlotContainer, selectedSlot)"
          >
            <AppIcon name="refresh" :size="15" />
            {{ tr(isMoveSource(selectedSlotContainer, selectedSlot) ? 'Inventory_MoveModeCancel' : 'Inventory_MoveSlotAction') }}
          </button>
          <button
            v-if="selectedSlot.item.dynamic_kind !== 'none'"
            type="button"
            :class="{ active: dynamicEditors[String(selectedSlot.slot_index)] }"
            :disabled="palStore.LOADING_FLAG"
            @click="toggleDynamicEditor(selectedSlot)"
          >
            <AppIcon name="settings" :size="15" />
            {{ tr('Inventory_EditDynamicTitle') }}
          </button>
          <button
            type="button"
            class="is-danger"
            :disabled="palStore.LOADING_FLAG"
            @click="clearSelectedSlot"
          >
            <AppIcon name="trash" :size="15" />
            {{ tr('Inventory_ClearSlotTitle') }}
          </button>
        </div>

        <div
          v-if="dynamicEditors[String(selectedSlot.slot_index)]"
          class="dynamic-editor"
        >
          <header>
            <strong>{{ tr('Inventory_DynamicAttributes', [dynamicKindLabel(dynamicEditors[String(selectedSlot.slot_index)].dynamic_kind)]) }}</strong>
            <small>{{ tr('Inventory_DynamicWritableHint') }}</small>
          </header>
          <p v-if="dynamicEditors[String(selectedSlot.slot_index)].writable_fields.length === 0">
            {{ tr('Inventory_NoEditableDynamicFields') }}
          </p>
          <label
            v-for="field in dynamicEditors[String(selectedSlot.slot_index)].writable_fields"
            :key="field"
          >
            <span>{{ dynamicFieldLabel(field) }}</span>
            <input
              v-model="dynamicEditors[String(selectedSlot.slot_index)].values[field]"
              :type="Array.isArray(dynamicEditors[String(selectedSlot.slot_index)].original[field]) ? 'text' : 'number'"
              min="0"
              step="any"
            >
          </label>
          <button
            v-if="dynamicEditors[String(selectedSlot.slot_index)].writable_fields.length"
            type="button"
            :disabled="palStore.LOADING_FLAG"
            @click="saveDynamic(selectedSlot)"
          >
            {{ tr('Inventory_SaveDynamicFields') }}
          </button>
        </div>
      </section>
    </Teleport>

    <ItemPicker
      ref="addPicker"
      v-model="selectedStaticId"
      v-model:quantity="addCount"
      :options="palStore.ITEM_CATALOG_RESULTS"
      :selected-option="selectedCatalogItem"
      :disabled="palStore.LOADING_FLAG"
      :confirm-disabled="!dynamicInitializerValid"
      trigger-hidden
      show-quantity
      @confirm="confirmAdd"
    >
      <template #details>
        <button
          v-if="pendingMode === 'empty_only' && palStore.ITEM_CLIPBOARD"
          type="button"
          class="picker-paste-action"
          :disabled="palStore.LOADING_FLAG"
          @click="pasteIntoPendingSlot"
        >
          <AppIcon name="copy" :size="15" />
          {{ tr('Inventory_Paste') }}
        </button>
        <div v-if="selectedCatalogItem && dynamicKind !== 'none'" class="picker-dynamic-fields">
          <div class="picker-dynamic-fields__heading">
            <strong>{{ tr('Inventory_NewDynamicRecord', [dynamicKindLabel(dynamicKind)]) }}</strong>
            <small>{{ tr('Inventory_IndependentDynamicRecord') }}</small>
          </div>
          <label>
            <span>{{ tr('Inventory_RecordItemId') }}</span>
            <input v-model="dynamicRecordStaticId" autocomplete="off" spellcheck="false">
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
            <input v-model="dynamicPassiveTraits" :placeholder="tr('Inventory_PassiveTraitsPlaceholder')">
          </label>
          <label v-if="dynamicKind === 'egg'" class="picker-dynamic-fields__egg">
            <span>{{ tr('Inventory_EggSpecies') }}</span>
            <PalSpeciesPicker v-model="eggCharacterId" :options="eggSpecies" :selected-option="selectedEggSpecies" :disabled="palStore.LOADING_FLAG" show-internal-name :title="tr('Inventory_SelectEggSpecies')" :placeholder="tr('Inventory_EggSpeciesPlaceholder')" />
          </label>
          <p v-if="!dynamicInitializerValid" class="picker-dynamic-fields__error">{{ tr('Inventory_DynamicRequired') }}</p>
        </div>
      </template>
    </ItemPicker>
  </section>
</template>

<style scoped>
.inventory-editor {
  height: 100%;
  width: 100%;
  min-width: 0;
  min-height: 710px;
  container-type: inline-size;
  color: var(--ui-text);
}

.inventory-game-layout {
  --inventory-slot-size: clamp(48.5px, calc(6cqw - 11.5px), 101.84px);
  display: grid;
  height: 100%;
  min-height: 710px;
  grid-template-columns: clamp(360px, 36%, 680px) minmax(360px, 1fr);
  align-items: stretch;
  gap: 0;
  overflow: hidden;
  background-color: oklch(0.13 0.025 225);
  background-image: url('/images/Pal/Texture/UI/Main_Menu/T_prt_pal_skill_base_02.webp');
  background-position: center;
  background-size: 280px 36px;
  background-blend-mode: soft-light;
  border: 1px solid var(--ui-border-strong);
  border-radius: var(--ui-radius-md);
  box-shadow: inset 0 1px 0 oklch(1 0 0 / .05);
}

.inventory-board {
  display: grid;
  height: 100%;
  min-width: 0;
  min-height: 0;
  grid-template-rows: auto minmax(0, 1fr);
  overflow: hidden;
  background: oklch(0.105 0.02 225 / .94);
  border-right: 1px solid oklch(0.7 0.03 220 / .38);
}

.container-tabs {
  display: flex;
  min-width: 0;
  overflow-x: auto;
  padding: 5px;
  border-bottom: 1px solid oklch(0.72 0.035 220 / .45);
  scrollbar-width: thin;
}

.container-tabs button {
  position: relative;
  display: grid;
  min-width: 118px;
  min-height: 44px;
  flex: 1 0 auto;
  align-content: center;
  gap: 2px;
  padding: 7px 12px;
  color: var(--ui-text-muted);
  background: oklch(0.17 0.02 220 / .76);
  border: 1px solid transparent;
  border-right-color: oklch(0.72 0.035 220 / .28);
  border-radius: 0;
  text-align: left;
  transition: color 160ms ease, background-color 160ms ease;
}

.container-tabs button::after {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  height: 3px;
  background: transparent;
  content: '';
}

.container-tabs button:hover:not(:disabled) {
  color: var(--ui-text);
  background: oklch(0.24 0.035 220 / .86);
}

.container-tabs button:active:not(:disabled) { transform: translateY(1px); }
.container-tabs button:focus-visible { z-index: 1; outline: 2px solid var(--ui-accent); outline-offset: -3px; }
.container-tabs button.active {
  color: oklch(0.22 0.022 220);
  background: oklch(0.79 0.035 215);
  border-color: oklch(0.9 0.025 210 / .5);
}
.container-tabs button.active::after { background: var(--ui-accent); }
.container-tabs button.active small { color: oklch(0.37 0.025 220); }
.container-tabs span { font-size: 11px; font-weight: 700; white-space: nowrap; }
.container-tabs small { color: var(--ui-text-muted); font-size: 8px; font-variant-numeric: tabular-nums; }

.inventory-slot-grid {
  display: grid;
  min-height: 0;
  grid-template-columns: repeat(6, minmax(44px, 1fr));
  grid-auto-rows: max-content;
  align-content: start;
  gap: 6px;
  padding: 12px;
  overflow-y: auto;
  scrollbar-gutter: stable;
}

.equipment-board {
  height: 100%;
  min-width: 0;
  padding: 18px 16px;
  overflow: hidden;
  background: oklch(0.145 0.023 220 / .84);
}

.equipment-stage {
  display: grid;
  height: 100%;
  min-height: 0;
  grid-template-columns:
    minmax(130px, .95fr)
    minmax(44px, 1.05fr)
    minmax(86px, .68fr);
  grid-template-rows: minmax(0, 1fr) auto;
  gap: 20px 13px;
}

.equipment-side {
  display: flex;
  min-width: 0;
  flex-direction: column;
}

.equipment-side--left {
  grid-column: 1;
  grid-row: 1;
  justify-content: space-between;
}

.equipment-side--right {
  grid-column: 3;
  grid-row: 1 / 3;
  width: var(--inventory-slot-size);
  justify-self: end;
  justify-content: space-between;
}

.equipment-stage__model {
  min-width: 0;
  grid-column: 2;
  grid-row: 1;
}

.equipment-section {
  min-width: 0;
}

.equipment-section h3 {
  display: flex;
  min-height: 27px;
  align-items: center;
  margin: 0;
  margin-bottom: 7px;
  padding: 0 9px;
  overflow: hidden;
  color: oklch(0.83 0.1 205);
  border-left: 3px solid oklch(0.82 0.14 205);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.equipment-section__warning {
  margin: 0;
  color: var(--ui-danger);
  font-size: 9px;
}

.equipment-slot-grid {
  display: grid;
  grid-template-columns: repeat(2, var(--inventory-slot-size));
  gap: 7px;
}

.equipment-section--weapon .equipment-slot-grid {
  grid-auto-columns: var(--inventory-slot-size);
  grid-auto-flow: column;
  grid-template-columns: none;
  grid-template-rows: repeat(4, var(--inventory-slot-size));
}

.equipment-section--head .equipment-slot-grid,
.equipment-section--body .equipment-slot-grid,
.equipment-section--shield .equipment-slot-grid,
.equipment-section--glider .equipment-slot-grid,
.equipment-section--sphere-module .equipment-slot-grid {
  grid-template-columns: var(--inventory-slot-size);
}

.equipment-bottom {
  display: grid;
  align-self: end;
  align-items: end;
  grid-column: 1 / 3;
  grid-row: 2;
  grid-template-columns: max-content minmax(0, 1fr);
  gap: 18px;
}

.equipment-section--food .equipment-slot-grid {
  grid-template-columns: repeat(5, var(--inventory-slot-size));
}

.equipment-slot { width: 100%; }

.inventory-slot,
.equipment-slot {
  --slot-rarity: var(--ui-border-strong);
  position: relative;
  display: grid;
  min-width: 0;
  min-height: 0;
  aspect-ratio: 1;
  place-items: center;
  padding: 7px;
  overflow: hidden;
  color: var(--ui-text);
  background: oklch(0.115 0.018 224 / .9);
  border: 1px solid oklch(0.72 0.035 220 / .32);
  border-bottom: 3px solid var(--slot-rarity);
  border-radius: 0;
  box-shadow: inset 0 0 0 1px oklch(1 0 0 / .025);
  transition: background-color 160ms ease, border-color 160ms ease, transform 160ms ease;
}

.inventory-slot:hover:not(:disabled),
.equipment-slot:hover:not(:disabled) {
  z-index: 1;
  background: oklch(0.2 0.03 220 / .96);
  border-color: var(--slot-rarity);
  transform: translateY(-2px);
}

.inventory-slot:focus-visible,
.inventory-slot.is-selected,
.inventory-slot.is-drop-target,
.equipment-slot:focus-visible,
.equipment-slot.is-selected,
.equipment-slot.is-drop-target {
  border-color: var(--ui-accent);
  outline: 0;
  box-shadow: inset 0 0 0 1px var(--ui-accent);
}

.inventory-slot--rarity-1 { --slot-rarity: oklch(0.69 0.06 235); }
.inventory-slot--rarity-2 { --slot-rarity: oklch(0.71 0.13 230); }
.inventory-slot--rarity-3 { --slot-rarity: oklch(0.69 0.16 310); }
.inventory-slot--rarity-4,
.inventory-slot--rarity-5 { --slot-rarity: oklch(0.8 0.15 90); }

.inventory-slot.is-empty,
.equipment-slot.is-empty {
  padding: 0;
  color: var(--ui-text-muted);
  background: oklch(0.125 0.015 225 / .72);
  border-bottom-width: 1px;
  border-style: dashed;
  opacity: .76;
}

.inventory-slot.is-empty:hover:not(:disabled),
.equipment-slot.is-empty:hover:not(:disabled) {
  color: var(--ui-accent);
  border-color: var(--ui-accent);
}

.inventory-slot[draggable="true"],
.equipment-slot[draggable="true"] { cursor: grab; }
.inventory-slot.is-dragging,
.equipment-slot.is-dragging { opacity: .52; cursor: grabbing; }
.inventory-slot.is-move-source,
.equipment-slot.is-move-source { outline: 2px solid var(--ui-accent); outline-offset: 1px; }

.inventory-slot__index,
.equipment-slot__index {
  position: absolute;
  top: 4px;
  left: 5px;
  color: var(--ui-text-muted);
  font-size: 8px;
  font-variant-numeric: tabular-nums;
  opacity: .66;
}

.inventory-slot__icon,
.equipment-slot__icon {
  position: absolute;
  top: 50%;
  left: 50%;
  display: block;
  width: calc(100% - 14px);
  height: calc(100% - 14px);
  max-width: calc(100% - 14px);
  max-height: calc(100% - 14px);
  object-fit: contain;
  filter: drop-shadow(0 5px 7px color-mix(in srgb, var(--ui-canvas) 58%, transparent));
  transform: translate(-50%, -50%);
  pointer-events: none;
}

.inventory-slot__quantity,
.equipment-slot__quantity {
  position: absolute;
  right: 3px;
  bottom: 3px;
  min-width: 16px;
  padding: 1px 3px;
  color: var(--ui-text);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
  text-align: right;
  background: oklch(0.07 0.015 225 / .78);
  border-radius: 3px;
  text-shadow: 0 1px 2px var(--ui-canvas);
}

.inventory-slot__plus,
.equipment-slot__plus { pointer-events: none; }

.inventory-message { margin: 0; padding: 14px; color: var(--ui-text-muted); }
.inventory-message--warning { color: var(--ui-danger); }
.move-status { margin: 10px 0 0; color: var(--ui-accent); font-size: 11px; }

.inventory-slot-editor {
  position: fixed;
  z-index: 120;
  display: grid;
  width: 304px;
  max-height: calc(100dvh - 24px);
  gap: 12px;
  padding: 12px;
  overflow-y: auto;
  color: var(--ui-text);
  background: var(--ui-surface);
  border: 1px solid var(--ui-border-strong);
  border-radius: var(--ui-radius-sm);
  box-shadow: 0 8px 24px color-mix(in srgb, #000 32%, transparent);
}

.inventory-slot-editor > header {
  display: flex;
  align-items: center;
  gap: 9px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--ui-border);
}

.inventory-slot-editor > header > div { display: grid; min-width: 0; flex: 1 1 auto; gap: 2px; }
.inventory-slot-editor > header strong,
.inventory-slot-editor > header small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.inventory-slot-editor > header strong { font-size: 12px; }
.inventory-slot-editor > header small { color: var(--ui-text-muted); font-size: 9px; }

.inventory-slot-editor__close {
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

.inventory-slot-editor__close:hover,
.inventory-slot-editor__close:focus-visible { color: var(--ui-text); background: var(--ui-surface-hover); }

.inventory-slot-editor__count { display: grid; gap: 5px; }
.inventory-slot-editor__count > span { display: flex; align-items: center; justify-content: space-between; gap: 8px; color: var(--ui-text-secondary); font-size: 10px; font-weight: 700; }
.inventory-slot-editor__count small { color: var(--ui-text-muted); font-size: 9px; font-weight: 500; }
.inventory-slot-editor__count input {
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
.inventory-slot-editor__count input:focus { border-color: var(--ui-accent); outline: 0; box-shadow: 0 0 0 2px color-mix(in srgb, var(--ui-accent) 22%, transparent); }
.inventory-slot-editor__count button { height: 34px; padding: 0 10px; color: var(--ui-accent); background: var(--ui-accent-soft); border: 0; border-radius: 6px; font-size: 10px; font-weight: 800; }

.inventory-slot-editor__actions { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px; }
.inventory-slot-editor__actions button {
  display: inline-flex;
  min-height: 32px;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 0 8px;
  color: var(--ui-accent);
  background: var(--ui-accent-soft);
  border: 0;
  border-radius: 6px;
  font-size: 9.5px;
  font-weight: 700;
}
.inventory-slot-editor__actions button.active { color: var(--ui-text); box-shadow: inset 0 0 0 1px var(--ui-accent); }
.inventory-slot-editor__actions button.is-danger { color: var(--ui-danger); background: var(--ui-danger-soft); }
.inventory-slot-editor button:disabled { cursor: not-allowed; opacity: .55; }

.dynamic-editor {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 7px;
  padding-top: 9px;
  border-top: 1px solid var(--ui-border);
}
.dynamic-editor header { display: grid; }
.dynamic-editor header small,
.dynamic-editor label span { color: var(--ui-text-muted); font-size: 10px; }
.dynamic-editor label { display: grid; gap: 3px; }
.dynamic-editor input { min-height: 32px; padding: 0 7px; border: 1px solid var(--ui-border); border-radius: 6px; color: var(--ui-text); background: var(--ui-canvas); }
.dynamic-editor button { min-height: 32px; align-self: end; border: 0; border-radius: 6px; color: var(--ui-text); background: var(--ui-accent-soft); }

.picker-paste-action {
  display: inline-flex;
  min-height: 34px;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 0 11px;
  color: var(--ui-accent);
  background: var(--ui-accent-soft);
  border: 1px solid color-mix(in srgb, var(--ui-accent) 38%, var(--ui-border));
  border-radius: 6px;
  font-size: 10px;
  font-weight: 700;
}

.picker-dynamic-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; padding: 10px; border: 1px solid var(--ui-accent); border-radius: var(--ui-radius-sm); background: var(--ui-accent-soft); }
.picker-dynamic-fields__heading { display: grid; grid-column: 1 / -1; gap: 2px; }
.picker-dynamic-fields__heading small,
.picker-dynamic-fields label span { color: var(--ui-text-muted); font-size: 10px; }
.picker-dynamic-fields label { display: grid; gap: 4px; color: var(--ui-text-secondary); font-size: 11px; }
.picker-dynamic-fields input { min-height: 34px; padding: 0 8px; color: var(--ui-text); background: var(--ui-surface); border: 1px solid var(--ui-border); border-radius: 6px; }
.picker-dynamic-fields__egg { grid-column: 1 / -1; }
.picker-dynamic-fields__error { grid-column: 1 / -1; margin: 0; color: var(--ui-danger); font-size: 11px; }

@media (max-width: 920px) {
  .inventory-game-layout {
    grid-template-columns: minmax(300px, .9fr) minmax(360px, 1.1fr);
  }
}

@media (max-width: 700px) {
  .inventory-editor {
    height: auto;
    min-height: 0;
  }

  .inventory-game-layout {
    height: auto;
    min-height: 0;
    grid-template-columns: minmax(0, 1fr);
  }

  .inventory-board {
    height: 520px;
    min-height: 520px;
    border-right: 0;
    border-bottom: 1px solid var(--ui-border-strong);
  }

  .equipment-board { height: auto; min-height: 560px; }
  .equipment-stage { height: auto; min-height: 520px; }
}

@media (max-width: 620px) {
  .inventory-slot-grid {
    grid-template-columns: repeat(6, minmax(38px, 1fr));
    gap: 4px;
    padding: 8px;
  }

  .inventory-slot-editor {
    right: 12px !important;
    bottom: 12px;
    left: 12px !important;
    top: auto !important;
    width: auto;
    visibility: visible !important;
  }

  .equipment-board { padding: 14px 10px; }

  .picker-dynamic-fields { grid-template-columns: minmax(0, 1fr); }
  .picker-dynamic-fields__heading,
  .picker-dynamic-fields__egg,
  .picker-dynamic-fields__error { grid-column: auto; }
}

@media (prefers-reduced-motion: reduce) {
  .container-tabs button,
  .inventory-slot,
  .equipment-slot { transition: none; }
}
</style>
