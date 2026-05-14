<template>
  <div class="container mx-auto px-4 py-6">
    <!-- 页面标题 -->
    <div class="mb-6">
      <h1 class="text-2xl font-bold text-gray-800">启动策略回测中心</h1>
      <p class="text-sm text-gray-500 mt-1">
        统一从「整体策略表现」和「历史启动样本」两个视角，评估你的启动龙头体系。
      </p>
    </div>

    <!-- 顶部 Tab 切换 -->
    <div class="bg-white rounded-xl shadow border border-gray-100 mb-6">
      <div class="border-b border-gray-100 px-4 pt-3">
        <nav class="flex space-x-4" aria-label="Tabs">
          <button
            type="button"
            class="px-3 pb-3 text-sm font-medium border-b-2"
            :class="
              activeTab === 'overall'
                ? 'border-indigo-500 text-indigo-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            "
            @click="activeTab = 'overall'"
          >
            启动策略整体回测
          </button>
          <button
            type="button"
            class="px-3 pb-3 text-sm font-medium border-b-2"
            :class="
              activeTab === 'signals'
                ? 'border-indigo-500 text-indigo-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            "
            @click="activeTab = 'signals'"
          >
            历史信号 & 数据工具
          </button>
        </nav>
      </div>

      <!-- Tab 内容 -->
      <div class="p-4 lg:p-6">
        <div v-if="activeTab === 'overall'">
          <p class="text-xs text-gray-500 mb-3">
            基于历史启动信号，按统一交易计划（买入价 / 止损价 / 第一目标价）评估策略整体收益、胜率与「按计划执行 vs 实际结果」情况。
          </p>
          <StartupOverallBacktestPanel />
        </div>

        <div v-else>
          <p class="text-xs text-gray-500 mb-3">
            管理已启动信号的历史样本：检查缺少条件、回填历史数据、批量金叉计算，以及按时间段查看启动信号列表，给整体回测提供更干净的数据基础。
          </p>
          <StartupSignalsAndBackfillPanel />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import StartupOverallBacktestPanel from '@/components/startup/StartupOverallBacktestPanel.vue'
import StartupSignalsAndBackfillPanel from '@/components/startup/StartupSignalsAndBackfillPanel.vue'

const activeTab = ref('overall') // 'overall' | 'signals'
</script>

<style scoped>
</style>

