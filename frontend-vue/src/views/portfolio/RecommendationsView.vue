<template>
  <div class="p-8 space-y-8">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-semibold text-gray-900 mb-2">推荐选股</h1>
        <p class="text-sm text-gray-500">基于多维度策略的智能股票推荐</p>
      </div>
      <div class="flex items-center gap-2">
        <Button size="sm" variant="secondary" @click="handleRefresh" :disabled="loading">
          {{ loading ? '加载中...' : '刷新' }}
        </Button>
        <Button size="sm" variant="primary" @click="handleAiAnalysis" :disabled="analyzing">
          {{ analyzing ? '分析中...' : 'AI评分' }}
        </Button>
      </div>
    </div>

    <!-- 当前主线 -->
    <div class="rounded-lg border border-gray-200 bg-white shadow-sm overflow-hidden">
      <div class="px-4 py-3 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
        <h2 class="text-sm font-semibold text-gray-800">当前主线</h2>
        <button
          @click="fetchMainline"
          :disabled="mainlineLoading"
          class="text-xs text-blue-600 hover:underline disabled:opacity-50"
        >
          {{ mainlineLoading ? '加载中...' : '刷新' }}
        </button>
      </div>
      <div v-if="mainlineLoading && !mainlineData?.mainline?.length" class="p-6 text-center text-gray-500 text-sm">
        加载中...
      </div>
      <div v-else-if="mainlineError" class="p-6 text-center">
        <p class="text-red-600 text-sm">{{ mainlineError }}</p>
        <button @click="fetchMainline" class="mt-2 text-xs text-blue-600 hover:underline">重试</button>
      </div>
      <div v-else-if="!mainlineData?.mainline?.length" class="p-6 text-center text-gray-500 text-sm">
        <p>暂无主线数据，可能因数据更新中</p>
        <router-link to="/sector-board-leaders" class="mt-2 inline-block text-blue-600 hover:underline text-xs">
          查看板块领涨
        </router-link>
      </div>
      <div v-else class="p-4">
        <div class="flex flex-wrap gap-3">
          <router-link
            v-for="(m, idx) in mainlineData.mainline.slice(0, 5)"
            :key="m.sector_id || idx"
            :to="{ path: '/sector-board-leaders', query: { sector: m.sector_name } }"
            class="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-100 hover:bg-gray-200 text-sm transition-colors"
          >
            <span class="font-medium text-gray-900">{{ m.sector_name }}</span>
            <span
              v-if="m.signals?.momentum_5d != null"
              class="text-red-600 text-xs"
            >
              5日{{ m.signals.momentum_5d > 0 ? '+' : '' }}{{ m.signals.momentum_5d }}%
            </span>
            <span v-if="m.leader_stock" class="text-gray-500 text-xs">龙头: {{ m.leader_stock }}</span>
          </router-link>
        </div>
        <p class="mt-3 text-xs text-gray-400">
          基于近5日涨幅、龙头涨停数、成交额等综合计算。仅供参考，不构成投资建议。
        </p>
      </div>
    </div>

    <!-- 统计卡片 -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
      <StatCard
        label="达尔文评分"
        :value="darwinCount"
        :change="darwinChange"
        :icon="StarIcon"
      />
      <!-- 波段和短线暂时隐藏
      <StatCard
        label="波段股票"
        :value="swingCount"
        :change="swingChange"
        :icon="ChartBarIcon"
      />
      <StatCard
        label="短线股票"
        :value="shortCount"
        :change="shortChange"
        :icon="BoltIcon"
      />
      -->
      <div class="relative">
        <StatCard
          label="新高回踩"
          :value="newHighCount"
          :change="newHighChange"
          :icon="ArrowTrendingUpIcon"
        />
        <button 
          @click="handleRefreshNewHigh" 
          :disabled="refreshingNewHigh"
          class="absolute top-2 right-2 p-1.5 rounded-full hover:bg-gray-200 transition-colors disabled:opacity-50"
          :title="refreshingNewHigh ? '刷新中...' : '刷新新高回踩'"
        >
          <svg 
            class="w-4 h-4 text-gray-500" 
            :class="{ 'animate-spin': refreshingNewHigh }"
            fill="none" 
            stroke="currentColor" 
            viewBox="0 0 24 24"
          >
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
        </button>
      </div>
    </div>

    <!-- 瀑布流布局 -->
    <div class="space-y-8">
      <div v-if="loading" class="py-12 text-center text-gray-500">
        <p>加载中...</p>
      </div>

      <!-- 瀑布流：按分类显示 -->
      <div v-else class="space-y-12">
        <!-- 达尔文评分 -->
        <div>
          <div class="flex items-center justify-between mb-4">
            <h2 class="text-xl font-semibold text-gray-900 flex items-center gap-2">
              <span class="text-yellow-500">⭐</span>
              达尔文评分
              <span class="text-sm font-normal text-gray-500">({{ darwinCount }}只)</span>
            </h2>
          </div>
          <div v-if="darwinStocks.length > 0" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <StockCard
              v-for="(stock, index) in darwinStocks"
              :key="`darwin-${stock.code}-${index}`"
              :stock="stock"
              :strategy-type="'darwin'"
            />
          </div>
          <div v-else class="py-8 text-center text-gray-500">
            <p>暂无达尔文评分推荐</p>
          </div>
        </div>

        <!-- 波段股票和短线股票暂时隐藏 -->

        <!-- 新高回踩 -->
        <div>
          <div class="flex items-center justify-between mb-4">
            <h2 class="text-xl font-semibold text-gray-900 flex items-center gap-2">
              <span class="text-purple-500">📊</span>
              新高回踩
              <span class="text-sm font-normal text-gray-500">({{ newHighCount }}只)</span>
            </h2>
          </div>
          <div v-if="newHighStocks.length > 0" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <StockCard
              v-for="(stock, index) in newHighStocks"
              :key="`newhigh-${stock.code}-${index}`"
              :stock="stock"
              :strategy-type="'new_high'"
            />
          </div>
          <div v-else class="py-8 text-center text-gray-500">
            <p>暂无新高回踩推荐</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { StarIcon, ChartBarIcon, BoltIcon, ArrowTrendingUpIcon } from '@heroicons/vue/24/outline'
import { stockApi, formatStockData } from '../../api/stockApi'
import { dataCache, CACHE_KEYS } from '../../services/dataCache'
import Card from '../../components/ui/Card.vue'
import Button from '../../components/ui/Button.vue'
import StatCard from '../../components/ui/StatCard.vue'
import StockCard from '../../components/ui/StockCard.vue'

const darwinCount = ref(0)
const swingCount = ref(0)
const shortCount = ref(0)
const newHighCount = ref(0)
const loading = ref(false)
const analyzing = ref(false)
const refreshingNewHigh = ref(false)

// 当前主线
const mainlineLoading = ref(false)
const mainlineData = ref(null)
const mainlineError = ref('')

async function fetchMainline() {
  mainlineLoading.value = true
  mainlineError.value = ''
  try {
    const base = import.meta.env.VITE_API_BASE_URL || ''
    const resp = await fetch(`${base}/api/sector-rotation/current-mainline?top=5`)
    const json = await resp.json()
    if (json.success && json.data) {
      mainlineData.value = json.data
    } else {
      mainlineData.value = { mainline: [] }
    }
  } catch (e) {
    mainlineError.value = e.message || '获取主线失败'
    mainlineData.value = null
  } finally {
    mainlineLoading.value = false
  }
}

// 变化百分比
const darwinChange = ref(undefined)
const swingChange = ref(undefined)
const shortChange = ref(undefined)
const newHighChange = ref(undefined)

// 存储原始数据
const darwinStocks = ref([])
const swingStocks = ref([])
const shortStocks = ref([])
const newHighStocks = ref([])

// 获取数据
const fetchData = async (forceRefresh = false) => {
  loading.value = true
  try {
    // 检查缓存
    if (!forceRefresh) {
      const cached = dataCache.get(CACHE_KEYS.RECOMMENDATIONS)
      if (cached && cached.data) {
        console.log('📦 使用缓存的推荐选股数据')
        // 从缓存中筛选：只显示建议买入的达尔文股票
        const darwinCached = (cached.data.darwin || []).filter(stock => {
          const advice = stock.advice || stock.operationAdvice || stock.operation_advice || ''
          return advice === '买入'
        })
        darwinStocks.value = darwinCached.map(formatStockData)
        swingStocks.value = (cached.data.swing || []).map(formatStockData)
        shortStocks.value = (cached.data.short || []).map(formatStockData)
        newHighStocks.value = (cached.data.new_high || []).map(formatStockData)
        
        darwinCount.value = darwinStocks.value.length
        swingCount.value = swingStocks.value.length
        shortCount.value = shortStocks.value.length
        newHighCount.value = newHighStocks.value.length
        
        loading.value = false
        return
      }
    }
    
    // 并行获取所有数据（添加错误处理）
    // 达尔文数据从缓存获取（由dataPreloader预加载），不再单独请求
    const cachedDarwin = dataCache.get(CACHE_KEYS.DARWIN_STOCKS) || []
    
    const [swingData, shortData, newHighData] = await Promise.allSettled([
      stockApi.getSwingStocks(50).catch(() => []),
      stockApi.getShortStocks(50).catch(() => []),
      stockApi.getNewHighStocks(500).catch(() => []),  // 新高回踩取500只
    ]).then(results => results.map(r => r.status === 'fulfilled' ? (r.value || []) : []))
    
    const darwinData = cachedDarwin

    // 达尔文筛选：只显示建议买入的股票，按评分排序，取前10只
    // 与 React 版本保持一致：严格等于 '买入'
    const darwinFiltered = darwinData
      .filter(stock => {
        const advice = stock.advice || stock.operationAdvice || stock.operation_advice || ''
        return advice === '买入'
      })
      .sort((a, b) => {
        const scoreA = a.darwinScore || a.darwin_score || a.finalScore || a.final_score || 0
        const scoreB = b.darwinScore || b.darwin_score || b.finalScore || b.final_score || 0
        return scoreB - scoreA
      })
      .slice(0, 10)

    darwinStocks.value = darwinFiltered.map(formatStockData)
    swingStocks.value = swingData.map(formatStockData)
    shortStocks.value = shortData.map(formatStockData)
    newHighStocks.value = newHighData.map(formatStockData)

    darwinCount.value = darwinStocks.value.length
    swingCount.value = swingStocks.value.length
    shortCount.value = shortStocks.value.length
    newHighCount.value = newHighStocks.value.length

    // 计算变化百分比（相对于上一次统计）
    const lastStats = JSON.parse(localStorage.getItem('lastStats') || '{}')
    
    if (lastStats.darwin && lastStats.darwin > 0) {
      darwinChange.value = ((darwinCount.value - lastStats.darwin) / lastStats.darwin) * 100
    } else {
      darwinChange.value = undefined
    }

    if (lastStats.swing && lastStats.swing > 0) {
      swingChange.value = ((swingCount.value - lastStats.swing) / lastStats.swing) * 100
    } else {
      swingChange.value = undefined
    }

    if (lastStats.short && lastStats.short > 0) {
      shortChange.value = ((shortCount.value - lastStats.short) / lastStats.short) * 100
    } else {
      shortChange.value = undefined
    }

    // 保存当前统计
    localStorage.setItem('lastStats', JSON.stringify({
      darwin: darwinCount.value,
      swing: swingCount.value,
      short: shortCount.value,
      timestamp: Date.now()
    }))
    
    // 更新缓存
    dataCache.set(CACHE_KEYS.RECOMMENDATIONS, {
      darwin: darwinFiltered,
      swing: swingData,
      short: shortData
    })
  } catch (error) {
    console.error('获取数据失败:', error)
  } finally {
    loading.value = false
  }
}

// 处理股票点击
const handleStockClick = (stock) => {
  console.log('点击股票:', stock)
}

// 刷新数据
const handleRefresh = () => {
  fetchData(true) // 强制刷新
}

// 刷新新高回踩（重新计算）
const handleRefreshNewHigh = async () => {
  refreshingNewHigh.value = true
  try {
    // 调用后端API强制重新计算新高回踩
    const response = await fetch('/api/recommendations?type=new_high&force_refresh=true&limit=500')
    const data = await response.json()
    
    const items = data.data?.new_high || []
    console.log('📊 新高回踩数据:', items.length, items.slice(0, 3))
    newHighStocks.value = items.map(stock => ({
      code: stock.code || stock.ts_code?.split('.')[0],
      name: stock.name || '',
      lastPrice: stock.lastPrice || stock.currentPrice || stock.close || 0,
      changePct: stock.changePct || stock.change_pct || 0,
      turnoverRate: stock.turnoverRate || stock.turnover_rate || 0,
      amount: stock.amount || 0,
      type: 'new_high',
      reason: stock.reason || '新高回踩策略',
    }))
    newHighChange.value = items.length
    
    alert(`新高回踩刷新成功: ${newHighStocks.value.length} 只股票`)
  } catch (error) {
    console.error('刷新新高回踩失败:', error)
    alert('刷新新高回踩失败: ' + error.message)
  } finally {
    refreshingNewHigh.value = false
  }
}

// 保存AI评分到localStorage
const saveAiScores = () => {
  const allStocks = [...darwinStocks.value, ...swingStocks.value, ...shortStocks.value]
  const aiScores = {}
  allStocks.forEach(stock => {
    if (stock.code && (stock.aiScore || stock.deepseekScore || stock.aiAnalysis || stock.deepseekAnalysis)) {
      aiScores[stock.code] = {
        aiScore: stock.aiScore,
        deepseekScore: stock.deepseekScore,
        aiAnalysis: stock.aiAnalysis,
        deepseekAnalysis: stock.deepseekAnalysis,
        timestamp: Date.now()
      }
    }
  })
  localStorage.setItem('aiScores', JSON.stringify(aiScores))
}

// 从localStorage加载AI评分
const loadAiScores = () => {
  try {
    const saved = localStorage.getItem('aiScores')
    if (saved) {
      const aiScores = JSON.parse(saved)
      const updateStocksWithSaved = (stocks) => {
        return stocks.map(stock => {
          if (stock.code && aiScores[stock.code]) {
            const saved = aiScores[stock.code]
            // 如果保存的数据超过7天，则不使用
            if (Date.now() - saved.timestamp < 7 * 24 * 60 * 60 * 1000) {
              return {
                ...stock,
                aiScore: saved.aiScore,
                deepseekScore: saved.deepseekScore,
                aiAnalysis: saved.aiAnalysis,
                deepseekAnalysis: saved.deepseekAnalysis,
              }
            }
          }
          return stock
        })
      }
      darwinStocks.value = updateStocksWithSaved(darwinStocks.value)
      swingStocks.value = updateStocksWithSaved(swingStocks.value)
      shortStocks.value = updateStocksWithSaved(shortStocks.value)
    }
  } catch (error) {
    console.error('加载AI评分失败:', error)
  }
}

// 测试AI连接
const testAiConnection = async () => {
  try {
    const response = await fetch('/api/ai-test')
    const result = await response.json()
    if (result.success) {
      const messages = []
      if (result.openai.enabled) {
        messages.push(`OpenAI: ${result.openai.message}`)
      }
      if (result.deepseek.enabled) {
        messages.push(`Deepseek: ${result.deepseek.message}`)
      }
      if (messages.length === 0) {
        alert('⚠️ AI服务未启用，请在配置中启用')
      } else {
        alert(messages.join('\n'))
      }
    } else {
      alert(`❌ 测试失败: ${result.error}`)
    }
  } catch (error) {
    console.error('测试AI连接失败:', error)
    alert('测试AI连接失败')
  }
}

// AI分析（流式返回）
const handleAiAnalysis = async () => {
  analyzing.value = true
  
  // 先测试连接（不阻塞）
  testAiConnection().catch(err => {
    console.warn('AI连接测试失败:', err)
  })
  try {
    // 获取所有股票的代码
    const allStocks = [...darwinStocks.value, ...swingStocks.value, ...shortStocks.value]
    const stockCodes = allStocks.map(s => s.code).filter(Boolean)
    
    if (stockCodes.length === 0) {
      alert('没有股票需要分析')
      analyzing.value = false
      return
    }

    // 调用AI分析API（流式返回）
    const API_BASE_URL = '' // 使用相对路径，通过Vite代理转发
    const response = await fetch(`${API_BASE_URL}/api/ai-analysis`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(stockCodes),
    })

    if (!response.ok) {
      throw new Error(`AI分析失败: ${response.status}`)
    }

    // 检查响应类型
    const contentType = response.headers.get('content-type')
    console.log('📡 响应Content-Type:', contentType)
    
    if (!contentType || !contentType.includes('text/event-stream')) {
      console.warn('⚠️ 响应不是流式格式，尝试按JSON解析')
      const result = await response.json()
      console.log('📦 JSON响应:', result)
      
      if (result.success && result.data) {
        // 兼容非流式返回
        const updateStocksWithAi = (stocks) => {
          return stocks.map(stock => {
            const analyzedStock = result.data.find(s => {
              const sCode = s.代码 || s.code || s.股票代码 || ''
              const stockCode = stock.code || ''
              const cleanSCode = String(sCode).replace(/^(sh|sz|bj)/i, '').trim()
              const cleanStockCode = String(stockCode).replace(/^(sh|sz|bj)/i, '').trim()
              return cleanSCode === cleanStockCode || sCode === stockCode
            })
            
            if (analyzedStock) {
              return {
                ...stock,
                aiScore: analyzedStock.AI评分 || analyzedStock.aiScore || analyzedStock['AI评分'],
                deepseekScore: analyzedStock.Deepseek评分 || analyzedStock.deepseekScore || analyzedStock['Deepseek评分'],
                aiAnalysis: analyzedStock.AI分析 || analyzedStock.aiAnalysis || analyzedStock['AI分析'],
                deepseekAnalysis: analyzedStock.Deepseek分析 || analyzedStock.deepseekAnalysis || analyzedStock['Deepseek分析'],
              }
            }
            return stock
          })
        }
        
        darwinStocks.value = updateStocksWithAi(darwinStocks.value)
        swingStocks.value = updateStocksWithAi(swingStocks.value)
        shortStocks.value = updateStocksWithAi(shortStocks.value)
        saveAiScores()
        alert(`✅ AI分析完成，共分析 ${result.count || result.data.length} 只股票`)
        return
      }
    }

    // 处理流式返回
    if (!response.body) {
      throw new Error('响应体为空')
    }
    
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let processedCount = 0

    const updateStocksWithAi = (stocks, analyzedStock) => {
      return stocks.map(stock => {
        // 尝试多种方式匹配股票代码
        const sCode = analyzedStock.代码 || analyzedStock.code || analyzedStock.股票代码 || ''
        const stockCode = stock.code || ''
        // 清理代码格式（去除sh/sz/bj前缀）
        const cleanSCode = String(sCode).replace(/^(sh|sz|bj)/i, '').trim()
        const cleanStockCode = String(stockCode).replace(/^(sh|sz|bj)/i, '').trim()
        
        if (cleanSCode === cleanStockCode || sCode === stockCode) {
          return {
            ...stock,
            aiScore: analyzedStock.AI评分 || analyzedStock.aiScore || analyzedStock['AI评分'],
            deepseekScore: analyzedStock.Deepseek评分 || analyzedStock.deepseekScore || analyzedStock['Deepseek评分'],
            aiAnalysis: analyzedStock.AI分析 || analyzedStock.aiAnalysis || analyzedStock['AI分析'],
            deepseekAnalysis: analyzedStock.Deepseek分析 || analyzedStock.deepseekAnalysis || analyzedStock['Deepseek分析'],
          }
        }
        return stock
      })
    }

    console.log('🔄 开始读取流式数据...')
    while (true) {
      const { done, value } = await reader.read()
      
      if (done) {
        console.log('✅ 流式数据读取完成')
        break
      }

      const chunk = decoder.decode(value, { stream: true })
      console.log('📦 收到数据块:', chunk.substring(0, 200))
      
      buffer += chunk
      const lines = buffer.split('\n')
      buffer = lines.pop() || '' // 保留最后一个不完整的行

      for (const line of lines) {
        const trimmedLine = line.trim()
        if (!trimmedLine) continue
        
        console.log('📝 处理行:', trimmedLine.substring(0, 100))
        
        if (trimmedLine.startsWith('data: ')) {
          try {
            const jsonStr = trimmedLine.slice(6)
            console.log('🔍 JSON字符串:', jsonStr.substring(0, 200))
            const data = JSON.parse(jsonStr)
            console.log('✅ 解析成功:', data.type, data.index || data.count)
            
            if (data.type === 'stock') {
              // 逐条更新股票数据
              darwinStocks.value = updateStocksWithAi(darwinStocks.value, data.data)
              swingStocks.value = updateStocksWithAi(swingStocks.value, data.data)
              shortStocks.value = updateStocksWithAi(shortStocks.value, data.data)
              
              processedCount++
              console.log(`✅ 已分析 ${processedCount}/${data.total}: ${data.data.代码 || data.data.code}`)
            } else if (data.type === 'complete') {
              // 保存到localStorage
              saveAiScores()
              console.log(`✅ AI分析完成，共分析 ${data.count} 只股票`)
              alert(`✅ AI分析完成，共分析 ${data.count} 只股票`)
            } else if (data.type === 'error') {
              console.error('AI分析错误:', data.message)
              alert(`❌ AI分析错误: ${data.message}`)
            }
          } catch (e) {
            console.error('❌ 解析流数据失败:', e, '行内容:', trimmedLine.substring(0, 200))
          }
        } else {
          console.log('⚠️ 跳过非data行:', trimmedLine.substring(0, 50))
        }
      }
    }
  } catch (error) {
    console.error('AI分析失败:', error)
    alert('AI分析失败，请稍后重试')
  } finally {
    analyzing.value = false
  }
}

// 监听全局刷新事件
const handleGlobalRefresh = () => {
  fetchData(true)
}

onMounted(() => {
  fetchMainline()
  // 先尝试使用缓存，如果没有缓存再加载
  fetchData(false).then(() => {
    // 数据加载完成后，加载保存的AI评分
    loadAiScores()
  })
  window.addEventListener('global-refresh', handleGlobalRefresh)
})

onUnmounted(() => {
  window.removeEventListener('global-refresh', handleGlobalRefresh)
})
</script>

