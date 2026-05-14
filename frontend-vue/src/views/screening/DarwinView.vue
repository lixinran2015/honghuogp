<template>
  <div class="p-8 space-y-8">
    <!-- 页面标题 -->
    <div>
      <h1 class="text-2xl font-semibold text-gray-900 mb-2">达尔文评分</h1>
      <p class="text-sm text-gray-500">基于财务质量的长期投资标的筛选</p>
    </div>

    <!-- 筛选和搜索 -->
    <Card padding="md">
      <div class="flex items-center gap-4 flex-wrap">
        <div class="flex-1 min-w-[200px]">
          <input
            v-model="searchQuery"
            type="text"
            placeholder="搜索股票名称或代码..."
            class="w-full px-4 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
          />
        </div>
        <FilterBar>
          <FilterButton
            v-for="filter in scoreFilters"
            :key="filter.id"
            :label="filter.label"
            :active="activeScoreFilter === filter.id"
            @click="activeScoreFilter = filter.id"
          />
        </FilterBar>
        <Button size="sm" variant="secondary" @click="handleRefresh" :disabled="loading">
          {{ loading ? '加载中...' : '刷新' }}
        </Button>
      </div>
    </Card>

    <!-- 股票表格 -->
    <Card padding="none">
      <div v-if="loading" class="py-12 text-center text-gray-500">
        <p>加载中...</p>
      </div>
      <div v-else-if="filteredStocks.length > 0" class="space-y-8 overflow-x-auto">
        <!-- 行业龙头股票 -->
        <div v-if="filteredLeaderStocks.length > 0" class="stock-group-section">
          <div class="group-header">
            <h3 class="group-title">
              🏆 行业龙头 <span class="group-count">({{ filteredLeaderStocks.length }}只)</span>
            </h3>
          </div>
          <Table :headers="['排名', '股票名称', '代码', '价格', '涨跌幅', '换手率', '成交额', '板块', '系统评分', '趋势分', '板块热度', '入手区间', '操作建议', '操作']">
            <TableRow
              v-for="(stock, index) in filteredLeaderStocks"
              :key="stock.code"
              hoverable
            >
              <TableCell>{{ index + 1 }}</TableCell>
              <TableCell>
                <div>
                  <p class="font-medium text-gray-900">{{ stock.name || '--' }}</p>
                </div>
              </TableCell>
              <TableCell align="right" class="font-mono text-sm">{{ stock.code || '--' }}</TableCell>
              <TableCell align="right">
                <span v-if="stock.price && stock.price !== '--'" class="text-sm font-medium text-gray-900">
                  ¥{{ typeof stock.price === 'number' ? stock.price.toFixed(2) : stock.price }}
                </span>
                <span v-else class="text-sm text-gray-400">--</span>
              </TableCell>
              <TableCell align="right">
                <span v-if="stock.changePercent !== null && stock.changePercent !== undefined" :class="[
                  'text-sm font-medium',
                  stock.changePercent >= 0 ? 'text-red-600' : 'text-green-600'
                ]">
                  {{ stock.changePercent >= 0 ? '+' : '' }}{{ stock.changePercent.toFixed(2) }}%
                </span>
                <span v-else class="text-sm text-gray-400">--</span>
              </TableCell>
              <TableCell align="right">
                <span v-if="stock.turnover && stock.turnover !== '--'" class="text-sm text-gray-600">
                  {{ stock.turnover }}
                </span>
                <span v-else class="text-sm text-gray-400">--</span>
              </TableCell>
              <TableCell align="right">
                <span v-if="stock.volume && stock.volume !== '--'" class="text-sm text-gray-600">
                  {{ stock.volume }}
                </span>
                <span v-else class="text-sm text-gray-400">--</span>
              </TableCell>
              <TableCell>
                <span class="text-sm text-gray-600">{{ stock.sector || '--' }}</span>
              </TableCell>
              <TableCell align="right">
                <span class="font-semibold text-gray-900">{{ stock.score.toFixed(1) }}</span>
              </TableCell>
              <TableCell align="right">
                <span v-if="stock.trendScore !== null && stock.trendScore !== undefined" :class="[
                  'text-sm font-medium',
                  stock.trendScore >= 70 ? 'text-red-600' : stock.trendScore >= 50 ? 'text-yellow-600' : 'text-green-600'
                ]">
                  {{ stock.trendScore.toFixed(1) }}%
                </span>
                <span v-else class="text-sm text-gray-400">--</span>
              </TableCell>
              <TableCell align="right">
                <span v-if="stock.sectorHeat !== null && stock.sectorHeat !== undefined" class="text-sm text-gray-600">
                  {{ stock.sectorHeat }}
                </span>
                <span v-else class="text-sm text-gray-400">--</span>
              </TableCell>
              <TableCell align="right">
                <span v-if="stock.buyRange && stock.buyRange.min && stock.buyRange.max" class="text-sm text-gray-600">
                  ¥{{ stock.buyRange.min.toFixed(2) }} - ¥{{ stock.buyRange.max.toFixed(2) }}
                </span>
                <span v-else class="text-sm text-gray-400">--</span>
              </TableCell>
              <TableCell>
                <span v-if="stock.advice" :class="[
                  'text-sm font-medium px-2 py-1 rounded',
                  stock.advice === '买入' ? 'bg-red-100 text-red-700' : 'bg-gray-100 text-gray-700'
                ]">
                  {{ stock.advice }}
                </span>
                <span v-else class="text-sm text-gray-400">--</span>
              </TableCell>
              <TableCell class="sticky right-0 bg-white z-10 min-w-[160px]">
                <div class="flex gap-2">
                  <button
                    @click="openChart(stock)"
                    class="px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 rounded transition-colors border border-gray-200 whitespace-nowrap"
                  >
                    K线
                  </button>
                  <button
                    v-if="!stock.inHolding"
                    @click="handleAddToHolding(stock)"
                    class="px-3 py-1.5 text-xs font-medium text-blue-600 hover:bg-blue-50 rounded transition-colors border border-blue-200 whitespace-nowrap"
                  >
                    + 加入
                  </button>
                  <button
                    v-else
                    @click="handleViewHolding"
                    class="px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 rounded transition-colors border border-gray-200 whitespace-nowrap"
                  >
                    已在池
                  </button>
                </div>
              </TableCell>
            </TableRow>
          </Table>
        </div>

        <!-- 其他股票 -->
        <div v-if="filteredNonLeaderStocks.length > 0" class="stock-group-section">
          <div class="group-header">
            <h3 class="group-title">
              📊 其他股票 <span class="group-count">({{ filteredNonLeaderStocks.length }}只)</span>
            </h3>
          </div>
          <Table :headers="['排名', '股票名称', '代码', '价格', '涨跌幅', '换手率', '成交额', '板块', '系统评分', '趋势分', '板块热度', '入手区间', '操作建议', '操作']">
            <TableRow
              v-for="(stock, index) in filteredNonLeaderStocks"
              :key="stock.code"
              hoverable
            >
              <TableCell>{{ index + 1 }}</TableCell>
              <TableCell>
                <div>
                  <p class="font-medium text-gray-900">{{ stock.name || '--' }}</p>
                </div>
              </TableCell>
              <TableCell align="right" class="font-mono text-sm">{{ stock.code || '--' }}</TableCell>
              <TableCell align="right">
                <span v-if="stock.price && stock.price !== '--'" class="text-sm font-medium text-gray-900">
                  ¥{{ typeof stock.price === 'number' ? stock.price.toFixed(2) : stock.price }}
                </span>
                <span v-else class="text-sm text-gray-400">--</span>
              </TableCell>
              <TableCell align="right">
                <span v-if="stock.changePercent !== null && stock.changePercent !== undefined" :class="[
                  'text-sm font-medium',
                  stock.changePercent >= 0 ? 'text-red-600' : 'text-green-600'
                ]">
                  {{ stock.changePercent >= 0 ? '+' : '' }}{{ stock.changePercent.toFixed(2) }}%
                </span>
                <span v-else class="text-sm text-gray-400">--</span>
              </TableCell>
              <TableCell align="right">
                <span v-if="stock.turnover && stock.turnover !== '--'" class="text-sm text-gray-600">
                  {{ stock.turnover }}
                </span>
                <span v-else class="text-sm text-gray-400">--</span>
              </TableCell>
              <TableCell align="right">
                <span v-if="stock.volume && stock.volume !== '--'" class="text-sm text-gray-600">
                  {{ stock.volume }}
                </span>
                <span v-else class="text-sm text-gray-400">--</span>
              </TableCell>
              <TableCell>
                <span class="text-sm text-gray-600">{{ stock.sector || '--' }}</span>
              </TableCell>
              <TableCell align="right">
                <span class="font-semibold text-gray-900">{{ stock.score.toFixed(1) }}</span>
              </TableCell>
              <TableCell align="right">
                <span v-if="stock.trendScore !== null && stock.trendScore !== undefined" :class="[
                  'text-sm font-medium',
                  stock.trendScore >= 70 ? 'text-red-600' : stock.trendScore >= 50 ? 'text-yellow-600' : 'text-green-600'
                ]">
                  {{ stock.trendScore.toFixed(1) }}%
                </span>
                <span v-else class="text-sm text-gray-400">--</span>
              </TableCell>
              <TableCell align="right">
                <span v-if="stock.sectorHeat !== null && stock.sectorHeat !== undefined" class="text-sm text-gray-600">
                  {{ stock.sectorHeat }}
                </span>
                <span v-else class="text-sm text-gray-400">--</span>
              </TableCell>
              <TableCell align="right">
                <span v-if="stock.buyRange && stock.buyRange.min && stock.buyRange.max" class="text-sm text-gray-600">
                  ¥{{ stock.buyRange.min.toFixed(2) }} - ¥{{ stock.buyRange.max.toFixed(2) }}
                </span>
                <span v-else class="text-sm text-gray-400">--</span>
              </TableCell>
              <TableCell>
                <span v-if="stock.advice" :class="[
                  'text-sm font-medium px-2 py-1 rounded',
                  stock.advice === '买入' ? 'bg-red-100 text-red-700' : 'bg-gray-100 text-gray-700'
                ]">
                  {{ stock.advice }}
                </span>
                <span v-else class="text-sm text-gray-400">--</span>
              </TableCell>
              <TableCell class="sticky right-0 bg-white z-10 min-w-[160px]">
                <div class="flex gap-2">
                  <button
                    @click="openChart(stock)"
                    class="px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 rounded transition-colors border border-gray-200 whitespace-nowrap"
                  >
                    K线
                  </button>
                  <button
                    v-if="!stock.inHolding"
                    @click="handleAddToHolding(stock)"
                    class="px-3 py-1.5 text-xs font-medium text-blue-600 hover:bg-blue-50 rounded transition-colors border border-blue-200 whitespace-nowrap"
                  >
                    + 加入
                  </button>
                  <button
                    v-else
                    @click="handleViewHolding"
                    class="px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 rounded transition-colors border border-gray-200 whitespace-nowrap"
                  >
                    已在池
                  </button>
                </div>
              </TableCell>
            </TableRow>
          </Table>
        </div>
      </div>
      <div v-else class="py-12 text-center text-gray-500">
        <p>暂无数据</p>
      </div>
    </Card>

    <!-- TradingView K线弹窗 -->
    <div v-if="chartStock" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" @click.self="chartStock = null">
      <div class="bg-white rounded-xl shadow-xl max-w-4xl w-full max-h-[90vh] overflow-hidden flex flex-col">
        <div class="flex items-center justify-between px-4 py-3 border-b border-gray-200">
          <h3 class="text-lg font-semibold text-gray-800">{{ chartStock?.name }} ({{ chartStock?.code }}) - TradingView 日K线</h3>
          <button @click="chartStock = null" class="p-2 text-gray-500 hover:text-gray-700 rounded">✕</button>
        </div>
        <div class="flex-1 min-h-0 overflow-auto" style="min-height: 400px">
          <TradingViewChart :ts-code="chartTsCode" />
        </div>
      </div>
    </div>

    <!-- 加入操作池对话框 -->
    <div v-if="showAddDialog" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg p-6 max-w-md w-full mx-4">
        <h3 class="text-lg font-semibold mb-4">加入操作池</h3>
        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">股票</label>
            <p class="text-sm text-gray-600">{{ selectedStock?.name }} ({{ selectedStock?.code }})</p>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">分类</label>
            <select v-model="addForm.board_type" class="w-full px-3 py-2 border border-gray-300 rounded-md">
              <option value="darwin">达尔文</option>
              <option value="swing">波段</option>
              <option value="short">短线</option>
              <option value="other">其他</option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">买入价（可选）</label>
            <input
              v-model.number="addForm.buy_price"
              type="number"
              step="0.01"
              class="w-full px-3 py-2 border border-gray-300 rounded-md"
              placeholder="输入买入价"
            />
            <button
              @click="addForm.buy_price = selectedStock?.price || selectedStock?.currentPrice"
              class="mt-1 text-xs text-blue-600 hover:text-blue-800"
            >
              使用当前价
            </button>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">数量（可选）</label>
            <input
              v-model.number="addForm.quantity"
              type="number"
              step="100"
              class="w-full px-3 py-2 border border-gray-300 rounded-md"
              placeholder="输入数量（股）"
            />
          </div>
        </div>
        <div class="flex items-center gap-2 mt-6">
          <button
            @click="handleConfirmAdd"
            class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            确认
          </button>
          <button
            @click="showAddDialog = false"
            class="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition-colors"
          >
            取消
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { stockApi, formatStockData } from '../../api/stockApi'
import { dataCache, CACHE_KEYS } from '../../services/dataCache'
import Card from '../../components/ui/Card.vue'
import Button from '../../components/ui/Button.vue'
import Table from '../../components/ui/Table.vue'
import TableRow from '../../components/ui/TableRow.vue'
import TableCell from '../../components/ui/TableCell.vue'
import FilterBar from '../../components/ui/FilterBar.vue'
import FilterButton from '../../components/ui/FilterButton.vue'
import TradingViewChart from '../../components/TradingViewChart.vue'

const router = useRouter()
const searchQuery = ref('')
const activeScoreFilter = ref('all')
const loading = ref(false)
const stocks = ref([])
const showAddDialog = ref(false)
const selectedStock = ref(null)
const chartStock = ref(null)
const addForm = ref({
  board_type: 'darwin',
  buy_price: null,
  quantity: null
})

const chartTsCode = computed(() => {
  const s = chartStock.value
  if (!s?.code) return ''
  const c = String(s.code).replace(/\.(SH|SZ|BJ)$/i, '')
  return c.startsWith('6') ? `${c}.SH` : `${c}.SZ`
})

function openChart(stock) {
  chartStock.value = stock
}

const scoreFilters = [
  { id: 'all', label: '全部' },
  { id: 'high', label: '高分 (>80)' },
  { id: 'medium', label: '中分 (60-80)' },
  { id: 'low', label: '低分 (<60)' },
]

// 防止重复请求的标志
let isFetching = false

// 获取达尔文股票数据
const fetchDarwinStocks = async (forceRefresh = false) => {
  // 防止重复请求
  if (isFetching) {
    console.log('⏳ 达尔文数据正在加载中，跳过重复请求')
    return
  }
  
  loading.value = true
  try {
    // 检查缓存
    if (!forceRefresh) {
      const cached = dataCache.get(CACHE_KEYS.DARWIN_STOCKS)
      // 支持两种缓存格式：直接数组或 {data: [...]}
      const cachedData = cached?.data || (Array.isArray(cached) ? cached : null)
      if (cachedData && cachedData.length > 0) {
        console.log('📦 使用缓存的达尔文评分数据:', cachedData.length, '只')
        const sortedStocks = cachedData
          .sort((a, b) => {
            const scoreA = a.darwinScore || a.darwin_score || a.finalScore || a.final_score || 0
            const scoreB = b.darwinScore || b.darwin_score || b.finalScore || b.final_score || 0
            return scoreB - scoreA
          })
          .map(formatStockData)
        stocks.value = sortedStocks
        loading.value = false
        return
      }
    }
    
    isFetching = true
    // 达尔文评分页面显示所有有评分的公司，不进行买入条件过滤
    // 买入条件过滤只在推荐选股页面使用
    // 使用limit=1000与React版本保持一致
    const data = await stockApi.getDarwinStocks(1000).catch(() => [])
    // 按评分排序
    const sortedStocks = data
      .sort((a, b) => {
        const scoreA = a.darwinScore || a.darwin_score || a.finalScore || a.final_score || 0
        const scoreB = b.darwinScore || b.darwin_score || b.finalScore || b.final_score || 0
        return scoreB - scoreA
      })
      .map(formatStockData)
    
    stocks.value = sortedStocks
    
    // 更新缓存
    dataCache.set(CACHE_KEYS.DARWIN_STOCKS, data)
  } catch (error) {
    console.error('获取达尔文股票失败:', error)
    stocks.value = []
  } finally {
    loading.value = false
    isFetching = false
  }
}

const handleRefresh = () => {
  fetchDarwinStocks(true) // 强制刷新
}

// 监听全局刷新事件
const handleGlobalRefresh = () => {
  fetchDarwinStocks(true)
}

// 分离龙头和非龙头股票
const leaderStocks = computed(() => {
  return stocks.value.filter(s => s.isIndustryLeader === true)
})

const nonLeaderStocks = computed(() => {
  return stocks.value.filter(s => !s.isIndustryLeader)
})

const filteredLeaderStocks = computed(() => {
  let result = leaderStocks.value

  // 搜索过滤
  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    result = result.filter(s => 
      (s.name || '').toLowerCase().includes(query) || 
      (s.code || '').includes(query)
    )
  }

  // 评分过滤
  if (activeScoreFilter.value === 'high') {
    result = result.filter(s => s.score > 80)
  } else if (activeScoreFilter.value === 'medium') {
    result = result.filter(s => s.score >= 60 && s.score <= 80)
  } else if (activeScoreFilter.value === 'low') {
    result = result.filter(s => s.score < 60)
  }

  // 按评分排序
  return result.sort((a, b) => b.score - a.score)
})

const filteredNonLeaderStocks = computed(() => {
  let result = nonLeaderStocks.value

  // 搜索过滤
  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    result = result.filter(s => 
      (s.name || '').toLowerCase().includes(query) || 
      (s.code || '').includes(query)
    )
  }

  // 评分过滤
  if (activeScoreFilter.value === 'high') {
    result = result.filter(s => s.score > 80)
  } else if (activeScoreFilter.value === 'medium') {
    result = result.filter(s => s.score >= 60 && s.score <= 80)
  } else if (activeScoreFilter.value === 'low') {
    result = result.filter(s => s.score < 60)
  }

  // 按评分排序
  return result.sort((a, b) => b.score - a.score)
})

// 兼容旧的filteredStocks（用于统计）
const filteredStocks = computed(() => {
  return [...filteredLeaderStocks.value, ...filteredNonLeaderStocks.value]
})

const handleAddToHolding = (stock) => {
  selectedStock.value = stock
  addForm.value = {
    board_type: 'darwin',
    buy_price: stock.price || stock.currentPrice || null,
    quantity: null
  }
  showAddDialog.value = true
}

const handleViewHolding = () => {
  router.push('/holdings')
}

const handleConfirmAdd = async () => {
  if (!selectedStock.value) return
  
  try {
    const response = await fetch('/api/holdings', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        symbol: selectedStock.value.code,
        name: selectedStock.value.name,
        board_type: addForm.value.board_type,
        buy_price: addForm.value.buy_price,
        quantity: addForm.value.quantity,
        bypass_trading_rules: false
      })
    })
    
    const result = await response.json()
    
    if (result.success) {
      showAddDialog.value = false
      // 更新股票的inHolding状态
      if (selectedStock.value) {
        selectedStock.value.inHolding = true
      }
      alert('已加入操作池')
      // 刷新列表以更新所有股票的inHolding状态
      fetchDarwinStocks()
    } else {
      alert('加入失败，请重试')
    }
  } catch (error) {
    console.error('加入操作池失败:', error)
    alert('加入失败，请重试')
  }
}

onMounted(() => {
  // 先尝试使用缓存，如果没有缓存再加载
  fetchDarwinStocks(false)
  window.addEventListener('global-refresh', handleGlobalRefresh)
})

onUnmounted(() => {
  window.removeEventListener('global-refresh', handleGlobalRefresh)
})
</script>

<style scoped>
.stock-group-section {
  margin-bottom: 32px;
}

.group-header {
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 2px solid #e2e8f0;
}

.group-title {
  font-size: 18px;
  font-weight: 600;
  color: #1e293b;
  margin: 0;
}

.group-count {
  font-size: 14px;
  font-weight: 400;
  color: #64748b;
  margin-left: 8px;
}

/* 表格单元格内容样式优化 */
:deep(.darwin-table-td) {
  vertical-align: middle;
}

/* 数字字段右对齐 */
:deep(.darwin-table-td[style*="text-align: right"]) {
  font-variant-numeric: tabular-nums;
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;
}

/* 价格样式 */
:deep(.price-cell) {
  font-weight: 600;
  color: #1e293b;
}

/* 涨跌幅样式 */
:deep(.change-positive) {
  color: #dc2626;
  font-weight: 500;
}

:deep(.change-negative) {
  color: #16a34a;
  font-weight: 500;
}

/* 评分样式 */
:deep(.score-cell) {
  font-weight: 600;
  color: #1e293b;
}

/* 操作建议样式 */
:deep(.advice-cell) {
  font-weight: 500;
}

:deep(.advice-buy) {
  background: #fef2f2;
  color: #dc2626;
  padding: 4px 10px;
  border-radius: 6px;
  display: inline-block;
}

:deep(.advice-other) {
  background: #f1f5f9;
  color: #475569;
  padding: 4px 10px;
  border-radius: 6px;
  display: inline-block;
}
</style>

