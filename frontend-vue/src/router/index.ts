import { createRouter, createWebHistory } from 'vue-router'

import { TOKEN_STORAGE_KEY } from '@/api/client'
import AuthWorkspaceView from '@/views/AuthWorkspaceView.vue'
import ChatWorkbenchView from '@/views/ChatWorkbenchView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/chat' },
    { path: '/auth', name: 'auth', component: AuthWorkspaceView, meta: { requiresGuest: true } },
    { path: '/chat', name: 'chat', component: ChatWorkbenchView, meta: { requiresAuth: true } },
  ],
})

/** 根据本地 token 控制登录页与聊天页的访问权限。 */
router.beforeEach((to) => {
  const hasToken = Boolean(localStorage.getItem(TOKEN_STORAGE_KEY))

  if (to.meta.requiresAuth && !hasToken) {
    return { path: '/auth' }
  }

  if (to.meta.requiresGuest && hasToken) {
    return { path: '/chat' }
  }

  return true
})

export default router
