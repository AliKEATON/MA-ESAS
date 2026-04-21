<script setup lang="ts">
import { computed } from 'vue'

import type { MessageResponse } from '@/types/api'
import { renderMarkdown } from '@/utils/markdown'

const props = defineProps<{
  message: MessageResponse
}>()

/** 将助手文本渲染成安全 HTML。 */
const html = computed(() => renderMarkdown(props.message.content))
</script>

<template>
  <div class="assistant-message">
    <article class="assistant-message__body markdown-body" v-html="html" />
    <time class="assistant-message__time">{{ new Date(message.created_at).toLocaleString() }}</time>
  </div>
</template>

<style scoped>
.assistant-message {
  max-width: min(100%, 52rem);
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.assistant-message__body {
  color: #162131;
}

.assistant-message__time {
  color: #94a3b8;
  font-size: 0.78rem;
}
</style>
