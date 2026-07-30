import test from 'node:test'
import assert from 'node:assert/strict'

import axios from 'axios'
import { createPinia, setActivePinia } from 'pinia'

globalThis.alert = () => {}
globalThis.confirm = () => true
globalThis.window = { confirm: () => true }
globalThis.localStorage = {
  getItem: () => null,
  setItem: () => {},
}

const { usePalEditorStore } = await import('../src/stores/paleditor.js')

function makeLoadedDirtyStore({ platform = 'steam', pendingChanges = 2 } = {}) {
  setActivePinia(createPinia())
  const store = usePalEditorStore()
  store.SAVE_LOADED_FLAG = true
  store.SAVE_PLATFORM = platform
  store.SESSION_ID = 'session-1'
  store.SESSION_REVISION = 7
  store.PENDING_CHANGE_COUNT = pendingChanges
  store.PAL_WRITE_BACK_PATH = 'D:/synthetic-save'
  return store
}

test('Steam save keeps WritePath and revision behavior and releases loading on success', async () => {
  const store = makeLoadedDirtyStore()
  const alerts = []
  const previousAlert = globalThis.alert
  let request
  globalThis.alert = message => alerts.push(message)
  axios.post = async (url, data) => {
    request = { url, data: structuredClone(data) }
    return {
      data: {
        status: 0,
        data: {
          revision: 7,
          backup_path: 'D:/backup',
          written_files: ['Level.sav'],
        },
      },
    }
  }

  try {
    const saved = await store.writeSave()

    assert.equal(saved, true)
    assert.deepEqual(request, {
      url: '/api/save/save',
      data: {
        WritePath: 'D:/synthetic-save',
        session_id: 'session-1',
        expected_revision: 7,
      },
    })
    assert.equal(store.SESSION_REVISION, 7)
    assert.equal(store.PENDING_CHANGE_COUNT, 0)
    assert.equal(store.LOADING_FLAG, false)
    assert.deepEqual(alerts, [
      'Changes successfully saved to D:/synthetic-save.',
    ])
  } finally {
    globalThis.alert = previousAlert
  }
})

test('WGS save writes back to the original slot and releases loading on success', async () => {
  const store = makeLoadedDirtyStore({ platform: 'xgp' })
  const alerts = []
  const confirmations = []
  const previousAlert = globalThis.alert
  const previousConfirm = window.confirm
  let request
  globalThis.alert = message => alerts.push(message)
  window.confirm = message => {
    confirmations.push(message)
    return true
  }
  axios.post = async (url, data) => {
    request = { url, data: structuredClone(data) }
    return {
      data: {
        status: 0,
        data: {
          revision: 8,
          backup_path: 'D:/wgs-backup',
          written_files: ['container.12'],
        },
      },
    }
  }

  try {
    const saved = await store.writeSave()

    assert.equal(saved, true)
    assert.deepEqual(request, {
      url: '/api/save/save',
      data: {
        session_id: 'session-1',
        expected_revision: 7,
      },
    })
    assert.equal(confirmations.length, 1)
    assert.equal(store.SESSION_REVISION, 8)
    assert.equal(store.PENDING_CHANGE_COUNT, 0)
    assert.equal(store.LOADING_FLAG, false)
    assert.deepEqual(alerts, [
      'Local Game Pass save completed. Verified backup: D:/wgs-backup. Xbox cloud sync is not verified.',
    ])
  } finally {
    globalThis.alert = previousAlert
    window.confirm = previousConfirm
  }
})

test('WGS save cancellation preserves pending changes and releases its loading state', async () => {
  const store = makeLoadedDirtyStore({ platform: 'xgp' })
  const previousConfirm = window.confirm
  let requestCount = 0
  window.confirm = () => false
  axios.post = async () => {
    requestCount += 1
    throw new Error('save request must not be sent after cancellation')
  }

  try {
    const saved = await store.writeSave()

    assert.equal(saved, false)
    assert.equal(requestCount, 0)
    assert.equal(store.PENDING_CHANGE_COUNT, 2)
    assert.equal(store.LOADING_FLAG, false)
  } finally {
    window.confirm = previousConfirm
  }
})

test('repairable missing guild handles prompt, repair, and retry the save', async () => {
  const store = makeLoadedDirtyStore()
  const previousConfirm = window.confirm
  const confirmations = []
  const requests = []
  let saveAttempts = 0
  window.confirm = message => {
    confirmations.push(message)
    return true
  }
  axios.post = async (url, data) => {
    requests.push({ url, data: structuredClone(data) })
    if (url === '/api/save/repair-character-references') {
      return {
        data: {
          status: 0,
          data: {
            revision: 8,
            repair: {
              kind: 'missing_guild_handles',
              repair_count: 1,
              guild_count: 1,
              remaining_hard_issue_count: 0,
            },
            saveCapabilities: {
              writeBack: true,
              exportSteamCopy: true,
            },
          },
        },
      }
    }
    assert.equal(url, '/api/save/save')
    saveAttempts += 1
    if (saveAttempts === 1) {
      return {
        data: {
          status: 1,
          msg: 'Character records and their references are inconsistent.',
          error: {
            code: 'CHARACTER_INDEX_INVARIANT_FAILED',
            details: {
              repair: {
                available: true,
                kind: 'missing_guild_handles',
                repair_count: 1,
                guild_count: 1,
              },
            },
            retryable: true,
          },
        },
      }
    }
    return {
      data: {
        status: 0,
        data: {
          revision: 8,
          backup_path: 'D:/verified-backup',
          written_files: ['Level.sav'],
        },
      },
    }
  }

  try {
    assert.equal(await store.writeSave(), true)
    assert.equal(confirmations.length, 1)
    assert.match(confirmations[0], /Saving failed/i)
    assert.match(confirmations[0], /1 Pal record/i)
    assert.match(confirmations[0], /complete backup/i)
    assert.deepEqual(requests, [
      {
        url: '/api/save/save',
        data: {
          WritePath: 'D:/synthetic-save',
          session_id: 'session-1',
          expected_revision: 7,
        },
      },
      {
        url: '/api/save/repair-character-references',
        data: {
          session_id: 'session-1',
          expected_revision: 7,
        },
      },
      {
        url: '/api/save/save',
        data: {
          WritePath: 'D:/synthetic-save',
          session_id: 'session-1',
          expected_revision: 8,
        },
      },
    ])
    assert.equal(store.SESSION_REVISION, 8)
    assert.equal(store.PENDING_CHANGE_COUNT, 0)
    assert.equal(store.LAST_ERROR, null)
    assert.equal(store.LOADING_FLAG, false)
  } finally {
    window.confirm = previousConfirm
  }
})

test('a backup failure after character reference repair keeps the repair pending', async () => {
  const store = makeLoadedDirtyStore()
  const previousConfirm = window.confirm
  let saveAttempts = 0
  window.confirm = () => true
  axios.post = async url => {
    if (url === '/api/save/repair-character-references') {
      return {
        data: {
          status: 0,
          data: {
            revision: 8,
            repair: {
              kind: 'missing_guild_handles',
              repair_count: 1,
              guild_count: 1,
              remaining_hard_issue_count: 0,
            },
          },
        },
      }
    }
    assert.equal(url, '/api/save/save')
    saveAttempts += 1
    if (saveAttempts === 1) {
      return {
        data: {
          status: 1,
          msg: 'repairable character references',
          error: {
            code: 'CHARACTER_INDEX_INVARIANT_FAILED',
            details: {
              repair: {
                available: true,
                kind: 'missing_guild_handles',
                repair_count: 1,
              },
            },
            retryable: true,
          },
        },
      }
    }
    return {
      data: {
        status: 1,
        msg: 'backup failed',
        error: {
          code: 'BACKUP_FAILED',
          details: {
            phase: 'copy_file',
            failed_file: 'Level.sav',
            os_error_category: 'disk_space',
          },
          retryable: true,
        },
      },
    }
  }

  try {
    assert.equal(await store.writeSave(), false)
    assert.equal(saveAttempts, 2)
    assert.equal(store.SESSION_REVISION, 8)
    assert.equal(store.PENDING_CHANGE_COUNT, 3)
    assert.equal(store.LAST_ERROR.code, 'BACKUP_FAILED')
    assert.equal(store.LAST_ERROR.details.failed_file, 'Level.sav')
    assert.equal(store.LOADING_FLAG, false)
  } finally {
    window.confirm = previousConfirm
  }
})

test('declining character reference repair preserves the failed save state', async () => {
  const store = makeLoadedDirtyStore()
  const previousConfirm = window.confirm
  let requestCount = 0
  window.confirm = () => false
  axios.post = async url => {
    requestCount += 1
    assert.equal(url, '/api/save/save')
    return {
      data: {
        status: 1,
        msg: 'generic backend message',
        error: {
          code: 'CHARACTER_INDEX_INVARIANT_FAILED',
          details: {
            repair: {
              available: true,
              kind: 'missing_guild_handles',
              repair_count: 1,
              guild_count: 1,
            },
          },
          retryable: true,
        },
      },
    }
  }

  try {
    assert.equal(await store.writeSave(), false)
    assert.equal(requestCount, 1)
    assert.equal(store.LAST_ERROR.code, 'CHARACTER_INDEX_INVARIANT_FAILED')
    assert.match(store.LAST_ERROR.message, /not written/i)
    assert.equal(store.SESSION_REVISION, 7)
    assert.equal(store.PENDING_CHANGE_COUNT, 2)
    assert.equal(store.LOADING_FLAG, false)
  } finally {
    window.confirm = previousConfirm
  }
})

test('unsafe character reference failures never offer automatic repair', async () => {
  const store = makeLoadedDirtyStore()
  const previousConfirm = window.confirm
  let confirmationCount = 0
  window.confirm = () => {
    confirmationCount += 1
    return true
  }
  axios.post = async url => {
    assert.equal(url, '/api/save/save')
    return {
      data: {
        status: 1,
        msg: 'unsafe character references',
        error: {
          code: 'CHARACTER_INDEX_INVARIANT_FAILED',
          details: {
            repair: {
              available: false,
              kind: 'missing_guild_handles',
              repair_count: 0,
            },
          },
          retryable: false,
        },
      },
    }
  }

  try {
    assert.equal(await store.writeSave(), false)
    assert.equal(confirmationCount, 0)
    assert.equal(store.LAST_ERROR.code, 'CHARACTER_INDEX_INVARIANT_FAILED')
    assert.equal(store.PENDING_CHANGE_COUNT, 2)
  } finally {
    window.confirm = previousConfirm
  }
})

for (const { platform, code } of [
  { platform: 'steam', code: 'BACKUP_FAILED' },
  { platform: 'xgp', code: 'WGS_BACKUP_FAILED' },
]) {
  test(`${code} preserves pending changes and releases the save loading state`, async () => {
    const store = makeLoadedDirtyStore({ platform })
    axios.post = async url => {
      assert.equal(url, '/api/save/save')
      return {
        data: {
          status: 1,
          msg: `${code} message`,
          error: {
            code,
            details: {
              backup_path: 'D:/failed-backup',
              phase: 'copy_file',
              failed_file: 'Level.sav',
              os_error_code: 28,
              os_error_category: 'disk_space',
              retryable: true,
            },
            retryable: true,
          },
        },
      }
    }

    const saved = await store.writeSave()

    assert.equal(saved, false)
    assert.equal(store.LAST_ERROR.code, code)
    assert.equal(store.LAST_ERROR.details.phase, 'copy_file')
    assert.equal(store.LAST_ERROR.details.failed_file, 'Level.sav')
    assert.equal(store.LAST_ERROR.details.os_error_category, 'disk_space')
    assert.match(store.LAST_ERROR.action, /disk space/i)
    assert.equal(store.PENDING_CHANGE_COUNT, 2)
    assert.equal(store.LOADING_FLAG, false)
  })
}

for (const { platform, code, messagePattern, actionPattern } of [
  {
    platform: 'xgp',
    code: 'WGS_GAME_RUNNING',
    messagePattern: /Close Palworld completely/i,
    actionPattern: /cloud synchronization/i,
  },
  {
    platform: 'xgp',
    code: 'WGS_SOURCE_CHANGED',
    messagePattern: /Game Pass source changed/i,
    actionPattern: /Reload the save source/i,
  },
  {
    platform: 'steam',
    code: 'SAVE_TARGET_CHANGED',
    messagePattern: /Steam save source changed/i,
    actionPattern: /Reload the save source/i,
  },
]) {
  test(`${code} remains distinct from backup failure`, async () => {
    const store = makeLoadedDirtyStore({ platform })
    axios.post = async () => ({
      data: {
        status: 1,
        msg: 'generic backend failure',
        error: { code, details: {}, retryable: true },
      },
    })

    assert.equal(await store.writeSave(), false)
    assert.equal(store.LAST_ERROR.code, code)
    assert.match(store.LAST_ERROR.message, messagePattern)
    assert.match(store.LAST_ERROR.action, actionPattern)
    assert.doesNotMatch(store.LAST_ERROR.message, /backup failed/i)
  })
}

test('save releases its loading state and preserves pending changes when the backend does not respond', async () => {
  const store = makeLoadedDirtyStore()
  axios.post = async url => {
    assert.equal(url, '/api/save/save')
    const error = new Error('Network Error')
    error.request = { readyState: 4 }
    throw error
  }

  const saved = await store.writeSave()

  assert.equal(saved, false)
  assert.equal(store.LAST_ERROR.code, 'NETWORK_NO_RESPONSE')
  assert.match(store.LAST_ERROR.message, /did not respond/i)
  assert.match(store.LAST_ERROR.action, /backend is running/i)
  assert.notEqual(store.LAST_ERROR.code, 'BACKUP_FAILED')
  assert.equal(store.PENDING_CHANGE_COUNT, 2)
  assert.equal(store.LOADING_FLAG, false)
})

test('save releases its loading state and preserves pending changes after a JavaScript exception', async () => {
  const store = makeLoadedDirtyStore()
  axios.post = async url => {
    assert.equal(url, '/api/save/save')
    throw new TypeError('unexpected client failure')
  }

  const saved = await store.writeSave()

  assert.equal(saved, false)
  assert.equal(store.LAST_ERROR.code, 'CLIENT_REQUEST_FAILED')
  assert.match(store.LAST_ERROR.message, /could not be sent/i)
  assert.equal(store.PENDING_CHANGE_COUNT, 2)
  assert.equal(store.LOADING_FLAG, false)
})

test('save does not clear a loading state owned by another operation', async () => {
  const store = makeLoadedDirtyStore()
  store.LOADING_FLAG = true
  axios.post = async url => {
    assert.equal(url, '/api/save/save')
    const error = new Error('Network Error')
    error.request = { readyState: 4 }
    throw error
  }

  const saved = await store.writeSave()

  assert.equal(saved, false)
  assert.equal(store.PENDING_CHANGE_COUNT, 2)
  assert.equal(store.LOADING_FLAG, true)
})
