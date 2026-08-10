import { reactive, readonly } from 'vue'

const neutralResult = mode => {
  if (mode === 'confirm') return false
  if (mode === 'prompt') return null
  return undefined
}

function normalizeRequest(mode, messageOrOptions, options = {}) {
  const request = typeof messageOrOptions === 'string'
    ? { message: messageOrOptions, ...options }
    : { ...(messageOrOptions || {}), ...options }

  return {
    mode,
    tone: request.tone || (mode === 'confirm' ? 'warning' : 'info'),
    title: request.title || '',
    message: request.message || '',
    details: request.details || '',
    confirmLabel: request.confirmLabel || '',
    cancelLabel: request.cancelLabel || '',
    inputLabel: request.inputLabel || '',
    defaultValue: request.defaultValue || '',
    dismissible: request.dismissible ?? mode === 'alert',
  }
}

function nativeDialogMethod(name) {
  const browserWindow = globalThis.window
  if (browserWindow && typeof browserWindow[name] === 'function') {
    return browserWindow[name].bind(browserWindow)
  }
  if (typeof globalThis[name] === 'function') return globalThis[name].bind(globalThis)
  return null
}

export function createMessageDialogController() {
  const mutableState = reactive({ current: null })
  const state = readonly(mutableState)
  const queue = []
  let hostCount = 0
  let nextId = 1

  function fallback(request) {
    const message = request.details
      ? `${request.message}\n\n${request.details}`
      : request.message

    if (request.mode === 'confirm') {
      return Boolean(nativeDialogMethod('confirm')?.(message))
    }
    if (request.mode === 'prompt') {
      return nativeDialogMethod('prompt')?.(message, request.defaultValue) ?? null
    }
    nativeDialogMethod('alert')?.(message)
    return undefined
  }

  function pump() {
    if (!mutableState.current && queue.length) {
      mutableState.current = queue.shift()
    }
  }

  function request(mode, messageOrOptions, options) {
    const normalized = normalizeRequest(mode, messageOrOptions, options)
    if (!hostCount) return Promise.resolve(fallback(normalized))

    return new Promise(resolve => {
      queue.push({
        ...normalized,
        id: nextId++,
        resolve,
      })
      pump()
    })
  }

  function settle(value) {
    const current = mutableState.current
    if (!current) return
    mutableState.current = null
    current.resolve(value)
    pump()
  }

  function attachHost() {
    hostCount += 1
    pump()
    let attached = true

    return () => {
      if (!attached) return
      attached = false
      hostCount = Math.max(0, hostCount - 1)
      if (hostCount) return

      if (mutableState.current) {
        const current = mutableState.current
        mutableState.current = null
        current.resolve(neutralResult(current.mode))
      }
      while (queue.length) {
        const pending = queue.shift()
        pending.resolve(neutralResult(pending.mode))
      }
    }
  }

  return {
    state,
    showMessage: (messageOrOptions, options) => request('alert', messageOrOptions, options),
    confirmMessage: (messageOrOptions, options) => request('confirm', messageOrOptions, options),
    promptMessage: (messageOrOptions, options) => request('prompt', messageOrOptions, options),
    attachHost,
    settle,
  }
}

const controller = createMessageDialogController()

export const showMessage = controller.showMessage
export const confirmMessage = controller.confirmMessage
export const promptMessage = controller.promptMessage

export function useMessageDialogHost() {
  return {
    state: controller.state,
    attachHost: controller.attachHost,
    settle: controller.settle,
  }
}
