<template>
  <header class="fixed top-0 left-0 lg:left-64 right-0 h-16 glass-strong z-30 transition-[left] duration-300">
    <div class="h-full px-4 lg:px-6 flex items-center justify-between">
      <!-- 移动端：汉堡菜单 -->
      <button
        @click="toggleSidebar"
        class="lg:hidden p-2 -ml-2 rounded-lg text-warmgray-500 hover:bg-warm-100 hover:text-warmgray-900 transition-colors duration-150"
        title="打开菜单"
      >
        <Bars3Icon class="w-6 h-6" />
      </button>

      <!-- 页面标题 -->
      <div class="hidden lg:flex items-center gap-2">
        <h2 class="text-lg font-semibold text-warmgray-800">{{ pageTitle }}</h2>
      </div>

      <!-- 右侧操作区 -->
      <div class="flex items-center gap-2 lg:gap-3 ml-auto">
        <!-- 市场状态指示器 -->
        <div class="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-md bg-warm-100 border border-border">
          <div class="w-2 h-2 rounded-full bg-profit live-indicator"></div>
          <span class="text-xs text-warmgray-500">交易中</span>
        </div>

        <!-- 搜索按钮 -->
        <button
          @click="$emit('open-command-palette')"
          class="flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-warmgray-500 hover:text-warmgray-900 hover:bg-warm-100 rounded-md transition-all duration-150"
          title="快速搜索 (Ctrl+K)"
        >
          <MagnifyingGlassIcon class="w-4 h-4" />
          <span class="hidden sm:inline">搜索</span>
          <kbd class="hidden md:inline-flex px-1.5 py-0.5 text-xs rounded bg-warm-100 text-warmgray-500 font-mono border border-border">⌘K</kbd>
        </button>

        <!-- 刷新按钮 -->
        <button
          @click="handleGlobalRefresh"
          class="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-warmgray-500 hover:text-warmgray-900 hover:bg-warm-100 rounded-md transition-all duration-150"
          :disabled="refreshing"
          :class="{ 'opacity-50 cursor-not-allowed': refreshing }"
        >
          <ArrowPathIcon class="w-4 h-4" :class="{ 'animate-spin': refreshing }" />
          <span class="hidden sm:inline">{{ refreshing ? '刷新中' : '刷新' }}</span>
        </button>

        <!-- 帮助按钮 -->
        <button
          @click="showHelp = true"
          class="p-2 text-warmgray-500 hover:text-warmgray-900 hover:bg-warm-100 rounded-md transition-all duration-150"
          title="使用说明"
        >
          <QuestionMarkCircleIcon class="w-5 h-5" />
        </button>

        <!-- 当前时间 -->
        <div class="hidden lg:block text-sm text-warmgray-500 font-mono">
          {{ updateTime }}
        </div>
      </div>
    </div>

    <!-- 帮助模态框 -->
    <HelpModal :isOpen="showHelp" @close="showHelp = false" />
  </header>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import {
  MagnifyingGlassIcon,
  Bars3Icon,
  ArrowPathIcon,
  QuestionMarkCircleIcon
} from '@heroicons/vue/24/outline'
import HelpModal from '../HelpModal.vue'
import { useLayout } from '../../composables/useLayout'
import { dataCache } from '../../services/dataCache'

const route = useRoute()
const { toggleSidebar } = useLayout()

defineEmits(['open-command-palette'])

const updateTime = ref('--:--:--')
const refreshing = ref(false)
const showHelp = ref(false)

// 根据路由获取页面标题
const pageTitle = computed(() => {
  const titles = {
    '/leader-tracking': '龙头跟踪',
    '/holdings': '我的自选',
    '/watchlist': '股票跟踪',
    '/sentiment': '情绪分析',
    '/limit-up-2days': '2连板监控',
    '/hot-sector': '热门板块',
    '/startup': '启动监控',
    '/daily-review': '每日复盘',
  }
  return titles[route.path] || '短线龙头系统'
})

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
