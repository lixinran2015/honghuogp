<template>
  <div class="p-4 lg:p-6 bg-warm-50 min-h-screen">
    <!-- 标题区 -->
    <div class="mb-6 flex items-center justify-between flex-wrap gap-3">
      <div>
        <h1 class="text-xl font-bold text-warmgray-900">长线跟踪池</h1>
        <p class="text-sm text-warmgray-500 mt-1">
          记录候选标的，定期检查是否还符合长期持有逻辑
        </p>
      </div>
      <div class="flex items-center gap-2">
        <select
          v-model="statusFilter"
          class="px-3 py-1.5 text-sm border border-border rounded-md bg-white text-warmgray-700 focus:outline-none focus:ring-1 focus:ring-cta"
          @change="fetchData"
        >
          <option value="">全部</option>
          <option value="watching">观察中</option>
          <option value="promoted">已买入</option>
          <option value="dropped">已剔除</option>
        </select>
        <button
          @click="runCheck"
          :disabled="checking"
          class="px-4 py-1.5 bg-cta text-white text-sm font-medium rounded-md hover:bg-cta/90 disabled:opacity-50 transition-colors"
        >
          {{ checking ? '检查中...' : '执行检查' }}
        </button>
        <button
          @click="fetchData"
          :disabled="loading"
          class="px-4 py-1.5 border border-border text-warmgray-700 text-sm font-medium rounded-md hover:bg-warm-100 transition-colors"
        >
          {{ loading ? '加载中...' : '刷新' }}
        </button>
      </div>
    </div>

    <!-- 检查结果摘要 -->
    <div v-if="checkSummary" class="mb-4 bg-white rounded-lg border border-border p-4">
      <div class="flex items-center gap-4 flex-wrap">
        <div class="text-sm">
          <span class="text-warmgray-500">检查日期：</span>
          <span class="font-medium">{{ checkSummary.check_date || '-' }}</span>
        </div>
        <div class="text-sm">
          <span class="text-warmgray-500">总计：</span>
          <span class="font-medium">{{ checkSummary.total }}</span>
        </div>
        <div class="text-sm">
          <span class="text-warmgray-500">健康：</span>
          <span class="font-medium text-profit">{{ checkSummary.healthy_count }}</span>
        </div>
        <div class="text-sm">
          <span class="text-warmgray-500">异常：</span>
          <span class="font-medium text-loss">{{ checkSummary.unhealthy_count }}</span>
        </div>
      </div>
      <!-- 异常列表 -->
      <div v-if="checkSummary.unhealthy_results && checkSummary.unhealthy_results.length" class="mt-3 space-y-2">
        <div v-for="r in checkSummary.unhealthy_results" :key="r.ts_code" class="text-sm bg-loss/5 rounded p-2">
          <span class="font-medium">{{ r.name }} ({{ r.ts_code }})</span>
          <span class="text-loss ml-2">{{ r.drop_reason }}</span>
        </div>
      </div>
    </div>

    <!-- 跟踪池列表 -->
    <div class="bg-white rounded-lg border border-border overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="bg-warmgray-50 border-b border-border">
              <th class="px-4 py-3 text-left font-semibold text-warmgray-700">股票</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">状态</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">综合评分</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">入选价</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">入选成交额</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">检查结果</th>
              <th class="px-4 py-3 text-left font-semibold text-warmgray-700">剔除理由</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="stock in stocks"
              :key="stock.ts_code"
              class="border-b border-border hover:bg-warm-50 transition-colors"
              :class="{ 'bg-loss/5': stock.drop_reason }"
            >
              <td class="px-4 py-3">
                <div class="font-medium text-warmgray-900">{{ stock.name }}</div>
                <div class="text-xs text-warmgray-500">{{ stock.ts_code }}</div>
                <div class="text-xs text-warmgray-400">{{ stock.industry }} · {{ stock.sector_type }}</div>
              </td>
              <td class="px-4 py-3 text-center">
                <span
                  class="inline-block px-2 py-0.5 rounded text-xs font-medium"
                  :class="statusClass(stock.status)"
                >
                  {{ statusText(stock.status) }}
                </span>
              </td>
              <td class="px-4 py-3 text-center">
                <span class="font-bold text-cta">{{ stock.composite_score }}</span>
              </td>
              <td class="px-4 py-3 text-center text-warmgray-700">
                {{ stock.close_price != null ? stock.close_price.toFixed(2) : '-' }}
              </td>
              <td class="px-4 py-3 text-center text-warmgray-700">
                {{ stock.amount != null ? (stock.amount / 1e5).toFixed(1) + '亿' : '-' }}
              </td>
              <td class="px-4 py-3 text-center">
                <div v-if="stock.check_result">
                  <span
                    class="inline-block px-2 py-0.5 rounded text-xs font-medium"
                    :class="stock.check_result.is_healthy ? 'bg-profit/10 text-profit' : 'bg-loss/10 text-loss'"
                  >
                    {{ stock.check_result.is_healthy ? '健康' : '异常' }}
                  </span>
                  <div v-if="stock.check_result.warnings && stock.check_result.warnings.length" class="mt-1 text-xs text-warmgray-500">
                    {{ stock.check_result.warnings.join('；') }}
                  </div>
                </div>
                <span v-else class="text-xs text-warmgray-400">未检查</span>
              </td>
              <td class="px-4 py-3 text-left">
                <div v-if="stock.drop_reason" class="text-xs text-loss">{{ stock.drop_reason }}</div>
                <div v-else-if="stock.note" class="text-xs text-warmgray-500">{{ stock.note }}</div>
                <span v-else class="text-xs text-warmgray-400">-</span>
              </td>
              <td class="px-4 py-3 text-center">
                <div class="flex items-center gap-1 justify-center">
                  <button
                    v-if="stock.status === 'watching'"
                    @click="buyStock(stock)"
                    class="px-2 py-1 text-xs bg-profit/10 text-profit rounded hover:bg-profit/20 transition-colors"
                  >
                    标记买入
                  </button>
                  <button
                    v-if="stock.status === 'watching'"
                    @click="dropStock(stock.ts_code)"
                    class="px-2 py-1 text-xs bg-loss/10 text-loss rounded hover:bg-loss/20 transition-colors"
                  >
                    剔除
                  </button>
                  <button
                    @click="editNote(stock)"
                    class="px-2 py-1 text-xs bg-warm-100 text-warmgray-600 rounded hover:bg-warm-200 transition-colors"
                  >
                    备注
                  </button>
                  <button
                    @click="deleteStock(stock.ts_code)"
                    class="px-2 py-1 text-xs bg-warm-100 text-warmgray-400 rounded hover:bg-loss/10 hover:text-loss transition-colors"
                  >
                    删除
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="stocks.length === 0 && !loading">
              <td colspan="8" class="px-4 py-8 text-center text-warmgray-500">
                跟踪池为空，请从四步精选页面添加标的
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

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

const loading = ref(false)
const checking = ref(false)
const stocks = ref([])
const statusFilter = ref('')
const checkSummary = ref(null)

async function fetchData() {
  loading.value = true
  try {
    const params = new URLSearchParams()
    if (statusFilter.value) {
      params.append('status', statusFilter.value)
    }
    const response = await fetch(`${API_BASE_URL}/api/long-term/tracking-pool?${params}`)
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    const result = await response.json()
    if (result.success) {
      stocks.value = result.data || []
    } else {
      stocks.value = []
    }
  } catch (e) {
    console.error('获取跟踪池失败:', e)
    stocks.value = []
  } finally {
    loading.value = false
  }
}

async function runCheck() {
  checking.value = true
  try {
    const response = await fetch(`${API_BASE_URL}/api/long-term/tracking-pool/check`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    })
    const result = await response.json()
    if (result.success) {
      checkSummary.value = {
        check_date: result.data.results[0]?.check_date,
        total: result.data.total,
        healthy_count: result.data.healthy_count,
        unhealthy_count: result.data.unhealthy_count,
        unhealthy_results: result.data.results.filter(r => !r.is_healthy),
      }
      await fetchData()
    }
  } catch (e) {
    console.error('执行检查失败:', e)
    alert('检查失败')
  } finally {
    checking.value = false
  }
}

async function buyStock(stock) {
  const priceStr = prompt(`买入 ${stock.name} (${stock.ts_code})，请输入买入价格：`, stock.close_price || '')
  if (priceStr === null || priceStr === '') return
  const price = parseFloat(priceStr)
  if (isNaN(price) || price <= 0) {
    alert('请输入有效的价格')
    return
  }

  const sharesStr = prompt('请输入买入股数：', '100')
  if (sharesStr === null || sharesStr === '') return
  const shares = parseInt(sharesStr)
  if (isNaN(shares) || shares <= 0) {
    alert('请输入有效的股数')
    return
  }

  try {
    // 1. 创建持仓记录
    const buyResponse = await fetch(`${API_BASE_URL}/api/long-term/portfolio/buy`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ts_code: stock.ts_code,
        name: stock.name,
        industry: stock.industry,
        price: price,
        shares: shares,
        darwin_score: stock.darwin_score,
        reason: '从跟踪池买入',
      }),
    })
    const buyResult = await buyResponse.json()
    if (!buyResult.success) {
      alert(buyResult.message || '买入失败')
      return
    }

    // 2. 更新跟踪池状态为 promoted
    const response = await fetch(`${API_BASE_URL}/api/long-term/tracking-pool/${stock.ts_code}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: 'promoted' }),
    })
    const result = await response.json()
    if (result.success) {
      alert(`买入成功：${stock.name} ${shares}股 @ ${price}`)
      await fetchData()
    }
  } catch (e) {
    console.error('买入失败:', e)
    alert('买入失败')
  }
}

async function updateStatus(ts_code, status) {
  try {
    const response = await fetch(`${API_BASE_URL}/api/long-term/tracking-pool/${ts_code}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    })
    const result = await response.json()
    if (result.success) {
      await fetchData()
    }
  } catch (e) {
    console.error('更新状态失败:', e)
  }
}

async function dropStock(ts_code) {
  const reason = prompt('请输入剔除理由：')
  if (reason === null) return
  try {
    const response = await fetch(`${API_BASE_URL}/api/long-term/tracking-pool/${ts_code}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: 'dropped', drop_reason: reason || '' }),
    })
    const result = await response.json()
    if (result.success) {
      await fetchData()
    }
  } catch (e) {
    console.error('剔除失败:', e)
  }
}

async function editNote(stock) {
  const note = prompt('备注：', stock.note || '')
  if (note === null) return
  try {
    const response = await fetch(`${API_BASE_URL}/api/long-term/tracking-pool/${stock.ts_code}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ note }),
    })
    const result = await response.json()
    if (result.success) {
      await fetchData()
    }
  } catch (e) {
    console.error('更新备注失败:', e)
  }
}

async function deleteStock(ts_code) {
  if (!confirm('确定删除这只股票？')) return
  try {
    const response = await fetch(`${API_BASE_URL}/api/long-term/tracking-pool/${ts_code}`, {
      method: 'DELETE',
    })
    const result = await response.json()
    if (result.success) {
      await fetchData()
    }
  } catch (e) {
    console.error('删除失败:', e)
  }
}

function statusClass(status) {
  const map = {
    watching: 'bg-cta/10 text-cta',
    promoted: 'bg-profit/10 text-profit',
    dropped: 'bg-loss/10 text-loss',
  }
  return map[status] || 'bg-warm-100 text-warmgray-600'
}

function statusText(status) {
  const map = {
    watching: '观察中',
    promoted: '已买入',
    dropped: '已剔除',
  }
  return map[status] || status
}

onMounted(() => {
  fetchData()
})
</script>
