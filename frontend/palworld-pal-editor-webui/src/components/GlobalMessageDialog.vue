<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { usePalEditorStore } from '@/stores/paleditor'
import { useMessageDialogHost } from '@/services/message-dialog'
import AppIcon from './modules/AppIcon.vue'

const palStore = usePalEditorStore()
const { state, attachHost, settle } = useMessageDialogHost()
const dialogElement = ref(null)
const inputElement = ref(null)
const inputValue = ref('')
let detachHost = null
let returnFocus = null
let pendingReturnFocus = null

const request = computed(() => state.current)
const titleKeys = Object.freeze({
  error: 'MessageDialog_ErrorTitle',
  info: 'MessageDialog_InfoTitle',
  success: 'MessageDialog_SuccessTitle',
  warning: 'MessageDialog_WarningTitle',
})
const iconNames = Object.freeze({
  error: 'error',
  info: 'info',
  success: 'success',
  warning: 'warning',
})

const title = computed(() => {
  if (request.value?.title) return request.value.title
  if (request.value?.mode === 'confirm') {
    return palStore.getTranslatedText('MessageDialog_ConfirmTitle')
  }
  if (request.value?.mode === 'prompt') {
    return palStore.getTranslatedText('MessageDialog_InputTitle')
  }
  return palStore.getTranslatedText(titleKeys[request.value?.tone] || titleKeys.info)
})
const iconName = computed(() => iconNames[request.value?.tone] || iconNames.info)
const dialogRole = computed(() => (
  request.value?.mode === 'confirm' || ['error', 'warning'].includes(request.value?.tone)
    ? 'alertdialog'
    : 'dialog'
))
const canDismiss = computed(() => request.value?.dismissible === true)
const confirmLabel = computed(() => request.value?.confirmLabel || palStore.getTranslatedText(
  request.value?.mode === 'alert'
    ? 'MessageDialog_Acknowledge'
    : 'MessageDialog_ConfirmAction',
))
const cancelLabel = computed(() => request.value?.cancelLabel || palStore.getTranslatedText(
  'MessageDialog_CancelAction',
))

function dismissResult() {
  if (request.value?.mode === 'confirm') return false
  if (request.value?.mode === 'prompt') return null
  return undefined
}

function dismiss() {
  if (canDismiss.value) settle(dismissResult())
}

function confirm() {
  if (request.value?.mode === 'prompt') {
    settle(inputValue.value)
    return
  }
  settle(request.value?.mode === 'confirm' ? true : undefined)
}

function cancel() {
  settle(dismissResult())
}

function restoreFocus() {
  const focusTarget = pendingReturnFocus
  pendingReturnFocus = null
  if (focusTarget instanceof HTMLElement) focusTarget.focus()
}

function trapFocus(event) {
  if (event.key === 'Escape') {
    event.preventDefault()
    dismiss()
    return
  }
  if (event.key !== 'Tab' || !dialogElement.value) return

  const focusable = Array.from(dialogElement.value.querySelectorAll(
    'button:not(:disabled), input:not(:disabled), summary, [tabindex]:not([tabindex="-1"])',
  ))
  if (!focusable.length) return
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

watch(
  () => request.value?.id,
  async (id, previousId) => {
    if (id && !previousId) returnFocus = document.activeElement
    if (!id) {
      pendingReturnFocus = returnFocus
      returnFocus = null
      return
    }

    inputValue.value = request.value.defaultValue
    await nextTick()
    if (request.value.mode === 'prompt') inputElement.value?.focus()
    else dialogElement.value?.querySelector('.message-dialog__primary')?.focus()
  },
)

onMounted(() => { detachHost = attachHost() })
onBeforeUnmount(() => detachHost?.())
</script>

<template>
  <Teleport to="body">
    <Transition name="message-dialog-fade" @after-leave="restoreFocus">
      <div
        v-if="request"
        class="message-dialog-overlay"
        @click.self="dismiss"
      >
        <section
          ref="dialogElement"
          class="message-dialog"
          :class="`message-dialog--${request.tone}`"
          :role="dialogRole"
          aria-modal="true"
          aria-labelledby="global-message-dialog-title"
          aria-describedby="global-message-dialog-message"
          @keydown="trapFocus"
        >
          <header class="message-dialog__header">
            <span class="message-dialog__icon" aria-hidden="true">
              <AppIcon :name="iconName" :size="22" />
            </span>
            <h2 id="global-message-dialog-title">{{ title }}</h2>
            <button
              v-if="canDismiss"
              type="button"
              class="message-dialog__close"
              :aria-label="palStore.getTranslatedText('Common_Close')"
              @click="cancel"
            >
              <AppIcon name="x" :size="17" />
            </button>
          </header>

          <div class="message-dialog__body">
            <p id="global-message-dialog-message">{{ request.message }}</p>
            <label v-if="request.mode === 'prompt'" class="message-dialog__input-field">
              <span v-if="request.inputLabel">{{ request.inputLabel }}</span>
              <input
                ref="inputElement"
                v-model="inputValue"
                type="text"
                :aria-label="request.inputLabel || request.message"
                @keydown.enter.prevent="confirm"
              />
            </label>
            <details v-if="request.details" class="message-dialog__details">
              <summary>{{ palStore.getTranslatedText('MessageDialog_Details') }}</summary>
              <pre>{{ request.details }}</pre>
            </details>
          </div>

          <footer class="message-dialog__actions">
            <button
              v-if="request.mode !== 'alert'"
              type="button"
              class="message-dialog__button message-dialog__button--secondary"
              @click="cancel"
            >
              {{ cancelLabel }}
            </button>
            <button
              type="button"
              class="message-dialog__button message-dialog__button--primary message-dialog__primary"
              @click="confirm"
            >
              {{ confirmLabel }}
            </button>
          </footer>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.message-dialog-overlay {
  position: fixed;
  inset: 0;
  z-index: 1600;
  display: grid;
  place-items: center;
  padding: 20px;
  background: oklch(0.1 0.018 252 / 0.74);
}

.message-dialog {
  width: min(520px, 100%);
  max-height: min(680px, calc(100dvh - 40px));
  overflow: hidden;
  color: var(--ui-text);
  background: var(--ui-surface);
  border: 1px solid var(--ui-border-strong);
  border-radius: 14px;
}

.message-dialog__header {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  min-height: 62px;
  padding: 15px 18px;
  border-bottom: 1px solid var(--ui-border);
}

.message-dialog__header h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 650;
  line-height: 1.3;
}

.message-dialog__icon {
  display: grid;
  width: 36px;
  height: 36px;
  place-items: center;
  color: var(--ui-accent);
  background: var(--ui-accent-soft);
  border-radius: 10px;
}

.message-dialog--success .message-dialog__icon {
  color: var(--ui-success);
  background: oklch(0.25 0.045 158);
}

.message-dialog--warning .message-dialog__icon {
  color: oklch(0.8 0.14 78);
  background: oklch(0.27 0.055 78);
}

.message-dialog--error .message-dialog__icon {
  color: var(--ui-danger);
  background: var(--ui-danger-soft);
}

.message-dialog__close {
  display: grid;
  width: 34px;
  height: 34px;
  padding: 0;
  place-items: center;
  color: var(--ui-text-muted);
  background: transparent;
  border: 0;
  border-radius: var(--ui-radius-sm);
}

.message-dialog__close:hover {
  color: var(--ui-text);
  background: var(--ui-surface-raised);
}

.message-dialog__body {
  max-height: calc(100dvh - 210px);
  padding: 20px 20px 8px;
  overflow-y: auto;
}

.message-dialog__body p {
  margin: 0;
  color: var(--ui-text-secondary);
  font-size: 14px;
  line-height: 1.65;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.message-dialog__input-field {
  display: grid;
  gap: 7px;
  margin-top: 16px;
  color: var(--ui-text-secondary);
  font-size: 12px;
}

.message-dialog__input-field input {
  width: 100%;
  min-height: 40px;
  padding: 8px 10px;
  color: var(--ui-text);
  background: var(--ui-surface-raised);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
  outline: 0;
}

.message-dialog__input-field input:focus {
  border-color: var(--ui-accent);
  box-shadow: 0 0 0 3px oklch(0.72 0.14 246 / 0.16);
}

.message-dialog__details {
  margin-top: 16px;
  color: var(--ui-text-muted);
  font-size: 12px;
}

.message-dialog__details summary {
  width: fit-content;
  cursor: pointer;
  user-select: none;
}

.message-dialog__details pre {
  max-height: 180px;
  margin: 9px 0 0;
  padding: 10px;
  overflow: auto;
  color: var(--ui-text-secondary);
  background: var(--ui-canvas);
  border-radius: var(--ui-radius-sm);
  font-family: Consolas, "Cascadia Mono", monospace;
  font-size: 11.5px;
  line-height: 1.5;
  white-space: pre-wrap;
}

.message-dialog__actions {
  display: flex;
  justify-content: flex-end;
  gap: 9px;
  padding: 16px 20px 20px;
}

.message-dialog__button {
  min-width: 92px;
  min-height: 38px;
  padding: 7px 16px;
  border-radius: var(--ui-radius-sm);
  font-weight: 600;
}

.message-dialog__button--secondary {
  color: var(--ui-text-secondary);
  background: var(--ui-surface-raised);
  border: 1px solid var(--ui-border);
}

.message-dialog__button--secondary:hover {
  color: var(--ui-text);
  border-color: var(--ui-border-strong);
}

.message-dialog__button--primary {
  color: oklch(0.18 0.03 252);
  background: var(--ui-accent);
  border: 1px solid var(--ui-accent);
}

.message-dialog--error .message-dialog__button--primary {
  color: white;
  background: var(--ui-danger);
  border-color: var(--ui-danger);
}

.message-dialog-fade-enter-active,
.message-dialog-fade-leave-active {
  transition: opacity 180ms cubic-bezier(0.16, 1, 0.3, 1);
}

.message-dialog-fade-enter-active .message-dialog,
.message-dialog-fade-leave-active .message-dialog {
  transition: opacity 180ms cubic-bezier(0.16, 1, 0.3, 1), transform 180ms cubic-bezier(0.16, 1, 0.3, 1);
}

.message-dialog-fade-enter-from,
.message-dialog-fade-leave-to,
.message-dialog-fade-enter-from .message-dialog,
.message-dialog-fade-leave-to .message-dialog {
  opacity: 0;
}

.message-dialog-fade-enter-from .message-dialog,
.message-dialog-fade-leave-to .message-dialog {
  transform: translateY(8px) scale(0.985);
}

@media (max-width: 540px) {
  .message-dialog-overlay { padding: 12px; }
  .message-dialog { max-height: calc(100dvh - 24px); }
  .message-dialog__header { padding: 13px 14px; }
  .message-dialog__body { padding: 17px 16px 6px; }
  .message-dialog__actions { padding: 14px 16px 16px; }
  .message-dialog__button { flex: 1; min-width: 0; }
}

@media (prefers-reduced-motion: reduce) {
  .message-dialog-fade-enter-active,
  .message-dialog-fade-leave-active,
  .message-dialog-fade-enter-active .message-dialog,
  .message-dialog-fade-leave-active .message-dialog {
    transition-duration: 0.01ms;
  }
}
</style>
