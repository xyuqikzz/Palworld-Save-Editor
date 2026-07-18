<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { usePalEditorStore } from '@/stores/paleditor'
import AppIcon from '@/components/modules/AppIcon.vue'
import ItemIcon from '@/components/modules/ItemIcon.vue'
import ItemPicker from '@/components/modules/ItemPicker.vue'
import PalSpeciesPicker from '@/components/modules/PalSpeciesPicker.vue'

const palStore = usePalEditorStore()
const selectedContainerType = ref('COMMON')
const selectedStaticId = ref('')
const addCount = ref(1)
const pendingSlot = ref(null)
const addPicker = ref(null)
const dynamicRecordStaticId = ref('')
const dynamicDurability = ref(0)
const dynamicAmmo = ref(0)
const dynamicPassiveTraits = ref('')
const eggCharacterId = ref('')
const dynamicEditors = ref({})

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
const selectedContainer = computed(() =>
  containers.value.find(container => container.container_type === selectedContainerType.value)
    || containers.value[0]
)
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
const visibleSlots = computed(() => selectedContainer.value?.slots || [])
const occupiedCount = container => container.slots.filter(slot => slot.state === 'occupied').length

async function loadCatalog() {
  const results = await palStore.searchItemCatalog('', selectedContainerType.value)
  if (!results.some(item => item.static_id === selectedStaticId.value)) {
    selectedStaticId.value = results[0]?.static_id || ''
  }
}

async function addToSlot(slot) {
  if (!selectedStaticId.value || !dynamicInitializerValid.value) return
  await palStore.putInventoryItem(
    selectedContainer.value,
    slot,
    selectedStaticId.value,
    addCount.value,
    buildDynamicInit(),
  )
}

function itemMaxStack(staticId) {
  return Math.max(1, Number(palStore.ITEM_CATALOG_RESULTS.find(item => item.static_id === staticId)?.max_stack) || 1)
}

async function openAddDialog(slot) {
  pendingSlot.value = slot
  selectedStaticId.value = ''
  addCount.value = 1
  await loadCatalog()
  addPicker.value?.open()
}

async function confirmAdd({ item, quantity }) {
  selectedStaticId.value = item.static_id
  addCount.value = quantity
  if (pendingSlot.value && dynamicInitializerValid.value) {
    await addToSlot(pendingSlot.value)
  }
  pendingSlot.value = null
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
    return
  }
  const data = await palStore.loadDynamicItemAttributes(selectedContainer.value, slot)
  if (!data) return
  const values = Object.fromEntries(Object.entries(data.attributes).map(([field, value]) => [
    field,
    Array.isArray(value) ? value.join(', ') : value,
  ]))
  dynamicEditors.value = {
    ...dynamicEditors.value,
    [key]: { ...data, original: data.attributes, values },
  }
}

async function saveDynamic(slot) {
  const panel = dynamicEditors.value[String(slot.slot_index)]
  const values = Object.fromEntries(Object.entries(panel.values).map(([field, value]) => {
    if (Array.isArray(panel.original[field])) {
      return [field, String(value).split(',').map(item => item.trim()).filter(Boolean)]
    }
    return [field, Number(value)]
  }))
  if (await palStore.updateDynamicItemAttributes(selectedContainer.value, slot, values)) {
    dynamicEditors.value = {}
  }
}

watch(selectedContainerType, () => {
  dynamicEditors.value = {}
  selectedStaticId.value = ''
  loadCatalog()
})
watch(selectedStaticId, staticId => {
  dynamicRecordStaticId.value = staticId || ''
  dynamicDurability.value = 0
  dynamicAmmo.value = 0
  dynamicPassiveTraits.value = ''
  eggCharacterId.value = ''
})
onMounted(loadCatalog)
</script>

<template>
  <section class="inventory-editor" aria-labelledby="inventory-title">
    <header class="inventory-heading">
      <div>
        <p class="eyebrow">{{ tr('Inventory_Eyebrow') }}</p>
        <h2 id="inventory-title">{{ palStore.getTranslatedText('Editor_Inventory') }}</h2>
      </div>
      <span v-if="selectedContainer" class="capacity">
        {{ occupiedCount(selectedContainer) }} / {{ selectedContainer.capacity ?? '—' }}
      </span>
    </header>

    <nav class="container-tabs" :aria-label="tr('Inventory_ContainersAriaLabel')">
      <button
        v-for="container in containers"
        :key="container.container_type"
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
    <div v-else class="slot-grid">
      <article
        v-for="slot in visibleSlots"
        :key="slot.slot_index"
        :class="['slot-card', { empty: slot.state === 'empty' }]"
      >
        <span class="slot-index">#{{ slot.slot_index }}</span>
        <template v-if="slot.state === 'occupied'">
          <div class="slot-main">
            <ItemIcon :icon="slot.item.icon" :name="slot.item.name" :size="44" />
            <div class="slot-copy">
              <strong>{{ slot.item.name || slot.item.static_id }}</strong>
              <small>{{ slot.item.static_id }}</small>
              <small v-if="slot.item.dynamic_kind !== 'none'" class="dynamic-kind">
                {{ dynamicKindLabel(slot.item.dynamic_kind) }} · {{ tr('Inventory_Linked') }}
              </small>
            </div>
            <input
              v-model.number="slot.item.count"
              class="slot-count"
              type="number"
              min="1"
              :max="itemMaxStack(slot.item.static_id)"
              step="1"
              :aria-label="tr('Inventory_ItemCountAriaLabel')"
            >
          </div>
          <div class="slot-actions">
            <button
              type="button"
              class="max-action"
              :disabled="palStore.LOADING_FLAG"
              @click="slot.item.count = itemMaxStack(slot.item.static_id)"
            >{{ tr('Inventory_Max') }}</button>
            <button
              class="icon-action"
              :disabled="palStore.LOADING_FLAG"
              :title="tr('Inventory_SaveCountTitle')"
              @click="palStore.updateInventoryItem(selectedContainer, slot)"
            ><AppIcon name="check" :size="15" /></button>
            <button
              class="icon-action"
              :disabled="palStore.LOADING_FLAG"
              :title="tr('Inventory_CopySlotTitle')"
              @click="palStore.copyInventoryItem(selectedContainer, slot)"
            ><AppIcon name="copy" :size="15" /></button>
            <button
              v-if="slot.item.dynamic_kind !== 'none'"
              class="icon-action"
              :disabled="palStore.LOADING_FLAG"
              :title="tr('Inventory_EditDynamicTitle')"
              @click="toggleDynamicEditor(slot)"
            ><AppIcon name="settings" :size="15" /></button>
            <button
              class="icon-action danger"
              :disabled="palStore.LOADING_FLAG"
              :title="tr('Inventory_ClearSlotTitle')"
              @click="palStore.clearInventoryItem(selectedContainer, slot)"
            ><AppIcon name="trash" :size="15" /></button>
          </div>
          <div v-if="dynamicEditors[String(slot.slot_index)]" class="dynamic-editor">
            <header>
              <strong>{{ tr('Inventory_DynamicAttributes', [dynamicKindLabel(dynamicEditors[String(slot.slot_index)].dynamic_kind)]) }}</strong>
              <small>{{ tr('Inventory_DynamicWritableHint') }}</small>
            </header>
            <p v-if="dynamicEditors[String(slot.slot_index)].writable_fields.length === 0">
              {{ tr('Inventory_NoEditableDynamicFields') }}
            </p>
            <label
              v-for="field in dynamicEditors[String(slot.slot_index)].writable_fields"
              :key="field"
            >
              <span>{{ dynamicFieldLabel(field) }}</span>
              <input
                v-model="dynamicEditors[String(slot.slot_index)].values[field]"
                :type="Array.isArray(dynamicEditors[String(slot.slot_index)].original[field]) ? 'text' : 'number'"
                min="0"
                step="any"
              >
            </label>
            <button
              v-if="dynamicEditors[String(slot.slot_index)].writable_fields.length"
              :disabled="palStore.LOADING_FLAG"
              @click="saveDynamic(slot)"
            >{{ tr('Inventory_SaveDynamicFields') }}</button>
          </div>
        </template>
        <template v-else>
          <div class="empty-copy">
            <strong>{{ tr('Inventory_EmptySlot') }}</strong>
            <small>{{ tr('Inventory_ChooseCatalogItem') }}</small>
          </div>
          <button
            class="add-action"
            :disabled="palStore.LOADING_FLAG"
            @click="openAddDialog(slot)"
          ><AppIcon name="plus" :size="15" /> {{ tr('Inventory_Add') }}</button>
          <button
            class="add-action"
            :disabled="palStore.LOADING_FLAG || !palStore.ITEM_CLIPBOARD"
            @click="palStore.pasteInventoryItem(selectedContainer, slot)"
          ><AppIcon name="copy" :size="15" /> {{ tr('Inventory_Paste') }}</button>
        </template>
      </article>
    </div>
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
  width: 100%;
  min-width: 0;
  padding: 22px;
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-md);
  background: var(--ui-surface);
}

.inventory-heading,
.slot-card {
  display: flex;
  align-items: center;
}

.inventory-heading { justify-content: space-between; gap: 20px; }
.inventory-heading h2 { margin: 2px 0 0; font-size: 20px; }
.eyebrow { margin: 0; color: var(--ui-accent); font-size: 11px; letter-spacing: .08em; text-transform: uppercase; }
.capacity { color: var(--ui-text-secondary); font-variant-numeric: tabular-nums; }

.container-tabs {
  display: grid;
  grid-template-columns: repeat(5, minmax(112px, 1fr));
  gap: 6px;
  margin: 18px 0;
  overflow-x: auto;
}

.container-tabs button {
  min-width: 112px;
  padding: 9px 10px;
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
  color: var(--ui-text-secondary);
  background: var(--ui-surface-raised);
  text-align: left;
}
.container-tabs button span,
.container-tabs button small { display: block; }
.container-tabs button span { font-size: 11px; font-weight: 650; }
.container-tabs button small { margin-top: 2px; color: var(--ui-text-muted); }
.container-tabs button.active { border-color: var(--ui-accent); color: var(--ui-text); background: var(--ui-accent-soft); }

.picker-dynamic-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; padding: 10px; border: 1px solid var(--ui-accent); border-radius: var(--ui-radius-sm); background: var(--ui-accent-soft); }
.picker-dynamic-fields__heading { display: grid; grid-column: 1 / -1; gap: 2px; }
.picker-dynamic-fields__heading small,
.picker-dynamic-fields label span { color: var(--ui-text-muted); font-size: 10px; }
.picker-dynamic-fields label { display: grid; gap: 4px; color: var(--ui-text-secondary); font-size: 11px; }
.picker-dynamic-fields input { min-height: 34px; padding: 0 8px; color: var(--ui-text); background: var(--ui-surface); border: 1px solid var(--ui-border); border-radius: 6px; }
.picker-dynamic-fields__egg { grid-column: 1 / -1; }
.picker-dynamic-fields__error { grid-column: 1 / -1; margin: 0; color: var(--ui-danger); font-size: 11px; }
.slot-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(330px, 1fr)); gap: 8px; }
.slot-card {
  position: relative;
  min-height: 82px;
  gap: 8px;
  padding: 16px 9px 9px;
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
  background: var(--ui-surface-raised);
  flex-wrap: wrap;
}
.slot-card.empty { border-style: dashed; background: transparent; }
.slot-index { position: absolute; top: 3px; left: 8px; color: var(--ui-text-muted); font-size: 10px; }
.slot-main { display: flex; align-items: center; flex: 1 0 100%; min-width: 0; gap: 8px; }
.slot-actions { display: flex; flex: 1 0 100%; justify-content: flex-end; gap: 6px; }
.slot-copy,
.empty-copy { display: grid; min-width: 0; flex: 1; }
.slot-copy strong,
.slot-copy small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.slot-copy small,
.empty-copy small { color: var(--ui-text-muted); font-size: 10px; }
.dynamic-kind { color: var(--ui-accent) !important; }
.slot-count { flex: 0 0 70px; width: 70px; min-height: 32px; padding: 0 7px; border: 1px solid var(--ui-border); border-radius: 6px; color: var(--ui-text); background: var(--ui-canvas); }
.icon-action,
.add-action,
.max-action { min-height: 32px; border: 0; border-radius: 6px; color: var(--ui-text); background: var(--ui-accent-soft); }
.max-action { padding: 0 8px; color: var(--ui-accent); font-size: 10px; font-weight: 700; }
.icon-action { display: grid; width: 32px; place-content: center; }
.icon-action.danger { color: var(--ui-danger); background: var(--ui-danger-soft); }
.add-action { display: inline-flex; align-items: center; gap: 5px; padding: 0 10px; }
.inventory-message { color: var(--ui-text-muted); }
.inventory-message--warning { color: var(--ui-danger); }
.dynamic-editor {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  flex: 1 0 100%;
  gap: 7px;
  padding-top: 9px;
  border-top: 1px solid var(--ui-border);
}
.dynamic-editor header { display: grid; grid-column: 1 / -1; }
.dynamic-editor header small,
.dynamic-editor label span { color: var(--ui-text-muted); font-size: 10px; }
.dynamic-editor label { display: grid; gap: 3px; }
.dynamic-editor input { min-height: 32px; padding: 0 7px; border: 1px solid var(--ui-border); border-radius: 6px; color: var(--ui-text); background: var(--ui-canvas); }
.dynamic-editor button { min-height: 32px; align-self: end; border: 0; border-radius: 6px; color: var(--ui-text); background: var(--ui-accent-soft); }

@media (max-width: 620px) {
  .inventory-editor { padding: 14px; }
  .catalog-workbench { grid-template-columns: minmax(0, 1fr) 86px; }
  .container-tabs { margin-block: 12px; }
}
</style>
