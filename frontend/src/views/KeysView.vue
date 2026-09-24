<script setup>
import { KeyRound, Plus, Trash2 } from '@lucide/vue'
import { onMounted, ref } from 'vue'

import { api, jsonBody } from '../api'
import EmptyState from '../components/EmptyState.vue'
import PageHeader from '../components/PageHeader.vue'
import StatusBadge from '../components/StatusBadge.vue'

const keys = ref([])
const adding = ref(false)
const form = ref({ api_key: '', label: '' })
const error = ref('')

function successRate(key) {
  const attempts = key.total_requests + key.fail_count
  return attempts ? Math.round((key.total_requests / attempts) * 100) + '%' : '-'
}

async function load() {
  try {
    keys.value = (await api('/admin/api/keys')).keys
    error.value = ''
  } catch (err) {
    error.value = err.message
  }
}

async function addKey() {
  try {
    await api('/admin/api/keys', { method: 'POST', body: jsonBody(form.value) })
    form.value = { api_key: '', label: '' }
    adding.value = false
    await load()
  } catch (err) {
    error.value = err.message
  }
}

async function toggle(key) {
  await api(`/admin/api/keys/${key.id}/toggle`, { method: 'POST' })
  await load()
}

async function remove(key) {
  if (!window.confirm(`确认删除 ${key.label || key.api_key}？`)) return
  await api(`/admin/api/keys/${key.id}`, { method: 'DELETE' })
  await load()
}

onMounted(load)
</script>

<template>
  <PageHeader
    title="上游密钥"
    description="管理 NVIDIA NIM API Key、调度状态和累计用量。"
  >
    <template #actions>
      <button class="button button--primary" type="button" @click="adding = !adding">
        <Plus :size="16" />
        添加密钥
      </button>
    </template>
  </PageHeader>

  <p v-if="error" class="notice notice--error">{{ error }}</p>

  <form v-if="adding" class="surface inline-form inline-form--key" @submit.prevent="addKey">
    <label class="field">
      <span>NVIDIA API Key</span>
      <input v-model="form.api_key" type="password" required placeholder="nvapi-..." autocomplete="off" />
    </label>
    <label class="field">
      <span>备注</span>
      <input v-model="form.label" placeholder="例如：主账号" />
    </label>
    <button class="button button--primary" type="submit">保存密钥</button>
  </form>

  <section class="surface table-section">
    <div class="section-heading">
      <div>
        <p class="section-kicker">KEY POOL</p>
        <h2>调度池</h2>
      </div>
      <StatusBadge tone="neutral">{{ keys.length }} 个密钥</StatusBadge>
    </div>
    <div v-if="keys.length" class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>密钥</th>
            <th>状态</th>
            <th>累计 Token</th>
            <th>请求</th>
            <th>成功率</th>
            <th class="align-right">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="key in keys" :key="key.id">
            <td>
              <div class="key-cell">
                <span class="model-icon"><KeyRound :size="16" /></span>
                <span><strong>{{ key.label || `Key #${key.id}` }}</strong><small class="mono">{{ key.api_key }}</small></span>
              </div>
            </td>
            <td>
              <StatusBadge v-if="!key.enabled" tone="neutral">已禁用</StatusBadge>
              <StatusBadge v-else-if="key.cooling" tone="warning">冷却 {{ key.cooldown_remaining }}s</StatusBadge>
              <StatusBadge v-else tone="success">可用</StatusBadge>
            </td>
            <td class="tabular">{{ (key.total_prompt_tokens + key.total_completion_tokens).toLocaleString() }}</td>
            <td class="tabular">{{ key.total_requests }}</td>
            <td class="tabular">{{ successRate(key) }}</td>
            <td>
              <div class="row-actions">
                <label class="switch" :title="key.enabled ? '禁用密钥' : '启用密钥'">
                  <input type="checkbox" :checked="key.enabled" @change="toggle(key)" />
                  <span />
                </label>
                <button class="icon-button icon-button--danger" type="button" title="删除密钥" @click="remove(key)">
                  <Trash2 :size="16" />
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <EmptyState v-else title="调度池为空" description="添加第一个 NVIDIA API Key 后即可开始代理请求。" />
  </section>
</template>
