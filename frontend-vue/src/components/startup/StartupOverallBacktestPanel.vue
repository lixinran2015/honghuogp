<template>
  <div>
    <!-- 回测参数 -->
    <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-5 mb-6">
      <h3 class="text-lg font-medium text-gray-800 mb-3">回测参数</h3>

      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <div class="flex flex-col gap-1">
          <label class="text-sm text-gray-600">开始日期</label>
          <input
            v-model="form.startDate"
            type="date"
            class="px-3 py-2 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <div class="flex flex-col gap-1">
          <label class="text-sm text-gray-600">结束日期</label>
          <input
            v-model="form.endDate"
            type="date"
            class="px-3 py-2 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <div class="flex flex-col gap-1">
          <label class="text-sm text-gray-600">初始资金（元）</label>
          <input
            v-model.number="form.initialCapital"
            type="number"
            min="100000"
            step="10000"
            class="px-3 py-2 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <div class="flex flex-col gap-1">
          <label class="text-sm text-gray-600">单票资金（元）</label>
          <input
            v-model.number="form.capitalPerStock"
            type="number"
            min="10000"
            step="5000"
            class="px-3 py-2 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <div class="flex flex-col gap-1">
          <label class="text-sm text-gray-600">每天最多持有票数</label>
          <input
            v-model.number="form.maxStocksPerDay"
            type="number"
            min="1"
            max="30"
            step="1"
            class="px-3 py-2 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <div class="flex flex-col gap-1">
          <label class="text-sm text-gray-600">最大持有天数（交易日）</label>
          <input
            v-model.number="form.maxHoldDays"
            type="number"
            min="1"
            max="20"
            step="1"
            class="px-3 py-2 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <div class="flex flex-col gap-1">
          <label class="text-sm text-gray-600">止损比例（-0.10 表示 -10%）</label>
          <input
            v-model.number="form.stopLoss"
            type="number"
            min="-0.3"
            max="-0.01"
            step="0.01"
            class="px-3 py-2 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <div class="flex flex-col gap-1">
          <label class="text-sm text-gray-600">最低入选得分</label>
          <input
            v-model.number="form.minScore"
            type="number"
            min="40"
            max="100"
            step="5"
            class="px-3 py-2 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <div class="flex flex-col gap-1">
          <label class="text-sm text-gray-600">风险过滤</label>
          <select
            v-model="form.riskPassed"
            class="px-3 py-2 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="all">不过滤（与单票诊断一致）</option>
            <option value="only_passed">只统计通过风险排除的（更保守）</option>
            <option value="only_not_passed">只统计有风险标记的</option>
          </select>
        </div>
      </div>

      <div class="mt-4 flex items-center justify-between gap-4 flex-wrap">
        <div class="flex items-center gap-3">
          <label class="inline-flex items-center text-sm text-gray-600">
            <input
              v-model="form.forceRecalculate"
              type="checkbox"
              class="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
            />
            <span class="ml-2">强制重新计算（忽略历史缓存）</span>
          </label>
        </div>

        <div class="flex items-center gap-3">
          <button
            @click="runBacktest"
            :disabled="loading"
            class="inline-flex items-center px-5 py-2.5 rounded-lg text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60"
          >
            <span v-if="loading">回测中...</span>
            <span v-else>运行回测</span>
          </button>
          <button
            @click="resetToDefault"
            :disabled="loading"
            class="inline-flex items-center px-4 py-2.5 rounded-lg text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 disabled:opacity-60"
          >
            重置为默认参数
          </button>
        </div>
      </div>

      <p class="mt-3 text-xs text-gray-500">
        规则概览：score≥{{ form.minScore }} 的启动信号，次一交易日开盘均匀建仓，最多持有
        {{ form.maxHoldDays }} 个交易日或止损 {{ (form.stopLoss * 100).toFixed(0) }}%。
      </p>
    </div>

    <!-- 结果区域 -->
    <div v-if="result" class="space-y-6">
      <!-- 核心指标 -->
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div class="bg-white border border-gray-100 rounded-xl p-4 shadow-sm">
          <div class="text-xs text-gray-500 mb-1">总收益率</div>
          <div
            :class="[
              'text-2xl font-semibold',
              result.stats.total_return_pct >= 0 ? 'text-emerald-600' : 'text-rose-600',
            ]"
          >
            {{ formatPct(result.stats.total_return_pct) }}
          </div>
          <div class="text-xs text-gray-500 mt-1">
            最终资金：{{ formatAmount(result.stats.final_capital) }} 元
          </div>
        </div>
        <div class="bg-white border border-gray-100 rounded-xl p-4 shadow-sm">
          <div class="text-xs text-gray-500 mb-1">胜率 / 交易次数</div>
          <div class="text-2xl font-semibold text-gray-900">
            {{ formatPct(result.stats.win_rate) }}
          </div>
          <div class="text-xs text-gray-500 mt-1">
            总交易 {{ result.stats.total_trades }} 笔（盈利
            {{ result.stats.profitable_trades }} / 亏损 {{ result.stats.losing_trades }}）
          </div>
        </div>
        <div class="bg-white border border-gray-100 rounded-xl p-4 shadow-sm">
          <div class="text-xs text-gray-500 mb-1">平均单笔收益 / 亏损</div>
          <div class="text-sm font-semibold text-emerald-600">
            平均收益：{{ formatPct(result.stats.avg_profit) }}
          </div>
          <div class="text-sm font-semibold text-rose-600 mt-1">
            平均亏损：{{ formatPct(result.stats.avg_loss) }}
          </div>
          <div class="text-xs text-gray-500 mt-1">
            盈亏比：{{ result.stats.profit_loss_ratio?.toFixed(2) }}
          </div>
        </div>
        <div class="bg-white border border-gray-100 rounded-xl p-4 shadow-sm">
          <div class="text-xs text-gray-500 mb-1">极值 / 持有天数</div>
          <div class="text-sm font-semibold text-emerald-600">
            最大单笔：{{ formatPct(result.stats.max_profit) }}
          </div>
          <div class="text-sm font-semibold text-rose-600 mt-1">
            最大回撤：{{ formatPct(result.stats.max_loss) }}
          </div>
          <div class="text-xs text-gray-500 mt-1">
            平均持有：{{ result.stats.avg_hold_days?.toFixed(1) }} 个交易日
          </div>
        </div>
      </div>

      <!-- 按计划执行 vs 实际结果 对比 -->
      <div
        v-if="planVsActual"
        class="bg-white border border-gray-100 rounded-xl p-4 shadow-sm"
      >
        <h3 class="text-sm font-medium text-gray-800 mb-2">按计划执行 vs 实际结果</h3>
        <p class="text-xs text-gray-500 mb-3">
          以统一交易计划中的止损价 / 第一目标价为基准，将每笔实际收益划分为四类，粗略评估「是否按计划拿满 / 是否止损过慢」。
        </p>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3 text-xs">
          <div>
            <div class="text-gray-500 mb-1">计划可参与笔数</div>
            <div class="text-base font-semibold text-gray-900">
              {{ planVsActual.total_with_plan || 0 }} 笔
            </div>
            <div class="text-[11px] text-gray-500 mt-1">
              计划期望：{{ formatPct(planVsActual.expected_return_pct_avg) }}，
              计划止损：{{ formatPct(planVsActual.stop_loss_pct_avg) }}
            </div>
          </div>
          <div>
            <div class="text-gray-500 mb-1">达到或超过计划目标</div>
            <div class="text-base font-semibold text-emerald-600">
              {{ planVsActual.target_or_above?.count || 0 }} 笔
              （{{ formatPct(planVsActual.target_or_above?.ratio) }}）
            </div>
            <div class="text-[11px] text-gray-500 mt-1">
              平均实际：{{ formatPct(planVsActual.target_or_above?.avg_return_pct) }}
            </div>
          </div>
          <div>
            <div class="text-gray-500 mb-1">盈利但未到目标</div>
            <div class="text-base font-semibold text-blue-600">
              {{ planVsActual.positive_but_below_target?.count || 0 }} 笔
              （{{ formatPct(planVsActual.positive_but_below_target?.ratio) }}）
            </div>
            <div class="text-[11px] text-gray-500 mt-1">
              平均实际：{{ formatPct(planVsActual.positive_but_below_target?.avg_return_pct) }}
            </div>
          </div>
          <div>
            <div class="text-gray-500 mb-1">亏损表现</div>
            <div class="space-y-1">
              <div>
                <span class="text-[11px] text-gray-500">好于计划止损：</span>
                <span class="text-[11px] font-semibold text-amber-600">
                  {{ planVsActual.loss_better_than_stop?.count || 0 }} 笔
                  （{{ formatPct(planVsActual.loss_better_than_stop?.ratio) }}）
                </span>
              </div>
              <div>
                <span class="text-[11px] text-gray-500">差于计划止损：</span>
                <span class="text-[11px] font-semibold text-rose-600">
                  {{ planVsActual.worse_than_plan_stop?.count || 0 }} 笔
                  （{{ formatPct(planVsActual.worse_than_plan_stop?.ratio) }}）
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 退出原因统计 -->
      <div
        v-if="exitReasons && Object.keys(exitReasons).length"
        class="bg-white border border-gray-100 rounded-xl p-4 shadow-sm"
      >
        <h3 class="text-sm font-medium text-gray-800 mb-3">按退出原因统计</h3>
        <div class="overflow-x-auto">
          <table class="min-w-full text-xs">
            <thead>
              <tr class="bg-gray-50 text-gray-600">
                <th class="px-3 py-2 text-left font-medium">退出原因</th>
                <th class="px-3 py-2 text-right font-medium">笔数</th>
                <th class="px-3 py-2 text-right font-medium">平均收益</th>
                <th class="px-3 py-2 text-right font-medium">胜率</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(v, k) in exitReasons"
                :key="k"
                class="border-t border-gray-100"
              >
                <td class="px-3 py-2 text-gray-700">
                  {{ exitReasonLabel(k) }}
                </td>
                <td class="px-3 py-2 text-right text-gray-700">
                  {{ v.count }}
                </td>
                <td
                  class="px-3 py-2 text-right"
                  :class="v.avg_return_pct >= 0 ? 'text-emerald-600' : 'text-rose-600'"
                >
                  {{ formatPct(v.avg_return_pct) }}
                </td>
                <td class="px-3 py-2 text-right text-gray-700">
                  {{ formatPct(v.win_rate) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 因子分组统计 -->
      <div
        v-if="factorBuckets && factorBuckets.mom_20d"
        class="bg-white border border-gray-100 rounded-xl p-4 shadow-sm"
      >
        <h3 class="text-sm font-medium text-gray-800 mb-3">按 20 日动量（mom_20d）分组统计</h3>
        <p class="text-xs text-gray-500 mb-2">
          以每笔交易的买入日为基准，按 20 日涨幅分为三档，统计各档的平均单笔收益与胜率，帮助评估「强势启动」是否更值得参与。
        </p>
        <div class="overflow-x-auto">
          <table class="min-w-full text-xs">
            <thead>
              <tr class="bg-gray-50 text-gray-600">
                <th class="px-3 py-2 text-left font-medium">动量分组（买入日前 20 日涨幅）</th>
                <th class="px-3 py-2 text-right font-medium">交易笔数</th>
                <th class="px-3 py-2 text-right font-medium">平均收益</th>
                <th class="px-3 py-2 text-right font-medium">胜率</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(v, key) in factorBuckets.mom_20d"
                :key="key"
                class="border-t border-gray-100"
              >
                <td class="px-3 py-2 text-gray-700">
                  {{ v.label }}
                </td>
                <td class="px-3 py-2 text-right text-gray-700">
                  {{ v.count }}
                </td>
                <td
                  class="px-3 py-2 text-right"
                  :class="v.avg_return_pct >= 0 ? 'text-emerald-600' : 'text-rose-600'"
                >
                  {{ formatPct(v.avg_return_pct) }}
                </td>
                <td class="px-3 py-2 text-right text-gray-700">
                  {{ formatPct(v.win_rate) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 交易明细 -->
      <div class="bg-white border border-gray-100 rounded-xl p-4 shadow-sm">
        <div class="flex items-center justify-between mb-3">
          <h3 class="text-sm font-medium text-gray-800">
            交易明细（共 {{ result.trades.length }} 笔）
          </h3>
          <div class="text-xs text-gray-500">
            信号：score ≥ {{ result.params.min_score }}，
            买入：T+1 开盘，
            持有 ≤ {{ result.params.max_hold_days }} 个交易日 或 止损
            {{ (result.params.stop_loss * 100).toFixed(0) }}%
          </div>
        </div>
        <div class="overflow-x-auto">
          <table class="min-w-full text-xs">
            <thead>
              <tr class="bg-gray-50 text-gray-600">
                <th class="px-3 py-2 text-left font-medium">代码</th>
                <th class="px-3 py-2 text-left font-medium">信号日</th>
                <th class="px-3 py-2 text-left font-medium">买入日</th>
                <th class="px-3 py-2 text-left font-medium">卖出日</th>
                <th class="px-3 py-2 text-right font-medium">买入价</th>
                <th class="px-3 py-2 text-right font-medium">卖出价</th>
                <th class="px-3 py-2 text-right font-medium">持仓股数</th>
                <th class="px-3 py-2 text-right font-medium">持有天数</th>
                <th class="px-3 py-2 text-right font-medium">单笔收益</th>
                <th class="px-3 py-2 text-left font-medium">退出原因</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(t, idx) in result.trades"
                :key="idx"
                class="border-t border-gray-100 hover:bg-gray-50"
              >
                <td class="px-3 py-2 text-gray-800 font-medium">
                  {{ t.ts_code }}
                </td>
                <td class="px-3 py-2 text-gray-600">
                  {{ formatDate(t.signal_date) }}
                </td>
                <td class="px-3 py-2 text-gray-600">
                  {{ formatDate(t.buy_date) }}
                </td>
                <td class="px-3 py-2 text-gray-600">
                  {{ formatDate(t.sell_date) }}
                </td>
                <td class="px-3 py-2 text-right text-gray-700">
                  {{ formatPrice(t.buy_price) }}
                </td>
                <td class="px-3 py-2 text-right text-gray-700">
                  {{ formatPrice(t.sell_price) }}
                </td>
                <td class="px-3 py-2 text-right text-gray-700">
                  {{ t.buy_quantity }}
                </td>
                <td class="px-3 py-2 text-right text-gray-700">
                  {{ t.hold_days }}
                </td>
                <td
                  class="px-3 py-2 text-right font-medium"
                  :class="t.profit_loss_pct >= 0 ? 'text-emerald-600' : 'text-rose-600'"
                >
                  {{ formatPct(t.profit_loss_pct) }}
                </td>
                <td class="px-3 py-2 text-gray-600">
                  {{ exitReasonLabel(t.exit_reason) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- 无结果提示 -->
    <div
      v-else
      class="bg-white border border-dashed border-gray-200 rounded-xl p-8 text-center text-gray-500 mt-4"
    >
      <p class="text-sm">
        还没有回测结果，点击上方「运行回测」即可基于历史启动信号评估整体策略表现。
      </p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

const loading = ref(false)
const result = ref(null)

// 默认参数：与后端接口默认值保持一致
const form = ref(createDefaultForm())

function createDefaultForm() {
  const today = new Date()
  const end = today.toISOString().split('T')[0]
  const startDate = new Date(today)
  startDate.setDate(startDate.getDate() - 365)
  const start = startDate.toISOString().split('T')[0]

  return {
    startDate: start,
    endDate: end,
    initialCapital: 300000,
    capitalPerStock: 30000,
    maxStocksPerDay: 10,
    maxHoldDays: 5,
    stopLoss: -0.1,
    minScore: 60,
    riskPassed: 'all', // all | only_passed | only_not_passed
    forceRecalculate: false,
  }
}

function resetToDefault() {
  form.value = createDefaultForm()
}

async function runBacktest() {
  loading.value = true
  try {
    const params = {
      start_date: form.value.startDate || undefined,
      end_date: form.value.endDate || undefined,
      initial_capital: form.value.initialCapital,
      capital_per_stock: form.value.capitalPerStock,
      max_stocks_per_day: form.value.maxStocksPerDay,
      max_hold_days: form.value.maxHoldDays,
      stop_loss: form.value.stopLoss,
      min_score: form.value.minScore,
      force_recalculate: form.value.forceRecalculate,
    }

    if (form.value.riskPassed === 'only_passed') {
      params.risk_passed = true
    } else if (form.value.riskPassed === 'only_not_passed') {
      params.risk_passed = false
    }

    const resp = await axios.get(`${API_BASE_URL}/api/startup/candidates/backtest`, {
      params,
    })

    if (resp.data && resp.data.success) {
      result.value = resp.data
    } else {
      const msg = resp.data?.message || resp.data?.detail || '回测失败'
      alert(msg)
    }
  } catch (e) {
    console.error(e)
    alert('回测接口调用失败，请检查后端服务是否正常运行')
  } finally {
    loading.value = false
  }
}

const planVsActual = computed(() =>
  result.value ? result.value.stats?.plan_vs_actual || null : null
)

const exitReasons = computed(() =>
  result.value ? result.value.stats?.exit_reasons || {} : {}
)
const factorBuckets = computed(() =>
  result.value ? result.value.stats?.factor_buckets || {} : {}
)

function formatPct(v) {
  if (v === null || v === undefined) return '--'
  const num = Number(v)
  if (Number.isNaN(num)) return '--'
  return `${num >= 0 ? '+' : ''}${num.toFixed(2)}%`
}

function formatAmount(v) {
  if (v === null || v === undefined) return '--'
  const num = Number(v)
  if (Number.isNaN(num)) return '--'
  if (num >= 1e6) return `${(num / 1e6).toFixed(2)} 百万`
  if (num >= 1e4) return `${(num / 1e4).toFixed(2)} 万`
  return num.toFixed(0)
}

function formatPrice(v) {
  if (v === null || v === undefined) return '--'
  const num = Number(v)
  if (Number.isNaN(num) || num <= 0) return '--'
  return num.toFixed(2)
}

function formatDate(d) {
  if (!d) return '--'
  if (typeof d === 'string') return d.slice(0, 10)
  try {
    return d.toISOString().split('T')[0]
  } catch {
    return String(d)
  }
}

function exitReasonLabel(reason) {
  if (!reason) return '未知'
  if (reason === 'max_hold_days') return '到达最大持有天数'
  if (reason === 'stop_loss') return '触发止损'
  if (reason === 'end_of_backtest') return '回测结束强制卖出'
  return reason
}
</script>

<style scoped>
</style>

