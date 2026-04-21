<script setup lang="ts">
import { computed } from 'vue'

import type { AnalysisTaskProgressResponse, ConversationTaskResponse } from '@/types/api'
import type { TaskPollingState } from '@/types/chat'

const props = defineProps<{
  task: ConversationTaskResponse
  progress?: AnalysisTaskProgressResponse
  pollingState?: TaskPollingState
}>()

const emit = defineEmits<{
  retry: [taskId: string]
  resume: [taskId: string]
}>()

/** 组合任务显示所需的当前进度信息。 */
const effectiveProgress = computed(() => {
  return (
    props.progress || {
      task_id: props.task.task_id,
      status: props.task.status,
      current_step: props.task.current_step,
      progress: props.task.progress,
      steps: [],
      report_ready: props.task.report_ready,
      error_message: null,
    }
  )
})

const shouldShowResume = computed(() => {
  return (
    (effectiveProgress.value.status === 'pending' || effectiveProgress.value.status === 'processing') &&
    props.pollingState?.autoPollEnabled === false
  )
})
</script>

<template>
  <section class="analysis-task-message">
    <header class="analysis-task-message__header">
      <div>
        <p class="analysis-task-message__eyebrow">正在分析商品问题</p>
        <h3 class="analysis-task-message__title">{{ task.question }}</h3>
      </div>
      <span class="analysis-task-message__status">{{ effectiveProgress.status }}</span>
    </header>

    <div class="analysis-task-message__progress-shell">
      <div class="analysis-task-message__progress-bar" :style="{ width: `${effectiveProgress.progress}%` }" />
    </div>
    <p class="analysis-task-message__step">
      当前步骤：{{ effectiveProgress.current_step || '等待调度' }} · {{ effectiveProgress.progress }}%
    </p>

    <ul v-if="effectiveProgress.steps.length" class="analysis-task-message__steps">
      <li v-for="step in effectiveProgress.steps" :key="step.step">
        <span>{{ step.label }}</span>
        <strong>{{ step.status }}</strong>
      </li>
    </ul>

    <div v-if="shouldShowResume" class="analysis-task-message__actions">
      <button class="text-button" type="button" @click="emit('resume', task.task_id)">恢复自动轮询</button>
    </div>

    <div v-if="effectiveProgress.status === 'failed'" class="analysis-task-message__error">
      <p>{{ effectiveProgress.error_message || '分析任务失败。' }}</p>
      <button class="primary-button" type="button" @click="emit('retry', task.task_id)">重试任务</button>
    </div>
  </section>
</template>

<style scoped>
.analysis-task-message {
  display: grid;
  gap: 0.95rem;
  border: 1px solid rgba(226, 232, 240, 0.92);
  border-radius: 1.35rem;
  background: rgba(255, 255, 255, 0.88);
  padding: 1.15rem 1.2rem;
  box-shadow: 0 20px 44px rgba(15, 23, 42, 0.06);
}

.analysis-task-message__header {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
}

.analysis-task-message__eyebrow {
  margin: 0 0 0.35rem;
  color: #2563eb;
  font-size: 0.8rem;
}

.analysis-task-message__title {
  margin: 0;
  font-size: 1rem;
  line-height: 1.5;
  color: #132033;
}

.analysis-task-message__status {
  color: #64748b;
  font-size: 0.82rem;
  text-transform: uppercase;
}

.analysis-task-message__progress-shell {
  height: 0.7rem;
  border-radius: 999px;
  background: rgba(191, 219, 254, 0.36);
  overflow: hidden;
}

.analysis-task-message__progress-bar {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #2563eb 0%, #38bdf8 100%);
}

.analysis-task-message__step {
  margin: 0;
  color: #475569;
  font-size: 0.92rem;
}

.analysis-task-message__steps {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 0.55rem;
}

.analysis-task-message__steps li {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  color: #334155;
  font-size: 0.9rem;
}

.analysis-task-message__actions,
.analysis-task-message__error {
  display: flex;
  align-items: center;
  gap: 0.8rem;
}

.analysis-task-message__error {
  flex-wrap: wrap;
  color: #b42318;
}
</style>
