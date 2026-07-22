<script setup>
defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 18 },
  strokeWidth: { type: [Number, String], default: 1.9 }
});
</script>

<template>
  <svg
    class="app-icon"
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    :stroke-width="strokeWidth"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    focusable="false"
  >
    <template v-if="name === 'check'"><path d="m5 12 4.2 4.2L19 6.8" /></template>
    <template v-else-if="name === 'chevron-down'"><path d="m7 9 5 5 5-5" /></template>
    <template v-else-if="name === 'chevron-up'"><path d="m7 15 5-5 5 5" /></template>
    <template v-else-if="name === 'chevrons-up'"><path d="m7 17 5-5 5 5M7 11l5-5 5 5" /></template>
    <template v-else-if="name === 'chevrons-down'"><path d="m7 7 5 5 5-5M7 13l5 5 5-5" /></template>
    <template v-else-if="name === 'plus'"><path d="M12 5v14M5 12h14" /></template>
    <template v-else-if="name === 'x'"><path d="m6 6 12 12M18 6 6 18" /></template>
    <template v-else-if="name === 'trash'"><path d="M4 7h16M10 11v6M14 11v6M9 7l1-3h4l1 3M6 7l1 13h10l1-13" /></template>
    <template v-else-if="name === 'edit'"><path d="M4 20h4l11-11-4-4L4 16v4ZM13.5 6.5l4 4" /></template>
    <template v-else-if="name === 'pin'"><path d="m14 4 6 6-3 1-4 4 1 3-1 1-4-4-4 4-1-1 4-4-4-4 1-1 3 1 4-4 1-3Z" /></template>
    <template v-else-if="name === 'copy'"><rect x="9" y="9" width="10" height="10" rx="2" /><path d="M15 9V7a2 2 0 0 0-2-2H7a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2" /></template>
    <template v-else-if="name === 'duplicate'"><rect x="8" y="8" width="11" height="11" rx="2" /><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" /></template>
    <template v-else-if="name === 'refresh'"><path d="M20 11a8 8 0 1 0 1.3 4.4M20 5v6h-6" /></template>
    <template v-else-if="name === 'crown'"><path d="m4 8 4 4 4-7 4 7 4-4-2 10H6L4 8ZM7 21h10" /></template>
    <template v-else-if="name === 'sparkles'"><path d="m12 3-1 5-5 1 5 1 1 5 1-5 5-1-5-1-1-5ZM19 14l-.5 2.5L16 17l2.5.5L19 20l.5-2.5L22 17l-2.5-.5L19 14Z" /></template>
    <template v-else-if="name === 'heart'"><path d="M20.8 8.6c0 5-8.8 10.2-8.8 10.2S3.2 13.6 3.2 8.6A4.4 4.4 0 0 1 11 5.8L12 7l1-1.2a4.4 4.4 0 0 1 7.8 2.8Z" /></template>
    <template v-else-if="name === 'sword'"><path d="m14.5 4.5 5 5M5 19l8.5-8.5 5 5L10 24M4 20l4-4" /></template>
    <template v-else-if="name === 'shield'"><path d="M12 3 5 6v5c0 4.5 3 8 7 10 4-2 7-5.5 7-10V6l-7-3Z" /></template>
    <template v-else-if="name === 'hammer'"><path d="m14 5 5 5M4 20l10-10M12 3l9 9-3 3-9-9 3-3Z" /></template>
    <template v-else-if="name === 'id'"><rect x="3" y="5" width="18" height="14" rx="2" /><circle cx="8" cy="11" r="2" /><path d="M5.5 16c.8-1.6 4.2-1.6 5 0M13 10h5M13 14h5" /></template>
    <template v-else-if="name === 'box'"><path d="m3 7 9-4 9 4-9 4-9-4ZM3 7v10l9 4 9-4V7M12 11v10" /></template>
    <template v-else-if="name === 'building'"><path d="M4 21V5l8-3v19M12 8h8v13M7 9h2M7 13h2M15 12h2M15 16h2" /></template>
    <template v-else-if="name === 'user'"><circle cx="12" cy="8" r="3" /><path d="M5 21c.8-4 3.2-6 7-6s6.2 2 7 6" /></template>
    <template v-else-if="name === 'pill'"><path d="m8 5 11 11a4.2 4.2 0 0 1-6 6L2 11a4.2 4.2 0 0 1 6-6Z" /><path d="m6 13 6-6" /></template>
    <template v-else-if="name === 'medical'"><path d="M12 4v16M4 12h16" /></template>
    <template v-else-if="name === 'folder'"><path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z" /></template>
    <template v-else-if="name === 'file'"><path d="M6 3h8l4 4v14H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" /><path d="M14 3v5h5M8 13h8M8 17h5" /></template>
    <template v-else-if="name === 'back'"><path d="m10 6-6 6 6 6M4 12h16" /></template>
    <template v-else-if="name === 'forward'"><path d="m14 6 6 6-6 6M20 12H4" /></template>
    <template v-else-if="name === 'warning'"><path d="m12 3 10 18H2L12 3ZM12 9v4M12 17h.01" /></template>
    <template v-else-if="name === 'snowflake'"><path d="m12 2 1.5 3-1.5 2-1.5-2L12 2Zm0 20-1.5-3 1.5-2 1.5 2-1.5 3ZM3.3 7l3.3.3 1 2.3-2.7.8L3.3 7Zm17.4 10-3.3-.3-1-2.3 2.7-.8 1.6 3.4ZM3.3 17l1.6-3.4 2.7.8-1 2.3-3.3.3Zm17.4-10-1.6 3.4-2.7-.8 1-2.3 3.3-.3Z" /><path d="M12 7v10M7.7 9.6l8.6 4.8M7.7 14.4l8.6-4.8" /></template>
    <template v-else-if="name === 'clock'"><circle cx="12" cy="12" r="8" /><path d="M12 7v5l3 2" /></template>
    <template v-else-if="name === 'search'"><circle cx="11" cy="11" r="7" /><path d="m20 20-4-4" /></template>
    <template v-else-if="name === 'settings'"><circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M4.9 4.9 7 7M17 17l2.1 2.1M2 12h3M19 12h3M4.9 19.1 7 17M17 7l2.1-2.1" /></template>
    <template v-else><circle cx="12" cy="12" r="3" fill="currentColor" stroke="none" /></template>
  </svg>
</template>

<style scoped>
.app-icon { display: block; flex: 0 0 auto; }
</style>
