<template>
  <div class="container mx-auto px-4 py-6">
    <!-- 标题区 -->
    <div class="mb-6">
      <h1 class="text-2xl font-bold text-gray-800">启动主线雷达</h1>
      <p class="text-sm text-gray-500 mt-1">
        基于最近几天的启动信号，按「行业 / 题材」聚合成板块强度。列表仅展示<strong class="text-gray-700">主线强度 &gt; 5</strong> 的板块中、强度排名前 <strong class="text-gray-700">10</strong> 条主线，以及其中的空间龙头、补涨龙和跟风链条。
      </p>
    </div>

    <!-- 查询条件 -->
    <div class="bg-white rounded-xl shadow border border-gray-100 mb-6 p-4 lg:p-6">
      <div class="flex flex-col lg:flex-row lg:items-end gap-4">
        <div class="flex-1 min-w-[200px]">
          <label class="block text-xs font-medium text-gray-500 mb-1">开始日期</label>
          <input
            v-model="startDate"
            type="date"
            class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
          />
        </div>
        <div class="flex-1 min-w-[200px]">
          <label class="block text-xs font-medium text-gray-500 mb-1">结束日期</label>
          <input
            v-model="endDate"
            type="date"
            class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
          />
        </div>
        <div class="w-full lg:w-40">
          <label class="block text-xs font-medium text-gray-500 mb-1">最低得分</label>
          <input
            v-model.number="minScore"
            type="number"
            min="0"
            max="100"
            class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
          />
        </div>
        <div class="w-full lg:w-44">
          <label class="block text-xs font-medium text-gray-500 mb-1">阶段</label>
          <select
            v-model="stage"
            class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
          >
            <option value="">confirmed + started</option>
            <option value="confirmed">仅启动确认 (confirmed)</option>
            <option value="started">仅完全启动 (started)</option>
          </select>
        </div>
        <div class="flex flex-col gap-2 items-stretch lg:items-end">
          <div class="flex gap-3">
          <button
            @click="fetchData"
            :disabled="loading"
            class="px-4 py-2 rounded-lg text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {{ loading ? '加载中...' : '刷新' }}
          </button>
          <button
            @click="resetRangeAndFetch"
            :disabled="loading"
            class="px-3 py-2 rounded-lg text-sm font-medium text-gray-600 bg-gray-50 border border-gray-200 hover:bg-gray-100 disabled:opacity-60 disabled:cursor-not-allowed"
          >
            最近 5 日
          </button>
          <button
            @click="handleRebuildSectorLeaders"
            :disabled="loading || rebuildingLeaders"
            class="px-3 py-2 rounded-lg text-xs font-medium text-amber-800 bg-amber-50 border border-amber-200 hover:bg-amber-100 disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {{ rebuildingLeaders ? '重建板块龙头中...' : '重建板块龙头(v2)' }}
          </button>
          </div>
          <div v-if="rebuildMessage" class="text-[11px] text-amber-700">
            {{ rebuildMessage }}
          </div>
        </div>
      </div>
      <p class="mt-3 text-xs text-gray-400">
        提示：不填日期时，后端会自动使用「结束日期=今天，开始日期=结束日期往前 5 天」的窗口。
      </p>
    </div>

    <!-- 错误提示 -->
    <div v-if="error" class="mb-4 bg-red-50 border border-red-200 text-red-700 text-sm px-4 py-3 rounded-lg">
      {{ error }}
    </div>

    <!-- 空状态 -->
    <div
      v-if="!loading && !error && sectors.length === 0"
      class="bg-blue-50 border border-blue-100 text-blue-700 text-sm px-6 py-6 rounded-lg text-center"
    >
      暂无主线数据，请调整日期区间或稍后重试。
    </div>
    <div
      v-else-if="!loading && !error && sectors.length > 0 && filteredSectors.length === 0"
      class="bg-amber-50 border border-amber-100 text-amber-800 text-sm px-6 py-6 rounded-lg text-center"
    >
      当前返回的板块中无有效主线，故雷达列表为空。可调低「最低得分」或扩大日期窗口后重试。
    </div>

    <!-- 各主线空间龙头（按股票分组） -->
    <div
      v-if="!loading && !error && spaceLeadersByStock.length > 0"
      class="mb-4 bg-amber-50/80 border border-amber-200 rounded-xl p-4"
    >
      <div class="flex flex-col lg:flex-row lg:items-start gap-4">
        <div class="flex-1">
          <div class="text-sm font-semibold text-amber-800 mb-3">各主线空间龙头（按股票）</div>
      <div class="space-y-2">
        <div
          v-for="stock in spaceLeadersByStock"
          :key="stock.ts_code"
          class="flex flex-wrap items-center gap-2"
        >
          <button
            type="button"
            class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs border border-amber-300 bg-white text-gray-800 hover:bg-amber-50 transition shrink-0"
            @click="openDiagnose(stock.ts_code)"
          >
            <span class="font-semibold">{{ stock.name || stock.ts_code }}</span>
            <span class="font-mono text-gray-500">{{ stock.ts_code }}</span>
            <span class="text-amber-600">· {{ stock.role_label }}</span>
          </button>
          <span class="text-gray-400 text-[11px]">→</span>
          <div class="flex flex-wrap gap-1.5">
            <span
              v-for="sector in stock.sectors"
              :key="sector"
              class="inline-flex px-2 py-0.5 rounded text-[11px] bg-amber-100/80 text-amber-800"
            >
              {{ sector }}
            </span>
          </div>
        </div>
      </div>
        </div>

        <!-- 各板块刚启动龙头（按股票分组，与左侧逻辑一致） -->
        <div v-if="newLeadersByStock.length > 0" class="flex-1 border-t pt-3 lg:border-t-0 lg:border-l lg:pl-4 lg:pt-0 border-amber-200">
          <div class="text-sm font-semibold text-red-700 mb-2">各板块刚启动龙头（按股票）</div>
          <div class="space-y-2 pr-1">
            <div
              v-for="stock in newLeadersByStock"
              :key="stock.ts_code"
              class="flex flex-wrap items-center gap-2 text-xs"
            >
              <button
                type="button"
                class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-red-200 bg-white text-red-700 hover:bg-red-50 transition shrink-0"
                @click="openDiagnose(stock.ts_code)"
              >
                <span class="font-semibold">{{ stock.name || stock.ts_code }}</span>
                <span class="font-mono text-[11px] text-red-500">{{ stock.ts_code }}</span>
                <span class="px-1.5 py-0.5 rounded-full text-[10px] font-semibold bg-red-100 text-red-700">刚启动</span>
              </button>
              <span class="text-gray-400 text-[11px]">→</span>
              <div class="flex flex-wrap gap-1.5">
                <span
                  v-for="sector in stock.sectors"
                  :key="sector"
                  class="inline-flex px-2 py-0.5 rounded text-[11px] bg-rose-50 text-rose-700"
                >
                  {{ sector }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 明日轮动方向预判 -->
    <div
      v-if="!loading && !error && rotationHint"
      class="mb-6 bg-white rounded-xl shadow border border-gray-100 p-4"
    >
      <div class="flex items-center gap-2 mb-3 flex-wrap">
        <span class="text-sm font-semibold text-gray-800">明日轮动方向</span>
        <span
          v-if="rotationHint.conclusion_type"
          class="inline-flex px-2 py-0.5 rounded-full text-[11px] font-medium"
          :class="{
            'bg-green-50 text-green-700': rotationHint.conclusion_type === 'internal_rotation',
            'bg-blue-50 text-blue-700': rotationHint.conclusion_type === 'second_taking_over',
            'bg-red-50 text-red-700': rotationHint.conclusion_type === 'retreat',
          }"
        >
          {{
            rotationHint.conclusion_type === 'internal_rotation'
              ? '主线内部轮动'
              : rotationHint.conclusion_type === 'second_taking_over'
                ? '次主线接棒'
                : rotationHint.conclusion_type === 'retreat'
                  ? '退潮观望'
                  : rotationHint.conclusion_type
          }}
        </span>
        <span v-if="rotationHint.trade_date" class="text-xs text-gray-400">
          统计日：{{ rotationHint.trade_date }}
        </span>
        <span v-if="rotationHint.predict_date" class="text-xs text-gray-400">
          预测日：{{ rotationHint.predict_date }}
        </span>
      </div>
      <p class="text-sm text-gray-700 mb-3">{{ rotationHint.conclusion }}</p>
      <div v-if="rotationHint.suggest_sector" class="mb-2 text-sm">
        <span class="text-gray-500">建议关注板块：</span>
        <span class="font-medium text-indigo-600">{{ rotationHint.suggest_sector }}</span>
      </div>
      <!-- 主线对应股票：内部轮动时拆成「高」「低」两组，体现高切低 -->
      <div v-if="(rotationHint.main_sector_chain || []).length > 0" class="mb-3">
        <template v-if="rotationHint.conclusion_type === 'internal_rotation'">
          <div class="mb-2">
            <div class="text-xs font-medium text-amber-700 mb-1">高位龙头（观察分歧/洗盘，高切低的「高」）</div>
            <div class="flex flex-wrap gap-2">
              <button
                v-for="s in (rotationHint.main_sector_chain || []).filter(x => x.position_type === 'high')"
                :key="s.ts_code"
                type="button"
                class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs border border-amber-200 bg-amber-50/80 text-amber-800 hover:bg-amber-100 transition"
                @click="openDiagnose(s.ts_code)"
              >
                <span class="font-medium">{{ s.name || s.ts_code }}</span>
                <span v-if="s.role_label" class="text-[11px] text-amber-600">{{ s.role_label }}</span>
              </button>
            </div>
            <p class="text-[11px] text-gray-400 mt-0.5">上述为空间龙头，明日若分歧/洗盘，资金可能切向下方低位。</p>
          </div>
          <div>
            <div class="text-xs font-medium text-green-700 mb-1">低位可关注（补涨/稳健，高切低的「低」）</div>
            <div class="flex flex-wrap gap-2">
              <button
                v-for="s in (rotationHint.main_sector_chain || []).filter(x => x.position_type === 'low')"
                :key="s.ts_code"
                type="button"
                class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs border border-green-200 bg-green-50/80 text-green-800 hover:bg-green-100 transition"
                @click="openDiagnose(s.ts_code)"
              >
                <span class="font-medium">{{ s.name || s.ts_code }}</span>
                <span v-if="s.role_label" class="text-[11px] text-green-600">{{ s.role_label }}</span>
              </button>
            </div>
            <p class="text-[11px] text-gray-400 mt-0.5">可关注主线内补涨龙、相对强势等接力机会。</p>
          </div>
        </template>
        <template v-else>
          <div class="text-xs font-medium text-gray-600 mb-1.5">主线对应股票</div>
          <div class="flex flex-wrap gap-2">
            <button
              v-for="s in rotationHint.main_sector_chain"
              :key="s.ts_code"
              type="button"
              class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs border border-gray-200 bg-gray-50 text-gray-700 hover:bg-indigo-50 hover:border-indigo-200 hover:text-indigo-700 transition"
              @click="openDiagnose(s.ts_code)"
            >
              <span class="font-medium">{{ s.name || s.ts_code }}</span>
              <span v-if="s.role_label" class="text-[11px] text-gray-500">{{ s.role_label }}</span>
            </button>
          </div>
        </template>
      </div>
      <ul v-if="(rotationHint.details || []).length > 0" class="text-xs text-gray-500 space-y-1 list-disc list-inside">
        <li v-for="(line, i) in rotationHint.details" :key="i">{{ line }}</li>
      </ul>
    </div>

    <!-- 主线列表 -->
    <div v-if="filteredSectors.length > 0" class="space-y-4">
      <div class="flex items-center justify-between text-xs text-gray-500 px-1">
        <div>共 {{ filteredSectors.length }} 条（强度 &gt; 5，取前 10）</div>
        <div>
          窗口：
          <span class="font-medium text-gray-700">{{ windowLabel }}</span>
        </div>
      </div>

      <div class="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <div
          v-for="(s, idx) in filteredSectors"
          :key="s.sector_key"
          class="bg-white rounded-xl shadow border border-gray-100 p-4 hover:border-indigo-200 hover:shadow-md transition"
        >
          <!-- 标题行 -->
          <div class="flex items-start justify-between gap-2 mb-2">
            <div>
          <div class="flex items-center gap-2">
                <span
                  class="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium"
                  :class="isIndexStyleSector(s)
                    ? 'bg-purple-50 text-purple-700'
                    : s.sector_type === 'industry'
                      ? 'bg-blue-50 text-blue-700'
                      : 'bg-amber-50 text-amber-700'"
                >
                  {{
                    isIndexStyleSector(s)
                      ? '指数 / 风格'
                      : s.sector_type === 'industry'
                        ? '行业'
                        : '题材'
                  }}
                </span>
                <h2 class="text-base font-semibold text-gray-900">
                  {{ idx + 1 }}. {{ s.sector_name }}
                </h2>
              </div>
              <div class="mt-1 text-xs text-gray-500">
                信号 {{ s.total_signals }} 次 · 覆盖 {{ s.distinct_stocks }} 只股 · 活跃 {{ s.days_active }} 日 ·
                近 3 日信号 {{ s.recent_3d_signals }} 次
              </div>
            </div>
            <div class="text-right">
              <div class="text-[11px] text-gray-400 mb-0.5">主线强度</div>
              <div class="text-lg font-bold text-indigo-600">
                {{ s.strength_score.toFixed(1) }}
              </div>
            </div>
          </div>

          <!-- 强度条 -->
          <div class="mt-1 mb-3">
            <div class="h-1.5 w-full bg-gray-100 rounded-full overflow-hidden">
              <div
                class="h-full rounded-full bg-gradient-to-r from-indigo-400 via-indigo-500 to-purple-500"
                :style="{ width: strengthPercent(s) + '%' }"
              />
            </div>
          </div>

          <!-- 接力链条 -->
          <div v-if="(s.chain || []).length > 0" class="mb-2">
            <div class="text-xs font-medium text-gray-600 mb-1">接力链条（空间龙头 / 补涨龙 / 跟风）</div>
            <div class="flex flex-wrap gap-2">
              <button
                v-for="stock in s.chain"
                :key="stock.ts_code + (stock.role_label || '')"
                type="button"
                class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs border border-gray-200 text-gray-700 bg-gray-50 hover:bg-indigo-50 hover:border-indigo-200 hover:text-indigo-700 transition"
                @click="openDiagnose(stock.ts_code)"
              >
                <span class="font-semibold text-xs">
                  {{ stock.name || stock.ts_code }}
                </span>
                <span class="font-mono text-[11px] text-gray-400">
                  {{ stock.ts_code }}
                </span>
              <span class="text-[11px] text-gray-500">
                  {{ stock.role_label || '待定角色' }}
                </span>
              <span
                v-if="stock.is_new_leader"
                class="px-1.5 py-0.5 rounded-full text-[10px] font-semibold bg-red-100 text-red-700"
              >
                刚启动
              </span>
              </button>
            </div>
          </div>
          <div v-else class="mb-2 text-xs text-gray-400">
            暂无可用的龙头/连板角色数据。
          </div>

          <!-- 简要走势信息（文字版） -->
          <div class="mt-2 text-[11px] text-gray-400 space-y-0.5">
            <div v-if="isIndexStyleSector(s)">
              这是一个「指数 / 风格」类板块，更多反映被动资金与风格偏好，适合作为主线的
              <span class="font-medium text-gray-500">资金 / 风格辅助标签</span>，而非单一进攻产业主线。
            </div>
            <div>
              平均得分 {{ s.avg_score_overall.toFixed(1) }}，最近几日信号集中度越高、强度分越高，越可能是当下主线。
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

const router = useRouter()

const startDate = ref('')
const endDate = ref('')
const minScore = ref(60)
const stage = ref('')

const loading = ref(false)
const error = ref(null)
const sectors = ref([])
const windowInfo = ref({ start_date: null, end_date: null })
const spaceLeadersLead = ref([])
const rotationHint = ref(null)
const rebuildingLeaders = ref(false)
const rebuildMessage = ref('')

const windowLabel = computed(() => {
  if (!windowInfo.value || !windowInfo.value.start_date || !windowInfo.value.end_date) {
    return '—'
  }
  if (windowInfo.value.start_date === windowInfo.value.end_date) {
    return windowInfo.value.start_date
  }
  return `${windowInfo.value.start_date} ~ ${windowInfo.value.end_date}`
})

/** 雷达列表：按强度降序取前 10 */
const filteredSectors = computed(() => {
  const list = [...(sectors.value || [])]
  list.sort((a, b) => (b.strength_score || 0) - (a.strength_score || 0))
  return list.slice(0, 10)
})

// 按股票分组：同一只股在多个主线为空间龙头时合并为一行，列出所属主线
const spaceLeadersByStock = computed(() => {
  const byCode = new Map()
  for (const item of spaceLeadersLead.value || []) {
    for (const stock of item.stocks || []) {
      const tc = stock.ts_code
      if (!tc) continue
      if (!byCode.has(tc)) {
        byCode.set(tc, {
          ts_code: tc,
          name: stock.name || tc,
          role_label: stock.role_label || '空间龙头',
          sectors: [],
        })
      }
      const name = stock.name || tc
      if (stock.name && !byCode.get(tc).name || byCode.get(tc).name === tc) byCode.get(tc).name = name
      if (item.sector_name && !byCode.get(tc).sectors.includes(item.sector_name)) {
        byCode.get(tc).sectors.push(item.sector_name)
      }
    }
  }
  return Array.from(byCode.values()).sort((a, b) => {
    const na = (a.sectors || []).length
    const nb = (b.sectors || []).length
    if (nb !== na) return nb - na
    return (a.name || '').localeCompare(b.name || '', 'zh-CN')
  })
})

// 各板块刚启动龙头（按股票分组，主题/板块越多越靠前）
const newLeadersByStock = computed(() => {
  const byCode = new Map()
  // 只从主线强度前 10 的板块中提取刚启动龙头
  for (const s of filteredSectors.value || []) {
    const chain = s.chain || []
    for (const c of chain) {
      if (!c.is_new_leader) continue
      const tc = c.ts_code
      if (!tc) continue
      if (!byCode.has(tc)) {
        byCode.set(tc, {
          ts_code: tc,
          name: c.name || tc,
          sectors: [],
        })
      }
      const list = byCode.get(tc).sectors
      if (s.sector_name && !list.includes(s.sector_name)) {
        list.push(s.sector_name)
      }
    }
  }
  return Array.from(byCode.values()).sort((a, b) => {
    const na = (a.sectors || []).length
    const nb = (b.sectors || []).length
    if (nb !== na) return nb - na
    return (a.name || '').localeCompare(b.name || '', 'zh-CN')
  })
})

const strengthPercent = (s) => {
  // 相对「当前雷达列表」中的最大强度归一化（与 filteredSectors 一致）
  const list = filteredSectors.value || []
  if (!list.length) return 0
  const maxStrength = Math.max(...list.map((x) => x.strength_score || 0))
  if (!maxStrength) return 0
  const ratio = (s.strength_score || 0) / maxStrength
  return Math.min(100, Math.max(8, ratio * 100))
}

// 判断是否为「指数 / 风格」类板块（如 标普道琼斯A股、MSCI 概念、富时罗素、中证指数 等）
const isIndexStyleSector = (s) => {
  if (!s) return false
  const name = (s.sector_name || '').toUpperCase()
  const keywords = ['标普', '道琼斯', 'MSCI', '富时', '罗素', '中证', '沪深300', '上证50', '指数', 'ETF']
  return keywords.some((k) => name.includes(k.toUpperCase()))
}

const resetRangeAndFetch = () => {
  // 清空日期，让后端走默认「最近 5 日」窗口
  startDate.value = ''
  endDate.value = ''
  fetchData()
}

const handleRebuildSectorLeaders = async () => {
  if (rebuildingLeaders.value) return
  if (!confirm('将按最近 30 个交易日，用 4+2 规则重算 rolling_30d_v2 的板块龙头快照。\n\n建议在盘后使用，过程可能耗时数十秒，确认继续？')) {
    return
  }
  rebuildingLeaders.value = true
  rebuildMessage.value = ''
  try {
    const params = {}
    if (endDate.value) params.end_date = endDate.value
    const res = await axios.post(`${API_BASE_URL}/api/data-management/sector-leaders/rebuild-v2`, null, {
      params,
    })
    const data = res.data || {}
    if (data.success) {
      rebuildMessage.value = data.data?.message || '板块龙头重建完成'
      // 重建后自动刷新一次主线数据
      fetchData()
    } else {
      rebuildMessage.value = data.detail || data.message || '板块龙头重建失败'
    }
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error(e)
    rebuildMessage.value = e?.response?.data?.detail || e?.message || '板块龙头重建失败'
  } finally {
    rebuildingLeaders.value = false
  }
}

const fetchData = async () => {
  loading.value = true
  error.value = null

  try {
    const params = {
      min_score: minScore.value,
    }
    if (startDate.value) params.start_date = startDate.value
    if (endDate.value) params.end_date = endDate.value
    if (stage.value) params.stage = stage.value

    const res = await axios.get(`${API_BASE_URL}/api/startup/sector-strength`, { params })
    const data = res.data || {}

    if (data.success === false) {
      error.value = data.message || '加载失败'
      sectors.value = []
      windowInfo.value = { start_date: null, end_date: null }
      spaceLeadersLead.value = []
      rotationHint.value = null
      return
    }

    sectors.value = data.sectors || []
    windowInfo.value = data.window || { start_date: null, end_date: null }
    spaceLeadersLead.value = data.space_leaders_lead || []

    // 明日轮动方向：用当前查询的 end_date（或窗口结束日）请求预判
    const hintDate = endDate.value || data.window?.end_date
    rotationHint.value = null
    if (hintDate) {
      try {
        const hintRes = await axios.get(`${API_BASE_URL}/api/startup/rotation-hint`, {
          params: {
            end_date: hintDate,
            start_date: startDate.value || undefined,
            min_score: minScore.value,
            stage: stage.value || undefined,
          },
        })
        rotationHint.value = hintRes.data || null
      } catch (e) {
        // 轮动预判失败不阻塞主流程，仅清空
        rotationHint.value = null
      }
    }
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error(e)
    error.value = e?.response?.data?.detail || e?.message || '请求失败'
    sectors.value = []
    windowInfo.value = { start_date: null, end_date: null }
    spaceLeadersLead.value = []
    rotationHint.value = null
  } finally {
    loading.value = false
  }
}

const openDiagnose = (tsCode) => {
  if (!tsCode) return
  router.push({ path: '/diagnose', query: { code: tsCode } })
}

onMounted(() => {
  resetRangeAndFetch()
})
</script>

<style scoped>
</style>

