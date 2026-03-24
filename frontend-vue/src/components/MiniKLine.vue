<template>
  <div ref="el" class="w-full h-10"></div>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  tsCode: {
    type: String,
    required: true,
  },
  points: {
    type: Array,
    default: () => [],
  },
})

const el = ref(null)
let instance = null

const render = () => {
  if (!el.value) return
  const pts = props.points || []
  if (!pts.length) {
    if (instance) {
      instance.clear()
    }
    return
  }
  if (!instance) {
    instance = echarts.init(el.value)
  }
  const closes = pts.map((p) => p.close)
  const option = {
    animation: false,
    grid: { left: 0, right: 0, top: 0, bottom: 0 },
    xAxis: { type: 'category', show: false, data: pts.map((p) => p.trade_date) },
    yAxis: { type: 'value', show: false, scale: true },
    series: [
      {
        type: 'line',
        data: closes,
        showSymbol: false,
        lineStyle: { width: 1, color: '#4f46e5' },
        smooth: true,
      },
    ],
  }
  instance.setOption(option, true)
}

onMounted(() => {
  render()
})

watch(
  () => props.points,
  () => {
    render()
  },
  { deep: true },
)

onBeforeUnmount(() => {
  if (instance) {
    instance.dispose()
    instance = null
  }
})
</script>

<style scoped>
</style>

