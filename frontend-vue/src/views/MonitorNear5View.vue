<template>
  <div class="p-8 space-y-8">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-3">
        <h1 class="text-2xl font-semibold text-gray-900">分时监控</h1>
        <!-- 筛选条件说明按钮 -->
        <button 
          @click="showFilterInfo = !showFilterInfo"
          class="text-sm text-blue-600 hover:text-blue-800 flex items-center gap-1 px-3 py-1 rounded-md hover:bg-blue-50 transition-colors"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
          </svg>
          <span>{{ showFilterInfo ? '收起' : '查看' }}筛选条件</span>
          <svg class="w-4 h-4 transition-transform" :class="{ 'rotate-180': showFilterInfo }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
          </svg>
        </button>
      </div>
    </div>

    <!-- 筛选条件说明（可折叠） -->
    <transition
      enter-active-class="transition-all duration-300 ease-out"
      enter-from-class="opacity-0 -translate-y-2"
      enter-to-class="opacity-100 translate-y-0"
      leave-active-class="transition-all duration-200 ease-in"
      leave-from-class="opacity-100 translate-y-0"
      leave-to-class="opacity-0 -translate-y-2"
    >
      <div v-if="showFilterInfo" class="bg-gradient-to-r from-blue-50 to-indigo-50 p-6 rounded-lg border border-blue-200">
        <h2 class="text-lg font-semibold text-gray-900 mb-3 flex items-center">
          <svg class="w-5 h-5 mr-2 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
          </svg>
          完整筛选条件
        </h2>
        
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <!-- 监控范围 -->
          <div class="bg-white p-4 rounded-lg shadow-sm">
            <h3 class="text-sm font-semibold text-gray-700 mb-2 flex items-center">
              <span class="bg-blue-500 text-white rounded-full w-6 h-6 flex items-center justify-center text-xs mr-2">1</span>
              监控股票范围
            </h3>
            <ul class="space-y-1 text-sm text-gray-600">
              <li class="flex items-start">
                <span class="text-green-500 mr-2">✓</span>
                <span><strong>S1股票池</strong>：距离30日新高≤5%的股票</span>
              </li>
              <li class="flex items-start">
                <span class="text-green-500 mr-2">✓</span>
                <span><strong>30日新高</strong>：当前价格≥30日最高价的股票</span>
              </li>
              <li class="flex items-start">
                <span class="text-blue-500 mr-2">→</span>
                <span class="text-gray-500">自动合并去重</span>
              </li>
            </ul>
          </div>

          <!-- 筛选条件 -->
          <div class="bg-white p-4 rounded-lg shadow-sm">
            <h3 class="text-sm font-semibold text-gray-700 mb-2 flex items-center">
              <span class="bg-blue-500 text-white rounded-full w-6 h-6 flex items-center justify-center text-xs mr-2">2</span>
              分时筛选条件
            </h3>
            <ul class="space-y-1 text-sm text-gray-600">
              <li class="flex items-start">
                <span class="text-green-500 mr-2">✓</span>
                <span><strong>涨幅要求</strong>：相对前日收盘价 ≥ 3%</span>
              </li>
              <li class="flex items-start">
                <span class="text-green-500 mr-2">✓</span>
                <span><strong>未破均线</strong>：9:35-指定时间内最低价 ≥ 均线（容忍度0.1%）</span>
              </li>
              <li class="flex items-start">
                <span class="text-green-500 mr-2">✓</span>
                <span><strong>当前价位</strong>：指定时间的价格 ≥ 分时均线</span>
              </li>
            </ul>
          </div>

          <!-- 加入跟踪池条件 -->
          <div class="bg-white p-4 rounded-lg shadow-sm">
            <h3 class="text-sm font-semibold text-gray-700 mb-2 flex items-center">
              <span class="bg-green-500 text-white rounded-full w-6 h-6 flex items-center justify-center text-xs mr-2">3</span>
              自动加入跟踪池
            </h3>
            <ul class="space-y-1 text-sm text-gray-600">
              <li class="flex items-start">
                <span class="text-green-500 mr-2">✓</span>
                <span><strong>时间点</strong>：仅 9:40 的监控结果</span>
              </li>
              <li class="flex items-start">
                <span class="text-green-500 mr-2">✓</span>
                <span><strong>符合条件</strong>：同时满足上述所有筛选条件</span>
              </li>
              <li class="flex items-start">
                <span class="text-blue-500 mr-2">→</span>
                <span class="text-gray-500">其他时间点结果仅保存在数据库</span>
              </li>
            </ul>
          </div>

          <!-- 结果标识 -->
          <div class="bg-white p-4 rounded-lg shadow-sm">
            <h3 class="text-sm font-semibold text-gray-700 mb-2 flex items-center">
              <span class="bg-purple-500 text-white rounded-full w-6 h-6 flex items-center justify-center text-xs mr-2">4</span>
              结果标识说明
            </h3>
            <ul class="space-y-1 text-sm text-gray-600">
              <li class="flex items-start">
                <span class="text-red-500 mr-2">🔥</span>
                <span><strong>30日新高</strong>：当前价格已突破30日最高价</span>
              </li>
              <li class="flex items-start">
                <span class="text-blue-500 mr-2">📊</span>
                <span><strong>普通</strong>：来自S1池，接近新高但未突破</span>
              </li>
              <li class="flex items-start">
                <span class="text-gray-400 mr-2">ℹ️</span>
                <span class="text-gray-500">两类股票都同样值得关注</span>
              </li>
            </ul>
          </div>
        </div>

        <!-- 注意事项 -->
        <div class="mt-4 p-3 bg-yellow-50 border border-yellow-200 rounded-md">
          <p class="text-xs text-yellow-800">
            <strong>💡 提示：</strong>分时均线 = 累计成交额 ÷ 累计成交量 | 检查从9:35开始（排除集合竞价） | 容忍度0.1%表示允许短暂触碰均线
          </p>
        </div>
      </div>
    </transition>

    <!-- 参数设置 -->
    <div class="bg-white p-6 rounded-lg shadow">
      <h2 class="text-lg font-semibold text-gray-900 mb-4">监控参数</h2>
      <div class="grid grid-cols-4 gap-4">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">交易日期</label>
          <input
            v-model="params.date"
            type="date"
            class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">涨幅阈值(%)</label>
          <input
            v-model.number="params.min_change_pct"
            type="number"
            step="0.5"
            min="0"
            max="20"
            class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">并发线程数</label>
          <select
            v-model.number="params.max_workers"
            class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500"
          >
            <option :value="4">4</option>
            <option :value="8">8</option>
            <option :value="16">16</option>
          </select>
        </div>
        <div class="flex items-end gap-2">
          <label class="flex items-center text-sm text-gray-600 whitespace-nowrap">
            <input type="checkbox" v-model="params.force" class="mr-1" />
            强制重跑
          </label>
          <Button 
            @click="startMonitor" 
            :disabled="status.running && !params.force"
            variant="primary"
            class="flex-1"
          >
            {{ status.running ? '监控中...' : '开始监控' }}
          </Button>
        </div>
      </div>
    </div>

    <!-- 监控状态 -->
    <div v-if="status.running || status.message" class="bg-white p-6 rounded-lg shadow">
      <h2 class="text-lg font-semibold text-gray-900 mb-4">监控状态</h2>
      
      <!-- 进度条 -->
      <div class="mb-4">
        <div class="flex justify-between text-sm text-gray-600 mb-1">
          <span>{{ status.message }}</span>
          <span>{{ status.progress }} / {{ status.total }}</span>
        </div>
        <div class="w-full bg-gray-200 rounded-full h-2">
          <div 
            class="bg-blue-600 h-2 rounded-full transition-all duration-300"
            :style="{ width: `${(status.progress / status.total) * 100}%` }"
          ></div>
        </div>
      </div>

      <!-- 时间点状态 -->
      <div class="flex flex-wrap gap-2">
        <span 
          v-for="(tp, idx) in timePoints" 
          :key="tp"
          :class="[
            'px-3 py-1 rounded-full text-sm',
            idx < status.progress ? 'bg-green-100 text-green-800' :
            idx === status.progress && status.running ? 'bg-blue-100 text-blue-800 animate-pulse' :
            'bg-gray-100 text-gray-600'
          ]"
        >
          {{ timeLabels[idx] }}
        </span>
      </div>

      <!-- 错误信息 -->
      <div v-if="status.error" class="mt-4 p-3 bg-red-50 text-red-700 rounded-md">
        {{ status.error }}
      </div>

      <!-- 当前结果 -->
      <div v-if="status.results && status.results.length > 0" class="mt-4">
        <p class="text-sm text-gray-600 mb-2">当前筛选出 {{ status.results.length }} 只股票：</p>
        <div class="flex flex-wrap gap-2">
          <span 
            v-for="code in status.results.slice(0, 20)" 
            :key="code"
            class="px-2 py-1 bg-blue-50 text-blue-700 rounded text-sm"
          >
            {{ code }}
          </span>
          <span v-if="status.results.length > 20" class="px-2 py-1 text-gray-500 text-sm">
            ...还有 {{ status.results.length - 20 }} 只
          </span>
        </div>
      </div>
    </div>

    <!-- 快速查看结果 -->
    <div class="bg-white p-6 rounded-lg shadow">
      <h2 class="text-lg font-semibold text-gray-900 mb-4">查看历史结果</h2>
      <div class="flex items-center gap-4 mb-4">
        <input
          v-model="queryDate"
          type="date"
          class="px-3 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500"
        />
        <div class="flex flex-wrap gap-2">
          <button
            v-for="(tp, idx) in timePoints"
            :key="tp"
            @click="queryResults(tp)"
            :class="[
              'px-3 py-1 rounded-md text-sm transition-colors',
              selectedTime === tp 
                ? 'bg-blue-600 text-white' 
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            ]"
          >
            {{ timeLabels[idx] }}
          </button>
        </div>
        <Button 
          @click="downloadResults" 
          variant="secondary"
          :disabled="!selectedTime || queryResultsData.length === 0"
          class="ml-auto"
        >
          下载结果文件
        </Button>
      </div>

      <!-- 结果表格 -->
      <div v-if="queryLoading" class="py-8 text-center text-gray-500">
        加载中...
      </div>
      <div v-else-if="queryResultsData.length === 0 && selectedTime" class="py-8 text-center text-gray-500">
        没有符合条件的结果
      </div>
      <div v-else-if="queryResultsData.length > 0" class="overflow-x-auto">
        <table class="min-w-full divide-y divide-gray-200">
          <thead class="bg-gray-50">
            <tr>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">股票代码</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">股票名称</th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('pct_today')">
                今日涨幅(%) {{ sortField === 'pct_today' ? (sortOrder === 'desc' ? '↓' : '↑') : '' }}
              </th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('pct_5d')">
                5日涨幅(%) {{ sortField === 'pct_5d' ? (sortOrder === 'desc' ? '↓' : '↑') : '' }}
              </th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('pct_10d')">
                10日涨幅(%) {{ sortField === 'pct_10d' ? (sortOrder === 'desc' ? '↓' : '↑') : '' }}
              </th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">金额(万元)</th>
              <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">是否30日新高</th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">当前价格</th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">30日最高价</th>
            </tr>
          </thead>
          <tbody class="bg-white divide-y divide-gray-200">
            <tr v-for="stock in sortedResults" :key="stock.code" class="hover:bg-gray-50">
              <td class="px-4 py-3 text-sm text-gray-900">{{ stock.code }}</td>
              <td class="px-4 py-3 text-sm text-gray-900">{{ stock.name || '--' }}</td>
              <td class="px-4 py-3 text-sm text-right" :class="getChangeColor(stock.pct_today)">
                {{ formatPercent(stock.pct_today) }}
              </td>
              <td class="px-4 py-3 text-sm text-right" :class="getChangeColor(stock.pct_5d)">
                {{ formatPercent(stock.pct_5d) }}
              </td>
              <td class="px-4 py-3 text-sm text-right" :class="getChangeColor(stock.pct_10d)">
                {{ formatPercent(stock.pct_10d) }}
              </td>
              <td class="px-4 py-3 text-sm text-right text-gray-900">
                {{ formatAmount(stock.amount) }}
              </td>
              <td class="px-4 py-3 text-sm text-center">
                <span 
                  v-if="stock.is_30d_high !== undefined"
                  :class="stock.is_30d_high ? 'px-2 py-1 bg-green-100 text-green-800 rounded text-xs font-medium' : 'px-2 py-1 bg-gray-100 text-gray-600 rounded text-xs'"
                >
                  {{ stock.is_30d_high ? '是' : '否' }}
                </span>
                <span v-else class="text-gray-400">--</span>
              </td>
              <td class="px-4 py-3 text-sm text-right text-gray-900">
                {{ stock.current_price ? stock.current_price.toFixed(2) : '--' }}
              </td>
              <td class="px-4 py-3 text-sm text-right text-gray-900">
                {{ stock.high_30d ? stock.high_30d.toFixed(2) : '--' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import Button from '@/components/ui/Button.vue'

// 时间点
const timePoints = ref([
  "09:40:00", "09:50:00", "10:00:00", "10:10:00", "10:20:00",
  "10:30:00", "10:40:00", "10:50:00", "11:00:00"
])
const timeLabels = ref([
  "9点40", "9点50", "10点", "10点10分", "10点20分",
  "10点30分", "10点40分", "10点50分", "11点"
])

// 界面控制
const showFilterInfo = ref(false)

// 参数
const params = ref({
  date: new Date().toISOString().split('T')[0],
  min_change_pct: 3.0,
  max_workers: 8,
  force: false
})

// 状态
const status = ref({
  running: false,
  progress: 0,
  total: 9,
  message: '',
  results: [],
  error: null
})

// 查询
const queryDate = ref(new Date().toISOString().split('T')[0])
const selectedTime = ref('')
const queryLoading = ref(false)
const queryResultsData = ref([])
const sortField = ref('pct_today')
const sortOrder = ref('desc')

// 轮询定时器
let pollInterval = null

// 排序后的结果
const sortedResults = computed(() => {
  if (!queryResultsData.value.length) return []
  
  return [...queryResultsData.value].sort((a, b) => {
    const aVal = a[sortField.value] ?? -Infinity
    const bVal = b[sortField.value] ?? -Infinity
    return sortOrder.value === 'desc' ? bVal - aVal : aVal - bVal
  })
})

// 启动监控
async function startMonitor() {
  try {
    const response = await fetch('/api/monitor/run_near5_940', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params.value)
    })
    const data = await response.json()
    
    if (data.success) {
      startPolling()
    } else {
      alert(data.message || '启动失败')
    }
  } catch (error) {
    console.error('启动监控失败:', error)
    alert('启动监控失败')
  }
}

// 开始轮询状态
function startPolling() {
  if (pollInterval) clearInterval(pollInterval)
  
  pollInterval = setInterval(async () => {
    try {
      const response = await fetch('/api/monitor/status/near5_940')
      const data = await response.json()
      status.value = data
      
      if (!data.running) {
        stopPolling()
      }
    } catch (error) {
      console.error('获取状态失败:', error)
    }
  }, 1000)
}

// 停止轮询
function stopPolling() {
  if (pollInterval) {
    clearInterval(pollInterval)
    pollInterval = null
  }
}

// 查询结果
async function queryResults(time) {
  selectedTime.value = time
  queryLoading.value = true
  
  try {
    const response = await fetch(`/api/monitor/results?date=${queryDate.value}&time=${time}`)
    const data = await response.json()
    
    if (data.success) {
      queryResultsData.value = data.data || []
    } else {
      queryResultsData.value = []
    }
  } catch (error) {
    console.error('查询结果失败:', error)
    queryResultsData.value = []
  } finally {
    queryLoading.value = false
  }
}

// 下载结果
async function downloadResults() {
  if (!selectedTime.value) {
    alert('请先选择时间点')
    return
  }
  
  if (queryResultsData.value.length === 0) {
    alert('当前时间点没有数据可下载')
    return
  }
  
  window.open(`/api/monitor/download/near5?date=${queryDate.value}&time=${selectedTime.value}`, '_blank')
}

// 排序
function sortBy(field) {
  if (sortField.value === field) {
    sortOrder.value = sortOrder.value === 'desc' ? 'asc' : 'desc'
  } else {
    sortField.value = field
    sortOrder.value = 'desc'
  }
}

// 格式化
function formatPercent(val) {
  if (val === null || val === undefined) return '--'
  return (val >= 0 ? '+' : '') + val.toFixed(2) + '%'
}

function formatAmount(val) {
  if (!val) return '--'
  return (val / 10000).toFixed(2)
}

function getChangeColor(val) {
  if (val === null || val === undefined) return 'text-gray-500'
  if (val > 0) return 'text-red-600'
  if (val < 0) return 'text-green-600'
  return 'text-gray-600'
}

// 生命周期
onMounted(async () => {
  // 获取时间点
  try {
    const response = await fetch('/api/monitor/time_points')
    const data = await response.json()
    if (data.time_points) {
      timePoints.value = data.time_points
      timeLabels.value = data.labels
    }
  } catch (error) {
    console.error('获取时间点失败:', error)
  }
  
  // 检查是否有正在运行的任务
  try {
    const response = await fetch('/api/monitor/status/near5_940')
    const data = await response.json()
    status.value = data
    
    if (data.running) {
      startPolling()
    }
  } catch (error) {
    console.error('获取状态失败:', error)
  }
})

onUnmounted(() => {
  stopPolling()
})
</script>

