<template>
  <div class="p-4 lg:p-6 bg-warm-50 min-h-screen">
    <!-- 标题栏 -->
    <div class="mb-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
      <div>
        <h1 class="text-xl font-bold text-warmgray-900">A股短线龙头日报</h1>
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
          class="px-4 py-2 rounded-md text-sm font-medium text-warmgray-900 bg-cta hover:bg-cta-hover transition-colors"
          @click="loadReport"
        >
          加载日报
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
      v-else-if="htmlContent"
      class="bg-white rounded-xl border border-border shadow-sm p-6 lg:p-10"
    >
      <article
        class="prose prose-stone max-w-none prose-headings:text-warmgray-900 prose-p:text-warmgray-700 prose-strong:text-warmgray-900 prose-table:text-sm prose-th:bg-warm-100 prose-th:font-semibold prose-td:border-border prose-tr:border-border"
        v-html="htmlContent"
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

const selectedDate = ref(new Date().toISOString().split('T')[0])
const htmlContent = ref('')
const loading = ref(false)
const error = ref('')

async function loadReport() {
  loading.value = true
  error.value = ''
  htmlContent.value = ''

  try {
    const dateStr = selectedDate.value
    const res = await fetch(`/daily-reports/${dateStr}.html`)
    if (!res.ok) {
      throw new Error(`未找到 ${dateStr} 的日报，请确认该日期已生成。`)
    }
    const html = await res.text()
    htmlContent.value = html
  } catch (e) {
    error.value = e.message || '加载日报失败'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadReport()
})
</script>
