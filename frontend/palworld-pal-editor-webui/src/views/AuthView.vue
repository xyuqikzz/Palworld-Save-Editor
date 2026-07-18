<script setup>
import { usePalEditorStore } from '@/stores/paleditor'
import { ref } from 'vue'
const palStore = usePalEditorStore()

const PW = ref("")

</script>
<template>
    <div id="authDiv">
        <section class="auth-card" aria-labelledby="auth-title">
            <img :alt="palStore.getTranslatedText('Common_AppName')" class="logo" src="@/assets/logo.ico" width="72" height="72" />
            <p class="eyebrow">{{ palStore.getTranslatedText('Common_AppName') }}</p>
            <h1 id="auth-title">{{ palStore.getTranslatedText("AuthView_PW_Prompt_1") }}</h1>
            <p class="hint">{{ palStore.getTranslatedText("AuthView_PW_Prompt_2") }}</p>
            <label class="sr-only" for="password">{{ palStore.getTranslatedText('AuthView_Password') }}</label>
            <input id="password" type="password" v-model="PW" :placeholder="palStore.getTranslatedText('AuthView_Password')"
                :disabled="palStore.LOADING_FLAG" @keyup.enter="palStore.login">
            <button @click="palStore.login" :disabled="palStore.LOADING_FLAG" :value="PW">
                {{ palStore.getTranslatedText("AuthView_BTN_Unlock") }}
            </button>
        </section>
    </div>
</template>

<style scoped>
div#authDiv {
    display: flex;
    min-height: 100dvh;
    align-items: center;
    justify-content: center;
    padding: 24px;
}

.auth-card {
    width: min(100%, 430px);
    display: flex;
    flex-direction: column;
    gap: 14px;
    padding: 34px;
    background: var(--ui-surface);
    border: 1px solid var(--ui-border);
    border-radius: var(--ui-radius-lg);
    box-shadow: var(--ui-shadow-md);
}

.logo {
    border-radius: 14px;
}

.eyebrow {
    margin: 4px 0 0;
    color: var(--ui-accent);
    font-size: 0.82rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    text-transform: uppercase;
}

h1 {
    margin: 0;
    color: var(--ui-text);
    font-size: 1.35rem;
}

.hint {
    margin: 0;
    color: var(--ui-text-muted);
    line-height: 1.65;
}

input {
    height: 42px;
    padding: 0 12px;
    color: var(--ui-text);
    background: var(--ui-canvas);
    border: 1px solid var(--ui-border);
    border-radius: 8px;
    font: inherit;
}

input:focus {
    outline: none;
    border-color: var(--ui-accent);
    box-shadow: 0 0 0 3px oklch(0.72 0.14 246 / 0.16);
}

button {
    height: 42px;
    color: oklch(0.16 0.025 252);
    background: var(--ui-accent);
    border: 1px solid var(--ui-accent);
    border-radius: 8px;
    font: inherit;
    font-weight: 650;
    cursor: pointer;
}

button:hover {
    background: var(--ui-accent-strong);
    border-color: var(--ui-accent-strong);
}

button:disabled {
    cursor: default;
    opacity: 0.56;
}
</style>
