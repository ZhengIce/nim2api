<script setup>
import { Boxes, Copy, Plus, RefreshCw, Search, Trash2 } from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'

import { api, jsonBody } from '../api'
import EmptyState from '../components/EmptyState.vue'
import PageHeader from '../components/PageHeader.vue'
import StatusBadge from '../components/StatusBadge.vue'

const models = ref([])
const query = ref('')
const syncing = ref(false)
const adding = ref(false)
const form = ref({ id: '', label: '' })
const notice = ref('')
const error = ref('')

const filtered = computed(() => {
  const value = query.value.toLowerCase().trim()
  if (!value) return models.value
  return models.value.filter((model) =>
    [model.id, model.label, model.owned_by].some((item) => String(item || '').toLowerCase().includes(value)),
  )
})

async function load() {
  try {
    models.value = (await api('/admin/api/models')).models
  } catch (err) {
    error.value = err.message
  }
}

async function sync() {
  syncing.value = true
  notice.value = ''
  error.value = ''
  try {
    const result = await api('/admin/api/models/sync', { method: 'POST' })
    notice.value = `已从上游同步 ${result.synced} 个模型`
    await load()
  } catch (err) {
    error.value = err.message
  } finally {
    syncing.value = false
  }
}

async function addModel() {
  try {
    await api('/admin/api/models', { method: 'POST', body: jsonBody(form.value) })
    form.value = { id: '', label: '' }
    adding.value = false
    await load()
  } catch (err) {
    error.value = err.message
  }
}

async function toggle(model) {
  await api('/admin/api/models/toggle', { method: 'POST', body: jsonBody({ id: model.id }) })
  await load()
}

async function remove(model) {
  if (!window.confirm(`确认删除模型 ${model.id}？`)) return
  await api('/admin/api/models/delete', { method: 'POST', body: jsonBody({ id: model.id }) })
  await load()
}

function copy(value) {
  navigator.clipboard.writeText(value)
  notice.value = '模型 ID 已复制'
}

onMounted(load)
</script>

<template>
  <PageHeader
    title="模型管理"
    description="同步 NVIDIA 模型目录，并控制网关允许访问的模型。"
  >
    <template #actions>
      <button class="button button--secondary" type="button" @click="adding = !adding">
        <Plus :size="16" />
        手动添加
      </button>
      <button class="button button--primary" type="button" :disabled="syncing" @click="sync">
        <RefreshCw :size="16" :class="{ spin: syncing }" />
        {{ syncing ? '同步中' : '同步上游' }}
      </button>
    </template>
  </PageHeader>

  <p v-if="notice" class="notice notice--success">{{ notice }}</p>
  <p v-if="error" class="notice notice--error">{{ error }}</p>

  <form v-if="adding" class="surface inline-form" @submit.prevent="addModel">
    <label class="field">
      <span>模型 ID</span>
      <input v-model="form.id" required placeholder="meta/llama-3.1-70b-instruct" />
    </label>
    <label class="field">
      <span>备注</span>
      <input v-model="form.label" placeholder="可选" />
    </label>
    <button class="button button--primary" type="submit">添加模型</button>
  </form>

  <section class="surface table-section">
    <div class="table-toolbar">
      <div class="section-heading">
        <div>
          <p class="section-kicker">MODEL CATALOG</p>
          <h2>模型目录</h2>
        </div>
        <StatusBadge tone="neutral">{{ models.length }} 个</StatusBadge>
      </div>
      <label class="search-field">
        <Search :size="16" />
        <input v-model="query" placeholder="搜索模型或提供方" />
      </label>
    </div>

    <div v-if="filtered.length" class="model-list">
      <article v-for="model in filtered" :key="model.id" class="model-row">
        <span class="model-icon"><Boxes :size="18" /></span>
        <div class="model-main">
          <div>
            <strong class="mono">{{ model.id }}</strong>
            <button class="copy-button" type="button" title="复制模型 ID" @click="copy(model.id)">
              <Copy :size="14" />
            </button>
          </div>
          <span>{{ model.label || model.owned_by || 'NVIDIA NIM' }}</span>
        </div>
        <StatusBadge :tone="model.source === 'upstream' ? 'info' : 'neutral'">
          {{ model.source === 'upstream' ? '上游同步' : '手动添加' }}
        </StatusBadge>
        <label class="switch" :title="model.enabled ? '禁用模型' : '启用模型'">
          <input type="checkbox" :checked="model.enabled" @change="toggle(model)" />
          <span />
        </label>
        <button class="icon-button icon-button--danger" type="button" title="删除模型" @click="remove(model)">
          <Trash2 :size="16" />
        </button>
      </article>
    </div>
    <EmptyState v-else title="没有匹配的模型" description="同步上游目录，或手动添加一个模型。" />
  </section>
</template>
