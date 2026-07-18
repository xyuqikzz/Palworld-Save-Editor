<script setup>
import { usePalEditorStore } from '@/stores/paleditor'
import AppIcon from './AppIcon.vue'
const palStore = usePalEditorStore()

defineProps(['icon', 'name', 'value', 'title'])
defineEmits([])
</script>

<template>
    <button :name="name" :value="value" :title="title" :disabled="palStore.LOADING_FLAG">
        <AppIcon :name="icon" />
    </button>
</template>

<style scoped>
button {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 2rem;
    height: 2rem;
    padding: 0;
    margin: 0;
    background: var(--ui-surface);
    color: var(--ui-text-muted);
    border: 1px solid var(--ui-border);
    border-radius: 7px;
    transition: background-color 160ms ease, border-color 160ms ease, color 160ms ease;
    cursor: pointer;
}

button:hover {
    background: var(--ui-accent-soft);
    color: var(--ui-accent);
    border-color: var(--ui-accent);
}

button:disabled {
    opacity: 0.48;
}
</style>
