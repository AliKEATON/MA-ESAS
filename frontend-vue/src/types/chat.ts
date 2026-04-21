import type {
  AnalysisResultResponse,
  AnalysisTaskProgressResponse,
  ConversationTaskResponse,
  MessageResponse,
} from '@/types/api'

export type DisplayMessageKind = 'user' | 'assistant' | 'analysis-task'

export type TaskPollingState = {
  lastSignature: string | null
  stagnantRounds: number
  autoPollEnabled: boolean
  timerId: number | null
}

export type DisplayMessage = {
  id: string
  kind: DisplayMessageKind
  createdAt: string
  message?: MessageResponse
  task?: ConversationTaskResponse
  progress?: AnalysisTaskProgressResponse
  result?: AnalysisResultResponse
}
