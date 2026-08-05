<script setup>
import { computed, reactive, ref, watch } from 'vue'
import AppIcon from '@/components/modules/AppIcon.vue'
import PalSpeciesPicker from '@/components/modules/PalSpeciesPicker.vue'
import PalSkillPicker from '@/components/modules/PalSkillPicker.vue'
import PassivePresetDialog from '@/components/modules/PassivePresetDialog.vue'
import PassiveSkillCard from '@/components/modules/PassiveSkillCard.vue'
import { palSpeciesIconKey } from '@/components/modules/pal-species-filter'
import {
  buildPalGrantPayload,
  clampPalGrantForm,
  createPalGrantForm,
  createPalGrantLimits,
  DEFAULT_REMOTE_SOUL_MAX,
  maximizePalGrantEnhancements,
  maximizePalGrantLevel,
  REMOTE_PAL_GRANT_DRAFT_STORAGE_KEY,
  replacePalGrantPassiveSkills,
} from '@/components/modules/pal-grant-config'
import { usePalEditorStore } from '@/stores/paleditor'

const props = defineProps({
  palOptions: { type: Array, default: () => [] },
  palData: { type: Object, default: () => ({}) },
  passiveOptions: { type: Array, default: () => [] },
  levelMaximum: { type: Number, default: 80 },
  soulMaximum: { type: Number, default: DEFAULT_REMOTE_SOUL_MAX },
  disabled: { type: Boolean, default: false },
  canSubmit: { type: Boolean, default: false },
})

const emit = defineEmits(['submit'])
const palStore = usePalEditorStore()
const loadPalGrantDraft = () => {
  if (typeof localStorage === 'undefined') return {}
  try {
    return JSON.parse(
      localStorage.getItem(REMOTE_PAL_GRANT_DRAFT_STORAGE_KEY) || '{}',
    ) || {}
  } catch {
    return {}
  }
}
const form = reactive(createPalGrantForm(loadPalGrantDraft()))
const selectedPassive = ref('')
const passivePresetDialog = ref(null)
const passivePresets = ref([])
const tr = (key, args = []) => palStore.getTranslatedText(key, args)

const grantLimits = computed(() => createPalGrantLimits({
  unrestricted: !palStore.HIDE_INVALID_OPTIONS,
  soulMaximum: props.soulMaximum,
}))
const ivMaximum = computed(() => grantLimits.value.ivMaximum)
const soulEnhancementMaximum = computed(() => grantLimits.value.soulMaximum)
const soulBonusPercent = rank => Number(rank || 0) * 3
const condensationMaximum = computed(
  () => grantLimits.value.condensationMaximum,
)
const selectedPal = computed(() => props.palData[form.characterId] || null)
const selectedPalName = computed(() => (
  selectedPal.value?.I18n
  || selectedPal.value?.InternalName
  || tr('Remote_PalCharacterId')
))
const ivControls = computed(() => [
  { key: 'hp', image: 'max_hp', icon: 'heart', label: tr('Remote_StatHp') },
  { key: 'shot', image: 'attack', icon: 'sword', label: tr('Remote_StatAttack') },
  { key: 'defense', icon: 'shield', label: tr('Remote_StatDefense') },
])
const soulControls = computed(() => [
  { key: 'soulHp', image: 'max_hp', icon: 'heart', label: tr('Remote_StatHp') },
  { key: 'soulAttack', image: 'attack', icon: 'sword', label: tr('Remote_StatAttack') },
  { key: 'soulDefense', icon: 'shield', label: tr('Remote_StatDefense') },
  { key: 'soulCraftSpeed', image: 'work_speed', icon: 'hammer', label: tr('PlayerAttribute_work_speed') },
])
const passiveMap = computed(() => new Map(
  props.passiveOptions.map(skill => [skill.InternalName, skill]),
))
const availablePassiveOptions = computed(() => {
  const selected = new Set(form.passiveSkills)
  return props.passiveOptions.filter(skill => !selected.has(skill.InternalName))
})
const pinnedPassivePresets = computed(
  () => passivePresets.value.filter(preset => preset.pinned),
)

const applyPassivePreset = skills => {
  replacePalGrantPassiveSkills(form, skills)
  selectedPassive.value = ''
}

const addPassive = skill => {
  replacePalGrantPassiveSkills(form, [...form.passiveSkills, skill.InternalName])
  selectedPassive.value = ''
}

const removePassive = internalName => {
  replacePalGrantPassiveSkills(
    form,
    form.passiveSkills.filter(skill => skill !== internalName),
  )
}

const presetIsAvailable = preset => (
  preset.skills.every(skill => passiveMap.value.has(skill))
)

const presetIsActive = preset => (
  form.passiveSkills.length === preset.skills.length
  && form.passiveSkills.every((skill, index) => skill === preset.skills[index])
)

const adjustLevel = amount => {
  form.level = Math.max(
    1,
    Math.min(props.levelMaximum, Number(form.level || 1) + amount),
  )
}

const setCondensationRank = rank => {
  form.enhancements.condensation = rank + 1
}

watch(
  [() => props.levelMaximum, grantLimits],
  () => clampPalGrantForm(form, props.levelMaximum, grantLimits.value),
  { immediate: true },
)

watch(
  form,
  () => {
    if (typeof localStorage === 'undefined') return
    try {
      localStorage.setItem(
        REMOTE_PAL_GRANT_DRAFT_STORAGE_KEY,
        JSON.stringify(createPalGrantForm(form)),
      )
    } catch {
      // Storage can be unavailable in hardened or private browser contexts.
    }
  },
  { deep: true },
)

const submit = () => {
  if (!form.characterId || !props.canSubmit || props.disabled) return
  emit('submit', buildPalGrantPayload(
    form,
    props.levelMaximum,
    grantLimits.value,
  ))
}
</script>

<template>
  <form class="remote-pal-grant" @submit.prevent="submit">
    <header class="remote-pal-grant__header">
      <span class="remote-pal-grant__header-icon">
        <AppIcon name="paw" :size="19" />
      </span>
      <div>
        <small>{{ palStore.getTranslatedText('Remote_TabOperations') }}</small>
        <h3>{{ palStore.getTranslatedText('Remote_GrantPal') }}</h3>
      </div>
      <button
        type="button"
        class="remote-pal-grant__max-all"
        :disabled="disabled"
        :title="palStore.getTranslatedText('PalEditor_MaxAllEnhancements')"
        @click="maximizePalGrantEnhancements(form, grantLimits)"
      >
        <AppIcon name="chevrons-up" :size="15" />
        {{ palStore.getTranslatedText('Common_Max') }}
      </button>
    </header>

    <div class="remote-pal-grant__layout">
      <div class="remote-pal-grant__primary">
        <section class="remote-pal-grant__identity">
          <div class="remote-pal-grant__pal-preview">
            <span>
              <img
                v-if="selectedPal"
                :src="`/image/pals/${palSpeciesIconKey(selectedPal)}`"
                :alt="selectedPalName"
                draggable="false"
              >
              <AppIcon v-else name="paw" :size="26" />
            </span>
            <div>
              <small>{{ selectedPal?.InternalName || palStore.getTranslatedText('Remote_PalCharacterId') }}</small>
              <strong>{{ selectedPalName }}</strong>
            </div>
          </div>

          <PalSpeciesPicker
            v-model="form.characterId"
            :options="palOptions"
            :selected-option="selectedPal"
            :disabled="disabled"
            show-internal-name
          />
          <div class="remote-pal-grant__level">
            <label for="remote-pal-level">{{ palStore.getTranslatedText('Remote_Level') }}</label>
            <div>
              <button
                type="button"
                :title="palStore.getTranslatedText('Common_Decrease')"
                :disabled="disabled || form.level <= 1"
                @click="adjustLevel(-1)"
              >
                <AppIcon name="chevron-down" :size="15" />
              </button>
              <input
                id="remote-pal-level"
                v-model.number="form.level"
                type="number"
                min="1"
                :max="levelMaximum"
                :disabled="disabled"
                required
              >
              <button
                type="button"
                :title="palStore.getTranslatedText('Common_Increase')"
                :disabled="disabled || form.level >= levelMaximum"
                @click="adjustLevel(1)"
              >
                <AppIcon name="chevron-up" :size="15" />
              </button>
              <button
                type="button"
                class="remote-pal-grant__level-max"
                :title="palStore.getTranslatedText('Common_Max')"
                :disabled="disabled || form.level >= levelMaximum"
                @click="maximizePalGrantLevel(form)"
              >
                {{ palStore.getTranslatedText('Common_Max') }}
              </button>
            </div>
          </div>
        </section>

        <section class="remote-pal-grant__section remote-pal-grant__passive-section">
          <div class="remote-pal-grant__section-heading">
            <div>
              <span class="remote-pal-grant__section-icon">
                <AppIcon name="sparkles" :size="16" />
              </span>
              <strong>{{ palStore.getTranslatedText('Editor_Passive_Skills') }}</strong>
              <small>{{ form.passiveSkills.length }} / 4</small>
            </div>
            <div>
              <button
                type="button"
                class="remote-pal-grant__preset-button"
                :disabled="disabled"
                @click="passivePresetDialog?.open()"
              >
                {{ palStore.getTranslatedText('PalEditor_PassivePresets') }}
              </button>
              <PalSkillPicker
                v-model="selectedPassive"
                kind="passive"
                :options="availablePassiveOptions"
                :disabled="disabled || form.passiveSkills.length >= 4"
                @select="addPassive"
              />
            </div>
          </div>

          <nav
            v-if="pinnedPassivePresets.length"
            class="remote-pal-grant__presets"
            :aria-label="palStore.getTranslatedText('PalEditor_PassivePreset_QuickBar')"
          >
            <button
              v-for="preset in pinnedPassivePresets"
              :key="preset.id"
              type="button"
              :class="{ active: presetIsActive(preset) }"
              :disabled="disabled || !presetIsAvailable(preset)"
              @click="applyPassivePreset(preset.skills)"
            >
              {{ preset.name }}
            </button>
          </nav>

          <div v-if="form.passiveSkills.length" class="remote-pal-grant__passives">
            <div v-for="skill in form.passiveSkills" :key="skill">
              <PassiveSkillCard
                :skill="passiveMap.get(skill)"
                :internal-name="skill"
                :focusable="false"
              />
              <button
                type="button"
                :aria-label="palStore.getTranslatedText('Common_Remove')"
                :disabled="disabled"
                @click="removePassive(skill)"
              >
                <AppIcon name="x" :size="13" />
              </button>
            </div>
          </div>
          <p v-else class="remote-pal-grant__empty">
            <AppIcon name="sparkles" :size="17" />
            {{ palStore.getTranslatedText('PalEditor_PassivePreset_NoSkills') }}
          </p>
        </section>
      </div>

      <div class="remote-pal-grant__training">
        <section class="remote-pal-grant__section">
          <div class="remote-pal-grant__training-heading">
            <span><AppIcon name="activity" :size="16" /></span>
            <strong>{{ palStore.getTranslatedText('Editor_IV') }}</strong>
            <small>0—{{ ivMaximum }}</small>
          </div>
          <div class="remote-pal-grant__stat-list">
            <div v-for="control in ivControls" :key="control.key" class="remote-pal-grant__stat">
              <header>
                <label :for="`remote-iv-${control.key}`">
                  <span class="remote-pal-grant__stat-icon">
                    <img
                      v-if="control.image"
                      :src="`/image/player_attributes/${control.image}`"
                      alt=""
                      draggable="false"
                    >
                    <AppIcon v-else :name="control.icon" :size="15" />
                  </span>
                  {{ control.label }}
                </label>
                <output>{{ form.ivs[control.key] }}</output>
              </header>
              <div>
                <input
                  :id="`remote-iv-${control.key}`"
                  v-model.number="form.ivs[control.key]"
                  type="range"
                  min="0"
                  :max="ivMaximum"
                  :disabled="disabled"
                >
                <input
                  v-model.number="form.ivs[control.key]"
                  type="number"
                  min="0"
                  :max="ivMaximum"
                  :aria-label="control.label"
                  :disabled="disabled"
                >
              </div>
            </div>
          </div>
        </section>

        <section class="remote-pal-grant__section">
          <div class="remote-pal-grant__training-heading">
            <span><AppIcon name="sparkles" :size="16" /></span>
            <strong>{{ palStore.getTranslatedText('Editor_Souls_Upgrade') }}</strong>
            <small>0—{{ soulEnhancementMaximum }} ({{ soulBonusPercent(soulEnhancementMaximum) }}%)</small>
          </div>
          <div class="remote-pal-grant__stat-list remote-pal-grant__stat-list--souls">
            <div v-for="control in soulControls" :key="control.key" class="remote-pal-grant__stat">
              <header>
                <label :for="`remote-soul-${control.key}`">
                  <span class="remote-pal-grant__stat-icon">
                    <img
                      v-if="control.image"
                      :src="`/image/player_attributes/${control.image}`"
                      alt=""
                      draggable="false"
                    >
                    <AppIcon v-else :name="control.icon" :size="15" />
                  </span>
                  {{ control.label }}
                </label>
                <output>
                  {{ form.enhancements[control.key] }}
                  ({{ soulBonusPercent(form.enhancements[control.key]) }}%)
                </output>
              </header>
              <div>
                <input
                  :id="`remote-soul-${control.key}`"
                  v-model.number="form.enhancements[control.key]"
                  type="range"
                  min="0"
                  :max="soulEnhancementMaximum"
                  :disabled="disabled"
                >
                <input
                  v-model.number="form.enhancements[control.key]"
                  type="number"
                  min="0"
                  :max="soulEnhancementMaximum"
                  :aria-label="control.label"
                  :disabled="disabled"
                >
              </div>
            </div>
          </div>
        </section>

        <section class="remote-pal-grant__section remote-pal-grant__section--condensation">
          <div class="remote-pal-grant__training-heading">
            <span><AppIcon name="crown" :size="16" /></span>
            <strong>{{ palStore.getTranslatedText('Editor_Condenser_Rank') }}</strong>
            <output>{{ form.enhancements.condensation - 1 }} / {{ condensationMaximum - 1 }}</output>
          </div>
          <div
            class="remote-pal-grant__condensation"
            role="group"
            :aria-label="palStore.getTranslatedText('Editor_Condenser_Rank')"
          >
            <template v-if="condensationMaximum <= 5">
              <button
                v-for="rank in 5"
                :key="rank"
                type="button"
                :class="{ active: form.enhancements.condensation === rank }"
                :aria-pressed="form.enhancements.condensation === rank"
                :disabled="disabled"
                @click="setCondensationRank(rank - 1)"
              >
                {{ rank - 1 }}
              </button>
            </template>
            <div v-else class="remote-pal-grant__condensation-range">
              <input
                v-model.number="form.enhancements.condensation"
                type="range"
                min="1"
                :max="condensationMaximum"
                :disabled="disabled"
              >
              <input
                v-model.number="form.enhancements.condensation"
                type="number"
                min="1"
                :max="condensationMaximum"
                :aria-label="palStore.getTranslatedText('Editor_Condenser_Rank')"
                :disabled="disabled"
              >
            </div>
          </div>
        </section>
      </div>
    </div>

    <footer class="remote-pal-grant__footer">
      <div>
        <strong>{{ selectedPalName }}</strong>
        <span>
          {{ palStore.getTranslatedText('Common_LevelWithValue', [form.level]) }}
          ·
          {{ palStore.getTranslatedText('Editor_Passive_Skills') }}
          {{ form.passiveSkills.length }} / 4
        </span>
      </div>
      <button
        class="remote-pal-grant__submit"
        :disabled="disabled || !canSubmit || !form.characterId"
      >
        <AppIcon name="plus" :size="15" />
        {{ palStore.getTranslatedText('Remote_Execute') }}
      </button>
    </footer>

    <PassivePresetDialog
      ref="passivePresetDialog"
      :options="passiveOptions"
      :disabled="disabled"
      @apply="applyPassivePreset"
      @change="passivePresets = $event"
    />
  </form>
</template>

<style scoped>
.remote-pal-grant {
  display: grid;
  grid-column: 1 / -1;
  gap: 16px;
  min-height: 190px;
  padding: 16px;
  background: oklch(0.145 0.02 252);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-md);
  box-shadow: inset 0 1px 0 oklch(1 0 0 / .03);
}

.remote-pal-grant__header,
.remote-pal-grant__section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.remote-pal-grant__header {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  padding-bottom: 13px;
  border-bottom: 1px solid var(--ui-border);
}

.remote-pal-grant__header-icon {
  display: inline-grid;
  width: 42px;
  height: 42px;
  place-items: center;
  color: var(--ui-accent);
  background: oklch(0.19 0.047 245);
  border: 1px solid oklch(0.59 0.16 240 / .35);
  border-radius: 10px;
}

.remote-pal-grant__header > div { display: grid; min-width: 0; }
.remote-pal-grant__header small {
  margin: 0 0 3px;
  color: var(--ui-accent);
  font-size: 10px;
  font-weight: 750;
  letter-spacing: .08em;
}

.remote-pal-grant h3 { margin: 0; font-size: 16px; letter-spacing: -.015em; }
.remote-pal-grant button {
  font: inherit;
  cursor: pointer;
}

.remote-pal-grant__max-all,
.remote-pal-grant__preset-button,
.remote-pal-grant__submit {
  display: inline-flex;
  min-height: 36px;
  align-items: center;
  justify-content: center;
  gap: 7px;
  padding: 0 12px;
  color: var(--ui-text-secondary);
  background: var(--ui-surface);
  border: 1px solid var(--ui-border-strong);
  border-radius: var(--ui-radius-sm);
  font-size: 11px;
  font-weight: 700;
  transition: color 160ms ease, background-color 160ms ease, border-color 160ms ease, transform 160ms ease;
}

.remote-pal-grant__max-all { color: var(--ui-accent); background: var(--ui-accent-soft); border-color: oklch(0.6 0.15 240 / .38); }
.remote-pal-grant__max-all:hover:not(:disabled),
.remote-pal-grant__preset-button:hover:not(:disabled) {
  color: var(--ui-text);
  background: var(--ui-surface-hover);
  border-color: var(--ui-accent);
}

.remote-pal-grant__max-all:active:not(:disabled),
.remote-pal-grant__preset-button:active:not(:disabled),
.remote-pal-grant__submit:active:not(:disabled) { transform: translateY(1px); }
.remote-pal-grant button:focus-visible,
.remote-pal-grant input:focus-visible { outline: 2px solid var(--ui-accent); outline-offset: 2px; }
.remote-pal-grant button:disabled,
.remote-pal-grant input:disabled { opacity: .5; cursor: not-allowed; }

.remote-pal-grant__layout {
  display: grid;
  grid-template-columns: minmax(300px, .95fr) minmax(0, 1.05fr);
  align-items: start;
  gap: 12px;
}

.remote-pal-grant__primary,
.remote-pal-grant__training { display: grid; min-width: 0; gap: 12px; }

.remote-pal-grant__identity,
.remote-pal-grant__section {
  min-width: 0;
  padding: 13px;
  background: var(--ui-surface);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
}

.remote-pal-grant__identity { display: grid; gap: 12px; }
.remote-pal-grant__pal-preview {
  display: grid;
  min-width: 0;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: 11px;
  padding: 2px 2px 10px;
  border-bottom: 1px solid var(--ui-border);
}

.remote-pal-grant__pal-preview > span {
  display: grid;
  width: 68px;
  height: 68px;
  overflow: hidden;
  place-items: center;
  color: var(--ui-text-muted);
  background: var(--ui-canvas);
  border: 1px solid var(--ui-border-strong);
  border-radius: 11px;
}

.remote-pal-grant__pal-preview img { width: 100%; height: 100%; object-fit: contain; }
.remote-pal-grant__pal-preview > div { display: grid; min-width: 0; gap: 3px; }
.remote-pal-grant__pal-preview small,
.remote-pal-grant__pal-preview strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.remote-pal-grant__pal-preview small { color: var(--ui-text-muted); font-size: 9px; }
.remote-pal-grant__pal-preview strong { color: var(--ui-text); font-size: 15px; }

.remote-pal-grant__identity :deep(.pal-species-picker) { width: 100%; }
.remote-pal-grant__level { display: grid; gap: 6px; }
.remote-pal-grant__level > label { color: var(--ui-text-muted); font-size: 10px; font-weight: 650; }
.remote-pal-grant__level > div {
  display: grid;
  grid-template-columns: 38px minmax(0, 1fr) 38px 52px;
  overflow: hidden;
  background: var(--ui-canvas);
  border: 1px solid var(--ui-border-strong);
  border-radius: var(--ui-radius-sm);
}

.remote-pal-grant__level button {
  display: grid;
  min-height: 39px;
  padding: 0;
  place-items: center;
  color: var(--ui-text-secondary);
  background: var(--ui-surface-raised);
  border: 0;
}

.remote-pal-grant__level button:first-child { border-right: 1px solid var(--ui-border); }
.remote-pal-grant__level input + button,
.remote-pal-grant__level .remote-pal-grant__level-max {
  border-left: 1px solid var(--ui-border);
}
.remote-pal-grant__level .remote-pal-grant__level-max {
  color: var(--ui-accent);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: .04em;
}
.remote-pal-grant__level button:hover:not(:disabled) { color: var(--ui-accent); background: var(--ui-surface-hover); }
.remote-pal-grant input[type="number"] {
  box-sizing: border-box;
  width: 100%;
  min-height: 38px;
  padding: 0 10px;
  color: var(--ui-text);
  background: var(--ui-canvas);
  border: 1px solid var(--ui-border-strong);
  border-radius: 6px;
  font: inherit;
  font-variant-numeric: tabular-nums;
}

.remote-pal-grant__level input[type="number"] {
  min-height: 39px;
  text-align: center;
  background: transparent;
  border: 0;
  border-radius: 0;
  font-size: 14px;
  font-weight: 750;
}

.remote-pal-grant__section {
  display: grid;
  align-content: start;
  gap: 10px;
}

.remote-pal-grant__section-heading > div {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 8px;
}

.remote-pal-grant__section-heading strong,
.remote-pal-grant__training-heading strong {
  color: var(--ui-text-secondary);
  font-size: 12px;
  letter-spacing: .01em;
}

.remote-pal-grant__section-heading small {
  color: var(--ui-text-muted);
  font-size: 9px;
  font-variant-numeric: tabular-nums;
}

.remote-pal-grant__passive-section .remote-pal-grant__section-heading {
  align-items: stretch;
  flex-direction: column;
}

.remote-pal-grant__passive-section .remote-pal-grant__section-heading > div:last-child {
  width: 100%;
}

.remote-pal-grant__passive-section :deep(.pal-skill-trigger) {
  min-width: 0;
  flex: 1 1 auto;
}

.remote-pal-grant__section-icon,
.remote-pal-grant__training-heading > span {
  display: inline-grid;
  width: 30px;
  height: 30px;
  place-items: center;
  color: var(--ui-accent);
  background: var(--ui-accent-soft);
  border-radius: 7px;
}

.remote-pal-grant__preset-button { min-height: 32px; padding-inline: 9px; font-size: 10px; }
.remote-pal-grant__presets { display: flex; flex-wrap: wrap; gap: 6px; }
.remote-pal-grant__presets button {
  min-height: 27px;
  padding: 4px 8px;
  color: var(--ui-text-secondary);
  background: var(--ui-canvas);
  border: 1px solid var(--ui-border);
  border-radius: 5px;
  font-size: 10px;
  transition: color 160ms ease, background-color 160ms ease, border-color 160ms ease;
}
.remote-pal-grant__presets button.active {
  color: var(--ui-accent);
  background: var(--ui-accent-soft);
  border-color: var(--ui-accent);
}
.remote-pal-grant__presets button:hover:not(:disabled) { color: var(--ui-text); border-color: var(--ui-border-strong); }

.remote-pal-grant__passives { display: grid; grid-template-columns: minmax(0, 1fr); gap: 7px; }
.remote-pal-grant__passives > div { position: relative; min-width: 0; }
.remote-pal-grant__passives > div > button {
  position: absolute;
  top: 7px;
  right: 6px;
  z-index: 1;
  display: grid;
  width: 25px;
  height: 25px;
  padding: 0;
  place-items: center;
  color: var(--ui-text-muted);
  background: oklch(0.14 0.018 252 / .9);
  border: 1px solid var(--ui-border);
  border-radius: 6px;
}
.remote-pal-grant__passives > div > button:hover:not(:disabled) { color: var(--ui-danger); border-color: var(--ui-danger); }
.remote-pal-grant__passives :deep(.passive-skill-banner) { padding-right: 38px; }
.remote-pal-grant__empty {
  display: flex;
  min-height: 62px;
  align-items: center;
  justify-content: center;
  gap: 7px;
  margin: 0;
  color: var(--ui-text-muted);
  background: var(--ui-canvas);
  border: 1px dashed var(--ui-border-strong);
  border-radius: 7px;
  font-size: 10px;
}

.remote-pal-grant__training-heading {
  display: grid;
  min-height: 30px;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
}

.remote-pal-grant__training-heading small,
.remote-pal-grant__training-heading output {
  color: var(--ui-text-muted);
  font-size: 9px;
  font-variant-numeric: tabular-nums;
}

.remote-pal-grant__stat-list { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 7px; }
.remote-pal-grant__stat-list--souls { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.remote-pal-grant__stat {
  display: grid;
  gap: 7px;
  padding: 9px;
  background: var(--ui-canvas);
  border: 1px solid transparent;
  border-radius: 7px;
  transition: border-color 160ms ease, background-color 160ms ease;
}

.remote-pal-grant__stat:focus-within { background: var(--ui-surface-raised); border-color: var(--ui-accent); }
.remote-pal-grant__stat > header {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.remote-pal-grant__stat label {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 6px;
  color: var(--ui-text-secondary);
  font-size: 10px;
  font-weight: 650;
}

.remote-pal-grant__stat-icon {
  display: inline-grid;
  width: 24px;
  height: 24px;
  flex: 0 0 24px;
  place-items: center;
  color: var(--ui-text-muted);
  background: var(--ui-surface-raised);
  border: 1px solid var(--ui-border);
  border-radius: 5px;
}
.remote-pal-grant__stat-icon img {
  width: 17px;
  height: 17px;
  object-fit: contain;
}
.remote-pal-grant__stat output {
  color: var(--ui-accent);
  font-size: 12px;
  font-weight: 750;
  font-variant-numeric: tabular-nums;
}

.remote-pal-grant__stat > div {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 52px;
  align-items: center;
  gap: 8px;
}

.remote-pal-grant__stat input[type="range"] {
  width: 100%;
  height: 4px;
  margin: 0;
  accent-color: var(--ui-accent);
  cursor: pointer;
}

.remote-pal-grant__stat input[type="number"] {
  min-height: 30px;
  padding: 0 6px;
  text-align: center;
  font-size: 11px;
  font-weight: 700;
}

.remote-pal-grant__section--condensation { gap: 9px; }
.remote-pal-grant__condensation {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 5px;
}

.remote-pal-grant__condensation button {
  position: relative;
  min-height: 34px;
  color: var(--ui-text-muted);
  background: var(--ui-canvas);
  border: 1px solid var(--ui-border);
  border-radius: 6px;
  font-size: 11px;
  font-weight: 750;
  font-variant-numeric: tabular-nums;
  transition: color 160ms ease, background-color 160ms ease, border-color 160ms ease, transform 160ms ease;
}

.remote-pal-grant__condensation-range {
  display: grid;
  grid-column: 1 / -1;
  grid-template-columns: minmax(0, 1fr) 64px;
  align-items: center;
  gap: 10px;
}
.remote-pal-grant__condensation-range input[type="range"] {
  width: 100%;
  height: 4px;
  margin: 0;
  accent-color: var(--ui-accent);
}
.remote-pal-grant__condensation-range input[type="number"] {
  min-height: 34px;
  padding-inline: 7px;
  text-align: center;
  font-size: 11px;
  font-weight: 700;
}

.remote-pal-grant__condensation button:hover:not(:disabled) { color: var(--ui-text); border-color: var(--ui-border-strong); }
.remote-pal-grant__condensation button.active {
  color: var(--ui-accent);
  background: var(--ui-accent-soft);
  border-color: var(--ui-accent);
  box-shadow: inset 0 -2px 0 var(--ui-accent);
}

.remote-pal-grant__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 13px;
  background: var(--ui-canvas);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
}

.remote-pal-grant__footer > div { display: grid; min-width: 0; gap: 3px; }
.remote-pal-grant__footer strong,
.remote-pal-grant__footer span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.remote-pal-grant__footer strong { color: var(--ui-text); font-size: 12px; }
.remote-pal-grant__footer span { color: var(--ui-text-muted); font-size: 9px; }
.remote-pal-grant__submit {
  min-width: 122px;
  flex: 0 0 auto;
  color: oklch(0.16 0.025 252);
  background: var(--ui-accent);
  border-color: var(--ui-accent);
}
.remote-pal-grant__submit:hover:not(:disabled) { background: var(--ui-accent-strong); border-color: var(--ui-accent-strong); }

@media (max-width: 1100px) {
  .remote-pal-grant__layout { grid-template-columns: minmax(0, 1fr); }
  .remote-pal-grant__passives { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 700px) {
  .remote-pal-grant { padding: 12px; }
  .remote-pal-grant__section-heading { align-items: stretch; flex-direction: column; }
  .remote-pal-grant__section-heading > div:last-child { justify-content: space-between; }
  .remote-pal-grant__passives,
  .remote-pal-grant__stat-list,
  .remote-pal-grant__stat-list--souls { grid-template-columns: minmax(0, 1fr); }
  .remote-pal-grant__footer { align-items: stretch; flex-direction: column; }
  .remote-pal-grant__submit { width: 100%; }
}

@media (max-width: 480px) {
  .remote-pal-grant__header { grid-template-columns: auto minmax(0, 1fr); }
  .remote-pal-grant__max-all { grid-column: 1 / -1; width: 100%; margin-top: 8px; }
  .remote-pal-grant__pal-preview > span { width: 58px; height: 58px; }
}

@media (prefers-reduced-motion: reduce) {
  .remote-pal-grant button,
  .remote-pal-grant__stat { transition: none; }
}
</style>
