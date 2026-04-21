<script setup lang="ts">
import type { MessageResponse } from '@/types/api'

defineProps<{
  message: MessageResponse
}>()
</script>

<template>
  <div class="message-row message-row-user">
    <article class="user-bubble">
      <p class="user-bubble__content">{{ message.content }}</p>
      <time class="user-bubble__time">{{ new Date(message.created_at).toLocaleString() }}</time>
    </article>
  </div>
</template>

<style scoped>
.message-row {
  display: flex;
}

.message-row-user {
  justify-content: flex-end;
}

.user-bubble {
  max-width: min(76%, 42rem);
  border-radius: 1.45rem;
  background: linear-gradient(135deg, #eef2ff 0%, #ffffff 100%);
  border: 1px solid rgba(199, 210, 254, 0.8);
  padding: 1rem 1.15rem 0.78rem;
  box-shadow: 0 16px 34px rgba(37, 99, 235, 0.08);
}

.user-bubble__content {
  margin: 0;
  white-space: pre-wrap;
  color: #111827;
  line-height: 1.7;
}

.user-bubble__time {
  display: block;
  margin-top: 0.65rem;
  color: #64748b;
  font-size: 0.76rem;
  text-align: right;
}
</style>
