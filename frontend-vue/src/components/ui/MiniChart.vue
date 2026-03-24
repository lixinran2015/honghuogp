<template>
  <svg :width="width" :height="height" class="mini-chart">
    <polyline
      v-if="points.length > 1"
      :points="pointsString"
      fill="none"
      :stroke="trend ? '#ef4444' : '#10b981'"
      stroke-width="1.5"
      stroke-linecap="round"
      stroke-linejoin="round"
    />
    <circle
      v-if="points.length > 0"
      :cx="points[points.length - 1].x"
      :cy="points[points.length - 1].y"
      r="2"
      :fill="trend ? '#ef4444' : '#10b981'"
    />
  </svg>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  data: {
    type: Array,
    default: () => []
  },
  trend: {
    type: Boolean,
    default: true
  },
  width: {
    type: Number,
    default: 80
  },
  height: {
    type: Number,
    default: 24
  }
})

const points = computed(() => {
  if (!props.data || props.data.length === 0) return []
  
  const prices = props.data.map(d => d.close || d.price || d)
  if (prices.length === 0) return []
  
  const min = Math.min(...prices)
  const max = Math.max(...prices)
  const range = max - min || 1
  
  const padding = 2
  const chartWidth = props.width - padding * 2
  const chartHeight = props.height - padding * 2
  
  return prices.map((price, i) => ({
    x: padding + (i / (prices.length - 1 || 1)) * chartWidth,
    y: padding + chartHeight - ((price - min) / range) * chartHeight
  }))
})

const pointsString = computed(() => {
  return points.value.map(p => `${p.x},${p.y}`).join(' ')
})
</script>

<style scoped>
.mini-chart {
  display: block;
}
</style>

