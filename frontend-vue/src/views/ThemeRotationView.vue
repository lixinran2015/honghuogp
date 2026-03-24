<template>
  <div class="container mx-auto px-4 py-6">
    <div class="mb-6">
      <h1 class="text-2xl font-bold text-gray-800">长期主题轮动</h1>
      <p class="text-sm text-gray-500 mt-1">监控六大长期主题领涨情况与次日预测（仅供参考）</p>
    </div>

    <!-- 免责说明 -->
    <div class="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
      <strong>免责声明：</strong>本页数据与预测仅供参考，不构成任何投资建议。请独立研判，风险自担。
    </div>

    <!-- 板块涨跌幅热力图 -->
    <div class="mb-6">
      <SectorHeatmap :items="sectorItems" />
    </div>

    <!-- 昨日/今日领涨 -->
    <div class="bg-white rounded-lg shadow p-6 mb-6">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-semibold text-gray-800">昨日 / 今日领涨主题</h2>
        <span v-if="latestTradeDate && dataStaleHint" class="text-sm text-amber-600">{{ dataStaleHint }}</span>
      </div>
      <div v-if="summaryLoading" class="text-gray-500">加载中...</div>
      <div v-else-if="summaryError" class="text-red-600">{{ summaryError }}</div>
      <div v-else-if="!summary || summary.length === 0" class="space-y-3">
        <p class="text-gray-500">暂无数据</p>
        <div v-if="diagnostic" class="rounded-lg border border-gray-200 bg-gray-50 p-4 text-sm text-gray-700 space-y-2">
          <p><strong>诊断：</strong></p>
          <p v-if="!diagnostic.config_exists">配置不存在：{{ diagnostic.config_path }}</p>
          <p v-else-if="diagnostic.monitor_sector_count === 0">
            未匹配到监控板块（配置中 {{ diagnostic.themes_count }} 个主题）。
            <span v-if="diagnostic.unmapped_sector_names && diagnostic.unmapped_sector_names.length">未匹配名称示例：{{ diagnostic.unmapped_sector_names.slice(0, 8).join('、') }}</span>
            请确认 <code class="bg-gray-200 px-1 rounded">config/long_term_themes.json</code> 中的 sector_names 与 <code class="bg-gray-200 px-1 rounded">dim_sector.name</code>（东方财富行业名称）一致，或先运行「行业板块初始化」写入 dim_sector。
          </p>
          <p v-else-if="diagnostic.fact_sector_daily_row_count_monitor === 0">
            已匹配 {{ diagnostic.monitor_sector_count }} 个板块，但 <code class="bg-gray-200 px-1 rounded">fact_sector_daily</code> 无数据。
            请闭市后等待自动更新，或手动执行「板块日线更新」脚本。
          </p>
          <p v-else>
            已匹配 {{ diagnostic.monitor_sector_count }} 个板块，日线约 {{ diagnostic.fact_sector_daily_row_count_monitor }} 条，最近交易日：{{ diagnostic.latest_trade_date_monitor || diagnostic.latest_trade_date_any || '无' }}。若仍无领涨摘要，请检查最近交易日是否有数据。
          </p>
        </div>
        <button
          v-else
          type="button"
          @click="fetchDiagnostic"
          :disabled="diagnosticLoading"
          class="text-sm text-blue-600 hover:underline disabled:opacity-50"
        >
          {{ diagnosticLoading ? '加载中...' : '查看无数据原因' }}
        </button>
      </div>
      <div v-else class="space-y-4">
        <div
          v-for="(day, dayIdx) in summary"
          :key="day.trade_date"
          class="border border-gray-200 rounded-lg p-4"
        >
          <div class="text-sm font-medium text-gray-700 mb-2">
            {{ day.trade_date }}
            <span v-if="summary.length >= 2 && dayIdx === summary.length - 1" class="text-gray-500">（今日）</span>
            <span v-else-if="summary.length >= 2 && dayIdx === summary.length - 2" class="text-gray-500">（昨日）</span>
          </div>
          <div class="flex flex-wrap gap-2">
            <span
              v-for="(item, idx) in (day.top_gain || [])"
              :key="idx"
              class="inline-flex items-center px-3 py-1 rounded-full text-sm"
              :class="idx === 0 ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-700'"
            >
              {{ item.theme_name }}（{{ item.sector_name }} {{ item.change_pct != null ? (item.change_pct > 0 ? '+' : '') + Number(item.change_pct).toFixed(2) + '%' : '-' }}）
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- 明日预测领涨 -->
    <div class="bg-white rounded-lg shadow p-6 mb-6">
      <h2 class="text-lg font-semibold text-gray-800 mb-4">明日预测领涨主题</h2>
      <div v-if="predictLoading" class="text-gray-500">加载中...</div>
      <div v-else-if="predictError" class="text-red-600">{{ predictError }}</div>
      <div v-else-if="!predict" class="text-gray-500">暂无预测</div>
      <div v-else>
        <p class="text-sm text-gray-600 mb-2">
          基于 {{ predict.as_of_date }} 领涨「{{ todayLeadingDisplay }}」，预测 {{ predict.predict_date }} 可能轮动到的主题（转移概率）：
        </p>
        <template v-if="(predict.candidates || []).length > 0">
          <p class="text-base font-medium text-blue-700 mb-3">
            预测明日最可能领涨：<strong>{{ (predict.candidates[0].theme_name || THEME_NAME_MAP[predict.candidates[0].theme_code] || predict.candidates[0].theme_code) }}</strong>
            （概率 {{ (predict.candidates[0].prob * 100).toFixed(1) }}%）
          </p>
          <div class="flex flex-wrap gap-3">
            <div
              v-for="(c, i) in (predict.candidates || [])"
              :key="c.theme_code"
              class="flex items-center gap-2 px-4 py-2 rounded-lg border"
              :class="i === 0 ? 'border-blue-300 bg-blue-50' : 'border-gray-200 bg-gray-50'"
            >
              <span class="font-medium text-gray-900">{{ c.theme_name || THEME_NAME_MAP[c.theme_code] || c.theme_code }}</span>
              <span class="text-sm text-gray-600">概率 {{ (c.prob * 100).toFixed(1) }}%（样本 {{ c.sample_count }} 次）</span>
            </div>
          </div>
          <!-- 推荐：板块龙头/行业龙头 + 绝对龙头票（优先展示 Top1 预测主题） -->
          <template v-for="(c, i) in (predict.candidates || [])" :key="'leaders-' + c.theme_code">
            <div v-if="i === 0 && ((c.industry_leaders && c.industry_leaders.length) || (c.absolute_leaders && c.absolute_leaders.length))" class="mt-4 pt-4 border-t border-gray-200">
              <div class="text-sm font-medium text-gray-700 mb-2">
                「{{ c.theme_name || THEME_NAME_MAP[c.theme_code] || c.theme_code }}」推荐标的：
              </div>
              <div class="space-y-3">
                <div v-if="c.industry_leaders && c.industry_leaders.length">
                  <span class="text-xs text-gray-500">板块龙头/行业龙头：</span>
                  <div class="flex flex-wrap gap-2 mt-1">
                    <span
                      v-for="l in c.industry_leaders"
                      :key="l.ts_code"
                      class="inline-flex items-center gap-1 px-2 py-1 rounded text-sm bg-amber-50 border border-amber-200 text-amber-800"
                    >
                      {{ l.stock_name || l.ts_code }}
                      <span class="text-xs text-amber-600">({{ l.leader_type }})</span>
                    </span>
                  </div>
                </div>
                <div v-if="c.absolute_leaders && c.absolute_leaders.length">
                  <span class="text-xs text-gray-500">龙头角色·绝对龙头：</span>
                  <div class="flex flex-wrap gap-2 mt-1">
                    <span
                      v-for="l in c.absolute_leaders"
                      :key="l.ts_code"
                      class="inline-flex items-center gap-1 px-2 py-1 rounded text-sm bg-blue-50 border border-blue-200 text-blue-800"
                    >
                      {{ l.stock_name || l.ts_code }}
                      <span v-if="l.sector_name" class="text-xs text-blue-600">({{ l.sector_name }})</span>
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </template>
        </template>
        <p v-else class="text-amber-600 text-sm">暂无「{{ todayLeadingDisplay }}」的历史转移样本，无法给出预测。可展开下方「轮动规律」查看数据情况。</p>
        <p v-if="predict.message" class="text-sm mt-2" :class="predict.message.includes('数据截至') ? 'text-amber-600' : 'text-gray-500'">{{ predict.message }}</p>
      </div>
    </div>

    <!-- 规律与转移矩阵（折叠） -->
    <div class="bg-white rounded-lg shadow mb-6">
      <button
        @click="patternsOpen = !patternsOpen"
        class="w-full px-6 py-4 flex items-center justify-between text-left font-semibold text-gray-800 hover:bg-gray-50 rounded-lg"
      >
        <span>轮动规律（转移概率 / 动量·反转）</span>
        <span class="text-gray-500">{{ patternsOpen ? '▼' : '▶' }}</span>
      </button>
      <div v-show="patternsOpen" class="px-6 pb-6 border-t border-gray-100">
        <div v-if="patternsLoading" class="py-4 text-gray-500">加载中...</div>
        <div v-else-if="patternsError" class="py-4 text-red-600">{{ patternsError }}</div>
        <div v-else-if="patterns" class="py-4 space-y-4">
          <div>
            <span class="text-sm font-medium text-gray-700">样本：</span>
            <span class="text-sm text-gray-600">最近 {{ patterns.sample_days }} 个交易日，{{ patterns.total_pairs || 0 }} 个转移对</span>
          </div>
          <div v-if="patterns.momentum_ratio != null || patterns.reversal_ratio != null">
            <span class="text-sm font-medium text-gray-700">动量/反转：</span>
            <span class="text-sm text-gray-600">动量 {{ (patterns.momentum_ratio * 100).toFixed(1) }}%，反转 {{ (patterns.reversal_ratio * 100).toFixed(1) }}%</span>
          </div>
          <div v-if="transitionList.length > 0">
            <div class="text-sm font-medium text-gray-700 mb-2">转移概率（今日领涨 → 明日领涨，Top 15）</div>
            <div class="overflow-x-auto">
              <table class="min-w-full text-sm">
                <thead>
                  <tr class="border-b border-gray-200">
                    <th class="text-left py-2 pr-4">转移</th>
                    <th class="text-right py-2">概率</th>
                    <th class="text-right py-2">样本数</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="row in transitionList"
                    :key="row.key"
                    class="border-b border-gray-100"
                  >
                    <td class="py-2 pr-4">{{ row.key }}</td>
                    <td class="text-right">{{ (row.prob * 100).toFixed(1) }}%</td>
                    <td class="text-right">{{ row.count }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
          <p v-else class="text-amber-600 text-sm">
            {{ patterns.message || '暂无转移概率数据。可能原因：历史交易日不足（至少需 2 天）、板块日线未更新、或 config 中 sector_names 与 dim_sector 未匹配。请先运行「板块日线更新」并检查诊断。' }}
          </p>
        </div>
      </div>
    </div>

    <div class="text-center">
      <button
        @click="loadAll"
        :disabled="summaryLoading || predictLoading"
        class="px-6 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 text-sm"
      >
        {{ summaryLoading || predictLoading ? '加载中...' : '刷新' }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import SectorHeatmap from '../components/SectorHeatmap.vue'
import axios from 'axios'

const summary = ref([])
const latestTradeDate = ref(null)
const sectorItems = ref([])
const summaryLoading = ref(false)
const summaryError = ref('')
const predict = ref(null)
const predictLoading = ref(false)
const predictError = ref('')
const patterns = ref(null)
const patternsLoading = ref(false)
const patternsError = ref('')
const patternsOpen = ref(false)

const diagnostic = ref(null)
const diagnosticLoading = ref(false)

const summaryDays = ref(5)
const lookbackDays = ref(120)

// 主题代码→中文名映射（与 long_term_themes.json 一致，用于 API 未返回 theme_name 时的回退）
const THEME_NAME_MAP = {
  aging_health: '老龄化与健康',
  new_energy: '新能源与低碳',
  semiconductor: '半导体与高端制造',
  ai_digital: '人工智能与数字化',
  consumption: '消费升级',
  agriculture: '农业与粮食安全',
}

const todayLeadingDisplay = computed(() => {
  const p = predict.value
  if (!p) return ''
  return p.today_leading_theme_name || THEME_NAME_MAP[p.today_leading_theme] || p.today_leading_theme
})

// 数据滞后提示：最新交易日距今超过 2 天时提示需运行「板块日线更新」
const dataStaleHint = computed(() => {
  const d = latestTradeDate.value
  if (!d) return ''
  const latest = new Date(d)
  const today = new Date()
  const diffDays = Math.floor((today - latest) / (1000 * 60 * 60 * 24))
  if (diffDays > 2) return `数据截至 ${d}，已滞后 ${diffDays} 天，请运行「板块日线更新」获取最新数据`
  return ''
})

async function fetchSummary() {
  summaryLoading.value = true
  summaryError.value = ''
  try {
    const res = await fetch(`/api/sector-rotation/themed-daily-summary?days=${summaryDays.value}`)
    const json = await res.json()
    if (json.success && json.data && json.data.summary) {
      summary.value = json.data.summary
      latestTradeDate.value = json.data.latest_trade_date || null
      if (json.data.summary.length > 0) diagnostic.value = null
    } else {
      summary.value = []
      latestTradeDate.value = null
      summaryError.value = json.detail || '获取失败'
    }
  } catch (e) {
    summaryError.value = e.message || '网络错误'
    summary.value = []
    latestTradeDate.value = null
  } finally {
    summaryLoading.value = false
    if (summary.value.length === 0 && !diagnostic.value) fetchDiagnostic()
  }
}

async function fetchDiagnostic() {
  diagnosticLoading.value = true
  diagnostic.value = null
  try {
    const res = await fetch('/api/sector-rotation/diagnostic')
    const json = await res.json()
    if (json.success && json.data) diagnostic.value = json.data
  } finally {
    diagnosticLoading.value = false
  }
}

async function fetchPredict() {
  predictLoading.value = true
  predictError.value = ''
  try {
    const res = await fetch(`/api/sector-rotation/predict-next-day?top=3&lookback_days=${lookbackDays.value}`)
    const json = await res.json()
    if (json.success && json.data) {
      predict.value = json.data
    } else {
      predict.value = null
      predictError.value = json.detail || '获取失败'
    }
  } catch (e) {
    predictError.value = e.message || '网络错误'
    predict.value = null
  } finally {
    predictLoading.value = false
  }
}

async function fetchPatterns() {
  if (!patternsOpen.value) return
  patternsLoading.value = true
  patternsError.value = ''
  try {
    const res = await fetch(`/api/sector-rotation/rotation-patterns?lookback_days=${lookbackDays.value}`)
    const json = await res.json()
    if (json.success && json.data) {
      patterns.value = json.data
    } else {
      patterns.value = null
      patternsError.value = json.detail || '获取失败'
    }
  } catch (e) {
    patternsError.value = e.message || '网络错误'
    patterns.value = null
  } finally {
    patternsLoading.value = false
  }
}

const transitionList = computed(() => {
  if (!patterns.value || !patterns.value.transition_matrix) return []
  const counts = patterns.value.transition_counts || {}
  return Object.entries(patterns.value.transition_matrix)
    .map(([key, prob]) => ({ key, prob, count: counts[key] || 0 }))
    .sort((a, b) => b.prob - a.prob)
    .slice(0, 15)
})

async function fetchSectorHeatmap() {
  try {
    const res = await axios.get('/api/hot-sectors/industry-boards-with-leaders', { params: { refresh: false } })
    sectorItems.value = res.data?.items || []
  } catch {
    sectorItems.value = []
  }
}

function loadAll() {
  fetchSummary()
  fetchPredict()
  fetchSectorHeatmap()
  if (patternsOpen.value) fetchPatterns()
}

onMounted(() => {
  loadAll()
})
</script>
