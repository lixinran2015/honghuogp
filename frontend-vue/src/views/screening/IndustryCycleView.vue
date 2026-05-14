<template>
  <div class="container mx-auto px-4 py-6">
    <div class="mb-6 flex items-start justify-between flex-wrap gap-4">
      <div>
        <h1 class="text-2xl font-bold text-gray-800 dark:text-gray-100">行业周期变更建议</h1>
        <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">
          基于规则引擎的行业周期与净现比/收现比阈值建议（数据源：suggest_YYYYMMDD.json）
        </p>
        <!-- 判断原则（可折叠） -->
        <div class="mt-3">
          <button
            type="button"
            @click="showPrinciples = !showPrinciples"
            class="text-sm text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1"
          >
            {{ showPrinciples ? '▼' : '▶' }} 上升期 / 成熟期 / 下滑期 判断原则
          </button>
          <div v-show="showPrinciples" class="mt-2 p-4 bg-gray-50 dark:bg-gray-800/60 border border-gray-200 dark:border-gray-700 rounded-lg text-sm text-gray-700 dark:text-gray-300 space-y-3 max-w-2xl">
            <p class="font-medium text-gray-800 dark:text-gray-100">依据：行业营收同比（YoY）、近 5 日/20 日资金净流入（亿元）、申万行业指数涨跌幅；房地产单独降级为下滑期。5 日资金判下滑时会用 20 日资金辅助过滤短期噪音。</p>
            <div>
              <span class="font-medium text-green-700 dark:text-green-400">上升期：</span>
              营收 YoY &gt; 10%，且（资金净流入，或净流出未达 -50 亿）；若净流出 &gt; 50 亿但营收 YoY &gt; 15%，则不单凭资金判下滑、按营收判上升期。
            </div>
            <div>
              <span class="font-medium text-blue-600 dark:text-blue-400">成熟期：</span>
              营收 YoY 在 0%～10%，或指数波动在 ±3% 附近；现金流与需求相对稳定（可结合资本开支等细化）。
            </div>
            <div>
              <span class="font-medium text-orange-600 dark:text-orange-400">下滑期：</span>
              营收 YoY &lt; 0%；或资金近 5 日净流出 &gt; 50 亿且营收 YoY 不高于 15%，且 20 日资金也偏弱（避免短期波动误判）；或行业为房地产（单独降级）。
            </div>
            <p class="mt-3 pt-3 border-t border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-400">
              <span class="font-medium">局限与优化方向：</span>① 营收来自财报，存在滞后，可引入业绩预告/PMI 等前瞻指标。② 50 亿为绝对值，大行业与小行业不可比，后续可改为「资金/流通市值」等相对指标。③ 成熟期可结合资本开支下降等特征细化。④ 房地产可细分到子板块（如保障房、商管）再评估。
            </p>
          </div>
        </div>
      </div>
      <div class="flex items-center gap-3 flex-wrap">
        <select
          v-model="selectedDate"
          @change="loadData"
          class="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-800"
        >
          <option value="">最新</option>
          <option v-for="d in dateList" :key="d" :value="d">{{ formatDate(d) }}</option>
        </select>
        <select
          v-model="filterCycle"
          class="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-800"
        >
          <option value="">全部周期</option>
          <option value="rising">上升期</option>
          <option value="mature">成熟期</option>
          <option value="declining">下滑期</option>
        </select>
        <select
          v-model="filterChanged"
          class="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-800"
        >
          <option value="">全部</option>
          <option value="cycle">周期有变化</option>
          <option value="threshold">阈值有变化</option>
        </select>
        <button
          @click="runCollect"
          :disabled="loading || runningCollect"
          class="px-4 py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700 disabled:opacity-50 text-sm font-medium"
        >
          {{ runningCollect ? '采集中...' : '采集数据' }}
        </button>
        <button
          @click="runSuggest"
          :disabled="loading || runningSuggest"
          class="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 text-sm font-medium"
        >
          {{ runningSuggest ? '生成中...' : '生成建议' }}
        </button>
        <button
          @click="loadData"
          :disabled="loading"
          class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm"
        >
          {{ loading ? '加载中...' : '刷新' }}
        </button>
        <button
          @click="runApply(true)"
          :disabled="loading || runningApply || !suggestions.length"
          class="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 disabled:opacity-50 text-sm"
          title="预览将写入 YAML 的变更，不实际修改"
        >
          {{ runningApply ? '执行中...' : '试跑回写' }}
        </button>
        <button
          @click="runApply(false)"
          :disabled="loading || runningApply || !suggestions.length"
          class="px-4 py-2 bg-violet-600 text-white rounded-lg hover:bg-violet-700 disabled:opacity-50 text-sm font-medium"
          title="将当前建议写回 config/industry_cash_ratio_thresholds.yaml（会备份原配置）"
        >
          {{ runningApply ? '执行中...' : '回写' }}
        </button>
      </div>
    </div>

    <div v-if="error" class="mb-4 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-red-700 dark:text-red-400">
      {{ error }}
    </div>

    <!-- 策略选择与投资提示 -->
    <div v-if="suggestions.length > 0" class="mb-6 space-y-4">
      <div class="flex items-center gap-4 flex-wrap">
        <span class="text-sm font-medium text-gray-700 dark:text-gray-300">投资策略：</span>
        <div class="flex gap-2">
          <button
            v-for="opt in strategyOptions"
            :key="opt.value"
            @click="investmentStrategy = opt.value"
            :class="[
              'px-4 py-2 rounded-lg text-sm font-medium transition-colors',
              investmentStrategy === opt.value
                ? opt.activeClass
                : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-600'
            ]"
          >
            {{ opt.label }}
          </button>
        </div>
      </div>

      <!-- 下滑期警示 -->
      <div class="p-4 bg-orange-50 dark:bg-orange-900/20 border border-orange-200 dark:border-orange-800 rounded-lg">
        <p class="text-orange-800 dark:text-orange-300 font-medium flex items-center gap-2">
          <span class="text-lg">⚠</span> 建议不要配置下滑期行业股票——需求萎缩、现金流风险高，即使配置也应以防守为主、严格控制仓位。
        </p>
        <p v-if="decliningIndustries.length > 0" class="mt-2 text-sm text-orange-700 dark:text-orange-400">
          当前下滑期行业：{{ decliningIndustries.join('、') }}
        </p>
      </div>

      <!-- 策略推荐 -->
      <div v-if="investmentStrategy !== 'all'" class="p-4 rounded-lg" :class="strategyRecommendClass">
        <p class="font-medium mb-2">{{ strategyRecommendTitle }}</p>
        <p class="text-sm opacity-90 mb-2">{{ strategyRecommendDesc }}</p>
        <p v-if="recommendedIndustries.length > 0" class="text-sm">
          <span class="font-medium">推荐关注龙头：</span>{{ recommendedIndustries.join('、') }}
        </p>
      </div>
    </div>

    <div v-if="meta" class="mb-4 text-sm text-gray-500 dark:text-gray-400">
      生成于 {{ meta.generated_at }} · 数据源 {{ meta.source_cycle_data?.split(/[/\\]/).pop() || '-' }}
    </div>

    <!-- 建议表格 -->
    <div v-if="!loading && filteredSuggestions.length > 0" class="bg-white dark:bg-gray-800 rounded-lg shadow overflow-hidden dark:border dark:border-gray-700">
      <div class="overflow-x-auto">
        <table class="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
          <thead class="bg-gray-50 dark:bg-gray-700/50">
            <tr>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-600 dark:text-gray-300 uppercase w-8"></th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-600 dark:text-gray-300 uppercase">行业</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-600 dark:text-gray-300 uppercase">当前周期</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-600 dark:text-gray-300 uppercase">建议周期</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-600 dark:text-gray-300 uppercase">净现比 当前→建议</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-600 dark:text-gray-300 uppercase">收现比 当前→建议</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-600 dark:text-gray-300 uppercase">原因</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-200 dark:divide-gray-700">
            <tr
              v-for="s in filteredSuggestions"
              :key="s.industry"
              :class="[
                'hover:bg-gray-50 dark:hover:bg-gray-700/30',
                isChanged(s) ? 'bg-amber-50/50 dark:bg-amber-900/10' : '',
                isRecommended(s) ? 'ring-1 ring-inset ring-green-400/50' : '',
                isDeclining(s) ? 'bg-orange-50/30 dark:bg-orange-900/10' : ''
              ]"
            >
              <td class="px-4 py-3">
                <span v-if="isRecommended(s)" class="text-green-600 dark:text-green-400" title="符合当前策略推荐">★</span>
                <span v-else-if="isDeclining(s)" class="text-orange-500" title="下滑期，建议规避">!</span>
              </td>
              <td class="px-4 py-3 text-sm font-medium text-gray-900 dark:text-gray-100">{{ s.industry }}</td>
              <td class="px-4 py-3">
                <span :class="cycleBadgeClass(s.current_cycle)">{{ cycleLabel(s.current_cycle) }}</span>
              </td>
              <td class="px-4 py-3">
                <span :class="cycleBadgeClass(s.suggested_cycle)">{{ cycleLabel(s.suggested_cycle) }}</span>
                <span v-if="s.current_cycle !== s.suggested_cycle" class="ml-1 text-amber-600 dark:text-amber-400">→</span>
              </td>
              <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">
                {{ ncrStr(s) }}
                <span v-if="s.current_net_cash_ratio !== s.suggested_net_cash_ratio" class="text-amber-600 dark:text-amber-400">*</span>
              </td>
              <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">
                {{ crrStr(s) }}
                <span v-if="s.current_cash_receipt_ratio !== s.suggested_cash_receipt_ratio" class="text-amber-600 dark:text-amber-400">*</span>
              </td>
              <td class="px-4 py-3 text-sm text-gray-600 dark:text-gray-400 max-w-xs truncate" :title="s.reason">{{ s.reason }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div v-else-if="!loading" class="text-center py-12 text-gray-500 dark:text-gray-400">
      暂无建议数据，请先点击「生成建议」或确保已有 <code class="px-1.5 py-0.5 bg-gray-200 dark:bg-gray-700 rounded">cycle_data_*.json</code>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''
const loading = ref(false)
const runningCollect = ref(false)
const runningSuggest = ref(false)
const runningApply = ref(false)
const error = ref('')
const dateList = ref([])
const selectedDate = ref('')
const filterCycle = ref('')
const filterChanged = ref('')
const rawData = ref(null)
const investmentStrategy = ref('steady') // steady | aggressive | all
const showPrinciples = ref(false) // 判断原则折叠

const strategyOptions = [
  { value: 'steady', label: '稳健（成熟期龙头）', activeClass: 'bg-blue-600 text-white' },
  { value: 'aggressive', label: '激进（上升期龙头）', activeClass: 'bg-green-600 text-white' },
  { value: 'all', label: '仅参考', activeClass: 'bg-gray-600 text-white' },
]

const meta = computed(() => {
  if (!rawData.value) return null
  return {
    generated_at: rawData.value.generated_at,
    source_cycle_data: rawData.value.source_cycle_data
  }
})

const suggestions = computed(() => rawData.value?.suggestions || [])

const decliningIndustries = computed(() => {
  return suggestions.value
    .filter(s => s.suggested_cycle === 'declining' || s.current_cycle === 'declining')
    .map(s => s.industry)
})

const recommendedIndustries = computed(() => {
  const cycle = investmentStrategy.value === 'steady' ? 'mature' : investmentStrategy.value === 'aggressive' ? 'rising' : null
  if (!cycle) return []
  return suggestions.value
    .filter(s => (s.suggested_cycle === cycle || s.current_cycle === cycle))
    .map(s => s.industry)
})

const strategyRecommendClass = computed(() => {
  if (investmentStrategy.value === 'steady') return 'bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 text-blue-800 dark:text-blue-300'
  if (investmentStrategy.value === 'aggressive') return 'bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 text-green-800 dark:text-green-300'
  return ''
})

const strategyRecommendTitle = computed(() => {
  if (investmentStrategy.value === 'steady') return '稳健投资者：优先考虑成熟期行业龙头'
  if (investmentStrategy.value === 'aggressive') return '激进投资者：可关注上升期行业龙头'
  return ''
})

const strategyRecommendDesc = computed(() => {
  if (investmentStrategy.value === 'steady') return '成熟期行业现金流稳定、ROE 较高，适合中长期持有，波动相对可控。'
  if (investmentStrategy.value === 'aggressive') return '上升期行业景气度高，弹性大，但需控制仓位、关注估值，优选龙头。'
  return ''
})

const filteredSuggestions = computed(() => {
  let list = suggestions.value
  if (filterCycle.value) {
    list = list.filter(s => s.current_cycle === filterCycle.value || s.suggested_cycle === filterCycle.value)
  }
  if (filterChanged.value === 'cycle') {
    list = list.filter(s => s.current_cycle !== s.suggested_cycle)
  } else if (filterChanged.value === 'threshold') {
    list = list.filter(s =>
      s.current_net_cash_ratio !== s.suggested_net_cash_ratio ||
      s.current_cash_receipt_ratio !== s.suggested_cash_receipt_ratio
    )
  }
  return list
})

function cycleLabel(c) {
  const map = { rising: '上升期', mature: '成熟期', declining: '下滑期' }
  return map[c] || c || '-'
}

function cycleBadgeClass(c) {
  const base = 'px-2 py-0.5 rounded text-xs'
  if (c === 'rising') return base + ' bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-400'
  if (c === 'mature') return base + ' bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-400'
  if (c === 'declining') return base + ' bg-orange-100 dark:bg-orange-900/40 text-orange-700 dark:text-orange-400'
  return base + ' bg-gray-200 dark:bg-gray-600 text-gray-600 dark:text-gray-400'
}

function ncrStr(s) {
  const a = s.current_net_cash_ratio ?? '-'
  const b = s.suggested_net_cash_ratio ?? '-'
  return `${a} → ${b}`
}

function crrStr(s) {
  const a = s.current_cash_receipt_ratio ?? '-'
  const b = s.suggested_cash_receipt_ratio ?? '-'
  return `${a} → ${b}`
}

function isRecommended(s) {
  if (investmentStrategy.value === 'all') return false
  const cycle = investmentStrategy.value === 'steady' ? 'mature' : 'rising'
  return s.suggested_cycle === cycle || s.current_cycle === cycle
}

function isDeclining(s) {
  return s.suggested_cycle === 'declining' || s.current_cycle === 'declining'
}

function isChanged(s) {
  return s.current_cycle !== s.suggested_cycle ||
    s.current_net_cash_ratio !== s.suggested_net_cash_ratio ||
    s.current_cash_receipt_ratio !== s.suggested_cash_receipt_ratio
}

function formatDate(d) {
  if (!d) return ''
  return `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}`
}

async function runCollect() {
  runningCollect.value = true
  error.value = ''
  try {
    const res = await axios.post(`${API_BASE}/api/data-warehouse/industry-cycle/run-collect`)
    if (res.data?.success) {
      // 用本次采集生成的日期更新选中，便于看到新数据
      if (res.data?.date) selectedDate.value = res.data.date
      if (res.data?.path) console.info('行业周期采集已写入:', res.data.path)
      await runSuggest()
    } else {
      error.value = res.data?.message || '采集失败'
    }
  } catch (e) {
    error.value = e.response?.data?.detail || e.message || '采集失败'
  } finally {
    runningCollect.value = false
  }
}

async function runSuggest() {
  runningSuggest.value = true
  error.value = ''
  try {
    const res = await axios.post(`${API_BASE}/api/data-warehouse/industry-cycle/run-suggest`)
    if (res.data?.success) {
      if (res.data.date) selectedDate.value = res.data.date
      await loadData()
    } else {
      error.value = res.data?.message || '生成失败'
    }
  } catch (e) {
    error.value = e.response?.data?.detail || e.message || '生成失败'
  } finally {
    runningSuggest.value = false
  }
}

async function runApply(dryRun) {
  if (!dryRun && !confirm('确定将当前建议回写到 config/industry_cash_ratio_thresholds.yaml？原配置会备份为 .bak 文件。')) return
  runningApply.value = true
  error.value = ''
  try {
    const params = { dry_run: dryRun }
    if (selectedDate.value) params.suggest_date = selectedDate.value
    const res = await axios.post(`${API_BASE}/api/data-warehouse/industry-cycle/apply`, null, { params })
    if (res.data?.success) {
      if (dryRun && res.data.preview) {
        alert('试跑结果（未写入）：\n\n' + res.data.preview)
      } else {
        if (res.data.suggest_date) selectedDate.value = res.data.suggest_date
        await loadData()
        alert(res.data.message || '回写成功')
      }
    } else {
      error.value = res.data?.message || '回写失败'
    }
  } catch (e) {
    error.value = e.response?.data?.detail || e.message || '回写失败'
  } finally {
    runningApply.value = false
  }
}

async function loadData() {
  loading.value = true
  error.value = ''
  try {
    const listRes = await axios.get(`${API_BASE}/api/data-warehouse/industry-cycle/suggest-list`)
    if (listRes.data?.success && listRes.data.data?.length) {
      dateList.value = listRes.data.data
      if (!selectedDate.value) selectedDate.value = dateList.value[0]
    }
    const params = selectedDate.value ? { date: selectedDate.value } : {}
    const res = await axios.get(`${API_BASE}/api/data-warehouse/industry-cycle/suggest`, { params })
    if (res.data?.success) {
      rawData.value = res.data.data
    } else {
      rawData.value = null
      error.value = res.data?.message || '加载失败'
    }
  } catch (e) {
    error.value = e.response?.data?.detail || e.message || '加载失败'
    rawData.value = null
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadData()
})
</script>
