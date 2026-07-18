<script setup>
import { usePalEditorStore } from '@/stores/paleditor'
const palStore = usePalEditorStore()

defineProps(['placeholder'])
const model = defineModel()

</script>

<template>
    <input type="text" v-model="model" :placeholder="placeholder" :disabled="palStore.LOADING_FLAG">
</template>

<style scoped>
input {
    display: flex;
    align-items: center;
    background: var(--ui-surface-raised);
    height: 2.25rem;
    max-width: 100%;
    /* margin: .2rem; */
    padding: .2rem .4rem;
    border-radius: .5rem;
    color: var(--ui-text);
    /* box-shadow: 2px 2px 10px rgb(38, 38, 38); */
    transition: all 0.15s ease-in-out;

    border: 1px solid var(--ui-border);
    outline: none;
    flex: 1;
}

input:focus {
    background: var(--ui-surface-hover);
    border-color: var(--ui-accent);
    box-shadow: 0 0 0 3px oklch(0.72 0.14 246 / 0.16);
    transition: all 0.15s ease-in-out;

    color: var(--ui-text);
}
</style>
