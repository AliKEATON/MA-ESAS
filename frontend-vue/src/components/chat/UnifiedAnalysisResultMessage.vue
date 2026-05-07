<script setup lang="ts">
import { computed } from 'vue'

import UnifiedReportCharts from '@/components/chat/UnifiedReportCharts.vue'
import type { AnalysisResultResponse } from '@/types/api'
import { renderMarkdown } from '@/utils/markdown'

const props = defineProps<{
  result: AnalysisResultResponse
}>()

/** 统一生成摘要正文，只消费新版 final_response.answer。 */
const summaryHtml = computed(() => {
  const answer = props.result.final_response?.answer
  return renderMarkdown(String(answer || '暂无摘要'))
})

/** 生成图表数据，只消费新版 final_response.charts。 */
const finalCharts = computed(() => props.result.final_response?.charts || [])

/** 生成商品标题显示文案。 */
const productDisplayName = computed(() => {
  const product = props.result.product
  if (!product) {
    return String(props.result.product_context?.external_product_id || '分析结果')
  }
  return product.product_name || product.external_product_id
})

const resultStatusLabel = computed(() => {
  return props.result.result_ready === false ? '处理中' : '已完成'
})
</script>

<template>
  <article class="analysis-result-message">
    <header class="analysis-result-message__header">
      <div>
        <p class="analysis-result-message__eyebrow">分析已完成</p>
        <h3 class="analysis-result-message__title">{{ productDisplayName }}</h3>
      </div>
      <div class="analysis-result-message__header-meta">
        <span class="analysis-result-message__status">{{ resultStatusLabel }}</span>
        <span class="analysis-result-message__source">
          {{ result.product?.source || result.product_context?.source || '--' }}
        </span>
      </div>
    </header>

    <div class="analysis-result-message__collapsed-progress">
      分析进度已完成，详细处理过程已自动收起。
    </div>

    <section class="analysis-result-message__section">
      <header class="analysis-result-message__section-title">结论摘要</header>
      <div class="markdown-body" v-html="summaryHtml" />
    </section>

    <section v-if="finalCharts.length" class="analysis-result-message__section">
      <header class="analysis-result-message__section-title">可视化图表</header>
      <UnifiedReportCharts :charts="finalCharts" />
    </section>

    <section v-if="result.evidence.length" class="analysis-result-message__section">
      <header class="analysis-result-message__section-title">证据评论</header>
      <ul class="analysis-result-message__evidence">
        <li v-for="(item, index) in result.evidence" :key="`${result.task_id}-${index}`">
          <div class="analysis-result-message__evidence-meta">
            <span>{{ item.dimension || '未分类' }}</span>
            <span v-if="item.score !== null">评分 {{ item.score }}</span>
            <span v-if="item.similarity !== null">相似度 {{ item.similarity }}</span>
          </div>
          <p>{{ item.content }}</p>
        </li>
      </ul>
    </section>
  </article>
</template>

<style scoped>
.analysis-result-message {
  display: grid;
  gap: 1.15rem;
  min-width: 0;
  max-width: 100%;
}

.analysis-result-message__header {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  min-width: 0;
}

.analysis-result-message__eyebrow {
  margin: 0 0 0.35rem;
  color: #0f766e;
  font-size: 0.8rem;
}

.analysis-result-message__title {
  margin: 0;
  color: #132033;
  font-size: 1.08rem;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.analysis-result-message__header-meta {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.analysis-result-message__status {
  border-radius: 999px;
  background: rgba(15, 118, 110, 0.12);
  color: #0f766e;
  padding: 0.28rem 0.65rem;
  font-size: 0.78rem;
  font-weight: 600;
}

.analysis-result-message__source {
  color: #64748b;
  font-size: 0.82rem;
  text-transform: uppercase;
}

.analysis-result-message__collapsed-progress {
  color: #64748b;
  font-size: 0.9rem;
  padding-bottom: 0.2rem;
  border-bottom: 1px dashed rgba(148, 163, 184, 0.35);
}

.analysis-result-message__section {
  display: grid;
  gap: 0.75rem;
  min-width: 0;
}

.analysis-result-message__section-title {
  color: #132033;
  font-weight: 600;
}

.analysis-result-message__evidence {
  display: grid;
  gap: 0.85rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.analysis-result-message__evidence li {
  border-left: 3px solid rgba(37, 99, 235, 0.22);
  padding-left: 0.9rem;
  min-width: 0;
}

.analysis-result-message__evidence p {
  margin: 0.35rem 0 0;
  color: #263243;
  line-height: 1.7;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.analysis-result-message__evidence-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.7rem;
  color: #64748b;
  font-size: 0.84rem;
}
</style>
