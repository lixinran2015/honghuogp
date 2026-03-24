<template>
  <div class="tradingview-chart bg-white rounded-lg shadow overflow-hidden">
    <div class="flex items-center justify-between px-4 py-2 border-b border-gray-200">
      <h3 class="text-base font-semibold text-gray-800">TradingView 日K线</h3>
      <a
        v-if="tradingViewSymbol"
        :href="chartLink"
        target="_blank"
        rel="noopener noreferrer"
        class="text-xs text-blue-600 hover:underline"
      >
        在 TradingView 中打开
      </a>
    </div>
    <div class="w-full overflow-hidden" style="height: 450px">
      <!-- 使用官方 script 嵌入，结构需与文档一致 -->
      <div
        v-if="tradingViewSymbol"
        ref="containerRef"
        class="tradingview-widget-container"
        style="height: 100%; width: 100%"
      >
        <div class="tradingview-widget-container__widget" style="height: 100%; width: 100%"></div>
      </div>
      <div v-else class="h-full flex items-center justify-center text-gray-500 text-sm">
        请输入股票代码查看图表
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, computed, onBeforeUnmount, nextTick } from 'vue'
import { tsCodeToTradingView } from '../utils/tradingViewSymbol'

const props = defineProps({
  /** Tushare 股票代码，如 000788.SZ、600519.SH */
  tsCode: { type: String, default: '' }
})

const containerRef = ref(null)
let scriptEl = null

const tradingViewSymbol = ref('')

const chartLink = computed(() => {
  if (!tradingViewSymbol.value) return ''
  return `https://www.tradingview.com/symbols/${tradingViewSymbol.value.replace(':', '-')}/`
})

function loadWidget() {
  if (!containerRef.value || !tradingViewSymbol.value) return

  const container = containerRef.value
  if (scriptEl && scriptEl.parentNode) {
    scriptEl.parentNode.removeChild(scriptEl)
    scriptEl = null
  }

  scriptEl = document.createElement('script')
  scriptEl.src = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js'
  scriptEl.type = 'text/javascript'
  scriptEl.async = true
  scriptEl.textContent = JSON.stringify({
    autosize: true,
    symbol: tradingViewSymbol.value,
    interval: 'D',
    timezone: 'Asia/Shanghai',
    theme: 'light',
    style: '1',
    locale: 'zh',
    hide_top_toolbar: false,
    save_image: false,
    calendar: false,
    support_host: 'https://www.tradingview.com'
  })
  container.appendChild(scriptEl)
}

watch(
  () => props.tsCode,
  (val) => {
    tradingViewSymbol.value = tsCodeToTradingView(val || '')
  },
  { immediate: true }
)

watch(tradingViewSymbol, (sym) => {
  if (sym) nextTick(loadWidget)
}, { immediate: true })

onBeforeUnmount(() => {
  if (scriptEl?.parentNode) {
    scriptEl.parentNode.removeChild(scriptEl)
  }
})
</script>
