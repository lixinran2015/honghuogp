<template>
  <div class="p-4 lg:p-6 bg-warm-50 min-h-screen">
    <!-- 标题区 -->
    <div class="mb-6 flex items-center justify-between flex-wrap gap-3">
      <div>
        <h1 class="text-xl font-bold text-warmgray-900">长线日报</h1>
        <p class="text-sm text-warmgray-500 mt-1">
          报告日期: {{ reportData?.report_date || '-' }}
          <span v-if="reportData?.generated_at" class="text-warmgray-400 ml-2">
            生成于 {{ formatTime(reportData.generated_at) }}
          </span>
        </p>
      </div>
      <div class="flex items-center gap-2">
        <input
          v-model="selectedDate"
          type="date"
          class="px-3 py-1.5 text-sm border border-border rounded-md bg-white text-warmgray-700 focus:outline-none focus:ring-1 focus:ring-cta"
        />
        <button
          @click="fetchReport"
          :disabled="loading"
          class="px-4 py-1.5 bg-cta text-white text-sm font-medium rounded-md hover:bg-cta/90 disabled:opacity-50 transition-colors"
        >
          {{ loading ? '生成中...' : '生成日报' }}
        </button>
      </div>
    </div>

    <!-- 市场环境摘要 -->
    <div v-if="marketSummary" class="mb-4 grid grid-cols-2 md:grid-cols-4 gap-3">
      <div class="bg-white rounded-lg border border-border p-3">
        <div class="text-xs text-warmgray-500">市场趋势</div>
        <div class="text-lg font-semibold" :class="trendClass(marketSummary.trend)">
          {{ trendText(marketSummary.trend) }}
        </div>
      </div>
      <div class="bg-white rounded-lg border border-border p-3">
        <div class="text-xs text-warmgray-500">情绪指数</div>
        <div class="text-lg font-semibold text-warmgray-900">{{ marketSummary.emotion_index }}</div>
      </div>
      <div class="bg-white rounded-lg border border-border p-3">
        <div class="text-xs text-warmgray-500">策略建议</div>
        <div class="text-lg font-semibold text-cta">{{ strategyText(marketSummary.strategy) }}</div>
      </div>
      <div class="bg-white rounded-lg border border-border p-3">
        <div class="text-xs text-warmgray-500">北向资金5日</div>
        <div class="text-lg font-semibold" :class="marketSummary.north_flow_5d >= 0 ? 'text-profit' : 'text-loss'">
          {{ formatYi(marketSummary.north_flow_5d) }}
        </div>
      </div>
    </div>

    <!-- 新入选标的 -->
    <div class="bg-white rounded-lg border border-border overflow-hidden mb-4">
      <div class="px-4 py-3 border-b border-border bg-warmgray-50 flex items-center justify-between">
        <h3 class="text-sm font-semibold text-warmgray-700">新入选标的</h3>
        <span class="text-xs text-warmgray-500">共 {{ newCandidates.length }} 只</span>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="bg-warmgray-50 border-b border-border">
              <th class="px-4 py-3 text-left font-semibold text-warmgray-700">股票</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">行业</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">Darwin</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">PE分位</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">PB分位</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">ROE</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">建仓条件</th>
              <th class="px-4 py-3 text-left font-semibold text-warmgray-700">选入理由</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="s in newCandidates"
              :key="s.ts_code"
              class="border-b border-border hover:bg-warm-50 transition-colors"
            >
              <td class="px-4 py-3">
                <div class="font-medium text-warmgray-900">{{ s.name }}</div>
                <div class="text-xs text-warmgray-500">{{ s.ts_code }}</div>
              </td>
              <td class="px-4 py-3 text-center text-warmgray-600 text-xs">{{ s.industry }}</td>
              <td class="px-4 py-3 text-center">
                <span class="font-semibold" :class="scoreClass(s.darwin_score)">{{ s.darwin_score?.toFixed(0) }}</span>
              </td>
              <td class="px-4 py-3 text-center text-warmgray-700">{{ formatPercent(s.pe_percentile_5y) }}</td>
              <td class="px-4 py-3 text-center text-warmgray-700">{{ formatPercent(s.pb_percentile_5y) }}</td>
              <td class="px-4 py-3 text-center text-warmgray-700">{{ s.roe_ttm?.toFixed(1) }}%</td>
              <td class="px-4 py-3 text-center">
                <span
                  class="px-2 py-0.5 rounded text-xs font-medium"
                  :class="s.entry_analysis?.can_enter ? 'bg-profit/10 text-profit' : 'bg-loss/10 text-loss'"
                >
                  {{ s.entry_analysis?.can_enter ? '可建仓' : '未达标' }}
                </span>
                <div class="text-xs text-warmgray-500 mt-0.5">{{ s.entry_analysis?.nice_to_have_score }}/4</div>
              </td>
              <td class="px-4 py-3 text-warmgray-600 text-xs max-w-xs">{{ s.reason }}</td>
            </tr>
            <tr v-if="newCandidates.length === 0 && !loading">
              <td colspan="8" class="px-4 py-8 text-center text-warmgray-500">
                暂无新入选标的
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 持仓回顾 -->
    <div class="bg-white rounded-lg border border-border overflow-hidden mb-4">
      <div class="px-4 py-3 border-b border-border bg-warmgray-50 flex items-center justify-between">
        <h3 class="text-sm font-semibold text-warmgray-700">持仓回顾</h3>
        <span class="text-xs text-warmgray-500">共 {{ holdingReview.length }} 只持仓</span>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="bg-warmgray-50 border-b border-border">
              <th class="px-4 py-3 text-left font-semibold text-warmgray-700">股票</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">持仓阶段</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">持仓天数</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">成本</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">现价</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">市值</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">收益率</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">Darwin</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">PE分位</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="h in holdingReview"
              :key="h.ts_code"
              class="border-b border-border hover:bg-warm-50 transition-colors"
            >
              <td class="px-4 py-3">
                <div class="font-medium text-warmgray-900">{{ h.name }}</div>
                <div class="text-xs text-warmgray-500">{{ h.ts_code }}</div>
                <div class="text-xs text-warmgray-400">{{ h.industry }}</div>
              </td>
              <td class="px-4 py-3 text-center">
                <span
                  class="px-2 py-0.5 rounded text-xs font-medium"
                  :class="stageClass(h.hold_stage)"
                >
                  {{ h.hold_stage }}
                </span>
              </td>
              <td class="px-4 py-3 text-center text-warmgray-700">{{ h.hold_days }}天</td>
              <td class="px-4 py-3 text-center text-warmgray-700">{{ h.avg_cost?.toFixed(2) }}</td>
              <td class="px-4 py-3 text-center text-warmgray-700">{{ h.current_price?.toFixed(2) }}</td>
              <td class="px-4 py-3 text-center text-warmgray-700">{{ formatWan(h.market_value) }}</td>
              <td class="px-4 py-3 text-center">
                <span :class="h.return_pct >= 0 ? 'text-profit' : 'text-loss'" class="font-medium">
                  {{ h.return_pct?.toFixed(1) }}%
                </span>
              </td>
              <td class="px-4 py-3 text-center">
                <span class="font-semibold" :class="scoreClass(h.darwin_score)">{{ h.darwin_score?.toFixed(0) }}</span>
              </td>
              <td class="px-4 py-3 text-center text-warmgray-700">{{ formatPercent(h.pe_percentile_5y) }}</td>
            </tr>
            <tr v-if="holdingReview.length === 0 && !loading">
              <td colspan="9" class="px-4 py-8 text-center text-warmgray-500">
                暂无持仓记录
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 卖出分析 -->
    <div class="bg-white rounded-lg border border-border overflow-hidden mb-4">
      <div class="px-4 py-3 border-b border-border bg-warmgray-50 flex items-center justify-between">
        <h3 class="text-sm font-semibold text-warmgray-700">卖出分析</h3>
        <span class="text-xs text-warmgray-500">{{ sellAnalysis.length }} 只触发卖出信号</span>
      </div>
      <div v-if="sellAnalysis.length > 0" class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="bg-warmgray-50 border-b border-border">
              <th class="px-4 py-3 text-left font-semibold text-warmgray-700">股票</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">持仓天数</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">当前收益</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">建议卖出</th>
              <th class="px-4 py-3 text-left font-semibold text-warmgray-700">卖出理由</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="s in sellAnalysis"
              :key="s.ts_code"
              class="border-b border-border hover:bg-warm-50 transition-colors"
            >
              <td class="px-4 py-3">
                <div class="font-medium text-warmgray-900">{{ s.name }}</div>
                <div class="text-xs text-warmgray-500">{{ s.ts_code }}</div>
              </td>
              <td class="px-4 py-3 text-center text-warmgray-700">{{ s.hold_days }}天</td>
              <td class="px-4 py-3 text-center">
                <span :class="s.return_pct >= 0 ? 'text-profit' : 'text-loss'">
                  {{ s.return_pct?.toFixed(1) }}%
                </span>
              </td>
              <td class="px-4 py-3 text-center">
                <span
                  class="px-2 py-0.5 rounded text-xs font-bold"
                  :class="s.max_sell_pct >= 1.0 ? 'bg-loss/15 text-loss' : s.max_sell_pct >= 0.5 ? 'bg-warning/15 text-warning' : 'bg-cta/10 text-cta'"
                >
                  {{ (s.max_sell_pct * 100).toFixed(0) }}%
                </span>
              </td>
              <td class="px-4 py-3 text-warmgray-600 text-xs max-w-sm">
                {{ s.reasons?.join('；') }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="px-4 py-8 text-center text-warmgray-500">
        暂无卖出信号
      </div>
    </div>

    <!-- 告警汇总 -->
    <div v-if="alertSummary?.counts" class="bg-white rounded-lg border border-border overflow-hidden">
      <div class="px-4 py-3 border-b border-border bg-warmgray-50 flex items-center justify-between">
        <h3 class="text-sm font-semibold text-warmgray-700">告警汇总</h3>
        <div class="flex items-center gap-3">
          <span class="text-xs px-2 py-0.5 rounded font-medium bg-loss/10 text-loss">
            严重 {{ alertSummary.counts.CRITICAL || 0 }}
          </span>
          <span class="text-xs px-2 py-0.5 rounded font-medium bg-warning/10 text-warning">
            警告 {{ alertSummary.counts.WARNING || 0 }}
          </span>
          <span class="text-xs px-2 py-0.5 rounded font-medium bg-cta/10 text-cta">
            提示 {{ alertSummary.counts.NOTICE || 0 }}
          </span>
        </div>
      </div>
      <div v-if="alertSummary.recent?.length > 0" class="divide-y divide-border">
        <div
          v-for="a in alertSummary.recent"
          :key="`${a.ts_code}-${a.created_at}`"
          class="px-4 py-3 flex items-start gap-3"
        >
          <span
            class="mt-0.5 w-2 h-2 rounded-full flex-shrink-0"
            :class="a.level === 'CRITICAL' ? 'bg-loss' : a.level === 'WARNING' ? 'bg-warning' : 'bg-cta'"
          />
          <div class="flex-1 min-w-0">
            <div class="text-sm font-medium text-warmgray-800">{{ a.ts_code }} — {{ a.alert_type }}</div>
            <div class="text-xs text-warmgray-500 mt-0.5">{{ a.message }}</div>
            <div class="text-xs text-warmgray-400 mt-0.5">{{ a.created_at }}</div>
          </div>
        </div>
      </div>
      <div v-else class="px-4 py-8 text-center text-warmgray-500">
        暂无未解决告警
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

const loading = ref(false)
const selectedDate = ref('')
const reportData = ref(null)
const marketSummary = ref(null)
const newCandidates = ref([])
const holdingReview = ref([])
const sellAnalysis = ref([])
const alertSummary = ref(null)

async function fetchReport() {
  loading.value = true
  try {
    const url = selectedDate.value
      ? `${API_BASE_URL}/api/long-term/daily-report?trade_date=${selectedDate.value}`
      : `${API_BASE_URL}/api/long-term/daily-report`
    const response = await fetch(url)
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const result = await response.json()
    const data = result.data || {}
    reportData.value = data
    marketSummary.value = data.market_summary || null
    newCandidates.value = data.new_candidates || []
    holdingReview.value = data.holding_review || []
    sellAnalysis.value = data.sell_analysis || []
    alertSummary.value = data.alert_summary || null
    if (data.report_date && !selectedDate.value) {
      selectedDate.value = data.report_date
    }
  } catch (e) {
    console.error('日报获取失败:', e)
  } finally {
    loading.value = false
  }
}

function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

function formatPercent(value) {
  if (value === null || value === undefined) return '-'
  return (value * 100).toFixed(1) + '%'
}

function formatWan(value) {
  if (!value) return '-'
  const wan = value / 10000
  if (wan >= 10000) return (wan / 10000).toFixed(2) + '亿'
  return wan.toFixed(1) + '万'
}

function formatYi(value) {
  if (value === null || value === undefined) return '-'
  const yi = value / 100000000
  return (yi >= 0 ? '+' : '') + yi.toFixed(2) + '亿'
}

function scoreClass(score) {
  if (score >= 70) return 'text-profit'
  if (score >= 50) return 'text-cta'
  return 'text-loss'
}

function trendClass(trend) {
  if (trend === 'BULLISH') return 'text-profit'
  if (trend === 'BEARISH') return 'text-loss'
  return 'text-warmgray-900'
}

function trendText(trend) {
  const map = { BULLISH: '牛市', BEARISH: '熊市', UNKNOWN: '未知', BALANCED: '震荡' }
  return map[trend] || trend
}

function strategyText(strategy) {
  const map = { AGGRESSIVE: '积极', DEFENSIVE: '防御', BALANCED: '均衡' }
  return map[strategy] || strategy
}

function stageClass(stage) {
  const map = {
    '建仓期': 'bg-cta/10 text-cta',
    '观察期': 'bg-warm-100 text-warmgray-700',
    '持有期': 'bg-profit/10 text-profit',
    '中期持有': 'bg-primary-100 text-primary-700',
    '长期持有': 'bg-profit/15 text-profit',
  }
  return map[stage] || 'bg-warm-100 text-warmgray-700'
}

onMounted(() => {
  fetchReport()
})
</script>
