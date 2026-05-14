<template>
  <div class="p-4 lg:p-6 bg-warm-50 min-h-screen">
    <!-- 标题区 -->
    <div class="mb-6 flex items-center justify-between flex-wrap gap-3">
      <div>
        <h1 class="text-xl font-bold text-warmgray-900">长线选股</h1>
        <p class="text-sm text-warmgray-500 mt-1">
          五层精选漏斗：基础排除 → 行业差异化 → 价值陷阱过滤 → 估值安全边际 → 质量精选层
        </p>
      </div>
      <div class="flex items-center gap-2">
        <select
          v-model="selectedSector"
          class="px-3 py-1.5 text-sm border border-border rounded-md bg-white text-warmgray-700 focus:outline-none focus:ring-1 focus:ring-cta"
        >
          <option value="">全部行业</option>
          <option value="金融地产">金融地产</option>
          <option value="消费白马">消费白马</option>
          <option value="科技成长">科技成长</option>
          <option value="周期资源">周期资源</option>
          <option value="公用事业">公用事业</option>
          <option value="制造业">制造业</option>
        </select>
        <button
          @click="fetchData"
          :disabled="loading"
          class="px-4 py-1.5 bg-cta text-white text-sm font-medium rounded-md hover:bg-cta/90 disabled:opacity-50 transition-colors"
        >
          {{ loading ? '计算中...' : '重新筛选' }}
        </button>
      </div>
    </div>

    <!-- 筛选统计 -->
    <div v-if="filterStats" class="mb-4 grid grid-cols-2 md:grid-cols-5 gap-3">
      <div class="bg-white rounded-lg border border-border p-3">
        <div class="text-xs text-warmgray-500">全市场</div>
        <div class="text-lg font-semibold text-warmgray-900">{{ filterStats.step1_total }}</div>
      </div>
      <div class="bg-white rounded-lg border border-border p-3">
        <div class="text-xs text-warmgray-500">行业筛选后</div>
        <div class="text-lg font-semibold text-primary-700">{{ filterStats.step2_after_industry_filter }}</div>
      </div>
      <div class="bg-white rounded-lg border border-border p-3">
        <div class="text-xs text-warmgray-500">价值陷阱过滤</div>
        <div class="text-lg font-semibold text-primary-700">{{ filterStats.step3_after_value_trap }}</div>
      </div>
      <div class="bg-white rounded-lg border border-border p-3">
        <div class="text-xs text-warmgray-500">估值安全边际</div>
        <div class="text-lg font-semibold text-primary-700">{{ filterStats.step4_after_valuation }}</div>
      </div>
      <div class="bg-white rounded-lg border border-border p-3">
        <div class="text-xs text-warmgray-500">质量精选</div>
        <div class="text-lg font-semibold text-profit">{{ filterStats.step5_after_quality }}</div>
      </div>
    </div>

    <!-- 候选列表 -->
    <div class="bg-white rounded-lg border border-border overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="bg-warmgray-50 border-b border-border">
              <th class="px-4 py-3 text-left font-semibold text-warmgray-700">股票</th>
              <th class="px-4 py-3 text-left font-semibold text-warmgray-700">行业类型</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">Darwin</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">财务健康</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">综合评分</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">ROE</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">PE</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">PB</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">PE分位</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">PB分位</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="stock in candidates"
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
                <span class="font-semibold" :class="scoreClass(stock.darwin_score)">
                  {{ stock.darwin_score }}
                </span>
              </td>
              <td class="px-4 py-3 text-center">
                <span class="font-medium" :class="healthClass(stock.financial_health)">
                  {{ (stock.financial_health * 100).toFixed(1) }}%
                </span>
              </td>
              <td class="px-4 py-3 text-center">
                <span class="font-bold text-cta">{{ stock.composite_score }}</span>
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
              <td class="px-4 py-3 text-center">
                <span v-if="stock.pe_percentile_5y != null" :class="percentileClass(stock.pe_percentile_5y)">
                  {{ (stock.pe_percentile_5y * 100).toFixed(0) }}%
                </span>
                <span v-else class="text-warmgray-400">-</span>
              </td>
              <td class="px-4 py-3 text-center">
                <span v-if="stock.pb_percentile_5y != null" :class="percentileClass(stock.pb_percentile_5y)">
                  {{ (stock.pb_percentile_5y * 100).toFixed(0) }}%
                </span>
                <span v-else class="text-warmgray-400">-</span>
              </td>
            </tr>
            <tr v-if="candidates.length === 0 && !loading">
              <td colspan="10" class="px-4 py-8 text-center text-warmgray-500">
                暂无候选股票，请尝试调整筛选条件
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 说明 -->
    <div class="mt-4 text-xs text-warmgray-500 space-y-1">
      <p>五层筛选：1）基础排除（ST/退市/上市不满3年） 2）行业差异化ROE/负债率门槛 + Darwin财务健康≥0.85 3）价值陷阱过滤 4）估值安全边际（PE/PB分位&lt;70%、相对行业合理） 5）质量精选层（PE&gt;0、成交额≥1亿、Darwin≥60、PE/PB分位&lt;50%）</p>
      <p>综合评分 = Darwin评分 × 财务健康系数，按综合评分降序排列。最终约10-15只精选标的。</p>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

const loading = ref(false)
const candidates = ref([])
const filterStats = ref(null)
const selectedSector = ref('')

async function fetchData() {
  loading.value = true
  try {
    const params = new URLSearchParams()
    params.append('limit', '15')
    if (selectedSector.value) {
      params.append('sector_type', selectedSector.value)
    }
    const response = await fetch(`${API_BASE_URL}/api/long-term/selection?${params}`)
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
    console.error('长线选股数据获取失败:', e)
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

function percentileClass(p) {
  if (p <= 0.3) return 'text-profit font-medium'
  if (p <= 0.5) return 'text-cta font-medium'
  if (p <= 0.7) return 'text-warmgray-700'
  return 'text-loss font-medium'
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

onMounted(() => {
  fetchData()
})
</script>
