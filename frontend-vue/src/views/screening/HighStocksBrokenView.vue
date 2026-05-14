<template>
  <div class="p-8 space-y-6">
    <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
      <div>
        <h1 class="text-2xl font-semibold text-gray-900 dark:text-gray-100 mb-2">已破线股票</h1>
        <p class="text-sm text-gray-500 dark:text-gray-400">从 180 日新高监控中清理出的破 10 日线股票，站稳 10 日线后可移回监控</p>
      </div>
      <router-link
        to="/high-stocks"
        class="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-primary-600 text-white hover:bg-primary-700 transition-colors"
      >
        返回监控页
      </router-link>
    </div>

    <div v-if="loading" class="py-12 text-center text-gray-500">加载中...</div>
    <div v-else-if="list.length === 0" class="py-12 text-center text-gray-500">
      <p>暂无已破线股票</p>
      <p class="mt-2 text-sm">在「180日新高」监控页点击「一键清理破线」后，破线股票会出现在此处</p>
    </div>
    <div v-else class="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
      <table class="w-full">
        <thead class="bg-gray-50 dark:bg-gray-700/50">
          <tr>
            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">代码</th>
            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">名称</th>
            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">行业</th>
            <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">现价</th>
            <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">10日线</th>
            <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">状态</th>
            <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">破线日</th>
            <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">操作</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-200 dark:divide-gray-700">
          <tr
            v-for="s in list"
            :key="s.ts_code"
            class="hover:bg-gray-50 dark:hover:bg-gray-700/50"
          >
            <td class="px-4 py-3 text-sm font-medium text-gray-900 dark:text-gray-100">{{ s.code }}</td>
            <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ s.name || '--' }}</td>
            <td class="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">{{ s.industry || '--' }}</td>
            <td class="px-4 py-3 text-sm text-right font-medium">{{ s.price != null ? s.price.toFixed(2) : '--' }}</td>
            <td class="px-4 py-3 text-sm text-right">{{ s.ma10 != null ? s.ma10.toFixed(2) : '--' }}</td>
            <td class="px-4 py-3 text-center">
              <span v-if="s.below_ma10" class="text-red-600 dark:text-red-400 text-xs">仍破线</span>
              <span v-else class="text-green-600 dark:text-green-400 text-xs font-medium">已站稳</span>
            </td>
            <td class="px-4 py-3 text-center text-xs text-gray-500 dark:text-gray-400">{{ s.broken_date || '--' }}</td>
            <td class="px-4 py-3 text-center">
              <button
                v-if="!s.below_ma10"
                type="button"
                @click="restore(s)"
                :disabled="restoring === s.ts_code"
                class="text-sm text-primary-600 dark:text-primary-400 hover:underline disabled:opacity-50"
              >
                {{ restoring === s.ts_code ? '处理中...' : '移回监控' }}
              </button>
              <span v-else class="text-xs text-gray-400">站稳后可移回</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''
const list = ref([])
const loading = ref(false)
const restoring = ref(null)

async function fetchList() {
  loading.value = true
  try {
    const res = await axios.get(`${API_BASE}/api/stock-universe/high_180d/broken`)
    if (res.data?.success) {
      list.value = (res.data.data || []).map(s => ({
        ...s,
        code: s.code || (s.ts_code ? s.ts_code.split('.')[0] : ''),
      }))
    }
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

async function restore(s) {
  if (!confirm(`确定将 ${s.name || s.ts_code} 移回 180 日新高监控吗？`)) return
  restoring.value = s.ts_code
  try {
    const res = await axios.post(`${API_BASE}/api/stock-universe/high_180d/restore`, null, {
      params: { ts_code: s.ts_code },
    })
    if (res.data?.success) {
      list.value = list.value.filter(x => x.ts_code !== s.ts_code)
    } else {
      alert(res.data?.message || '移回失败')
    }
  } catch (e) {
    alert('移回失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    restoring.value = null
  }
}

onMounted(() => {
  fetchList()
})
</script>
