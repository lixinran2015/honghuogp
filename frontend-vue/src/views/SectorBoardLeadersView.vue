<template>
  <div class="container mx-auto px-4 py-6">
    <div class="mb-6 flex items-start justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-800">板块领涨</h1>
        <p class="text-sm text-gray-500 mt-1">东财行业板块实时排名与领涨股（数据源：东方财富）。排名按涨跌幅重算；同名板块可能来自不同分类，板块代码不同则成分股与涨跌幅不同。</p>
      </div>
      <div class="flex items-center gap-3">
        <span
          v-if="source"
          class="text-xs px-2 py-1 rounded"
          :class="source === 'db' ? 'bg-green-100 text-green-700' : 'bg-blue-100 text-blue-700'"
        >
          {{ source === 'db' ? '缓存' : '实时' }}
        </span>
        <button
          @click="loadData(false)"
          :disabled="loading"
          class="px-4 py-2 bg-gray-100 text-gray-700 rounded hover:bg-gray-200 disabled:opacity-50 text-sm flex items-center gap-2"
        >
          {{ loading ? '加载中...' : '刷新' }}
        </button>
        <button
          @click="loadData(true)"
          :disabled="loading"
          class="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 text-sm flex items-center gap-2"
        >
          强制刷新（拉取最新）
        </button>
      </div>
    </div>

    <div v-if="mainlineNames.length" class="mb-4 flex items-center gap-2 flex-wrap">
      <span class="text-sm text-gray-600">主线：</span>
      <span
        v-for="name in mainlineNames"
        :key="name"
        class="text-xs px-2 py-1 rounded bg-amber-100 text-amber-800"
      >
        {{ name }}
      </span>
    </div>

    <div class="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
      <strong>免责声明：</strong>本页数据仅供参考，不构成投资建议。
    </div>

    <!-- 板块涨跌幅热力图（与表格共用同一数据源） -->
    <div class="mb-6">
      <SectorHeatmap :items="items" />
    </div>

    <div class="bg-white rounded-lg shadow overflow-hidden">
      <div v-if="loading && !items.length" class="p-12 text-center text-gray-500">
        加载中...
      </div>
      <div v-else-if="error" class="p-12 text-center text-red-600">
        {{ error }}
      </div>
      <div v-else-if="!items.length" class="p-12 text-center text-gray-500">
        <p>暂无数据</p>
        <p class="text-sm mt-2">请点击「强制刷新」拉取东财行业板块数据</p>
      </div>
      <div v-else class="overflow-x-auto">
        <table class="min-w-full divide-y divide-gray-200">
          <thead class="bg-gray-50">
            <tr>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">排名</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">板块名称</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase" title="板块代码，同名板块（东财/申万不同分类）代码不同">板块代码</th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">涨跌幅</th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">总市值</th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">换手率</th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">上涨</th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">涨停</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">领涨股</th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">领涨股涨幅</th>
            </tr>
          </thead>
          <tbody class="bg-white divide-y divide-gray-200">
            <tr
              v-for="(row, idx) in items"
              :key="row.sector_id || idx"
              :data-sector-name="row.name"
              :class="[
                'hover:bg-gray-50',
                highlightSector && (row.name === highlightSector) ? 'bg-amber-50 ring-2 ring-amber-300' : '',
                mainlineNames.includes(row.name) ? 'bg-amber-50/50' : ''
              ]"
            >
              <td class="px-4 py-3 text-sm font-medium text-gray-900">{{ row.rank ?? '-' }}</td>
              <td class="px-4 py-3 text-sm font-medium text-gray-900">{{ row.name ?? '-' }}</td>
              <td class="px-4 py-3 text-xs text-gray-500" :title="'同名板块可能来自不同分类(东财/申万)，代码不同则成分股与涨跌幅不同'">{{ row.sector_id ?? '-' }}</td>
              <td
                class="px-4 py-3 text-sm text-right font-medium"
                :class="pctClass(row.change_pct)"
              >
                {{ formatPct(row.change_pct) }}
              </td>
              <td class="px-4 py-3 text-sm text-right text-gray-600">{{ formatMarketCap(row.market_cap) }}</td>
              <td class="px-4 py-3 text-sm text-right text-gray-600">{{ formatPct(row.turnover_rate) }}</td>
              <td class="px-4 py-3 text-sm text-right text-gray-600">{{ row.up_count ?? '-' }}</td>
              <td class="px-4 py-3 text-sm text-right text-gray-600">{{ row.limit_up_count ?? '-' }}</td>
              <td class="px-4 py-3 text-sm font-medium text-blue-600">{{ row.leader_stock ?? '-' }}</td>
              <td
                class="px-4 py-3 text-sm text-right font-medium"
                :class="pctClass(row.leader_change_pct)"
              >
                {{ formatPct(row.leader_change_pct) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="items.length && !loading" class="px-4 py-3 border-t border-gray-200 text-sm text-gray-500">
        共 {{ items.length }} 个板块 · 日期 {{ date }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import axios from 'axios'
import SectorHeatmap from '../components/SectorHeatmap.vue'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''
const route = useRoute()

const loading = ref(false)
const items = ref([])
const date = ref('')
const source = ref('')
const error = ref('')
const highlightSector = ref('') // URL ?sector= 预填，用于高亮
const mainlineNames = ref([]) // 当前主线板块名称，用于高亮

function pctClass(val) {
  if (val == null) return 'text-gray-500'
  const v = Number(val)
  if (v > 0) return 'text-red-600'
  if (v < 0) return 'text-green-600'
  return 'text-gray-500'
}

function formatPct(val) {
  if (val == null) return '-'
  const v = Number(val)
  const sign = v > 0 ? '+' : ''
  return `${sign}${v.toFixed(2)}%`
}

function formatMarketCap(val) {
  if (val == null) return '-'
  const v = Number(val)
  if (v >= 1e12) return (v / 1e12).toFixed(2) + '万亿'
  if (v >= 1e8) return (v / 1e8).toFixed(2) + '亿'
  return v.toLocaleString()
}

async function loadMainline() {
  try {
    const resp = await axios.get(`${API_BASE_URL}/api/sector-rotation/current-mainline`, { params: { top: 5 } })
    if (resp.data?.success && resp.data?.data?.mainline) {
      mainlineNames.value = resp.data.data.mainline.map(m => m.sector_name).filter(Boolean)
    } else {
      mainlineNames.value = []
    }
  } catch {
    mainlineNames.value = []
  }
}

async function loadData(forceRefresh = false) {
  loading.value = true
  error.value = ''
  try {
    const resp = await axios.get(`${API_BASE_URL}/api/hot-sectors/industry-boards-with-leaders`, {
      params: { refresh: forceRefresh },
    })
    items.value = resp.data.items || []
    date.value = resp.data.date || ''
    source.value = resp.data.source || ''
    if (resp.data.message && !items.value.length) {
      error.value = resp.data.message
    }
  } catch (e) {
    error.value = e.response?.data?.detail || e.message || '加载失败'
    items.value = []
  } finally {
    loading.value = false
  }
}

watch(() => route.query.sector, (val) => {
  highlightSector.value = val || ''
}, { immediate: true })

// 高亮时滚动到该行
function scrollToHighlighted() {
  if (!highlightSector.value) return
  nextTick(() => {
    const el = document.querySelector(`tr[data-sector-name="${highlightSector.value}"]`)
    el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  })
}

onMounted(() => {
  highlightSector.value = route.query.sector || ''
  loadMainline()
  loadData(false)
})

watch([items, highlightSector], () => {
  if (items.value.length && highlightSector.value) scrollToHighlighted()
})
</script>
