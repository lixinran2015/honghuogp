<template>
  <div class="container mx-auto px-4 py-6">
    <!-- 页面标题 -->
    <div class="mb-6 flex items-start justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-800">人气榜2连板股票</h1>
        <p class="text-sm text-gray-500 mt-1">实时计算股吧人气榜中连续2天涨停的股票</p>
      </div>
      
      <!-- 操作按钮 -->
      <div class="flex items-center gap-3">
        <button
          @click="loadData"
          :disabled="loading"
          class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed text-sm flex items-center gap-2"
        >
          <svg v-if="!loading" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          <span v-else class="animate-spin">⟳</span>
          {{ loading ? '加载中...' : '刷新' }}
        </button>
      </div>
    </div>

    <!-- 统计信息 -->
    <div v-if="summary" class="mb-6 grid grid-cols-1 md:grid-cols-3 gap-4">
      <div class="bg-white rounded-lg shadow p-4">
        <div class="text-sm text-gray-600 mb-1">计算日期</div>
        <div class="text-lg font-semibold text-gray-800">{{ summary.query_date }}</div>
      </div>
      <div class="bg-white rounded-lg shadow p-4">
        <div class="text-sm text-gray-600 mb-1">人气榜股票数</div>
        <div class="text-lg font-semibold text-blue-600">{{ summary.popularity_count }} 只</div>
      </div>
      <div class="bg-white rounded-lg shadow p-4">
        <div class="text-sm text-gray-600 mb-1">2连板股票数</div>
        <div class="text-lg font-semibold text-red-600">{{ summary.count }} 只</div>
      </div>
    </div>

    <!-- 筛选器 -->
    <div class="mb-4 bg-white rounded-lg shadow p-4">
      <div class="flex items-center gap-4 flex-wrap">
        <div class="flex items-center gap-2">
          <label class="text-sm text-gray-600 font-medium">计算日期：</label>
          <input
            v-model="queryDate"
            type="date"
            class="px-3 py-2 border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            @change="loadData"
          />
          <button
            @click="setToday"
            class="px-3 py-2 text-sm text-blue-600 hover:text-blue-700 hover:bg-blue-50 rounded"
          >
            今天
          </button>
        </div>
        <div class="flex items-center gap-2">
          <label class="text-sm text-gray-600 font-medium">排名范围：</label>
          <input
            v-model.number="minRank"
            type="number"
            placeholder="最低排名"
            class="px-3 py-2 border border-gray-300 rounded text-sm w-24 focus:outline-none focus:ring-2 focus:ring-blue-500"
            @change="loadData"
          />
          <span class="text-gray-500">-</span>
          <input
            v-model.number="maxRank"
            type="number"
            placeholder="最高排名"
            class="px-3 py-2 border border-gray-300 rounded text-sm w-24 focus:outline-none focus:ring-2 focus:ring-blue-500"
            @change="loadData"
          />
        </div>
        <button
          @click="loadData"
          :disabled="loading"
          class="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed text-sm flex items-center gap-2 font-medium"
        >
          <svg v-if="!loading" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
          </svg>
          <span v-else class="animate-spin">⟳</span>
          {{ loading ? '计算中...' : '计算2连板' }}
        </button>
      </div>
      <div class="mt-3 text-xs text-gray-500">
        💡 提示：选择日期后点击"计算2连板"按钮，系统会实时计算该日期人气榜中连续2天涨停的股票。例如：选择 2024-12-08 可计算12月8日的2连板股票（基于12月6日和12月7日是否连续涨停）。
      </div>
    </div>

    <!-- 2连板股票表格 -->
    <div class="bg-white rounded-lg shadow overflow-hidden">
      <div class="overflow-x-auto">
        <table class="min-w-full divide-y divide-gray-200">
          <thead class="bg-gray-50">
            <tr>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">排名</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">变动</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">代码</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">名称</th>
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
              <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">涨停日期</th>
            </tr>
          </thead>
          <tbody class="bg-white divide-y divide-gray-200">
            <tr 
              v-for="item in sortedData" 
              :key="item.ts_code"
              class="hover:bg-gray-50 transition-colors"
            >
              <td class="px-4 py-3 whitespace-nowrap">
                <span class="text-sm font-semibold text-gray-900">{{ item.rank_position || '-' }}</span>
              </td>
              <td class="px-4 py-3 whitespace-nowrap">
                <span 
                  v-if="item.rank_change && item.rank_change > 0"
                  class="text-sm text-green-600 font-medium"
                >
                  ↑{{ item.rank_change }}
                </span>
                <span 
                  v-else-if="item.rank_change && item.rank_change < 0"
                  class="text-sm text-red-600 font-medium"
                >
                  ↓{{ Math.abs(item.rank_change) }}
                </span>
                <span v-else class="text-sm text-gray-400">-</span>
              </td>
              <td class="px-4 py-3 whitespace-nowrap">
                <span class="text-sm font-mono text-gray-900">{{ item.ts_code }}</span>
              </td>
              <td class="px-4 py-3 whitespace-nowrap">
                <span class="text-sm text-gray-900 font-medium">{{ item.name }}</span>
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
              <td class="px-4 py-3 whitespace-nowrap text-center">
                <div class="text-xs text-gray-600">
                  <div>{{ formatDate(item.day_before_date) }}</div>
                  <div class="text-gray-400">-</div>
                  <div>{{ formatDate(item.yesterday_date) }}</div>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      
      <!-- 空状态 -->
      <div v-if="!loading && sortedData.length === 0" class="text-center py-12">
        <p class="text-gray-500 mb-2">暂无2连板股票</p>
        <p class="text-sm text-gray-400">当前人气榜中没有连续2天涨停的股票</p>
        <button
          @click="loadData"
          class="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm"
        >
          重新加载
        </button>
      </div>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading" class="text-center py-12">
      <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      <p class="mt-2 text-gray-500">加载中...</p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

const loading = ref(false)
const data = ref([])
const summary = ref(null)
const queryDate = ref('')
const minRank = ref(null)
const maxRank = ref(100)

// 排序相关
const sortField = ref(null)  // 当前排序字段
const sortOrder = ref('desc')  // 排序方向：'asc' 升序, 'desc' 降序

// 格式化价格
function formatPrice(value) {
  if (value === null || value === undefined) return '-'
  return parseFloat(value).toFixed(2)
}

// 格式化百分比
function formatPercent(value) {
  if (value === null || value === undefined) return '-'
  const num = parseFloat(value)
  const sign = num >= 0 ? '+' : ''
  return `${sign}${num.toFixed(2)}%`
}

// 格式化日期
function formatDate(dateStr) {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${month}/${day}`
}

// 加载数据
async function loadData() {
  loading.value = true
  try {
    const params = {}
    if (queryDate.value) {
      params.trade_date = queryDate.value
    }
    if (minRank.value !== null && minRank.value !== '') {
      params.min_rank = minRank.value
    }
    if (maxRank.value !== null && maxRank.value !== '') {
      params.max_rank = maxRank.value
    }

    const response = await axios.get(`${API_BASE_URL}/api/startup/limit-up-2days`, { params })
    
    if (response.data.success) {
      data.value = response.data.data || []
      summary.value = {
        query_date: response.data.query_date,
        popularity_count: response.data.popularity_count || 0,
        count: response.data.count || 0
      }
    } else {
      console.error('加载失败:', response.data.message)
      data.value = []
      summary.value = null
    }
  } catch (error) {
    console.error('加载2连板股票失败:', error)
    data.value = []
    summary.value = null
  } finally {
    loading.value = false
  }
}

// 设置今天日期
function setToday() {
  const today = new Date()
  const year = today.getFullYear()
  const month = String(today.getMonth() + 1).padStart(2, '0')
  const day = String(today.getDate()).padStart(2, '0')
  queryDate.value = `${year}-${month}-${day}`
  loadData()
}

// 排序函数：按近10日涨幅排序
function sortByChange10d() {
  if (sortField.value === 'change_10d') {
    // 如果已经是按这个字段排序，切换排序方向
    sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    // 第一次点击，设置为降序（从高到低）
    sortField.value = 'change_10d'
    sortOrder.value = 'desc'
  }
}

// 计算排序后的数据
const sortedData = computed(() => {
  if (!sortField.value || !data.value.length) {
    return data.value
  }
  
  const sorted = [...data.value]
  
  if (sortField.value === 'change_10d') {
    sorted.sort((a, b) => {
      // 处理 null/undefined 值，放在最后
      const aVal = a.change_10d
      const bVal = b.change_10d
      
      if (aVal === null || aVal === undefined) return 1
      if (bVal === null || bVal === undefined) return -1
      
      if (sortOrder.value === 'asc') {
        return aVal - bVal
      } else {
        return bVal - aVal
      }
    })
  }
  
  return sorted
})

// 初始化：设置默认查询日期为今天
onMounted(() => {
  setToday()
})
</script>
