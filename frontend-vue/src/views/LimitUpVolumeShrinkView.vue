<template>
  <div class="container mx-auto px-4 py-6">
    <!-- 页面标题 -->
    <div class="mb-6">
      <h1 class="text-2xl font-bold text-gray-800 mb-2">涨停缩量</h1>
      <p class="text-sm text-gray-500">
        <span v-if="strategyType === 'mainboard_limit_up'">
          查找最近5个交易日内有涨停记录，且当前量比&lt;0.6的主板股票（600/601/603/000/001/002）
        </span>
        <span v-else>
          查找最近5个交易日内涨幅>=10%，且第2天或第3天量比&lt;0.6的创业板/科创板股票（300/688，任意一天满足即可）
        </span>
      </p>
    </div>

    <!-- 操作栏 -->
    <div class="mb-4 bg-white rounded-lg shadow p-4">
      <div class="flex items-center justify-between mb-4">
        <div class="flex items-center gap-4">
          <div class="flex items-center gap-2">
            <label class="text-sm text-gray-600 font-medium">策略类型：</label>
            <select
              v-model="strategyType"
              class="px-3 py-2 border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
            >
              <option value="mainboard_limit_up">主板涨停缩量</option>
              <option value="cyb_rise_shrink">创业板/科创板涨幅缩量</option>
            </select>
          </div>
          <div class="flex items-center gap-2">
            <label class="text-sm text-gray-600 font-medium">查询日期：</label>
            <input
              v-model="queryDate"
              type="date"
              class="px-3 py-2 border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
        </div>
        
        <div class="flex items-center gap-2">
          <button
            @click="loadData"
            :disabled="loading"
            class="px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed text-sm flex items-center gap-2"
          >
            <svg v-if="!loading" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <span v-else class="animate-spin">⟳</span>
            {{ loading ? '加载中...' : (strategyType === 'cyb_rise_shrink' ? '查询创业板/科创板' : '查询主板') }}
          </button>
          <button
            v-if="strategyType === 'mainboard_limit_up'"
            @click="calculate"
            :disabled="calculating || calculatingCyb"
            class="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed text-sm flex items-center gap-2"
            title="计算主板涨停缩量股票"
          >
            <svg v-if="!calculating" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
            <span v-else class="animate-spin">⟳</span>
            {{ calculating ? '计算中...' : '计算主板' }}
          </button>
          <button
            v-if="strategyType === 'cyb_rise_shrink'"
            @click="calculateCyb"
            :disabled="calculating || calculatingCyb"
            class="px-6 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:bg-gray-400 disabled:cursor-not-allowed text-sm flex items-center gap-2"
            title="计算创业板科创板涨幅缩量股票（涨幅>=10%，第2天或第3天量比<0.6，任意一天满足即可）"
          >
            <svg v-if="!calculatingCyb" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
            </svg>
            <span v-else class="animate-spin">⟳</span>
            {{ calculatingCyb ? '计算中...' : '计算创业板/科创板' }}
          </button>
          <button
            v-if="strategyType === 'mainboard_limit_up'"
            @click="loadHistoryData"
            :disabled="loadingHistory"
            class="px-6 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 disabled:bg-gray-400 disabled:cursor-not-allowed text-sm flex items-center gap-2"
            title="查询近1年的主板涨停缩量历史数据（会自动先计算再查询）"
          >
            <svg v-if="!loadingHistory" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span v-else class="animate-spin">⟳</span>
            {{ loadingHistory ? '加载中...' : '查询一年数据' }}
          </button>
          <button
            v-if="strategyType === 'cyb_rise_shrink'"
            @click="loadOneYearData"
            :disabled="loadingOneYear"
            class="px-6 py-2 bg-teal-600 text-white rounded-lg hover:bg-teal-700 disabled:bg-gray-400 disabled:cursor-not-allowed text-sm flex items-center gap-2"
            title="查询近1年的创业板/科创板涨幅缩量数据"
          >
            <svg v-if="!loadingOneYear" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
            <span v-else class="animate-spin">⟳</span>
            {{ loadingOneYear ? '加载中...' : '查询1年数据' }}
          </button>
          <button
            v-if="strategyType === 'cyb_rise_shrink'"
            @click="showCheckDialog = true"
            class="px-6 py-2 bg-pink-600 text-white rounded-lg hover:bg-pink-700 text-sm flex items-center gap-2"
            title="单票检测：排查指定股票在指定日期为什么不符合条件"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
            </svg>
            单票检测
          </button>
          <button
            v-if="strategyType === 'cyb_rise_shrink'"
            @click="showStopLossAnalysisDialog = true"
            class="px-6 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 text-sm flex items-center gap-2"
            title="止损股票分析：分析止损股票的共同特征，找出规避风险的方法"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
            止损股票分析
          </button>
          <button
            @click="showBacktestDialog = true"
            class="px-6 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 text-sm flex items-center gap-2"
            :title="strategyType === 'cyb_rise_shrink' ? '创业板/科创板涨幅缩量策略回测' : '主板涨停缩量策略回测'"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
            {{ strategyType === 'cyb_rise_shrink' ? '创业板/科创板回测' : '主板回测' }}
          </button>
          <button
            @click="showTradeRecords"
            class="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm flex items-center gap-2"
            :title="strategyType === 'cyb_rise_shrink' ? '查看创业板/科创板回测交易记录详情' : '查看主板回测交易记录详情'"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
            </svg>
            {{ strategyType === 'cyb_rise_shrink' ? '查看创业板/科创板交易记录' : '查看主板交易记录' }}
          </button>
        </div>
      </div>
      
      <div v-if="currentTradeDate || historyDateRange" class="text-xs text-gray-500">
        <span v-if="currentTradeDate">当前显示日期：</span>
        <span v-if="currentTradeDate" class="text-blue-600 font-semibold">{{ currentTradeDate }}</span>
        <span v-if="historyDateRange" class="text-orange-600 font-semibold">
          历史数据：{{ historyDateRange.start_date }} 至 {{ historyDateRange.end_date }}
        </span>
        <span class="ml-4">共 {{ stocks.length }} 只股票</span>
      </div>
    </div>

    <!-- 数据表格 -->
    <div class="bg-white rounded-lg shadow overflow-hidden">
      <div class="overflow-x-auto">
        <table class="min-w-full divide-y divide-gray-200">
          <thead class="bg-gray-50">
            <tr>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">代码</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">名称</th>
              <th 
                class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100 select-none"
                @click="sortBy('limit_up_date')"
              >
                <div class="flex items-center justify-center gap-1">
                  <span>涨停日期</span>
                  <svg 
                    v-if="sortField === 'limit_up_date'"
                    class="w-4 h-4" 
                    :class="sortOrder === 'asc' ? 'text-blue-600' : 'text-blue-600'"
                    fill="none" 
                    stroke="currentColor" 
                    viewBox="0 0 24 24"
                  >
                    <path 
                      v-if="sortOrder === 'asc'"
                      stroke-linecap="round" 
                      stroke-linejoin="round" 
                      stroke-width="2" 
                      d="M5 15l7-7 7 7" 
                    />
                    <path 
                      v-else
                      stroke-linecap="round" 
                      stroke-linejoin="round" 
                      stroke-width="2" 
                      d="M19 9l-7 7-7-7" 
                    />
                  </svg>
                  <svg 
                    v-else
                    class="w-4 h-4 text-gray-400" 
                    fill="none" 
                    stroke="currentColor" 
                    viewBox="0 0 24 24"
                  >
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4" />
                  </svg>
                </div>
              </th>
              <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">距离天数</th>
              <th 
                class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100 select-none"
                @click="sortBy('volume_ratio')"
              >
                <div class="flex items-center justify-end gap-1">
                  <span>量比</span>
                  <svg 
                    v-if="sortField === 'volume_ratio'"
                    class="w-4 h-4" 
                    :class="sortOrder === 'asc' ? 'text-blue-600' : 'text-blue-600'"
                    fill="none" 
                    stroke="currentColor" 
                    viewBox="0 0 24 24"
                  >
                    <path 
                      v-if="sortOrder === 'asc'"
                      stroke-linecap="round" 
                      stroke-linejoin="round" 
                      stroke-width="2" 
                      d="M5 15l7-7 7 7" 
                    />
                    <path 
                      v-else
                      stroke-linecap="round" 
                      stroke-linejoin="round" 
                      stroke-width="2" 
                      d="M19 9l-7 7-7-7" 
                    />
                  </svg>
                  <svg 
                    v-else
                    class="w-4 h-4 text-gray-400" 
                    fill="none" 
                    stroke="currentColor" 
                    viewBox="0 0 24 24"
                  >
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4" />
                  </svg>
                </div>
              </th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">今日收盘</th>
              <th 
                class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100 select-none"
                @click="sortBy('today_change_pct')"
              >
                <div class="flex items-center justify-end gap-1">
                  <span>今日涨幅</span>
                  <svg 
                    v-if="sortField === 'today_change_pct'"
                    class="w-4 h-4" 
                    :class="sortOrder === 'asc' ? 'text-blue-600' : 'text-blue-600'"
                    fill="none" 
                    stroke="currentColor" 
                    viewBox="0 0 24 24"
                  >
                    <path 
                      v-if="sortOrder === 'asc'"
                      stroke-linecap="round" 
                      stroke-linejoin="round" 
                      stroke-width="2" 
                      d="M5 15l7-7 7 7" 
                    />
                    <path 
                      v-else
                      stroke-linecap="round" 
                      stroke-linejoin="round" 
                      stroke-width="2" 
                      d="M19 9l-7 7-7-7" 
                    />
                  </svg>
                  <svg 
                    v-else
                    class="w-4 h-4 text-gray-400" 
                    fill="none" 
                    stroke="currentColor" 
                    viewBox="0 0 24 24"
                  >
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4" />
                  </svg>
                </div>
              </th>
              <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">今日成交额</th>
              <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">操作</th>
            </tr>
          </thead>
          <tbody class="bg-white divide-y divide-gray-200">
            <tr 
              v-for="stock in sortedStocks" 
              :key="stock.id"
              class="hover:bg-gray-50"
            >
              <td class="px-4 py-3 text-sm font-medium text-gray-900">{{ formatCode(stock.ts_code) }}</td>
              <td class="px-4 py-3 text-sm text-gray-700">{{ stock.stock_name || '--' }}</td>
              <td class="px-4 py-3 text-sm text-center text-gray-700">{{ stock.limit_up_date || '--' }}</td>
              <td class="px-4 py-3 text-sm text-center text-gray-700">{{ stock.limit_up_days_ago !== null ? stock.limit_up_days_ago + '天' : '--' }}</td>
              <td class="px-4 py-3 text-sm text-right">
                <span 
                  class="font-semibold"
                  :class="stock.volume_ratio < 0.6 ? 'text-red-600' : 'text-gray-700'"
                >
                  {{ formatNumber(stock.volume_ratio, 2) }}
                </span>
              </td>
              <td class="px-4 py-3 text-sm text-right text-gray-700">{{ formatNumber(stock.today_close, 2) }}</td>
              <td class="px-4 py-3 text-sm text-right">
                <span :class="getChangeColor(stock.today_change_pct)">
                  {{ formatPercent(stock.today_change_pct) }}
                </span>
              </td>
              <td class="px-4 py-3 text-sm text-right text-gray-700">{{ formatAmount(stock.today_amount) }}</td>
              <td class="px-4 py-3 text-sm text-center">
                <button
                  @click="addToWatchlist(stock)"
                  class="px-3 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700"
                >
                  加入跟踪池
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      
      <div v-if="stocks.length === 0 && !loading" class="py-12 text-center text-gray-500">
        <p>暂无数据</p>
      </div>
    </div>

    <!-- 回测对话框 -->
    <div 
      v-if="showBacktestDialog" 
      class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
      @click.self="showBacktestDialog = false"
    >
      <div class="bg-white rounded-lg shadow-xl max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
        <div class="p-6">
          <div class="flex items-center justify-between mb-4">
            <h2 class="text-xl font-bold text-gray-800">策略回测</h2>
            <button
              @click="showBacktestDialog = false"
              class="text-gray-400 hover:text-gray-600"
            >
              <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <!-- 回测参数 -->
          <div class="space-y-4 mb-6">
            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">开始日期</label>
                <input
                  v-model="backtestParams.start_date"
                  type="date"
                  class="w-full px-3 py-2 border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">结束日期</label>
                <input
                  v-model="backtestParams.end_date"
                  type="date"
                  class="w-full px-3 py-2 border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-2">卖出策略</label>
              <div class="flex flex-col gap-2">
                <label class="flex items-center">
                  <input
                    type="radio"
                    v-model="backtestParams.sell_strategy"
                    value="profit_stop"
                    class="mr-2"
                  />
                  <span class="text-sm text-gray-700">策略1：止盈止损策略（止盈{{ backtestParams.profit_target }}%，止损{{ backtestParams.stop_loss }}%）</span>
                </label>
                <label class="flex items-center">
                  <input
                    type="radio"
                    v-model="backtestParams.sell_strategy"
                    value="ma5_loss"
                    class="mr-2"
                  />
                  <span class="text-sm text-gray-700">策略2：破跌5日线或亏损5%，从第三天开始没有涨停就退出</span>
                </label>
                <label class="flex items-center">
                  <input
                    type="radio"
                    v-model="backtestParams.sell_strategy"
                    value="ma5_loss_5pct"
                    class="mr-2"
                  />
                  <span class="text-sm text-gray-700">策略3：破跌5日线或亏损5%或最大持仓5天</span>
                </label>
                <label class="flex items-center">
                  <input
                    type="radio"
                    v-model="backtestParams.sell_strategy"
                    value="ma5_rising"
                    class="mr-2"
                  />
                  <span class="text-sm text-gray-700">策略4：上涨过程中不破5日线不卖，止损-5%</span>
                </label>
              </div>
            </div>
            <div class="grid grid-cols-3 gap-4">
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">目标收益率 (%)</label>
                <input
                  v-model.number="backtestParams.profit_target"
                  type="number"
                  step="0.01"
                  :disabled="backtestParams.sell_strategy === 'ma5_loss' || backtestParams.sell_strategy === 'ma5_loss_5pct' || backtestParams.sell_strategy === 'ma5_rising'"
                  class="w-full px-3 py-2 border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
                />
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">止损比例 (%)</label>
                <input
                  v-model.number="backtestParams.stop_loss"
                  type="number"
                  step="0.01"
                  :disabled="backtestParams.sell_strategy === 'ma5_loss' || backtestParams.sell_strategy === 'ma5_loss_5pct' || backtestParams.sell_strategy === 'ma5_rising'"
                  class="w-full px-3 py-2 border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
                />
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">最大持有天数</label>
                <input
                  v-model.number="backtestParams.max_hold_days"
                  type="number"
                  :disabled="false"
                  class="w-full px-3 py-2 border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
                />
                <p v-if="backtestParams.sell_strategy === 'ma5_loss'" class="text-xs text-gray-500 mt-1">策略2：从第三天开始，每天检查涨停，未涨停则退出</p>
                <p v-if="backtestParams.sell_strategy === 'ma5_loss_5pct'" class="text-xs text-gray-500 mt-1">策略3最大持仓5天</p>
              </div>
            </div>
          </div>

          <!-- 回测结果 -->
          <div v-if="backtestResult" class="mb-6">
            <h3 class="text-lg font-semibold text-gray-800 mb-3">回测结果</h3>
            <div v-if="backtestResult.success" class="space-y-3">
              <!-- 资金管理统计 -->
              <div v-if="backtestResult.statistics.capital_management" class="mb-6 p-4 bg-blue-50 rounded-lg border border-blue-200">
                <h3 class="text-lg font-bold text-gray-800 mb-3">资金管理统计</h3>
                <div class="grid grid-cols-4 gap-4 text-sm">
                  <div class="bg-white p-3 rounded">
                    <div class="text-gray-600">初始本金</div>
                    <div class="text-xl font-bold text-gray-800">{{ formatNumber(backtestResult.statistics.capital_management.initial_capital, 0) }} 元</div>
                  </div>
                  <div class="bg-white p-3 rounded">
                    <div class="text-gray-600">最终总资产</div>
                    <div class="text-xl font-bold text-gray-800">{{ formatNumber(backtestResult.statistics.capital_management.total_assets, 0) }} 元</div>
                  </div>
                  <div class="bg-white p-3 rounded">
                    <div class="text-gray-600">总盈亏</div>
                    <div class="text-xl font-bold" :class="backtestResult.statistics.capital_management.total_profit_loss >= 0 ? 'text-red-600' : 'text-green-600'">
                      {{ formatNumber(backtestResult.statistics.capital_management.total_profit_loss, 0) }} 元
                    </div>
                  </div>
                  <div class="bg-white p-3 rounded">
                    <div class="text-gray-600">总收益率</div>
                    <div class="text-xl font-bold" :class="backtestResult.statistics.capital_management.total_profit_loss_pct >= 0 ? 'text-red-600' : 'text-green-600'">
                      {{ formatPercent(backtestResult.statistics.capital_management.total_profit_loss_pct) }}
                    </div>
                  </div>
                </div>
                <div class="mt-3 text-sm text-gray-600 grid grid-cols-2 gap-4">
                  <div>可用资金: {{ formatNumber(backtestResult.statistics.capital_management.final_available_capital, 0) }} 元</div>
                  <div>持仓市值: {{ formatNumber(backtestResult.statistics.capital_management.holdings_value, 0) }} 元</div>
                </div>
                
                <!-- 交易成本统计 -->
                <div v-if="backtestResult.statistics.capital_management.total_trading_cost !== undefined" class="mt-4 pt-4 border-t border-blue-300">
                  <h4 class="text-sm font-semibold text-gray-700 mb-3">交易成本统计</h4>
                  <div class="grid grid-cols-2 gap-3 text-sm">
                    <div class="bg-white p-3 rounded">
                      <div class="text-gray-600 mb-1">买入手续费</div>
                      <div class="text-lg font-semibold text-gray-800">
                        {{ formatNumber(backtestResult.statistics.capital_management.total_buy_commission || 0, 2) }} 元
                      </div>
                    </div>
                    <div class="bg-white p-3 rounded">
                      <div class="text-gray-600 mb-1">卖出手续费</div>
                      <div class="text-lg font-semibold text-gray-800">
                        {{ formatNumber(backtestResult.statistics.capital_management.total_sell_commission || 0, 2) }} 元
                      </div>
                    </div>
                    <div class="bg-white p-3 rounded">
                      <div class="text-gray-600 mb-1">印花税</div>
                      <div class="text-lg font-semibold text-gray-800">
                        {{ formatNumber(backtestResult.statistics.capital_management.total_stamp_tax || 0, 2) }} 元
                      </div>
                    </div>
                    <div class="bg-white p-3 rounded">
                      <div class="text-gray-600 mb-1">总交易成本</div>
                      <div class="text-lg font-semibold text-orange-600">
                        {{ formatNumber(backtestResult.statistics.capital_management.total_trading_cost || 0, 2) }} 元
                      </div>
                      <div class="text-xs text-gray-500 mt-1">
                        (占初始本金 {{ formatPercent((backtestResult.statistics.capital_management.trading_cost_ratio || 0)) }})
                      </div>
                    </div>
                  </div>
                </div>
              </div>
              
              <div class="grid grid-cols-3 gap-4 text-sm">
                <div class="bg-gray-50 p-3 rounded">
                  <div class="text-gray-600">总交易次数</div>
                  <div class="text-xl font-bold text-gray-800">{{ backtestResult.statistics.total_trades }}</div>
                </div>
                <div class="bg-gray-50 p-3 rounded">
                  <div class="text-gray-600">胜率</div>
                  <div class="text-xl font-bold text-green-600">{{ (backtestResult.statistics.win_rate * 100).toFixed(2) }}%</div>
                </div>
                <div class="bg-gray-50 p-3 rounded">
                  <div class="text-gray-600">平均收益率</div>
                  <div class="text-xl font-bold" :class="backtestResult.statistics.mean_return >= 0 ? 'text-red-600' : 'text-green-600'">
                    {{ (backtestResult.statistics.mean_return * 100).toFixed(2) }}%
                  </div>
                </div>
                <div class="bg-gray-50 p-3 rounded">
                  <div class="text-gray-600">年化收益率</div>
                  <div class="text-xl font-bold" :class="backtestResult.statistics.annual_return >= 0 ? 'text-red-600' : 'text-green-600'">
                    {{ (backtestResult.statistics.annual_return * 100).toFixed(2) }}%
                  </div>
                </div>
                <div class="bg-gray-50 p-3 rounded">
                  <div class="text-gray-600">夏普比率</div>
                  <div class="text-xl font-bold text-gray-800">{{ backtestResult.statistics.sharpe_ratio.toFixed(2) }}</div>
                </div>
                <div class="bg-gray-50 p-3 rounded">
                  <div class="text-gray-600">最大回撤</div>
                  <div class="text-xl font-bold text-red-600">{{ (backtestResult.statistics.max_drawdown * 100).toFixed(2) }}%</div>
                </div>
              </div>
              <div class="text-sm text-gray-600 mt-4">
                <div>盈利次数: {{ backtestResult.statistics.win_count }} | 亏损次数: {{ backtestResult.statistics.loss_count }}</div>
                <div>平均盈利: {{ (backtestResult.statistics.mean_profit * 100).toFixed(2) }}% | 平均亏损: {{ (backtestResult.statistics.mean_loss * 100).toFixed(2) }}%</div>
                <div>盈亏比: {{ backtestResult.statistics.profit_loss_ratio.toFixed(2) }}</div>
              </div>
              
              <!-- 信号和交易记录对应关系（仅创业板策略显示） -->
              <div v-if="strategyType === 'cyb_rise_shrink' && backtestResult.signals && backtestResult.signals.length > 0" class="mt-6">
                <h3 class="text-lg font-semibold text-gray-800 mb-3">信号与交易记录对应关系</h3>
                <div class="bg-white rounded-lg border border-gray-200 overflow-hidden">
                  <div class="overflow-x-auto">
                    <table class="min-w-full divide-y divide-gray-200">
                      <thead class="bg-gray-50">
                        <tr>
                          <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">信号日期</th>
                          <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">股票代码</th>
                          <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">股票名称</th>
                          <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">买入日期</th>
                          <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">买入价</th>
                          <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">卖出日期</th>
                          <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">卖出价</th>
                          <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">收益率</th>
                          <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">盈亏</th>
                          <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">退出原因</th>
                        </tr>
                      </thead>
                      <tbody class="bg-white divide-y divide-gray-200">
                        <tr 
                          v-for="(signal, index) in backtestResult.signals" 
                          :key="index"
                          :class="signal.trade && signal.trade.profit_loss_pct ? (signal.trade.profit_loss_pct >= 0 ? 'bg-red-50' : 'bg-green-50') : 'bg-gray-50'"
                        >
                          <td class="px-4 py-3 whitespace-nowrap text-sm text-gray-900">{{ signal.signal_date }}</td>
                          <td class="px-4 py-3 whitespace-nowrap text-sm text-gray-900">{{ signal.ts_code }}</td>
                          <td class="px-4 py-3 whitespace-nowrap text-sm text-gray-900">{{ signal.stock_name || '--' }}</td>
                          <td class="px-4 py-3 whitespace-nowrap text-sm text-gray-900">
                            {{ signal.trade ? signal.trade.buy_date : '--' }}
                          </td>
                          <td class="px-4 py-3 whitespace-nowrap text-sm text-gray-900">
                            {{ signal.trade ? formatNumber(signal.trade.buy_price, 2) : '--' }}
                          </td>
                          <td class="px-4 py-3 whitespace-nowrap text-sm text-gray-900">
                            {{ signal.trade ? signal.trade.sell_date : '--' }}
                          </td>
                          <td class="px-4 py-3 whitespace-nowrap text-sm text-gray-900">
                            {{ signal.trade ? formatNumber(signal.trade.sell_price, 2) : '--' }}
                          </td>
                          <td class="px-4 py-3 whitespace-nowrap text-sm font-semibold" 
                              :class="signal.trade && signal.trade.profit_loss_pct ? (signal.trade.profit_loss_pct >= 0 ? 'text-red-600' : 'text-green-600') : 'text-gray-500'">
                            {{ signal.trade ? formatPercent(signal.trade.profit_loss_pct) : '未交易' }}
                          </td>
                          <td class="px-4 py-3 whitespace-nowrap text-sm font-semibold" 
                              :class="signal.trade && signal.trade.profit_loss ? (signal.trade.profit_loss >= 0 ? 'text-red-600' : 'text-green-600') : 'text-gray-500'">
                            {{ signal.trade ? formatNumber(signal.trade.profit_loss, 0) + ' 元' : '--' }}
                          </td>
                          <td class="px-4 py-3 whitespace-nowrap text-sm text-gray-900">
                            {{ signal.trade ? getExitReasonText(signal.trade.exit_reason) : '--' }}
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>
                <div class="mt-3 text-sm text-gray-600">
                  <div>总信号数: {{ backtestResult.signals.length }} | 已交易: {{ backtestResult.signals.filter(s => s.has_trade).length }} | 未交易: {{ backtestResult.signals.filter(s => !s.has_trade).length }}</div>
                  <div>盈利信号: <span class="text-red-600 font-semibold">{{ backtestResult.signals.filter(s => s.trade && s.trade.profit_loss_pct >= 0).length }}</span> | 
                       亏损信号: <span class="text-green-600 font-semibold">{{ backtestResult.signals.filter(s => s.trade && s.trade.profit_loss_pct < 0).length }}</span></div>
                </div>
                
                <!-- 亏损分析 -->
                <div v-if="backtestResult.signals && backtestResult.signals.length > 0" class="mt-6 p-4 bg-red-50 rounded-lg border border-red-200">
                  <h3 class="text-lg font-semibold text-gray-800 mb-3">亏损分析</h3>
                  
                  <!-- 按退出原因统计亏损 -->
                  <div class="mb-4">
                    <h4 class="text-md font-semibold text-gray-700 mb-2">按退出原因统计亏损</h4>
                    <div class="grid grid-cols-2 gap-3 text-sm">
                      <div v-for="(count, reason) in lossByExitReason" :key="reason" class="bg-white p-3 rounded border border-gray-200">
                        <div class="text-gray-600">{{ getExitReasonText(reason) }}</div>
                        <div class="text-lg font-semibold text-green-600">{{ count }} 笔</div>
                        <div class="text-xs text-gray-500">亏损金额: {{ formatNumber(lossAmountByExitReason[reason] || 0, 0) }} 元</div>
                      </div>
                    </div>
                  </div>
                  
                  <!-- 亏损金额分布 -->
                  <div class="mb-4">
                    <h4 class="text-md font-semibold text-gray-700 mb-2">亏损金额分布</h4>
                    <div class="grid grid-cols-4 gap-3 text-sm">
                      <div class="bg-white p-3 rounded border border-gray-200">
                        <div class="text-gray-600">总亏损金额</div>
                        <div class="text-lg font-semibold text-green-600">{{ formatNumber(totalLossAmount, 0) }} 元</div>
                      </div>
                      <div class="bg-white p-3 rounded border border-gray-200">
                        <div class="text-gray-600">平均亏损金额</div>
                        <div class="text-lg font-semibold text-green-600">{{ formatNumber(avgLossAmount, 0) }} 元</div>
                      </div>
                      <div class="bg-white p-3 rounded border border-gray-200">
                        <div class="text-gray-600">最大单笔亏损</div>
                        <div class="text-lg font-semibold text-green-600">{{ formatNumber(maxLossAmount, 0) }} 元</div>
                      </div>
                      <div class="bg-white p-3 rounded border border-gray-200">
                        <div class="text-gray-600">平均亏损率</div>
                        <div class="text-lg font-semibold text-green-600">{{ formatPercent(avgLossPct) }}</div>
                      </div>
                    </div>
                  </div>
                  
                  <!-- 亏损率分布 -->
                  <div class="mb-4">
                    <h4 class="text-md font-semibold text-gray-700 mb-2">亏损率分布</h4>
                    <div class="grid grid-cols-5 gap-2 text-xs">
                      <div class="bg-white p-2 rounded border border-gray-200">
                        <div class="text-gray-600">亏损 < -10%</div>
                        <div class="text-sm font-semibold text-green-600">{{ lossDistribution['<-10%'] }} 笔</div>
                      </div>
                      <div class="bg-white p-2 rounded border border-gray-200">
                        <div class="text-gray-600">-10% ~ -5%</div>
                        <div class="text-sm font-semibold text-green-600">{{ lossDistribution['-10% to -5%'] }} 笔</div>
                      </div>
                      <div class="bg-white p-2 rounded border border-gray-200">
                        <div class="text-gray-600">-5% ~ -2%</div>
                        <div class="text-sm font-semibold text-green-600">{{ lossDistribution['-5% to -2%'] }} 笔</div>
                      </div>
                      <div class="bg-white p-2 rounded border border-gray-200">
                        <div class="text-gray-600">-2% ~ 0%</div>
                        <div class="text-sm font-semibold text-green-600">{{ lossDistribution['-2% to 0%'] }} 笔</div>
                      </div>
                      <div class="bg-white p-2 rounded border border-gray-200">
                        <div class="text-gray-600">小亏 (< -1%)</div>
                        <div class="text-sm font-semibold text-green-600">{{ lossDistribution['small'] }} 笔</div>
                      </div>
                    </div>
                  </div>
                  
                  <!-- 亏损最多的股票（Top 10） -->
                  <div>
                    <h4 class="text-md font-semibold text-gray-700 mb-2">亏损最多的股票（Top 10）</h4>
                    <div class="bg-white rounded border border-gray-200 overflow-hidden">
                      <table class="min-w-full divide-y divide-gray-200 text-sm">
                        <thead class="bg-gray-50">
                          <tr>
                            <th class="px-3 py-2 text-left text-xs font-medium text-gray-500">股票代码</th>
                            <th class="px-3 py-2 text-left text-xs font-medium text-gray-500">股票名称</th>
                            <th class="px-3 py-2 text-left text-xs font-medium text-gray-500">信号日期</th>
                            <th class="px-3 py-2 text-right text-xs font-medium text-gray-500">亏损率</th>
                            <th class="px-3 py-2 text-right text-xs font-medium text-gray-500">亏损金额</th>
                            <th class="px-3 py-2 text-left text-xs font-medium text-gray-500">退出原因</th>
                          </tr>
                        </thead>
                        <tbody class="bg-white divide-y divide-gray-200">
                          <tr v-for="(signal, index) in topLossStocks" :key="index" class="bg-green-50">
                            <td class="px-3 py-2 text-gray-900">{{ signal.ts_code }}</td>
                            <td class="px-3 py-2 text-gray-900">{{ signal.stock_name || '--' }}</td>
                            <td class="px-3 py-2 text-gray-900">{{ signal.signal_date }}</td>
                            <td class="px-3 py-2 text-right font-semibold text-green-600">{{ formatPercent(signal.trade.profit_loss_pct) }}</td>
                            <td class="px-3 py-2 text-right font-semibold text-green-600">{{ formatNumber(signal.trade.profit_loss, 0) }} 元</td>
                            <td class="px-3 py-2 text-gray-900">{{ getExitReasonText(signal.trade.exit_reason) }}</td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div v-else class="text-red-600">
              回测失败: {{ backtestResult.error }}
            </div>
          </div>

          <!-- 操作按钮 -->
          <div class="flex justify-end gap-2">
            <button
              @click="showBacktestDialog = false"
              class="px-4 py-2 text-gray-700 bg-gray-200 rounded-lg hover:bg-gray-300 text-sm"
            >
              关闭
            </button>
            <button
              @click="runBacktest"
              :disabled="backtesting"
              class="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:bg-gray-400 disabled:cursor-not-allowed text-sm flex items-center gap-2"
            >
              <span v-if="backtesting" class="animate-spin">⟳</span>
              {{ backtesting ? '回测中...' : '执行回测' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 交易记录对话框 -->
    <div 
      v-if="showTradeRecordsDialog" 
      class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
      @click.self="showTradeRecordsDialog = false"
    >
      <div class="bg-white rounded-lg shadow-xl max-w-6xl w-full mx-4 max-h-[90vh] overflow-y-auto">
        <div class="p-6">
          <div class="flex items-center justify-between mb-4">
            <h2 class="text-xl font-bold text-gray-800">交易记录详情</h2>
            <button
              @click="showTradeRecordsDialog = false"
              class="text-gray-400 hover:text-gray-600"
            >
              <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <!-- 过滤条件 -->
          <div class="mb-4 grid grid-cols-4 gap-4">
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">退出原因</label>
              <select
                v-model="tradeRecordFilters.exit_reason"
                class="w-full px-3 py-2 border border-gray-300 rounded text-sm"
              >
                <option value="">全部</option>
                <option value="profit_target">止盈</option>
                <option value="stop_loss">止损</option>
                <option value="time_limit">时间限制</option>
                <option value="loss_10pct">亏损10%</option>
                <option value="loss_5pct">亏损5%</option>
                <option value="break_ma5">破跌5日线</option>
                <option value="data_end">数据结束</option>
                <option value="day3_no_limit_up">第三天未涨停</option>
              </select>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">收益率范围</label>
              <div class="flex gap-2">
                <input
                  v-model.number="tradeRecordFilters.min_return_pct"
                  type="number"
                  step="0.01"
                  placeholder="最小"
                  class="w-full px-2 py-2 border border-gray-300 rounded text-sm"
                />
                <input
                  v-model.number="tradeRecordFilters.max_return_pct"
                  type="number"
                  step="0.01"
                  placeholder="最大"
                  class="w-full px-2 py-2 border border-gray-300 rounded text-sm"
                />
              </div>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">排序</label>
              <select
                v-model="tradeRecordSort"
                class="w-full px-3 py-2 border border-gray-300 rounded text-sm"
              >
                <option value="return_asc">收益率升序（先看亏损）</option>
                <option value="return_desc">收益率降序</option>
                <option value="date_desc">日期降序</option>
                <option value="date_asc">日期升序</option>
              </select>
            </div>
            <div class="flex items-end">
              <button
                @click="loadTradeRecords"
                class="w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm"
              >
                查询
              </button>
            </div>
          </div>

          <!-- 交易记录表格 -->
          <div v-if="loadingTradeRecords" class="text-center py-8">
            <div class="animate-spin text-blue-600 text-2xl">⟳</div>
            <p class="mt-2 text-gray-600">加载中...</p>
          </div>
          <div v-else-if="tradeRecords.length > 0" class="overflow-x-auto">
            <table class="min-w-full divide-y divide-gray-200">
              <thead class="bg-gray-50">
                <tr>
                  <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">信号日期</th>
                  <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">股票代码</th>
                  <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">股票名称</th>
                  <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">买入日期</th>
                  <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">买入价格</th>
                  <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">买入金额</th>
                  <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">卖出日期</th>
                  <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">卖出价格</th>
                  <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">卖出金额</th>
                  <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">单票收益率</th>
                  <th class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">盈亏金额</th>
                  <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">持有天数</th>
                  <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">退出原因</th>
                  <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">卖出策略</th>
                </tr>
              </thead>
              <tbody class="bg-white divide-y divide-gray-200">
                <tr 
                  v-for="record in sortedTradeRecords" 
                  :key="record.id"
                  class="hover:bg-gray-50"
                >
                  <td class="px-4 py-3 text-sm text-gray-700">{{ record.signal_date }}</td>
                  <td class="px-4 py-3 text-sm font-medium text-gray-900">{{ formatCode(record.ts_code) }}</td>
                  <td class="px-4 py-3 text-sm text-gray-700">{{ record.stock_name || '--' }}</td>
                  <td class="px-4 py-3 text-sm text-gray-700">{{ record.buy_date }}</td>
                  <td class="px-4 py-3 text-sm text-right text-gray-700">{{ formatNumber(record.buy_price, 2) }}</td>
                  <td class="px-4 py-3 text-sm text-right text-gray-700">{{ record.buy_amount ? formatNumber(record.buy_amount, 0) + ' 元' : '--' }}</td>
                  <td class="px-4 py-3 text-sm text-gray-700">{{ record.sell_date || '--' }}</td>
                  <td class="px-4 py-3 text-sm text-right text-gray-700">{{ record.sell_price ? formatNumber(record.sell_price, 2) : '--' }}</td>
                  <td class="px-4 py-3 text-sm text-right text-gray-700">{{ record.sell_amount ? formatNumber(record.sell_amount, 0) + ' 元' : '--' }}</td>
                  <td class="px-4 py-3 text-sm text-right font-semibold" :class="getReturnColor(record.profit_loss_pct !== undefined && record.profit_loss_pct !== null ? record.profit_loss_pct / 100 : record.return_pct)">
                    {{ record.profit_loss_pct !== undefined && record.profit_loss_pct !== null ? formatPercent(record.profit_loss_pct) : formatPercent(record.return_pct * 100) }}
                  </td>
                  <td class="px-4 py-3 text-sm text-right font-semibold" :class="getReturnColor(record.profit_loss !== undefined && record.profit_loss !== null ? record.profit_loss / (record.buy_amount || 1) : record.return_pct)">
                    {{ record.profit_loss !== undefined && record.profit_loss !== null ? formatNumber(record.profit_loss, 0) + ' 元' : '--' }}
                  </td>
                  <td class="px-4 py-3 text-sm text-center text-gray-700">{{ record.hold_days || '--' }}</td>
                  <td class="px-4 py-3 text-sm text-gray-700">{{ getExitReasonText(record.exit_reason) }}</td>
                  <td class="px-4 py-3 text-sm text-gray-700">{{ getSellStrategyText(record.sell_strategy) }}</td>
                </tr>
              </tbody>
            </table>
            <div class="mt-4 text-sm text-gray-600">
              共 {{ tradeRecordsTotal }} 条记录，显示 {{ sortedTradeRecords.length }} 条
            </div>
          </div>
          <div v-else class="text-center py-8 text-gray-500">
            暂无交易记录
          </div>
        </div>
      </div>
    </div>

    <!-- 止损股票分析对话框 -->
    <div 
      v-if="showStopLossAnalysisDialog" 
      class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
      @click.self="showStopLossAnalysisDialog = false"
    >
      <div class="bg-white rounded-lg shadow-xl max-w-4xl w-full mx-4 max-h-[90vh] overflow-y-auto">
        <div class="p-6">
          <div class="flex items-center justify-between mb-4">
            <h2 class="text-xl font-bold text-gray-800">止损股票分析</h2>
            <button
              @click="showStopLossAnalysisDialog = false"
              class="text-gray-400 hover:text-gray-600"
            >
              <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <!-- 输入区域 -->
          <div class="mb-4">
            <label class="block text-sm font-medium text-gray-700 mb-2">
              输入止损股票列表（每行一个，格式：股票代码 信号日期，如：300403.SZ 2025-11-13）
            </label>
            <textarea
              v-model="stopLossStocksInput"
              rows="10"
              class="w-full px-3 py-2 border border-gray-300 rounded text-sm font-mono"
              placeholder="300403.SZ 2025-11-13&#10;300192.SZ 2025-08-25&#10;300163.SZ 2025-11-07&#10;..."
            ></textarea>
          </div>

          <div class="flex justify-end gap-2 mb-4">
            <button
              @click="showStopLossAnalysisDialog = false"
              class="px-4 py-2 text-gray-700 bg-gray-200 rounded-lg hover:bg-gray-300 text-sm"
            >
              取消
            </button>
            <button
              @click="analyzeStopLossStocks"
              :disabled="analyzingStopLoss || !stopLossStocksInput.trim()"
              class="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:bg-gray-400 disabled:cursor-not-allowed text-sm flex items-center gap-2"
            >
              <span v-if="analyzingStopLoss" class="animate-spin">⟳</span>
              {{ analyzingStopLoss ? '分析中...' : '开始分析' }}
            </button>
          </div>

          <!-- 分析结果 -->
          <div v-if="stopLossAnalysisResult" class="border-t pt-4">
            <h3 class="text-lg font-semibold text-gray-800 mb-4">分析结果</h3>
            
            <!-- 共同特征 -->
            <div v-if="stopLossAnalysisResult.common_features" class="mb-4 p-4 bg-blue-50 rounded-lg">
              <h4 class="font-semibold text-gray-800 mb-2">共同特征</h4>
              <div class="grid grid-cols-2 gap-2 text-sm">
                <div><span class="text-gray-600">平均止损天数：</span><span class="font-medium">{{ stopLossAnalysisResult.common_features.avg_days_to_stop_loss?.toFixed(1) }}天</span></div>
                <div><span class="text-gray-600">平均信号量比：</span><span class="font-medium">{{ stopLossAnalysisResult.common_features.avg_signal_volume_ratio?.toFixed(2) }}</span></div>
                <div><span class="text-gray-600">平均信号涨幅：</span><span class="font-medium">{{ stopLossAnalysisResult.common_features.avg_signal_change_pct?.toFixed(2) }}%</span></div>
                <div><span class="text-gray-600">平均买入日跌幅：</span><span class="font-medium">{{ stopLossAnalysisResult.common_features.avg_buy_change_pct?.toFixed(2) }}%</span></div>
                <div><span class="text-gray-600">买入价低于5日线：</span><span class="font-medium">{{ stopLossAnalysisResult.common_features.buy_below_ma5_count }}/{{ stopLossAnalysisResult.total_stocks }}</span></div>
                <div><span class="text-gray-600">买入价低于10日线：</span><span class="font-medium">{{ stopLossAnalysisResult.common_features.buy_below_ma10_count }}/{{ stopLossAnalysisResult.total_stocks }}</span></div>
              </div>
            </div>

            <!-- 规避建议 -->
            <div v-if="stopLossAnalysisResult.suggestions && stopLossAnalysisResult.suggestions.length > 0" class="mb-4">
              <h4 class="font-semibold text-gray-800 mb-2">规避建议</h4>
              <div class="space-y-2">
                <div 
                  v-for="(suggestion, index) in stopLossAnalysisResult.suggestions" 
                  :key="index"
                  class="p-3 rounded-lg"
                  :class="suggestion.priority === '高' ? 'bg-red-50 border border-red-200' : 'bg-yellow-50 border border-yellow-200'"
                >
                  <div class="flex items-start gap-2">
                    <span 
                      class="px-2 py-1 rounded text-xs font-semibold"
                      :class="suggestion.priority === '高' ? 'bg-red-200 text-red-800' : 'bg-yellow-200 text-yellow-800'"
                    >
                      {{ suggestion.priority }}
                    </span>
                    <div class="flex-1">
                      <div class="text-sm font-medium text-gray-800">{{ suggestion.type }}：{{ suggestion.description }}</div>
                      <div class="text-sm text-gray-600 mt-1">{{ suggestion.suggestion }}</div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- 详细分析 -->
            <div v-if="stopLossAnalysisResult.analysis && stopLossAnalysisResult.analysis.length > 0" class="mt-4">
              <h4 class="font-semibold text-gray-800 mb-2">详细分析</h4>
              <div class="overflow-x-auto">
                <table class="min-w-full divide-y divide-gray-200 text-sm">
                  <thead class="bg-gray-50">
                    <tr>
                      <th class="px-3 py-2 text-left">股票代码</th>
                      <th class="px-3 py-2 text-left">信号日期</th>
                      <th class="px-3 py-2 text-left">买入日期</th>
                      <th class="px-3 py-2 text-left">止损天数</th>
                      <th class="px-3 py-2 text-left">买入日跌幅</th>
                      <th class="px-3 py-2 text-left">买入价vs信号收盘</th>
                      <th class="px-3 py-2 text-left">低于5日线</th>
                      <th class="px-3 py-2 text-left">低于10日线</th>
                    </tr>
                  </thead>
                  <tbody class="bg-white divide-y divide-gray-200">
                    <tr v-for="(item, index) in stopLossAnalysisResult.analysis" :key="index">
                      <td class="px-3 py-2">{{ item.ts_code }}</td>
                      <td class="px-3 py-2">{{ item.signal_date }}</td>
                      <td class="px-3 py-2">{{ item.buy_date }}</td>
                      <td class="px-3 py-2">{{ item.days_to_stop_loss }}天</td>
                      <td class="px-3 py-2" :class="item.buy_change_pct < 0 ? 'text-red-600' : ''">{{ item.buy_change_pct?.toFixed(2) }}%</td>
                      <td class="px-3 py-2" :class="item.buy_price_vs_signal_close_pct > 3 ? 'text-red-600' : ''">{{ item.buy_price_vs_signal_close_pct?.toFixed(2) }}%</td>
                      <td class="px-3 py-2">{{ item.buy_below_ma5 ? '是' : '否' }}</td>
                      <td class="px-3 py-2">{{ item.buy_below_ma10 ? '是' : '否' }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 单票检测对话框 -->
    <div 
      v-if="showCheckDialog" 
      class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
      @click.self="showCheckDialog = false"
    >
      <div class="bg-white rounded-lg shadow-xl max-w-4xl w-full mx-4 max-h-[90vh] overflow-y-auto">
        <div class="p-6">
          <div class="flex items-center justify-between mb-4">
            <h2 class="text-xl font-bold text-gray-800">单票检测</h2>
            <button
              @click="showCheckDialog = false"
              class="text-gray-400 hover:text-gray-600"
            >
              <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <!-- 输入表单 -->
          <div class="space-y-4 mb-6">
            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">股票代码</label>
                <input
                  v-model="checkParams.ts_code"
                  type="text"
                  placeholder="如：688656.SH"
                  class="w-full px-3 py-2 border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <p class="mt-1 text-xs text-gray-500">格式：股票代码.市场（如：688656.SH 或 300001.SZ）</p>
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">检查日期（涨幅>=10%的日期）</label>
                <input
                  v-model="checkParams.check_date"
                  type="date"
                  class="w-full px-3 py-2 border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>
            <div class="flex justify-end gap-2">
              <button
                @click="showCheckDialog = false"
                class="px-4 py-2 text-gray-700 bg-gray-200 rounded-lg hover:bg-gray-300 text-sm"
              >
                取消
              </button>
              <button
                @click="checkSingleStock"
                :disabled="checking || !checkParams.ts_code || !checkParams.check_date"
                class="px-4 py-2 bg-pink-600 text-white rounded-lg hover:bg-pink-700 disabled:bg-gray-400 disabled:cursor-not-allowed text-sm flex items-center gap-2"
              >
                <span v-if="checking" class="animate-spin">⟳</span>
                {{ checking ? '检测中...' : '开始检测' }}
              </button>
            </div>
          </div>

          <!-- 检测结果 -->
          <div v-if="checkResult" class="border-t pt-4">
            <h3 class="text-lg font-semibold text-gray-800 mb-4">检测结果</h3>
            
            <!-- 基本信息 -->
            <div class="mb-4 p-4 bg-gray-50 rounded-lg">
              <div class="grid grid-cols-2 gap-4">
                <div>
                  <span class="text-sm text-gray-600">股票代码：</span>
                  <span class="text-sm font-medium">{{ checkResult.ts_code }}</span>
                </div>
                <div>
                  <span class="text-sm text-gray-600">检查日期：</span>
                  <span class="text-sm font-medium">{{ checkResult.check_date }}</span>
                </div>
                <div class="col-span-2">
                  <span class="text-sm text-gray-600">是否符合条件：</span>
                  <span 
                    class="text-sm font-bold"
                    :class="checkResult.qualified ? 'text-green-600' : 'text-red-600'"
                  >
                    {{ checkResult.qualified ? '✅ 符合' : '❌ 不符合' }}
                  </span>
                </div>
              </div>
            </div>

            <!-- 检测步骤 -->
            <div class="mb-4">
              <h4 class="text-md font-semibold text-gray-700 mb-2">检测步骤</h4>
              <div class="space-y-2">
                <div
                  v-for="step in checkResult.steps"
                  :key="step.step"
                  class="p-3 rounded-lg border"
                  :class="step.status === 'pass' ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'"
                >
                  <div class="flex items-start gap-2">
                    <span 
                      class="text-lg"
                      :class="step.status === 'pass' ? 'text-green-600' : 'text-red-600'"
                    >
                      {{ step.status === 'pass' ? '✅' : '❌' }}
                    </span>
                    <div class="flex-1">
                      <div class="font-medium text-sm text-gray-800">
                        {{ step.step }}. {{ step.name }}
                      </div>
                      <div class="text-sm text-gray-600 mt-1">{{ step.message }}</div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- 第2天和第3天详情 -->
            <div v-if="checkResult.day2 || checkResult.day3" class="mb-4">
              <h4 class="text-md font-semibold text-gray-700 mb-2">第2天和第3天详情</h4>
              <div class="grid grid-cols-2 gap-4">
                <div v-if="checkResult.day2" class="p-3 rounded-lg border" :class="checkResult.day2.qualified ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'">
                  <div class="font-medium text-sm text-gray-800 mb-2">第2天（{{ checkResult.day2.date }}）</div>
                  <div class="text-xs space-y-1 text-gray-600">
                    <div>量比：{{ checkResult.day2.volume_ratio !== null ? checkResult.day2.volume_ratio.toFixed(4) : '--' }}</div>
                    <div>涨跌幅：{{ checkResult.day2.change_pct !== null ? checkResult.day2.change_pct.toFixed(2) + '%' : '--' }}</div>
                    <div v-if="!checkResult.day2.qualified && checkResult.day2.reason" class="text-red-600 font-medium">
                      不符合原因：{{ checkResult.day2.reason }}
                    </div>
                    <div v-else-if="checkResult.day2.qualified" class="text-green-600 font-medium">
                      ✅ 符合条件
                    </div>
                  </div>
                </div>
                <div v-if="checkResult.day3" class="p-3 rounded-lg border" :class="checkResult.day3.qualified ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'">
                  <div class="font-medium text-sm text-gray-800 mb-2">第3天（{{ checkResult.day3.date }}）</div>
                  <div class="text-xs space-y-1 text-gray-600">
                    <div>量比：{{ checkResult.day3.volume_ratio !== null ? checkResult.day3.volume_ratio.toFixed(4) : '--' }}</div>
                    <div>涨跌幅：{{ checkResult.day3.change_pct !== null ? checkResult.day3.change_pct.toFixed(2) + '%' : '--' }}</div>
                    <div v-if="!checkResult.day3.qualified && checkResult.day3.reason" class="text-red-600 font-medium">
                      不符合原因：{{ checkResult.day3.reason }}
                    </div>
                    <div v-else-if="checkResult.day3.qualified" class="text-green-600 font-medium">
                      ✅ 符合条件
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- 错误信息 -->
            <div v-if="checkResult.errors && checkResult.errors.length > 0" class="p-3 bg-red-50 border border-red-200 rounded-lg">
              <h4 class="text-md font-semibold text-red-700 mb-2">错误信息</h4>
              <ul class="list-disc list-inside text-sm text-red-600 space-y-1">
                <li v-for="(error, index) in checkResult.errors" :key="index">{{ error }}</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import axios from 'axios'

const route = useRoute()

const stocks = ref([])
const loading = ref(false)
const loadingHistory = ref(false)
const loadingOneYear = ref(false)
const calculating = ref(false)
const calculatingCyb = ref(false)

// 根据路由路径设置默认策略类型
const getDefaultStrategyType = () => {
  const path = route.path
  if (path === '/limit-up-volume-shrink-cyb') {
    return 'cyb_rise_shrink'
  }
  return 'mainboard_limit_up'  // 默认主板策略
}
const strategyType = ref(getDefaultStrategyType())  // 策略类型：mainboard_limit_up(主板涨停缩量), cyb_rise_shrink(创业板科创板涨幅缩量)

// 监听路由变化，更新策略类型
watch(() => route.path, (newPath) => {
  if (newPath === '/limit-up-volume-shrink-cyb') {
    strategyType.value = 'cyb_rise_shrink'
  } else if (newPath === '/limit-up-volume-shrink-mainboard' || newPath === '/limit-up-volume-shrink') {
    strategyType.value = 'mainboard_limit_up'
  }
}, { immediate: true })

const queryDate = ref('')
const currentTradeDate = ref('')
const historyDateRange = ref(null)
const sortField = ref('limit_up_date')
const sortOrder = ref('desc')
const showBacktestDialog = ref(false)
const backtesting = ref(false)
const backtestResult = ref(null)
const backtestParams = ref({
  start_date: '',
  end_date: '',
  profit_target: 20,
  stop_loss: -10,
  max_hold_days: 5,
  sell_strategy: 'profit_stop'  // 'profit_stop': 止盈止损策略, 'ma5_loss': 破跌5日线或亏损5%策略, 'ma5_loss_5pct': 破跌5日线或亏损5%策略, 'ma5_rising': 上涨过程中不破5日线不卖或亏损5%策略
})

// 单票检测相关
const showCheckDialog = ref(false)
const checking = ref(false)
const checkResult = ref(null)
const checkParams = ref({
  ts_code: '',
  check_date: ''
})

// 止损股票分析相关
const showStopLossAnalysisDialog = ref(false)
const analyzingStopLoss = ref(false)
const stopLossStocksInput = ref('')
const stopLossAnalysisResult = ref(null)

// 交易记录相关
const showTradeRecordsDialog = ref(false)
const loadingTradeRecords = ref(false)
const tradeRecords = ref([])
const tradeRecordsTotal = ref(0)
const tradeRecordFilters = ref({
  start_date: '',
  end_date: '',
  exit_reason: '',
  min_return_pct: null,
  max_return_pct: null,
  sell_strategy: ''
})
const tradeRecordSort = ref('return_asc')

// 格式化股票代码（去掉后缀）
const formatCode = (tsCode) => {
  if (!tsCode) return '--'
  return tsCode.split('.')[0]
}

// 格式化数字
const formatNumber = (value, decimals = 2) => {
  if (value === null || value === undefined) return '--'
  return Number(value).toFixed(decimals)
}

// 格式化百分比
const formatPercent = (value) => {
  if (value === null || value === undefined) return '--'
  const num = Number(value)
  return (num >= 0 ? '+' : '') + num.toFixed(2) + '%'
}

// 格式化成交额
const formatAmount = (value) => {
  if (value === null || value === undefined) return '--'
  const num = Number(value)
  if (num >= 100000000) {
    return (num / 100000000).toFixed(2) + '亿'
  } else if (num >= 10000) {
    return (num / 10000).toFixed(2) + '万'
  }
  return num.toFixed(2)
}

// 获取涨跌幅颜色
const getChangeColor = (value) => {
  if (value === null || value === undefined) return 'text-gray-700'
  const num = Number(value)
  if (num > 0) return 'text-red-600 font-semibold'
  if (num < 0) return 'text-green-600 font-semibold'
  return 'text-gray-700'
}

// 排序
const sortBy = (field) => {
  if (sortField.value === field) {
    sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortField.value = field
    sortOrder.value = 'desc'
  }
}

// 排序后的股票列表
const sortedStocks = computed(() => {
  const sorted = [...stocks.value]
  
  sorted.sort((a, b) => {
    let aVal = a[sortField.value]
    let bVal = b[sortField.value]
    
    // 处理null/undefined
    if (aVal === null || aVal === undefined) return 1
    if (bVal === null || bVal === undefined) return -1
    
    // 日期字符串特殊处理
    if (sortField.value === 'limit_up_date') {
      aVal = aVal ? new Date(aVal).getTime() : 0
      bVal = bVal ? new Date(bVal).getTime() : 0
    } else {
      // 转换为数字进行比较
      aVal = Number(aVal)
      bVal = Number(bVal)
    }
    
    if (sortOrder.value === 'asc') {
      return aVal - bVal
    } else {
      return bVal - aVal
    }
  })
  
  return sorted
})

// 加载数据
const loadData = async () => {
  loading.value = true
  historyDateRange.value = null
  try {
    const params = {
      strategy_type: strategyType.value
    }
    if (queryDate.value) {
      params.trade_date = queryDate.value
    }
    
    const response = await axios.get('/api/limit-up-volume-shrink/list', { params })
    
    if (response.data.success) {
      stocks.value = response.data.data || []
      currentTradeDate.value = response.data.trade_date || ''
    } else {
      alert('查询失败：' + (response.data.message || '未知错误'))
    }
  } catch (error) {
    console.error('查询失败:', error)
    alert('查询失败：' + (error.response?.data?.detail || error.message))
  } finally {
    loading.value = false
  }
}

// 加载历史数据（先批量计算，再获取）
const loadHistoryData = async () => {
  loadingHistory.value = true
  currentTradeDate.value = ''
  try {
    // 计算日期范围（默认近1年）
    const endDate = new Date()
    const startDate = new Date()
    startDate.setFullYear(startDate.getFullYear() - 1)
    
    const startDateStr = startDate.toISOString().split('T')[0]
    const endDateStr = endDate.toISOString().split('T')[0]
    
    // 第一步：批量计算近1年的数据
    const confirmMsg = `将批量计算 ${startDateStr} 至 ${endDateStr} 的涨停缩量数据，这可能需要一些时间，是否继续？`
    if (!confirm(confirmMsg)) {
      loadingHistory.value = false
      return
    }
    
    alert('开始批量计算，请稍候...')
    
    const calcParams = {
      start_date: startDateStr,
      end_date: endDateStr
    }
    
    const calcResponse = await axios.post('/api/limit-up-volume-shrink/calculate-batch', null, { params: calcParams })
    
    if (!calcResponse.data.success) {
      alert('批量计算失败：' + (calcResponse.data.message || '未知错误'))
      loadingHistory.value = false
      return
    }
    
    alert(`批量计算完成：${calcResponse.data.message}`)
    
    // 第二步：获取历史数据
    const params = {
      start_date: startDateStr,
      end_date: endDateStr,
      strategy_type: strategyType.value,
      limit: 2000
    }
    
    const response = await axios.get('/api/limit-up-volume-shrink/history', { params })
    
    if (response.data.success) {
      stocks.value = response.data.data || []
      historyDateRange.value = response.data.date_range || null
      alert(`成功加载 ${response.data.count} 条历史数据`)
    } else {
      alert('加载历史数据失败：' + (response.data.message || '未知错误'))
    }
  } catch (error) {
    console.error('加载历史数据失败:', error)
    alert('加载历史数据失败：' + (error.response?.data?.detail || error.message))
  } finally {
    loadingHistory.value = false
  }
}

// 加载1年数据（仅限创业板/科创板）
const loadOneYearData = async () => {
  if (strategyType.value !== 'cyb_rise_shrink') {
    alert('此功能仅适用于创业板/科创板策略')
    return
  }
  
  loadingOneYear.value = true
  currentTradeDate.value = ''
  try {
    // 计算日期范围（近1年）
    const endDate = new Date()
    const startDate = new Date()
    startDate.setFullYear(startDate.getFullYear() - 1)
    
    const startDateStr = startDate.toISOString().split('T')[0]
    const endDateStr = endDate.toISOString().split('T')[0]
    
    // 直接查询历史数据（会触发从 fact_daily_price_qfq 计算并保存）
    const params = {
      start_date: startDateStr,
      end_date: endDateStr,
      strategy_type: 'cyb_rise_shrink',
      limit: 10000
    }
    
    const response = await axios.get('/api/limit-up-volume-shrink/history', { params })
    
    if (response.data.success) {
      stocks.value = response.data.data || []
      historyDateRange.value = response.data.date_range || null
      alert(`成功加载 ${response.data.count} 条创业板/科创板数据（${startDateStr} 至 ${endDateStr}）`)
    } else {
      alert('加载数据失败：' + (response.data.message || '未知错误'))
    }
  } catch (error) {
    console.error('加载1年数据失败:', error)
    alert('加载数据失败：' + (error.response?.data?.detail || error.message))
  } finally {
    loadingOneYear.value = false
  }
}

// 计算主板涨停缩量
const calculate = async () => {
  calculating.value = true
  try {
    const params = {}
    if (queryDate.value) {
      params.trade_date = queryDate.value
    }
    
    const response = await axios.post('/api/limit-up-volume-shrink/calculate', null, { params })
    
    if (response.data.success) {
      alert(`计算完成：${response.data.message}`)
      // 计算完成后重新加载数据
      await loadData()
    } else {
      alert('计算失败：' + (response.data.message || '未知错误'))
    }
  } catch (error) {
    console.error('计算失败:', error)
    alert('计算失败：' + (error.response?.data?.detail || error.message))
  } finally {
    calculating.value = false
  }
}

// 计算创业板科创板涨幅缩量
const calculateCyb = async () => {
  calculatingCyb.value = true
  try {
    const params = {}
    if (queryDate.value) {
      params.trade_date = queryDate.value
    }
    
    const response = await axios.post('/api/limit-up-volume-shrink/cyb-rise-shrink/calculate', null, { params })
    
    if (response.data.success) {
      alert(`计算完成：${response.data.message}`)
      // 计算完成后可以提示用户切换到创业板科创板数据查看
      // 注意：当前页面显示的是主板数据，如果需要查看创业板科创板数据，需要调用对应的查询接口
    } else {
      alert('计算失败：' + (response.data.message || '未知错误'))
    }
  } catch (error) {
    console.error('计算失败:', error)
    alert('计算失败：' + (error.response?.data?.detail || error.message))
  } finally {
    calculatingCyb.value = false
  }
}

// 加入跟踪池
const addToWatchlist = async (stock) => {
  try {
    const response = await axios.post('/api/watchlist', {
      ts_code: stock.ts_code,
      note: '涨停缩量'
    })
    
    if (response.data.success) {
      alert('已加入跟踪池')
    } else {
      alert('加入失败：' + (response.data.message || '未知错误'))
    }
  } catch (error) {
    console.error('加入跟踪池失败:', error)
    alert('加入失败：' + (error.response?.data?.detail || error.message))
  }
}

// 执行回测
const runBacktest = async () => {
  backtesting.value = true
  backtestResult.value = null
  try {
    const params = {
      profit_target: backtestParams.value.profit_target / 100, // 转换为小数
      stop_loss: backtestParams.value.stop_loss / 100, // 转换为小数
      max_hold_days: backtestParams.value.max_hold_days,
      sell_strategy: backtestParams.value.sell_strategy,
      strategy_type: strategyType.value  // 添加策略类型参数
    }
    
    if (backtestParams.value.start_date) {
      params.start_date = backtestParams.value.start_date
    }
    if (backtestParams.value.end_date) {
      params.end_date = backtestParams.value.end_date
    }
    
    const response = await axios.get('/api/limit-up-volume-shrink/backtest', { params })
    
    if (response.data.success) {
      backtestResult.value = response.data
    } else {
      backtestResult.value = { success: false, error: response.data.error || '回测失败' }
    }
  } catch (error) {
    console.error('回测失败:', error)
    backtestResult.value = { 
      success: false, 
      error: error.response?.data?.detail || error.message || '回测失败' 
    }
  } finally {
    backtesting.value = false
  }
}

// 初始化：设置默认日期为今天
onMounted(() => {
  const today = new Date()
  queryDate.value = today.toISOString().split('T')[0]
  
  // 设置回测默认日期（1年前到今天）
  const oneYearAgo = new Date()
  oneYearAgo.setFullYear(oneYearAgo.getFullYear() - 1)
  backtestParams.value.start_date = oneYearAgo.toISOString().split('T')[0]
  backtestParams.value.end_date = today.toISOString().split('T')[0]
  
  loadData()
})

// 显示交易记录对话框
const showTradeRecords = () => {
  showTradeRecordsDialog.value = true
  // 如果有回测结果，使用回测的日期范围和策略
  if (backtestResult.value && backtestResult.value.backtest_period) {
    tradeRecordFilters.value.start_date = backtestResult.value.backtest_period.start_date
    tradeRecordFilters.value.end_date = backtestResult.value.backtest_period.end_date
    if (backtestResult.value.parameters && backtestResult.value.parameters.sell_strategy) {
      tradeRecordFilters.value.sell_strategy = backtestResult.value.parameters.sell_strategy
    }
  } else {
    // 如果没有回测结果，设置默认日期范围（最近1年）
    const today = new Date()
    const oneYearAgo = new Date()
    oneYearAgo.setFullYear(oneYearAgo.getFullYear() - 1)
    tradeRecordFilters.value.start_date = oneYearAgo.toISOString().split('T')[0]
    tradeRecordFilters.value.end_date = today.toISOString().split('T')[0]
    tradeRecordFilters.value.sell_strategy = '' // 不限制策略
  }
  loadTradeRecords()
}

// 加载交易记录
const loadTradeRecords = async () => {
  loadingTradeRecords.value = true
  try {
    const params = {
      limit: 5000,
      offset: 0,
      strategy_type: strategyType.value  // 添加策略类型参数
    }
    
    if (tradeRecordFilters.value.start_date) {
      params.start_date = tradeRecordFilters.value.start_date
    }
    if (tradeRecordFilters.value.end_date) {
      params.end_date = tradeRecordFilters.value.end_date
    }
    if (tradeRecordFilters.value.exit_reason) {
      params.exit_reason = tradeRecordFilters.value.exit_reason
    }
    if (tradeRecordFilters.value.min_return_pct !== null) {
      params.min_return_pct = tradeRecordFilters.value.min_return_pct / 100
    }
    if (tradeRecordFilters.value.max_return_pct !== null) {
      params.max_return_pct = tradeRecordFilters.value.max_return_pct / 100
    }
    if (tradeRecordFilters.value.sell_strategy) {
      params.sell_strategy = tradeRecordFilters.value.sell_strategy
    }
    
    const response = await axios.get('/api/limit-up-volume-shrink/backtest/trades', { params })
    
    if (response.data.success) {
      tradeRecords.value = response.data.data || []
      tradeRecordsTotal.value = response.data.total || 0
    } else {
      alert('加载交易记录失败：' + (response.data.message || '未知错误'))
    }
  } catch (error) {
    console.error('加载交易记录失败:', error)
    alert('加载交易记录失败：' + (error.response?.data?.detail || error.message))
  } finally {
    loadingTradeRecords.value = false
  }
}

// 排序后的交易记录
const sortedTradeRecords = computed(() => {
  const sorted = [...tradeRecords.value]
  
  sorted.sort((a, b) => {
    if (tradeRecordSort.value === 'return_asc') {
      return (a.return_pct || 0) - (b.return_pct || 0)
    } else if (tradeRecordSort.value === 'return_desc') {
      return (b.return_pct || 0) - (a.return_pct || 0)
    } else if (tradeRecordSort.value === 'date_desc') {
      return new Date(b.signal_date) - new Date(a.signal_date)
    } else if (tradeRecordSort.value === 'date_asc') {
      return new Date(a.signal_date) - new Date(b.signal_date)
    }
    return 0
  })
  
  return sorted
})

// 获取退出原因文本
const getExitReasonText = (reason) => {
  const reasonMap = {
    'profit_target': '止盈',
    'stop_loss': '止损',
    'time_limit': '时间限制',
    'loss_10pct': '亏损10%',
    'loss_5pct': '亏损5%',
    'break_ma5': '破5日线',
    'data_end': '数据结束',
    'day3_no_limit_up': '第三天未涨停',
    'limit_up_broken': '炸板'
  }
  return reasonMap[reason] || reason || '--'
}

// 获取卖出策略文本
const getSellStrategyText = (strategy) => {
  const strategyMap = {
    'profit_stop': '策略1：止盈止损',
    'ma5_loss': '策略2：破跌5日线或亏损5%，从第三天开始没有涨停就退出',
    'ma5_loss_5pct': '策略3：破跌5日线或亏损5%',
    'ma5_rising': '策略4：上涨过程中不破5日线不卖，止损-5%'
  }
  return strategyMap[strategy] || strategy || '--'
}

// 获取收益率颜色
const getReturnColor = (returnPct) => {
  if (returnPct === null || returnPct === undefined) return 'text-gray-700'
  const num = Number(returnPct)
  if (num > 0) return 'text-red-600 font-semibold'
  if (num < 0) return 'text-green-600 font-semibold'
  return 'text-gray-700'
}

// 亏损分析计算属性
const lossByExitReason = computed(() => {
  if (!backtestResult.value || !backtestResult.value.signals) return {}
  const lossSignals = backtestResult.value.signals.filter(s => s.trade && s.trade.profit_loss_pct < 0)
  const result = {}
  lossSignals.forEach(signal => {
    const reason = signal.trade.exit_reason || 'unknown'
    result[reason] = (result[reason] || 0) + 1
  })
  return result
})

const lossAmountByExitReason = computed(() => {
  if (!backtestResult.value || !backtestResult.value.signals) return {}
  const lossSignals = backtestResult.value.signals.filter(s => s.trade && s.trade.profit_loss_pct < 0)
  const result = {}
  lossSignals.forEach(signal => {
    const reason = signal.trade.exit_reason || 'unknown'
    result[reason] = (result[reason] || 0) + (signal.trade.profit_loss || 0)
  })
  return result
})

const totalLossAmount = computed(() => {
  if (!backtestResult.value || !backtestResult.value.signals) return 0
  const lossSignals = backtestResult.value.signals.filter(s => s.trade && s.trade.profit_loss_pct < 0)
  return lossSignals.reduce((sum, s) => sum + (s.trade.profit_loss || 0), 0)
})

const avgLossAmount = computed(() => {
  if (!backtestResult.value || !backtestResult.value.signals) return 0
  const lossSignals = backtestResult.value.signals.filter(s => s.trade && s.trade.profit_loss_pct < 0)
  if (lossSignals.length === 0) return 0
  return totalLossAmount.value / lossSignals.length
})

const maxLossAmount = computed(() => {
  if (!backtestResult.value || !backtestResult.value.signals) return 0
  const lossSignals = backtestResult.value.signals.filter(s => s.trade && s.trade.profit_loss_pct < 0)
  if (lossSignals.length === 0) return 0
  return Math.min(...lossSignals.map(s => s.trade.profit_loss || 0))
})

const avgLossPct = computed(() => {
  if (!backtestResult.value || !backtestResult.value.signals) return 0
  const lossSignals = backtestResult.value.signals.filter(s => s.trade && s.trade.profit_loss_pct < 0)
  if (lossSignals.length === 0) return 0
  const sum = lossSignals.reduce((sum, s) => sum + (s.trade.profit_loss_pct || 0), 0)
  return sum / lossSignals.length
})

const lossDistribution = computed(() => {
  if (!backtestResult.value || !backtestResult.value.signals) {
    return { '<-10%': 0, '-10% to -5%': 0, '-5% to -2%': 0, '-2% to 0%': 0, 'small': 0 }
  }
  const lossSignals = backtestResult.value.signals.filter(s => s.trade && s.trade.profit_loss_pct < 0)
  const result = { '<-10%': 0, '-10% to -5%': 0, '-5% to -2%': 0, '-2% to 0%': 0, 'small': 0 }
  lossSignals.forEach(signal => {
    const pct = signal.trade.profit_loss_pct || 0
    if (pct < -0.10) {
      result['<-10%']++
    } else if (pct < -0.05) {
      result['-10% to -5%']++
    } else if (pct < -0.02) {
      result['-5% to -2%']++
    } else if (pct < 0) {
      result['-2% to 0%']++
    }
    if (pct > -0.01 && pct < 0) {
      result['small']++
    }
  })
  return result
})

const topLossStocks = computed(() => {
  if (!backtestResult.value || !backtestResult.value.signals) return []
  const lossSignals = backtestResult.value.signals
    .filter(s => s.trade && s.trade.profit_loss_pct < 0)
    .map(s => ({ ...s }))
  lossSignals.sort((a, b) => (a.trade.profit_loss || 0) - (b.trade.profit_loss || 0))
  return lossSignals.slice(0, 10)
})

// 单票检测
const checkSingleStock = async () => {
  if (!checkParams.value.ts_code || !checkParams.value.check_date) {
    alert('请填写股票代码和检查日期')
    return
  }

  checking.value = true
  checkResult.value = null
  
  try {
    const response = await axios.get('/api/limit-up-volume-shrink/cyb-rise-shrink/check', {
      params: {
        ts_code: checkParams.value.ts_code,
        check_date: checkParams.value.check_date
      }
    })
    
    if (response.data.success) {
      checkResult.value = response.data.result
    } else {
      alert('检测失败：' + (response.data.message || '未知错误'))
    }
  } catch (error) {
    console.error('单票检测失败:', error)
    alert('检测失败：' + (error.response?.data?.detail || error.message))
  } finally {
    checking.value = false
  }
}

// 分析止损股票
const analyzeStopLossStocks = async () => {
  if (!stopLossStocksInput.value.trim()) {
    alert('请输入止损股票列表')
    return
  }
  
  analyzingStopLoss.value = true
  stopLossAnalysisResult.value = null
  
  try {
    // 解析输入的股票列表
    // 支持格式：
    // 1. 股票代码 日期（如：300845.SZ 2025-08-20）
    // 2. 股票代码 股票名称 日期 ...（如：300845.SZ	捷安高科	2025-08-20	-10.14%	-5982 元	止损）
    const lines = stopLossStocksInput.value.trim().split('\n').filter(line => line.trim())
    const stocks = []
    
    for (const line of lines) {
      const parts = line.trim().split(/\s+/)  // 按空格或制表符分割
      if (parts.length >= 2) {
        // 尝试找到日期（格式：YYYY-MM-DD）
        let dateStr = null
        let tsCode = parts[0]
        
        // 查找日期格式的字符串
        for (let i = 1; i < parts.length; i++) {
          const part = parts[i]
          // 检查是否是日期格式（YYYY-MM-DD）
          if (/^\d{4}-\d{2}-\d{2}$/.test(part)) {
            dateStr = part
            break
          }
        }
        
        // 如果没有找到日期格式，尝试第二个部分（兼容旧格式）
        if (!dateStr && parts.length >= 2) {
          // 如果第二个部分看起来像日期，使用它
          if (/^\d{4}-\d{2}-\d{2}$/.test(parts[1])) {
            dateStr = parts[1]
          } else {
            // 否则尝试第三个部分
            if (parts.length >= 3 && /^\d{4}-\d{2}-\d{2}$/.test(parts[2])) {
              dateStr = parts[2]
            }
          }
        }
        
        if (dateStr && tsCode) {
          stocks.push({
            ts_code: tsCode,
            signal_date: dateStr  // 实际是卖出日期
          })
        }
      }
    }
    
    if (stocks.length === 0) {
      alert('请正确输入股票列表，格式：股票代码 日期（如：300845.SZ 2025-08-20）')
      return
    }
    
    const response = await axios.post('/api/limit-up-volume-shrink/analyze-stop-loss-stocks', stocks)
    
    if (response.data.success) {
      stopLossAnalysisResult.value = response.data.result
    } else {
      alert('分析失败：' + (response.data.message || '未知错误'))
    }
  } catch (error) {
    console.error('分析止损股票失败:', error)
    alert('分析失败：' + (error.response?.data?.detail || error.message))
  } finally {
    analyzingStopLoss.value = false
  }
}
</script>

<style scoped>
.slide-down-enter-active,
.slide-down-leave-active {
  transition: all 0.3s ease;
  max-height: 500px;
  overflow: hidden;
}

.slide-down-enter-from,
.slide-down-leave-to {
  max-height: 0;
  opacity: 0;
}
</style>
