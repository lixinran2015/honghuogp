<template>
  <div class="container mx-auto px-4 py-6">
    <!-- 检查缺少条件功能 -->
    <div class="bg-white rounded-lg shadow-md p-6 mb-6">
      <h2 class="text-lg font-semibold text-gray-700 mb-4">🔍 检查缺少条件</h2>
      <p class="text-sm text-gray-500 mb-4">
        对所有非完全启动的股票进行检查，查看后续是否满足条件。每个交易日会检查前5个交易日内所有非完全启动的股票（stage !=
        'started'）。对于满足2/3条件的股票，限制：离金叉日期不超过5个交易日。
      </p>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        <!-- 开始日期 -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">开始日期</label>
          <input
            v-model="checkMissingParams.start_date"
            type="date"
            class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        <!-- 结束日期 -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">结束日期</label>
          <input
            v-model="checkMissingParams.end_date"
            type="date"
            class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        <!-- 最大交易日数 -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1"
            >最大交易日数（距离金叉）</label
          >
          <input
            v-model.number="checkMissingParams.max_trading_days"
            type="number"
            min="1"
            max="10"
            class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="5"
          />
        </div>

        <!-- 批次大小 -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">批次大小</label>
          <input
            v-model.number="checkMissingParams.batch_size"
            type="number"
            min="10"
            max="200"
            class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="50"
          />
        </div>
      </div>

      <!-- 操作按钮 -->
      <div class="flex gap-3">
        <button
          @click="checkMissingConditions"
          :disabled="checkingMissing"
          class="px-6 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center space-x-2"
        >
          <span v-if="checkingMissing">检查中...</span>
          <span v-else>🔍 开始检查缺少条件</span>
        </button>
      </div>

      <!-- 检查结果 -->
      <div v-if="checkMissingResult" class="mt-4 p-4 bg-gray-50 rounded-lg">
        <div class="text-sm font-semibold text-gray-700 mb-2">
          {{ checkMissingResult.message }}
        </div>
        <div class="grid grid-cols-2 md:grid-cols-5 gap-4 text-sm">
          <div>
            <div class="text-gray-500">交易日数</div>
            <div class="text-lg font-semibold text-gray-900">
              {{ checkMissingResult.trading_days_count || 0 }}
            </div>
          </div>
          <div>
            <div class="text-gray-500">总数</div>
            <div class="text-lg font-semibold text-gray-900">
              {{ checkMissingResult.total || 0 }}
            </div>
          </div>
          <div>
            <div class="text-gray-500">已检查</div>
            <div class="text-lg font-semibold text-blue-600">
              {{ checkMissingResult.checked || 0 }}
            </div>
          </div>
          <div>
            <div class="text-gray-500">已跳过</div>
            <div class="text-lg font-semibold text-yellow-600">
              {{ checkMissingResult.skipped || 0 }}
            </div>
          </div>
          <div>
            <div class="text-gray-500">已更新</div>
            <div class="text-lg font-semibold text-green-600">
              {{ checkMissingResult.updated || 0 }}
            </div>
          </div>
        </div>

        <!-- 按日期统计 -->
        <div
          v-if="checkMissingResult.by_date && Object.keys(checkMissingResult.by_date).length > 0"
          class="mt-4 pt-4 border-t border-gray-200"
        >
          <div class="text-sm font-semibold text-gray-700 mb-2">
            按日期统计（显示前
            {{ Math.min(Object.keys(checkMissingResult.by_date).length, 20) }} 个交易日）：
          </div>
          <div class="max-h-60 overflow-y-auto">
            <table class="min-w-full text-xs">
              <thead class="bg-gray-100">
                <tr>
                  <th class="px-2 py-1 text-left">日期</th>
                  <th class="px-2 py-1 text-center">总数</th>
                  <th class="px-2 py-1 text-center">已检查</th>
                  <th class="px-2 py-1 text-center">已跳过</th>
                  <th class="px-2 py-1 text-center">已更新</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-200">
                <tr
                  v-for="(stats, date) in Object.entries(checkMissingResult.by_date).slice(0, 20)"
                  :key="date"
                >
                  <td class="px-2 py-1">{{ date }}</td>
                  <td class="px-2 py-1 text-center">{{ stats.total }}</td>
                  <td class="px-2 py-1 text-center text-blue-600">
                    {{ stats.checked }}
                  </td>
                  <td class="px-2 py-1 text-center text-yellow-600">
                    {{ stats.skipped }}
                  </td>
                  <td class="px-2 py-1 text-center text-green-600">
                    {{ stats.updated }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- 详情列表（显示前20条） -->
        <div
          v-if="checkMissingResult.details && checkMissingResult.details.length > 0"
          class="mt-4 pt-4 border-t border-gray-200"
        >
          <div class="text-sm font-semibold text-gray-700 mb-2">
            检查详情（显示前
            {{ Math.min(checkMissingResult.details.length, 20) }} 条，共
            {{ checkMissingResult.details.length }} 条）：
          </div>
          <div class="max-h-96 overflow-y-auto">
            <div
              v-for="(detail, index) in checkMissingResult.details.slice(0, 20)"
              :key="index"
              class="mb-4 p-3 bg-white border border-gray-200 rounded-lg"
            >
              <div class="grid grid-cols-2 md:grid-cols-4 gap-2 mb-2 text-xs">
                <div>
                  <span class="text-gray-500">检查日期:</span>
                  <span class="font-semibold">
                    {{ detail.check_date || detail.trade_date || '--' }}
                  </span>
                </div>
                <div>
                  <span class="text-gray-500">原始日期:</span>
                  <span class="font-semibold">
                    {{ detail.original_date || '--' }}
                  </span>
                </div>
                <div>
                  <span class="text-gray-500">股票代码:</span>
                  <span class="font-mono font-semibold">{{ detail.ts_code }}</span>
                </div>
                <div>
                  <span class="text-gray-500">股票名称:</span>
                  <span class="font-semibold">{{ detail.name }}</span>
                </div>
              </div>

              <div class="grid grid-cols-2 md:grid-cols-4 gap-2 mb-2 text-xs">
                <div>
                  <span class="text-gray-500">状态:</span>
                  <span
                    :class="{
                      'text-green-600 font-semibold': detail.status === 'updated',
                      'text-blue-600 font-semibold': detail.status === 'checked',
                      'text-yellow-600 font-semibold': detail.status === 'skipped',
                    }"
                  >
                    {{
                      detail.status === 'updated'
                        ? '已更新'
                        : detail.status === 'checked'
                          ? '已检查'
                          : '已跳过'
                    }}
                  </span>
                </div>
                <div>
                  <span class="text-gray-500">原阶段:</span>
                  <span class="font-semibold">{{ detail.old_stage || '--' }}</span>
                </div>
                <div v-if="detail.new_stage">
                  <span class="text-gray-500">新阶段:</span>
                  <span class="font-semibold text-green-600">
                    {{ detail.new_stage }}
                  </span>
                </div>
                <div>
                  <span class="text-gray-500">得分:</span>
                  <span class="font-semibold">
                    {{ detail.old_score || '--' }} →
                    {{ detail.new_score || '--' }}
                  </span>
                </div>
              </div>

              <div
                v-if="detail.already_passed && detail.already_passed.length > 0"
                class="mb-2 text-xs"
              >
                <span class="text-gray-500 font-semibold">已符合条件:</span>
                <span class="text-green-600 ml-1">
                  {{ detail.already_passed.join('、') }}
                </span>
              </div>

              <div
                v-if="detail.missing_conditions && detail.missing_conditions.length > 0"
                class="mb-2 text-xs"
              >
                <span class="text-gray-500 font-semibold">待检查条件:</span>
                <span class="text-orange-600 ml-1">
                  {{ detail.missing_conditions.join('、') }}
                </span>
              </div>

              <div
                v-if="detail.condition_check_results && detail.condition_check_results.length > 0"
                class="mb-2 text-xs"
              >
                <span class="text-gray-500 font-semibold">检查结果:</span>
                <div class="ml-4 mt-1 space-y-1">
                  <div
                    v-for="(result, idx) in detail.condition_check_results"
                    :key="idx"
                    class="flex items-center"
                  >
                    <span
                      :class="result.passed ? 'text-green-600' : 'text-red-600'"
                      class="mr-2"
                    >
                      {{ result.passed ? '✅' : '❌' }}
                    </span>
                    <span>{{ result.condition }}</span>
                  </div>
                </div>
              </div>

              <div
                v-if="detail.newly_passed && detail.newly_passed.length > 0"
                class="mb-2 text-xs"
              >
                <span class="text-gray-500 font-semibold">新满足条件:</span>
                <span class="text-green-600 ml-1">
                  {{ detail.newly_passed.join('、') }}
                </span>
              </div>

              <div
                v-if="detail.still_missing && detail.still_missing.length > 0"
                class="mb-2 text-xs"
              >
                <span class="text-gray-500 font-semibold">仍缺少条件:</span>
                <span class="text-red-600 ml-1">
                  {{ detail.still_missing.join('、') }}
                </span>
              </div>

              <div v-if="detail.reason" class="text-xs text-yellow-600">
                <span class="font-semibold">跳过原因:</span> {{ detail.reason }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 历史数据回填 -->
    <div class="bg-white rounded-lg shadow-md p-6 mb-6">
      <h2 class="text-lg font-semibold text-gray-700 mb-4">📦 历史数据回填</h2>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        <!-- 回填参数 -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">回填开始日期</label>
          <input
            v-model="backfillParams.start_date"
            type="date"
            class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">回填结束日期</label>
          <input
            v-model="backfillParams.end_date"
            type="date"
            class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      </div>

      <!-- 强制回填选项 -->
      <div class="mb-4">
        <label class="flex items-center space-x-2 cursor-pointer">
          <input
            type="checkbox"
            v-model="backfillParams.force_recalculate"
            class="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
          />
          <span class="text-sm font-medium text-gray-700">
            强制回填（即使已有数据也重新计算）
          </span>
        </label>
        <p class="text-xs text-gray-500 mt-1 ml-6">
          勾选后将重新计算所有日期，即使数据库中已有数据也会更新
        </p>
      </div>

      <!-- 数据覆盖状态 -->
      <div v-if="coverageStatus" class="mb-4 p-4 bg-gray-50 rounded-lg">
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <div class="text-gray-500">总交易日</div>
            <div class="text-lg font-semibold text-gray-900">
              {{ coverageStatus.trading_days?.total || 0 }}
            </div>
          </div>
          <div>
            <div class="text-gray-500">已有数据</div>
            <div class="text-lg font-semibold text-green-600">
              {{ coverageStatus.trading_days?.with_data || 0 }}
            </div>
          </div>
          <div>
            <div class="text-gray-500">缺失数据</div>
            <div class="text-lg font-semibold text-red-600">
              {{ coverageStatus.trading_days?.missing || 0 }}
            </div>
          </div>
          <div>
            <div class="text-gray-500">覆盖率</div>
            <div class="text-lg font-semibold text-blue-600">
              {{ coverageStatus.trading_days?.coverage_rate || '0%' }}
            </div>
          </div>
        </div>
        <div v-if="coverageStatus.records" class="mt-3 pt-3 border-t border-gray-200">
          <div class="text-sm text-gray-600">
            记录数：金叉候选 {{ coverageStatus.records.golden_cross || 0 }} 条，启动确认
            {{ coverageStatus.records.confirmed }} 条，完全启动
            {{ coverageStatus.records.started }} 条，总计
            {{ coverageStatus.records.total }} 条
          </div>
        </div>
        <!-- 缺失日期列表 -->
        <div
          v-if="coverageStatus.missing_dates && coverageStatus.missing_dates.length > 0"
          class="mt-3 pt-3 border-t border-gray-200"
        >
          <div class="text-sm text-gray-600 mb-2">
            缺失日期列表（显示前
            {{ Math.min(coverageStatus.missing_dates.length, 50) }} 个，共
            {{
              coverageStatus.missing_dates_count ||
              coverageStatus.missing_dates.length
            }} 个）：
          </div>
          <div class="max-h-40 overflow-y-auto bg-gray-50 p-2 rounded text-xs font-mono">
            <div class="flex flex-wrap gap-1">
              <span
                v-for="(date, index) in coverageStatus.missing_dates.slice(0, 50)"
                :key="index"
                class="px-2 py-1 bg-white rounded border border-gray-200"
              >
                {{ date }}
              </span>
              <span
                v-if="coverageStatus.missing_dates.length > 50"
                class="px-2 py-1 text-gray-500"
              >
                ... 还有
                {{ coverageStatus.missing_dates.length - 50 }}
                个日期
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- 操作按钮 -->
      <div class="flex gap-3 flex-wrap">
        <button
          @click="checkCoverage"
          :disabled="loadingCoverage"
          class="px-6 py-2 bg-yellow-600 text-white rounded-md hover:bg-yellow-700 disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center space-x-2"
        >
          <span v-if="loadingCoverage">检查中...</span>
          <span v-else>🔍 检查数据覆盖情况</span>
        </button>

        <button
          @click="startBackfill"
          :disabled="backfilling || batchGoldenCrossing || !backfillParams.start_date"
          class="px-6 py-2 bg-orange-600 text-white rounded-md hover:bg-orange-700 disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center space-x-2"
        >
          <span v-if="backfilling">回填中...</span>
          <span v-else>🚀 开始回填历史数据</span>
        </button>

        <button
          @click="startBatchGoldenCross"
          :disabled="batchGoldenCrossing || backfilling || !backfillParams.start_date"
          class="px-6 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center space-x-2"
        >
          <span v-if="batchGoldenCrossing">计算中...</span>
          <span v-else>⚡ 批量金叉计算</span>
        </button>
      </div>

      <!-- 回填进度提示 -->
      <div
        v-if="backfilling || batchGoldenCrossing"
        class="mt-4 p-4 bg-blue-50 border border-blue-200 rounded-lg"
      >
        <div class="flex items-center space-x-2">
          <div class="animate-spin">⟳</div>
          <span class="text-blue-700">
            <span v-if="backfilling">
              历史数据回填任务已在后台启动，请稍后刷新页面查看结果...
            </span>
            <span v-else-if="batchGoldenCrossing">
              批量金叉计算任务已在后台启动，请稍后刷新页面查看结果...
            </span>
          </span>
        </div>
      </div>
    </div>

    <!-- 参数设置区域 -->
    <div class="bg-white rounded-lg shadow-md p-6 mb-6">
      <h2 class="text-lg font-semibold text-gray-700 mb-4">📊 查询回测信号</h2>

      <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <!-- 开始日期 -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">开始日期</label>
          <input
            v-model="queryParams.start_date"
            type="date"
            class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="YYYY-MM-DD"
          />
        </div>

        <!-- 结束日期 -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">结束日期</label>
          <input
            v-model="queryParams.end_date"
            type="date"
            class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="YYYY-MM-DD"
          />
        </div>

        <!-- 最低得分 -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">最低得分</label>
          <input
            v-model.number="queryParams.min_score"
            type="number"
            min="60"
            max="100"
            class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="60"
          />
        </div>

        <!-- 阶段过滤 -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">阶段过滤</label>
          <select
            v-model="queryParams.stage_filter"
            class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">全部（confirmed + started）</option>
            <option value="confirmed">启动确认（有风险）</option>
            <option value="started">完全启动（无风险）</option>
          </select>
        </div>
      </div>

      <!-- 操作按钮 -->
      <div class="mt-4 flex gap-3">
        <button
          @click="loadBacktestSignals"
          :disabled="loading"
          class="px-6 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center space-x-2"
        >
          <span v-if="loading">加载中...</span>
          <span v-else>🔍 查询回测数据</span>
        </button>

        <button
          @click="loadStats"
          :disabled="loadingStats"
          class="px-6 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center space-x-2"
        >
          <span v-if="loadingStats">加载中...</span>
          <span v-else>📈 查看统计信息</span>
        </button>

        <button
          @click="exportToCSV"
          :disabled="!signals.length"
          class="px-6 py-2 bg-purple-600 text-white rounded-md hover:bg-purple-700 disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center space-x-2"
        >
          📥 导出CSV
        </button>

        <button
          @click="resetParams"
          class="px-6 py-2 bg-gray-500 text-white rounded-md hover:bg-gray-600"
        >
          🔄 重置
        </button>
      </div>
    </div>

    <!-- 统计信息卡片 -->
    <div v-if="stats" class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
      <div class="bg-white rounded-lg shadow-md p-4">
        <div class="text-sm text-gray-500">总信号数</div>
        <div class="text-2xl font-bold text-blue-600">{{ stats.total_count }}</div>
      </div>

      <div class="bg-white rounded-lg shadow-md p-4">
        <div class="text-sm text-gray-500">启动确认</div>
        <div class="text-2xl font-bold text-yellow-600">
          {{ stats.by_stage?.confirmed || 0 }}
        </div>
      </div>

      <div class="bg-white rounded-lg shadow-md p-4">
        <div class="text-sm text-gray-500">完全启动</div>
        <div class="text-2xl font-bold text-green-600">
          {{ stats.by_stage?.started || 0 }}
        </div>
      </div>

      <div class="bg-white rounded-lg shadow-md p-4">
        <div class="text-sm text-gray-500">日期范围</div>
        <div class="text-sm font-semibold text-gray-700">
          {{ stats.period?.start_date }}<br />
          至 {{ stats.period?.end_date }}
        </div>
      </div>
    </div>

    <!-- 数据表格 -->
    <div class="bg-white rounded-lg shadow-md overflow-hidden">
      <div class="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
        <h2 class="text-lg font-semibold text-gray-700">
          回测信号列表 ({{ signals.length }})
        </h2>
        <div v-if="queryPeriod" class="text-sm text-gray-500">
          查询期间：{{ queryPeriod.start_date }} 至 {{ queryPeriod.end_date }}
        </div>
      </div>

      <div v-if="loading" class="p-8 text-center text-gray-500">
        加载中...
      </div>

      <div v-else-if="signals.length === 0" class="p-8 text-center text-gray-500">
        暂无数据，请点击"查询回测数据"按钮获取数据
      </div>

      <div v-else class="overflow-x-auto">
        <table class="min-w-full divide-y divide-gray-200">
          <thead class="bg-gray-50">
            <tr>
              <th
                class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer hover:bg-gray-100"
                @click="handleSort('signal_date')"
              >
                入选日期 {{ sortIcon('signal_date') }}
              </th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                股票代码
              </th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                股票名称
              </th>
              <th
                class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase cursor-pointer hover:bg-gray-100"
                @click="handleSort('entry_score')"
              >
                得分 {{ sortIcon('entry_score') }}
              </th>
              <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">
                阶段
              </th>
              <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">
                风险
              </th>
              <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">
                辅助条件
              </th>
              <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">
                参考买入价/止损/目标
              </th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                通过的信号
              </th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                风险原因
              </th>
            </tr>
          </thead>
          <tbody class="bg-white divide-y divide-gray-200">
            <tr
              v-for="signal in sortedSignals"
              :key="`${signal.signal_date}-${signal.ts_code}`"
              class="hover:bg-gray-50"
            >
              <td class="px-4 py-3 text-sm text-gray-600">
                {{ formatDateForTable(signal.signal_date) }}
              </td>
              <td class="px-4 py-3 text-sm font-mono text-gray-900">
                {{ signal.ts_code }}
              </td>
              <td class="px-4 py-3 text-sm font-medium text-gray-900">
                {{ signal.stock_name }}
              </td>
              <td class="px-4 py-3 text-sm text-center">
                <span
                  :class="{
                    'text-green-600 font-semibold': signal.entry_score >= 100,
                    'text-blue-600 font-semibold':
                      signal.entry_score >= 70 && signal.entry_score < 100,
                    'text-yellow-600':
                      signal.entry_score >= 60 && signal.entry_score < 70,
                  }"
                >
                  {{ signal.entry_score }}
                </span>
              </td>
              <td class="px-4 py-3 text-sm text-center">
                <span
                  :class="{
                    'px-2 py-1 rounded text-xs font-semibold': true,
                    'bg-green-100 text-green-700':
                      signal.entry_stage === 'started',
                    'bg-yellow-100 text-yellow-700':
                      signal.entry_stage === 'confirmed',
                  }"
                >
                  {{ signal.entry_stage === 'started' ? '完全启动' : '启动确认' }}
                </span>
              </td>
              <td class="px-4 py-3 text-sm text-center">
                <span
                  :class="{
                    'text-green-600': signal.risk_passed,
                    'text-red-600': !signal.risk_passed,
                  }"
                >
                  {{ signal.risk_passed ? '无风险' : '有风险' }}
                </span>
              </td>
              <td class="px-4 py-3 text-sm text-center text-gray-600">
                {{ signal.assist_count }}
              </td>
              <td class="px-4 py-3 text-xs text-gray-600 whitespace-nowrap">
                <div v-if="signal.trade_plan">
                  <div>买：{{ formatPrice(signal.trade_plan.entry_price) }}</div>
                  <div>损：{{ formatPrice(signal.trade_plan.stop_loss_price) }}</div>
                  <div>目：{{ formatPrice(signal.trade_plan.take_profit_price) }}</div>
                </div>
                <div v-else class="text-gray-400">—</div>
              </td>
              <td class="px-4 py-3 text-sm text-gray-600 max-w-xs">
                <div class="truncate" :title="signal.passed_signals?.join('、')">
                  {{ signal.passed_signals?.join('、') || '--' }}
                </div>
              </td>
              <td class="px-4 py-3 text-sm text-orange-600 max-w-xs">
                <div class="truncate" :title="signal.risk_reasons?.join('、')">
                  {{ signal.risk_reasons?.join('、') || '--' }}
                </div>
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
import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

// 查询参数
const queryParams = ref({
  start_date: '',
  end_date: '',
  min_score: 60,
  stage_filter: '',
})

// 回填参数
const backfillParams = ref({
  force_recalculate: false, // 是否强制回填
  start_date: '',
  end_date: '',
})

// 数据
const signals = ref([])
const stats = ref(null)
const queryPeriod = ref(null)

// 排序
const sortField = ref('signal_date') // 默认按入选日期排序
const sortOrder = ref('desc') // 默认降序
const coverageStatus = ref(null)
const loading = ref(false)
const loadingStats = ref(false)
const loadingCoverage = ref(false)
const backfilling = ref(false)
const batchGoldenCrossing = ref(false)

// 检查缺少条件参数
const checkMissingParams = ref({
  start_date: '',
  end_date: '',
  max_trading_days: 5,
  batch_size: 50,
})

// 检查缺少条件结果
const checkMissingResult = ref(null)
const checkingMissing = ref(false)

// 加载回测信号数据
async function loadBacktestSignals() {
  loading.value = true

  try {
    const params = {
      min_score: queryParams.value.min_score,
    }

    if (queryParams.value.start_date) {
      params.start_date = queryParams.value.start_date
    }
    if (queryParams.value.end_date) {
      params.end_date = queryParams.value.end_date
    }
    if (queryParams.value.stage_filter) {
      params.stage_filter = queryParams.value.stage_filter
    }

    const response = await axios.get(`${API_BASE_URL}/api/startup/backtest-signals`, {
      params,
    })

    if (response.data.success) {
      signals.value = response.data.signals || []
      queryPeriod.value = response.data.period

      if (signals.value.length > 0) {
        console.log(`✅ 成功加载 ${signals.value.length} 个回测信号`)
      } else {
        console.log('⚠️ 未找到符合条件的回测信号')
      }
    } else {
      alert('查询失败: ' + (response.data.message || '未知错误'))
    }
  } catch (error) {
    console.error('加载回测信号失败:', error)
    alert('查询失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    loading.value = false
  }
}

// 加载统计信息
async function loadStats() {
  loadingStats.value = true

  try {
    const params = {
      min_score: queryParams.value.min_score,
    }

    if (queryParams.value.start_date) {
      params.start_date = queryParams.value.start_date
    }
    if (queryParams.value.end_date) {
      params.end_date = queryParams.value.end_date
    }

    const response = await axios.get(
      `${API_BASE_URL}/api/startup/backtest-signals/stats`,
      { params },
    )

    if (response.data.success) {
      stats.value = response.data
      console.log('✅ 统计信息加载成功')
    } else {
      alert('查询统计信息失败: ' + (response.data.message || '未知错误'))
    }
  } catch (error) {
    console.error('加载统计信息失败:', error)
    alert('查询失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    loadingStats.value = false
  }
}

// 导出为CSV
function exportToCSV() {
  if (sortedSignals.value.length === 0) {
    alert('没有数据可导出')
    return
  }

  const headers = [
    '入选日期',
    '股票代码',
    '股票名称',
    '得分',
    '阶段',
    '风险通过',
    '辅助条件数',
    '通过的信号',
    '风险原因',
    '金叉日期',
  ]

  const rows = sortedSignals.value.map((signal) => [
    signal.signal_date,
    signal.ts_code,
    signal.stock_name,
    signal.entry_score,
    signal.entry_stage === 'started' ? '完全启动' : '启动确认',
    signal.risk_passed ? '是' : '否',
    signal.assist_count,
    signal.passed_signals?.join('、') || '',
    signal.risk_reasons?.join('、') || '',
    signal.golden_cross_date || '',
  ])

  const csvContent = [
    headers.join(','),
    ...rows.map((row) =>
      row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(','),
    ),
  ].join('\n')

  const BOM = '\uFEFF'
  const blob = new Blob([BOM + csvContent], {
    type: 'text/csv;charset=utf-8;',
  })
  const link = document.createElement('a')
  const url = URL.createObjectURL(blob)

  link.setAttribute('href', url)
  link.setAttribute(
    'download',
    `backtest_signals_${new Date().toISOString().split('T')[0]}.csv`,
  )
  link.style.visibility = 'hidden'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)

  console.log('✅ CSV导出成功')
}

// 重置参数
function resetParams() {
  queryParams.value = {
    start_date: '',
    end_date: '',
    min_score: 60,
    stage_filter: '',
  }
  signals.value = []
  stats.value = null
  queryPeriod.value = null
}

// 辅助格式化
function formatDateForTable(dateStr) {
  if (!dateStr) return '--'
  if (typeof dateStr === 'string' && dateStr.length === 10) {
    return dateStr.substring(5).replace('-', '/')
  }
  return dateStr
}

function sortIcon(field) {
  if (sortField.value !== field) return ''
  return sortOrder.value === 'desc' ? '↓' : '↑'
}

function handleSort(field) {
  if (sortField.value === field) {
    sortOrder.value = sortOrder.value === 'desc' ? 'asc' : 'desc'
  } else {
    sortField.value = field
    sortOrder.value = 'desc'
  }
}

const sortedSignals = computed(() => {
  if (!sortField.value) return signals.value

  const field = sortField.value
  const order = sortOrder.value

  return [...signals.value].sort((a, b) => {
    let aVal = a[field]
    let bVal = b[field]

    if (field === 'signal_date') {
      aVal = new Date(aVal)
      bVal = new Date(bVal)
      return order === 'desc' ? bVal - aVal : aVal - bVal
    }

    if (field === 'entry_score') {
      aVal = Number(aVal) || 0
      bVal = Number(bVal) || 0
      return order === 'desc' ? bVal - aVal : aVal - bVal
    }

    if (aVal < bVal) return order === 'desc' ? 1 : -1
    if (aVal > bVal) return order === 'desc' ? -1 : 1
    return 0
  })
})

function formatPrice(v) {
  if (v == null || isNaN(v)) return '—'
  return Number(v).toFixed(2)
}

// 检查数据覆盖情况
async function checkCoverage() {
  loadingCoverage.value = true

  try {
    const params = {}

    if (backfillParams.value.start_date) {
      params.start_date = backfillParams.value.start_date
    }
    if (backfillParams.value.end_date) {
      params.end_date = backfillParams.value.end_date
    }

    const response = await axios.get(
      `${API_BASE_URL}/api/startup/backfill-history/status`,
      { params },
    )

    if (response.data.success) {
      coverageStatus.value = response.data
      console.log('✅ 数据覆盖情况检查完成')
    } else {
      alert('检查失败: ' + (response.data.message || '未知错误'))
    }
  } catch (error) {
    console.error('检查数据覆盖情况失败:', error)
    alert('检查失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    loadingCoverage.value = false
  }
}

// 开始回填历史数据
async function startBackfill() {
  if (!backfillParams.value.start_date) {
    alert('请先设置回填开始日期')
    return
  }

  const endDateStr = backfillParams.value.end_date || '今天'
  const forceMode = backfillParams.value.force_recalculate
    ? '\n⚠️ 强制回填模式：将重新计算已有数据'
    : ''
  if (
    !confirm(
      `确认回填历史数据？\n日期范围：${backfillParams.value.start_date} 至 ${endDateStr}${forceMode}\n\n这将是一个耗时操作，将在后台执行。`,
    )
  ) {
    return
  }

  backfilling.value = true

  try {
    const params = {
      start_date: backfillParams.value.start_date,
      universe: 'mainboard',
      min_score: 20,
      batch_size: 10,
      skip_existing: !backfillParams.value.force_recalculate,
    }

    if (backfillParams.value.end_date) {
      params.end_date = backfillParams.value.end_date
    }

    const response = await axios.post(
      `${API_BASE_URL}/api/startup/backfill-history`,
      null,
      { params },
    )

    if (response.data.success) {
      alert('✅ ' + response.data.message)
      setTimeout(() => {
        checkCoverage()
      }, 3000)
    } else {
      alert('回填失败: ' + (response.data.message || '未知错误'))
    }
  } catch (error) {
    console.error('启动回填失败:', error)
    alert('启动失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    backfilling.value = false
  }
}

// 批量计算金叉并入库
async function startBatchGoldenCross() {
  if (!backfillParams.value.start_date) {
    alert('请先设置开始日期')
    return
  }

  const endDateStr = backfillParams.value.end_date || '今天'
  if (
    !confirm(
      `确认批量计算金叉并入库？\n日期范围：${backfillParams.value.start_date} 至 ${endDateStr}\n股票池：主板\n\n这将是一个耗时操作，将在后台执行。`,
    )
  ) {
    return
  }

  batchGoldenCrossing.value = true

  try {
    const params = {
      start_date: backfillParams.value.start_date,
      universe: 'mainboard',
      batch_size: 20,
    }

    if (backfillParams.value.end_date) {
      params.end_date = backfillParams.value.end_date
    }

    const response = await axios.post(
      `${API_BASE_URL}/api/startup/batch-golden-cross`,
      null,
      { params },
    )

    if (response.data.success) {
      alert('✅ ' + response.data.message)
      setTimeout(() => {
        checkCoverage()
      }, 3000)
    } else {
      alert('批量计算失败: ' + (response.data.message || '未知错误'))
    }
  } catch (error) {
    console.error('批量计算金叉失败:', error)
    alert('启动失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    batchGoldenCrossing.value = false
  }
}

// 检查缺少条件
async function checkMissingConditions() {
  if (!checkMissingParams.value.start_date || !checkMissingParams.value.end_date) {
    alert('请先设置开始日期和结束日期')
    return
  }

  if (
    !confirm(
      `确认检查缺少条件？\n日期范围：${checkMissingParams.value.start_date} 至 ${checkMissingParams.value.end_date}\n最大交易日数：${checkMissingParams.value.max_trading_days}\n批次大小：${checkMissingParams.value.batch_size}\n\n这将逐个交易日检查所有满足2/3条件的股票，检查缺少的条件是否满足。`,
    )
  ) {
    return
  }

  checkingMissing.value = true
  checkMissingResult.value = null

  try {
    const params = {
      start_date: checkMissingParams.value.start_date,
      end_date: checkMissingParams.value.end_date,
      max_trading_days: checkMissingParams.value.max_trading_days,
      batch_size: checkMissingParams.value.batch_size,
    }

    const response = await axios.post(
      `${API_BASE_URL}/api/startup/check-missing-conditions`,
      null,
      { params },
    )

    if (response.data.success) {
      checkMissingResult.value = response.data
      alert('✅ ' + response.data.message)
      setTimeout(() => {
        loadBacktestSignals()
        loadStats()
      }, 1000)
    } else {
      alert('检查失败: ' + (response.data.message || '未知错误'))
    }
  } catch (error) {
    console.error('检查缺少条件失败:', error)
    alert('检查失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    checkingMissing.value = false
  }
}

// 挂载时默认加载最近一年的数据
onMounted(() => {
  const today = new Date()
  const oneYearAgo = new Date(today)
  oneYearAgo.setFullYear(today.getFullYear() - 1)

  queryParams.value.end_date = today.toISOString().split('T')[0]
  queryParams.value.start_date = oneYearAgo.toISOString().split('T')[0]

  backfillParams.value.end_date = today.toISOString().split('T')[0]
  backfillParams.value.start_date = oneYearAgo.toISOString().split('T')[0]

  checkMissingParams.value.end_date = today.toISOString().split('T')[0]
  checkMissingParams.value.start_date = oneYearAgo.toISOString().split('T')[0]

  loadBacktestSignals()
  loadStats()
  checkCoverage()
})
</script>

<style scoped>
/* 子组件局部样式（如有需要） */
</style>

