<script setup>
import { usePalEditorStore } from '@/stores/paleditor'
import { useRoute } from 'vue-router'
import AppIcon from '@/components/modules/AppIcon.vue'
import { ref, onMounted, nextTick, watch } from "vue";
const palStore = usePalEditorStore()
const route = useRoute()
const props = defineProps({
  mode: {
    type: String,
    default: 'player',
    validator: value => ['pal', 'player'].includes(value),
  },
})
const playerListContainer = ref(null);
const expandedGuilds = ref(new Set());

function toggleGuild(nodeId) {
  const next = new Set(expandedGuilds.value);
  if (next.has(nodeId)) next.delete(nodeId);
  else next.add(nodeId);
  expandedGuilds.value = next;
}

function isExpanded(nodeId) {
  return expandedGuilds.value.has(nodeId);
}

function shortId(value) {
  return value ? String(value).slice(-8) : '';
}

function guildName(guild) {
  if (guild.kind === 'no_guild') {
    return palStore.getTranslatedText('PlayerTree_NoGuild');
  }
  if (guild.kind === 'unknown') {
    return palStore.getTranslatedText('PlayerTree_UnknownGuild', [shortId(guild.guild_id)]);
  }
  return guild.name || palStore.getTranslatedText('PlayerTree_UnnamedGuild');
}

function baseName(base, index) {
  if (base.kind === 'unmatched') {
    return palStore.getTranslatedText('PlayerTree_UnrecognizedBase');
  }
  return palStore.getTranslatedText('PlayerTree_BaseNumber', [index + 1]);
}

async function selectMember(playerId) {
  await palStore.selectPlayer(playerId, false, props.mode === 'pal');
}

watch(
  () => palStore.GUILD_TREE.map(guild => guild.node_id).join('|'),
  () => {
    const validIds = new Set(palStore.GUILD_TREE.map(guild => guild.node_id));
    const next = new Set(
      Array.from(expandedGuilds.value).filter(nodeId => validIds.has(nodeId))
    );
    if (next.size === 0 && palStore.GUILD_TREE[0]) {
      next.add(palStore.GUILD_TREE[0].node_id);
    }
    expandedGuilds.value = next;
  },
  { immediate: true },
);

onMounted(async () => {
  if (!['Editor', 'Players'].includes(route.name)) return;
  await nextTick();
  const firstMember = playerListContainer.value?.querySelector('button.member-item:not(:disabled)');
  const firstTarget = props.mode === 'pal'
    ? playerListContainer.value?.querySelector('button.base-item[data-has-workers="true"]:not(:disabled)')
      || firstMember
    : firstMember;
  if (firstTarget) firstTarget.click();
});
</script>

<template>
  <aside class="flex list-panel player-panel">
    <div class="title panel-title">
      <div>
        <p>{{ palStore.getTranslatedText("PlayerTree_Title") }}</p>
        <span>{{ palStore.GUILD_TREE.length }}</span>
      </div>
      <div class="tooltip-container panel-action-slot">
        <template v-if="palStore.SELECTED_PLAYER_ID != null && !palStore.PLAYER_MAP.get(palStore.SELECTED_PLAYER_ID)?.HasViewingCage">
          <button class="playerSettings" type="button"
            :title="palStore.getTranslatedText('PlayerList_Viewing_Cage')" :disabled="palStore.LOADING_FLAG"
            @click="palStore.updatePlayer" name="unlock_viewing_cage"><AppIcon name="snowflake" :size="16" /></button>
          <span class="tooltip-text">{{ palStore.getTranslatedText('PlayerList_Viewing_Cage') }}</span>
        </template>
      </div>
    </div>
    <div class="overflow-list guild-tree" ref="playerListContainer">
      <section class="guild-group" v-for="guild in palStore.GUILD_TREE" :key="guild.node_id">
        <div class="guild-toggle">
          <button class="guild-expand" type="button" @click="toggleGuild(guild.node_id)"
            :aria-expanded="isExpanded(guild.node_id)"
            :title="guildName(guild)">
            <AppIcon :class="['guild-chevron', { expanded: isExpanded(guild.node_id) }]"
              name="chevron-down" :size="15" />
            <span class="guild-name">{{ guildName(guild) }}</span>
            <span v-if="guild.kind === 'independent'" class="guild-kind">
              {{ palStore.getTranslatedText('PlayerTree_Independent') }}
            </span>
            <span class="guild-summary">
              <template v-if="props.mode === 'player'">
                {{ guild.member_count }} {{ palStore.getTranslatedText('PlayerTree_Members') }}
              </template>
              <template v-else>
                {{ palStore.getTranslatedText('PlayerTree_Summary', [guild.member_count, guild.base_count]) }}
              </template>
            </span>
          </button>
        </div>

        <div class="guild-children" v-if="isExpanded(guild.node_id)">
          <template v-if="props.mode === 'pal' && guild.bases.length">
            <p class="tree-section-label">{{ palStore.getTranslatedText('PlayerTree_Bases') }}</p>
            <button class="tree-item base-item" type="button" data-selectable
              v-for="(base, index) in guild.bases" :key="base.node_id"
              :data-has-workers="base.worker_count > 0"
              @click="palStore.selectBase(guild, base)"
              :title="palStore.getTranslatedText('PlayerTree_WorkerCount', [base.worker_count])"
              :disabled="palStore.SELECTED_BASE_KEY === base.node_id || palStore.LOADING_FLAG"
              :selected="palStore.SELECTED_BASE_KEY === base.node_id"
              :aria-current="palStore.SELECTED_BASE_KEY === base.node_id ? 'true' : undefined">
              <AppIcon :name="base.kind === 'unmatched' ? 'warning' : 'building'" :size="15" />
              <span class="tree-item-name">{{ baseName(base, index) }}</span>
              <span class="tree-item-meta">{{ base.worker_count }}</span>
            </button>
          </template>

          <template v-if="guild.members.length">
            <p class="tree-section-label">{{ palStore.getTranslatedText('PlayerTree_Members') }}</p>
            <button class="tree-item member-item" type="button" data-selectable
              v-for="member in guild.members" :key="member.player_id"
              @click="selectMember(member.player_id)" :title="member.player_id"
              :disabled="member.player_id === palStore.SELECTED_PLAYER_ID || palStore.LOADING_FLAG"
              :selected="member.player_id === palStore.SELECTED_PLAYER_ID"
              :aria-current="member.player_id === palStore.SELECTED_PLAYER_ID ? 'true' : undefined">
              <AppIcon name="user" :size="15" />
              <span class="tree-item-name">{{ member.name }}</span>
              <span class="tree-item-meta">{{ palStore.getTranslatedText('Common_LevelWithValue', [member.level]) }}</span>
            </button>
          </template>
        </div>
      </section>

      <div class="tree-empty" v-if="palStore.GUILD_TREE.length === 0">
        {{ palStore.getTranslatedText('PlayerTree_Empty') }}
      </div>
    </div>
  </aside>
</template>

<style scoped>
.list-panel {
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  height: 100%;
  width: 100%;
  min-width: 0;
}

.panel-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.panel-title > div:first-child {
  min-width: 0;
  display: flex;
  align-items: baseline;
  gap: 7px;
}

.panel-title span {
  color: var(--ui-text-muted);
  font-size: 11px;
  font-weight: 500;
}

.overflow-list {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow-y: auto;
}

.guild-tree {
  gap: 8px;
  padding: 8px 6px 10px;
}

.guild-group {
  min-width: 0;
}

.guild-toggle,
.guild-expand,
.tree-item {
  display: flex;
  align-items: center;
  width: 100%;
  min-width: 0;
  border: 0;
  text-align: left;
}

.guild-toggle {
  min-height: 36px;
  gap: 8px;
  padding: 6px 8px;
  color: var(--ui-text);
  background: var(--ui-surface-raised);
  border-radius: var(--ui-radius-sm);
}

.guild-toggle:hover {
  background: var(--ui-surface-hover);
}

.guild-expand {
  flex: 1 1 auto;
  gap: 8px;
  padding: 0;
  color: inherit;
  background: transparent;
}

.guild-chevron {
  transform: rotate(-90deg);
  transition: transform 140ms ease-out;
}

.guild-chevron.expanded {
  transform: rotate(0deg);
}

.guild-name,
.tree-item-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.guild-name {
  flex: 1 1 auto;
  font-weight: 700;
}

.guild-kind {
  flex: 0 0 auto;
  padding: 1px 5px;
  color: var(--ui-accent);
  background: var(--ui-accent-soft);
  border-radius: 5px;
  font-size: 9px;
}

.guild-summary,
.tree-item-meta {
  flex: 0 0 auto;
  color: var(--ui-text-muted);
  font-size: 10px;
}

.guild-children {
  display: grid;
  gap: 2px;
  padding: 6px 4px 4px 12px;
}

.tree-section-label {
  margin: 4px 8px 2px;
  color: var(--ui-text-muted);
  font-size: 10px;
  font-weight: 700;
}

.tree-section-label:not(:first-child) {
  margin-top: 8px;
}

.tree-item {
  min-height: 32px;
  gap: 8px;
  padding: 5px 8px;
  color: var(--ui-text-secondary);
  background: transparent;
  border-radius: var(--ui-radius-sm);
}

.tree-item:hover:not(:disabled) {
  color: var(--ui-text);
  background: var(--ui-surface-hover);
}

.tree-item[selected="true"] {
  color: var(--ui-text);
  background: var(--ui-accent-soft);
  opacity: 1;
}

.tree-item:disabled:not([selected="true"]) {
  color: var(--ui-text-muted);
  background: transparent;
  opacity: 0.72;
}

.tree-item-name {
  flex: 1 1 auto;
}

.base-item > .app-icon {
  color: var(--ui-accent);
}

.tree-empty {
  padding: 18px 10px;
  color: var(--ui-text-muted);
  text-align: left;
  font-size: 11px;
}

.panel-action-slot {
  position: relative;
  width: 32px;
  height: 32px;
  flex: 0 0 32px;
}

.panel-action-slot > button.playerSettings {
  display: inline-flex;
  width: 100%;
  height: 100%;
  align-items: center;
  justify-content: center;
  margin: 0;
  padding: 0;
  line-height: 1;
}

.tooltip-text {
  visibility: hidden;
  opacity: 0;
  width: 200px;
  padding: 8px 10px;
  position: absolute;
  z-index: 60;
  top: 44px;
  left: -70px;
  transition: opacity 140ms ease;
}

.tooltip-container:hover .tooltip-text { visibility: visible; opacity: 1; }

@media (prefers-reduced-motion: reduce) {
  .guild-chevron { transition: none; }
}

</style>
