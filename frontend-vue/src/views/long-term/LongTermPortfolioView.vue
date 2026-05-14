<template>
  <div class="p-4 lg:p-6 bg-warm-50 min-h-screen">
    <!-- 标题区 -->
    <div class="mb-6 flex items-center justify-between flex-wrap gap-3">
      <div>
        <h1 class="text-xl font-bold text-warmgray-900">长线组合</h1>
        <p class="text-sm text-warmgray-500 mt-1">持仓管理、权重监控与再平衡建议</p>
      </div>
      <div class="flex items-center gap-2">
        <select
          v-model="marketEnv"
          class="px-3 py-1.5 text-sm border border-border rounded-md bg-white text-warmgray-700 focus:outline-none focus:ring-1 focus:ring-cta"
        >
          <option value="balanced">震荡市场</option>
          <option value="aggressive">牛市</option>
          <option value="defensive">熊市</option>
        </select>
        <button
          @click="runRebalance"
          :disabled="loading"
          class="px-4 py-1.5 bg-cta text-white text-sm font-medium rounded-md hover:bg-cta/90 disabled:opacity-50 transition-colors"
        >
          {{ loading ? '分析中...' : '再平衡分析' }}
        </button>
      </div>
    </div>

    <!-- 组合统计 -->
    <div v-if="stats" class="mb-4 grid grid-cols-2 md:grid-cols-4 gap-3">
      <div class="bg-white rounded-lg border border-border p-3">
        <div class="text-xs text-warmgray-500">总市值</div>
        <div class="text-lg font-semibold text-warmgray-900">{{ formatWan(stats.total_market_value) }}</div>
      </div>
      <div class="bg-white rounded-lg border border-border p-3">
        <div class="text-xs text-warmgray-500">总收益</div>
        <div class="text-lg font-semibold" :class="stats.total_return_pct >= 0 ? 'text-profit' : 'text-loss'">
          {{ stats.total_return_pct?.toFixed(1) }}%
        </div>
      </div>
      <div class="bg-white rounded-lg border border-border p-3">
        <div class="text-xs text-warmgray-500">持仓数量</div>
        <div class="text-lg font-semibold text-warmgray-900">{{ stats.holding_count }}</div>
      </div>
      <div class="bg-white rounded-lg border border-border p-3">
        <div class="text-xs text-warmgray-500">加权收益</div>
        <div class="text-lg font-semibold" :class="stats.weighted_return_pct >= 0 ? 'text-profit' : 'text-loss'">
          {{ stats.weighted_return_pct?.toFixed(1) }}%
        </div>
      </div>
    </div>

    <!-- 行业分布 -->
    <div v-if="stats?.industry_breakdown" class="mb-4 bg-white rounded-lg border border-border p-4">
      <h3 class="text-sm font-semibold text-warmgray-700 mb-2">行业分布</h3>
      <div class="flex flex-wrap gap-2">
        <div
          v-for="(weight, industry) in stats.industry_breakdown"
          :key="industry"
          class="px-3 py-1 rounded-full text-xs font-medium bg-warm-100 text-warmgray-700"
        >
          {{ industry }} {{ (weight * 100).toFixed(1) }}%
        </div>
      </div>
    </div>

    <!-- 持仓列表 -->
    <div class="bg-white rounded-lg border border-border overflow-hidden mb-4">
      <div class="px-4 py-3 border-b border-border bg-warmgray-50">
        <h3 class="text-sm font-semibold text-warmgray-700">当前持仓</h3>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="bg-warmgray-50 border-b border-border">
              <th class="px-4 py-3 text-left font-semibold text-warmgray-700">股票</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">成本</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">持股数</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">当前权重</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">目标权重</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">收益率</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">Darwin</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">状态</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="h in holdings"
              :key="h.ts_code"
              class="border-b border-border hover:bg-warm-50 transition-colors"
            >
              <td class="px-4 py-3">
                <div class="font-medium text-warmgray-900">{{ h.name }}</div>
                <div class="text-xs text-warmgray-500">{{ h.ts_code }}</div>
                <div class="text-xs text-warmgray-400">{{ h.industry }}</div>
              </td>
              <td class="px-4 py-3 text-center text-warmgray-700">{{ h.avg_cost?.toFixed(2) }}</td>
              <td class="px-4 py-3 text-center text-warmgray-700">{{ h.total_shares }}</td>
              <td class="px-4 py-3 text-center">
                <span class="font-medium">{{ (h.current_weight * 100).toFixed(1) }}%</span>
              </td>
              <td class="px-4 py-3 text-center">
                <span class="font-medium text-cta">{{ (h.target_weight * 100).toFixed(1) }}%</span>
              </td>
              <td class="px-4 py-3 text-center">
                <span :class="h.return_pct >= 0 ? 'text-profit' : 'text-loss'">
                  {{ h.return_pct?.toFixed(1) }}%
                </span>
              </td>
              <td class="px-4 py-3 text-center">
                <span class="font-semibold" :class="scoreClass(h.darwin_score)">{{ h.darwin_score }}</span>
              </td>
              <td class="px-4 py-3 text-center">
                <span class="px-2 py-0.5 rounded text-xs font-medium bg-profit/10 text-profit">{{ h.status }}</span>
              </td>
            </tr>
            <tr v-if="holdings.length === 0 && !loading">
              <td colspan="8" class="px-4 py-8 text-center text-warmgray-500">
                暂无持仓记录
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 再平衡建议 -->
    <div v-if="rebalanceSuggestions.length > 0" class="bg-white rounded-lg border border-border overflow-hidden">
      <div class="px-4 py-3 border-b border-border bg-warmgray-50">
        <h3 class="text-sm font-semibold text-warmgray-700">再平衡建议</h3>
        <p class="text-xs text-warmgray-500 mt-0.5">{{ rebalanceSummary }}</p>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="bg-warmgray-50 border-b border-border">
              <th class="px-4 py-3 text-left font-semibold text-warmgray-700">股票</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">操作</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">当前权重</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">目标权重</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">变动</th>
              <th class="px-4 py-3 text-left font-semibold text-warmgray-700">原因</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="s in rebalanceSuggestions"
              :key="s.ts_code"
              class="border-b border-border hover:bg-warm-50 transition-colors"
            >
              <td class="px-4 py-3">
                <div class="font-medium text-warmgray-900">{{ s.name || s.ts_code }}</div>
              </td>
              <td class="px-4 py-3 text-center">
                <span
                  class="px-2 py-0.5 rounded text-xs font-medium"
                  :class="s.action === 'buy' ? 'bg-profit/10 text-profit' : s.action === 'sell' ? 'bg-loss/10 text-loss' : 'bg-warm-100 text-warmgray-700'"
                >
                  {{ s.action === 'buy' ? '买入' : s.action === 'sell' ? '卖出' : '持有' }}
                </span>
              </td>
              <td class="px-4 py-3 text-center text-warmgray-700">{{ (s.current_weight * 100).toFixed(1) }}%</td>
              <td class="px-4 py-3 text-center text-cta">{{ (s.target_weight * 100).toFixed(1) }}%</td>
              <td class="px-4 py-3 text-center font-medium" :class="s.delta_weight > 0 ? 'text-profit' : 'text-loss'">
                {{ s.delta_weight > 0 ? '+' : '' }}{{ (s.delta_weight * 100).toFixed(1) }}%
              </td>
              <td class="px-4 py-3 text-warmgray-600 text-xs">{{ s.reason }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

const loading = ref(false)
const holdings = ref([])
const stats = ref(null)
const marketEnv = ref('balanced')
const rebalanceSuggestions = ref([])
const rebalanceSummary = ref('')

async function fetchPortfolio() {
  loading.value = true
  try {
    const response = await fetch(`${API_BASE_URL}/api/long-term/portfolio`)
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const result = await response.json()
    holdings.value = result.holdings || []
    stats.value = result.stats || null
  } catch (e) {
    console.error('组合数据获取失败:', e)
  } finally {
    loading.value = false
  }
}

async function runRebalance() {
  loading.value = true
  try {
    const response = await fetch(`${API_BASE_URL}/api/long-term/portfolio/rebalance`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ market_environment: marketEnv.value }),
    })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const result = await response.json()
    rebalanceSuggestions.value = result.suggestions || []
    rebalanceSummary.value = result.summary || ''
    if (result.current_stats) {
      stats.value = result.current_stats
    }
  } catch (e) {
    console.error('再平衡分析失败:', e)
  } finally {
    loading.value = false
  }
}

function formatWan(value) {
  if (!value) return '-'
  const wan = value / 10000
  if (wan >= 10000) return (wan / 10000).toFixed(2) + '亿'
  return wan.toFixed(1) + '万'
}

function scoreClass(score) {
  if (score >= 70) return 'text-profit'
  if (score >= 50) return 'text-cta'
  return 'text-loss'
}

onMounted(() => {
  fetchPortfolio()
})
</script>
