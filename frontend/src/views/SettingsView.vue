<script setup>
import { AlertTriangle, CalendarClock, MessageSquareText, Save, ServerCog } from '@lucide/vue'
import { onMounted, ref } from 'vue'

import { api, jsonBody } from '../api'
import PageHeader from '../components/PageHeader.vue'

const form = ref({
  upstream_base_url: '',
  cooldown_seconds: 60,
  listen_port: 5010,
  model_check_enabled: false,
  model_check_interval_minutes: 60,
  system_prompt_mode: 'passthrough',
  system_prompt: '',
  admin_password: '',
  confirm_password: '',
})
const loading = ref(false)
const notice = ref('')
const error = ref('')

async function load() {
  try {
    const data = await api('/admin/api/config')
    form.value = { ...form.value, ...data, admin_password: '', confirm_password: '' }
  } catch (err) {
    error.value = err.message
  }
}

async function save() {
  error.value = ''
  notice.value = ''
  if (form.value.admin_password && form.value.admin_password !== form.value.confirm_password) {
    error.value = '两次输入的管理密码不一致'
    return
  }
  loading.value = true
  try {
    const result = await api('/admin/api/config', {
      method: 'PUT',
      body: jsonBody({
        upstream_base_url: form.value.upstream_base_url,
        cooldown_seconds: form.value.cooldown_seconds,
        listen_port: form.value.listen_port,
        model_check_enabled: form.value.model_check_enabled,
        model_check_interval_minutes: form.value.model_check_interval_minutes,
        system_prompt_mode: form.value.system_prompt_mode,
        system_prompt: form.value.system_prompt,
        admin_password: form.value.admin_password,
      }),
    })
    if (form.value.admin_password) {
      window.location.assign('/login')
      return
    }
    notice.value = result.restart_required
      ? '配置已保存。监听端口将在服务重启后生效。'
      : '配置已保存并立即生效。'
    await load()
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <PageHeader
    title="网关配置"
    description="调整上游服务、调度策略和控制台登录凭据。"
  />

  <p v-if="notice" class="notice notice--success">{{ notice }}</p>
  <p v-if="error" class="notice notice--error">{{ error }}</p>

  <form class="settings-layout" @submit.prevent="save">
    <section class="surface settings-section">
      <div class="section-heading">
        <div>
          <p class="section-kicker">UPSTREAM</p>
          <h2>上游与调度</h2>
        </div>
        <ServerCog :size="20" class="muted" />
      </div>
      <div class="form-grid">
        <label class="field field--full">
          <span>上游 API 地址</span>
          <input v-model="form.upstream_base_url" type="url" required placeholder="https://integrate.api.nvidia.com/v1" />
          <small>所有模型和聊天请求都会转发到这个基础地址。</small>
        </label>
        <label class="field">
          <span>冷却时间</span>
          <div class="input-suffix">
            <input v-model.number="form.cooldown_seconds" type="number" min="1" max="86400" required />
            <span>秒</span>
          </div>
          <small>Key 遇到 429、5xx 或网络故障后的暂停时间。</small>
        </label>
        <label class="field">
          <span>监听端口</span>
          <input v-model.number="form.listen_port" type="number" min="1" max="65535" required />
          <small>仅通过 python main.py 启动时生效，修改后需重启。</small>
        </label>
      </div>
    </section>

    <section class="surface settings-section">
      <div class="section-heading">
        <div>
          <p class="section-kicker">EDITOR PRESET</p>
          <h2>编辑器系统预设</h2>
        </div>
        <MessageSquareText :size="20" class="muted" />
      </div>
      <div class="form-grid">
        <label class="field">
          <span>注入策略</span>
          <select v-model="form.system_prompt_mode">
            <option value="passthrough">完全透传客户端预设</option>
            <option value="prepend">网关预设置于客户端预设之前</option>
            <option value="replace">使用网关预设替换客户端预设</option>
          </select>
          <small>同时作用于 Chat Completions 的系统消息和 Responses API 的 instructions。</small>
        </label>
        <label class="field field--full">
          <span>系统提示词</span>
          <textarea
            v-model="form.system_prompt"
            rows="8"
            maxlength="20000"
            :disabled="form.system_prompt_mode === 'passthrough'"
            placeholder="例如：你是一名专注于当前代码库的编程助手……"
          />
          <small>{{ form.system_prompt.length }} / 20000 字符；完全透传模式下不会注入。</small>
        </label>
      </div>
    </section>

    <section class="surface settings-section">
      <div class="section-heading">
        <div>
          <p class="section-kicker">AUTOMATION</p>
          <h2>模型检测计划</h2>
        </div>
        <CalendarClock :size="20" class="muted" />
      </div>
      <div class="automation-toggle">
        <div>
          <strong>定时检测启用模型</strong>
          <span>后台按计划发送最小推理请求，并更新模型检测状态。</span>
        </div>
        <label class="switch" title="启用或关闭定时模型检测">
          <input v-model="form.model_check_enabled" type="checkbox" />
          <span />
        </label>
      </div>
      <div class="form-grid automation-fields">
        <label class="field">
          <span>检测间隔</span>
          <div class="input-suffix">
            <input
              v-model.number="form.model_check_interval_minutes"
              type="number"
              min="1"
              max="10080"
              required
            />
            <span>分钟</span>
          </div>
          <small>保存后立即重新计算下次执行时间，范围 1 分钟到 7 天。</small>
        </label>
      </div>
    </section>

    <section class="surface settings-section">
      <div class="section-heading">
        <div>
          <p class="section-kicker">SECURITY</p>
          <h2>管理密码</h2>
        </div>
      </div>
      <div class="notice notice--subtle">
        <AlertTriangle :size="17" />
        修改密码后当前会话会立即退出，请使用新密码重新登录。
      </div>
      <div class="form-grid">
        <label class="field">
          <span>新管理密码</span>
          <input v-model="form.admin_password" type="password" minlength="8" autocomplete="new-password" placeholder="留空表示不修改" />
        </label>
        <label class="field">
          <span>确认新密码</span>
          <input v-model="form.confirm_password" type="password" autocomplete="new-password" placeholder="再次输入新密码" />
        </label>
      </div>
    </section>

    <div class="settings-actions">
      <button class="button button--primary" type="submit" :disabled="loading">
        <Save :size="16" />
        {{ loading ? '保存中' : '保存配置' }}
      </button>
    </div>
  </form>
</template>
