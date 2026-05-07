<script setup lang="ts">
import { computed, ref } from 'vue'

import { ApiClientError } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import type { UserResponse } from '@/types/api'

const props = defineProps<{
  user: UserResponse | null
}>()

const authStore = useAuthStore()

const currentPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const errorMessage = ref('')
const successMessage = ref('')

const statusLabel = computed(() => (props.user?.is_active ? '正常' : '已停用'))
const createdAtLabel = computed(() => {
  if (!props.user?.created_at) {
    return '暂无记录'
  }

  return new Intl.DateTimeFormat('zh-CN', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(props.user.created_at))
})

/** 清空密码表单和提示信息。 */
function resetForm() {
  currentPassword.value = ''
  newPassword.value = ''
  confirmPassword.value = ''
}

/** 提交修改密码表单。 */
async function submitChangePassword() {
  errorMessage.value = ''
  successMessage.value = ''

  if (!currentPassword.value || !newPassword.value || !confirmPassword.value) {
    errorMessage.value = '请完整填写当前密码、新密码和确认密码。'
    return
  }

  if (currentPassword.value.length < 6 || newPassword.value.length < 6) {
    errorMessage.value = '密码长度不能少于 6 位。'
    return
  }

  if (newPassword.value !== confirmPassword.value) {
    errorMessage.value = '两次输入的新密码不一致。'
    return
  }

  try {
    const response = await authStore.changePassword(currentPassword.value, newPassword.value)
    if (response.data.success) {
      successMessage.value = '密码已更新，下次登录请使用新密码。'
      resetForm()
    }
  } catch (error) {
    errorMessage.value =
      error instanceof ApiClientError ? error.message : '修改密码失败，请稍后重试。'
  }
}
</script>

<template>
  <section class="profile-workspace-panel">
    <header class="profile-workspace-panel__hero">
      <div class="profile-workspace-panel__hero-copy">
        <span class="profile-workspace-panel__eyebrow">Account Center</span>
        <h2>个人信息与账户安全</h2>
        <p>在同一工作区内查看账户资料，并完成密码更新，避免打断当前分析流程。</p>
      </div>
    </header>

    <section class="profile-workspace-panel__grid">
      <article class="profile-workspace-panel__panel">
        <div class="profile-workspace-panel__panel-head">
          <span class="profile-workspace-panel__kicker">Profile</span>
          <h3>基础信息</h3>
        </div>

        <dl class="profile-workspace-panel__info-list">
          <div class="profile-workspace-panel__info-item">
            <dt>用户名</dt>
            <dd>{{ user?.username || '未获取' }}</dd>
          </div>
          <div class="profile-workspace-panel__info-item">
            <dt>邮箱</dt>
            <dd>{{ user?.email || '未获取' }}</dd>
          </div>
          <div class="profile-workspace-panel__info-item">
            <dt>账户状态</dt>
            <dd>{{ statusLabel }}</dd>
          </div>
          <div class="profile-workspace-panel__info-item">
            <dt>注册时间</dt>
            <dd>{{ createdAtLabel }}</dd>
          </div>
        </dl>
      </article>

      <article class="profile-workspace-panel__panel">
        <div class="profile-workspace-panel__panel-head">
          <span class="profile-workspace-panel__kicker">Security</span>
          <h3>修改密码</h3>
        </div>

        <p class="profile-workspace-panel__panel-intro">
          为了保证账户安全，请先输入当前密码，再设置一个新的登录密码。
        </p>

        <form class="profile-workspace-panel__form" @submit.prevent="submitChangePassword">
          <label class="profile-workspace-panel__field">
            <span>当前密码</span>
            <input v-model="currentPassword" type="password" autocomplete="current-password" />
          </label>

          <label class="profile-workspace-panel__field">
            <span>新密码</span>
            <input v-model="newPassword" type="password" autocomplete="new-password" />
          </label>

          <label class="profile-workspace-panel__field">
            <span>确认新密码</span>
            <input v-model="confirmPassword" type="password" autocomplete="new-password" />
          </label>

          <p v-if="errorMessage" class="profile-workspace-panel__message profile-workspace-panel__message--error">
            {{ errorMessage }}
          </p>
          <p
            v-else-if="successMessage"
            class="profile-workspace-panel__message profile-workspace-panel__message--success"
          >
            {{ successMessage }}
          </p>

          <div class="profile-workspace-panel__actions">
            <button class="primary-button" type="submit" :disabled="authStore.changingPassword">
              {{ authStore.changingPassword ? '保存中...' : '更新密码' }}
            </button>
          </div>
        </form>
      </article>
    </section>
  </section>
</template>

<style scoped>
.profile-workspace-panel {
  display: grid;
  gap: 1.25rem;
  padding: 0.5rem 0 1.5rem;
}

.profile-workspace-panel__hero {
  display: block;
}

.profile-workspace-panel__hero-copy,
.profile-workspace-panel__panel {
  border: 1px solid rgba(226, 232, 240, 0.92);
  border-radius: 1.35rem;
  background: rgba(255, 255, 255, 0.82);
  box-shadow: 0 18px 42px rgba(15, 23, 42, 0.05);
  backdrop-filter: blur(16px);
}

.profile-workspace-panel__hero-copy {
  padding: 1.4rem 1.5rem;
}

.profile-workspace-panel__eyebrow,
.profile-workspace-panel__kicker {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.76rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #64748b;
}

.profile-workspace-panel__hero-copy h2,
.profile-workspace-panel__panel-head h3 {
  margin: 0.45rem 0 0;
  color: #111827;
}

.profile-workspace-panel__hero-copy h2 {
  font-size: clamp(1.6rem, 2.2vw, 2.35rem);
  letter-spacing: -0.04em;
}

.profile-workspace-panel__hero-copy p {
  max-width: 34rem;
  margin: 0.9rem 0 0;
  color: #52627c;
  line-height: 1.8;
}

.profile-workspace-panel__grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.08fr);
  gap: 1rem;
}

.profile-workspace-panel__panel {
  padding: 1.35rem 1.4rem;
}

.profile-workspace-panel__panel-head {
  display: grid;
  gap: 0.18rem;
}

.profile-workspace-panel__panel-intro {
  margin: 0.75rem 0 0;
  color: #64748b;
  line-height: 1.7;
}

.profile-workspace-panel__info-list {
  margin: 1rem 0 0;
  display: grid;
  gap: 0.8rem;
}

.profile-workspace-panel__info-item {
  display: grid;
  gap: 0.28rem;
  padding: 0.9rem 0.95rem;
  border-radius: 1rem;
  background: rgba(248, 250, 252, 0.85);
  border: 1px solid rgba(226, 232, 240, 0.78);
}

.profile-workspace-panel__info-item dt {
  color: #64748b;
  font-size: 0.8rem;
}

.profile-workspace-panel__info-item dd {
  margin: 0;
  color: #111827;
  font-weight: 600;
}

.profile-workspace-panel__form {
  display: grid;
  gap: 0.95rem;
  margin-top: 1rem;
}

.profile-workspace-panel__field {
  display: grid;
  gap: 0.45rem;
}

.profile-workspace-panel__field span {
  color: #334155;
  font-size: 0.88rem;
  font-weight: 600;
}

.profile-workspace-panel__field input {
  width: 100%;
  border: 1px solid rgba(203, 213, 225, 0.88);
  border-radius: 0.95rem;
  padding: 0.9rem 1rem;
  background: rgba(255, 255, 255, 0.94);
  color: #111827;
  outline: none;
  transition: border-color 0.18s ease, box-shadow 0.18s ease;
}

.profile-workspace-panel__field input:focus {
  border-color: rgba(37, 99, 235, 0.45);
  box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.08);
}

.profile-workspace-panel__message {
  margin: 0;
  padding: 0.88rem 0.95rem;
  border-radius: 0.95rem;
  font-size: 0.92rem;
}

.profile-workspace-panel__message--error {
  background: rgba(254, 242, 242, 0.92);
  border: 1px solid rgba(248, 113, 113, 0.26);
  color: #b91c1c;
}

.profile-workspace-panel__message--success {
  background: rgba(240, 253, 244, 0.92);
  border: 1px solid rgba(74, 222, 128, 0.24);
  color: #15803d;
}

.profile-workspace-panel__actions {
  display: flex;
  justify-content: flex-start;
}

@media (max-width: 900px) {
  .profile-workspace-panel__grid {
    grid-template-columns: 1fr;
  }
}
</style>
