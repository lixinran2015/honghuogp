<template>
  <div class="container mx-auto px-4 py-6">
    <!-- 页面标题 -->
    <div class="mb-6">
      <h1 class="text-2xl font-bold text-gray-800">股票启动诊断</h1>
      <p class="text-sm text-gray-500 mt-1">输入股票代码和日期，查看详细的筛选结果</p>
    </div>

    <!-- 输入表单 -->
    <div class="bg-white rounded-lg shadow p-6 mb-6">
      <div class="flex items-end space-x-4">
        <div class="flex-1">
          <label class="block text-sm font-medium text-gray-700 mb-2">股票代码或名称</label>
          <input
            v-model="tsCode"
            type="text"
            placeholder="如: 000788.SZ 或 北大医药"
            class="w-full px-4 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            @keyup.enter="diagnose"
          />
        </div>
        
        <div class="flex-1">
          <label class="block text-sm font-medium text-gray-700 mb-2">交易日期</label>
          <input
            v-model="tradeDate"
            type="date"
            class="w-full px-4 py-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            @keyup.enter="diagnose"
          />
        </div>
        
        <button
          @click="diagnose"
          :disabled="loading || !tsCode || !tradeDate"
          class="px-8 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {{ loading ? '诊断中...' : '开始诊断' }}
        </button>
      </div>
    </div>

    <!-- 诊断结果 -->
    <div v-if="result" class="space-y-6">
      <!-- TradingView 日K线 + 公司简介/财务 -->
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
        <div class="lg:col-span-2">
          <TradingViewChart :ts-code="result.ts_code" />
        </div>
        <div>
          <CompanyProfileWidget :ts-code="result.ts_code" />
        </div>
      </div>

      <!-- 基本信息 -->
      <div class="bg-white rounded-lg shadow p-6">
        <h2 class="text-xl font-bold mb-4">📊 基本信息</h2>
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <div class="text-sm text-gray-500">股票名称</div>
            <div class="text-lg font-semibold">{{ result.name }}</div>
          </div>
          <div>
            <div class="text-sm text-gray-500">代码</div>
            <div class="text-lg font-semibold">{{ result.ts_code }}</div>
          </div>
          <div>
            <div class="text-sm text-gray-500">日期</div>
            <div class="text-lg font-semibold">{{ result.trade_date }}</div>
          </div>
          <div>
            <div class="text-sm text-gray-500">收盘价</div>
            <div class="text-lg font-semibold">{{ result.indicators.price.close.toFixed(2) }}元</div>
          </div>
        </div>
      </div>

      <!-- 龙头买点历史表现小卡片 -->
      <div class="bg-white rounded-lg shadow p-6">
        <h2 class="text-xl font-bold mb-3">🔥 龙头买点历史表现</h2>
        <div v-if="backtestLoading" class="text-sm text-gray-500">
          回测数据加载中...
        </div>
        <div v-else-if="backtestError" class="text-sm text-red-600">
          回测数据加载失败：{{ backtestError }}
        </div>
        <div
          v-else-if="backtestSummary && backtestSummary.total_signals > 0"
          class="space-y-2 text-sm text-gray-700"
        >
          <div>
            在最近 {{ backtestSummary.window_days }} 个自然日内，该股共出现
            <span class="font-semibold text-gray-900">{{ backtestSummary.total_signals }}</span>
            次「龙头买点」信号（以右侧确认为主）。
          </div>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-3 mt-2">
            <div class="p-3 rounded bg-emerald-50 border border-emerald-100">
              <div class="text-xs text-emerald-700 mb-1">5 日净收益（均值 / 胜率）</div>
              <div class="text-sm font-semibold text-emerald-900">
                {{ formatPct(backtestSummary.ret_5d?.avg) }} /
                {{ formatPct(backtestSummary.ret_5d?.win_rate) }}
              </div>
            </div>
            <div class="p-3 rounded bg-blue-50 border border-blue-100">
              <div class="text-xs text-blue-700 mb-1">10 日净收益（均值 / 胜率）</div>
              <div class="text-sm font-semibold text-blue-900">
                {{ formatPct(backtestSummary.ret_10d?.avg) }} /
                {{ formatPct(backtestSummary.ret_10d?.win_rate) }}
              </div>
            </div>
          </div>
          <div class="text-[11px] text-gray-400 mt-1">
            说明：以上为事件级回测结果，基于「主线前 10 + 龙头买点」规则，含双边约 0.2% 成本，仅供参考。
          </div>
        </div>
        <div v-else class="text-sm text-gray-500">
          最近一段时间内，该股尚未触发符合「龙头买点」规则的历史信号。
        </div>
      </div>

      <!-- 诊断建议 -->
      <div v-if="result.advice" class="border rounded-lg p-4 mb-4" :class="{
        'bg-green-50 border-green-300': result.result.score >= 60,
        'bg-yellow-50 border-yellow-300': result.result.score >= 30 && result.result.score < 60,
        'bg-blue-50 border-blue-300': result.result.score < 30
      }">
        <div class="flex items-center justify-between">
          <div class="text-lg font-semibold" :class="{
            'text-green-700': result.result.score >= 60,
            'text-yellow-700': result.result.score >= 30 && result.result.score < 60,
            'text-blue-700': result.result.score < 30
          }">
            {{ result.advice }}
          </div>
          <button
            @click="handleAiInterpret"
            :disabled="interpreting || !result"
            class="px-4 py-2 text-sm font-medium text-white bg-purple-600 rounded-lg hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {{ interpreting ? '解读中...' : '🤖 AI解读' }}
          </button>
        </div>
      </div>

      <!-- AI解读结果 -->
      <div v-if="aiInterpretation" class="bg-purple-50 border border-purple-300 rounded-lg p-4 mb-4">
        <div class="flex items-start justify-between mb-2">
          <h3 class="text-lg font-semibold text-purple-700">🤖 AI解读</h3>
          <button
            @click="aiInterpretation = null"
            class="text-gray-500 hover:text-gray-700 text-sm"
          >
            ✕
          </button>
        </div>
        <div class="text-sm text-gray-700 whitespace-pre-wrap">{{ aiInterpretation }}</div>
      </div>

      <!-- AI解读错误提示 -->
      <div v-if="interpretError" class="bg-red-50 border border-red-300 rounded-lg p-4 mb-4">
        <div class="flex items-center justify-between">
          <div class="text-sm text-red-700">{{ interpretError }}</div>
          <button
            @click="interpretError = null"
            class="text-red-500 hover:text-red-700 text-sm"
          >
            ✕
          </button>
        </div>
      </div>

      <!-- 金叉信息提示 -->
      <div v-if="result.golden_cross_info" class="bg-gray-50 border border-gray-300 rounded-lg p-3 mb-4">
        <div class="flex items-center text-sm">
          <span class="text-gray-700">
            🟡 金叉观察期：{{ result.golden_cross_info.date }} 发生金叉，距今 {{ result.golden_cross_info.days_since }} 个交易日
          </span>
        </div>
      </div>

      <!-- 筛选结果 -->
      <div class="bg-white rounded-lg shadow p-6">
        <h2 class="text-xl font-bold mb-4">🎯 筛选结果</h2>
        <div class="grid grid-cols-3 gap-4 mb-4">
          <div class="text-center p-4 bg-gray-50 rounded">
            <div class="text-sm text-gray-500">阶段</div>
            <div class="text-lg font-bold mt-2">
              <span :class="{
                'text-yellow-600': result.result.stage === 'golden_cross',
                'text-green-600': result.result.stage === 'confirmed',
                'text-gray-600': result.result.stage === 'filtered'
              }">
                {{ stageText(result.result.stage) }}
              </span>
            </div>
          </div>
          <div class="text-center p-4 bg-gray-50 rounded">
            <div class="text-sm text-gray-500">得分</div>
            <div class="text-lg font-bold mt-2">{{ result.result.score }}分</div>
          </div>
          <div class="text-center p-4 bg-gray-50 rounded">
            <div class="text-sm text-gray-500">是否启动</div>
            <div class="text-lg font-bold mt-2">
              <span :class="result.result.is_started ? 'text-green-600' : 'text-red-600'">
                {{ result.result.is_started ? '✅ 是' : '❌ 否' }}
              </span>
            </div>
          </div>
        </div>

        <div v-if="result.result.signals && result.result.signals.length > 0" class="mb-4">
          <div class="text-sm font-medium text-green-700 mb-2">✅ 通过的信号：</div>
          <ul class="list-disc list-inside space-y-1">
            <li v-for="(signal, idx) in result.result.signals" :key="idx" class="text-sm text-green-600">
              {{ signal }}
            </li>
          </ul>
        </div>

        <div v-if="result.result.risks && result.result.risks.length > 0">
          <div class="text-sm font-medium text-red-700 mb-2">❌ 失败原因：</div>
          <ul class="list-disc list-inside space-y-1">
            <li v-for="(risk, idx) in result.result.risks" :key="idx" class="text-sm text-red-600">
              {{ risk }}
            </li>
          </ul>
        </div>
      </div>

      <!-- 关键指标 -->
      <div class="bg-white rounded-lg shadow p-6">
        <h2 class="text-xl font-bold mb-4">📈 关键指标</h2>
        
        <!-- 均线 -->
        <div class="mb-6">
          <h3 class="font-semibold mb-3">均线数据</h3>
          <div class="grid grid-cols-4 gap-4">
            <div class="p-3 bg-blue-50 rounded">
              <div class="text-xs text-gray-600">MA5</div>
              <div class="text-lg font-bold">{{ result.indicators.ma.ma5.toFixed(2) }}</div>
            </div>
            <div class="p-3 bg-blue-50 rounded">
              <div class="text-xs text-gray-600">MA10</div>
              <div class="text-lg font-bold">{{ result.indicators.ma.ma10.toFixed(2) }}</div>
            </div>
            <div class="p-3 bg-blue-50 rounded">
              <div class="text-xs text-gray-600">MA20</div>
              <div class="text-lg font-bold">{{ result.indicators.ma.ma20.toFixed(2) }}</div>
            </div>
            <div class="p-3 bg-blue-50 rounded">
              <div class="text-xs text-gray-600">MA60</div>
              <div class="text-lg font-bold">{{ result.indicators.ma.ma60.toFixed(2) }}</div>
            </div>
          </div>
        </div>

        <!-- 成交量 -->
        <div class="mb-6">
          <h3 class="font-semibold mb-3">成交数据</h3>
          <div class="grid grid-cols-3 gap-4">
            <div class="p-3 bg-purple-50 rounded">
              <div class="text-xs text-gray-600">成交额</div>
              <div class="text-lg font-bold">{{ result.indicators.volume.amount.toFixed(2) }}亿</div>
            </div>
            <div class="p-3 bg-purple-50 rounded">
              <div class="text-xs text-gray-600">换手率</div>
              <div class="text-lg font-bold">{{ result.indicators.volume.turnover_rate.toFixed(2) }}%</div>
            </div>
            <div class="p-3 bg-purple-50 rounded">
              <div class="text-xs text-gray-600">量比</div>
              <div class="text-lg font-bold">{{ result.indicators.volume.volume_ratio.toFixed(2) }}x</div>
            </div>
          </div>
        </div>

        <!-- 其他 -->
        <div>
          <h3 class="font-semibold mb-3">其他指标</h3>
          <div class="grid grid-cols-3 gap-4">
            <div class="p-3 bg-green-50 rounded">
              <div class="text-xs text-gray-600">流通市值</div>
              <div class="text-lg font-bold">{{ result.indicators.market_cap.circulation.toFixed(2) }}亿</div>
            </div>
            <div class="p-3 bg-green-50 rounded">
              <div class="text-xs text-gray-600">前60日收盘价最高价</div>
              <div class="text-lg font-bold">{{ (result.indicators.high?.high_60d ?? result.indicators.high?.high_90d ?? result.indicators.high?.high_120d)?.toFixed(2) || 'N/A' }}元</div>
            </div>
            <div class="p-3 bg-green-50 rounded">
              <div class="text-xs text-gray-600">当前收盘价</div>
              <div class="text-lg font-bold">{{ result.indicators.price?.close?.toFixed(2) || 'N/A' }}元</div>
            </div>
          </div>
        </div>
      </div>

      <!-- 建议买卖价位 -->
      <div v-if="result.trade_plan" class="bg-white rounded-lg shadow p-6">
        <h2 class="text-xl font-bold mb-4">🧭 建议交易计划</h2>
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div class="p-3 bg-blue-50 rounded">
            <div class="text-xs text-gray-600">参考买入价</div>
            <div class="text-lg font-bold">{{ formatPrice(result.trade_plan.entry_price) }} 元</div>
            <div class="mt-1 text-xs text-gray-500">
              区间：{{ formatPrice(result.trade_plan.buy_range[0]) }} ~ {{ formatPrice(result.trade_plan.buy_range[1]) }} 元
              （±{{ result.trade_plan.buy_range_pct.toFixed(1) }}%）
            </div>
          </div>
          <div class="p-3 bg-red-50 rounded">
            <div class="text-xs text-gray-600">建议止损价</div>
            <div class="text-lg font-bold text-red-600">
              {{ formatPrice(result.trade_plan.stop_loss_price) }} 元
            </div>
            <div class="mt-1 text-xs text-gray-500">
              相对买入价：{{ result.trade_plan.stop_loss_pct.toFixed(1) }}%
            </div>
          </div>
          <div class="p-3 bg-green-50 rounded">
            <div class="text-xs text-gray-600">第一目标价</div>
            <div class="text-lg font-bold text-green-600">
              {{ formatPrice(result.trade_plan.take_profit_price) }} 元
            </div>
            <div class="mt-1 text-xs text-gray-500">
              预期收益：{{ result.trade_plan.expected_return_pct.toFixed(1) }}%（来源：{{ result.trade_plan.target_source }}）
            </div>
          </div>
          <div class="p-3 bg-gray-50 rounded">
            <div class="text-xs text-gray-600">当前收盘价</div>
            <div class="text-lg font-bold">
              {{ formatPrice(result.indicators.price.close) }} 元
            </div>
            <div class="mt-1 text-xs text-gray-500">
              相对参考买入价：{{ diffToEntry(result.indicators.price.close, result.trade_plan.entry_price) }}
            </div>
          </div>
        </div>
        <div class="mt-3 text-xs text-gray-500">
          说明：以上价位基于当前日线数据和近 90/120 日高点自动计算，仅作为风控和止盈参考，实际交易需结合盘中走势与个人风险承受能力。
        </div>
      </div>

      <!-- 条件检查 -->
      <div class="bg-white rounded-lg shadow p-6">
        <h2 class="text-xl font-bold mb-4">🔍 条件检查</h2>
        
        <div class="space-y-3">
          <div class="p-4 border rounded" :class="result.checks.golden_cross.passed ? 'border-green-300 bg-green-50' : 'border-red-300 bg-red-50'">
            <div class="flex items-center justify-between">
              <div class="font-semibold">{{ result.checks.golden_cross.passed ? '✅' : '❌' }} 5日金叉10日</div>
            </div>
            <div class="text-sm text-gray-600 mt-2">
              <div v-if="result.checks.golden_cross.from_history" class="text-yellow-700 font-semibold mb-1">
                📌 {{ result.checks.golden_cross.history_info }}
              </div>
              <div v-else>
                <div>当前: {{ result.checks.golden_cross.current }}</div>
                <div>前一日: {{ result.checks.golden_cross.previous }}</div>
              </div>
            </div>
          </div>

          <div class="p-4 border rounded" :class="result.checks.bullish_alignment.passed ? 'border-green-300 bg-green-50' : 'border-red-300 bg-red-50'">
            <div class="flex items-center justify-between">
              <div class="font-semibold">{{ result.checks.bullish_alignment.passed ? '✅' : '❌' }} 均线多头排列</div>
            </div>
            <div class="text-sm text-gray-600 mt-2">
              {{ result.checks.bullish_alignment.description }}
            </div>
          </div>

          <div class="p-4 border rounded" :class="(result.checks.breakthrough_60d || result.checks.breakthrough_90d)?.passed ? 'border-green-300 bg-green-50' : 'border-red-300 bg-red-50'">
            <div class="flex items-center justify-between">
              <div class="font-semibold">{{ (result.checks.breakthrough_60d || result.checks.breakthrough_90d)?.passed ? '✅' : '❌' }} 突破60日高点</div>
            </div>
            <div class="text-sm text-gray-600 mt-2">
              {{ (result.checks.breakthrough_60d || result.checks.breakthrough_90d)?.description || '数据未加载' }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 空状态提示 -->
    <div v-if="!result && !error && !loading" class="bg-blue-50 border border-blue-300 rounded-lg p-8 text-center">
      <div class="text-blue-700 text-lg mb-2">👆 请输入股票代码或名称开始诊断</div>
      <div class="text-sm text-blue-600">
        <div>支持输入：股票代码（如 000788.SZ）或股票名称（如 北大医药）</div>
        <div class="mt-2 text-xs">💡 提示：请选择已有交易数据的日期（今天可能还没有数据）</div>
      </div>
    </div>

    <!-- 错误提示 -->
    <div v-if="error" class="bg-red-50 border border-red-300 rounded-lg p-4">
      <div class="text-red-700 font-semibold mb-2">❌ 诊断失败</div>
      <div class="text-red-600 text-sm">{{ error }}</div>
      <div class="text-xs text-red-500 mt-2">💡 提示：如果是"未找到数据"，请尝试选择前一个交易日</div>
    </div>
  </div>

  <!-- 智能问答组件 -->
  <AiChat />
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import axios from 'axios'
import AiChat from '../components/AiChat.vue'
import TradingViewChart from '../components/TradingViewChart.vue'
import CompanyProfileWidget from '../components/CompanyProfileWidget.vue'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

const route = useRoute()
const tsCode = ref('')
const tradeDate = ref(new Date().toISOString().split('T')[0])
const loading = ref(false)
const result = ref(null)
const error = ref(null)
const interpreting = ref(false)
const aiInterpretation = ref(null)
const interpretError = ref(null)

// 龙头买点回测小卡片状态
const backtestLoading = ref(false)
const backtestError = ref(null)
const backtestSummary = ref(null)

function stageText(stage) {
  const map = {
    'golden_cross': '🟡 金叉候选',
    'confirmed': '🟢 启动确认',
    'filtered': '⚪ 已过滤'
  }
  return map[stage] || stage
}

function formatPrice(v) {
  if (v == null || isNaN(v)) return '—'
  return Number(v).toFixed(2)
}

function diffToEntry(price, entry) {
  if (!price || !entry) return '—'
  const pct = (price / entry - 1) * 100
  const sign = pct >= 0 ? '+' : ''
  return `${sign}${pct.toFixed(1)}%`
}

async function diagnose() {
  if (!tsCode.value || !tradeDate.value) {
    error.value = '请输入股票代码和日期'
    return
  }

  loading.value = true
  error.value = null
  result.value = null
  aiInterpretation.value = null
  interpretError.value = null
  backtestSummary.value = null
  backtestError.value = null

  try {
    const response = await axios.get(`${API_BASE_URL}/api/startup/diagnose/${tsCode.value}`, {
      params: { trade_date: tradeDate.value }
    })

    if (response.data.success) {
      result.value = response.data
      // 诊断成功后，顺便拉取该股在龙头买点体系下的历史表现（默认最近 12 个月，右侧信号）
      fetchLeaderBuyBacktestSummary(result.value.ts_code)
    } else {
      error.value = response.data.message || '诊断失败'
    }
  } catch (err) {
    error.value = err.response?.data?.detail || err.message || '请求失败'
  } finally {
    loading.value = false
  }
}

async function fetchLeaderBuyBacktestSummary(code) {
  if (!code) {
    backtestSummary.value = null
    return
  }
  backtestLoading.value = true
  backtestError.value = null
  try {
    const end = new Date()
    const start = new Date()
    start.setMonth(start.getMonth() - 12)
    const fmt = (d) => d.toISOString().slice(0, 10)
    const res = await axios.get(`${API_BASE_URL}/api/startup/leader-buy-backtest/summary`, {
      params: {
        start_date: fmt(start),
        end_date: fmt(end),
        min_strength: 4.0,
        signal_type: 'right',
        ts_code: code,
      },
    })
    const data = res.data || {}
    if (!data.success) {
      backtestError.value = data.message || data.detail || '加载失败'
      backtestSummary.value = null
      return
    }
    const summary = data.summary || {}
    backtestSummary.value = {
      ...summary,
      total_signals: data.total_signals || 0,
      window_days: Math.max(1, Math.round((end - start) / (1000 * 3600 * 24))),
    }
  } catch (err) {
    // eslint-disable-next-line no-console
    console.error('fetchLeaderBuyBacktestSummary error', err)
    backtestError.value = err?.response?.data?.detail || err?.message || '请求失败'
    backtestSummary.value = null
  } finally {
    backtestLoading.value = false
  }
}

function formatPct(v) {
  if (v === null || v === undefined) return '--'
  const num = Number(v)
  if (Number.isNaN(num)) return '--'
  const sign = num > 0 ? '+' : ''
  return `${sign}${num.toFixed(2)}%`
}

async function handleAiInterpret() {
  if (!result.value || !tsCode.value || !tradeDate.value) {
    interpretError.value = '请先完成诊断'
    return
  }

  interpreting.value = true
  interpretError.value = null
  aiInterpretation.value = null

  try {
    const response = await axios.post(
      `${API_BASE_URL}/api/startup/diagnose/${tsCode.value}/interpret`,
      null,
      {
        params: { trade_date: tradeDate.value }
      }
    )

    if (response.data.success && response.data.interpretation) {
      aiInterpretation.value = response.data.interpretation
    } else {
      interpretError.value = response.data.message || 'AI解读失败，请稍后重试'
    }
  } catch (err) {
    interpretError.value = err.response?.data?.message || err.message || 'AI解读请求失败'
  } finally {
    interpreting.value = false
  }
}

onMounted(() => {
  const code = route.query?.code
  if (code && typeof code === 'string') {
    const c = code.trim()
    if (/^\d{6}$/.test(c)) {
      tsCode.value = c.startsWith('6') ? `${c}.SH` : `${c}.SZ`
    } else if (/^\d{6}\.(SH|SZ|BJ)$/i.test(c)) {
      tsCode.value = c
    }
  }
})
</script>

