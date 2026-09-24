<script setup>
import { Copy, Plus, ShieldCheck, Trash2 } from '@lucide/vue'
import { onMounted, ref } from 'vue'

import { api, jsonBody } from '../api'
import EmptyState from '../components/EmptyState.vue'
import PageHeader from '../components/PageHeader.vue'
import StatusBadge from '../components/StatusBadge.vue'

const tokens = ref([])
const adding = ref(false)
const form = ref({ token: '', label: '' })
const createdToken = ref('')
const error = ref('')

function dateTime(value) {
  return new Date(value * 1000).toLocaleString('zh-CN', { hour12: false })
}

async function load() {
  tokens.value = (await api('/admin/api/tokens')).tokens
}

async function addToken() {
  try {
    const result = await api('/admin/api/tokens', { method: 'POST', body: jsonBody(form.value) })
    createdToken.value = result.token
    form.value = { token: '', label: '' }
    adding.value = false
    await load()
  } catch (err) {
    error.value = err.message
  }
}

async function toggle(token) {
  await api(`/admin/api/tokens/${token.id}/toggle`, { method: 'POST' })
  await load()
}

async function remove(token) {
  if (!window.confirm('确认删除该访问令牌？')) return
  await api(`/admin/api/tokens/${token.id}`, { method: 'DELETE' })
  await load()
}

function copy(value) {
  navigator.clipboard.writeText(value)
}

onMounted(() => load().catch((err) => { error.value = err.message }))
</script>

<template>
  <PageHeader
    title="访问令牌"
    description="控制客户端访问 /v1 接口时使用的 Bearer Token。"
  >
    <template #actions>
      <button class="button button--primary" type="button" @click="adding = !adding">
        <Plus :size="16" />
        创建令牌
      </button>
    </template>
  </PageHeader>

  <p v-if="error" class="notice notice--error">{{ error }}</p>
  <div v-if="!tokens.length" class="notice notice--warning">
    当前没有启用的访问令牌，所有客户端均可调用网关接口。
  </div>
  <div v-if="createdToken" class="secret-reveal">
    <div>
      <strong>新令牌仅完整显示这一次</strong>
      <code>{{ createdToken }}</code>
    </div>
    <button class="button button--secondary" type="button" @click="copy(createdToken)">
      <Copy :size="16" />复制
    </button>
  </div>

  <form v-if="adding" class="surface inline-form" @submit.prevent="addToken">
    <label class="field">
      <span>自定义令牌</span>
      <input v-model="form.token" placeholder="留空则自动生成" autocomplete="off" />
    </label>
    <label class="field">
      <span>备注</span>
      <input v-model="form.label" placeholder="例如：生产客户端" />
    </label>
    <button class="button button--primary" type="submit">创建令牌</button>
  </form>

  <section class="surface table-section">
    <div class="section-heading">
      <div>
        <p class="section-kicker">CLIENT ACCESS</p>
        <h2>令牌列表</h2>
      </div>
      <StatusBadge :tone="tokens.some((token) => token.enabled) ? 'success' : 'warning'">
        {{ tokens.filter((token) => token.enabled).length }} 个启用
      </StatusBadge>
    </div>
    <div v-if="tokens.length" class="token-list">
      <article v-for="token in tokens" :key="token.id" class="token-row">
        <span class="model-icon"><ShieldCheck :size="18" /></span>
        <div class="token-main">
          <strong>{{ token.label || `访问令牌 #${token.id}` }}</strong>
          <code>{{ token.token }}</code>
        </div>
        <span class="muted">{{ dateTime(token.created_at) }}</span>
        <StatusBadge :tone="token.enabled ? 'success' : 'neutral'">
          {{ token.enabled ? '启用' : '禁用' }}
        </StatusBadge>
        <label class="switch" :title="token.enabled ? '禁用令牌' : '启用令牌'">
          <input type="checkbox" :checked="token.enabled" @change="toggle(token)" />
          <span />
        </label>
        <button class="icon-button icon-button--danger" type="button" title="删除令牌" @click="remove(token)">
          <Trash2 :size="16" />
        </button>
      </article>
    </div>
    <EmptyState v-else title="没有访问令牌" description="创建令牌后，网关将开始验证客户端身份。" />
  </section>
</template>
