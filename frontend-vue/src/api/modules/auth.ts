import { request } from '@/api/client'
import type { AuthResponse, UserResponse } from '@/types/api'

/** 调用注册接口。 */
export function register(username: string, email: string, password: string) {
  return request<UserResponse>('POST', '/api/auth/register', {
    data: { username, email, password },
  })
}

/** 调用登录接口。 */
export function login(username: string, password: string) {
  return request<AuthResponse>('POST', '/api/auth/login', {
    data: { username, password },
  })
}

/** 获取当前登录用户信息。 */
export function getCurrentUser() {
  return request<UserResponse>('GET', '/api/auth/me')
}
