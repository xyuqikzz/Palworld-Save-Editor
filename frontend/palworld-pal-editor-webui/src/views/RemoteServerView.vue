<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import AppIcon from '@/components/modules/AppIcon.vue'
import ItemIcon from '@/components/modules/ItemIcon.vue'
import ItemPicker from '@/components/modules/ItemPicker.vue'
import RemotePalGrantForm from '@/components/modules/RemotePalGrantForm.vue'
import RemotePalCard from '@/components/modules/RemotePalCard.vue'
import RemoteRuntimeMap from '@/components/modules/RemoteRuntimeMap.vue'
import { formatRuntimeAttributes } from '@/components/modules/remote-runtime-values'
import { usePalEditorStore } from '@/stores/paleditor'

const palStore = usePalEditorStore()
const router = useRouter()
const selectedPlayerId = ref('')
const activeTab = ref('overview')
const palPageIndex = ref(0)
const palCollection = ref('party')
const palPageSize = computed(() => palCollection.value === 'party' ? 5 : 30)
const commandMessage = ref('')
const selectedInventoryContainerType = ref('')
const itemForm = reactive({ itemId: '', quantity: 1 })
const experienceForm = reactive({ amount: 1000 })

const hasPlayers = computed(() => palStore.REMOTE_PLAYERS.length > 0)
const can = capability => palStore.REMOTE_CAPABILITIES.includes(capability)
const grantablePals = computed(() => palStore.PAL_STATIC_DATA_LIST.filter(
  pal => !pal.Invalid && !pal.IsHuman,
))
const details = computed(() => palStore.REMOTE_PLAYER_DETAILS)
const detailPlayer = computed(() => details.value?.player || null)
const selectedPlayer = computed(() => palStore.REMOTE_PLAYERS.find(
  player => playerId(player) === selectedPlayerId.value,
) || null)
const displayPlayer = computed(() => detailPlayer.value || selectedPlayer.value)
const inventory = computed(() => details.value?.inventory || null)
const runtimeAttributes = computed(() => formatRuntimeAttributes(
  detailPlayer.value,
  inventory.value,
))
const detailHealth = computed(() => runtimeAttributes.value.health)
const pals = computed(() => details.value?.pals || null)
const inventoryContainers = computed(() => inventory.value?.containers || [])
const palEntries = computed(() => pals.value?.entries || [])
const visibleBackpackContainerTypes = new Set(['COMMON', 'ESSENTIAL'])
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
    side: 'left',
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
const backpackContainers = computed(() => inventoryContainers.value.filter(
  container => visibleBackpackContainerTypes.has(normalizeInventoryContainerType(container.type)),
))
const selectedInventoryContainer = computed(() => (
  backpackContainers.value.find(
    container => container.type === selectedInventoryContainerType.value,
  ) || backpackContainers.value[0] || null
))
const equipmentSections = computed(() => equipmentSectionDefinitions.map(definition => {
  const container = inventoryContainers.value.find(
    candidate => normalizeInventoryContainerType(candidate.type) === definition.containerType,
  ) || null
  const slots = inventorySlots(container)
  return {
    ...definition,
    container,
    slots: definition.slotIndices
      ? definition.slotIndices.map(slotIndex => (
        slots.find(slot => slot.slotIndex === slotIndex) || { slotIndex, item: null }
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
const foodEquipmentSection = computed(() => equipmentSections.value.find(
  section => section.side === 'bottom',
) || null)
const itemCatalog = computed(() => new Map(
  palStore.ITEM_CATALOG_RESULTS.map(item => [item.static_id, item]),
))
const inventoryContainerLabelKeys = Object.freeze({
  COMMON: 'Inventory_Container_Common',
  ESSENTIAL: 'Inventory_Container_Essential',
  WEAPON_LOADOUT: 'Inventory_Container_WeaponLoadout',
  PLAYER_EQUIP_ARMOR: 'Inventory_Container_ArmorEquipment',
  FOOD_EQUIP: 'Inventory_Container_FoodEquipment',
  Common: 'Inventory_Container_Common',
  DropSlot: 'Inventory_Container_DropSlot',
  Essential: 'Inventory_Container_Essential',
  WeaponLoadout: 'Inventory_Container_WeaponLoadout',
  PlayerEquipArmor: 'Inventory_Container_ArmorEquipment',
  FoodEquip: 'Inventory_Container_FoodEquipment',
})
const runtimeAbilityRows = computed(() => {
  return [
    {
      key: 'hp',
      icon: 'heart',
      image: 'max_hp',
      label: palStore.getTranslatedText('Remote_StatHp'),
      value: detailHealth.value.label,
    },
    {
      key: 'stamina',
      icon: 'activity',
      image: 'max_sp',
      label: palStore.getTranslatedText('PlayerAttribute_max_sp'),
      value: valueOrDash(runtimeAttributes.value.stamina),
      partial: runtimeAttributes.value.stamina === null,
    },
    {
      key: 'attack',
      icon: 'sword',
      image: 'attack',
      label: palStore.getTranslatedText('PlayerAttribute_attack'),
      value: valueOrDash(runtimeAttributes.value.attack),
      partial: runtimeAttributes.value.attack === null,
    },
    {
      key: 'defense',
      icon: 'shield',
      label: palStore.getTranslatedText('Remote_StatDefense'),
      value: valueOrDash(runtimeAttributes.value.defense),
      partial: runtimeAttributes.value.defense === null,
    },
    {
      key: 'work-speed',
      icon: 'hammer',
      image: 'work_speed',
      label: palStore.getTranslatedText('PlayerAttribute_work_speed'),
      value: valueOrDash(runtimeAttributes.value.craftSpeed),
      partial: runtimeAttributes.value.craftSpeed === null,
    },
    {
      key: 'carry-weight',
      icon: 'box',
      image: 'carry_weight',
      label: palStore.getTranslatedText('PlayerAttribute_carry_weight'),
      value: valueOrDash(runtimeAttributes.value.carryWeight),
      partial: runtimeAttributes.value.carryWeight === null,
    },
  ]
})
const healthPercent = computed(() => detailHealth.value.percent)
const selectedGuild = computed(() => {
  const guildId = detailPlayer.value?.guildId
    || detailPlayer.value?.guild_id
  if (!guildId) return null
  return palStore.REMOTE_GUILDS.find(
    guild => (guild.guildId || guild.guild_id) === guildId,
  ) || null
})

function playerId(player) {
  return player.player_uid
    || player.playerUid
    || player.playerId
    || player.userId
    || player.uid
    || ''
}

function playerName(player) {
  return player.name || player.nickname || playerId(player)
}

function playerInitial(player) {
  return playerName(player || {}).trim().slice(0, 1).toUpperCase() || '?'
}

function guildId(guild) {
  return guild.guildId || guild.guild_id || ''
}

function openMapPlayer(id) {
  selectedPlayerId.value = id
  activeTab.value = 'overview'
}

async function selectRemoteTab(tab) {
  activeTab.value = tab
  if (tab === 'inventory' && selectedPlayerId.value) {
    await palStore.loadRemotePlayerInventory(selectedPlayerId.value)
  }
  if (tab === 'pals' && selectedPlayerId.value) {
    await loadPalPage(palPageIndex.value)
  }
  if (tab === 'map' && !can('map.read')) {
    await palStore.refreshRemoteStatus({ background: true })
  }
}

async function selectPalCollection(collection) {
  if (palCollection.value === collection) return
  palCollection.value = collection
  palPageIndex.value = 0
  if (activeTab.value === 'pals' && selectedPlayerId.value) {
    await loadPalPage(0)
  }
}


async function loadPalPage(page, { force = false } = {}) {
  const maximumPage = Math.max(0, Number(pals.value?.pageCount || 1) - 1)
  const normalizedPage = Math.min(
    maximumPage,
    Math.max(0, Math.trunc(Number(page) || 0)),
  )
  if (await palStore.loadRemotePlayerPals(
    selectedPlayerId.value,
    normalizedPage,
    { collection: palCollection.value, force, pageSize: palPageSize.value },
  )) {
    palPageIndex.value = Number(pals.value?.pageIndex || normalizedPage)
  }
}

function itemInfo(itemId) {
  return itemCatalog.value.get(itemId) || {
    static_id: itemId,
    name: itemId,
    icon: null,
  }
}

function normalizeInventoryContainerType(containerType) {
  return String(containerType || '')
    .trim()
    .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
    .replace(/[\s-]+/g, '_')
    .toUpperCase()
}

function inventoryContainerLabel(containerType) {
  const key = inventoryContainerLabelKeys[containerType]
  return key
    ? palStore.getTranslatedText(key)
    : palStore.getTranslatedText('Inventory_Container_Unknown', [containerType])
}

function inventorySlots(container) {
  const items = container?.items || []
  const itemBySlot = new Map(items.map(item => [Number(item.slotIndex), item]))
  const highestOccupiedSlot = items.reduce(
    (highest, item) => Math.max(highest, Number(item.slotIndex) || 0),
    -1,
  )
  const slotCount = Math.max(
    Number(container?.slotCount) || 0,
    highestOccupiedSlot + 1,
  )
  return Array.from({ length: slotCount }, (_, slotIndex) => ({
    slotIndex,
    item: itemBySlot.get(slotIndex) || null,
  }))
}

function itemRarity(itemId) {
  const rarity = Number(itemInfo(itemId).rarity)
  return Number.isFinite(rarity)
    ? Math.max(0, Math.min(5, Math.trunc(rarity)))
    : 0
}

function palInfo(entry) {
  return palStore.PAL_STATIC_DATA[entry.characterId] || {
    InternalName: entry.characterId,
    I18n: entry.characterId,
  }
}

function valueOrDash(value) {
  return value === null || value === undefined || value === '' ? '—' : value
}

async function refreshRemote({
  clearCommandMessage = true,
  background = false,
} = {}) {
  if (clearCommandMessage) commandMessage.value = ''
  const selectedBeforeRefresh = selectedPlayerId.value
  if (await palStore.refreshRemoteStatus({ background })) {
    await Promise.all([
      palStore.loadRemotePlayers(),
      palStore.loadRemoteGuilds(),
    ])
    const selectedStillOnline = palStore.REMOTE_PLAYERS.some(
      player => playerId(player) === selectedPlayerId.value,
    )
    if (!selectedStillOnline) {
      selectedPlayerId.value = hasPlayers.value
        ? playerId(palStore.REMOTE_PLAYERS[0])
        : ''
    } else if (
      selectedBeforeRefresh
      && can('player.details')
    ) {
      await palStore.loadRemotePlayerDetails(selectedBeforeRefresh)
      if (activeTab.value === 'inventory') {
        await palStore.loadRemotePlayerInventory(
          selectedBeforeRefresh,
          { force: true },
        )
      } else if (activeTab.value === 'pals') {
        await loadPalPage(palPageIndex.value, { force: true })
      }
    }
  }
}

async function runCommand(operation, payload = {}, targetPlayer = true) {
  commandMessage.value = ''
  const result = await palStore.executeRemoteCommand({
    operation,
    target: targetPlayer ? { player_uid: selectedPlayerId.value } : {},
    payload,
  })
  if (!result) return
  commandMessage.value = palStore.getTranslatedText('Remote_CommandCompleted')
}

async function grantSelectedItem() {
  if (!itemForm.itemId || !selectedPlayerId.value) return
  await runCommand('inventory.grant', {
    item_id: itemForm.itemId,
    quantity: Number(itemForm.quantity),
  })
}

async function disconnect() {
  if (await palStore.disconnectRemote()) {
    await router.replace({ name: 'Entry' })
  }
}

watch(selectedPlayerId, async playerIdValue => {
  palPageIndex.value = 0
  if (playerIdValue && can('player.details')) {
    await palStore.loadRemotePlayerDetails(playerIdValue)
    if (activeTab.value === 'inventory') {
      await palStore.loadRemotePlayerInventory(playerIdValue)
    } else if (activeTab.value === 'pals') {
      await loadPalPage(0)
    }
  } else {
    await palStore.loadRemotePlayerDetails('')
  }
})

watch(backpackContainers, containers => {
  if (!containers.length) {
    selectedInventoryContainerType.value = ''
    return
  }
  if (!containers.some(
    container => container.type === selectedInventoryContainerType.value,
  )) {
    selectedInventoryContainerType.value = containers[0].type
  }
}, { immediate: true })

onMounted(async () => {
  if (!palStore.REMOTE_CONNECTED) {
    const resumed = await palStore.resumeRemoteSession()
    if (!resumed) {
      await router.replace({ name: 'Entry' })
      return
    }
  }
  await Promise.all([
    palStore.ITEM_CATALOG_RESULTS.length
      ? Promise.resolve()
      : palStore.searchItemCatalog(''),
    palStore.PAL_STATIC_DATA_LIST.length
      ? Promise.resolve()
      : palStore.fetchStaticData(),
  ])
  await refreshRemote()
})
</script>

<template>
  <main class="remote-page" aria-labelledby="remote-page-title">
    <div class="remote-shell">
      <header class="remote-header">
        <div class="remote-heading">
          <p class="remote-heading__kicker">{{ palStore.getTranslatedText('Remote_ManagementEyebrow') }}</p>
          <h1 id="remote-page-title">{{ palStore.REMOTE_SERVER?.name || palStore.REMOTE_SERVER_ADDRESS }}</h1>
          <p>{{ palStore.getTranslatedText('Remote_ManagementHint') }}</p>
        </div>
        <div class="remote-header__actions">
          <button
            type="button"
            class="remote-button"
            :disabled="palStore.REMOTE_LOADING"
            @click="refreshRemote"
          >
            <AppIcon name="refresh" :size="16" />
            {{ palStore.getTranslatedText('Remote_Refresh') }}
          </button>
          <button
            type="button"
            class="remote-button remote-button--danger"
            :disabled="palStore.REMOTE_LOADING"
            @click="disconnect"
          >
            <AppIcon name="x" :size="16" />
            {{ palStore.getTranslatedText('Remote_Disconnect') }}
          </button>
        </div>
      </header>

      <div class="remote-source" :title="palStore.REMOTE_SERVER_ADDRESS">
        <span :class="['remote-source__state', { 'is-ready': palStore.REMOTE_STATUS?.ready }]">
          <i />
          {{ palStore.getTranslatedText(palStore.REMOTE_STATUS?.ready ? 'Remote_Connected' : 'Remote_NotReady') }}
        </span>
        <span class="remote-source__name">
          {{ palStore.REMOTE_SERVER_ADDRESS || palStore.REMOTE_SERVER?.world_guid || '—' }}
        </span>
        <span class="remote-source__meta">
          {{ [palStore.REMOTE_SERVER?.platform, palStore.REMOTE_SERVER?.game_version].filter(Boolean).join(' · ') || 'PalEditorBridge' }}
        </span>
        <code>v{{ palStore.REMOTE_STATUS?.bridgeVersion || '—' }}</code>
      </div>

      <section class="remote-metrics" :aria-label="palStore.getTranslatedText('Remote_GameReady')">
        <article :class="{ 'is-positive': palStore.REMOTE_STATUS?.gameReady }">
          <span class="remote-metrics__icon"><AppIcon name="activity" :size="18" /></span>
          <div>
            <strong>{{ palStore.getTranslatedText(palStore.REMOTE_STATUS?.gameReady ? 'Remote_Value_Yes' : 'Remote_Value_No') }}</strong>
            <span>{{ palStore.getTranslatedText('Remote_GameReady') }}</span>
          </div>
        </article>
        <article>
          <span class="remote-metrics__icon"><AppIcon name="shield" :size="18" /></span>
          <div>
            <strong>{{ palStore.REMOTE_STATUS?.instanceMode || '—' }}</strong>
            <span>{{ palStore.getTranslatedText('Remote_InstanceMode') }}</span>
          </div>
        </article>
        <article :class="{ 'is-positive': palStore.REMOTE_STATUS?.runtimeDataReady }">
          <span class="remote-metrics__icon"><AppIcon name="overview" :size="18" /></span>
          <div>
            <strong>{{ palStore.getTranslatedText(palStore.REMOTE_STATUS?.runtimeDataReady ? 'Remote_Value_Yes' : 'Remote_Value_No') }}</strong>
            <span>{{ palStore.getTranslatedText('Remote_RuntimeDataReady') }}</span>
          </div>
        </article>
        <article>
          <span class="remote-metrics__icon"><AppIcon name="user" :size="18" /></span>
          <div>
            <strong>{{ palStore.REMOTE_PLAYERS.length }}</strong>
            <span>{{ palStore.getTranslatedText('Remote_OnlinePlayers') }}</span>
          </div>
        </article>
        <article>
          <span class="remote-metrics__icon"><AppIcon name="building" :size="18" /></span>
          <div>
            <strong>{{ palStore.REMOTE_GUILDS.length }}</strong>
            <span>{{ palStore.getTranslatedText('Remote_Guilds') }}</span>
          </div>
        </article>
        <article>
          <span class="remote-metrics__icon"><AppIcon name="file" :size="18" /></span>
          <div>
            <strong>{{ palStore.REMOTE_SESSION_REVISION }}</strong>
            <span>{{ palStore.getTranslatedText('Remote_SessionRevision') }}</span>
          </div>
        </article>
      </section>

      <div class="remote-workspace">
        <aside class="remote-sidebar">
          <section class="remote-card remote-card--players">
            <header class="remote-card__heading">
              <div>
                <p>{{ palStore.getTranslatedText('Remote_RuntimeDataReady') }}</p>
                <h2>{{ palStore.getTranslatedText('Remote_Players') }}</h2>
              </div>
              <span class="remote-card__count">{{ palStore.REMOTE_PLAYERS.length }}</span>
            </header>
            <div v-if="hasPlayers" class="player-list">
              <button
                v-for="player in palStore.REMOTE_PLAYERS"
                :key="playerId(player)"
                type="button"
                :class="{ active: selectedPlayerId === playerId(player) }"
                :aria-pressed="selectedPlayerId === playerId(player)"
                @click="selectedPlayerId = playerId(player)"
              >
                <span class="player-list__avatar">{{ playerInitial(player) }}</span>
                <span class="player-list__copy">
                  <strong>{{ playerName(player) }}</strong>
                  <small>{{ playerId(player) }}</small>
                </span>
                <span class="player-list__level">
                  {{ player.level ? `${palStore.getTranslatedText('Common_LevelShort')}${player.level}` : '—' }}
                </span>
                <AppIcon name="forward" :size="14" />
              </button>
            </div>
            <div v-else class="sidebar-empty">
              <span><AppIcon name="user" :size="20" /></span>
              <p>{{ palStore.getTranslatedText('Remote_NoPlayers') }}</p>
            </div>
          </section>

          <section class="remote-card">
            <header class="remote-card__heading">
              <div>
                <p>{{ palStore.getTranslatedText('Remote_OnlinePlayers') }}</p>
                <h2>{{ palStore.getTranslatedText('Remote_Guilds') }}</h2>
              </div>
              <span class="remote-card__count">{{ palStore.REMOTE_GUILDS.length }}</span>
            </header>
            <div v-if="palStore.REMOTE_GUILDS.length" class="guild-list">
              <article v-for="guild in palStore.REMOTE_GUILDS" :key="guildId(guild)">
                <span class="guild-list__icon"><AppIcon name="building" :size="16" /></span>
                <span>
                  <strong>{{ guild.name || guildId(guild) }}</strong>
                  <small>{{ palStore.getTranslatedText('Remote_OnlineMembers', [guild.onlineMemberCount || 0]) }}</small>
                </span>
              </article>
            </div>
            <p v-else class="empty-copy">{{ palStore.getTranslatedText('Remote_NoGuilds') }}</p>
          </section>

          <details class="remote-card capability-card">
            <summary>
              <span>
                <AppIcon name="settings" :size="16" />
                {{ palStore.getTranslatedText('Remote_Capabilities') }}
              </span>
              <b>{{ palStore.REMOTE_CAPABILITIES.length }}</b>
            </summary>
            <div class="capability-list">
              <code v-for="capability in palStore.REMOTE_CAPABILITIES" :key="capability">{{ capability }}</code>
            </div>
          </details>
        </aside>

        <section class="remote-console">
          <header class="remote-console__heading">
            <span class="remote-console__avatar">{{ playerInitial(displayPlayer) }}</span>
            <div>
              <p>{{ palStore.getTranslatedText('Remote_CommandCenter') }}</p>
              <h2>{{ displayPlayer ? playerName(displayPlayer) : palStore.getTranslatedText('Remote_PlayerDetails') }}</h2>
              <code>{{ selectedPlayerId || '—' }}</code>
            </div>
            <span v-if="displayPlayer" class="remote-console__level">
              {{ palStore.getTranslatedText('Common_LevelShort') }}{{ valueOrDash(displayPlayer.level) }}
            </span>
          </header>

          <nav class="remote-tabs" role="tablist" :aria-label="palStore.getTranslatedText('Remote_PlayerDetails')">
            <button
              type="button"
              role="tab"
              :class="{ active: activeTab === 'overview' }"
              :aria-selected="activeTab === 'overview'"
              @click="selectRemoteTab('overview')"
            >
              <AppIcon name="overview" :size="16" />
              {{ palStore.getTranslatedText('Remote_TabOverview') }}
            </button>
            <button
              type="button"
              role="tab"
              :class="{ active: activeTab === 'inventory' }"
              :aria-selected="activeTab === 'inventory'"
              @click="selectRemoteTab('inventory')"
            >
              <AppIcon name="box" :size="16" />
              {{ palStore.getTranslatedText('Remote_TabInventory') }}
            </button>
            <button
              type="button"
              role="tab"
              :class="{ active: activeTab === 'pals' }"
              :aria-selected="activeTab === 'pals'"
              @click="selectRemoteTab('pals')"
            >
              <AppIcon name="paw" :size="16" />
              {{ palStore.getTranslatedText('Remote_TabPals') }}
            </button>
            <button
              type="button"
              role="tab"
              :class="{
                active: activeTab === 'map',
                'remote-tabs__unavailable': !can('map.read'),
              }"
              :aria-selected="activeTab === 'map'"
              :title="!can('map.read') ? palStore.getTranslatedText('RemoteMap_CapabilityUnavailable') : undefined"
              @click="selectRemoteTab('map')"
            >
              <AppIcon name="map" :size="16" />
              {{ palStore.getTranslatedText('Remote_TabMap') }}
              <span v-if="can('map.read')">{{ palStore.REMOTE_MAP_DATA?.players?.length || 0 }}</span>
              <span v-else aria-hidden="true">!</span>
            </button>
            <button
              type="button"
              role="tab"
              :class="{ active: activeTab === 'operations' }"
              :aria-selected="activeTab === 'operations'"
              @click="selectRemoteTab('operations')"
            >
              <AppIcon name="settings" :size="16" />
              {{ palStore.getTranslatedText('Remote_TabOperations') }}
            </button>
          </nav>

          <p v-if="commandMessage" class="command-message" role="status">
            <AppIcon name="check" :size="16" />
            {{ commandMessage }}
          </p>
          <p v-if="palStore.LAST_ERROR?.context?.startsWith('remote-')" class="command-error" role="alert">
            <AppIcon name="warning" :size="16" />
            {{ palStore.LAST_ERROR.message }}
          </p>

          <div v-if="palStore.REMOTE_PLAYER_DETAILS_LOADING" class="detail-skeleton" aria-busy="true">
            <span v-for="index in 6" :key="index" />
          </div>

          <div
            v-else-if="activeTab === 'map' && !can('map.read')"
            class="data-state data-state--map-unavailable"
          >
            <span><AppIcon name="warning" :size="24" /></span>
            <strong>{{ palStore.getTranslatedText('RemoteMap_CapabilityUnavailable') }}</strong>
            <p>{{ palStore.getTranslatedText('RemoteMap_CapabilityHint') }}</p>
          </div>

          <RemoteRuntimeMap
            v-else-if="activeTab === 'map'"
            @select-player="openMapPlayer"
          />

          <div v-else-if="!selectedPlayerId" class="data-state">
            <span><AppIcon name="user" :size="26" /></span>
            <strong>{{ palStore.getTranslatedText('Remote_SelectPlayer') }}</strong>
          </div>

          <div v-else-if="activeTab === 'overview'" class="detail-panel">
            <article v-if="detailPlayer" class="profile-card">
              <header class="profile-card__hero">
                <span class="profile-card__avatar">{{ playerInitial(detailPlayer) }}</span>
                <div>
                  <small>{{ palStore.getTranslatedText('Remote_PlayerProfile') }}</small>
                  <h3>{{ playerName(detailPlayer) }}</h3>
                  <p>{{ selectedGuild?.name || detailPlayer.guildName || palStore.getTranslatedText('Remote_Guild') }}</p>
                </div>
                <strong>{{ palStore.getTranslatedText('Common_LevelShort') }}{{ valueOrDash(detailPlayer.level) }}</strong>
              </header>
              <dl class="detail-grid">
                <div>
                  <dt>{{ palStore.getTranslatedText('Remote_PlayerId') }}</dt>
                  <dd>{{ playerId(detailPlayer) }}</dd>
                </div>
                <div>
                  <dt>{{ palStore.getTranslatedText('Remote_Guild') }}</dt>
                  <dd>{{ selectedGuild?.name || detailPlayer.guildName || '—' }}</dd>
                </div>
                <div>
                  <dt>{{ palStore.getTranslatedText('Remote_Experience') }}</dt>
                  <dd>{{ valueOrDash(detailPlayer.experience) }}</dd>
                </div>
                <div>
                  <dt>{{ palStore.getTranslatedText('Remote_Rank') }}</dt>
                  <dd>{{ valueOrDash(detailPlayer.rank) }}</dd>
                </div>
                <div>
                  <dt>{{ palStore.getTranslatedText('Remote_Health') }}</dt>
                  <dd>{{ detailHealth.label }}</dd>
                </div>
                <div>
                  <dt>{{ palStore.getTranslatedText('Remote_UnusedStatusPoints') }}</dt>
                  <dd>{{ valueOrDash(detailPlayer.unusedStatusPoints) }}</dd>
                </div>
              </dl>
              <p v-if="detailPlayer.detailsStatus === 'partial'" class="partial-note">
                <AppIcon name="warning" :size="15" />
                {{ palStore.getTranslatedText('Remote_DataPartial') }}
              </p>
            </article>
            <div v-else class="data-state">
              <span><AppIcon name="warning" :size="24" /></span>
              <strong>{{ palStore.getTranslatedText('Remote_DetailsUnavailable') }}</strong>
            </div>
          </div>

          <div v-else-if="activeTab === 'inventory'" class="detail-panel">
            <div v-if="inventory?.status !== 'available'" class="data-state data-state--error">
              <span><AppIcon name="warning" :size="24" /></span>
              <strong>{{ inventory?.error || palStore.getTranslatedText('Remote_InventoryUnavailable') }}</strong>
            </div>
            <div v-else-if="inventoryContainers.length" class="inventory-layout">
              <section class="inventory-board">
                <nav
                  class="inventory-container-tabs"
                  :aria-label="palStore.getTranslatedText('Inventory_ContainersAriaLabel')"
                >
                  <button
                    v-for="container in backpackContainers"
                    :key="container.type"
                    type="button"
                    :class="{ active: selectedInventoryContainer?.type === container.type }"
                    @click="selectedInventoryContainerType = container.type"
                  >
                    <span>{{ inventoryContainerLabel(container.type) }}</span>
                    <small>{{ container.occupiedSlotCount }} / {{ container.slotCount }}</small>
                  </button>
                </nav>

                <div class="inventory-board__toolbar">
                  <div>
                    <AppIcon name="box" :size="16" />
                    <strong>{{ inventoryContainerLabel(selectedInventoryContainer?.type) }}</strong>
                  </div>
                  <span>
                    {{ selectedInventoryContainer?.occupiedSlotCount || 0 }}
                    /
                    {{ selectedInventoryContainer?.slotCount || 0 }}
                  </span>
                </div>

                <div
                  v-if="selectedInventoryContainer"
                  class="inventory-slot-grid"
                  :aria-label="inventoryContainerLabel(selectedInventoryContainer.type)"
                >
                  <article
                    v-for="slot in inventorySlots(selectedInventoryContainer)"
                    :key="`${selectedInventoryContainer.type}-${slot.slotIndex}`"
                    :class="[
                      'inventory-slot',
                      slot.item && `inventory-slot--rarity-${itemRarity(slot.item.itemId)}`,
                      { 'is-empty': !slot.item },
                    ]"
                    :title="slot.item ? `${itemInfo(slot.item.itemId).name} · ${slot.item.itemId}` : ''"
                  >
                    <template v-if="slot.item">
                      <span class="inventory-slot__index">{{ slot.slotIndex + 1 }}</span>
                      <ItemIcon
                        class="inventory-slot__icon"
                        :icon="itemInfo(slot.item.itemId).icon"
                        :name="itemInfo(slot.item.itemId).name"
                        :size="68"
                      />
                      <b class="inventory-slot__quantity">{{ slot.item.quantity }}</b>
                    </template>
                    <span v-else class="inventory-slot__empty-index">{{ slot.slotIndex + 1 }}</span>
                  </article>
                </div>
              </section>

              <section class="equipment-board">
                <h3 class="sr-only">{{ palStore.getTranslatedText('Remote_Equipment') }}</h3>
                <div class="equipment-stage">
                  <div class="equipment-side equipment-side--left">
                    <section
                      v-for="section in leftEquipmentSections"
                      :key="section.key"
                      :class="['equipment-section', `equipment-section--${section.key}`]"
                    >
                      <header>
                        <strong>{{ palStore.getTranslatedText(section.labelKey) }}</strong>
                      </header>
                      <div class="equipment-slot-grid">
                        <article
                          v-for="slot in section.slots"
                          :key="`${section.key}-${slot.slotIndex}`"
                          :class="[
                            'equipment-slot',
                            slot.item && `inventory-slot--rarity-${itemRarity(slot.item.itemId)}`,
                            { 'is-empty': !slot.item },
                          ]"
                          :title="slot.item ? `${itemInfo(slot.item.itemId).name} · ${slot.item.itemId}` : ''"
                        >
                          <span class="equipment-slot__index">{{ slot.slotIndex + 1 }}</span>
                          <template v-if="slot.item">
                            <ItemIcon
                              class="equipment-slot__icon"
                              :icon="itemInfo(slot.item.itemId).icon"
                              :name="itemInfo(slot.item.itemId).name"
                              :size="72"
                            />
                            <b v-if="slot.item.quantity > 1" class="equipment-slot__quantity">
                              {{ slot.item.quantity }}
                            </b>
                          </template>
                        </article>
                      </div>
                    </section>
                  </div>

                  <div class="equipment-model-space" aria-hidden="true"></div>

                  <div class="equipment-side equipment-side--right">
                    <section
                      v-for="section in rightEquipmentSections"
                      :key="section.key"
                      :class="['equipment-section', `equipment-section--${section.key}`]"
                    >
                      <header>
                        <strong>{{ palStore.getTranslatedText(section.labelKey) }}</strong>
                      </header>
                      <div class="equipment-slot-grid">
                        <article
                          v-for="slot in section.slots"
                          :key="`${section.key}-${slot.slotIndex}`"
                          :class="[
                            'equipment-slot',
                            slot.item && `inventory-slot--rarity-${itemRarity(slot.item.itemId)}`,
                            { 'is-empty': !slot.item },
                          ]"
                          :title="slot.item ? `${itemInfo(slot.item.itemId).name} · ${slot.item.itemId}` : ''"
                        >
                          <span class="equipment-slot__index">{{ slot.slotIndex + 1 }}</span>
                          <template v-if="slot.item">
                            <ItemIcon
                              class="equipment-slot__icon"
                              :icon="itemInfo(slot.item.itemId).icon"
                              :name="itemInfo(slot.item.itemId).name"
                              :size="72"
                            />
                            <b v-if="slot.item.quantity > 1" class="equipment-slot__quantity">
                              {{ slot.item.quantity }}
                            </b>
                          </template>
                        </article>
                      </div>
                    </section>
                  </div>

                  <section
                    v-if="foodEquipmentSection"
                    class="equipment-section equipment-section--food"
                  >
                    <header>
                      <strong>{{ palStore.getTranslatedText(foodEquipmentSection.labelKey) }}</strong>
                    </header>
                    <div class="equipment-slot-grid">
                      <article
                        v-for="slot in foodEquipmentSection.slots"
                        :key="`${foodEquipmentSection.key}-${slot.slotIndex}`"
                        :class="[
                          'equipment-slot',
                          slot.item && `inventory-slot--rarity-${itemRarity(slot.item.itemId)}`,
                          { 'is-empty': !slot.item },
                        ]"
                        :title="slot.item ? `${itemInfo(slot.item.itemId).name} · ${slot.item.itemId}` : ''"
                      >
                        <span class="equipment-slot__index">{{ slot.slotIndex + 1 }}</span>
                        <template v-if="slot.item">
                          <ItemIcon
                            class="equipment-slot__icon"
                            :icon="itemInfo(slot.item.itemId).icon"
                            :name="itemInfo(slot.item.itemId).name"
                            :size="72"
                          />
                          <b v-if="slot.item.quantity > 1" class="equipment-slot__quantity">
                            {{ slot.item.quantity }}
                          </b>
                        </template>
                      </article>
                    </div>
                  </section>
                </div>
              </section>

              <aside class="runtime-attributes">
                <div class="runtime-player-level">
                  <strong>{{ valueOrDash(displayPlayer?.level) }}</strong>
                  <div>
                    <small>{{ palStore.getTranslatedText('Common_Level') }}</small>
                    <b>{{ playerName(displayPlayer || {}) }}</b>
                  </div>
                </div>
                <div v-if="detailHealth.current !== null" class="runtime-health">
                  <div>
                    <span><AppIcon name="heart" :size="15" /></span>
                    <strong>{{ detailHealth.label }}</strong>
                  </div>
                  <progress v-if="detailHealth.percent !== null" :value="healthPercent" max="100">
                    {{ healthPercent }}%
                  </progress>
                </div>
                <header class="runtime-attributes__heading">
                  <div>
                    <small>{{ palStore.getTranslatedText('Remote_PlayerProfile') }}</small>
                    <h3>{{ palStore.getTranslatedText('PlayerAttributes_Title') }}</h3>
                  </div>
                </header>
                <div class="runtime-attributes__points">
                  <span>{{ palStore.getTranslatedText('Remote_UnusedStatusPoints') }}</span>
                  <b>{{ valueOrDash(detailPlayer?.unusedStatusPoints) }}</b>
                </div>
                <dl>
                  <div v-for="attribute in runtimeAbilityRows" :key="attribute.key">
                    <dt>
                      <span>
                        <img
                          v-if="attribute.image"
                          :src="`/image/player_attributes/${attribute.image}`"
                          alt=""
                        >
                        <AppIcon v-else :name="attribute.icon" :size="17" />
                      </span>
                      {{ attribute.label }}
                    </dt>
                    <dd :class="{ 'is-partial': attribute.partial }">
                      {{ attribute.value }}
                    </dd>
                  </div>
                </dl>
                <p v-if="runtimeAttributes.partial" class="runtime-attributes__note">
                  <AppIcon name="warning" :size="14" />
                  {{ palStore.getTranslatedText('Remote_DataPartial') }}
                </p>
              </aside>
            </div>
            <div v-else class="data-state">
              <span><AppIcon name="box" :size="24" /></span>
              <strong>{{ palStore.getTranslatedText('Remote_EmptyInventory') }}</strong>
            </div>
          </div>

          <div v-else-if="activeTab === 'pals'" class="detail-panel">
            <nav
              class="pal-collection-tabs"
              :aria-label="palStore.getTranslatedText('Remote_PalCollections')"
            >
              <button
                type="button"
                :class="{ active: palCollection === 'party' }"
                :aria-pressed="palCollection === 'party'"
                @click="selectPalCollection('party')"
              >
                <AppIcon name="paw" :size="16" />
                {{ palStore.getTranslatedText('Remote_PalCollectionParty') }}
              </button>
              <button
                type="button"
                :class="{ active: palCollection === 'palbox' }"
                :aria-pressed="palCollection === 'palbox'"
                @click="selectPalCollection('palbox')"
              >
                <AppIcon name="box" :size="16" />
                {{ palStore.getTranslatedText('Remote_PalCollectionTerminal') }}
              </button>
            </nav>
            <header class="panel-summary">
              <span class="panel-summary__icon"><AppIcon name="paw" :size="20" /></span>
              <div>
                <small>
                  {{ palStore.getTranslatedText(
                    palCollection === 'party' ? 'Remote_PartyPals' : 'Remote_Pals'
                  ) }}
                </small>
                <h3 v-if="palCollection === 'party'">
                  {{ palStore.getTranslatedText('Remote_PartyPalsSummary', [pals?.count ?? pals?.loadedCount ?? '—']) }}
                </h3>
                <h3 v-else>
                  {{ palStore.getTranslatedText('Remote_PalboxSummary', [pals?.count ?? '—', pals?.capacity || 0]) }}
                </h3>
              </div>
              <strong v-if="palCollection === 'palbox'">
                {{ pals?.pageCount || 0 }} {{ palStore.getTranslatedText('Remote_Pages') }}
              </strong>
            </header>
            <div v-if="pals?.status !== 'available'" class="data-state data-state--error">
              <span><AppIcon name="warning" :size="24" /></span>
              <strong>
                {{ pals?.error || palStore.getTranslatedText(
                  palCollection === 'party'
                    ? 'Remote_PartyPalsUnavailable'
                    : 'Remote_PalsUnavailable'
                ) }}
              </strong>
            </div>
            <div
              v-else-if="palEntries.length"
              class="pal-collection"
              :class="`pal-collection--${palCollection}`"
            >
              <RemotePalCard
                v-for="entry in palEntries"
                :key="entry.instanceId || `${palCollection}-${entry.slotIndex}`"
                :entry="entry"
                :pal="palInfo(entry)"
                :layout="palCollection"
              />
            </div>
            <div v-else class="data-state">
              <span><AppIcon name="paw" :size="24" /></span>
              <strong>
                {{ palStore.getTranslatedText(
                  palCollection === 'party' ? 'Remote_EmptyPartyPals' : 'Remote_EmptyPals'
                ) }}
              </strong>
            </div>
            <footer v-if="pals?.status === 'available'" class="pal-pagination">
              <button
                v-if="(pals?.pageCount || 0) > 1"
                type="button"
                class="remote-button"
                :disabled="!pals?.hasPrevious || palStore.REMOTE_PLAYER_DETAILS_LOADING"
                @click="loadPalPage(palPageIndex - 1)"
              >
                {{ palStore.getTranslatedText('Common_PreviousPage') }}
              </button>
              <span v-if="(pals?.pageCount || 0) > 1">
                {{ palPageIndex + 1 }} / {{ Math.max(1, pals?.pageCount || 1) }}
              </span>
              <button
                v-if="(pals?.pageCount || 0) > 1"
                type="button"
                class="remote-button"
                :disabled="!pals?.hasNext || palStore.REMOTE_PLAYER_DETAILS_LOADING"
                @click="loadPalPage(palPageIndex + 1)"
              >
                {{ palStore.getTranslatedText('Common_NextPage') }}
              </button>
              <button
                type="button"
                class="remote-button"
                :disabled="palStore.REMOTE_PLAYER_DETAILS_LOADING"
                @click="loadPalPage(palPageIndex, { force: true })"
              >
                {{ palStore.getTranslatedText('Common_Refresh') }}
              </button>
            </footer>
          </div>

          <div v-else class="operation-grid">
            <form
              v-if="can('inventory.grant')"
              class="operation-card"
              @submit.prevent="grantSelectedItem"
            >
              <header class="operation-card__heading">
                <span><AppIcon name="box" :size="18" /></span>
                <div>
                  <small>{{ palStore.getTranslatedText('Remote_TabOperations') }}</small>
                  <h3>{{ palStore.getTranslatedText('Remote_GrantItem') }}</h3>
                </div>
              </header>
              <ItemPicker
                v-model="itemForm.itemId"
                :options="palStore.ITEM_CATALOG_RESULTS"
                :disabled="palStore.REMOTE_LOADING"
              />
              <label>
                <span>{{ palStore.getTranslatedText('Remote_Quantity') }}</span>
                <input v-model.number="itemForm.quantity" type="number" min="1" max="9999" required />
              </label>
              <button class="remote-button remote-button--primary" :disabled="palStore.REMOTE_LOADING || !selectedPlayerId || !itemForm.itemId">
                <AppIcon name="plus" :size="15" />
                {{ palStore.getTranslatedText('Remote_Execute') }}
              </button>
            </form>

            <form
              v-if="can('player.experience.add')"
              class="operation-card"
              @submit.prevent="runCommand('player.experience.add', { amount: Number(experienceForm.amount) })"
            >
              <header class="operation-card__heading">
                <span><AppIcon name="activity" :size="18" /></span>
                <div>
                  <small>{{ palStore.getTranslatedText('Remote_TabOperations') }}</small>
                  <h3>{{ palStore.getTranslatedText('Remote_AddExperience') }}</h3>
                </div>
              </header>
              <label>
                <span>{{ palStore.getTranslatedText('Remote_ExperienceAmount') }}</span>
                <input v-model.number="experienceForm.amount" type="number" min="1" max="2000000000" required />
              </label>
              <button class="remote-button remote-button--primary" :disabled="palStore.REMOTE_LOADING || !selectedPlayerId">
                <AppIcon name="plus" :size="15" />
                {{ palStore.getTranslatedText('Remote_Execute') }}
              </button>
            </form>

            <RemotePalGrantForm
              v-if="can('pal.grant')"
              :pal-options="grantablePals"
              :pal-data="palStore.PAL_STATIC_DATA"
              :passive-options="palStore.PASSIVE_SKILLS_LIST"
              :level-maximum="palStore.MAX_LEVEL"
              :soul-maximum="palStore.MAX_SOULS_LEVEL || 60"
              :disabled="palStore.REMOTE_LOADING"
              :can-submit="Boolean(selectedPlayerId)"
              @submit="runCommand('pal.grant', $event)"
            />

            <article v-if="can('world.save')" class="operation-card operation-card--world">
              <header class="operation-card__heading">
                <span><AppIcon name="file" :size="18" /></span>
                <div>
                  <small>{{ palStore.getTranslatedText('Remote_TabOperations') }}</small>
                  <h3>{{ palStore.getTranslatedText('Remote_SaveWorld') }}</h3>
                </div>
              </header>
              <p>{{ palStore.getTranslatedText('Remote_SaveWorldHint') }}</p>
              <button
                type="button"
                class="remote-button remote-button--primary"
                :disabled="palStore.REMOTE_LOADING"
                @click="runCommand('world.save', {}, false)"
              >
                <AppIcon name="check" :size="15" />
                {{ palStore.getTranslatedText('Remote_SaveNow') }}
              </button>
            </article>

            <article
              v-if="!palStore.REMOTE_CAPABILITIES.some((capability) => ['inventory.grant', 'player.experience.add', 'pal.grant', 'world.save'].includes(capability))"
              class="operation-card operation-card--empty"
            >
              <span><AppIcon name="settings" :size="26" /></span>
              <h3>{{ palStore.getTranslatedText('Remote_NoLiveCommands') }}</h3>
              <p>{{ palStore.getTranslatedText('Remote_DevelopmentOnly') }}</p>
            </article>
          </div>
        </section>
      </div>
    </div>
  </main>
</template>

<style scoped>
.remote-page {
  min-height: 100dvh;
  padding: 88px clamp(14px, 2.2vw, 34px) 48px;
  color: var(--ui-text);
  background:
    radial-gradient(circle at 82% 7%, oklch(0.28 0.045 246 / 0.22), transparent 31rem),
    var(--ui-canvas);
}

.remote-shell {
  width: min(1540px, 100%);
  margin-inline: auto;
}

.remote-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 28px;
  margin-bottom: 18px;
}

.remote-heading { min-width: 0; }
.remote-heading__kicker,
.remote-card__heading p,
.operation-card__heading small {
  margin: 0 0 5px;
  color: var(--ui-accent);
  font-size: 10px;
  font-weight: 750;
  letter-spacing: 0.08em;
}

.remote-heading h1 {
  margin: 0;
  font-size: clamp(28px, 3vw, 42px);
  line-height: 1.08;
  font-weight: 760;
  letter-spacing: -0.045em;
  text-wrap: balance;
}

.remote-heading > p:last-child {
  max-width: 68ch;
  margin: 10px 0 0;
  color: var(--ui-text-muted);
  font-size: 13px;
  line-height: 1.65;
  text-wrap: pretty;
}

.remote-header__actions {
  display: flex;
  flex: 0 0 auto;
  gap: 8px;
}

.remote-button {
  display: inline-flex;
  min-height: 38px;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 0 13px;
  color: var(--ui-text-secondary);
  background: var(--ui-surface);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
  font: inherit;
  font-size: 12px;
  font-weight: 650;
}

.remote-button:hover:not(:disabled) {
  color: var(--ui-text);
  background: var(--ui-surface-hover);
  border-color: var(--ui-border-strong);
}

.remote-button--primary {
  color: oklch(0.16 0.025 252);
  background: var(--ui-accent);
  border-color: var(--ui-accent);
}

.remote-button--primary:hover:not(:disabled) {
  color: oklch(0.12 0.02 252);
  background: oklch(0.78 0.12 246);
  border-color: oklch(0.78 0.12 246);
}

.remote-button--danger:hover:not(:disabled) {
  color: var(--ui-danger);
  background: var(--ui-danger-soft);
  border-color: oklch(0.45 0.08 24);
}

.remote-button:disabled { opacity: 0.45; }

.remote-source {
  display: flex;
  min-width: 0;
  min-height: 36px;
  align-items: center;
  gap: 9px;
  margin-bottom: 14px;
  padding: 6px 9px;
  color: var(--ui-text-muted);
  background: oklch(0.19 0.017 252 / 0.78);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
  font-size: 11px;
}

.remote-source__state {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 6px;
  padding: 3px 7px;
  color: var(--ui-text-secondary);
  background: var(--ui-surface-raised);
  border-radius: 5px;
  font-size: 9px;
  font-weight: 750;
}

.remote-source__state i {
  width: 6px;
  height: 6px;
  background: var(--ui-danger);
  border-radius: 50%;
  box-shadow: 0 0 0 3px oklch(0.69 0.17 24 / 0.12);
}

.remote-source__state.is-ready { color: var(--ui-success); }
.remote-source__state.is-ready i {
  background: var(--ui-success);
  box-shadow: 0 0 0 3px oklch(0.72 0.12 158 / 0.13);
}

.remote-source__name {
  min-width: 0;
  flex: 1 1 auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.remote-source__meta { flex: 0 0 auto; color: var(--ui-text-secondary); }
.remote-source code {
  flex: 0 0 auto;
  color: var(--ui-text-muted);
  font: 10px/1.4 ui-monospace, "Cascadia Code", Consolas, monospace;
}

.remote-metrics {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  margin-bottom: 14px;
  overflow: hidden;
  background: var(--ui-surface);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-lg);
  box-shadow: var(--ui-shadow-sm);
}

.remote-metrics article {
  display: flex;
  min-width: 0;
  min-height: 102px;
  align-items: center;
  gap: 12px;
  padding: 16px;
}

.remote-metrics article + article { border-left: 1px solid var(--ui-border); }
.remote-metrics__icon {
  display: inline-grid;
  width: 38px;
  height: 38px;
  flex: 0 0 auto;
  place-items: center;
  color: var(--ui-text-secondary);
  background: var(--ui-surface-raised);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
}

.remote-metrics article.is-positive .remote-metrics__icon {
  color: var(--ui-success);
  background: oklch(0.25 0.05 158);
  border-color: oklch(0.42 0.07 158);
}

.remote-metrics article > div {
  display: grid;
  min-width: 0;
  gap: 5px;
}

.remote-metrics strong {
  overflow: hidden;
  font-size: clamp(16px, 1.5vw, 23px);
  line-height: 1;
  font-weight: 740;
  letter-spacing: -0.035em;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.remote-metrics article > div > span {
  overflow: hidden;
  color: var(--ui-text-muted);
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.remote-workspace {
  display: grid;
  grid-template-columns: minmax(292px, 326px) minmax(0, 1fr);
  align-items: start;
  gap: 14px;
}

.remote-sidebar { display: flex; flex-direction: column; gap: 14px; }
.remote-card,
.remote-console {
  min-width: 0;
  background: var(--ui-surface);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-md);
  box-shadow: var(--ui-shadow-sm);
}

.remote-card { padding: 18px; }
.remote-card__heading {
  display: flex;
  min-width: 0;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 13px;
}

.remote-card__heading h2 {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  letter-spacing: -0.015em;
}

.remote-card__count {
  display: inline-grid;
  min-width: 28px;
  height: 28px;
  place-items: center;
  color: var(--ui-accent);
  background: var(--ui-accent-soft);
  border-radius: 8px;
  font-size: 10px;
  font-weight: 750;
}

.player-list,
.guild-list { display: grid; gap: 6px; }
.player-list {
  max-height: min(52dvh, 520px);
  overflow-y: auto;
  padding-right: 2px;
}

.player-list button {
  display: grid;
  min-width: 0;
  min-height: 58px;
  grid-template-columns: auto minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 9px;
  padding: 7px 8px;
  color: var(--ui-text-secondary);
  background: var(--ui-surface-raised);
  border: 1px solid transparent;
  border-radius: var(--ui-radius-sm);
  text-align: left;
}

.player-list button:hover {
  color: var(--ui-text);
  background: var(--ui-surface-hover);
  border-color: var(--ui-border-strong);
  transform: translateX(2px);
}

.player-list button.active {
  color: var(--ui-text);
  background: var(--ui-accent-soft);
  border-color: var(--ui-accent);
}

.player-list__avatar,
.remote-console__avatar,
.profile-card__avatar {
  display: inline-grid;
  flex: 0 0 auto;
  place-items: center;
  color: var(--ui-accent);
  background: var(--ui-accent-soft);
  font-weight: 760;
}

.player-list__avatar {
  width: 34px;
  height: 34px;
  border-radius: 8px;
  font-size: 11px;
}

.player-list__copy {
  display: grid;
  min-width: 0;
  gap: 2px;
}

.player-list__copy strong,
.player-list__copy small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.player-list__copy strong { font-size: 11px; }
.player-list__copy small { color: var(--ui-text-muted); font-size: 8px; }
.player-list__level {
  color: var(--ui-text-muted);
  font-size: 9px;
  font-weight: 650;
}
.player-list button > .app-icon { color: var(--ui-text-muted); }
.player-list button.active > .app-icon { color: var(--ui-accent); }

.sidebar-empty {
  display: flex;
  min-height: 106px;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 8px;
  color: var(--ui-text-muted);
  background: var(--ui-surface-raised);
  border-radius: var(--ui-radius-sm);
  text-align: center;
}

.sidebar-empty > span {
  display: inline-grid;
  width: 38px;
  height: 38px;
  place-items: center;
  color: var(--ui-text-secondary);
  background: var(--ui-canvas);
  border-radius: 9px;
}
.sidebar-empty p { max-width: 24ch; margin: 0; font-size: 10px; }

.guild-list article {
  display: grid;
  min-width: 0;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: 9px;
  padding: 8px;
  background: var(--ui-surface-raised);
  border-radius: var(--ui-radius-sm);
}

.guild-list__icon {
  display: inline-grid;
  width: 30px;
  height: 30px;
  place-items: center;
  color: var(--ui-text-secondary);
  background: var(--ui-canvas);
  border-radius: 7px;
}

.guild-list article > span:last-child {
  display: grid;
  min-width: 0;
  gap: 2px;
}

.guild-list strong,
.guild-list small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.guild-list strong { font-size: 11px; }
.guild-list small,
.empty-copy { color: var(--ui-text-muted); font-size: 9px; }
.empty-copy { margin: 0; line-height: 1.6; }

.capability-card { padding-block: 13px; }
.capability-card summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  color: var(--ui-text-secondary);
  list-style: none;
  font-size: 11px;
  font-weight: 650;
  cursor: pointer;
}
.capability-card summary::-webkit-details-marker { display: none; }
.capability-card summary > span { display: flex; align-items: center; gap: 8px; }
.capability-card summary b {
  display: inline-grid;
  min-width: 24px;
  height: 24px;
  place-items: center;
  color: var(--ui-text-muted);
  background: var(--ui-surface-raised);
  border-radius: 6px;
  font-size: 9px;
}

.capability-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--ui-border);
}
.capability-list code {
  padding: 4px 7px;
  color: var(--ui-text-secondary);
  background: var(--ui-canvas);
  border: 1px solid var(--ui-border);
  border-radius: 5px;
  font-size: 9px;
}

.remote-console {
  min-height: 680px;
  padding: 20px;
}

.remote-console__heading {
  display: grid;
  min-width: 0;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 13px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--ui-border);
}

.remote-console__avatar {
  width: 48px;
  height: 48px;
  border: 1px solid oklch(0.5 0.08 246);
  border-radius: 12px;
  font-size: 16px;
}

.remote-console__heading > div {
  display: grid;
  min-width: 0;
}

.remote-console__heading p {
  margin: 0;
  color: var(--ui-accent);
  font-size: 9px;
  font-weight: 750;
  letter-spacing: .08em;
}

.remote-console__heading h2 {
  margin: 2px 0 0;
  font-size: 20px;
  letter-spacing: -0.025em;
}

.remote-console__heading code {
  overflow: hidden;
  margin-top: 2px;
  color: var(--ui-text-muted);
  font: 9px/1.4 ui-monospace, "Cascadia Code", Consolas, monospace;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.remote-console__level {
  padding: 7px 10px;
  color: var(--ui-accent);
  background: var(--ui-accent-soft);
  border: 1px solid oklch(0.5 0.08 246);
  border-radius: var(--ui-radius-sm);
  font-size: 12px;
  font-weight: 750;
}

.remote-tabs {
  display: flex;
  gap: 4px;
  margin-top: 12px;
  padding: 4px;
  overflow-x: auto;
  background: var(--ui-canvas);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
}

.remote-tabs button {
  display: flex;
  min-height: 36px;
  align-items: center;
  justify-content: center;
  gap: 7px;
  padding: 0 11px;
  color: var(--ui-text-muted);
  background: transparent;
  border: 1px solid transparent;
  border-radius: 6px;
  font: inherit;
  font-size: 11px;
  font-weight: 620;
}

.remote-tabs button:hover {
  color: var(--ui-text);
  background: var(--ui-surface-raised);
}

.remote-tabs button.active {
  color: var(--ui-text);
  background: var(--ui-surface-raised);
  border-color: var(--ui-border-strong);
  box-shadow: 0 1px 2px oklch(0.05 0.02 252 / 0.24);
}

.remote-tabs button.active > .app-icon { color: var(--ui-accent); }
.remote-tabs button.remote-tabs__unavailable > .app-icon,
.remote-tabs button.remote-tabs__unavailable > span { color: var(--ui-warning); }
.remote-tabs span {
  min-width: 19px;
  padding: 1px 5px;
  color: var(--ui-text-muted);
  background: var(--ui-canvas);
  border-radius: 99px;
  font-size: 8px;
  text-align: center;
}

.command-message,
.command-error {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 12px 0 0;
  padding: 10px 12px;
  border: 1px solid transparent;
  border-radius: var(--ui-radius-sm);
  font-size: 11px;
}
.command-message { color: var(--ui-success); background: oklch(0.25 0.055 158); border-color: oklch(0.42 0.07 158); }
.command-error { color: var(--ui-danger); background: var(--ui-danger-soft); border-color: oklch(0.45 0.08 24); }

.detail-panel { margin-top: 16px; }
.detail-skeleton {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-top: 16px;
}

.detail-skeleton span {
  min-height: 106px;
  background: linear-gradient(100deg, var(--ui-surface-raised) 25%, var(--ui-surface-hover) 45%, var(--ui-surface-raised) 65%);
  background-size: 220% 100%;
  border-radius: var(--ui-radius-sm);
  animation: remote-shimmer 1.4s ease-in-out infinite;
}
.detail-skeleton span:first-child {
  min-height: 150px;
  grid-column: 1 / -1;
}

@keyframes remote-shimmer {
  to { background-position: -220% 0; }
}

.data-state {
  display: flex;
  min-height: 330px;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 10px;
  color: var(--ui-text-muted);
  text-align: center;
}

.data-state > span {
  display: inline-grid;
  width: 52px;
  height: 52px;
  place-items: center;
  color: var(--ui-text-secondary);
  background: var(--ui-surface-raised);
  border: 1px solid var(--ui-border);
  border-radius: 13px;
}
.data-state strong { max-width: 52ch; font-size: 12px; font-weight: 620; }
.data-state p { max-width: 64ch; margin: 0; font-size: 11px; line-height: 1.65; }
.data-state--error { min-height: 190px; color: var(--ui-danger); }
.data-state--error > span { color: var(--ui-danger); background: var(--ui-danger-soft); border-color: oklch(0.45 0.08 24); }
.data-state--map-unavailable { min-height: 330px; }
.data-state--map-unavailable > span {
  color: var(--ui-warning);
  background: oklch(0.28 0.045 78);
  border-color: oklch(0.5 0.07 78);
}

.profile-card,
.inventory-group,
.pal-card {
  background: var(--ui-surface-raised);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
}

.profile-card { overflow: hidden; }
.profile-card__hero {
  display: grid;
  min-width: 0;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 14px;
  padding: 18px;
  background:
    linear-gradient(110deg, var(--ui-accent-soft), transparent 64%),
    var(--ui-surface-raised);
}

.profile-card__avatar {
  width: 52px;
  height: 52px;
  border: 1px solid oklch(0.5 0.08 246);
  border-radius: 13px;
  font-size: 17px;
}

.profile-card__hero > div { display: grid; min-width: 0; }
.profile-card__hero small,
.panel-summary small {
  color: var(--ui-text-muted);
  font-size: 9px;
  font-weight: 680;
  letter-spacing: .05em;
}
.profile-card__hero h3,
.panel-summary h3 {
  margin: 3px 0 0;
  font-size: 18px;
  letter-spacing: -0.02em;
}
.profile-card__hero p {
  margin: 3px 0 0;
  overflow: hidden;
  color: var(--ui-text-muted);
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.profile-card__hero > strong { color: var(--ui-accent); font-size: 22px; }

.detail-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1px;
  margin: 1px 0 0;
  background: var(--ui-border);
}

.detail-grid > div {
  min-width: 0;
  min-height: 82px;
  padding: 13px;
  background: var(--ui-surface);
}
.detail-grid dt,
.pal-card dt { color: var(--ui-text-muted); font-size: 9px; }
.detail-grid dd,
.pal-card dd {
  margin: 7px 0 0;
  overflow-wrap: anywhere;
  color: var(--ui-text-secondary);
  font-size: 12px;
  font-weight: 650;
}

.partial-note {
  display: flex;
  align-items: center;
  gap: 7px;
  margin: 0;
  padding: 10px 13px;
  color: oklch(0.82 0.1 80);
  background: oklch(0.27 0.04 80);
  border-top: 1px solid oklch(0.45 0.06 80);
  font-size: 10px;
}

.panel-summary {
  display: grid;
  min-width: 0;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 11px;
  padding: 2px 2px 15px;
}

.panel-summary__icon {
  display: inline-grid;
  width: 40px;
  height: 40px;
  place-items: center;
  color: var(--ui-accent);
  background: var(--ui-accent-soft);
  border-radius: 9px;
}
.panel-summary > div { min-width: 0; }
.panel-summary > strong { color: var(--ui-text-secondary); font-size: 11px; }
.inventory-layout {
  display: grid;
  min-height: 620px;
  grid-template-columns:
    minmax(300px, .95fr)
    minmax(360px, 1.35fr)
    minmax(220px, .68fr);
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
  min-width: 0;
  overflow: hidden;
  background: oklch(0.105 0.02 225 / .94);
  border-right: 1px solid oklch(0.7 0.03 220 / .38);
}

.inventory-container-tabs {
  display: flex;
  min-width: 0;
  overflow-x: auto;
  padding: 5px;
  border-bottom: 1px solid oklch(0.72 0.035 220 / .45);
  scrollbar-width: thin;
}

.inventory-container-tabs button {
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
  transition: color 160ms ease, background-color 160ms ease;
}

.inventory-container-tabs button::after {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  height: 3px;
  background: transparent;
  content: '';
}

.inventory-container-tabs button:hover { color: var(--ui-text); background: oklch(0.24 0.035 220 / .86); }
.inventory-container-tabs button:active { transform: translateY(1px); }
.inventory-container-tabs button:focus-visible { z-index: 1; outline: 2px solid var(--ui-accent); outline-offset: -3px; }
.inventory-container-tabs button.active {
  color: oklch(0.22 0.022 220);
  background: oklch(0.79 0.035 215);
  border-color: oklch(0.9 0.025 210 / .5);
}
.inventory-container-tabs button.active::after { background: var(--ui-accent); }
.inventory-container-tabs span { font-size: 11px; font-weight: 700; white-space: nowrap; }
.inventory-container-tabs button.active small { color: oklch(0.37 0.025 220); }
.inventory-container-tabs small { color: var(--ui-text-muted); font-size: 8px; font-variant-numeric: tabular-nums; }

.inventory-board__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 36px;
  padding: 0 12px;
  color: var(--ui-text-secondary);
  background: oklch(0.12 0.018 225 / .82);
  border-bottom: 1px solid oklch(0.72 0.035 220 / .24);
}

.inventory-board__toolbar > div { display: flex; align-items: center; gap: 7px; }
.inventory-board__toolbar strong { font-size: 11px; }
.inventory-board__toolbar > span { color: var(--ui-text-muted); font-size: 10px; font-variant-numeric: tabular-nums; }

.inventory-slot-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(44px, 1fr));
  gap: 6px;
  padding: 12px;
}

.inventory-slot,
.equipment-slot {
  --slot-rarity: var(--ui-border-strong);
  position: relative;
  display: grid;
  aspect-ratio: 1;
  min-width: 0;
  min-height: 0;
  place-items: center;
  padding: 7px;
  overflow: hidden;
  background: oklch(0.115 0.018 224 / .9);
  border: 1px solid oklch(0.72 0.035 220 / .32);
  border-bottom: 3px solid var(--slot-rarity);
  border-radius: 0;
  box-shadow: inset 0 0 0 1px oklch(1 0 0 / .025);
  transition: background-color 160ms ease, border-color 160ms ease, transform 160ms ease;
}

.inventory-slot:not(.is-empty):hover,
.equipment-slot:not(.is-empty):hover {
  z-index: 1;
  background: oklch(0.2 0.03 220 / .96);
  border-color: var(--slot-rarity);
  transform: translateY(-2px);
}

.inventory-slot--rarity-1 { --slot-rarity: oklch(0.69 0.06 235); }
.inventory-slot--rarity-2 { --slot-rarity: oklch(0.71 0.13 230); }
.inventory-slot--rarity-3 { --slot-rarity: oklch(0.69 0.16 310); }
.inventory-slot--rarity-4,
.inventory-slot--rarity-5 { --slot-rarity: oklch(0.8 0.15 90); }

.inventory-slot.is-empty,
.equipment-slot.is-empty {
  min-height: 0;
  padding: 0;
  background: oklch(0.125 0.015 225 / .72);
  border-bottom-width: 1px;
  opacity: .76;
}

.inventory-slot__index,
.inventory-slot__empty-index {
  position: absolute;
  top: 4px;
  left: 5px;
  color: var(--ui-text-muted);
  font-size: 8px;
  font-variant-numeric: tabular-nums;
}

.inventory-slot__empty-index { opacity: .42; }

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
  transform: translate(-50%, -50%);
  pointer-events: none;
}

.inventory-slot__icon {
  filter: drop-shadow(0 6px 8px oklch(0.04 0.02 252 / .4));
}

.inventory-slot__quantity {
  position: absolute;
  right: 5px;
  bottom: 4px;
  color: var(--ui-text);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  text-shadow: 0 1px 2px oklch(0.04 0.02 252 / .75);
}

.equipment-board {
  min-width: 0;
  padding: 18px 16px;
  background: oklch(0.145 0.023 220 / .84);
  border-right: 1px solid oklch(0.72 0.035 220 / .34);
}

.equipment-stage {
  display: grid;
  min-height: 584px;
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
  grid-row: 1;
  justify-content: space-between;
}

.equipment-model-space {
  min-width: 0;
  grid-column: 2;
  grid-row: 1;
}

.equipment-section {
  min-width: 0;
}

.equipment-section--food {
  grid-column: 1 / -1;
  grid-row: 2;
}

.equipment-section > header {
  display: flex;
  min-height: 27px;
  align-items: center;
  margin-bottom: 7px;
  padding: 0 9px;
  color: oklch(0.83 0.1 205);
  border-left: 3px solid oklch(0.82 0.14 205);
}

.equipment-section > header strong {
  overflow: hidden;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.equipment-slot-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(46px, 72px));
  gap: 7px;
}

.equipment-section--weapon .equipment-slot-grid {
  grid-auto-columns: minmax(46px, 72px);
  grid-auto-flow: column;
  grid-template-columns: none;
  grid-template-rows: repeat(4, minmax(46px, 72px));
}

.equipment-section--head .equipment-slot-grid,
.equipment-section--body .equipment-slot-grid,
.equipment-section--shield .equipment-slot-grid,
.equipment-section--glider .equipment-slot-grid,
.equipment-section--sphere-module .equipment-slot-grid {
  grid-template-columns: minmax(56px, 82px);
}

.equipment-section--food .equipment-slot-grid {
  grid-template-columns: repeat(5, minmax(46px, 72px));
}

.equipment-slot__index {
  position: absolute;
  top: 4px;
  left: 5px;
  color: var(--ui-text-muted);
  font-size: 8px;
  font-variant-numeric: tabular-nums;
}

.equipment-slot__icon {
  max-width: 100%;
  filter: drop-shadow(0 7px 9px oklch(0.03 0.02 230 / .5));
}

.equipment-slot__quantity {
  position: absolute;
  right: 5px;
  bottom: 4px;
  color: var(--ui-text);
  font-size: 10px;
  font-variant-numeric: tabular-nums;
}

.runtime-attributes {
  min-width: 0;
  padding: 16px 14px;
  background: oklch(0.095 0.018 220 / .92);
}

.runtime-player-level {
  display: grid;
  min-height: 70px;
  grid-template-columns: 66px minmax(0, 1fr);
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid oklch(0.72 0.035 220 / .26);
}

.runtime-player-level > strong {
  display: inline-grid;
  height: 58px;
  place-items: center;
  color: oklch(0.92 0.04 205);
  background: oklch(0.3 0.055 213);
  border-left: 4px solid oklch(0.81 0.16 207);
  font-size: 32px;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}

.runtime-player-level > div {
  display: grid;
  min-width: 0;
  gap: 3px;
}

.runtime-player-level small {
  color: oklch(0.8 0.15 205);
  font-size: 10px;
  font-weight: 750;
  letter-spacing: .08em;
}

.runtime-player-level b {
  overflow: hidden;
  color: var(--ui-text);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.runtime-health {
  display: grid;
  gap: 6px;
  margin-bottom: 22px;
}

.runtime-health > div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  color: oklch(0.9 0.04 180);
}

.runtime-health > div > span { display: inline-flex; }
.runtime-health strong {
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.runtime-health progress {
  width: 100%;
  height: 10px;
  overflow: hidden;
  appearance: none;
  background: oklch(0.12 0.018 220);
  border: 0;
  border-radius: 0;
}

.runtime-health progress::-webkit-progress-bar { background: oklch(0.12 0.018 220); }
.runtime-health progress::-webkit-progress-value { background: oklch(0.72 0.16 165); }
.runtime-health progress::-moz-progress-bar { background: oklch(0.72 0.16 165); }

.runtime-attributes__heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 7px;
  padding: 0 2px 5px;
  background: oklch(0.4 0.035 215 / .86);
  border-left: 3px solid oklch(0.82 0.14 205);
}

.runtime-attributes__heading small {
  display: none;
  color: oklch(0.83 0.1 205);
  font-size: 8px;
  font-weight: 700;
  letter-spacing: .07em;
}

.runtime-attributes__heading h3 { margin: 0; padding: 4px 7px 0; font-size: 12px; }

.runtime-attributes__points {
  display: flex;
  min-height: 34px;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 6px;
  padding: 0 9px;
  color: var(--ui-text-muted);
  background: oklch(0.13 0.018 224 / .92);
  border-left: 3px solid var(--ui-border-strong);
  border-bottom: 1px solid var(--ui-text-muted);
  font-size: 10px;
}

.runtime-attributes__points b { font-size: 15px; font-variant-numeric: tabular-nums; }
.runtime-attributes dl { display: grid; gap: 5px; margin: 0; }
.runtime-attributes dl > div {
  display: grid;
  min-height: 37px;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 0 9px;
  background: oklch(0.105 0.017 222 / .94);
  border-left: 2px solid transparent;
}

.runtime-attributes dt {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 7px;
  color: var(--ui-text-secondary);
  font-size: 11px;
}

.runtime-attributes dt > span { color: var(--ui-text); }
.runtime-attributes dt > span {
  display: inline-grid;
  width: 20px;
  height: 20px;
  flex: 0 0 20px;
  place-items: center;
}
.runtime-attributes dt img {
  width: 18px;
  height: 18px;
  object-fit: contain;
  filter: grayscale(1) brightness(1.55) contrast(.9);
}
.runtime-attributes dd {
  display: flex;
  align-items: baseline;
  gap: 5px;
  margin: 0;
  color: var(--ui-text);
  font-size: 14px;
  font-weight: 650;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.runtime-attributes dd.is-partial { color: var(--ui-text-muted); }
.runtime-attributes dd small { color: var(--ui-accent); font-size: 7px; font-weight: 700; }
.runtime-attributes__note {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin: 10px 0 0;
  color: var(--ui-text-muted);
  font-size: 9px;
  line-height: 1.45;
}

.pal-collection-tabs {
  display: inline-flex;
  gap: 3px;
  margin-bottom: 12px;
  padding: 3px;
  background: var(--ui-canvas);
  border: 1px solid var(--ui-border);
  border-radius: 9px;
}

.pal-collection-tabs button {
  display: inline-flex;
  min-height: 32px;
  align-items: center;
  gap: 7px;
  padding: 0 12px;
  color: var(--ui-text-muted);
  font: inherit;
  font-size: 10px;
  font-weight: 700;
  background: transparent;
  border: 0;
  border-radius: 6px;
  cursor: pointer;
}

.pal-collection-tabs button:hover { color: var(--ui-text); background: var(--ui-surface-hover); }
.pal-collection-tabs button.active { color: var(--ui-text); background: var(--ui-surface-raised); box-shadow: var(--ui-shadow-sm); }
.pal-collection-tabs button:focus-visible { outline: 2px solid var(--ui-accent); outline-offset: 1px; }

.pal-collection { display: grid; gap: 8px; }
.pal-collection--party { grid-template-columns: minmax(280px, 520px); }
.pal-collection--palbox { grid-template-columns: repeat(auto-fill, minmax(78px, 1fr)); }
.pal-pagination {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 12px;
}
.pal-pagination > span {
  min-width: 72px;
  color: var(--ui-text-secondary);
  font-size: 10px;
  text-align: center;
}

.operation-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 16px;
}

.operation-card {
  display: flex;
  min-width: 0;
  min-height: 220px;
  flex-direction: column;
  gap: 12px;
  padding: 15px;
  background: var(--ui-surface-raised);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
}

.operation-card__heading {
  display: grid;
  min-width: 0;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: 10px;
}

.operation-card__heading > span {
  display: inline-grid;
  width: 38px;
  height: 38px;
  place-items: center;
  color: var(--ui-accent);
  background: var(--ui-accent-soft);
  border-radius: 9px;
}

.operation-card__heading > div { min-width: 0; }
.operation-card h3,
.operation-card p { margin: 0; }
.operation-card h3 { font-size: 14px; letter-spacing: -0.01em; }
.operation-card p { color: var(--ui-text-muted); font-size: 11px; line-height: 1.65; }
.operation-card label { display: grid; gap: 5px; color: var(--ui-text-muted); font-size: 10px; }
.operation-card input {
  width: 100%;
  min-height: 38px;
  padding: 0 10px;
  color: var(--ui-text);
  background: var(--ui-surface);
  border: 1px solid var(--ui-border-strong);
  border-radius: var(--ui-radius-sm);
  font: inherit;
}
.operation-card input:focus { border-color: var(--ui-accent); box-shadow: 0 0 0 3px oklch(0.72 0.14 246 / 0.14); outline: 0; }
.operation-card .remote-button { align-self: flex-start; margin-top: auto; }
.operation-card--world {
  background:
    linear-gradient(135deg, oklch(0.27 0.045 158 / 0.56), transparent 70%),
    var(--ui-surface-raised);
  border-color: oklch(0.42 0.06 158);
}
.operation-card--world .operation-card__heading > span { color: var(--ui-success); background: oklch(0.25 0.05 158); }
.operation-card--empty {
  grid-column: 1 / -1;
  min-height: 240px;
  align-items: center;
  justify-content: center;
  text-align: center;
}
.operation-card--empty > span {
  display: inline-grid;
  width: 52px;
  height: 52px;
  place-items: center;
  color: var(--ui-text-muted);
  background: var(--ui-canvas);
  border-radius: 13px;
}
.operation-card--empty p { max-width: 58ch; }

@media (max-width: 1240px) {
  .remote-metrics { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .remote-metrics article:nth-child(4) { border-left: 0; }
  .remote-metrics article:nth-child(n + 4) { border-top: 1px solid var(--ui-border); }
  .remote-workspace { grid-template-columns: minmax(270px, 300px) minmax(0, 1fr); }
}

@media (max-width: 920px) {
  .remote-workspace { grid-template-columns: minmax(0, 1fr); }
  .remote-sidebar {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .remote-card--players { grid-row: span 2; }
  .player-list { max-height: 360px; }
  .inventory-layout {
    grid-template-columns: minmax(300px, .9fr) minmax(360px, 1.1fr);
  }
  .runtime-attributes {
    grid-column: 1 / -1;
    border-top: 1px solid oklch(0.72 0.035 220 / .34);
  }
}

@media (max-width: 700px) {
  .remote-page { padding: 78px 10px 32px; }
  .remote-header { align-items: stretch; flex-direction: column; gap: 16px; }
  .remote-header__actions { width: 100%; }
  .remote-header__actions .remote-button { flex: 1 1 0; }
  .remote-source__meta,
  .remote-source code { display: none; }
  .remote-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .remote-metrics article:nth-child(n) { border-top: 0; border-left: 0; }
  .remote-metrics article:nth-child(even) { border-left: 1px solid var(--ui-border); }
  .remote-metrics article:nth-child(n + 3) { border-top: 1px solid var(--ui-border); }
  .remote-sidebar { grid-template-columns: minmax(0, 1fr); }
  .remote-card--players { grid-row: auto; }
  .remote-console { padding: 13px; }
  .remote-tabs { justify-content: flex-start; }
  .remote-tabs button { flex: 0 0 auto; }
  .inventory-layout { grid-template-columns: minmax(0, 1fr); }
  .inventory-board,
  .equipment-board {
    border-right: 0;
    border-bottom: 1px solid oklch(0.72 0.035 220 / .34);
  }
  .equipment-stage { min-height: 520px; }
  .detail-grid,
  .detail-skeleton,
  .operation-grid { grid-template-columns: minmax(0, 1fr); }
  .detail-skeleton span:first-child { grid-column: auto; }
}

@media (max-width: 480px) {
  .remote-heading h1 { font-size: 27px; }
  .remote-metrics { grid-template-columns: minmax(0, 1fr); }
  .remote-metrics article:nth-child(n) { border-left: 0; border-top: 1px solid var(--ui-border); }
  .remote-metrics article:first-child { border-top: 0; }
  .remote-console__heading { grid-template-columns: auto minmax(0, 1fr); }
  .remote-console__level { display: none; }
  .profile-card__hero { grid-template-columns: auto minmax(0, 1fr); }
  .profile-card__hero > strong { grid-column: 2; font-size: 16px; }
  .inventory-slot-grid {
    grid-template-columns: repeat(5, minmax(44px, 1fr));
    gap: 5px;
    padding: 9px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .detail-skeleton span { animation: none; }
  .player-list button:hover { transform: none; }
}
</style>
