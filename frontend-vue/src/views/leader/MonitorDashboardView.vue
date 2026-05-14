<template>
  <div class="p-6 space-y-6">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-warmgray-900">短线监控仪表盘</h1>
        <p class="text-sm text-warmgray-500 mt-1">实时追踪模型绩效、健康度与熔断状态</p>
      </div>
      <div class="flex items-center gap-2">
        <button
          @click="refreshData"
          :disabled="isLoading"
          class="px-3 py-1.5 text-sm bg-warmgray-100 text-warmgray-700 rounded-lg hover:bg-warmgray-200 disabled:opacity-50 flex items-center gap-1"
        >
          <ArrowPathIcon class="w-4 h-4" :class="{ 'animate-spin': isLoading }" />
          刷新
        </button>
      </div>
    </div>

    <!-- 错误提示 -->
    <div
      v-if="errorMessage"
      class="bg-red-50 border border-red-200 rounded-lg p-4 flex items-center gap-3"
    >
      <ShieldExclamationIcon class="w-5 h-5 text-red-600 flex-shrink-0" />
      <span class="text-sm text-red-700">{{ errorMessage }}</span>
    </div>

    <!-- 熔断告警 -->
    <div
      v-if="circuitBreaker?.triggered"
      class="bg-red-50 border border-red-200 rounded-lg p-4 flex items-start gap-3"
    >
      <ShieldExclamationIcon class="w-6 h-6 text-red-600 flex-shrink-0 mt-0.5" />
      <div>
        <h3 class="font-semibold text-red-700">熔断已触发</h3>
        <p class="text-sm text-red-600 mt-1">
          健康度={{ circuitBreaker.health_score }}，关键告警={{ circuitBreaker.critical_count }} 条。
          建议暂停新开仓，优先处理持仓止损与止盈。
        </p>
        <ul v-if="circuitBreaker.suggestions?.length" class="mt-2 text-sm text-red-600 list-disc list-inside">
          <li v-for="(s, idx) in circuitBreaker.suggestions" :key="idx">{{ s }}</li>
        </ul>
      </div>
    </div>

    <!-- 核心指标卡片 -->
    <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
      <div class="bg-white rounded-lg border border-border p-4">
        <div class="text-xs text-warmgray-500 mb-1">胜率</div>
        <div class="text-xl font-semibold" :class="getWinRateClass(performance?.win_rate)">
          {{ formatPercent(performance?.win_rate) }}
        </div>
      </div>
      <div class="bg-white rounded-lg border border-border p-4">
        <div class="text-xs text-warmgray-500 mb-1">盈亏比</div>
        <div class="text-xl font-semibold" :class="getProfitFactorClass(performance?.profit_factor)">
          {{ performance?.profit_factor?.toFixed(2) || '-' }}
        </div>
      </div>
      <div class="bg-white rounded-lg border border-border p-4">
        <div class="text-xs text-warmgray-500 mb-1">Sharpe</div>
        <div class="text-xl font-semibold text-warmgray-900">
          {{ performance?.sharpe_ratio?.toFixed(2) || '-' }}
        </div>
      </div>
      <div class="bg-white rounded-lg border border-border p-4">
        <div class="text-xs text-warmgray-500 mb-1">最大回撤</div>
        <div class="text-xl font-semibold text-loss">
          {{ formatPercent(performance?.max_drawdown) }}
        </div>
      </div>
      <div class="bg-white rounded-lg border border-border p-4">
        <div class="text-xs text-warmgray-500 mb-1">平均持仓天数</div>
        <div class="text-xl font-semibold text-warmgray-900">
          {{ performance?.avg_holding_days?.toFixed(1) || '-' }}
        </div>
      </div>
      <div class="bg-white rounded-lg border border-border p-4">
        <div class="text-xs text-warmgray-500 mb-1">最大连亏</div>
        <div class="text-xl font-semibold" :class="getConsecutiveLossClass(performance?.consecutive_losses)">
          {{ performance?.consecutive_losses ?? '-' }}
        </div>
      </div>
    </div>

    <!-- 健康度与建议 -->
    <div v-if="healthReport" class="bg-white rounded-lg border border-border p-6">
      <div class="flex items-center justify-between mb-4">
        <h3 class="text-lg font-semibold text-warmgray-900">模型健康度</h3>
        <span
          :class="[
            'px-3 py-1 rounded-full text-sm font-medium',
            healthReport.circuit_breaker_triggered
              ? 'bg-red-100 text-red-700'
              : healthReport.health_score >= 70
              ? 'bg-green-100 text-green-700'
              : healthReport.health_score >= 50
              ? 'bg-amber-100 text-amber-700'
              : 'bg-red-100 text-red-700'
          ]"
        >
          健康度 {{ healthReport.health_score }}
        </span>
      </div>

      <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
        <div class="bg-warmgray-50 rounded-lg p-4">
          <div class="text-xs text-warmgray-500 mb-1">关键告警</div>
          <div class="text-xl font-semibold text-warmgray-900">{{ healthReport.critical_count || 0 }}</div>
        </div>
        <div class="bg-warmgray-50 rounded-lg p-4">
          <div class="text-xs text-warmgray-500 mb-1">一般告警</div>
          <div class="text-xl font-semibold text-warmgray-900">{{ healthReport.warning_count || 0 }}</div>
        </div>
        <div class="bg-warmgray-50 rounded-lg p-4">
          <div class="text-xs text-warmgray-500 mb-1">信号样本数</div>
          <div class="text-xl font-semibold text-warmgray-900">{{ performance?.sample_count || 0 }}</div>
        </div>
        <div class="bg-warmgray-50 rounded-lg p-4">
          <div class="text-xs text-warmgray-500 mb-1">平均收益</div>
          <div class="text-xl font-semibold" :class="(performance?.avg_return || 0) >= 0 ? 'text-profit' : 'text-loss'">
            {{ formatPercent(performance?.avg_return) }}
          </div>
        </div>
      </div>

      <div v-if="healthReport.suggestions?.length" class="space-y-2">
        <div
          v-for="(s, idx) in healthReport.suggestions"
          :key="idx"
          class="flex items-start gap-2 text-sm"
        >
          <LightBulbIcon class="w-4 h-4 text-cta mt-0.5 flex-shrink-0" />
          <span class="text-warmgray-700">{{ s }}</span>
        </div>
      </div>
      <div v-else class="text-sm text-warmgray-500">暂无新建议</div>
    </div>

    <!-- 按等级分组统计 -->
    <div v-if="gradePerformance && Object.keys(gradePerformance).length" class="bg-white rounded-lg border border-border p-6">
      <h3 class="text-lg font-semibold text-warmgray-900 mb-4">按评级分组绩效</h3>
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="bg-warmgray-50">
              <th class="px-4 py-2 text-left text-warmgray-600">评级</th>
              <th class="px-4 py-2 text-right text-warmgray-600">样本数</th>
              <th class="px-4 py-2 text-right text-warmgray-600">胜率</th>
              <th class="px-4 py-2 text-right text-warmgray-600">平均收益</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(item, grade) in gradePerformance"
              :key="grade"
              class="border-b border-border hover:bg-warmgray-50"
            >
              <td class="px-4 py-2 font-medium">{{ grade }}</td>
              <td class="px-4 py-2 text-right">{{ item.count }}</td>
              <td class="px-4 py-2 text-right" :class="item.win_rate >= 0.5 ? 'text-profit' : 'text-loss'">
                {{ formatPercent(item.win_rate) }}
              </td>
              <td class="px-4 py-2 text-right" :class="item.avg_return >= 0 ? 'text-profit' : 'text-loss'">
                {{ formatPercent(item.avg_return) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ArrowPathIcon, LightBulbIcon, ShieldExclamationIcon } from '@heroicons/vue/24/outline'
import { monitorApi } from '../../api/monitorApi'

const isLoading = ref(false)
const performance = ref(null)
const gradePerformance = ref(null)
const healthReport = ref(null)
const circuitBreaker = ref(null)
const errorMessage = ref(null)

function formatPercent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return (value * 100).toFixed(2) + '%'
}

function getWinRateClass(rate) {
  if (!rate && rate !== 0) return 'text-warmgray-900'
  if (rate >= 0.5) return 'text-green-600'
  if (rate >= 0.4) return 'text-amber-600'
  return 'text-red-600'
}

function getProfitFactorClass(pf) {
  if (!pf && pf !== 0) return 'text-warmgray-900'
  if (pf >= 1.5) return 'text-green-600'
  if (pf >= 1.0) return 'text-amber-600'
  return 'text-red-600'
}

function getConsecutiveLossClass(cl) {
  if (cl === null || cl === undefined) return 'text-warmgray-900'
  if (cl <= 2) return 'text-green-600'
  if (cl <= 4) return 'text-amber-600'
  return 'text-red-600'
}

async function refreshData() {
  isLoading.value = true
  try {
    const [perfRes, healthRes, cbRes] = await Promise.all([
      monitorApi.getPerformance(20, true),
      monitorApi.getHealth(),
      monitorApi.getCircuitBreaker(),
    ])

    if (perfRes.success) {
      performance.value = perfRes.performance
      gradePerformance.value = perfRes.grade_performance || null
    }

    if (healthRes.success) {
      healthReport.value = healthRes
    }

    if (cbRes.success) {
      circuitBreaker.value = cbRes
    }
  } catch (error) {
    console.error('刷新监控数据失败:', error)
    errorMessage.value = '获取监控数据失败，请检查网络或后端服务'
    setTimeout(() => { errorMessage.value = null }, 5000)
  } finally {
    isLoading.value = false
  }
}

onMounted(() => {
  refreshData()
})
</script>
