<script setup>
import AppIcon from '@/components/modules/AppIcon.vue'
import { getArenaNpcName } from '@/data/arenaNpcNames'
import { usePalEditorStore } from '@/stores/paleditor'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

const palStore = usePalEditorStore()
const router = useRouter()
const arenaPlayersOnly = ref(false)

const overview = computed(() => palStore.OVERVIEW_DATA)
const totals = computed(() => overview.value?.totals || {})
const traits = computed(() => overview.value?.traits || {})
const condition = computed(() => overview.value?.condition || {})
const expeditions = computed(() => overview.value?.expeditions || {})
const anomalies = computed(() => overview.value?.anomalies || {})
const arenaPreviewEntries = computed(() => {
  const rankedEntries = palStore.ARENA_LEADERBOARD.filter(entry => entry.rank !== null)
  const entries = arenaPlayersOnly.value
    ? rankedEntries.filter(entry => entry.entry_type !== 'npc')
    : rankedEntries
  return entries.slice(0, 10)
})
const maxSpeciesCount = computed(() => Math.max(
  1,
  ...(overview.value?.top_species || []).map(item => Number(item.count) || 0),
))
const sourceName = computed(() => (
  palStore.SOURCE_DISPLAY_NAME
  || palStore.PAL_GAME_SAVE_PATH
  || palStore.getTranslatedText('Overview_SourceUnknown')
))

const reasonTranslationKeys = Object.freeze({
  EXPEDITION_ASSIGNMENT_INVALID: 'Overview_Reason_ExpeditionInvalid',
  EXPEDITION_ASSIGNMENT_UNKNOWN: 'Overview_Reason_ExpeditionUnknown',
  PAL_DETACHED: 'Overview_Reason_Detached',
  PAL_SICK: 'Overview_Reason_Sick',
  PAL_FAINTED: 'Overview_Reason_Fainted',
})

function navigate(name) {
  router.push({ name })
}

function arenaDisplayName(entry) {
  if (entry.entry_type === 'npc') {
    return getArenaNpcName(entry.name_text_id, palStore.I18n)
  }
  return entry.name || entry.player_id
}

function openArenaEntry(entry) {
  if (entry.entry_type === 'player' && entry.player_id) {
    router.push({ name: 'PlayerEditor', params: { playerId: entry.player_id } })
    return
  }
  navigate('ArenaLeaderboard')
}

function reasonText(code) {
  return palStore.getTranslatedText(
    reasonTranslationKeys[code] || 'Overview_Reason_Structural',
  )
}

function speciesWidth(count) {
  return `${Math.max(6, Math.round((Number(count) / maxSpeciesCount.value) * 100))}%`
}

function openAnomaly(row) {
  if (row.owner_id && row.pal_id) {
    router.push({
      name: 'PlayerPalEditor',
      params: {
        playerId: row.owner_id,
        palId: row.pal_id,
      },
    })
    return
  }
  if (row.reason_codes?.some(code => code.startsWith('EXPEDITION_'))) {
    navigate('Expeditions')
    return
  }
  navigate('Editor')
}

function refreshOverview() {
  return Promise.all([
    palStore.loadOverview(),
    palStore.loadArenaLeaderboard(),
  ])
}

onMounted(() => {
  refreshOverview()
})
</script>

<template>
  <section class="overview-page" aria-labelledby="overview-title">
    <div class="overview-shell">
      <header class="overview-header">
        <div class="overview-heading">
          <p class="overview-kicker">{{ palStore.getTranslatedText('Overview_Eyebrow') }}</p>
          <h1 id="overview-title">{{ palStore.getTranslatedText('Overview_Title') }}</h1>
          <p>{{ palStore.getTranslatedText('Overview_Description') }}</p>
        </div>
        <div class="overview-header__actions">
          <button
            class="overview-button overview-button--secondary"
            type="button"
            :disabled="palStore.OVERVIEW_LOADING || palStore.ARENA_LOADING"
            @click="refreshOverview"
          >
            <AppIcon name="refresh" :size="16" />
            {{ palStore.getTranslatedText('Overview_Refresh') }}
          </button>
          <button
            class="overview-button overview-button--secondary"
            type="button"
            :title="palStore.getTranslatedText('Overview_HealAllPals_Tooltip')"
            :disabled="
              palStore.LOADING_FLAG
              || !Number(totals.pals)
            "
            @click="palStore.healAllPalsInSave"
          >
            <AppIcon name="medical" :size="16" />
            {{ palStore.getTranslatedText('Overview_HealAllPals') }}
          </button>
          <button
            class="overview-button overview-button--primary"
            type="button"
            @click="navigate('Editor')"
          >
            {{ palStore.getTranslatedText('Overview_OpenEditor') }}
            <AppIcon name="forward" :size="16" />
          </button>
        </div>
      </header>

      <div class="overview-source" :title="sourceName">
        <span :class="['overview-source__platform', `is-${palStore.SAVE_PLATFORM}`]">
          {{ palStore.getTranslatedText(palStore.SAVE_PLATFORM === 'xgp' ? 'SourceBadge_Xgp' : 'SourceBadge_Steam') }}
        </span>
        <span class="overview-source__name">{{ sourceName }}</span>
        <span class="overview-source__revision">
          {{ palStore.getTranslatedText('Overview_Revision', [overview?.revision ?? palStore.SESSION_REVISION]) }}
        </span>
      </div>

      <div v-if="palStore.OVERVIEW_LOADING && !overview" class="overview-loading" aria-busy="true">
        <span v-for="index in 10" :key="index" />
      </div>

      <template v-else-if="overview">
        <section class="metric-rail" :aria-label="palStore.getTranslatedText('Overview_CoreStats')">
          <article class="metric-cell">
            <span class="metric-cell__icon"><AppIcon name="user" :size="18" /></span>
            <div>
              <strong>{{ totals.players || 0 }}</strong>
              <span>{{ palStore.getTranslatedText('Overview_Players') }}</span>
              <small>{{ palStore.getTranslatedText('Overview_PlayerHint') }}</small>
            </div>
          </article>
          <article class="metric-cell metric-cell--primary">
            <span class="metric-cell__icon"><AppIcon name="paw" :size="19" /></span>
            <div>
              <strong>{{ totals.pals || 0 }}</strong>
              <span>{{ palStore.getTranslatedText('Overview_Pals') }}</span>
              <small>{{ palStore.getTranslatedText('Overview_SpeciesCount', [totals.species || 0]) }}</small>
            </div>
          </article>
          <article class="metric-cell">
            <span class="metric-cell__icon"><AppIcon name="id" :size="18" /></span>
            <div>
              <strong>{{ totals.human_npcs || 0 }}</strong>
              <span>{{ palStore.getTranslatedText('Overview_HumanNpcs') }}</span>
              <small>{{ palStore.getTranslatedText('Overview_CreatureCount', [totals.creature_pals || 0]) }}</small>
            </div>
          </article>
          <article class="metric-cell">
            <span class="metric-cell__icon"><AppIcon name="building" :size="18" /></span>
            <div>
              <strong>{{ totals.bases || 0 }}</strong>
              <span>{{ palStore.getTranslatedText('Overview_Bases') }}</span>
              <small>{{ palStore.getTranslatedText('Overview_GuildCount', [totals.guilds || 0]) }}</small>
            </div>
          </article>
          <article :class="['metric-cell', 'metric-cell--attention', { 'is-clear': !anomalies.pal_count }]">
            <span class="metric-cell__icon">
              <AppIcon :name="anomalies.pal_count ? 'warning' : 'check'" :size="18" />
            </span>
            <div>
              <strong>{{ anomalies.pal_count || 0 }}</strong>
              <span>{{ palStore.getTranslatedText('Overview_AttentionPals') }}</span>
              <small>
                {{ palStore.getTranslatedText(
                  anomalies.pal_count ? 'Overview_AttentionHint' : 'Overview_HealthyHint',
                ) }}
              </small>
            </div>
          </article>
        </section>

        <section class="overview-primary-grid">
          <article class="overview-card quick-card">
            <header class="card-heading">
              <div>
                <p>{{ palStore.getTranslatedText('Overview_WorkspaceEyebrow') }}</p>
                <h2>{{ palStore.getTranslatedText('Overview_WorkspaceTitle') }}</h2>
              </div>
              <span>{{ palStore.getTranslatedText('Overview_WorkspaceHint') }}</span>
            </header>
            <div class="quick-grid">
              <button type="button" @click="navigate('Editor')">
                <span class="quick-grid__icon"><AppIcon name="id" :size="19" /></span>
                <span>
                  <strong>{{ palStore.getTranslatedText('TopBar_Page_Pals') }}</strong>
                  <small>{{ palStore.getTranslatedText('Overview_ActionEditor') }}</small>
                </span>
                <AppIcon name="forward" :size="15" />
              </button>
              <button type="button" @click="navigate('Map')">
                <span class="quick-grid__icon"><AppIcon name="map" :size="19" /></span>
                <span>
                  <strong>{{ palStore.getTranslatedText('TopBar_Page_Map') }}</strong>
                  <small>{{ palStore.getTranslatedText('Overview_ActionMap') }}</small>
                </span>
                <AppIcon name="forward" :size="15" />
              </button>
              <button type="button" @click="navigate('Expeditions')">
                <span class="quick-grid__icon"><AppIcon name="clock" :size="19" /></span>
                <span>
                  <strong>{{ palStore.getTranslatedText('TopBar_Page_Expeditions') }}</strong>
                  <small>{{ palStore.getTranslatedText('Overview_ActionExpeditions') }}</small>
                </span>
                <AppIcon name="forward" :size="15" />
              </button>
              <button type="button" @click="navigate('ArenaLeaderboard')">
                <span class="quick-grid__icon"><AppIcon name="crown" :size="19" /></span>
                <span>
                  <strong>{{ palStore.getTranslatedText('TopBar_Page_Arena') }}</strong>
                  <small>{{ palStore.getTranslatedText('Overview_ActionArena') }}</small>
                </span>
                <AppIcon name="forward" :size="15" />
              </button>
            </div>
          </article>

          <aside :class="['overview-card', 'health-card', { 'health-card--clear': !anomalies.pal_count }]">
            <header>
              <span><AppIcon :name="anomalies.pal_count ? 'activity' : 'check'" :size="20" /></span>
              <div>
                <p>{{ palStore.getTranslatedText('Overview_HealthEyebrow') }}</p>
                <h2>{{ palStore.getTranslatedText('Overview_HealthTitle') }}</h2>
              </div>
            </header>
            <strong class="health-card__value">{{ anomalies.pal_count || 0 }}</strong>
            <p class="health-card__summary">
              {{ palStore.getTranslatedText(
                anomalies.pal_count ? 'Overview_HealthNeedsReview' : 'Overview_HealthClear',
              ) }}
            </p>
            <dl>
              <div>
                <dt>{{ palStore.getTranslatedText('Overview_StructuralIssues') }}</dt>
                <dd>{{ anomalies.structural_issue_count || 0 }}</dd>
              </div>
              <div>
                <dt>{{ palStore.getTranslatedText('Overview_InvalidExpeditions') }}</dt>
                <dd>{{ expeditions.invalid_assignments || 0 }}</dd>
              </div>
              <div>
                <dt>{{ palStore.getTranslatedText('Overview_ConditionIssues') }}</dt>
                <dd>{{ (condition.sick_pals || 0) + (condition.fainted_pals || 0) }}</dd>
              </div>
            </dl>
            <small v-if="!anomalies.index_available" class="health-card__notice">
              {{ palStore.getTranslatedText('Overview_IndexUnavailable') }}
            </small>
          </aside>
        </section>

        <section class="status-grid">
          <article class="overview-card expedition-card">
            <header class="card-heading">
              <div>
                <p>{{ palStore.getTranslatedText('Overview_ExpeditionEyebrow') }}</p>
                <h2>{{ palStore.getTranslatedText('Overview_ExpeditionTitle') }}</h2>
              </div>
              <button type="button" @click="navigate('Expeditions')">
                {{ palStore.getTranslatedText('Overview_Manage') }}
                <AppIcon name="forward" :size="14" />
              </button>
            </header>
            <div class="expedition-stats">
              <div>
                <strong>{{ expeditions.active || 0 }}</strong>
                <span>{{ palStore.getTranslatedText('Overview_ExpeditionActive') }}</span>
              </div>
              <div>
                <strong>{{ expeditions.assigned_pals || 0 }}</strong>
                <span>{{ palStore.getTranslatedText('Overview_ExpeditionAssigned') }}</span>
              </div>
              <div>
                <strong>{{ expeditions.completable || 0 }}</strong>
                <span>{{ palStore.getTranslatedText('Overview_ExpeditionCompletable') }}</span>
              </div>
              <div :class="{ 'is-danger': expeditions.invalid_assignments }">
                <strong>{{ expeditions.invalid_assignments || 0 }}</strong>
                <span>{{ palStore.getTranslatedText('Overview_ExpeditionInvalid') }}</span>
              </div>
            </div>
            <p v-if="!expeditions.data_available" class="card-note">
              <AppIcon name="warning" :size="15" />
              {{ palStore.getTranslatedText('Overview_ExpeditionUnavailable') }}
            </p>
            <p v-else-if="expeditions.unknown_assignments" class="card-note">
              <AppIcon name="warning" :size="15" />
              {{ palStore.getTranslatedText('Overview_ExpeditionUnknownCount', [expeditions.unknown_assignments]) }}
            </p>
          </article>

          <article class="overview-card composition-card">
            <header class="card-heading">
              <div>
                <p>{{ palStore.getTranslatedText('Overview_CompositionEyebrow') }}</p>
                <h2>{{ palStore.getTranslatedText('Overview_CompositionTitle') }}</h2>
              </div>
            </header>
            <dl class="compact-stats">
              <div><dt>{{ palStore.getTranslatedText('Overview_BossPals') }}</dt><dd>{{ traits.boss_pals || 0 }}</dd></div>
              <div><dt>{{ palStore.getTranslatedText('Overview_RarePals') }}</dt><dd>{{ traits.rare_pals || 0 }}</dd></div>
              <div><dt>{{ palStore.getTranslatedText('Overview_AwakenedPals') }}</dt><dd>{{ traits.awakened_pals || 0 }}</dd></div>
              <div><dt>{{ palStore.getTranslatedText('Overview_BaseWorkers') }}</dt><dd>{{ totals.base_workers || 0 }}</dd></div>
              <div><dt>{{ palStore.getTranslatedText('Overview_SickPals') }}</dt><dd>{{ condition.sick_pals || 0 }}</dd></div>
              <div><dt>{{ palStore.getTranslatedText('Overview_FaintedPals') }}</dt><dd>{{ condition.fainted_pals || 0 }}</dd></div>
            </dl>
          </article>
        </section>

        <section class="overview-card arena-preview-card">
          <header class="card-heading arena-preview-heading">
            <div>
              <p>{{ palStore.getTranslatedText('Arena_WorldLocal') }}</p>
              <h2>{{ palStore.getTranslatedText('Arena_Title') }}</h2>
              <span class="arena-preview-heading__hint">
                {{ palStore.getTranslatedText('Overview_ArenaRankHint') }}
              </span>
            </div>
            <div class="arena-preview-actions">
              <div
                class="arena-preview-toggle"
                role="group"
                :aria-label="palStore.getTranslatedText('Arena_Title')"
              >
                <button
                  type="button"
                  :aria-pressed="!arenaPlayersOnly"
                  @click="arenaPlayersOnly = false"
                >
                  {{ palStore.getTranslatedText('Overview_ArenaAllTopTen') }}
                </button>
                <button
                  type="button"
                  :aria-pressed="arenaPlayersOnly"
                  @click="arenaPlayersOnly = true"
                >
                  {{ palStore.getTranslatedText('Overview_ArenaPlayersTopTen') }}
                </button>
              </div>
              <button
                class="arena-preview-link"
                type="button"
                @click="navigate('ArenaLeaderboard')"
              >
                {{ palStore.getTranslatedText('Overview_ArenaViewAll') }}
                <AppIcon name="forward" :size="14" />
              </button>
            </div>
          </header>

          <div
            v-if="palStore.ARENA_LOADING && !palStore.ARENA_LEADERBOARD.length"
            class="arena-preview-loading"
            aria-busy="true"
          >
            <span v-for="index in 10" :key="index" />
          </div>
          <div
            v-else-if="arenaPreviewEntries.length"
            :class="['arena-preview-list', { 'is-short': arenaPreviewEntries.length <= 5 }]"
          >
            <button
              v-for="entry in arenaPreviewEntries"
              :key="entry.entry_id"
              type="button"
              :class="['arena-preview-row', { 'is-npc': entry.entry_type === 'npc' }]"
              @click="openArenaEntry(entry)"
            >
              <span :class="['arena-preview-rank', `is-rank-${entry.rank}`]">
                {{ entry.rank }}
              </span>
              <span class="arena-preview-identity">
                <strong>{{ arenaDisplayName(entry) }}</strong>
                <small>
                  {{
                    entry.entry_type === 'npc'
                      ? entry.name_text_id
                      : (entry.guild_name || entry.player_id)
                  }}
                </small>
              </span>
              <span :class="['arena-preview-badge', { 'is-player': entry.entry_type === 'player' }]">
                {{
                  palStore.getTranslatedText(
                    entry.entry_type === 'npc' ? 'Arena_NPCBadge' : 'Overview_ArenaPlayerBadge',
                  )
                }}
              </span>
              <span class="arena-preview-rp">
                <strong>{{ Number(entry.rank_point || 0).toLocaleString() }}</strong>
                <small>{{ palStore.getTranslatedText('Arena_ColumnRankPoint') }}</small>
              </span>
              <AppIcon name="forward" :size="14" />
            </button>
          </div>
          <p v-else class="card-empty">{{ palStore.getTranslatedText('Arena_NoEntries') }}</p>
        </section>

        <section class="insight-grid">
          <article class="overview-card species-card">
            <header class="card-heading">
              <div>
                <p>{{ palStore.getTranslatedText('Overview_DistributionEyebrow') }}</p>
                <h2>{{ palStore.getTranslatedText('Overview_TopSpecies') }}</h2>
              </div>
              <span>{{ palStore.getTranslatedText('Overview_TotalSpecies', [totals.species || 0]) }}</span>
            </header>
            <div v-if="overview.top_species?.length" class="species-list">
              <div v-for="species in overview.top_species" :key="species.internal_id" class="species-row">
                <span class="species-row__portrait">
                  <AppIcon name="paw" :size="16" />
                  <img
                    v-if="species.icon_access_key"
                    :src="`/image/pals/${species.icon_access_key}`"
                    :alt="species.name"
                    @error="$event.currentTarget.hidden = true"
                  />
                </span>
                <span class="species-row__copy">
                  <strong>{{ species.name }}</strong>
                  <small>{{ species.internal_id }}</small>
                </span>
                <span class="species-row__bar"><i :style="{ width: speciesWidth(species.count) }" /></span>
                <b>{{ species.count }}</b>
              </div>
            </div>
            <p v-else class="card-empty">{{ palStore.getTranslatedText('Overview_NoSpecies') }}</p>
          </article>

          <article class="overview-card players-card">
            <header class="card-heading">
              <div>
                <p>{{ palStore.getTranslatedText('Overview_PlayersEyebrow') }}</p>
                <h2>{{ palStore.getTranslatedText('Overview_PlayerOverview') }}</h2>
              </div>
            </header>
            <div v-if="overview.players?.length" class="player-overview-list">
              <button
                v-for="player in overview.players"
                :key="player.player_id"
                type="button"
                @click="router.push({ name: 'PlayerEditor', params: { playerId: player.player_id } })"
              >
                <span class="player-overview-list__avatar">{{ (player.name || '?').slice(0, 1).toUpperCase() }}</span>
                <span>
                  <strong>{{ player.name || player.player_id }}</strong>
                  <small>{{ palStore.getTranslatedText('Common_LevelWithValue', [player.level]) }}</small>
                </span>
                <b>{{ palStore.getTranslatedText('Overview_PlayerPalCount', [player.pal_count]) }}</b>
              </button>
            </div>
            <p v-else class="card-empty">{{ palStore.getTranslatedText('Overview_NoPlayers') }}</p>
          </article>
        </section>

        <section class="overview-card anomaly-card">
          <header class="card-heading">
            <div>
              <p>{{ palStore.getTranslatedText('Overview_AnomalyEyebrow') }}</p>
              <h2>{{ palStore.getTranslatedText('Overview_AnomalyTitle') }}</h2>
            </div>
            <span>
              {{ palStore.getTranslatedText('Overview_IssueCount', [anomalies.issue_count || 0]) }}
            </span>
          </header>
          <div v-if="anomalies.preview?.length" class="anomaly-list">
            <button
              v-for="row in anomalies.preview"
              :key="row.pal_id"
              type="button"
              @click="openAnomaly(row)"
            >
              <span :class="['anomaly-list__state', `is-${row.severity}`]">
                <AppIcon name="warning" :size="16" />
              </span>
              <span class="anomaly-list__portrait">
                <AppIcon name="paw" :size="16" />
                <img
                  v-if="row.icon_access_key"
                  :src="`/image/pals/${row.icon_access_key}`"
                  :alt="row.name"
                  @error="$event.currentTarget.hidden = true"
                />
              </span>
              <span class="anomaly-list__identity">
                <strong>{{ row.name }}</strong>
                <small>
                  {{ row.owner_name || palStore.getTranslatedText(`Overview_Scope_${row.scope}`) }}
                  <template v-if="row.level">
                    · {{ palStore.getTranslatedText('Common_LevelWithValue', [row.level]) }}
                  </template>
                </small>
              </span>
              <span class="anomaly-list__reasons">
                <span v-for="code in row.reason_codes.slice(0, 2)" :key="code">
                  {{ reasonText(code) }}
                  <small>{{ code }}</small>
                </span>
              </span>
              <AppIcon name="forward" :size="15" />
            </button>
          </div>
          <div v-else class="anomaly-empty">
            <span><AppIcon name="check" :size="22" /></span>
            <div>
              <strong>{{ palStore.getTranslatedText('Overview_NoAnomalies') }}</strong>
              <p>{{ palStore.getTranslatedText('Overview_NoAnomaliesHint') }}</p>
            </div>
          </div>
        </section>
      </template>

      <section v-else class="overview-error" role="status">
        <span><AppIcon name="warning" :size="22" /></span>
        <div>
          <strong>{{ palStore.getTranslatedText('Overview_LoadFailed') }}</strong>
          <p>{{ palStore.getTranslatedText('Overview_LoadFailedHint') }}</p>
        </div>
        <button type="button" @click="refreshOverview">
          {{ palStore.getTranslatedText('Overview_Retry') }}
        </button>
      </section>
    </div>
  </section>
</template>

<style scoped>
.overview-page {
  min-height: 100dvh;
  padding: calc(var(--editor-top-offset) + 24px) clamp(14px, 2.2vw, 34px) 48px;
  color: var(--ui-text);
  background:
    radial-gradient(circle at 78% 8%, oklch(0.28 0.045 246 / 0.2), transparent 30rem),
    var(--ui-canvas);
}

.overview-shell {
  width: min(1540px, 100%);
  margin-inline: auto;
}

.overview-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 28px;
  margin-bottom: 18px;
}

.overview-heading { min-width: 0; }
.overview-kicker,
.card-heading p,
.health-card header p {
  margin: 0 0 5px;
  color: var(--ui-accent);
  font-size: 10px;
  font-weight: 750;
  letter-spacing: 0.08em;
}

.overview-heading h1 {
  margin: 0;
  font-size: clamp(28px, 3vw, 42px);
  line-height: 1.08;
  font-weight: 760;
  letter-spacing: -0.045em;
  text-wrap: balance;
}

.overview-heading > p:last-child {
  max-width: 68ch;
  margin: 10px 0 0;
  color: var(--ui-text-muted);
  font-size: 13px;
  line-height: 1.65;
  text-wrap: pretty;
}

.overview-header__actions {
  display: flex;
  flex: 0 0 auto;
  gap: 8px;
}

.overview-button,
.card-heading button {
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

.overview-button:hover:not(:disabled),
.card-heading button:hover:not(:disabled) {
  color: var(--ui-text);
  background: var(--ui-surface-hover);
  border-color: var(--ui-border-strong);
}

.overview-button--primary {
  color: oklch(0.16 0.025 252);
  background: var(--ui-accent);
  border-color: var(--ui-accent);
}

.overview-button--primary:hover:not(:disabled) {
  color: oklch(0.12 0.02 252);
  background: oklch(0.78 0.12 246);
  border-color: oklch(0.78 0.12 246);
}

.overview-button:disabled { opacity: 0.45; }

.overview-source {
  display: flex;
  min-width: 0;
  min-height: 34px;
  align-items: center;
  gap: 9px;
  margin-bottom: 14px;
  padding: 6px 9px;
  color: var(--ui-text-muted);
  background: oklch(0.19 0.017 252 / 0.76);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
  font-size: 11px;
}

.overview-source__platform {
  flex: 0 0 auto;
  padding: 2px 6px;
  color: var(--ui-text-secondary);
  background: var(--ui-surface-raised);
  border-radius: 4px;
  font-size: 9px;
  font-weight: 750;
}

.overview-source__platform.is-xgp { color: var(--ui-accent); }
.overview-source__name {
  min-width: 0;
  flex: 1 1 auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.overview-source__revision { flex: 0 0 auto; font-variant-numeric: tabular-nums; }

.metric-rail {
  display: grid;
  grid-template-columns: 1.05fr 1.22fr 1.08fr 1fr 1.15fr;
  margin-bottom: 14px;
  overflow: hidden;
  background: var(--ui-surface);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-lg);
  box-shadow: var(--ui-shadow-sm);
}

.metric-cell {
  display: flex;
  min-width: 0;
  min-height: 112px;
  align-items: center;
  gap: 14px;
  padding: 18px;
}

.metric-cell + .metric-cell { border-left: 1px solid var(--ui-border); }

.metric-cell__icon,
.quick-grid__icon {
  display: inline-grid;
  flex: 0 0 auto;
  place-items: center;
  color: var(--ui-text-secondary);
  background: var(--ui-surface-raised);
  border: 1px solid var(--ui-border);
}

.metric-cell__icon {
  width: 40px;
  height: 40px;
  border-radius: var(--ui-radius-sm);
}

.metric-cell--primary .metric-cell__icon {
  color: var(--ui-accent);
  background: var(--ui-accent-soft);
  border-color: oklch(0.5 0.08 246);
}

.metric-cell--attention {
  background: linear-gradient(110deg, var(--ui-danger-soft), transparent 78%);
}

.metric-cell--attention .metric-cell__icon {
  color: var(--ui-danger);
  background: var(--ui-danger-soft);
  border-color: oklch(0.45 0.08 24);
}

.metric-cell--attention.is-clear { background: transparent; }
.metric-cell--attention.is-clear .metric-cell__icon {
  color: var(--ui-success);
  background: oklch(0.25 0.05 158);
  border-color: oklch(0.42 0.07 158);
}

.metric-cell > div { min-width: 0; display: grid; }
.metric-cell strong,
.health-card__value {
  font-size: 30px;
  line-height: 1;
  font-weight: 740;
  letter-spacing: -0.045em;
  font-variant-numeric: tabular-nums;
}
.metric-cell span:not(.metric-cell__icon) { margin-top: 6px; color: var(--ui-text-secondary); font-size: 12px; font-weight: 650; }
.metric-cell small { margin-top: 2px; overflow: hidden; color: var(--ui-text-muted); font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }

.overview-primary-grid,
.status-grid,
.insight-grid {
  display: grid;
  gap: 14px;
  margin-bottom: 14px;
}

.overview-primary-grid { grid-template-columns: minmax(0, 1.7fr) minmax(300px, 0.72fr); }
.status-grid { grid-template-columns: minmax(0, 1.5fr) minmax(340px, 0.8fr); }
.insight-grid { grid-template-columns: minmax(0, 1.32fr) minmax(360px, 0.9fr); }

.overview-card {
  min-width: 0;
  padding: 18px;
  background: var(--ui-surface);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-md);
  box-shadow: var(--ui-shadow-sm);
}

.card-heading {
  display: flex;
  min-width: 0;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 15px;
}

.card-heading > div { min-width: 0; }
.card-heading h2,
.health-card h2 {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  letter-spacing: -0.015em;
}
.card-heading > span {
  max-width: 40ch;
  color: var(--ui-text-muted);
  font-size: 10px;
  text-align: right;
}
.card-heading button {
  min-height: 30px;
  padding-inline: 9px;
  background: transparent;
  border-color: transparent;
  color: var(--ui-accent);
  font-size: 10px;
}

.quick-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.quick-grid button {
  display: grid;
  min-width: 0;
  min-height: 76px;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  padding: 12px;
  color: var(--ui-text-secondary);
  background: var(--ui-surface-raised);
  border: 1px solid transparent;
  border-radius: var(--ui-radius-sm);
  text-align: left;
}

.quick-grid button:hover {
  color: var(--ui-text);
  background: var(--ui-surface-hover);
  border-color: var(--ui-border-strong);
  transform: translateY(-1px);
}

.quick-grid__icon {
  width: 38px;
  height: 38px;
  color: var(--ui-accent);
  background: var(--ui-accent-soft);
  border-color: transparent;
  border-radius: 9px;
}

.quick-grid button > span:nth-child(2) { min-width: 0; display: grid; gap: 3px; }
.quick-grid strong { color: var(--ui-text); font-size: 12px; }
.quick-grid small { overflow: hidden; color: var(--ui-text-muted); font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }

.health-card {
  position: relative;
  overflow: hidden;
  background: linear-gradient(145deg, oklch(0.25 0.05 24), var(--ui-surface) 72%);
  border-color: oklch(0.42 0.07 24);
}

.health-card::after {
  position: absolute;
  right: -34px;
  bottom: -42px;
  width: 130px;
  height: 130px;
  border: 22px solid oklch(0.62 0.12 24 / 0.08);
  border-radius: 50%;
  content: "";
  pointer-events: none;
}

.health-card--clear {
  background: linear-gradient(145deg, oklch(0.24 0.04 158), var(--ui-surface) 72%);
  border-color: oklch(0.4 0.06 158);
}

.health-card header { display: flex; align-items: center; gap: 10px; }
.health-card header > span {
  display: inline-grid;
  width: 38px;
  height: 38px;
  place-items: center;
  color: var(--ui-danger);
  background: var(--ui-danger-soft);
  border: 1px solid oklch(0.45 0.08 24);
  border-radius: 9px;
}
.health-card--clear header > span { color: var(--ui-success); background: oklch(0.25 0.05 158); border-color: oklch(0.42 0.07 158); }
.health-card__value { display: block; margin-top: 24px; font-size: 42px; }
.health-card__summary { max-width: 34ch; min-height: 3em; margin: 7px 0 18px; color: var(--ui-text-secondary); font-size: 11px; }
.health-card dl { display: grid; gap: 6px; margin: 0; }
.health-card dl div { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding-top: 7px; border-top: 1px solid oklch(0.65 0.04 252 / 0.13); }
.health-card dt { color: var(--ui-text-muted); font-size: 10px; }
.health-card dd { margin: 0; color: var(--ui-text-secondary); font-size: 11px; font-weight: 700; }
.health-card__notice { display: block; margin-top: 12px; color: oklch(0.82 0.1 80); font-size: 9px; }

.expedition-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  overflow: hidden;
  background: var(--ui-surface-raised);
  border-radius: var(--ui-radius-sm);
}

.expedition-stats > div { display: grid; min-height: 80px; align-content: center; gap: 5px; padding: 12px 14px; }
.expedition-stats > div + div { border-left: 1px solid var(--ui-border); }
.expedition-stats strong { font-size: 23px; line-height: 1; letter-spacing: -0.035em; }
.expedition-stats span { color: var(--ui-text-muted); font-size: 10px; }
.expedition-stats .is-danger strong { color: var(--ui-danger); }
.card-note { display: flex; align-items: center; gap: 7px; margin: 12px 0 0; color: oklch(0.82 0.1 80); font-size: 10px; }

.compact-stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1px;
  margin: 0;
  overflow: hidden;
  background: var(--ui-border);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
}

.compact-stats > div { display: grid; min-height: 70px; align-content: center; gap: 4px; padding: 10px; background: var(--ui-surface-raised); }
.compact-stats dt { color: var(--ui-text-muted); font-size: 9px; }
.compact-stats dd { margin: 0; font-size: 18px; font-weight: 700; }

.arena-preview-card { margin-bottom: 14px; }
.arena-preview-heading { align-items: center; }
.arena-preview-heading__hint {
  display: block;
  margin-top: 4px;
  color: var(--ui-text-muted);
  font-size: 9px;
}

.arena-preview-actions,
.arena-preview-toggle {
  display: flex;
  align-items: center;
}

.arena-preview-actions { gap: 8px; }
.arena-preview-toggle {
  padding: 3px;
  background: var(--ui-canvas);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
}

.arena-preview-toggle button,
.arena-preview-link {
  min-height: 30px;
  padding: 0 10px;
  border: 0;
  border-radius: 6px;
  font: inherit;
  font-size: 10px;
  font-weight: 650;
}

.arena-preview-toggle button {
  color: var(--ui-text-muted);
  background: transparent;
}

.arena-preview-toggle button[aria-pressed="true"] {
  color: var(--ui-text);
  background: var(--ui-surface-raised);
  box-shadow: 0 0 0 1px var(--ui-border);
}

.arena-preview-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--ui-accent);
  background: transparent;
}

.arena-preview-toggle button:hover,
.arena-preview-link:hover { color: var(--ui-text); }

.arena-preview-list,
.arena-preview-loading {
  display: grid;
  grid-template-rows: repeat(5, minmax(0, auto));
  grid-template-columns: repeat(2, minmax(0, 1fr));
  grid-auto-flow: column;
  gap: 6px;
}

.arena-preview-list.is-short {
  grid-template-rows: none;
  grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
  grid-auto-flow: row;
}

.arena-preview-row {
  display: grid;
  min-width: 0;
  min-height: 58px;
  grid-template-columns: auto minmax(0, 1fr) auto auto auto;
  align-items: center;
  gap: 10px;
  padding: 7px 9px;
  color: var(--ui-text-secondary);
  background: var(--ui-surface-raised);
  border: 1px solid transparent;
  border-radius: var(--ui-radius-sm);
  text-align: left;
}

.arena-preview-row:hover {
  color: var(--ui-text);
  background: var(--ui-surface-hover);
  border-color: var(--ui-border-strong);
}

.arena-preview-row.is-npc {
  background: color-mix(in oklch, var(--ui-accent) 4%, var(--ui-surface-raised));
}

.arena-preview-rank {
  display: inline-grid;
  width: 30px;
  height: 30px;
  place-items: center;
  color: var(--ui-text-muted);
  background: var(--ui-canvas);
  border: 1px solid var(--ui-border);
  border-radius: 8px;
  font-size: 11px;
  font-weight: 750;
  font-variant-numeric: tabular-nums;
}

.arena-preview-rank.is-rank-1 { color: oklch(0.86 0.13 88); background: oklch(0.27 0.045 88); border-color: oklch(0.5 0.08 88); }
.arena-preview-rank.is-rank-2 { color: oklch(0.82 0.025 250); background: oklch(0.27 0.018 250); border-color: oklch(0.48 0.025 250); }
.arena-preview-rank.is-rank-3 { color: oklch(0.76 0.09 55); background: oklch(0.26 0.04 55); border-color: oklch(0.47 0.07 55); }

.arena-preview-identity {
  display: grid;
  min-width: 0;
  gap: 2px;
}

.arena-preview-identity strong,
.arena-preview-identity small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.arena-preview-identity strong { color: var(--ui-text); font-size: 10px; }
.arena-preview-identity small { color: var(--ui-text-muted); font-size: 8px; }
.arena-preview-badge {
  padding: 3px 6px;
  color: var(--ui-accent);
  background: var(--ui-accent-soft);
  border-radius: 999px;
  font-size: 8px;
  font-weight: 750;
}
.arena-preview-badge.is-player { color: var(--ui-text-secondary); background: var(--ui-canvas); }
.arena-preview-rp { display: flex; align-items: baseline; justify-content: flex-end; gap: 3px; font-variant-numeric: tabular-nums; }
.arena-preview-rp strong { color: var(--ui-text); font-size: 12px; }
.arena-preview-rp small { color: var(--ui-text-muted); font-size: 8px; }

.arena-preview-loading span {
  min-height: 58px;
  background: linear-gradient(100deg, var(--ui-surface-raised) 25%, var(--ui-surface-hover) 45%, var(--ui-surface-raised) 65%);
  background-size: 220% 100%;
  border-radius: var(--ui-radius-sm);
  animation: overview-shimmer 1.4s ease-in-out infinite;
}

.species-list,
.player-overview-list,
.anomaly-list { display: grid; gap: 6px; }

.species-row {
  display: grid;
  min-width: 0;
  min-height: 48px;
  grid-template-columns: auto minmax(130px, 0.8fr) minmax(100px, 1fr) 34px;
  align-items: center;
  gap: 10px;
  padding: 6px 8px;
  background: var(--ui-surface-raised);
  border-radius: var(--ui-radius-sm);
}

.species-row__portrait,
.anomaly-list__portrait {
  position: relative;
  display: inline-grid;
  overflow: hidden;
  place-items: center;
  color: var(--ui-text-muted);
  background: var(--ui-canvas);
  border: 1px solid var(--ui-border);
  border-radius: 8px;
}
.species-row__portrait { width: 34px; height: 34px; }
.species-row__portrait img,
.anomaly-list__portrait img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
.species-row__copy { min-width: 0; display: grid; }
.species-row__copy strong { overflow: hidden; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.species-row__copy small { overflow: hidden; color: var(--ui-text-muted); font-size: 8px; text-overflow: ellipsis; white-space: nowrap; }
.species-row__bar { display: block; height: 5px; overflow: hidden; background: var(--ui-canvas); border-radius: 999px; }
.species-row__bar i { display: block; height: 100%; background: var(--ui-accent); border-radius: inherit; }
.species-row b { color: var(--ui-text-secondary); font-size: 11px; text-align: right; }

.player-overview-list { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.player-overview-list button {
  display: grid;
  min-width: 0;
  min-height: 54px;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 9px;
  padding: 7px 8px;
  color: var(--ui-text-secondary);
  background: var(--ui-surface-raised);
  border: 1px solid transparent;
  border-radius: var(--ui-radius-sm);
  text-align: left;
}
.player-overview-list button:hover { color: var(--ui-text); background: var(--ui-surface-hover); border-color: var(--ui-border-strong); }
.player-overview-list__avatar { display: inline-grid; width: 32px; height: 32px; place-items: center; color: var(--ui-accent); background: var(--ui-accent-soft); border-radius: 8px; font-size: 11px; font-weight: 750; }
.player-overview-list button > span:nth-child(2) { min-width: 0; display: grid; }
.player-overview-list strong { overflow: hidden; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.player-overview-list small { color: var(--ui-text-muted); font-size: 8px; }
.player-overview-list b { color: var(--ui-text-muted); font-size: 9px; font-weight: 600; }

.anomaly-card { margin-bottom: 14px; }
.anomaly-list button {
  display: grid;
  min-width: 0;
  min-height: 58px;
  grid-template-columns: auto auto minmax(160px, 0.8fr) minmax(220px, 1.3fr) auto;
  align-items: center;
  gap: 10px;
  padding: 8px;
  color: var(--ui-text-secondary);
  background: var(--ui-surface-raised);
  border: 1px solid transparent;
  border-radius: var(--ui-radius-sm);
  text-align: left;
}
.anomaly-list button:hover { color: var(--ui-text); background: var(--ui-surface-hover); border-color: var(--ui-border-strong); }
.anomaly-list__state { display: inline-grid; width: 28px; height: 28px; place-items: center; color: oklch(0.82 0.12 80); background: oklch(0.27 0.05 80); border-radius: 7px; }
.anomaly-list__state.is-danger { color: var(--ui-danger); background: var(--ui-danger-soft); }
.anomaly-list__portrait { width: 38px; height: 38px; }
.anomaly-list__identity { min-width: 0; display: grid; }
.anomaly-list__identity strong { overflow: hidden; color: var(--ui-text); font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.anomaly-list__identity small { overflow: hidden; color: var(--ui-text-muted); font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.anomaly-list__reasons { display: flex; min-width: 0; flex-wrap: wrap; gap: 6px; }
.anomaly-list__reasons > span { display: grid; padding: 4px 7px; color: var(--ui-text-secondary); background: var(--ui-canvas); border: 1px solid var(--ui-border); border-radius: 5px; font-size: 9px; }
.anomaly-list__reasons small { color: var(--ui-text-muted); font-size: 7px; }

.anomaly-empty,
.overview-error {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 18px;
  color: var(--ui-text-secondary);
  background: var(--ui-surface-raised);
  border-radius: var(--ui-radius-sm);
}
.anomaly-empty > span,
.overview-error > span { display: inline-grid; width: 40px; height: 40px; flex: 0 0 auto; place-items: center; color: var(--ui-success); background: oklch(0.25 0.05 158); border-radius: 9px; }
.anomaly-empty strong,
.overview-error strong { font-size: 12px; }
.anomaly-empty p,
.overview-error p { margin: 2px 0 0; color: var(--ui-text-muted); font-size: 10px; }
.overview-error { margin-top: 20px; border: 1px solid var(--ui-border); }
.overview-error > span { color: var(--ui-danger); background: var(--ui-danger-soft); }
.overview-error > div { flex: 1 1 auto; }
.overview-error button { min-height: 34px; padding: 0 12px; color: var(--ui-text); background: var(--ui-surface); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-sm); }
.card-empty { min-height: 90px; margin: 0; display: grid; place-items: center; color: var(--ui-text-muted); background: var(--ui-surface-raised); border-radius: var(--ui-radius-sm); font-size: 10px; }

.overview-loading {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
}
.overview-loading span {
  min-height: 112px;
  background: linear-gradient(100deg, var(--ui-surface) 25%, var(--ui-surface-raised) 45%, var(--ui-surface) 65%);
  background-size: 220% 100%;
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-md);
  animation: overview-shimmer 1.4s ease-in-out infinite;
}
.overview-loading span:nth-child(n + 6) { min-height: 190px; grid-column: span 2; }
.overview-loading span:last-child { grid-column: span 2; }

@keyframes overview-shimmer {
  to { background-position: -220% 0; }
}

@media (max-width: 1180px) {
  .metric-rail { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .metric-cell + .metric-cell { border-left: 0; }
  .metric-cell:nth-child(2),
  .metric-cell:nth-child(3),
  .metric-cell:nth-child(5) { border-left: 1px solid var(--ui-border); }
  .metric-cell:nth-child(n + 4) { border-top: 1px solid var(--ui-border); }
  .overview-primary-grid,
  .status-grid,
  .insight-grid { grid-template-columns: minmax(0, 1fr); }
  .health-card { min-height: 280px; }
}

@media (max-width: 760px) {
  .overview-page { padding: calc(var(--editor-top-offset) + 16px) 10px 32px; }
  .overview-header { align-items: stretch; flex-direction: column; gap: 16px; }
  .overview-header__actions { width: 100%; flex-wrap: wrap; }
  .overview-button { flex: 1 1 140px; }
  .metric-rail { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .metric-cell { min-height: 96px; padding: 14px; }
  .metric-cell:nth-child(n) { border-top: 0; border-left: 0; }
  .metric-cell:nth-child(even) { border-left: 1px solid var(--ui-border); }
  .metric-cell:nth-child(n + 3) { border-top: 1px solid var(--ui-border); }
  .metric-cell:last-child { grid-column: 1 / -1; border-left: 0; }
  .quick-grid { grid-template-columns: minmax(0, 1fr); }
  .expedition-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .expedition-stats > div:nth-child(3) { border-left: 0; }
  .expedition-stats > div:nth-child(n + 3) { border-top: 1px solid var(--ui-border); }
  .compact-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .arena-preview-heading { align-items: flex-start; flex-direction: column; }
  .arena-preview-actions { width: 100%; justify-content: space-between; }
  .arena-preview-list,
  .arena-preview-loading {
    grid-template-rows: none;
    grid-template-columns: minmax(0, 1fr);
    grid-auto-flow: row;
  }
  .player-overview-list { grid-template-columns: minmax(0, 1fr); }
  .anomaly-list button { grid-template-columns: auto auto minmax(0, 1fr) auto; }
  .anomaly-list__reasons { grid-column: 3 / -1; padding-left: 0; }
  .anomaly-list button > .app-icon:last-child { grid-column: 4; grid-row: 1; }
  .overview-loading { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .overview-loading span:nth-child(n) { grid-column: auto; }
}

@media (max-width: 480px) {
  .overview-heading h1 { font-size: 27px; }
  .overview-source__revision { display: none; }
  .metric-rail { grid-template-columns: minmax(0, 1fr); }
  .metric-cell:nth-child(n) { border-left: 0; border-top: 1px solid var(--ui-border); }
  .metric-cell:first-child { border-top: 0; }
  .metric-cell:last-child { grid-column: auto; }
  .species-row { grid-template-columns: auto minmax(0, 1fr) 28px; }
  .species-row__bar { display: none; }
  .card-heading { align-items: flex-start; flex-direction: column; gap: 7px; }
  .card-heading > span { text-align: left; }
  .arena-preview-actions { align-items: stretch; flex-direction: column; }
  .arena-preview-toggle { width: 100%; }
  .arena-preview-toggle button { flex: 1 1 0; }
  .arena-preview-link { align-self: flex-start; padding-inline: 3px; }
  .arena-preview-row { grid-template-columns: auto minmax(0, 1fr) auto auto; }
  .arena-preview-badge { display: none; }
  .arena-preview-row > .app-icon:last-child { display: none; }
  .overview-loading { grid-template-columns: minmax(0, 1fr); }
}

@media (prefers-reduced-motion: reduce) {
  .overview-loading span,
  .arena-preview-loading span { animation: none; }
  .quick-grid button:hover { transform: none; }
}
</style>
