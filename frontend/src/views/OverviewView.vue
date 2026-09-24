<script setup>
import { Activity, ArrowUpRight, Clock3, KeyRound, RefreshCw, Zap } from '@lucide/vue'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { api } from '../api'
import EmptyState from '../components/EmptyState.vue'
import PageHeader from '../components/PageHeader.vue'
import StatusBadge from '../components/StatusBadge.vue'

const stats = ref(null)
const usage = ref([])
const logs = ref([])
const loading = ref(true)
const error = ref('')
let timer

const maxUsage = computed(() => Math.max(1, ...usage.value.map((item) => item.total)))
const recentUsage = computed(() => usage.value.slice(-30))

function compact(value) {
  return new Intl.NumberFormat('zh-CN', { notation: 'compact', maximumFractionDigits: 1 }).format(value || 0)
}

function time(value) {
  return new Date(value * 1000).toLocaleTimeString('zh-CN', { hour12: false })
}

async function load(silent = false) {
  if (!silent) loading.value = true
  try {
    const [statsData, usageData, logsData] = await Promise.all([
      api('/admin/api/stats'),
      api('/admin/api/usage?minutes=60'),
      api('/admin/api/logs?limit=8'),
    ])
    stats.value = statsData
    usage.value = usageData.series
    logs.value = logsData.logs
    error.value = ''
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  load()
  timer = window.setInterval(() => load(true), 10000)
})
onBeforeUnmount(() => window.clearInterval(timer))
</script>

<template>
  <PageHeader
    title="运行概览"
    description="追踪网关流量、密钥可用性和最近请求表现。"
  >
    <template #actions>
      <button class="button button--secondary" type="button" @click="load()">
        <RefreshCw :size="16" :class="{ spin: loading }" />
        刷新
      </button>
    </template>
  </PageHeader>

  <p v-if="error" class="notice notice--error">{{ error }}</p>

  <section class="metric-grid" aria-label="运行指标">
    <article class="metric">
      <span class="metric-icon"><Activity :size="18" /></span>
      <p>总请求</p>
      <strong>{{ compact(stats?.total_requests) }}</strong>
      <small>累计代理请求</small>
    </article>
    <article class="metric">
      <span class="metric-icon"><Zap :size="18" /></span>
      <p>今日 Token</p>
      <strong>{{ compact(stats?.today_tokens) }}</strong>
      <small>总计 {{ compact(stats?.total_tokens) }}</small>
    </article>
    <article class="metric">
      <span class="metric-icon"><Clock3 :size="18" /></span>
      <p>平均延迟</p>
      <strong>{{ stats?.avg_latency_ms || 0 }}<em> ms</em></strong>
      <small>全部历史请求</small>
    </article>
    <article class="metric metric--accent">
      <span class="metric-icon"><KeyRound :size="18" /></span>
      <p>可用密钥</p>
      <strong>{{ stats?.available_keys || 0 }}<em> / {{ stats?.total_keys || 0 }}</em></strong>
      <small>实时可调度数量</small>
    </article>
  </section>

  <section class="content-grid content-grid--overview">
    <article class="surface usage-panel">
      <div class="section-heading">
        <div>
          <p class="section-kicker">LAST 60 MINUTES</p>
          <h2>Token 流量</h2>
        </div>
        <StatusBadge tone="success">实时</StatusBadge>
      </div>
      <div class="bar-chart" aria-label="最近 60 分钟 Token 使用量">
        <div
          v-for="item in recentUsage"
          :key="item.t"
          class="bar-chart-column"
          :title="`${time(item.t)} · ${item.total} Token`"
        >
          <span :style="{ height: `${Math.max(2, item.total / maxUsage * 100)}%` }" />
        </div>
      </div>
      <div class="chart-axis">
        <span>{{ recentUsage.length ? time(recentUsage[0].t).slice(0, 5) : '--:--' }}</span>
        <span>现在</span>
      </div>
    </article>

    <aside class="surface quick-panel">
      <div class="section-heading">
        <div>
          <p class="section-kicker">SHORTCUTS</p>
          <h2>快速操作</h2>
        </div>
      </div>
      <RouterLink class="quick-link" to="/checks">
        <span><Activity :size="18" />检测模型可用性</span>
        <ArrowUpRight :size="16" />
      </RouterLink>
      <RouterLink class="quick-link" to="/models">
        <span><Zap :size="18" />同步模型目录</span>
        <ArrowUpRight :size="16" />
      </RouterLink>
      <RouterLink class="quick-link" to="/tokens">
        <span><KeyRound :size="18" />创建访问令牌</span>
        <ArrowUpRight :size="16" />
      </RouterLink>
    </aside>
  </section>

  <section class="surface table-section">
    <div class="section-heading">
      <div>
        <p class="section-kicker">REQUEST LOG</p>
        <h2>最近请求</h2>
      </div>
      <span class="muted">{{ logs.length }} 条</span>
    </div>
    <div v-if="logs.length" class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>时间</th>
            <th>模型</th>
            <th>密钥</th>
            <th>状态</th>
            <th>Token</th>
            <th>延迟</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="log in logs" :key="log.id">
            <td class="tabular">{{ time(log.created_at) }}</td>
            <td class="mono">{{ log.model || '-' }}</td>
            <td>{{ log.key_label || log.api_key || '-' }}</td>
            <td>
              <StatusBadge :tone="log.status >= 200 && log.status < 300 ? 'success' : 'danger'">
                {{ log.status }}
              </StatusBadge>
            </td>
            <td class="tabular">{{ (log.prompt_tokens + log.completion_tokens).toLocaleString() }}</td>
            <td class="tabular">{{ log.latency_ms }} ms</td>
          </tr>
        </tbody>
      </table>
    </div>
    <EmptyState v-else title="还没有请求记录" description="成功代理请求后会在这里出现。" />
  </section>
</template>
