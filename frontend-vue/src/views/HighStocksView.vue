<template>
  <div class="p-8 space-y-6">
    <!-- 页面标题与操作 -->
    <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
      <div>
        <h1 class="text-2xl font-semibold text-gray-900 dark:text-gray-100 mb-2">新高监控</h1>
        <p class="text-sm text-gray-500 dark:text-gray-400">{{ currentStrategyDescription }}</p>
      </div>
      <div class="flex items-center gap-3">
        <button
          type="button"
          @click="cleanBroken"
          :disabled="cleaning || loading || stocks.length === 0"
          class="px-4 py-2 rounded-lg text-sm font-medium bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200 hover:bg-amber-200 dark:hover:bg-amber-800/50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {{ cleaning ? '清理中...' : '一键清理破线' }}
        </button>
        <router-link
          to="/high-stocks-broken"
          class="px-4 py-2 rounded-lg text-sm font-medium border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
        >
          已破线股票
        </router-link>
      </div>
    </div>

    <!-- Tab切换 -->
    <div class="border-b border-gray-200">
      <nav class="-mb-px flex space-x-8">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          @click="activeTab = tab.key"
          :class="[
            activeTab === tab.key
              ? 'border-indigo-500 text-indigo-600'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300',
            'whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm'
          ]"
        >
          {{ tab.label }}
          <span v-if="activeTab === tab.key" class="ml-2 bg-indigo-100 text-indigo-600 py-0.5 px-2 rounded-full text-xs">
            {{ stocks.length }}
          </span>
        </button>
      </nav>
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
      <p>{{ currentStrategyLabel }}股票池为空，请先在数据管理页面刷新股票池</p>
    </div>

    <div v-else class="bg-white rounded-lg border border-gray-200 overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full">
          <thead class="bg-gray-50">
            <tr>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">代码</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">名称</th>
              <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('first_entry_date')">
                首次入选 {{ sortField === 'first_entry_date' ? (sortOrder === 'desc' ? '↓' : '↑') : '' }}
              </th>
              <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('frequency_10d')">
                10日出现 {{ sortField === 'frequency_10d' ? (sortOrder === 'desc' ? '↓' : '↑') : '' }}
              </th>
              <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('frequency_20d')">
                20日出现 {{ sortField === 'frequency_20d' ? (sortOrder === 'desc' ? '↓' : '↑') : '' }}
              </th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('industry')">
                行业 {{ sortField === 'industry' ? (sortOrder === 'desc' ? '↓' : '↑') : '' }}
              </th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">价格</th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('change_pct')">
                涨跌幅 {{ sortField === 'change_pct' ? (sortOrder === 'desc' ? '↓' : '↑') : '' }}
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
              <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">10日线</th>
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
              <td class="px-4 py-3 text-center text-xs text-gray-600">
                <span v-if="stock.first_entry_date" class="text-indigo-600 font-medium">
                  {{ stock.first_entry_date }}
                </span>
                <span v-else class="text-gray-400">--</span>
              </td>
              <td class="px-4 py-3 text-center">
                <span 
                  v-if="getFrequency10d(stock.ts_code) >= 3" 
                  class="px-2 py-1 bg-red-100 text-red-700 rounded text-xs font-bold"
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
                >
                  {{ getFrequency20d(stock.ts_code) }}次 ⚡
                </span>
                <span v-else-if="getFrequency20d(stock.ts_code) > 0" class="text-xs text-gray-500">
                  {{ getFrequency20d(stock.ts_code) }}次
                </span>
                <span v-else class="text-xs text-gray-400">--</span>
              </td>
              <td class="px-4 py-3 text-sm text-gray-600">{{ stock.industry || '--' }}</td>
              <td class="px-4 py-3 text-sm text-right font-medium">{{ stock.price?.toFixed(2) || '--' }}</td>
              <td class="px-4 py-3 text-sm text-right" :class="stock.change_pct >= 0 ? 'text-red-600' : 'text-green-600'">
                {{ stock.change_pct >= 0 ? '+' : '' }}{{ stock.change_pct?.toFixed(2) || '--' }}%
              </td>
              <td class="px-4 py-3 text-sm text-right" :class="stock.pct_10d >= 0 ? 'text-red-600' : 'text-green-600'">
                {{ stock.pct_10d !== null ? (stock.pct_10d >= 0 ? '+' : '') + stock.pct_10d.toFixed(2) : '--' }}
              </td>
              <td class="px-4 py-3 text-sm text-right" :class="stock.pct_20d >= 0 ? 'text-red-600' : 'text-green-600'">
                {{ stock.pct_20d !== null ? (stock.pct_20d >= 0 ? '+' : '') + stock.pct_20d.toFixed(2) : '--' }}
              </td>
              <td class="px-4 py-3 text-sm text-right" :class="stock.pct_60d >= 0 ? 'text-red-600' : 'text-green-600'">
                {{ stock.pct_60d !== null ? (stock.pct_60d >= 0 ? '+' : '') + stock.pct_60d.toFixed(2) : '--' }}
              </td>
              <td class="px-4 py-3 text-sm text-right" :class="stock.pct_120d >= 0 ? 'text-red-600' : 'text-green-600'">
                {{ stock.pct_120d !== null ? (stock.pct_120d >= 0 ? '+' : '') + stock.pct_120d.toFixed(2) : '--' }}
              </td>
              <td class="px-4 py-3 text-sm text-right text-gray-600">
                {{ stock.amount ? (stock.amount / 100000000).toFixed(2) + '亿' : '--' }}
              </td>
              <td class="px-4 py-3 text-center">
                <span v-if="stock.below_ma10" class="text-red-600 text-xs">已破线</span>
                <span v-else class="text-green-600 text-xs">正常</span>
              </td>
              <td class="px-4 py-3 text-center">
                <div class="flex items-center justify-center gap-2">
                  <button 
                    @click="addToWatchlist(stock)"
                    class="text-xs text-blue-600 hover:text-blue-800"
                  >
                    加入跟踪池
                  </button>
                  <button 
                    @click="deleteStock(stock.ts_code)"
                    class="text-xs text-red-600 hover:text-red-800"
                  >
                    删除
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import axios from 'axios'
import StatCard from '../components/ui/StatCard.vue'

// Tab配置
const tabs = [
  { key: 'high_180d', label: '180日新高', api: '/api/stock-universe/high_180d/realtime' }
]

// 当前激活的Tab
const activeTab = ref('high_180d')

// 数据状态
const stocks = ref([])
const frequencyMap = ref({})
const loading = ref(false)
const cleaning = ref(false)

// 排序状态
const sortField = ref('change_pct')
const sortOrder = ref('desc')

// 当前策略信息
const currentStrategyLabel = computed(() => {
  return tabs.find(t => t.key === activeTab.value)?.label || '新高'
})

const currentStrategyDescription = computed(() => {
  return '主板强势股（已是180日新高，股价>5元，成交额>10亿，180日涨幅<60%）'
})

// 统计数据
const upCount = computed(() => stocks.value.filter(s => s.change_pct > 0).length)
const downCount = computed(() => stocks.value.filter(s => s.change_pct < 0).length)
const strong20dCount = computed(() => stocks.value.filter(s => s.pct_20d > 10).length)
const strong60dCount = computed(() => stocks.value.filter(s => s.pct_60d > 20).length)
const strong120dCount = computed(() => stocks.value.filter(s => s.pct_120d > 30).length)

// 排序后的股票列表
const sortedStocks = computed(() => {
  if (!stocks.value.length) return []
  
  return [...stocks.value].sort((a, b) => {
    let aVal = a[sortField.value]
    let bVal = b[sortField.value]
    
    if (aVal == null && bVal == null) return 0
    if (aVal == null) return 1
    if (bVal == null) return -1
    
    if (typeof aVal === 'string') {
      return sortOrder.value === 'desc' 
        ? bVal.localeCompare(aVal)
        : aVal.localeCompare(bVal)
    }
    
    return sortOrder.value === 'desc' ? bVal - aVal : aVal - bVal
  })
})

// 获取频率
const getFrequency10d = (tsCode) => frequencyMap.value[tsCode]?.frequency_10d || 0
const getFrequency20d = (tsCode) => frequencyMap.value[tsCode]?.frequency_20d || 0

// 获取实时数据
const fetchRealtimeData = async () => {
  loading.value = true
  
  try {
    const currentTab = tabs.find(t => t.key === activeTab.value)
    
    // 构建API参数
    const params = {}
    
    const response = await axios.get(currentTab.api, { params })
    
    if (response.data.success) {
      stocks.value = response.data.data.map(stock => ({
        ...stock,
        code: stock.ts_code.split('.')[0]
      }))
      
      // 获取频率数据
      await fetchFrequencyData()
    }
  } catch (error) {
    console.error('获取实时数据失败:', error)
  } finally {
    loading.value = false
  }
}

// 获取频率数据
const fetchFrequencyData = async () => {
  try {
    const response = await axios.get(`/api/stock-universe/${activeTab.value}/frequency`)
    if (response.data.success) {
      frequencyMap.value = response.data.data
    }
  } catch (error) {
    console.error('获取频率数据失败:', error)
  }
}

// 加入跟踪池
const addToWatchlist = async (stock) => {
  try {
    const response = await axios.post('/api/watchlist', {
      ts_code: stock.ts_code,
      note: '180日新高'
    })
    
    if (response.data.success) {
      alert(`成功将 ${stock.name || stock.code} 加入跟踪池`)
    } else {
      alert(response.data.message || '加入跟踪池失败')
    }
  } catch (error) {
    console.error('加入跟踪池失败:', error)
    const errorMsg = error.response?.data?.detail || error.response?.data?.message || error.message
    alert('加入跟踪池失败: ' + errorMsg)
  }
}

// 一键清理破线
const cleanBroken = async () => {
  if (!confirm('确定将当前列表中所有「已破10日线」的股票移出监控并加入已破线列表吗？')) return
  cleaning.value = true
  try {
    const API_BASE = import.meta.env.VITE_API_BASE_URL || ''
    const res = await axios.post(`${API_BASE}/api/stock-universe/high_180d/clean_broken`)
    if (res.data?.success) {
      const n = res.data.count ?? 0
      alert(n > 0 ? `已清理 ${n} 只破线股票，可在「已破线股票」页查看。` : res.data.message || '当前无破线股票')
      await fetchRealtimeData()
    } else {
      alert(res.data?.message || '清理失败')
    }
  } catch (e) {
    alert('清理失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    cleaning.value = false
  }
}

// 删除股票
const deleteStock = async (tsCode) => {
  if (!confirm(`确定要删除 ${tsCode} 吗？`)) return
  
  try {
    const today = new Date().toISOString().split('T')[0]
    const response = await axios.delete('/api/stock-universe/remove_stock', {
      params: {
        universe_type: activeTab.value,
        ts_code: tsCode,
        date: today
      }
    })
    
    if (response.data.success) {
      alert('删除成功')
      await fetchRealtimeData()
    }
  } catch (error) {
    console.error('删除失败:', error)
    alert('删除失败: ' + error.message)
  }
}

// 排序
const sortBy = (field) => {
  if (sortField.value === field) {
    sortOrder.value = sortOrder.value === 'desc' ? 'asc' : 'desc'
  } else {
    sortField.value = field
    sortOrder.value = 'desc'
  }
}

// 监听Tab切换
watch(activeTab, () => {
  fetchRealtimeData()
})

// 生命周期
onMounted(() => {
  fetchRealtimeData()
})
</script>

