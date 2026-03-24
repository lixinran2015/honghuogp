<template>
  <div class="p-8 space-y-8">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-semibold text-gray-900 mb-2">策略引擎</h1>
        <p class="text-sm text-gray-500">策略配置与回测分析</p>
      </div>
      <Button size="sm" variant="secondary" @click="handleRefresh" :disabled="loading">
        {{ loading ? '加载中...' : '刷新' }}
      </Button>
    </div>

    <!-- 操作依据说明卡片 -->
    <Card class="bg-gradient-to-r from-blue-50 to-indigo-50 border-blue-200">
      <div class="p-6">
        <h2 class="text-lg font-semibold text-gray-900 mb-4 flex items-center">
          <span class="mr-2">📋</span>
          操作依据说明
        </h2>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <!-- 买入 -->
          <div class="bg-white p-4 rounded-lg border border-green-200 shadow-sm">
            <div class="flex items-center mb-3">
              <span class="px-2.5 py-1 bg-green-100 text-green-700 rounded text-xs font-semibold mr-2">买入</span>
              <span class="text-sm font-semibold text-gray-900">建仓时机</span>
            </div>
            <ul class="text-xs text-gray-600 space-y-1.5">
              <li class="flex items-start">
                <span class="text-green-600 mr-1">✓</span>
                <span>追高风险较低（low），策略信号明确</span>
              </li>
              <li class="flex items-start">
                <span class="text-green-600 mr-1">✓</span>
                <span>量价配合良好（量增价升、量平价升）</span>
              </li>
              <li class="flex items-start">
                <span class="text-green-600 mr-1">✓</span>
                <span>趋势向上确认（MA20>MA60）；大盘/板块不处于明显下跌</span>
              </li>
              <li class="flex items-start">
                <span class="text-green-600 mr-1">✓</span>
                <span>单次建仓不超过总仓位约1/3，控制仓位、分批建仓</span>
              </li>
            </ul>
          </div>

          <!-- 加仓 -->
          <div class="bg-white p-4 rounded-lg border border-blue-200 shadow-sm">
            <div class="flex items-center mb-3">
              <span class="px-2.5 py-1 bg-blue-100 text-blue-700 rounded text-xs font-semibold mr-2">加仓</span>
              <span class="text-sm font-semibold text-gray-900">增持时机</span>
            </div>
            <ul class="text-xs text-gray-600 space-y-1.5">
              <li class="flex items-start">
                <span class="text-blue-600 mr-1">✓</span>
                <span>已有持仓，追高风险低（low）</span>
              </li>
              <li class="flex items-start">
                <span class="text-blue-600 mr-1">✓</span>
                <span>浮盈/浮亏在-5%~+5%区间</span>
              </li>
              <li class="flex items-start">
                <span class="text-blue-600 mr-1">✓</span>
                <span>趋势延续确认，量价结构健康</span>
              </li>
              <li class="flex items-start">
                <span class="text-blue-600 mr-1">✓</span>
                <span>加仓后该标的建议不超过总仓位一定比例；浮亏近-5%时若跌破关键均线则不再加仓</span>
              </li>
            </ul>
          </div>

          <!-- 减仓 -->
          <div class="bg-white p-4 rounded-lg border border-yellow-200 shadow-sm">
            <div class="flex items-center mb-3">
              <span class="px-2.5 py-1 bg-yellow-100 text-yellow-700 rounded text-xs font-semibold mr-2">减仓</span>
              <span class="text-sm font-semibold text-gray-900">减持时机</span>
            </div>
            <ul class="text-xs text-gray-600 space-y-1.5">
              <li class="flex items-start">
                <span class="text-yellow-600 mr-1">⚠</span>
                <span>止盈型：浮盈≥15%或追高+浮盈≥5%，分批减仓约1/2，可保留底仓</span>
              </li>
              <li class="flex items-start">
                <span class="text-yellow-600 mr-1">⚠</span>
                <span>风控型：量价背离或高位放量下跌，加大减仓力度</span>
              </li>
              <li class="flex items-start">
                <span class="text-yellow-600 mr-1">⚠</span>
                <span>减仓后可不低于初始仓位约30%，便于趋势延续时仍能参与</span>
              </li>
              <li class="flex items-start">
                <span class="text-yellow-600 mr-1">⚠</span>
                <span>分批减仓，锁定收益</span>
              </li>
            </ul>
          </div>

          <!-- 清仓 -->
          <div class="bg-white p-4 rounded-lg border border-red-200 shadow-sm">
            <div class="flex items-center mb-3">
              <span class="px-2.5 py-1 bg-red-100 text-red-700 rounded text-xs font-semibold mr-2">清仓</span>
              <span class="text-sm font-semibold text-gray-900">止损/止盈</span>
            </div>
            <ul class="text-xs text-gray-600 space-y-1.5">
              <li class="flex items-start">
                <span class="text-red-600 mr-1">✗</span>
                <span>亏损达-8%：建议先减半仓观察，反弹无力或继续破位再清仓</span>
              </li>
              <li class="flex items-start">
                <span class="text-red-600 mr-1">✗</span>
                <span>趋势明确反转（量增价跌、跌破关键均线）</span>
              </li>
              <li class="flex items-start">
                <span class="text-red-600 mr-1">✗</span>
                <span>重大利空消息或基本面恶化</span>
              </li>
              <li class="flex items-start">
                <span class="text-red-600 mr-1">✗</span>
                <span>及时止损，保护本金</span>
              </li>
            </ul>
          </div>
        </div>
        <div class="mt-4 pt-4 border-t border-gray-200">
          <p class="text-xs text-gray-500 leading-relaxed">
            <span class="font-semibold text-gray-700">说明：</span>
            操作建议基于策略信号、量价形态、追高风险等级（low/medium/high）、盈亏比例等多维度综合判断。建仓建议单次不超过总仓位约1/3；加仓需控制单票比例且浮亏近-5%时跌破均线不宜再加；减仓区分止盈型（保留底仓）与风控型（加大力度）；亏损-8%可先减半仓再观察，趋势反转宜清仓。请结合市场环境与个人风险承受能力执行。
          </p>
        </div>
      </div>
    </Card>

    <!-- 加载状态 -->
    <div v-if="loading" class="flex justify-center items-center py-12">
      <div class="text-gray-500">加载中...</div>
    </div>

    <!-- 策略卡片 - 一行4个，垂直布局，卡片高度放大 -->
    <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
      <Card
        v-for="strategy in strategies"
        :key="strategy.id"
        hoverable
        class="min-h-[600px] flex flex-col"
      >
        <!-- 卡片头部 -->
        <div class="flex items-start justify-between mb-4">
          <div class="flex-1">
            <h3 class="text-lg font-semibold text-gray-900 mb-1">{{ strategy.name }}</h3>
            <p class="text-sm text-gray-500 mb-2">{{ strategy.description }}</p>
            <!-- 新高回踩策略的分步说明 -->
            <div v-if="strategy.filterSteps" class="space-y-2 mt-3">
              <div v-for="(step, idx) in strategy.filterSteps" :key="idx" class="flex items-start text-xs">
                <span class="px-1.5 py-0.5 bg-indigo-100 text-indigo-700 rounded font-medium mr-2 whitespace-nowrap">{{ step.label }}</span>
                <span class="text-gray-600">{{ step.content }}</span>
              </div>
            </div>
          </div>
          <div :class="[
            'px-2 py-1 rounded text-xs font-medium whitespace-nowrap ml-2',
            strategy.status === 'active' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-700'
          ]">
            {{ strategy.status === 'active' ? '运行中' : '已停止' }}
          </div>
        </div>

        <!-- 性能指标 -->
        <div class="space-y-2 mb-4">
          <div class="flex justify-between text-sm">
            <span class="text-gray-500">收益率</span>
            <span class="font-semibold text-gray-900">{{ strategy.return }}%</span>
          </div>
          <div class="flex justify-between text-sm">
            <span class="text-gray-500">胜率</span>
            <span class="font-semibold text-gray-900">{{ strategy.winRate }}%</span>
          </div>
          <div class="flex justify-between text-sm">
            <span class="text-gray-500">最大回撤</span>
            <span class="font-semibold text-gray-900">{{ strategy.maxDrawdown }}%</span>
          </div>
        </div>

        <!-- 策略详情 - 垂直布局 -->
        <div class="mt-auto space-y-4 border-t pt-4 flex-1 flex flex-col">
          <!-- 使用字段 -->
          <div v-if="strategy.fields && strategy.fields.length > 0">
            <h4 class="text-xs font-semibold text-gray-700 mb-2">使用字段</h4>
            <ul class="space-y-1">
              <li v-for="(field, idx) in strategy.fields.slice(0, 4)" :key="idx" class="text-xs text-gray-600">
                • {{ field }}
              </li>
              <li v-if="strategy.fields.length > 4" class="text-xs text-gray-400">
                等{{ strategy.fields.length }}个字段
              </li>
            </ul>
          </div>

          <!-- 评分公式（如果有） -->
          <div v-if="strategy.formula">
            <h4 class="text-xs font-semibold text-gray-700 mb-1">评分公式</h4>
            <p class="text-xs text-gray-600 bg-blue-50 p-2 rounded border border-blue-200">{{ strategy.formula }}</p>
          </div>

          <!-- 输出内容 -->
          <div v-if="strategy.output">
            <h4 class="text-xs font-semibold text-gray-700 mb-1">输出内容</h4>
            <p class="text-xs text-gray-600">{{ strategy.output }}</p>
          </div>

          <!-- 示例（如果有） -->
          <div v-if="strategy.examples && strategy.examples.length > 0 && strategy.id !== 'volume-price'">
            <h4 class="text-xs font-semibold text-gray-700 mb-2">示例</h4>
            <div class="space-y-2">
              <div
                v-for="(example, idx) in strategy.examples.slice(0, 2)"
                :key="idx"
                class="text-xs p-2 rounded border border-gray-200 bg-gray-50"
              >
                <pre class="text-xs text-gray-600 whitespace-pre-wrap">{{ JSON.stringify(example, null, 2) }}</pre>
              </div>
            </div>
          </div>

          <!-- 量价形态（仅量价关系策略显示，放在最下面） -->
          <div v-if="strategy.id === 'volume-price' && strategy.patterns && strategy.patterns.length > 0">
            <h4 class="text-xs font-semibold text-gray-700 mb-2">量价形态（{{ strategy.patterns.length }}种）</h4>
            <div class="space-y-2">
              <div
                v-for="(pattern, idx) in strategy.patterns"
                :key="idx"
                class="text-xs p-2 rounded border border-gray-200 bg-gray-50 hover:bg-gray-100 transition-colors"
              >
                <div class="flex items-center justify-between mb-1">
                  <span class="font-medium text-gray-900">{{ pattern.pattern }}</span>
                  <span :class="[
                    'px-1.5 py-0.5 rounded text-xs font-medium',
                    getAdviceColorClass(pattern.advice)
                  ]">
                    {{ pattern.advice }}
                  </span>
                </div>
                <p class="text-gray-600 text-xs leading-relaxed mb-1">{{ pattern.description }}</p>
                <p v-if="pattern.example" class="text-gray-500 text-xs italic">{{ pattern.example }}</p>
              </div>
            </div>
          </div>

          <!-- 策略步骤（其他策略显示，放在最下面） -->
          <div v-if="strategy.steps && strategy.steps.length > 0 && strategy.id !== 'volume-price'">
            <h4 class="text-xs font-semibold text-gray-700 mb-2">筛选步骤（{{ strategy.steps.length }}步）</h4>
            <div class="space-y-2">
              <div
                v-for="(step, idx) in strategy.steps"
                :key="idx"
                class="text-xs p-2 rounded border border-gray-200 bg-gray-50 hover:bg-gray-100 transition-colors"
              >
                <div class="flex items-center justify-between mb-1">
                  <span class="font-medium text-gray-900">步骤{{ step.step }}：{{ step.name }}</span>
                </div>
                <p class="text-gray-600 text-xs leading-relaxed mb-1">{{ step.description }}</p>
                <p v-if="step.example" class="text-gray-500 text-xs italic">示例：{{ step.example }}</p>
              </div>
            </div>
          </div>
        </div>
      </Card>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import Card from '../components/ui/Card.vue'
import Button from '../components/ui/Button.vue'
import { getStrategyEngines } from '../api/strategyApi.js'

const loading = ref(true)
const selectedStrategy = ref(null)

// 默认策略数据（如果API失败时使用）
const defaultStrategies = [
  {
    id: 'volume-price',
    name: '量价关系策略',
    description: '识别12种量价形态，给出操作建议（买入、持有、减仓、观望）',
    status: 'active',
    return: 24.5,
    winRate: 75.2,
    maxDrawdown: -10.8,
  },
  {
    id: 'darwin',
    name: '达尔文长期策略',
    description: '基于财务质量的长期投资',
    status: 'active',
    return: 15.8,
    winRate: 68.5,
    maxDrawdown: -8.2,
  },
  {
    id: 'new_high',
    name: '新高回踩策略',
    description: '三阶段筛选策略',
    filterSteps: [
      { label: '前置筛选', content: '创业板/科创板（300/301/688开头）+ 非ST股票' },
      { label: 'S1新高策略', content: '股价>=10元，成交额<=10亿，近30日新高（收盘价距30日最高≤5%）' },
      { label: '新高回踩', content: '当日涨幅>=3%' },
    ],
    status: 'active',
    return: 22.3,
    winRate: 72.1,
    maxDrawdown: -12.5,
  },
  {
    id: 'short',
    name: '短线动量策略',
    description: '热门板块的龙头股票',
    status: 'active',
    return: 18.6,
    winRate: 65.8,
    maxDrawdown: -15.3,
  },
]

const strategies = ref([...defaultStrategies])

// 获取操作建议的颜色类
const getAdviceColorClass = (advice) => {
  if (advice.includes('买入')) {
    return 'bg-green-100 text-green-700'
  } else if (advice.includes('卖出') || advice.includes('减仓')) {
    return 'bg-red-100 text-red-700'
  } else if (advice.includes('持有')) {
    return 'bg-yellow-100 text-yellow-700'
  } else {
    return 'bg-gray-100 text-gray-700'
  }
}

// 从API获取策略引擎详情
const fetchStrategyEngines = async () => {
  try {
    loading.value = true
    const engines = await getStrategyEngines()
    
    if (engines && engines.length > 0) {
      // 将API返回的引擎数据与默认策略合并
      strategies.value = defaultStrategies.map(defaultStrategy => {
        // 查找对应的引擎数据
        const engine = engines.find(e => {
          if (defaultStrategy.id === 'volume-price') {
            return e.name === '量价关系模型'
          } else if (defaultStrategy.id === 'darwin') {
            return e.name.includes('达尔文') || e.name.includes('长期')
          } else if (defaultStrategy.id === 'swing') {
            return e.name.includes('波段') || e.name.includes('回踩')
          } else if (defaultStrategy.id === 'short') {
            return e.name.includes('短线') || e.name.includes('动量')
          }
          return false
        })

        if (engine) {
          return {
            ...defaultStrategy,
            fields: engine.fields || [],
            output: engine.output || '',
            patterns: engine.patterns || [],
            examples: engine.examples || [],
            steps: engine.steps || [],
            formula: engine.formula || ''
          }
        }
        return defaultStrategy
      })
    }
  } catch (error) {
    console.error('获取策略引擎详情失败:', error)
    // 使用默认数据
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchStrategyEngines()
})
</script>

