<script setup>
import AppIcon from '@/components/modules/AppIcon.vue'
import ElementIcon from '@/components/modules/ElementIcon.vue'
import VariantBadge from '@/components/modules/VariantBadge.vue'
import { elementTranslationKey } from '@/components/modules/pal-species-filter'
import { usePalEditorStore } from '@/stores/paleditor'
import { computed, nextTick, onMounted, ref } from 'vue'

const palStore = usePalEditorStore()
const editingKind = ref(null)
const editingGuildId = ref(null)
const editDraft = ref('')

const MAX_GUILD_NAME_LENGTH = 24
const MAX_BASE_CAMP_LEVEL = 35
const MAX_GUILD_CHEST_CAPACITY = 2466

const SUITABILITY_LABEL_KEYS = {
  'EPalWorkSuitability::EmitFlame': 'Guild_Suitability_EmitFlame',
  'EPalWorkSuitability::Watering': 'Guild_Suitability_Watering',
  'EPalWorkSuitability::Seeding': 'Guild_Suitability_Seeding',
  'EPalWorkSuitability::GenerateElectricity': 'Guild_Suitability_GenerateElectricity',
  'EPalWorkSuitability::Handcraft': 'Guild_Suitability_Handcraft',
  'EPalWorkSuitability::Collection': 'Guild_Suitability_Collection',
  'EPalWorkSuitability::Deforest': 'Guild_Suitability_Deforest',
  'EPalWorkSuitability::Mining': 'Guild_Suitability_Mining',
  'EPalWorkSuitability::OilExtraction': 'Guild_Suitability_OilExtraction',
  'EPalWorkSuitability::ProductMedicine': 'Guild_Suitability_ProductMedicine',
  'EPalWorkSuitability::Cool': 'Guild_Suitability_Cool',
  'EPalWorkSuitability::Transport': 'Guild_Suitability_Transport',
  'EPalWorkSuitability::MonsterFarm': 'Guild_Suitability_MonsterFarm',
}

const writesDisabled = computed(() => (
  palStore.LOADING_FLAG
  || palStore.GUILD_LOADING
  || palStore.RAW_JSON_PENDING
))

function shortId(value) {
  return value ? String(value).slice(-8) : ''
}

function guildName(guild) {
  return guild.name || palStore.getTranslatedText('PlayerTree_UnnamedGuild')
}

function baseName(base, index) {
  const name = String(base.name || '')
  if (
    name
    && !name.startsWith('新規生成拠点テンプレート名')
    && base.kind !== 'missing'
  ) {
    return name
  }
  return palStore.getTranslatedText('PlayerTree_BaseNumber', [index + 1])
}

function workerName(worker) {
  return worker.name || worker.internal_id || shortId(worker.pal_id)
}

function workerGender(worker) {
  if (worker.gender === 'EPalGenderType::Female') return '♀'
  if (worker.gender === 'EPalGenderType::Male') return '♂'
  return ''
}

function workerStatusKey(worker) {
  if (worker.fainted) return 'Guild_WorkerFainted'
  if (worker.sick) return 'Guild_WorkerSick'
  return 'Guild_WorkerHealthy'
}

function workerSuitabilities(worker) {
  return Object.entries(worker.work_suitabilities || {})
    .filter(([, level]) => Number(level) > 0)
    .sort(([left], [right]) => left.localeCompare(right))
}

function suitabilityLabel(key) {
  return palStore.getTranslatedText(
    SUITABILITY_LABEL_KEYS[key] || 'Guild_Suitability_Unknown',
    [key.split('::').pop()],
  )
}

function suitabilityIconSrc(key) {
  return key ? `/image/suitabilities/${key.split('::').pop()}` : ''
}

function passiveSkillName(skill) {
  return palStore.PASSIVE_SKILLS[skill]?.I18n?.[0] || skill
}

function elementLabel(element) {
  return palStore.getTranslatedText(
    elementTranslationKey(element),
    [element],
  )
}

function isEditing(kind, guild) {
  return editingKind.value === kind
    && editingGuildId.value === guild.guild_id
}

function cancelEdit() {
  editingKind.value = null
  editingGuildId.value = null
  editDraft.value = ''
}

async function startEdit(kind, guild, value, event) {
  if (writesDisabled.value) return
  editingKind.value = kind
  editingGuildId.value = guild.guild_id
  editDraft.value = String(value ?? '')
  const row = event.currentTarget.closest('[data-edit-row]')
  await nextTick()
  const input = row?.querySelector('input')
  input?.focus()
  input?.select()
}

function validDraft(kind, guild) {
  if (kind === 'name') {
    const name = editDraft.value.trim()
    return name.length > 0 && name.length <= MAX_GUILD_NAME_LENGTH
  }
  const value = Number(editDraft.value)
  if (!Number.isInteger(value)) return false
  if (kind === 'level') {
    return value > guild.base_camp_level && value <= MAX_BASE_CAMP_LEVEL
  }
  if (kind === 'chest') {
    return value > guild.guild_chest_capacity
      && value <= MAX_GUILD_CHEST_CAPACITY
  }
  return false
}

async function saveEdit(kind, guild) {
  if (writesDisabled.value || !validDraft(kind, guild)) return
  let updated = false
  if (kind === 'name') {
    updated = await palStore.updateGuildName(guild.guild_id, editDraft.value)
  } else if (kind === 'level') {
    updated = await palStore.updateGuildBaseCampLevel(
      guild.guild_id,
      Number(editDraft.value),
    )
  } else if (kind === 'chest') {
    updated = await palStore.updateGuildChestCapacity(
      guild.guild_id,
      Number(editDraft.value),
    )
  }
  if (updated) cancelEdit()
}

function canEditLevel(guild) {
  return guild.base_camp_level_status === 'available'
    && Number.isInteger(guild.base_camp_level)
    && guild.base_camp_level < MAX_BASE_CAMP_LEVEL
}

function canEditChest(guild) {
  return guild.guild_chest_status === 'available'
    && Number.isInteger(guild.guild_chest_capacity)
    && guild.guild_chest_capacity < MAX_GUILD_CHEST_CAPACITY
}

function refreshGuilds() {
  cancelEdit()
  return palStore.loadGuilds()
}

onMounted(refreshGuilds)
</script>

<template>
  <section class="guild-view">
    <div class="guild-shell">
      <div class="guild-actions">
        <button
          class="guild-button"
          type="button"
          :disabled="palStore.GUILD_LOADING || palStore.LOADING_FLAG"
          @click="refreshGuilds"
        >
          <AppIcon name="refresh" :size="16" />
          {{ palStore.getTranslatedText('Guild_Refresh') }}
        </button>
      </div>

      <div v-if="palStore.GUILD_LOADING && !palStore.GUILD_LIST.length"
        class="guild-loading" aria-busy="true">
        <span v-for="index in 3" :key="index" />
      </div>

      <div v-else-if="!palStore.GUILD_LIST.length" class="guild-empty">
        <AppIcon name="building" :size="24" />
        <p>{{ palStore.getTranslatedText('Guild_Empty') }}</p>
      </div>

      <div v-else class="guild-list">
        <article v-for="guild in palStore.GUILD_LIST" :key="guild.guild_id"
          class="guild-card">
          <header class="guild-card__header">
            <div class="guild-title-block">
              <div class="guild-name-row" data-edit-row>
                <span class="guild-mark"><AppIcon name="building" :size="18" /></span>
                <input v-if="isEditing('name', guild)"
                  v-model="editDraft" class="guild-input guild-input--name"
                  type="text" maxlength="24"
                  :aria-label="palStore.getTranslatedText('Common_Edit')"
                  :disabled="writesDisabled"
                  @keydown.enter.prevent="saveEdit('name', guild)"
                  @keydown.esc.prevent="cancelEdit" />
                <h2 v-else>{{ guildName(guild) }}</h2>
                <span v-if="guild.kind === 'independent'" class="guild-kind">
                  {{ palStore.getTranslatedText('PlayerTree_Independent') }}
                </span>
                <button v-if="guild.name_editable" class="icon-button" type="button"
                  :title="palStore.getTranslatedText(isEditing('name', guild) ? 'Common_Save' : 'Common_Edit')"
                  :aria-label="palStore.getTranslatedText(isEditing('name', guild) ? 'Common_Save' : 'Common_Edit')"
                  :disabled="writesDisabled || (isEditing('name', guild) && !validDraft('name', guild))"
                  @click="isEditing('name', guild)
                    ? saveEdit('name', guild)
                    : startEdit('name', guild, guild.name, $event)">
                  <AppIcon :name="isEditing('name', guild) ? 'check' : 'edit'" :size="15" />
                </button>
              </div>
              <p :title="guild.guild_id">
                {{ palStore.getTranslatedText('Guild_GuildId') }}
                <span>{{ shortId(guild.guild_id) }}</span>
              </p>
            </div>
            <div class="guild-summary">
              <strong>{{ guild.member_count }}</strong>
              <span>{{ palStore.getTranslatedText('PlayerTree_Members') }}</span>
              <strong>{{ guild.base_count }}</strong>
              <span>{{ palStore.getTranslatedText('PlayerTree_Bases') }}</span>
            </div>
          </header>

          <div class="guild-metrics">
            <div class="guild-metric" data-edit-row>
              <span class="guild-metric__icon"><AppIcon name="activity" :size="17" /></span>
              <div>
                <small>{{ palStore.getTranslatedText('Guild_TerminalLevel') }}</small>
                <strong v-if="!isEditing('level', guild)">
                  {{ guild.base_camp_level_status === 'available'
                    ? palStore.getTranslatedText('Guild_TerminalLevelValue', [guild.base_camp_level])
                    : palStore.getTranslatedText('Guild_FieldUnavailable') }}
                </strong>
                <input v-else v-model.number="editDraft" class="guild-input"
                  type="number" :min="guild.base_camp_level + 1"
                  :max="MAX_BASE_CAMP_LEVEL"
                  :aria-label="palStore.getTranslatedText('Guild_EditTerminalLevel')"
                  :disabled="writesDisabled"
                  @keydown.enter.prevent="saveEdit('level', guild)"
                  @keydown.esc.prevent="cancelEdit" />
                <span>{{ palStore.getTranslatedText('Guild_TerminalLevelHelp') }}</span>
              </div>
              <button v-if="canEditLevel(guild)" class="icon-button" type="button"
                :title="palStore.getTranslatedText(isEditing('level', guild) ? 'Common_Save' : 'Guild_EditTerminalLevel')"
                :aria-label="palStore.getTranslatedText(isEditing('level', guild) ? 'Common_Save' : 'Guild_EditTerminalLevel')"
                :disabled="writesDisabled || (isEditing('level', guild) && !validDraft('level', guild))"
                @click="isEditing('level', guild)
                  ? saveEdit('level', guild)
                  : startEdit('level', guild, guild.base_camp_level, $event)">
                <AppIcon :name="isEditing('level', guild) ? 'check' : 'edit'" :size="15" />
              </button>
            </div>

            <div class="guild-metric" data-edit-row>
              <span class="guild-metric__icon"><AppIcon name="box" :size="17" /></span>
              <div>
                <small>{{ palStore.getTranslatedText('PlayerTree_GuildChest') }}</small>
                <strong v-if="!isEditing('chest', guild)">
                  {{ guild.guild_chest_status === 'available'
                    ? palStore.getTranslatedText('PlayerTree_GuildChestSlots', [guild.guild_chest_capacity])
                    : palStore.getTranslatedText('Guild_FieldUnavailable') }}
                </strong>
                <input v-else v-model.number="editDraft" class="guild-input"
                  type="number" :min="guild.guild_chest_capacity + 1"
                  :max="MAX_GUILD_CHEST_CAPACITY"
                  :aria-label="palStore.getTranslatedText('PlayerTree_EditGuildChestCapacity')"
                  :disabled="writesDisabled"
                  @keydown.enter.prevent="saveEdit('chest', guild)"
                  @keydown.esc.prevent="cancelEdit" />
                <span>{{ palStore.getTranslatedText('PlayerTree_GuildChestCapacityHelp') }}</span>
              </div>
              <button v-if="canEditChest(guild)" class="icon-button" type="button"
                :title="palStore.getTranslatedText(isEditing('chest', guild) ? 'Common_Save' : 'PlayerTree_EditGuildChestCapacity')"
                :aria-label="palStore.getTranslatedText(isEditing('chest', guild) ? 'Common_Save' : 'PlayerTree_EditGuildChestCapacity')"
                :disabled="writesDisabled || (isEditing('chest', guild) && !validDraft('chest', guild))"
                @click="isEditing('chest', guild)
                  ? saveEdit('chest', guild)
                  : startEdit('chest', guild, guild.guild_chest_capacity, $event)">
                <AppIcon :name="isEditing('chest', guild) ? 'check' : 'edit'" :size="15" />
              </button>
            </div>
          </div>

          <div class="guild-content-grid">
            <section class="guild-section">
              <header>
                <div>
                  <AppIcon name="building" :size="16" />
                  <h3>{{ palStore.getTranslatedText('PlayerTree_Bases') }}</h3>
                </div>
                <span>{{ guild.base_count }}</span>
              </header>
              <div v-if="guild.bases.length" class="base-list">
                <article v-for="(base, index) in guild.bases" :key="base.base_id"
                  :class="['base-row', { 'is-missing': base.kind === 'missing' }]">
                  <div class="base-row__heading">
                    <span class="base-index">{{ index + 1 }}</span>
                    <div>
                      <strong>{{ baseName(base, index) }}</strong>
                      <small :title="base.base_id">{{ shortId(base.base_id) }}</small>
                    </div>
                  </div>
                  <div class="worker-capacity-row">
                    <div>
                      <small>{{ palStore.getTranslatedText('Guild_WorkerCapacity') }}</small>
                      <strong>
                        <template v-if="base.worker_capacity_status === 'available'">
                          {{ palStore.getTranslatedText('Guild_WorkerCapacityValue', [
                            base.worker_count,
                            base.worker_capacity,
                          ]) }}
                        </template>
                        <template v-else>
                          {{ base.kind === 'missing'
                            ? palStore.getTranslatedText('Guild_BaseRecordMissing')
                            : palStore.getTranslatedText('Guild_FieldUnavailable') }}
                        </template>
                      </strong>
                    </div>
                  </div>
                  <section v-if="base.kind === 'base'" class="base-workers">
                    <header>
                      <div>
                        <AppIcon name="activity" :size="14" />
                        <strong>{{ palStore.getTranslatedText('Guild_WorkingPals') }}</strong>
                        <span>{{ base.workers?.length || 0 }}</span>
                      </div>
                    </header>
                    <div v-if="base.workers?.length" class="worker-pal-grid">
                      <article
                        v-for="worker in base.workers"
                        :key="worker.pal_id"
                        class="worker-pal"
                        tabindex="0"
                        :aria-label="palStore.getTranslatedText('Guild_WorkerPalAria', [
                          workerName(worker),
                          worker.level,
                        ])"
                      >
                        <img
                          v-if="worker.icon_access_key"
                          class="worker-pal__portrait"
                          :src="`/image/pals/${worker.icon_access_key}`"
                          alt=""
                          loading="lazy"
                          draggable="false"
                        >
                        <span v-else class="worker-pal__portrait is-placeholder">
                          <AppIcon name="activity" :size="18" />
                        </span>
                        <span class="worker-pal__copy">
                          <strong>{{ workerName(worker) }}</strong>
                          <small>
                            {{ palStore.getTranslatedText('Common_LevelWithValue', [worker.level]) }}
                            <template v-if="workerGender(worker)"> · {{ workerGender(worker) }}</template>
                          </small>
                        </span>
                        <span
                          v-if="worker.fainted || worker.sick"
                          :class="['worker-pal__status-dot', {
                            'is-fainted': worker.fainted,
                            'is-sick': worker.sick && !worker.fainted,
                          }]"
                          aria-hidden="true"
                        />

                        <div class="worker-pal-tooltip" role="tooltip">
                          <header class="worker-tooltip__identity">
                            <img
                              v-if="worker.icon_access_key"
                              :src="`/image/pals/${worker.icon_access_key}`"
                              alt=""
                              loading="lazy"
                              draggable="false"
                            >
                            <span v-else class="worker-tooltip__placeholder">
                              <AppIcon name="activity" :size="24" />
                            </span>
                            <div>
                              <span class="worker-tooltip__eyebrow">
                                {{ palStore.getTranslatedText('Guild_WorkingPals') }}
                              </span>
                              <strong>{{ workerName(worker) }}</strong>
                              <small :title="worker.pal_id">
                                {{ worker.internal_id || shortId(worker.pal_id) }}
                              </small>
                            </div>
                            <span class="worker-tooltip__variants">
                              <VariantBadge v-if="worker.tower" kind="tower" :size="14" show-label />
                              <VariantBadge v-if="worker.boss" kind="boss" :size="14" show-label />
                              <VariantBadge v-if="worker.rare" kind="rare" :size="14" show-label />
                            </span>
                          </header>

                          <div class="worker-tooltip__meta">
                            <span>{{ palStore.getTranslatedText('Common_LevelWithValue', [worker.level]) }}</span>
                            <span v-if="workerGender(worker)">{{ workerGender(worker) }}</span>
                            <span :class="{
                              'is-healthy': !worker.sick && !worker.fainted,
                              'is-sick': worker.sick && !worker.fainted,
                              'is-fainted': worker.fainted,
                            }">
                              {{ palStore.getTranslatedText(workerStatusKey(worker)) }}
                            </span>
                          </div>

                          <div v-if="worker.elements?.length" class="worker-tooltip__elements">
                            <span v-for="element in worker.elements" :key="element">
                              <ElementIcon
                                :element="element"
                                :size="15"
                                :alt="elementLabel(element)"
                              />
                              {{ elementLabel(element) }}
                            </span>
                          </div>

                          <section v-if="workerSuitabilities(worker).length"
                            class="worker-tooltip__section">
                            <h4>{{ palStore.getTranslatedText('Editor_Suitabilities') }}</h4>
                            <div class="worker-tooltip__suitabilities">
                              <span v-for="[suitability, level] in workerSuitabilities(worker)"
                                :key="suitability">
                                <img :src="suitabilityIconSrc(suitability)" alt="">
                                <span>{{ suitabilityLabel(suitability) }}</span>
                                <strong>{{ level }}</strong>
                              </span>
                            </div>
                          </section>

                          <section class="worker-tooltip__section">
                            <h4>{{ palStore.getTranslatedText('Editor_Passive_Skills') }}</h4>
                            <div v-if="worker.passive_skills?.length"
                              class="worker-tooltip__passives">
                              <span v-for="skill in worker.passive_skills" :key="skill">
                                {{ passiveSkillName(skill) }}
                              </span>
                            </div>
                            <p v-else>{{ palStore.getTranslatedText('Guild_NoPassiveSkills') }}</p>
                          </section>
                        </div>
                      </article>
                    </div>
                    <p v-else class="base-workers__empty">
                      {{ palStore.getTranslatedText('Guild_NoWorkingPals') }}
                    </p>
                  </section>
                </article>
              </div>
              <p v-else class="section-empty">
                {{ palStore.getTranslatedText('Guild_NoBases') }}
              </p>
            </section>

            <section class="guild-section">
              <header>
                <div>
                  <AppIcon name="user" :size="16" />
                  <h3>{{ palStore.getTranslatedText('PlayerTree_Members') }}</h3>
                </div>
                <span>{{ guild.member_count }}</span>
              </header>
              <div v-if="guild.members.length" class="member-list">
                <div v-for="member in guild.members" :key="member.player_id"
                  class="member-row">
                  <span class="member-avatar">
                    {{ (member.name || '?').slice(0, 1).toUpperCase() }}
                  </span>
                  <div>
                    <strong>{{ member.name || shortId(member.player_id) }}</strong>
                    <small :title="member.player_id">{{ shortId(member.player_id) }}</small>
                  </div>
                  <span v-if="member.level != null" class="member-level">
                    {{ palStore.getTranslatedText('Common_LevelWithValue', [member.level]) }}
                  </span>
                  <span v-else class="member-level is-muted">
                    {{ palStore.getTranslatedText('Guild_PlayerDataUnavailable') }}
                  </span>
                </div>
              </div>
              <p v-else class="section-empty">
                {{ palStore.getTranslatedText('Guild_NoMembers') }}
              </p>
            </section>
          </div>
        </article>
      </div>
    </div>
  </section>
</template>

<style scoped>
.guild-view {
  min-height: 100dvh;
  padding: calc(var(--editor-top-offset) + 28px) 24px 48px;
  color: var(--ui-text);
  background: var(--ui-canvas);
}

.guild-shell {
  width: min(1180px, 100%);
  margin: 0 auto;
}

.guild-actions,
.guild-card__header,
.guild-name-row,
.guild-summary,
.guild-metric,
.guild-section > header,
.guild-section > header > div,
.base-row__heading,
.worker-capacity-row,
.base-workers > header,
.base-workers > header > div,
.worker-pal,
.worker-tooltip__identity,
.worker-tooltip__meta,
.worker-tooltip__elements,
.worker-tooltip__elements > span,
.worker-tooltip__suitabilities > span,
.member-row,
.guild-button,
.icon-button {
  display: flex;
  align-items: center;
}

.guild-actions {
  justify-content: flex-end;
  margin-bottom: 16px;
}

.guild-button {
  min-height: 38px;
  gap: 8px;
  padding: 0 14px;
  color: var(--ui-text);
  background: var(--ui-surface-raised);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
  font-weight: 700;
}

.guild-button:hover:not(:disabled) {
  border-color: color-mix(in srgb, var(--ui-accent) 55%, var(--ui-border));
  background: var(--ui-surface-hover);
}

.guild-list {
  display: grid;
  gap: 18px;
}

.guild-card {
  overflow: visible;
  background: var(--ui-surface);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-lg);
  box-shadow: var(--ui-shadow-sm);
}

.guild-card__header {
  justify-content: space-between;
  gap: 20px;
  padding: 20px 22px;
  border-bottom: 1px solid var(--ui-border);
}

.guild-title-block {
  min-width: 0;
}

.guild-name-row {
  min-width: 0;
  gap: 9px;
}

.guild-name-row h2 {
  min-width: 0;
  margin: 0;
  overflow: hidden;
  font-size: 19px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.guild-title-block > p {
  margin: 6px 0 0 39px;
  color: var(--ui-text-muted);
  font-size: 10px;
}

.guild-title-block > p span {
  margin-left: 5px;
  color: var(--ui-text-secondary);
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
}

.guild-mark,
.guild-metric__icon {
  display: inline-grid;
  place-content: center;
  color: var(--ui-accent);
  background: var(--ui-accent-soft);
  border-radius: 8px;
}

.guild-mark {
  width: 30px;
  height: 30px;
}

.guild-kind {
  padding: 2px 7px;
  color: var(--ui-accent);
  background: var(--ui-accent-soft);
  border-radius: 999px;
  font-size: 9px;
  font-weight: 800;
}

.guild-summary {
  flex: 0 0 auto;
  gap: 7px;
  color: var(--ui-text-muted);
  font-size: 11px;
}

.guild-summary strong {
  color: var(--ui-text);
  font-size: 15px;
}

.guild-summary span + strong {
  margin-left: 9px;
}

.guild-metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1px;
  background: var(--ui-border);
  border-bottom: 1px solid var(--ui-border);
}

.guild-metric {
  min-width: 0;
  min-height: 92px;
  gap: 12px;
  padding: 16px 22px;
  background: var(--ui-surface-raised);
}

.guild-metric__icon {
  width: 34px;
  height: 34px;
  flex: 0 0 34px;
}

.guild-metric > div {
  display: grid;
  min-width: 0;
  flex: 1 1 auto;
  gap: 3px;
}

.guild-metric small,
.worker-capacity-row small {
  color: var(--ui-text-muted);
  font-size: 10px;
  font-weight: 700;
}

.guild-metric strong {
  font-size: 16px;
}

.guild-metric > div > span {
  color: var(--ui-text-muted);
  font-size: 10px;
}

.guild-content-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(280px, .9fr);
  gap: 18px;
  padding: 20px 22px 22px;
}

.guild-section {
  min-width: 0;
}

.guild-section > header {
  justify-content: space-between;
  margin-bottom: 10px;
}

.guild-section > header > div {
  gap: 7px;
}

.guild-section h3 {
  margin: 0;
  font-size: 12px;
}

.guild-section > header > span {
  color: var(--ui-text-muted);
  font-size: 10px;
}

.base-list,
.member-list {
  display: grid;
  gap: 7px;
}

.base-row,
.member-row {
  min-width: 0;
  background: var(--ui-surface-raised);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
}

.base-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 16px;
  min-height: 62px;
  padding: 10px 12px;
}

.base-row.is-missing {
  border-style: dashed;
}

.base-row__heading {
  min-width: 0;
  gap: 10px;
}

.base-index {
  display: inline-grid;
  width: 26px;
  height: 26px;
  flex: 0 0 26px;
  place-content: center;
  color: var(--ui-accent);
  background: var(--ui-accent-soft);
  border-radius: 7px;
  font-size: 10px;
  font-weight: 800;
}

.base-row__heading > div,
.member-row > div,
.worker-capacity-row > div {
  display: grid;
  min-width: 0;
  gap: 3px;
}

.base-row__heading strong,
.member-row strong {
  overflow: hidden;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.base-row__heading small,
.member-row small {
  color: var(--ui-text-muted);
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 9px;
}

.worker-capacity-row {
  gap: 7px;
}

.worker-capacity-row > div {
  justify-items: end;
}

.worker-capacity-row strong {
  font-size: 11px;
}

.base-workers {
  min-width: 0;
  grid-column: 1 / -1;
  padding-top: 10px;
  border-top: 1px solid var(--ui-border);
}

.base-workers > header {
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.base-workers > header > div {
  min-width: 0;
  gap: 6px;
  color: var(--ui-text-secondary);
}

.base-workers > header strong {
  font-size: 10px;
}

.base-workers > header span {
  color: var(--ui-text-muted);
  font-size: 9px;
}

.worker-pal-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(142px, 1fr));
  gap: 6px;
}

.worker-pal {
  position: relative;
  min-width: 0;
  min-height: 42px;
  gap: 8px;
  padding: 5px 7px;
  background: var(--ui-canvas);
  border: 1px solid var(--ui-border);
  border-radius: 8px;
  outline: 0;
  transition:
    border-color 140ms ease,
    background-color 140ms ease,
    transform 140ms ease;
}

.worker-pal:hover,
.worker-pal:focus-visible {
  z-index: 30;
  background: var(--ui-surface-hover);
  border-color: color-mix(in srgb, var(--ui-accent) 62%, var(--ui-border));
  transform: translateY(-1px);
}

.worker-pal:focus-visible {
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--ui-accent) 24%, transparent);
}

.worker-pal__portrait,
.worker-pal__portrait.is-placeholder {
  width: 31px;
  height: 31px;
  flex: 0 0 31px;
  border-radius: 7px;
}

.worker-pal__portrait {
  object-fit: contain;
}

.worker-pal__portrait.is-placeholder,
.worker-tooltip__placeholder {
  display: inline-grid;
  place-content: center;
  color: var(--ui-text-muted);
  background: var(--ui-surface-raised);
}

.worker-pal__copy {
  display: grid;
  min-width: 0;
  flex: 1 1 auto;
  gap: 2px;
}

.worker-pal__copy strong,
.worker-pal__copy small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.worker-pal__copy strong {
  font-size: 10px;
}

.worker-pal__copy small {
  color: var(--ui-text-muted);
  font-size: 9px;
}

.worker-pal__status-dot {
  width: 6px;
  height: 6px;
  flex: 0 0 6px;
  border-radius: 50%;
}

.worker-pal__status-dot.is-sick {
  background: var(--ui-warning, #f6c96b);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--ui-warning, #f6c96b) 16%, transparent);
}

.worker-pal__status-dot.is-fainted {
  background: var(--ui-danger);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--ui-danger) 16%, transparent);
}

.worker-pal-tooltip {
  visibility: hidden;
  position: absolute;
  z-index: 80;
  top: calc(100% + 8px);
  left: 0;
  width: min(340px, calc(100vw - 64px));
  padding: 13px;
  color: var(--ui-text);
  background: color-mix(in srgb, var(--ui-surface) 96%, transparent);
  border: 1px solid var(--ui-border-strong);
  border-radius: var(--ui-radius-md);
  box-shadow: var(--ui-shadow-md);
  opacity: 0;
  pointer-events: none;
  transform: translateY(-4px);
  transition:
    opacity 140ms ease,
    transform 140ms ease,
    visibility 140ms;
  backdrop-filter: blur(12px);
}

.worker-pal:hover .worker-pal-tooltip,
.worker-pal:focus-visible .worker-pal-tooltip {
  visibility: visible;
  opacity: 1;
  transform: translateY(0);
}

.worker-tooltip__identity {
  position: relative;
  min-width: 0;
  align-items: flex-start;
  gap: 10px;
  padding-bottom: 11px;
  border-bottom: 1px solid var(--ui-border);
}

.worker-tooltip__identity > img,
.worker-tooltip__placeholder {
  width: 48px;
  height: 48px;
  flex: 0 0 48px;
  object-fit: contain;
  border-radius: 10px;
}

.worker-tooltip__identity > div {
  display: grid;
  min-width: 0;
  flex: 1 1 auto;
  gap: 2px;
}

.worker-tooltip__identity strong,
.worker-tooltip__identity small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.worker-tooltip__identity strong {
  font-size: 13px;
}

.worker-tooltip__identity small,
.worker-tooltip__eyebrow {
  color: var(--ui-text-muted);
  font-size: 9px;
}

.worker-tooltip__identity small {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
}

.worker-tooltip__eyebrow {
  font-weight: 800;
  letter-spacing: .06em;
  text-transform: uppercase;
}

.worker-tooltip__variants {
  display: flex;
  position: absolute;
  right: 0;
  bottom: 8px;
  gap: 7px;
  color: var(--ui-text-secondary);
  font-size: 9px;
}

.worker-tooltip__meta {
  flex-wrap: wrap;
  gap: 6px;
  padding: 10px 0 7px;
}

.worker-tooltip__meta > span,
.worker-tooltip__elements > span,
.worker-tooltip__passives > span {
  padding: 3px 7px;
  color: var(--ui-text-secondary);
  background: var(--ui-surface-raised);
  border: 1px solid var(--ui-border);
  border-radius: 999px;
  font-size: 9px;
  font-weight: 700;
}

.worker-tooltip__meta > span.is-healthy {
  color: var(--ui-success);
  border-color: color-mix(in srgb, var(--ui-success) 38%, var(--ui-border));
}

.worker-tooltip__meta > span.is-sick {
  color: var(--ui-warning, #f6c96b);
  border-color: color-mix(in srgb, var(--ui-warning, #f6c96b) 38%, var(--ui-border));
}

.worker-tooltip__meta > span.is-fainted {
  color: var(--ui-danger);
  border-color: color-mix(in srgb, var(--ui-danger) 38%, var(--ui-border));
}

.worker-tooltip__elements {
  flex-wrap: wrap;
  gap: 5px;
  margin-bottom: 8px;
}

.worker-tooltip__elements > span {
  gap: 4px;
}

.worker-tooltip__section {
  margin-top: 9px;
}

.worker-tooltip__section h4 {
  margin: 0 0 6px;
  color: var(--ui-text-muted);
  font-size: 9px;
  letter-spacing: .05em;
  text-transform: uppercase;
}

.worker-tooltip__section p,
.base-workers__empty {
  margin: 0;
  color: var(--ui-text-muted);
  font-size: 9px;
}

.worker-tooltip__suitabilities {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 5px;
}

.worker-tooltip__suitabilities > span {
  min-width: 0;
  gap: 5px;
  padding: 5px 6px;
  color: var(--ui-text-secondary);
  background: var(--ui-surface-raised);
  border-radius: 7px;
  font-size: 9px;
}

.worker-tooltip__suitabilities img {
  width: 17px;
  height: 17px;
  flex: 0 0 17px;
  object-fit: contain;
}

.worker-tooltip__suitabilities span > span {
  min-width: 0;
  flex: 1 1 auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.worker-tooltip__suitabilities strong {
  color: var(--ui-text);
  font-size: 10px;
}

.worker-tooltip__passives {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.base-workers__empty {
  padding: 5px 1px 1px;
}

.member-row {
  min-height: 48px;
  gap: 10px;
  padding: 8px 10px;
}

.member-avatar {
  display: inline-grid;
  width: 29px;
  height: 29px;
  flex: 0 0 29px;
  place-content: center;
  color: var(--ui-accent);
  background: var(--ui-accent-soft);
  border-radius: 50%;
  font-size: 10px;
  font-weight: 800;
}

.member-row > div {
  flex: 1 1 auto;
}

.member-level {
  flex: 0 0 auto;
  color: var(--ui-text-secondary);
  font-size: 10px;
  font-weight: 700;
}

.member-level.is-muted {
  color: var(--ui-text-muted);
  font-size: 9px;
  font-weight: 500;
}

.icon-button {
  width: 28px;
  height: 28px;
  flex: 0 0 28px;
  justify-content: center;
  padding: 0;
  color: var(--ui-text-muted);
  background: transparent;
  border: 0;
  border-radius: 6px;
}

.icon-button:hover:not(:disabled),
.icon-button:focus-visible {
  color: var(--ui-accent);
  background: var(--ui-accent-soft);
}

.guild-input {
  width: 76px;
  height: 29px;
  padding: 0 7px;
  color: var(--ui-text);
  background: var(--ui-canvas);
  border: 1px solid var(--ui-accent);
  border-radius: 6px;
  font: inherit;
  font-weight: 700;
  outline: 0;
}

.guild-input--name {
  width: min(300px, 45vw);
}

.guild-input:focus {
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--ui-accent) 22%, transparent);
}

.section-empty,
.guild-empty {
  color: var(--ui-text-muted);
  text-align: center;
}

.section-empty {
  margin: 0;
  padding: 20px 10px;
  background: var(--ui-surface-raised);
  border: 1px dashed var(--ui-border);
  border-radius: var(--ui-radius-sm);
  font-size: 10px;
}

.guild-empty {
  display: grid;
  min-height: 260px;
  place-content: center;
  justify-items: center;
  gap: 10px;
  background: var(--ui-surface);
  border: 1px dashed var(--ui-border);
  border-radius: var(--ui-radius-lg);
}

.guild-empty p {
  margin: 0;
}

.guild-loading {
  display: grid;
  gap: 14px;
}

.guild-loading span {
  height: 260px;
  background: linear-gradient(
    90deg,
    var(--ui-surface) 25%,
    var(--ui-surface-hover) 50%,
    var(--ui-surface) 75%
  );
  background-size: 200% 100%;
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-lg);
  animation: guild-loading 1.2s linear infinite;
}

button:disabled {
  cursor: not-allowed;
  opacity: .55;
}

@keyframes guild-loading {
  to { background-position: -200% 0; }
}

@media (max-width: 820px) {
  .guild-view {
    padding-right: 14px;
    padding-left: 14px;
  }

  .guild-card__header {
    align-items: flex-start;
    flex-direction: column;
  }

  .guild-metrics,
  .guild-content-grid {
    grid-template-columns: 1fr;
  }

  .guild-summary {
    width: 100%;
  }
}

@media (max-width: 520px) {
  .guild-view {
    padding-top: calc(var(--editor-top-offset) + 18px);
  }

  .guild-card__header,
  .guild-metric,
  .guild-content-grid {
    padding-right: 14px;
    padding-left: 14px;
  }

  .base-row {
    grid-template-columns: 1fr;
  }

  .worker-capacity-row {
    justify-content: space-between;
  }

  .worker-capacity-row > div {
    justify-items: start;
  }

  .worker-pal-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .worker-pal:nth-child(even) .worker-pal-tooltip {
    right: 0;
    left: auto;
  }
}

@media (prefers-reduced-motion: reduce) {
  .guild-loading span { animation: none; }
  .worker-pal,
  .worker-pal-tooltip { transition: none; }
}
</style>
