<script setup>
import {
  Activity,
  BookOpen,
  Boxes,
  ChevronRight,
  Gauge,
  KeyRound,
  LogOut,
  Menu,
  Settings,
  ShieldCheck,
  X,
} from '@lucide/vue'
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api } from '../api'

const route = useRoute()
const router = useRouter()
const mobileOpen = ref(false)

const nav = [
  { to: '/overview', label: '运行概览', icon: Gauge },
  { to: '/checks', label: '模型检测', icon: Activity },
  { to: '/models', label: '模型管理', icon: Boxes },
  { to: '/keys', label: '上游密钥', icon: KeyRound },
  { to: '/tokens', label: '访问令牌', icon: ShieldCheck },
  { to: '/settings', label: '网关配置', icon: Settings },
  { to: '/docs', label: '接口文档', icon: BookOpen },
]

async function logout() {
  await api('/admin/api/logout', { method: 'POST' })
  router.replace('/login')
}
</script>

<template>
  <div class="app-shell">
    <header class="mobile-header glass-nav">
      <div class="brand brand--compact">
        <span class="brand-mark" aria-hidden="true">N</span>
        <span>NIM Gateway</span>
      </div>
      <button class="icon-button" type="button" aria-label="打开导航" @click="mobileOpen = true">
        <Menu :size="20" />
      </button>
    </header>

    <button
      v-if="mobileOpen"
      class="nav-scrim"
      aria-label="关闭导航"
      @click="mobileOpen = false"
    />

    <aside class="sidebar" :class="{ 'sidebar--open': mobileOpen }">
      <div class="sidebar-top">
        <div class="brand">
          <span class="brand-mark" aria-hidden="true">N</span>
          <span>
            <strong>NIM Gateway</strong>
            <small>Control plane</small>
          </span>
        </div>
        <button class="icon-button sidebar-close" type="button" aria-label="关闭导航" @click="mobileOpen = false">
          <X :size="20" />
        </button>
      </div>

      <nav class="main-nav" aria-label="主要导航">
        <RouterLink
          v-for="item in nav"
          :key="item.to"
          :to="item.to"
          class="nav-link"
          @click="mobileOpen = false"
        >
          <component :is="item.icon" :size="18" />
          <span>{{ item.label }}</span>
          <ChevronRight :size="15" class="nav-chevron" />
        </RouterLink>
      </nav>

      <div class="sidebar-footer">
        <div class="gateway-state">
          <span class="state-dot" />
          <span>Gateway online</span>
        </div>
        <button class="nav-link logout-button" type="button" @click="logout">
          <LogOut :size="18" />
          <span>退出登录</span>
        </button>
      </div>
    </aside>

    <main class="main-content">
      <div class="page-frame">
        <slot />
      </div>
    </main>
  </div>
</template>
