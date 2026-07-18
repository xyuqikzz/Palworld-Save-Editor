<script setup>
import { usePalEditorStore } from '@/stores/paleditor'
import AppIcon from '@/components/modules/AppIcon.vue'
import { ref, onMounted, nextTick } from "vue";
const palStore = usePalEditorStore()
const playerListContainer = ref(null);
onMounted(async () => {
  await nextTick(); // Wait for the DOM to update with the dynamic buttons
  const buttons = playerListContainer.value.querySelectorAll('button:not(:disabled)');
  if (buttons.length > 0) {
    buttons[0].click(); // Simulate a click on the first enabled button
  }
});
</script>

<template>
  <aside class="flex list-panel player-panel">
    <div class="title panel-title">
      <div>
        <p>{{ palStore.getTranslatedText("PlayerList_Text") }}</p>
        <span>{{ palStore.PLAYER_MAP.size }}</span>
      </div>
      <div class="tooltip-container">
        <button class="playerSettings"
          v-if="palStore.SELECTED_PLAYER_ID != null && !palStore.PLAYER_MAP.get(palStore.SELECTED_PLAYER_ID)?.HasViewingCage"
          :title="palStore.getTranslatedText('PlayerList_Viewing_Cage')" :disabled="palStore.LOADING_FLAG"
          @click="palStore.updatePlayer" name="unlock_viewing_cage"><AppIcon name="snowflake" :size="16" /></button>
        <span class="tooltip-text">{{ palStore.getTranslatedText('PlayerList_Viewing_Cage') }}</span>
      </div>
    </div>
    <div class="overflow-list" ref="playerListContainer">
      <div class="overflow-container" v-if="palStore.HAS_WORKING_PAL_FLAG">
        <button class="player" @click="palStore.selectPlayer(palStore.PAL_BASE_WORKER_BTN)"
          :disabled="palStore.BASE_PAL_BTN_CLK_FLAG || palStore.LOADING_FLAG">
          {{ palStore.getTranslatedText('PlayerList_Base_Pal') }}
        </button>
      </div>
      <div class="overflow-container" v-for="player in palStore.PLAYER_MAP.values()" :key="player.InstanceId">
        <button class="player real" @click="palStore.selectPlayer(player.InstanceId)" :title="player.InstanceId"
          :disabled="(player.InstanceId == palStore.SELECTED_PLAYER_ID && palStore.SHOW_PLAYER_EDIT_FLAG) || palStore.LOADING_FLAG"
          :selected="player.InstanceId == palStore.SELECTED_PLAYER_ID"
          :aria-current="player.InstanceId == palStore.SELECTED_PLAYER_ID ? 'true' : undefined">
          {{ player.NickName }}
        </button>
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
  gap: 3px;
}

.overflow-container {
  display: flex;
  flex-shrink: 0;
  min-width: 0;
}

button.player {
  width: 100%;
  min-width: 0;
  overflow: hidden;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
}

button.playerSettings {
  flex: 0 0 auto;
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

.tooltip-container { position: relative; }
.tooltip-container:hover .tooltip-text { visibility: visible; opacity: 1; }

</style>
