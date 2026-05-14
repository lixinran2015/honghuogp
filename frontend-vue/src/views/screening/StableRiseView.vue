<template>
  <div class="container mx-auto px-4 py-6">
    <!-- 页面标题 -->
    <div class="mb-6">
      <h1 class="text-2xl font-bold text-gray-800 mb-2">📈 止跌企稳回升</h1>
      <p class="text-sm text-gray-500">
        前期新高股票回踩 10%~25% 后再次站上 10 日线，适合纳入跟踪
      </p>
    </div>

    <!-- 操作栏 -->
    <div class="mb-6 bg-white rounded-lg shadow p-4">
      <div class="flex flex-wrap items-center gap-4">
        <button
          @click="loadData"
          :disabled="loading"
          class="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-400 text-sm"
        >
          {{ loading ? '加载中...' : '刷新' }}
        </button>
        <button
          @click="updateS2Pool"
          :disabled="updating"
          class="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:bg-gray-400 text-sm"
          title="重新计算 S2 股票池（需先有 S1 和主板池）"
        >
          {{ updating ? '更新中...' : '更新 S2 池' }}
        </button>
        <button
          v-if="list.length > 0"
          @click="addAllToWatchlist"
          :disabled="addingAll"
          class="px-4 py-2 bg-purple-600 text-white rounded hover:bg-purple-700 disabled:bg-gray-400 text-sm"
          :title="`将 ${list.length} 只股票加入跟踪`"
        >
          {{ addingAll ? '添加中...' : `一键加入跟踪 (${list.length})` }}
        </button>
      </div>
      <div v-if="list.length > 0" class="mt-2 text-xs text-gray-500">
        共 {{ list.length }} 只 · 数据日期：{{ dateStr }}
      </div>
    </div>

    <!-- 数据表格 -->
    <div class="bg-white rounded-lg shadow overflow-hidden">
      <div v-if="loading && list.length === 0" class="p-8 text-center text-gray-500">加载中...</div>
      <div v-else-if="error" class="p-8 text-center text-red-600">{{ error }}</div>
      <div v-else-if="list.length === 0" class="p-8 text-center text-gray-500">
        暂无数据。请先点击「更新 S2 池」生成股票池（需已更新主板池和 S1 池）
      </div>
      <div v-else class="overflow-x-auto">
        <table class="min-w-full divide-y divide-gray-200">
          <thead class="bg-gray-50">
            <tr>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">序号</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">股票</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">行业</th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">最新价</th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">涨跌幅</th>
              <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">操作</th>
            </tr>
          </thead>
          <tbody class="bg-white divide-y divide-gray-200">
            <tr v-for="(item, idx) in list" :key="item.ts_code || item.code" class="hover:bg-gray-50">
              <td class="px-4 py-3 text-sm text-gray-500">{{ idx + 1 }}</td>
              <td class="px-4 py-3">
                <router-link :to="'/diagnose?code=' + (item.code || item.代码 || '').replace(/\.(SH|SZ|BJ)$/, '')" class="text-blue-600 hover:underline font-medium">
                  {{ item.name || item.名称 || item.股票名称 || item.stock_name || '-' }}
                </router-link>
                <span class="text-gray-500 text-xs ml-1">{{ item.code || item.代码 || item.ts_code }}</span>
              </td>
              <td class="px-4 py-3 text-sm text-gray-600">{{ item.行业 || item.sector || '-' }}</td>
              <td class="px-4 py-3 text-right text-sm">{{ formatPrice(item) }}</td>
              <td class="px-4 py-3 text-right">
                <span :class="getChangeClass(item)">
                  {{ formatChange(item) }}
                </span>
              </td>
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
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

const list = ref([])
const loading = ref(false)
const error = ref('')
const dateStr = ref('')
const updating = ref(false)
const addingAll = ref(false)

function getTsCode(item) {
  return item.ts_code || (item.code ? (item.code.startsWith('6') ? item.code + '.SH' : item.code + '.SZ') : null)
}

function formatPrice(item) {
  const p = item.close ?? item.收盘价 ?? item.price
  return p != null ? Number(p).toFixed(2) : '-'
}

function formatChange(item) {
  const pct = item.pct_chg ?? item.涨跌幅 ?? item.change_pct
  if (pct == null) return '-'
  const v = Number(pct)
  const sign = v >= 0 ? '+' : ''
  return `${sign}${v.toFixed(2)}%`
}

function getChangeClass(item) {
  const pct = item.pct_chg ?? item.涨跌幅 ?? item.change_pct
  if (pct == null) return 'text-gray-500'
  const v = Number(pct)
  return v >= 0 ? 'text-red-600 font-medium' : 'text-green-600'
}

async function loadData() {
  loading.value = true
  error.value = ''
  try {
    const res = await axios.get(`${API_BASE_URL}/api/stock-universe/stocks/detail`, {
      params: { universe_type: 's2', limit: 500 }
    })
    list.value = res.data.stocks || []
    dateStr.value = res.data.date || ''
  } catch (e) {
    error.value = e.response?.data?.detail || e.message || '加载失败'
    list.value = []
  } finally {
    loading.value = false
  }
}

async function updateS2Pool() {
  updating.value = true
  try {
    await axios.post(`${API_BASE_URL}/api/stock-universe/update`, null, {
      params: { universe_type: 's2', force_refresh: true }
    })
    await loadData()
  } catch (e) {
    alert('更新失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    updating.value = false
  }
}

async function addToWatchlist(item) {
  const tsCode = getTsCode(item)
  if (!tsCode) return
  try {
    await axios.post(`${API_BASE_URL}/api/watchlist`, { ts_code: tsCode })
    alert('已加入跟踪')
  } catch (e) {
    alert('操作失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function addAllToWatchlist() {
  if (list.value.length === 0) return
  addingAll.value = true
  let added = 0
  let failed = 0
  try {
    for (const item of list.value) {
      const tsCode = getTsCode(item)
      if (!tsCode) continue
      try {
        await axios.post(`${API_BASE_URL}/api/watchlist`, { ts_code: tsCode })
        added++
      } catch {
        failed++
      }
    }
    alert(`已加入跟踪 ${added} 只${failed > 0 ? `，${failed} 只已存在或失败` : ''}`)
  } finally {
    addingAll.value = false
  }
}

onMounted(() => loadData())
</script>
