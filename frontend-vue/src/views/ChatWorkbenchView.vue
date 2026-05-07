<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { ApiClientError } from '@/api/client'
import ChatMessageList from '@/components/chat/ChatMessageList.vue'
import WorkspaceComposer from '@/components/chat/WorkspaceComposer.vue'
import WorkspaceSidebar from '@/components/sidebar/WorkspaceSidebar.vue'
import { useAuthStore } from '@/stores/auth'
import { useChatStore } from '@/stores/chat'

const router = useRouter()
const authStore = useAuthStore()
const chatStore = useChatStore()

const feedbackMessage = ref('')
const isEditingTitle = ref(false)
const titleDraft = ref('')

const currentConversation = computed(() => chatStore.currentConversationDetail)
const currentConversationTitle = computed(() => {
  if (currentConversation.value?.title) {
    return currentConversation.value.title
  }
  if (currentConversation.value) {
    return `会话 ${currentConversation.value.id}`
  }
  return '新会话'
})

/** 初始化聊天页，优先恢复会话列表和当前详情。 */
async function initializeChatView() {
  try {
    await chatStore.fetchConversations()
    if (chatStore.currentConversationId) {
      await chatStore.fetchConversationDetail(chatStore.currentConversationId)
    }
  } catch (error) {
    handleError(error, '加载聊天数据失败')
  }
}

/** 统一处理界面错误提示。 */
function handleError(error: unknown, fallbackMessage: string) {
  feedbackMessage.value = error instanceof ApiClientError ? error.message : fallbackMessage
}

/** 创建会话并切换到新会话。 */
async function createConversation() {
  feedbackMessage.value = ''
  try {
    await chatStore.createConversation()
  } catch (error) {
    handleError(error, '创建会话失败')
  }
}

/** 刷新侧边栏和当前会话数据。 */
async function refreshData() {
  feedbackMessage.value = ''
  try {
    await chatStore.fetchConversations()
    if (chatStore.currentConversationId) {
      await chatStore.fetchConversationDetail(chatStore.currentConversationId)
    }
  } catch (error) {
    handleError(error, '刷新失败')
  }
}

/** 执行退出登录。 */
async function logout() {
  chatStore.stopAllPolling()
  authStore.clearAuthState()
  await router.push('/auth')
}

/** 发送聊天输入内容。 */
async function onSend(content: string) {
  feedbackMessage.value = ''
  try {
    await chatStore.sendMessage(content)
  } catch (error) {
    handleError(error, '发送消息失败')
  }
}

/** 重试失败的分析任务。 */
async function onRetryTask(taskId: string) {
  feedbackMessage.value = ''
  try {
    await chatStore.retryTask(taskId)
  } catch (error) {
    handleError(error, '重试任务失败')
  }
}

/** 保存当前会话标题。 */
async function saveConversationTitle() {
  if (!chatStore.currentConversationId || !titleDraft.value.trim()) {
    isEditingTitle.value = false
    return
  }

  feedbackMessage.value = ''
  try {
    await chatStore.renameConversation(chatStore.currentConversationId, titleDraft.value.trim())
    isEditingTitle.value = false
  } catch (error) {
    handleError(error, '更新会话标题失败')
  }
}

/** 从侧边栏触发会话重命名。 */
async function openRenameConversation(conversationId: number) {
  feedbackMessage.value = ''
  if (chatStore.currentConversationId !== conversationId) {
    try {
      await chatStore.selectConversation(conversationId)
    } catch (error) {
      handleError(error, '加载会话失败，无法重命名')
      return
    }
  }
  isEditingTitle.value = true
}

/** 从侧边栏触发会话删除。 */
async function removeConversationFromSidebar(conversationId: number) {
  feedbackMessage.value = ''
  if (!window.confirm('确认删除这个会话吗？')) {
    return
  }

  try {
    await chatStore.removeConversation(conversationId)
  } catch (error) {
    handleError(error, '删除会话失败')
  }
}

watch(
  currentConversationTitle,
  (title) => {
    titleDraft.value = title
  },
  { immediate: true },
)

onMounted(() => {
  void initializeChatView()
})

onBeforeUnmount(() => {
  chatStore.stopAllPolling()
})
</script>

<template>
  <main class="chat-workbench">
    <WorkspaceSidebar
      :collapsed="chatStore.sidebarCollapsed"
      :conversations="chatStore.conversations"
      :current-conversation-id="chatStore.currentConversationId"
      :current-user="authStore.currentUser"
      :loading="chatStore.loadingConversations"
      @toggle="chatStore.toggleSidebar"
      @create-conversation="createConversation"
      @refresh="refreshData"
      @select-conversation="chatStore.selectConversation"
      @rename-conversation="openRenameConversation"
      @delete-conversation="removeConversationFromSidebar"
      @logout="logout"
    />

    <section class="chat-workbench__main">
      <header class="chat-workbench__topbar">
        <div v-if="isEditingTitle" class="chat-workbench__title-editor">
          <input
            v-model="titleDraft"
            class="chat-workbench__title-input"
            type="text"
            @keyup.enter="saveConversationTitle"
          />
          <button class="primary-button" type="button" @click="saveConversationTitle">保存</button>
          <button class="secondary-button" type="button" @click="isEditingTitle = false">取消</button>
        </div>

        <div v-else class="chat-workbench__title-shell">
          <div class="chat-workbench__title-copy">
            <span class="chat-workbench__eyebrow">当前会话</span>
            <h1>{{ currentConversationTitle }}</h1>
          </div>
        </div>
      </header>

      <div class="chat-workbench__content-shell">
        <div class="chat-workbench__content">
          <p v-if="feedbackMessage" class="chat-workbench__feedback">
            {{ feedbackMessage }}
          </p>

          <section v-if="chatStore.displayMessages.length" class="chat-workbench__messages-shell">
            <ChatMessageList
              :messages="chatStore.displayMessages"
              :task-polling-state="chatStore.taskPollingState"
              @retry-task="onRetryTask"
              @resume-task="chatStore.resumeTaskPolling"
            />
          </section>

          <section v-else class="chat-workbench__empty">
            <span class="chat-workbench__empty-kicker">MA-ESAS Workspace</span>
            <h2>开始一段新对话</h2>
            <p>直接提问，或者发送受支持的商品链接，让分析任务在聊天流里完成。</p>
          </section>
        </div>
      </div>

      <footer class="chat-workbench__composer">
        <div class="chat-workbench__composer-inner">
          <WorkspaceComposer :loading="chatStore.sendingMessage" @send="onSend" />
        </div>
      </footer>
    </section>
  </main>
</template>

<style scoped>
.chat-workbench {
  height: 100vh;
  display: grid;
  grid-template-columns: auto 1fr;
  background:
    radial-gradient(circle at top center, rgba(59, 130, 246, 0.12), transparent 24%),
    radial-gradient(circle at 88% 18%, rgba(15, 23, 42, 0.06), transparent 18%),
    #f4f7fb;
  overflow: hidden;
}

.chat-workbench__main {
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-rows: auto 1fr auto;
  overflow: hidden;
}

.chat-workbench__topbar {
  padding: 1.1rem 1.5rem 0.7rem;
}

.chat-workbench__title-shell,
.chat-workbench__title-editor {
  width: min(100%, 60rem);
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.95rem 1.15rem;
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 1.2rem;
  background: rgba(255, 255, 255, 0.8);
  box-shadow: 0 12px 40px rgba(15, 23, 42, 0.05);
  backdrop-filter: blur(16px);
}

.chat-workbench__title-copy {
  display: grid;
  gap: 0.15rem;
}

.chat-workbench__eyebrow {
  font-size: 0.78rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #64748b;
}

.chat-workbench__title-shell h1 {
  margin: 0;
  color: #111827;
  font-size: 1.08rem;
  letter-spacing: -0.01em;
}

.chat-workbench__title-editor {
  flex-wrap: wrap;
}

.chat-workbench__title-input {
  flex: 1;
  min-width: 14rem;
  border: 1px solid rgba(203, 213, 225, 0.88);
  border-radius: 0.95rem;
  padding: 0.85rem 1rem;
  background: rgba(255, 255, 255, 0.96);
}

.chat-workbench__content-shell {
  min-height: 0;
  overflow: hidden;
}

.chat-workbench__content {
  width: min(100%, 60rem);
  height: 100%;
  margin: 0 auto;
  padding: 0.15rem 1.5rem 1rem;
  display: grid;
  grid-template-rows: auto 1fr;
  gap: 0.85rem;
  overflow: hidden;
  min-width: 0;
}

.chat-workbench__messages-shell {
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 0.4rem 0 1.4rem;
}

.chat-workbench__feedback {
  margin: 0;
  padding: 0.9rem 1rem;
  border-radius: 1rem;
  border: 1px solid rgba(248, 113, 113, 0.24);
  background: rgba(254, 242, 242, 0.88);
  color: #b91c1c;
}

.chat-workbench__empty {
  min-height: 0;
  display: grid;
  place-content: center;
  gap: 0.8rem;
  padding: 2rem 1rem 3rem;
  text-align: center;
  color: #52627c;
}

.chat-workbench__empty-kicker {
  font-size: 0.82rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: #2563eb;
}

.chat-workbench__empty h2 {
  margin: 0;
  color: #111827;
  font-size: clamp(1.8rem, 2.4vw, 2.8rem);
  letter-spacing: -0.04em;
}

.chat-workbench__empty p {
  max-width: 30rem;
  margin: 0 auto;
  line-height: 1.8;
}

.chat-workbench__composer {
  padding: 0.8rem 1.5rem 1.05rem;
  background: linear-gradient(180deg, rgba(244, 247, 251, 0) 0%, #f4f7fb 18%, #f4f7fb 100%);
}

.chat-workbench__composer-inner {
  width: min(100%, 60rem);
  margin: 0 auto;
}

@media (max-width: 900px) {
  .chat-workbench {
    grid-template-columns: 1fr;
    grid-template-rows: auto 1fr;
  }
}
</style>
