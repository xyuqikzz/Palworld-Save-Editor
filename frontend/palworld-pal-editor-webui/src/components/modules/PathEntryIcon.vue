<script setup>
import { computed } from 'vue'
import DefaultFileIcon from '@iconify-vue/vscode-icons/default-file'
import DefaultFolderIcon from '@iconify-vue/vscode-icons/default-folder'
import ArchiveFileIcon from '@iconify-vue/vscode-icons/file-type-zip'
import AudioFileIcon from '@iconify-vue/vscode-icons/file-type-audio'
import BackupFileIcon from '@iconify-vue/vscode-icons/file-type-bak'
import BinaryFileIcon from '@iconify-vue/vscode-icons/file-type-binary'
import ConfigFileIcon from '@iconify-vue/vscode-icons/file-type-config'
import ImageFileIcon from '@iconify-vue/vscode-icons/file-type-image'
import JsonFileIcon from '@iconify-vue/vscode-icons/file-type-json'
import MarkdownFileIcon from '@iconify-vue/vscode-icons/file-type-markdown'
import TextFileIcon from '@iconify-vue/vscode-icons/file-type-text'
import VideoFileIcon from '@iconify-vue/vscode-icons/file-type-video'

import AppIcon from './AppIcon.vue'
import { getPathEntryIconKind } from './path-entry-icon'

const props = defineProps({
    entry: {
        type: Object,
        required: true,
    },
    size: {
        type: Number,
        default: 22,
    },
})

const ICON_COMPONENTS = Object.freeze({
    archive: ArchiveFileIcon,
    audio: AudioFileIcon,
    backup: BackupFileIcon,
    binary: BinaryFileIcon,
    config: ConfigFileIcon,
    file: DefaultFileIcon,
    folder: DefaultFolderIcon,
    image: ImageFileIcon,
    json: JsonFileIcon,
    markdown: MarkdownFileIcon,
    text: TextFileIcon,
    video: VideoFileIcon,
})

const iconKind = computed(() => getPathEntryIconKind(props.entry))
const iconComponent = computed(() => ICON_COMPONENTS[iconKind.value] || DefaultFileIcon)
</script>

<template>
    <span class="path-entry-icon" :class="`path-entry-icon--${iconKind}`" aria-hidden="true">
        <AppIcon v-if="iconKind === 'drive'" name="hard-drive" :size="size" />
        <component
            :is="iconComponent"
            v-else
            :width="String(size)"
            :height="String(size)"
        />
    </span>
</template>

<style scoped>
.path-entry-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    flex: 0 0 24px;
}

.path-entry-icon--drive {
    color: var(--ui-accent);
}
</style>
