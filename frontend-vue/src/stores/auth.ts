import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { ApiClientError, TOKEN_STORAGE_KEY } from '@/api/client'
import * as authApi from '@/api/modules/auth'
import type { UserResponse } from '@/types/api'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem(TOKEN_STORAGE_KEY))
  const currentUser = ref<UserResponse | null>(null)
  const loading = ref(false)
  const initialized = ref(false)

  /** 判断当前是否已登录。 */
  const isAuthenticated = computed(() => Boolean(token.value && currentUser.value))

  /** 写入新的登录态并同步到本地存储。 */
  function setAuthState(nextToken: string, user: UserResponse) {
    token.value = nextToken
    currentUser.value = user
    localStorage.setItem(TOKEN_STORAGE_KEY, nextToken)
  }

  /** 清空本地登录态。 */
  function clearAuthState() {
    token.value = null
    currentUser.value = null
    localStorage.removeItem(TOKEN_STORAGE_KEY)
  }

  /** 通过 /me 恢复登录态，失败时清空无效 token。 */
  async function hydrateAuthState() {
    if (!token.value) {
      initialized.value = true
      return
    }

    loading.value = true
    try {
      const response = await authApi.getCurrentUser()
      currentUser.value = response.data
    } catch (error) {
      clearAuthState()
      if (!(error instanceof ApiClientError && error.statusCode === 401)) {
        throw error
      }
    } finally {
      loading.value = false
      initialized.value = true
    }
  }

  /** 调用登录接口并建立本地登录态。 */
  async function login(username: string, password: string) {
    loading.value = true
    try {
      const response = await authApi.login(username, password)
      setAuthState(response.data.access_token, response.data.user)
      initialized.value = true
      return response.data.user
    } finally {
      loading.value = false
    }
  }

  /** 调用注册接口。 */
  async function register(username: string, email: string, password: string) {
    loading.value = true
    try {
      return await authApi.register(username, email, password)
    } finally {
      loading.value = false
    }
  }

  return {
    token,
    currentUser,
    loading,
    initialized,
    isAuthenticated,
    setAuthState,
    clearAuthState,
    hydrateAuthState,
    login,
    register,
  }
})
