<script setup lang="ts">
import { computed } from 'vue'
import { use } from 'echarts/core'
import { BarChart, LineChart, PieChart, RadarChart, ScatterChart } from 'echarts/charts'
import { GridComponent, LegendComponent, RadarComponent, TitleComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import VChart from 'vue-echarts'

import type { FinalResponseChart } from '@/types/api'

use([
  CanvasRenderer,
  BarChart,
  LineChart,
  PieChart,
  ScatterChart,
  RadarChart,
  GridComponent,
  LegendComponent,
  RadarComponent,
  TitleComponent,
  TooltipComponent,
])

const props = defineProps<{
  charts: FinalResponseChart[]
}>()

/** 将新版 final_response.charts 转成前端图表渲染配置。 */
const chartEntries = computed(() => {
  return props.charts.map((chart) => {
    const option = buildChartOption(chart)
    if (!option) {
      return null
    }

    return {
      key: chart.chart_id,
      title: chart.title || chart.chart_id,
      option,
    }
  })
    .filter(Boolean)
})

function buildChartOption(chart: FinalResponseChart) {
  if (chart.chart_type === 'pie') {
    return buildPieOption(chart)
  }

  if (chart.chart_type === 'radar') {
    return buildRadarOption(chart)
  }

  return buildAxisOption(chart)
}

function buildAxisOption(chart: FinalResponseChart) {
  const primarySeries = chart.series?.[0]
  if (!chart.x_axis?.length || !primarySeries?.data?.length) {
    return null
  }

  const supportsNumericAxis = chart.chart_type === 'scatter'
  const xAxisData = supportsNumericAxis ? undefined : chart.x_axis

  return {
    tooltip: { trigger: chart.chart_type === 'scatter' ? 'item' : 'axis' },
    legend: chart.series.length > 1 ? {} : undefined,
    grid: { left: 36, right: 18, top: 40, bottom: 24, containLabel: true },
    xAxis: {
      type: supportsNumericAxis ? 'value' : 'category',
      data: xAxisData,
      axisLabel: {
        color: '#60708c',
        rotate: !supportsNumericAxis && chart.x_axis.length > 5 ? 18 : 0,
      },
      splitLine: supportsNumericAxis ? { lineStyle: { color: 'rgba(148, 163, 184, 0.12)' } } : undefined,
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: '#60708c' },
      splitLine: { lineStyle: { color: 'rgba(148, 163, 184, 0.18)' } },
    },
    series: chart.series.map((series, index) => ({
      type: toEchartsSeriesType(chart.chart_type),
      name: series.name,
      data: supportsNumericAxis
        ? series.data.map((value, dataIndex) => [Number(chart.x_axis[dataIndex] ?? 0), Number(value)])
        : series.data.map((value) => Number(value)),
      stack: chart.chart_type === 'stacked_bar' ? 'total' : undefined,
      smooth: chart.chart_type === 'line',
      symbolSize: chart.chart_type === 'scatter' ? 12 : undefined,
      areaStyle: chart.chart_type === 'line' ? { opacity: 0.08 } : undefined,
      itemStyle: {
        color: index === 0 ? '#2f6fed' : '#38bdf8',
        borderRadius: chart.chart_type === 'bar' || chart.chart_type === 'stacked_bar' ? [8, 8, 0, 0] : undefined,
      },
    })),
  }
}

function buildPieOption(chart: FinalResponseChart) {
  const primarySeries = chart.series?.[0]
  if (!primarySeries?.data?.length) {
    return null
  }

  const pieData = primarySeries.data
    .map((item, index) => {
      if (typeof item === 'object' && item && 'name' in item && 'value' in item) {
        return { name: String(item.name), value: Number(item.value) }
      }

      const fallbackName = chart.x_axis[index]
      if (fallbackName === undefined) {
        return null
      }
      return { name: String(fallbackName), value: Number(item) }
    })
    .filter(Boolean)

  if (!pieData.length) {
    return null
  }

  return {
    tooltip: { trigger: 'item' },
    legend: { bottom: 0, textStyle: { color: '#60708c' } },
    series: [
      {
        type: 'pie',
        radius: ['42%', '70%'],
        itemStyle: { borderRadius: 8, borderColor: '#fff', borderWidth: 2 },
        label: { color: '#334155' },
        data: pieData,
      },
    ],
  }
}

function buildRadarOption(chart: FinalResponseChart) {
  const primarySeries = chart.series?.[0]
  if (!chart.x_axis?.length || !primarySeries?.data?.length) {
    return null
  }

  const indicators = chart.x_axis.map((label, index) => ({
    name: String(label),
    max: Math.max(...chart.series.map((series) => Number(series.data[index] ?? 0)), 1),
  }))

  return {
    tooltip: { trigger: 'item' },
    legend: chart.series.length > 1 ? { bottom: 0, textStyle: { color: '#60708c' } } : undefined,
    radar: {
      indicator: indicators,
      splitLine: { lineStyle: { color: 'rgba(148, 163, 184, 0.24)' } },
      axisLine: { lineStyle: { color: 'rgba(148, 163, 184, 0.3)' } },
      splitArea: { areaStyle: { color: ['rgba(255,255,255,0.6)'] } },
    },
    series: [
      {
        type: 'radar',
        data: chart.series.map((series) => ({
          name: series.name,
          value: series.data.map((item) => Number(item)),
        })),
      },
    ],
  }
}

function toEchartsSeriesType(chartType: FinalResponseChart['chart_type']) {
  if (chartType === 'line') {
    return 'line'
  }

  if (chartType === 'scatter') {
    return 'scatter'
  }

  return 'bar'
}
</script>

<template>
  <section v-if="chartEntries.length" class="report-charts">
    <div v-for="entry in chartEntries" :key="entry!.key" class="report-chart">
      <header class="report-chart__header">{{ entry!.title }}</header>
      <VChart :option="entry!.option" autoresize class="report-chart__canvas" />
    </div>
  </section>
</template>

<style scoped>
.report-charts {
  display: grid;
  gap: 0.95rem;
}

.report-chart {
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 1.2rem;
  background: rgba(255, 255, 255, 0.92);
  padding: 1rem 1rem 0.8rem;
}

.report-chart__header {
  margin-bottom: 0.75rem;
  font-size: 0.94rem;
  font-weight: 600;
  color: #0f172a;
}

.report-chart__canvas {
  height: 18rem;
}
</style>
