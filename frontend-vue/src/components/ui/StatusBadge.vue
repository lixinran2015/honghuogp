<template>
  <span
    :class="[
      'inline-flex items-center px-2 py-0.5 rounded text-xs font-medium',
      variantClasses[variant],
      sizeClasses[size],
      className
    ]"
  >
    <span
      v-if="dot"
      :class="[
        'w-1.5 h-1.5 rounded-full mr-1.5',
        dotClasses[variant]
      ]"
    />
    <slot />
  </span>
</template>

<script setup>
const props = defineProps({
  variant: {
    type: String,
    default: 'default',
    validator: (v) => ['default', 'success', 'warning', 'danger', 'info', 'neutral'].includes(v)
  },
  size: {
    type: String,
    default: 'md',
    validator: (v) => ['sm', 'md', 'lg'].includes(v)
  },
  dot: {
    type: Boolean,
    default: false
  },
  className: {
    type: String,
    default: ''
  }
})

const variantClasses = {
  default: 'bg-dark-600 text-dark-200',
  success: 'bg-profit/15 text-profit border border-profit/20',
  warning: 'bg-warning/15 text-warning border border-warning/20',
  danger: 'bg-loss/15 text-loss border border-loss/20',
  info: 'bg-info/15 text-info border border-info/20',
  neutral: 'bg-dark-700 text-dark-300 border border-border'
}

const dotClasses = {
  default: 'bg-dark-400',
  success: 'bg-profit',
  warning: 'bg-warning',
  danger: 'bg-loss',
  info: 'bg-info',
  neutral: 'bg-dark-400'
}

const sizeClasses = {
  sm: 'text-2xs px-1.5 py-0.5',
  md: 'text-xs px-2 py-0.5',
  lg: 'text-sm px-2.5 py-1'
}
</script>
