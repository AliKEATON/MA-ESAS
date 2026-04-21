<script setup lang="ts">
import type { DisplayMessage, TaskPollingState } from '@/types/chat'
import UnifiedAnalysisResultMessage from '@/components/chat/UnifiedAnalysisResultMessage.vue'
import AnalysisTaskMessage from '@/components/chat/AnalysisTaskMessage.vue'
import AssistantMessage from '@/components/chat/AssistantMessage.vue'
import UserBubbleMessage from '@/components/chat/UserBubbleMessage.vue'

defineProps<{
  messages: DisplayMessage[]
  taskPollingState: Record<string, TaskPollingState>
}>()

const emit = defineEmits<{
  retryTask: [taskId: string]
  resumeTask: [taskId: string]
}>()
</script>

<template>
  <section class="chat-message-list">
    <template v-for="item in messages" :key="item.id">
      <UserBubbleMessage v-if="item.kind === 'user' && item.message" :message="item.message" />

      <AssistantMessage v-else-if="item.kind === 'assistant' && item.message" :message="item.message" />

      <div v-else-if="item.kind === 'analysis-task' && item.task" class="chat-message-list__assistant-block">
        <UnifiedAnalysisResultMessage v-if="item.result" :result="item.result" />
        <AnalysisTaskMessage
          v-else
          :task="item.task"
          :progress="item.progress"
          :polling-state="taskPollingState[item.task.task_id]"
          @retry="emit('retryTask', $event)"
          @resume="emit('resumeTask', $event)"
        />
      </div>
    </template>
  </section>
</template>

<style scoped>
.chat-message-list {
  display: grid;
  gap: 1.5rem;
}

.chat-message-list > * {
  animation: message-rise 0.24s ease;
}

.chat-message-list__assistant-block {
  display: grid;
  gap: 0.8rem;
}

@keyframes message-rise {
  from {
    opacity: 0;
    transform: translateY(8px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
