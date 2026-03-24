<template>
  <div
    :class="[
      'bg-white rounded-xl border border-gray-200 shadow-card',
      paddingClasses,
      hoverable && 'transition-all hover:shadow-hover hover:-translate-y-0.5',
      className
    ]"
  >
    <div v-if="$slots.header" class="mb-4">
      <slot name="header" />
    </div>
    
    <slot />
    
    <div v-if="$slots.footer" class="mt-4 pt-4 border-t border-gray-100">
      <slot name="footer" />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  padding: {
    type: String,
    default: 'md', // sm, md, lg, none
    validator: (v) => ['sm', 'md', 'lg', 'none'].includes(v),
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

const paddingClasses = computed(() => {
  const paddings = {
    sm: 'p-4',
    md: 'p-6',
    lg: 'p-8',
    none: '',
  }
  return paddings[props.padding]
})
</script>

