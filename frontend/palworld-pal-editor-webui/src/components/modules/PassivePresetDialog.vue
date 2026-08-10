<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import AppIcon from '@/components/modules/AppIcon.vue'
import PassiveSkillCard from '@/components/modules/PassiveSkillCard.vue'
import PalSkillPicker from '@/components/modules/PalSkillPicker.vue'
import { usePalEditorStore } from '@/stores/paleditor'
import { confirmMessage } from '@/services/message-dialog'
import {
  MAX_PASSIVE_PRESET_NAME_LENGTH,
  MAX_PASSIVE_PRESET_SKILLS,
  createDefaultPassivePresets,
  loadPassivePresets,
  removePassivePreset,
  savePassivePresets,
  togglePassivePresetPinned,
  upsertPassivePreset,
} from '@/components/modules/passive-presets'

const props = defineProps({
  options: { type: Array, default: () => [] },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['apply', 'change'])
const palStore = usePalEditorStore()
const dialog = ref(null)
const addButton = ref(null)
const presets = ref([])
const editing = ref(false)
const draft = ref({ id: '', name: '', skills: [], pinned: false })
const selectedSkill = ref('')
const formError = ref('')
const storageWarning = ref('')

const tr = (key, args = []) => palStore.getTranslatedText(key, args)
const optionMap = computed(() => new Map(props.options.map((skill) => [skill.InternalName, skill])))
const availableDraftOptions = computed(() => {
  const selected = new Set(draft.value.skills)
  return props.options.filter((skill) => !selected.has(skill.InternalName))
})

const presetHasUnknownSkills = (preset) => preset.skills.some((skill) => !optionMap.value.has(skill))
const skillName = (skill) => optionMap.value.get(skill)?.I18n?.[0] || skill
const publishPresets = () => emit('change', presets.value.map((preset) => ({
  ...preset,
  skills: [...preset.skills],
})))

const makePresetId = () => {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
  return `passive-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

const load = () => {
  const defaults = createDefaultPassivePresets(
    tr,
    props.options.map((skill) => skill.InternalName),
  )
  const result = loadPassivePresets(globalThis.localStorage, defaults)
  presets.value = result.presets
  publishPresets()
  storageWarning.value = result.recovered
    ? tr('PalEditor_PassivePreset_StorageRecovered')
    : ''
}

const open = async () => {
  if (props.disabled || dialog.value?.open) return
  load()
  cancelEdit()
  dialog.value?.showModal()
  await nextTick()
  addButton.value?.focus()
}

const close = () => dialog.value?.close()
const closeFromBackdrop = (event) => {
  if (event.target === dialog.value) close()
}

const startAdd = () => {
  draft.value = { id: makePresetId(), name: '', skills: [], pinned: false }
  selectedSkill.value = ''
  formError.value = ''
  editing.value = true
}

const startEdit = (preset) => {
  draft.value = { id: preset.id, name: preset.name, skills: [...preset.skills], pinned: preset.pinned }
  selectedSkill.value = ''
  formError.value = ''
  editing.value = true
}

const cancelEdit = () => {
  editing.value = false
  draft.value = { id: '', name: '', skills: [], pinned: false }
  selectedSkill.value = ''
  formError.value = ''
}

const addDraftSkill = (skill) => {
  if (
    draft.value.skills.length >= MAX_PASSIVE_PRESET_SKILLS
    || draft.value.skills.includes(skill.InternalName)
  ) return
  draft.value.skills.push(skill.InternalName)
  selectedSkill.value = ''
}

const removeDraftSkill = (index) => {
  draft.value.skills.splice(index, 1)
}

const persist = (nextPresets) => {
  try {
    presets.value = savePassivePresets(globalThis.localStorage, nextPresets)
    publishPresets()
    storageWarning.value = ''
    return true
  } catch {
    storageWarning.value = tr('PalEditor_PassivePreset_StorageSaveFailed')
    return false
  }
}

const saveDraft = () => {
  const name = draft.value.name.trim()
  if (!name) {
    formError.value = tr('PalEditor_PassivePreset_NameRequired')
    return
  }
  const duplicate = presets.value.some((preset) => (
    preset.id !== draft.value.id
    && preset.name.trim().toLocaleLowerCase() === name.toLocaleLowerCase()
  ))
  if (duplicate) {
    formError.value = tr('PalEditor_PassivePreset_NameDuplicate')
    return
  }
  const next = upsertPassivePreset(presets.value, { ...draft.value, name })
  if (persist(next)) cancelEdit()
}

const deletePreset = async (preset) => {
  if (!await confirmMessage(
    tr('PalEditor_PassivePreset_DeleteConfirm', [preset.name]),
    { tone: 'error' },
  )) return
  if (persist(removePassivePreset(presets.value, preset.id)) && draft.value.id === preset.id) {
    cancelEdit()
  }
}

const togglePinned = (preset) => {
  persist(togglePassivePresetPinned(presets.value, preset.id))
}

const applyPreset = (preset) => {
  if (props.disabled || presetHasUnknownSkills(preset)) return
  emit('apply', [...preset.skills])
  close()
}

watch(
  () => props.options.map((skill) => skill.InternalName).join('\u0000'),
  load,
  { immediate: true },
)

defineExpose({ open })
</script>

<template>
  <Teleport to="body">
    <dialog
      ref="dialog"
      :class="['passive-preset-dialog', { 'is-editing': editing }]"
      :aria-label="tr('PalEditor_PassivePreset_Title')"
      @click="closeFromBackdrop"
      @close="cancelEdit"
    >
      <section class="passive-preset-dialog__surface">
        <header class="passive-preset-dialog__header">
          <div>
            <h2>{{ tr('PalEditor_PassivePreset_Title') }}</h2>
            <p>{{ tr('PalEditor_PassivePreset_Description') }}</p>
          </div>
          <button type="button" class="icon-button" :aria-label="tr('Common_Close')" :title="tr('Common_Close')" @click="close">
            <AppIcon name="x" :size="19" />
          </button>
        </header>

        <p v-if="storageWarning" class="passive-preset-warning" role="alert">
          <AppIcon name="warning" :size="17" />
          {{ storageWarning }}
        </p>

        <div class="passive-preset-dialog__toolbar">
          <div class="passive-preset-dialog__count">
            <strong>{{ tr('PalEditor_PassivePreset_Count', [presets.length]) }}</strong>
            <span>{{ tr('PalEditor_PassivePreset_PinnedCount', [presets.filter((preset) => preset.pinned).length]) }}</span>
          </div>
          <button ref="addButton" type="button" class="preset-button preset-button--primary" @click="startAdd">
            <AppIcon name="plus" :size="16" />
            {{ tr('PalEditor_PassivePreset_Add') }}
          </button>
        </div>

        <div class="passive-preset-dialog__body" :class="{ 'is-editing': editing }">
          <div class="passive-preset-list">
            <div v-if="!presets.length" class="passive-preset-empty">
              <AppIcon name="settings" :size="24" />
              <p>{{ tr('PalEditor_PassivePreset_Empty') }}</p>
            </div>

            <article
              v-for="preset in presets"
              :key="preset.id"
              :class="['passive-preset-row', { 'is-pinned': preset.pinned }]"
            >
              <div class="passive-preset-row__content">
                <header class="passive-preset-row__header">
                  <div class="passive-preset-row__title">
                    <strong>{{ preset.name }}</strong>
                    <span v-if="preset.pinned" class="passive-preset-pinned-badge">
                      <AppIcon name="pin" :size="12" />
                      {{ tr('PalEditor_PassivePreset_Pinned') }}
                    </span>
                  </div>
                  <div class="passive-preset-row__actions">
                    <button
                      type="button"
                      :class="['icon-button', 'icon-button--pin', { 'is-active': preset.pinned }]"
                      :aria-label="tr(preset.pinned ? 'PalEditor_PassivePreset_UnpinNamed' : 'PalEditor_PassivePreset_PinNamed', [preset.name])"
                      :title="tr(preset.pinned ? 'PalEditor_PassivePreset_Unpin' : 'PalEditor_PassivePreset_Pin')"
                      @click="togglePinned(preset)"
                    >
                      <AppIcon name="pin" :size="16" />
                    </button>
                    <button
                      type="button"
                      class="preset-button preset-button--primary"
                      :disabled="disabled || presetHasUnknownSkills(preset)"
                      :title="presetHasUnknownSkills(preset) ? tr('PalEditor_PassivePreset_Unavailable') : tr('PalEditor_PassivePreset_Apply')"
                      @click="applyPreset(preset)"
                    >
                      {{ tr('PalEditor_PassivePreset_Apply') }}
                    </button>
                    <button type="button" class="icon-button" :aria-label="tr('PalEditor_PassivePreset_EditNamed', [preset.name])" :title="tr('Common_Edit')" @click="startEdit(preset)">
                      <AppIcon name="edit" :size="16" />
                    </button>
                    <button type="button" class="icon-button icon-button--danger" :aria-label="tr('PalEditor_PassivePreset_DeleteNamed', [preset.name])" :title="tr('Common_Delete')" @click="deletePreset(preset)">
                      <AppIcon name="trash" :size="16" />
                    </button>
                  </div>
                </header>
                <div v-if="preset.skills.length" class="passive-preset-traits">
                  <PassiveSkillCard
                    v-for="skill in preset.skills"
                    :key="skill"
                    :skill="optionMap.get(skill)"
                    :internal-name="skill"
                    :fallback-description="tr('PalEditor_PassivePreset_UnknownSkill', [skill])"
                  />
                </div>
                <span v-else class="passive-preset-row__empty">{{ tr('PalEditor_PassivePreset_NoSkills') }}</span>
              </div>
            </article>
          </div>

          <form v-if="editing" class="passive-preset-editor" @submit.prevent="saveDraft">
            <header>
              <h3>{{ tr('PalEditor_PassivePreset_EditorTitle') }}</h3>
              <button type="button" class="icon-button" :aria-label="tr('Common_Close')" :title="tr('Common_Close')" @click="cancelEdit">
                <AppIcon name="x" :size="17" />
              </button>
            </header>

            <label class="passive-preset-field">
              <span>{{ tr('Common_Name') }}</span>
              <input
                v-model="draft.name"
                type="text"
                :maxlength="MAX_PASSIVE_PRESET_NAME_LENGTH"
                :placeholder="tr('PalEditor_PassivePreset_NamePlaceholder')"
                autocomplete="off"
              >
            </label>

            <div class="passive-preset-field">
              <span>{{ tr('PalEditor_PassivePreset_Skills', [draft.skills.length, MAX_PASSIVE_PRESET_SKILLS]) }}</span>
              <PalSkillPicker
                v-model="selectedSkill"
                kind="passive"
                :options="availableDraftOptions"
                :selected-option="optionMap.get(selectedSkill)"
                :disabled="draft.skills.length >= MAX_PASSIVE_PRESET_SKILLS"
                :show-internal-name="!palStore.HIDE_INVALID_OPTIONS"
                :placeholder="tr('PalEditor_PassivePreset_AddSkill')"
                :title="tr('Editor_Passive_Picker_Title')"
                :search-placeholder="tr('Editor_Passive_Search_Placeholder')"
                :results-label="tr('Editor_Passive_Results_Label')"
                :empty-text="tr('Editor_Passive_Empty')"
                :close-label="tr('Common_Close')"
                :rating-label="tr('Editor_Skill_Rating')"
                @select="addDraftSkill"
              />
            </div>

            <div class="passive-preset-editor__skills">
              <div v-for="(skill, index) in draft.skills" :key="`${skill}-${index}`" class="passive-preset-editor__skill">
                <span :class="{ 'is-unknown': !optionMap.has(skill) }">{{ skillName(skill) }}</span>
                <button type="button" class="icon-button" :aria-label="tr('Common_Remove')" :title="tr('Common_Remove')" @click="removeDraftSkill(index)">
                  <AppIcon name="x" :size="15" />
                </button>
              </div>
              <p v-if="!draft.skills.length">{{ tr('PalEditor_PassivePreset_NoSkillsHint') }}</p>
            </div>

            <p v-if="formError" class="passive-preset-form-error" role="alert">{{ formError }}</p>

            <footer>
              <button type="button" class="preset-button" @click="cancelEdit">{{ tr('Common_Cancel') }}</button>
              <button type="submit" class="preset-button preset-button--primary">{{ tr('Common_Save') }}</button>
            </footer>
          </form>
        </div>
      </section>
    </dialog>
  </Teleport>
</template>

<style scoped>
.passive-preset-dialog {
  width: min(960px, calc(100vw - 32px));
  max-width: none;
  height: fit-content;
  max-height: min(680px, calc(100dvh - 32px));
  padding: 0;
  overflow: hidden;
  color: var(--ui-text);
  background: var(--ui-surface);
  border: 1px solid var(--ui-border-strong);
  border-radius: 14px;
  box-shadow: 0 24px 72px oklch(0.04 0.02 252 / 0.55);
}

.passive-preset-dialog::backdrop { background: oklch(0.08 0.018 252 / 0.78); }
.passive-preset-dialog.is-editing { width: min(1180px, calc(100vw - 32px)); }

.passive-preset-dialog__surface {
  display: flex;
  max-height: inherit;
  flex-direction: column;
}

.passive-preset-dialog__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 20px 22px 18px;
  background: var(--ui-surface-raised);
  border-bottom: 1px solid var(--ui-border);
}

.passive-preset-dialog__header h2,
.passive-preset-editor h3 { margin: 0; color: var(--ui-text); font-size: 19px; font-weight: 720; letter-spacing: -0.015em; }
.passive-preset-dialog__header p { max-width: 62ch; margin: 5px 0 0; color: var(--ui-text-muted); font-size: 13px; line-height: 1.5; }

.passive-preset-warning {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  padding: 9px 18px;
  color: var(--ui-warning, #f6c96b);
  background: color-mix(in srgb, var(--ui-warning, #f6c96b) 10%, transparent);
  border-bottom: 1px solid var(--ui-border);
  font-size: 12px;
}

.passive-preset-dialog__toolbar {
  display: flex;
  min-height: 52px;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 16px 10px 22px;
  color: var(--ui-text-muted);
  border-bottom: 1px solid var(--ui-border);
  font-size: 12px;
}

.passive-preset-dialog__count { display: flex; align-items: baseline; gap: 9px; }
.passive-preset-dialog__count strong { color: var(--ui-text-secondary); font-size: 12px; font-weight: 650; }
.passive-preset-dialog__count span { color: var(--ui-text-muted); font-size: 11px; }

.passive-preset-dialog__body {
  display: grid;
  min-height: 0;
  max-height: calc(100dvh - 180px);
  flex: 1 1 auto;
  grid-template-columns: minmax(0, 1fr);
}

.passive-preset-dialog__body.is-editing { grid-template-columns: minmax(520px, 1.35fr) minmax(360px, 0.85fr); }

.passive-preset-list {
  display: grid;
  min-height: 0;
  align-content: start;
  gap: 10px;
  padding: 12px;
  overflow-y: auto;
}

.passive-preset-row {
  padding: 15px 16px;
  background: var(--ui-surface-raised);
  border: 1px solid var(--ui-border);
  border-radius: 10px;
  transition: border-color 180ms ease, background-color 180ms ease, transform 180ms ease;
}

.passive-preset-row:hover { background: var(--ui-surface-hover); border-color: var(--ui-border-strong); }
.passive-preset-row.is-pinned { border-color: color-mix(in srgb, var(--ui-accent) 45%, var(--ui-border)); }

.passive-preset-row__content { min-width: 0; }
.passive-preset-row__header { display: flex; min-width: 0; align-items: flex-start; justify-content: space-between; gap: 12px; }
.passive-preset-row__title { display: flex; min-width: 0; align-items: center; gap: 8px; padding-top: 6px; }
.passive-preset-row__title > strong { overflow: hidden; font-size: 14px; font-weight: 700; text-overflow: ellipsis; white-space: nowrap; }
.passive-preset-pinned-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 6px;
  color: var(--ui-accent);
  background: var(--ui-accent-soft);
  border-radius: 5px;
  font-size: 10px;
  font-weight: 700;
}
.passive-preset-traits {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px 8px;
  margin-top: 10px;
}

.passive-preset-editor__skill .is-unknown { color: var(--ui-danger); }
.passive-preset-row__empty { color: var(--ui-text-muted); font-size: 12px; }
.passive-preset-row__actions { display: flex; flex: 0 0 auto; align-items: flex-start; gap: 6px; }

.preset-button,
.icon-button {
  display: inline-flex;
  min-height: 34px;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin: 0;
  color: var(--ui-text-secondary);
  background: var(--ui-surface);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
}

.preset-button { padding: 6px 10px; font-size: 12px; font-weight: 650; }
.icon-button { width: 34px; padding: 0; }
.preset-button, .icon-button { transition: color 180ms ease, background-color 180ms ease, border-color 180ms ease, transform 120ms ease; }
.preset-button:hover:not(:disabled), .icon-button:hover:not(:disabled) { color: var(--ui-text); background: var(--ui-surface-hover); border-color: var(--ui-border-strong); }
.preset-button:active:not(:disabled), .icon-button:active:not(:disabled) { transform: translateY(1px) scale(0.98); }
.preset-button:focus-visible, .icon-button:focus-visible, .passive-preset-field input:focus-visible { outline: 2px solid var(--ui-accent); outline-offset: 2px; }
.preset-button:disabled, .icon-button:disabled { cursor: not-allowed; opacity: 0.48; }
.preset-button--primary { color: oklch(0.16 0.025 252); background: var(--ui-accent); border-color: var(--ui-accent); }
.preset-button--primary:hover:not(:disabled) { color: oklch(0.12 0.02 252); background: var(--ui-accent-strong); border-color: var(--ui-accent-strong); }
.icon-button--danger { color: var(--ui-danger); }
.icon-button--pin.is-active { color: var(--ui-accent); background: var(--ui-accent-soft); border-color: color-mix(in srgb, var(--ui-accent) 55%, var(--ui-border)); }

.passive-preset-empty {
  display: grid;
  min-height: 220px;
  place-content: center;
  justify-items: center;
  gap: 10px;
  color: var(--ui-text-muted);
  text-align: center;
}

.passive-preset-empty p { margin: 0; }

.passive-preset-editor {
  min-width: 0;
  padding: 16px;
  overflow-y: auto;
  background: var(--ui-surface-raised);
  border-left: 1px solid var(--ui-border);
}

.passive-preset-editor > header,
.passive-preset-editor > footer { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.passive-preset-editor h3 { font-size: 15px; }
.passive-preset-editor > footer { justify-content: flex-end; margin-top: 16px; }

.passive-preset-field { display: grid; gap: 7px; margin-top: 16px; color: var(--ui-text-secondary); font-size: 12px; font-weight: 650; }
.passive-preset-field input { min-height: 36px; padding: 7px 9px; color: var(--ui-text); background: var(--ui-surface-raised); border: 1px solid var(--ui-border-strong); border-radius: var(--ui-radius-sm); }
.passive-preset-field :deep(.pal-skill-trigger) { width: 100%; min-width: 0; flex: none; }

.passive-preset-editor__skills { display: grid; gap: 6px; margin-top: 10px; }
.passive-preset-editor__skills > p { margin: 4px 0; color: var(--ui-text-muted); font-size: 12px; line-height: 1.5; }
.passive-preset-editor__skill { display: flex; min-height: 36px; align-items: center; justify-content: space-between; gap: 8px; padding: 0 3px 0 9px; background: var(--ui-surface-raised); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-sm); font-size: 12px; }
.passive-preset-editor__skill .icon-button { width: 30px; min-height: 30px; }
.passive-preset-form-error { margin: 10px 0 0; color: var(--ui-danger); font-size: 12px; }

@media (max-width: 920px) {
  .passive-preset-dialog { width: calc(100vw - 20px); height: fit-content; max-height: calc(100dvh - 20px); }
  .passive-preset-dialog__body.is-editing { grid-template-columns: minmax(0, 1fr); grid-template-rows: minmax(180px, 0.7fr) minmax(300px, 1fr); }
  .passive-preset-editor { border-top: 1px solid var(--ui-border); border-left: 0; }
}

@media (max-width: 560px) {
  .passive-preset-row__header { flex-direction: column; }
  .passive-preset-row__actions { align-self: flex-end; }
}

@media (prefers-reduced-motion: reduce) {
  .preset-button, .icon-button { transition: none; }
}
</style>
