<template>
  <div class="container mx-auto px-4 py-6">
    <!-- 页面标题 -->
    <div class="mb-6">
      <h1 class="text-2xl font-bold text-gray-800 mb-2">60日新高</h1>
      <p class="text-sm text-gray-500">
        计算指定日期第一次突破60日新高的股票
      </p>
    </div>

    <!-- 操作栏 -->
    <div class="mb-4 bg-white rounded-lg shadow p-4">
      <div class="flex items-center justify-between mb-4">
        <div class="flex items-center gap-4">
          <div class="flex items-center gap-2">
            <label class="text-sm text-gray-600 font-medium">股票日期：</label>
            <input
              v-model="stockDate"
              type="date"
              class="px-3 py-2 border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
        </div>

        <div class="flex items-center gap-2">
          <button
            @click="queryFromDatabase"
            :disabled="loading || querying"
            class="px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed text-sm flex items-center gap-2"
          >
            <svg v-if="!querying" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <span v-else class="animate-spin">⟳</span>
            {{ querying ? '查询中...' : '查询' }}
          </button>
          <button
            @click="calculate"
            :disabled="loading || querying"
            class="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed text-sm flex items-center gap-2"
          >
            <svg v-if="!loading" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
            <span v-else class="animate-spin">⟳</span>
            {{ loading ? '计算中...' : '计算' }}
          </button>
          <button
            @click="addAllToWatchlist"
            :disabled="loading || querying || addingToWatchlist || eligibleStocksCount === 0"
            class="px-6 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:bg-gray-400 disabled:cursor-not-allowed text-sm flex items-center gap-2"
            :title="eligibleStocksCount === 0 ? '没有60日新高的股票' : `将 ${eligibleStocksCount} 只股票加入跟踪池`"
          >
            <svg v-if="!addingToWatchlist" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
            </svg>
            <span v-else class="animate-spin">⟳</span>
            {{ addingToWatchlist ? '添加中...' : `一键加入跟踪池${eligibleStocksCount > 0 ? ` (${eligibleStocksCount})` : ''}` }}
          </button>
        </div>
      </div>

      <div v-if="dataSource" class="text-xs text-gray-500">
        <span>数据来源：</span>
        <span :class="dataSource === 'calculated' ? 'text-blue-600 font-semibold' : 'text-green-600 font-semibold'">
          {{ dataSource === 'calculated' ? '实时计算' : '数据库查询' }}
        </span>
      </div>
    </div>

    <!-- 提示信息 -->
    <div v-if="stockDate && !loading" class="mb-4 bg-blue-50 border border-blue-200 rounded-lg p-3">
      <p class="text-sm text-blue-800">
        <span class="font-semibold">计算说明：</span>
        计算 <span class="font-semibold">{{ stockDate }}</span> 全部股票中，第一次突破60日新高的股票
      </p>
    </div>

    <!-- 数据表格 -->
    <div class="bg-white rounded-lg shadow overflow-hidden">
      <div class="overflow-x-auto">
        <table class="min-w-full divide-y divide-gray-200">
          <thead class="bg-gray-50">
            <tr>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">代码</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">名称</th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">今日收盘</th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">今日涨幅</th>
              <th
                class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100 select-none"
                @click="sortByChange5d"
              >
                <div class="flex items-center justify-end gap-1">
                  <span>近5日涨幅</span>
                  <svg
                    v-if="sortField === 'change_5d'"
                    class="w-4 h-4"
                    :class="sortOrder === 'asc' ? 'text-blue-600' : 'text-blue-600'"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      v-if="sortOrder === 'asc'"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      stroke-width="2"
                      d="M5 15l7-7 7 7"
                    />
                    <path
                      v-else
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      stroke-width="2"
                      d="M19 9l-7 7-7-7"
                    />
                  </svg>
                  <svg
                    v-else
                    class="w-4 h-4 text-gray-400"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4" />
                  </svg>
                </div>
              </th>
              <th
                class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100 select-none"
                @click="sortByChange10d"
              >
                <div class="flex items-center justify-end gap-1">
                  <span>近10日涨幅</span>
                  <svg
                    v-if="sortField === 'change_10d'"
                    class="w-4 h-4"
                    :class="sortOrder === 'asc' ? 'text-blue-600' : 'text-blue-600'"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      v-if="sortOrder === 'asc'"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      stroke-width="2"
                      d="M5 15l7-7 7 7"
                    />
                    <path
                      v-else
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      stroke-width="2"
                      d="M19 9l-7 7-7-7"
                    />
                  </svg>
                  <svg
                    v-else
                    class="w-4 h-4 text-gray-400"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4" />
                  </svg>
                </div>
              </th>
              <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">是否60日新高</th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">成交额</th>
              <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">新高日期</th>
            </tr>
          </thead>
          <tbody class="bg-white divide-y divide-gray-200">
            <tr
              v-for="item in sortedData"
              :key="item.ts_code"
              class="hover:bg-gray-50 transition-colors"
            >
              <td class="px-4 py-3 whitespace-nowrap">
                <span class="text-sm font-mono text-gray-900">{{ item.ts_code }}</span>
              </td>
              <td class="px-4 py-3 whitespace-nowrap">
                <span class="text-sm text-gray-900 font-medium">{{ item.name }}</span>
              </td>
              <td class="px-4 py-3 whitespace-nowrap text-right">
                <span class="text-sm text-gray-900">{{ item.today_close ? item.today_close.toFixed(2) : '-' }}</span>
              </td>
              <td class="px-4 py-3 whitespace-nowrap text-right">
                <span
                  v-if="item.change_pct !== null && item.change_pct !== undefined"
                  :class="[
                    'text-sm font-semibold',
                    item.change_pct >= 0 ? 'text-red-600' : 'text-green-600'
                  ]"
                >
                  {{ formatPercent(item.change_pct) }}
                </span>
                <span v-else class="text-sm text-gray-400">-</span>
              </td>
              <td class="px-4 py-3 whitespace-nowrap text-right">
                <span
                  v-if="item.change_5d !== null && item.change_5d !== undefined"
                  :class="[
                    'text-sm font-semibold',
                    item.change_5d >= 0 ? 'text-red-600' : 'text-green-600'
                  ]"
                >
                  {{ formatPercent(item.change_5d) }}
                </span>
                <span v-else class="text-sm text-gray-400">-</span>
              </td>
              <td class="px-4 py-3 whitespace-nowrap text-right">
                <span
                  v-if="item.change_10d !== null && item.change_10d !== undefined"
                  :class="[
                    'text-sm font-semibold',
                    item.change_10d >= 0 ? 'text-red-600' : 'text-green-600'
                  ]"
                >
                  {{ formatPercent(item.change_10d) }}
                </span>
                <span v-else class="text-sm text-gray-400">-</span>
              </td>
              <td class="px-4 py-3 whitespace-nowrap text-center">
                <span
                  v-if="item.is_60d_high === true"
                  class="px-2 py-1 bg-green-100 text-green-800 rounded text-xs font-semibold"
                >
                  是
                </span>
                <span
                  v-else-if="item.is_60d_high === false"
                  class="px-2 py-1 bg-gray-100 text-gray-600 rounded text-xs"
                >
                  否
                </span>
                <span v-else class="text-sm text-gray-400">-</span>
              </td>
              <td class="px-4 py-3 whitespace-nowrap text-right">
                <span class="text-sm text-gray-900">{{ formatAmount(item.amount) }}</span>
              </td>
              <td class="px-4 py-3 whitespace-nowrap text-center">
                <div class="text-xs text-gray-600">
                  {{ formatDate(item.today_date) }}
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 空状态 -->
      <div v-if="!loading && !querying && sortedData.length === 0" class="text-center py-12">
        <p class="text-gray-500 mb-2">暂无数据</p>
        <p class="text-sm text-gray-400">
          <span v-if="dataSource === 'queried'">未找到该日期的数据，请先使用"计算"功能计算该日期的数据</span>
          <span v-else>点击"计算"按钮开始计算，或点击"查询"按钮查询历史数据</span>
        </p>
      </div>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading || querying" class="text-center py-12">
      <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      <p class="mt-2 text-gray-500">{{ loading ? '计算中...' : '查询中...' }}</p>
    </div>

    <!-- 统计信息 -->
    <div v-if="!loading && data.length > 0" class="mt-4 bg-white rounded-lg shadow p-4">
      <div class="flex items-center gap-6 text-sm">
        <div>
          <span class="text-gray-600">第一次突破60日新高：</span>
          <span class="font-semibold text-blue-600">{{ data.length }}</span>
          <span class="text-gray-500">只</span>
        </div>
        <div>
          <span class="text-gray-600">检查股票总数：</span>
          <span class="font-semibold text-gray-900">{{ popularityCount }}</span>
          <span class="text-gray-500">只</span>
        </div>
        <div>
          <span class="text-gray-600">股票日期：</span>
          <span class="font-semibold text-gray-900">{{ stockDate || '今天' }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

const loading = ref(false)
const querying = ref(false)
const addingToWatchlist = ref(false)
const data = ref([])
const stockDate = ref('')
const popularityCount = ref(0)
const dataSource = ref(null)

// 排序相关
const sortField = ref(null)
const sortOrder = ref('desc')

// 计算符合条件的股票数量（60日新高）
const eligibleStocksCount = computed(() => {
  if (!data.value || data.value.length === 0) {
    return 0
  }
  return data.value.filter(stock => stock.is_60d_high === true).length
})

// 格式化日期
function formatDate(dateStr) {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

// 格式化百分比
function formatPercent(value) {
  if (value === null || value === undefined) return '-'
  const num = parseFloat(value)
  const sign = num >= 0 ? '+' : ''
  return `${sign}${num.toFixed(2)}%`
}

// 格式化成交额（单位：万元）
function formatAmount(value) {
  if (value === null || value === undefined) return '-'
  const num = parseFloat(value)
  if (isNaN(num) || num === 0) return '-'

  if (num >= 100000000) {
    return (num / 100000000).toFixed(2) + '亿'
  }
  if (num >= 10000) {
    return (num / 10000).toFixed(2) + '万'
  }
  return num.toFixed(2)
}

// 排序功能
function sortByChange5d() {
  if (sortField.value === 'change_5d') {
    sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortField.value = 'change_5d'
    sortOrder.value = 'desc'
  }
}

function sortByChange10d() {
  if (sortField.value === 'change_10d') {
    sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortField.value = 'change_10d'
    sortOrder.value = 'desc'
  }
}

// 排序后的数据
const sortedData = computed(() => {
  if (!sortField.value) {
    return data.value
  }

  const sorted = [...data.value].sort((a, b) => {
    const aVal = a[sortField.value]
    const bVal = b[sortField.value]

    if (aVal === null || aVal === undefined) return 1
    if (bVal === null || bVal === undefined) return -1

    if (sortOrder.value === 'asc') {
      return aVal - bVal
    } else {
      return bVal - aVal
    }
  })

  return sorted
})

// 从数据库查询
async function queryFromDatabase(silent = false) {
  if (!stockDate.value) {
    if (!silent) {
      alert('请选择股票日期')
    }
    return
  }

  querying.value = true
  data.value = []
  dataSource.value = null

  try {
    const params = {
      trade_date: stockDate.value,
      is_first_60d_high: true
    }

    const response = await axios.get(`${API_BASE_URL}/api/startup/limit-up-today-60d-high/query`, { params })

    if (response.data.success) {
      const resultData = response.data.data || []
      if (resultData.length > 0) {
        data.value = resultData
        popularityCount.value = resultData.length
        dataSource.value = 'queried'
      } else {
        data.value = []
      }
    } else {
      console.error('查询失败:', response.data.message)
      if (!silent) {
        alert('查询失败: ' + (response.data.message || '未知错误'))
      }
      data.value = []
    }
  } catch (error) {
    console.error('查询失败:', error)
    const errorMsg = error.response?.data?.detail || error.response?.data?.message || error.message
    if (!silent) {
      if (errorMsg.includes('404') || errorMsg.includes('未找到')) {
        alert(`未找到 ${stockDate.value} 的数据，请先使用"计算"功能计算该日期的数据`)
      } else {
        alert('查询失败: ' + errorMsg)
      }
    }
    data.value = []
  } finally {
    querying.value = false
  }
}

// 计算
async function calculate(silent = false) {
  if (!stockDate.value) {
    if (!silent) {
      alert('请选择股票日期')
    }
    return
  }

  loading.value = true
  data.value = []
  dataSource.value = null

  try {
    const params = {
      trade_date: stockDate.value
    }

    const response = await axios.get(`${API_BASE_URL}/api/startup/limit-up-today-60d-high`, { params })

    if (response.data.success) {
      data.value = response.data.data || []
      popularityCount.value = response.data.popularity_count || 0
      dataSource.value = 'calculated'
    } else {
      console.error('计算失败:', response.data.message)
      if (!silent) {
        alert('计算失败: ' + (response.data.message || '未知错误'))
      }
      data.value = []
    }
  } catch (error) {
    console.error('计算失败:', error)
    if (!silent) {
      alert('计算失败: ' + (error.response?.data?.detail || error.message))
    }
    data.value = []
  } finally {
    loading.value = false
  }
}

// 一键加入跟踪池
async function addAllToWatchlist() {
  if (!data.value || data.value.length === 0) {
    alert('当前没有可添加的股票')
    return
  }

  const eligibleStocks = data.value.filter(stock => stock.is_60d_high === true)

  if (eligibleStocks.length === 0) {
    alert('当前没有60日新高的股票')
    return
  }

  if (!confirm(`确认要将 ${eligibleStocks.length} 只60日新高股票加入跟踪池吗？\n理由：60日新高`)) {
    return
  }

  addingToWatchlist.value = true
  let successCount = 0
  let failCount = 0
  const failMessages = []

  try {
    for (const stock of eligibleStocks) {
      try {
        const response = await axios.post(`${API_BASE_URL}/api/watchlist`, {
          ts_code: stock.ts_code,
          note: '60日新高'
        })

        if (response.data.success) {
          successCount++
        } else {
          failCount++
          if (!response.data.message || !response.data.message.includes('已在跟踪列表中')) {
            failMessages.push(`${stock.name || stock.ts_code}: ${response.data.message || '添加失败'}`)
          } else {
            successCount++
            failCount--
          }
        }
      } catch (error) {
        failCount++
        const errorMsg = error.response?.data?.detail || error.response?.data?.message || error.message
        if (errorMsg.includes('已在跟踪列表中')) {
          successCount++
          failCount--
        } else {
          failMessages.push(`${stock.name || stock.ts_code}: ${errorMsg}`)
        }
      }
    }

    let message = `添加完成！\n60日新高股票: ${eligibleStocks.length} 只\n成功: ${successCount} 只`
    if (failCount > 0) {
      message += `\n失败: ${failCount} 只`
      if (failMessages.length > 0) {
        message += `\n\n失败详情：\n${failMessages.slice(0, 5).join('\n')}`
        if (failMessages.length > 5) {
          message += `\n...还有 ${failMessages.length - 5} 条失败信息`
        }
      }
    }
    alert(message)
  } catch (error) {
    console.error('批量加入跟踪池失败:', error)
    alert('批量加入跟踪池失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    addingToWatchlist.value = false
  }
}

// 初始化：设置默认日期为今天，并自动查询今天的数据
onMounted(async () => {
  const today = new Date()
  const year = today.getFullYear()
  const month = String(today.getMonth() + 1).padStart(2, '0')
  const day = String(today.getDate()).padStart(2, '0')
  const todayStr = `${year}-${month}-${day}`

  stockDate.value = todayStr

  await queryFromDatabase(true, false)
})
</script>
