import { request } from '@/api/client'
import type { AnalysisResultResponse, AnalysisTaskProgressResponse } from '@/types/api'

/** 获取分析任务进度。 */
export function getTaskProgress(taskId: string) {
  return request<AnalysisTaskProgressResponse>('GET', `/api/analysis/tasks/${taskId}`)
}

/** 获取分析任务结果。 */
export function getTaskResult(taskId: string) {
  return request<AnalysisResultResponse | null>('GET', `/api/analysis/tasks/${taskId}/result`, {
    allowStatuses: [200, 202],
  })
}

/** 重试失败任务。 */
export function retryTask(taskId: string) {
  return request<AnalysisTaskProgressResponse>('POST', `/api/analysis/tasks/${taskId}/retry`)
}
