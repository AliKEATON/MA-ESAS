export type ApiResponse<T> = {
  code: number
  data: T
  message: string
  _http_status?: number
}

export type UserResponse = {
  id: number
  username: string
  email: string
  is_active: boolean
  created_at: string
}

export type AuthResponse = {
  user: UserResponse
  access_token: string
  token_type: string
  expires_in: number
}

export type AnalysisTaskStatus = 'pending' | 'processing' | 'completed' | 'failed'
export type AnalysisStepStatus = 'pending' | 'processing' | 'completed' | 'failed'
export type MessageRole = 'user' | 'assistant' | 'system'
export type MessageType = 'chat' | 'analysis_request' | 'analysis_result' | 'system_notice'

export type MessageResponse = {
  id: number
  role: MessageRole
  message_type: MessageType
  content: string
  created_at: string
}

export type AnalysisTaskSummaryResponse = {
  task_id: string
  status: AnalysisTaskStatus
  progress: number
  current_step: string | null
  product_id: number | null
}

export type ConversationTaskResponse = {
  task_id: string
  status: AnalysisTaskStatus
  progress: number
  current_step: string | null
  product_id: number | null
  question: string
  report_ready: boolean
  created_at: string
  finished_at: string | null
}

export type MessageSendResponse = {
  user_message: MessageResponse
  analysis_task: AnalysisTaskSummaryResponse
}

export type ConversationResponse = {
  id: number
  title: string | null
  bound_product_id: number | null
  last_message_preview: string | null
  latest_task: AnalysisTaskSummaryResponse | null
  task_count: number
  completed_task_count: number
  created_at: string
  updated_at: string
}

export type ConversationListResponse = {
  total: number
  page: number
  page_size: number
  items: ConversationResponse[]
}

export type ConversationDetailResponse = {
  id: number
  title: string | null
  bound_product_id: number | null
  messages: MessageResponse[]
  tasks: ConversationTaskResponse[]
  created_at: string
  updated_at: string
}

export type AnalysisTaskStepResponse = {
  step: string
  label: string
  status: AnalysisStepStatus
}

export type AnalysisTaskProgressResponse = {
  task_id: string
  status: AnalysisTaskStatus
  current_step: string | null
  progress: number
  steps: AnalysisTaskStepResponse[]
  report_ready: boolean
  error_message: string | null
}

export type AnalysisProductResponse = {
  product_id: number
  source: string
  external_product_id: string
  product_name: string | null
}

export type AnalysisEvidenceItem = {
  content: string
  score: number | null
  dimension: string | null
  similarity: number | null
}

export type FinalResponseChartSeries = {
  name: string
  data: Array<number | string | { name: string; value: number }>
}

export type FinalResponseChart = {
  chart_id: string
  chart_type: 'bar' | 'line' | 'pie' | 'scatter' | 'radar' | 'stacked_bar'
  title: string
  description?: string | null
  x_axis: Array<string | number>
  series: FinalResponseChartSeries[]
}

export type FinalResponsePayload = {
  answer?: string | null
  charts?: FinalResponseChart[]
  meta?: Record<string, unknown> | null
}

export type AnalysisResultResponse = {
  report_id: number
  task_id: string
  conversation_id: number | null
  product: AnalysisProductResponse | null
  product_context?: Record<string, unknown> | null
  data_context?: Record<string, unknown> | null
  final_response: FinalResponsePayload
  route_decision?: Record<string, unknown> | null
  sql_result?: Record<string, unknown> | null
  visual_result?: Record<string, unknown> | null
  rag_result?: Record<string, unknown> | null
  answer_draft?: Record<string, unknown> | null
  master_decision?: Record<string, unknown> | null
  retry_count?: number
  evidence: AnalysisEvidenceItem[]
  created_at: string
  result_ready?: boolean
}
