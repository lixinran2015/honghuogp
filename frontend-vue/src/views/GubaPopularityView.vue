<template>
  <div class="container mx-auto px-4 py-6">
    <!-- 页面标题 -->
    <div class="mb-6 flex items-start justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-800">人气排行榜</h1>
        <p class="text-sm text-gray-500 mt-1">东方财富股吧实时人气排名</p>
      </div>
      
      <!-- 操作按钮 -->
      <div class="flex items-center gap-3">
        <button
          @click="triggerCrawl"
          :disabled="crawling"
          class="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed text-sm flex items-center gap-2"
        >
          <svg v-if="!crawling" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
          <span v-else class="animate-spin">⟳</span>
          {{ crawling ? '爬取中...' : '重新爬取' }}
        </button>
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

    <!-- 数据信息 -->
    <div v-if="tradeDate" class="mb-4 text-sm text-gray-600">
      <span>数据日期：{{ tradeDate }}</span>
      <span class="ml-4">共 {{ data.length }} 条记录</span>
    </div>

    <!-- 排行榜表格 -->
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
                  class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                  @click="toggleSortFirstEntry">
                首次入榜
                <span v-if="sortFirstEntry === 'asc'" class="ml-1">↑</span>
                <span v-else-if="sortFirstEntry === 'desc'" class="ml-1">↓</span>
              </th>
              <th 
                  class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                  @click="toggleSortContinuousDays">
                持续天数
                <span v-if="sortContinuousDays === 'asc'" class="ml-1">↑</span>
                <span v-else-if="sortContinuousDays === 'desc'" class="ml-1">↓</span>
              </th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">最新价</th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">涨跌额</th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">涨跌幅</th>
            </tr>
          </thead>
          <tbody class="bg-white divide-y divide-gray-200">
            <tr 
              v-for="item in data" 
              :key="item.ts_code"
              class="hover:bg-gray-50 transition-colors"
            >
              <td class="px-4 py-3 whitespace-nowrap">
                <span class="text-sm font-semibold text-gray-900">{{ item.rank_position }}</span>
              </td>
              <td class="px-4 py-3 whitespace-nowrap">
                <span 
                  v-if="item.rank_change > 0"
                  class="text-sm text-green-600 font-medium"
                >
                  ↑{{ item.rank_change }}
                </span>
                <span 
                  v-else-if="item.rank_change < 0"
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
                <span class="text-sm text-gray-900">{{ item.stock_name }}</span>
              </td>
              <td class="px-4 py-3 whitespace-nowrap text-center">
                <span 
                  v-if="item.is_first_entry"
                  class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800"
                  :title="`首次入榜日期: ${item.first_entry_date}`"
                >
                  新
                </span>
                <span v-else class="text-sm text-gray-400">-</span>
              </td>
              <td class="px-4 py-3 whitespace-nowrap text-right">
                <span 
                  :class="getContinuousDaysColor(item.continuous_days)"
                  class="text-sm font-medium"
                >
                  {{ item.continuous_days || 0 }}天
                </span>
              </td>
              <td class="px-4 py-3 whitespace-nowrap text-right">
                <span class="text-sm text-gray-900">{{ formatPrice(item.latest_price) }}</span>
              </td>
              <td class="px-4 py-3 whitespace-nowrap text-right">
                <span 
                  :class="getChangeColor(item.change_amount)"
                  class="text-sm font-medium"
                >
                  {{ formatChange(item.change_amount) }}
                </span>
              </td>
              <td class="px-4 py-3 whitespace-nowrap text-right">
                <span 
                  :class="getChangeColor(item.change_pct)"
                  class="text-sm font-medium"
                >
                  {{ formatPercent(item.change_pct) }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      
      <!-- 空状态 -->
      <div v-if="!loading && data.length === 0" class="text-center py-12">
        <p class="text-gray-500">暂无数据</p>
        <button
          @click="loadData"
          class="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm"
        >
          重新加载
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

const loading = ref(false)
const crawling = ref(false)
const data = ref([])
const tradeDate = ref('')
const sortFirstEntry = ref(null) // null, 'asc', 'desc'
const sortContinuousDays = ref(null) // null, 'asc', 'desc'

// 触发爬虫重新爬取数据
async function triggerCrawl() {
  if (!confirm('确定要重新爬取数据吗？这可能需要几分钟时间。')) {
    return
  }
  
  crawling.value = true
  try {
    const response = await axios.post(`${API_BASE_URL}/api/guba/popularity/crawl`, null, {
      params: {
        limit: 100
      }
    })
    
    if (response.data.success) {
      alert('爬虫任务已启动，正在后台爬取数据。爬取完成后请点击"刷新"按钮查看最新数据。')
      // 等待3秒后自动刷新数据
      setTimeout(() => {
        loadData()
      }, 3000)
    } else {
      alert('启动爬虫失败: ' + (response.data.message || '未知错误'))
    }
  } catch (error) {
    console.error('启动爬虫失败:', error)
    alert('启动爬虫失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    crawling.value = false
  }
}

// 加载数据
async function loadData() {
  loading.value = true
  try {
    const params = {
      limit: 100,
      include_first_entry: true,  // 固定启用首次入榜
      include_continuous_days: true  // 固定启用持续天数
    }
    
    const response = await axios.get(`${API_BASE_URL}/api/guba/popularity`, { params })
    
    if (response.data.success) {
      let result = response.data.data
      
      // 应用排序
      if (sortFirstEntry.value || sortContinuousDays.value) {
        result = [...result].sort((a, b) => {
          // 优先按首次入榜排序
          if (sortFirstEntry.value) {
            const isFirstA = a.is_first_entry ? 1 : 0
            const isFirstB = b.is_first_entry ? 1 : 0
            if (isFirstA !== isFirstB) {
              if (sortFirstEntry.value === 'asc') {
                return isFirstA - isFirstB  // 首次入榜的在后
              } else {
                return isFirstB - isFirstA  // 首次入榜的在前
              }
            }
            // 如果都是首次入榜或都不是，按日期排序
            if (a.is_first_entry && b.is_first_entry) {
              const dateA = a.first_entry_date || ''
              const dateB = b.first_entry_date || ''
              if (dateA !== dateB) {
                return sortFirstEntry.value === 'asc' ? dateA.localeCompare(dateB) : dateB.localeCompare(dateA)
              }
            }
          }
          
          // 然后按持续天数排序
          if (sortContinuousDays.value) {
            const daysA = a.continuous_days || 0
            const daysB = b.continuous_days || 0
            if (daysA !== daysB) {
              if (sortContinuousDays.value === 'asc') {
                return daysA - daysB
              } else {
                return daysB - daysA
              }
            }
          }
          
          // 如果都没有排序或值相同，保持原排名顺序
          return (a.rank_position || 0) - (b.rank_position || 0)
        })
      }
      
      data.value = result
      tradeDate.value = response.data.trade_date
    } else {
      alert('加载失败: ' + (response.data.message || '未知错误'))
    }
  } catch (error) {
    console.error('加载失败:', error)
    alert('加载失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    loading.value = false
  }
}

// 切换首次入榜排序
function toggleSortFirstEntry() {
  if (sortFirstEntry.value === null) {
    sortFirstEntry.value = 'desc'  // 首次入榜的在前
  } else if (sortFirstEntry.value === 'desc') {
    sortFirstEntry.value = 'asc'   // 首次入榜的在后
  } else {
    sortFirstEntry.value = null    // 取消排序
  }
  
  // 重新加载数据以应用排序
  loadData()
}

// 切换持续天数排序
function toggleSortContinuousDays() {
  if (sortContinuousDays.value === null) {
    sortContinuousDays.value = 'desc'  // 持续天数多的在前
  } else if (sortContinuousDays.value === 'desc') {
    sortContinuousDays.value = 'asc'   // 持续天数少的在前
  } else {
    sortContinuousDays.value = null    // 取消排序
  }
  
  // 重新加载数据以应用排序
  loadData()
}

// 格式化价格
function formatPrice(price) {
  if (price === null || price === undefined) return '--'
  return price.toFixed(2)
}

// 格式化涨跌额
function formatChange(change) {
  if (change === null || change === undefined) return '--'
  const sign = change >= 0 ? '+' : ''
  return sign + change.toFixed(2)
}

// 格式化百分比
function formatPercent(percent) {
  if (percent === null || percent === undefined) return '--'
  return percent.toFixed(2) + '%'
}

// 获取涨跌颜色
function getChangeColor(value) {
  if (value === null || value === undefined) return 'text-gray-500'
  if (value > 0) return 'text-red-600'
  if (value < 0) return 'text-green-600'
  return 'text-gray-500'
}

// 获取持续天数颜色
function getContinuousDaysColor(days) {
  if (!days || days === 0) return 'text-gray-400'
  if (days <= 3) return 'text-yellow-600'
  if (days <= 7) return 'text-orange-600'
  return 'text-red-600'
}

// 页面加载时自动加载数据
onMounted(() => {
  loadData()
})
</script>

