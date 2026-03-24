<template>
  <div class="p-8 space-y-6">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-semibold text-gray-900 mb-2">每日复盘</h1>
        <p class="text-sm text-gray-500">{{ today }} 复盘报告</p>
      </div>
      <div class="flex items-center gap-2">
        <Button size="sm" variant="primary" @click="generateReport" :disabled="generating">
          {{ generating ? 'AI 生成中...' : '生成 AI 报告' }}
        </Button>
        <Button size="sm" variant="secondary" @click="refreshData" :disabled="loading">
          {{ loading ? '加载中...' : '刷新数据' }}
        </Button>
        <Button size="sm" variant="outline" @click="openSavedReports">
          历史报告
        </Button>
      </div>
    </div>

    <!-- 大盘走势 -->
    <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
      <h2 class="text-lg font-medium text-gray-900 mb-4">大盘走势</h2>
      <div class="grid grid-cols-3 gap-4">
        <div
          v-for="idx in marketIndices"
          :key="idx.code"
          class="bg-gray-50 rounded-lg p-4"
        >
          <div class="text-sm text-gray-500 mb-1">{{ idx.name }}</div>
          <div class="text-xl font-semibold" :class="idx.change_pct >= 0 ? 'text-red-600' : 'text-green-600'">
            {{ idx.value?.toFixed(2) || '-' }}
          </div>
          <div class="text-sm" :class="idx.change_pct >= 0 ? 'text-red-500' : 'text-green-500'">
            {{ idx.change_pct >= 0 ? '+' : '' }}{{ idx.change_pct?.toFixed(2) || '0' }}%
          </div>
        </div>
      </div>
    </div>

    <!-- 持仓表现 -->
    <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
      <h2 class="text-lg font-medium text-gray-900 mb-4">持仓表现</h2>
      <div class="grid grid-cols-5 gap-3 mb-4">
        <div class="bg-gray-50 rounded-lg p-3 text-center">
          <div class="text-2xl font-semibold text-gray-900">{{ holdingsSummary.count || 0 }}</div>
          <div class="text-xs text-gray-500">持仓数量</div>
        </div>
        <div class="bg-gray-50 rounded-lg p-3 text-center">
          <div class="text-2xl font-semibold" :class="holdingsSummary.total_profit >= 0 ? 'text-red-600' : 'text-green-600'">
            {{ formatAmount(holdingsSummary.total_profit) }}
          </div>
          <div class="text-xs text-gray-500">总浮盈</div>
        </div>
        <div class="bg-gray-50 rounded-lg p-3 text-center">
          <div class="text-2xl font-semibold" :class="holdingsSummary.avg_profit_rate >= 0 ? 'text-red-600' : 'text-green-600'">
            {{ holdingsSummary.avg_profit_rate?.toFixed(1) || '0' }}%
          </div>
          <div class="text-xs text-gray-500">平均盈亏</div>
        </div>
        <div class="bg-gray-50 rounded-lg p-3 text-center">
          <div class="text-2xl font-semibold text-red-600">{{ holdingsSummary.profitable_count || 0 }}</div>
          <div class="text-xs text-gray-500">盈利只数</div>
        </div>
        <div class="bg-gray-50 rounded-lg p-3 text-center">
          <div class="text-2xl font-semibold text-green-600">{{ holdingsSummary.losing_count || 0 }}</div>
          <div class="text-xs text-gray-500">亏损只数</div>
        </div>
      </div>
      <div class="overflow-x-auto">
        <table class="min-w-full text-sm">
          <thead>
            <tr class="text-left text-gray-500 border-b">
              <th class="py-2 px-3">股票</th>
              <th class="py-2 px-3 text-right">盈亏%</th>
              <th class="py-2 px-3 text-right">浮盈</th>
              <th class="py-2 px-3 text-right">持仓天数</th>
              <th class="py-2 px-3">今日建议</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="h in holdings" :key="h.symbol" class="border-b border-gray-50 hover:bg-gray-50">
              <td class="py-2 px-3">
                <span class="font-medium">{{ h.name }}</span>
                <span class="text-gray-400 ml-1">{{ h.symbol }}</span>
              </td>
              <td class="py-2 px-3 text-right font-medium" :class="h.profit_rate >= 0 ? 'text-red-600' : 'text-green-600'">
                {{ h.profit_rate >= 0 ? '+' : '' }}{{ h.profit_rate?.toFixed(2) }}%
              </td>
              <td class="py-2 px-3 text-right" :class="h.profit_amount >= 0 ? 'text-red-600' : 'text-green-600'">
                {{ formatAmount(h.profit_amount) }}
              </td>
              <td class="py-2 px-3 text-right text-gray-600">{{ h.holding_days || '-' }}天</td>
              <td class="py-2 px-3">
                <span
                  v-if="h.today_action"
                  :class="getActionClass(h.today_action)"
                  class="px-2 py-0.5 rounded text-xs"
                >
                  {{ getActionLabel(h.today_action) }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="!holdings.length" class="text-center text-gray-400 py-8">暂无持仓</div>
      </div>
    </div>

    <!-- 操作回顾 -->
    <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-medium text-gray-900">操作回顾（近{{ historyDays }}天）</h2>
        <select v-model="historyDays" @change="refreshData" class="text-sm border rounded px-2 py-1">
          <option :value="7">7天</option>
          <option :value="30">30天</option>
          <option :value="60">60天</option>
          <option :value="90">90天</option>
        </select>
      </div>
      <div class="grid grid-cols-4 gap-3 mb-4">
        <div class="bg-gray-50 rounded-lg p-3 text-center">
          <div class="text-2xl font-semibold text-gray-900">{{ closedSummary.count || 0 }}</div>
          <div class="text-xs text-gray-500">清仓次数</div>
        </div>
        <div class="bg-gray-50 rounded-lg p-3 text-center">
          <div class="text-2xl font-semibold" :class="closedSummary.total_realized >= 0 ? 'text-red-600' : 'text-green-600'">
            {{ formatAmount(closedSummary.total_realized) }}
          </div>
          <div class="text-xs text-gray-500">已实现盈亏</div>
        </div>
        <div class="bg-gray-50 rounded-lg p-3 text-center">
          <div class="text-2xl font-semibold text-blue-600">{{ closedSummary.win_rate?.toFixed(1) || '0' }}%</div>
          <div class="text-xs text-gray-500">胜率</div>
        </div>
        <div class="bg-gray-50 rounded-lg p-3 text-center">
          <div class="text-lg font-semibold">
            <span class="text-red-600">{{ closedSummary.win_count || 0 }}</span>
            <span class="text-gray-400 mx-1">/</span>
            <span class="text-green-600">{{ closedSummary.loss_count || 0 }}</span>
          </div>
          <div class="text-xs text-gray-500">盈/亏笔数</div>
        </div>
      </div>
      <div class="overflow-x-auto">
        <table class="min-w-full text-sm">
          <thead>
            <tr class="text-left text-gray-500 border-b">
              <th class="py-2 px-3">股票</th>
              <th class="py-2 px-3 text-right">买入价</th>
              <th class="py-2 px-3 text-right">卖出价</th>
              <th class="py-2 px-3 text-right">盈亏%</th>
              <th class="py-2 px-3 text-right">已实现</th>
              <th class="py-2 px-3 text-right">持有天数</th>
              <th class="py-2 px-3">卖出日期</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in closedRecords" :key="c.symbol + c.close_date" class="border-b border-gray-50 hover:bg-gray-50">
              <td class="py-2 px-3">
                <span class="font-medium">{{ c.name }}</span>
                <span class="text-gray-400 ml-1">{{ c.symbol }}</span>
              </td>
              <td class="py-2 px-3 text-right text-gray-600">{{ c.buy_price?.toFixed(2) }}</td>
              <td class="py-2 px-3 text-right text-gray-600">{{ c.close_price?.toFixed(2) }}</td>
              <td class="py-2 px-3 text-right font-medium" :class="c.profit_rate >= 0 ? 'text-red-600' : 'text-green-600'">
                {{ c.profit_rate >= 0 ? '+' : '' }}{{ c.profit_rate?.toFixed(2) }}%
              </td>
              <td class="py-2 px-3 text-right" :class="c.realized_profit >= 0 ? 'text-red-600' : 'text-green-600'">
                {{ formatAmount(c.realized_profit) }}
              </td>
              <td class="py-2 px-3 text-right text-gray-600">{{ c.holding_days || '-' }}天</td>
              <td class="py-2 px-3 text-gray-500">{{ c.close_date }}</td>
            </tr>
          </tbody>
        </table>
        <div v-if="!closedRecords.length" class="text-center text-gray-400 py-8">暂无清仓记录</div>
      </div>
    </div>

    <!-- 操作建议遵从度分析 -->
    <div v-if="complianceSummary.total_trades > 0" class="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
      <h2 class="text-lg font-medium text-gray-900 mb-4">操作建议遵从度分析</h2>
      <div class="grid grid-cols-4 gap-3 mb-4">
        <div class="bg-gray-50 rounded-lg p-3 text-center">
          <div class="text-2xl font-semibold text-gray-900">{{ complianceSummary.total_trades }}</div>
          <div class="text-xs text-gray-500">总交易次数</div>
        </div>
        <div class="bg-gray-50 rounded-lg p-3 text-center">
          <div class="text-2xl font-semibold" :class="complianceScoreClass">
            {{ complianceSummary.avg_compliance_score?.toFixed(0) || 0 }}
          </div>
          <div class="text-xs text-gray-500">平均遵从度评分</div>
        </div>
        <div class="bg-gray-50 rounded-lg p-3 text-center">
          <div class="text-2xl font-semibold text-orange-600">
            {{ complianceSummary.tag_distribution?.['该止损没止损'] || 0 }}
          </div>
          <div class="text-xs text-gray-500">该止损没止损</div>
        </div>
        <div class="bg-gray-50 rounded-lg p-3 text-center">
          <div class="text-2xl font-semibold text-yellow-600">
            {{ complianceSummary.tag_distribution?.['该减仓没减'] || 0 }}
          </div>
          <div class="text-xs text-gray-500">该减仓没减</div>
        </div>
      </div>

      <!-- 问题标签分布 -->
      <div v-if="complianceTags.length" class="mb-4">
        <h3 class="text-sm font-medium text-gray-700 mb-2">问题分布</h3>
        <div class="flex flex-wrap gap-2">
          <span
            v-for="[tag, count] in complianceTags"
            :key="tag"
            class="px-3 py-1 rounded-full text-sm"
            :class="getComplianceTagClass(tag)"
          >
            {{ tag }}: {{ count }}
          </span>
        </div>
      </div>

      <!-- 近期问题交易 -->
      <div v-if="complianceRecords.length">
        <h3 class="text-sm font-medium text-gray-700 mb-2">近期需要改进的操作</h3>
        <div class="space-y-2">
          <div
            v-for="r in complianceRecords"
            :key="r.symbol + r.close_date"
            class="flex items-center justify-between p-3 bg-gray-50 rounded-lg"
          >
            <div class="flex items-center gap-3">
              <span class="font-medium">{{ r.name }}</span>
              <span class="text-gray-400 text-sm">{{ r.symbol }}</span>
              <div class="flex gap-1">
                <span
                  v-for="tag in r.review_tags"
                  :key="tag"
                  class="text-xs px-2 py-0.5 rounded"
                  :class="getComplianceTagClass(tag)"
                >
                  {{ tag }}
                </span>
              </div>
            </div>
            <div class="text-right">
              <div class="font-medium" :class="r.profit_rate >= 0 ? 'text-red-600' : 'text-green-600'">
                {{ r.profit_rate >= 0 ? '+' : '' }}{{ r.profit_rate?.toFixed(1) }}%
              </div>
              <div class="text-xs text-gray-400">{{ r.close_date }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- AI 复盘报告 -->
    <div v-if="aiReport" class="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-medium text-gray-900">AI 复盘报告</h2>
        <div class="flex items-center gap-2">
          <span class="text-xs text-gray-400">生成于 {{ reportGeneratedAt }}</span>
          <Button size="xs" variant="outline" @click="saveReport('daily')" :disabled="saving">
            {{ saving ? '保存中...' : '保存报告' }}
          </Button>
        </div>
      </div>
      <div class="prose prose-sm max-w-none text-gray-700" v-html="renderedReport"></div>
    </div>

    <!-- 操作模式分析 -->
    <div v-if="patternAnalysis" class="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-medium text-gray-900">操作模式分析</h2>
        <Button size="xs" variant="outline" @click="saveReport('pattern')" :disabled="saving">
          {{ saving ? '保存中...' : '保存分析' }}
        </Button>
      </div>
      <div class="prose prose-sm max-w-none text-gray-700" v-html="renderedPattern"></div>
    </div>

    <!-- 机会提示 -->
    <div v-if="opportunities.length" class="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
      <h2 class="text-lg font-medium text-gray-900 mb-4">监控中的机会</h2>
      <div class="space-y-2">
        <div
          v-for="o in opportunities"
          :key="o.symbol"
          class="flex items-center justify-between p-3 bg-gray-50 rounded-lg"
        >
          <div>
            <span class="font-medium">{{ o.name }}</span>
            <span class="text-gray-400 ml-1">{{ o.symbol }}</span>
            <span v-if="o.sector" class="ml-2 text-xs text-blue-500">{{ o.sector }}</span>
          </div>
          <div class="text-sm text-gray-500 max-w-md truncate">{{ o.reason }}</div>
        </div>
      </div>
    </div>

    <!-- 历史报告弹窗 -->
    <div v-if="showSavedReports" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50" @click.self="showSavedReports = false">
      <div class="bg-white rounded-xl shadow-xl w-full max-w-4xl max-h-[80vh] overflow-hidden flex flex-col">
        <div class="flex items-center justify-between p-4 border-b">
          <h2 class="text-lg font-medium">历史复盘报告</h2>
          <button @click="showSavedReports = false" class="text-gray-400 hover:text-gray-600">
            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div class="flex-1 overflow-auto p-4">
          <div v-if="savedReportsLoading" class="text-center py-8 text-gray-500">加载中...</div>
          <div v-else-if="!savedReports.length" class="text-center py-8 text-gray-400">暂无保存的报告</div>
          <div v-else class="space-y-3">
            <div
              v-for="r in savedReports"
              :key="r.id"
              class="border rounded-lg p-4 hover:bg-gray-50 cursor-pointer"
              @click="loadSavedReport(r.id)"
            >
              <div class="flex items-center justify-between">
                <div>
                  <span class="font-medium">{{ r.review_date }}</span>
                  <span class="ml-2 text-xs px-2 py-0.5 rounded" :class="r.report_type === 'daily' ? 'bg-blue-100 text-blue-700' : 'bg-purple-100 text-purple-700'">
                    {{ r.report_type === 'daily' ? '每日复盘' : '模式分析' }}
                  </span>
                  <span v-if="r.is_prev_day_review" class="ml-2 text-xs text-gray-500">(前日)</span>
                </div>
                <div class="flex items-center gap-2">
                  <span class="text-xs text-gray-400">{{ r.created_at }}</span>
                  <button
                    @click.stop="deleteSavedReport(r.id)"
                    class="text-red-400 hover:text-red-600 text-xs px-2 py-1"
                  >
                    删除
                  </button>
                </div>
              </div>
              <p class="text-sm text-gray-600 mt-2 line-clamp-2">{{ r.preview }}</p>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 查看报告详情弹窗 -->
    <div v-if="viewingReport" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50" @click.self="viewingReport = null">
      <div class="bg-white rounded-xl shadow-xl w-full max-w-4xl max-h-[80vh] overflow-hidden flex flex-col">
        <div class="flex items-center justify-between p-4 border-b">
          <div>
            <h2 class="text-lg font-medium">{{ viewingReport.review_date }} {{ viewingReport.report_type === 'daily' ? '每日复盘' : '模式分析' }}</h2>
            <span class="text-xs text-gray-400">保存于 {{ viewingReport.created_at }}</span>
          </div>
          <button @click="viewingReport = null" class="text-gray-400 hover:text-gray-600">
            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div class="flex-1 overflow-auto p-6">
          <div class="prose prose-sm max-w-none text-gray-700" v-html="renderedViewingReport"></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import Button from '@/components/ui/Button.vue'

const today = new Date().toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' })

const loading = ref(false)
const generating = ref(false)
const saving = ref(false)
const historyDays = ref(30)

const marketIndices = ref([])
const holdings = ref([])
const holdingsSummary = ref({})
const closedRecords = ref([])
const closedSummary = ref({})
const opportunities = ref([])
const aiReport = ref('')
const patternAnalysis = ref('')
const reportGeneratedAt = ref('')

// 遵从度分析相关
const complianceSummary = ref({
  total_trades: 0,
  avg_compliance_score: 0,
  tag_distribution: {},
  records: []
})

// 历史报告相关
const showSavedReports = ref(false)
const savedReports = ref([])
const savedReportsLoading = ref(false)
const viewingReport = ref(null)

const renderedReport = computed(() => aiReport.value ? DOMPurify.sanitize(marked(aiReport.value)) : '')
const renderedPattern = computed(() => patternAnalysis.value ? DOMPurify.sanitize(marked(patternAnalysis.value)) : '')
const renderedViewingReport = computed(() => viewingReport.value ? DOMPurify.sanitize(marked(viewingReport.value.report_content)) : '')

// 遵从度计算属性
const complianceScoreClass = computed(() => {
  const score = complianceSummary.value.avg_compliance_score || 0
  if (score >= 80) return 'text-green-600'
  if (score >= 60) return 'text-yellow-600'
  return 'text-red-600'
})

const complianceTags = computed(() => {
  const dist = complianceSummary.value.tag_distribution || {}
  return Object.entries(dist).sort((a, b) => b[1] - a[1])
})

const complianceRecords = computed(() => {
  const records = complianceSummary.value.records || []
  return records.filter(r => r.review_tags && r.review_tags.length > 0).slice(0, 5)
})

function getComplianceTagClass(tag) {
  const classes = {
    '该止损没止损': 'bg-red-100 text-red-700',
    '该减仓没减': 'bg-orange-100 text-orange-700',
    '卖飞了': 'bg-yellow-100 text-yellow-700',
    '拿太久': 'bg-blue-100 text-blue-700',
    '亏损加仓': 'bg-purple-100 text-purple-700',
    '完美执行': 'bg-green-100 text-green-700',
  }
  return classes[tag] || 'bg-gray-100 text-gray-700'
}

function formatAmount(val) {
  if (val === null || val === undefined) return '-'
  const num = Number(val)
  if (Math.abs(num) >= 10000) {
    return (num / 10000).toFixed(2) + '万'
  }
  return num.toFixed(0) + '元'
}

function getActionClass(action) {
  const map = {
    buy: 'bg-red-100 text-red-700',
    add: 'bg-red-100 text-red-700',
    hold: 'bg-gray-100 text-gray-700',
    reduce: 'bg-yellow-100 text-yellow-700',
    close: 'bg-green-100 text-green-700',
  }
  return map[action] || 'bg-gray-100 text-gray-700'
}

function getActionLabel(action) {
  const map = {
    buy: '建仓',
    add: '加仓',
    hold: '持有',
    reduce: '减仓',
    close: '清仓',
  }
  return map[action] || action
}

async function refreshData() {
  loading.value = true
  try {
    const res = await fetch(`/api/daily-review/data?history_days=${historyDays.value}`)
    const json = await res.json()
    if (json.success && json.data) {
      const d = json.data
      marketIndices.value = d.market?.indices || []
      holdings.value = d.holdings?.holdings || []
      holdingsSummary.value = d.holdings?.summary || {}
      closedRecords.value = d.closed_history?.records || []
      closedSummary.value = d.closed_history?.summary || {}
      opportunities.value = d.opportunities || []
      // 加载遵从度分析数据
      if (d.compliance_summary) {
        complianceSummary.value = d.compliance_summary
      }
    }
  } catch (e) {
    console.error('获取复盘数据失败', e)
  } finally {
    loading.value = false
  }
}

async function generateReport() {
  generating.value = true
  try {
    const res = await fetch(`/api/daily-review/report?history_days=${historyDays.value}`)
    const json = await res.json()
    if (json.success) {
      aiReport.value = json.report || ''
      reportGeneratedAt.value = json.generated_at || ''
      if (json.data) {
        marketIndices.value = json.data.market?.indices || marketIndices.value
        holdings.value = json.data.holdings?.holdings || holdings.value
        holdingsSummary.value = json.data.holdings?.summary || holdingsSummary.value
        closedRecords.value = json.data.closed_history?.records || closedRecords.value
        closedSummary.value = json.data.closed_history?.summary || closedSummary.value
        opportunities.value = json.data.opportunities || opportunities.value
      }
    }
    // 同时获取模式分析
    const patternRes = await fetch(`/api/daily-review/pattern-analysis?history_days=${historyDays.value}`)
    const patternJson = await patternRes.json()
    if (patternJson.success) {
      patternAnalysis.value = patternJson.analysis || ''
    }
  } catch (e) {
    console.error('生成 AI 报告失败', e)
  } finally {
    generating.value = false
  }
}

async function saveReport(reportType) {
  saving.value = true
  try {
    const res = await fetch(`/api/daily-review/save-report?report_type=${reportType}`, {
      method: 'POST',
    })
    const json = await res.json()
    if (json.success) {
      alert(json.message || '保存成功')
    } else {
      alert(json.message || '保存失败')
    }
  } catch (e) {
    console.error('保存报告失败', e)
    alert('保存失败')
  } finally {
    saving.value = false
  }
}

async function openSavedReports() {
  showSavedReports.value = true
  await loadSavedReportsList()
}

async function loadSavedReportsList() {
  savedReportsLoading.value = true
  try {
    const res = await fetch('/api/daily-review/saved-reports')
    const json = await res.json()
    if (json.success) {
      savedReports.value = json.reports || []
    }
  } catch (e) {
    console.error('获取历史报告列表失败', e)
  } finally {
    savedReportsLoading.value = false
  }
}

async function loadSavedReport(reportId) {
  try {
    const res = await fetch(`/api/daily-review/saved-report/${reportId}`)
    const json = await res.json()
    if (json.success && json.report) {
      viewingReport.value = json.report
    }
  } catch (e) {
    console.error('获取报告详情失败', e)
  }
}

async function deleteSavedReport(reportId) {
  if (!confirm('确定要删除这条报告吗？')) return
  try {
    const res = await fetch(`/api/daily-review/saved-report/${reportId}`, {
      method: 'DELETE',
    })
    const json = await res.json()
    if (json.success) {
      await loadSavedReportsList()
    }
  } catch (e) {
    console.error('删除报告失败', e)
  }
}

onMounted(() => {
  refreshData()
})
</script>
