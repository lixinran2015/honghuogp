<template>
  <div class="p-6 space-y-6">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-warmgray-900">LSTM-MAB 模型进化监控</h1>
        <p class="text-sm text-warmgray-500 mt-1">追踪模型性能、健康状态和自动进化</p>
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

    <!-- 健康状态卡片 -->
    <div v-if="healthStatus" class="bg-white rounded-lg border border-border p-6">
      <div class="flex items-center justify-between mb-4">
        <h3 class="text-lg font-semibold text-warmgray-900">模型健康状态</h3>
        <span
          :class="[
            'px-3 py-1 rounded-full text-sm font-medium',
            healthStatus.is_healthy ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
          ]"
        >
          {{ healthStatus.is_healthy ? '健康' : '需要关注' }}
        </span>
      </div>

      <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
        <div class="bg-warmgray-50 rounded-lg p-4">
          <div class="text-xs text-warmgray-500 mb-1">总预测数</div>
          <div class="text-xl font-semibold text-warmgray-900">
            {{ healthStatus.total_predictions?.toLocaleString() || '-' }}
          </div>
        </div>
        <div class="bg-warmgray-50 rounded-lg p-4">
          <div class="text-xs text-warmgray-500 mb-1">近期命中率</div>
          <div class="text-xl font-semibold" :class="getHitRateColor(healthStatus.recent_hit_rate)">
            {{ healthStatus.recent_hit_rate ? (healthStatus.recent_hit_rate * 100).toFixed(1) + '%' : '-' }}
          </div>
        </div>
        <div class="bg-warmgray-50 rounded-lg p-4">
          <div class="text-xs text-warmgray-500 mb-1">预测相关性</div>
          <div class="text-xl font-semibold text-warmgray-900">
            {{ healthStatus.recent_correlation ? healthStatus.recent_correlation.toFixed(3) : '-' }}
          </div>
        </div>
        <div class="bg-warmgray-50 rounded-lg p-4">
          <div class="text-xs text-warmgray-500 mb-1">最后训练</div>
          <div class="text-xl font-semibold text-warmgray-900">
            {{ healthStatus.last_training_date || '-' }}
          </div>
        </div>
      </div>

      <!-- 建议列表 -->
      <div v-if="healthStatus.recommendations?.length" class="space-y-2">
        <div
          v-for="(rec, idx) in healthStatus.recommendations"
          :key="idx"
          class="flex items-start gap-2 text-sm"
        >
          <LightBulbIcon class="w-4 h-4 text-cta mt-0.5 flex-shrink-0" />
          <span :class="rec.includes('良好') ? 'text-green-600' : 'text-amber-600'">{{ rec }}</span>
        </div>
      </div>
    </div>

    <!-- 重训练建议 -->
    <div v-if="retrainStatus" class="bg-white rounded-lg border border-border p-6">
      <div class="flex items-center justify-between">
        <div>
          <h3 class="text-lg font-semibold text-warmgray-900">重训练建议</h3>
          <p class="text-sm text-warmgray-500 mt-1">{{ retrainStatus.reason }}</p>
        </div>
        <div class="flex items-center gap-3">
          <span
            :class="[
              'px-3 py-1 rounded-full text-sm font-medium',
              retrainStatus.should_retrain ? 'bg-amber-100 text-amber-700' : 'bg-green-100 text-green-700'
            ]"
          >
            {{ retrainStatus.should_retrain ? '建议重训练' : '无需重训练' }}
          </span>
          <button
            v-if="retrainStatus.should_retrain"
            @click="goToTraining"
            class="px-4 py-2 bg-cta text-white rounded-lg text-sm font-medium hover:bg-cta/90"
          >
            去训练
          </button>
        </div>
      </div>
    </div>

    <!-- 性能趋势 -->
    <div v-if="performanceData" class="bg-white rounded-lg border border-border p-6">
      <h3 class="text-lg font-semibold text-warmgray-900 mb-4">性能趋势 (30天)</h3>

      <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div class="text-center">
          <div class="text-2xl font-bold text-cta">{{ performanceData.total_predictions?.toLocaleString() || '-' }}</div>
          <div class="text-xs text-warmgray-500">总预测数</div>
        </div>
        <div class="text-center">
          <div class="text-2xl font-bold" :class="getHitRateColor(performanceData.overall_hit_rate)">
            {{ performanceData.overall_hit_rate ? (performanceData.overall_hit_rate * 100).toFixed(1) + '%' : '-' }}
          </div>
          <div class="text-xs text-warmgray-500">整体命中率</div>
        </div>
        <div class="text-center">
          <div class="text-2xl font-bold text-warmgray-900">
            {{ performanceData.avg_correlation ? performanceData.avg_correlation.toFixed(3) : '-' }}
          </div>
          <div class="text-xs text-warmgray-500">平均相关性</div>
        </div>
        <div class="text-center">
          <div class="text-2xl font-bold text-warmgray-900">
            {{ performanceData.avg_rmse ? performanceData.avg_rmse.toFixed(4) : '-' }}
          </div>
          <div class="text-xs text-warmgray-500">平均RMSE</div>
        </div>
      </div>

      <!-- 情绪周期表现 -->
      <div v-if="performanceData.by_emotion_cycle?.length" class="mt-6">
        <h4 class="text-sm font-medium text-warmgray-700 mb-3">按情绪周期表现</h4>
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="bg-warmgray-50">
                <th class="px-4 py-2 text-left text-warmgray-600">情绪周期</th>
                <th class="px-4 py-2 text-right text-warmgray-600">预测数</th>
                <th class="px-4 py-2 text-right text-warmgray-600">平均收益</th>
                <th class="px-4 py-2 text-right text-warmgray-600">准确度</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="item in performanceData.by_emotion_cycle"
                :key="item.emotion_cycle"
                class="border-b border-border hover:bg-warmgray-50"
              >
                <td class="px-4 py-2">{{ item.emotion_cycle }}</td>
                <td class="px-4 py-2 text-right">{{ item.count }}</td>
                <td class="px-4 py-2 text-right" :class="item.avg_return > 0 ? 'text-profit' : 'text-loss'">
                  {{ (item.avg_return * 100).toFixed(2) }}%
                </td>
                <td class="px-4 py-2 text-right">
                  {{ item.avg_accuracy ? (item.avg_accuracy * 100).toFixed(1) + '%' : '-' }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 因子表现 -->
      <div v-if="performanceData.by_factor?.length" class="mt-6">
        <h4 class="text-sm font-medium text-warmgray-700 mb-3">因子表现</h4>
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="bg-warmgray-50">
                <th class="px-4 py-2 text-left text-warmgray-600">因子</th>
                <th class="px-4 py-2 text-right text-warmgray-600">平均权重</th>
                <th class="px-4 py-2 text-right text-warmgray-600">命中率</th>
                <th class="px-4 py-2 text-right text-warmgray-600">累计奖励</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="item in performanceData.by_factor"
                :key="item.factor_name"
                class="border-b border-border hover:bg-warmgray-50"
              >
                <td class="px-4 py-2">{{ getFactorLabel(item.factor_name) }}</td>
                <td class="px-4 py-2 text-right">{{ (item.avg_weight * 100).toFixed(1) }}%</td>
                <td class="px-4 py-2 text-right" :class="getHitRateColor(item.avg_hit_rate)">
                  {{ item.avg_hit_rate ? (item.avg_hit_rate * 100).toFixed(1) + '%' : '-' }}
                </td>
                <td class="px-4 py-2 text-right" :class="item.total_reward > 0 ? 'text-profit' : 'text-loss'">
                  {{ item.total_reward?.toFixed(3) || '-' }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- 版本历史 -->
    <div v-if="versionHistory.length" class="bg-white rounded-lg border border-border p-6">
      <h3 class="text-lg font-semibold text-warmgray-900 mb-4">模型版本历史</h3>
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="bg-warmgray-50">
              <th class="px-4 py-2 text-left text-warmgray-600">版本</th>
              <th class="px-4 py-2 text-left text-warmgray-600">训练日期</th>
              <th class="px-4 py-2 text-right text-warmgray-600">训练R²</th>
              <th class="px-4 py-2 text-right text-warmgray-600">验证R²</th>
              <th class="px-4 py-2 text-right text-warmgray-600">样本数</th>
              <th class="px-4 py-2 text-center text-warmgray-600">状态</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="version in versionHistory"
              :key="version.version"
              class="border-b border-border hover:bg-warmgray-50"
            >
              <td class="px-4 py-2 font-mono text-xs">{{ version.version }}</td>
              <td class="px-4 py-2">{{ version.trained_date }}</td>
              <td class="px-4 py-2 text-right">{{ version.train_r2?.toFixed(4) || '-' }}</td>
              <td class="px-4 py-2 text-right">{{ version.val_r2?.toFixed(4) || '-' }}</td>
              <td class="px-4 py-2 text-right">{{ version.n_samples?.toLocaleString() || '-' }}</td>
              <td class="px-4 py-2 text-center">
                <span
                  :class="[
                    'px-2 py-0.5 rounded-full text-xs',
                    version.is_active ? 'bg-green-100 text-green-700' : 'bg-warmgray-100 text-warmgray-600'
                  ]"
                >
                  {{ version.is_active ? '当前' : '历史' }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 操作按钮 -->
    <div class="flex gap-3">
      <button
        @click="saveModel"
        :disabled="isSaving"
        class="px-4 py-2 bg-cta text-white rounded-lg text-sm font-medium hover:bg-cta/90 disabled:opacity-50 flex items-center gap-2"
      >
        <ArrowDownTrayIcon v-if="!isSaving" class="w-4 h-4" />
        <ArrowPathIcon v-else class="w-4 h-4 animate-spin" />
        {{ isSaving ? '保存中...' : '保存模型' }}
      </button>
      <button
        @click="loadModel"
        :disabled="isLoadingModel"
        class="px-4 py-2 bg-warmgray-100 text-warmgray-700 rounded-lg text-sm font-medium hover:bg-warmgray-200 disabled:opacity-50 flex items-center gap-2"
      >
        <ArrowUpTrayIcon v-if="!isLoadingModel" class="w-4 h-4" />
        <ArrowPathIcon v-else class="w-4 h-4 animate-spin" />
        {{ isLoadingModel ? '加载中...' : '加载模型' }}
      </button>
      <button
        @click="runFeedback"
        :disabled="isRunningFeedback"
        class="px-4 py-2 bg-warmgray-100 text-warmgray-700 rounded-lg text-sm font-medium hover:bg-warmgray-200 disabled:opacity-50 flex items-center gap-2"
      >
        <ArrowPathIcon v-if="!isRunningFeedback" class="w-4 h-4" />
        <span v-else class="w-4 h-4 border-2 border-warmgray-400 border-t-transparent rounded-full animate-spin" />
        {{ isRunningFeedback ? '执行中...' : '执行反馈循环' }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowPathIcon, LightBulbIcon, ArrowDownTrayIcon, ArrowUpTrayIcon } from '@heroicons/vue/24/outline'

const router = useRouter()
const API_BASE = '/api/lstm-mab'

// 状态
const isLoading = ref(false)
const isSaving = ref(false)
const isLoadingModel = ref(false)
const isRunningFeedback = ref(false)

const healthStatus = ref(null)
const retrainStatus = ref(null)
const performanceData = ref(null)
const versionHistory = ref([])

// 因子标签映射
const factorLabels = {
  leader_position: '龙头地位',
  technical: '技术形态',
  money_flow: '资金流向',
  sentiment: '情绪指标',
}

function getFactorLabel(name) {
  return factorLabels[name] || name
}

function getHitRateColor(rate) {
  if (!rate) return 'text-warmgray-900'
  if (rate >= 0.6) return 'text-green-600'
  if (rate >= 0.5) return 'text-amber-600'
  return 'text-red-600'
}

// 获取健康状态
async function fetchHealth() {
  try {
    const response = await fetch(`${API_BASE}/health`)
    const data = await response.json()
    if (data.success) {
      healthStatus.value = data.health
      retrainStatus.value = {
        should_retrain: data.should_retrain,
        reason: data.retrain_reason,
      }
    }
  } catch (error) {
    console.error('获取健康状态失败:', error)
  }
}

// 获取性能数据
async function fetchPerformance() {
  try {
    const response = await fetch(`${API_BASE}/performance?days=30`)
    const data = await response.json()
    if (data.success) {
      performanceData.value = data.summary
    }
  } catch (error) {
    console.error('获取性能数据失败:', error)
  }
}

// 获取进化报告
async function fetchEvolutionReport() {
  try {
    const response = await fetch(`${API_BASE}/evolution-report`)
    const data = await response.json()
    if (data.success) {
      versionHistory.value = data.report.version_history || []
    }
  } catch (error) {
    console.error('获取进化报告失败:', error)
  }
}

// 刷新所有数据
async function refreshData() {
  isLoading.value = true
  await Promise.all([
    fetchHealth(),
    fetchPerformance(),
    fetchEvolutionReport(),
  ])
  isLoading.value = false
}

// 保存模型
async function saveModel() {
  isSaving.value = true
  try {
    const response = await fetch(`${API_BASE}/save`, { method: 'POST' })
    const data = await response.json()
    if (data.success) {
      alert('模型保存成功')
    } else {
      alert(data.error || '保存失败')
    }
  } catch (error) {
    console.error('保存模型失败:', error)
    alert('保存请求失败')
  } finally {
    isSaving.value = false
  }
}

// 加载模型
async function loadModel() {
  isLoadingModel.value = true
  try {
    const response = await fetch(`${API_BASE}/load`, { method: 'POST' })
    const data = await response.json()
    if (data.success) {
      alert('模型加载成功')
      refreshData()
    } else {
      alert(data.error || '加载失败')
    }
  } catch (error) {
    console.error('加载模型失败:', error)
    alert('加载请求失败')
  } finally {
    isLoadingModel.value = false
  }
}

// 执行反馈循环
async function runFeedback() {
  isRunningFeedback.value = true
  try {
    const response = await fetch(`${API_BASE}/run-daily-feedback`, {
      method: 'POST',
    })
    const data = await response.json()
    if (data.success) {
      alert('每日反馈任务已启动，请在几秒后刷新查看结果')
      // 延迟刷新，等待后台任务完成
      setTimeout(() => {
        refreshData()
      }, 5000)
    } else {
      alert(data.error || '启动失败')
    }
  } catch (error) {
    console.error('启动每日反馈失败:', error)
    alert('启动请求失败')
  } finally {
    isRunningFeedback.value = false
  }
}

// 跳转到训练页面
function goToTraining() {
  router.push('/lstm-mab')
}

onMounted(() => {
  refreshData()
})
</script>
