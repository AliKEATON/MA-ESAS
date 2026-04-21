import axios, { AxiosError } from 'axios'

import type { ApiResponse } from '@/types/api'

const TOKEN_STORAGE_KEY = 'ma_esas_token'

export class ApiClientError extends Error {
  statusCode: number

  constructor(message: string, statusCode = 500) {
    super(message)
    this.name = 'ApiClientError'
    this.statusCode = statusCode
  }
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
  (error: AxiosError<ApiResponse<unknown> | { detail?: string }>) => {
    if (error.response?.status === 401) {
      localStorage.removeItem(TOKEN_STORAGE_KEY)
      if (window.location.pathname !== '/auth') {
        window.location.href = '/auth'
      }
    }

    const payload = error.response?.data
    const message =
      (typeof payload === 'object' && payload && 'detail' in payload && payload.detail) ||
      (typeof payload === 'object' && payload && 'message' in payload && payload.message) ||
      error.message ||
      '请求失败'

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
