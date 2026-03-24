<template>
  <div class="container mx-auto px-4 py-6">
    <!-- 页面标题 -->
    <div class="mb-6 flex items-start justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-800">股票列表</h1>
        <p class="text-sm text-gray-500 mt-1">显示所有热门板块下的股票信息</p>
      </div>
      <div class="flex items-center gap-2">
        <button
          @click="batchAddToWatchlist"
          :disabled="loading || addingToWatchlist || filteredStocks.length === 0"
          class="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:bg-gray-400 text-sm flex items-center gap-2"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
          </svg>
          {{ addingToWatchlist ? '添加中...' : '一键加入跟踪池' }}
        </button>
        <button
          @click="loadStocks"
          :disabled="loading"
          class="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-400 text-sm flex items-center gap-2"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          {{ loading ? '加载中...' : '刷新' }}
        </button>
      </div>
    </div>

    <!-- 筛选条件 -->
    <div class="mb-4 bg-white p-4 rounded-lg shadow">
      <div class="grid grid-cols-3 gap-4">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">板块筛选</label>
          <select
            v-model="filterSectorId"
            @change="applyFilters"
            class="w-full px-3 py-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
          >
            <option :value="null">全部板块</option>
            <option v-for="sector in sectors" :key="sector.id" :value="sector.id">
              {{ sector.name }}
            </option>
          </select>
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">股票代码/名称</label>
          <input
            v-model="filterStockCode"
            @input="applyFilters"
            type="text"
            placeholder="输入股票代码或名称..."
            class="w-full px-3 py-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
          />
        </div>
        <div class="flex items-end">
          <button
            @click="clearFilters"
            class="px-4 py-2 border border-gray-300 text-gray-700 rounded hover:bg-gray-50 text-sm"
          >
            清除筛选
          </button>
        </div>
      </div>
    </div>

    <!-- 统计信息 -->
    <div class="mb-4 bg-white p-4 rounded-lg shadow">
      <div class="flex items-center gap-6 text-sm">
        <div>
          <span class="text-gray-500">总股票数：</span>
          <span class="font-semibold text-gray-900">{{ filteredStocks.length }}</span>
        </div>
        <div>
          <span class="text-gray-500">涉及板块：</span>
          <span class="font-semibold text-gray-900">{{ uniqueSectorsCount }}</span>
        </div>
      </div>
    </div>

    <!-- 股票表格 -->
    <div class="bg-white rounded-lg shadow overflow-hidden">
      <div class="overflow-x-auto">
        <table class="min-w-full divide-y divide-gray-200">
          <thead class="bg-gray-50">
            <tr>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer hover:bg-gray-100" @click="sortBy('sector_name')">
                所属板块
                <span v-if="sortField === 'sector_name'" class="ml-1">
                  {{ sortOrder === 'asc' ? '↑' : '↓' }}
                </span>
              </th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer hover:bg-gray-100" @click="sortBy('ts_code')">
                股票代码
                <span v-if="sortField === 'ts_code'" class="ml-1">
                  {{ sortOrder === 'asc' ? '↑' : '↓' }}
                </span>
              </th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer hover:bg-gray-100" @click="sortBy('stock_name')">
                股票名称
                <span v-if="sortField === 'stock_name'" class="ml-1">
                  {{ sortOrder === 'asc' ? '↑' : '↓' }}
                </span>
              </th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer hover:bg-gray-100" @click="sortBy('today_change_pct')">
                今日涨幅
                <span v-if="sortField === 'today_change_pct'" class="ml-1">
                  {{ sortOrder === 'asc' ? '↑' : '↓' }}
                </span>
              </th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer hover:bg-gray-100" @click="sortBy('added_at')">
                添加时间
                <span v-if="sortField === 'added_at'" class="ml-1">
                  {{ sortOrder === 'asc' ? '↑' : '↓' }}
                </span>
              </th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer hover:bg-gray-100" @click="sortBy('change_pct_after_add')">
                加入后涨幅
                <span v-if="sortField === 'change_pct_after_add'" class="ml-1">
                  {{ sortOrder === 'asc' ? '↑' : '↓' }}
                </span>
              </th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">备注</th>
              <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">操作</th>
            </tr>
          </thead>
          <tbody class="bg-white divide-y divide-gray-200">
            <tr v-for="stock in sortedStocks" :key="stock.id" class="hover:bg-gray-50">
              <td class="px-4 py-3 text-sm">
                <span class="px-2 py-1 bg-blue-100 text-blue-800 rounded text-xs font-medium">
                  {{ stock.sector_name }}
                </span>
              </td>
              <td class="px-4 py-3 text-sm font-medium text-blue-600">{{ stock.ts_code }}</td>
              <td class="px-4 py-3 text-sm text-gray-900">{{ stock.stock_name || '-' }}</td>
              <td class="px-4 py-3 text-sm font-medium" :class="getChangeColorClass(stock.today_change_pct)">
                <span v-if="stock.today_change_pct !== null && stock.today_change_pct !== undefined">
                  {{ formatChangePercent(stock.today_change_pct) }}
                </span>
                <span v-else class="text-gray-400">-</span>
              </td>
              <td class="px-4 py-3 text-sm text-gray-500">{{ formatDate(stock.added_at) }}</td>
              <td class="px-4 py-3 text-sm font-medium" :class="getChangeColorClass(stock.change_pct_after_add)">
                <span v-if="stock.change_pct_after_add !== null && stock.change_pct_after_add !== undefined">
                  {{ formatChangePercent(stock.change_pct_after_add) }}
                </span>
                <span v-else class="text-gray-400">-</span>
              </td>
              <td class="px-4 py-3 text-sm text-gray-500">{{ stock.notes || '-' }}</td>
              <td class="px-4 py-3 text-sm text-center">
                <button
                  @click="viewSector(stock.sector_id)"
                  class="text-blue-600 hover:text-blue-800 mr-3"
                  title="查看板块"
                >
                  <svg class="w-4 h-4 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                  </svg>
                </button>
                <button
                  @click="removeStock(stock)"
                  class="text-red-600 hover:text-red-800"
                  title="删除"
                >
                  <svg class="w-4 h-4 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </button>
              </td>
            </tr>
          </tbody>
        </table>

        <!-- 空状态 -->
        <div v-if="filteredStocks.length === 0" class="p-12 text-center text-gray-500">
          <svg class="w-16 h-16 mx-auto mb-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
          </svg>
          <p class="text-lg">暂无股票数据</p>
          <p class="text-sm mt-2">请先在"热门板块"页面添加股票</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'

const router = useRouter()
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

const loading = ref(false)
const addingToWatchlist = ref(false)
const stocks = ref([])
const sectors = ref([])
const filterSectorId = ref(null)
const filterStockCode = ref('')
const sortField = ref('sector_name')
const sortOrder = ref('asc')

// 加载板块列表
async function loadSectors() {
  try {
    const response = await axios.get(`${API_BASE_URL}/api/hot-sector`)
    if (response.data.success) {
      sectors.value = (response.data.data || []).filter(s => s.status === 'active')
    }
  } catch (error) {
    console.error('加载板块列表失败:', error)
  }
}

// 加载股票列表
async function loadStocks() {
  loading.value = true
  try {
    const params = {}
    if (filterSectorId.value) {
      params.sector_id = filterSectorId.value
    }
    if (filterStockCode.value) {
      params.ts_code = filterStockCode.value
    }
    
    const response = await axios.get(`${API_BASE_URL}/api/hot-sector/all-stocks`, { params })
    if (response.data.success) {
      stocks.value = response.data.data || []
    } else {
      alert('加载股票列表失败: ' + (response.data.message || '未知错误'))
    }
  } catch (error) {
    console.error('加载股票列表失败:', error)
    alert('加载股票列表失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    loading.value = false
  }
}

// 过滤后的股票列表
const filteredStocks = computed(() => {
  let result = stocks.value
  
  // 按股票代码/名称过滤
  if (filterStockCode.value) {
    const keyword = filterStockCode.value.toLowerCase()
    result = result.filter(s => 
      s.ts_code.toLowerCase().includes(keyword) ||
      (s.stock_name && s.stock_name.toLowerCase().includes(keyword))
    )
  }
  
  return result
})

// 排序后的股票列表
const sortedStocks = computed(() => {
  const result = [...filteredStocks.value]
  
  result.sort((a, b) => {
    let aVal = a[sortField.value]
    let bVal = b[sortField.value]
    
    // 处理日期排序
    if (sortField.value === 'added_at') {
      aVal = aVal ? new Date(aVal).getTime() : 0
      bVal = bVal ? new Date(bVal).getTime() : 0
    }
    
    // 处理数字排序（涨幅）
    if (sortField.value === 'change_pct_after_add' || sortField.value === 'today_change_pct') {
      aVal = aVal !== null && aVal !== undefined ? aVal : -Infinity
      bVal = bVal !== null && bVal !== undefined ? bVal : -Infinity
    }
    
    // 处理字符串排序
    if (typeof aVal === 'string') {
      aVal = aVal.toLowerCase()
      bVal = bVal.toLowerCase()
    }
    
    if (sortOrder.value === 'asc') {
      return aVal > bVal ? 1 : aVal < bVal ? -1 : 0
    } else {
      return aVal < bVal ? 1 : aVal > bVal ? -1 : 0
    }
  })
  
  return result
})

// 唯一板块数量
const uniqueSectorsCount = computed(() => {
  const sectorSet = new Set(filteredStocks.value.map(s => s.sector_id))
  return sectorSet.size
})

// 排序
function sortBy(field) {
  if (sortField.value === field) {
    sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortField.value = field
    sortOrder.value = 'asc'
  }
}

// 应用筛选
function applyFilters() {
  loadStocks()
}

// 清除筛选
function clearFilters() {
  filterSectorId.value = null
  filterStockCode.value = ''
  loadStocks()
}

// 格式化日期
function formatDate(dateStr) {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  return `${year}-${month}-${day} ${hours}:${minutes}`
}

// 格式化涨幅百分比
function formatChangePercent(value) {
  if (value === null || value === undefined) {
    return '-'
  }
  // 确保是数字类型
  const numValue = typeof value === 'string' ? parseFloat(value) : Number(value)
  if (isNaN(numValue)) {
    return '-'
  }
  const sign = numValue > 0 ? '+' : ''
  return `${sign}${numValue.toFixed(2)}%`
}

// 获取涨幅颜色类
function getChangeColorClass(changePct) {
  if (changePct === null || changePct === undefined) {
    return 'text-gray-400'
  }
  // 确保是数字类型
  const numValue = typeof changePct === 'string' ? parseFloat(changePct) : Number(changePct)
  if (isNaN(numValue)) {
    return 'text-gray-400'
  }
  if (numValue > 0) {
    return 'text-red-600'
  } else if (numValue < 0) {
    return 'text-green-600'
  } else {
    return 'text-gray-500'
  }
}

// 查看板块
function viewSector(sectorId) {
  router.push(`/hot-sector`)
  // 注意：这里跳转到热门板块页面，但无法自动选中板块
  // 可以考虑使用路由参数或状态管理来实现
}

// 删除股票
async function removeStock(stock) {
  if (!confirm(`确定要从板块 "${stock.sector_name}" 中删除股票 "${stock.stock_name || stock.ts_code}" 吗？`)) {
    return
  }

  try {
    const response = await axios.delete(
      `${API_BASE_URL}/api/hot-sector/${stock.sector_id}/stocks/${stock.ts_code}`
    )
    if (response.data.success) {
      alert('删除成功')
      await loadStocks()
    } else {
      alert('删除失败: ' + (response.data.message || '未知错误'))
    }
  } catch (error) {
    console.error('删除股票失败:', error)
    alert('删除股票失败: ' + (error.response?.data?.detail || error.message))
  }
}

// 一键加入跟踪池
async function batchAddToWatchlist() {
  if (filteredStocks.value.length === 0) {
    alert('没有可添加的股票')
    return
  }

  if (!confirm(`确定要将当前列表中的 ${filteredStocks.value.length} 只股票加入跟踪池吗？\n加入理由：板块龙头`)) {
    return
  }

  addingToWatchlist.value = true
  let successCount = 0
  let skipCount = 0
  let failCount = 0
  const errors = []

  try {
    // 批量添加股票到跟踪池
    for (const stock of filteredStocks.value) {
      try {
        const response = await axios.post(`${API_BASE_URL}/api/watchlist`, {
          ts_code: stock.ts_code,
          note: '板块龙头'
        })
        
        if (response.data.success) {
          successCount++
        } else {
          // 如果股票已存在，也算跳过
          if (response.data.message && response.data.message.includes('已在跟踪列表中')) {
            skipCount++
          } else {
            failCount++
            errors.push(`${stock.ts_code}: ${response.data.message || '未知错误'}`)
          }
        }
      } catch (error) {
        // 检查是否是已存在的错误
        if (error.response?.data?.message && error.response.data.message.includes('已在跟踪列表中')) {
          skipCount++
        } else {
          failCount++
          errors.push(`${stock.ts_code}: ${error.response?.data?.detail || error.message}`)
        }
      }
    }

    // 显示结果
    let message = `添加完成！\n成功: ${successCount} 只`
    if (skipCount > 0) {
      message += `\n跳过（已存在）: ${skipCount} 只`
    }
    if (failCount > 0) {
      message += `\n失败: ${failCount} 只`
      if (errors.length > 0 && errors.length <= 5) {
        message += `\n\n失败详情：\n${errors.join('\n')}`
      }
    }
    alert(message)
  } catch (error) {
    console.error('批量添加失败:', error)
    alert('批量添加失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    addingToWatchlist.value = false
  }
}

// 初始化
onMounted(() => {
  loadSectors()
  loadStocks()
})
</script>
