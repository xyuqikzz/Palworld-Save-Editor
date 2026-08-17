<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue';
import { usePalEditorStore } from '@/stores/paleditor';
import { useRoute, useRouter } from 'vue-router';
import AppIcon from '@/components/modules/AppIcon.vue';

const palStore = usePalEditorStore();
const route = useRoute();
const router = useRouter();
const lastOfflineSourceMode = ref(
  palStore.SAVE_SOURCE_MODE === 'xgp' ? 'xgp' : 'steam',
);
const entryEditMode = ref(
  route.query.source === 'global-palbox'
    ? 'global-palbox'
    : palStore.SAVE_SOURCE_MODE === 'remote' ? 'online' : 'offline',
);
const remoteAdminPassword = ref('');
const modInstallDialog = ref(null);
const bridgeModDownloadAvailable = ref(false);
const bridgeModDownloadState = ref('idle');
const bridgeModDownloadResult = ref(null);
const ue4ssReleasesUrl = 'https://github.com/UE4SS-RE/RE-UE4SS/releases';
const windowsClientUe4ssPath = String.raw`…\steamapps\common\Palworld\Pal\Binaries\Win64`;
const windowsXgpClientUe4ssPath = String.raw`…\XboxGames\Palworld\Content\Pal\Binaries\WinGDK`;
const windowsServerUe4ssPath = String.raw`…\steamapps\common\PalServer\Pal\Binaries\Win64`;
const bridgeModPrimaryPath = String.raw`Pal\Binaries\<Win64|WinGDK>\ue4ss\Mods\PalEditorBridge`;
const bridgeModFallbackPath = String.raw`Pal\Binaries\<Win64|WinGDK>\Mods\PalEditorBridge`;
const serverRestConfiguration = 'RESTAPIEnabled=True · RESTAPIPort=8212 · AdminPassword=…';

async function selectEntryEditMode(mode) {
  entryEditMode.value = mode;
  if (mode === 'global-palbox') {
    if (palStore.SAVE_SOURCE_MODE === 'remote') {
      palStore.SAVE_SOURCE_MODE = lastOfflineSourceMode.value;
    }
    await palStore.initializeGlobalPalbox();
    return;
  }
  if (mode === 'online') {
    if (palStore.SAVE_SOURCE_MODE === 'steam' || palStore.SAVE_SOURCE_MODE === 'xgp') {
      lastOfflineSourceMode.value = palStore.SAVE_SOURCE_MODE;
    }
    palStore.SAVE_SOURCE_MODE = 'remote';
    return;
  }

  palStore.SAVE_SOURCE_MODE = lastOfflineSourceMode.value;
}

function selectOfflineSourceMode(mode) {
  entryEditMode.value = 'offline';
  lastOfflineSourceMode.value = mode;
  palStore.SAVE_SOURCE_MODE = mode;
}

function selectGlobalPalboxSourceMode(mode) {
  palStore.GLOBAL_PALBOX_SOURCE_MODE = mode;
  palStore.GLOBAL_PALBOX_ERROR = null;
}

async function openGlobalPalbox() {
  if (await palStore.openGlobalPalbox()) {
    await router.push({ name: 'GlobalPalbox' });
  }
}

function refreshBridgeModDownloadAvailability() {
  bridgeModDownloadAvailable.value = Boolean(
    window.pywebview?.api?.download_bridge_mod,
  );
}

async function downloadBridgeMod() {
  const nativeDownload = window.pywebview?.api?.download_bridge_mod;
  if (!nativeDownload) {
    bridgeModDownloadState.value = 'unavailable';
    return;
  }

  bridgeModDownloadState.value = 'loading';
  bridgeModDownloadResult.value = null;
  try {
    const result = await nativeDownload();
    if (!result || result.status === 'cancelled') {
      bridgeModDownloadState.value = 'idle';
      return;
    }
    if (result.status !== 'completed') {
      bridgeModDownloadState.value = result.status === 'unsupported'
        ? 'unavailable'
        : 'failed';
      return;
    }
    bridgeModDownloadResult.value = result;
    bridgeModDownloadState.value = 'completed';
    modInstallDialog.value?.showModal();
  } catch {
    bridgeModDownloadState.value = 'failed';
  }
}

function closeModInstallDialog() {
  modInstallDialog.value?.close();
}

async function connectRemote() {
  const connected = await palStore.connectRemote({
    adminPassword: remoteAdminPassword.value,
  });
  if (connected) {
    remoteAdminPassword.value = '';
    await router.push({ name: 'RemoteServer' });
  }
}

async function connectLocalGame() {
  if (await palStore.connectLocalGame()) {
    await router.push({ name: 'RemoteServer' });
  }
}

onMounted(() => {
  refreshBridgeModDownloadAvailability();
  window.addEventListener(
    'pywebviewready',
    refreshBridgeModDownloadAvailability,
  );
  if (entryEditMode.value === 'global-palbox') {
    palStore.initializeGlobalPalbox();
  }
});

onBeforeUnmount(() => {
  window.removeEventListener(
    'pywebviewready',
    refreshBridgeModDownloadAvailability,
  );
});
</script>

<template>
  <main id="entryDiv">
    <section class="entry-shell">
      <header class="entry-intro" aria-labelledby="entry-title">
        <img :alt="palStore.getTranslatedText('Common_AppName')" class="logo" src="@/assets/logo.ico" width="60" height="60" />
        <div class="entry-intro-copy">
          <p class="product-name">{{ palStore.getTranslatedText('Common_AppName') }}</p>
          <h1 id="entry-title">{{ palStore.getTranslatedText('EntryView_Title') }}</h1>
        </div>
        <div class="entry-support-copy">
          <p class="entry-copy">{{ palStore.getTranslatedText('EntryView_Intro') }}</p>
          <p class="free-notice">{{ palStore.getTranslatedText('EntryView_Free_Notice') }}</p>
        </div>
      </header>

      <div class="entry-workspace">
        <div class="source-switch" role="radiogroup" :aria-label="palStore.getTranslatedText('Entry_Source_Label')">
          <label :class="{ active: entryEditMode === 'offline' }">
            <input
              type="radio"
              name="entry-edit-mode"
              value="offline"
              :checked="entryEditMode === 'offline'"
              @change="selectEntryEditMode('offline')"
            />
            <span class="source-icon source-icon--offline" aria-hidden="true">
              <AppIcon name="folder" :size="26" />
            </span>
            <span class="source-label-text">
              <span class="source-name">{{ palStore.getTranslatedText('Entry_Source_Offline') }}</span>
            </span>
          </label>
          <label :class="{ active: entryEditMode === 'online' }">
            <input
              type="radio"
              name="entry-edit-mode"
              value="online"
              :checked="entryEditMode === 'online'"
              @change="selectEntryEditMode('online')"
            />
            <span class="source-icon source-icon--remote" aria-hidden="true">
              <AppIcon name="computer" :size="26" />
            </span>
            <span class="source-label-text">
              <span class="source-name">{{ palStore.getTranslatedText('Entry_Source_Online') }}</span>
              <span class="beta-badge">{{ palStore.getTranslatedText('Entry_Source_Beta') }}</span>
            </span>
          </label>
          <label>
            <input
              type="radio"
              name="entry-edit-mode"
              value="migration"
              @change="router.push({ name: 'SaveMigration' })"
            />
            <span class="source-icon source-icon--migration" aria-hidden="true">
              <AppIcon name="forward" :size="26" />
            </span>
            <span class="source-label-text">
              <span class="source-name">{{ palStore.getTranslatedText('Migration_Entry') }}</span>
              <span class="beta-badge">{{ palStore.getTranslatedText('Entry_Source_Beta') }}</span>
            </span>
          </label>
          <label :class="{ active: entryEditMode === 'global-palbox' }">
            <input
              type="radio"
              name="entry-edit-mode"
              value="global-palbox"
              :checked="entryEditMode === 'global-palbox'"
              @change="selectEntryEditMode('global-palbox')"
            />
            <span class="source-icon source-icon--offline" aria-hidden="true">
              <AppIcon name="box" :size="26" />
            </span>
            <span class="source-label-text">
              <span class="source-name">{{ palStore.getTranslatedText('GlobalPalbox_Entry') }}</span>
            </span>
          </label>
        </div>

        <section class="entry-panel" aria-labelledby="save-path-heading">
          <div
            v-if="entryEditMode === 'offline'"
            class="offline-platform-switch"
            role="radiogroup"
            :aria-label="palStore.getTranslatedText('Entry_Platform_Label')"
          >
            <span>{{ palStore.getTranslatedText('Entry_Platform_Label') }}</span>
            <label :class="{ active: palStore.SAVE_SOURCE_MODE === 'steam' }">
              <input
                type="radio"
                name="offline-save-platform"
                value="steam"
                :checked="palStore.SAVE_SOURCE_MODE === 'steam'"
                @change="selectOfflineSourceMode('steam')"
              />
              <img src="@/assets/steam.svg" alt="" width="18" height="18" />
              {{ palStore.getTranslatedText('Entry_Platform_Steam') }}
            </label>
            <label :class="{ active: palStore.SAVE_SOURCE_MODE === 'xgp' }">
              <input
                type="radio"
                name="offline-save-platform"
                value="xgp"
                :checked="palStore.SAVE_SOURCE_MODE === 'xgp'"
                @change="selectOfflineSourceMode('xgp')"
              />
              <img src="@/assets/xbox.svg" alt="" width="18" height="18" />
              {{ palStore.getTranslatedText('Entry_Platform_Xgp') }}
            </label>
          </div>

          <div
            v-if="entryEditMode === 'global-palbox'"
            class="offline-platform-switch"
            role="radiogroup"
            :aria-label="palStore.getTranslatedText('GlobalPalbox_Platform')"
          >
            <span>{{ palStore.getTranslatedText('GlobalPalbox_Platform') }}</span>
            <label :class="{ active: palStore.GLOBAL_PALBOX_SOURCE_MODE === 'steam' }">
              <input
                type="radio"
                name="global-palbox-platform"
                value="steam"
                :checked="palStore.GLOBAL_PALBOX_SOURCE_MODE === 'steam'"
                @change="selectGlobalPalboxSourceMode('steam')"
              />
              <img src="@/assets/steam.svg" alt="" width="18" height="18" />
              {{ palStore.getTranslatedText('Entry_Platform_Steam') }}
            </label>
            <label :class="{ active: palStore.GLOBAL_PALBOX_SOURCE_MODE === 'xgp' }">
              <input
                type="radio"
                name="global-palbox-platform"
                value="xgp"
                :checked="palStore.GLOBAL_PALBOX_SOURCE_MODE === 'xgp'"
                @change="selectGlobalPalboxSourceMode('xgp')"
              />
              <img src="@/assets/xbox.svg" alt="" width="18" height="18" />
              {{ palStore.getTranslatedText('SourceBadge_Xgp') }}
            </label>
          </div>

          <div class="panel-heading">
            <h2 id="save-path-heading">
              {{ palStore.getTranslatedText(
                entryEditMode === 'global-palbox'
                  ? 'GlobalPalbox_File'
                  : palStore.SAVE_SOURCE_MODE === 'remote'
                    ? 'Remote_Title'
                    : 'EntryView_Save_Path'
              ) }}
            </h2>
            <p>
              {{ palStore.getTranslatedText(
                entryEditMode === 'global-palbox'
                  ? 'GlobalPalbox_OpenHint'
                  : palStore.SAVE_SOURCE_MODE === 'xgp'
                  ? 'Entry_Xgp_Hint'
                  : palStore.SAVE_SOURCE_MODE === 'remote'
                    ? 'Remote_Hint'
                    : 'EntryView_Path_Hint'
              ) }}
            </p>
          </div>

          <template v-if="entryEditMode === 'global-palbox'">
            <aside class="global-palbox-note" role="note">
              <AppIcon name="info" :size="17" />
              <span>{{ palStore.getTranslatedText(
                palStore.GLOBAL_PALBOX_SOURCE_MODE === 'xgp'
                  ? 'GlobalPalbox_XgpHint'
                  : 'GlobalPalbox_SteamHint'
              ) }}</span>
            </aside>

            <div v-if="palStore.GLOBAL_PALBOX_SOURCE_MODE === 'steam'" class="save-path-row">
              <label class="path-field">
                <span class="sr-only">{{ palStore.getTranslatedText('GlobalPalbox_File') }}</span>
                <input
                  type="text"
                  v-model="palStore.GLOBAL_PALBOX_PATH"
                  :placeholder="palStore.getTranslatedText('GlobalPalbox_PathPlaceholder')"
                  :disabled="palStore.GLOBAL_PALBOX_LOADING"
                />
              </label>
              <button class="button button--quiet" @click="palStore.show_file_picker('global-palbox')" :disabled="palStore.GLOBAL_PALBOX_LOADING || palStore.LOADING_FLAG">
                {{ palStore.getTranslatedText('GlobalPalbox_ChooseFile') }}
              </button>
            </div>

            <template v-else>
              <div class="save-path-row xgp-path-row">
                <label class="path-field">
                  <span class="sr-only">{{ palStore.getTranslatedText('GlobalPalbox_XgpFolder') }}</span>
                  <input
                    type="text"
                    v-model="palStore.GLOBAL_PALBOX_XGP_PATH"
                    :placeholder="palStore.getTranslatedText('Entry_Xgp_Path_Example')"
                    :disabled="palStore.GLOBAL_PALBOX_LOADING"
                  />
                </label>
                <button
                  class="button button--quiet"
                  @click="palStore.show_file_picker('global-palbox-xgp')"
                  :disabled="palStore.GLOBAL_PALBOX_LOADING"
                >
                  {{ palStore.getTranslatedText('Entry_Xgp_Select_Folder') }}
                </button>
              </div>
              <div
                v-if="palStore.GLOBAL_PALBOX_XGP_SOURCES.length"
                class="xgp-sources xgp-entry-sources"
                role="radiogroup"
                :aria-label="palStore.getTranslatedText('GlobalPalbox_XgpSelect')"
              >
                <label
                  v-for="source in palStore.GLOBAL_PALBOX_XGP_SOURCES"
                  :key="source.sourceId"
                  class="xgp-source"
                >
                  <input
                    type="radio"
                    v-model="palStore.SELECTED_GLOBAL_PALBOX_XGP_SOURCE_ID"
                    :value="source.sourceId"
                  />
                  <span>
                    <strong>{{ source.displayName }}</strong>
                    <small>{{ new Date(source.updatedAt).toLocaleString() }}</small>
                  </span>
                  <em>{{ palStore.getTranslatedText(`Entry_Xgp_Status_${source.status}`) }}</em>
                </label>
              </div>
              <p class="path-current" v-else>
                {{ palStore.getTranslatedText('GlobalPalbox_XgpNoSources') }}
              </p>
            </template>
            <p v-if="palStore.GLOBAL_PALBOX_ERROR" class="entry-error" role="alert">
              {{ palStore.GLOBAL_PALBOX_ERROR }}
            </p>
            <div
              v-if="palStore.GLOBAL_PALBOX_SOURCE_MODE === 'xgp'"
              class="entry-primary-row xgp-entry-actions"
            >
              <button
                class="button button--quiet"
                @click="palStore.discoverGlobalPalboxXgp()"
                :disabled="palStore.GLOBAL_PALBOX_LOADING || !palStore.GLOBAL_PALBOX_XGP_PATH"
              >
                {{ palStore.getTranslatedText('Entry_Xgp_Discover') }}
              </button>
              <button
                class="button button--primary"
                @click="openGlobalPalbox"
                :disabled="palStore.GLOBAL_PALBOX_LOADING || !palStore.SELECTED_GLOBAL_PALBOX_XGP_SOURCE_ID"
              >
                {{ palStore.getTranslatedText('GlobalPalbox_Open') }}
              </button>
            </div>
            <div v-else class="entry-primary-row">
              <button
                class="button button--primary"
                @click="openGlobalPalbox"
                :disabled="palStore.GLOBAL_PALBOX_LOADING || !palStore.GLOBAL_PALBOX_PATH"
              >
                {{ palStore.getTranslatedText('GlobalPalbox_Open') }}
              </button>
            </div>
          </template>

          <template v-else-if="palStore.SAVE_SOURCE_MODE === 'steam'">
            <div class="save-path-row">
              <label class="path-field">
                <span class="sr-only">{{ palStore.getTranslatedText('EntryView_Save_Path') }}</span>
                <input
                  type="text"
                  v-model="palStore.PAL_GAME_SAVE_PATH"
                  :placeholder="palStore.getTranslatedText('EntryView_Path_Example')"
                  :disabled="palStore.LOADING_FLAG"
                />
              </label>
              <button class="button button--quiet" @click="palStore.show_file_picker('steam')" :disabled="palStore.LOADING_FLAG">
                {{ palStore.getTranslatedText('EntryView_BTN_Path_Picker') }}
              </button>
            </div>
            <div class="entry-primary-row">
              <button class="button button--primary" @click="palStore.loadSave" :disabled="palStore.LOADING_FLAG">
                {{ palStore.getTranslatedText('EntryView_BTN_Load') }}
              </button>
            </div>
          </template>

          <template v-else-if="palStore.SAVE_SOURCE_MODE === 'xgp'">
            <div class="save-path-row xgp-path-row">
              <label class="path-field">
                <span class="sr-only">{{ palStore.getTranslatedText('Entry_Xgp_Folder') }}</span>
                <input
                  type="text"
                  v-model="palStore.XGP_WGS_PATH"
                  :placeholder="palStore.getTranslatedText('Entry_Xgp_Path_Example')"
                  :disabled="palStore.LOADING_FLAG"
                />
              </label>
              <button class="button button--quiet" @click="palStore.show_file_picker('xgp')" :disabled="palStore.LOADING_FLAG">
                {{ palStore.getTranslatedText('Entry_Xgp_Select_Folder') }}
              </button>
            </div>
            <p
              v-if="palStore.LAST_ERROR?.context === 'discover-xgp-sources'"
              class="entry-error"
              role="alert"
            >
              {{ palStore.LAST_ERROR.message }}
            </p>
            <div class="xgp-sources xgp-entry-sources" v-if="palStore.XGP_SOURCES.length" role="radiogroup" :aria-label="palStore.getTranslatedText('Entry_Xgp_Select')">
              <label v-for="source in palStore.XGP_SOURCES" :key="source.sourceId" class="xgp-source">
                <input type="radio" v-model="palStore.SELECTED_XGP_SOURCE_ID" :value="source.sourceId" />
                <span>
                  <strong>{{ source.displayName }}</strong>
                  <small>{{ source.worldId?.slice(0, 8) }} · {{ new Date(source.updatedAt).toLocaleString() }}</small>
                </span>
                <em>{{ palStore.getTranslatedText(`Entry_Xgp_Status_${source.status}`) }}</em>
              </label>
            </div>
            <p class="path-current" v-else>{{ palStore.getTranslatedText('Entry_Xgp_NoSources') }}</p>
            <div class="entry-primary-row xgp-entry-actions">
              <button class="button button--quiet" @click="palStore.discoverXgpSources()" :disabled="palStore.LOADING_FLAG || !palStore.XGP_WGS_PATH">
                {{ palStore.getTranslatedText('Entry_Xgp_Discover') }}
              </button>
              <button class="button button--primary" @click="palStore.loadSave" :disabled="palStore.LOADING_FLAG || !palStore.SELECTED_XGP_SOURCE_ID">
                {{ palStore.getTranslatedText('EntryView_BTN_Load') }}
              </button>
            </div>
          </template>

          <template v-else>
            <aside class="remote-platform-notice" role="note">
              <span><AppIcon name="building" :size="16" /></span>
              <div>
                <strong>{{ palStore.getTranslatedText('Remote_WindowsOnlyTitle') }}</strong>
                <p>{{ palStore.getTranslatedText('Remote_WindowsOnlyHint') }}</p>
              </div>
            </aside>
            <div v-if="!palStore.REMOTE_CONNECTED" class="remote-connect-form">
              <aside class="remote-mod-notice" role="note">
                <span class="remote-mod-notice__icon">
                  <AppIcon name="folder" :size="19" />
                </span>
                <div>
                  <strong>{{ palStore.getTranslatedText('Remote_ModRequiredTitle') }}</strong>
                  <p>{{ palStore.getTranslatedText('Remote_ModRequiredHint') }}</p>
                  <small v-if="!bridgeModDownloadAvailable">
                    {{ palStore.getTranslatedText('Remote_ModDesktopOnly') }}
                  </small>
                  <small v-else-if="bridgeModDownloadState === 'failed'" class="remote-mod-download-error" role="alert">
                    {{ palStore.getTranslatedText('Remote_ModDownloadFailed') }}
                  </small>
                </div>
                <button
                  class="button button--quiet remote-mod-download"
                  type="button"
                  @click="downloadBridgeMod"
                  :disabled="!bridgeModDownloadAvailable || bridgeModDownloadState === 'loading'"
                >
                  <AppIcon name="folder" :size="15" />
                  {{ palStore.getTranslatedText(
                    bridgeModDownloadState === 'loading'
                      ? 'Remote_ModDownloading'
                      : 'Remote_ModDownloadButton'
                  ) }}
                </button>
              </aside>
              <section class="local-connect-card">
                <div>
                  <strong>{{ palStore.getTranslatedText('Remote_LocalConnect') }}</strong>
                  <p>{{ palStore.getTranslatedText('Remote_LocalConnectHint') }}</p>
                </div>
                <button
                  class="button button--primary"
                  @click="connectLocalGame"
                  :disabled="palStore.REMOTE_LOADING"
                >
                  {{ palStore.getTranslatedText('Remote_LocalConnect') }}
                </button>
              </section>
              <div
                v-if="palStore.LAST_ERROR?.context === 'local-connect'"
                class="entry-error"
                role="alert"
              >
                <p>{{ palStore.LAST_ERROR.message }}</p>
                <details v-if="palStore.LAST_ERROR.rawMessage">
                  <summary>{{ palStore.getTranslatedText('MessageDialog_Details') }}</summary>
                  <code>{{ palStore.LAST_ERROR.rawMessage }}</code>
                </details>
              </div>
              <div class="remote-divider">
                <span>{{ palStore.getTranslatedText('Remote_ManualConnection') }}</span>
              </div>
              <label class="remote-field">
                <span>{{ palStore.getTranslatedText('Remote_Address') }}</span>
                <input
                  type="text"
                  v-model.trim="palStore.REMOTE_SERVER_ADDRESS"
                  :placeholder="palStore.getTranslatedText('Remote_AddressPlaceholder')"
                  :disabled="palStore.REMOTE_LOADING"
                  autocomplete="url"
                />
              </label>
              <label class="remote-field">
                <span>{{ palStore.getTranslatedText('Remote_AdminPassword') }}</span>
                <input
                  type="password"
                  v-model="remoteAdminPassword"
                  :disabled="palStore.REMOTE_LOADING"
                  :placeholder="palStore.REMOTE_CREDENTIAL_SAVED ? palStore.getTranslatedText('Remote_SavedCredentialPlaceholder') : ''"
                  autocomplete="current-password"
                />
              </label>

              <p
                v-if="palStore.LAST_ERROR?.context === 'remote-connect'"
                class="entry-error"
                role="alert"
              >
                {{ palStore.LAST_ERROR.message }}
              </p>
              <div class="entry-primary-row">
                <button
                  class="button button--primary"
                  @click="connectRemote"
                  :disabled="palStore.REMOTE_LOADING || !palStore.REMOTE_SERVER_ADDRESS || (!remoteAdminPassword && !palStore.REMOTE_CREDENTIAL_SAVED)"
                >
                  {{ palStore.getTranslatedText('Remote_Connect') }}
                </button>
              </div>
            </div>

            <div v-else class="remote-connect-form">
              <p class="path-current">{{ palStore.getTranslatedText('Remote_AlreadyConnected') }}</p>
              <div class="entry-primary-row">
                <button class="button button--primary" @click="router.push({ name: 'RemoteServer' })">
                  {{ palStore.getTranslatedText('Remote_OpenManagement') }}
                </button>
              </div>
            </div>
          </template>
        </section>
      </div>

      <footer class="entry-safety">
        <p><AppIcon name="shield" :size="15" />{{ palStore.getTranslatedText('Entry_Safety_Backup') }}</p>
        <p><AppIcon name="file" :size="15" />{{ palStore.getTranslatedText('Entry_Safety_Platforms') }}</p>
      </footer>
    </section>

    <dialog
      ref="modInstallDialog"
      class="mod-install-dialog"
      aria-labelledby="mod-install-title"
      @click.self="closeModInstallDialog"
    >
      <article>
        <header class="mod-install-dialog__header">
          <span><AppIcon name="check" :size="20" /></span>
          <div>
            <small>{{ palStore.getTranslatedText('Remote_ModDownloadComplete') }}</small>
            <h2 id="mod-install-title">{{ palStore.getTranslatedText('Remote_ModInstallDialogTitle') }}</h2>
          </div>
          <button
            type="button"
            :aria-label="palStore.getTranslatedText('Remote_ModInstallClose')"
            @click="closeModInstallDialog"
          >
            <AppIcon name="x" :size="17" />
          </button>
        </header>

        <section class="mod-download-result">
          <AppIcon name="folder" :size="17" />
          <div>
            <span>{{ palStore.getTranslatedText('Remote_ModDownloadSavedAt') }}</span>
            <code>{{ bridgeModDownloadResult?.path }}</code>
          </div>
        </section>

        <ol class="mod-install-steps">
          <li>
            <span>1</span>
            <div>
              <strong>{{ palStore.getTranslatedText('Remote_ModInstallPrerequisiteTitle') }}</strong>
              <p>{{ palStore.getTranslatedText('Remote_ModInstallPrerequisiteHint') }}</p>
              <dl class="mod-path-list">
                <div>
                  <dt>{{ palStore.getTranslatedText('Remote_ModInstallClientPath') }}</dt>
                  <dd><code>{{ windowsClientUe4ssPath }}</code></dd>
                </div>
                <div>
                  <dt>{{ palStore.getTranslatedText('Remote_ModInstallXgpClientPath') }}</dt>
                  <dd><code>{{ windowsXgpClientUe4ssPath }}</code></dd>
                </div>
                <div>
                  <dt>{{ palStore.getTranslatedText('Remote_ModInstallServerPath') }}</dt>
                  <dd><code>{{ windowsServerUe4ssPath }}</code></dd>
                </div>
              </dl>
            </div>
          </li>
          <li>
            <span>2</span>
            <div>
              <strong>{{ palStore.getTranslatedText('Remote_ModInstallBridgeTitle') }}</strong>
              <p>{{ palStore.getTranslatedText('Remote_ModInstallBridgeHint') }}</p>
              <dl class="mod-path-list">
                <div>
                  <dt>{{ palStore.getTranslatedText('Remote_ModInstallModsPath') }}</dt>
                  <dd><code>{{ bridgeModPrimaryPath }}</code></dd>
                </div>
                <div>
                  <dt>{{ palStore.getTranslatedText('Remote_ModInstallModsPathFallback') }}</dt>
                  <dd><code>{{ bridgeModFallbackPath }}</code></dd>
                </div>
              </dl>
            </div>
          </li>
        </ol>

        <aside class="mod-server-note" role="note">
          <AppIcon name="warning" :size="16" />
          <div>
            <strong>{{ palStore.getTranslatedText('Remote_ModInstallServerConfigTitle') }}</strong>
            <p>{{ palStore.getTranslatedText('Remote_ModInstallServerConfigHint') }}</p>
            <code>{{ serverRestConfiguration }}</code>
          </div>
        </aside>

        <p class="mod-install-restart">{{ palStore.getTranslatedText('Remote_ModInstallRestart') }}</p>
        <footer>
          <a :href="ue4ssReleasesUrl" target="_blank" rel="noreferrer">
            {{ palStore.getTranslatedText('Remote_ModOpenUe4ssReleases') }}
          </a>
          <button class="button button--primary" type="button" @click="closeModInstallDialog">
            {{ palStore.getTranslatedText('Remote_ModInstallClose') }}
          </button>
        </footer>
      </article>
    </dialog>
    <p class="version-info">{{ palStore.VERSION }}</p>
  </main>
</template>

<style scoped>
#entryDiv {
  position: relative;
  width: min(1112px, calc(100vw - 48px));
  min-height: 100dvh;
  margin: 0 auto;
  padding: 104px 0 36px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.entry-shell {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  width: 100%;
  height: clamp(620px, calc(100dvh - 176px), 750px);
  min-height: 0;
  overflow: hidden;
  background: var(--ui-surface);
  border: 1px solid var(--ui-border);
  border-radius: 0;
  box-shadow: var(--ui-shadow-md);
}

.entry-intro {
  display: grid;
  grid-template-columns: 60px minmax(0, 1fr);
  align-items: start;
  gap: 16px;
  padding: 30px 28px 18px;
}

.logo {
  border-radius: 15px;
  box-shadow: 0 1px 0 oklch(0.6 0.03 252 / 0.16) inset, var(--ui-shadow-md);
}

.entry-intro-copy { min-width: 0; }
.entry-support-copy { grid-column: 1 / -1; min-width: 0; }

.product-name {
  margin: 0 0 5px;
  color: var(--ui-accent-strong);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.045em;
  text-transform: uppercase;
}

h1, h2, p { margin: 0; }

h1 {
  color: var(--ui-text);
  max-width: 20ch;
  font-size: clamp(30px, 3vw, 40px);
  line-height: 1.12;
  font-weight: 690;
  letter-spacing: -0.035em;
  text-wrap: balance;
}

.entry-copy {
  max-width: 72ch;
  margin-top: 0;
  color: var(--ui-text-muted);
  font-size: 14px;
  line-height: 1.65;
  text-wrap: pretty;
}

.free-notice {
  display: inline-flex;
  align-items: center;
  margin-top: 8px;
  padding: 4px 9px;
  color: var(--ui-success);
  background: oklch(0.25 0.055 158);
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
}

.entry-workspace {
  display: grid;
  grid-template-columns: 323px minmax(0, 1fr);
  min-height: 0;
  border-top: 1px solid var(--ui-border);
  border-bottom: 1px solid var(--ui-border);
}

.source-switch {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
  padding: 18px 20px;
  border-right: 1px solid var(--ui-border);
}

.source-switch label {
  position: relative;
  display: grid;
  grid-template-columns: 38px minmax(0, 1fr);
  align-items: center;
  gap: 12px;
  min-height: 64px;
  padding: 0 14px;
  color: var(--ui-text-muted);
  border: 1px solid transparent;
  border-radius: var(--ui-radius-sm);
  cursor: pointer;
  transition: color 160ms ease, background-color 160ms ease, border-color 160ms ease;
}

.source-switch label::before {
  position: absolute;
  inset: 8px auto 8px -1px;
  width: 3px;
  background: transparent;
  border-radius: 0 3px 3px 0;
  content: '';
}

.source-switch label:hover:not(.active) { color: var(--ui-text-secondary); background: var(--ui-surface-raised); }
.source-switch label.active {
  color: var(--ui-text);
  background: var(--ui-accent-soft);
  border-color: var(--ui-accent);
}
.source-switch label.active::before { background: var(--ui-accent); }
.source-switch label:has(input:focus-visible) { outline: 2px solid var(--ui-accent); outline-offset: 2px; }
.source-switch input { position: absolute; opacity: 0; pointer-events: none; }
.source-icon {
  display: grid;
  width: 38px;
  height: 38px;
  place-items: center;
  border-radius: 50%;
}
.source-icon img { display: block; opacity: .88; }
.source-icon--offline,
.source-icon--migration,
.source-icon--remote { color: var(--ui-accent-strong); }
.source-label-text { display: flex; align-items: center; gap: 8px; min-width: 0; }
.source-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 620; }
.beta-badge {
  padding: 2px 6px;
  color: var(--ui-text-secondary);
  background: var(--ui-surface-raised);
  border-radius: 999px;
  font-size: 9px;
  font-weight: 760;
  letter-spacing: .08em;
  line-height: 1.5;
}

.entry-panel {
  display: flex;
  flex-direction: column;
  width: 100%;
  min-height: 0;
  overflow-y: auto;
  padding: 28px 28px 26px;
}

.offline-platform-switch {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: -4px 0 20px;
  padding-bottom: 18px;
  border-bottom: 1px solid var(--ui-border);
}

.offline-platform-switch > span {
  margin-right: auto;
  color: var(--ui-text-muted);
  font-size: 11px;
  font-weight: 650;
  letter-spacing: .04em;
}

.offline-platform-switch label {
  position: relative;
  display: inline-flex;
  min-width: 104px;
  min-height: 36px;
  align-items: center;
  justify-content: center;
  gap: 7px;
  padding: 0 12px;
  color: var(--ui-text-muted);
  background: var(--ui-canvas);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
  font-size: 12px;
  font-weight: 650;
  cursor: pointer;
  transition: color 160ms ease, background-color 160ms ease, border-color 160ms ease;
}

.offline-platform-switch label:hover:not(.active) {
  color: var(--ui-text-secondary);
  border-color: var(--ui-border-strong);
}

.offline-platform-switch label.active {
  color: var(--ui-text);
  background: var(--ui-accent-soft);
  border-color: var(--ui-accent);
}

.offline-platform-switch label:has(input:focus-visible) {
  outline: 2px solid var(--ui-accent);
  outline-offset: 2px;
}

.offline-platform-switch input {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}

.offline-platform-switch img { display: block; opacity: .9; }

.panel-heading h2 {
  color: var(--ui-text);
  font-size: 18px;
  font-weight: 680;
  letter-spacing: -0.015em;
}

.panel-heading p,
.path-current {
  margin-top: 6px;
  color: var(--ui-text-muted);
  font-size: 13px;
  line-height: 1.6;
}

.save-path-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 118px;
  gap: 10px;
  margin-top: 18px;
}

.path-field { display: block; min-width: 0; }

.path-field input {
  box-sizing: border-box;
  width: 100%;
  min-height: 44px;
  padding: 0 13px;
  color: var(--ui-text);
  background: var(--ui-canvas);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
  font: inherit;
  font-size: 13px;
}

.remote-connect-form {
  display: flex;
  flex-shrink: 0;
  flex-direction: column;
  min-height: 0;
}

.xgp-path-row {
  grid-template-columns: minmax(0, 1fr) 150px;
}

.xgp-path-row .button { white-space: nowrap; }

.remote-platform-notice {
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr);
  align-items: center;
  gap: 10px;
  margin: 14px 0 10px;
  padding: 9px 11px;
  color: oklch(0.79 0.12 78);
  background: color-mix(in srgb, oklch(0.72 0.13 78) 9%, var(--ui-surface-raised));
  border-left: 3px solid oklch(0.72 0.13 78);
}

.remote-platform-notice > span {
  display: grid;
  width: 30px;
  height: 30px;
  place-items: center;
  background: color-mix(in srgb, oklch(0.72 0.13 78) 14%, transparent);
  border-radius: 6px;
}

.remote-platform-notice > div { display: grid; gap: 2px; min-width: 0; }
.remote-platform-notice strong { color: var(--ui-text); font-size: 11px; }
.remote-platform-notice p { color: var(--ui-text-secondary); font-size: 10px; line-height: 1.45; }

.remote-mod-notice {
  display: grid;
  grid-template-columns: 38px minmax(0, 1fr) auto;
  align-items: center;
  gap: 11px;
  margin-bottom: 12px;
  padding: 12px;
  color: var(--ui-accent-strong);
  background: color-mix(in srgb, var(--ui-accent) 9%, var(--ui-surface-raised));
  border: 1px solid color-mix(in srgb, var(--ui-accent) 34%, var(--ui-border));
  border-radius: var(--ui-radius-sm);
}

.remote-mod-notice__icon {
  display: grid;
  width: 38px;
  height: 38px;
  place-items: center;
  background: var(--ui-accent-soft);
  border: 1px solid color-mix(in srgb, var(--ui-accent) 35%, var(--ui-border));
  border-radius: 8px;
}

.remote-mod-notice > div { display: grid; gap: 3px; min-width: 0; }
.remote-mod-notice strong { color: var(--ui-text); font-size: 12px; }
.remote-mod-notice p { color: var(--ui-text-secondary); font-size: 11px; line-height: 1.5; }
.remote-mod-notice small { color: var(--ui-text-muted); font-size: 9px; line-height: 1.45; }
.remote-mod-download-error { color: var(--ui-danger, #ff8d8d) !important; }
.remote-mod-download { display: inline-flex; min-width: 112px; align-items: center; justify-content: center; gap: 7px; }
.local-connect-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 14px;
  color: var(--ui-text-secondary);
  background: var(--ui-surface-raised);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
}

.local-connect-card strong {
  color: var(--ui-text);
  font-size: 13px;
}

.local-connect-card p {
  max-width: 570px;
  margin: 4px 0 0;
  color: var(--ui-text-muted);
  font-size: 11px;
  line-height: 1.5;
}

.local-connect-card .button {
  flex: 0 0 auto;
}

.remote-divider {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
  color: var(--ui-text-muted);
  font-size: 10px;
}

.remote-divider::before,
.remote-divider::after {
  flex: 1;
  height: 1px;
  background: var(--ui-border);
  content: "";
}

.remote-field {
  display: grid;
  gap: 6px;
  margin-top: 14px;
  color: var(--ui-text-secondary);
  font-size: 12px;
}

.remote-field input {
  box-sizing: border-box;
  width: 100%;
  min-height: 42px;
  padding: 0 13px;
  color: var(--ui-text);
  background: var(--ui-canvas);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
  font: inherit;
}

.remote-field input:focus {
  outline: 0;
  border-color: var(--ui-accent);
  box-shadow: 0 0 0 3px oklch(0.72 0.14 246 / 0.16);
}


.remote-dashboard {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  gap: 14px;
  min-height: 0;
  margin-top: 18px;
}

.remote-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 13px 14px;
  background: var(--ui-surface-raised);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
}

.remote-summary > div { display: grid; gap: 3px; min-width: 0; }
.remote-summary span,
.remote-section > span,
.remote-metrics span {
  color: var(--ui-text-muted);
  font-size: 10px;
  letter-spacing: .04em;
  text-transform: uppercase;
}
.remote-summary strong { overflow: hidden; color: var(--ui-text); text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
.remote-summary small { color: var(--ui-text-muted); font-size: 10px; }
.remote-state {
  flex: 0 0 auto;
  padding: 4px 8px;
  color: var(--ui-danger, #ff8d8d);
  background: color-mix(in srgb, var(--ui-danger, #ef4444) 10%, transparent);
  border-radius: 999px;
  font-size: 10px;
}
.remote-state.ready { color: var(--ui-success); background: color-mix(in srgb, var(--ui-success) 12%, transparent); }

.remote-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}
.remote-metrics > div {
  display: grid;
  gap: 5px;
  padding: 10px 12px;
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
}
.remote-metrics strong { color: var(--ui-text); font-size: 14px; }
.remote-section { display: grid; gap: 7px; min-height: 0; }
.capability-list { display: flex; flex-wrap: wrap; gap: 6px; }
.capability-list code {
  padding: 4px 7px;
  color: var(--ui-text-secondary);
  background: var(--ui-canvas);
  border: 1px solid var(--ui-border);
  border-radius: 5px;
  font-size: 10px;
}
.remote-player-section { overflow: hidden; }
.remote-player-list { display: grid; gap: 5px; overflow-y: auto; }
.remote-player-list > div {
  display: flex;
  justify-content: space-between;
  padding: 6px 9px;
  color: var(--ui-text-secondary);
  background: var(--ui-surface-raised);
  border-radius: 5px;
  font-size: 11px;
}
.remote-player-list small { color: var(--ui-text-muted); }
.remote-development-note { color: var(--ui-text-muted); font-size: 10px; line-height: 1.5; }
.remote-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: auto; }

.path-field input:hover:not(:disabled) { border-color: var(--ui-border-strong); }
.path-field input:focus { outline: 0; border-color: var(--ui-accent); box-shadow: 0 0 0 3px oklch(0.72 0.14 246 / 0.16); }

.entry-primary-row { display: flex; justify-content: flex-end; margin-top: 24px; }
.entry-primary-row .button { min-width: 204px; min-height: 44px; }
.xgp-entry-actions {
  gap: 10px;
  margin-top: auto;
  padding-top: 12px;
}
.xgp-entry-actions .button { min-width: 168px; }

.button {
  min-height: 40px;
  padding: 0 14px;
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
  font: inherit;
  cursor: pointer;
  transition: background-color 160ms ease, border-color 160ms ease;
}

.button--quiet { background: var(--ui-surface-raised); color: var(--ui-text-secondary); }
.button--primary { background: var(--ui-accent); border-color: var(--ui-accent); color: oklch(0.16 0.025 252); }
.button:hover:not(:disabled) { border-color: var(--ui-border-strong); background: var(--ui-surface-hover); }
.button--primary:hover:not(:disabled) { background: var(--ui-accent-strong); border-color: var(--ui-accent-strong); }
.button:disabled { opacity: .5; cursor: not-allowed; }

.path-current { overflow-wrap: anywhere; }
.global-palbox-note {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  margin-top: 14px;
  padding: 10px 12px;
  color: var(--ui-text-secondary);
  background: var(--ui-surface-raised);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
  font-size: 11px;
  line-height: 1.5;
}
.global-palbox-note :deep(svg) { flex: 0 0 auto; margin-top: 1px; color: var(--ui-accent-strong); }
.entry-error {
  margin-top: 10px;
  padding: 9px 11px;
  color: var(--ui-danger, #ff8d8d);
  background: color-mix(in srgb, var(--ui-danger, #ef4444) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--ui-danger, #ef4444) 34%, transparent);
  border-radius: var(--ui-radius-sm);
  font-size: 12px;
  line-height: 1.55;
}
.entry-error > p { margin: 0; }
.entry-error details { margin-top: 6px; color: var(--ui-text-muted); }
.entry-error summary { width: fit-content; cursor: pointer; }
.entry-error code {
  display: block;
  margin-top: 5px;
  overflow-wrap: anywhere;
  color: var(--ui-text-secondary);
  font-size: 11px;
  white-space: pre-wrap;
}
.xgp-sources {
  display: grid;
  flex: 1 1 0;
  grid-auto-rows: max-content;
  align-content: start;
  gap: 7px;
  min-height: 0;
  overflow-y: auto;
  margin: 12px 0 14px;
}
.xgp-entry-sources {
  min-height: 72px;
  padding-right: 4px;
  margin-bottom: 8px;
  scrollbar-gutter: stable;
}
.xgp-source {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 10px;
  color: var(--ui-text-secondary);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
  cursor: pointer;
  transition: color 160ms ease, background-color 160ms ease, border-color 160ms ease;
}
.xgp-source:hover:not(:has(input:checked)) { background: var(--ui-surface-hover); border-color: var(--ui-border-strong); }
.xgp-source:has(input:focus-visible) { outline: 2px solid var(--ui-accent); outline-offset: -2px; }
.xgp-source:has(input:checked) { border-color: var(--ui-accent); background: var(--ui-accent-soft); }
.xgp-source input { width: 14px; height: 14px; margin: 0; accent-color: var(--ui-accent); }
.xgp-source span { display: grid; gap: 3px; min-width: 0; }
.xgp-source strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; }
.xgp-source small, .xgp-source em { color: var(--ui-text-muted); font-size: 10px; font-style: normal; }
.xgp-source:has(input:checked) strong { color: var(--ui-text); }
.xgp-source:has(input:checked) em { color: var(--ui-accent-strong); }
.entry-safety {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  min-height: 68px;
  padding: 0 28px;
  color: var(--ui-text-muted);
  font-size: 11px;
}
.entry-safety p { display: inline-flex; align-items: center; gap: 7px; }
.version-info { color: var(--ui-text-muted); font-size: 11px; letter-spacing: 0.025em; }

.button:focus-visible,
.mod-install-dialog button:focus-visible,
.mod-install-dialog a:focus-visible {
  outline: 2px solid var(--ui-accent);
  outline-offset: 2px;
}

.mod-install-dialog {
  width: min(720px, calc(100vw - 40px));
  max-height: min(820px, calc(100dvh - 40px));
  padding: 0;
  overflow: auto;
  color: var(--ui-text);
  background: var(--ui-surface);
  border: 1px solid var(--ui-border-strong);
  border-radius: var(--ui-radius-lg);
  box-shadow: var(--ui-shadow-md);
}

.mod-install-dialog::backdrop { background: oklch(0.08 0.02 252 / .78); backdrop-filter: blur(5px); }
.mod-install-dialog > article { display: grid; gap: 16px; padding: 20px; }
.mod-install-dialog__header { display: grid; grid-template-columns: 42px minmax(0, 1fr) 34px; align-items: center; gap: 11px; padding-bottom: 14px; border-bottom: 1px solid var(--ui-border); }
.mod-install-dialog__header > span { display: grid; width: 42px; height: 42px; place-items: center; color: var(--ui-success); background: color-mix(in srgb, var(--ui-success) 12%, var(--ui-surface-raised)); border-radius: 9px; }
.mod-install-dialog__header > div { display: grid; gap: 3px; min-width: 0; }
.mod-install-dialog__header small { color: var(--ui-success); font-size: 9px; font-weight: 720; letter-spacing: .06em; text-transform: uppercase; }
.mod-install-dialog__header h2 { font-size: 18px; }
.mod-install-dialog__header > button { display: grid; width: 34px; height: 34px; padding: 0; place-items: center; color: var(--ui-text-muted); background: transparent; border: 1px solid transparent; border-radius: 7px; cursor: pointer; }
.mod-install-dialog__header > button:hover { color: var(--ui-text); background: var(--ui-surface-hover); border-color: var(--ui-border); }

.mod-download-result { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 9px; padding: 10px 12px; color: var(--ui-accent); background: var(--ui-accent-soft); border-left: 3px solid var(--ui-accent); }
.mod-download-result > div { display: grid; gap: 4px; min-width: 0; }
.mod-download-result span { color: var(--ui-text-secondary); font-size: 10px; }
.mod-download-result code,
.mod-path-list code,
.mod-server-note code { overflow-wrap: anywhere; color: var(--ui-text); font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 10px; }

.mod-install-steps { display: grid; gap: 14px; margin: 0; padding: 0; list-style: none; }
.mod-install-steps > li { display: grid; grid-template-columns: 30px minmax(0, 1fr); gap: 12px; }
.mod-install-steps > li > span { display: grid; width: 30px; height: 30px; place-items: center; color: var(--ui-accent); background: var(--ui-accent-soft); border: 1px solid color-mix(in srgb, var(--ui-accent) 34%, var(--ui-border)); border-radius: 7px; font-size: 11px; font-weight: 760; font-variant-numeric: tabular-nums; }
.mod-install-steps > li > div { display: grid; gap: 6px; min-width: 0; }
.mod-install-steps strong { color: var(--ui-text); font-size: 12px; }
.mod-install-steps p { color: var(--ui-text-secondary); font-size: 10px; line-height: 1.55; }
.mod-path-list { display: grid; gap: 6px; margin: 2px 0 0; }
.mod-path-list > div { display: grid; grid-template-columns: 118px minmax(0, 1fr); align-items: center; gap: 9px; padding: 7px 9px; background: var(--ui-canvas); border: 1px solid var(--ui-border); }
.mod-path-list dt { color: var(--ui-text-muted); font-size: 9px; }
.mod-path-list dd { min-width: 0; margin: 0; }

.mod-server-note { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 9px; padding: 10px 12px; color: oklch(0.79 0.12 78); background: color-mix(in srgb, oklch(0.72 0.13 78) 9%, var(--ui-canvas)); border: 1px solid color-mix(in srgb, oklch(0.72 0.13 78) 28%, var(--ui-border)); }
.mod-server-note > div { display: grid; gap: 3px; min-width: 0; }
.mod-server-note strong { color: var(--ui-text); font-size: 10px; }
.mod-server-note p { color: var(--ui-text-secondary); font-size: 9px; line-height: 1.5; }
.mod-server-note code { color: oklch(0.86 0.08 78); }
.mod-install-restart { color: var(--ui-text-muted); font-size: 10px; line-height: 1.55; }
.mod-install-dialog footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding-top: 2px; }
.mod-install-dialog footer a { color: var(--ui-accent-strong); font-size: 10px; text-decoration: none; }
.mod-install-dialog footer a:hover { text-decoration: underline; }
.mod-install-dialog footer .button { min-width: 112px; }
@media (max-width: 920px) {
  .entry-workspace { grid-template-columns: 250px minmax(0, 1fr); }
  .source-switch { padding-inline: 12px; }
  .entry-panel { padding-inline: 24px; }
}

@media (max-width: 760px) {
  #entryDiv { width: min(100% - 28px, 640px); padding-top: 82px; }
  .entry-shell { height: auto; min-height: 0; overflow: visible; }
  .entry-intro { grid-template-columns: 56px minmax(0, 1fr); gap: 14px; padding: 22px 20px; }
  .logo { width: 56px; height: 56px; border-radius: 13px; }
  .entry-workspace { grid-template-columns: 1fr; }
  .source-switch {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    padding: 12px;
    border-right: 0;
    border-bottom: 1px solid var(--ui-border);
  }
  .source-switch label { min-height: 64px; padding-inline: 6px; }
  .source-icon { display: none; }
  .source-switch label { grid-template-columns: minmax(0, 1fr); gap: 7px; }
  .source-switch .source-label-text {
    flex-direction: column;
    justify-content: center;
    gap: 2px;
  }
  .source-switch .source-name {
    overflow: visible;
    font-size: 11px;
    line-height: 1.25;
    text-align: center;
    white-space: normal;
  }
  .source-switch .beta-badge { padding: 1px 4px; font-size: 8px; }
  .entry-panel { min-height: 360px; padding: 22px 20px; }
  .offline-platform-switch { flex-wrap: wrap; margin-top: 0; }
  .offline-platform-switch > span { flex: 1 0 100%; }
  .offline-platform-switch label { flex: 1 1 0; }
  .save-path-row { grid-template-columns: 1fr; }
  .xgp-entry-actions { flex-direction: column; margin-top: 16px; }
  .xgp-entry-actions .button { min-width: 0; }
  .remote-mod-notice { grid-template-columns: 38px minmax(0, 1fr); }
  .remote-mod-download { grid-column: 1 / -1; width: 100%; }
  .mod-path-list > div { grid-template-columns: 1fr; gap: 4px; }
  .mod-install-dialog footer { align-items: stretch; flex-direction: column; }
  .mod-install-dialog footer .button { width: 100%; }
  .entry-primary-row .button { width: 100%; }
  .entry-safety { align-items: flex-start; flex-direction: column; gap: 7px; padding: 12px 20px; }
  h1 { max-width: 22ch; }
}

@media (prefers-reduced-motion: reduce) {
  .button,
  .offline-platform-switch label,
  .source-switch label { transition: none; }
}
</style>
