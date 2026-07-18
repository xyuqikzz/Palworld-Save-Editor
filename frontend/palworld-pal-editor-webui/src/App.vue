<script setup>
import EntryView from './views/EntryView.vue';
import { usePalEditorStore } from '@/stores/paleditor';
import EditorView from './views/EditorView.vue';
import TopBar from './components/TopBar.vue';
import AuthView from './views/AuthView.vue';
import { onMounted } from 'vue';

const palStore = usePalEditorStore();

onMounted(async () => {
  await palStore.fetch_config();
  if (!palStore.HAS_PASSWORD) {
    await palStore.login({ target: { value: '' } });
  }
  await palStore.auth();
});
</script>

<template>
  <TopBar />
  <AuthView v-if="palStore.IS_LOCKED" />
  <main v-else class="app-shell">
    <EntryView v-if="!palStore.SAVE_LOADED_FLAG" />
    <EditorView v-else />
  </main>
</template>

<style>
.app-shell {
  min-height: 100vh;
}
</style>
