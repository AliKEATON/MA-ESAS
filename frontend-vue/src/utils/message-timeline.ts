import type {
  AnalysisResultResponse,
  AnalysisTaskProgressResponse,
  ConversationDetailResponse,
  ConversationTaskResponse,
} from '@/types/api'
import type { DisplayMessage } from '@/types/chat'

type ProgressMap = Record<string, AnalysisTaskProgressResponse>
type ResultMap = Record<string, AnalysisResultResponse>

/** 根据消息、任务、缓存结果构造聊天区最终显示用的消息流。 */
export function buildDisplayMessages(
  detail: ConversationDetailResponse | null,
  taskProgressCache: ProgressMap,
  taskResultCache: ResultMap,
): DisplayMessage[] {
  if (!detail) {
    return []
  }

  const timeline: DisplayMessage[] = []
  const availableTasks = [...detail.tasks].sort((left, right) => {
    return new Date(left.created_at).getTime() - new Date(right.created_at).getTime()
  })

  for (const message of detail.messages) {
    if (shouldHideBackendMessage(message.message_type)) {
      continue
    }

    timeline.push({
      id: `message-${message.id}`,
      kind: message.role === 'user' ? 'user' : 'assistant',
      createdAt: message.created_at,
      message,
    })

    if (message.message_type === 'analysis_request') {
      const matchedTask = matchTaskForMessage(availableTasks, message.content, message.created_at)
      if (matchedTask) {
        const progress = taskProgressCache[matchedTask.task_id]
        const result = taskResultCache[matchedTask.task_id]
        timeline.push({
          id: `task-${matchedTask.task_id}`,
          kind: 'analysis-task',
          createdAt: progress?.current_step ? matchedTask.created_at : message.created_at,
          task: matchedTask,
          progress,
          result,
        })
      }
    }
  }

  for (const unmatchedTask of availableTasks) {
    timeline.push({
      id: `task-${unmatchedTask.task_id}`,
      kind: 'analysis-task',
      createdAt: unmatchedTask.created_at,
      task: unmatchedTask,
      progress: taskProgressCache[unmatchedTask.task_id],
      result: taskResultCache[unmatchedTask.task_id],
    })
  }

  return timeline.sort((left, right) => {
    return new Date(left.createdAt).getTime() - new Date(right.createdAt).getTime()
  })
}

/** 过滤后端原始系统通知和分析结果消息，避免在前端重复显示。 */
function shouldHideBackendMessage(messageType: string): boolean {
  return messageType === 'system_notice' || messageType === 'analysis_result'
}

/** 用问题文本和时间顺序把分析任务匹配回对应的分析请求消息。 */
function matchTaskForMessage(
  tasks: ConversationTaskResponse[],
  question: string,
  messageCreatedAt: string,
): ConversationTaskResponse | undefined {
  const directIndex = tasks.findIndex((task) => task.question === question)
  if (directIndex >= 0) {
    return tasks.splice(directIndex, 1)[0]
  }

  const messageTimestamp = new Date(messageCreatedAt).getTime()
  const fallbackIndex = tasks.findIndex((task) => new Date(task.created_at).getTime() >= messageTimestamp)
  if (fallbackIndex >= 0) {
    return tasks.splice(fallbackIndex, 1)[0]
  }

  return tasks.shift()
}
