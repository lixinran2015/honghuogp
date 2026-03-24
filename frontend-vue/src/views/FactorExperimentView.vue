<template>
  <div class="p-6 max-w-7xl mx-auto">
    <h2 class="text-2xl font-semibold text-gray-900 mb-4">
      因子实验室（MVP）
    </h2>

    <!-- 配置区 -->
    <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-5 mb-6">
      <h3 class="text-lg font-medium text-gray-800 mb-3">实验配置</h3>

      <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
        <div class="flex flex-col gap-1">
          <label class="text-sm text-gray-600">交易日期</label>
          <input
            v-model="form.tradeDate"
            type="date"
            class="px-3 py-2 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <div class="flex flex-col gap-1 md:col-span-2">
          <label class="text-sm text-gray-600">股票列表（ts_code，一行一个）</label>
          <textarea
            v-model="form.tsCodesInput"
            rows="3"
            class="px-3 py-2 rounded-lg border border-gray-300 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
            placeholder="示例：&#10;600519.SH&#10;000001.SZ"
          />
        </div>
      </div>

      <div class="border-t border-gray-100 mt-4 pt-4">
        <h4 class="text-sm font-medium text-gray-800 mb-2">筛选规则</h4>
        <p class="text-xs text-gray-500 mb-3">
          当前可用字段：<code>mom_10d</code>、<code>mom_20d</code>、<code>turnover_5d</code>、<code>turnover_20d</code>、<code>pe_ttm</code>、<code>pb_mrq</code>、<code>roe_ttm</code>、<code>peg</code>。
        </p>

        <div class="space-y-2">
          <div
            v-for="(rule, idx) in form.rules"
            :key="idx"
            class="flex flex-wrap items-center gap-2 text-xs"
          >
            <select
              v-model="rule.field"
              class="px-2 py-1 rounded border border-gray-300 bg-white"
            >
              <option value="mom_20d">20日动量 mom_20d</option>
              <option value="mom_10d">10日动量 mom_10d</option>
              <option value="turnover_5d">5日均换手 turnover_5d</option>
              <option value="turnover_20d">20日均换手 turnover_20d</option>
              <option value="pe_ttm">市盈率 pe_ttm</option>
              <option value="pb_mrq">市净率 pb_mrq</option>
              <option value="roe_ttm">ROE roe_ttm</option>
              <option value="peg">PEG peg</option>
            </select>
            <select
              v-model="rule.op"
              class="px-2 py-1 rounded border border-gray-300 bg-white"
            >
              <option value="gt">&gt;</option>
              <option value="ge">&gt;=</option>
              <option value="lt">&lt;</option>
              <option value="le">&lt;=</option>
              <option value="between">区间 [low, high]</option>
            </select>
            <template v-if="rule.op === 'between'">
              <input
                v-model.number="rule.value[0]"
                type="number"
                class="w-20 px-2 py-1 rounded border border-gray-300"
                placeholder="low"
              />
              <span>~</span>
              <input
                v-model.number="rule.value[1]"
                type="number"
                class="w-20 px-2 py-1 rounded border border-gray-300"
                placeholder="high"
              />
            </template>
            <template v-else>
              <input
                v-model.number="rule.value"
                type="number"
                class="w-24 px-2 py-1 rounded border border-gray-300"
                placeholder="阈值"
              />
            </template>
            <button
              v-if="form.rules.length > 1"
              @click="removeRule(idx)"
              class="px-2 py-1 rounded bg-red-50 text-red-600 border border-red-200 hover:bg-red-100"
            >
              删除
            </button>
          </div>
        </div>

        <div class="mt-3 flex items-center justify-between gap-3">
          <button
            @click="addRule"
            type="button"
            class="inline-flex items-center px-3 py-1.5 rounded-lg text-xs font-medium text-indigo-700 bg-indigo-50 hover:bg-indigo-100"
          >
            + 添加规则
          </button>
          <div class="flex items-center gap-3">
            <button
              @click="runCalc"
              :disabled="loading"
              class="inline-flex items-center px-4 py-2 rounded-lg text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 disabled:opacity-60"
            >
              仅计算因子
            </button>
            <button
              @click="runScreen"
              :disabled="loading"
              class="inline-flex items-center px-4 py-2 rounded-lg text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60"
            >
              {{ loading ? '筛选中...' : '计算并筛选' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 结果区 -->
    <div v-if="Object.keys(factorData).length" class="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
      <div class="flex items-center justify-between mb-3">
        <h3 class="text-sm font-medium text-gray-800">
          因子结果（共 {{ Object.keys(factorData).length }} 只，筛选通过 {{ passedCodes.length }} 只）
        </h3>
        <div class="text-xs text-gray-500">
          交易日：{{ tradeDate }}
        </div>
      </div>
      <div class="overflow-x-auto">
        <table class="min-w-full text-xs">
          <thead>
            <tr class="bg-gray-50 text-gray-600">
              <th class="px-3 py-2 text-left font-medium">代码</th>
              <th class="px-3 py-2 text-right font-medium">close</th>
              <th class="px-3 py-2 text-right font-medium">chg%</th>
              <th class="px-3 py-2 text-right font-medium">mom_10d</th>
              <th class="px-3 py-2 text-right font-medium">mom_20d</th>
              <th class="px-3 py-2 text-right font-medium">turn_5d</th>
              <th class="px-3 py-2 text-right font-medium">turn_20d</th>
              <th class="px-3 py-2 text-right font-medium">pe_ttm</th>
              <th class="px-3 py-2 text-right font-medium">pb_mrq</th>
              <th class="px-3 py-2 text-right font-medium">roe_ttm</th>
              <th class="px-3 py-2 text-right font-medium">peg</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="code in Object.keys(factorData)"
              :key="code"
              class="border-t border-gray-100"
              :class="passedCodes.includes(code) ? 'bg-emerald-50/40' : ''"
            >
              <td class="px-3 py-2 text-gray-800 font-medium">
                {{ code }}
              </td>
              <td class="px-3 py-2 text-right text-gray-700">
                {{ formatNumber(factorData[code].close, 2) }}
              </td>
              <td class="px-3 py-2 text-right" :class="colorClass(factorData[code].change_pct)">
                {{ formatPct(factorData[code].change_pct) }}
              </td>
              <td class="px-3 py-2 text-right" :class="colorClass(factorData[code].mom_10d)">
                {{ formatPct(factorData[code].mom_10d) }}
              </td>
              <td class="px-3 py-2 text-right" :class="colorClass(factorData[code].mom_20d)">
                {{ formatPct(factorData[code].mom_20d) }}
              </td>
              <td class="px-3 py-2 text-right text-gray-700">
                {{ formatNumber(factorData[code].turnover_5d, 2) }}
              </td>
              <td class="px-3 py-2 text-right text-gray-700">
                {{ formatNumber(factorData[code].turnover_20d, 2) }}
              </td>
              <td class="px-3 py-2 text-right text-gray-700">
                {{ formatNumber(factorData[code].pe_ttm, 1) }}
              </td>
              <td class="px-3 py-2 text-right text-gray-700">
                {{ formatNumber(factorData[code].pb_mrq, 2) }}
              </td>
              <td class="px-3 py-2 text-right text-gray-700">
                {{ formatNumber(factorData[code].roe_ttm, 1) }}
              </td>
              <td class="px-3 py-2 text-right text-gray-700">
                {{ formatNumber(factorData[code].peg, 2) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div v-else class="bg-white border border-dashed border-gray-200 rounded-xl p-8 text-center text-gray-500 mt-4">
      <p class="text-sm">
        还没有因子结果。填写股票列表和规则后，点击「计算并筛选」即可查看。
      </p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

const today = new Date()
const defaultDate = today.toISOString().split('T')[0]

const form = ref({
  tradeDate: defaultDate,
  tsCodesInput: '',
  rules: [
    { field: 'mom_20d', op: 'gt', value: 20 },
    { field: 'pe_ttm', op: 'between', value: [0, 60] },
  ],
})

const loading = ref(false)
const factorData = ref({})
const passedCodes = ref([])
const tradeDate = ref(defaultDate)

function parseTsCodes() {
  return form.value.tsCodesInput
    .split('\n')
    .map((s) => s.trim())
    .filter((s) => s.length > 0)
}

async function runCalc() {
  const codes = parseTsCodes()
  if (!codes.length) {
    alert('请至少填写一个 ts_code（如 600519.SH）')
    return
  }
  loading.value = true
  try {
    const resp = await axios.post(`${API_BASE_URL}/api/factors/calc`, {
      ts_codes: codes,
      trade_date: form.value.tradeDate || null,
    })
    if (resp.data && resp.data.success) {
      factorData.value = resp.data.data || {}
      passedCodes.value = Object.keys(factorData.value)
      tradeDate.value = resp.data.trade_date
    } else {
      alert(resp.data?.detail || resp.data?.message || '计算失败')
    }
  } catch (e) {
    console.error(e)
    alert('计算因子失败，请检查后端 /api/factors/calc 是否可用')
  } finally {
    loading.value = false
  }
}

async function runScreen() {
  const codes = parseTsCodes()
  if (!codes.length) {
    alert('请至少填写一个 ts_code（如 600519.SH）')
    return
  }
  loading.value = true
  try {
    const payload = {
      ts_codes: codes,
      trade_date: form.value.tradeDate || null,
      rules: form.value.rules.map((r) => ({
        field: r.field,
        op: r.op,
        value: r.op === 'between' ? r.value : Number(r.value),
      })),
    }
    const resp = await axios.post(`${API_BASE_URL}/api/factors/screen`, payload)
    if (resp.data && resp.data.success) {
      factorData.value = resp.data.data || {}
      passedCodes.value = resp.data.ts_codes || []
      tradeDate.value = resp.data.trade_date
    } else {
      alert(resp.data?.detail || resp.data?.message || '筛选失败')
    }
  } catch (e) {
    console.error(e)
    alert('筛选失败，请检查后端 /api/factors/screen 是否可用')
  } finally {
    loading.value = false
  }
}

function addRule() {
  form.value.rules.push({ field: 'mom_20d', op: 'gt', value: 10 })
}

function removeRule(idx) {
  form.value.rules.splice(idx, 1)
}

function formatPct(v) {
  if (v === null || v === undefined) return '--'
  const num = Number(v)
  if (Number.isNaN(num)) return '--'
  return `${num >= 0 ? '+' : ''}${num.toFixed(2)}%`
}

function formatNumber(v, digits = 2) {
  if (v === null || v === undefined) return '--'
  const num = Number(v)
  if (Number.isNaN(num)) return '--'
  return num.toFixed(digits)
}

function colorClass(v) {
  if (v === null || v === undefined) return ''
  const num = Number(v)
  if (Number.isNaN(num)) return ''
  if (num > 0) return 'text-red-600'
  if (num < 0) return 'text-green-600'
  return 'text-gray-700'
}
</script>

<style scoped>
</style>

