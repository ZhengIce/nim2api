<script setup>
import { Boxes, CalendarClock, CheckCircle2, Database, Play, RefreshCw, Server, XCircle } from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'

import { api, jsonBody } from '../api'
import EmptyState from '../components/EmptyState.vue'
import ConnectivitySpark from '../components/ConnectivitySpark.vue'
import PageHeader from '../components/PageHeader.vue'
import StatusBadge from '../components/StatusBadge.vue'

const health = ref(null)
const models = ref([])
const schedule = ref(null)
const history = ref({})
const running = ref(false)
const activeId = ref('')
const error = ref('')

const enabledModels = computed(() => models.value.filter((model) => model.enabled))
const healthyCount = computed(() =>
  enabledModels.value.filter((model) => model.last_check_ok).length,
)

function dateTime(value) {
  if (!value) return '尚未检测'
  return new Date(value * 1000).toLocaleString('zh-CN', { hour12: false })
}

async function load() {
  try {
    const [healthData, modelData, scheduleData, historyData] = await Promise.all([
      api('/admin/api/health'),
      api('/admin/api/models'),
      api('/admin/api/model-checks/schedule'),
      api('/admin/api/model-checks/history?points=24'),
    ])
    health.value = healthData
    models.value = modelData.models
    schedule.value = scheduleData
    history.value = historyData.history
    error.value = ''
  } catch (err) {
    error.value = err.message
  }
}

async function runAll() {
  running.value = true
  error.value = ''
  try {
    await api('/admin/api/model-checks/run', { method: 'POST' })
    await load()
  } catch (err) {
    error.value = err.message
  } finally {
    running.value = false
  }
}

async function runOne(id) {
  activeId.value = id
  try {
    await api('/admin/api/model-checks/check', {
      method: 'POST',
      body: jsonBody({ id }),
    })
    await load()
  } catch (err) {
    error.value = err.message
  } finally {
    activeId.value = ''
  }
}

onMounted(load)
</script>

<template>
  <PageHeader
    title="模型检测"
    description="通过最小聊天补全请求验证模型是否可以被当前网关正常调用。"
  >
    <template #actions>
      <button
        class="button button--primary"
        type="button"
        :disabled="running || !enabledModels.length"
        @click="runAll"
      >
        <Play :size="16" />
        {{ running ? '检测中' : '检测全部模型' }}
      </button>
    </template>
  </PageHeader>

  <p v-if="error" class="notice notice--error">{{ error }}</p>
  <div class="notice notice--warning">
    检测会为每个启用模型发送一次 max_tokens=1 的真实推理请求，因此会产生极少量 Token 消耗。
  </div>

  <section class="schedule-strip">
    <span class="schedule-icon"><CalendarClock :size="19" /></span>
    <div>
      <strong v-if="schedule?.running">模型检测正在运行</strong>
      <strong v-else-if="schedule?.enabled">每 {{ schedule.interval_minutes }} 分钟自动检测</strong>
      <strong v-else>定时检测未启用</strong>
      <span v-if="schedule?.enabled && schedule?.next_run_at">
        下次执行：{{ dateTime(schedule.next_run_at) }}
      </span>
      <span v-else>可在网关配置中开启并设置检测间隔。</span>
    </div>
    <div v-if="schedule?.last_run_at" class="schedule-result">
      <strong>{{ schedule.last_success }} / {{ schedule.last_total }}</strong>
      <span>上次正常 · {{ dateTime(schedule.last_run_at) }}</span>
    </div>
    <RouterLink class="button button--secondary button--compact" to="/settings">配置计划</RouterLink>
  </section>

  <section class="health-strip">
    <div>
      <span class="health-icon"><Server :size="18" /></span>
      <span><small>网关服务</small><strong>{{ health?.service === 'ok' ? '运行正常' : '未知' }}</strong></span>
      <StatusBadge tone="success">Online</StatusBadge>
    </div>
    <div>
      <span class="health-icon"><Database :size="18" /></span>
      <span><small>模型目录</small><strong>{{ enabledModels.length }} 个启用模型</strong></span>
      <StatusBadge tone="info">Catalog</StatusBadge>
    </div>
    <div>
      <span class="health-icon"><Boxes :size="18" /></span>
      <span><small>检测状态</small><strong>{{ healthyCount }} / {{ enabledModels.length }} 正常</strong></span>
      <StatusBadge :tone="healthyCount === enabledModels.length && enabledModels.length ? 'success' : 'warning'">
        Inference
      </StatusBadge>
    </div>
  </section>

  <section class="surface table-section">
    <div class="section-heading">
      <div>
        <p class="section-kicker">MODEL PROBES</p>
        <h2>模型检测结果</h2>
      </div>
      <button class="icon-button" type="button" title="刷新" @click="load">
        <RefreshCw :size="17" />
      </button>
    </div>
    <div v-if="enabledModels.length" class="check-list">
      <article v-for="model in enabledModels" :key="model.id" class="check-row">
        <span
          class="check-result-icon"
          :class="{ 'check-result-icon--ok': model.last_check_ok }"
        >
          <CheckCircle2 v-if="model.last_check_ok" :size="19" />
          <XCircle v-else :size="19" />
        </span>
        <div class="check-main">
          <strong class="mono">{{ model.id }}</strong>
          <span>{{ model.label || model.owned_by || 'NVIDIA NIM' }}</span>
        </div>
        <div class="check-message">
          <strong>{{ model.last_check_message || '等待首次检测' }}</strong>
          <span>{{ dateTime(model.last_checked_at) }}</span>
        </div>
        <ConnectivitySpark :points="history[model.id] || []" />
        <div class="check-latency">
          <strong>{{ model.last_check_latency_ms || '-' }}</strong>
          <span>ms</span>
        </div>
        <button
          class="button button--secondary button--compact"
          type="button"
          :disabled="activeId === model.id"
          @click="runOne(model.id)"
        >
          <RefreshCw :size="15" :class="{ spin: activeId === model.id }" />
          检测
        </button>
      </article>
    </div>
    <EmptyState v-else title="没有启用的模型" description="先在“模型管理”页面同步模型并启用需要检测的模型。" />
  </section>
</template>
