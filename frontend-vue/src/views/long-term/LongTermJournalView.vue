<template>
  <div class="p-4 lg:p-6 bg-warm-50 min-h-screen">
    <!-- 标题区 -->
    <div class="mb-6 flex items-center justify-between flex-wrap gap-3">
      <div>
        <h1 class="text-xl font-bold text-warmgray-900">投资日志</h1>
        <p class="text-sm text-warmgray-500 mt-1">强制留痕：记录每一笔买入、加仓、减仓、卖出操作</p>
      </div>
      <button
        @click="showForm = !showForm"
        class="px-4 py-1.5 bg-cta text-white text-sm font-medium rounded-md hover:bg-cta/90 transition-colors"
      >
        {{ showForm ? '取消' : '+ 新增记录' }}
      </button>
    </div>

    <!-- 统计 -->
    <div v-if="stats" class="mb-4 grid grid-cols-4 md:grid-cols-6 gap-3">
      <div class="bg-white rounded-lg border border-border p-3">
        <div class="text-xs text-warmgray-500">总记录</div>
        <div class="text-lg font-semibold text-warmgray-900">{{ stats.total_entries }}</div>
      </div>
      <div v-for="(count, action) in stats.by_action" :key="action" class="bg-white rounded-lg border border-border p-3">
        <div class="text-xs text-warmgray-500">{{ actionLabel(action) }}</div>
        <div class="text-lg font-semibold text-cta">{{ count }}</div>
      </div>
    </div>

    <!-- 新增表单 -->
    <div v-if="showForm" class="mb-4 bg-white rounded-lg border border-border p-4">
      <h3 class="text-sm font-semibold text-warmgray-700 mb-3">新增投资记录</h3>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div class="relative">
          <label class="block text-xs text-warmgray-500 mb-1">股票代码</label>
          <input
            v-model="searchKeyword"
            @input="onSearchInput"
            @keydown.down.prevent="highlightNext"
            @keydown.up.prevent="highlightPrev"
            @keydown.enter.prevent="selectHighlighted"
            @blur="hideDropdownSoon"
            @focus="onSearchFocus"
            type="text"
            class="w-full px-3 py-2 text-sm border border-border rounded-md"
            placeholder="输入代码或名称搜索..."
          />
          <!-- 下拉结果 -->
          <div v-if="showDropdown && searchResults.length" class="absolute z-50 left-0 right-0 mt-1 bg-white border border-border rounded-md shadow-lg max-h-60 overflow-y-auto">
            <div
              v-for="(stock, idx) in searchResults"
              :key="stock.ts_code"
              @mousedown.prevent="selectStock(stock)"
              :class="[
                'px-3 py-2 cursor-pointer text-sm flex items-center justify-between',
                idx === highlightedIndex ? 'bg-warm-100' : 'hover:bg-warm-50'
              ]"
            >
              <span>
                <span class="font-medium text-warmgray-900">{{ stock.name }}</span>
                <span class="text-xs text-warmgray-500 ml-1">{{ stock.ts_code }}</span>
              </span>
              <span v-if="stock.industry" class="text-xs text-warmgray-400">{{ stock.industry }}</span>
            </div>
          </div>
          <div v-if="selectedStockName" class="mt-1 text-xs text-warmgray-500">
            已选: {{ selectedStockName }}
          </div>
        </div>
        <div>
          <label class="block text-xs text-warmgray-500 mb-1">操作</label>
          <select v-model="form.action" class="w-full px-3 py-2 text-sm border border-border rounded-md">
            <option value="buy">买入</option>
            <option value="add">加仓</option>
            <option value="reduce">减仓</option>
            <option value="sell">卖出</option>
            <option value="hold_review">持仓复盘</option>
          </select>
        </div>
        <div>
          <label class="block text-xs text-warmgray-500 mb-1">日期</label>
          <input v-model="form.trade_date" type="date" class="w-full px-3 py-2 text-sm border border-border rounded-md" />
        </div>
        <div>
          <label class="block text-xs text-warmgray-500 mb-1">价格</label>
          <input v-model.number="form.price" type="number" step="0.01" class="w-full px-3 py-2 text-sm border border-border rounded-md" placeholder="0.00" />
        </div>
        <div>
          <label class="block text-xs text-warmgray-500 mb-1">股数</label>
          <input v-model.number="form.shares" type="number" class="w-full px-3 py-2 text-sm border border-border rounded-md" placeholder="0" />
        </div>
        <div>
          <label class="block text-xs text-warmgray-500 mb-1">权重变动</label>
          <input v-model.number="form.weight_change" type="number" step="0.0001" class="w-full px-3 py-2 text-sm border border-border rounded-md" placeholder="0.05 = 5%" />
        </div>
        <div>
          <label class="block text-xs text-warmgray-500 mb-1">Darwin评分</label>
          <input v-model.number="form.darwin_score" type="number" step="0.1" class="w-full px-3 py-2 text-sm border border-border rounded-md" placeholder="0-100" />
        </div>
        <div>
          <label class="block text-xs text-warmgray-500 mb-1">PE分位</label>
          <input v-model.number="form.pe_percentile" type="number" step="0.01" class="w-full px-3 py-2 text-sm border border-border rounded-md" placeholder="0-1" />
        </div>
        <div class="col-span-2">
          <label class="block text-xs text-warmgray-500 mb-1">投资逻辑 / 卖出理由</label>
          <input v-model="form.reason" type="text" class="w-full px-3 py-2 text-sm border border-border rounded-md" placeholder="记录当时的决策依据..." />
        </div>
        <div class="col-span-2 flex items-end">
          <button
            @click="submitForm"
            :disabled="submitting"
            class="px-4 py-2 bg-cta text-white text-sm font-medium rounded-md hover:bg-cta/90 disabled:opacity-50"
          >
            {{ submitting ? '保存中...' : '保存记录' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 日志列表 -->
    <div class="bg-white rounded-lg border border-border overflow-hidden">
      <div class="px-4 py-3 border-b border-border bg-warmgray-50 flex items-center justify-between">
        <h3 class="text-sm font-semibold text-warmgray-700">历史记录</h3>
        <div class="flex items-center gap-2">
          <select v-model="filterAction" class="px-2 py-1 text-xs border border-border rounded bg-white">
            <option value="">全部操作</option>
            <option value="buy">买入</option>
            <option value="add">加仓</option>
            <option value="reduce">减仓</option>
            <option value="sell">卖出</option>
            <option value="hold_review">持仓复盘</option>
          </select>
        </div>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="bg-warmgray-50 border-b border-border">
              <th class="px-4 py-3 text-left font-semibold text-warmgray-700">日期</th>
              <th class="px-4 py-3 text-left font-semibold text-warmgray-700">股票</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">操作</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">价格</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">股数</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">权重变动</th>
              <th class="px-4 py-3 text-left font-semibold text-warmgray-700">理由</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">Darwin</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">PE分位</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="entry in filteredEntries"
              :key="entry.id"
              class="border-b border-border hover:bg-warm-50 transition-colors"
            >
              <td class="px-4 py-3 text-warmgray-600">{{ entry.trade_date }}</td>
              <td class="px-4 py-3">
                <div class="font-medium text-warmgray-900">{{ entry.name || entry.ts_code }}</div>
                <div v-if="entry.name && entry.name !== entry.ts_code" class="text-xs text-warmgray-500">{{ entry.ts_code }}</div>
              </td>
              <td class="px-4 py-3 text-center">
                <span class="px-2 py-0.5 rounded text-xs font-medium" :class="actionClass(entry.action)">
                  {{ actionLabel(entry.action) }}
                </span>
              </td>
              <td class="px-4 py-3 text-center text-warmgray-700">{{ entry.price?.toFixed(2) || '-' }}</td>
              <td class="px-4 py-3 text-center text-warmgray-700">{{ entry.shares || '-' }}</td>
              <td class="px-4 py-3 text-center">
                <span v-if="entry.weight_change != null" :class="entry.weight_change > 0 ? 'text-profit' : 'text-loss'">
                  {{ entry.weight_change > 0 ? '+' : '' }}{{ (entry.weight_change * 100).toFixed(1) }}%
                </span>
                <span v-else>-</span>
              </td>
              <td class="px-4 py-3 text-warmgray-600 max-w-xs truncate">{{ entry.reason || '-' }}</td>
              <td class="px-4 py-3 text-center">
                <span class="font-semibold" :class="scoreClass(entry.darwin_score)">{{ entry.darwin_score || '-' }}</span>
              </td>
              <td class="px-4 py-3 text-center">
                <span v-if="entry.pe_percentile != null" :class="percentileClass(entry.pe_percentile)">
                  {{ (entry.pe_percentile * 100).toFixed(0) }}%
                </span>
                <span v-else>-</span>
              </td>
            </tr>
            <tr v-if="filteredEntries.length === 0">
              <td colspan="9" class="px-4 py-8 text-center text-warmgray-500">
                {{ loading ? '加载中...' : '暂无记录' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

const loading = ref(false)
const submitting = ref(false)
const showForm = ref(false)
const entries = ref([])
const stats = ref(null)
const filterAction = ref('')

// 股票搜索自动补全状态
const searchKeyword = ref('')
const searchResults = ref([])
const showDropdown = ref(false)
const searchLoading = ref(false)
const highlightedIndex = ref(-1)
const selectedStockName = ref('')
const searchTimer = ref(null)

const form = ref({
  ts_code: '',
  action: 'buy',
  trade_date: new Date().toISOString().split('T')[0],
  price: null,
  shares: null,
  weight_change: null,
  reason: '',
  darwin_score: null,
  pe_percentile: null,
})

// ── 股票搜索 ──

function onSearchInput() {
  if (searchTimer.value) clearTimeout(searchTimer.value)
  highlightedIndex.value = -1
  if (!searchKeyword.value.trim()) {
    searchResults.value = []
    showDropdown.value = false
    return
  }
  searchTimer.value = setTimeout(() => doSearch(searchKeyword.value.trim()), 200)
}

function onSearchFocus() {
  if (searchResults.value.length && searchKeyword.value.trim()) {
    showDropdown.value = true
  }
}

function hideDropdownSoon() {
  setTimeout(() => { showDropdown.value = false }, 150)
}

async function doSearch(keyword) {
  searchLoading.value = true
  try {
    const response = await fetch(`${API_BASE_URL}/api/long-term/search-stock?keyword=${encodeURIComponent(keyword)}&limit=10`)
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const result = await response.json()
    if (result.success) {
      searchResults.value = result.data || []
      showDropdown.value = searchResults.value.length > 0
    } else {
      searchResults.value = []
      showDropdown.value = false
    }
  } catch (e) {
    console.error('搜索股票失败:', e)
    searchResults.value = []
    showDropdown.value = false
  } finally {
    searchLoading.value = false
  }
}

function highlightNext() {
  if (!searchResults.value.length) return
  highlightedIndex.value = (highlightedIndex.value + 1) % searchResults.value.length
}

function highlightPrev() {
  if (!searchResults.value.length) return
  highlightedIndex.value = (highlightedIndex.value - 1 + searchResults.value.length) % searchResults.value.length
}

function selectHighlighted() {
  if (highlightedIndex.value >= 0 && highlightedIndex.value < searchResults.value.length) {
    selectStock(searchResults.value[highlightedIndex.value])
  }
}

function selectStock(stock) {
  form.value.ts_code = stock.ts_code
  selectedStockName.value = stock.name
  searchKeyword.value = stock.ts_code
  showDropdown.value = false
  searchResults.value = []
  highlightedIndex.value = -1
}

const filteredEntries = computed(() => {
  if (!filterAction.value) return entries.value
  return entries.value.filter(e => e.action === filterAction.value)
})

async function fetchEntries() {
  loading.value = true
  try {
    const response = await fetch(`${API_BASE_URL}/api/long-term/journal?limit=100`)
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const result = await response.json()
    entries.value = result.entries || []
  } catch (e) {
    console.error('日志数据获取失败:', e)
  } finally {
    loading.value = false
  }
}

async function fetchStats() {
  try {
    const response = await fetch(`${API_BASE_URL}/api/long-term/journal/stats`)
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    stats.value = await response.json()
  } catch (e) {
    console.error('统计获取失败:', e)
  }
}

async function submitForm() {
  if (!form.value.ts_code || !form.value.trade_date) {
    alert('请填写股票代码和日期')
    return
  }
  submitting.value = true
  try {
    const response = await fetch(`${API_BASE_URL}/api/long-term/journal`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form.value),
    })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const result = await response.json()
    if (result.success) {
      showForm.value = false
      // 重置表单
      form.value = {
        ts_code: '',
        action: 'buy',
        trade_date: new Date().toISOString().split('T')[0],
        price: null,
        shares: null,
        weight_change: null,
        reason: '',
        darwin_score: null,
        pe_percentile: null,
      }
      searchKeyword.value = ''
      selectedStockName.value = ''
      searchResults.value = []
      showDropdown.value = false
      await fetchEntries()
      await fetchStats()
    } else {
      alert(result.message || '保存失败')
    }
  } catch (e) {
    console.error('保存日志失败:', e)
    alert('保存失败')
  } finally {
    submitting.value = false
  }
}

function actionLabel(action) {
  const map = {
    buy: '买入',
    add: '加仓',
    reduce: '减仓',
    sell: '卖出',
    hold_review: '复盘',
  }
  return map[action] || action
}

function actionClass(action) {
  const map = {
    buy: 'bg-profit/10 text-profit',
    add: 'bg-profit/10 text-profit',
    reduce: 'bg-cta/10 text-cta',
    sell: 'bg-loss/10 text-loss',
    hold_review: 'bg-warm-100 text-warmgray-600',
  }
  return map[action] || 'bg-warm-100 text-warmgray-600'
}

function scoreClass(score) {
  if (!score) return 'text-warmgray-400'
  if (score >= 70) return 'text-profit'
  if (score >= 50) return 'text-cta'
  return 'text-loss'
}

function percentileClass(p) {
  if (p <= 0.3) return 'text-profit font-medium'
  if (p <= 0.5) return 'text-cta font-medium'
  if (p <= 0.7) return 'text-warmgray-700'
  return 'text-loss font-medium'
}

onMounted(() => {
  fetchEntries()
  fetchStats()
})
</script>
