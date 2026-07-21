<script setup>
import { computed } from 'vue'

const props = defineProps({
  element: { type: String, required: true },
  size: { type: [Number, String], default: 16 },
  alt: { type: String, default: '' }
})

const ELEMENT_ASSET_NAMES = {
  Electricity: 'Electric'
}

const elementName = computed(() => {
  const name = props.element.split('::').pop().replace('EPalElementType_', '')
  const normalizedName = name ? name[0].toUpperCase() + name.slice(1) : ''
  return ELEMENT_ASSET_NAMES[normalizedName] || normalizedName
})

const src = computed(() => elementName.value ? `/image/elements/Element_${elementName.value}` : '')
</script>

<template>
  <img v-if="src" class="element-icon" :src="src" :width="size" :height="size" :alt="alt" draggable="false">
</template>

<style scoped>
.element-icon {
  display: block;
  flex: 0 0 auto;
  object-fit: contain;
}
</style>
