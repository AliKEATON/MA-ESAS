import { request } from '@/api/client'
import type { AuthResponse, PasswordChangeResponse, UserResponse } from '@/types/api'

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

/** 调用修改密码接口。 */
export function changePassword(currentPassword: string, newPassword: string) {
  return request<PasswordChangeResponse>('POST', '/api/auth/change-password', {
    data: {
      current_password: currentPassword,
      new_password: newPassword,
    },
  })
}
