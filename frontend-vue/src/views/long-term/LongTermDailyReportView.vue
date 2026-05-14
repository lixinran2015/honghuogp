<template>
  <div class="p-4 lg:p-6 bg-warm-50 min-h-screen">
    <!-- 标题栏 -->
    <div class="mb-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
      <div>
        <h1 class="text-xl font-bold text-warmgray-900">长线投资日报</h1>
        <p class="text-sm text-warmgray-500 mt-1">
          每日自动生成 · 数据展示仅供参考
        </p>
      </div>
      <div class="flex items-center gap-3">
        <input
          v-model="selectedDate"
          type="date"
          class="px-3 py-2 rounded-md border border-border bg-white text-sm text-warmgray-700 focus:outline-none focus:ring-2 focus:ring-cta/50"
        />
        <button
          class="px-4 py-2 rounded-md text-sm font-medium text-warmgray-900 bg-cta hover:bg-cta-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          :disabled="loading || generating"
          @click="loadReport"
        >
          加载日报
        </button>
        <button
          class="px-4 py-2 rounded-md text-sm font-medium text-white bg-warmgray-800 hover:bg-warmgray-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          :disabled="loading || generating"
          @click="generateReport"
        >
          <span v-if="generating" class="inline-flex items-center gap-1">
            <span class="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
            生成中...
          </span>
          <span v-else>生成日报</span>
        </button>
      </div>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading" class="flex items-center justify-center py-20">
      <div class="w-8 h-8 border-2 border-cta border-t-transparent rounded-full animate-spin"></div>
      <span class="ml-3 text-sm text-warmgray-500">正在加载日报...</span>
    </div>

    <!-- 错误提示 -->
    <div
      v-else-if="error"
      class="bg-loss/10 border border-loss/30 text-loss text-sm px-4 py-3 rounded-lg"
    >
      {{ error }}
    </div>

    <!-- 日报内容 -->
    <div
      v-else-if="htmlReport"
      class="bg-white rounded-xl border border-border shadow-sm p-6 lg:p-10"
    >
      <article
        class="prose prose-stone max-w-none prose-headings:text-warmgray-900 prose-p:text-warmgray-700 prose-strong:text-warmgray-900 prose-table:text-sm prose-th:bg-warm-100 prose-th:font-semibold prose-td:border-border prose-tr:border-border"
        v-html="htmlReport"
      />
    </div>

    <!-- 空状态 -->
    <div v-else class="text-center py-20 text-warmgray-400 text-sm">
      请选择日期并加载日报
    </div>

    <!-- 固定免责声明 -->
    <div class="mt-6 text-xs text-warmgray-400 text-center">
      本内容仅为数据整理与个人研究记录，不构成任何投资建议。股市有风险，入市需谨慎。
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

const selectedDate = ref(new Date().toISOString().split('T')[0])
const htmlReport = ref('')
const reportDate = ref('')
const loading = ref(false)
const generating = ref(false)
const error = ref('')

async function loadReport() {
  loading.value = true
  error.value = ''
  htmlReport.value = ''

  try {
    const dateStr = selectedDate.value
    const response = await fetch(`${API_BASE_URL}/api/long-term/daily-report?trade_date=${dateStr}`)
    if (!response.ok) {
      if (response.status === 404) {
        throw new Error(`未找到 ${dateStr} 的日报，请先生成。`)
      }
      throw new Error(`HTTP ${response.status}`)
    }
    const result = await response.json()
    const data = result.data || {}
    htmlReport.value = data.html_report || ''
    reportDate.value = data.report_date || dateStr
  } catch (e) {
    console.error('日报加载失败:', e)
    error.value = e.message || '加载日报失败'
  } finally {
    loading.value = false
  }
}

async function generateReport() {
  if (!confirm('生成长线日报需要调用数据接口和AI服务，耗时约 10-30 秒，是否继续？')) {
    return
  }
  generating.value = true
  error.value = ''
  htmlReport.value = ''

  try {
    const dateStr = selectedDate.value
    const response = await fetch(`${API_BASE_URL}/api/long-term/daily-report/generate?trade_date=${dateStr}`, {
      method: 'POST',
    })
    const result = await response.json()
    if (!response.ok || !result.success) {
      throw new Error(result.detail || result.message || '生成日报失败')
    }
    const tradeDate = result.data?.report_date
    if (tradeDate) {
      selectedDate.value = tradeDate
    }
    await loadReport()
  } catch (e) {
    console.error('日报生成失败:', e)
    error.value = e.message || '生成日报失败'
  } finally {
    generating.value = false
  }
}

onMounted(() => {
  loadReport()
})
</script>
