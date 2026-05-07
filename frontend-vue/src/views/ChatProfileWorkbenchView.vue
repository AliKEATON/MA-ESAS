<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { ApiClientError } from '@/api/client'
import ChatMessageList from '@/components/chat/ChatMessageList.vue'
import WorkspaceComposerPanel from '@/components/chat/WorkspaceComposerPanel.vue'
import ProfileWorkspacePanel from '@/components/profile/ProfileWorkspacePanel.vue'
import WorkspaceSidebarShell from '@/components/sidebar/WorkspaceSidebarShell.vue'
import ProductVisualAnalysisPanel from '@/components/visual-analysis/ProductVisualAnalysisPanel.vue'
import { useAuthStore } from '@/stores/auth'
import { useChatStore } from '@/stores/chat'

type WorkbenchView = 'chat' | 'profile' | 'visual-analysis'

const router = useRouter()
const authStore = useAuthStore()
const chatStore = useChatStore()

const activeView = ref<WorkbenchView>('chat')
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
const topbarEyebrow = computed(() => {
  if (activeView.value === 'profile') {
    return '账户设置'
  }
  if (activeView.value === 'visual-analysis') {
    return '商品分析'
  }
  return '当前会话'
})
const topbarTitle = computed(() => {
  if (activeView.value === 'profile') {
    return '个人信息'
  }
  if (activeView.value === 'visual-analysis') {
    return '商品可视化分析'
  }
  return currentConversationTitle.value
})
const topbarDisclaimer = computed(() => (
  activeView.value === 'visual-analysis'
    ? '分析结果基于商品评论统计生成，请结合实际甄别'
    : '内容由 AI 生成，请仔细甄别'
))

/** 初始化工作台，优先恢复会话列表和当前会话详情。 */
async function initializeWorkbench() {
  try {
    await chatStore.fetchConversations()
    if (chatStore.currentConversationId) {
      await chatStore.fetchConversationDetail(chatStore.currentConversationId)
    }
  } catch (error) {
    handleError(error, '加载工作台数据失败')
  }
}

/** 统一处理页面错误提示。 */
function handleError(error: unknown, fallbackMessage: string) {
  feedbackMessage.value = error instanceof ApiClientError ? error.message : fallbackMessage
}

/** 切换到聊天视图。 */
function openChatView() {
  activeView.value = 'chat'
}

/** 切换到个人信息视图。 */
function openProfileView() {
  activeView.value = 'profile'
  isEditingTitle.value = false
  feedbackMessage.value = ''
}

/** 切换到商品可视化分析视图。 */
function openVisualAnalysisView() {
  activeView.value = 'visual-analysis'
  isEditingTitle.value = false
  feedbackMessage.value = ''
}

/** 创建会话并切换到新会话。 */
async function createConversation() {
  feedbackMessage.value = ''
  openChatView()
  try {
    await chatStore.createConversation()
  } catch (error) {
    handleError(error, '创建会话失败')
  }
}

/** 刷新侧边栏与当前区域的数据。 */
async function refreshData() {
  feedbackMessage.value = ''
  try {
    await chatStore.fetchConversations()
    if (activeView.value === 'chat' && chatStore.currentConversationId) {
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

/** 切换当前会话。 */
async function selectConversation(conversationId: number) {
  feedbackMessage.value = ''
  openChatView()
  try {
    await chatStore.selectConversation(conversationId)
  } catch (error) {
    handleError(error, '加载会话失败')
  }
}

/** 发送聊天消息。 */
async function onSend(content: string) {
  feedbackMessage.value = ''
  openChatView()
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

/** 从侧边栏进入会话重命名。 */
async function openRenameConversation(conversationId: number) {
  feedbackMessage.value = ''
  openChatView()
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

/** 从侧边栏删除会话。 */
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
  void initializeWorkbench()
})

onBeforeUnmount(() => {
  chatStore.stopAllPolling()
})
</script>

<template>
  <main class="chat-profile-workbench">
    <WorkspaceSidebarShell
      :collapsed="chatStore.sidebarCollapsed"
      :conversations="chatStore.conversations"
      :current-conversation-id="chatStore.currentConversationId"
      :current-user="authStore.currentUser"
      :loading="chatStore.loadingConversations"
      :active-view="activeView"
      @toggle="chatStore.toggleSidebar"
      @create-conversation="createConversation"
      @refresh="refreshData"
      @select-conversation="selectConversation"
      @rename-conversation="openRenameConversation"
      @delete-conversation="removeConversationFromSidebar"
      @open-profile="openProfileView"
      @open-visual-analysis="openVisualAnalysisView"
      @logout="logout"
    />

    <section class="chat-profile-workbench__main">
      <header class="chat-profile-workbench__topbar">
        <div v-if="activeView === 'chat' && isEditingTitle" class="chat-profile-workbench__title-editor">
          <input
            v-model="titleDraft"
            class="chat-profile-workbench__title-input"
            type="text"
            @keyup.enter="saveConversationTitle"
          />
          <button class="primary-button" type="button" @click="saveConversationTitle">保存</button>
          <button class="secondary-button" type="button" @click="isEditingTitle = false">取消</button>
        </div>

        <div v-else class="chat-profile-workbench__title-shell">
          <div class="chat-profile-workbench__title-copy">
            <div class="chat-profile-workbench__title-row">
              <span class="chat-profile-workbench__eyebrow">{{ topbarEyebrow }}</span>
              <h1>{{ topbarTitle }}</h1>
            </div>
            <p class="chat-profile-workbench__title-disclaimer">{{ topbarDisclaimer }}</p>
          </div>

          <button
            v-if="activeView !== 'chat'"
            class="secondary-button"
            type="button"
            @click="openChatView"
          >
            返回聊天
          </button>
        </div>
      </header>

      <div class="chat-profile-workbench__content-shell">
        <div class="chat-profile-workbench__content">
          <p v-if="feedbackMessage" class="chat-profile-workbench__feedback">
            {{ feedbackMessage }}
          </p>

          <template v-if="activeView === 'profile'">
            <section class="chat-profile-workbench__profile-shell">
              <ProfileWorkspacePanel :user="authStore.currentUser" />
            </section>
          </template>

          <template v-else-if="activeView === 'visual-analysis'">
            <section class="chat-profile-workbench__profile-shell">
              <ProductVisualAnalysisPanel />
            </section>
          </template>

          <template v-else>
            <section v-if="chatStore.displayMessages.length" class="chat-profile-workbench__messages-shell">
              <ChatMessageList
                :messages="chatStore.displayMessages"
                :task-polling-state="chatStore.taskPollingState"
                @retry-task="onRetryTask"
                @resume-task="chatStore.resumeTaskPolling"
              />
            </section>

            <section v-else class="chat-profile-workbench__empty">
              <span class="chat-profile-workbench__empty-kicker">MA-ESAS Workspace</span>
              <h2>开始一段新对话</h2>
              <p>直接提问，或发送受支持的商品链接，让分析任务在聊天流里完成。</p>
            </section>
          </template>
        </div>
      </div>

      <footer v-if="activeView === 'chat'" class="chat-profile-workbench__composer">
        <div class="chat-profile-workbench__composer-inner">
          <WorkspaceComposerPanel :loading="chatStore.sendingMessage" @send="onSend" />
        </div>
      </footer>
    </section>
  </main>
</template>

<style scoped>
.chat-profile-workbench {
  height: 100vh;
  display: grid;
  grid-template-columns: auto 1fr;
  background:
    radial-gradient(circle at top center, rgba(59, 130, 246, 0.12), transparent 24%),
    radial-gradient(circle at 88% 18%, rgba(15, 23, 42, 0.06), transparent 18%),
    #f4f7fb;
  overflow: hidden;
}

.chat-profile-workbench__main {
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-rows: auto 1fr auto;
  overflow: hidden;
}

.chat-profile-workbench__topbar {
  padding: 0 0 0.45rem;
}

.chat-profile-workbench__title-shell,
.chat-profile-workbench__title-editor {
  width: 100%;
  margin: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  min-height: 4.2rem;
  padding: 0.6rem 0.95rem;
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 0;
  background: rgba(255, 255, 255, 0.8);
  box-shadow: 0 12px 40px rgba(15, 23, 42, 0.05);
  backdrop-filter: blur(16px);
}

.chat-profile-workbench__title-copy {
  position: relative;
  display: grid;
  flex: 1;
  min-width: 0;
  gap: 0.08rem;
}

.chat-profile-workbench__title-row {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 0;
  min-height: 1.4rem;
}

.chat-profile-workbench__eyebrow {
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  font-size: 0.78rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #64748b;
  max-width: 8rem;
  text-align: left;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.chat-profile-workbench__title-shell h1 {
  margin: 0;
  color: #111827;
  font-size: 0.94rem;
  font-weight: 500;
  letter-spacing: -0.01em;
  text-align: center;
  line-height: 1.25;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.chat-profile-workbench__title-disclaimer {
  margin: 0;
  width: 100%;
  font-size: 0.68rem;
  line-height: 1.2;
  color: rgba(100, 116, 139, 0.5);
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.chat-profile-workbench__title-editor {
  flex-wrap: nowrap;
}

.chat-profile-workbench__title-input {
  flex: 1;
  min-width: 14rem;
  border: 1px solid rgba(203, 213, 225, 0.88);
  border-radius: 0.95rem;
  padding: 0.85rem 1rem;
  background: rgba(255, 255, 255, 0.96);
}

.chat-profile-workbench__content-shell {
  min-height: 0;
  overflow: hidden;
}

.chat-profile-workbench__content {
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

.chat-profile-workbench__messages-shell,
.chat-profile-workbench__profile-shell {
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 0.4rem 0 1.4rem;
  scrollbar-width: thin;
  scrollbar-color: rgba(148, 163, 184, 0.22) transparent;
}

.chat-profile-workbench__messages-shell::-webkit-scrollbar,
.chat-profile-workbench__profile-shell::-webkit-scrollbar {
  width: 8px;
}

.chat-profile-workbench__messages-shell::-webkit-scrollbar-track,
.chat-profile-workbench__profile-shell::-webkit-scrollbar-track {
  background: transparent;
}

.chat-profile-workbench__messages-shell::-webkit-scrollbar-thumb,
.chat-profile-workbench__profile-shell::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, 0.18);
  border-radius: 999px;
  border: 2px solid transparent;
  background-clip: padding-box;
}

.chat-profile-workbench__messages-shell::-webkit-scrollbar-thumb:hover,
.chat-profile-workbench__profile-shell::-webkit-scrollbar-thumb:hover {
  background: rgba(148, 163, 184, 0.28);
  background-clip: padding-box;
}

.chat-profile-workbench__feedback {
  margin: 0;
  padding: 0.9rem 1rem;
  border-radius: 1rem;
  border: 1px solid rgba(248, 113, 113, 0.24);
  background: rgba(254, 242, 242, 0.88);
  color: #b91c1c;
}

.chat-profile-workbench__empty {
  min-height: 0;
  display: grid;
  place-content: center;
  gap: 0.8rem;
  padding: 2rem 1rem 3rem;
  text-align: center;
  color: #52627c;
}

.chat-profile-workbench__empty-kicker {
  font-size: 0.82rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: #2563eb;
}

.chat-profile-workbench__empty h2 {
  margin: 0;
  color: #111827;
  font-size: clamp(1.8rem, 2.4vw, 2.8rem);
  letter-spacing: -0.04em;
}

.chat-profile-workbench__empty p {
  max-width: 30rem;
  margin: 0 auto;
  line-height: 1.8;
}

.chat-profile-workbench__composer {
  padding: 0.8rem 1.5rem 1.05rem;
  background: linear-gradient(180deg, rgba(244, 247, 251, 0) 0%, #f4f7fb 18%, #f4f7fb 100%);
}

.chat-profile-workbench__composer-inner {
  width: min(100%, 60rem);
  margin: 0 auto;
}

@media (max-width: 900px) {
  .chat-profile-workbench {
    grid-template-columns: 1fr;
    grid-template-rows: auto 1fr;
  }
}
</style>
