<template>
  <div
    :class="[
      'bg-dark-700 rounded-lg border border-border p-4 card-hover',
      className
    ]"
  >
    <!-- 卡片标题 -->
    <div v-if="title || $slots.header" class="flex items-center justify-between mb-3">
      <div class="flex items-center gap-2">
        <component v-if="icon" :is="icon" class="w-4 h-4 text-dark-400" />
        <h3 class="text-xs font-semibold text-dark-400 uppercase tracking-wider">{{ title }}</h3>
      </div>
      <slot name="header-action" />
    </div>

    <!-- 卡片内容 -->
    <div class="relative">
      <slot />
    </div>
  </div>
</template>

<script setup>
defineProps({
  title: {
    type: String,
    default: ''
  },
  icon: {
    type: [Object, Function],
    default: null
  },
  className: {
    type: String,
    default: ''
  }
})
</script>
