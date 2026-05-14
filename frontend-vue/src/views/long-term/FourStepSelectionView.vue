<template>
  <div class="p-4 lg:p-6 bg-warm-50 min-h-screen">
    <!-- 标题区 -->
    <div class="mb-6 flex items-center justify-between flex-wrap gap-3">
      <div>
        <h1 class="text-xl font-bold text-warmgray-900">四步精选选股</h1>
        <p class="text-sm text-warmgray-500 mt-1">
          技术强势 → 流动性充裕 → 财务排雷 → 长线逻辑
        </p>
      </div>
      <div class="flex items-center gap-2">
        <select
          v-model="minAmount"
          class="px-3 py-1.5 text-sm border border-border rounded-md bg-white text-warmgray-700 focus:outline-none focus:ring-1 focus:ring-cta"
        >
          <option :value="500000">成交额 ≥ 5亿</option>
          <option :value="1000000">成交额 ≥ 10亿</option>
          <option :value="2000000">成交额 ≥ 20亿</option>
          <option :value="5000000">成交额 ≥ 50亿</option>
        </select>
        <button
          @click="fetchData"
          :disabled="loading"
          class="px-4 py-1.5 bg-cta text-white text-sm font-medium rounded-md hover:bg-cta/90 disabled:opacity-50 transition-colors"
        >
          {{ loading ? '计算中...' : '重新筛选' }}
        </button>
        <button
          v-if="candidates.length > 0"
          @click="batchAddToPool"
          :disabled="adding"
          class="px-4 py-1.5 bg-profit text-white text-sm font-medium rounded-md hover:bg-profit/90 disabled:opacity-50 transition-colors"
        >
          {{ adding ? '添加中...' : '全部加入跟踪池' }}
        </button>
        <button
          @click="goToPool"
          class="px-4 py-1.5 border border-border text-warmgray-700 text-sm font-medium rounded-md hover:bg-warm-100 transition-colors"
        >
          查看跟踪池
        </button>
      </div>
    </div>

    <!-- 筛选统计 -->
    <div v-if="filterStats" class="mb-4 grid grid-cols-2 md:grid-cols-4 gap-3">
      <div class="bg-white rounded-lg border border-border p-3">
        <div class="text-xs text-warmgray-500">① 60日新高</div>
        <div class="text-lg font-semibold text-warmgray-900">{{ filterStats.step1_60d_high }}</div>
      </div>
      <div class="bg-white rounded-lg border border-border p-3">
        <div class="text-xs text-warmgray-500">② 流动性充裕</div>
        <div class="text-lg font-semibold text-primary-700">{{ filterStats.step2_liquidity }}</div>
      </div>
      <div class="bg-white rounded-lg border border-border p-3">
        <div class="text-xs text-warmgray-500">③ 财务排雷</div>
        <div class="text-lg font-semibold text-primary-700">{{ filterStats.step3_financial_clean }}</div>
      </div>
      <div class="bg-white rounded-lg border border-border p-3">
        <div class="text-xs text-warmgray-500">④ 长线逻辑</div>
        <div class="text-lg font-semibold text-profit">{{ filterStats.step4_long_term_logic }}</div>
      </div>
    </div>

    <!-- 候选列表 -->
    <div class="bg-white rounded-lg border border-border overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="bg-warmgray-50 border-b border-border">
              <th class="px-4 py-3 text-left font-semibold text-warmgray-700">股票</th>
              <th class="px-4 py-3 text-left font-semibold text-warmgray-700">行业</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">综合评分</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">Darwin</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">财务健康</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">ROE</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">PE</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">PB</th>
              <th
                class="px-4 py-3 text-center font-semibold text-warmgray-700 cursor-pointer select-none hover:text-cta"
                @click="toggleSort('close_price')"
              >
                价格
                <span v-if="sortColumn === 'close_price'" class="ml-0.5 text-xs">{{ sortDirection === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th
                class="px-4 py-3 text-center font-semibold text-warmgray-700 cursor-pointer select-none hover:text-cta"
                @click="toggleSort('amount')"
              >
                成交额
                <span v-if="sortColumn === 'amount'" class="ml-0.5 text-xs">{{ sortDirection === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">毛利率</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">营收增</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">利润增</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="stock in sortedCandidates"
              :key="stock.ts_code"
              class="border-b border-border hover:bg-warm-50 transition-colors"
            >
              <td class="px-4 py-3">
                <div class="font-medium text-warmgray-900">{{ stock.name }}</div>
                <div class="text-xs text-warmgray-500">{{ stock.ts_code }}</div>
                <div class="text-xs text-warmgray-400">{{ stock.industry }}</div>
              </td>
              <td class="px-4 py-3">
                <span
                  class="inline-block px-2 py-0.5 rounded text-xs font-medium"
                  :class="sectorBadgeClass(stock.sector_type)"
                >
                  {{ stock.sector_type }}
                </span>
              </td>
              <td class="px-4 py-3 text-center">
                <span class="font-bold text-cta">{{ stock.composite_score }}</span>
              </td>
              <td class="px-4 py-3 text-center">
                <span class="font-semibold" :class="scoreClass(stock.darwin_score)">
                  {{ stock.darwin_score }}
                </span>
              </td>
              <td class="px-4 py-3 text-center">
                <span class="font-medium" :class="healthClass(stock.financial_health)">
                  {{ (stock.financial_health * 100).toFixed(1) }}%
                </span>
              </td>
              <td class="px-4 py-3 text-center text-warmgray-700">
                {{ stock.roe_ttm != null ? stock.roe_ttm.toFixed(1) + '%' : '-' }}
              </td>
              <td class="px-4 py-3 text-center text-warmgray-700">
                {{ stock.pe_ttm != null ? stock.pe_ttm.toFixed(1) : '-' }}
              </td>
              <td class="px-4 py-3 text-center text-warmgray-700">
                {{ stock.pb != null ? stock.pb.toFixed(2) : '-' }}
              </td>
              <td class="px-4 py-3 text-center text-warmgray-700">
                {{ stock.close_price != null ? stock.close_price.toFixed(2) : '-' }}
              </td>
              <td class="px-4 py-3 text-center text-warmgray-700">
                {{ stock.amount != null ? (stock.amount / 1e5).toFixed(1) + '亿' : '-' }}
              </td>
              <td class="px-4 py-3 text-center text-warmgray-700">
                {{ stock.gross_margin != null ? stock.gross_margin.toFixed(1) + '%' : '-' }}
              </td>
              <td class="px-4 py-3 text-center text-warmgray-700">
                <span :class="growthClass(stock.revenue_growth)">
                  {{ stock.revenue_growth != null ? stock.revenue_growth.toFixed(1) + '%' : '-' }}
                </span>
              </td>
              <td class="px-4 py-3 text-center text-warmgray-700">
                <span :class="growthClass(stock.profit_growth)">
                  {{ stock.profit_growth != null ? stock.profit_growth.toFixed(1) + '%' : '-' }}
                </span>
              </td>
              <td class="px-4 py-3 text-center">
                <button
                  @click="addSingleToPool(stock)"
                  class="px-2 py-1 text-xs bg-cta/10 text-cta rounded hover:bg-cta/20 transition-colors"
                >
                  加入跟踪池
                </button>
              </td>
            </tr>
            <tr v-if="candidates.length === 0 && !loading">
              <td colspan="13" class="px-4 py-8 text-center text-warmgray-500">
                暂无候选股票，请尝试调整筛选条件
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 说明 -->
    <div class="mt-4 text-xs text-warmgray-500 space-y-1">
      <p>四步精选：① 60日新高（技术强势） ② 成交额 ≥ 门槛（流动性充裕） ③ 审计无保留 + 现金流健康 + 负债可控 + 商誉合理（财务排雷） ④ ROE达标 + 毛利率≥15% + 有分红 + 非双降 + PE合理（长线逻辑）</p>
      <p>综合评分 = Darwin评分 × 财务健康系数，按综合评分降序排列。</p>
      <p>营收增 / 利润增 颜色含义：<span class="text-profit font-medium">绿色 ≥ 20%</span>（高速增长） <span class="text-cta font-medium">橘色 0% ~ 20%</span>（正增长） <span class="text-warmgray-700 font-medium">灰色 -10% ~ 0%</span>（轻微下滑） <span class="text-loss font-medium">红色 &lt; -10%</span>（明显衰退）</p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''
const router = useRouter()

const loading = ref(false)
const candidates = ref([])
const filterStats = ref(null)
const minAmount = ref(1000000)
const adding = ref(false)

// 排序状态
const sortColumn = ref('')
const sortDirection = ref('desc') // 'asc' | 'desc'

const sortedCandidates = computed(() => {
  if (!sortColumn.value) return candidates.value
  const col = sortColumn.value
  const dir = sortDirection.value === 'asc' ? 1 : -1
  return [...candidates.value].sort((a, b) => {
    const av = a[col]
    const bv = b[col]
    if (av == null && bv == null) return 0
    if (av == null) return 1 * dir
    if (bv == null) return -1 * dir
    return (av - bv) * dir
  })
})

function toggleSort(column) {
  if (sortColumn.value === column) {
    sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortColumn.value = column
    sortDirection.value = 'desc'
  }
}

async function fetchData() {
  loading.value = true
  try {
    const params = new URLSearchParams()
    params.append('limit', '15')
    params.append('min_amount', minAmount.value.toString())
    const response = await fetch(`${API_BASE_URL}/api/long-term/four-step-selection?${params}`)
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    const result = await response.json()
    if (result.success && result.data) {
      candidates.value = result.data.candidates || []
      filterStats.value = result.data.filter_stats || null
    } else {
      candidates.value = []
      filterStats.value = null
    }
  } catch (e) {
    console.error('四步精选选股数据获取失败:', e)
    candidates.value = []
  } finally {
    loading.value = false
  }
}

function scoreClass(score) {
  if (score >= 70) return 'text-profit'
  if (score >= 50) return 'text-cta'
  return 'text-loss'
}

function healthClass(health) {
  if (health >= 0.9) return 'text-profit'
  if (health >= 0.85) return 'text-cta'
  return 'text-loss'
}

function growthClass(g) {
  if (g == null) return 'text-warmgray-400'
  if (g >= 20) return 'text-profit font-medium'
  if (g >= 0) return 'text-cta'
  if (g >= -10) return 'text-warmgray-700'
  return 'text-loss'
}

function sectorBadgeClass(type) {
  const map = {
    '金融地产': 'bg-blue-50 text-blue-700',
    '消费白马': 'bg-pink-50 text-pink-700',
    '科技成长': 'bg-purple-50 text-purple-700',
    '周期资源': 'bg-orange-50 text-orange-700',
    '公用事业': 'bg-green-50 text-green-700',
    '制造业': 'bg-gray-50 text-gray-700',
  }
  return map[type] || 'bg-gray-50 text-gray-700'
}

async function addSingleToPool(stock) {
  try {
    const response = await fetch(`${API_BASE_URL}/api/long-term/tracking-pool`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ts_code: stock.ts_code,
        name: stock.name,
        industry: stock.industry,
        sector_type: stock.sector_type,
        composite_score: stock.composite_score,
        darwin_score: stock.darwin_score,
        financial_health: stock.financial_health,
        pe_ttm: stock.pe_ttm,
        pb: stock.pb,
        roe_ttm: stock.roe_ttm,
        amount: stock.amount,
        close_price: stock.close_price,
        source: 'four_step_selection',
      }),
    })
    const result = await response.json()
    if (result.success) {
      alert(`已添加 ${stock.name} 到跟踪池`)
    } else {
      alert(result.message || '添加失败')
    }
  } catch (e) {
    console.error('添加跟踪池失败:', e)
    alert('添加失败')
  }
}

async function batchAddToPool() {
  if (!candidates.value.length) return
  adding.value = true
  try {
    const stocks = candidates.value.map(s => ({
      ts_code: s.ts_code,
      name: s.name,
      industry: s.industry,
      sector_type: s.sector_type,
      composite_score: s.composite_score,
      darwin_score: s.darwin_score,
      financial_health: s.financial_health,
      pe_ttm: s.pe_ttm,
      pb: s.pb,
      roe_ttm: s.roe_ttm,
      amount: s.amount,
      close_price: s.close_price,
    }))
    const response = await fetch(`${API_BASE_URL}/api/long-term/tracking-pool/batch-add`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stocks, source: 'four_step_selection' }),
    })
    const result = await response.json()
    if (result.success) {
      alert(`成功添加 ${result.data.added_count} 只，跳过 ${result.data.skipped_count} 只`)
    } else {
      alert('批量添加失败')
    }
  } catch (e) {
    console.error('批量添加失败:', e)
    alert('批量添加失败')
  } finally {
    adding.value = false
  }
}

function goToPool() {
  router.push('/long-term-tracking-pool')
}

onMounted(() => {
  fetchData()
})
</script>
