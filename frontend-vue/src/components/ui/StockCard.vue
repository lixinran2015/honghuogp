<template>
  <Card :hoverable="true" padding="md" class="stock-card">
    <div class="space-y-3">
      <!-- 第一行：名称、股票代码、价格 -->
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-3 flex-1">
          <h3 class="font-semibold text-gray-900 text-lg">{{ stock.name || '--' }}</h3>
          <span class="text-sm text-gray-500 font-mono">{{ stock.code || '--' }}</span>
          <span class="text-gray-500">价格：</span>
          <span class="text-gray-900 font-semibold text-lg">¥{{ stock.price || '--' }}</span>
        </div>
        <span :class="[
          'px-2 py-1 rounded text-xs font-medium',
          strategyType === 'darwin' ? 'bg-yellow-100 text-yellow-700' :
          strategyType === 'swing' ? 'bg-green-100 text-green-700' :
          'bg-blue-100 text-blue-700'
        ]">
          {{ strategyType === 'darwin' ? '达尔文' : strategyType === 'swing' ? '波段' : '短线' }}
        </span>
      </div>

      <!-- 第二行：涨跌幅、换手率、成交额 -->
      <div class="flex items-center gap-3 text-sm flex-wrap">
        <span class="text-gray-500">
          涨跌幅：
          <span :class="[
            'font-medium',
            stock.changePercent >= 0 ? 'text-red-600' : 'text-green-600'
          ]">
            {{ stock.changePercent >= 0 ? '+' : '' }}{{ stock.changePercent.toFixed(2) }}%
          </span>
        </span>
        <span class="text-gray-500">
          换手率：<span class="text-gray-900 font-medium">{{ stock.turnover || '--' }}</span>
        </span>
        <span class="text-gray-500">
          成交额：<span class="text-gray-900 font-medium">{{ stock.volume || '--' }}</span>
        </span>
      </div>

      <!-- 第二行：板块、系统评分、趋势分 -->
      <div class="flex items-center gap-3 text-sm flex-wrap">
        <span class="text-gray-500">
          板块：<span class="text-gray-900 font-medium">{{ stock.sector || '--' }}</span>
        </span>
        <span v-if="stock.score" class="text-gray-500">
          系统评分：<span class="text-gray-900 font-medium">{{ stock.score.toFixed(1) }}</span>
        </span>
        <span v-if="stock.trendScore !== null && stock.trendScore !== undefined" class="text-gray-500">
          趋势分：
          <span :class="[
            'font-medium',
            (stock.trendScore >= 70 || (stock.trendScore < 1 && stock.trendScore >= 0.7)) ? 'text-red-600' :
            (stock.trendScore >= 50 || (stock.trendScore < 1 && stock.trendScore >= 0.5)) ? 'text-yellow-600' :
            'text-green-600'
          ]">
            {{ stock.trendScore < 1 ? (stock.trendScore * 100).toFixed(1) : stock.trendScore.toFixed(1) }}%
          </span>
        </span>
      </div>

      <!-- 量价策略 -->
      <div v-if="stock.volumePricePattern" class="flex items-center gap-3 text-sm flex-wrap">
        <span class="text-gray-500">
          量价形态：
          <span class="px-2 py-0.5 bg-purple-100 text-purple-800 text-xs rounded font-medium">
            {{ stock.volumePricePattern }}
          </span>
        </span>
        <span v-if="stock.vpAdvice || stock.vpComment" class="text-gray-500 text-xs">
          <span v-if="stock.vpAdvice" class="px-2 py-0.5 bg-blue-100 text-blue-800 rounded mr-2">
            {{ stock.vpAdvice }}
          </span>
          <span v-if="stock.vpComment" class="text-gray-600">{{ stock.vpComment }}</span>
        </span>
      </div>

      <!-- 板块热度和入手区间 -->
      <div v-if="stock.sectorHeat || stock.buyRange" class="flex items-center gap-3 text-sm flex-wrap">
        <span v-if="stock.sectorHeat" class="text-gray-500">
          板块热度：<span class="text-gray-900 font-medium">{{ stock.sectorHeat }}</span>
        </span>
        <span v-if="stock.buyRange" class="text-gray-500">
          入手区间：
          <span class="text-gray-900 font-medium">
            <template v-if="typeof stock.buyRange === 'object'">
              ¥{{ stock.buyRange.min.toFixed(2) }} - ¥{{ stock.buyRange.max.toFixed(2) }}
            </template>
            <template v-else>
              {{ stock.buyRange }}
            </template>
          </span>
        </span>
      </div>

      <!-- AI评分及评分理由 -->
      <div v-if="stock.aiScore || stock.aiAnalysis" class="bg-purple-50 p-2 rounded">
        <div class="flex items-start gap-2">
          <span class="text-xs text-gray-500">AI评分：</span>
          <div class="flex-1">
            <div v-if="stock.aiScore" class="flex items-center gap-2 mb-1">
              <span class="text-sm font-semibold text-purple-700">{{ formatAiScore(stock.aiScore) }}</span>
              <span v-if="stock.deepseekScore" class="text-sm font-semibold text-blue-700">/ {{ formatAiScore(stock.deepseekScore) }}</span>
            </div>
            <p v-if="stock.aiAnalysis" class="text-xs text-gray-700 mt-1 whitespace-pre-wrap">{{ formatAiText(stock.aiAnalysis) }}</p>
            <p v-if="stock.deepseekAnalysis" class="text-xs text-gray-700 mt-1 whitespace-pre-wrap">{{ formatAiText(stock.deepseekAnalysis) }}</p>
          </div>
        </div>
      </div>

      <!-- 推荐理由 -->
      <div v-if="stock.reason" class="bg-blue-50 p-2 rounded">
        <p class="text-xs text-gray-500 mb-1">推荐理由</p>
        <p class="text-sm text-gray-700">{{ stock.reason }}</p>
      </div>

      <!-- 操作按钮 -->
      <div class="flex items-center justify-end gap-2 pt-2 border-t">
        <!-- 买入按钮 -->
        <button
          v-if="stock.advice && stock.advice.includes('买入')"
          :class="[
            'px-3 py-1.5 text-sm font-medium rounded-lg transition-colors border',
            'bg-green-100 text-green-700 hover:bg-green-200 border-green-300'
          ]"
        >
          {{ stock.advice }}
        </button>
        <!-- 加入操作池按钮 -->
        <button
          v-if="!stock.inHolding"
          @click="handleAddToHolding"
          class="px-3 py-1.5 text-sm font-medium text-blue-600 hover:bg-blue-50 rounded-lg transition-colors border border-blue-200"
        >
          + 加入操作池
        </button>
        <button
          v-else
          @click="handleViewHolding"
          class="px-3 py-1.5 text-sm font-medium text-gray-600 hover:bg-gray-50 rounded-lg transition-colors border border-gray-200"
        >
          已在操作池
        </button>
      </div>
    </div>

    <!-- 加入操作池对话框 -->
    <div v-if="showAddDialog" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg p-6 max-w-md w-full mx-4">
        <h3 class="text-lg font-semibold mb-4">加入操作池</h3>
        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">股票</label>
            <p class="text-sm text-gray-600">{{ stock.name }} ({{ stock.code }})</p>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">分类</label>
            <select v-model="addForm.board_type" class="w-full px-3 py-2 border border-gray-300 rounded-md">
              <option value="darwin">达尔文</option>
              <option value="swing">波段</option>
              <option value="short">短线</option>
              <option value="other">其他</option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">买入价（可选）</label>
            <input
              v-model.number="addForm.buy_price"
              type="number"
              step="0.01"
              class="w-full px-3 py-2 border border-gray-300 rounded-md"
              placeholder="输入买入价"
            />
            <button
              @click="addForm.buy_price = stock.price || stock.currentPrice"
              class="mt-1 text-xs text-blue-600 hover:text-blue-800"
            >
              使用当前价
            </button>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">数量（可选）</label>
            <input
              v-model.number="addForm.quantity"
              type="number"
              step="100"
              class="w-full px-3 py-2 border border-gray-300 rounded-md"
              placeholder="输入数量（股）"
            />
          </div>
        </div>
        <div class="flex items-center gap-2 mt-6">
          <button
            @click="handleConfirmAdd"
            class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            确认
          </button>
          <button
            @click="showAddDialog = false"
            class="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition-colors"
          >
            取消
          </button>
        </div>
      </div>
    </div>
  </Card>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import Card from './Card.vue'

const props = defineProps({
  stock: {
    type: Object,
    required: true,
  },
  strategyType: {
    type: String,
    default: 'all',
  },
})

const emit = defineEmits(['added'])

const router = useRouter()
const showAddDialog = ref(false)
const addForm = ref({
  board_type: props.strategyType === 'darwin' ? 'darwin' : props.strategyType === 'swing' ? 'swing' : props.strategyType === 'short' ? 'short' : 'other',
  buy_price: null,
  quantity: null
})

const handleAddToHolding = () => {
  addForm.value.buy_price = props.stock.price || props.stock.currentPrice
  showAddDialog.value = true
}

const handleViewHolding = () => {
  router.push('/holdings')
}

const handleConfirmAdd = async () => {
  try {
    const response = await fetch('/api/holdings', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        symbol: props.stock.code,
        name: props.stock.name,
        board_type: addForm.value.board_type,
        buy_price: addForm.value.buy_price,
        quantity: addForm.value.quantity,
        bypass_trading_rules: false
      })
    })
    
    const result = await response.json()
    
    if (result.success) {
      showAddDialog.value = false
      emit('added')
      alert('已加入操作池')
    } else {
      alert('加入失败，请重试')
    }
  } catch (error) {
    console.error('加入操作池失败:', error)
    alert('加入失败，请重试')
  }
}

// 格式化AI评分（去除markdown格式）
const formatAiScore = (score) => {
  if (!score) return ''
  // 去除markdown格式，如 **文本** -> 文本
  return String(score)
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/\*(.*?)\*/g, '$1')
    .replace(/`(.*?)`/g, '$1')
    .trim()
}

// 格式化AI文本（去除markdown格式，保留换行）
const formatAiText = (text) => {
  if (!text) return ''
  return String(text)
    // 去除markdown标题
    .replace(/^#{1,6}\s+/gm, '')
    // 去除粗体
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/\*(.*?)\*/g, '$1')
    // 去除代码块
    .replace(/```[\s\S]*?```/g, '')
    .replace(/`(.*?)`/g, '$1')
    // 去除链接，保留文本
    .replace(/\[([^\]]+)\]\([^\)]+\)/g, '$1')
    // 去除列表标记
    .replace(/^[\s]*[-*+]\s+/gm, '• ')
    .replace(/^\d+\.\s+/gm, '')
    // 去除多余空行（保留最多一个空行）
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}
</script>

<style scoped>
.stock-card {
  transition: all 0.2s ease;
}

.stock-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}
</style>

