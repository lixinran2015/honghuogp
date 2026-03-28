<template>
  <div class="p-6 space-y-6">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-semibold text-gray-900 mb-2">短线龙头优化系统</h1>
        <p class="text-sm text-gray-500">多因子评分 + 买卖点策略 + 情绪周期 + 风控监控</p>
      </div>
      <div class="flex items-center gap-2">
        <Button size="sm" variant="outline" @click="checkDataStatus" :disabled="checkingData">
          {{ checkingData ? '检查中...' : '数据诊断' }}
        </Button>
        <Button size="sm" variant="outline" @click="fillLimitUpData" :disabled="fillingLimitUp">
          {{ fillingLimitUp ? '补充中...' : '补充涨停数据' }}
        </Button>
        <Button size="sm" variant="primary" @click="refreshAll" :disabled="loading">
          {{ loading ? '加载中...' : '刷新数据' }}
        </Button>
      </div>
    </div>

    <!-- 数据状态提示 -->
    <div v-if="dataStatus && dataStatus.all_tables_empty" class="bg-yellow-50 border border-yellow-200 rounded-xl p-4">
      <div class="flex items-start gap-3">
        <svg class="w-5 h-5 text-yellow-600 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
        <div class="flex-1">
          <div class="text-sm font-medium text-yellow-800">数据状态提示</div>
          <div class="text-sm text-yellow-700 mt-1">{{ dataStatus.summary?.recommendation || '数据库中暂无数据' }}</div>
          <div class="mt-2 text-sm text-yellow-600">
            请使用"刷新数据"按钮获取实时数据，或调用 API：
            <code class="bg-yellow-100 px-1 py-0.5 rounded">POST /api/leader-optimization/quick-refresh</code>
          </div>
        </div>
      </div>
    </div>

    <!-- 跟踪池数据不完整提示 -->
    <div v-if="scoredPool.length > 0 && !scoredPool[0].score" class="bg-orange-50 border border-orange-200 rounded-xl p-4">
      <div class="flex items-start gap-3">
        <svg class="w-5 h-5 text-orange-600 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <div class="flex-1">
          <div class="text-sm font-medium text-orange-800">跟踪池数据不完整</div>
          <div class="text-sm text-orange-700 mt-1">
            数据库中的跟踪池数据缺少评分信息。请先确保主线雷达数据已生成，然后点击"刷新数据"按钮同步龙头跟踪池。
          </div>
          <div class="mt-2 text-sm text-orange-600">
            操作步骤：
            <ol class="list-decimal list-inside mt-1 space-y-1">
              <li>在"主线雷达"页面刷新数据</li>
              <li>返回本页面点击"刷新数据"按钮</li>
              <li>或调用 API：<code class="bg-orange-100 px-1 py-0.5 rounded">POST /api/leader-score/sync-pool?trade_date=YYYY-MM-DD</code></li>
            </ol>
          </div>
        </div>
      </div>
    </div>

    <!-- 情绪周期卡片 -->
    <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-medium text-gray-900">情绪周期</h2>
        <div class="flex items-center gap-2">
          <span v-if="emotionCycle.data_source" class="text-xs text-gray-400">
            来源: {{ emotionCycle.data_source === 'database' ? '数据库' : '手动' }}
          </span>
          <span
            class="px-3 py-1 rounded-full text-sm font-medium"
            :class="getEmotionCycleClass(emotionCycle.cycle)"
          >
            {{ emotionCycle.cycle || '分析中...' }}
          </span>
        </div>
      </div>
      <div class="flex flex-wrap gap-4">
        <!-- 调试信息 -->
        <div v-if="true" class="w-full bg-yellow-50 p-2 text-xs text-gray-600 mb-2">
          DEBUG: {{ JSON.stringify(emotionCycle) }}
        </div>
        <div key="limit_up" class="flex-1 min-w-[120px] bg-gray-50 rounded-lg p-3 text-center">
          <div class="text-xl font-semibold text-gray-900">{{ emotionCycle.limit_up_count ?? '-' }}</div>
          <div class="text-xs text-gray-500">涨停家数</div>
        </div>
        <div key="limit_down" class="flex-1 min-w-[120px] bg-gray-50 rounded-lg p-3 text-center">
          <div class="text-xl font-semibold text-gray-900">{{ emotionCycle.limit_down_count ?? '-' }}</div>
          <div class="text-xs text-gray-500">跌停家数</div>
        </div>
        <div key="max_limit" class="flex-1 min-w-[120px] bg-gray-50 rounded-lg p-3 text-center">
          <div class="text-xl font-semibold text-gray-900">{{ emotionCycle.max_continuous_limit ?? '-' }}</div>
          <div class="text-xs text-gray-500">市场高度</div>
        </div>
        <div key="ad_ratio" class="flex-1 min-w-[120px] bg-gray-50 rounded-lg p-3 text-center">
          <div class="text-xl font-semibold text-gray-900">{{ emotionCycle.advance_decline_ratio?.toFixed(2) ?? '-' }}</div>
          <div class="text-xs text-gray-500">涨跌比</div>
        </div>
        <div key="emotion_score" class="flex-1 min-w-[120px] bg-gray-50 rounded-lg p-3 text-center">
          <div class="text-xl font-semibold text-gray-900">{{ emotionCycle.emotion_score?.toFixed(0) ?? '-' }}</div>
          <div class="text-xs text-gray-500">情绪分</div>
        </div>
        <div key="entry_threshold" class="flex-1 min-w-[120px] bg-gray-50 rounded-lg p-3 text-center">
          <div class="text-xl font-semibold text-blue-600">{{ emotionCycle.entry_threshold ?? '-' }}</div>
          <div class="text-xs text-gray-500">入池阈值</div>
        </div>
      </div>
    </div>

    <!-- 模型健康度 -->
    <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-medium text-gray-900">模型健康度</h2>
        <span
          class="px-3 py-1 rounded-full text-sm font-medium"
          :class="getHealthClass(modelHealth.health_score)"
        >
          {{ modelHealth.health_score?.toFixed(0) || '-' }}分
        </span>
      </div>
      <div class="grid grid-cols-5 gap-4">
        <div class="bg-gray-50 rounded-lg p-3 text-center">
          <div class="text-xl font-semibold" :class="getMetricClass(modelHealth.win_rate, 0.40)">
            {{ (modelHealth.win_rate * 100)?.toFixed(1) || '-' }}%
          </div>
          <div class="text-xs text-gray-500">胜率</div>
        </div>
        <div class="bg-gray-50 rounded-lg p-3 text-center">
          <div class="text-xl font-semibold" :class="getMetricClass(modelHealth.profit_loss_ratio, 1.3)">
            {{ modelHealth.profit_loss_ratio?.toFixed(2) || '-' }}
          </div>
          <div class="text-xs text-gray-500">盈亏比</div>
        </div>
        <div class="bg-gray-50 rounded-lg p-3 text-center">
          <div class="text-xl font-semibold" :class="modelHealth.max_drawdown <= -0.20 ? 'text-red-600' : 'text-green-600'">
            {{ (modelHealth.max_drawdown * 100)?.toFixed(1) || '-' }}%
          </div>
          <div class="text-xs text-gray-500">最大回撤</div>
        </div>
        <div class="bg-gray-50 rounded-lg p-3 text-center">
          <div class="text-xl font-semibold" :class="getMetricClass(modelHealth.signal_accuracy, 0.50)">
            {{ (modelHealth.signal_accuracy * 100)?.toFixed(1) || '-' }}%
          </div>
          <div class="text-xs text-gray-500">信号准确率</div>
        </div>
        <div class="bg-gray-50 rounded-lg p-3 text-center">
          <div class="text-xl font-semibold" :class="modelHealth.can_trade ? 'text-green-600' : 'text-red-600'">
            {{ modelHealth.can_trade ? '可交易' : '暂停' }}
          </div>
          <div class="text-xs text-gray-500">交易状态</div>
        </div>
      </div>
    </div>

    <!-- 龙头推荐列表 -->
    <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-medium text-gray-900">龙头推荐</h2>
        <div class="flex items-center gap-2">
          <select v-model="minGrade" @change="fetchRecommendations" class="text-sm border rounded px-2 py-1">
            <option value="S">S级</option>
            <option value="A">A级及以上</option>
            <option value="B">B级及以上</option>
          </select>
          <Button size="xs" variant="outline" @click="showBuySignalTypes = true">
            买点说明
          </Button>
        </div>
      </div>

      <div v-if="recommendations.length" class="overflow-x-auto">
        <table class="min-w-full text-sm">
          <thead>
            <tr class="text-left text-gray-500 border-b">
              <th class="py-2 px-3">股票</th>
              <th class="py-2 px-3 text-center">评级</th>
              <th class="py-2 px-3 text-right">综合评分</th>
              <th class="py-2 px-3 text-right">推荐日期</th>
              <th class="py-2 px-3 text-right">龙头地位</th>
              <th class="py-2 px-3 text-right">技术形态</th>
              <th class="py-2 px-3 text-right">资金流向</th>
              <th class="py-2 px-3 text-right">情绪热度</th>
              <th class="py-2 px-3">买点信号</th>
              <th class="py-2 px-3 text-center">风险等级</th>
              <th class="py-2 px-3">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in recommendations" :key="r.ts_code" class="border-b border-gray-50 hover:bg-gray-50">
              <td class="py-2 px-3">
                <span class="font-medium">{{ r.name }}</span>
                <span class="text-gray-400 ml-1 text-xs">{{ r.ts_code }}</span>
              </td>
              <td class="py-2 px-3 text-center">
                <span class="px-2 py-0.5 rounded text-xs font-bold" :class="getGradeClass(r.grade)">
                  {{ r.grade }}
                </span>
              </td>
              <td class="py-2 px-3 text-right font-medium">{{ r.total_score?.toFixed(1) }}</td>
              <td class="py-2 px-3 text-right text-xs text-gray-500">{{ r.recommend_date }}</td>
              <td class="py-2 px-3 text-right text-gray-600">{{ r.breakdown?.leader_position?.toFixed(1) }}</td>
              <td class="py-2 px-3 text-right text-gray-600">{{ r.breakdown?.technical?.toFixed(1) }}</td>
              <td class="py-2 px-3 text-right text-gray-600">{{ r.breakdown?.money_flow?.toFixed(1) }}</td>
              <td class="py-2 px-3 text-right text-gray-600">{{ r.breakdown?.sentiment?.toFixed(1) }}</td>
              <td class="py-2 px-3">
                <div class="flex flex-wrap gap-1">
                  <span
                    v-for="signal in r.buy_signals"
                    :key="signal.type"
                    class="text-xs px-2 py-0.5 rounded"
                    :class="signal.qualified ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'"
                    :title="signal.reason"
                  >
                    {{ signal.type }}
                  </span>
                </div>
              </td>
              <td class="py-2 px-3 text-center">
                <span class="text-xs" :class="getRiskClass(r.risk_level)">
                  {{ r.risk_level }}
                </span>
              </td>
              <td class="py-2 px-3">
                <Button size="xs" variant="outline" @click="analyzeSellStrategy(r)">
                  卖点分析
                </Button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="text-center text-gray-400 py-8">
        {{ loading ? '加载中...' : '暂无推荐' }}
      </div>
    </div>

    <!-- 带评分的跟踪池 -->
    <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-medium text-gray-900">跟踪池（带评分）</h2>
        <div class="flex items-center gap-2">
          <select v-model="poolFilter.grade" @change="fetchScoredPool" class="text-sm border rounded px-2 py-1">
            <option value="">全部评级</option>
            <option value="S">S级</option>
            <option value="A">A级</option>
            <option value="B">B级</option>
          </select>
          <Button size="xs" variant="outline" @click="syncPool" :disabled="syncing">
            {{ syncing ? '同步中...' : '同步当日' }}
          </Button>
          <Button size="xs" variant="primary" @click="batchSyncPool" :disabled="batchSyncing">
            {{ batchSyncing ? '批量同步中...' : '批量同步(60天)' }}
          </Button>
        </div>
      </div>

      <div v-if="scoredPool.length" class="overflow-x-auto">
        <table class="min-w-full text-sm">
          <thead>
            <tr class="text-left text-gray-500 border-b">
              <th class="py-2 px-3">股票</th>
              <th class="py-2 px-3 text-center">评级</th>
              <th class="py-2 px-3 text-right">评分</th>
              <th class="py-2 px-3 text-right">评分日期</th>
              <th class="py-2 px-3 text-right">连板</th>
              <th class="py-2 px-3 text-right">封单比</th>
              <th class="py-2 px-3">买点信号</th>
              <th class="py-2 px-3 text-center">入池状态</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in scoredPool" :key="s.ts_code" class="border-b border-gray-50 hover:bg-gray-50">
              <td class="py-2 px-3">
                <span class="font-medium">{{ s.name }}</span>
                <span class="text-gray-400 ml-1 text-xs">{{ s.ts_code }}</span>
              </td>
              <td class="py-2 px-3 text-center">
                <span class="px-2 py-0.5 rounded text-xs font-bold" :class="getGradeClass(s.grade)">
                  {{ s.grade }}
                </span>
              </td>
              <td class="py-2 px-3 text-right font-medium">{{ s.score?.toFixed(1) }}</td>
              <td class="py-2 px-3 text-right text-xs text-gray-500">{{ s.last_seen_date }}</td>
              <td class="py-2 px-3 text-right">{{ s.continuous_limit }}</td>
              <td class="py-2 px-3 text-right">{{ s.block_ratio?.toFixed(2) }}</td>
              <td class="py-2 px-3">
                <span v-if="s.buy_signal" class="text-xs px-2 py-0.5 rounded bg-blue-100 text-blue-700">
                  {{ s.buy_signal }}
                </span>
                <span v-else class="text-xs text-gray-400">-</span>
              </td>
              <td class="py-2 px-3 text-center">
                <span
                  class="text-xs px-2 py-0.5 rounded"
                  :class="s.should_enter ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'"
                >
                  {{ s.should_enter ? '已入池' : '未入池' }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="text-center text-gray-400 py-8">
        {{ loading ? '加载中...' : '暂无数据' }}
      </div>
    </div>

    <!-- 买点类型说明弹窗 -->
    <div v-if="showBuySignalTypes" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50" @click.self="showBuySignalTypes = false">
      <div class="bg-white rounded-xl shadow-xl w-full max-w-2xl max-h-[80vh] overflow-hidden flex flex-col">
        <div class="flex items-center justify-between p-4 border-b">
          <h2 class="text-lg font-medium">买点类型说明</h2>
          <button @click="showBuySignalTypes = false" class="text-gray-400 hover:text-gray-600">
            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div class="flex-1 overflow-auto p-4">
          <div class="space-y-3">
            <div v-for="t in buySignalTypes" :key="t.type" class="p-3 bg-gray-50 rounded-lg">
              <div class="font-medium text-gray-900">{{ t.type }}</div>
              <div class="text-sm text-gray-600 mt-1">{{ t.description }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 卖点分析弹窗 -->
    <div v-if="selectedStock" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50" @click.self="selectedStock = null">
      <div class="bg-white rounded-xl shadow-xl w-full max-w-3xl max-h-[80vh] overflow-hidden flex flex-col">
        <div class="flex items-center justify-between p-4 border-b">
          <h2 class="text-lg font-medium">{{ selectedStock.name }} 卖点策略分析</h2>
          <button @click="selectedStock = null" class="text-gray-400 hover:text-gray-600">
            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div class="flex-1 overflow-auto p-6 space-y-4">
          <!-- 输入参数 -->
          <div class="grid grid-cols-4 gap-3">
            <div>
              <label class="text-xs text-gray-500">买入价格</label>
              <input v-model.number="sellParams.buy_price" type="number" step="0.01" class="w-full border rounded px-2 py-1 text-sm" />
            </div>
            <div>
              <label class="text-xs text-gray-500">当前价格</label>
              <input v-model.number="sellParams.current_price" type="number" step="0.01" class="w-full border rounded px-2 py-1 text-sm" />
            </div>
            <div>
              <label class="text-xs text-gray-500">买入后最高价</label>
              <input v-model.number="sellParams.highest_price" type="number" step="0.01" class="w-full border rounded px-2 py-1 text-sm" />
            </div>
            <div class="flex items-end">
              <Button size="sm" variant="primary" @click="calculateSellStrategy" :disabled="calculating">
                {{ calculating ? '计算中...' : '计算策略' }}
              </Button>
            </div>
          </div>

          <!-- 策略结果 -->
          <div v-if="sellStrategy" class="space-y-4">
            <div class="p-4 rounded-lg" :class="getStrategyActionClass(sellStrategy.action)">
              <div class="text-lg font-semibold">{{ sellStrategy.action }}</div>
              <div class="text-sm mt-1">{{ sellStrategy.reason }}</div>
            </div>

            <div class="grid grid-cols-2 gap-4">
              <div class="bg-gray-50 rounded-lg p-4">
                <h3 class="text-sm font-medium text-gray-700 mb-2">止损设置</h3>
                <div class="text-sm text-gray-600">
                  <div>止损价格: <span class="font-medium text-red-600">{{ sellStrategy.stop_loss?.price?.toFixed(2) }}</span></div>
                  <div>止损比例: <span class="font-medium">{{ (sellStrategy.stop_loss?.pct * 100)?.toFixed(1) }}%</span></div>
                </div>
              </div>
              <div class="bg-gray-50 rounded-lg p-4">
                <h3 class="text-sm font-medium text-gray-700 mb-2">止盈设置</h3>
                <div class="text-sm text-gray-600">
                  <div>第一止盈: <span class="font-medium text-green-600">{{ sellStrategy.take_profit?.first?.toFixed(2) }}</span></div>
                  <div>第二止盈: <span class="font-medium text-green-600">{{ sellStrategy.take_profit?.second?.toFixed(2) }}</span></div>
                </div>
              </div>
            </div>

            <div class="bg-gray-50 rounded-lg p-4">
              <h3 class="text-sm font-medium text-gray-700 mb-2">卖出信号检查</h3>
              <div class="space-y-2">
                <div v-for="(signal, idx) in sellStrategy.signals" :key="idx" class="flex items-center justify-between text-sm">
                  <span>{{ signal.name }}</span>
                  <span
                    class="px-2 py-0.5 rounded text-xs"
                    :class="signal.triggered ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'"
                  >
                    {{ signal.triggered ? '已触发' : '未触发' }}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import Button from '@/components/ui/Button.vue'

const loading = ref(false)
const syncing = ref(false)
const batchSyncing = ref(false)
const calculating = ref(false)
const checkingData = ref(false)
const fillingLimitUp = ref(false)
const showBuySignalTypes = ref(false)
const selectedStock = ref(null)
const dataStatus = ref(null)

// 情绪周期
const emotionCycle = ref({})

// 模型健康度
const modelHealth = ref({
  win_rate: 0.45,
  profit_loss_ratio: 1.5,
  max_drawdown: -0.15,
  signal_accuracy: 0.55,
  health_score: 80,
  can_trade: true,
})

// 推荐列表
const recommendations = ref([])
const minGrade = ref('A')

// 跟踪池
const scoredPool = ref([])
const poolFilter = ref({
  grade: '',
})

// 买点类型
const buySignalTypes = ref([])

// 卖点分析参数
const sellParams = ref({
  buy_price: 10,
  current_price: 11,
  highest_price: 12,
})
const sellStrategy = ref(null)

// 获取情绪周期样式
function getEmotionCycleClass(cycle) {
  const classes = {
    '高涨期': 'bg-red-100 text-red-700',
    '震荡期': 'bg-yellow-100 text-yellow-700',
    '低迷期': 'bg-blue-100 text-blue-700',
    '冰点期': 'bg-gray-100 text-gray-700',
  }
  return classes[cycle] || 'bg-gray-100 text-gray-700'
}

// 获取健康度样式
function getHealthClass(score) {
  if (score >= 80) return 'bg-green-100 text-green-700'
  if (score >= 60) return 'bg-yellow-100 text-yellow-700'
  return 'bg-red-100 text-red-700'
}

// 获取指标样式
function getMetricClass(value, threshold) {
  return value >= threshold ? 'text-green-600' : 'text-red-600'
}

// 获取评级样式
function getGradeClass(grade) {
  const classes = {
    'S': 'bg-purple-100 text-purple-700',
    'A': 'bg-green-100 text-green-700',
    'B': 'bg-blue-100 text-blue-700',
    'C': 'bg-gray-100 text-gray-700',
  }
  return classes[grade] || 'bg-gray-100 text-gray-700'
}

// 获取风险等级样式
function getRiskClass(level) {
  const classes = {
    '高': 'text-red-600',
    '中': 'text-yellow-600',
    '低': 'text-green-600',
  }
  return classes[level] || 'text-gray-600'
}

// 获取策略操作样式
function getStrategyActionClass(action) {
  if (action?.includes('卖出') || action?.includes('止损')) return 'bg-red-50 text-red-700 border border-red-200'
  if (action?.includes('减仓')) return 'bg-yellow-50 text-yellow-700 border border-yellow-200'
  return 'bg-green-50 text-green-700 border border-green-200'
}

// 获取情绪周期
async function fetchEmotionCycle() {
  try {
    const res = await fetch('/api/emotion-cycle/analyze')
    const json = await res.json()
    console.log('情绪周期API返回:', json)
    if (json.success) {
      // 合并 data 和 entry_threshold、data_source
      emotionCycle.value = {
        ...json.data,
        entry_threshold: json.entry_threshold,
        data_source: json.data_source,
      }
      console.log('情绪周期数据已设置:', emotionCycle.value)
    }
  } catch (e) {
    console.error('获取情绪周期失败', e)
  }
}

// 获取模型健康度
async function fetchModelHealth() {
  try {
    const res = await fetch('/api/model-monitor/check', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        win_rate: modelHealth.value.win_rate,
        profit_loss_ratio: modelHealth.value.profit_loss_ratio,
        max_drawdown: modelHealth.value.max_drawdown,
        signal_accuracy: modelHealth.value.signal_accuracy,
      }),
    })
    const json = await res.json()
    if (json.success) {
      // 保持原有的绩效数据，只更新健康度相关字段
      modelHealth.value = {
        ...modelHealth.value,
        health_score: json.health_score,
        can_trade: json.health_score >= 30, // 健康度>=30才允许交易
        alerts: json.alerts,
        alert_count: json.alert_count,
        critical_count: json.critical_count,
        circuit_breaker_triggered: json.circuit_breaker_triggered,
        suggestions: json.suggestions,
      }
    }
  } catch (e) {
    console.error('获取模型健康度失败', e)
  }
}

// 获取推荐列表
async function fetchRecommendations() {
  try {
    const res = await fetch(`/api/leader-recommendation/list?min_grade=${minGrade.value}&emotion_cycle=${emotionCycle.value.cycle || '震荡期'}`)
    const json = await res.json()
    if (json.success) {
      recommendations.value = json.recommendations || []
    }
  } catch (e) {
    console.error('获取推荐失败', e)
  }
}

// 获取跟踪池
async function fetchScoredPool() {
  try {
    const params = new URLSearchParams()
    if (poolFilter.value.grade) params.append('min_grade', poolFilter.value.grade)
    params.append('emotion_cycle', emotionCycle.value.cycle || '震荡期')
    // 传入今天的日期，确保获取最新数据
    params.append('trade_date', new Date().toISOString().split('T')[0])

    const res = await fetch(`/api/leader-score/pool?${params}`)
    const json = await res.json()
    if (json.success) {
      // 按评分日期倒序排序（最新的在前）
      scoredPool.value = (json.pool || []).sort((a, b) => {
        const dateA = new Date(a.last_seen_date || '1970-01-01')
        const dateB = new Date(b.last_seen_date || '1970-01-01')
        return dateB - dateA
      })
    }
  } catch (e) {
    console.error('获取跟踪池失败', e)
  }
}

// 同步跟踪池评分
async function syncPool() {
  syncing.value = true
  try {
    const res = await fetch('/api/leader-score/sync-pool', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        trade_date: new Date().toISOString().split('T')[0],
        emotion_cycle: emotionCycle.value.cycle || '震荡期',
      }),
    })
    const json = await res.json()
    if (json.success) {
      await fetchScoredPool()
      alert(`同步成功：入池 ${json.entered_count} 只，失败 ${json.failed_count} 只`)
    }
  } catch (e) {
    console.error('同步失败', e)
    alert('同步失败')
  } finally {
    syncing.value = false
  }
}

// 批量同步跟踪池评分
async function batchSyncPool() {
  if (!confirm('批量同步将同步最近60个交易日的数据，可能需要几分钟时间。\n\n是否继续？')) {
    return
  }

  batchSyncing.value = true
  try {
    const res = await fetch('/api/leader-score/sync-pool/batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        days: 60,
        emotion_cycle: emotionCycle.value.cycle || '震荡期',
      }),
    })
    const json = await res.json()
    if (json.success) {
      await fetchScoredPool()
      alert(`批量同步完成！\n交易日数量: ${json.trade_dates_count}\n总入池: ${json.total_entered} 只\n总失败: ${json.total_failed} 只\n总错误: ${json.total_errors} 只`)
    } else {
      alert('批量同步失败: ' + (json.error || '未知错误'))
    }
  } catch (e) {
    console.error('批量同步失败', e)
    alert('批量同步失败')
  } finally {
    batchSyncing.value = false
  }
}

// 获取买点类型
async function fetchBuySignalTypes() {
  try {
    const res = await fetch('/api/leader-signals/buy/types')
    const json = await res.json()
    if (json.success) {
      buySignalTypes.value = json.types || []
    }
  } catch (e) {
    console.error('获取买点类型失败', e)
  }
}

// 分析卖点策略
function analyzeSellStrategy(stock) {
  selectedStock.value = stock
  sellStrategy.value = null
  sellParams.value = {
    buy_price: 10,
    current_price: 11,
    highest_price: 12,
  }
}

// 计算卖点策略
async function calculateSellStrategy() {
  if (!selectedStock.value) return

  calculating.value = true
  try {
    const params = new URLSearchParams({
      ts_code: selectedStock.value.ts_code,
      name: selectedStock.value.name,
      buy_price: sellParams.value.buy_price,
      buy_date: new Date().toISOString().split('T')[0],
      current_price: sellParams.value.current_price,
      highest_price_since_buy: sellParams.value.highest_price,
      emotion_cycle: emotionCycle.value.cycle || '震荡期',
    })

    const res = await fetch(`/api/leader-signals/sell/analyze?${params}`, {
      method: 'POST',
    })
    const json = await res.json()
    if (json.success) {
      sellStrategy.value = json.strategy
    }
  } catch (e) {
    console.error('计算卖点策略失败', e)
  } finally {
    calculating.value = false
  }
}

// 刷新所有数据
async function refreshAll() {
  loading.value = true
  await Promise.all([
    fetchEmotionCycle(),
    fetchModelHealth(),
    fetchRecommendations(),
    fetchScoredPool(),
    fetchBuySignalTypes(),
  ])
  loading.value = false
}

// 检查数据状态
async function checkDataStatus() {
  checkingData.value = true
  try {
    const res = await fetch('/api/leader-optimization/diag/data-status')
    const json = await res.json()
    if (json.success) {
      dataStatus.value = {
        all_tables_empty: json.summary?.all_tables_empty,
        summary: json.summary,
        data_status: json.data_status,
      }
    }
  } catch (e) {
    console.error('检查数据状态失败', e)
  } finally {
    checkingData.value = false
  }
}

// 补充涨停数据
async function fillLimitUpData() {
  fillingLimitUp.value = true
  try {
    const tradeDate = new Date().toISOString().split('T')[0]
    const res = await fetch(`/api/leader-optimization/fill-limit-up?trade_date=${tradeDate}`, {
      method: 'POST',
    })
    const json = await res.json()
    if (json.success) {
      if (json.skipped) {
        alert(json.message)
      } else {
        alert(`涨停数据补充完成！\n日期: ${json.trade_date}\n新增: ${json.added_count} 条\n总计: ${json.new_count} 条`)
        // 刷新数据
        await refreshAll()
      }
    } else {
      alert('补充失败: ' + (json.message || '未知错误'))
    }
  } catch (e) {
    console.error('补充涨停数据失败', e)
    alert('补充涨停数据失败')
  } finally {
    fillingLimitUp.value = false
  }
}

onMounted(() => {
  refreshAll()
  checkDataStatus()
})
</script>
