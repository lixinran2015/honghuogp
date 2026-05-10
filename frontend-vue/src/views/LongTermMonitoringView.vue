<template>
  <div class="p-4 lg:p-6 bg-warm-50 min-h-screen">
    <!-- 标题区 -->
    <div class="mb-6 flex items-center justify-between flex-wrap gap-3">
      <div>
        <h1 class="text-xl font-bold text-warmgray-900">持仓监控</h1>
        <p class="text-sm text-warmgray-500 mt-1">基本面红线、估值告警与外资动向监控</p>
      </div>
      <div class="flex items-center gap-2">
        <button
          @click="scanHoldings"
          :disabled="scanning"
          class="px-4 py-1.5 bg-cta text-white text-sm font-medium rounded-md hover:bg-cta/90 disabled:opacity-50 transition-colors"
        >
          {{ scanning ? '扫描中...' : '手动扫描' }}
        </button>
      </div>
    </div>

    <!-- 告警统计 -->
    <div class="mb-4 grid grid-cols-3 gap-3">
      <div class="bg-white rounded-lg border border-border p-3">
        <div class="text-xs text-warmgray-500">CRITICAL</div>
        <div class="text-lg font-semibold text-loss">{{ alertCounts.CRITICAL }}</div>
      </div>
      <div class="bg-white rounded-lg border border-border p-3">
        <div class="text-xs text-warmgray-500">WARNING</div>
        <div class="text-lg font-semibold text-cta">{{ alertCounts.WARNING }}</div>
      </div>
      <div class="bg-white rounded-lg border border-border p-3">
        <div class="text-xs text-warmgray-500">NOTICE</div>
        <div class="text-lg font-semibold text-warmgray-700">{{ alertCounts.NOTICE }}</div>
      </div>
    </div>

    <!-- 告警列表 -->
    <div class="bg-white rounded-lg border border-border overflow-hidden">
      <div class="px-4 py-3 border-b border-border bg-warmgray-50 flex items-center justify-between">
        <h3 class="text-sm font-semibold text-warmgray-700">告警列表</h3>
        <div class="flex items-center gap-2">
          <select
            v-model="filterLevel"
            class="px-2 py-1 text-xs border border-border rounded bg-white"
          >
            <option value="">全部级别</option>
            <option value="CRITICAL">CRITICAL</option>
            <option value="WARNING">WARNING</option>
            <option value="NOTICE">NOTICE</option>
          </select>
          <button
            @click="fetchAlerts"
            class="px-2 py-1 text-xs bg-warm-100 text-warmgray-600 rounded hover:bg-warm-200"
          >
            刷新
          </button>
        </div>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="bg-warmgray-50 border-b border-border">
              <th class="px-4 py-3 text-left font-semibold text-warmgray-700">股票</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">级别</th>
              <th class="px-4 py-3 text-left font-semibold text-warmgray-700">类型</th>
              <th class="px-4 py-3 text-left font-semibold text-warmgray-700">内容</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">指标值</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">时间</th>
              <th class="px-4 py-3 text-center font-semibold text-warmgray-700">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="alert in filteredAlerts"
              :key="alert.id"
              class="border-b border-border hover:bg-warm-50 transition-colors"
            >
              <td class="px-4 py-3 font-medium text-warmgray-900">{{ alert.ts_code }}</td>
              <td class="px-4 py-3 text-center">
                <span
                  class="px-2 py-0.5 rounded text-xs font-medium"
                  :class="levelClass(alert.level)"
                >
                  {{ alert.level }}
                </span>
              </td>
              <td class="px-4 py-3 text-warmgray-600">{{ alert.alert_type }}</td>
              <td class="px-4 py-3 text-warmgray-700">{{ alert.message }}</td>
              <td class="px-4 py-3 text-center text-warmgray-600">
                <span v-if="alert.metric_value != null">
                  {{ alert.metric_value }}
                  <span v-if="alert.threshold_value != null" class="text-warmgray-400">/ {{ alert.threshold_value }}</span>
                </span>
                <span v-else>-</span>
              </td>
              <td class="px-4 py-3 text-center text-xs text-warmgray-500">{{ formatDate(alert.created_at) }}</td>
              <td class="px-4 py-3 text-center">
                <button
                  v-if="!alert.is_resolved"
                  @click="resolveAlert(alert.id)"
                  class="px-2 py-1 text-xs bg-profit/10 text-profit rounded hover:bg-profit/20"
                >
                  解决
                </button>
                <span v-else class="text-xs text-warmgray-400">已解决</span>
              </td>
            </tr>
            <tr v-if="filteredAlerts.length === 0">
              <td colspan="7" class="px-4 py-8 text-center text-warmgray-500">
                {{ loading ? '加载中...' : '暂无告警' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

const loading = ref(false)
const scanning = ref(false)
const alerts = ref([])
const filterLevel = ref('')

const alertCounts = computed(() => {
  const counts = { CRITICAL: 0, WARNING: 0, NOTICE: 0 }
  for (const a of alerts.value) {
    if (!a.is_resolved && counts[a.level] != null) {
      counts[a.level]++
    }
  }
  return counts
})

const filteredAlerts = computed(() => {
  let result = alerts.value.filter(a => !a.is_resolved)
  if (filterLevel.value) {
    result = result.filter(a => a.level === filterLevel.value)
  }
  return result
})

async function fetchAlerts() {
  loading.value = true
  try {
    const response = await fetch(`${API_BASE_URL}/api/long-term/monitoring/alerts?is_resolved=false&limit=100`)
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const result = await response.json()
    alerts.value = result.alerts || []
  } catch (e) {
    console.error('告警数据获取失败:', e)
  } finally {
    loading.value = false
  }
}

async function scanHoldings() {
  scanning.value = true
  try {
    const response = await fetch(`${API_BASE_URL}/api/long-term/monitoring/scan`, { method: 'POST' })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const result = await response.json()
    console.log('扫描结果:', result)
    await fetchAlerts()
  } catch (e) {
    console.error('持仓扫描失败:', e)
  } finally {
    scanning.value = false
  }
}

async function resolveAlert(alertId) {
  try {
    const response = await fetch(`${API_BASE_URL}/api/long-term/monitoring/alerts/${alertId}/resolve`, {
      method: 'POST',
    })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    await fetchAlerts()
  } catch (e) {
    console.error('解决告警失败:', e)
  }
}

function levelClass(level) {
  const map = {
    'CRITICAL': 'bg-loss/10 text-loss',
    'WARNING': 'bg-cta/10 text-cta',
    'NOTICE': 'bg-warm-100 text-warmgray-600',
  }
  return map[level] || 'bg-warm-100 text-warmgray-600'
}

function formatDate(dateStr) {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${d.getMinutes().toString().padStart(2, '0')}`
}

onMounted(() => {
  fetchAlerts()
})
</script>
