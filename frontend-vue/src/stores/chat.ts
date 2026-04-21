import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import * as analysisApi from '@/api/modules/analysis'
import * as conversationsApi from '@/api/modules/conversations'
import type {
  AnalysisResultResponse,
  AnalysisTaskProgressResponse,
  AnalysisTaskStatus,
  ConversationDetailResponse,
  ConversationResponse,
  ConversationTaskResponse,
} from '@/types/api'
import type { TaskPollingState } from '@/types/chat'
import { buildDisplayMessages } from '@/utils/message-timeline'

const CONVERSATION_STORAGE_KEY = 'ma_esas_active_conversation'
const STAGNANT_ROUND_LIMIT = 20
const POLL_INTERVAL_MS = 3000

function createDefaultPollingState(): TaskPollingState {
  return {
    lastSignature: null,
    stagnantRounds: 0,
    autoPollEnabled: true,
    timerId: null,
  }
}

function isTerminalStatus(status: AnalysisTaskStatus): boolean {
  return status === 'completed' || status === 'failed'
}

export const useChatStore = defineStore('chat', () => {
  const conversations = ref<ConversationResponse[]>([])
  const currentConversationId = ref<number | null>(readStoredConversationId())
  const currentConversationDetail = ref<ConversationDetailResponse | null>(null)
  const loadingConversations = ref(false)
  const loadingConversationDetail = ref(false)
  const sendingMessage = ref(false)
  const sidebarCollapsed = ref(false)

  const taskProgressCache = ref<Record<string, AnalysisTaskProgressResponse>>({})
  const taskResultCache = ref<Record<string, AnalysisResultResponse>>({})
  const taskPollingState = ref<Record<string, TaskPollingState>>({})

  /** 生成聊天区最终显示的消息流。 */
  const displayMessages = computed(() => {
    return buildDisplayMessages(
      currentConversationDetail.value,
      taskProgressCache.value,
      taskResultCache.value,
    )
  })

  /** 写入当前激活会话 id。 */
  function setCurrentConversationId(conversationId: number | null) {
    currentConversationId.value = conversationId
    if (conversationId === null) {
      localStorage.removeItem(CONVERSATION_STORAGE_KEY)
      return
    }
    localStorage.setItem(CONVERSATION_STORAGE_KEY, String(conversationId))
  }

  /** 读取并刷新会话列表。 */
  async function fetchConversations() {
    loadingConversations.value = true
    try {
      const response = await conversationsApi.listConversations()
      conversations.value = response.data.items

      const existingIds = new Set(conversations.value.map((item) => item.id))
      if (currentConversationId.value && !existingIds.has(currentConversationId.value)) {
        setCurrentConversationId(null)
        currentConversationDetail.value = null
      }

      if (!currentConversationId.value && conversations.value.length > 0) {
        setCurrentConversationId(conversations.value[0].id)
      }
    } finally {
      loadingConversations.value = false
    }
  }

  /** 读取当前会话详情，并为任务同步进度和轮询。 */
  async function fetchConversationDetail(conversationId = currentConversationId.value) {
    if (!conversationId) {
      currentConversationDetail.value = null
      return null
    }

    loadingConversationDetail.value = true
    try {
      const response = await conversationsApi.getConversationDetail(conversationId)
      currentConversationDetail.value = response.data
      setCurrentConversationId(response.data.id)
      syncTaskCaches(response.data.tasks)
      ensureTaskResults(response.data.tasks)
      syncTaskPolling(response.data.tasks)
      return response.data
    } finally {
      loadingConversationDetail.value = false
    }
  }

  /** 创建新会话并切换过去。 */
  async function createConversation() {
    const response = await conversationsApi.createConversation(null)
    await fetchConversations()
    setCurrentConversationId(response.data.id)
    await fetchConversationDetail(response.data.id)
    return response.data
  }

  /** 切换当前会话，并清理旧会话轮询。 */
  async function selectConversation(conversationId: number) {
    stopAllPolling()
    setCurrentConversationId(conversationId)
    await fetchConversationDetail(conversationId)
  }

  /** 更新会话标题后刷新列表与详情。 */
  async function renameConversation(conversationId: number, title: string) {
    await conversationsApi.updateConversation(conversationId, title)
    await fetchConversations()
    if (currentConversationId.value === conversationId) {
      await fetchConversationDetail(conversationId)
    }
  }

  /** 删除会话后自动切换到剩余会话。 */
  async function removeConversation(conversationId: number) {
    await conversationsApi.deleteConversation(conversationId)
    if (currentConversationId.value === conversationId) {
      stopAllPolling()
      setCurrentConversationId(null)
      currentConversationDetail.value = null
    }
    await fetchConversations()
    if (currentConversationId.value) {
      await fetchConversationDetail(currentConversationId.value)
    }
  }

  /** 确保消息发送前有可用会话。 */
  async function ensureConversation() {
    if (currentConversationId.value) {
      return currentConversationId.value
    }
    const conversation = await createConversation()
    return conversation.id
  }

  /** 统一发送消息，并按 handling_mode 衔接会话刷新与任务轮询。 */
  async function sendMessage(content: string) {
    sendingMessage.value = true
    try {
      const conversationId = await ensureConversation()
      const response = await conversationsApi.sendMessage(conversationId, content)
      await fetchConversations()
      await fetchConversationDetail(conversationId)

      if (response.data.analysis_task) {
        startPollingTask(response.data.analysis_task.task_id)
      }
      return response.data
    } finally {
      sendingMessage.value = false
    }
  }

  /** 重试失败任务后重置其缓存状态并恢复轮询。 */
  async function retryTask(taskId: string) {
    await analysisApi.retryTask(taskId)
    delete taskResultCache.value[taskId]
    delete taskProgressCache.value[taskId]
    resetPollingState(taskId)
    if (currentConversationId.value) {
      await fetchConversationDetail(currentConversationId.value)
    }
    startPollingTask(taskId)
  }

  /** 停止所有轮询定时器。 */
  function stopAllPolling() {
    Object.keys(taskPollingState.value).forEach((taskId) => stopPollingTask(taskId))
  }

  /** 折叠或展开侧边栏。 */
  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  /** 同步任务摘要到本地进度缓存。 */
  function syncTaskCaches(tasks: ConversationTaskResponse[]) {
    const validTaskIds = new Set(tasks.map((item) => item.task_id))
    for (const task of tasks) {
      if (!taskProgressCache.value[task.task_id]) {
        taskProgressCache.value[task.task_id] = {
          task_id: task.task_id,
          status: task.status,
          current_step: task.current_step,
          progress: task.progress,
          steps: [],
          report_ready: task.report_ready,
          error_message: null,
        }
      }
      if (!taskPollingState.value[task.task_id]) {
        taskPollingState.value[task.task_id] = createDefaultPollingState()
      }
    }

    Object.keys(taskPollingState.value).forEach((taskId) => {
      if (!validTaskIds.has(taskId)) {
        stopPollingTask(taskId)
        delete taskPollingState.value[taskId]
      }
    })
  }

  /** 为已完成但尚未缓存结果的任务补拉一次结果。 */
  function ensureTaskResults(tasks: ConversationTaskResponse[]) {
    for (const task of tasks) {
      if (task.status === 'completed' && !taskResultCache.value[task.task_id]) {
        void fetchTaskResult(task.task_id)
      }
    }
  }

  /** 按当前任务状态自动启动或停止轮询。 */
  function syncTaskPolling(tasks: ConversationTaskResponse[]) {
    for (const task of tasks) {
      if (task.status === 'pending' || task.status === 'processing') {
        startPollingTask(task.task_id)
      } else {
        stopPollingTask(task.task_id)
      }
    }
  }

  /** 启动单个任务的递归轮询。 */
  function startPollingTask(taskId: string) {
    const state = taskPollingState.value[taskId] || createDefaultPollingState()
    taskPollingState.value[taskId] = state

    if (state.timerId !== null || !state.autoPollEnabled) {
      return
    }

    if (taskResultCache.value[taskId]) {
      state.autoPollEnabled = false
      return
    }

    state.timerId = window.setTimeout(() => {
      state.timerId = null
      void pollTask(taskId)
    }, POLL_INTERVAL_MS)
  }

  /** 停止单个任务的轮询。 */
  function stopPollingTask(taskId: string) {
    const state = taskPollingState.value[taskId]
    if (!state) {
      return
    }

    if (state.timerId !== null) {
      window.clearTimeout(state.timerId)
      state.timerId = null
    }
  }

  /** 重新允许任务自动轮询。 */
  function resumeTaskPolling(taskId: string) {
    resetPollingState(taskId)
    startPollingTask(taskId)
  }

  /** 轮询任务进度，并在状态变化时同步详情和结果。 */
  async function pollTask(taskId: string) {
    const state = taskPollingState.value[taskId] || createDefaultPollingState()
    taskPollingState.value[taskId] = state

    if (!state.autoPollEnabled) {
      return
    }

    const progressResponse = await analysisApi.getTaskProgress(taskId)
    const progress = progressResponse.data
    taskProgressCache.value[taskId] = progress

    const nextSignature = JSON.stringify([
      progress.status,
      progress.current_step,
      progress.progress,
      progress.report_ready,
      progress.error_message,
    ])
    if (state.lastSignature === nextSignature) {
      state.stagnantRounds += 1
    } else {
      state.lastSignature = nextSignature
      state.stagnantRounds = 0
      if (currentConversationId.value) {
        await fetchConversationDetail(currentConversationId.value)
      }
    }

    if (progress.report_ready) {
      await fetchTaskResult(taskId)
      state.autoPollEnabled = false
      stopPollingTask(taskId)
      if (currentConversationId.value) {
        await fetchConversationDetail(currentConversationId.value)
      }
      return
    }

    if (isTerminalStatus(progress.status)) {
      state.autoPollEnabled = false
      stopPollingTask(taskId)
      return
    }

    if (state.stagnantRounds >= STAGNANT_ROUND_LIMIT) {
      state.autoPollEnabled = false
      stopPollingTask(taskId)
      return
    }

    startPollingTask(taskId)
  }

  /** 拉取任务结果，并写入结果缓存。 */
  async function fetchTaskResult(taskId: string) {
    const response = await analysisApi.getTaskResult(taskId)
    if (response._http_status === 200 && response.data) {
      taskResultCache.value[taskId] = response.data
      return response.data
    }
    return null
  }

  /** 重置单个任务的轮询状态。 */
  function resetPollingState(taskId: string) {
    stopPollingTask(taskId)
    taskPollingState.value[taskId] = createDefaultPollingState()
  }

  return {
    conversations,
    currentConversationId,
    currentConversationDetail,
    loadingConversations,
    loadingConversationDetail,
    sendingMessage,
    sidebarCollapsed,
    taskProgressCache,
    taskResultCache,
    taskPollingState,
    displayMessages,
    fetchConversations,
    fetchConversationDetail,
    createConversation,
    selectConversation,
    renameConversation,
    removeConversation,
    sendMessage,
    retryTask,
    stopAllPolling,
    toggleSidebar,
    resumeTaskPolling,
  }
})

function readStoredConversationId(): number | null {
  const raw = localStorage.getItem(CONVERSATION_STORAGE_KEY)
  if (!raw) {
    return null
  }
  const parsed = Number(raw)
  return Number.isNaN(parsed) ? null : parsed
}
