<template>
  <div class="container mx-auto px-4 py-6">
    <div class="mb-6">
      <h1 class="text-2xl font-bold text-gray-800">龙头买点离线回测任务</h1>
      <p class="text-sm text-gray-500 mt-1">
        查看最近多次离线回测任务的区间、规则版本与更新时间，便于排查问题与对齐口径。
      </p>
    </div>

    <div class="bg-white rounded-xl shadow border border-gray-100 p-4 mb-4 space-y-4">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="text-xs text-gray-500">
          共 {{ items.length }} 条记录（按更新时间倒序）
        </div>
        <div class="flex flex-wrap items-center gap-2 text-xs">
          <div class="flex items-center gap-1">
            <span class="text-gray-500">回测开始</span>
            <input
              v-model="startDate"
              type="date"
              class="px-2 py-1 border border-gray-300 rounded-md text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500"
            />
          </div>
          <div class="flex items-center gap-1">
            <span class="text-gray-500">回测结束</span>
            <input
              v-model="endDate"
              type="date"
              class="px-2 py-1 border border-gray-300 rounded-md text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500"
            />
          </div>
          <button
            type="button"
            class="px-3 py-1.5 rounded-md text-xs font-medium text-indigo-700 bg-indigo-50 border border-indigo-200 hover:bg-indigo-100 disabled:opacity-60"
            :disabled="running || loading"
            @click="triggerOfflineRun"
          >
            {{ running ? '回测运行中...' : '手动执行离线回测' }}
          </button>
          <button
            type="button"
            class="px-3 py-1.5 rounded-md text-xs font-medium text-gray-700 bg-gray-50 border border-gray-200 hover:bg-gray-100 disabled:opacity-60"
            :disabled="loading"
            @click="fetchHistory"
          >
            {{ loading ? '刷新中...' : '刷新' }}
          </button>
        </div>
      </div>

      <div v-if="error" class="mb-3 text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
        {{ error }}
      </div>

      <div v-if="!loading && !error && items.length === 0" class="text-sm text-gray-500">
        暂无离线回测元信息记录，可以通过上方按钮手动执行一次离线回测任务。
      </div>

      <div v-if="items.length > 0" class="overflow-x-auto">
        <table class="min-w-full text-xs">
          <thead class="bg-gray-50 text-gray-500 border-b border-gray-100">
            <tr>
              <th class="px-2 py-2 text-left">ID</th>
              <th class="px-2 py-2 text-left">回测区间</th>
              <th class="px-2 py-2 text-left">规则版本</th>
              <th class="px-2 py-2 text-left">最近更新时间</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in items"
              :key="row.id"
              class="border-b border-gray-50 hover:bg-gray-50"
            >
              <td class="px-2 py-1 text-gray-500">
                {{ row.id }}
              </td>
              <td class="px-2 py-1 text-gray-800">
                {{ row.last_run_start_date }} ~ {{ row.last_run_end_date }}
              </td>
              <td class="px-2 py-1 text-gray-800">
                {{ row.rule_version || '--' }}
              </td>
              <td class="px-2 py-1 text-gray-600">
                {{ formatDateTime(row.updated_at) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="mt-4 text-[11px] text-gray-400">
        数据来源：data warehouse 中的 <code class="font-mono text-[11px] bg-gray-100 px-1 py-0.5 rounded">bt_leader_buy_meta</code> 表，
        由离线回测脚本 <code class="font-mono text-[11px] bg-gray-100 px-1 py-0.5 rounded">run_offline_leader_buy_backtest</code> 在每次运行后写入。
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

const loading = ref(false)
const error = ref(null)
const items = ref([])
const running = ref(false)

const today = new Date()
const oneYearAgo = new Date()
oneYearAgo.setFullYear(today.getFullYear() - 1)

const formatDate = (d) => d.toISOString().slice(0, 10)

const startDate = ref(formatDate(oneYearAgo))
const endDate = ref(formatDate(today))

const formatDateTime = (v) => {
  if (!v) return '--'
  // v 形如 2026-03-16T12:34:56.123456
  const s = String(v)
  return s.replace('T', ' ').slice(0, 19)
}

const fetchHistory = async () => {
  loading.value = true
  error.value = null
  try {
    const res = await axios.get(`${API_BASE_URL}/api/startup/leader-buy-backtest/meta/history`, {
      params: { limit: 20 },
    })
    const data = res.data || {}
    if (!data.success) {
      error.value = data.message || data.detail || '加载失败'
      items.value = []
      return
    }
    items.value = data.items || []
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error(e)
    error.value = e?.response?.data?.detail || e?.message || '请求失败'
    items.value = []
  } finally {
    loading.value = false
  }
}

const triggerOfflineRun = async () => {
  if (running.value) return
  error.value = null
  running.value = true
  try {
    const params = {
      start_date: startDate.value,
      end_date: endDate.value,
      // 其他参数使用后端默认值：min_strength=4.0, top_n_sectors=10, include_left_signals=True, window_days=60
    }
    const res = await axios.post(`${API_BASE_URL}/api/startup/leader-buy-backtest/offline-run`, null, {
      params,
    })
    const data = res.data || {}
    if (!data.success) {
      error.value = data.message || data.detail || '离线回测执行失败'
      return
    }
    // 执行成功后刷新一次历史记录
    await fetchHistory()
    // eslint-disable-next-line no-alert
    alert('离线回测任务已执行完成，元信息已更新。')
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error(e)
    error.value = e?.response?.data?.detail || e?.message || '离线回测执行失败'
  } finally {
    running.value = false
  }
}

onMounted(() => {
  fetchHistory()
})
</script>

<style scoped>
</style>

