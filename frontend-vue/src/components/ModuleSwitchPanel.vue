<template>
  <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
    <div class="flex items-center justify-between mb-4">
      <h3 class="text-lg font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
        <SwatchIcon class="w-5 h-5 text-primary-500" />
        系统模式
      </h3>
      <span :class="['text-xs px-2 py-1 rounded-full font-medium', modeBadgeClass]">
        {{ modeText }}
      </span>
    </div>

    <p class="text-sm text-gray-500 dark:text-gray-400 mb-4">
      切换系统模式以显示/隐藏对应的功能菜单
    </p>

    <div class="grid grid-cols-3 gap-2">
      <button
        v-for="mode in modes"
        :key="mode.value"
        @click="handleModeSwitch(mode.value)"
        :disabled="isLoading"
        :class="[
          'px-3 py-2 rounded-lg text-sm font-medium transition-colors',
          currentMode === mode.value
            ? 'bg-primary-500 text-white'
            : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600',
          isLoading && 'opacity-50 cursor-not-allowed'
        ]"
      >
        {{ mode.label }}
      </button>
    </div>

    <div v-if="error" class="mt-3 text-sm text-red-600 dark:text-red-400">
      {{ error }}
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { SwatchIcon } from '@heroicons/vue/24/outline'
import { useModuleConfig } from '../composables/useModuleConfig'

const { systemMode, setSystemMode, isLoading, error } = useModuleConfig()

const currentMode = computed(() => systemMode.value)

const modes = [
  { value: 'short_term', label: '短线龙头' },
  { value: 'long_term', label: '长线趋势' },
  { value: 'all', label: '完整系统' },
]

const modeText = computed(() => {
  const map = {
    short_term: '短线龙头',
    long_term: '长线趋势',
    all: '完整系统',
    unknown: '未知'
  }
  return map[currentMode.value] || '未知'
})

const modeBadgeClass = computed(() => {
  const map = {
    short_term: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
    long_term: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
    all: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
    unknown: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-400'
  }
  return map[currentMode.value] || map.unknown
})

async function handleModeSwitch(mode) {
  if (mode === currentMode.value) return
  const success = await setSystemMode(mode)
  if (success) {
    // 刷新页面以应用新的菜单配置
    window.location.reload()
  }
}
</script>
