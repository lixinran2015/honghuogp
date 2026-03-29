<template>
  <aside
    :class="[
      'fixed left-0 top-0 w-64 h-screen bg-warmgray-50 border-r border-border overflow-y-auto z-40 transition-transform duration-300 ease-out',
      sidebarOpen ? 'translate-x-0' : '-translate-x-full',
      'lg:translate-x-0'
    ]"
  >
    <!-- Logo区域 -->
    <div class="h-16 flex items-center gap-3 px-4 border-b border-border bg-warm-50">
      <div class="w-8 h-8 bg-cta rounded-lg flex items-center justify-center shadow-lg shadow-cta/20">
        <span class="text-white font-bold text-sm">龙</span>
      </div>
      <div class="flex-1 min-w-0">
        <h1 class="text-base font-semibold text-warmgray-800 truncate">短线龙头系统</h1>
        <span :class="['text-xs px-1.5 py-0.5 rounded font-medium', systemModeClass]">
          {{ systemModeText }}
        </span>
      </div>
    </div>

    <!-- 菜单区域 -->
    <nav class="p-3 space-y-1">
      <div v-for="group in visibleMenuGroups" :key="group.id" class="mb-1">
        <!-- 一级菜单标题（可点击） -->
        <button
          @click="toggleGroup(group.id)"
          class="w-full px-3 py-2 text-xs font-semibold text-warmgray-500 uppercase tracking-wider hover:bg-warm-100 rounded-md transition-colors duration-150 flex items-center justify-between"
        >
          <span>{{ group.title }}</span>
          <component
            :is="isGroupExpanded(group.id) ? ChevronDownIcon : ChevronRightIcon"
            class="w-3.5 h-3.5 text-warmgray-400"
          />
        </button>

        <!-- 二级菜单项（可折叠） -->
        <transition name="slide-down">
          <div v-show="isGroupExpanded(group.id)" class="mt-0.5 space-y-0.5">
            <button
              v-for="item in group.items"
              :key="item.path"
              @click="handleNavClick(item)"
              :class="[
                'w-full px-3 py-2 rounded-md text-sm font-medium transition-all duration-150 flex items-center gap-2.5',
                isActive(item.path)
                  ? 'text-warmgray-900 bg-primary-100 border-l-2 border-cta'
                  : 'text-warmgray-600 hover:text-warmgray-900 hover:bg-warm-100'
              ]"
            >
              <component
                :is="getIconComponent(item.icon)"
                :class="[
                  'w-4 h-4 flex-shrink-0',
                  isActive(item.path) ? 'text-cta' : 'text-warmgray-400'
                ]"
              />
              <span>{{ item.label }}</span>
            </button>
          </div>
        </transition>
      </div>
    </nav>

    <!-- 底部信息 -->
    <div class="absolute bottom-0 left-0 right-0 p-3 border-t border-border bg-warmgray-50">
      <div class="flex items-center gap-2 text-xs text-warmgray-500">
        <div class="w-2 h-2 rounded-full bg-profit live-indicator"></div>
        <span>系统运行正常</span>
      </div>
    </div>
  </aside>
</template>

<script setup>
import { computed, ref, watch, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useLayout } from '../../composables/useLayout'
import { useModuleConfig } from '../../composables/useModuleConfig'
import {
  BriefcaseIcon,
  StarIcon,
  CogIcon,
  EyeIcon,
  ArrowTrendingUpIcon,
  RocketLaunchIcon,
  MagnifyingGlassIcon,
  ClockIcon,
  FireIcon,
  CheckCircleIcon,
  ChartBarIcon,
  ChevronRightIcon,
  ChevronDownIcon,
  ListBulletIcon,
  BookOpenIcon,
  CalendarDaysIcon,
  ArrowPathIcon,
  ClipboardDocumentListIcon,
  SwatchIcon,
  CpuChipIcon,
} from '@heroicons/vue/24/outline'

const router = useRouter()
const route = useRoute()
const { sidebarOpen, closeSidebar } = useLayout()
const { isShortTermEnabled, isLongTermEnabled, isCommonEnabled, systemMode, loadModuleStatus } = useModuleConfig()

const currentPath = computed(() => route.path)

// 展开/折叠状态管理
const expandedGroups = ref(new Set())

// 检查分组是否展开
const isGroupExpanded = (groupId) => {
  return expandedGroups.value.has(groupId)
}

// 切换分组展开/折叠
const toggleGroup = (groupId) => {
  if (expandedGroups.value.has(groupId)) {
    expandedGroups.value.delete(groupId)
  } else {
    expandedGroups.value.add(groupId)
  }
}

// 根据当前路由自动展开对应的分组
const autoExpandGroup = () => {
  const currentPathValue = currentPath.value
  for (const group of visibleMenuGroups.value) {
    const hasActiveItem = group.items.some(item => item.path === currentPathValue)
    if (hasActiveItem) {
      expandedGroups.value.add(group.id)
    }
  }
}

// 监听路由变化，自动展开对应分组
watch(currentPath, () => {
  autoExpandGroup()
})

// 组件挂载时加载模块状态并展开当前路由所在的分组
onMounted(async () => {
  console.log('[Sidebar] 开始加载模块状态...')
  await loadModuleStatus()
  console.log('[Sidebar] 模块状态加载完成:', {
    shortTerm: isShortTermEnabled.value,
    longTerm: isLongTermEnabled.value,
    common: isCommonEnabled.value,
    visibleGroups: visibleMenuGroups.value.map(g => g.id)
  })
  autoExpandGroup()
})

// 菜单分组配置（已按产品线拆分：短线龙头 / 长线趋势 / 共享底座）
// module 字段: 'short_term' | 'long_term' | 'common' | 'all'
const allMenuGroups = [
  {
    id: 'core',
    title: '选股中心',
    module: 'common',
    items: [
      { path: '/holdings', label: '我的自选', icon: 'BriefcaseIcon' },
      { path: '/watchlist', label: '股票跟踪', icon: 'EyeIcon' },
      { path: '/leader-tracking', label: '龙头跟踪', icon: 'ChartBarIcon' },
      { path: '/daily-review', label: '每日复盘', icon: 'ClipboardDocumentListIcon' },
    ]
  },
  {
    id: 'startup',
    title: '短线龙头',
    module: 'short_term',
    items: [
      { path: '/startup', label: '启动监控', icon: 'RocketLaunchIcon' },
      { path: '/startup-mainline', label: '主线雷达', icon: 'ChartBarIcon' },
      { path: '/startup-backtest', label: '启动回测', icon: 'ChartBarIcon' },
      { path: '/startup-performance', label: '启动表现', icon: 'ChartBarIcon' },
      { path: '/leader-buy-backtest', label: '龙头买点回测', icon: 'ChartBarIcon' },
      { path: '/leader-optimization', label: '龙头优化系统', icon: 'StarIcon' },
      { path: '/lstm-mab', label: 'LSTM-MAB 模型', icon: 'CpuChipIcon' },
      { path: '/leader-strategy-intro', label: '策略说明', icon: 'BookOpenIcon' },
      { path: '/diagnose', label: '单票诊断', icon: 'MagnifyingGlassIcon' },
      { path: '/limit-up-2days', label: '2连板', icon: 'ArrowTrendingUpIcon' },
    ]
  },
  {
    id: 'sector',
    title: '板块与龙头',
    module: 'long_term',
    items: [
      { path: '/hot-sector', label: '热门板块', icon: 'FireIcon' },
      { path: '/hot-sector-stocks', label: '板块股票', icon: 'ListBulletIcon' },
      { path: '/industry-leaders', label: '板块龙头', icon: 'StarIcon' },
      { path: '/absolute-leaders', label: '绝对龙头', icon: 'StarIcon' },
      { path: '/sector-board-leaders', label: '板块领涨', icon: 'ChartBarIcon' },
      { path: '/money-flow-heavy', label: '大额资金净流入', icon: 'ArrowTrendingUpIcon' },
    ]
  },
  {
    id: 'cycle',
    title: '周期与长期',
    module: 'long_term',
    items: [
      { path: '/industry-cycle', label: '行业周期', icon: 'ArrowPathIcon' },
      { path: '/theme-rotation', label: '长期主题轮动', icon: 'ArrowTrendingUpIcon' },
      { path: '/darwin', label: '达尔文长期策略', icon: 'ChartBarIcon' },
    ]
  },
  {
    id: 'research',
    title: '投研工具',
    module: 'long_term',
    items: [
      { path: '/backtest', label: '通用回测', icon: 'ChartBarIcon' },
      { path: '/factor-lab', label: '因子实验室', icon: 'ChartBarIcon' },
      { path: '/ai-strategy', label: 'AI 策略助手', icon: 'ChartBarIcon' },
      { path: '/recommendation-pool', label: '智能推荐', icon: 'StarIcon' },
      { path: '/stock-selector', label: '选股器', icon: 'MagnifyingGlassIcon' },
    ]
  },
  {
    id: 'review',
    title: '复盘与情绪',
    module: 'long_term',
    items: [
      { path: '/guba-popularity', label: '人气榜', icon: 'FireIcon' },
      { path: '/monitor-near5', label: '分时监控', icon: 'ClockIcon' },
      { path: '/limit-up-today-60d-high', label: '60日新高', icon: 'FireIcon' },
      { path: '/stable-rise', label: '止跌企稳回升', icon: 'ArrowTrendingUpIcon' },
      { path: '/high-stocks', label: '180日新高', icon: 'ArrowTrendingUpIcon' },
      { path: '/high-stocks-broken', label: '已破线股票', icon: 'ArrowTrendingUpIcon' },
      { path: '/sentiment', label: '情绪分析', icon: 'FireIcon' },
      { path: '/sold-stock', label: '已卖出', icon: 'CheckCircleIcon' },
      { path: '/knowledge-base', label: '知识库', icon: 'BookOpenIcon' },
    ]
  },
  {
    id: 'system',
    title: '设置与数据',
    module: 'common',
    items: [
      { path: '/strategy', label: '策略引擎', icon: 'CogIcon' },
      { path: '/data-management', label: '数据管理', icon: 'ChartBarIcon' },
      { path: '/stock-financial', label: '财务数据', icon: 'ChartBarIcon' },
      { path: '/scheduled-task', label: '定时任务', icon: 'ClockIcon' },
      { path: '/trade-calendar', label: '交易日历', icon: 'CalendarDaysIcon' },
      { path: '/leader-buy-meta', label: '龙头回测任务', icon: 'ChartBarIcon' },
    ]
  },
]

// 根据模块启用状态过滤菜单组
const visibleMenuGroups = computed(() => {
  return allMenuGroups.filter(group => {
    // 如果菜单组标记为 common，始终显示
    if (group.module === 'common') return isCommonEnabled.value
    // 如果标记为 short_term，根据短线模块状态
    if (group.module === 'short_term') return isShortTermEnabled.value
    // 如果标记为 long_term，根据长线模块状态
    if (group.module === 'long_term') return isLongTermEnabled.value
    // 默认显示
    return true
  })
})

// 系统模式显示文本
const systemModeText = computed(() => {
  switch (systemMode.value) {
    case 'short_term': return '短线龙头'
    case 'long_term': return '长线趋势'
    case 'all': return '完整系统'
    default: return '未知模式'
  }
})

// 系统模式样式
const systemModeClass = computed(() => {
  switch (systemMode.value) {
    case 'short_term': return 'bg-cta/15 text-cta'
    case 'long_term': return 'bg-primary-100 text-primary-700'
    case 'all': return 'bg-profit/15 text-profit'
    default: return 'bg-warm-100 text-warmgray-500'
  }
})

// 图标映射
const iconMap = {
  BriefcaseIcon,
  StarIcon,
  CogIcon,
  EyeIcon,
  ArrowTrendingUpIcon,
  RocketLaunchIcon,
  MagnifyingGlassIcon,
  ClockIcon,
  FireIcon,
  CheckCircleIcon,
  ChartBarIcon,
  ListBulletIcon,
  BookOpenIcon,
  CalendarDaysIcon,
  ArrowPathIcon,
  ClipboardDocumentListIcon,
  SwatchIcon,
}

const getIconComponent = (iconName) => {
  return iconMap[iconName] || BriefcaseIcon
}

const isActive = (path) => {
  return currentPath.value === path
}

const handleNavClick = (item) => {
  router.push(item.path)
  closeSidebar() // 移动端点击菜单后关闭侧边栏
}
</script>

<style scoped>
/* 折叠展开动画 */
.slide-down-enter-active {
  transition: all 0.2s ease-out;
  overflow: hidden;
}

.slide-down-leave-active {
  transition: all 0.15s ease-in;
  overflow: hidden;
}

.slide-down-enter-from {
  opacity: 0;
  max-height: 0;
  transform: translateY(-5px);
}

.slide-down-enter-to {
  opacity: 1;
  max-height: 500px;
  transform: translateY(0);
}

.slide-down-leave-from {
  opacity: 1;
  max-height: 500px;
  transform: translateY(0);
}

.slide-down-leave-to {
  opacity: 0;
  max-height: 0;
  transform: translateY(-5px);
}
</style>
