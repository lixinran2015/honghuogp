<template>
  <div class="p-8 space-y-8">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-semibold text-gray-900 mb-2">180日新高股票</h1>
        <p class="text-sm text-gray-500">主板强势股（已是180日新高，股价>5元，成交额>10亿，180日涨幅<60%）</p>
      </div>
      <div class="flex items-center gap-2">
        <Button size="sm" :variant="autoRefresh ? 'primary' : 'secondary'" @click="toggleAutoRefresh">
          {{ autoRefresh ? '⏸ 暂停刷新' : '▶ 开启刷新' }}
        </Button>
        <Button size="sm" variant="secondary" @click="fetchRealtimeData" :disabled="loading">
          {{ loading ? '加载中...' : '刷新' }}
        </Button>
      </div>
    </div>

    <!-- 统计信息 -->
    <div class="grid grid-cols-6 gap-4">
      <StatCard label="股票数量" :value="stocks.length" />
      <StatCard label="上涨数量" :value="upCount" :change="upCount" />
      <StatCard label="下跌数量" :value="downCount" :change="-downCount" />
      <StatCard label="20日涨幅>10%" :value="strong20dCount" :change="strong20dCount" />
      <StatCard label="60日涨幅>20%" :value="strong60dCount" :change="strong60dCount" />
      <StatCard label="120日涨幅>30%" :value="strong120dCount" :change="strong120dCount" />
    </div>

    <!-- 股票列表 -->
    <div v-if="loading && stocks.length === 0" class="py-12 text-center text-gray-500">
      <p>加载中...</p>
    </div>

    <div v-else-if="stocks.length === 0" class="py-12 text-center text-gray-500">
      <p>180日高点股票池为空，请先在数据管理页面刷新股票池</p>
    </div>

    <div v-else class="bg-white rounded-lg border border-gray-200 overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full">
          <thead class="bg-gray-50">
            <tr>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">代码</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">名称</th>
              <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('frequency_10d')">
                10日出现 {{ sortField === 'frequency_10d' ? (sortOrder === 'desc' ? '↓' : '↑') : '' }}
              </th>
              <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('frequency_20d')">
                20日出现 {{ sortField === 'frequency_20d' ? (sortOrder === 'desc' ? '↓' : '↑') : '' }}
              </th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('industry')">
                行业 {{ sortField === 'industry' ? (sortOrder === 'desc' ? '↓' : '↑') : '' }}
              </th>
              <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">当天分时</th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">价格</th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('change_pct')">
                涨跌幅 ↓ {{ sortField === 'change_pct' ? (sortOrder === 'desc' ? '↓' : '↑') : '' }}
              </th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('pct_10d')">
                10日涨幅(%) {{ sortField === 'pct_10d' ? (sortOrder === 'desc' ? '↓' : '↑') : '' }}
              </th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('pct_20d')">
                20日涨幅(%) {{ sortField === 'pct_20d' ? (sortOrder === 'desc' ? '↓' : '↑') : '' }}
              </th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('pct_60d')">
                60日涨幅(%) {{ sortField === 'pct_60d' ? (sortOrder === 'desc' ? '↓' : '↑') : '' }}
              </th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('pct_120d')">
                120日涨幅(%) {{ sortField === 'pct_120d' ? (sortOrder === 'desc' ? '↓' : '↑') : '' }}
              </th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('amount')">
                成交额 {{ sortField === 'amount' ? (sortOrder === 'desc' ? '↓' : '↑') : '' }}
              </th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('turnover_rate')">
                换手率 {{ sortField === 'turnover_rate' ? (sortOrder === 'desc' ? '↓' : '↑') : '' }}
              </th>
              <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">10日线</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">备注</th>
              <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">操作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-200">
            <tr 
              v-for="stock in sortedStocks" 
              :key="stock.ts_code"
              class="hover:bg-gray-50"
            >
              <td class="px-4 py-3 text-sm font-medium text-gray-900">{{ stock.code }}</td>
              <td class="px-4 py-3 text-sm text-gray-700">{{ stock.name || '--' }}</td>
              <td class="px-4 py-3 text-center">
                <span 
                  v-if="getFrequency10d(stock.ts_code) >= 3" 
                  class="px-2 py-1 bg-red-100 text-red-700 rounded text-xs font-bold"
                  :title="`近10日出现${getFrequency10d(stock.ts_code)}次`"
                >
                  {{ getFrequency10d(stock.ts_code) }}次 🔥
                </span>
                <span v-else-if="getFrequency10d(stock.ts_code) > 0" class="text-xs text-gray-500">
                  {{ getFrequency10d(stock.ts_code) }}次
                </span>
                <span v-else class="text-xs text-gray-400">--</span>
              </td>
              <td class="px-4 py-3 text-center">
                <span 
                  v-if="getFrequency20d(stock.ts_code) >= 5" 
                  class="px-2 py-1 bg-orange-100 text-orange-700 rounded text-xs font-bold"
                  :title="`近20日出现${getFrequency20d(stock.ts_code)}次`"
                >
                  {{ getFrequency20d(stock.ts_code) }}次 🔥
                </span>
                <span v-else-if="getFrequency20d(stock.ts_code) > 0" class="text-xs text-gray-500">
                  {{ getFrequency20d(stock.ts_code) }}次
                </span>
                <span v-else class="text-xs text-gray-400">--</span>
              </td>
              <td class="px-4 py-3 text-xs text-gray-600">{{ stock.industry || '--' }}</td>
              <td class="px-4 py-3">
                <div v-if="stock.chartLoading" class="text-xs text-gray-400">加载中...</div>
                <div v-else-if="!stock.kline || stock.kline.length === 0" class="text-xs text-gray-400">
                  {{ stock.kline_error || '暂无分时数据' }}
                </div>
                <MiniChart v-else :data="stock.kline" :trend="stock.change_pct >= 0" />
              </td>
              <td class="px-4 py-3 text-sm text-right font-medium">¥{{ formatPrice(stock.price) }}</td>
              <td class="px-4 py-3 text-sm text-right font-semibold" :class="getChangeClass(stock.change_pct)">
                {{ formatChange(stock.change_pct) }}%
              </td>
              <td class="px-4 py-3 text-sm text-right font-medium" :class="getChangeClass(stock.pct_10d)">
                {{ stock.pct_10d !== null && stock.pct_10d !== undefined ? formatChange(stock.pct_10d) + '%' : '--' }}
              </td>
              <td class="px-4 py-3 text-sm text-right font-medium" :class="getChangeClass(stock.pct_20d)">
                {{ stock.pct_20d !== null && stock.pct_20d !== undefined ? formatChange(stock.pct_20d) + '%' : '--' }}
              </td>
              <td class="px-4 py-3 text-sm text-right font-medium" :class="getChangeClass(stock.pct_60d)">
                {{ stock.pct_60d !== null && stock.pct_60d !== undefined ? formatChange(stock.pct_60d) + '%' : '--' }}
              </td>
              <td class="px-4 py-3 text-sm text-right font-medium" :class="getChangeClass(stock.pct_120d)">
                {{ stock.pct_120d !== null && stock.pct_120d !== undefined ? formatChange(stock.pct_120d) + '%' : '--' }}
              </td>
              <td class="px-4 py-3 text-sm text-right text-gray-600">{{ formatAmount(stock.amount) }}</td>
              <td class="px-4 py-3 text-sm text-right text-gray-600">{{ formatPercent(stock.turnover_rate) }}%</td>
              <td class="px-4 py-3 text-sm text-center">
                <span v-if="stock.below_ma10" class="text-green-600">破线</span>
                <span v-else class="text-red-600">站上</span>
              </td>
              <td class="px-4 py-3 text-sm text-gray-500">
                {{ stock.note || '--' }}
              </td>
              <td class="px-4 py-3 text-center">
                <button
                  @click="removeFromUniverse(stock.ts_code)"
                  class="text-red-500 hover:text-red-700 text-sm"
                  title="从股票池中移除"
                >
                  删除
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 最后更新时间 -->
    <div class="text-center text-sm text-gray-400">
      最后更新: {{ lastUpdate || '--' }}
      <span v-if="autoRefresh && isTradingTime()" class="ml-2 text-green-500">(交易时间，每10秒自动刷新)</span>
      <span v-else-if="autoRefresh" class="ml-2 text-yellow-500">(非交易时间，暂停刷新)</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import Card from '../components/ui/Card.vue'
import Button from '../components/ui/Button.vue'
import StatCard from '../components/ui/StatCard.vue'
import MiniChart from '../components/ui/MiniChart.vue'

// 状态
const stocks = ref([])
const loading = ref(false)
const autoRefresh = ref(true)
const lastUpdate = ref('')
const sortField = ref('change_pct')  // 排序字段
const sortOrder = ref('desc')  // 排序方向：desc降序，asc升序
const frequencyMap = ref({})  // 股票出现频次映射

let refreshInterval = null

// 计算属性
const upCount = computed(() => stocks.value.filter(s => s.change_pct > 0).length)
const downCount = computed(() => stocks.value.filter(s => s.change_pct < 0).length)
const belowMa10Count = computed(() => stocks.value.filter(s => s.below_ma10).length)
const strong20dCount = computed(() => stocks.value.filter(s => s.pct_20d && s.pct_20d > 10).length)
const strong60dCount = computed(() => stocks.value.filter(s => s.pct_60d && s.pct_60d > 20).length)
const strong120dCount = computed(() => stocks.value.filter(s => s.pct_120d && s.pct_120d > 30).length)

// 排序后的股票列表
const sortedStocks = computed(() => {
  if (!stocks.value.length) return []
  
  return [...stocks.value].sort((a, b) => {
    const field = sortField.value
    let aVal = a[field]
    let bVal = b[field]
    
    // 特殊处理：按出现频次排序
    if (field === 'frequency_10d') {
      aVal = getFrequency10d(a.ts_code)
      bVal = getFrequency10d(b.ts_code)
    }
    else if (field === 'frequency_20d') {
      aVal = getFrequency20d(a.ts_code)
      bVal = getFrequency20d(b.ts_code)
    }
    // 处理字符串类型字段（如行业）
    else if (field === 'industry') {
      aVal = aVal || ''
      bVal = bVal || ''
      if (sortOrder.value === 'desc') {
        return bVal.localeCompare(aVal, 'zh-CN')
      } else {
        return aVal.localeCompare(bVal, 'zh-CN')
      }
    }
    
    // 处理数值类型字段
    aVal = aVal ?? -Infinity
    bVal = bVal ?? -Infinity
    return sortOrder.value === 'desc' ? bVal - aVal : aVal - bVal
  })
})

// 获取实时数据
async function fetchRealtimeData() {
  loading.value = true
  try {
    // 并行获取实时数据和频次数据
    const [realtimeResponse, frequencyResponse] = await Promise.all([
      fetch('/api/stock-universe/high_180d/realtime'),
      fetch('/api/stock-universe/high_180d/frequency?days=10')
    ])
    
    const realtimeData = await realtimeResponse.json()
    const frequencyData = await frequencyResponse.json()
    
    if (realtimeData.success) {
      stocks.value = realtimeData.data || []
      lastUpdate.value = new Date().toLocaleTimeString()
    } else {
      console.error('获取数据失败:', realtimeData.message)
    }
    
    if (frequencyData.success) {
      frequencyMap.value = frequencyData.data || {}
    }
    
  } catch (error) {
    console.error('获取实时数据失败:', error)
  } finally {
    loading.value = false
  }
}

// 获取股票出现频次
function getFrequency10d(tsCode) {
  return frequencyMap.value[tsCode]?.frequency_10d || 0
}

function getFrequency20d(tsCode) {
  return frequencyMap.value[tsCode]?.frequency_20d || 0
}

// 从股票池中移除（真正删除）
async function removeFromUniverse(tsCode) {
  if (!confirm('确定要从180日高点股票池中永久移除该股票吗？\n\n注意：删除后需要重新刷新股票池才会再次出现。')) return
  
  try {
    const response = await fetch(`/api/stock-universe/remove_stock?universe_type=high_180d&ts_code=${encodeURIComponent(tsCode)}`, {
      method: 'DELETE'
    })
    const data = await response.json()
    
    if (data.success) {
      // 从前端列表中移除
      stocks.value = stocks.value.filter(s => s.ts_code !== tsCode)
      alert('✅ 已从股票池中永久删除')
    } else {
      alert('❌ ' + (data.message || '删除失败'))
    }
  } catch (error) {
    console.error('删除股票失败:', error)
    alert('❌ 删除失败: ' + error.message)
  }
}

// 切换自动刷新
function toggleAutoRefresh() {
  autoRefresh.value = !autoRefresh.value
  if (autoRefresh.value) {
    startAutoRefresh()
  } else {
    stopAutoRefresh()
  }
}

// 判断是否为交易时间
function isTradingTime() {
  const now = new Date()
  const day = now.getDay()
  if (day === 0 || day === 6) return false
  
  const hour = now.getHours()
  const minute = now.getMinutes()
  const time = hour * 100 + minute
  
  if ((time >= 915 && time <= 1130) || (time >= 1300 && time <= 1500)) {
    return true
  }
  return false
}

// 开始自动刷新
function startAutoRefresh() {
  if (refreshInterval) return
  refreshInterval = setInterval(() => {
    if (isTradingTime()) {
      fetchRealtimeData()
    }
  }, 10000)  // 每10秒检查并刷新
}

// 停止自动刷新
function stopAutoRefresh() {
  if (refreshInterval) {
    clearInterval(refreshInterval)
    refreshInterval = null
  }
}

// 排序函数
function sortBy(field) {
  if (sortField.value === field) {
    sortOrder.value = sortOrder.value === 'desc' ? 'asc' : 'desc'
  } else {
    sortField.value = field
    sortOrder.value = 'desc'
  }
}

// 格式化函数
function formatPrice(value) {
  return (value || 0).toFixed(2)
}

function formatChange(value) {
  const v = value || 0
  return v > 0 ? `+${v.toFixed(2)}` : v.toFixed(2)
}

function formatAmount(value) {
  const v = value || 0
  if (v >= 1e8) return (v / 1e8).toFixed(2) + '亿'
  if (v >= 1e4) return (v / 1e4).toFixed(2) + '万'
  return v.toFixed(2)
}

function formatPercent(value) {
  return (value || 0).toFixed(2)
}

function getChangeClass(value) {
  if (value > 0) return 'text-red-600'
  if (value < 0) return 'text-green-600'
  return 'text-gray-600'
}

// 生命周期
onMounted(async () => {
  await fetchRealtimeData()
  if (autoRefresh.value) {
    startAutoRefresh()
  }
})

onUnmounted(() => {
  stopAutoRefresh()
})
</script>

