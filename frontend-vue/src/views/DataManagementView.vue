<template>
  <div class="p-8 space-y-8">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-semibold text-gray-900 mb-2">数据管理</h1>
        <p class="text-sm text-gray-500">监控数据源健康状态和数据质量</p>
      </div>
      <div class="flex gap-2">
        <Button 
          size="sm" 
          variant="primary" 
          @click="handleFillMissingDaily" 
          :disabled="fillingMissingDaily"
          class="bg-emerald-600 hover:bg-emerald-700 text-white"
          title="先查库最新日线日期，再补近5日内、今天之前的缺失日线"
        >
          {{ fillingMissingDaily ? '补充中...' : '补缺失日线' }}
        </Button>
        <Button 
          size="sm" 
          variant="primary" 
          @click="handleUpdateMissing" 
          :disabled="updatingMissing"
          class="bg-blue-600 hover:bg-blue-700 text-white"
        >
          {{ updatingMissing ? '更新中...' : '增量更新' }}
        </Button>
        <Button size="sm" variant="secondary" @click="handleRefresh" :disabled="loading">
          {{ loading ? '加载中...' : '刷新' }}
        </Button>
      </div>
    </div>

    <!-- 缺失数据提示 -->
    <div v-if="missingDates.length > 0" class="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
      <div class="flex items-center justify-between">
        <div>
          <p class="text-sm font-medium text-yellow-800">
            ⚠️ 检测到 {{ missingDates.length }} 个交易日数据缺失
          </p>
          <p class="text-xs text-yellow-600 mt-1">
            缺失日期: {{ missingDates.join(', ') }}
          </p>
        </div>
        <Button 
          size="sm" 
          @click="handleUpdateMissing" 
          :disabled="updatingMissing"
          class="bg-yellow-600 hover:bg-yellow-700 text-white"
        >
          {{ updatingMissing ? '更新中...' : '立即更新' }}
        </Button>
      </div>
    </div>

    <!-- 数据源健康状态 -->
    <div>
      <h2 class="text-lg font-semibold text-gray-900 mb-4">数据源健康状态</h2>
      <div class="grid grid-cols-4 gap-3">
        <Card
          v-for="(source, key) in dataSourceHealth.sources"
          :key="key"
          class="p-3"
        >
          <div class="flex items-center justify-between mb-1">
            <h3 class="text-sm font-medium text-gray-900">{{ source.name }}</h3>
            <span
              :class="[
                'px-2 py-0.5 text-xs rounded font-medium',
                source.available
                  ? 'bg-green-100 text-green-700'
                  : 'bg-red-100 text-red-700'
              ]"
            >
              {{ source.available ? '可用' : '不可用' }}
            </span>
          </div>
          <p class="text-xs text-gray-500">类型: {{ source.type }}</p>
          <p v-if="source.latest_date" class="text-xs text-gray-500 mt-0.5">
            最新: {{ source.latest_date }}
          </p>
          <p v-if="source.error" class="text-xs text-red-600 mt-1 line-clamp-2">
            {{ source.error }}
          </p>
        </Card>
      </div>
      <p class="text-xs text-gray-500 mt-2">
        检查时间: {{ dataSourceHealth.check_time ? new Date(dataSourceHealth.check_time).toLocaleString('zh-CN') : '--' }}
      </p>
    </div>

    <!-- 数据质量指标 -->
    <div>
      <h2 class="text-lg font-semibold text-gray-900 mb-4">数据质量指标</h2>
      
      <!-- 股票池统计（第一行，用色块区分） -->
      <div class="grid grid-cols-2 md:grid-cols-6 gap-3 mb-6">
        <Card class="p-4 bg-blue-50 border-blue-200">
          <div class="text-xs text-gray-600 mb-1">总股票数</div>
          <div class="text-2xl font-bold text-blue-700">{{ totalStocksCount }}</div>
        </Card>
        <Card class="p-4 bg-gray-50 border-gray-300">
          <div class="flex items-center justify-between mb-1">
            <div class="text-xs text-gray-600">主板池</div>
            <button 
              @click="handleRefreshMainboard" 
              :disabled="refreshingMainboard"
              class="text-xs px-2 py-0.5 bg-gray-200 hover:bg-gray-300 text-gray-700 rounded disabled:opacity-50"
            >
              {{ refreshingMainboard ? '刷新中...' : '刷新' }}
            </button>
          </div>
          <div class="text-2xl font-bold text-gray-700">{{ dataQuality.universe_stats?.mainboard || 0 }}</div>
          <div class="text-xs text-gray-400 mt-1">仅主板</div>
        </Card>
        <Card class="p-4 bg-slate-50 border-slate-200">
          <div class="flex items-center justify-between mb-1">
            <div class="text-xs text-gray-600">基础池</div>
            <button 
              @click="handleRefreshBaseUniverse" 
              :disabled="refreshingBase"
              class="text-xs px-2 py-0.5 bg-slate-200 hover:bg-slate-300 text-slate-600 rounded disabled:opacity-50"
            >
              {{ refreshingBase ? '刷新中...' : '刷新' }}
            </button>
          </div>
          <div class="text-2xl font-bold text-slate-700">{{ dataQuality.universe_stats?.base || 0 }}</div>
        </Card>
        <Card class="p-4 bg-green-50 border-green-200">
          <div class="flex items-center justify-between mb-1">
            <div class="text-xs text-gray-600">S1 <span class="text-gray-400">(新高策略)</span></div>
            <button 
              @click="handleRefreshS1Universe" 
              :disabled="refreshingS1"
              class="text-xs px-2 py-0.5 bg-green-200 hover:bg-green-300 text-green-700 rounded disabled:opacity-50"
            >
              {{ refreshingS1 ? '刷新中...' : '刷新' }}
            </button>
          </div>
          <div class="text-2xl font-bold text-green-700">{{ dataQuality.universe_stats?.s1 || 0 }}</div>
          <div class="text-xs text-gray-400 mt-2 border-t border-green-200 pt-2">
            ✓ 股价 ≥ 10元<br>
            ✓ 成交额 ≥ 2亿<br>
            ✓ 距30日高点 ≤ 5%
          </div>
          <div class="mt-2">
            <button 
              @click="handleDownloadS1Stocks" 
              :disabled="downloadingS1"
              class="text-xs px-2 py-0.5 bg-green-300 hover:bg-green-400 text-green-800 rounded disabled:opacity-50 w-full"
            >
              {{ downloadingS1 ? '下载中...' : '下载' }}
            </button>
          </div>
        </Card>
        <Card class="p-4 bg-yellow-50 border-yellow-200">
          <div class="flex items-center justify-between mb-1">
            <div class="text-xs text-gray-600">S2 <span class="text-gray-400">(二次新高备选)</span></div>
            <button 
              @click="handleRefreshS2Universe" 
              :disabled="refreshingS2"
              class="text-xs px-2 py-0.5 bg-yellow-200 hover:bg-yellow-300 text-yellow-700 rounded disabled:opacity-50"
            >
              {{ refreshingS2 ? '刷新中...' : '刷新' }}
            </button>
          </div>
          <div class="text-2xl font-bold text-yellow-700">{{ dataQuality.universe_stats?.s2 || 0 }}</div>
          <div class="text-xs text-gray-400 mt-2 border-t border-yellow-200 pt-2">
            ✓ 曾进入S1池<br>
            ✓ 回踩10%-25%<br>
            ✓ 站上10日线
          </div>
        </Card>
        <!-- 30日新高策略（移到这里） -->
        <Card class="p-4 bg-purple-50 border-purple-200">
          <div class="flex items-center justify-between mb-1">
            <div class="text-xs text-gray-600">30日新高</div>
            <button 
              @click="handleRefreshNewHighStrategy" 
              :disabled="refreshingNewHigh || !dataQuality.data_dimensions?.new_high_strategy"
              class="text-xs px-2 py-0.5 bg-purple-200 hover:bg-purple-300 text-purple-700 rounded disabled:opacity-50"
            >
              {{ refreshingNewHigh ? '刷新中...' : '刷新' }}
            </button>
          </div>
          <div class="text-2xl font-bold text-purple-700">
            {{ dataQuality.data_dimensions?.new_high_strategy?.valid_count || 0 }}
          </div>
          <div class="text-xs text-gray-400 mt-2 border-t border-purple-200 pt-2">
            ✓ 今日收盘>前30日<br>
            ✓ 180日涨幅≤300%<br>
            ✓ 成交额>2亿
          </div>
          <div class="mt-2">
            <button 
              @click="handleAddNewHighToWatchlist" 
              :disabled="addingToWatchlist || !dataQuality.data_dimensions?.new_high_strategy || (dataQuality.data_dimensions.new_high_strategy.valid_count || 0) === 0"
              class="text-xs px-2 py-0.5 bg-purple-300 hover:bg-purple-400 text-purple-800 rounded disabled:opacity-50 w-full"
            >
              {{ addingToWatchlist ? '添加中...' : '加入跟踪池' }}
            </button>
          </div>
        </Card>
        <!-- 180日高点策略（主板强势股） -->
        <Card class="p-4 bg-indigo-50 border-indigo-200">
          <div class="flex items-center justify-between mb-1">
            <div class="text-xs text-gray-600">180日高点 <span class="text-gray-400">(主板)</span></div>
            <button 
              @click="handleRefreshHigh180d" 
              :disabled="refreshingHigh180d"
              class="text-xs px-2 py-0.5 bg-indigo-200 hover:bg-indigo-300 text-indigo-700 rounded disabled:opacity-50"
            >
              {{ refreshingHigh180d ? '刷新中...' : '刷新' }}
            </button>
          </div>
          <div class="text-2xl font-bold text-indigo-700">{{ dataQuality.universe_stats?.high_180d || 0 }}</div>
          <div class="text-xs text-gray-400 mt-2 border-t border-indigo-200 pt-2">
            ✓ 已是180日新高<br>
            ✓ 股价 > 5元<br>
            ✓ 成交额 > 10亿<br>
            ✓ 180日涨幅 < 60%<br>
            ✓ 仅主板（600/601/603/000/001/002）
          </div>
          <div class="mt-2">
            <button 
              @click="handleDownloadHigh180dStocks" 
              :disabled="downloadingHigh180d"
              class="text-xs px-2 py-0.5 bg-indigo-300 hover:bg-indigo-400 text-indigo-800 rounded disabled:opacity-50 w-full"
            >
              {{ downloadingHigh180d ? '下载中...' : '下载' }}
            </button>
          </div>
        </Card>
        <!-- 60日新高策略（主板强势股） -->
        <Card class="p-4 bg-purple-50 border-purple-200">
          <div class="flex items-center justify-between mb-1">
            <div class="text-xs text-gray-600">60日新高 <span class="text-gray-400">(主板)</span></div>
            <button 
              @click="handleRefreshHigh60d" 
              :disabled="refreshingHigh60d"
              class="text-xs px-2 py-0.5 bg-purple-200 hover:bg-purple-300 text-purple-700 rounded disabled:opacity-50"
            >
              {{ refreshingHigh60d ? '刷新中...' : '刷新' }}
            </button>
          </div>
          <div class="text-2xl font-bold text-purple-700">{{ dataQuality.universe_stats?.high_60d || 0 }}</div>
          <div class="text-xs text-gray-400 mt-2 border-t border-purple-200 pt-2">
            ✓ 距60日高点 ≤ 3%<br>
            ✓ 成交额 ≥ 10亿<br>
            ✓ 仅主板（600/601/603/000/001/002）
          </div>
          <div class="mt-2">
            <button 
              @click="handleDownloadHigh60dStocks" 
              :disabled="downloadingHigh60d"
              class="text-xs px-2 py-0.5 bg-purple-300 hover:bg-purple-400 text-purple-800 rounded disabled:opacity-50 w-full"
            >
              {{ downloadingHigh60d ? '下载中...' : '下载' }}
            </button>
          </div>
        </Card>
      </div>
      
      <!-- 按数据维度显示（简化版：总数、完整性、最新日期，白色背景） -->
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <!-- 日线数据 -->
        <Card class="p-4" v-if="dataQuality.data_dimensions.daily_price">
          <h3 class="text-sm font-medium text-gray-900 mb-3">日线数据</h3>
          <div class="space-y-2">
            <div class="flex items-center justify-between text-sm">
              <span class="text-gray-600">目标数量:</span>
              <span class="font-medium">{{ dataQuality.data_dimensions.daily_price.target_count || 0 }}</span>
            </div>
            <div class="flex items-center justify-between text-sm">
              <span class="text-gray-600">更新数量:</span>
              <span class="font-medium">{{ dataQuality.data_dimensions.daily_price.updated_count || 0 }}</span>
            </div>
            <div class="flex items-center justify-between text-sm">
              <span class="text-gray-600">完整性:</span>
              <span 
                :class="[
                  'font-medium',
                  (dataQuality.data_dimensions.daily_price.completeness || 0) >= 100 
                    ? 'text-green-600' 
                    : 'text-red-600'
                ]"
              >
                {{ dataQuality.data_dimensions.daily_price.completeness || 0 }}%
              </span>
            </div>
            <div v-if="dataQuality.data_dimensions.daily_price.update_date" class="text-xs text-gray-500 mt-1">
              更新日期: {{ dataQuality.data_dimensions.daily_price.update_date }}
            </div>
          </div>
        </Card>
        
        <!-- 财务数据 -->
        <Card class="p-4" v-if="dataQuality.data_dimensions.fundamental">
          <h3 class="text-sm font-medium text-gray-900 mb-3">财务数据</h3>
          <div class="space-y-2">
            <div class="flex items-center justify-between text-sm">
              <span class="text-gray-600">目标数量:</span>
              <span class="font-medium">{{ dataQuality.data_dimensions.fundamental.target_count || 0 }}</span>
            </div>
            <div class="flex items-center justify-between text-sm">
              <span class="text-gray-600">更新数量:</span>
              <span class="font-medium">{{ dataQuality.data_dimensions.fundamental.updated_count || 0 }}</span>
            </div>
            <div class="flex items-center justify-between text-sm">
              <span class="text-gray-600">完整性:</span>
              <span 
                :class="[
                  'font-medium',
                  (dataQuality.data_dimensions.fundamental.completeness || 0) >= 100 
                    ? 'text-green-600' 
                    : 'text-red-600'
                ]"
              >
                {{ dataQuality.data_dimensions.fundamental.completeness || 0 }}%
              </span>
            </div>
            <div v-if="dataQuality.data_dimensions.fundamental.update_date" class="text-xs text-gray-500 mt-1">
              更新日期: {{ dataQuality.data_dimensions.fundamental.update_date }}
            </div>
          </div>
        </Card>
        
        <!-- 板块数据 -->
        <Card class="p-4" v-if="dataQuality.data_dimensions.sector">
          <h3 class="text-sm font-medium text-gray-900 mb-3">板块数据</h3>
          <div class="space-y-2">
            <div class="flex items-center justify-between text-sm">
              <span class="text-gray-600">目标数量:</span>
              <span class="font-medium">{{ dataQuality.data_dimensions.sector.target_count || 0 }}</span>
            </div>
            <div class="flex items-center justify-between text-sm">
              <span class="text-gray-600">更新数量:</span>
              <span class="font-medium">{{ dataQuality.data_dimensions.sector.updated_count || 0 }}</span>
            </div>
            <div class="flex items-center justify-between text-sm">
              <span class="text-gray-600">完整性:</span>
              <span 
                :class="[
                  'font-medium',
                  (dataQuality.data_dimensions.sector.completeness || 0) >= 100 
                    ? 'text-green-600' 
                    : 'text-red-600'
                ]"
              >
                {{ dataQuality.data_dimensions.sector.completeness || 0 }}%
              </span>
            </div>
            <div v-if="dataQuality.data_dimensions.sector.update_date" class="text-xs text-gray-500 mt-1">
              更新日期: {{ dataQuality.data_dimensions.sector.update_date }}
            </div>
          </div>
        </Card>
        
        <!-- 公司基础信息 -->
        <Card class="p-4" v-if="dataQuality.data_dimensions.stock_info">
          <h3 class="text-sm font-medium text-gray-900 mb-3">公司基础信息</h3>
          <div class="space-y-2">
            <div class="flex items-center justify-between text-sm">
              <span class="text-gray-600">目标数量:</span>
              <span class="font-medium">{{ dataQuality.data_dimensions.stock_info.target_count || 0 }}</span>
            </div>
            <div class="flex items-center justify-between text-sm">
              <span class="text-gray-600">更新数量:</span>
              <span class="font-medium">{{ dataQuality.data_dimensions.stock_info.updated_count || 0 }}</span>
            </div>
            <div class="flex items-center justify-between text-sm">
              <span class="text-gray-600">完整性:</span>
              <span 
                :class="[
                  'font-medium',
                  (dataQuality.data_dimensions.stock_info.completeness || 0) >= 100 
                    ? 'text-green-600' 
                    : 'text-red-600'
                ]"
              >
                {{ dataQuality.data_dimensions.stock_info.completeness || 0 }}%
              </span>
            </div>
            <div v-if="dataQuality.data_dimensions.stock_info.update_date" class="text-xs text-gray-500 mt-1">
              更新日期: {{ dataQuality.data_dimensions.stock_info.update_date }}
            </div>
          </div>
        </Card>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import Card from '../components/ui/Card.vue'
import Button from '../components/ui/Button.vue'
import { dataManagementApi } from '../api/dataManagementApi'
import { dataCache, CACHE_KEYS } from '../services/dataCache'

const loading = ref(false)
const updatingMissing = ref(false)
const fillingMissingDaily = ref(false)
const refreshingMainboard = ref(false)
const refreshingBase = ref(false)
const refreshingS1 = ref(false)
const refreshingS2 = ref(false)
const refreshingNewHigh = ref(false)
const refreshingHigh180d = ref(false)
const refreshingHigh60d = ref(false)
const addingToWatchlist = ref(false)
const downloadingS1 = ref(false)
const downloadingHigh180d = ref(false)
const downloadingHigh60d = ref(false)
const missingDates = ref([])
const dataSourceHealth = ref({ sources: {}, check_time: null })
const dataQuality = ref({
  data_dimensions: {
    daily_price: {
      name: '日线数据',
      target_count: 0,
      updated_count: 0,
      completeness: 0.0,
      update_date: null
    },
    fundamental: {
      name: '财务数据',
      target_count: 0,
      updated_count: 0,
      completeness: 0.0,
      update_date: null
    },
    stock_info: {
      name: '公司基础信息',
      target_count: 0,
      updated_count: 0,
      completeness: 0.0,
      update_date: null
    },
    sector: {
      name: '板块数据',
      target_count: 0,
      updated_count: 0,
      completeness: 0.0,
      update_date: null
    },
    realtime: {
      name: '实时数据',
      available: false,
      last_check: null
    }
  },
  universe_stats: {}
})
const taskExecutionStatus = ref({ tasks: [], total: 0 })
const selectedTaskFilter = ref('')
const selectedTaskType = ref('')
const triggering = ref(false)
const triggerResult = ref(null)
const expandedGroups = ref({}) // 控制折叠状态

// 计算总股票数（使用公司基础信息的目标数量）
const totalStocksCount = computed(() => {
  return dataQuality.value.data_dimensions?.stock_info?.target_count || 0
})


const fetchData = async (forceRefresh = false) => {
  loading.value = true
  try {
    // 检查缓存（不同数据类型使用不同的缓存时间）
    if (!forceRefresh) {
      // 数据源健康状态：缓存5分钟
      const cachedHealth = dataCache.get(CACHE_KEYS.DATA_MANAGEMENT_HEALTH)
      if (cachedHealth && dataCache.has(CACHE_KEYS.DATA_MANAGEMENT_HEALTH, 5 * 60 * 1000)) {
        dataSourceHealth.value = cachedHealth.data
      } else {
        const health = await dataManagementApi.getDataSourceHealth()
        dataSourceHealth.value = health
        dataCache.set(CACHE_KEYS.DATA_MANAGEMENT_HEALTH, health)
      }
      
      // 数据质量指标：缓存10分钟
      const cachedQuality = dataCache.get(CACHE_KEYS.DATA_MANAGEMENT_QUALITY)
      if (cachedQuality && dataCache.has(CACHE_KEYS.DATA_MANAGEMENT_QUALITY, 10 * 60 * 1000)) {
        console.log('📦 使用缓存的数据质量指标')
        dataQuality.value = cachedQuality.data
      } else {
        const quality = await dataManagementApi.getDataQualityMetrics()
        dataQuality.value = quality
        dataCache.set(CACHE_KEYS.DATA_MANAGEMENT_QUALITY, quality)
      }
      
      // 如果所有数据都来自缓存，直接返回
      if (cachedHealth && cachedQuality &&
          dataCache.has(CACHE_KEYS.DATA_MANAGEMENT_HEALTH, 5 * 60 * 1000) &&
          dataCache.has(CACHE_KEYS.DATA_MANAGEMENT_QUALITY, 10 * 60 * 1000)) {
        console.log('📦 使用缓存的数据管理数据')
        loading.value = false
        return
      }
    } else {
      // 强制刷新：并行获取所有数据
      const [health, quality] = await Promise.all([
        dataManagementApi.getDataSourceHealth(),
        dataManagementApi.getDataQualityMetrics()
      ])
      
      dataSourceHealth.value = health
      dataQuality.value = quality
      
      // 更新缓存
      dataCache.set(CACHE_KEYS.DATA_MANAGEMENT_HEALTH, health)
      dataCache.set(CACHE_KEYS.DATA_MANAGEMENT_QUALITY, quality)
    }
  } catch (error) {
    console.error('获取数据失败:', error)
    dataSourceHealth.value = { sources: {}, check_time: null }
    dataQuality.value = { data_dimensions: dataQuality.value?.data_dimensions || {}, universe_stats: {} }
    alert('获取数据失败，请重试。若数据库未连接，请先启动并连接数据库。')
  } finally {
    loading.value = false
  }
}

const handleRefresh = () => {
  fetchData(true) // 强制刷新
}

// 检查缺失数据（失败时置空列表，不阻塞页面）
const checkMissingData = async () => {
  try {
    const result = await dataManagementApi.checkMissingData(5)
    missingDates.value = result.missing_dates || []
  } catch (error) {
    console.error('检查缺失数据失败:', error)
    missingDates.value = []
  }
}

// 补缺失日线：先查库最新日期，再补近5日内、今天之前的缺失
const handleFillMissingDaily = async () => {
  fillingMissingDaily.value = true
  try {
    const result = await dataManagementApi.fillMissingDaily(5)
    const latest = result.latest_date || '未知'
    const missing = result.missing_dates || []
    if (result.started && missing.length > 0) {
      alert(`最新日线日期: ${latest}\n缺失日期（已启动补充）: ${missing.join(', ')}\n任务在后台执行，请稍后刷新页面查看。`)
      fetchData(true).catch(() => {})
      dataManagementApi.checkMissingData(5).then((data) => {
        missingDates.value = data.missing_dates || []
      }).catch(() => {})
    } else {
      alert(`最新日线日期: ${latest}\n${result.message || '数据已完整，无需补充'}`)
      missingDates.value = []
      fetchData(true).catch(() => {})
    }
  } catch (error) {
    console.error('补缺失日线失败:', error)
    alert('补缺失日线失败: ' + (error?.message || String(error)))
  } finally {
    fillingMissingDaily.value = false
  }
}

// 增量更新缺失数据（日线）
const handleUpdateMissing = async () => {
  updatingMissing.value = true
  try {
    const result = await dataManagementApi.updateMissingData(5)
    const msg = result?.message || '增量更新任务已启动'
    const dates = result?.update_dates
    const detail = Array.isArray(dates) && dates.length
      ? `，将更新 ${dates.length} 个交易日`
      : ''
    alert(msg + detail + '。任务在后台执行，请稍后在「数据质量」或刷新页面查看结果。')
    // 刷新数据质量（不阻塞）；检查缺失数据在后台执行，失败不影响“增量更新已触发”的结论
    fetchData(true).catch(() => {})
    dataManagementApi.checkMissingData(5).then((data) => {
      missingDates.value = data.missing_dates || []
    }).catch(() => { /* 检查缺失较慢或超时时静默忽略，不误报为增量更新失败 */ })
  } catch (error) {
    console.error('增量更新失败:', error)
    alert('增量更新失败: ' + (error?.message || String(error)))
  } finally {
    updatingMissing.value = false
  }
}

// 刷新基础池
// 刷新主板池
const handleRefreshMainboard = async () => {
  refreshingMainboard.value = true
  try {
    const response = await fetch('/api/stock-universe/update?universe_type=mainboard&force_refresh=true', {
      method: 'POST'
    })
    const result = await response.json()
    if (result.success) {
      alert(`主板池刷新成功！更新了 ${result.result?.added || result.result?.filtered || 0} 只股票`)
      // 刷新数据
      await fetchData(true)
    } else {
      alert('刷新失败: ' + (result.detail || '未知错误'))
    }
  } catch (error) {
    console.error('刷新主板池失败:', error)
    alert('刷新失败: ' + error.message)
  } finally {
    refreshingMainboard.value = false
  }
}

const handleRefreshBaseUniverse = async () => {
  refreshingBase.value = true
  try {
    const response = await fetch('/api/stock-universe/update?universe_type=base&force_refresh=true', {
      method: 'POST'
    })
    const result = await response.json()
    if (result.success) {
      alert(`基础池刷新成功！更新了 ${result.result?.added || result.result?.filtered || 0} 只股票`)
      // 刷新数据
      await fetchData(true)
    } else {
      alert('刷新失败: ' + (result.detail || '未知错误'))
    }
  } catch (error) {
    console.error('刷新基础池失败:', error)
    alert('刷新基础池失败: ' + error.message)
  } finally {
    refreshingBase.value = false
  }
}

// 刷新S1池
const handleRefreshS1Universe = async () => {
  refreshingS1.value = true
  try {
    const response = await fetch('/api/stock-universe/update?universe_type=s1&force_refresh=true', {
      method: 'POST'
    })
    const result = await response.json()
    if (result.success) {
      alert(`S1池刷新成功！更新了 ${result.result?.added || result.result?.filtered || 0} 只股票`)
      // 刷新数据
      await fetchData(true)
    } else {
      alert('刷新失败: ' + (result.detail || '未知错误'))
    }
  } catch (error) {
    console.error('刷新S1池失败:', error)
    alert('刷新S1池失败: ' + error.message)
  } finally {
    refreshingS1.value = false
  }
}

// 刷新30日新高策略指标
const handleRefreshNewHighStrategy = async () => {
  refreshingNewHigh.value = true
  try {
    // 刷新数据质量指标（会重新计算30日新高策略）
    const quality = await dataManagementApi.getDataQualityMetrics()
    dataQuality.value = quality
    
    // 更新缓存
    dataCache.set(CACHE_KEYS.DATA_MANAGEMENT_QUALITY, quality)
    
    const validCount = quality.data_dimensions?.new_high_strategy?.valid_count || 0
    const abnormalCount = quality.data_dimensions?.new_high_strategy?.abnormal_count || 0
    
    alert(`30日新高策略计算完成！\n有效股票: ${validCount} 只\n异常股票: ${abnormalCount} 只`)
  } catch (error) {
    console.error('刷新30日新高策略失败:', error)
    alert('刷新失败: ' + error.message)
  } finally {
    refreshingNewHigh.value = false
  }
}

// 将30日新高股票加入跟踪池
const handleAddNewHighToWatchlist = async () => {
  addingToWatchlist.value = true
  try {
    const response = await fetch('/api/data-management/new-high-to-watchlist', {
      method: 'POST'
    })
    const result = await response.json()
    
    if (result.success) {
      alert(`成功添加 ${result.added_count} 只股票到跟踪池！\n已存在: ${result.existing_count} 只\n总有效股票: ${result.total_valid} 只`)
    } else {
      alert('添加失败: ' + (result.message || '未知错误'))
    }
  } catch (error) {
    console.error('添加到跟踪池失败:', error)
    alert('添加失败: ' + error.message)
  } finally {
    addingToWatchlist.value = false
  }
}

// 下载S1股票列表
const handleDownloadS1Stocks = async () => {
  downloadingS1.value = true
  try {
    // 获取今天的日期
    const today = new Date().toISOString().split('T')[0]
    
    // 调用下载接口
    const response = await fetch(`/api/monitor/download/s1_stocks?date=${today}&format=code`)
    
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: '下载失败' }))
      throw new Error(errorData.detail || '下载失败')
    }
    
    // 获取文件名（从响应头或使用默认名称）
    const contentDisposition = response.headers.get('content-disposition')
    let filename = `s1_stocks_${today}.txt`
    if (contentDisposition) {
      const filenameMatch = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/)
      if (filenameMatch && filenameMatch[1]) {
        filename = filenameMatch[1].replace(/['"]/g, '')
      }
    }
    
    // 下载文件
    const blob = await response.blob()
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    window.URL.revokeObjectURL(url)
    document.body.removeChild(a)
  } catch (error) {
    console.error('下载S1股票列表失败:', error)
    alert('下载失败: ' + error.message)
  } finally {
    downloadingS1.value = false
  }
}

// 刷新180日高点池
const handleRefreshHigh180d = async () => {
  refreshingHigh180d.value = true
  try {
    const response = await fetch('/api/stock-universe/update?universe_type=high_180d&force_refresh=true', {
      method: 'POST'
    })
    const result = await response.json()
    if (result.success) {
      alert(`180日高点池刷新成功！更新了 ${result.result?.added || result.result?.filtered || 0} 只股票`)
      // 刷新数据
      await fetchData(true)
    } else {
      alert('刷新失败: ' + (result.detail || '未知错误'))
    }
  } catch (error) {
    console.error('刷新180日高点池失败:', error)
    alert('刷新失败: ' + error.message)
  } finally {
    refreshingHigh180d.value = false
  }
}

// 下载180日高点股票列表
const handleDownloadHigh180dStocks = async () => {
  downloadingHigh180d.value = true
  try {
    const today = new Date().toISOString().split('T')[0]
    
    // 调用下载接口
    const response = await fetch(`/api/monitor/download/universe_stocks?universe_type=high_180d&date=${today}&format=code`)
    
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: '下载失败' }))
      throw new Error(errorData.detail || '下载失败')
    }
    
    // 获取文件名
    const contentDisposition = response.headers.get('content-disposition')
    let filename = `high_180d_stocks_${today}.txt`
    if (contentDisposition) {
      const filenameMatch = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/)
      if (filenameMatch && filenameMatch[1]) {
        filename = filenameMatch[1].replace(/['"]/g, '')
      }
    }
    
    // 下载文件
    const blob = await response.blob()
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    window.URL.revokeObjectURL(url)
    document.body.removeChild(a)
  } catch (error) {
    console.error('下载180日高点股票列表失败:', error)
    alert('下载失败: ' + error.message)
  } finally {
    downloadingHigh180d.value = false
  }
}

// 刷新60日新高池
const handleRefreshHigh60d = async () => {
  refreshingHigh60d.value = true
  try {
    const response = await fetch('/api/stock-universe/update?universe_type=high_60d&force_refresh=true', {
      method: 'POST'
    })
    const result = await response.json()
    if (result.success) {
      alert(`60日新高池刷新成功！更新了 ${result.result?.added || result.result?.filtered || 0} 只股票`)
      // 刷新数据
      await fetchData(true)
    } else {
      alert('刷新失败: ' + (result.detail || '未知错误'))
    }
  } catch (error) {
    console.error('刷新60日新高池失败:', error)
    alert('刷新失败: ' + error.message)
  } finally {
    refreshingHigh60d.value = false
  }
}

// 下载60日新高股票列表
const handleDownloadHigh60dStocks = async () => {
  downloadingHigh60d.value = true
  try {
    const today = new Date().toISOString().split('T')[0]
    
    // 调用下载接口
    const response = await fetch(`/api/monitor/download/universe_stocks?universe_type=high_60d&date=${today}&format=code`)
    
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: '下载失败' }))
      throw new Error(errorData.detail || '下载失败')
    }
    
    // 获取文件名
    const contentDisposition = response.headers.get('content-disposition')
    let filename = `high_60d_stocks_${today}.txt`
    if (contentDisposition) {
      const filenameMatch = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/)
      if (filenameMatch && filenameMatch[1]) {
        filename = filenameMatch[1].replace(/['"]/g, '')
      }
    }
    
    // 下载文件
    const blob = await response.blob()
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    window.URL.revokeObjectURL(url)
    document.body.removeChild(a)
  } catch (error) {
    console.error('下载60日新高股票列表失败:', error)
    alert('下载失败: ' + error.message)
  } finally {
    downloadingHigh60d.value = false
  }
}

// 刷新S2池
const handleRefreshS2Universe = async () => {
  refreshingS2.value = true
  try {
    const response = await fetch('/api/stock-universe/update?universe_type=s2&force_refresh=true', {
      method: 'POST'
    })
    const result = await response.json()
    if (result.success) {
      // 刷新数据质量统计
      await fetchData(true)
      alert(`S2池刷新成功，共 ${result.result?.added || 0} 只股票`)
    } else {
      alert('刷新S2池失败: ' + (result.detail || '未知错误'))
    }
  } catch (error) {
    console.error('刷新S2池失败:', error)
    alert('刷新S2池失败: ' + error.message)
  } finally {
    refreshingS2.value = false
  }
}

// 监听全局刷新事件
const handleGlobalRefresh = () => {
  fetchData(true)
}

onMounted(() => {
  fetchData()
  checkMissingData()
  window.addEventListener('global-refresh', handleGlobalRefresh)
})

onUnmounted(() => {
  window.removeEventListener('global-refresh', handleGlobalRefresh)
})
</script>

