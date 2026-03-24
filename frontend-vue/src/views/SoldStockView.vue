<template>
  <div class="container mx-auto px-4 py-6">
    <!-- 页面标题 -->
    <div class="mb-6 flex items-start justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-800">已卖出股票</h1>
        <p class="text-sm text-gray-500 mt-1">记录已卖出股票的表现分析</p>
      </div>
      
      <!-- 操作按钮 -->
      <div class="flex items-center gap-3">
        <button
          @click="showAddDialog = true"
          class="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm flex items-center gap-2"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
          </svg>
          添加卖出记录
        </button>
        <button
          @click="handleBatchRecalculate"
          :disabled="recalculating"
          class="px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 disabled:bg-gray-400 disabled:cursor-not-allowed text-sm flex items-center gap-2"
        >
          <svg v-if="!recalculating" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          <span v-else class="animate-spin">⟳</span>
          {{ recalculating ? '重新计算中...' : '批量重新计算' }}
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

    <!-- 筛选器 -->
    <div class="mb-4 bg-white rounded-lg shadow p-4">
      <div class="flex items-center gap-4 flex-wrap">
        <div class="flex items-center gap-2">
          <label class="text-sm text-gray-600 font-medium">股票代码：</label>
          <input
            v-model="filterTsCode"
            type="text"
            placeholder="输入股票代码"
            class="px-3 py-2 border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 w-32"
            @input="loadData"
          />
        </div>
        <div class="flex items-center gap-2">
          <label class="text-sm text-gray-600 font-medium">卖出日期：</label>
          <input
            v-model="filterStartDate"
            type="date"
            class="px-3 py-2 border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            @change="loadData"
          />
          <span class="text-gray-500">至</span>
          <input
            v-model="filterEndDate"
            type="date"
            class="px-3 py-2 border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            @change="loadData"
          />
        </div>
        <div class="flex items-center gap-2">
          <label class="text-sm text-gray-600 font-medium">排序：</label>
          <select
            v-model="sortBy"
            class="px-3 py-2 border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            @change="loadData"
          >
            <option value="sell_date">卖出日期</option>
            <option value="change_5d_after_sell">卖出后5日涨幅</option>
            <option value="change_10d_after_sell">卖出后10日涨幅</option>
          </select>
          <select
            v-model="sortOrder"
            class="px-3 py-2 border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            @change="loadData"
          >
            <option value="desc">降序</option>
            <option value="asc">升序</option>
          </select>
        </div>
      </div>
    </div>

    <!-- 说明 -->
    <p class="mb-4 text-sm text-gray-600">
      满足「重新站稳10日线」且「多头模式（MA5&gt;MA10&gt;MA20）」的已卖出股票会自动加入「股票跟踪」。
    </p>

    <!-- 日线图卡片列表 -->
    <div class="space-y-4">
      <div
        v-for="item in data"
        :key="item.id"
        class="bg-white rounded-lg shadow border border-gray-200 overflow-hidden"
      >
        <div class="p-4 flex flex-wrap items-start gap-4">
          <!-- 左侧：名称、代码、卖出日期、指标 -->
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 flex-wrap">
              <span class="font-semibold text-gray-900">{{ item.stock_name || item.ts_code }}</span>
              <span class="text-sm text-blue-600">{{ item.ts_code }}</span>
              <span class="text-sm text-gray-500">卖出 {{ formatDate(item.sell_date) }}</span>
              <span v-if="item.in_watchlist" class="px-2 py-0.5 bg-green-100 text-green-800 rounded text-xs font-medium">已加入跟踪</span>
              <span v-else-if="item.is_above_ma10_now && item.is_bullish_now" class="px-2 py-0.5 bg-amber-100 text-amber-800 rounded text-xs">符合条件（可自动加入）</span>
            </div>
            <div class="mt-2 flex flex-wrap gap-4 text-sm">
              <span :class="getChangeColor(item.change_5d_after_sell)">5日 {{ formatPercent(item.change_5d_after_sell) }}</span>
              <span :class="getChangeColor(item.change_10d_after_sell)">10日 {{ formatPercent(item.change_10d_after_sell) }}</span>
              <span>
                站稳10日线<span v-if="item.ma_as_of_date" class="text-gray-500">（截至{{ item.ma_as_of_date }}）</span>
                <span :class="item.is_above_ma10 ? 'text-green-600' : 'text-gray-500'">{{ item.is_above_ma10 === true ? '是' : item.is_above_ma10 === false ? '否' : '-' }}</span>
              </span>
              <span>
                站稳20/30<span v-if="item.ma_as_of_date" class="text-gray-500">（截至{{ item.ma_as_of_date }}）</span>
                <span :class="item.is_above_ma20 ? 'text-green-600' : 'text-gray-500'">{{ item.is_above_ma20 ? '是' : '否' }}</span> / <span :class="item.is_above_ma30 ? 'text-green-600' : 'text-gray-500'">{{ item.is_above_ma30 ? '是' : '否' }}</span>
              </span>
            </div>
            <p v-if="item.notes" class="mt-1 text-xs text-gray-500 truncate max-w-md" :title="item.notes">{{ item.notes }}</p>
          </div>
          <!-- 日线图 -->
          <div class="flex-shrink-0">
            <div v-if="!item.daily_chart || item.daily_chart.length === 0" class="w-48 h-12 flex items-center justify-center text-gray-400 text-xs border border-gray-100 rounded">暂无日线</div>
            <MiniChart v-else :data="item.daily_chart" :trend="chartTrend(item.daily_chart)" :width="200" :height="56" />
          </div>
          <!-- 操作 -->
          <div class="flex items-center gap-2">
            <button @click="showEditDialog(item)" class="p-2 text-blue-600 hover:bg-blue-50 rounded" title="编辑">编辑</button>
            <button @click="recalculatePerformance(item.id)" class="p-2 text-green-600 hover:bg-green-50 rounded" title="重新计算">重算</button>
            <button @click="deleteRecord(item.id)" class="p-2 text-red-600 hover:bg-red-50 rounded" title="删除">删除</button>
          </div>
        </div>
      </div>

      <!-- 空状态 -->
      <div v-if="!loading && data.length === 0" class="bg-white rounded-lg shadow border border-gray-200 text-center py-12">
        <p class="text-gray-500 mb-2">暂无卖出记录</p>
        <p class="text-sm text-gray-400">点击「添加卖出记录」添加第一条记录</p>
      </div>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading" class="text-center py-12">
      <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      <p class="mt-2 text-gray-500">加载中...</p>
    </div>

    <!-- 添加/编辑对话框 -->
    <div v-if="showAddDialog || showEditDialogFlag" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50" @click.self="closeDialog">
      <div class="bg-white rounded-lg shadow-xl p-6 w-full max-w-md">
        <h3 class="text-lg font-semibold mb-4">{{ showEditDialogFlag ? '编辑卖出记录' : '添加卖出记录' }}</h3>
        
        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">股票代码 *</label>
            <input
              v-model="formData.ts_code"
              type="text"
              placeholder="如：600519.SH 或 600519"
              class="w-full px-3 py-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
              :disabled="showEditDialogFlag"
              @blur="onStockCodeBlur"
            />
          </div>
          
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">股票名称</label>
            <input
              v-model="formData.stock_name"
              type="text"
              placeholder="自动获取或手动输入，如：贵州茅台"
              class="w-full px-3 py-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
              @blur="onStockNameBlur"
            />
          </div>
          
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">卖出日期 *</label>
            <input
              v-model="formData.sell_date"
              type="date"
              class="w-full px-3 py-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">备注</label>
            <textarea
              v-model="formData.notes"
              rows="3"
              placeholder="备注信息"
              class="w-full px-3 py-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
            ></textarea>
          </div>
        </div>
        
        <div class="mt-6 flex justify-end gap-3">
          <button
            @click="closeDialog"
            class="px-4 py-2 border border-gray-300 rounded text-gray-700 hover:bg-gray-50"
          >
            取消
          </button>
          <button
            @click="saveRecord"
            :disabled="saving"
            class="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-400"
          >
            {{ saving ? '保存中...' : '保存' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'
import MiniChart from '../components/ui/MiniChart.vue'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

const loading = ref(false)
const saving = ref(false)
const recalculating = ref(false)
const data = ref([])
const showAddDialog = ref(false)
const showEditDialogFlag = ref(false)
const editingId = ref(null)
const isSearchingStock = ref(false) // 防止循环触发

// 筛选条件
const filterTsCode = ref('')
const filterStartDate = ref('')
const filterEndDate = ref('')
const sortBy = ref('sell_date')
const sortOrder = ref('desc')

// 表单数据
const formData = ref({
  ts_code: '',
  stock_name: '',
  sell_date: '',
  notes: ''
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

// 获取涨幅颜色
function getChangeColor(value) {
  if (value === null || value === undefined) return 'text-gray-500'
  const num = parseFloat(value)
  if (num > 0) return 'text-red-600 font-semibold'
  if (num < 0) return 'text-green-600 font-semibold'
  return 'text-gray-500'
}

// 日线图涨跌：最近收盘 >= 最早收盘为红（涨）
function chartTrend(dailyChart) {
  if (!dailyChart || dailyChart.length < 2) return true
  const first = dailyChart[0]?.close
  const last = dailyChart[dailyChart.length - 1]?.close
  if (first == null || last == null) return true
  return last >= first
}

// 加载数据
async function loadData() {
  loading.value = true
  try {
    const params = {}
    if (filterTsCode.value) {
      params.ts_code = filterTsCode.value
    }
    if (filterStartDate.value) {
      params.start_date = filterStartDate.value
    }
    if (filterEndDate.value) {
      params.end_date = filterEndDate.value
    }
    if (sortBy.value) {
      params.sort_by = sortBy.value
    }
    if (sortOrder.value) {
      params.sort_order = sortOrder.value
    }
    params.with_daily = true
    params.chart_days = 60

    const response = await axios.get(`${API_BASE_URL}/api/sold-stock`, { params })
    
    if (response.data.success) {
      data.value = response.data.data || []
      // 自动将「重新站稳10日线+多头」的股票加入股票跟踪
      try {
        const addRes = await axios.post(`${API_BASE_URL}/api/sold-stock/auto-add-to-watchlist`)
        if (addRes.data.success && addRes.data.added && addRes.data.added.length > 0) {
          const addedSet = new Set(addRes.data.added)
          data.value = data.value.map((row) => (addedSet.has(row.ts_code) ? { ...row, in_watchlist: true } : row))
        }
      } catch (_) { /* 静默忽略 */ }
    } else {
      console.error('加载失败:', response.data.message)
      data.value = []
    }
  } catch (error) {
    console.error('加载卖出记录失败:', error)
    data.value = []
    alert('加载失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    loading.value = false
  }
}

// 显示编辑对话框
function showEditDialog(item) {
  editingId.value = item.id
  formData.value = {
    ts_code: item.ts_code,
    stock_name: item.stock_name || '',
    sell_date: item.sell_date || '',
    notes: item.notes || ''
  }
  showEditDialogFlag.value = true
}

// 根据股票代码查询股票名称
async function onStockCodeBlur() {
  if (!formData.value.ts_code || isSearchingStock.value) {
    return
  }
  
  const code = formData.value.ts_code.trim()
  if (!code) {
    return
  }
  
  isSearchingStock.value = true
  try {
    const response = await axios.get(`${API_BASE_URL}/api/sold-stock/search-stock`, {
      params: { keyword: code }
    })
    
    if (response.data.success) {
      // 更新股票代码（可能被规范化，如补全后缀）
      formData.value.ts_code = response.data.ts_code
      // 自动填充股票名称（如果为空或需要更新）
      if (!formData.value.stock_name || formData.value.stock_name !== response.data.stock_name) {
        formData.value.stock_name = response.data.stock_name
      }
    }
  } catch (error) {
    console.error('查询股票信息失败:', error)
    // 静默失败，不弹窗提示
  } finally {
    isSearchingStock.value = false
  }
}

// 根据股票名称查询股票代码
async function onStockNameBlur() {
  if (!formData.value.stock_name || isSearchingStock.value) {
    return
  }
  
  const name = formData.value.stock_name.trim()
  if (!name) {
    return
  }
  
  isSearchingStock.value = true
  try {
    const response = await axios.get(`${API_BASE_URL}/api/sold-stock/search-stock`, {
      params: { keyword: name }
    })
    
    if (response.data.success) {
      // 自动填充股票代码（如果为空或需要更新）
      if (!formData.value.ts_code || formData.value.ts_code !== response.data.ts_code) {
        formData.value.ts_code = response.data.ts_code
      }
      // 更新股票名称（可能被规范化）
      formData.value.stock_name = response.data.stock_name
    }
  } catch (error) {
    console.error('查询股票信息失败:', error)
    // 静默失败，不弹窗提示
  } finally {
    isSearchingStock.value = false
  }
}

// 关闭对话框
function closeDialog() {
  showAddDialog.value = false
  showEditDialogFlag.value = false
  editingId.value = null
  isSearchingStock.value = false
  formData.value = {
    ts_code: '',
    stock_name: '',
    sell_date: '',
    notes: ''
  }
}

// 保存记录
async function saveRecord() {
  if (!formData.value.ts_code || !formData.value.sell_date) {
    alert('请填写股票代码和卖出日期')
    return
  }

  saving.value = true
  try {
    if (showEditDialogFlag.value && editingId.value) {
      // 更新记录
      await axios.put(`${API_BASE_URL}/api/sold-stock/${editingId.value}`, formData.value)
      alert('更新成功')
    } else {
      // 创建记录
      await axios.post(`${API_BASE_URL}/api/sold-stock`, formData.value)
      alert('添加成功')
    }
    
    closeDialog()
    loadData()
  } catch (error) {
    console.error('保存失败:', error)
    alert('保存失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    saving.value = false
  }
}

// 删除记录
async function deleteRecord(id) {
  if (!confirm('确定要删除这条记录吗？')) {
    return
  }

  try {
    await axios.delete(`${API_BASE_URL}/api/sold-stock/${id}`)
    alert('删除成功')
    loadData()
  } catch (error) {
    console.error('删除失败:', error)
    alert('删除失败: ' + (error.response?.data?.detail || error.message))
  }
}

// 重新计算表现
async function recalculatePerformance(id) {
  if (!confirm('确定要重新计算卖出后表现吗？')) {
    return
  }

  try {
    await axios.post(`${API_BASE_URL}/api/sold-stock/${id}/recalculate`)
    alert('重新计算成功')
    loadData()
  } catch (error) {
    console.error('重新计算失败:', error)
    alert('重新计算失败: ' + (error.response?.data?.detail || error.message))
  }
}

// 批量重新计算表现
async function handleBatchRecalculate() {
  if (!confirm('确定要批量重新计算所有卖出记录的表现吗？\n\n这将重新计算所有记录，可能需要一些时间。')) {
    return
  }

  recalculating.value = true
  try {
    const response = await axios.post(`${API_BASE_URL}/api/sold-stock/batch-recalculate`)
    if (response.data.success) {
      const data = response.data.data
      const message = `批量重新计算完成！\n\n总计: ${data.total} 条\n成功: ${data.success} 条\n失败: ${data.failed} 条`
      alert(message)
      loadData() // 重新加载数据
    } else {
      alert('批量重新计算失败: ' + (response.data.message || '未知错误'))
    }
  } catch (error) {
    console.error('批量重新计算失败:', error)
    alert('批量重新计算失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    recalculating.value = false
  }
}

// 初始化
onMounted(() => {
  loadData()
})
</script>
