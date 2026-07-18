<script setup>
import { usePalEditorStore } from '@/stores/paleditor'
const palStore = usePalEditorStore()

defineProps(['content', 'name', 'value'])
</script>

<template>
    <button :name="name" :value="value" :disabled="palStore.LOADING_FLAG">
        {{ content }}
    </button>
</template>

<style scoped>
button {
    margin-bottom: 1rem;
    height: 3rem;
    background: var(--ui-accent);
    color: oklch(0.16 0.025 252);
    border: 1px solid var(--ui-accent);
    outline: none;
    border-radius: 0.5rem;
    font-size: 1.2rem;
    transition: all 0.3s ease-in-out;
}

button:hover {
    background: var(--ui-accent-strong);
    border-color: var(--ui-accent-strong);
    transition: all 0.3s ease-in-out;
    cursor: pointer;
}

button:disabled {
    background: var(--ui-surface-raised);
    color: var(--ui-text-muted);
    border-color: var(--ui-border);
    cursor: auto;
}
</style>
