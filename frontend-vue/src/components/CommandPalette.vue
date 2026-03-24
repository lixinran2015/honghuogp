<template>
  <Teleport to="body">
    <TransitionRoot appear :show="isOpen" as="template">
      <Dialog as="div" class="relative z-[100]" @close="close">
        <TransitionChild
          as="template"
          enter="duration-200 ease-out"
          enter-from="opacity-0"
          enter-to="opacity-100"
          leave="duration-150 ease-in"
          leave-from="opacity-100"
          leave-to="opacity-0"
        >
          <div class="fixed inset-0 bg-black/40 backdrop-blur-sm" aria-hidden="true" />
        </TransitionChild>

        <div class="fixed inset-0 overflow-y-auto">
          <div class="flex min-h-full items-start justify-center pt-[15vh] px-4">
            <TransitionChild
              as="template"
              enter="duration-200 ease-out"
              enter-from="opacity-0 scale-95"
              enter-to="opacity-100 scale-100"
              leave="duration-150 ease-in"
              leave-from="opacity-100 scale-100"
              leave-to="opacity-0 scale-95"
            >
              <DialogPanel class="w-full max-w-xl transform overflow-hidden rounded-xl bg-white dark:bg-gray-800 shadow-xl transition-all">
                <!-- 搜索框 -->
                <div class="flex items-center gap-2 border-b border-gray-200 dark:border-gray-600 px-4 py-3">
                  <MagnifyingGlassIcon class="h-5 w-5 text-gray-400 flex-shrink-0" />
                  <input
                    ref="searchInputRef"
                    v-model="keyword"
                    type="text"
                    placeholder="搜索股票、行业或功能..."
                    class="flex-1 outline-none text-base placeholder-gray-400"
                    @keydown.down.prevent="selectNext"
                    @keydown.up.prevent="selectPrev"
                    @keydown.enter="handleEnter"
                  />
                  <kbd class="hidden sm:inline-flex h-6 items-center gap-1 rounded border border-gray-200 bg-gray-50 px-2 text-xs text-gray-500">ESC</kbd>
                </div>

                <!-- 结果区 -->
                <div class="max-h-[60vh] overflow-y-auto py-2">
                  <!-- 加载中 -->
                  <div v-if="searchLoading" class="px-4 py-8 text-center text-gray-500 text-sm">
                    搜索中...
                  </div>

                  <!-- 有输入：展示搜索结果 -->
                  <template v-else-if="keyword.trim().length >= 1">
                    <!-- 股票结果 -->
                    <div v-if="stockResults.length > 0" class="mb-2">
                      <div class="px-4 py-2 text-xs font-medium text-gray-500 uppercase">股票</div>
                      <button
                        v-for="(stock, idx) in stockResults"
                        :key="stock.ts_code"
                        :class="[
                          'w-full px-4 py-2.5 flex items-center gap-3 text-left transition-colors',
                          selectedIndex === idx ? 'bg-blue-50 text-blue-700' : 'hover:bg-gray-50'
                        ]"
                        @click="goToStock(stock)"
                      >
                        <span class="font-mono text-sm text-gray-600">{{ stock.code || stock.ts_code }}</span>
                        <span class="flex-1 truncate">{{ stock.name }}</span>
                      </button>
                    </div>

                    <!-- 板块结果 -->
                    <div v-if="filteredSectors.length > 0" class="mb-2">
                      <div class="px-4 py-2 text-xs font-medium text-gray-500 uppercase">板块</div>
                      <button
                        v-for="(sector, idx) in filteredSectors"
                        :key="sector.name"
                        :class="[
                          'w-full px-4 py-2.5 flex items-center justify-between text-left transition-colors',
                          selectedIndex === stockResults.length + idx ? 'bg-blue-50 text-blue-700' : 'hover:bg-gray-50'
                        ]"
                        @click="goToSector(sector)"
                      >
                        <span class="flex-1 truncate">{{ sector.name }}</span>
                        <span v-if="sector.change_pct != null" :class="sector.change_pct >= 0 ? 'text-red-500' : 'text-green-500'" class="text-sm ml-2">
                          {{ (sector.change_pct >= 0 ? '+' : '') + (sector.change_pct?.toFixed(2) || '') }}%
                        </span>
                      </button>
                    </div>

                    <!-- 功能入口（根据关键词过滤） -->
                    <div v-if="filteredRoutes.length > 0" class="mb-2">
                      <div class="px-4 py-2 text-xs font-medium text-gray-500 uppercase">功能</div>
                      <button
                        v-for="(route, idx) in filteredRoutes"
                        :key="route.path"
                        :class="[
                          'w-full px-4 py-2.5 flex items-center gap-3 text-left transition-colors',
                          selectedIndex === stockResults.length + filteredSectors.length + idx ? 'bg-blue-50 text-blue-700' : 'hover:bg-gray-50'
                        ]"
                        @click="goToRoute(route.path)"
                      >
                        <span class="text-gray-900">{{ route.label }}</span>
                      </button>
                    </div>

                    <!-- 无结果 -->
                    <div v-if="stockResults.length === 0 && filteredSectors.length === 0 && filteredRoutes.length === 0" class="px-4 py-8 text-center text-gray-500 text-sm">
                      未找到相关结果
                    </div>
                  </template>

                  <!-- 无输入：展示最近、热门与快速入口 -->
                  <template v-else>
                    <!-- 最近查看 -->
                    <div v-if="recentStocks.length > 0 || recentRoutes.length > 0" class="mb-2">
                      <div class="px-4 py-2 text-xs font-medium text-gray-500 uppercase">最近</div>
                      <template v-if="recentStocks.length > 0">
                        <button
                          v-for="(stock, idx) in recentStocks"
                          :key="stock.ts_code || stock.code"
                          :class="[
                            'w-full px-4 py-2.5 flex items-center gap-3 text-left transition-colors',
                            selectedIndex === idx ? 'bg-blue-50 text-blue-700' : 'hover:bg-gray-50'
                          ]"
                          @click="goToStock(stock)"
                        >
                          <span class="font-mono text-sm text-gray-600">{{ (stock.ts_code || stock.code)?.replace(/\.(SH|SZ|BJ)$/, '') }}</span>
                          <span class="flex-1 truncate">{{ stock.name }}</span>
                        </button>
                      </template>
                      <template v-if="recentRoutes.length > 0">
                        <button
                          v-for="(route, idx) in recentRoutes"
                          :key="route.path"
                          :class="[
                            'w-full px-4 py-2.5 flex items-center gap-3 text-left transition-colors',
                            selectedIndex === recentStocks.length + idx ? 'bg-blue-50 text-blue-700' : 'hover:bg-gray-50'
                          ]"
                          @click="goToRoute(route.path)"
                        >
                          <span class="text-gray-900">{{ route.label }}</span>
                        </button>
                      </template>
                    </div>
                    <!-- 热门股票 -->
                    <div v-if="hotStocks.length > 0" class="mb-2">
                      <div class="px-4 py-2 text-xs font-medium text-gray-500 uppercase">热门股票</div>
                      <button
                        v-for="(stock, idx) in hotStocks"
                        :key="stock.ts_code"
                        :class="[
                          'w-full px-4 py-2.5 flex items-center justify-between text-left transition-colors',
                          selectedIndex === recentStocks.length + recentRoutes.length + idx ? 'bg-blue-50 text-blue-700' : 'hover:bg-gray-50'
                        ]"
                        @click="goToStock(stock)"
                      >
                        <span class="font-mono text-sm text-gray-600">{{ stock.ts_code?.replace(/\.(SH|SZ|BJ)$/, '') }}</span>
                        <span class="flex-1 truncate ml-2">{{ stock.stock_name || stock.name }}</span>
                        <span v-if="stock.change_pct != null" :class="stock.change_pct >= 0 ? 'text-red-500' : 'text-green-500'" class="text-sm">
                          {{ (stock.change_pct >= 0 ? '+' : '') + (stock.change_pct?.toFixed(2) || '') }}%
                        </span>
                      </button>
                    </div>

                    <!-- 快速入口 -->
                    <div class="mb-2">
                      <div class="px-4 py-2 text-xs font-medium text-gray-500 uppercase">快速入口</div>
                      <button
                        v-for="(route, idx) in allRoutes"
                        :key="route.path"
                        :class="[
                          'w-full px-4 py-2.5 flex items-center gap-3 text-left transition-colors',
                          selectedIndex === recentStocks.length + recentRoutes.length + hotStocks.length + idx ? 'bg-blue-50 text-blue-700' : 'hover:bg-gray-50'
                        ]"
                        @click="goToRoute(route.path)"
                      >
                        <span class="text-gray-900">{{ route.label }}</span>
                      </button>
                    </div>
                  </template>
                </div>

                <div class="border-t border-gray-100 px-4 py-2 text-xs text-gray-400">
                  按 <kbd class="px-1.5 py-0.5 rounded bg-gray-100">↑</kbd><kbd class="px-1.5 py-0.5 rounded bg-gray-100">↓</kbd> 选择，<kbd class="px-1.5 py-0.5 rounded bg-gray-100">Enter</kbd> 确认
                </div>
              </DialogPanel>
            </TransitionChild>
          </div>
        </div>
      </Dialog>
    </TransitionRoot>
  </Teleport>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { Dialog, DialogPanel, TransitionRoot, TransitionChild } from '@headlessui/vue'
import { MagnifyingGlassIcon } from '@heroicons/vue/24/outline'
import axios from 'axios'

const props = defineProps({
  isOpen: { type: Boolean, default: false }
})

const emit = defineEmits(['close'])

const router = useRouter()
const keyword = ref('')
const searchInputRef = ref(null)
const searchLoading = ref(false)
const stockResults = ref([])
const sectorList = ref([])
const hotStocks = ref([])
const selectedIndex = ref(0)

const API_BASE = ''
const RECENT_STOCKS_KEY = 'cmd_recent_stocks'
const RECENT_ROUTES_KEY = 'cmd_recent_routes'
const RECENT_LIMIT = 5

// 与 Sidebar 一致的菜单（扁平化用于搜索）
const allRoutes = [
  { path: '/holdings', label: '我的自选' },
  { path: '/recommendation-pool', label: '💎 智能推荐' },
  { path: '/stock-selector', label: '选股器' },
  { path: '/watchlist', label: '股票跟踪' },
  { path: '/startup', label: '启动监控' },
  { path: '/diagnose', label: '单票诊断' },
  { path: '/monitor-near5', label: '分时监控' },
  { path: '/guba-popularity', label: '人气榜' },
  { path: '/limit-up-2days', label: '2连板' },
  { path: '/limit-up-today-60d-high', label: '60日新高' },
  { path: '/hot-sector', label: '热门板块' },
  { path: '/industry-leaders', label: '👑 板块龙头' },
  { path: '/money-flow-heavy', label: '💰 大额资金净流入' },
  { path: '/stable-rise', label: '📈 止跌企稳回升' },
  { path: '/theme-rotation', label: '长期主题轮动' },
  { path: '/recommendations', label: '推荐选股' },
  { path: '/darwin', label: '达尔文长期' },
  { path: '/data-management', label: '数据管理' },
  { path: '/trade-calendar', label: '📅 交易日历' },
  { path: '/industry-cycle', label: '🔄 行业周期' },
]

function getRecentStocks() {
  try {
    const s = localStorage.getItem(RECENT_STOCKS_KEY)
    return s ? JSON.parse(s) : []
  } catch {
    return []
  }
}

function saveRecentStock(stock) {
  const code = stock.ts_code || stock.code
  if (!code) return
  let list = getRecentStocks().filter(s => (s.ts_code || s.code) !== code)
  list.unshift({ ts_code: code, code, name: stock.stock_name || stock.name })
  list = list.slice(0, RECENT_LIMIT)
  localStorage.setItem(RECENT_STOCKS_KEY, JSON.stringify(list))
}

function getRecentRoutes() {
  try {
    const s = localStorage.getItem(RECENT_ROUTES_KEY)
    return s ? JSON.parse(s) : []
  } catch {
    return []
  }
}

function saveRecentRoute(path, label) {
  if (!path) return
  const route = allRoutes.find(r => r.path === path) || { path, label: label || path }
  let list = getRecentRoutes().filter(r => r.path !== path)
  list.unshift({ path: route.path, label: route.label })
  list = list.slice(0, RECENT_LIMIT)
  localStorage.setItem(RECENT_ROUTES_KEY, JSON.stringify(list))
}

const recentStocks = ref([])
const recentRoutes = ref([])

const filteredRoutes = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  if (kw.length < 1) return allRoutes
  return allRoutes.filter(r => r.label.toLowerCase().includes(kw) || r.path.toLowerCase().includes(kw))
})

const filteredSectors = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  if (kw.length < 1 || sectorList.value.length === 0) return []
  return sectorList.value.filter(s => (s.name || '').toLowerCase().includes(kw)).slice(0, 8)
})

const totalItems = computed(() => {
  if (keyword.value.trim().length >= 1) {
    return stockResults.value.length + filteredSectors.value.length + filteredRoutes.value.length
  }
  return recentStocks.value.length + recentRoutes.value.length + hotStocks.value.length + allRoutes.length
})

function close() {
  emit('close')
  keyword.value = ''
  stockResults.value = []
  selectedIndex.value = 0
}

function goToRoute(path) {
  saveRecentRoute(path)
  router.push(path)
  close()
}

function goToStock(stock) {
  const code = stock.ts_code || stock.code
  if (code) {
    saveRecentStock(stock)
    router.push({ path: '/diagnose', query: { code: code.replace(/\.(SH|SZ|BJ)$/, '') } })
  }
  close()
}

function goToSector(sector) {
  const name = sector.name
  if (name) {
    saveRecentRoute('/sector-board-leaders')
    router.push({ path: '/sector-board-leaders', query: { sector: name } })
  }
  close()
}

function selectNext() {
  selectedIndex.value = (selectedIndex.value + 1) % Math.max(1, totalItems.value)
}

function selectPrev() {
  selectedIndex.value = selectedIndex.value - 1
  if (selectedIndex.value < 0) selectedIndex.value = totalItems.value - 1
  selectedIndex.value = Math.max(0, selectedIndex.value)
}

function handleEnter() {
  if (keyword.value.trim().length >= 1) {
    const nStocks = stockResults.value.length
    const nSectors = filteredSectors.value.length
    const nRoutes = filteredRoutes.value.length
    if (selectedIndex.value < nStocks) {
      const stock = stockResults.value[selectedIndex.value]
      if (stock) goToStock(stock)
    } else if (selectedIndex.value < nStocks + nSectors) {
      const sector = filteredSectors.value[selectedIndex.value - nStocks]
      if (sector) goToSector(sector)
    } else {
      const routeIdx = selectedIndex.value - nStocks - nSectors
      const route = filteredRoutes.value[routeIdx]
      if (route) goToRoute(route.path)
    }
  } else {
    const rStocks = recentStocks.value
    const rRoutes = recentRoutes.value
    const hStocks = hotStocks.value
    const idx = selectedIndex.value
    if (idx < rStocks.length) {
      goToStock(rStocks[idx])
    } else if (idx < rStocks.length + rRoutes.length) {
      goToRoute(rRoutes[idx - rStocks.length].path)
    } else if (idx < rStocks.length + rRoutes.length + hStocks.length) {
      goToStock(hStocks[idx - rStocks.length - rRoutes.length])
    } else {
      const routeIdx = idx - rStocks.length - rRoutes.length - hStocks.length
      const route = allRoutes[routeIdx]
      if (route) goToRoute(route.path)
    }
  }
}

// 搜索股票（防抖 300ms）
let searchTimer = null
watch(keyword, (val) => {
  selectedIndex.value = 0
  if (searchTimer) clearTimeout(searchTimer)
  if (val.trim().length < 1) {
    stockResults.value = []
    return
  }
  searchTimer = setTimeout(async () => {
    searchLoading.value = true
    try {
      const res = await axios.get(`${API_BASE}/api/watchlist/search`, { params: { keyword: val.trim() } })
      if (res.data?.success && Array.isArray(res.data.data)) {
        stockResults.value = res.data.data.map(s => ({
          ts_code: s.ts_code,
          code: s.code,
          name: s.name
        }))
      } else {
        stockResults.value = []
      }
    } catch {
      stockResults.value = []
    } finally {
      searchLoading.value = false
    }
  }, 300)
})

// 加载热门股票
async function loadHotStocks() {
  try {
    const res = await axios.get(`${API_BASE}/api/guba/popularity`, { params: { limit: 10 } })
    if (res.data?.success && Array.isArray(res.data.data)) {
      hotStocks.value = res.data.data.slice(0, 10)
    } else {
      hotStocks.value = []
    }
  } catch {
    hotStocks.value = []
  }
}

// 加载板块列表（用于行业/板块搜索）
async function loadSectorList() {
  try {
    const res = await axios.get(`${API_BASE}/api/hot-sectors/industry-boards-with-leaders`)
    const items = res.data?.items || []
    sectorList.value = items.map(s => ({ name: s.name, change_pct: s.change_pct }))
  } catch {
    sectorList.value = []
  }
}

watch(() => props.isOpen, (open) => {
  if (open) {
    recentStocks.value = getRecentStocks()
    recentRoutes.value = getRecentRoutes()
    loadHotStocks()
    loadSectorList()
    keyword.value = ''
    stockResults.value = []
    selectedIndex.value = 0
    nextTick(() => searchInputRef.value?.focus())
  }
})

// 快捷键由父组件 App.vue 监听 Cmd/Ctrl+K 打开
</script>
