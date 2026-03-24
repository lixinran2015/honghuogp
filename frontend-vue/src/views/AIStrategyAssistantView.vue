<template>
  <div class="p-6 max-w-6xl mx-auto space-y-6">
    <header class="flex items-center justify-between">
      <div>
        <h2 class="text-2xl font-semibold text-gray-900">AI 策略助手</h2>
        <p class="mt-1 text-sm text-gray-500">
          用自然语言描述你的交易想法，生成一份结构化的「策略配置草案」，后续可接入回测与实盘。
        </p>
      </div>
    </header>

    <!-- 上：输入区域 / 下：配置预览 + 回测结果 -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <!-- 输入卡片 -->
      <div class="bg-white border border-gray-100 rounded-xl shadow-sm p-4 space-y-4">
        <h3 class="text-sm font-medium text-gray-800">策略描述</h3>

        <div class="space-y-3">
          <label class="block text-xs font-medium text-gray-500">
            自然语言描述（必填）
          </label>
          <textarea
            v-model="form.description"
            rows="8"
            class="w-full rounded-lg border-gray-200 focus:border-primary-500 focus:ring-primary-500 text-sm"
            placeholder="示例：做短线启动龙头，只参与放量突破 20 日新高的首板/二板，结合 20 日动量和 20 日均换手筛掉低流动性个股，单票不超过 20% 仓位，典型持有 3~5 天……"
          />
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div class="space-y-1">
            <label class="block text-xs font-medium text-gray-500">
              策略目标（可选）
            </label>
            <input
              v-model="form.objective"
              type="text"
              class="w-full rounded-lg border-gray-200 focus:border-primary-500 focus:ring-primary-500 text-sm"
              placeholder="例如：稳健超越沪深300 / 做日内龙头等"
            />
          </div>
          <div class="space-y-1">
            <label class="block text-xs font-medium text-gray-500">
              风险偏好（可选）
            </label>
            <select
              v-model="form.risk_preference"
              class="w-full rounded-lg border-gray-200 focus:border-primary-500 focus:ring-primary-500 text-sm"
            >
              <option value="">未指定</option>
              <option value="保守">保守</option>
              <option value="中性">中性</option>
              <option value="激进">激进</option>
            </select>
          </div>
          <div class="space-y-1">
            <label class="block text-xs font-medium text-gray-500">
              最大持仓数量（可选）
            </label>
            <input
              v-model.number="form.max_positions"
              type="number"
              min="1"
              class="w-full rounded-lg border-gray-200 focus:border-primary-500 focus:ring-primary-500 text-sm"
              placeholder="例如 6 / 8"
            />
          </div>
          <div class="space-y-1">
            <label class="block text-xs font-medium text-gray-500">
              单票最大仓位（0~1，可选）
            </label>
            <input
              v-model.number="form.max_position_pct"
              type="number"
              min="0"
              max="1"
              step="0.05"
              class="w-full rounded-lg border-gray-200 focus:border-primary-500 focus:ring-primary-500 text-sm"
              placeholder="例如 0.2 表示 20%"
            />
          </div>
          <div class="space-y-1">
            <label class="block text-xs font-medium text-gray-500">
              典型持有周期（交易日，可选）
            </label>
            <input
              v-model.number="form.holding_period_days"
              type="number"
              min="1"
              class="w-full rounded-lg border-gray-200 focus:border-primary-500 focus:ring-primary-500 text-sm"
              placeholder="例如 5"
            />
          </div>
        </div>

        <div class="flex items-center justify-between pt-2">
          <button
            type="button"
            class="text-xs text-gray-400 hover:text-gray-600"
            @click="fillExample"
          >
            使用示例描述
          </button>

          <div class="flex items-center gap-3">
            <span v-if="providerLabel" class="text-xs text-gray-400">
              当前提供方：{{ providerLabel }}
            </span>
            <button
              type="button"
              class="inline-flex items-center px-4 py-2 rounded-lg text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 disabled:opacity-60 disabled:cursor-not-allowed"
              :disabled="loading || !form.description.trim()"
              @click="generate"
            >
              <span v-if="!loading">生成策略配置</span>
              <span v-else>正在生成...</span>
            </button>
          </div>
        </div>
      </div>

      <!-- 配置预览卡片 -->
      <div class="bg-white border border-gray-100 rounded-xl shadow-sm p-4 h-full flex flex-col">
        <div class="flex items-center justify-between mb-2">
          <h3 class="text-sm font-medium text-gray-800">策略配置预览</h3>
          <span v-if="result" class="text-xs text-gray-400">
            可直接作为后续回测/实盘的配置输入
          </span>
        </div>

        <div class="flex-1 overflow-auto rounded-lg bg-gray-950 text-gray-100 text-xs leading-relaxed p-3">
          <pre v-if="result"><code>{{ prettyJson }}</code></pre>
          <div
            v-else
            class="h-full flex items-center justify-center text-xs text-gray-400 text-center px-4"
          >
            在左侧输入策略描述并点击「生成策略配置」，这里会展示结构化的 JSON 结果（包括入场规则、出场规则、仓位与风控约束等）。
          </div>
        </div>
      </div>
    </div>

    <!-- 回测配置与结果 -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <!-- 回测参数 -->
      <div class="bg-white border border-gray-100 rounded-xl shadow-sm p-4 space-y-3">
        <h3 class="text-sm font-medium text-gray-800">用当前配置跑一个基础回测</h3>
        <p class="text-xs text-gray-500">
          当前版本使用内置基础策略（默认 20/60 均线）作为执行载体，只把策略配置中的仓位信息映射到回测参数，后续可以逐步细化。
        </p>

        <div class="grid grid-cols-2 gap-3 mt-2">
          <div class="space-y-1">
            <label class="block text-xs font-medium text-gray-500">股票代码</label>
            <input
              v-model="btForm.symbol"
              type="text"
              class="w-full rounded-lg border-gray-200 focus:border-primary-500 focus:ring-primary-500 text-sm"
              placeholder="例如 000001.SZ"
            />
          </div>
          <div class="space-y-1">
            <label class="block text-xs font-medium text-gray-500">基础策略</label>
            <select
              v-model="btForm.base_strategy_id"
              class="w-full rounded-lg border-gray-200 focus:border-primary-500 focus:ring-primary-500 text-sm"
            >
              <option value="ma_20_60">20/60 均线（金叉买入，死叉卖出）</option>
              <option value="new_high_60">60 日新高突破</option>
              <option value="new_high_120">120 日新高突破</option>
              <option value="ma_5_20">5/20 均线</option>
            </select>
          </div>
          <div class="space-y-1">
            <label class="block text-xs font-medium text-gray-500">开始日期</label>
            <input
              v-model="btForm.start_date"
              type="date"
              class="w-full rounded-lg border-gray-200 focus:border-primary-500 focus:ring-primary-500 text-sm"
            />
          </div>
          <div class="space-y-1">
            <label class="block text-xs font-medium text-gray-500">结束日期</label>
            <input
              v-model="btForm.end_date"
              type="date"
              class="w-full rounded-lg border-gray-200 focus:border-primary-500 focus:ring-primary-500 text-sm"
            />
          </div>
          <div class="space-y-1">
            <label class="block text-xs font-medium text-gray-500">初始资金</label>
            <input
              v-model.number="btForm.initial_capital"
              type="number"
              min="10000"
              step="10000"
              class="w-full rounded-lg border-gray-200 focus:border-primary-500 focus:ring-primary-500 text-sm"
            />
          </div>
        </div>

        <div class="flex items-center justify-between pt-2">
          <span class="text-xs text-gray-400">
            会自动使用当前上方生成的策略配置作为上下文。
          </span>
          <button
            type="button"
            class="inline-flex items-center px-4 py-2 rounded-lg text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 disabled:opacity-60 disabled:cursor-not-allowed"
            :disabled="btLoading || !result || !btForm.symbol.trim()"
            @click="runBacktest"
          >
            <span v-if="!btLoading">执行回测</span>
            <span v-else>回测中...</span>
          </button>
        </div>
      </div>

      <!-- 回测结果 -->
      <div class="bg-white border border-gray-100 rounded-xl shadow-sm p-4 space-y-3">
        <div class="flex items-center justify-between">
          <h3 class="text-sm font-medium text-gray-800">回测结果概要</h3>
          <span v-if="btResult" class="text-xs text-gray-400">
            标的：{{ btResult.symbol }}，区间：{{ btResult.period }}
          </span>
        </div>

        <div v-if="btResult" class="grid grid-cols-2 gap-3 text-xs">
          <div class="space-y-1">
            <div class="text-gray-500">总收益率</div>
            <div
              :class="btResult.total_return_pct >= 0 ? 'text-emerald-600' : 'text-rose-600'"
              class="text-base font-semibold"
            >
              {{ formatPct(btResult.total_return_pct) }}
            </div>
          </div>
          <div class="space-y-1">
            <div class="text-gray-500">最大回撤</div>
            <div class="text-base font-semibold">
              {{ formatPct(btResult.max_drawdown_pct) }}
            </div>
          </div>
          <div class="space-y-1">
            <div class="text-gray-500">胜率</div>
            <div class="text-base font-semibold">
              {{ formatPct(btResult.win_rate) }}
            </div>
          </div>
          <div class="space-y-1">
            <div class="text-gray-500">交易笔数</div>
            <div class="text-base font-semibold">
              {{ btResult.total_trades }}
            </div>
          </div>
          <div class="space-y-1">
            <div class="text-gray-500">最终资金</div>
            <div class="text-base font-semibold">
              {{ formatAmount(btResult.final_capital) }}
            </div>
          </div>
          <div class="space-y-1" v-if="btResult.used_position_size != null">
            <div class="text-gray-500">使用仓位比例</div>
            <div class="text-base font-semibold">
              {{ formatPct(btResult.used_position_size * 100) }}
            </div>
          </div>
        </div>

        <div
          v-else
          class="h-full flex items-center justify-center text-xs text-gray-400 text-center px-4"
        >
          先在上方生成策略配置，然后选择标的和时间区间，点击「执行回测」查看基础回测结果。
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch, onMounted } from 'vue'
import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

const loading = ref(false)
const result = ref(null)
const provider = ref('')
const btLoading = ref(false)
const btResult = ref(null)
const equityCanvas = ref(null)

const form = ref({
  description: '',
  objective: '',
  risk_preference: '',
  max_positions: null,
  max_position_pct: null,
  holding_period_days: null,
})

const btForm = ref({
  symbol: '',
  start_date: '',
  end_date: '',
  initial_capital: 100000,
  base_strategy_id: 'ma_20_60',
})

const providerLabel = computed(() => {
  if (!provider.value) return ''
  if (provider.value === 'fallback') return '本地模板（未启用外部 AI）'
  if (provider.value === 'deepseek_or_openai') return '外部 AI（DeepSeek / OpenAI）'
  if (provider.value === 'error') return '错误（请检查后端日志）'
  return provider.value
})

const prettyJson = computed(() => {
  if (!result.value) return ''
  try {
    return JSON.stringify(result.value, null, 2)
  } catch {
    return String(result.value)
  }
})

function fillExample() {
  form.value.description =
    '主要做「短线启动龙头」，只参与刚放量突破近 20 日新高的首板或二板，要求 20 日动量为正且 20 日均换手在 5%-20% 之间，优先选择所在板块当天在涨幅前列、且个股成交额不低于 5 亿。单票不超过 20% 仓位，典型持有 3-5 天，跌破 5 日线或放量长阴则减仓/离场。'
  if (!form.value.objective) {
    form.value.objective = '在控制回撤前提下，抓取题材龙头的启动波段'
  }
  if (!form.value.risk_preference) {
    form.value.risk_preference = '激进'
  }
  if (!form.value.max_positions) {
    form.value.max_positions = 6
  }
  if (!form.value.max_position_pct) {
    form.value.max_position_pct = 0.2
  }
  if (!form.value.holding_period_days) {
    form.value.holding_period_days = 5
  }
}

async function generate() {
  if (!form.value.description.trim()) {
    alert('请先填写策略描述')
    return
  }
  loading.value = true
  provider.value = ''
  try {
    const payload = {
      description: form.value.description,
      objective: form.value.objective || undefined,
      risk_preference: form.value.risk_preference || undefined,
      max_positions: form.value.max_positions || undefined,
      max_position_pct: form.value.max_position_pct || undefined,
      holding_period_days: form.value.holding_period_days || undefined,
    }
    const resp = await axios.post(`${API_BASE_URL}/api/strategy/ai/plan`, payload)
    provider.value = resp.data?.provider || ''
    if (resp.data?.success) {
      result.value = resp.data.strategy_config
    } else {
      const err = resp.data?.strategy_config?.error || '生成失败'
      alert(err)
    }
  } catch (e) {
    console.error(e)
    alert('调用 AI 策略助手接口失败，请检查后端服务是否正常运行')
  } finally {
    loading.value = false
  }
}

function formatPct(v) {
  if (v == null || isNaN(v)) return '--'
  return `${v.toFixed(2)}%`
}

function formatAmount(v) {
  if (v == null || isNaN(v)) return '--'
  if (v >= 1e6) return `${(v / 1e6).toFixed(2)} 百万`
  if (v >= 1e4) return `${(v / 1e4).toFixed(2)} 万`
  return v.toFixed(2)
}

async function runBacktest() {
  if (!result.value) {
    alert('请先生成策略配置')
    return
  }
  if (!btForm.value.symbol.trim()) {
    alert('请先填写股票代码')
    return
  }
  btLoading.value = true
  btResult.value = null
  try {
    const payload = {
      symbol: btForm.value.symbol.trim(),
      start_date: btForm.value.start_date,
      end_date: btForm.value.end_date || undefined,
      initial_capital: btForm.value.initial_capital,
      base_strategy_id: btForm.value.base_strategy_id,
      strategy_config: result.value,
    }
    const resp = await axios.post(`${API_BASE_URL}/api/backtest/strategy-config/run`, payload)
    if (resp.data && resp.data.success) {
      btResult.value = {
        symbol: resp.data.symbol,
        period: resp.data.period,
        total_return_pct: resp.data.total_return_pct,
        max_drawdown_pct: resp.data.max_drawdown_pct,
        win_rate: resp.data.win_rate,
        total_trades: resp.data.total_trades,
        final_capital: resp.data.final_capital,
        used_position_size: resp.data.used_position_size,
      }
    } else {
      alert(resp.data?.detail || resp.data?.message || '回测失败')
    }
  } catch (e) {
    console.error(e)
    const msg =
      e.response?.data?.detail ||
      e.response?.data?.message ||
      '回测接口调用失败，请检查后端服务是否正常运行'
    alert(msg)
  } finally {
    btLoading.value = false
  }
}

function drawEquityCurve(dailyValues, initialCapital) {
  if (!equityCanvas.value || !dailyValues || !dailyValues.length) return

  const canvas = equityCanvas.value
  const ctx = canvas.getContext('2d')
  const parent = canvas.parentElement
  const width = parent.clientWidth || 400
  const height = 180

  canvas.width = width
  canvas.height = height

  ctx.clearRect(0, 0, width, height)

  const values = dailyValues.map((d) => d.value ?? d.final_value ?? initialCapital)
  const minVal = Math.min(...values) * 0.98
  const maxVal = Math.max(...values) * 1.02
  const range = maxVal - minVal || 1

  ctx.fillStyle = '#f9fafb'
  ctx.fillRect(0, 0, width, height)

  ctx.strokeStyle = '#e5e7eb'
  ctx.lineWidth = 1
  for (let i = 0; i <= 3; i++) {
    const y = (height / 3) * i
    ctx.beginPath()
    ctx.moveTo(40, y)
    ctx.lineTo(width - 16, y)
    ctx.stroke()
  }

  ctx.beginPath()
  ctx.strokeStyle = '#4f46e5'
  ctx.lineWidth = 1.8

  const xStep = values.length > 1 ? (width - 56) / (values.length - 1) : 0

  values.forEach((val, idx) => {
    const x = 40 + idx * xStep
    const y = height - ((val - minVal) / range) * height
    if (idx === 0) ctx.moveTo(x, y)
    else ctx.lineTo(x, y)
  })
  ctx.stroke()
}

watch(
  () => btResult.value,
  (val) => {
    if (!val) return
    // 该接口的 daily_values 在原始 payload 中，前端目前仅取了概要字段，
    // 这里直接不画曲线，等待后续需要时扩展为使用后端返回的 daily_values。
    // 预留函数接口，避免未来改动模板结构。
  }
)

onMounted(() => {
  // 预留：需要时可在此初始化默认日期等
})
</script>

<style scoped>
</style>

