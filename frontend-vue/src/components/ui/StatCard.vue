<template>
  <div :class="['stat-card', className]">
    <div class="flex flex-col gap-3">
      <!-- 第一行：图标 + 标签 -->
      <div class="flex items-center gap-2">
        <div v-if="icon" class="p-1.5 rounded-lg flex-shrink-0" :class="iconBgClass">
          <component :is="icon" class="w-4 h-4" :class="iconColorClass" />
        </div>
        <p class="text-sm font-semibold text-gray-700 whitespace-nowrap">{{ label }}</p>
      </div>
      <!-- 第二行：数值 + 百分比 -->
      <div class="flex items-baseline justify-between gap-2">
        <p :class="['text-2xl font-bold truncate', valueColorClass]">
          {{ formattedValue }}
        </p>
        <div class="text-right flex-shrink-0">
          <p v-if="change !== undefined" :class="['text-sm font-semibold', changeColorClass]">
            {{ changeText }}
          </p>
          <p v-else class="text-sm font-semibold text-gray-400">--</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  label: {
    type: String,
    required: true,
  },
  value: {
    type: [String, Number],
    required: true,
  },
  change: {
    type: Number,
    default: undefined,
  },
  icon: {
    type: [Object, Function],
    default: null,
  },
  hoverable: {
    type: Boolean,
    default: false,
  },
  className: {
    type: String,
    default: '',
  },
})

const formattedValue = computed(() => {
  if (typeof props.value === 'number') {
    return props.value.toLocaleString('zh-CN')
  }
  return props.value
})

const changeText = computed(() => {
  if (props.change === undefined) return ''
  const sign = props.change >= 0 ? '+' : ''
  return `${sign}${props.change.toFixed(2)}%`
})

const changeColorClass = computed(() => {
  if (props.change === undefined) return 'text-gray-500'
  return props.change >= 0 ? 'text-red-600' : 'text-green-600'
})

const valueColorClass = computed(() => {
  return 'text-gray-900'
})

const iconBgClass = computed(() => {
  return 'bg-primary-50'
})

const iconColorClass = computed(() => {
  return 'text-primary-600'
})
</script>

<style scoped>
.stat-card {
  background: white;
  border-radius: 12px;
  padding: 1rem;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.04);
  transition: all 0.2s ease;
  min-height: 90px;
}

.stat-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  transform: translateY(-2px);
}
</style>

