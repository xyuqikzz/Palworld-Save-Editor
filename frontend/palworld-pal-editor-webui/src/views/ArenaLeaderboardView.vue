<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { getArenaNpcName } from '@/data/arenaNpcNames'
import { usePalEditorStore } from '@/stores/paleditor'

const palStore = usePalEditorStore()
const router = useRouter()
const drafts = reactive({})
const search = ref('')
const playersOnly = ref(false)

function isNpc(entry) {
  return entry.entry_type === 'npc'
}

function displayName(entry) {
  if (isNpc(entry)) return getArenaNpcName(entry.name_text_id, palStore.I18n)
  return entry.name || entry.player_id
}

function entryKey(entry) {
  return entry.entry_id || `${entry.entry_type}:${entry.player_id || entry.ranking_npc_id}`
}

const filteredEntries = computed(() => {
  const entries = playersOnly.value
    ? palStore.ARENA_LEADERBOARD.filter(entry => !isNpc(entry))
    : palStore.ARENA_LEADERBOARD
  const query = search.value.trim().toLocaleLowerCase()
  if (!query) return entries
  return entries.filter(entry => [
    displayName(entry),
    entry.guild_name,
    entry.player_id,
    entry.ranking_npc_id,
    entry.name_text_id,
  ].some(value => String(value || '').toLocaleLowerCase().includes(query)))
})

watch(
  () => palStore.ARENA_LEADERBOARD,
  entries => {
    const players = entries.filter(entry => !isNpc(entry))
    const currentIds = new Set(players.map(entry => entry.player_id))
    for (const playerId of Object.keys(drafts)) {
      if (!currentIds.has(playerId)) delete drafts[playerId]
    }
    for (const entry of players) {
      drafts[entry.player_id] = entry.rank_point ?? 0
    }
  },
  { deep: true, immediate: true },
)

function isValidRankPoint(value) {
  return Number.isInteger(value) && value >= 0 && value <= 2147483647
}

function capabilityText(code) {
  return palStore.getTranslatedText(
    code === 'ARENA_RANK_POINT_MISSING'
      ? 'Arena_FieldMissing'
      : 'Arena_FieldUnsupported',
  )
}

async function saveRankPoint(entry) {
  const value = drafts[entry.player_id]
  if (!isValidRankPoint(value)) return
  await palStore.setArenaRankPoint(entry.player_id, value)
}

async function resetPlayer(entry) {
  if (!window.confirm(
    palStore.getTranslatedText('Arena_ConfirmResetPlayer', [displayName(entry)]),
  )) return
  await palStore.resetArenaPlayer(entry.player_id)
}

async function resetAll() {
  if (!window.confirm(palStore.getTranslatedText('Arena_ConfirmResetAll'))) return
  await palStore.resetArenaLeaderboard()
}

onMounted(() => palStore.loadArenaLeaderboard())
</script>

<template>
  <div class="arena-page">
    <section class="arena-shell">
      <header class="arena-header">
        <div>
          <p class="arena-eyebrow">{{ palStore.getTranslatedText('Arena_WorldLocal') }}</p>
          <h1>{{ palStore.getTranslatedText('Arena_Title') }}</h1>
          <p class="arena-description">{{ palStore.getTranslatedText('Arena_Description') }}</p>
        </div>
        <div class="arena-header__actions">
          <button class="arena-button" type="button" @click="router.push({ name: 'Editor' })">
            {{ palStore.getTranslatedText('Arena_BackToEditor') }}
          </button>
          <button
            class="arena-button arena-button--danger"
            type="button"
            :disabled="palStore.ARENA_LOADING || !palStore.ARENA_RANKED_PLAYER_COUNT"
            @click="resetAll"
          >
            {{ palStore.getTranslatedText('Arena_ResetAll') }}
          </button>
        </div>
      </header>

      <div class="arena-controls">
        <label class="arena-player-toggle">
          <input v-model="playersOnly" type="checkbox" />
          <span>{{ palStore.getTranslatedText('Arena_PlayersOnly') }}</span>
        </label>
        <label class="arena-search">
          <span>{{ palStore.getTranslatedText('Arena_Search') }}</span>
          <input
            v-model="search"
            type="search"
            :placeholder="palStore.getTranslatedText('Arena_SearchPlaceholder')"
          />
        </label>
      </div>

      <div class="arena-table-wrap" :aria-busy="palStore.ARENA_LOADING">
        <table class="arena-table">
          <thead>
            <tr>
              <th>{{ palStore.getTranslatedText('Arena_ColumnRank') }}</th>
              <th>{{ palStore.getTranslatedText('Arena_ColumnPlayer') }}</th>
              <th>{{ palStore.getTranslatedText('Arena_ColumnGuild') }}</th>
              <th>{{ palStore.getTranslatedText('Arena_ColumnRankPoint') }}</th>
              <th>{{ palStore.getTranslatedText('Arena_ColumnActions') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="entry in filteredEntries"
              :key="entryKey(entry)"
              :class="{
                npc: isNpc(entry),
                unranked: entry.rank === null,
                unsupported: !isNpc(entry) && !entry.writable,
              }"
            >
              <td class="arena-rank">{{ entry.rank ?? '—' }}</td>
              <td>
                <strong>{{ displayName(entry) }}</strong>
                <code v-if="isNpc(entry)">{{ entry.name_text_id }}</code>
                <code v-else>{{ entry.player_id }}</code>
              </td>
              <td>
                <span v-if="isNpc(entry)" class="arena-npc-badge">
                  {{ palStore.getTranslatedText('Arena_NPCBadge') }}
                </span>
                <template v-else>{{ entry.guild_name || '—' }}</template>
              </td>
              <td>
                <input
                  v-if="!isNpc(entry) && entry.writable"
                  v-model.number="drafts[entry.player_id]"
                  class="arena-rp-input"
                  type="number"
                  min="0"
                  max="2147483647"
                  step="1"
                  :disabled="palStore.ARENA_LOADING"
                  :aria-label="palStore.getTranslatedText('Arena_RankPointFor', [displayName(entry)])"
                  @keyup.enter="saveRankPoint(entry)"
                />
                <small v-if="entry.field_state === 'missing'" class="arena-field-note">
                  {{ palStore.getTranslatedText('Arena_FieldWillInitialize') }}
                </small>
                <span v-if="isNpc(entry)" class="arena-static-rp">{{ entry.rank_point }}</span>
                <span
                  v-else-if="!entry.writable"
                  class="arena-capability"
                >{{ capabilityText(entry.capability_error) }}</span>
              </td>
              <td>
                <span v-if="isNpc(entry)">—</span>
                <div v-else-if="entry.writable" class="arena-row-actions">
                  <button
                    class="arena-button arena-button--primary"
                    type="button"
                    :disabled="palStore.ARENA_LOADING || !isValidRankPoint(drafts[entry.player_id]) || (entry.field_state === 'present' && drafts[entry.player_id] === entry.rank_point)"
                    @click="saveRankPoint(entry)"
                  >
                    {{ palStore.getTranslatedText(entry.field_state === 'missing' ? 'Arena_InitializeField' : 'Common_Save') }}
                  </button>
                  <button
                    v-if="entry.field_state === 'present'"
                    class="arena-button"
                    type="button"
                    :disabled="palStore.ARENA_LOADING || entry.rank_point === 0"
                    @click="resetPlayer(entry)"
                  >
                    {{ palStore.getTranslatedText('Arena_ResetPlayer') }}
                  </button>
                </div>
                <span v-else>—</span>
              </td>
            </tr>
            <tr v-if="!filteredEntries.length">
              <td class="arena-empty" colspan="5">{{ palStore.getTranslatedText('Arena_NoEntries') }}</td>
            </tr>
          </tbody>
        </table>
        <div v-if="palStore.ARENA_LOADING" class="arena-loading">
          {{ palStore.getTranslatedText('Arena_Loading') }}
        </div>
      </div>

      <footer class="arena-footer">
        <p>{{ palStore.getTranslatedText('Arena_SaveHint') }}</p>
        <p>{{ palStore.getTranslatedText('Arena_MissingFieldHint') }}</p>
      </footer>
    </section>
  </div>
</template>

<style scoped>
.arena-page {
  min-height: 100dvh;
  padding: var(--editor-top-offset) 12px 24px;
  background: var(--ui-canvas);
  color: var(--ui-text);
}

.arena-shell {
  width: min(1240px, 100%);
  margin: 0 auto;
  overflow: hidden;
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-md);
  background: var(--ui-surface);
  box-shadow: var(--ui-shadow-md);
}

.arena-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  padding: 24px;
  border-bottom: 1px solid var(--ui-border);
  background: var(--ui-surface-raised);
}

.arena-eyebrow,
.arena-description,
.arena-footer p { margin: 0; color: var(--ui-text-muted); }
.arena-eyebrow { font-size: 11px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; }
.arena-header h1 { margin: 5px 0 8px; font-size: clamp(24px, 3vw, 36px); letter-spacing: -0.035em; }
.arena-description { max-width: 700px; line-height: 1.6; }
.arena-header__actions,
.arena-row-actions { display: flex; gap: 8px; }

.arena-controls {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 18px;
  padding: 16px 24px;
}

.arena-player-toggle {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--ui-text-secondary);
  font-size: 12px;
  white-space: nowrap;
  cursor: pointer;
}

.arena-player-toggle input {
  accent-color: var(--ui-accent);
}

.arena-search {
  display: grid;
  grid-template-columns: auto minmax(220px, 420px);
  align-items: center;
  justify-content: end;
  gap: 10px;
  color: var(--ui-text-secondary);
  font-size: 12px;
}

.arena-search input,
.arena-rp-input {
  min-height: 36px;
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
  background: var(--ui-canvas);
  color: var(--ui-text);
}
.arena-search input { width: 100%; padding: 0 11px; }
.arena-rp-input { width: 150px; padding: 0 9px; }
.arena-search input:focus-visible,
.arena-rp-input:focus-visible { outline: 2px solid var(--ui-accent); outline-offset: 1px; }

.arena-table-wrap { position: relative; min-height: 220px; overflow-x: auto; }
.arena-table { width: 100%; border-collapse: collapse; }
.arena-table th,
.arena-table td { padding: 12px 16px; border-top: 1px solid var(--ui-border); text-align: left; vertical-align: middle; }
.arena-table th { color: var(--ui-text-muted); background: var(--ui-canvas); font-size: 11px; font-weight: 700; white-space: nowrap; }
.arena-table td { color: var(--ui-text-secondary); }
.arena-table td strong,
.arena-table td code { display: block; }
.arena-table td strong { color: var(--ui-text); }
.arena-table td code { margin-top: 3px; color: var(--ui-text-muted); font-size: 10px; }
.arena-table tr.unsupported { background: color-mix(in oklch, var(--ui-canvas) 70%, transparent); }
.arena-table tr.npc { background: color-mix(in oklch, var(--ui-accent) 4%, var(--ui-surface)); }
.arena-table tr.unranked .arena-rank { color: var(--ui-text-muted) !important; }
.arena-rank { width: 72px; color: var(--ui-accent) !important; font-size: 18px; font-weight: 750; }
.arena-capability { color: var(--ui-warning); font-size: 11px; }
.arena-field-note { display: block; margin-top: 5px; color: var(--ui-warning); font-size: 10px; }
.arena-static-rp { color: var(--ui-text); font-variant-numeric: tabular-nums; font-weight: 700; }
.arena-npc-badge {
  display: inline-flex;
  padding: 3px 7px;
  border: 1px solid var(--ui-accent);
  border-radius: 999px;
  color: var(--ui-accent);
  font-size: 10px;
  font-weight: 750;
}

.arena-button {
  min-height: 36px;
  padding: 0 12px;
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
  background: var(--ui-surface);
  color: var(--ui-text-secondary);
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}
.arena-button:hover:not(:disabled) { border-color: var(--ui-border-strong); color: var(--ui-text); background: var(--ui-surface-hover); }
.arena-button--primary { border-color: var(--ui-accent); background: var(--ui-accent); color: var(--ui-canvas); }
.arena-button--danger { border-color: var(--ui-danger); color: var(--ui-danger); background: var(--ui-danger-soft); }
.arena-button:disabled { opacity: 0.45; cursor: not-allowed; }
.arena-empty { height: 160px; text-align: center !important; color: var(--ui-text-muted) !important; }
.arena-loading { position: absolute; inset: 0; display: grid; place-items: center; background: color-mix(in oklch, var(--ui-surface) 82%, transparent); color: var(--ui-text-secondary); }
.arena-footer { display: grid; gap: 4px; padding: 16px 24px 20px; border-top: 1px solid var(--ui-border); font-size: 11px; line-height: 1.5; }

@media (max-width: 760px) {
  .arena-page { padding-inline: 8px; }
  .arena-header { flex-direction: column; padding: 18px; }
  .arena-header__actions { width: 100%; flex-wrap: wrap; }
  .arena-controls { display: grid; justify-content: stretch; padding-inline: 18px; }
  .arena-search { grid-template-columns: 1fr; justify-content: stretch; }
  .arena-table th,
  .arena-table td { padding: 10px 12px; }
  .arena-row-actions { flex-direction: column; }
  .arena-footer { padding-inline: 18px; }
}
</style>
