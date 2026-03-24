<template>
  <div class="bg-white rounded-lg shadow p-4 relative">
    <div class="flex items-center justify-between mb-3">
      <h3 class="text-lg font-semibold text-gray-800">板块涨跌幅热力图</h3>
      <div class="flex items-center gap-2 text-xs text-gray-500">
        <span class="flex items-center gap-1">
          <span class="w-4 h-3 rounded" style="background: linear-gradient(to right, #22c55e, #fbbf24, #ef4444)"></span>
          跌 ← 平 → 涨
        </span>
      </div>
    </div>
    <div ref="chartRef" class="w-full" style="height: 400px"></div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  /** 板块数据，由父组件传入（与表格共享数据源） */
  items: { type: Array, default: () => [] }
})

const chartRef = ref(null)
let chartInstance = null

function getBarColor(pct) {
  if (pct == null) return '#9ca3af'
  const v = Number(pct)
  if (v > 5) return '#ef4444'
  if (v > 2) return '#f97316'
  if (v > 0) return '#eab308'
  if (v > -2) return '#84cc16'
  if (v > -5) return '#22c55e'
  return '#15803d'
}

function renderChart(items) {
  if (!chartRef.value) return

  if (!chartInstance) {
    chartInstance = echarts.init(chartRef.value)
  }

  const names = items.map((r) => r.name || r.sector_id || '-')
  const values = items.map((r) => (r.change_pct != null ? Number(r.change_pct) : 0))
  const colors = values.map((v) => getBarColor(v))

  const option = {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params) => {
        if (!params?.[0]?.data) return ''
        const idx = params[0].dataIndex
        const item = items[idx]
        const pct = item?.change_pct != null ? Number(item.change_pct).toFixed(2) + '%' : '-'
        const leader = item?.leader_stock || '-'
        return `<div class="text-sm">
          <div><strong>${item?.name || '-'}</strong></div>
          <div>涨跌幅: ${pct}</div>
          <div>领涨股: ${leader}</div>
        </div>`
      },
    },
    grid: { left: '3%', right: '4%', bottom: '3%', top: '2%', containLabel: true },
    xAxis: {
      type: 'category',
      data: names,
      axisLabel: {
        rotate: 45,
        fontSize: 10,
        formatter: (v) => (v.length > 6 ? v.slice(0, 6) + '…' : v),
      },
    },
    yAxis: {
      type: 'value',
      name: '涨跌幅%',
      axisLabel: { formatter: '{value}%' },
      splitLine: { lineStyle: { type: 'dashed', color: '#e5e7eb' } },
    },
    visualMap: {
      show: false,
      min: -5,
      max: 5,
      inRange: { color: ['#15803d', '#22c55e', '#84cc16', '#eab308', '#f97316', '#ef4444'] },
    },
    series: [
      {
        type: 'bar',
        data: values.map((v, i) => ({ value: v, itemStyle: { color: colors[i] } })),
        barWidth: '60%',
      },
    ],
  }

  chartInstance.setOption(option, true)
}

watch(() => props.items, (val) => renderChart(val || []), { immediate: true })

const _onResize = () => chartInstance?.resize()
onMounted(() => {
  window.addEventListener('resize', _onResize)
})
onUnmounted(() => {
  window.removeEventListener('resize', _onResize)
  chartInstance?.dispose()
})
</script>
