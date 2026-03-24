<template>
  <div class="container mx-auto px-4 py-6">
    <!-- 页面标题 -->
    <div class="mb-6">
      <h1 class="text-2xl font-bold text-gray-800">股票财务数据</h1>
      <p class="text-sm text-gray-500 mt-1">查询并展示股票的详细财务数据</p>
    </div>

    <!-- 财务数据列表 -->
    <div class="bg-white rounded-lg shadow mb-6">
      <div class="p-6">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-xl font-bold text-gray-800">财务数据列表</h2>
          <div class="flex items-center space-x-4 flex-wrap gap-2">
            <input
              v-model="listFilter.ts_code"
              type="text"
              placeholder="股票代码"
              class="px-3 py-1 border border-gray-300 rounded text-sm"
              @keyup.enter="loadFinancialList"
            />
            <input
              v-model="listFilter.stock_name"
              type="text"
              placeholder="股票名称"
              class="px-3 py-1 border border-gray-300 rounded text-sm"
              @keyup.enter="loadFinancialList"
            />
            <input
              v-model="listFilter.industry"
              type="text"
              placeholder="行业"
              class="px-3 py-1 border border-gray-300 rounded text-sm"
              @keyup.enter="loadFinancialList"
            />
            <button
              @click="loadFinancialList"
              :disabled="listLoading"
              class="px-4 py-1 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-50"
            >
              {{ listLoading ? '加载中...' : '搜索' }}
            </button>
          </div>
        </div>

        <!-- 加载中 -->
        <div v-if="listLoading" class="text-center py-8">
          <div class="inline-block animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
          <p class="mt-2 text-sm text-gray-500">正在加载财务数据列表...</p>
        </div>

        <!-- 数据表格 -->
        <div v-else-if="financialList && financialList.length > 0" class="overflow-x-auto">
          <table class="min-w-full divide-y divide-gray-200">
            <thead class="bg-gray-50">
              <tr>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100 select-none" @click="handleSort('ts_code')" title="点击排序">
                  股票代码 {{ sortIcon('ts_code') }}
                </th>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">股票名称</th>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">行业</th>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100 select-none" @click="handleSort('end_date')" title="点击排序">
                  报告期 {{ sortIcon('end_date') }}
                </th>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100 select-none" @click="handleSort('revenue')" title="点击排序">
                  营业收入(万) {{ sortIcon('revenue') }}
                </th>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100 select-none" @click="handleSort('net_profit')" title="点击排序">
                  净利润(万) {{ sortIcon('net_profit') }}
                </th>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100 select-none" @click="handleSort('roe')" title="点击排序">
                  ROE {{ sortIcon('roe') }}
                </th>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100 select-none" @click="handleSort('net_margin')" title="点击排序">
                  净利率 {{ sortIcon('net_margin') }}
                </th>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100 select-none" @click="handleSort('deduct_net_margin')" title="点击排序">
                  扣非净利率 {{ sortIcon('deduct_net_margin') }}
                </th>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">操作</th>
              </tr>
            </thead>
            <tbody class="bg-white divide-y divide-gray-200">
              <tr v-for="item in financialList" :key="`${item.ts_code}-${item.end_date}`" class="hover:bg-gray-50">
                <td class="px-4 py-3 whitespace-nowrap text-sm font-medium text-gray-900">{{ item.ts_code }}</td>
                <td class="px-4 py-3 whitespace-nowrap text-sm text-gray-700">{{ item.stock_name || '--' }}</td>
                <td class="px-4 py-3 whitespace-nowrap text-sm text-gray-700">{{ item.industry || '--' }}</td>
                <td class="px-4 py-3 whitespace-nowrap text-sm text-gray-700">{{ item.end_date || '--' }}</td>
                <td class="px-4 py-3 whitespace-nowrap text-sm text-gray-700">
                  {{ formatNumberInWan(item.revenue) }}
                </td>
                <td class="px-4 py-3 whitespace-nowrap text-sm text-gray-700">
                  {{ formatNumberInWan(item.net_profit) }}
                </td>
                <td class="px-4 py-3 whitespace-nowrap text-sm text-gray-700">
                  {{ formatPercent(item.roe) }}
                </td>
                <td class="px-4 py-3 whitespace-nowrap text-sm text-gray-700">
                  {{ formatPercent(item.net_margin) }}
                </td>
                <td class="px-4 py-3 whitespace-nowrap text-sm text-gray-700">
                  {{ formatPercent(item.deduct_net_margin) }}
                </td>
                <td class="px-4 py-3 whitespace-nowrap text-sm">
                  <button
                    @click="viewDetail(item.ts_code, item.end_date)"
                    class="text-blue-600 hover:text-blue-800"
                  >
                    查看详情
                  </button>
                </td>
              </tr>
            </tbody>
          </table>

          <!-- 分页 -->
          <div v-if="pagination && pagination.total_pages > 1" class="mt-4 flex items-center justify-between">
            <div class="text-sm text-gray-700">
              显示第 {{ (pagination.page - 1) * pagination.page_size + 1 }} - 
              {{ Math.min(pagination.page * pagination.page_size, pagination.total) }} 条，
              共 {{ pagination.total }} 条
            </div>
            <div class="flex space-x-2">
              <button
                @click="changePage(pagination.page - 1)"
                :disabled="pagination.page <= 1"
                class="px-3 py-1 border border-gray-300 rounded text-sm disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50"
              >
                上一页
              </button>
              <span class="px-3 py-1 text-sm text-gray-700">
                第 {{ pagination.page }} / {{ pagination.total_pages }} 页
              </span>
              <button
                @click="changePage(pagination.page + 1)"
                :disabled="pagination.page >= pagination.total_pages"
                class="px-3 py-1 border border-gray-300 rounded text-sm disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50"
              >
                下一页
              </button>
            </div>
          </div>
        </div>

        <!-- 空状态 -->
        <div v-else class="text-center py-8 text-gray-500">
          暂无财务数据
        </div>
      </div>
    </div>

    <!-- 搜索表单 -->
    <div class="bg-white rounded-lg shadow p-6 mb-6">
      <div class="flex items-end space-x-4">
        <div class="flex-1">
          <label class="block text-sm font-medium text-gray-700 mb-2">股票代码</label>
          <input
            v-model="tsCode"
            type="text"
            placeholder="如: 000001.SZ 或 600519.SH"
            class="w-full px-4 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            @keyup.enter="loadFinancialData"
          />
        </div>
        
        <div class="flex-1">
          <label class="block text-sm font-medium text-gray-700 mb-2">报告期（可选）</label>
          <input
            v-model="endDate"
            type="date"
            class="w-full px-4 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            @keyup.enter="loadFinancialData"
          />
        </div>
        
        <button
          @click="loadFinancialData"
          :disabled="loading || !tsCode"
          class="px-8 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {{ loading ? '查询中...' : '查询' }}
        </button>
      </div>
    </div>

    <!-- 加载中 -->
    <div v-if="loading" class="text-center py-12">
      <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      <p class="mt-2 text-gray-500">正在加载财务数据...</p>
    </div>

    <!-- 错误提示 -->
    <div v-if="error" class="bg-red-50 border border-red-300 rounded-lg p-4 mb-6">
      <div class="flex items-center">
        <span class="text-red-600 font-semibold">❌ {{ error }}</span>
      </div>
    </div>

    <!-- 财务数据展示 -->
    <div v-if="financialData && financialData.success" class="space-y-6">
      <!-- 公司简介/财务 Widget + 基本信息 -->
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div class="lg:col-span-1">
          <CompanyProfileWidget v-if="financialData?.stock?.ts_code" :ts-code="financialData.stock.ts_code" />
        </div>
        <div class="lg:col-span-2 bg-white rounded-lg shadow p-6">
        <h2 class="text-xl font-bold mb-4">📊 基本信息</h2>
        <div class="grid grid-cols-2 md:grid-cols-5 gap-4">
          <div>
            <div class="text-sm text-gray-500">股票名称</div>
            <div class="text-lg font-semibold">{{ financialData.stock.name }}</div>
          </div>
          <div>
            <div class="text-sm text-gray-500">股票代码</div>
            <div class="text-lg font-semibold">{{ financialData.stock.ts_code }}</div>
          </div>
          <div>
            <div class="text-sm text-gray-500">行业</div>
            <div class="text-lg font-semibold">{{ financialData.stock.industry || '--' }}</div>
          </div>
          <div>
            <div class="text-sm text-gray-500">交易所</div>
            <div class="text-lg font-semibold">{{ financialData.stock.exchange || '--' }}</div>
          </div>
        </div>
        </div>
      </div>

      <!-- 报告期选择 -->
      <div v-if="financialData.history_reports && financialData.history_reports.length > 0" class="bg-white rounded-lg shadow p-6">
        <h2 class="text-xl font-bold mb-4">📅 历史报告期</h2>
        <div class="flex flex-wrap gap-2">
          <button
            v-for="report in financialData.history_reports"
            :key="report.end_date"
            @click="loadFinancialDataByDate(report.end_date)"
            :class="[
              'px-4 py-2 rounded-lg text-sm font-medium transition-colors',
              endDate === report.end_date
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            ]"
          >
            {{ report.end_date }} ({{ report.report_type || '--' }})
          </button>
        </div>
      </div>

      <!-- 核心财务指标 -->
      <div class="bg-white rounded-lg shadow p-6">
        <h2 class="text-xl font-bold mb-4">💰 核心财务指标</h2>
        <div class="grid grid-cols-2 md:grid-cols-4 gap-6">
          <div class="border-l-4 border-blue-500 pl-4">
            <div class="text-sm text-gray-500">报告期</div>
            <div class="text-xl font-bold text-gray-900">{{ financialData.fundamental.end_date || '--' }}</div>
            <div class="text-xs text-gray-400 mt-1">{{ financialData.fundamental.report_type || '--' }}</div>
          </div>
          <div class="border-l-4 border-green-500 pl-4">
            <div class="text-sm text-gray-500">ROE（净资产收益率）</div>
            <div class="text-xl font-bold text-gray-900">
              {{ formatPercent(financialData.fundamental.roe) }}
            </div>
          </div>
          <div class="border-l-4 border-green-500 pl-4">
            <div class="text-sm text-gray-500">毛利率</div>
            <div class="text-xl font-bold text-gray-900">
              {{ formatPercent(financialData.fundamental.gross_margin) }}
            </div>
          </div>
          <div class="border-l-4 border-green-500 pl-4">
            <div class="text-sm text-gray-500">净利率</div>
            <div class="text-xl font-bold text-gray-900">
              {{ formatPercent(financialData.fundamental.net_margin) }}
            </div>
          </div>
          <div class="border-l-4 border-green-500 pl-4">
            <div class="text-sm text-gray-500">扣非净利率</div>
            <div class="text-xl font-bold text-gray-900">
              {{ formatPercent(financialData.fundamental.deduct_net_margin) }}
            </div>
          </div>
        </div>
      </div>

      <!-- 财务数据详情 -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <!-- 盈利能力 -->
        <div class="bg-white rounded-lg shadow p-6">
          <h3 class="text-lg font-bold mb-4">📈 盈利能力</h3>
          <div class="space-y-3">
            <div class="flex justify-between items-center py-2 border-b border-gray-100">
              <span class="text-gray-600">营业收入（万）</span>
              <span class="font-semibold">{{ formatNumberInWan(financialData.fundamental.revenue) }}</span>
            </div>
            <div class="flex justify-between items-center py-2 border-b border-gray-100">
              <span class="text-gray-600">净利润（万）</span>
              <span class="font-semibold">{{ formatNumberInWan(financialData.fundamental.net_profit) }}</span>
            </div>
            <div class="flex justify-between items-center py-2 border-b border-gray-100">
              <span class="text-gray-600">ROE（净资产收益率）</span>
              <span class="font-semibold">{{ formatPercent(financialData.fundamental.roe) }}</span>
            </div>
            <div class="flex justify-between items-center py-2 border-b border-gray-100">
              <span class="text-gray-600">毛利率</span>
              <span class="font-semibold">{{ formatPercent(financialData.fundamental.gross_margin) }}</span>
            </div>
            <div class="flex justify-between items-center py-2 border-b border-gray-100">
              <span class="text-gray-600">净利率</span>
              <span class="font-semibold">{{ formatPercent(financialData.fundamental.net_margin) }}</span>
            </div>
            <div class="flex justify-between items-center py-2">
              <span class="text-gray-600">扣非净利率</span>
              <span class="font-semibold">{{ formatPercent(financialData.fundamental.deduct_net_margin) }}</span>
            </div>
          </div>
        </div>

        <!-- 财务结构 -->
        <div class="bg-white rounded-lg shadow p-6">
          <h3 class="text-lg font-bold mb-4">🏗️ 财务结构</h3>
          <div class="space-y-3">
            <div class="flex justify-between items-center py-2 border-b border-gray-100">
              <span class="text-gray-600">总资产（万）</span>
              <span class="font-semibold">{{ formatNumberInWan(financialData.fundamental.total_asset) }}</span>
            </div>
            <div class="flex justify-between items-center py-2 border-b border-gray-100">
              <span class="text-gray-600">总负债（万）</span>
              <span class="font-semibold">{{ formatNumberInWan(financialData.fundamental.total_debt) }}</span>
            </div>
            <div class="flex justify-between items-center py-2 border-b border-gray-100">
              <span class="text-gray-600">资产负债率</span>
              <span class="font-semibold">{{ formatPercent(financialData.fundamental.debt_ratio) }}</span>
            </div>
            <div class="flex justify-between items-center py-2">
              <span class="text-gray-600">经营现金流（万）</span>
              <span class="font-semibold">{{ formatNumberInWan(financialData.fundamental.op_cf) }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 原始数据（可展开） -->
      <div v-if="financialData.raw_payload" class="bg-white rounded-lg shadow p-6">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-lg font-bold">📋 原始数据</h3>
          <button
            @click="showRawData = !showRawData"
            class="text-sm text-blue-600 hover:text-blue-700"
          >
            {{ showRawData ? '收起' : '展开' }}
          </button>
        </div>
        <div v-if="showRawData" class="bg-gray-50 rounded p-4 overflow-auto max-h-96">
          <pre class="text-xs text-gray-700">{{ JSON.stringify(financialData.raw_payload, null, 2) }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import axios from 'axios'
import CompanyProfileWidget from '../components/CompanyProfileWidget.vue'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''
const route = useRoute()

const tsCode = ref('')
const endDate = ref('')
const loading = ref(false)
const error = ref(null)
const financialData = ref(null)
const showRawData = ref(false)

// 列表相关
const financialList = ref([])
const listLoading = ref(false)
const pagination = ref(null)
const listFilter = ref({
  ts_code: '',
  stock_name: '',
  industry: ''
})
// 排序：order_by 对应后端字段，order_desc true=降序
const sortOrder = ref({ order_by: 'net_margin', order_desc: true })

// 加载财务数据
async function loadFinancialData() {
  if (!tsCode.value) {
    error.value = '请输入股票代码'
    return
  }

  loading.value = true
  error.value = null
  financialData.value = null

  try {
    const params = {}
    if (endDate.value) {
      params.end_date = endDate.value
    }

    const response = await axios.get(
      `${API_BASE_URL}/api/data-warehouse/stock-financial/${tsCode.value}`,
      { params }
    )

    if (response.data.success) {
      financialData.value = response.data
    } else {
      error.value = response.data.message || '获取财务数据失败'
    }
  } catch (err) {
    console.error('加载财务数据失败:', err)
    error.value = err.response?.data?.detail || err.message || '加载财务数据失败'
  } finally {
    loading.value = false
  }
}

// 按日期加载财务数据
function loadFinancialDataByDate(date) {
  endDate.value = date
  loadFinancialData()
}

// 格式化百分比
function formatPercent(value) {
  if (value === null || value === undefined) return '--'
  return (value * 100).toFixed(2) + '%'
}

// 格式化数字（亿元/万元，支持负数）
function formatNumber(value) {
  if (value === null || value === undefined) return '--'
  const absVal = Math.abs(value)
  const sign = value < 0 ? '-' : ''
  if (absVal >= 100000000) {
    return sign + (absVal / 100000000).toFixed(2)
  } else if (absVal >= 10000) {
    return sign + (absVal / 10000).toFixed(2)
  }
  return value.toFixed(2)
}

// 格式化数字（万元为单位，支持负数）
function formatNumberInWan(value) {
  if (value === null || value === undefined) return '--'
  const absVal = Math.abs(value)
  const sign = value < 0 ? '-' : ''
  return sign + (absVal / 10000).toFixed(2)
}

// 加载财务数据列表
async function loadFinancialList() {
  listLoading.value = true
  
  try {
    const params = {
      page: pagination.value?.page || 1,
      page_size: 20,
      order_by: sortOrder.value.order_by,
      order_desc: sortOrder.value.order_desc
    }
    
    if (listFilter.value.ts_code) {
      params.ts_code = listFilter.value.ts_code
    }
    if (listFilter.value.stock_name) {
      params.stock_name = listFilter.value.stock_name
    }
    if (listFilter.value.industry) {
      params.industry = listFilter.value.industry
    }
    
    const response = await axios.get(
      `${API_BASE_URL}/api/data-warehouse/stock-financial-list`,
      { params }
    )
    
    if (response.data.success) {
      financialList.value = response.data.data
      pagination.value = response.data.pagination
    } else {
      financialList.value = []
      pagination.value = null
    }
  } catch (err) {
    console.error('加载财务数据列表失败:', err)
    financialList.value = []
    pagination.value = null
  } finally {
    listLoading.value = false
  }
}

// 切换排序：点击表头时切换或设置排序
function handleSort(field) {
  if (sortOrder.value.order_by === field) {
    sortOrder.value.order_desc = !sortOrder.value.order_desc
  } else {
    sortOrder.value.order_by = field
    sortOrder.value.order_desc = true
  }
  if (pagination.value) pagination.value.page = 1
  loadFinancialList()
}

// 排序图标
function sortIcon(field) {
  if (sortOrder.value.order_by !== field) return '↕'
  return sortOrder.value.order_desc ? '↓' : '↑'
}

// 切换页码
function changePage(page) {
  if (!pagination.value) return
  pagination.value.page = page
  loadFinancialList()
}

// 查看详情
function viewDetail(code, date) {
  tsCode.value = code
  endDate.value = date || ''
  loadFinancialData()
  // 滚动到详情区域
  setTimeout(() => {
    document.querySelector('.container')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, 100)
}

// 页面加载时自动加载列表
loadFinancialList()

onMounted(() => {
  const code = route.query?.code
  if (code && typeof code === 'string') {
    const trimmed = code.trim()
    // 支持 000788 或 000788.SZ 格式
    tsCode.value = /^\d{6}\.(SH|SZ|BJ)$/i.test(trimmed) ? trimmed : `${trimmed}.${trimmed.startsWith('6') ? 'SH' : 'SZ'}`
    listFilter.value.ts_code = trimmed.replace(/\.(SH|SZ|BJ)$/i, '')
    loadFinancialData()
  }
})
</script>
