<script setup lang="ts">
import { computed, ref } from 'vue'

import { ApiClientError } from '@/api/client'
import { getProductVisualization } from '@/api/modules/analysis'
import UnifiedReportCharts from '@/components/chat/UnifiedReportCharts.vue'
import type { ProductVisualizationResponse } from '@/types/api'

const productUrlInput = ref('')
const loading = ref(false)
const errorMessage = ref('')
const result = ref<ProductVisualizationResponse | null>(null)

/** 生成商品标题显示文案。 */
const productDisplayName = computed(() => {
  if (!result.value?.product) {
    return '商品可视化分析'
  }
  return result.value.product.product_name || result.value.product.external_product_id
})

/** 生成总体概览卡片。 */
const overviewCards = computed(() => {
  const overview = result.value?.overview
  if (!overview) {
    return []
  }
  return [
    { label: '评论总量', value: String(overview.total_count) },
    { label: '平均评分', value: overview.avg_score.toFixed(2) },
    { label: '差评率', value: `${(overview.bad_review_rate * 100).toFixed(1)}%` },
    { label: '好评率', value: `${(overview.positive_review_rate * 100).toFixed(1)}%` },
  ]
})

/** 触发商品可视化分析。 */
async function submitAnalysis() {
  const productUrl = productUrlInput.value.trim()
  if (!productUrl) {
    errorMessage.value = '请输入有效的商品链接。'
    result.value = null
    return
  }

  loading.value = true
  errorMessage.value = ''
  try {
    const response = await getProductVisualization(productUrl)
    result.value = response.data
  } catch (error) {
    errorMessage.value = error instanceof ApiClientError ? error.message : '获取商品可视化分析失败'
    result.value = null
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <section class="product-visual-analysis-panel">
    <header class="product-visual-analysis-panel__hero">
      <div class="product-visual-analysis-panel__hero-copy">
        <span class="product-visual-analysis-panel__kicker">商品分析</span>
        <h2>输入商品链接，直接查看可视化分析结果</h2>
        <p>页面会基于现有评论统计结果生成总体判断、维度拆解、风险提示和购买建议。</p>
      </div>

      <form class="product-visual-analysis-panel__query" @submit.prevent="submitAnalysis">
        <label class="product-visual-analysis-panel__field">
          <span>商品链接</span>
          <input
            v-model="productUrlInput"
            class="product-visual-analysis-panel__input"
            type="text"
            placeholder="例如：https://item.jd.com/1000001.html"
          />
        </label>
        <button class="primary-button product-visual-analysis-panel__submit" type="submit" :disabled="loading">
          {{ loading ? '分析中...' : '开始分析' }}
        </button>
      </form>
    </header>

    <p v-if="errorMessage" class="product-visual-analysis-panel__feedback product-visual-analysis-panel__feedback--error">
      {{ errorMessage }}
    </p>

    <section
      v-if="!result && !loading && !errorMessage"
      class="product-visual-analysis-panel__state product-visual-analysis-panel__state--empty"
    >
      <strong>等待输入商品链接</strong>
      <p>请输入已入库商品链接，页面会直接返回同步统计分析结果。</p>
    </section>

    <section
      v-else-if="loading"
      class="product-visual-analysis-panel__state product-visual-analysis-panel__state--loading"
    >
      <strong>正在整理统计结果...</strong>
      <p>正在读取商品评论并生成总体分析、维度分析与购买建议。</p>
    </section>

    <section
      v-else-if="result && (!result.exists || !result.has_data)"
      class="product-visual-analysis-panel__state product-visual-analysis-panel__state--empty"
    >
      <strong>{{ result.exists ? '暂无可用评论数据' : '未找到对应商品' }}</strong>
      <p>{{ result.reason || '当前没有可用于分析的数据。' }}</p>
    </section>

    <section v-else-if="result" class="product-visual-analysis-panel__result">
      <article class="product-visual-analysis-panel__section">
        <header class="product-visual-analysis-panel__section-head">
          <div>
            <span class="product-visual-analysis-panel__section-kicker">总体分析</span>
            <h3>{{ productDisplayName }}</h3>
          </div>
          <span class="product-visual-analysis-panel__meta">
            {{ result.product?.source || '--' }} / ID {{ result.product?.product_id || '--' }}
          </span>
        </header>

        <div class="product-visual-analysis-panel__overview-grid">
          <div v-for="card in overviewCards" :key="card.label" class="product-visual-analysis-panel__overview-card">
            <span>{{ card.label }}</span>
            <strong>{{ card.value }}</strong>
          </div>
        </div>

        <p class="product-visual-analysis-panel__summary">{{ result.overview?.summary_text }}</p>
      </article>

      <article v-if="result.charts.length" class="product-visual-analysis-panel__section">
        <header class="product-visual-analysis-panel__section-head">
          <div>
            <span class="product-visual-analysis-panel__section-kicker">核心图表</span>
            <h3>用图表快速判断整体口碑与关键风险</h3>
          </div>
        </header>
        <UnifiedReportCharts :charts="result.charts" />
      </article>

      <article v-if="result.dimension_analysis" class="product-visual-analysis-panel__section">
        <header class="product-visual-analysis-panel__section-head">
          <div>
            <span class="product-visual-analysis-panel__section-kicker">维度分析</span>
            <h3>识别最强、最弱和讨论最集中的维度</h3>
          </div>
        </header>

        <div class="product-visual-analysis-panel__chip-grid">
          <div class="product-visual-analysis-panel__chip-card">
            <span>表现最好</span>
            <strong>{{ result.dimension_analysis.best_dimension || '暂无结论' }}</strong>
          </div>
          <div class="product-visual-analysis-panel__chip-card">
            <span>表现最弱</span>
            <strong>{{ result.dimension_analysis.weakest_dimension || '暂无结论' }}</strong>
          </div>
          <div class="product-visual-analysis-panel__chip-card">
            <span>讨论最多</span>
            <strong>{{ result.dimension_analysis.most_discussed_dimension || '暂无结论' }}</strong>
          </div>
        </div>
      </article>

      <article v-if="result.risk_analysis" class="product-visual-analysis-panel__section">
        <header class="product-visual-analysis-panel__section-head">
          <div>
            <span class="product-visual-analysis-panel__section-kicker">风险提示</span>
            <h3>重点关注差评集中点和体验不稳定的维度</h3>
          </div>
        </header>

        <div class="product-visual-analysis-panel__list-grid">
          <section class="product-visual-analysis-panel__list-card">
            <h4>高风险维度</h4>
            <ul>
              <li v-for="item in result.risk_analysis.high_risk_dimensions" :key="item">{{ item }}</li>
              <li v-if="!result.risk_analysis.high_risk_dimensions.length">暂无明显高风险维度</li>
            </ul>
          </section>
          <section class="product-visual-analysis-panel__list-card">
            <h4>两极分化维度</h4>
            <ul>
              <li v-for="item in result.risk_analysis.polarized_dimensions" :key="item">{{ item }}</li>
              <li v-if="!result.risk_analysis.polarized_dimensions.length">暂无明显两极分化维度</li>
            </ul>
          </section>
        </div>
      </article>

      <article v-if="result.trend_analysis" class="product-visual-analysis-panel__section">
        <header class="product-visual-analysis-panel__section-head">
          <div>
            <span class="product-visual-analysis-panel__section-kicker">趋势观察</span>
            <h3>结合时间趋势判断近期口碑变化</h3>
          </div>
        </header>
        <p class="product-visual-analysis-panel__summary">{{ result.trend_analysis.trend_summary }}</p>
      </article>

      <article v-if="result.suggestions" class="product-visual-analysis-panel__section">
        <header class="product-visual-analysis-panel__section-head">
          <div>
            <span class="product-visual-analysis-panel__section-kicker">购买建议</span>
            <h3>{{ result.suggestions.recommendation_level }}</h3>
          </div>
        </header>

        <p class="product-visual-analysis-panel__summary">{{ result.suggestions.purchase_advice }}</p>

        <div class="product-visual-analysis-panel__list-grid">
          <section class="product-visual-analysis-panel__list-card">
            <h4>主要优点</h4>
            <ul>
              <li v-for="item in result.suggestions.strengths" :key="item">{{ item }}</li>
            </ul>
          </section>
          <section class="product-visual-analysis-panel__list-card">
            <h4>主要风险</h4>
            <ul>
              <li v-for="item in result.suggestions.risks" :key="item">{{ item }}</li>
            </ul>
          </section>
          <section class="product-visual-analysis-panel__list-card">
            <h4>适合人群</h4>
            <ul>
              <li v-for="item in result.suggestions.suitable_for" :key="item">{{ item }}</li>
            </ul>
          </section>
        </div>
      </article>
    </section>
  </section>
</template>

<style scoped>
.product-visual-analysis-panel {
  display: grid;
  gap: 1rem;
  min-height: 0;
}

.product-visual-analysis-panel__hero,
.product-visual-analysis-panel__section,
.product-visual-analysis-panel__state {
  border: 1px solid rgba(226, 232, 240, 0.9);
  background: rgba(255, 255, 255, 0.88);
  box-shadow: 0 14px 36px rgba(15, 23, 42, 0.05);
}

.product-visual-analysis-panel__hero,
.product-visual-analysis-panel__section {
  padding: 1rem 1.1rem;
}

.product-visual-analysis-panel__hero {
  display: grid;
  gap: 1rem;
}

.product-visual-analysis-panel__hero-copy {
  display: grid;
  gap: 0.2rem;
}

.product-visual-analysis-panel__kicker,
.product-visual-analysis-panel__section-kicker {
  font-size: 0.75rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #2563eb;
}

.product-visual-analysis-panel__hero-copy h2,
.product-visual-analysis-panel__section-head h3 {
  margin: 0;
  color: #0f172a;
}

.product-visual-analysis-panel__hero-copy p,
.product-visual-analysis-panel__summary {
  margin: 0;
  color: #475569;
  line-height: 1.7;
}

.product-visual-analysis-panel__query {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 0.75rem;
  align-items: end;
}

.product-visual-analysis-panel__field {
  display: grid;
  gap: 0.42rem;
}

.product-visual-analysis-panel__field span {
  color: #334155;
  font-size: 0.82rem;
  font-weight: 600;
}

.product-visual-analysis-panel__input {
  border: 1px solid rgba(203, 213, 225, 0.9);
  padding: 0.85rem 0.95rem;
  background: rgba(255, 255, 255, 0.96);
  color: #0f172a;
}

.product-visual-analysis-panel__submit {
  min-width: 7rem;
}

.product-visual-analysis-panel__feedback {
  margin: 0;
  padding: 0.9rem 1rem;
}

.product-visual-analysis-panel__feedback--error {
  border: 1px solid rgba(248, 113, 113, 0.24);
  background: rgba(254, 242, 242, 0.9);
  color: #b91c1c;
}

.product-visual-analysis-panel__state {
  display: grid;
  gap: 0.35rem;
  padding: 1.1rem;
  color: #475569;
}

.product-visual-analysis-panel__state strong {
  color: #0f172a;
}

.product-visual-analysis-panel__result {
  display: grid;
  gap: 1rem;
}

.product-visual-analysis-panel__section-head {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: start;
  margin-bottom: 0.9rem;
}

.product-visual-analysis-panel__meta {
  color: #64748b;
  font-size: 0.8rem;
  white-space: nowrap;
}

.product-visual-analysis-panel__overview-grid,
.product-visual-analysis-panel__chip-grid,
.product-visual-analysis-panel__list-grid {
  display: grid;
  gap: 0.75rem;
}

.product-visual-analysis-panel__overview-grid {
  grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
  margin-bottom: 0.8rem;
}

.product-visual-analysis-panel__overview-card,
.product-visual-analysis-panel__chip-card,
.product-visual-analysis-panel__list-card {
  border: 1px solid rgba(226, 232, 240, 0.9);
  background: rgba(248, 250, 252, 0.92);
  padding: 0.9rem;
}

.product-visual-analysis-panel__overview-card,
.product-visual-analysis-panel__chip-card {
  display: grid;
  gap: 0.25rem;
}

.product-visual-analysis-panel__overview-card span,
.product-visual-analysis-panel__chip-card span {
  font-size: 0.78rem;
  color: #64748b;
}

.product-visual-analysis-panel__overview-card strong,
.product-visual-analysis-panel__chip-card strong {
  font-size: 1.05rem;
  color: #0f172a;
}

.product-visual-analysis-panel__list-grid {
  grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
}

.product-visual-analysis-panel__list-card {
  display: grid;
  gap: 0.55rem;
}

.product-visual-analysis-panel__list-card h4 {
  margin: 0;
  color: #0f172a;
  font-size: 0.95rem;
}

.product-visual-analysis-panel__list-card ul {
  margin: 0;
  padding-left: 1.15rem;
  color: #334155;
  line-height: 1.7;
}

@media (max-width: 900px) {
  .product-visual-analysis-panel__query {
    grid-template-columns: 1fr;
  }

  .product-visual-analysis-panel__section-head {
    flex-direction: column;
  }

  .product-visual-analysis-panel__meta {
    white-space: normal;
  }
}
</style>
