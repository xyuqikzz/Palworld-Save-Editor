<script setup>
import { onMounted } from 'vue'

import AppIcon from '@/components/modules/AppIcon.vue'
import { usePalEditorStore } from '@/stores/paleditor'

const palStore = usePalEditorStore()

onMounted(() => {
  palStore.loadExpeditions()
})
</script>

<template>
  <main class="expedition-page">
    <section class="expedition-shell">
      <section class="maintenance-section">
        <div class="expedition-grid">
          <article class="operation-card">
            <div class="operation-card__icon"><AppIcon name="clock" :size="20" /></div>
            <div class="operation-card__content">
              <span class="operation-card__count">{{ palStore.COMPLETABLE_EXPEDITION_COUNT }}</span>
              <h2>{{ palStore.getTranslatedText('TopBar_Btn_CompleteExpeditions') }}</h2>
              <p>{{ palStore.getTranslatedText('TopBar_Btn_CompleteExpeditions_Tooltips') }}</p>
            </div>
            <button
              class="operation-button operation-button--primary"
              type="button"
              :disabled="palStore.LOADING_FLAG || palStore.RAW_JSON_PENDING || palStore.COMPLETABLE_EXPEDITION_COUNT === 0"
              @click="palStore.completeActiveExpeditions"
            >
              {{ palStore.getTranslatedText(
                palStore.COMPLETABLE_EXPEDITION_COUNT === 0
                  ? 'TopBar_Btn_CompleteExpeditions_Disabled'
                  : 'TopBar_Btn_CompleteExpeditions'
              ) }}
            </button>
          </article>

          <article class="operation-card">
            <div class="operation-card__icon"><AppIcon name="pin" :size="20" /></div>
            <div class="operation-card__content">
              <span class="operation-card__count">{{ palStore.EXPEDITION_PAL_COUNT }}</span>
              <h2>{{ palStore.getTranslatedText('TopBar_Btn_UnlockExpeditionPals') }}</h2>
              <p>{{ palStore.getTranslatedText('TopBar_Btn_UnlockExpeditionPals_Tooltips') }}</p>
            </div>
            <button
              class="operation-button"
              type="button"
              :disabled="palStore.LOADING_FLAG || palStore.RAW_JSON_PENDING || palStore.EXPEDITION_PAL_COUNT === 0"
              @click="palStore.unlockExpeditionPals"
            >
              {{ palStore.getTranslatedText(
                palStore.EXPEDITION_PAL_COUNT === 0
                  ? 'TopBar_Btn_UnlockExpeditionPals_Disabled'
                  : 'TopBar_Btn_UnlockExpeditionPals'
              ) }}
            </button>
          </article>
        </div>
      </section>

      <section class="expedition-content">
        <div class="section-heading">
          <div>
            <p>{{ palStore.getTranslatedText('Expedition_ActiveEyebrow') }}</p>
            <h2>{{ palStore.getTranslatedText('Expedition_ActiveTitle') }}</h2>
          </div>
          <button
            class="refresh-button"
            type="button"
            :disabled="palStore.EXPEDITION_LOADING || palStore.LOADING_FLAG"
            @click="palStore.loadExpeditions"
          >
            <AppIcon name="refresh" :size="16" />
            {{ palStore.getTranslatedText('Expedition_Refresh') }}
          </button>
        </div>

        <div v-if="palStore.EXPEDITION_LOADING && !palStore.EXPEDITION_DATA" class="expedition-state">
          {{ palStore.getTranslatedText('Expedition_Loading') }}
        </div>
        <div
          v-else-if="palStore.EXPEDITION_DATA && !palStore.EXPEDITION_DATA.data_available"
          class="expedition-state expedition-state--warning"
        >
          {{ palStore.getTranslatedText('Expedition_DataUnavailable') }}
        </div>
        <div
          v-else-if="!palStore.EXPEDITION_DATA?.expeditions?.length"
          class="expedition-state"
        >
          {{ palStore.getTranslatedText('Expedition_Empty') }}
        </div>
        <div v-else class="active-expeditions">
          <article
            v-for="expedition in palStore.EXPEDITION_DATA.expeditions"
            :key="expedition.expedition_id"
            class="expedition-card"
          >
            <header class="expedition-card__header">
              <div>
                <div class="expedition-card__labels">
                  <span>{{ expedition.guild_name || palStore.getTranslatedText('Expedition_UnknownGuild') }}</span>
                  <span>{{
                    expedition.base_number
                      ? palStore.getTranslatedText('PlayerTree_BaseNumber', [expedition.base_number])
                      : palStore.getTranslatedText('Expedition_UnknownBase')
                  }}</span>
                </div>
                <h3>{{ expedition.mission_id || palStore.getTranslatedText('Expedition_UnknownMission') }}</h3>
                <code>{{ expedition.expedition_id }}</code>
              </div>
              <button
                class="operation-button operation-button--primary"
                type="button"
                :disabled="palStore.LOADING_FLAG || palStore.RAW_JSON_PENDING || !expedition.can_complete"
                @click="palStore.completeExpedition(expedition.expedition_id)"
              >
                {{ palStore.getTranslatedText(
                  expedition.can_complete
                    ? 'Expedition_QuickComplete'
                    : 'Expedition_AwaitingSettlement'
                ) }}
              </button>
            </header>

            <div class="member-heading">
              <strong>
                {{ palStore.getTranslatedText('Expedition_Members', [expedition.member_count]) }}
              </strong>
              <span>
                {{ palStore.getTranslatedText('Expedition_BaseId') }} {{ expedition.base_id || '-' }}
              </span>
            </div>
            <div class="expedition-members">
              <article
                v-for="pal in expedition.members"
                :key="pal.pal_id"
                class="member-card"
              >
                <img
                  v-if="pal.icon_access_key"
                  :src="`/image/pals/${pal.icon_access_key}`"
                  :alt="pal.name"
                  loading="lazy"
                  draggable="false"
                >
                <span v-else class="member-card__fallback">
                  {{ (pal.name || '?').slice(0, 1) }}
                </span>
                <span>
                  <strong>{{ pal.name || pal.internal_id || pal.pal_id }}</strong>
                  <small>
                    {{ pal.internal_id || pal.pal_id }}
                    <template v-if="pal.level">
                      · {{ palStore.getTranslatedText('Common_LevelShort') }}{{ pal.level }}
                    </template>
                  </small>
                </span>
              </article>
            </div>
          </article>
        </div>
      </section>

      <section
        v-if="
          palStore.EXPEDITION_DATA?.invalid_locked_pals?.length
          || palStore.EXPEDITION_DATA?.unknown_locked_pals?.length
        "
        class="locked-section"
      >
        <div class="section-heading">
          <div>
            <p>{{ palStore.getTranslatedText('Expedition_LockedEyebrow') }}</p>
            <h2>{{ palStore.getTranslatedText('Expedition_InvalidLockedTitle') }}</h2>
          </div>
        </div>
        <p class="locked-section__description">
          {{ palStore.getTranslatedText('Expedition_InvalidLockedDescription') }}
        </p>
        <div class="locked-grid">
          <article
            v-for="pal in [
              ...(palStore.EXPEDITION_DATA.invalid_locked_pals || []),
              ...(palStore.EXPEDITION_DATA.unknown_locked_pals || []),
            ]"
            :key="pal.pal_id"
            class="locked-card"
          >
            <img
              v-if="pal.icon_access_key"
              :src="`/image/pals/${pal.icon_access_key}`"
              :alt="pal.name"
              loading="lazy"
              draggable="false"
            >
            <span v-else class="member-card__fallback">
              {{ (pal.name || '?').slice(0, 1) }}
            </span>
            <span>
              <strong>{{ pal.name || pal.internal_id || pal.pal_id }}</strong>
              <small>{{ pal.expedition_id || '-' }}</small>
            </span>
            <b :class="`status-${pal.assignment_status}`">
              {{ palStore.getTranslatedText(
                pal.assignment_status === 'invalid'
                  ? 'Expedition_Status_Invalid'
                  : 'Expedition_Status_Unknown'
              ) }}
            </b>
          </article>
        </div>
      </section>

      <footer class="expedition-footer">
        {{ palStore.getTranslatedText('Expedition_SaveHint') }}
      </footer>
    </section>
  </main>
</template>

<style scoped>
.expedition-page {
  box-sizing: border-box;
  min-height: 100dvh;
  padding: var(--editor-top-offset) 16px 28px;
  color: var(--ui-text);
  background: var(--ui-canvas);
}

.expedition-shell {
  width: min(1180px, 100%);
  margin: 0 auto;
  overflow: hidden;
  background: var(--ui-surface);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-md);
  box-shadow: var(--ui-shadow-md);
}

.expedition-content,
.locked-section,
.maintenance-section {
  padding: 20px;
  border-bottom: 1px solid var(--ui-border);
}

.section-heading,
.expedition-card__header,
.member-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.section-heading {
  margin-bottom: 14px;
}

.section-heading p {
  margin: 0 0 3px;
  color: var(--ui-accent);
  font-size: 9px;
  font-weight: 750;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.section-heading h2 {
  margin: 0;
  font-size: 18px;
}

.refresh-button {
  display: inline-flex;
  min-height: 34px;
  align-items: center;
  gap: 7px;
  padding: 0 11px;
  color: var(--ui-text-secondary);
  background: var(--ui-surface);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
  font: inherit;
  font-size: 11px;
}

.refresh-button:disabled {
  opacity: 0.45;
}

.expedition-state {
  padding: 28px 20px;
  color: var(--ui-text-muted);
  text-align: center;
  background: var(--ui-canvas);
  border: 1px dashed var(--ui-border);
  border-radius: var(--ui-radius-sm);
}

.expedition-state--warning {
  color: var(--ui-danger);
}

.active-expeditions {
  display: grid;
  gap: 12px;
}

.expedition-card {
  overflow: hidden;
  background: var(--ui-canvas);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-md);
}

.expedition-card__header {
  align-items: flex-start;
  padding: 17px 18px;
  background: var(--ui-surface-raised);
  border-bottom: 1px solid var(--ui-border);
}

.expedition-card__labels {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.expedition-card__labels span {
  padding: 4px 7px;
  color: var(--ui-accent);
  background: var(--ui-accent-soft);
  border-radius: 999px;
  font-size: 10px;
  font-weight: 650;
}

.expedition-card h3 {
  margin: 0 0 4px;
  font-size: 16px;
}

.expedition-card code {
  color: var(--ui-text-muted);
  font-size: 9px;
}

.member-heading {
  padding: 12px 18px 8px;
}

.member-heading strong {
  font-size: 12px;
}

.member-heading span {
  color: var(--ui-text-muted);
  font-size: 9px;
}

.expedition-members {
  display: grid;
  max-height: 330px;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 7px;
  overflow-y: auto;
  padding: 0 18px 18px;
}

.member-card,
.locked-card {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 9px;
  padding: 8px;
  background: var(--ui-surface);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
}

.member-card img,
.locked-card img,
.member-card__fallback {
  width: 34px;
  height: 34px;
  flex: 0 0 34px;
  object-fit: contain;
  border-radius: 8px;
}

.member-card__fallback {
  display: grid;
  place-items: center;
  color: var(--ui-accent);
  background: var(--ui-accent-soft);
  font-weight: 700;
}

.member-card > span:last-child,
.locked-card > span:nth-child(2) {
  display: grid;
  min-width: 0;
  gap: 2px;
}

.member-card strong,
.locked-card strong,
.member-card small,
.locked-card small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.member-card strong,
.locked-card strong {
  font-size: 11px;
}

.member-card small,
.locked-card small {
  color: var(--ui-text-muted);
  font-size: 9px;
}

.locked-section {
  background: color-mix(in oklch, var(--ui-danger) 4%, var(--ui-surface));
}

.locked-section__description {
  margin: -5px 0 14px;
  color: var(--ui-text-muted);
  font-size: 11px;
}

.locked-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.locked-card b {
  margin-left: auto;
  padding: 4px 6px;
  border-radius: 999px;
  font-size: 9px;
  white-space: nowrap;
}

.status-invalid {
  color: var(--ui-danger);
  background: color-mix(in oklch, var(--ui-danger) 12%, transparent);
}

.status-unknown {
  color: var(--ui-text-secondary);
  background: var(--ui-surface-hover);
}

.maintenance-section .expedition-grid {
  padding: 0;
}

.expedition-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  padding: 20px;
}

.operation-card {
  display: grid;
  min-width: 0;
  min-height: 270px;
  grid-template-rows: auto minmax(0, 1fr) auto;
  align-items: start;
  gap: 18px;
  padding: 22px;
  background: var(--ui-canvas);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-md);
}

.operation-card__icon {
  display: grid;
  width: 38px;
  height: 38px;
  place-items: center;
  color: var(--ui-accent);
  background: var(--ui-accent-soft);
  border: 1px solid color-mix(in oklch, var(--ui-accent) 55%, var(--ui-border));
  border-radius: var(--ui-radius-sm);
}

.operation-card__content {
  position: relative;
  min-width: 0;
  padding-right: 50px;
}

.operation-card__count {
  position: absolute;
  top: -4px;
  right: 0;
  color: var(--ui-text-muted);
  font-size: 28px;
  font-weight: 700;
  line-height: 1;
}

.operation-card h2 {
  margin: 0 0 9px;
  font-size: 16px;
  letter-spacing: -0.02em;
}

.operation-card p {
  margin: 0;
  color: var(--ui-text-muted);
  font-size: 12px;
  line-height: 1.6;
}

.operation-button {
  display: inline-flex;
  min-height: 38px;
  align-items: center;
  justify-content: center;
  padding: 0 14px;
  color: var(--ui-text-secondary);
  background: var(--ui-surface);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
  font: inherit;
  font-size: 12px;
  font-weight: 650;
}

.operation-button:hover:not(:disabled) {
  color: var(--ui-text);
  background: var(--ui-surface-hover);
  border-color: var(--ui-border-strong);
}

.operation-button--primary {
  color: oklch(0.16 0.025 252);
  background: var(--ui-accent);
  border-color: var(--ui-accent);
}

.operation-button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.expedition-footer {
  padding: 15px 28px 18px;
  color: var(--ui-text-muted);
  border-top: 1px solid var(--ui-border);
  font-size: 11px;
}

@media (max-width: 920px) {
  .expedition-members { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .locked-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .expedition-grid { grid-template-columns: 1fr; }
  .operation-card {
    min-height: auto;
    grid-template-columns: auto minmax(0, 1fr) auto;
    grid-template-rows: auto;
    align-items: center;
  }
}

@media (max-width: 620px) {
  .expedition-page { padding-inline: 8px; }
  .expedition-content,
  .locked-section,
  .maintenance-section { padding: 12px; }
  .section-heading,
  .expedition-card__header,
  .member-heading {
    align-items: stretch;
    flex-direction: column;
  }
  .expedition-card__header .operation-button { width: 100%; }
  .expedition-members,
  .locked-grid { grid-template-columns: 1fr; }
  .member-heading span { overflow-wrap: anywhere; }
  .expedition-grid { padding: 12px; }
  .maintenance-section .expedition-grid { padding: 0; }
  .operation-card {
    grid-template-columns: auto minmax(0, 1fr);
  }
  .operation-button { grid-column: 1 / -1; width: 100%; }
  .expedition-footer { padding-inline: 20px; }
}
</style>
