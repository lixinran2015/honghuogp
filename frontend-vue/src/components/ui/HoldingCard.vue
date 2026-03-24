<template>
  <Card class="hover:shadow-lg transition-shadow">
    <!-- 顶部：股票信息 -->
    <div class="flex items-start justify-between mb-4">
      <div>
        <h3 class="text-lg font-semibold text-gray-900">{{ holding.name }}</h3>
        <p class="text-sm text-gray-500">{{ holding.symbol }}</p>
      </div>
      <span :class="[
        'px-2 py-1 text-xs rounded',
        boardTypeColors[holding.board_type] || 'bg-gray-100 text-gray-700'
      ]">
        {{ boardTypeLabels[holding.board_type] || '其他' }}
      </span>
    </div>

    <!-- 核心数据 -->
    <div class="space-y-3 mb-4">
      <!-- 价格信息 -->
      <div class="flex items-center justify-between">
        <span class="text-sm text-gray-500">当前价</span>
        <span class="text-lg font-semibold text-gray-900">
          {{ holding.current_price && holding.current_price > 0 ? holding.current_price.toFixed(2) : '--' }}
        </span>
      </div>
      <div class="flex items-center justify-between">
        <span class="text-sm text-gray-500">成本价</span>
        <span class="text-sm font-medium text-gray-700">
          {{ holding.avg_cost_price && holding.avg_cost_price > 0 ? holding.avg_cost_price.toFixed(2) : '--' }}
        </span>
      </div>
      
      <!-- 盈亏信息 -->
      <div class="flex items-center justify-between pt-2 border-t">
        <span class="text-sm text-gray-500">浮动盈亏</span>
        <div class="text-right">
          <div v-if="holding.current_price && holding.current_price > 0 && holding.avg_cost_price && holding.avg_cost_price > 0" :class="[
            'text-lg font-semibold',
            (holding.profit_rate || 0) >= 0 ? 'text-red-600' : 'text-green-600'
          ]">
            {{ (holding.profit_rate || 0) >= 0 ? '+' : '' }}{{ (holding.profit_rate || 0).toFixed(2) }}%
          </div>
          <div v-else class="text-lg font-semibold text-gray-400">--</div>
          <div v-if="holding.profit_amount !== null && holding.profit_amount !== undefined" :class="[
            'text-xs',
            (holding.profit_amount || 0) >= 0 ? 'text-red-600' : 'text-green-600'
          ]">
            {{ (holding.profit_amount || 0) >= 0 ? '+' : '' }}{{ formatAmount(holding.profit_amount || 0) }}
          </div>
          <div v-else class="text-xs text-gray-400">--</div>
        </div>
      </div>
      
      <!-- 持仓数量 -->
      <div class="flex items-center justify-between">
        <span class="text-sm text-gray-500">持仓数量</span>
        <span class="text-sm font-medium text-gray-700">{{ formatQuantity(holding.total_quantity || 0) }}</span>
      </div>
      
      <!-- 市值 -->
      <div class="flex items-center justify-between">
        <span class="text-sm text-gray-500">市值</span>
        <span class="text-sm font-medium text-gray-700">{{ formatAmount(holding.market_value || 0) }}</span>
      </div>
    </div>

    <!-- 追高风险 -->
    <div class="mb-4 p-2 rounded" :class="riskLevelColors[holding.chase_risk_level] || 'bg-gray-50'">
      <div class="flex items-center justify-between mb-1">
        <span class="text-xs text-gray-600">追高风险</span>
        <span :class="[
          'px-2 py-0.5 text-xs rounded font-medium',
          riskLevelBadgeColors[holding.chase_risk_level] || 'bg-gray-100 text-gray-700'
        ]">
          {{ riskLevelLabels[holding.chase_risk_level] || '低' }}
        </span>
      </div>
      <p class="text-xs text-gray-600">{{ holding.chase_risk_reason || '暂无风险提示' }}</p>
    </div>

    <!-- 回涨分析（仅亏损股票显示） -->
    <div v-if="holding.profit_rate < 0 && holding.recovery_analysis" class="mb-4 p-3 rounded border-2" :class="recoveryLevelColors[holding.recovery_analysis.recovery_level] || 'bg-gray-50 border-gray-200'">
      <div class="flex items-center justify-between mb-2">
        <span class="text-xs font-semibold text-gray-700">回涨可能性分析</span>
        <div class="flex items-center gap-2">
          <span :class="[
            'px-2 py-0.5 text-xs rounded font-medium',
            recoveryLevelBadgeColors[holding.recovery_analysis.recovery_level] || 'bg-gray-100 text-gray-700'
          ]">
            {{ recoveryLevelLabels[holding.recovery_analysis.recovery_level] || '未知' }}
          </span>
          <span class="text-xs font-bold" :class="recoveryLevelTextColors[holding.recovery_analysis.recovery_level] || 'text-gray-600'">
            {{ holding.recovery_analysis.recovery_probability?.toFixed(0) || 0 }}%
          </span>
        </div>
      </div>
      <div v-if="holding.recovery_analysis.recovery_reasons && holding.recovery_analysis.recovery_reasons.length > 0" class="mb-2">
        <p class="text-xs font-medium text-green-700 mb-1">有利因素：</p>
        <ul class="text-xs text-gray-600 space-y-0.5">
          <li v-for="(reason, idx) in holding.recovery_analysis.recovery_reasons.slice(0, 3)" :key="idx" class="flex items-start">
            <span class="text-green-500 mr-1">•</span>
            <span>{{ reason }}</span>
          </li>
        </ul>
      </div>
      <div v-if="holding.recovery_analysis.risk_factors && holding.recovery_analysis.risk_factors.length > 0" class="mb-2">
        <p class="text-xs font-medium text-red-700 mb-1">风险因素：</p>
        <ul class="text-xs text-gray-600 space-y-0.5">
          <li v-for="(risk, idx) in holding.recovery_analysis.risk_factors.slice(0, 2)" :key="idx" class="flex items-start">
            <span class="text-red-500 mr-1">•</span>
            <span>{{ risk }}</span>
          </li>
        </ul>
      </div>
      <p class="text-xs text-gray-700 mt-2 font-medium">{{ holding.recovery_analysis.analysis || '暂无分析' }}</p>
    </div>

    <!-- 今日操作建议 -->
    <div class="mb-4 p-3 rounded" :class="actionColors[holding.today_action] || 'bg-blue-50'">
      <div class="flex items-center justify-between mb-1">
        <span class="text-xs font-medium text-gray-700">今日建议</span>
        <span :class="[
          'px-2 py-0.5 text-xs rounded font-medium',
          actionBadgeColors[holding.today_action] || 'bg-blue-100 text-blue-700'
        ]">
          {{ actionLabels[holding.today_action] || '持有' }}
        </span>
      </div>
      <p class="text-xs text-gray-600 mt-1">{{ holding.today_action_reason || '暂无建议' }}</p>
    </div>

    <!-- 操作按钮 -->
    <div class="flex items-center gap-2 pt-4 border-t">
      <Button size="sm" variant="secondary" @click="handleAddPosition">加仓</Button>
      <Button size="sm" variant="secondary" @click="handleReducePosition">减仓</Button>
      <Button size="sm" variant="secondary" @click="handleEdit">编辑</Button>
      <Button size="sm" variant="secondary" @click="handleDelete" class="!bg-red-500 !text-white hover:!bg-red-600">移出</Button>
    </div>

    <!-- 加仓/减仓对话框 -->
    <div v-if="showPositionDialog" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg p-6 max-w-md w-full mx-4">
        <h3 class="text-lg font-semibold mb-4">{{ positionDialogType === 'add' ? '加仓' : '减仓' }}</h3>
        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">价格</label>
            <input
              v-model.number="positionForm.price"
              type="number"
              step="0.01"
              class="w-full px-3 py-2 border border-gray-300 rounded-md"
              placeholder="输入价格"
            />
            <button
              @click="positionForm.price = holding.current_price"
              class="mt-1 text-xs text-blue-600 hover:text-blue-800"
            >
              使用当前价
            </button>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">数量</label>
            <input
              v-model.number="positionForm.quantity"
              type="number"
              step="100"
              class="w-full px-3 py-2 border border-gray-300 rounded-md"
              placeholder="输入数量（股）"
            />
          </div>
        </div>
        <div class="flex items-center gap-2 mt-6">
          <Button @click="handleConfirmPosition" :disabled="!positionForm.price || !positionForm.quantity">
            确认
          </Button>
          <Button variant="secondary" @click="showPositionDialog = false">取消</Button>
        </div>
      </div>
    </div>

    <!-- 编辑对话框 -->
    <div v-if="showEditDialog" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg p-6 max-w-md w-full mx-4">
        <h3 class="text-lg font-semibold mb-4">编辑持仓</h3>
        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">股票代码</label>
            <input
              v-model.trim="editForm.symbol"
              type="text"
              maxlength="10"
              class="w-full px-3 py-2 border border-gray-300 rounded-md font-mono"
              placeholder="如 002487 或 002487.SZ"
            />
            <p class="mt-1 text-xs text-gray-500">填错代码时可在此修改，如大金重工应为 002487</p>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">成本价</label>
            <input
              v-model.number="editForm.avg_cost_price"
              type="number"
              step="0.01"
              class="w-full px-3 py-2 border border-gray-300 rounded-md"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">持仓数量</label>
            <input
              v-model.number="editForm.total_quantity"
              type="number"
              step="100"
              class="w-full px-3 py-2 border border-gray-300 rounded-md"
            />
          </div>
        </div>
        <div class="flex items-center gap-2 mt-6">
          <Button @click="handleConfirmEdit">确认</Button>
          <Button variant="secondary" @click="showEditDialog = false">取消</Button>
        </div>
      </div>
    </div>
  </Card>
</template>

<script setup>
import { ref } from 'vue'
import Card from './Card.vue'
import Button from './Button.vue'

const props = defineProps({
  holding: {
    type: Object,
    required: true
  }
})

const emit = defineEmits(['update', 'delete'])

// 对话框状态
const showPositionDialog = ref(false)
const showEditDialog = ref(false)
const positionDialogType = ref('add') // 'add' | 'reduce'

// 表单数据
const positionForm = ref({
  price: null,
  quantity: null
})

const editForm = ref({
  symbol: props.holding.symbol || '',
  avg_cost_price: props.holding.avg_cost_price,
  total_quantity: props.holding.total_quantity
})

// 标签和颜色配置
const boardTypeLabels = {
  darwin: '长线·达尔文',
  swing: '波段',
  short: '短线',
  other: '其他'
}

const boardTypeColors = {
  darwin: 'bg-purple-100 text-purple-700',
  swing: 'bg-blue-100 text-blue-700',
  short: 'bg-yellow-100 text-yellow-700',
  other: 'bg-gray-100 text-gray-700'
}

const riskLevelLabels = {
  low: '低',
  medium: '中',
  high: '高'
}

const riskLevelColors = {
  low: 'bg-green-50',
  medium: 'bg-yellow-50',
  high: 'bg-red-50'
}

const riskLevelBadgeColors = {
  low: 'bg-green-100 text-green-700',
  medium: 'bg-yellow-100 text-yellow-700',
  high: 'bg-red-100 text-red-700'
}

const actionLabels = {
  buy: '买入',
  add: '加仓',
  hold: '持有',
  reduce: '减仓',
  close: '止损',
  skip: '跳过'
}

const actionColors = {
  buy: 'bg-green-50',
  add: 'bg-blue-50',
  hold: 'bg-gray-50',
  reduce: 'bg-yellow-50',
  close: 'bg-red-50',
  skip: 'bg-gray-50'
}

const actionBadgeColors = {
  buy: 'bg-green-100 text-green-700',
  add: 'bg-blue-100 text-blue-700',
  hold: 'bg-gray-100 text-gray-700',
  reduce: 'bg-yellow-100 text-yellow-700',
  close: 'bg-red-100 text-red-700',
  skip: 'bg-gray-100 text-gray-700'
}

const recoveryLevelLabels = {
  high: '高',
  medium: '中',
  low: '低',
  none: '无',
  unknown: '未知'
}

const recoveryLevelColors = {
  high: 'bg-green-50 border-green-300',
  medium: 'bg-yellow-50 border-yellow-300',
  low: 'bg-red-50 border-red-300',
  none: 'bg-gray-50 border-gray-200',
  unknown: 'bg-gray-50 border-gray-200'
}

const recoveryLevelBadgeColors = {
  high: 'bg-green-100 text-green-700',
  medium: 'bg-yellow-100 text-yellow-700',
  low: 'bg-red-100 text-red-700',
  none: 'bg-gray-100 text-gray-700',
  unknown: 'bg-gray-100 text-gray-700'
}

const recoveryLevelTextColors = {
  high: 'text-green-600',
  medium: 'text-yellow-600',
  low: 'text-red-600',
  none: 'text-gray-500',
  unknown: 'text-gray-500'
}

// 方法
const formatAmount = (amount) => {
  if (amount >= 100000000) {
    return `${(amount / 100000000).toFixed(2)}亿`
  } else if (amount >= 10000) {
    return `${(amount / 10000).toFixed(2)}万`
  }
  return amount.toFixed(2)
}

const formatQuantity = (quantity) => {
  if (quantity >= 10000) {
    return `${(quantity / 10000).toFixed(2)}万`
  }
  return quantity.toFixed(0)
}

const handleAddPosition = () => {
  positionDialogType.value = 'add'
  positionForm.value = {
    price: props.holding.current_price,
    quantity: null
  }
  showPositionDialog.value = true
}

const handleReducePosition = () => {
  positionDialogType.value = 'reduce'
  positionForm.value = {
    price: props.holding.current_price,
    quantity: null
  }
  showPositionDialog.value = true
}

const handleEdit = () => {
  editForm.value = {
    symbol: props.holding.symbol || '',
    avg_cost_price: props.holding.avg_cost_price,
    total_quantity: props.holding.total_quantity
  }
  showEditDialog.value = true
}

const handleDelete = async () => {
  if (!confirm('确定要移出操作池吗？')) {
    return
  }
  
  try {
    const response = await fetch(`/api/holdings/${props.holding.id}`, {
      method: 'DELETE'
    })
    const result = await response.json()
    
    if (result.success) {
      emit('delete')
    }
  } catch (error) {
    console.error('删除持仓失败:', error)
    alert('删除失败，请重试')
  }
}

const handleConfirmPosition = async () => {
  try {
    const opType = positionDialogType.value === 'add' ? 'buy' : 'sell'
    const response = await fetch(`/api/holdings/${props.holding.id}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        op_type: opType,
        price: positionForm.value.price,
        quantity: positionForm.value.quantity
      })
    })
    
    const result = await response.json()
    
    if (result.success) {
      showPositionDialog.value = false
      emit('update')
    } else {
      alert('操作失败，请重试')
    }
  } catch (error) {
    console.error('操作失败:', error)
    alert('操作失败，请重试')
  }
}

const handleConfirmEdit = async () => {
  try {
    const payload = {
      op_type: 'edit',
      price: editForm.value.avg_cost_price,
      quantity: editForm.value.total_quantity
    }
    if (editForm.value.symbol !== undefined && editForm.value.symbol !== null && String(editForm.value.symbol).trim() !== '') {
      payload.symbol = String(editForm.value.symbol).trim()
    }
    const response = await fetch(`/api/holdings/${props.holding.id}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    })
    
    const result = await response.json()
    
    if (result.success) {
      showEditDialog.value = false
      emit('update')
    } else {
      alert('编辑失败，请重试')
    }
  } catch (error) {
    console.error('编辑失败:', error)
    alert('编辑失败，请重试')
  }
}
</script>

