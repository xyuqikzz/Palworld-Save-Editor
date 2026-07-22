<script setup>
import { usePalEditorStore } from '@/stores/paleditor';
import TopBar from './components/TopBar.vue';
import AuthView from './views/AuthView.vue';
import UpdateNotice from './components/UpdateNotice.vue';
import { onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

const palStore = usePalEditorStore();
const route = useRoute();
const router = useRouter();
const BOOTSTRAPPING = ref(true);
let initializationPromise = null;

async function initializeAuthenticatedState() {
  if (palStore.IS_LOCKED) return false;
  if (initializationPromise) return initializationPromise;

  BOOTSTRAPPING.value = true;
  initializationPromise = (async () => {
    const resumed = await palStore.resumeCurrentSession();
    if (resumed) {
      if (!route.meta.requiresSession) {
        await router.replace({ name: 'Editor' });
      }
      return true;
    }
    if (route.meta.requiresSession) {
      await router.replace({ name: 'Entry' });
    }
    return false;
  })();

  try {
    return await initializationPromise;
  } finally {
    initializationPromise = null;
    BOOTSTRAPPING.value = false;
  }
}

async function reconcileRouteWithSession() {
  if (palStore.IS_LOCKED || BOOTSTRAPPING.value || palStore.LOADING_FLAG) return;
  if (palStore.SAVE_LOADED_FLAG && !route.meta.requiresSession) {
    await router.replace({ name: 'Editor' });
  } else if (!palStore.SAVE_LOADED_FLAG && route.meta.requiresSession) {
    await router.replace({ name: 'Entry' });
  }
}

watch(
  () => palStore.IS_LOCKED,
  async (locked) => {
    if (!locked) await initializeAuthenticatedState();
  },
  { flush: 'post' },
);

watch(
  () => [palStore.SAVE_LOADED_FLAG, palStore.LOADING_FLAG, route.fullPath],
  reconcileRouteWithSession,
  { flush: 'post' },
);

onMounted(async () => {
  await palStore.fetch_config();
  palStore.checkForUpdate();
  let authenticated = false;
  if (!palStore.HAS_PASSWORD) {
    authenticated = await palStore.login({ target: { value: '' } });
  } else {
    authenticated = await palStore.auth();
  }
  if (authenticated) {
    await initializeAuthenticatedState();
  } else {
    BOOTSTRAPPING.value = false;
  }
});
</script>

<template>
  <TopBar />
  <UpdateNotice />
  <AuthView v-if="palStore.IS_LOCKED" />
  <main v-else-if="BOOTSTRAPPING" class="app-shell route-loading" aria-busy="true">
    <span class="route-loading__indicator" />
  </main>
  <main v-else class="app-shell">
    <RouterView />
  </main>
</template>

<style>
.app-shell {
  min-height: 100vh;
}

.route-loading {
  display: grid;
  place-items: center;
  background: var(--ui-canvas);
}

.route-loading__indicator {
  width: 34px;
  height: 34px;
  border: 3px solid var(--ui-border);
  border-top-color: var(--ui-accent);
  border-radius: 50%;
  animation: route-loading-spin 700ms linear infinite;
}

@keyframes route-loading-spin {
  to { transform: rotate(360deg); }
}

@media (prefers-reduced-motion: reduce) {
  .route-loading__indicator { animation: none; }
}
</style>
