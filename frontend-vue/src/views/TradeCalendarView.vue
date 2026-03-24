<template>
  <div class="container mx-auto px-4 py-6">
    <div class="mb-6 flex items-start justify-between flex-wrap gap-4">
      <div>
        <h1 class="text-2xl font-bold text-gray-800 dark:text-gray-100">交易日历</h1>
        <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">A股交易日与休市日（数据源：dim_trade_calendar）</p>
      </div>
      <div class="flex items-center gap-3">
        <div class="flex gap-2">
          <input
            v-model="startDate"
            type="date"
            class="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-800"
          />
          <span class="self-center text-gray-500">至</span>
          <input
            v-model="endDate"
            type="date"
            class="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-800"
          />
        </div>
        <select
          v-model="filterOpen"
          class="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-800"
        >
          <option :value="null">全部</option>
          <option :value="true">仅交易日</option>
          <option :value="false">仅休市日</option>
        </select>
        <button
          @click="loadData"
          :disabled="loading"
          class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm"
        >
          {{ loading ? '加载中...' : '查询' }}
        </button>
      </div>
    </div>

    <div v-if="error" class="mb-4 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-red-700 dark:text-red-400">
      {{ error }}
    </div>

    <!-- 列表视图 -->
    <div v-if="!loading && items.length > 0" class="mt-6 bg-white dark:bg-gray-800 rounded-lg shadow overflow-hidden dark:border dark:border-gray-700">
      <div class="px-4 py-3 border-b border-gray-200 dark:border-gray-700">
        <h2 class="font-semibold text-gray-800 dark:text-gray-200">日期明细（共 {{ items.length }} 天）</h2>
      </div>
      <div class="max-h-96 overflow-y-auto">
        <div
          v-for="item in items"
          :key="item.trade_date"
          :class="[
            'px-4 py-2 flex items-center justify-between border-b border-gray-100 dark:border-gray-700/50 last:border-0',
            item.is_open ? 'bg-white dark:bg-gray-800' : 'bg-gray-50 dark:bg-gray-800/50'
          ]"
        >
          <span class="font-mono text-sm">{{ item.trade_date }}</span>
          <span
            :class="[
              'px-2 py-0.5 rounded text-xs',
              item.is_open
                ? 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-400'
                : 'bg-gray-200 dark:bg-gray-600 text-gray-600 dark:text-gray-400'
            ]"
          >
            {{ item.is_open ? '交易日' : '休市' }}
          </span>
        </div>
      </div>
    </div>

    <div v-else-if="!loading" class="text-center py-12 text-gray-500 dark:text-gray-400">
      暂无数据，请调整日期范围或点击「查询」加载
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''
const loading = ref(false)
const error = ref('')
const items = ref([])
const startDate = ref('')
const endDate = ref('')

const filterOpen = ref(null)

function initDates() {
  const d = new Date()
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  startDate.value = `${y}-${m}-01`
  const lastDay = new Date(y, d.getMonth() + 1, 0)
  endDate.value = `${y}-${String(lastDay.getMonth() + 1).padStart(2, '0')}-${String(lastDay.getDate()).padStart(2, '0')}`
}

async function loadData() {
  loading.value = true
  error.value = ''
  try {
    const params = { start_date: startDate.value, end_date: endDate.value }
    if (filterOpen.value !== null) params.is_open = filterOpen.value
    const res = await axios.get(`${API_BASE}/api/data-warehouse/trade-calendar`, { params })
    if (res.data?.success) {
      items.value = res.data.data || []
    } else {
      items.value = []
      error.value = res.data?.message || '加载失败'
    }
  } catch (e) {
    error.value = e.response?.data?.detail || e.message || '加载失败'
    items.value = []
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  initDates()
  loadData()
})
</script>
