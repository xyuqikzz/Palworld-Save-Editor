<script setup>
import { usePalEditorStore } from '@/stores/paleditor'
import { computed } from '@vue/reactivity';
import { ref, onMounted } from 'vue'

import IconButton from './modules/IconButton.vue';
import InputArea from './modules/InputArea.vue'
import BarButton from './modules/BarButton.vue'
import AppIcon from './modules/AppIcon.vue'
const palStore = usePalEditorStore()

const sortedPathChildren = computed(() => {
    return Array.from(palStore.PATH_CONTEXT.entries()).sort((a, b) => {
        if (a[1].isDir && !b[1].isDir) {
            return -1;
        } else if (!a[1].isDir && b[1].isDir) {
            return 1;
        }

        return a[1].filename.localeCompare(b[1].filename);
    })
})

const isLocalDataPicker = computed(
    () => palStore.FILE_PICKER_PURPOSE === 'local-data',
)
const isXgpPicker = computed(
    () => palStore.FILE_PICKER_PURPOSE === 'xgp',
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

const isSelectedFile = (path) => (
    (isLocalDataPicker.value || isXgpPicker.value)
    && palStore.PAL_FILE_PICKER_SELECTION === path
)

const pickerConfirmationDisabled = computed(() => {
    if (palStore.FILE_PICKER_PURPOSE === 'steam') {
        return !palStore.IS_PAL_SAVE_PATH
    }
    if (isLocalDataPicker.value) {
        return !palStore.PAL_FILE_PICKER_SELECTION
    }
    return false
})

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

// const scrollElement = ref(null);

// const checkScroll = () => {
//     if (!scrollElement.value) return;
//     const scrollTop = scrollElement.value.scrollTop;
//     const scrollHeight = scrollElement.value.scrollHeight;
//     const clientHeight = scrollElement.value.clientHeight;

//     scrollElement.value.classList.toggle('scrolled-top', scrollTop > 0);
//     scrollElement.value.classList.toggle('scrolled-bottom', scrollTop + clientHeight < scrollHeight);
// };

// onMounted(() => {
//     if (scrollElement.value) {
//         scrollElement.value.addEventListener('scroll', checkScroll);
//         checkScroll(); // Initial check to update shadow state
//     }
// });
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
            <div class="currentPath">
                <IconButton icon="back" :title="palStore.getTranslatedText('PathPicker_ParentDirectory')" @click="palStore.path_back" />
                <InputArea v-model="palStore.PAL_FILE_PICKER_PATH" />
                <IconButton icon="forward" :title="palStore.getTranslatedText('PathPicker_OpenPath')" @click="palStore.update_picker_result(palStore.PAL_FILE_PICKER_PATH)" />
                <button class="close-btn" @click="abort" :title="palStore.getTranslatedText('Common_Close')" :aria-label="palStore.getTranslatedText('Common_Close')"><AppIcon name="x" :size="17" /></button>
            </div>

            <ul ref="scrollElement">
                <li
                    v-for="([key, value]) of sortedPathChildren"
                    :key="key"
                    :isdir="value.isDir"
                    :class="{
                        'path-entry--selectable': value.isDir || isSelectableFile(value),
                        'path-entry--selected': isSelectedFile(key),
                        'path-entry--disabled': !value.isDir && ((isLocalDataPicker && !isLocalDataFile(value)) || (isXgpPicker && !isXgpIndexFile(value))),
                    }"
                    :tabindex="value.isDir || isSelectableFile(value) ? 0 : undefined"
                    :aria-selected="!value.isDir && (isLocalDataPicker || isXgpPicker) ? isSelectedFile(key) : undefined"
                    @click="selectPathEntry(key, value)"
                    @keydown.enter.prevent="selectPathEntry(key, value)"
                    @keydown.space.prevent="selectPathEntry(key, value)"
                    :fullpath="key"
                >
                    <AppIcon :name="value.isDir ? 'folder' : 'file'" :size="17" />
                    <span class="path-entry-name">{{ value.filename }}</span>
                </li>
            </ul>
            <BarButton
                @click="savePickerResult"
                :content="palStore.getTranslatedText('Common_Confirm')"
                :disabled="pickerConfirmationDisabled"
            />
        </div>
    </div>
</template>

<style scoped>
.modal-overlay {
    position: fixed;
    inset: 0;
    width: 100%;
    height: 100%;
    background: oklch(0.18 0.025 252 / 0.58);
    backdrop-filter: blur(5px);
    display: flex;
    justify-content: center;
    align-items: center;
    z-index: 1000;
}

.popup {
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);

    width: min(900px, calc(100vw - 32px));
    height: min(640px, calc(100vh - 48px));
    border: 1px solid var(--ui-border);
    border-radius: var(--ui-radius-lg);
    padding: 28px;
    background: var(--ui-surface);
    z-index: 10;
    box-shadow: 0 24px 80px oklch(0.22 0.035 250 / 0.28);

    display: flex;
    flex-direction: column;
    gap: 18px;
}

.popup .currentPath {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto auto;
    gap: 10px;
    align-items: center;
}

.popup ul {
    overflow-y: auto;
    list-style-type: none;
    padding: 4px;
    flex: 1;
}

.popup li.path-entry--selectable {
    cursor: pointer;
}

.popup li {
    display: flex;
    align-items: center;
    gap: 9px;
    min-width: 0;
    margin: 2px;
    padding: 9px 10px;
    border: 1px solid transparent;
    border-radius: 7px;
    color: var(--ui-text-muted);
}

.path-entry-name {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;

    white-space: nowrap;
}

.popup li.path-entry--selected {
    color: var(--ui-text);
    background: var(--ui-accent-soft);
    border-color: var(--ui-accent);
}

.popup li.path-entry--disabled {
    opacity: 0.42;
}

.popup li.path-entry--selectable:hover {
    color: var(--ui-text);
    background: var(--ui-surface-raised);
    border-color: var(--ui-border);
}

.close-btn {
    flex: 0 0 auto;
    background: transparent;
    border-radius: 7px;
    width: 2rem;
    height: 2rem;
    border: 1px solid var(--ui-border);
    color: var(--ui-text-muted);
    display: grid;
    place-content: center;
    cursor: pointer;
}

.close-btn:hover {
    background: var(--ui-surface-raised);
    color: var(--ui-text);
}
</style>
