import axios, { AxiosError } from 'axios'

import type { ApiResponse } from '@/types/api'

const TOKEN_STORAGE_KEY = 'ma_esas_token'

type ValidationDetailItem = {
  loc?: Array<string | number>
  msg?: string
}

export class ApiClientError extends Error {
  statusCode: number

  constructor(message: string, statusCode = 500) {
    super(message)
    this.name = 'ApiClientError'
    this.statusCode = statusCode
  }
}

/** 将后端错误对象转换成可读文本。 */
function formatErrorMessage(payload: unknown): string | null {
  if (!payload || typeof payload !== 'object') {
    return null
  }

  if ('detail' in payload) {
    const detail = payload.detail
    if (typeof detail === 'string') {
      return detail
    }

    if (Array.isArray(detail)) {
      const messages = detail
        .map((item) => {
          const validationItem = item as ValidationDetailItem | null
          if (!validationItem || typeof validationItem !== 'object') {
            return null
          }

          const fieldName = Array.isArray(validationItem.loc)
            ? String(validationItem.loc[validationItem.loc.length - 1] || '')
            : ''

          if (fieldName === 'current_password' || fieldName === 'new_password') {
            return '密码长度不能少于 6 位。'
          }

          return validationItem.msg || null
        })
        .filter((message): message is string => Boolean(message))

      if (messages.length > 0) {
        return Array.from(new Set(messages)).join(' ')
      }
    }
  }

  if ('message' in payload && typeof payload.message === 'string') {
    return payload.message
  }

  return null
}

/** 创建统一的 Axios 实例，并处理鉴权与错误转换。 */
export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
  timeout: 30000,
})

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_STORAGE_KEY)
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiResponse<unknown> | { detail?: unknown; message?: string }>) => {
    if (error.response?.status === 401) {
      localStorage.removeItem(TOKEN_STORAGE_KEY)
      if (window.location.pathname !== '/auth') {
        window.location.href = '/auth'
      }
    }

    const payload = error.response?.data
    const message = formatErrorMessage(payload) || error.message || '请求失败'

    return Promise.reject(new ApiClientError(String(message), error.response?.status || 500))
  },
)

/** 统一发送请求，并返回带 HTTP 状态码的业务响应。 */
export async function request<T>(
  method: 'GET' | 'POST' | 'PATCH' | 'DELETE',
  path: string,
  options?: {
    data?: Record<string, unknown>
    timeout?: number
    allowStatuses?: number[]
  },
): Promise<ApiResponse<T>> {
  const response = await apiClient.request<ApiResponse<T>>({
    method,
    url: path,
    data: options?.data,
    timeout: options?.timeout,
    validateStatus(status) {
      const allowed = options?.allowStatuses || [200, 201, 202]
      return allowed.includes(status)
    },
  })

  if (typeof response.data !== 'object' || response.data === null) {
    throw new ApiClientError('后端返回了无效响应', response.status)
  }

  return {
    ...response.data,
    _http_status: response.status,
  }
}

export { TOKEN_STORAGE_KEY }
