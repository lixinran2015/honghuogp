<template>
  <div class="p-8 space-y-8">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-semibold text-gray-900 mb-2">股票跟踪</h1>
        <p class="text-sm text-gray-500">实时监控股票，上涨超过2%语音提醒</p>
      </div>
      <div class="flex items-center gap-2">
        <input
          v-model="noteFilter"
          type="text"
          placeholder="按备注搜索..."
          class="px-3 py-1 border border-gray-300 rounded-md text-sm focus:ring-blue-500 focus:border-blue-500"
        />
        <Button size="sm" :variant="showSectors ? 'primary' : 'secondary'" @click="showSectors = !showSectors">
          {{ showSectors ? '🔽 隐藏板块' : '▶ 显示板块' }}
        </Button>
        <Button size="sm" :variant="autoRefresh ? 'primary' : 'secondary'" @click="toggleAutoRefresh">
          {{ autoRefresh ? '⏸ 暂停刷新' : '▶ 开启刷新' }}
        </Button>
        <Button size="sm" variant="secondary" @click="fetchRealtimeData" :disabled="loading">
          {{ loading ? '加载中...' : '刷新' }}
        </Button>
      </div>
    </div>

    <!-- 添加股票 -->
    <Card class="p-4">
      <div class="flex items-center gap-4 relative">
        <div class="flex-1 relative">
          <input
            v-model="newStockCode"
            type="text"
            class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            placeholder="输入股票代码或名称，如 300001 或 宁德时代"
            @input="searchStock"
            @keyup.enter="addStock"
            @blur="hideSearchResults"
          />
          <!-- 搜索结果下拉 -->
          <div v-if="searchResults.length > 0" class="absolute top-full left-0 right-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg z-10 max-h-60 overflow-y-auto">
            <div
              v-for="stock in searchResults"
              :key="stock.ts_code"
              class="px-4 py-2 hover:bg-gray-100 cursor-pointer flex justify-between"
              @mousedown="selectStock(stock)"
            >
              <span class="font-medium">{{ stock.name }}</span>
              <span class="text-gray-500">{{ stock.code }}</span>
            </div>
          </div>
        </div>
        <Button variant="primary" @click="addStock" :disabled="!newStockCode.trim()">
          + 添加跟踪
        </Button>
      </div>
    </Card>

    <!-- 统计信息 -->
    <div class="grid grid-cols-4 gap-4">
      <StatCard 
        :label="noteFilter ? '筛选结果' : '跟踪数量'" 
        :value="noteFilter ? sortedStocks.length : stocks.length" 
      />
      <StatCard label="上涨数量" :value="upCount" :change="upCount" />
      <StatCard label="下跌数量" :value="downCount" :change="-downCount" />
      <StatCard label="触发提醒" :value="alertCount" />
    </div>
    
    <!-- 筛选提示 -->
    <div v-if="noteFilter && sortedStocks.length < stocks.length" class="bg-blue-50 border border-blue-200 rounded-lg p-3">
      <p class="text-sm text-blue-800">
        🔍 按备注筛选中：找到 {{ sortedStocks.length }} 只股票（共 {{ stocks.length }} 只）
        <button @click="noteFilter = ''" class="ml-2 text-blue-600 hover:text-blue-800 underline">
          清除筛选
        </button>
      </p>
    </div>

    <!-- 语音提醒设置 -->
    <Card class="p-4 bg-yellow-50 border-yellow-200">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <span class="text-lg">🔔</span>
          <span class="font-medium text-gray-700">语音提醒</span>
          <span class="text-sm text-gray-500">上涨 ≥ {{ alertThreshold }}% 时提醒</span>
        </div>
        <div class="flex items-center gap-4">
          <label class="flex items-center gap-2">
            <input type="checkbox" v-model="voiceEnabled" class="rounded" />
            <span class="text-sm">启用语音</span>
          </label>
          <input
            v-model.number="alertThreshold"
            type="number"
            min="1"
            max="10"
            step="0.5"
            class="w-20 px-2 py-1 border border-gray-300 rounded text-center"
          />
          <span class="text-sm text-gray-500">%</span>
        </div>
      </div>
    </Card>

    <!-- 股票列表 -->
    <div v-if="loading && stocks.length === 0" class="py-12 text-center text-gray-500">
      <p>加载中...</p>
    </div>

    <div v-else-if="stocks.length === 0" class="py-12 text-center text-gray-500">
      <p>暂无跟踪股票，请添加股票代码</p>
    </div>
    
    <div v-else-if="noteFilter && sortedStocks.length === 0" class="py-12 text-center text-gray-500">
      <p>没有找到包含"{{ noteFilter }}"的股票</p>
      <button @click="noteFilter = ''" class="mt-2 text-blue-600 hover:text-blue-800 underline">
        清除筛选
      </button>
    </div>

    <div v-else class="bg-white rounded-lg border border-gray-200 overflow-hidden">
      <table class="w-full">
        <thead class="bg-gray-50">
          <tr>
            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">代码</th>
            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">名称</th>
            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('industry')">
              行业 {{ sortField === 'industry' ? (sortOrder === 'desc' ? '↓' : '↑') : '' }}
            </th>
            <th v-if="showSectors" class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">所属板块</th>
            <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">当天分时</th>
            <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">价格</th>
            <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('change_pct')">
              涨跌幅 {{ sortField === 'change_pct' ? (sortOrder === 'desc' ? '↓' : '↑') : '' }}
            </th>
            <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('pct_5d')">
              5日涨幅(%) {{ sortField === 'pct_5d' ? (sortOrder === 'desc' ? '↓' : '↑') : '' }}
            </th>
            <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('pct_after_startup_5d')" title="仅对来自启动池的股票有值">
              启动后5日(%) {{ sortField === 'pct_after_startup_5d' ? (sortOrder === 'desc' ? '↓' : '↑') : '' }}
            </th>
            <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('pct_10d')">
              10日涨幅(%) {{ sortField === 'pct_10d' ? (sortOrder === 'desc' ? '↓' : '↑') : '' }}
            </th>
            <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('amount')">
              成交额 {{ sortField === 'amount' ? (sortOrder === 'desc' ? '↓' : '↑') : '' }}
            </th>
            <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('turnover_rate')">
              换手率 {{ sortField === 'turnover_rate' ? (sortOrder === 'desc' ? '↓' : '↑') : '' }}
            </th>
            <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">10日线</th>
            <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">20日线</th>
            <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">人气榜单</th>
            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">来源</th>
            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">备注</th>
            <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">操作</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-200">
          <tr 
            v-for="stock in sortedStocks" 
            :key="stock.ts_code"
            :class="getRowClass(stock)"
          >
            <td class="px-4 py-3 text-sm font-medium text-gray-900">{{ stock.code }}</td>
            <td class="px-4 py-3 text-sm text-gray-700">{{ stock.name || '--' }}</td>
            <td class="px-4 py-3 text-xs text-gray-600">{{ stock.industry || '--' }}</td>
            <td v-if="showSectors" class="px-4 py-3">
              <div v-if="stock.sectors && stock.sectors.length > 0" class="flex flex-wrap gap-1">
                <span 
                  v-for="(sector, idx) in stock.sectors.slice(0, 3)" 
                  :key="idx"
                  class="px-1.5 py-0.5 bg-blue-50 text-blue-700 rounded text-xs"
                  :title="sector"
                >
                  {{ sector }}
                </span>
                <span 
                  v-if="stock.sectors.length > 3" 
                  class="px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded text-xs"
                  :title="stock.sectors.join('、')"
                >
                  +{{ stock.sectors.length - 3 }}
                </span>
              </div>
              <span v-else class="text-xs text-gray-400">--</span>
            </td>
            <td class="px-4 py-3">
              <div v-if="stock.chartLoading" class="text-xs text-gray-400">加载中...</div>
              <div v-else-if="!stock.kline || stock.kline.length === 0" class="text-xs text-gray-400">
                {{ stock.kline_error || '暂无分时数据' }}
              </div>
              <MiniChart v-else :data="stock.kline" :trend="stock.change_pct >= 0" />
            </td>
            <td class="px-4 py-3 text-sm text-right font-medium">¥{{ formatPrice(stock.price) }}</td>
            <td class="px-4 py-3 text-sm text-right font-semibold" :class="getChangeClass(stock.change_pct)">
              {{ formatChange(stock.change_pct) }}%
              <span v-if="stock.change_pct >= alertThreshold" class="ml-1">🔔</span>
            </td>
            <td class="px-4 py-3 text-sm text-right font-medium" :class="getChangeClass(stock.pct_5d)">
              {{ stock.pct_5d !== null && stock.pct_5d !== undefined ? formatChange(stock.pct_5d) + '%' : '--' }}
            </td>
            <td class="px-4 py-3 text-sm text-right font-medium" :class="getChangeClass(stock.pct_after_startup_5d)" title="股票启动后5日涨幅，仅对来自启动池的股票有值">
              {{ stock.pct_after_startup_5d !== null && stock.pct_after_startup_5d !== undefined ? formatChange(stock.pct_after_startup_5d) + '%' : '--' }}
            </td>
            <td class="px-4 py-3 text-sm text-right font-medium" :class="getChangeClass(stock.pct_10d)">
              {{ stock.pct_10d !== null && stock.pct_10d !== undefined ? formatChange(stock.pct_10d) + '%' : '--' }}
            </td>
            <td class="px-4 py-3 text-sm text-right text-gray-600">{{ formatAmount(stock.amount) }}</td>
            <td class="px-4 py-3 text-sm text-right text-gray-600">{{ formatPercent(stock.turnover_rate) }}%</td>
            <td class="px-4 py-3 text-sm text-center">
              <span v-if="stock.below_ma10" class="text-green-600">破线</span>
              <span v-else class="text-red-600">站上</span>
            </td>
            <td class="px-4 py-3 text-sm text-center">
              <span v-if="stock.below_ma20" class="text-green-600">破线</span>
              <span v-else class="text-red-600">站上</span>
            </td>
            <td class="px-4 py-3 text-sm text-center">
              <span 
                v-if="stock.is_in_popularity" 
                class="px-2 py-1 bg-green-100 text-green-800 rounded text-xs font-semibold"
                :title="stock.popularity_rank ? `排名：第${stock.popularity_rank}名` : '在人气榜单中'"
              >
                {{ stock.popularity_rank ? `第${stock.popularity_rank}名` : '是' }}
              </span>
              <span v-else class="text-gray-400 text-xs">否</span>
            </td>
            <td class="px-4 py-3 text-xs text-gray-500">
              <span
                v-if="sourceInfo(stock).label"
                class="inline-flex items-center px-1.5 py-0.5 rounded bg-indigo-50 text-indigo-700"
              >
                {{ sourceInfo(stock).label }}
              </span>
              <span v-else class="text-gray-400">--</span>
            </td>
            <td class="px-4 py-3 text-sm text-gray-500">
              <span v-if="editingStock !== stock.ts_code">{{ stock.note || '--' }}</span>
              <input
                v-else
                v-model="editNote"
                type="text"
                class="w-full px-2 py-1 border border-gray-300 rounded text-sm"
                @keyup.enter="saveNote(stock.ts_code)"
                @keyup.escape="cancelEdit"
              />
            </td>
            <td class="px-4 py-3 text-center space-x-2">
              <button
                v-if="editingStock !== stock.ts_code"
                @click="startEdit(stock)"
                class="text-blue-500 hover:text-blue-700 text-sm"
              >
                编辑
              </button>
              <template v-else>
                <button @click="saveNote(stock.ts_code)" class="text-green-500 hover:text-green-700 text-sm">保存</button>
                <button @click="cancelEdit" class="text-gray-500 hover:text-gray-700 text-sm">取消</button>
              </template>
              <button
                @click="openAddToHolding(stock)"
                class="text-orange-500 hover:text-orange-700 text-sm"
              >
                加入操作池
              </button>
              <button
                @click="removeStock(stock.ts_code)"
                class="text-red-500 hover:text-red-700 text-sm"
              >
                删除
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 最后更新时间 -->
    <div class="text-center text-sm text-gray-400">
      最后更新: {{ lastUpdate || '--' }}
      <span v-if="autoRefresh && isTradingTime()" class="ml-2 text-green-500">(交易时间，每30秒自动刷新)</span>
      <span v-else-if="autoRefresh" class="ml-2 text-yellow-500">(非交易时间，暂停刷新)</span>
    </div>

    <!-- 加入操作池弹窗 -->
    <div v-if="showHoldingModal" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg p-6 w-96 shadow-xl">
        <h3 class="text-lg font-semibold mb-4">加入操作池</h3>
        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">股票名称</label>
            <input type="text" :value="holdingForm.name" disabled class="w-full px-3 py-2 border border-gray-300 rounded-md bg-gray-100" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">股票代码</label>
            <input type="text" :value="holdingForm.code" disabled class="w-full px-3 py-2 border border-gray-300 rounded-md bg-gray-100" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">买入价格</label>
            <input type="number" v-model.number="holdingForm.price" step="0.01" class="w-full px-3 py-2 border border-gray-300 rounded-md" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">买入日期</label>
            <input type="date" v-model="holdingForm.buyDate" class="w-full px-3 py-2 border border-gray-300 rounded-md" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">买入数量（股）</label>
            <input type="number" v-model.number="holdingForm.quantity" step="100" min="100" class="w-full px-3 py-2 border border-gray-300 rounded-md" placeholder="请输入买入数量" />
          </div>
        </div>
        <div class="flex justify-end gap-3 mt-6">
          <button @click="closeHoldingModal" class="px-4 py-2 text-gray-600 hover:text-gray-800">取消</button>
          <button @click="submitHolding" :disabled="!holdingForm.quantity" class="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 disabled:bg-gray-300">确定</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import Card from '../components/ui/Card.vue'
import Button from '../components/ui/Button.vue'
import StatCard from '../components/ui/StatCard.vue'
import MiniChart from '../components/ui/MiniChart.vue'

// 状态
const stocks = ref([])
const loading = ref(false)
const newStockCode = ref('')
const searchResults = ref([])
const searchTimeout = ref(null)
let _hideTimer = null
const autoRefresh = ref(true)
const voiceEnabled = ref(true)
const alertThreshold = ref(2)
const lastUpdate = ref('')
const alertedStocks = ref(new Set())  // 已提醒过的股票
const showSectors = ref(false)  // 是否显示板块列，默认隐藏
const editingStock = ref(null)  // 正在编辑的股票代码
const editNote = ref('')  // 编辑中的备注
const showHoldingModal = ref(false)  // 加入操作池弹窗
const sortField = ref('change_pct')  // 排序字段
const sortOrder = ref('desc')  // 排序方向：desc降序，asc升序
const noteFilter = ref('')  // 备注搜索
const holdingForm = ref({
  ts_code: '',
  code: '',
  name: '',
  price: 0,
  quantity: 0,
  buyDate: new Date().toISOString().split('T')[0]
})

// 分时数据缓存
const intradayCache = ref({})  // { ts_code: { data: [...], fetchTime: timestamp } }
const CACHE_DURATION = 60 * 1000  // 缓存1分钟

let refreshInterval = null

// 计算属性
const upCount = computed(() => stocks.value.filter(s => s.change_pct > 0).length)
const downCount = computed(() => stocks.value.filter(s => s.change_pct < 0).length)
const alertCount = computed(() => stocks.value.filter(s => Math.abs(s.change_pct) >= alertThreshold.value).length)

// 解析股票来源（龙头跟踪 / 龙头回测 / 其它）
const sourceInfo = (stock) => {
  const note = (stock.note || '').trim()
  if (!note) {
    return { type: 'unknown', label: '' }
  }
  if (note.startsWith('龙头回测-')) {
    // 形如：龙头回测-右侧确认-算力主线
    const parts = note.split('-')
    const kind = parts[1] || '买点'
    return { type: 'leader_backtest', label: `龙头回测·${kind}` }
  }
  if (note.startsWith('龙头跟踪-')) {
    // 形如：龙头跟踪-刚启动 / 空间龙头
    const parts = note.split('-')
    const kind = parts[1] || '龙头'
    return { type: 'leader_tracking', label: `龙头跟踪·${kind}` }
  }
  return { type: 'custom', label: '' }
}

// 过滤和排序后的股票列表
const sortedStocks = computed(() => {
  if (!stocks.value.length) return []
  
  // 1. 按备注过滤
  let filtered = stocks.value
  if (noteFilter.value.trim()) {
    const keyword = noteFilter.value.trim().toLowerCase()
    filtered = stocks.value.filter(stock => {
      const note = (stock.note || '').toLowerCase()
      return note.includes(keyword)
    })
  }
  
  // 2. 排序
  return [...filtered].sort((a, b) => {
    const field = sortField.value
    let aVal = a[field]
    let bVal = b[field]
    
    // 处理字符串类型字段（如行业）
    if (field === 'industry') {
      aVal = aVal || ''  // 空值转为空字符串
      bVal = bVal || ''
      
      // 字符串排序
      if (sortOrder.value === 'desc') {
        return bVal.localeCompare(aVal, 'zh-CN')
      } else {
        return aVal.localeCompare(bVal, 'zh-CN')
      }
    }
    
    // 处理数值类型字段
    aVal = aVal ?? -Infinity
    bVal = bVal ?? -Infinity
    return sortOrder.value === 'desc' ? bVal - aVal : aVal - bVal
  })
})

// 获取跟踪列表
async function fetchWatchlist() {
  try {
    const response = await fetch('/api/watchlist')
    const data = await response.json()
    if (data.success) {
      stocks.value = data.data || []
    }
  } catch (error) {
    console.error('获取跟踪列表失败:', error)
  }
}

// 获取实时数据
async function fetchRealtimeData() {
  loading.value = true
  try {
    const response = await fetch('/api/watchlist/realtime')
    const data = await response.json()
    if (data.success) {
      const oldStocks = [...stocks.value]
      stocks.value = data.data || []
      lastUpdate.value = new Date().toLocaleTimeString()
      
      // 后端已经批量返回分时数据（kline字段），不需要再单独请求
      // 只需要更新缓存
      const now = Date.now()
      stocks.value.forEach(stock => {
        if (stock.kline && stock.kline.length > 0) {
          // 更新缓存
          intradayCache.value[stock.ts_code] = {
            data: stock.kline,
            fetchTime: now
          }
        }
      })
      
      // 检查是否需要语音提醒
      if (voiceEnabled.value) {
        checkAndAlert(oldStocks, stocks.value)
      }
    }
  } catch (error) {
    console.error('获取实时数据失败:', error)
  } finally {
    loading.value = false
  }
}

// 搜索股票
async function searchStock() {
  const keyword = newStockCode.value.trim()
  if (keyword.length < 1) {
    searchResults.value = []
    return
  }
  
  // 防抖
  if (searchTimeout.value) clearTimeout(searchTimeout.value)
  searchTimeout.value = setTimeout(async () => {
    try {
      const response = await fetch(`/api/watchlist/search?keyword=${encodeURIComponent(keyword)}`)
      const data = await response.json()
      if (data.success) {
        searchResults.value = data.data || []
      }
    } catch (error) {
      console.error('搜索失败:', error)
    }
  }, 300)
}

// 选择搜索结果
function selectStock(stock) {
  newStockCode.value = stock.code
  searchResults.value = []
}

// 隐藏搜索结果
function hideSearchResults() {
  _hideTimer = setTimeout(() => {
    searchResults.value = []
  }, 200)
}

// 添加股票
async function addStock() {
  const code = newStockCode.value.trim()
  if (!code) return
  
  searchResults.value = []
  
  try {
    const response = await fetch('/api/watchlist', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ts_code: code })
    })
    const data = await response.json()
    
    if (data.success) {
      newStockCode.value = ''
      await fetchRealtimeData()
    } else {
      alert(data.message || '添加失败')
    }
  } catch (error) {
    console.error('添加股票失败:', error)
    alert('添加失败')
  }
}

// 开始编辑备注
function startEdit(stock) {
  editingStock.value = stock.ts_code
  editNote.value = stock.note || ''
}

// 取消编辑
function cancelEdit() {
  editingStock.value = null
  editNote.value = ''
}

// 保存备注
async function saveNote(tsCode) {
  try {
    const response = await fetch(`/api/watchlist/${encodeURIComponent(tsCode)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ note: editNote.value })
    })
    const data = await response.json()
    
    if (data.success) {
      const stock = stocks.value.find(s => s.ts_code === tsCode)
      if (stock) stock.note = editNote.value
      cancelEdit()
    } else {
      alert(data.message || '保存失败')
    }
  } catch (error) {
    console.error('保存备注失败:', error)
    alert('保存失败')
  }
}

// 打开加入操作池弹窗
function openAddToHolding(stock) {
  holdingForm.value = {
    ts_code: stock.ts_code,
    code: stock.code,
    name: stock.name || stock.code,
    price: stock.price || 0,
    quantity: 0,
    buyDate: new Date().toISOString().split('T')[0]
  }
  showHoldingModal.value = true
}

// 关闭弹窗
function closeHoldingModal() {
  showHoldingModal.value = false
}

// 提交加入操作池
async function submitHolding() {
  if (!holdingForm.value.quantity || holdingForm.value.quantity <= 0) {
    alert('请输入买入数量')
    return
  }
  
  try {
    const response = await fetch('/api/holdings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        symbol: holdingForm.value.ts_code,
        name: holdingForm.value.name || holdingForm.value.code || holdingForm.value.ts_code,
        buy_price: holdingForm.value.price,
        quantity: holdingForm.value.quantity,
        buy_date: holdingForm.value.buyDate,
        bypass_trading_rules: false
      })
    })
    const data = await response.json()
    
    if (data.success) {
      alert('已加入操作池')
      closeHoldingModal()
    } else {
      alert(data.message || data.detail || '加入失败')
    }
  } catch (error) {
    console.error('加入操作池失败:', error)
    alert('加入失败')
  }
}

// 删除股票
async function removeStock(tsCode) {
  if (!confirm('确定要删除该股票吗？')) return
  
  try {
    const response = await fetch(`/api/watchlist/${encodeURIComponent(tsCode)}`, {
      method: 'DELETE'
    })
    const data = await response.json()
    
    if (data.success) {
      stocks.value = stocks.value.filter(s => s.ts_code !== tsCode)
      alertedStocks.value.delete(tsCode)
    } else {
      alert(data.message || '删除失败')
    }
  } catch (error) {
    console.error('删除股票失败:', error)
    alert('删除失败')
  }
}

// 切换自动刷新
function toggleAutoRefresh() {
  autoRefresh.value = !autoRefresh.value
  if (autoRefresh.value) {
    startAutoRefresh()
  } else {
    stopAutoRefresh()
  }
}

// 判断是否为交易时间
function isTradingTime() {
  const now = new Date()
  const day = now.getDay()
  // 周末不交易
  if (day === 0 || day === 6) return false
  
  const hour = now.getHours()
  const minute = now.getMinutes()
  const time = hour * 100 + minute
  
  // 交易时间: 9:15-11:30, 13:00-15:00
  if ((time >= 915 && time <= 1130) || (time >= 1300 && time <= 1500)) {
    return true
  }
  return false
}

// 开始自动刷新
function startAutoRefresh() {
  if (refreshInterval) return
  refreshInterval = setInterval(() => {
    if (isTradingTime()) {
      fetchRealtimeData()
    }
  }, 30000)  // 每30秒检查并刷新（分时数据）
}

// 停止自动刷新
function stopAutoRefresh() {
  if (refreshInterval) {
    clearInterval(refreshInterval)
    refreshInterval = null
  }
}

// 检查并发出语音提醒（仅上涨时提醒）
function checkAndAlert(oldStocks, newStocks) {
  // 非交易时间不播报
  if (!isTradingTime()) {
    return
  }
  
  for (const stock of newStocks) {
    const changePct = stock.change_pct || 0
    
    // 只在上涨超过阈值时提醒，下跌不提醒
    if (changePct >= alertThreshold.value && !alertedStocks.value.has(stock.ts_code)) {
      alertedStocks.value.add(stock.ts_code)
      
      // 语音提醒
      const message = `${stock.name || stock.code} 上涨 ${changePct.toFixed(2)}%`
      speak(message)
    }
    
    // 如果涨幅回到阈值以下，重置提醒状态
    if (changePct < alertThreshold.value) {
      alertedStocks.value.delete(stock.ts_code)
    }
  }
}

// 语音播报
function speak(text) {
  if ('speechSynthesis' in window) {
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.lang = 'zh-CN'
    utterance.rate = 1.0
    utterance.pitch = 1.0
    window.speechSynthesis.speak(utterance)
  }
}

// 切换分时图显示
async function toggleIntradayChart(stock) {
  // 切换显示状态
  stock.showChart = !stock.showChart
  
  // 如果要显示图表且数据为空，则加载数据
  if (stock.showChart && (!stock.kline || stock.kline.length === 0)) {
    stock.chartLoading = true
    try {
      const response = await fetch(`/api/watchlist/intraday/${stock.ts_code}`)
      const data = await response.json()
      console.log(`${stock.ts_code} 分时数据:`, data)
      if (data.success && data.data && data.data.length > 0) {
        stock.kline = data.data
      } else {
        // 数据为空时提示用户
        stock.kline = []
        if (data.count === 0) {
          alert(`${stock.name || stock.code}: 暂无当天分时数据（可能非交易时间或数据源无数据）`)
        }
      }
    } catch (error) {
      console.error(`获取 ${stock.ts_code} 分时数据失败:`, error)
      alert(`获取分时数据失败: ${error.message}`)
    } finally {
      stock.chartLoading = false
    }
  }
}

// 排序函数
function sortBy(field) {
  if (sortField.value === field) {
    // 如果已经是当前排序字段，切换排序方向
    sortOrder.value = sortOrder.value === 'desc' ? 'asc' : 'desc'
  } else {
    // 切换到新字段，默认降序
    sortField.value = field
    sortOrder.value = 'desc'
  }
}

// 格式化函数
function formatPrice(value) {
  return (value || 0).toFixed(2)
}

function formatChange(value) {
  const v = value || 0
  return v > 0 ? `+${v.toFixed(2)}` : v.toFixed(2)
}

function formatAmount(value) {
  const v = value || 0
  if (v >= 1e8) return (v / 1e8).toFixed(2) + '亿'
  if (v >= 1e4) return (v / 1e4).toFixed(2) + '万'
  return v.toFixed(2)
}

function formatPercent(value) {
  return (value || 0).toFixed(2)
}

function getChangeClass(value) {
  if (value > 0) return 'text-red-600'
  if (value < 0) return 'text-green-600'
  return 'text-gray-600'
}

function getRowClass(stock) {
  if (Math.abs(stock.change_pct) >= alertThreshold.value) {
    return stock.change_pct > 0 ? 'bg-red-50' : 'bg-green-50'
  }
  return ''
}

// 生命周期
onMounted(async () => {
  await fetchRealtimeData()
  if (autoRefresh.value) {
    startAutoRefresh()
  }
})

onUnmounted(() => {
  stopAutoRefresh()
  if (searchTimeout.value) clearTimeout(searchTimeout.value)
  if (_hideTimer) clearTimeout(_hideTimer)
})
</script>

