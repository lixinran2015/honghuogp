<template>
  <div
    :class="[
      'bg-dark-700 rounded-lg border border-border p-3 card-hover',
      trend === 'up' && 'border-profit/30',
      trend === 'down' && 'border-loss/30',
      className
    ]"
  >
    <!-- 标签 -->
    <div class="text-2xs font-medium text-dark-400 uppercase tracking-wider mb-1">
      {{ label }}
    </div>

    <!-- 数值 -->
    <div class="flex items-baseline gap-2">
      <span
        :class="[
          'text-kpi font-mono font-semibold',
          trend === 'up' && 'text-profit',
          trend === 'down' && 'text-loss',
          trend === 'neutral' && 'text-white'
        ]"
      >
        {{ formattedValue }}
      </span>
      <span
        v-if="change !== undefined"
        :class="[
          'text-xs font-mono',
          change > 0 && 'text-profit',
          change < 0 && 'text-loss',
          change === 0 && 'text-dark-400'
        ]"
      >
        {{ change > 0 ? '+' : '' }}{{ formattedChange }}%
      </span>
    </div>

    <!-- 副标题 -->
    <div v-if="subtitle" class="text-2xs text-dark-400 mt-1">
      {{ subtitle }}
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  label: {
    type: String,
    required: true
  },
  value: {
    type: [Number, String],
    required: true
  },
  change: {
    type: Number,
    default: undefined
  },
  subtitle: {
    type: String,
    default: ''
  },
  trend: {
    type: String,
    default: 'neutral',
    validator: (v) => ['up', 'down', 'neutral'].includes(v)
  },
  prefix: {
    type: String,
    default: ''
  },
  suffix: {
    type: String,
    default: ''
  },
  decimals: {
    type: Number,
    default: 2
  },
  className: {
    type: String,
    default: ''
  }
})

const formattedValue = computed(() => {
  const num = typeof props.value === 'string' ? parseFloat(props.value) : props.value
  if (isNaN(num)) return props.value

  // 大数字格式化
  if (Math.abs(num) >= 100000000) {
    return props.prefix + (num / 100000000).toFixed(props.decimals) + '亿' + props.suffix
  }
  if (Math.abs(num) >= 10000) {
    return props.prefix + (num / 10000).toFixed(props.decimals) + '万' + props.suffix
  }

  return props.prefix + num.toFixed(props.decimals) + props.suffix
})

const formattedChange = computed(() => {
  if (props.change === undefined) return '0.00'
  return props.change.toFixed(2)
})
</script>
