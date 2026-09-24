<script setup>
import { Inbox } from '@lucide/vue'

defineProps({
  title: { type: String, default: '暂无数据' },
  description: { type: String, default: '' },
})
</script>

<template>
  <div class="empty-state">
    <Inbox :size="24" />
    <strong>{{ title }}</strong>
    <span v-if="description">{{ description }}</span>
  </div>
</template>
