<template>
  <div
    v-if="isOpen"
    class="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"
    @click.self="close"
  >
    <div class="bg-white rounded-lg shadow-xl max-w-4xl w-full mx-4 max-h-[90vh] overflow-hidden flex flex-col">
      <!-- 头部 -->
      <div class="flex items-center justify-between p-6 border-b border-gray-200">
        <h2 class="text-2xl font-semibold text-gray-900">欢迎使用智能选股系统</h2>
        <button
          @click="close"
          class="text-gray-400 hover:text-gray-600 transition-colors"
        >
          <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <!-- 内容区域（可滚动） -->
      <div class="flex-1 overflow-y-auto p-6">
        <div class="space-y-6">
          <!-- 系统介绍 -->
          <section>
            <h3 class="text-lg font-semibold text-gray-900 mb-3 flex items-center">
              <span class="mr-2">📊</span>
              系统介绍
            </h3>
            <p class="text-gray-600 leading-relaxed">
              智能选股系统是一个基于量化策略的股票筛选和分析平台，提供多种策略引擎、实时数据监控和智能推荐功能。
              系统通过财务分析、技术指标、量价关系等多维度数据，帮助您做出更明智的投资决策。
            </p>
          </section>

          <!-- 主要功能 -->
          <section>
            <h3 class="text-lg font-semibold text-gray-900 mb-3 flex items-center">
              <span class="mr-2">✨</span>
              主要功能
            </h3>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div class="p-4 bg-blue-50 rounded-lg border border-blue-200">
                <h4 class="font-semibold text-blue-900 mb-2">操作池</h4>
                <p class="text-sm text-blue-700">管理您的持仓股票，查看盈亏情况、操作建议和风险等级</p>
              </div>
              <div class="p-4 bg-green-50 rounded-lg border border-green-200">
                <h4 class="font-semibold text-green-900 mb-2">推荐选股</h4>
                <p class="text-sm text-green-700">基于多种策略（达尔文、波段、短线）的智能股票推荐</p>
              </div>
              <div class="p-4 bg-yellow-50 rounded-lg border border-yellow-200">
                <h4 class="font-semibold text-yellow-900 mb-2">月度热点</h4>
                <p class="text-sm text-yellow-700">分析板块热度和轮动趋势，发现市场机会</p>
              </div>
              <div class="p-4 bg-purple-50 rounded-lg border border-purple-200">
                <h4 class="font-semibold text-purple-900 mb-2">达尔文评分</h4>
                <p class="text-sm text-purple-700">基于财务质量的长期投资评分系统</p>
              </div>
              <div class="p-4 bg-indigo-50 rounded-lg border border-indigo-200">
                <h4 class="font-semibold text-indigo-900 mb-2">策略引擎</h4>
                <p class="text-sm text-indigo-700">查看各种量化策略的详细说明和操作依据</p>
              </div>
              <div class="p-4 bg-pink-50 rounded-lg border border-pink-200">
                <h4 class="font-semibold text-pink-900 mb-2">数据管理</h4>
                <p class="text-sm text-pink-700">监控数据源健康状态、数据质量和任务执行情况</p>
              </div>
            </div>
          </section>

          <!-- 操作说明 -->
          <section>
            <h3 class="text-lg font-semibold text-gray-900 mb-3 flex items-center">
              <span class="mr-2">📖</span>
              操作说明
            </h3>
            <div class="space-y-3">
              <div class="flex items-start">
                <span class="text-blue-600 font-semibold mr-3">1.</span>
                <div>
                  <p class="font-medium text-gray-900">查看推荐股票</p>
                  <p class="text-sm text-gray-600">在"推荐选股"页面，系统会根据多种策略为您推荐股票，包括达尔文长期策略、波段回踩策略和短线动量策略</p>
                </div>
              </div>
              <div class="flex items-start">
                <span class="text-blue-600 font-semibold mr-3">2.</span>
                <div>
                  <p class="font-medium text-gray-900">管理持仓</p>
                  <p class="text-sm text-gray-600">在"操作池"页面添加您的持仓股票，系统会自动计算盈亏、提供操作建议（买入/加仓/减仓/清仓）</p>
                </div>
              </div>
              <div class="flex items-start">
                <span class="text-blue-600 font-semibold mr-3">3.</span>
                <div>
                  <p class="font-medium text-gray-900">分析板块热度</p>
                  <p class="text-sm text-gray-600">在"月度热点"页面查看板块热度变化趋势，发现热门板块和投资机会</p>
                </div>
              </div>
              <div class="flex items-start">
                <span class="text-blue-600 font-semibold mr-3">4.</span>
                <div>
                  <p class="font-medium text-gray-900">查看策略详情</p>
                  <p class="text-sm text-gray-600">在"策略引擎"页面了解各种策略的筛选逻辑、操作依据和评分公式</p>
                </div>
              </div>
              <div class="flex items-start">
                <span class="text-blue-600 font-semibold mr-3">5.</span>
                <div>
                  <p class="font-medium text-gray-900">监控数据质量</p>
                  <p class="text-sm text-gray-600">在"数据管理"页面查看数据源状态、数据完整性和任务执行情况</p>
                </div>
              </div>
            </div>
          </section>

          <!-- 操作建议说明 -->
          <section>
            <h3 class="text-lg font-semibold text-gray-900 mb-3 flex items-center">
              <span class="mr-2">💡</span>
              操作建议说明
            </h3>
            <div class="bg-gray-50 p-4 rounded-lg border border-gray-200">
              <p class="text-sm text-gray-700 mb-3">
                系统会根据策略信号、量价形态、追高风险等级、盈亏比例等多维度因素，为您提供操作建议：建仓单次约1/3仓位；加仓控制单票比例、浮亏近-5%跌破均线不宜再加；减仓区分止盈型（可保留底仓）与风控型；亏损-8%可先减半仓再观察，趋势反转宜清仓。
              </p>
              <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div class="text-center">
                  <div class="inline-block px-3 py-1 bg-green-100 text-green-700 rounded text-xs font-semibold mb-1">买入</div>
                  <p class="text-xs text-gray-600">追高风险低，单次建仓约1/3</p>
                </div>
                <div class="text-center">
                  <div class="inline-block px-3 py-1 bg-blue-100 text-blue-700 rounded text-xs font-semibold mb-1">加仓</div>
                  <p class="text-xs text-gray-600">已有持仓、趋势延续，控单票比例</p>
                </div>
                <div class="text-center">
                  <div class="inline-block px-3 py-1 bg-yellow-100 text-yellow-700 rounded text-xs font-semibold mb-1">减仓</div>
                  <p class="text-xs text-gray-600">止盈/风控型，可保留底仓</p>
                </div>
                <div class="text-center">
                  <div class="inline-block px-3 py-1 bg-red-100 text-red-700 rounded text-xs font-semibold mb-1">清仓</div>
                  <p class="text-xs text-gray-600">-8%可先减半再清，趋势反转止损</p>
                </div>
              </div>
            </div>
          </section>

          <!-- 注意事项 -->
          <section>
            <h3 class="text-lg font-semibold text-gray-900 mb-3 flex items-center">
              <span class="mr-2">⚠️</span>
              注意事项
            </h3>
            <ul class="space-y-2 text-sm text-gray-600">
              <li class="flex items-start">
                <span class="text-red-500 mr-2">•</span>
                <span>本系统提供的所有信息仅供参考，不构成投资建议，投资有风险，入市需谨慎</span>
              </li>
              <li class="flex items-start">
                <span class="text-red-500 mr-2">•</span>
                <span>建议结合市场环境、个人风险承受能力和投资目标做出决策</span>
              </li>
              <li class="flex items-start">
                <span class="text-red-500 mr-2">•</span>
                <span>数据更新可能存在延迟，请以实际交易数据为准</span>
              </li>
              <li class="flex items-start">
                <span class="text-red-500 mr-2">•</span>
                <span>定期刷新数据以获取最新信息，右上角提供全局刷新功能</span>
              </li>
            </ul>
          </section>
        </div>
      </div>

      <!-- 底部按钮 -->
      <div class="p-6 border-t border-gray-200 flex justify-end">
        <button
          @click="close"
          class="px-4 py-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600 transition-colors"
        >
          我知道了
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  isOpen: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['close'])

const close = () => {
  emit('close')
}
</script>

