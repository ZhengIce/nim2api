import { createRouter, createWebHistory } from 'vue-router'

import ChecksView from './views/ChecksView.vue'
import DocsView from './views/DocsView.vue'
import KeysView from './views/KeysView.vue'
import LoginView from './views/LoginView.vue'
import ModelsView from './views/ModelsView.vue'
import OverviewView from './views/OverviewView.vue'
import SettingsView from './views/SettingsView.vue'
import TokensView from './views/TokensView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/overview' },
    { path: '/login', component: LoginView, meta: { public: true } },
    { path: '/overview', component: OverviewView, meta: { title: '运行概览' } },
    { path: '/checks', component: ChecksView, meta: { title: '模型检测' } },
    { path: '/models', component: ModelsView, meta: { title: '模型管理' } },
    { path: '/keys', component: KeysView, meta: { title: '上游密钥' } },
    { path: '/tokens', component: TokensView, meta: { title: '访问令牌' } },
    { path: '/settings', component: SettingsView, meta: { title: '网关配置' } },
    { path: '/docs', component: DocsView, meta: { title: '接口文档' } },
  ],
})

router.beforeEach(async (to) => {
  if (to.meta.public) return true
  try {
    const response = await fetch('/admin/api/session', { credentials: 'same-origin' })
    if (response.ok) return true
  } catch {
    return true
  }
  return { path: '/login', query: { redirect: to.fullPath } }
})

export default router
