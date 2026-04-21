<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import { ApiClientError } from '@/api/client'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const activeTab = ref<'login' | 'register'>('login')
const loginForm = ref({ username: '', password: '' })
const registerForm = ref({ username: '', email: '', password: '' })
const errorMessage = ref('')
const successMessage = ref('')

const heroMetrics = computed(() => [
  { label: '统一入口', value: 'Chat + Analysis' },
  { label: '任务链路', value: '进度可追踪' },
  { label: '报告输出', value: '图表与证据' },
])

/** 提交登录表单。 */
async function submitLogin() {
  errorMessage.value = ''
  successMessage.value = ''

  try {
    await authStore.login(loginForm.value.username.trim(), loginForm.value.password)
    await router.push('/chat')
  } catch (error) {
    errorMessage.value = error instanceof ApiClientError ? error.message : '登录失败'
  }
}

/** 提交注册表单。 */
async function submitRegister() {
  errorMessage.value = ''
  successMessage.value = ''

  try {
    await authStore.register(
      registerForm.value.username.trim(),
      registerForm.value.email.trim(),
      registerForm.value.password,
    )
    successMessage.value = '注册成功，请直接登录。'
    activeTab.value = 'login'
  } catch (error) {
    errorMessage.value = error instanceof ApiClientError ? error.message : '注册失败'
  }
}
</script>

<template>
  <main class="auth-workspace">
    <section class="auth-shell">
      <article class="auth-hero">
        <div class="auth-hero__content">
          <p class="auth-hero__eyebrow">MA-ESAS</p>
          <h1>用一条消息，串起商品分析的整条工作流。</h1>
          <p class="auth-hero__summary">
            普通问答、评论分析、任务进度和最终报告都在同一条对话里完成，不需要切换入口。
          </p>

          <div class="auth-hero__metrics" aria-hidden="true">
            <div v-for="metric in heroMetrics" :key="metric.label" class="auth-hero__metric">
              <span>{{ metric.label }}</span>
              <strong>{{ metric.value }}</strong>
            </div>
          </div>
        </div>

        <div class="auth-hero__stage" aria-hidden="true">
          <div class="auth-stage__line" />
          <div class="auth-stage__item auth-stage__item--active">
            <span>01</span>
            <strong>发送问题或商品链接</strong>
          </div>
          <div class="auth-stage__item">
            <span>02</span>
            <strong>自动分流普通问答与分析任务</strong>
          </div>
          <div class="auth-stage__item">
            <span>03</span>
            <strong>在聊天流中返回图表、证据和摘要</strong>
          </div>
        </div>
      </article>

      <section class="auth-card">
        <div class="auth-card__header">
          <p class="auth-card__kicker">工作台入口</p>
          <h2>{{ activeTab === 'login' ? '登录你的分析工作台' : '创建新的工作台账号' }}</h2>
        </div>

        <div class="auth-card__tabs">
          <button
            class="auth-card__tab"
            :class="{ 'auth-card__tab--active': activeTab === 'login' }"
            type="button"
            @click="activeTab = 'login'"
          >
            登录
          </button>
          <button
            class="auth-card__tab"
            :class="{ 'auth-card__tab--active': activeTab === 'register' }"
            type="button"
            @click="activeTab = 'register'"
          >
            注册
          </button>
        </div>

        <p v-if="errorMessage" class="auth-card__message auth-card__message--error">{{ errorMessage }}</p>
        <p v-if="successMessage" class="auth-card__message auth-card__message--success">{{ successMessage }}</p>

        <form v-if="activeTab === 'login'" class="auth-form" @submit.prevent="submitLogin">
          <label class="auth-form__field">
            <span>用户名</span>
            <input v-model="loginForm.username" type="text" autocomplete="username" placeholder="输入你的用户名" />
          </label>

          <label class="auth-form__field">
            <span>密码</span>
            <input
              v-model="loginForm.password"
              type="password"
              autocomplete="current-password"
              placeholder="输入登录密码"
            />
          </label>

          <button class="primary-button auth-form__submit" type="submit" :disabled="authStore.loading">
            {{ authStore.loading ? '登录中...' : '登录' }}
          </button>
        </form>

        <form v-else class="auth-form" @submit.prevent="submitRegister">
          <label class="auth-form__field">
            <span>用户名</span>
            <input
              v-model="registerForm.username"
              type="text"
              autocomplete="username"
              placeholder="设置一个用户名"
            />
          </label>

          <label class="auth-form__field">
            <span>邮箱</span>
            <input
              v-model="registerForm.email"
              type="email"
              autocomplete="email"
              placeholder="输入你的邮箱"
            />
          </label>

          <label class="auth-form__field">
            <span>密码</span>
            <input
              v-model="registerForm.password"
              type="password"
              autocomplete="new-password"
              placeholder="设置登录密码"
            />
          </label>

          <button class="primary-button auth-form__submit" type="submit" :disabled="authStore.loading">
            {{ authStore.loading ? '提交中...' : '注册' }}
          </button>
        </form>
      </section>
    </section>
  </main>
</template>

<style scoped>
.auth-workspace {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 2rem;
  background:
    radial-gradient(circle at top left, rgba(14, 165, 233, 0.16), transparent 24%),
    radial-gradient(circle at right 20%, rgba(15, 23, 42, 0.08), transparent 26%),
    linear-gradient(180deg, #f7f8fb 0%, #eef2f7 100%);
}

.auth-shell {
  width: min(100%, 76rem);
  min-height: min(46rem, calc(100vh - 4rem));
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(24rem, 28rem);
  border-radius: 2rem;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.8);
  border: 1px solid rgba(226, 232, 240, 0.9);
  box-shadow: 0 28px 80px rgba(15, 23, 42, 0.1);
}

.auth-hero {
  position: relative;
  display: grid;
  grid-template-rows: 1fr auto;
  padding: 3rem;
  background:
    linear-gradient(145deg, rgba(248, 250, 252, 0.96) 0%, rgba(235, 241, 248, 0.96) 100%);
}

.auth-hero::after {
  content: '';
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 18% 18%, rgba(59, 130, 246, 0.16), transparent 18%),
    radial-gradient(circle at 82% 26%, rgba(15, 23, 42, 0.12), transparent 22%);
  pointer-events: none;
}

.auth-hero__content,
.auth-hero__stage {
  position: relative;
  z-index: 1;
}

.auth-hero__content {
  max-width: 34rem;
  display: grid;
  align-content: center;
  gap: 1.25rem;
}

.auth-hero__eyebrow,
.auth-card__kicker {
  margin: 0;
  font-size: 0.82rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #2563eb;
}

.auth-hero h1 {
  margin: 0;
  max-width: 10.5em;
  font-size: clamp(2.7rem, 4vw, 4.5rem);
  line-height: 0.96;
  letter-spacing: -0.04em;
  color: #0f172a;
}

.auth-hero__summary {
  margin: 0;
  max-width: 30rem;
  color: #475569;
  font-size: 1rem;
  line-height: 1.8;
}

.auth-hero__metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.85rem;
  padding-top: 0.5rem;
}

.auth-hero__metric {
  display: grid;
  gap: 0.3rem;
  padding-top: 0.85rem;
  border-top: 1px solid rgba(148, 163, 184, 0.35);
}

.auth-hero__metric span {
  color: #64748b;
  font-size: 0.8rem;
}

.auth-hero__metric strong {
  color: #111827;
  font-size: 0.96rem;
}

.auth-hero__stage {
  position: relative;
  display: grid;
  gap: 1rem;
  padding-top: 1.5rem;
}

.auth-stage__line {
  position: absolute;
  left: 0.65rem;
  top: 2rem;
  bottom: 2rem;
  width: 1px;
  background: linear-gradient(180deg, rgba(37, 99, 235, 0.45), rgba(148, 163, 184, 0.18));
}

.auth-stage__item {
  position: relative;
  display: grid;
  gap: 0.15rem;
  padding-left: 2.5rem;
  color: #475569;
}

.auth-stage__item::before {
  content: '';
  position: absolute;
  left: 0.25rem;
  top: 0.4rem;
  width: 0.8rem;
  height: 0.8rem;
  border-radius: 999px;
  background: #cbd5e1;
  box-shadow: 0 0 0 0.32rem rgba(255, 255, 255, 0.9);
}

.auth-stage__item--active::before {
  background: #2563eb;
}

.auth-stage__item span {
  font-size: 0.76rem;
  color: #64748b;
}

.auth-stage__item strong {
  font-size: 0.96rem;
  color: #0f172a;
  font-weight: 600;
}

.auth-card {
  display: grid;
  align-content: center;
  gap: 1.2rem;
  padding: 2.6rem 2.2rem;
  background: rgba(255, 255, 255, 0.92);
  border-left: 1px solid rgba(226, 232, 240, 0.75);
}

.auth-card__header {
  display: grid;
  gap: 0.45rem;
}

.auth-card__header h2 {
  margin: 0;
  font-size: 1.7rem;
  line-height: 1.15;
  color: #111827;
}

.auth-card__tabs {
  display: inline-grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.45rem;
  padding: 0.35rem;
  border-radius: 999px;
  background: #f1f5f9;
}

.auth-card__tab {
  border: none;
  border-radius: 999px;
  background: transparent;
  padding: 0.78rem 1rem;
  color: #475569;
  transition: background-color 0.18s ease, color 0.18s ease, transform 0.18s ease;
}

.auth-card__tab:hover {
  transform: translateY(-1px);
}

.auth-card__tab--active {
  background: #111827;
  color: #ffffff;
}

.auth-card__message {
  margin: 0;
  padding: 0.85rem 1rem;
  border-radius: 1rem;
  font-size: 0.92rem;
}

.auth-card__message--error {
  background: rgba(254, 226, 226, 0.78);
  color: #b91c1c;
}

.auth-card__message--success {
  background: rgba(220, 252, 231, 0.86);
  color: #166534;
}

.auth-form {
  display: grid;
  gap: 1rem;
}

.auth-form__field {
  display: grid;
  gap: 0.45rem;
}

.auth-form__field span {
  color: #475569;
  font-size: 0.9rem;
}

.auth-form__field input {
  width: 100%;
  border: 1px solid rgba(203, 213, 225, 0.9);
  border-radius: 1rem;
  padding: 0.95rem 1rem;
  font: inherit;
  background: #ffffff;
  transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
}

.auth-form__field input:focus {
  outline: none;
  border-color: rgba(37, 99, 235, 0.56);
  box-shadow: 0 0 0 0.28rem rgba(59, 130, 246, 0.14);
}

.auth-form__submit {
  margin-top: 0.4rem;
  min-height: 3.15rem;
}

@media (max-width: 1080px) {
  .auth-shell {
    grid-template-columns: 1fr;
    min-height: auto;
  }

  .auth-hero {
    min-height: 26rem;
  }

  .auth-card {
    border-left: none;
    border-top: 1px solid rgba(226, 232, 240, 0.75);
  }
}

@media (max-width: 720px) {
  .auth-workspace {
    padding: 1rem;
  }

  .auth-shell {
    border-radius: 1.5rem;
  }

  .auth-hero,
  .auth-card {
    padding: 1.5rem;
  }

  .auth-hero__metrics {
    grid-template-columns: 1fr;
  }

  .auth-hero h1 {
    max-width: none;
    font-size: clamp(2.2rem, 9vw, 3rem);
  }
}
</style>
