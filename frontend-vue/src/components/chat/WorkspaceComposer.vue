<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{
  loading?: boolean
}>()

const emit = defineEmits<{
  send: [content: string]
}>()

const draft = ref('')

/** 发送当前输入内容。 */
function submit() {
  const content = draft.value.trim()
  if (!content || props.loading) {
    return
  }
  emit('send', content)
  draft.value = ''
}

/** 处理 Enter 快捷发送，Shift+Enter 保留换行。 */
function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    submit()
  }
}
</script>

<template>
  <div class="workspace-composer">
    <div class="workspace-composer__shell">
      <textarea
        v-model="draft"
        class="workspace-composer__textarea"
        rows="1"
        placeholder="发送普通问题，或发送商品链接并补充你的分析诉求"
        @keydown="onKeydown"
      />

      <button class="primary-button workspace-composer__button" type="button" :disabled="loading" @click="submit">
        {{ loading ? '发送中...' : '发送' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.workspace-composer {
  position: relative;
}

.workspace-composer__shell {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 0.85rem;
  align-items: end;
  padding: 0.95rem;
  border: 1px solid rgba(226, 232, 240, 0.95);
  border-radius: 1.55rem;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 22px 48px rgba(15, 23, 42, 0.08);
  backdrop-filter: blur(18px);
}

.workspace-composer__textarea {
  min-height: 3.2rem;
  max-height: 12rem;
  resize: vertical;
  border: none;
  outline: none;
  background: transparent;
  color: #111827;
  font: inherit;
  line-height: 1.7;
}

.workspace-composer__textarea::placeholder {
  color: #94a3b8;
}

.workspace-composer__button {
  min-width: 6rem;
  min-height: 3.1rem;
}

@media (max-width: 640px) {
  .workspace-composer__shell {
    grid-template-columns: 1fr;
  }

  .workspace-composer__button {
    width: 100%;
  }
}
</style>
