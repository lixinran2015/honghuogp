<template>
  <div class="company-profile bg-white rounded-lg shadow overflow-hidden">
    <div class="px-4 py-3 border-b border-gray-200 bg-gray-50">
      <h3 class="text-base font-semibold text-gray-800">公司简介 / 财务概览</h3>
    </div>
    <div class="p-4">
      <!-- 加载中 -->
      <div v-if="loading" class="text-center py-8 text-gray-500 text-sm">加载中...</div>

      <!-- 无数据 -->
      <div v-else-if="!data && !error" class="text-center py-6 text-gray-500 text-sm">
        <p>暂无公司简介与财务数据</p>
        <router-link
          v-if="tsCode"
          :to="{ path: '/stock-financial', query: { code: tsCode } }"
          class="mt-2 inline-block text-blue-600 hover:underline text-xs"
        >
          前往财务数据页查看 →
        </router-link>
      </div>

      <!-- 错误 -->
      <div v-else-if="error" class="text-center py-6 text-amber-600 text-sm">
        {{ error }}
      </div>

      <!-- 有数据 -->
      <div v-else class="space-y-4">
        <!-- 基本信息 -->
        <div class="grid grid-cols-2 gap-3">
          <div>
            <div class="text-xs text-gray-500">公司名称</div>
            <div class="text-sm font-medium text-gray-800">{{ data.stock?.name || '-' }}</div>
          </div>
          <div>
            <div class="text-xs text-gray-500">行业</div>
            <div class="text-sm font-medium text-gray-800">{{ data.stock?.industry || '-' }}</div>
          </div>
          <div>
            <div class="text-xs text-gray-500">交易所</div>
            <div class="text-sm font-medium text-gray-800">{{ exchangeLabel(data.stock?.exchange) }}</div>
          </div>
          <div>
            <div class="text-xs text-gray-500">报告期</div>
            <div class="text-sm font-medium text-gray-800">{{ data.fundamental?.end_date || '-' }} {{ reportTypeLabel(data.fundamental?.report_type) }}</div>
          </div>
        </div>

        <!-- 财务指标 -->
        <div class="border-t border-gray-100 pt-3">
          <div class="text-xs text-gray-500 mb-2">核心指标</div>
          <div class="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <div class="p-2 bg-blue-50 rounded">
              <div class="text-xs text-gray-600">ROE</div>
              <div class="text-sm font-bold text-blue-700">{{ formatPct(data.fundamental?.roe) }}</div>
            </div>
            <div class="p-2 bg-green-50 rounded">
              <div class="text-xs text-gray-600">毛利率</div>
              <div class="text-sm font-bold text-green-700">{{ formatPct(data.fundamental?.gross_margin) }}</div>
            </div>
            <div class="p-2 bg-purple-50 rounded">
              <div class="text-xs text-gray-600">净利率</div>
              <div class="text-sm font-bold text-purple-700">{{ formatPct(data.fundamental?.net_margin) }}</div>
            </div>
            <div class="p-2 bg-amber-50 rounded">
              <div class="text-xs text-gray-600">营收增速</div>
              <div class="text-sm font-bold text-amber-700">{{ formatPct(data.fundamental?.revenue_growth) }}</div>
            </div>
            <div class="p-2 bg-gray-50 rounded">
              <div class="text-xs text-gray-600">营收(亿)</div>
              <div class="text-sm font-bold text-gray-800">{{ formatNum(data.fundamental?.revenue) }}</div>
            </div>
            <div class="p-2 bg-gray-50 rounded">
              <div class="text-xs text-gray-600">净现比（经营现金流/净利润）</div>
              <div class="text-sm font-bold text-gray-800">{{ formatPct(netCashRatio) }}</div>
            </div>
          </div>
        </div>

        <router-link
          v-if="tsCode"
          :to="{ path: '/stock-financial', query: { code: tsCode } }"
          class="inline-block text-blue-600 hover:underline text-xs"
        >
          查看完整财务数据 →
        </router-link>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, computed } from 'vue'
import axios from 'axios'

const props = defineProps({
  tsCode: { type: String, default: '' }
})

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

const loading = ref(false)
const data = ref(null)
const error = ref(null)

watch(
  () => props.tsCode,
  async (val) => {
    if (!val || !/^\d{6}\.(SH|SZ|BJ)$/i.test(val.trim())) {
      data.value = null
      error.value = null
      return
    }
    loading.value = true
    data.value = null
    error.value = null
    try {
      const res = await axios.get(`${API_BASE_URL}/api/data-warehouse/stock-financial/${val}`)
      if (res.data?.success && res.data?.stock) {
        data.value = res.data
      } else {
        data.value = null
        error.value = res.data?.message || '未找到财务数据'
      }
    } catch (e) {
      data.value = null
      error.value = e.response?.data?.detail || e.message || '加载失败'
    } finally {
      loading.value = false
    }
  },
  { immediate: true }
)

// 净现比：使用当前报表口径的 经营现金流 / 净利润
const netCashRatio = computed(() => {
  const f = data.value?.fundamental
  if (!f || f.op_cf == null || f.net_profit == null) return null
  const opCf = Number(f.op_cf)
  const netProfit = Number(f.net_profit)
  if (!Number.isFinite(opCf) || !Number.isFinite(netProfit) || netProfit <= 0) return null
  return opCf / netProfit
})

function formatPct(val) {
  if (val == null) return '-'
  const v = Number(val)
  if (Number.isNaN(v)) return '-'
  return (v * 100).toFixed(2) + '%'
}

function formatNum(val) {
  if (val == null) return '-'
  const v = Number(val)
  if (Number.isNaN(v)) return '-'
  if (v >= 1e8) return (v / 1e8).toFixed(2) + '亿'
  if (v >= 1e4) return (v / 1e4).toFixed(2) + '万'
  return v.toFixed(2)
}

function exchangeLabel(ex) {
  const m = { SSE: '上交所', SZSE: '深交所', BSE: '北交所' }
  return m[ex] || ex || '-'
}

function reportTypeLabel(rt) {
  const m = { annual: '年报', q1: '一季报', q2: '半年报', q3: '三季报' }
  return m[rt] || rt || ''
}
</script>
