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

const savePickerResult = () => {
    palStore.SHOW_FILE_PICKER = false
    palStore.PAL_GAME_SAVE_PATH = palStore.PAL_FILE_PICKER_PATH

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
}
</script>

<template>
    <div class="modal-overlay" v-if="palStore.SHOW_FILE_PICKER" @click.self="abort">
        <div class="popup">
            <button class="close-btn" @click="abort" :title="palStore.getTranslatedText('Common_Close')" :aria-label="palStore.getTranslatedText('Common_Close')"><AppIcon name="x" :size="17" /></button>
            <div class="currentPath">
                <IconButton icon="back" :title="palStore.getTranslatedText('PathPicker_ParentDirectory')" @click="palStore.path_back" />
                <InputArea v-model="palStore.PAL_FILE_PICKER_PATH" />
                <IconButton icon="forward" :title="palStore.getTranslatedText('PathPicker_OpenPath')" @click="palStore.update_picker_result(palStore.PAL_FILE_PICKER_PATH)" />
            </div>

            <ul ref="scrollElement">
                <li v-for="([key, value], index) of sortedPathChildren" :key="index" :isdir="value.isDir"
                    @click="() => { if (value.isDir) palStore.update_picker_result(key) }" :fullpath="key">
                    <AppIcon :name="value.isDir ? 'folder' : 'file'" :size="17" /> {{ value.filename }}
                </li>
            </ul>
            <BarButton @click="savePickerResult" :content="palStore.getTranslatedText('Common_Confirm')" :disabled="!palStore.IS_PAL_SAVE_PATH" />
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
    display: flex;
    gap: 10px;
    align-items: center;
}

.popup ul {
    overflow-y: auto;
    list-style-type: none;
    padding: 4px;
    flex: 1;
}

.popup li[isdir=true] {
    cursor: pointer;
}

.popup li {
    margin: 2px;
    padding: 9px 10px;
    border: 1px solid transparent;
    border-radius: 7px;
    color: var(--ui-text-muted);
}

.popup li:hover[isdir=true] {
    color: var(--ui-text);
    background: var(--ui-surface-raised);
    border-color: var(--ui-border);
}

.close-btn {
    position: absolute;
    top: 10px;
    right: 10px;
    background: transparent;
    border-radius: 7px;
    width: 30px;
    height: 30px;
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
