<script setup>
import { computed } from 'vue'

const props = defineProps({
  points: {
    type: Array,
    default: () => [],
  },
  count: {
    type: Number,
    default: 24,
  },
})

const segments = computed(() => {
  const recent = props.points.slice(-props.count)
  return [...Array(Math.max(0, props.count - recent.length)).fill(null), ...recent]
})

function segmentTitle(point) {
  if (!point) return '暂无检测记录'
  const checkedAt = new Date(point.created_at * 1000).toLocaleString('zh-CN', { hour12: false })
  const status = point.status ? `HTTP ${point.status}` : '未连接'
  return `${checkedAt} · ${status} · ${point.latency_ms} ms`
}
</script>

<template>
  <div class="connectivity-spark" role="img" aria-label="模型最近连通性记录，右侧为最新结果">
    <span
      v-for="(point, index) in segments"
      :key="index"
      class="connectivity-spark__bar"
      :class="{
        'connectivity-spark__bar--empty': !point,
        'connectivity-spark__bar--ok': point?.ok,
        'connectivity-spark__bar--failed': point && !point.ok,
      }"
      :title="segmentTitle(point)"
    />
  </div>
</template>
