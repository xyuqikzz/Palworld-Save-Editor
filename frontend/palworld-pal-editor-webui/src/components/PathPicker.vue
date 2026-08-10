<script setup>
import { computed, ref, watch } from 'vue'

import { usePalEditorStore } from '@/stores/paleditor'
import AppIcon from './modules/AppIcon.vue'
import BarButton from './modules/BarButton.vue'
import InputArea from './modules/InputArea.vue'
import PathEntryIcon from './modules/PathEntryIcon.vue'
import { filterAndSortPathEntries } from './modules/path-picker-entries'

const palStore = usePalEditorStore()
const searchQuery = ref('')
const sortMode = ref('modified-desc')

const isLocalDataPicker = computed(
    () => palStore.FILE_PICKER_PURPOSE === 'local-data',
)
const isXgpPicker = computed(
    () => palStore.FILE_PICKER_PURPOSE === 'xgp',
)

const sortedPathChildren = computed(() => filterAndSortPathEntries(
    palStore.PATH_CONTEXT.entries(),
    {
        query: searchQuery.value,
        sortMode: sortMode.value,
        locale: palStore.I18n || undefined,
    },
))

watch(
    () => [palStore.PAL_FILE_PICKER_PATH, palStore.IS_PATH_PICKER_ROOT_VIEW],
    () => { searchQuery.value = '' },
)

const isLocalDataFile = (entry) => (
    !entry.isDir && entry.filename.toLowerCase() === 'localdata.sav'
)
const isXgpIndexFile = (entry) => (
    !entry.isDir && entry.filename.toLowerCase() === 'containers.index'
)
const isSelectableFile = (entry) => (
    (isLocalDataPicker.value && isLocalDataFile(entry))
    || (isXgpPicker.value && isXgpIndexFile(entry))
)
const isDisabledFile = (entry) => (
    !entry.isDir
    && (
        (isLocalDataPicker.value && !isLocalDataFile(entry))
        || (isXgpPicker.value && !isXgpIndexFile(entry))
    )
)

const isSelectedFile = (path) => (
    (isLocalDataPicker.value || isXgpPicker.value)
    && palStore.PAL_FILE_PICKER_SELECTION === path
)

const pickerConfirmationDisabled = computed(() => {
    if (palStore.IS_PATH_PICKER_ROOT_VIEW) return true
    if (palStore.FILE_PICKER_PURPOSE === 'steam') {
        return !palStore.IS_PAL_SAVE_PATH
    }
    if (isLocalDataPicker.value) {
        return !palStore.PAL_FILE_PICKER_SELECTION
    }
    return false
})

const pickerConfirmationLabel = computed(() => (
    isXgpPicker.value && !palStore.PAL_FILE_PICKER_SELECTION
        ? 'PathPicker_Xgp_UseCurrentFolder'
        : 'Common_Confirm'
))

function formatModifiedAt(value) {
    if (!value) return palStore.getTranslatedText('PathPicker_ModifiedUnknown')
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) {
        return palStore.getTranslatedText('PathPicker_ModifiedUnknown')
    }
    return new Intl.DateTimeFormat(palStore.I18n || undefined, {
        dateStyle: 'medium',
        timeStyle: 'short',
    }).format(date)
}

const selectPathEntry = (path, entry) => {
    if (entry.isDir) palStore.update_picker_result(path)
    else if (isSelectableFile(entry)) {
        palStore.PAL_FILE_PICKER_SELECTION = path
    }
}

const savePickerResult = async () => {
    if (isLocalDataPicker.value) {
        await palStore.confirmLocalDataFileSelection(
            palStore.PAL_FILE_PICKER_SELECTION,
        )
        return
    }
    palStore.SHOW_FILE_PICKER = false
    if (palStore.FILE_PICKER_PURPOSE === 'xgp') {
        palStore.XGP_WGS_PATH = palStore.PAL_FILE_PICKER_SELECTION
            || palStore.PAL_FILE_PICKER_PATH
        await palStore.discoverXgpSources()
    } else {
        palStore.PAL_GAME_SAVE_PATH = palStore.PAL_FILE_PICKER_PATH
    }
}

const abort = () => {
    palStore.SHOW_FILE_PICKER = false
    palStore.PAL_FILE_PICKER_SELECTION = null
}
</script>

<template>
    <div class="modal-overlay" v-if="palStore.SHOW_FILE_PICKER" @click.self="abort">
        <div
            class="popup"
            role="dialog"
            aria-modal="true"
            :aria-label="palStore.getTranslatedText(isLocalDataPicker ? 'PlayerMap_LocalData_Select' : 'EntryView_BTN_Path_Picker')"
        >
            <div class="current-path">
                <button
                    type="button"
                    class="location-button location-button--roots"
                    :title="palStore.getTranslatedText('PathPicker_Roots')"
                    :aria-label="palStore.getTranslatedText('PathPicker_Roots')"
                    :disabled="palStore.LOADING_FLAG || palStore.IS_PATH_PICKER_ROOT_VIEW"
                    @click="palStore.show_path_picker_roots"
                >
                    <AppIcon name="computer" :size="17" />
                    <span>{{ palStore.getTranslatedText('PathPicker_Roots') }}</span>
                </button>
                <button
                    type="button"
                    class="location-button location-button--icon"
                    :title="palStore.getTranslatedText('PathPicker_ParentDirectory')"
                    :aria-label="palStore.getTranslatedText('PathPicker_ParentDirectory')"
                    :disabled="palStore.LOADING_FLAG || palStore.IS_PATH_PICKER_ROOT_VIEW"
                    @click="palStore.path_back"
                >
                    <AppIcon name="back" :size="17" />
                </button>
                <div v-if="palStore.IS_PATH_PICKER_ROOT_VIEW" class="root-location" aria-live="polite">
                    <AppIcon name="computer" :size="16" />
                    <span>{{ palStore.getTranslatedText('PathPicker_Roots') }}</span>
                </div>
                <InputArea v-else v-model="palStore.PAL_FILE_PICKER_PATH" />
                <button
                    v-if="!palStore.IS_PATH_PICKER_ROOT_VIEW"
                    type="button"
                    class="location-button location-button--icon"
                    :title="palStore.getTranslatedText('PathPicker_OpenPath')"
                    :aria-label="palStore.getTranslatedText('PathPicker_OpenPath')"
                    :disabled="palStore.LOADING_FLAG"
                    @click="palStore.update_picker_result(palStore.PAL_FILE_PICKER_PATH)"
                >
                    <AppIcon name="forward" :size="17" />
                </button>
                <button
                    type="button"
                    class="location-button location-button--icon"
                    @click="abort"
                    :title="palStore.getTranslatedText('Common_Close')"
                    :aria-label="palStore.getTranslatedText('Common_Close')"
                >
                    <AppIcon name="x" :size="17" />
                </button>
            </div>

            <div class="browser-controls">
                <label class="search-field">
                    <AppIcon name="search" :size="16" />
                    <span class="sr-only">{{ palStore.getTranslatedText('PathPicker_Search') }}</span>
                    <input
                        v-model="searchQuery"
                        type="search"
                        :placeholder="palStore.getTranslatedText('PathPicker_Search')"
                        :aria-label="palStore.getTranslatedText('PathPicker_Search')"
                    />
                </label>
                <label class="sort-field">
                    <span>{{ palStore.getTranslatedText('PathPicker_Sort') }}</span>
                    <select v-model="sortMode" :aria-label="palStore.getTranslatedText('PathPicker_Sort')">
                        <option value="modified-desc">{{ palStore.getTranslatedText('PathPicker_Sort_Modified') }}</option>
                        <option value="name-asc">{{ palStore.getTranslatedText('PathPicker_Sort_Name') }}</option>
                    </select>
                </label>
            </div>

            <div v-if="isXgpPicker" class="picker-guidance" role="note">
                <AppIcon name="info" :size="17" />
                <span>{{ palStore.getTranslatedText('PathPicker_Xgp_SelectionHint') }}</span>
            </div>

            <div class="list-heading" aria-hidden="true">
                <span>{{ palStore.getTranslatedText('PathPicker_Column_Name') }}</span>
                <span>{{ palStore.getTranslatedText('PathPicker_Column_Modified') }}</span>
            </div>

            <ul :aria-label="palStore.getTranslatedText('PathPicker_Entries')">
                <li
                    v-for="([path, entry]) of sortedPathChildren"
                    :key="path"
                    :class="{
                        'path-entry--selectable': entry.isDir || isSelectableFile(entry),
                        'path-entry--selected': isSelectedFile(path),
                        'path-entry--disabled': isDisabledFile(entry),
                        'path-entry--save': entry.isPalDir,
                    }"
                    :tabindex="entry.isDir || isSelectableFile(entry) ? 0 : undefined"
                    :aria-selected="!entry.isDir && (isLocalDataPicker || isXgpPicker) ? isSelectedFile(path) : undefined"
                    :aria-disabled="isDisabledFile(entry) || undefined"
                    :title="isXgpPicker && isDisabledFile(entry) ? palStore.getTranslatedText('PathPicker_Xgp_DisabledFile') : undefined"
                    @click="selectPathEntry(path, entry)"
                    @keydown.enter.prevent="selectPathEntry(path, entry)"
                    @keydown.space.prevent="selectPathEntry(path, entry)"
                >
                    <PathEntryIcon :entry="entry" />
                    <span class="path-entry-primary">
                        <span class="path-entry-name">{{ entry.filename }}</span>
                        <span v-if="entry.isPalDir" class="save-badge">
                            {{ palStore.getTranslatedText('PathPicker_SaveFolder') }}
                        </span>
                    </span>
                    <time
                        class="path-entry-time"
                        :datetime="entry.modifiedAt || undefined"
                    >
                        {{ entry.isRoot ? '' : formatModifiedAt(entry.modifiedAt) }}
                    </time>
                </li>
                <li v-if="!sortedPathChildren.length" class="empty-state" role="status">
                    <AppIcon name="search" :size="20" />
                    <span>{{ palStore.getTranslatedText('PathPicker_NoResults') }}</span>
                </li>
            </ul>

            <BarButton
                class="confirm-button"
                @click="savePickerResult"
                :content="palStore.getTranslatedText(pickerConfirmationLabel)"
                :disabled="pickerConfirmationDisabled"
            />
        </div>
    </div>
</template>

<style scoped>
.modal-overlay {
    position: fixed;
    inset: 0;
    z-index: 1000;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 100%;
    height: 100%;
    background: oklch(0.18 0.025 252 / 0.58);
    backdrop-filter: blur(5px);
}

.popup {
    position: fixed;
    top: 50%;
    left: 50%;
    z-index: 10;
    display: flex;
    flex-direction: column;
    width: min(960px, calc(100vw - 32px));
    height: min(680px, calc(100vh - 48px));
    padding: 24px;
    background: var(--ui-surface);
    border: 1px solid var(--ui-border);
    border-radius: var(--ui-radius-lg);
    box-shadow: var(--ui-shadow-md);
    transform: translate(-50%, -50%);
}

.current-path {
    display: grid;
    grid-template-columns: auto auto minmax(0, 1fr) auto auto;
    gap: 8px;
    align-items: center;
}

.location-button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 36px;
    padding: 0 10px;
    color: var(--ui-text-secondary);
    background: var(--ui-surface-raised);
    border: 1px solid var(--ui-border);
    border-radius: var(--ui-radius-sm);
}

.location-button--roots { gap: 7px; font-size: 12.5px; font-weight: 600; }
.location-button--icon { width: 36px; padding: 0; }
.location-button:hover:not(:disabled) {
    color: var(--ui-accent);
    background: var(--ui-accent-soft);
    border-color: var(--ui-accent);
}
.location-button:disabled { opacity: 0.48; }

.root-location {
    display: flex;
    align-items: center;
    min-width: 0;
    min-height: 36px;
    gap: 8px;
    padding: 0 11px;
    color: var(--ui-text);
    background: var(--ui-surface-raised);
    border: 1px solid var(--ui-border);
    border-radius: var(--ui-radius-sm);
}

.browser-controls {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-top: 16px;
}

.search-field {
    display: flex;
    flex: 1 1 320px;
    align-items: center;
    min-height: 36px;
    gap: 8px;
    padding: 0 10px;
    color: var(--ui-text-muted);
    background: var(--ui-surface-raised);
    border: 1px solid var(--ui-border);
    border-radius: var(--ui-radius-sm);
}

.search-field:focus-within {
    color: var(--ui-accent);
    border-color: var(--ui-accent);
    box-shadow: 0 0 0 3px oklch(0.72 0.14 246 / 0.16);
}

.search-field input {
    width: 100%;
    min-width: 0;
    color: var(--ui-text);
    background: transparent;
    border: 0;
    outline: 0;
}
.search-field input::placeholder { color: var(--ui-text-muted); }

.sort-field {
    display: flex;
    align-items: center;
    flex: 0 0 auto;
    gap: 8px;
    color: var(--ui-text-muted);
    font-size: 12px;
}

.sort-field select {
    min-height: 36px;
    padding: 0 30px 0 10px;
    color: var(--ui-text);
    background: var(--ui-surface-raised);
    border: 1px solid var(--ui-border);
    border-radius: var(--ui-radius-sm);
}

.picker-guidance {
    display: flex;
    align-items: flex-start;
    gap: 9px;
    margin-top: 12px;
    padding: 10px 12px;
    color: var(--ui-text-secondary);
    background: var(--ui-accent-soft);
    border: 1px solid var(--ui-border);
    border-radius: var(--ui-radius-sm);
    font-size: 12.5px;
    line-height: 1.45;
}

.picker-guidance :deep(svg) {
    flex: 0 0 auto;
    margin-top: 1px;
    color: var(--ui-accent);
}

.list-heading {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 176px;
    gap: 16px;
    margin-top: 14px;
    padding: 0 12px 7px 40px;
    color: var(--ui-text-muted);
    border-bottom: 1px solid var(--ui-border);
    font-size: 11.5px;
    font-weight: 600;
}

.popup ul {
    flex: 1;
    min-height: 0;
    margin: 0;
    padding: 5px 3px 10px;
    overflow-y: auto;
    list-style: none;
}

.popup li:not(.empty-state) {
    display: grid;
    grid-template-columns: 24px minmax(0, 1fr) 176px;
    align-items: center;
    min-width: 0;
    min-height: 42px;
    gap: 10px;
    margin: 2px 0;
    padding: 7px 10px;
    color: var(--ui-text-secondary);
    border: 1px solid transparent;
    border-radius: var(--ui-radius-sm);
}

.popup li.path-entry--selectable { cursor: pointer; }
.popup li.path-entry--selectable:hover,
.popup li.path-entry--selectable:focus-visible {
    color: var(--ui-text);
    background: var(--ui-surface-raised);
    border-color: var(--ui-border-strong);
    outline: none;
}

.popup li.path-entry--selected {
    color: var(--ui-text);
    background: var(--ui-accent-soft);
    border-color: var(--ui-accent);
}
.popup li.path-entry--disabled { opacity: 0.44; }
.popup li.path-entry--save { color: var(--ui-text); }

.path-entry-primary {
    display: flex;
    align-items: center;
    min-width: 0;
    gap: 8px;
}
.path-entry-name {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.path-entry-time {
    color: var(--ui-text-muted);
    font-size: 12px;
    white-space: nowrap;
}

.save-badge {
    flex: 0 0 auto;
    padding: 2px 6px;
    color: var(--ui-success);
    background: oklch(0.25 0.045 158);
    border-radius: 5px;
    font-size: 10.5px;
    font-weight: 650;
}

.empty-state {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 180px;
    gap: 9px;
    color: var(--ui-text-muted);
}

.confirm-button {
    flex: 0 0 auto;
    margin: 10px 0 0;
    font-size: 15px;
}

@media (min-width: 1440px) and (min-height: 800px) {
    .popup {
        width: min(1120px, calc(100vw - 64px));
        height: min(760px, calc(100vh - 64px));
        padding: 28px;
    }

    .list-heading {
        grid-template-columns: minmax(0, 1fr) 200px;
        padding-left: 44px;
    }

    .popup li:not(.empty-state) {
        grid-template-columns: 24px minmax(0, 1fr) 200px;
        min-height: 44px;
    }
}

@media (min-width: 1900px) and (min-height: 1000px) {
    .popup {
        width: min(1320px, calc(100vw - 80px));
        height: min(860px, calc(100vh - 80px));
    }
}

@media (max-width: 700px) {
    .popup {
        width: calc(100vw - 20px);
        height: calc(100dvh - 20px);
        padding: 16px;
    }
    .location-button--roots span { display: none; }
    .location-button--roots { width: 36px; padding: 0; }
    .browser-controls { align-items: stretch; flex-direction: column; gap: 8px; }
    .search-field { flex-basis: auto; }
    .sort-field { justify-content: space-between; }
    .sort-field select { flex: 1; }
}

@media (max-width: 540px) {
    .list-heading { grid-template-columns: minmax(0, 1fr); padding-left: 40px; }
    .list-heading span:last-child { display: none; }
    .popup li:not(.empty-state) { grid-template-columns: 24px minmax(0, 1fr); }
    .path-entry-time { grid-column: 2; }
}
</style>
