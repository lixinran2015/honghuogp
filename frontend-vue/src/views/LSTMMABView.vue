<template>
  <div class="p-6 space-y-6">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-warmgray-900">LSTM-MAB 智能评分模型</h1>
        <p class="text-sm text-warmgray-500 mt-1">基于 Phase 1 因子验证的机器学习评分系统</p>
      </div>
      <div class="flex items-center gap-2">
        <span
          :class="[
            'px-3 py-1 rounded-full text-xs font-medium',
            modelStatus.is_trained ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'
          ]"
        >
          {{ modelStatus.is_trained ? '模型已训练' : '模型未训练' }}
        </span>
      </div>
    </div>

    <!-- 模型状态卡片 -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
      <div class="bg-white rounded-lg border border-border p-4">
        <div class="text-xs text-warmgray-500 mb-1">训练状态</div>
        <div class="text-lg font-semibold" :class="modelStatus.is_trained ? 'text-green-600' : 'text-yellow-600'">
          {{ modelStatus.is_trained ? '已完成' : '未训练' }}
        </div>
      </div>
      <div class="bg-white rounded-lg border border-border p-4">
        <div class="text-xs text-warmgray-500 mb-1">训练日期</div>
        <div class="text-lg font-semibold text-warmgray-900">
          {{ modelStatus.training_date || '-' }}
        </div>
      </div>
      <div class="bg-white rounded-lg border border-border p-4">
        <div class="text-xs text-warmgray-500 mb-1">验证集 R²</div>
        <div class="text-lg font-semibold text-warmgray-900">
          {{ modelStatus.performance?.val_r2?.toFixed(4) || '-' }}
        </div>
      </div>
      <div class="bg-white rounded-lg border border-border p-4">
        <div class="text-xs text-warmgray-500 mb-1">样本数量</div>
        <div class="text-lg font-semibold text-warmgray-900">
          {{ modelStatus.performance?.n_samples?.toLocaleString() || '-' }}
        </div>
      </div>
    </div>

    <!-- 使用因子展示 -->
    <div class="bg-white rounded-lg border border-border p-6">
      <h3 class="text-lg font-semibold text-warmgray-900 mb-4">当前使用因子（Phase 1 验证通过）</h3>
      <div class="flex gap-3">
        <div
          v-for="factor in currentFactors"
          :key="factor.name"
          class="px-4 py-2 bg-cta/10 text-cta rounded-lg text-sm font-medium"
        >
          {{ factor.label }}
          <span class="ml-1 text-xs opacity-75">({{ factor.grade }}级)</span>
        </div>
      </div>
      <p class="text-xs text-warmgray-500 mt-3">
        * 基于 Phase 1 因子验证结果，仅使用 leader_position（A级）和 technical（B级）两个有效因子
      </p>
    </div>

    <!-- 训练控制 -->
    <div class="bg-white rounded-lg border border-border p-6">
      <h3 class="text-lg font-semibold text-warmgray-900 mb-4">模型训练</h3>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
        <div>
          <label class="block text-sm font-medium text-warmgray-700 mb-1">开始日期</label>
          <input
            v-model="trainParams.start_date"
            type="date"
            :disabled="isTraining"
            class="w-full px-3 py-2 border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-cta/20 disabled:opacity-50"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-warmgray-700 mb-1">结束日期</label>
          <input
            v-model="trainParams.end_date"
            type="date"
            :disabled="isTraining"
            class="w-full px-3 py-2 border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-cta/20 disabled:opacity-50"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-warmgray-700 mb-1">预测周期（天）</label>
          <input
            v-model.number="trainParams.target_horizon"
            type="number"
            min="1"
            max="20"
            :disabled="isTraining"
            class="w-full px-3 py-2 border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-cta/20 disabled:opacity-50"
          />
        </div>
      </div>

      <!-- 进度条 -->
      <div v-if="isTraining" class="mb-4">
        <div class="flex items-center justify-between text-sm text-warmgray-600 mb-2">
          <span>{{ trainingMessage }}</span>
          <span>{{ trainingProgress }}%</span>
        </div>
        <div class="w-full bg-warmgray-100 rounded-full h-2">
          <div
            class="bg-cta h-2 rounded-full transition-all duration-300"
            :style="{ width: trainingProgress + '%' }"
          ></div>
        </div>
        <div class="mt-2 text-xs text-warmgray-500">
          训练在后台执行，您可以离开此页面或进行其他操作
        </div>
      </div>

      <!-- 操作按钮 -->
      <div class="flex gap-3">
        <button
          v-if="!isTraining"
          @click="trainModel"
          class="px-4 py-2 bg-cta text-white rounded-lg text-sm font-medium hover:bg-cta/90 flex items-center gap-2"
        >
          <PlayIcon class="w-4 h-4" />
          开始训练
        </button>
        <button
          v-else
          @click="refreshTrainingStatus"
          :disabled="isRefreshing"
          class="px-4 py-2 bg-warmgray-100 text-warmgray-700 rounded-lg text-sm font-medium hover:bg-warmgray-200 disabled:opacity-50 flex items-center gap-2"
        >
          <ArrowPathIcon class="w-4 h-4" :class="{ 'animate-spin': isRefreshing }" />
          {{ isRefreshing ? '刷新中...' : '刷新状态' }}
        </button>
      </div>

      <!-- 训练结果 -->
      <div v-if="trainResult && !isTraining" class="mt-4 p-4 bg-green-50 border border-green-200 rounded-lg">
        <div class="text-sm font-medium text-green-800 mb-2">✅ 训练完成</div>
        <div class="grid grid-cols-3 gap-4 text-sm">
          <div>
            <span class="text-warmgray-500">训练集 R²:</span>
            <span class="ml-2 font-medium">{{ trainResult.metrics.train_r2.toFixed(4) }}</span>
          </div>
          <div>
            <span class="text-warmgray-500">验证集 R²:</span>
            <span class="ml-2 font-medium">{{ trainResult.metrics.val_r2.toFixed(4) }}</span>
          </div>
          <div>
            <span class="text-warmgray-500">样本数:</span>
            <span class="ml-2 font-medium">{{ trainResult.metrics.n_samples.toLocaleString() }}</span>
          </div>
        </div>
      </div>

      <!-- 训练错误 -->
      <div v-if="trainingError" class="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg">
        <div class="text-sm font-medium text-red-800">❌ 训练失败</div>
        <div class="text-sm text-red-600 mt-1">{{ trainingError }}</div>
      </div>
    </div>

    <!-- 股票评分测试 -->
    <div class="bg-white rounded-lg border border-border p-6">
      <h3 class="text-lg font-semibold text-warmgray-900 mb-4">股票评分预测</h3>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
        <div>
          <label class="block text-sm font-medium text-warmgray-700 mb-1">股票代码</label>
          <input
            v-model="predictParams.ts_code"
            type="text"
            placeholder="如: 000001.SZ"
            class="w-full px-3 py-2 border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-cta/20"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-warmgray-700 mb-1">龙头地位得分 (0-100)</label>
          <input
            v-model.number="predictParams.factor_values.leader_position"
            type="number"
            min="0"
            max="100"
            class="w-full px-3 py-2 border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-cta/20"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-warmgray-700 mb-1">技术形态得分 (0-100)</label>
          <input
            v-model.number="predictParams.factor_values.technical"
            type="number"
            min="0"
            max="100"
            class="w-full px-3 py-2 border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-cta/20"
          />
        </div>
      </div>
      <button
        @click="predictScore"
        :disabled="isPredicting || !modelStatus.is_trained"
        class="px-4 py-2 bg-cta text-white rounded-lg text-sm font-medium hover:bg-cta/90 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
      >
        <SparklesIcon v-if="!isPredicting" class="w-4 h-4" />
        <ArrowPathIcon v-else class="w-4 h-4 animate-spin" />
        {{ isPredicting ? '预测中...' : '获取评分' }}
      </button>

      <!-- 预测结果 -->
      <div v-if="predictResult" class="mt-4 p-4 bg-warmgray-50 rounded-lg">
        <div class="flex items-center justify-between mb-3">
          <div class="text-sm font-medium text-warmgray-900">预测结果</div>
          <span
            :class="[
              'px-3 py-1 rounded-full text-sm font-bold',
              predictResult.grade === 'S' ? 'bg-purple-100 text-purple-700' :
              predictResult.grade === 'A' ? 'bg-green-100 text-green-700' :
              predictResult.grade === 'B' ? 'bg-blue-100 text-blue-700' :
              'bg-gray-100 text-gray-700'
            ]"
          >
            {{ predictResult.grade }} 级
          </span>
        </div>
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div class="text-center p-3 bg-white rounded-lg">
            <div class="text-xs text-warmgray-500 mb-1">综合评分</div>
            <div class="text-2xl font-bold text-cta">{{ predictResult.total_score.toFixed(1) }}</div>
          </div>
          <div class="text-center p-3 bg-white rounded-lg">
            <div class="text-xs text-warmgray-500 mb-1">预期收益</div>
            <div class="text-2xl font-bold" :class="predictResult.expected_return > 0 ? 'text-profit' : 'text-loss'">
              {{ (predictResult.expected_return * 100).toFixed(2) }}%
            </div>
          </div>
          <div class="text-center p-3 bg-white rounded-lg">
            <div class="text-xs text-warmgray-500 mb-1">置信度</div>
            <div class="text-2xl font-bold text-warmgray-900">
              {{ (predictResult.confidence * 100).toFixed(1) }}%
            </div>
          </div>
          <div class="text-center p-3 bg-white rounded-lg">
            <div class="text-xs text-warmgray-500 mb-1">龙头权重</div>
            <div class="text-2xl font-bold text-warmgray-900">
              {{ (predictResult.factor_weights.leader_position * 100).toFixed(1) }}%
            </div>
          </div>
        </div>
        <div class="mt-3 text-xs text-warmgray-500">
          技术权重: {{ (predictResult.factor_weights.technical * 100).toFixed(1) }}%
        </div>
      </div>
    </div>

    <!-- 情绪周期设置 -->
    <div class="bg-white rounded-lg border border-border p-6">
      <h3 class="text-lg font-semibold text-warmgray-900 mb-4">情绪周期设置</h3>
      <div class="flex flex-wrap gap-2">
        <button
          v-for="cycle in emotionCycles"
          :key="cycle.value"
          @click="updateEmotionCycle(cycle.value)"
          :class="[
            'px-4 py-2 rounded-lg text-sm font-medium transition-colors',
            currentEmotionCycle === cycle.value
              ? 'bg-cta text-white'
              : 'bg-warmgray-100 text-warmgray-700 hover:bg-warmgray-200'
          ]"
        >
          {{ cycle.label }}
        </button>
      </div>
      <p class="text-xs text-warmgray-500 mt-3">
        * 不同情绪周期下，因子权重会自动调整。高涨期龙头地位权重65%/技术形态35%，冰点期龙头地位30%/技术形态70%
      </p>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { PlayIcon, ArrowPathIcon, SparklesIcon } from '@heroicons/vue/24/outline'

// 当前使用的因子（Phase 1 验证通过）
const currentFactors = [
  { name: 'leader_position', label: '龙头地位', grade: 'A' },
  { name: 'technical', label: '技术形态', grade: 'B' },
]

// 情绪周期选项
const emotionCycles = [
  { value: '高涨期', label: '高涨期' },
  { value: '主升期', label: '主升期' },
  { value: '震荡期', label: '震荡期' },
  { value: '分歧期', label: '分歧期' },
  { value: '低迷期', label: '低迷期' },
  { value: '退潮期', label: '退潮期' },
  { value: '冰点期', label: '冰点期' },
]

// 模型状态
const modelStatus = ref({
  is_trained: false,
  training_date: null,
  performance: {},
})

const currentEmotionCycle = ref('震荡期')

// 训练参数
const trainParams = ref({
  start_date: '2023-01-01',
  end_date: new Date().toISOString().split('T')[0],
  target_horizon: 5,
})

// 预测参数
const predictParams = ref({
  ts_code: '000001.SZ',
  factor_values: {
    leader_position: 80,
    technical: 75,
  },
})

// 状态
const isTraining = ref(false)
const isPredicting = ref(false)
const isRefreshing = ref(false)
const trainResult = ref(null)
const predictResult = ref(null)
const trainingProgress = ref(0)
const trainingMessage = ref('')
const trainingError = ref(null)

// 轮询定时器
let trainingPollInterval = null

// API 基础 URL
const API_BASE = '/api/lstm-mab'

// 获取模型状态
async function fetchModelStatus() {
  try {
    const response = await fetch(`${API_BASE}/status`)
    const data = await response.json()
    if (data.success) {
      modelStatus.value = data.model_status
      if (data.model_stats?.current_emotion_cycle) {
        currentEmotionCycle.value = data.model_stats.current_emotion_cycle
      }
    }
  } catch (error) {
    console.error('获取模型状态失败:', error)
  }
}

// 查询训练状态
async function checkTrainingStatus() {
  try {
    const response = await fetch(`${API_BASE}/train-status`)
    const data = await response.json()
    if (!data.success) return

    const status = data.training_status
    trainingProgress.value = status.progress || 0
    trainingMessage.value = status.message || '正在训练...'

    if (status.error) {
      trainingError.value = status.error
      isTraining.value = false
      stopPolling()
      return
    }

    if (!status.is_running && status.result) {
      // 训练完成
      isTraining.value = false
      trainResult.value = {
        metrics: status.result.metrics
      }
      stopPolling()
      await fetchModelStatus()
    }
  } catch (error) {
    console.error('查询训练状态失败:', error)
  }
}

// 开始轮询训练状态
function startPolling() {
  stopPolling() // 先停止之前的轮询
  trainingPollInterval = setInterval(checkTrainingStatus, 2000) // 每2秒查询一次
}

// 停止轮询
function stopPolling() {
  if (trainingPollInterval) {
    clearInterval(trainingPollInterval)
    trainingPollInterval = null
  }
}

// 训练模型
async function trainModel() {
  isTraining.value = true
  trainResult.value = null
  trainingError.value = null
  trainingProgress.value = 0
  trainingMessage.value = '正在启动训练任务...'

  try {
    const params = new URLSearchParams({
      start_date: trainParams.value.start_date,
      end_date: trainParams.value.end_date,
      target_horizon: trainParams.value.target_horizon.toString(),
    })
    const response = await fetch(`${API_BASE}/train?${params}`, {
      method: 'POST',
    })
    const data = await response.json()

    if (!response.ok) {
      alert(data.detail || '启动训练失败')
      isTraining.value = false
      return
    }

    if (data.success) {
      // 训练任务已启动，开始轮询状态
      trainingMessage.value = '训练任务已启动，正在准备数据...'
      startPolling()
    } else {
      alert(data.error || '启动训练失败')
      isTraining.value = false
    }
  } catch (error) {
    console.error('启动训练失败:', error)
    alert('启动训练请求失败')
    isTraining.value = false
  }
}

// 手动刷新训练状态
async function refreshTrainingStatus() {
  isRefreshing.value = true
  await checkTrainingStatus()
  setTimeout(() => {
    isRefreshing.value = false
  }, 500)
}

// 预测评分
async function predictScore() {
  isPredicting.value = true
  predictResult.value = null
  try {
    const response = await fetch(`${API_BASE}/predict`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(predictParams.value),
    })
    const data = await response.json()
    if (data.success) {
      predictResult.value = data.data
    } else {
      alert(data.error || '预测失败')
    }
  } catch (error) {
    console.error('预测失败:', error)
    alert('预测请求失败')
  } finally {
    isPredicting.value = false
  }
}

// 更新情绪周期
async function updateEmotionCycle(cycle) {
  try {
    const params = new URLSearchParams({ emotion_cycle: cycle })
    const response = await fetch(`${API_BASE}/update-emotion?${params}`, {
      method: 'POST',
    })
    const data = await response.json()
    if (data.success) {
      currentEmotionCycle.value = cycle
    }
  } catch (error) {
    console.error('更新情绪周期失败:', error)
  }
}

onMounted(() => {
  fetchModelStatus()
  // 页面加载时也检查一次训练状态（防止刷新页面时训练正在进行）
  checkTrainingStatus()
})

// 组件卸载时清理轮询
onUnmounted(() => {
  stopPolling()
})
</script>
