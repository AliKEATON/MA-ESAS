import { request } from '@/api/client'
import type {
  ConversationDetailResponse,
  ConversationListResponse,
  ConversationResponse,
  MessageResponse,
  MessageSendResponse,
} from '@/types/api'

/** 获取会话列表。 */
export function listConversations(page = 1, pageSize = 50) {
  return request<ConversationListResponse>('GET', `/api/conversations?page=${page}&page_size=${pageSize}`)
}

/** 创建新会话。 */
export function createConversation(boundProductId?: number | null) {
  return request<ConversationResponse>('POST', '/api/conversations', {
    data: { bound_product_id: boundProductId ?? null },
  })
}

/** 获取会话详情。 */
export function getConversationDetail(conversationId: number) {
  return request<ConversationDetailResponse>('GET', `/api/conversations/${conversationId}`)
}

/** 更新会话标题。 */
export function updateConversation(conversationId: number, title: string) {
  return request<ConversationResponse>('PATCH', `/api/conversations/${conversationId}`, {
    data: { title },
  })
}

/** 删除会话。 */
export function deleteConversation(conversationId: number) {
  return request<{ conversation_id: number }>('DELETE', `/api/conversations/${conversationId}`)
}

/** 获取会话消息列表。 */
export function getMessages(conversationId: number) {
  return request<MessageResponse[]>('GET', `/api/conversations/${conversationId}/messages`)
}

/** 统一发送消息。 */
export function sendMessage(conversationId: number, content: string) {
  return request<MessageSendResponse>('POST', `/api/conversations/${conversationId}/messages`, {
    data: { content },
    timeout: 60000,
  })
}
