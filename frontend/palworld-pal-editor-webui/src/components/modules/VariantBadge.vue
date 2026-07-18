<script setup>
import AppIcon from '@/components/modules/AppIcon.vue'
import { usePalEditorStore } from '@/stores/paleditor'

const palStore = usePalEditorStore()

defineProps({
  kind: { type: String, required: true },
  size: { type: [Number, String], default: 15 },
  showLabel: { type: Boolean, default: false }
})

const variants = {
  boss: { icon: 'crown', labelKey: 'Variant_Boss' },
  rare: { icon: 'sparkles', labelKey: 'Variant_Rare' },
  tower: { icon: 'building', labelKey: 'Variant_Tower' }
}
const variantLabel = kind => palStore.getTranslatedText(variants[kind].labelKey)
</script>

<template>
  <span v-if="variants[kind]" class="variant-badge" :title="variantLabel(kind)">
    <AppIcon :name="variants[kind].icon" :size="size" />
    <span v-if="showLabel">{{ variantLabel(kind) }}</span>
  </span>
</template>

<style scoped>
.variant-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex: 0 0 auto;
}
</style>
