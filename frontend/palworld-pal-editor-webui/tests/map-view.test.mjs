import assert from 'node:assert/strict'
import { existsSync, readFileSync, statSync } from 'node:fs'
import test from 'node:test'
import { fileURLToPath } from 'node:url'
import axios from 'axios'
import { createPinia, setActivePinia } from 'pinia'

globalThis.alert = () => {}
globalThis.window = { confirm: () => true }
globalThis.localStorage = {
  getItem: () => null,
  setItem: () => {},
  removeItem: () => {},
}

const { usePalEditorStore } = await import('../src/stores/paleditor.js')
const sourcePath = relativePath => fileURLToPath(
  new URL(`../src/${relativePath}`, import.meta.url),
)
const publicPath = relativePath => fileURLToPath(
  new URL(`../public/${relativePath}`, import.meta.url),
)

test('map is a loaded-save route backed by the packaged PSP WebP maps', () => {
  const router = readFileSync(sourcePath('router/index.js'), 'utf8')
  const topBar = readFileSync(sourcePath('components/TopBar.vue'), 'utf8')
  const overview = readFileSync(sourcePath('views/OverviewView.vue'), 'utf8')
  const view = readFileSync(sourcePath('views/MapView.vue'), 'utf8')
  const mapImages = [
    publicPath('map/psp/t_worldmap.webp'),
    publicPath('map/psp/t_treemap.webp'),
  ]

  assert.match(router, /path:\s*['"]\/map['"][\s\S]*?name:\s*['"]Map['"][\s\S]*?requiresSession:\s*true/)
  assert.match(topBar, /@click="navigate\('Map'\)"[\s\S]*?TopBar_Page_Map/)
  assert.match(overview, /@click="navigate\('Map'\)"[\s\S]*?TopBar_Page_Map/)
  assert.equal(mapImages.every(existsSync), true)
  assert.equal(
    mapImages.every(path => (
      readFileSync(path, { encoding: null }).subarray(8, 12).toString() === 'WEBP'
    )),
    true,
  )
  assert.ok(statSync(mapImages[0]).size < 3_000_000)
  assert.ok(statSync(mapImages[1]).size < 4_000_000)
  assert.match(view, /location_source|Map_SaveSnapshot/)
  assert.match(view, /showFastTravel|showPlayers|showBases/)
  assert.doesNotMatch(view, /showBossTowers|bossTower|boss-tower|Map_ShowBossTowers/)
  assert.match(view, /x:\s*\(\(y - current\.min_y\)/)
  assert.match(view, /y:\s*\(\(current\.max_x - x\)/)
  assert.doesNotMatch(view, /label:\s*base\.name/)
  assert.doesNotMatch(view, /\bonline\b/i)
})

test('base marker details can open the matching base Pal editor', () => {
  const router = readFileSync(sourcePath('router/index.js'), 'utf8')
  const view = readFileSync(sourcePath('views/MapView.vue'), 'utf8')

  assert.match(router, /path:\s*['"]\/editor\/base\/:baseKey['"][\s\S]*?name:\s*['"]BaseEditor['"]/)
  assert.match(
    view,
    /function openSelectedBase\(\)[\s\S]*?name:\s*'BaseEditor'[\s\S]*?baseKey:\s*`base:\$\{selectedMarker\.value\.base_id\}`/,
  )
  assert.match(
    view,
    /v-else-if="selectedMarker\.kind === 'base'"[\s\S]*?@click="openSelectedBase"[\s\S]*?Map_OpenBasePals/,
  )
})

test('zoomed map uses native 8192 WebP images and PSP marker assets', () => {
  const view = readFileSync(sourcePath('views/MapView.vue'), 'utf8')
  const markerAssets = [
    't_icon_compass_11.webp',
    't_icon_compass_camp.webp',
    't_icon_compass_fttower.webp',
  ]

  assert.equal(existsSync(publicPath('map/tiles')), false)
  assert.equal(markerAssets.every(name => existsSync(publicPath(`map/psp/${name}`))), true)
  assert.equal(existsSync(publicPath('map/psp/t_icon_compass_tower.webp')), false)
  assert.match(
    view,
    /const MAX_ZOOM = 6 \+ Math\.log\(1\.5\) \/ Math\.log\(ZOOM_FACTOR\)/,
  )
  assert.match(view, /const IMAGE_SIZE = 8192/)
  assert.match(view, /const MAX_NATIVE_SCALE = 1/)
  assert.match(view, /\.map-stage\s*\{[\s\S]*?width:\s*8192px;[\s\S]*?height:\s*8192px;/)
  assert.match(view, /\.map-image\s*\{[\s\S]*?width:\s*8192px;[\s\S]*?height:\s*8192px;/)
  assert.match(view, /MainMap:[\s\S]*?t_worldmap\.webp/)
  assert.match(view, /Tree:[\s\S]*?t_treemap\.webp/)
  assert.match(view, /MARKER_IMAGES[\s\S]*?t_icon_compass_11\.webp/)
  assert.match(view, /class="map-image"[\s\S]*?:src="activeMapConfig\.imageUrl"/)
  assert.doesNotMatch(view, /MAP_TILE_ROOT|map\/tiles|createTile|tileLevel/)
  assert.doesNotMatch(view, /import\.meta\.glob/)
})

test('map area tabs switch between the open world and prioritized World Tree bounds', () => {
  const view = readFileSync(sourcePath('views/MapView.vue'), 'utf8')

  assert.match(view, /const MAP_AREA_TABS = Object\.freeze\(\['MainMap', 'Tree'\]\)/)
  assert.match(view, /const MAP_AREA_PRIORITY = Object\.freeze\(\['Tree', 'MainMap'\]\)/)
  assert.match(
    view,
    /Tree:[\s\S]*?min_x:\s*347351\.5,[\s\S]*?max_x:\s*689148\.5,[\s\S]*?min_y:\s*-818197,[\s\S]*?max_y:\s*-476400,/,
  )
  assert.match(view, /function mapAreaForPosition[\s\S]*?MAP_AREA_PRIORITY\.find/)
  assert.match(view, /function markersInActiveArea[\s\S]*?activeMapArea\.value/)
  assert.match(view, /function switchMapArea[\s\S]*?activeMapArea\.value = area[\s\S]*?resetView\(\)/)
  assert.match(view, /class="map-area-tabs"[\s\S]*?role="tablist"/)
  assert.match(view, /v-for="area in MAP_AREA_TABS"[\s\S]*?role="tab"/)
  assert.match(view, /Map_AreaTabs|Map_Area_MainMap|Map_Area_Tree/)
})

test('map store reads the shared session snapshot without creating a pending change', async () => {
  setActivePinia(createPinia())
  const store = usePalEditorStore()
  store.SESSION_ID = 'session-map'
  store.SESSION_REVISION = 7

  axios.get = async url => {
    assert.equal(url, '/api/save/query/map?session_id=session-map')
    return {
      data: {
        status: 0,
        data: {
          revision: 7,
          location_source: 'save_last_transform',
          live: false,
          players: [{ player_id: 'player-1', name: 'Y7', x: 1, y: 2, z: 3 }],
          bases: [],
          unavailable_player_ids: [],
          unavailable_base_ids: [],
        },
      },
    }
  }

  assert.equal(await store.loadMapData(), true)
  assert.equal(store.MAP_LOADING, false)
  assert.equal(store.MAP_DATA.live, false)
  assert.equal(store.MAP_DATA.players[0].name, 'Y7')
  assert.equal(store.PENDING_CHANGE_COUNT, 0)
  assert.equal(store.SESSION_REVISION, 7)
})

test('player Other tab keeps both fog actions in one equal-height card', async () => {
  const view = readFileSync(sourcePath('views/MapView.vue'), 'utf8')
  const playerEditor = readFileSync(sourcePath('components/PlayerEditor.vue'), 'utf8')
  const storeSource = readFileSync(sourcePath('stores/paleditor.js'), 'utf8')
  const zh = readFileSync(sourcePath('i18n/zh-CN.js'), 'utf8')

  assert.doesNotMatch(view, /fogResetCapability|Map_FogReset_Button|fog-reset-panel/)
  assert.match(
    playerEditor,
    /id="player-attributes-tab"[\s\S]*?id="player-map-progress-tab"[\s\S]*?PlayerTab_MapProgress/,
  )
  assert.match(zh, /PlayerTab_MapProgress:\s*"其他"/)
  assert.match(
    playerEditor,
    /fogClearCapability[\s\S]*?fogResetCapability[\s\S]*?FOG_OF_WAR_STRUCTURE_UNSUPPORTED/,
  )
  assert.match(
    playerEditor,
    /Map_FogReset_Title[\s\S]*?class="player-map-action__actions"[\s\S]*?Map_FogClear_Button[\s\S]*?Map_FogReset_Button[\s\S]*?<\/article>/,
  )
  assert.match(
    playerEditor,
    /:disabled="palStore\.LOADING_FLAG \|\| !fogClearCapability\.available"/,
  )
  assert.match(
    playerEditor,
    /:disabled="palStore\.LOADING_FLAG \|\| !fogResetCapability\.available"/,
  )
  assert.match(
    playerEditor,
    /class="player-map-action__source"[\s\S]*?PlayerMap_FogSaveFile/,
  )
  assert.match(
    playerEditor,
    /player-map-progress-panel[\s\S]*?align-items:\s*stretch;/,
  )
  assert.match(
    playerEditor,
    /\.player-map-action__actions\s*\{[\s\S]*?grid-template-columns:\s*repeat\(2, minmax\(0, 1fr\)\);[\s\S]*?margin-top:\s*auto;/,
  )
  assert.match(zh, /PlayerMap_RequiredSaveFile:\s*"需要存档文件"/)
  assert.match(zh, /PlayerMap_FogSaveFile:\s*"LocalData\.sav"/)
  assert.match(zh, /PlayerMap_FastTravelSaveFile:\s*"Players\/\*\.sav"/)
  assert.match(storeSource, /const FOG_CLEAR_CONFIRMATION = "清除迷雾"/)
  assert.match(storeSource, /const FOG_RESET_CONFIRMATION = "重新覆盖未探索迷雾"/)
  assert.match(zh, /Map_FogClear_Button:\s*"清除迷雾"/)
  assert.match(zh, /Map_FogReset_Button:\s*"恢复迷雾"/)
  assert.match(zh, /重新覆盖未探索迷雾/)

  setActivePinia(createPinia())
  const store = usePalEditorStore()
  store.SESSION_ID = 'session-fog-clear'
  store.SESSION_REVISION = 4
  store.PENDING_CHANGE_COUNT = 0
  store.SAVE_CAPABILITIES = {
    fogOfWarClear: {
      available: true,
      reason: null,
      format: 'WorldMapUISaveDataMap',
      maps: ['MainMap', 'Tree'],
    },
    fogOfWarReset: {
      available: true,
      reason: null,
      format: 'WorldMapUISaveDataMap',
      maps: ['MainMap', 'Tree'],
    },
  }
  let confirmed = false
  globalThis.window.confirm = message => {
    confirmed = true
    assert.match(message, /reveals the full map|解锁全地图/i)
    return true
  }
  axios.post = async (url, data) => {
    assert.equal(url, '/api/save/local-data/fog-of-war/clear')
    assert.deepEqual(data, {
      session_id: 'session-fog-clear',
      expected_revision: 4,
      confirmation: '清除迷雾',
    })
    return {
      data: {
        status: 0,
        data: {
          revision: 5,
          changed: true,
        },
      },
    }
  }

  assert.equal(await store.clearFogOfWar(), true)
  assert.equal(confirmed, true)
  assert.equal(store.SESSION_REVISION, 5)
  assert.equal(store.PENDING_CHANGE_COUNT, 1)
})

test('fog restore uses the explicit revision-bound pending-change command', async () => {
  setActivePinia(createPinia())
  const store = usePalEditorStore()
  store.SESSION_ID = 'session-fog-reset'
  store.SESSION_REVISION = 6
  store.PENDING_CHANGE_COUNT = 0
  store.SAVE_CAPABILITIES = {
    fogOfWarReset: {
      available: true,
      reason: null,
      format: 'WorldMapUISaveDataMap',
      maps: ['MainMap', 'Tree'],
    },
  }
  let confirmed = false
  globalThis.window.confirm = message => {
    confirmed = true
    assert.match(message, /does not clear fog|重新覆盖未探索迷雾/i)
    return true
  }
  axios.post = async (url, data) => {
    assert.equal(url, '/api/save/local-data/fog-of-war/reset')
    assert.deepEqual(data, {
      session_id: 'session-fog-reset',
      expected_revision: 6,
      confirmation: '重新覆盖未探索迷雾',
    })
    return {
      data: {
        status: 0,
        data: {
          revision: 7,
          changed: true,
        },
      },
    }
  }

  assert.equal(await store.resetFogOfWar(), true)
  assert.equal(confirmed, true)
  assert.equal(store.SESSION_REVISION, 7)
  assert.equal(store.PENDING_CHANGE_COUNT, 1)
})

test('fog actions refuse unavailable LocalData without sending a command', async () => {
  setActivePinia(createPinia())
  const store = usePalEditorStore()
  store.SESSION_ID = 'session-fog-missing'
  const unavailable = {
    available: false,
    reason: 'LOCAL_DATA_MISSING',
    format: null,
    maps: [],
  }
  store.SAVE_CAPABILITIES = {
    fogOfWarClear: unavailable,
    fogOfWarReset: unavailable,
  }
  axios.post = async () => {
    throw new Error('the command must remain disabled')
  }

  assert.equal(await store.clearFogOfWar(), false)
  assert.equal(store.LAST_ERROR.code, 'LOCAL_DATA_MISSING')
  assert.equal(await store.resetFogOfWar(), false)
  assert.equal(store.LAST_ERROR.code, 'LOCAL_DATA_MISSING')
  assert.equal(store.PENDING_CHANGE_COUNT, 0)
})

test('LocalData selection is explicit, revision-bound, and does not create a pending change', async () => {
  const playerEditor = readFileSync(sourcePath('components/PlayerEditor.vue'), 'utf8')
  assert.match(playerEditor, /@click="palStore\.selectLocalData"/)
  assert.match(playerEditor, /PlayerMap_LocalData_Select/)

  setActivePinia(createPinia())
  const store = usePalEditorStore()
  store.SESSION_ID = 'session-local-data'
  store.SESSION_REVISION = 3
  store.PENDING_CHANGE_COUNT = 0
  store.SAVE_PLATFORM = 'steam'
  store.PAL_GAME_SAVE_PATH = 'D:/world/save'
  let requestedInitialPath = null
  store.SAVE_CAPABILITIES = {
    localDataSelection: {
      selected: false,
      platform: 'steam',
      canSelectFile: true,
      source: null,
      reason: 'LOCAL_DATA_NOT_SELECTED',
    },
  }
  globalThis.window.pywebview = {
    api: {
      select_local_data_file: async (initialPath) => {
        requestedInitialPath = initialPath
        return 'D:/profile/LocalData.sav'
      },
    },
  }
  axios.post = async (url, data) => {
    assert.equal(url, '/api/save/local-data/select')
    assert.deepEqual(data, {
      session_id: 'session-local-data',
      expected_revision: 3,
      path: 'D:/profile/LocalData.sav',
    })
    return {
      data: {
        status: 0,
        data: {
          revision: 4,
          saveCapabilities: {
            localDataSelection: {
              selected: true,
              platform: 'steam',
              canSelectFile: true,
              source: 'D:/profile/LocalData.sav',
              reason: null,
            },
            fogOfWarClear: { available: true, reason: null },
            fogOfWarReset: { available: true, reason: null },
          },
        },
      },
    }
  }

  assert.equal(await store.selectLocalData(), true)
  assert.equal(requestedInitialPath, 'D:/world/save')
  assert.equal(store.SESSION_REVISION, 4)
  assert.equal(store.PENDING_CHANGE_COUNT, 0)
  assert.equal(store.SAVE_CAPABILITIES.localDataSelection.selected, true)
  delete globalThis.window.pywebview
})

test('web LocalData selection uses the shared picker and confirms only LocalData.sav', async () => {
  const app = readFileSync(sourcePath('App.vue'), 'utf8')
  const entry = readFileSync(sourcePath('views/EntryView.vue'), 'utf8')
  const picker = readFileSync(sourcePath('components/PathPicker.vue'), 'utf8')
  const storeSource = readFileSync(sourcePath('stores/paleditor.js'), 'utf8')
  assert.match(app, /import PathPicker[\s\S]*?<PathPicker \/>/)
  assert.doesNotMatch(entry, /<PathPicker \/>/)
  assert.doesNotMatch(storeSource, /PlayerMap_LocalData_PathPrompt/)
  assert.match(picker, /FILE_PICKER_PURPOSE === 'local-data'/)
  assert.match(picker, /filename\.toLowerCase\(\) === 'localdata\.sav'/)
  assert.match(picker, /PAL_FILE_PICKER_SELECTION/)

  setActivePinia(createPinia())
  const store = usePalEditorStore()
  store.SESSION_ID = 'session-web-local-data'
  store.SESSION_REVISION = 8
  store.PENDING_CHANGE_COUNT = 0
  store.SAVE_PLATFORM = 'steam'
  store.PAL_GAME_SAVE_PATH = 'D:/world/save'
  store.SAVE_CAPABILITIES = {
    localDataSelection: {
      selected: false,
      platform: 'steam',
      canSelectFile: true,
      source: null,
      reason: 'LOCAL_DATA_NOT_SELECTED',
    },
  }
  delete globalThis.window.pywebview

  let requestCount = 0
  axios.post = async (url, data) => {
    requestCount += 1
    if (requestCount === 1) {
      assert.equal(url, '/api/save/browse-directory')
      assert.deepEqual(data, { path: 'D:/world/save' })
      return {
        data: {
          status: 0,
          data: {
            currentPath: 'D:/world/save',
            isPalDir: true,
            children: {
              'D:/world/save/LocalData.sav': {
                filename: 'LocalData.sav',
                isDir: false,
              },
              'D:/world/save/Level.sav': {
                filename: 'Level.sav',
                isDir: false,
              },
            },
          },
        },
      }
    }
    assert.equal(url, '/api/save/local-data/select')
    assert.deepEqual(data, {
      session_id: 'session-web-local-data',
      expected_revision: 8,
      path: 'D:/world/save/LocalData.sav',
    })
    return {
      data: {
        status: 0,
        data: {
          revision: 9,
          saveCapabilities: {
            localDataSelection: {
              selected: true,
              platform: 'steam',
              canSelectFile: true,
              source: 'D:/world/save/LocalData.sav',
              reason: null,
            },
          },
        },
      },
    }
  }

  assert.equal(await store.selectLocalData(), true)
  assert.equal(store.SHOW_FILE_PICKER, true)
  assert.equal(store.FILE_PICKER_PURPOSE, 'local-data')
  assert.equal(store.PAL_FILE_PICKER_PATH, 'D:/world/save')
  assert.equal(store.PATH_CONTEXT.get('D:/world/save/Level.sav').isDir, false)
  assert.equal(await store.confirmLocalDataFileSelection('D:/world/save/Level.sav'), false)
  assert.equal(requestCount, 1)
  assert.equal(await store.confirmLocalDataFileSelection('D:/world/save/LocalData.sav'), true)
  assert.equal(store.SHOW_FILE_PICKER, false)
  assert.equal(store.SAVE_CAPABILITIES.localDataSelection.selected, true)
})

test('WGS LocalData selection remains bound to the opened slot without a file picker', async () => {
  setActivePinia(createPinia())
  const store = usePalEditorStore()
  store.SESSION_ID = 'session-wgs-local-data'
  store.SESSION_REVISION = 12
  store.SAVE_PLATFORM = 'xgp'
  store.SAVE_CAPABILITIES = {
    localDataSelection: {
      selected: false,
      platform: 'xgp',
      canSelectFile: false,
      source: null,
      reason: 'LOCAL_DATA_NOT_SELECTED',
    },
  }
  let nativePickerCalled = false
  globalThis.window.pywebview = {
    api: {
      select_local_data_file: async () => {
        nativePickerCalled = true
        return 'D:/external/LocalData.sav'
      },
    },
  }
  axios.post = async (url, data) => {
    assert.equal(url, '/api/save/local-data/select')
    assert.deepEqual(data, {
      session_id: 'session-wgs-local-data',
      expected_revision: 12,
    })
    return {
      data: {
        status: 0,
        data: {
          revision: 13,
          saveCapabilities: {
            localDataSelection: {
              selected: true,
              platform: 'xgp',
              canSelectFile: false,
              source: 'Opened WGS slot',
              reason: null,
            },
          },
        },
      },

    }
  }

  assert.equal(await store.selectLocalData(), true)
  assert.equal(nativePickerCalled, false)
  assert.equal(store.SHOW_FILE_PICKER, false)
  delete globalThis.window.pywebview
})

test('ordinary backpack expansion reloads inventory so the visible slot count changes', async () => {
  const playerEditor = readFileSync(sourcePath('components/PlayerEditor.vue'), 'utf8')
  const zh = readFileSync(sourcePath('i18n/zh-CN.js'), 'utf8')
  assert.match(playerEditor, /PlayerInventoryCapacity_Title/)
  assert.match(playerEditor, /PlayerInventoryCapacity_SaveFile/)
  assert.match(playerEditor, /@click="palStore\.updatePlayerInventoryCapacity\(inventoryCapacityTarget\)"/)
  assert.match(playerEditor, /\.player-map-action__capacity-control/)
  assert.match(playerEditor, /type="number"[\s\S]*?:max="inventoryCapacityCapability\.maximum_capacity"/)
  assert.doesNotMatch(playerEditor, /player-inventory-capacity-presets|<datalist/)
  assert.match(playerEditor, /PlayerInventoryCapacity_PerformanceWarning/)
  assert.match(playerEditor, /target !== current/)
  assert.match(zh, /PlayerInventoryCapacity_Title:\s*"普通背包容量"/)
  assert.match(zh, /PlayerInventoryCapacity_ShrinkConfirm:[\s\S]*?物品可能消失/)
  assert.match(zh, /游戏官方基础容量为 42 格/)
  assert.match(zh, /过大的背包格子数组[\s\S]*?打开背包卡顿/)

  setActivePinia(createPinia())
  const store = usePalEditorStore()
  store.SESSION_ID = 'session-inventory-capacity'
  store.SESSION_REVISION = 7
  store.PENDING_CHANGE_COUNT = 0
  store.SELECTED_PLAYER_ID = 'player-1'
  store.SELECTED_PLAYER_DATA = {
    InventoryCapacityCapability: {
      available: true,
      reason: null,
      current_capacity: 54,
      allowed_capacities: [60, 90, 120],
      minimum_capacity: 42,
      maximum_capacity: 1000,
      custom_input: true,
      expand_only: false,
    },
    InventoryContainers: [],
  }
  globalThis.window.confirm = message => {
    assert.match(message, /54[\s\S]*75/)
    return true
  }
  axios.post = async (url, data) => {
    assert.equal(url, '/api/player/player-1/commands')
    assert.deepEqual(data, {
      session_id: 'session-inventory-capacity',
      expected_revision: 7,
      command: 'update_player_inventory_capacity',
      capacity: 75,
    })
    return {
      data: {
        status: 0,
        data: {
          revision: 8,
          changed: true,
          capability: {
            available: true,
            reason: null,
            current_capacity: 75,
            allowed_capacities: [60, 90, 120],
            minimum_capacity: 42,
            maximum_capacity: 1000,
            custom_input: true,
            expand_only: false,
          },
        },
      },
    }
  }
  axios.get = async url => {
    assert.equal(url, '/api/player/player-1/inventory?session_id=session-inventory-capacity')
    return {
      data: {
        status: 0,
        data: {
          revision: 8,
          containers: [{
            container_type: 'COMMON',
            capacity: 75,
            slots: Array.from({ length: 75 }, (_, slot_index) => ({ slot_index })),
          }],
        },
      },
    }
  }

  assert.equal(await store.updatePlayerInventoryCapacity(75), true)
  assert.equal(store.SESSION_REVISION, 8)
  assert.equal(store.PENDING_CHANGE_COUNT, 1)
  assert.equal(store.SELECTED_PLAYER_DATA.InventoryCapacityCapability.current_capacity, 75)
  assert.equal(store.SELECTED_PLAYER_DATA.InventoryContainers[0].slots.length, 75)
})

test('ordinary backpack reduction uses the item-loss confirmation', async () => {
  setActivePinia(createPinia())
  const store = usePalEditorStore()
  store.I18n = 'en'
  store.SESSION_ID = 'session-inventory-reduction'
  store.SESSION_REVISION = 3
  store.PENDING_CHANGE_COUNT = 0
  store.SELECTED_PLAYER_ID = 'player-1'
  store.SELECTED_PLAYER_DATA = {
    InventoryCapacityCapability: {
      available: true,
      reason: null,
      current_capacity: 90,
      allowed_capacities: [60, 120],
      minimum_capacity: 42,
      maximum_capacity: 1000,
      custom_input: true,
      expand_only: false,
    },
    InventoryContainers: [],
  }
  globalThis.window.confirm = message => {
    assert.match(message, /90[\s\S]*42/)
    assert.match(message, /items occupying those positions may disappear/i)
    return true
  }
  axios.post = async (url, data) => {
    assert.equal(url, '/api/player/player-1/commands')
    assert.deepEqual(data, {
      session_id: 'session-inventory-reduction',
      expected_revision: 3,
      command: 'update_player_inventory_capacity',
      capacity: 42,
    })
    return {
      data: {
        status: 0,
        data: {
          revision: 4,
          changed: true,
          capability: {
            available: true,
            reason: null,
            current_capacity: 42,
            allowed_capacities: [60, 90, 120],
            minimum_capacity: 42,
            maximum_capacity: 1000,
            custom_input: true,
            expand_only: false,
          },
        },
      },
    }
  }
  axios.get = async url => {
    assert.equal(url, '/api/player/player-1/inventory?session_id=session-inventory-reduction')
    return {
      data: {
        status: 0,
        data: {
          revision: 4,
          containers: [{
            container_type: 'COMMON',
            capacity: 42,
            slots: Array.from({ length: 42 }, (_, slot_index) => ({ slot_index })),
          }],
        },
      },
    }
  }

  assert.equal(await store.updatePlayerInventoryCapacity(42), true)
  assert.equal(store.SESSION_REVISION, 4)
  assert.equal(store.SELECTED_PLAYER_DATA.InventoryContainers[0].slots.length, 42)
})

test('selected-player fast-travel unlock is capability-gated and revision-bound', async () => {
  const playerEditor = readFileSync(sourcePath('components/PlayerEditor.vue'), 'utf8')
  const storeSource = readFileSync(sourcePath('stores/paleditor.js'), 'utf8')
  const zh = readFileSync(sourcePath('i18n/zh-CN.js'), 'utf8')

  assert.match(
    playerEditor,
    /v-show="activeEditorTab === 'map-progress'"[\s\S]*?PlayerMap_FastTravel_Progress/,
  )
  assert.doesNotMatch(playerEditor, /id="player-fast-travel-description"/)
  assert.match(
    playerEditor,
    /class="player-map-action__source"[\s\S]*?PlayerMap_FastTravelSaveFile/,
  )
  assert.match(
    playerEditor,
    /:disabled="palStore\.LOADING_FLAG \|\| !fastTravelCapability\.available"/,
  )
  assert.match(playerEditor, /@click="palStore\.unlockAllFastTravelPoints"/)
  assert.match(
    storeSource,
    /const FAST_TRAVEL_UNLOCK_CONFIRMATION = "解锁所有传送点"/,
  )
  assert.match(zh, /PlayerMap_FastTravel_Button:\s*"解锁所有传送点"/)
  assert.match(zh, /不会清除或揭开战争迷雾/)

  setActivePinia(createPinia())
  const store = usePalEditorStore()
  store.SESSION_ID = 'session-fast-travel'
  store.SESSION_REVISION = 9
  store.PENDING_CHANGE_COUNT = 0
  store.SELECTED_PLAYER_ID = 'player-1'
  store.SELECTED_PLAYER_DATA = {
    FastTravelUnlockCapability: {
      available: true,
      reason: null,
      format: 'MapProperty<NameProperty,BoolProperty>',
      unlocked_count: 28,
      total_count: 141,
    },
  }
  let confirmed = false
  globalThis.window.confirm = message => {
    confirmed = true
    assert.match(message, /does not clear or reveal fog|不会清除或揭开战争迷雾/i)
    return true
  }
  axios.post = async (url, data) => {
    assert.equal(url, '/api/player/player-1/commands')
    assert.deepEqual(data, {
      session_id: 'session-fast-travel',
      expected_revision: 9,
      command: 'unlock_all_fast_travel_points',
      confirmation: '解锁所有传送点',
    })
    return {
      data: {
        status: 0,
        data: {
          revision: 10,
          changed: true,
          value: {
            format: 'MapProperty<NameProperty,BoolProperty>',
            unlocked_count: 141,
            total_count: 141,
          },
        },
      },
    }
  }

  assert.equal(await store.unlockAllFastTravelPoints(), true)
  assert.equal(confirmed, true)
  assert.equal(store.SESSION_REVISION, 10)
  assert.equal(store.PENDING_CHANGE_COUNT, 1)
  assert.equal(
    store.SELECTED_PLAYER_DATA.FastTravelUnlockCapability.unlocked_count,
    141,
  )
})

test('selected-player fast-travel unlock refuses an unverified field', async () => {
  setActivePinia(createPinia())
  const store = usePalEditorStore()
  store.SESSION_ID = 'session-fast-travel-missing'
  store.SELECTED_PLAYER_ID = 'player-1'
  store.SELECTED_PLAYER_DATA = {
    FastTravelUnlockCapability: {
      available: false,
      reason: 'FAST_TRAVEL_FIELD_MISSING',
      format: null,
      unlocked_count: null,
      total_count: 141,
    },
  }
  axios.post = async () => {
    throw new Error('the command must remain disabled')
  }

  assert.equal(await store.unlockAllFastTravelPoints(), false)
  assert.equal(store.LAST_ERROR.code, 'FAST_TRAVEL_FIELD_MISSING')
  assert.equal(store.PENDING_CHANGE_COUNT, 0)
})
