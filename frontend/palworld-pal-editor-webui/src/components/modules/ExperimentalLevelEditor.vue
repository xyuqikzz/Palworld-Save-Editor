<script setup>
import { computed, ref } from 'vue'
import { usePalEditorStore } from '@/stores/paleditor'

const props = defineProps({ kind: { type: String, required: true } })
const store = usePalEditorStore()
const acknowledged = ref(false)
const level = ref(101)
const experience = ref('')
const valid = computed(() => acknowledged.value
  && Number.isSafeInteger(level.value) && level.value >= 1 && level.value <= 255
  && Number.isSafeInteger(experience.value) && experience.value >= 0)

async function apply() {
  if (!valid.value) return
  if (await store.setExperimentalLevel(props.kind, level.value, experience.value)) {
    acknowledged.value = false
    experience.value = ''
  }
}
</script>

<template>
  <details class="experimental-level">
    <summary>{{ store.getTranslatedText('ExperimentalLevel_Title') }}</summary>
    <p>{{ store.getTranslatedText('ExperimentalLevel_Warning') }}</p>
    <label class="acknowledgement">
      <input v-model="acknowledged" type="checkbox" :disabled="store.LOADING_FLAG">
      {{ store.getTranslatedText('ExperimentalLevel_Acknowledge') }}
    </label>
    <form @submit.prevent="apply">
      <label>
        {{ store.getTranslatedText('ExperimentalLevel_Level') }}
        <input v-model.number="level" type="number" min="1" max="255" step="1" required :disabled="!acknowledged || store.LOADING_FLAG">
      </label>
      <label>
        {{ store.getTranslatedText('ExperimentalLevel_Experience') }}
        <input v-model.number="experience" type="number" min="0" :max="Number.MAX_SAFE_INTEGER" step="1" required :disabled="!acknowledged || store.LOADING_FLAG">
      </label>
      <button type="submit" :disabled="!valid || store.LOADING_FLAG">{{ store.getTranslatedText('ExperimentalLevel_Apply') }}</button>
    </form>
  </details>
</template>

<style scoped>
.experimental-level { flex: 1 1 100%; padding: 0.75rem; border: 1px solid #b58943; border-radius: 6px; }
summary { cursor: pointer; font-weight: 600; }
p { max-width: 75ch; line-height: 1.5; margin: 0.75rem 0; }
form { display: flex; flex-wrap: wrap; align-items: end; gap: 0.75rem; margin-top: 0.75rem; }
form label { display: grid; gap: 0.35rem; }
input[type=number] { width: 12rem; max-width: 100%; padding: 0.4rem; }
.acknowledgement { display: flex; gap: 0.5rem; align-items: start; }
button { padding: 0.45rem 0.75rem; }
</style>
