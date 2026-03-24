<template>
  <header class="fixed top-0 left-0 lg:left-64 right-0 h-16 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700 z-30 transition-[left] duration-300">
    <div class="h-full px-4 lg:px-6 flex items-center justify-between">
      <!-- 移动端：汉堡菜单 -->
      <button
        @click="toggleSidebar"
        class="lg:hidden p-2 -ml-2 rounded-lg text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800"
        title="打开菜单"
      >
        <Bars3Icon class="w-6 h-6" />
      </button>
      <!-- 右侧操作区 -->
      <div class="flex items-center gap-2 lg:gap-4 ml-auto">
        <button
          @click="toggleTheme"
          class="flex items-center gap-1.5 px-2.5 py-1.5 text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
          :title="'主题：' + getThemeLabel()"
        >
          <SunIcon v-if="theme === 'light'" class="w-4 h-4" />
          <MoonIcon v-else-if="theme === 'dark'" class="w-4 h-4" />
          <ComputerDesktopIcon v-else class="w-4 h-4" />
        </button>
        <button
          @click="$emit('open-command-palette')"
          class="flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
          title="快速搜索 (Ctrl+K)"
        >
          <MagnifyingGlassIcon class="w-4 h-4" />
          <span class="hidden sm:inline">搜索</span>
          <kbd class="hidden md:inline-flex px-1.5 py-0.5 text-xs rounded bg-gray-100 dark:bg-gray-700 font-mono">⌘K</kbd>
        </button>
        <div class="hidden md:block text-sm text-gray-500 dark:text-gray-400">
          更新时间：{{ updateTime }}
        </div>
        <button 
          @click="handleGlobalRefresh"
          class="px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
          :disabled="refreshing"
        >
          {{ refreshing ? '刷新中...' : '刷新' }}
        </button>
        <button 
          @click="showHelp = true"
          class="px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors flex items-center gap-1"
          title="使用说明"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          帮助
        </button>
      </div>
    </div>

    <!-- 帮助模态框 -->
    <HelpModal :isOpen="showHelp" @close="showHelp = false" />
  </header>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { MagnifyingGlassIcon, SunIcon, MoonIcon, ComputerDesktopIcon, Bars3Icon } from '@heroicons/vue/24/outline'
import HelpModal from '../HelpModal.vue'
import { useTheme } from '../../composables/useTheme'
import { useLayout } from '../../composables/useLayout'

const { theme, toggleTheme, getThemeLabel } = useTheme()
const { toggleSidebar } = useLayout()
import { dataCache } from '../../services/dataCache'

defineEmits(['open-command-palette'])

const updateTime = ref('--:--:--')
const refreshing = ref(false)
const showHelp = ref(false)

// 全局刷新：清除所有缓存并触发页面刷新
const handleGlobalRefresh = () => {
  refreshing.value = true
  // 清除所有缓存
  dataCache.clearAll()
  // 触发页面刷新（通过事件通知各个页面）
  window.dispatchEvent(new CustomEvent('global-refresh'))
  // 延迟重置状态
  setTimeout(() => {
    refreshing.value = false
  }, 500)
}

let _clockTimer = null
onMounted(() => {
  const update = () => {
    const now = new Date()
    updateTime.value = now.toLocaleTimeString('zh-CN')
  }
  update()
  _clockTimer = setInterval(update, 1000)
})
onUnmounted(() => {
  if (_clockTimer) clearInterval(_clockTimer)
})
</script>
