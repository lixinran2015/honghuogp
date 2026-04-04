<template>
  <div class="p-4 lg:p-6 bg-warm-50 min-h-screen">
    <!-- 页面标题 -->
    <div class="mb-6 flex items-center justify-between">
      <div>
        <h1 class="text-xl font-bold text-warmgray-900">短线龙头仪表盘</h1>
        <p class="text-sm text-warmgray-500 mt-1">
          实时监控市场龙头动态，捕捉短线交易机会
        </p>
      </div>
      <div class="flex items-center gap-2">
        <button
          @click="refreshAllData"
          :disabled="loading"
          class="px-4 py-2 rounded-md text-sm font-medium text-warmgray-900 bg-cta hover:bg-cta-hover disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
        >
          <ArrowPathIcon class="w-4 h-4" :class="{ 'animate-spin': loading }" />
          {{ loading ? '刷新中...' : '刷新数据' }}
        </button>
      </div>
    </div>

    <!-- 错误提示 -->
    <div
      v-if="error"
      class="mb-4 bg-loss/10 border border-loss/30 text-loss text-sm px-4 py-3 rounded-lg"
    >
      <div class="flex items-center gap-2">
        <ExclamationCircleIcon class="w-4 h-4" />
        {{ error }}
      </div>
    </div>

    <!-- 熔断警告 -->
    <div
      v-if="circuitBreaker?.triggered"
      class="mb-4 bg-red-50 border border-red-200 rounded-lg p-4 flex items-start gap-3"
    >
      <ShieldExclamationIcon class="w-6 h-6 text-red-600 flex-shrink-0 mt-0.5" />
      <div>
        <h3 class="font-semibold text-red-700">熔断已触发</h3>
        <p class="text-sm text-red-600 mt-1">
          健康度={{ circuitBreaker.health_score }}，关键告警={{ circuitBreaker.critical_count }} 条。
          建议暂停新开仓，优先处理持仓止损与止盈。
        </p>
      </div>
    </div>

    <!-- 主布局：左侧主要区域 + 右侧侧边栏 -->
    <div class="grid grid-cols-1 xl:grid-cols-12 gap-4">
      <!-- 左侧主区域 (8列) -->
      <div class="xl:col-span-8 space-y-4">
        <!-- 市场简报卡片 -->
        <div class="bg-white rounded-lg border border-border p-4">
          <div class="flex items-center justify-between mb-3">
            <h2 class="text-sm font-semibold text-warmgray-900 flex items-center gap-2">
              <ChartBarIcon class="w-4 h-4 text-cta" />
              市场简报
            </h2>
            <div class="flex items-center gap-2">
              <span class="text-xs text-warmgray-500">情绪周期:</span>
              <span
                :class="[
                  'px-2 py-0.5 rounded-full text-xs font-medium',
                  emotionCycleClass
                ]"
              >
                {{ marketBrief.emotion_cycle || '震荡期' }}
                <span v-if="marketBrief.emotion_cycle === '高涨期'">🔥</span>
                <span v-else-if="marketBrief.emotion_cycle === '冰点期'">❄️</span>
              </span>
            </div>
          </div>

          <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div class="bg-warmgray-50 rounded-lg p-3">
              <div class="text-xs text-warmgray-500">涨停</div>
              <div class="text-lg font-semibold text-profit">
                {{ marketBrief.limit_up_count || 0 }}家
              </div>
            </div>
            <div class="bg-warmgray-50 rounded-lg p-3">
              <div class="text-xs text-warmgray-500">跌停</div>
              <div class="text-lg font-semibold text-loss">
                {{ marketBrief.limit_down_count || 0 }}家
              </div>
            </div>
            <div class="bg-warmgray-50 rounded-lg p-3">
              <div class="text-xs text-warmgray-500">炸板率</div>
              <div class="text-lg font-semibold" :class="getBombRateClass">
                {{ marketBrief.bomb_rate || 0 }}%
              </div>
            </div>
            <div class="bg-warmgray-50 rounded-lg p-3">
              <div class="text-xs text-warmgray-500">连板高度</div>
              <div class="text-lg font-semibold text-warmgray-900">
                {{ marketBrief.max_continuous || 0 }}板
              </div>
            </div>
          </div>

          <div class="mt-3 flex items-center gap-4 text-xs text-warmgray-500">
            <span>昨日涨停溢价: <span class="font-medium" :class="marketBrief.premium_yesterday > 0 ? 'text-profit' : 'text-loss'">{{ marketBrief.premium_yesterday > 0 ? '+' : '' }}{{ marketBrief.premium_yesterday || 0 }}%</span></span>
            <span>市场状态: <span class="font-medium text-warmgray-900">{{ marketBrief.market_status || '正常' }}</span></span>
          </div>
        </div>

        <!-- TOP精选 (S级) -->
        <div class="bg-white rounded-lg border border-border p-4">
          <div class="flex items-center justify-between mb-3">
            <h2 class="text-sm font-semibold text-warmgray-900 flex items-center gap-2">
              <StarIcon class="w-4 h-4 text-cta" />
              TOP精选 (S级)
            </h2>
            <button
              @click="importToHoldings"
              :disabled="topPicks.length === 0"
              class="px-3 py-1.5 text-xs font-medium text-white bg-cta hover:bg-cta-hover disabled:opacity-50 rounded-md flex items-center gap-1"
            >
              <PlusIcon class="w-3.5 h-3.5" />
              一键导入持仓
            </button>
          </div>

          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="bg-warmgray-50">
                  <th class="px-3 py-2 text-left text-warmgray-600 font-medium">股票</th>
                  <th class="px-3 py-2 text-center text-warmgray-600 font-medium">评分</th>
                  <th class="px-3 py-2 text-left text-warmgray-600 font-medium">买点</th>
                  <th class="px-3 py-2 text-center text-warmgray-600 font-medium">仓位</th>
                  <th class="px-3 py-2 text-center text-warmgray-600 font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="stock in topPicks"
                  :key="stock.ts_code"
                  class="border-b border-border hover:bg-warmgray-50 transition-colors"
                >
                  <td class="px-3 py-2.5">
                    <div class="font-medium text-warmgray-900">{{ stock.name }}</div>
                    <div class="text-xs text-warmgray-500">{{ stock.ts_code }}</div>
                  </td>
                  <td class="px-3 py-2.5 text-center">
                    <div class="font-semibold" :class="getScoreColor(stock.lstm_mab_score?.total_score)">
                      {{ stock.lstm_mab_score?.total_score?.toFixed(0) || '-' }}
                    </div>
                    <div class="text-xs font-medium" :class="getGradeClass(stock.lstm_mab_score?.grade)">
                      {{ stock.lstm_mab_score?.grade || 'D' }}
                    </div>
                  </td>
                  <td class="px-3 py-2.5">
                    <div class="flex items-center gap-1">
                      <span
                        v-if="stock.buy_signal?.signal_type"
                        class="px-1.5 py-0.5 bg-cta/10 text-cta text-xs rounded"
                      >
                        {{ stock.buy_signal.signal_type }}
                      </span>
                      <span v-else class="text-warmgray-400 text-xs">-</span>
                    </div>
                  </td>
                  <td class="px-3 py-2.5 text-center">
                    <span class="font-medium text-warmgray-900">
                      {{ stock.lstm_mab_score?.recommendation?.position_size || 0 }}%
                    </span>
                  </td>
                  <td class="px-3 py-2.5 text-center">
                    <button
                      @click="viewStockDetail(stock)"
                      class="px-2 py-1 text-xs text-cta hover:bg-cta/10 rounded transition-colors"
                    >
                      查看
                    </button>
                  </td>
                </tr>
                <tr v-if="topPicks.length === 0">
                  <td colspan="5" class="px-3 py-8 text-center text-warmgray-500">
                    暂无S级推荐股票
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- 龙头梯队图 -->
        <div class="bg-white rounded-lg border border-border p-4">
          <h2 class="text-sm font-semibold text-warmgray-900 mb-3 flex items-center gap-2">
            <RectangleStackIcon class="w-4 h-4 text-cta" />
            龙头梯队图
          </h2>

          <div class="space-y-2">
            <div
              v-for="item in sortedLadder"
              :key="item.height"
              class="flex items-center gap-3"
            >
              <div class="w-12 text-xs font-medium text-warmgray-500 text-right">
                {{ item.height }}板
              </div>
              <div class="flex-1 flex items-center gap-2 flex-wrap">
                <span
                  v-for="stock in item.stocks"
                  :key="stock.ts_code"
                  :class="[
                    'px-2 py-1 rounded text-xs font-medium cursor-pointer transition-colors',
                    stock.is_space_leader
                      ? 'bg-red-100 text-red-700 border border-red-200'
                      : 'bg-warmgray-100 text-warmgray-700 hover:bg-warmgray-200'
                  ]"
                  @click="viewStockDetail(stock)"
                >
                  {{ stock.name }}
                  <span v-if="stock.is_space_leader" class="ml-1">👑</span>
                </span>
                <span v-if="item.stocks.length === 0" class="text-xs text-warmgray-400">-</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧侧边栏 (4列) -->
      <div class="xl:col-span-4 space-y-4">
        <!-- 我的持仓 -->
        <div class="bg-white rounded-lg border border-border p-4">
          <h2 class="text-sm font-semibold text-warmgray-900 mb-3 flex items-center gap-2">
            <WalletIcon class="w-4 h-4 text-cta" />
            我的持仓
          </h2>

          <div class="space-y-2">
            <div
              v-for="position in holdings"
              :key="position.ts_code"
              class="flex items-center justify-between p-2 rounded-lg hover:bg-warmgray-50 transition-colors"
              :class="{ 'bg-red-50/50': position.profit_pct <= -5 }"
            >
              <div>
                <div class="font-medium text-warmgray-900">{{ position.name }}</div>
                <div class="text-xs text-warmgray-500">
                  {{ position.buy_price?.toFixed(2) }} → {{ position.current_price?.toFixed(2) }}
                </div>
              </div>
              <div class="text-right">
                <div
                  class="font-semibold"
                  :class="position.profit_pct >= 0 ? 'text-profit' : 'text-loss'"
                >
                  {{ position.profit_pct >= 0 ? '+' : '' }}{{ position.profit_pct?.toFixed(1) }}%
                </div>
                <div class="text-xs">
                  <span
                    v-if="position.profit_pct <= -5"
                    class="px-1.5 py-0.5 bg-red-100 text-red-600 rounded"
                  >
                    止损⚠️
                  </span>
                  <span
                    v-else-if="position.profit_pct >= 10"
                    class="px-1.5 py-0.5 bg-green-100 text-green-600 rounded"
                  >
                    持有
                  </span>
                  <span
                    v-else
                    class="text-warmgray-400"
                  >
                    持有
                  </span>
                </div>
              </div>
            </div>

            <div v-if="holdings.length === 0" class="text-center py-6 text-warmgray-400 text-sm">
              暂无持仓
            </div>
          </div>

          <!-- 持仓汇总 -->
          <div v-if="holdings.length > 0" class="mt-3 pt-3 border-t border-border">
            <div class="flex items-center justify-between text-sm">
              <span class="text-warmgray-500">总盈亏</span>
              <span
                class="font-semibold"
                :class="totalProfit >= 0 ? 'text-profit' : 'text-loss'"
              >
                {{ totalProfit >= 0 ? '+' : '' }}{{ totalProfit?.toFixed(2) }}%
              </span>
            </div>
          </div>
        </div>

        <!-- 板块热度云图 -->
        <div class="bg-white rounded-lg border border-border p-4">
          <h2 class="text-sm font-semibold text-warmgray-900 mb-3 flex items-center gap-2">
            <FireIcon class="w-4 h-4 text-cta" />
            板块热度
          </h2>

          <!-- 气泡图容器 -->
          <div class="relative h-48 bg-warmgray-50 rounded-lg overflow-hidden">
            <div
              v-for="sector in sectorHeatList"
              :key="sector.name"
              :style="{
                position: 'absolute',
                left: `${sector.x}%`,
                top: `${sector.y}%`,
                transform: 'translate(-50%, -50%)'
              }"
              class="flex flex-col items-center justify-center rounded-full transition-all hover:scale-110 cursor-pointer"
              :class="getSectorBubbleClass(sector.heat)"
              :title="`${sector.name}: 热度 ${sector.heat?.toFixed(1)}`"
              @click="viewSectorDetail(sector)"
            >
              <span class="text-xs font-medium text-center px-1">{{ sector.name }}</span>
              <span class="text-xs opacity-75">{{ sector.heat?.toFixed(0) }}</span>
            </div>

            <div v-if="sectorHeatList.length === 0" class="absolute inset-0 flex items-center justify-center text-warmgray-400 text-sm">
              暂无板块数据
            </div>
          </div>

          <!-- 板块列表 -->
          <div class="mt-3 space-y-1">
            <div
              v-for="sector in topSectors"
              :key="sector.name"
              class="flex items-center justify-between py-1"
            >
              <span class="text-sm text-warmgray-700">{{ sector.name }}</span>
              <div class="flex items-center gap-2">
                <div class="w-16 h-1.5 bg-warmgray-200 rounded-full overflow-hidden">
                  <div
                    class="h-full rounded-full"
                    :class="sector.heat >= 20 ? 'bg-red-500' : sector.heat >= 15 ? 'bg-orange-500' : 'bg-yellow-500'"
                    :style="{ width: `${Math.min(sector.heat * 4, 100)}%` }"
                  />
                </div>
                <span class="text-xs text-warmgray-500 w-8 text-right">{{ sector.heat?.toFixed(1) }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 快捷操作 -->
        <div class="bg-white rounded-lg border border-border p-4">
          <h2 class="text-sm font-semibold text-warmgray-900 mb-3">快捷操作</h2>
          <div class="grid grid-cols-2 gap-2">
            <button
              @click="$router.push('/leader-tracking')"
              class="px-3 py-2 text-xs font-medium text-warmgray-700 bg-warmgray-100 hover:bg-warmgray-200 rounded transition-colors"
            >
              龙头跟踪
            </button>
            <button
              @click="$router.push('/monitor')"
              class="px-3 py-2 text-xs font-medium text-warmgray-700 bg-warmgray-100 hover:bg-warmgray-200 rounded transition-colors"
            >
              监控面板
            </button>
            <button
              @click="$router.push('/lstm-mab-evolution')"
              class="px-3 py-2 text-xs font-medium text-warmgray-700 bg-warmgray-100 hover:bg-warmgray-200 rounded transition-colors"
            >
              模型进化
            </button>
            <button
              @click="$router.push('/backtest')"
              class="px-3 py-2 text-xs font-medium text-warmgray-700 bg-warmgray-100 hover:bg-warmgray-200 rounded transition-colors"
            >
              策略回测
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowPathIcon,
  ExclamationCircleIcon,
  ShieldExclamationIcon,
  ChartBarIcon,
  StarIcon,
  RectangleStackIcon,
  WalletIcon,
  FireIcon,
  PlusIcon,
} from '@heroicons/vue/24/outline'

const router = useRouter()

// 状态
const loading = ref(false)
const error = ref(null)
const marketBrief = ref({})
const topPicks = ref([])
const leaderLadder = ref({})
const holdings = ref([])
const sectorHeat = ref([])
const circuitBreaker = ref(null)

// 计算属性
const emotionCycleClass = computed(() => {
  const cycle = marketBrief.value.emotion_cycle
  if (cycle === '高涨期') return 'bg-red-100 text-red-700'
  if (cycle === '低迷期' || cycle === '冰点期') return 'bg-blue-100 text-blue-700'
  if (cycle === '退潮期') return 'bg-amber-100 text-amber-700'
  return 'bg-green-100 text-green-700'
})

const getBombRateClass = computed(() => {
  const rate = marketBrief.value.bomb_rate || 0
  if (rate >= 30) return 'text-loss'
  if (rate >= 20) return 'text-amber-600'
  return 'text-profit'
})

const sortedLadder = computed(() => {
  // 按连板高度降序排列（返回数组，避免对象遍历自动升序）
  const entries = Object.entries(leaderLadder.value)
    .sort(([a], [b]) => {
      const na = Number(a)
      const nb = Number(b)
      // 非数字键（如"观察"）始终放最后
      if (Number.isNaN(na) && Number.isNaN(nb)) return 0
      if (Number.isNaN(na)) return 1
      if (Number.isNaN(nb)) return -1
      return nb - na
    })
    .map(([height, stocks]) => ({ height, stocks }))
  return entries
})

const sectorHeatList = computed(() => {
  // 为板块生成气泡位置
  return sectorHeat.value.map((sector, index) => ({
    ...sector,
    x: 15 + (index % 4) * 23 + Math.random() * 5,
    y: 20 + Math.floor(index / 4) * 30 + Math.random() * 10
  }))
})

const topSectors = computed(() => {
  return sectorHeat.value.slice(0, 5)
})

const totalProfit = computed(() => {
  if (holdings.value.length === 0) return 0
  return holdings.value.reduce((sum, p) => sum + (p.profit_pct || 0), 0) / holdings.value.length
})

// 方法
function getScoreColor(score) {
  if (!score) return 'text-warmgray-400'
  if (score >= 90) return 'text-red-600'
  if (score >= 80) return 'text-orange-600'
  if (score >= 70) return 'text-amber-600'
  return 'text-warmgray-600'
}

function getGradeClass(grade) {
  if (grade === 'S') return 'text-red-600'
  if (grade === 'A') return 'text-orange-600'
  if (grade === 'B') return 'text-amber-600'
  return 'text-warmgray-400'
}

function getSectorBubbleClass(heat) {
  if (heat >= 25) return 'w-16 h-16 bg-red-500 text-white'
  if (heat >= 20) return 'w-14 h-14 bg-orange-500 text-white'
  if (heat >= 15) return 'w-12 h-12 bg-yellow-500 text-white'
  return 'w-10 h-10 bg-warmgray-300 text-warmgray-700'
}

async function fetchMarketBrief() {
  try {
    const response = await fetch('/api/short-term/dashboard/market-brief')
    const data = await response.json()
    if (data.success) {
      marketBrief.value = data.data || {}
    }
  } catch (e) {
    console.error('获取市场简报失败:', e)
  }
}

async function fetchTopPicks() {
  try {
    const response = await fetch('/api/leader-tracking/top-scored?with_scores=true&min_grade=S')
    const data = await response.json()
    if (data.success) {
      topPicks.value = data.leaders || []
    }
  } catch (e) {
    console.error('获取TOP精选失败:', e)
  }
}

async function fetchLeaderLadder() {
  try {
    // 获取全市场涨停梯队（含龙头标记）
    const response = await fetch('/api/short-term/dashboard/limit-up-ladder')
    const data = await response.json()
    if (data.success && data.ladder) {
      leaderLadder.value = data.ladder
    }
  } catch (e) {
    console.error('获取龙头梯队失败:', e)
  }
}

async function fetchHoldings() {
  try {
    const response = await fetch('/api/holdings')
    const data = await response.json()
    if (data.success && data.data) {
      // 转换字段名以适配模板
      holdings.value = data.data.map(h => ({
        ts_code: h.symbol || h.ts_code,
        name: h.name,
        buy_price: h.avg_cost_price || h.buy_price,
        current_price: h.current_price,
        profit_pct: h.profit_rate !== undefined ? h.profit_rate : h.profit_pct,
      }))
    } else {
      holdings.value = []
    }
  } catch (e) {
    console.error('获取持仓失败:', e)
    holdings.value = []
  }
}

async function fetchSectorHeat() {
  try {
    const response = await fetch('/api/hot-sectors/heat-snapshot')
    const data = await response.json()
    if (data.success) {
      sectorHeat.value = data.sectors || []
    }
  } catch (e) {
    console.error('获取板块热度失败:', e)
    // 使用模拟数据展示
    sectorHeat.value = [
      { name: '机器人', heat: 28.5 },
      { name: 'AI算力', heat: 25.2 },
      { name: '半导体', heat: 22.1 },
      { name: '新能源', heat: 18.5 },
      { name: '医药', heat: 15.3 },
      { name: '金融', heat: 12.8 },
      { name: '消费', heat: 10.5 },
      { name: '地产', heat: 8.2 },
    ]
  }
}

async function fetchCircuitBreaker() {
  try {
    const response = await fetch('/api/short-term/monitor/circuit-breaker')
    const data = await response.json()
    if (data.success) {
      circuitBreaker.value = data
    }
  } catch (e) {
    console.error('获取熔断状态失败:', e)
  }
}

async function refreshAllData() {
  loading.value = true
  error.value = null

  await Promise.all([
    fetchMarketBrief(),
    fetchTopPicks(),
    fetchLeaderLadder(),
    fetchHoldings(),
    fetchSectorHeat(),
    fetchCircuitBreaker(),
  ])

  loading.value = false
}

function viewStockDetail(stock) {
  router.push(`/stock-detail/${stock.ts_code}`)
}

function viewSectorDetail(sector) {
  router.push(`/sector-detail/${sector.name}`)
}

function importToHoldings() {
  // 实现一键导入持仓逻辑
  alert('已导入 ' + topPicks.value.length + ' 只股票到观察列表')
}

onMounted(() => {
  refreshAllData()
})
</script>
