<script setup>
import { ArrowRight, KeyRound, LockKeyhole, ShieldCheck } from '@lucide/vue'
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api, jsonBody } from '../api'

const route = useRoute()
const router = useRouter()
const password = ref('')
const loading = ref(false)
const error = ref('')

async function submit() {
  loading.value = true
  error.value = ''
  try {
    await api('/admin/api/login', {
      method: 'POST',
      body: jsonBody({ password: password.value }),
    })
    router.replace(String(route.query.redirect || '/overview'))
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <main class="login-page">
    <section class="login-identity">
      <div class="login-wordmark">
        <span class="brand-mark brand-mark--large">N</span>
        <span>NVIDIA NIM Gateway</span>
      </div>
      <div class="login-copy">
        <p class="eyebrow">CONTROL PLANE</p>
        <h1>一个安静、可靠的<br />模型流量入口。</h1>
        <p>集中管理上游密钥、模型目录、访问令牌与运行状态。</p>
      </div>
      <div class="login-trust">
        <span><ShieldCheck :size="17" /> HttpOnly 会话</span>
        <span><KeyRound :size="17" /> 密钥脱敏展示</span>
      </div>
    </section>

    <section class="login-panel">
      <form class="login-form" @submit.prevent="submit">
        <div class="login-form-icon"><LockKeyhole :size="24" /></div>
        <div>
          <p class="eyebrow">ADMIN ACCESS</p>
          <h2>登录控制台</h2>
          <p>请输入 config.toml 中配置的管理密码。</p>
        </div>
        <label class="field">
          <span>管理密码</span>
          <input
            v-model="password"
            type="password"
            autocomplete="current-password"
            placeholder="输入密码"
            autofocus
          />
        </label>
        <p v-if="error" class="form-error">{{ error }}</p>
        <button class="button button--primary button--wide" type="submit" :disabled="loading || !password">
          <span>{{ loading ? '正在验证' : '进入控制台' }}</span>
          <ArrowRight :size="17" />
        </button>
      </form>
    </section>
  </main>
</template>
