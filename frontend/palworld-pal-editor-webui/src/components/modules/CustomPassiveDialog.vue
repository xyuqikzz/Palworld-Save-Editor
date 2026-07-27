<script setup>
import { computed, nextTick, ref } from 'vue'
import AppIcon from '@/components/modules/AppIcon.vue'
import { usePalEditorStore } from '@/stores/paleditor'

defineProps({
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['add'])
const palStore = usePalEditorStore()
const dialog = ref(null)
const input = ref(null)
const internalName = ref('')
const riskAccepted = ref(false)

const tr = key => palStore.getTranslatedText(key)
const canSubmit = computed(() => (
  Boolean(internalName.value.trim())
  && internalName.value.length <= 128
  && riskAccepted.value
))

const open = async () => {
  if (dialog.value?.open) return
  internalName.value = ''
  riskAccepted.value = false
  dialog.value?.showModal()
  await nextTick()
  input.value?.focus()
}

const close = () => {
  dialog.value?.close()
}

const submit = () => {
  if (!canSubmit.value) return
  emit('add', internalName.value)
}

defineExpose({ open, close })
</script>

<template>
  <dialog
    ref="dialog"
    class="custom-passive-dialog"
    :aria-labelledby="'custom-passive-title'"
    @cancel="close"
    @click.self="close"
  >
    <form class="custom-passive-dialog__panel" @submit.prevent="submit">
      <header class="custom-passive-dialog__header">
        <div>
          <span class="custom-passive-dialog__eyebrow">
            {{ tr('PalEditor_CustomPassive_Eyebrow') }}
          </span>
          <h2 id="custom-passive-title">
            {{ tr('PalEditor_CustomPassive_Title') }}
          </h2>
        </div>
        <button
          type="button"
          class="custom-passive-dialog__close"
          :aria-label="tr('Common_Close')"
          :title="tr('Common_Close')"
          @click="close"
        >
          <AppIcon name="x" />
        </button>
      </header>

      <label class="custom-passive-dialog__field">
        <span>{{ tr('PalEditor_CustomPassive_InternalName') }}</span>
        <input
          ref="input"
          v-model="internalName"
          type="text"
          maxlength="128"
          autocomplete="off"
          spellcheck="false"
          :disabled="disabled"
          :placeholder="tr('PalEditor_CustomPassive_Placeholder')"
        >
        <small>{{ tr('PalEditor_CustomPassive_InternalNameHint') }}</small>
      </label>

      <section class="custom-passive-dialog__warning">
        <strong>{{ tr('PalEditor_CustomPassive_RiskTitle') }}</strong>
        <ul>
          <li>{{ tr('PalEditor_CustomPassive_RiskModInstalled') }}</li>
          <li>{{ tr('PalEditor_CustomPassive_RiskSemantics') }}</li>
          <li>{{ tr('PalEditor_CustomPassive_RiskWrongId') }}</li>
        </ul>
      </section>

      <label class="custom-passive-dialog__confirmation">
        <input
          v-model="riskAccepted"
          type="checkbox"
          :disabled="disabled"
        >
        <span>{{ tr('PalEditor_CustomPassive_Confirm') }}</span>
      </label>

      <footer class="custom-passive-dialog__actions">
        <button type="button" class="secondary" @click="close">
          {{ tr('Common_Cancel') }}
        </button>
        <button type="submit" class="primary" :disabled="disabled || !canSubmit">
          {{ tr('PalEditor_CustomPassive_Submit') }}
        </button>
      </footer>
    </form>
  </dialog>
</template>

<style scoped>
.custom-passive-dialog {
  width: min(620px, calc(100vw - 32px));
  max-height: calc(100vh - 32px);
  padding: 0;
  overflow: auto;
  color: var(--ui-text);
  background: var(--ui-surface);
  border: 1px solid var(--ui-border-strong);
  border-radius: var(--ui-radius-lg);
  box-shadow: var(--ui-shadow-lg);
}

.custom-passive-dialog::backdrop {
  background: rgb(3 7 18 / 70%);
  backdrop-filter: blur(3px);
}

.custom-passive-dialog__panel {
  display: grid;
  gap: 18px;
  padding: 22px;
}

.custom-passive-dialog__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.custom-passive-dialog__eyebrow {
  color: var(--ui-danger);
  font-size: 11px;
  font-weight: 750;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.custom-passive-dialog__header h2 {
  margin: 4px 0 0;
  font-size: 20px;
}

.custom-passive-dialog__close {
  display: grid;
  width: 32px;
  height: 32px;
  flex: 0 0 auto;
  place-items: center;
  margin: 0;
  padding: 0;
  color: var(--ui-text-secondary);
  background: transparent;
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
}

.custom-passive-dialog__field {
  display: grid;
  gap: 7px;
  color: var(--ui-text);
  font-size: 13px;
  font-weight: 700;
}

.custom-passive-dialog__field input {
  width: 100%;
  min-height: 40px;
  padding: 0 11px;
  color: var(--ui-text);
  background: var(--ui-surface-raised);
  border: 1px solid var(--ui-border-strong);
  border-radius: var(--ui-radius-sm);
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
}

.custom-passive-dialog__field small {
  color: var(--ui-text-muted);
  font-size: 11px;
  font-weight: 500;
  line-height: 1.45;
}

.custom-passive-dialog__warning {
  padding: 14px 16px;
  color: var(--ui-text-secondary);
  background: color-mix(in srgb, var(--ui-danger) 9%, var(--ui-surface-raised));
  border: 1px solid color-mix(in srgb, var(--ui-danger) 45%, var(--ui-border));
  border-radius: var(--ui-radius-sm);
  font-size: 12px;
  line-height: 1.5;
}

.custom-passive-dialog__warning strong {
  color: var(--ui-danger);
}

.custom-passive-dialog__warning ul {
  display: grid;
  gap: 6px;
  margin: 9px 0 0;
  padding-left: 18px;
}

.custom-passive-dialog__confirmation {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  color: var(--ui-text-secondary);
  font-size: 12px;
  line-height: 1.45;
}

.custom-passive-dialog__confirmation input {
  width: 16px;
  height: 16px;
  flex: 0 0 auto;
  margin-top: 1px;
  accent-color: var(--ui-danger);
}

.custom-passive-dialog__actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.custom-passive-dialog__actions button {
  min-height: 36px;
  margin: 0;
  padding: 0 14px;
  border-radius: var(--ui-radius-sm);
  font-size: 12px;
  font-weight: 700;
}

.custom-passive-dialog__actions .secondary {
  color: var(--ui-text-secondary);
  background: var(--ui-surface-raised);
  border: 1px solid var(--ui-border);
}

.custom-passive-dialog__actions .primary {
  color: #fff;
  background: var(--ui-danger);
  border: 1px solid var(--ui-danger);
}

.custom-passive-dialog__actions .primary:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}
</style>
