<template>
  <div class="container mx-auto px-4 py-6">
    <!-- 页面标题 -->
    <div class="mb-6">
      <h1 class="text-2xl font-bold text-gray-800 mb-2">💰 大额资金净流入</h1>
      <p class="text-sm text-gray-500">
        每日主力净流入超过指定阈值的股票列表（数据来自 fact_money_flow）
      </p>
    </div>

    <!-- 筛选栏 -->
    <div class="mb-6 bg-white rounded-lg shadow p-4">
      <div class="flex items-center gap-4 flex-wrap">
        <div class="flex items-center gap-2">
          <label class="text-sm text-gray-600 font-medium">交易日期：</label>
          <input
            v-model="tradeDate"
            type="date"
            class="px-3 py-2 border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <div class="flex items-center gap-2">
          <label class="text-sm text-gray-600 font-medium">最小净流入（亿）：</label>
          <input
            v-model.number="minAmountYi"
            type="number"
            min="1"
            max="500"
            step="5"
            class="px-3 py-2 border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 w-24"
          />
        </div>
        <button
          @click="loadData"
          :disabled="loading"
          class="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-400 text-sm"
        >
          {{ loading ? '加载中...' : '查询' }}
        </button>
        <button
          @click="triggerMoneyFlowUpdate"
          :disabled="updateTriggering"
          class="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:bg-gray-400 text-sm"
          title="从 Tushare 拉取个股主力资金流向，写入 fact_money_flow（任务名：money_flow_update）"
        >
          {{ updateTriggering ? '执行中...' : '更新资金流向' }}
        </button>
      </div>
    </div>

    <!-- 数据表格 -->
    <div class="bg-white rounded-lg shadow overflow-hidden">
      <div v-if="loading" class="p-8 text-center text-gray-500">加载中...</div>
      <div v-else-if="error" class="p-8 text-center text-red-600">{{ error }}</div>
      <div v-else-if="list.length === 0" class="p-8 text-center text-gray-500">
        <p class="mb-2">暂无数据</p>
        <p class="text-sm mb-2">请先点击「更新资金流向」拉取数据（任务约 1–2 分钟）</p>
        <p class="text-xs">或选择前一交易日（如 {{ prevTradeDateStr }}）查询，当日数据通常在收盘后才有</p>
      </div>
      <div v-else class="overflow-x-auto">
        <table class="min-w-full divide-y divide-gray-200">
          <thead class="bg-gray-50">
            <tr>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">序号</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">股票</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">行业</th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">净流入(亿)</th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">净流入占比(%)</th>
              <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">操作</th>
            </tr>
          </thead>
          <tbody class="bg-white divide-y divide-gray-200">
            <tr v-for="(item, idx) in list" :key="item.ts_code" class="hover:bg-gray-50">
              <td class="px-4 py-3 text-sm text-gray-500">{{ idx + 1 }}</td>
              <td class="px-4 py-3">
                <router-link :to="'/diagnose?code=' + (item.ts_code?.replace('.', '') || '')" class="text-blue-600 hover:underline font-medium">
                  {{ item.stock_name || item.ts_code }}
                </router-link>
                <span class="text-gray-500 text-xs ml-1">{{ item.ts_code }}</span>
              </td>
              <td class="px-4 py-3 text-sm text-gray-600">{{ item.industry || '-' }}</td>
              <td class="px-4 py-3 text-right text-sm font-semibold text-red-600">{{ item.main_net_inflow_yi?.toFixed(2) || '-' }}</td>
              <td class="px-4 py-3 text-right text-sm text-gray-600">{{ item.main_net_inflow_rate != null ? item.main_net_inflow_rate.toFixed(2) + '%' : '-' }}</td>
              <td class="px-4 py-3 text-center">
                <button
                  @click="addToWatchlist(item)"
                  class="text-blue-600 hover:text-blue-800 text-xs"
                >
                  加入跟踪
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="list.length > 0" class="px-4 py-2 bg-gray-50 text-xs text-gray-500">
        共 {{ list.length }} 只 · 数据日期：{{ tradeDate }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

const list = ref([])
const loading = ref(false)
const error = ref('')
const tradeDate = ref('')
const minAmountYi = ref(30)
const updateTriggering = ref(false)

function formatToday() {
  const d = new Date()
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0')
}
// 前一交易日（简单按工作日估算）
const prevTradeDateStr = (() => {
  const d = new Date()
  let back = 1
  if (d.getDay() === 1) back = 3  // 周一则退回上周五
  else if (d.getDay() === 0) back = 2
  d.setDate(d.getDate() - back)
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0')
})()

async function loadData() {
  loading.value = true
  error.value = ''
  try {
    const params = { min_amount_yi: minAmountYi.value }
    if (tradeDate.value) params.trade_date = tradeDate.value
    const res = await axios.get(`${API_BASE_URL}/api/money-flow/heavy-inflow`, { params })
    if (res.data.success) {
      list.value = res.data.data || []
    } else {
      error.value = res.data.detail || '加载失败'
    }
  } catch (e) {
    error.value = e.response?.data?.detail || e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

let _autoRefreshTimer = null
async function triggerMoneyFlowUpdate() {
  if (updateTriggering.value) return
  updateTriggering.value = true
  try {
    await axios.post(`${API_BASE_URL}/api/scheduled-task/money_flow_update/trigger`)
    alert('任务已触发（约 1–2 分钟），完成后请点击「查询」刷新')
    if (_autoRefreshTimer) clearTimeout(_autoRefreshTimer)
    _autoRefreshTimer = setTimeout(() => loadData(), 60000)  // 60秒后自动刷新
  } catch (e) {
    alert('触发失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    updateTriggering.value = false
  }
}
onUnmounted(() => {
  if (_autoRefreshTimer) clearTimeout(_autoRefreshTimer)
})

async function addToWatchlist(item) {
  try {
    if (!item.ts_code) return
    await axios.post(`${API_BASE_URL}/api/watchlist`, { ts_code: item.ts_code })
    alert('已加入跟踪')
  } catch (e) {
    alert('操作失败: ' + (e.response?.data?.detail || e.message))
  }
}

onMounted(() => {
  tradeDate.value = formatToday()
  loadData()
})
</script>
