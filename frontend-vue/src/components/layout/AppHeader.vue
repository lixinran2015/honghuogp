<template>
  <header class="sticky top-0 z-50 bg-white border-b border-gray-200">
    <div class="max-w-full mx-auto px-6">
      <!-- 第一行：Logo 和操作 -->
      <div class="h-16 flex items-center justify-between">
        <!-- Logo 和标题 -->
        <div class="flex items-center gap-3">
          <div class="w-8 h-8 bg-primary-500 rounded-lg flex items-center justify-center">
            <span class="text-white font-bold text-sm">选</span>
          </div>
          <h1 class="text-lg font-semibold text-gray-900">智能选股系统</h1>
        </div>
        
        <!-- 右侧操作区 -->
        <div class="flex items-center gap-4">
          <div class="text-sm text-gray-500">
            更新时间：{{ updateTime }}
          </div>
          <button 
            @click="handleGlobalRefresh"
            class="px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
            :disabled="refreshing"
          >
            {{ refreshing ? '刷新中...' : '刷新' }}
          </button>
          <button 
            @click="showHelp = true"
            class="px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-100 rounded-lg transition-colors flex items-center gap-1"
            title="使用说明"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            帮助
          </button>
        </div>
      </div>
      
      <!-- 第二行：导航菜单 -->
      <nav class="h-12 flex items-center gap-1 border-t border-gray-100">
        <NavItem
          v-for="item in navItems"
          :key="item.path"
          :item="item"
          :active="currentPath === item.path"
          @click="handleNavClick(item)"
        />
      </nav>
    </div>

    <!-- 帮助模态框 -->
    <HelpModal :isOpen="showHelp" @close="showHelp = false" />
  </header>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import NavItem from './NavItem.vue'
import HelpModal from '../HelpModal.vue'
import { dataCache } from '../../services/dataCache'

const router = useRouter()
const route = useRoute()

const currentPath = computed(() => route.path)

const updateTime = ref('--:--:--')
const refreshing = ref(false)
const showHelp = ref(false)

const navItems = [
  { path: '/holdings', label: '我的自选', icon: 'BriefcaseIcon' },
  { path: '/recommendation-pool', label: '💎 智能推荐', icon: 'StarIcon' },
  { path: '/stock-selector', label: '选股器', icon: 'SearchIcon' },
  { path: '/strategy', label: '策略引擎', icon: 'CogIcon' },
  { path: '/watchlist', label: '股票跟踪', icon: 'EyeIcon' },
  { path: '/high-stocks', label: '新高监控', icon: 'TrendingUpIcon' },
  { path: '/startup', label: '启动监控', icon: 'RocketIcon' },
  { path: '/diagnose', label: '单票诊断', icon: 'SearchIcon' },
  { path: '/monitor-near5', label: '分时监控', icon: 'ClockIcon' },
  { path: '/guba-popularity', label: '人气榜', icon: 'FireIcon' },
  { path: '/limit-up-2days', label: '2连板', icon: 'TrendingUpIcon' },
  { path: '/limit-up-today-60d-high', label: '涨停+新高', icon: 'FireIcon' },
  { path: '/sold-stock', label: '已卖出', icon: 'CheckCircleIcon' },
  { path: '/data-management', label: '数据管理', icon: 'ChartBarIcon' },
  { path: '/scheduled-task', label: '定时任务', icon: 'ClockIcon' },
]

const handleNavClick = (item) => {
  router.push(item.path)
}

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

