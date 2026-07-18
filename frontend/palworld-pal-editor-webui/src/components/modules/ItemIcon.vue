<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  icon: { type: String, default: null },
  name: { type: String, default: '' },
  size: { type: [Number, String], default: 48 }
})

const failed = ref(false)
watch(() => props.icon, () => {
  failed.value = false
})
</script>

<template>
  <img
    v-if="icon && !failed"
    class="item-icon"
    :src="`/image/items/${icon}`"
    :width="size"
    :height="size"
    :alt="name"
    draggable="false"
    @error="failed = true"
  >
  <span v-else class="item-icon item-icon--missing" :style="{ width: `${size}px`, height: `${size}px` }">?</span>
</template>

<style scoped>
.item-icon {
  flex: 0 0 auto;
  border-radius: .5rem;
  object-fit: contain;
}

.item-icon--missing {
  display: grid;
  place-items: center;
  background: #303033;
  color: #8f9199;
  font-weight: 700;
}
</style>
