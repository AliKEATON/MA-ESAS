<script setup lang="ts">
import { computed, ref } from 'vue'

import type { ConversationResponse, UserResponse } from '@/types/api'

const props = defineProps<{
  conversations: ConversationResponse[]
  currentConversationId: number | null
  currentUser: UserResponse | null
  loading?: boolean
  collapsed?: boolean
}>()

const emit = defineEmits<{
  toggle: []
  createConversation: []
  refresh: []
  selectConversation: [conversationId: number]
  renameConversation: [conversationId: number]
  deleteConversation: [conversationId: number]
  logout: []
}>()

const profileOpen = ref(false)

/** 生成底部个人信息卡显示名称。 */
const profileLabel = computed(() => props.currentUser?.username || '未登录用户')

/** 切换个人信息弹层。 */
function toggleProfileCard() {
  profileOpen.value = !profileOpen.value
}

/** 退出登录前关闭个人信息弹层。 */
function handleLogout() {
  profileOpen.value = false
  emit('logout')
}
</script>

<template>
  <aside class="workspace-sidebar" :class="{ 'workspace-sidebar--collapsed': collapsed }">
    <div class="workspace-sidebar__top">
      <button class="icon-button workspace-sidebar__toggle" type="button" @click="emit('toggle')">
        {{ collapsed ? '→' : '←' }}
      </button>

      <div v-if="!collapsed" class="workspace-sidebar__brand">
        <span class="workspace-sidebar__brand-mark">MA-ESAS</span>
        <strong>分析工作台</strong>
        <p>统一聊天入口</p>
      </div>
    </div>

    <template v-if="!collapsed">
      <div class="workspace-sidebar__actions">
        <button class="primary-button" type="button" @click="emit('createConversation')">新建会话</button>
        <button class="secondary-button" type="button" @click="emit('refresh')">刷新</button>
      </div>

      <div class="workspace-sidebar__section-head">
        <span>会话列表</span>
        <small v-if="loading">同步中...</small>
      </div>

      <section class="workspace-sidebar__list">
        <article
          v-for="item in conversations"
          :key="item.id"
          class="workspace-sidebar__item"
          :class="{ 'workspace-sidebar__item--active': item.id === currentConversationId }"
        >
          <button class="workspace-sidebar__item-main" type="button" @click="emit('selectConversation', item.id)">
            <div class="workspace-sidebar__item-title" :title="item.title || `会话 ${item.id}`">
              {{ item.title || `会话 ${item.id}` }}
            </div>
            <div class="workspace-sidebar__item-preview" :title="item.last_message_preview || '暂无消息'">
              {{ item.last_message_preview || '暂无消息' }}
            </div>
            <div v-if="item.latest_task" class="workspace-sidebar__item-task">
              {{ item.latest_task.status }}
            </div>
          </button>

          <div class="workspace-sidebar__item-tools">
            <button
              class="workspace-sidebar__tool-button"
              type="button"
              title="重命名"
              @click.stop="emit('renameConversation', item.id)"
            >
              ✎
            </button>
            <button
              class="workspace-sidebar__tool-button workspace-sidebar__tool-button--danger"
              type="button"
              title="删除"
              @click.stop="emit('deleteConversation', item.id)"
            >
              ⌫
            </button>
          </div>
        </article>
      </section>

      <footer class="workspace-sidebar__footer">
        <button class="workspace-sidebar__profile" type="button" @click="toggleProfileCard">
          <span class="workspace-sidebar__avatar">{{ profileLabel.slice(0, 1).toUpperCase() }}</span>
          <span class="workspace-sidebar__profile-copy">
            <strong>{{ profileLabel }}</strong>
            <small>{{ props.currentUser?.email || '未获取邮箱' }}</small>
          </span>
        </button>

        <div v-if="profileOpen" class="workspace-sidebar__popover">
          <div class="workspace-sidebar__popover-card">
            <span class="workspace-sidebar__popover-kicker">当前账号</span>
            <strong>{{ props.currentUser?.username || '未登录用户' }}</strong>
            <small>{{ props.currentUser?.email || '未获取邮箱' }}</small>
            <button class="secondary-button" type="button" @click="handleLogout">退出登录</button>
          </div>
        </div>
      </footer>
    </template>

    <div v-else class="workspace-sidebar__collapsed">
      <button class="icon-button" type="button" title="新建会话" @click="emit('createConversation')">+</button>
      <button class="icon-button" type="button" title="刷新" @click="emit('refresh')">↻</button>
      <button class="icon-button workspace-sidebar__collapsed-profile" type="button" @click="toggleProfileCard">
        {{ profileLabel.slice(0, 1).toUpperCase() }}
      </button>

      <div v-if="profileOpen" class="workspace-sidebar__popover workspace-sidebar__popover--collapsed">
        <div class="workspace-sidebar__popover-card">
          <span class="workspace-sidebar__popover-kicker">当前账号</span>
          <strong>{{ props.currentUser?.username || '未登录用户' }}</strong>
          <small>{{ props.currentUser?.email || '未获取邮箱' }}</small>
          <button class="secondary-button" type="button" @click="handleLogout">退出登录</button>
        </div>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.workspace-sidebar {
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

.workspace-sidebar--collapsed {
  width: 5rem;
  padding-inline: 0.75rem;
}

.workspace-sidebar__top,
.workspace-sidebar__collapsed {
  display: flex;
  gap: 0.65rem;
}

.workspace-sidebar__brand {
  display: grid;
  gap: 0.12rem;
  align-content: center;
}

.workspace-sidebar__brand-mark {
  font-size: 0.74rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: #2563eb;
}

.workspace-sidebar__brand strong {
  font-size: 1.05rem;
  color: #0f172a;
}

.workspace-sidebar__brand p {
  margin: 0;
  color: #64748b;
  font-size: 0.82rem;
}

.workspace-sidebar__actions {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 0.55rem;
}

.workspace-sidebar__section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: #64748b;
  font-size: 0.82rem;
  padding-inline: 0.15rem;
}

.workspace-sidebar__section-head span {
  color: #334155;
  font-weight: 600;
}

.workspace-sidebar__list {
  min-height: 0;
  flex: 1;
  display: grid;
  align-content: start;
  gap: 0.45rem;
  overflow-y: auto;
  padding-right: 0.15rem;
}

.workspace-sidebar__item {
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

.workspace-sidebar__item::before {
  content: '';
  position: absolute;
  inset: 0 auto 0 0;
  width: 3px;
  border-radius: 999px;
  background: transparent;
  transition: background-color 0.18s ease;
}

.workspace-sidebar__item:hover,
.workspace-sidebar__item--active {
  transform: translateY(-1px);
  border-color: rgba(59, 130, 246, 0.26);
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 16px 36px rgba(15, 23, 42, 0.06);
}

.workspace-sidebar__item--active::before {
  background: linear-gradient(180deg, #2563eb 0%, #38bdf8 100%);
}

.workspace-sidebar__item-main {
  min-width: 0;
  display: grid;
  align-content: start;
  gap: 0.18rem;
  border: none;
  background: transparent;
  padding: 0;
  text-align: left;
}

.workspace-sidebar__item-title,
.workspace-sidebar__item-preview,
.workspace-sidebar__item-task,
.workspace-sidebar__profile-copy strong,
.workspace-sidebar__profile-copy small {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.workspace-sidebar__item-title {
  color: #111827;
  font-size: 0.92rem;
  font-weight: 600;
}

.workspace-sidebar__item-preview,
.workspace-sidebar__item-task {
  color: #64748b;
  font-size: 0.78rem;
}

.workspace-sidebar__item-tools {
  display: grid;
  align-content: start;
  gap: 0.32rem;
}

.workspace-sidebar__tool-button {
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

.workspace-sidebar__tool-button:hover {
  transform: translateY(-1px);
  border-color: rgba(37, 99, 235, 0.28);
  background: rgba(239, 246, 255, 0.92);
  color: #1d4ed8;
}

.workspace-sidebar__tool-button--danger:hover {
  border-color: rgba(248, 113, 113, 0.36);
  background: rgba(254, 242, 242, 0.96);
  color: #dc2626;
}

.workspace-sidebar__footer {
  position: relative;
  flex-shrink: 0;
}

.workspace-sidebar__profile {
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

.workspace-sidebar__avatar {
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

.workspace-sidebar__profile-copy {
  min-width: 0;
  display: grid;
}

.workspace-sidebar__profile-copy strong {
  color: #111827;
}

.workspace-sidebar__profile-copy small {
  color: #64748b;
  font-size: 0.78rem;
}

.workspace-sidebar__popover {
  position: absolute;
  left: 0;
  right: 0;
  bottom: calc(100% + 0.6rem);
  z-index: 5;
}

.workspace-sidebar__popover--collapsed {
  left: calc(100% + 0.5rem);
  right: auto;
  bottom: 0;
}

.workspace-sidebar__popover-card {
  min-width: 13.5rem;
  display: grid;
  gap: 0.5rem;
  padding: 0.95rem;
  border: 1px solid rgba(226, 232, 240, 0.95);
  border-radius: 1.1rem;
  background: rgba(255, 255, 255, 0.98);
  box-shadow: 0 22px 48px rgba(15, 23, 42, 0.12);
}

.workspace-sidebar__popover-kicker {
  font-size: 0.74rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #64748b;
}

.workspace-sidebar__collapsed {
  height: 100%;
  flex-direction: column;
  align-items: center;
}

.workspace-sidebar__collapsed-profile {
  margin-top: auto;
}

@media (max-width: 900px) {
  .workspace-sidebar {
    width: 100%;
    height: auto;
    max-height: 16.5rem;
    border-right: none;
    border-bottom: 1px solid rgba(226, 232, 240, 0.9);
  }

  .workspace-sidebar__list {
    max-height: 8rem;
  }
}
</style>
