<script setup lang="ts">
import { computed, ref } from 'vue'

import type { ConversationResponse, UserResponse } from '@/types/api'

const props = defineProps<{
  conversations: ConversationResponse[]
  currentConversationId: number | null
  currentUser: UserResponse | null
  loading?: boolean
  collapsed?: boolean
  activeView: 'chat' | 'profile' | 'visual-analysis'
}>()

const emit = defineEmits<{
  toggle: []
  createConversation: []
  refresh: []
  selectConversation: [conversationId: number]
  renameConversation: [conversationId: number]
  deleteConversation: [conversationId: number]
  openProfile: []
  openVisualAnalysis: []
  logout: []
}>()

const profileOpen = ref(false)

/** 生成底部个人信息展示名称。 */
const profileLabel = computed(() => props.currentUser?.username || '未登录用户')

/** 切换个人信息弹层显示状态。 */
function toggleProfileCard() {
  profileOpen.value = !profileOpen.value
}

/** 打开右侧个人信息页并关闭弹层。 */
function openProfilePanel() {
  profileOpen.value = false
  emit('openProfile')
}

/** 触发退出登录并关闭弹层。 */
function handleLogout() {
  profileOpen.value = false
  emit('logout')
}

/** 触发切换会话并关闭弹层。 */
function handleSelectConversation(conversationId: number) {
  profileOpen.value = false
  emit('selectConversation', conversationId)
}
</script>

<template>
  <aside class="workspace-sidebar-shell" :class="{ 'workspace-sidebar-shell--collapsed': collapsed }">
    <div class="workspace-sidebar-shell__top">
      <button class="icon-button workspace-sidebar-shell__toggle" type="button" @click="emit('toggle')">
        {{ collapsed ? '→' : '←' }}
      </button>

      <div v-if="!collapsed" class="workspace-sidebar-shell__brand">
        <strong>分析工作台</strong>
      </div>
    </div>

    <template v-if="!collapsed">
      <div class="workspace-sidebar-shell__actions">
        <button class="secondary-button workspace-sidebar-shell__action-button" type="button" @click="emit('createConversation')">
          新建会话
        </button>
        <button class="secondary-button workspace-sidebar-shell__action-button" type="button" @click="emit('refresh')">刷新</button>
        <button
          class="primary-button workspace-sidebar-shell__action-button"
          :class="{ 'workspace-sidebar-shell__action-button--active': activeView === 'visual-analysis' }"
          type="button"
          @click="emit('openVisualAnalysis')"
        >
          商品分析
        </button>
      </div>

      <div class="workspace-sidebar-shell__section-head">
        <span>会话列表</span>
        <small v-if="loading">同步中...</small>
      </div>

      <section class="workspace-sidebar-shell__list">
        <article
          v-for="item in conversations"
          :key="item.id"
          class="workspace-sidebar-shell__item"
          :class="{ 'workspace-sidebar-shell__item--active': item.id === currentConversationId && activeView === 'chat' }"
        >
          <button class="workspace-sidebar-shell__item-main" type="button" @click="handleSelectConversation(item.id)">
            <div class="workspace-sidebar-shell__item-title" :title="item.title || `会话 ${item.id}`">
              {{ item.title || `会话 ${item.id}` }}
            </div>
            <div class="workspace-sidebar-shell__item-preview" :title="item.last_message_preview || '暂无消息'">
              {{ item.last_message_preview || '暂无消息' }}
            </div>
            <div v-if="item.latest_task" class="workspace-sidebar-shell__item-task">
              {{ item.latest_task.status }}
            </div>
          </button>

          <div class="workspace-sidebar-shell__item-tools">
            <button
              class="workspace-sidebar-shell__tool-button"
              type="button"
              title="重命名"
              @click.stop="emit('renameConversation', item.id)"
            >
              ✎
            </button>
            <button
              class="workspace-sidebar-shell__tool-button workspace-sidebar-shell__tool-button--danger"
              type="button"
              title="删除"
              @click.stop="emit('deleteConversation', item.id)"
            >
              🗑
            </button>
          </div>
        </article>
      </section>

      <footer class="workspace-sidebar-shell__footer">
        <div class="workspace-sidebar-shell__profile-row">
          <button
            class="workspace-sidebar-shell__profile"
            :class="{ 'workspace-sidebar-shell__profile--active': activeView === 'profile' }"
            type="button"
            @click="openProfilePanel"
          >
            <span class="workspace-sidebar-shell__avatar">{{ profileLabel.slice(0, 1).toUpperCase() }}</span>
            <span class="workspace-sidebar-shell__profile-copy">
              <strong>{{ profileLabel }}</strong>
              <small>{{ props.currentUser?.email || '暂无邮箱信息' }}</small>
            </span>
          </button>

          <button class="icon-button workspace-sidebar-shell__profile-menu" type="button" @click="toggleProfileCard">
            ⋯
          </button>
        </div>

        <div v-if="profileOpen" class="workspace-sidebar-shell__popover">
          <div class="workspace-sidebar-shell__popover-card">
            <span class="workspace-sidebar-shell__popover-kicker">当前账号</span>
            <strong>{{ props.currentUser?.username || '未登录用户' }}</strong>
            <small>{{ props.currentUser?.email || '暂无邮箱信息' }}</small>
            <div class="workspace-sidebar-shell__popover-actions">
              <button class="secondary-button" type="button" @click="openProfilePanel">个人信息</button>
              <button class="secondary-button" type="button" @click="handleLogout">退出登录</button>
            </div>
          </div>
        </div>
      </footer>
    </template>

    <div v-else class="workspace-sidebar-shell__collapsed">
      <button class="icon-button" type="button" title="新建会话" @click="emit('createConversation')">+</button>
      <button class="icon-button" type="button" title="刷新" @click="emit('refresh')">↻</button>
      <button class="icon-button" type="button" title="商品分析" @click="emit('openVisualAnalysis')">◫</button>
      <button class="icon-button" type="button" title="个人信息" @click="openProfilePanel">
        {{ profileLabel.slice(0, 1).toUpperCase() }}
      </button>
      <button class="icon-button workspace-sidebar-shell__collapsed-menu" type="button" title="账户菜单" @click="toggleProfileCard">
        ⋯
      </button>

      <div v-if="profileOpen" class="workspace-sidebar-shell__popover workspace-sidebar-shell__popover--collapsed">
        <div class="workspace-sidebar-shell__popover-card">
          <span class="workspace-sidebar-shell__popover-kicker">当前账号</span>
          <strong>{{ props.currentUser?.username || '未登录用户' }}</strong>
          <small>{{ props.currentUser?.email || '暂无邮箱信息' }}</small>
          <div class="workspace-sidebar-shell__popover-actions">
            <button class="secondary-button" type="button" @click="openProfilePanel">个人信息</button>
            <button class="secondary-button" type="button" @click="handleLogout">退出登录</button>
          </div>
        </div>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.workspace-sidebar-shell {
  width: 19.5rem;
  height: 100vh;
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
  padding: 1rem 0.9rem 0.9rem;
  border-right: 1px solid rgba(226, 232, 240, 0.9);
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.96) 0%, rgba(240, 244, 248, 0.98) 100%);
  overflow: hidden;
}

.workspace-sidebar-shell--collapsed {
  width: 5rem;
  padding-inline: 0.75rem;
}

.workspace-sidebar-shell__top,
.workspace-sidebar-shell__collapsed {
  display: flex;
  gap: 0.65rem;
}

.workspace-sidebar-shell__brand {
  display: grid;
  gap: 0.12rem;
  align-content: center;
}

.workspace-sidebar-shell__brand strong {
  font-size: 1.05rem;
  color: #0f172a;
}

.workspace-sidebar-shell__actions {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.55rem;
}

.workspace-sidebar-shell__action-button {
  min-height: 2.2rem;
  padding: 0.45rem 0.65rem;
  font-size: 0.8rem;
}

.workspace-sidebar-shell__action-button--active {
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.16);
}

.workspace-sidebar-shell__section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: #64748b;
  font-size: 0.82rem;
  padding-inline: 0.15rem;
}

.workspace-sidebar-shell__section-head span {
  color: #334155;
  font-weight: 600;
}

.workspace-sidebar-shell__list {
  min-height: 0;
  flex: 1;
  display: grid;
  align-content: start;
  gap: 0.45rem;
  overflow-y: auto;
  padding-right: 0.15rem;
}

.workspace-sidebar-shell__item {
  position: relative;
  height: 5.35rem;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 0.5rem;
  padding: 0.62rem 0.62rem 0.62rem 0.82rem;
  border: 1px solid rgba(226, 232, 240, 0.82);
  border-radius: 1rem;
  background: rgba(255, 255, 255, 0.84);
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.03);
  transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease, background-color 0.18s ease;
}

.workspace-sidebar-shell__item::before {
  content: '';
  position: absolute;
  inset: 0 auto 0 0;
  width: 3px;
  border-radius: 999px;
  background: transparent;
  transition: background-color 0.18s ease;
}

.workspace-sidebar-shell__item:hover,
.workspace-sidebar-shell__item--active {
  transform: translateY(-1px);
  border-color: rgba(59, 130, 246, 0.26);
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 16px 36px rgba(15, 23, 42, 0.06);
}

.workspace-sidebar-shell__item--active::before {
  background: linear-gradient(180deg, #2563eb 0%, #38bdf8 100%);
}

.workspace-sidebar-shell__item-main {
  min-width: 0;
  display: grid;
  align-content: start;
  gap: 0.18rem;
  border: none;
  background: transparent;
  padding: 0;
  text-align: left;
}

.workspace-sidebar-shell__item-title,
.workspace-sidebar-shell__item-preview,
.workspace-sidebar-shell__item-task,
.workspace-sidebar-shell__profile-copy strong,
.workspace-sidebar-shell__profile-copy small {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.workspace-sidebar-shell__item-title {
  color: #111827;
  font-size: 0.92rem;
  font-weight: 600;
}

.workspace-sidebar-shell__item-preview,
.workspace-sidebar-shell__item-task {
  color: #64748b;
  font-size: 0.78rem;
}

.workspace-sidebar-shell__item-tools {
  display: grid;
  align-content: start;
  gap: 0.32rem;
}

.workspace-sidebar-shell__tool-button {
  width: 1.95rem;
  height: 1.95rem;
  display: grid;
  place-items: center;
  border: 1px solid rgba(203, 213, 225, 0.86);
  border-radius: 0.72rem;
  background: rgba(248, 250, 252, 0.92);
  color: #475569;
  transition: border-color 0.18s ease, background-color 0.18s ease, color 0.18s ease, transform 0.18s ease;
}

.workspace-sidebar-shell__tool-button:hover {
  transform: translateY(-1px);
  border-color: rgba(37, 99, 235, 0.28);
  background: rgba(239, 246, 255, 0.92);
  color: #1d4ed8;
}

.workspace-sidebar-shell__tool-button--danger:hover {
  border-color: rgba(248, 113, 113, 0.36);
  background: rgba(254, 242, 242, 0.96);
  color: #dc2626;
}

.workspace-sidebar-shell__footer {
  position: relative;
  flex-shrink: 0;
}

.workspace-sidebar-shell__profile-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 0.55rem;
}

.workspace-sidebar-shell__profile {
  width: 100%;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 0.7rem;
  align-items: center;
  border: 1px solid rgba(226, 232, 240, 0.88);
  border-radius: 1rem;
  background: rgba(255, 255, 255, 0.9);
  padding: 0.75rem 0.82rem;
  text-align: left;
}

.workspace-sidebar-shell__profile--active {
  border-color: rgba(59, 130, 246, 0.3);
  background: rgba(239, 246, 255, 0.82);
}

.workspace-sidebar-shell__profile-menu {
  align-self: stretch;
  width: 2.8rem;
  height: auto;
  border-radius: 1rem;
}

.workspace-sidebar-shell__avatar {
  width: 2.25rem;
  height: 2.25rem;
  display: grid;
  place-items: center;
  border-radius: 999px;
  background: linear-gradient(135deg, #0f172a 0%, #334155 100%);
  color: #ffffff;
  font-size: 0.85rem;
  font-weight: 700;
}

.workspace-sidebar-shell__profile-copy {
  min-width: 0;
  display: grid;
}

.workspace-sidebar-shell__profile-copy strong {
  color: #111827;
}

.workspace-sidebar-shell__profile-copy small {
  color: #64748b;
  font-size: 0.78rem;
}

.workspace-sidebar-shell__popover {
  position: absolute;
  left: 0;
  right: 0;
  bottom: calc(100% + 0.6rem);
  z-index: 5;
}

.workspace-sidebar-shell__popover--collapsed {
  left: calc(100% + 0.5rem);
  right: auto;
  bottom: 0;
}

.workspace-sidebar-shell__popover-card {
  min-width: 13.5rem;
  display: grid;
  gap: 0.5rem;
  padding: 0.95rem;
  border: 1px solid rgba(226, 232, 240, 0.95);
  border-radius: 1.1rem;
  background: rgba(255, 255, 255, 0.98);
  box-shadow: 0 22px 48px rgba(15, 23, 42, 0.12);
}

.workspace-sidebar-shell__popover-kicker {
  font-size: 0.74rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #64748b;
}

.workspace-sidebar-shell__popover-actions {
  display: grid;
  gap: 0.55rem;
  margin-top: 0.35rem;
}

.workspace-sidebar-shell__collapsed {
  height: 100%;
  flex-direction: column;
  align-items: center;
}

.workspace-sidebar-shell__collapsed-menu {
  margin-top: auto;
}

@media (max-width: 900px) {
  .workspace-sidebar-shell {
    width: 100%;
    height: auto;
    max-height: 16.5rem;
    border-right: none;
    border-bottom: 1px solid rgba(226, 232, 240, 0.9);
  }

  .workspace-sidebar-shell__list {
    max-height: 8rem;
  }
}
</style>
