<script setup>
defineProps({
  tone: { type: String, default: 'neutral' },
})
</script>

<template>
  <span class="status-badge" :class="`status-badge--${tone}`">
    <span class="status-badge-dot" />
    <slot />
  </span>
</template>
