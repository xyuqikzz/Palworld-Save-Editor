<script setup>
import { usePalEditorStore } from '@/stores/paleditor';
import TopBar from './components/TopBar.vue';
import AuthView from './views/AuthView.vue';
import UpdateNotice from './components/UpdateNotice.vue';
import PathPicker from './components/PathPicker.vue';
import GlobalMessageDialog from './components/GlobalMessageDialog.vue';
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
    await palStore.loadRemoteProfile();
    const remoteResumed = await palStore.resumeRemoteSession();
    const saveResumed = await palStore.resumeCurrentSession();

    if (route.meta.requiresRemoteSession) {
      if (!remoteResumed) await router.replace({ name: 'Entry' });
      return remoteResumed;
    }
    if (route.meta.requiresSession) {
      if (!saveResumed) await router.replace({ name: 'Entry' });
      return saveResumed;
    }
    if (remoteResumed) {
      await router.replace({ name: 'RemoteServer' });
      return true;
    }
    if (saveResumed) {
      await router.replace({ name: 'Overview' });
      return true;
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
  if (route.meta.requiresRemoteSession && !palStore.REMOTE_CONNECTED) {
    await router.replace({ name: 'Entry' });
  } else if (route.meta.requiresSession && !palStore.SAVE_LOADED_FLAG) {
    await router.replace({ name: 'Entry' });
  } else if (route.name === 'Entry' && palStore.REMOTE_CONNECTED) {
    await router.replace({ name: 'RemoteServer' });
  } else if (route.name === 'Entry' && palStore.SAVE_LOADED_FLAG) {
    await router.replace({ name: 'Overview' });
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
  () => [
    palStore.SAVE_LOADED_FLAG,
    palStore.REMOTE_CONNECTED,
    palStore.LOADING_FLAG,
    route.fullPath,
  ],
  reconcileRouteWithSession,
  { flush: 'post' },
);

onMounted(async () => {
  await palStore.fetch_config();
  if (!palStore.SKIP_UPDATE_CHECK) palStore.checkForUpdate();
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
  <PathPicker />
  <GlobalMessageDialog />
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
