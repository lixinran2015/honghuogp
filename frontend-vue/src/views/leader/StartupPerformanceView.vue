<template>
  <div class="container mx-auto px-4 py-6">
    <!-- 页面标题 -->
    <div class="mb-6">
      <h1 class="text-2xl font-bold text-gray-800">启动股票表现分析</h1>
      <p class="text-sm text-gray-500 mt-1">显示得分≥60的股票入选后的涨幅表现（后5日、10日、20日、60日）</p>
    </div>

    <!-- 标签页 -->
    <div class="mb-6">
      <div class="border-b border-gray-200">
        <nav class="-mb-px flex space-x-8">
          <button
            @click="activeTab = 'performance'"
            :class="activeTab === 'performance' ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'"
            class="whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm"
          >
            📊 表现统计
          </button>
          <button
            @click="activeTab = 'risk-analysis'"
            :class="activeTab === 'risk-analysis' ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'"
            class="whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm"
          >
            🔍 风险分析
          </button>
          <button
            @click="activeTab = 'backtest'"
            :class="activeTab === 'backtest' ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'"
            class="whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm"
          >
            📈 策略回测
          </button>
        </nav>
      </div>
    </div>

    <!-- 查询参数 -->
    <div class="bg-white rounded-lg shadow-md p-6 mb-6">
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        <!-- 查询天数 -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">查询最近N天</label>
          <input
            v-model.number="params.days"
            type="number"
            min="1"
            max="365"
            class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="30"
          />
        </div>
        
        <!-- 最低得分 -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">最低得分</label>
          <input
            v-model.number="params.min_score"
            type="number"
            min="60"
            max="100"
            class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="60"
          />
        </div>
      </div>
      
      <!-- 查询按钮 -->
      <button
        @click="fetchData"
        :disabled="loading"
        class="px-6 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
      >
        <span v-if="loading">查询中...</span>
        <span v-else>🔍 查询</span>
      </button>
    </div>

    <!-- 统计信息 -->
    <div v-if="stats" class="bg-white rounded-lg shadow-md p-6 mb-6">
      <h2 class="text-lg font-semibold text-gray-700 mb-4">📊 统计信息</h2>
      <div class="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
        <div class="text-center">
          <div class="text-sm text-gray-500">总数</div>
          <div class="text-2xl font-bold text-gray-900">{{ stats.total }}</div>
        </div>
        <div class="text-center">
          <div class="text-sm text-gray-500">后5日平均涨幅</div>
          <div class="text-2xl font-bold" :class="getColorClass(stats.avg_change_5d)">
            {{ formatPercent(stats.avg_change_5d) }}
          </div>
          <div class="text-xs text-gray-500">正收益: {{ stats.positive_5d }}</div>
        </div>
        <div class="text-center">
          <div class="text-sm text-gray-500">后10日平均涨幅</div>
          <div class="text-2xl font-bold" :class="getColorClass(stats.avg_change_10d)">
            {{ formatPercent(stats.avg_change_10d) }}
          </div>
          <div class="text-xs text-gray-500">正收益: {{ stats.positive_10d }}</div>
        </div>
        <div class="text-center">
          <div class="text-sm text-gray-500">后20日平均涨幅</div>
          <div class="text-2xl font-bold" :class="getColorClass(stats.avg_change_20d)">
            {{ formatPercent(stats.avg_change_20d) }}
          </div>
          <div class="text-xs text-gray-500">正收益: {{ stats.positive_20d }}</div>
        </div>
        <div class="text-center">
          <div class="text-sm text-gray-500">后60日平均涨幅</div>
          <div class="text-2xl font-bold" :class="getColorClass(stats.avg_change_60d)">
            {{ formatPercent(stats.avg_change_60d) }}
          </div>
          <div class="text-xs text-gray-500">正收益: {{ stats.positive_60d }}</div>
        </div>
      </div>
      
      <!-- 按得分分组统计 -->
      <div class="border-t pt-4 mt-4">
        <h3 class="text-md font-semibold text-gray-700 mb-3">📊 按得分分组统计</h3>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <!-- 60分组 -->
          <div v-if="stats.by_score && stats.by_score.score_60" class="bg-yellow-50 p-4 rounded-lg border-2 border-yellow-300">
            <div class="text-center mb-3">
              <div class="text-lg font-bold text-yellow-800">60-69分</div>
              <div class="text-sm text-gray-600">样本数: {{ stats.by_score.score_60.count }}</div>
            </div>
            <div class="grid grid-cols-2 gap-2 text-sm">
              <div>
                <div class="text-gray-600">后5日</div>
                <div class="font-bold" :class="getColorClass(stats.by_score.score_60.avg_change_5d)">
                  {{ formatPercent(stats.by_score.score_60.avg_change_5d) }}
                </div>
                <div class="text-xs text-gray-500">正收益: {{ stats.by_score.score_60.positive_5d }}</div>
              </div>
              <div>
                <div class="text-gray-600">后10日</div>
                <div class="font-bold" :class="getColorClass(stats.by_score.score_60.avg_change_10d)">
                  {{ formatPercent(stats.by_score.score_60.avg_change_10d) }}
                </div>
                <div class="text-xs text-gray-500">正收益: {{ stats.by_score.score_60.positive_10d }}</div>
              </div>
              <div>
                <div class="text-gray-600">后20日</div>
                <div class="font-bold" :class="getColorClass(stats.by_score.score_60.avg_change_20d)">
                  {{ formatPercent(stats.by_score.score_60.avg_change_20d) }}
                </div>
                <div class="text-xs text-gray-500">正收益: {{ stats.by_score.score_60.positive_20d }}</div>
              </div>
              <div>
                <div class="text-gray-600">后60日</div>
                <div class="font-bold" :class="getColorClass(stats.by_score.score_60.avg_change_60d)">
                  {{ formatPercent(stats.by_score.score_60.avg_change_60d) }}
                </div>
                <div class="text-xs text-gray-500">正收益: {{ stats.by_score.score_60.positive_60d }}</div>
              </div>
            </div>
          </div>
          
          <!-- 70分组 -->
          <div v-if="stats.by_score && stats.by_score.score_70" class="bg-orange-50 p-4 rounded-lg border-2 border-orange-300">
            <div class="text-center mb-3">
              <div class="text-lg font-bold text-orange-800">70-79分</div>
              <div class="text-sm text-gray-600">样本数: {{ stats.by_score.score_70.count }}</div>
            </div>
            <div class="grid grid-cols-2 gap-2 text-sm">
              <div>
                <div class="text-gray-600">后5日</div>
                <div class="font-bold" :class="getColorClass(stats.by_score.score_70.avg_change_5d)">
                  {{ formatPercent(stats.by_score.score_70.avg_change_5d) }}
                </div>
                <div class="text-xs text-gray-500">正收益: {{ stats.by_score.score_70.positive_5d }}</div>
              </div>
              <div>
                <div class="text-gray-600">后10日</div>
                <div class="font-bold" :class="getColorClass(stats.by_score.score_70.avg_change_10d)">
                  {{ formatPercent(stats.by_score.score_70.avg_change_10d) }}
                </div>
                <div class="text-xs text-gray-500">正收益: {{ stats.by_score.score_70.positive_10d }}</div>
              </div>
              <div>
                <div class="text-gray-600">后20日</div>
                <div class="font-bold" :class="getColorClass(stats.by_score.score_70.avg_change_20d)">
                  {{ formatPercent(stats.by_score.score_70.avg_change_20d) }}
                </div>
                <div class="text-xs text-gray-500">正收益: {{ stats.by_score.score_70.positive_20d }}</div>
              </div>
              <div>
                <div class="text-gray-600">后60日</div>
                <div class="font-bold" :class="getColorClass(stats.by_score.score_70.avg_change_60d)">
                  {{ formatPercent(stats.by_score.score_70.avg_change_60d) }}
                </div>
                <div class="text-xs text-gray-500">正收益: {{ stats.by_score.score_70.positive_60d }}</div>
              </div>
            </div>
          </div>
          
          <!-- 80分组 -->
          <div v-if="stats.by_score && stats.by_score.score_80" class="bg-red-50 p-4 rounded-lg border-2 border-red-300">
            <div class="text-center mb-3">
              <div class="text-lg font-bold text-red-800">80分及以上</div>
              <div class="text-sm text-gray-600">样本数: {{ stats.by_score.score_80.count }}</div>
            </div>
            <div class="grid grid-cols-2 gap-2 text-sm">
              <div>
                <div class="text-gray-600">后5日</div>
                <div class="font-bold" :class="getColorClass(stats.by_score.score_80.avg_change_5d)">
                  {{ formatPercent(stats.by_score.score_80.avg_change_5d) }}
                </div>
                <div class="text-xs text-gray-500">正收益: {{ stats.by_score.score_80.positive_5d }}</div>
              </div>
              <div>
                <div class="text-gray-600">后10日</div>
                <div class="font-bold" :class="getColorClass(stats.by_score.score_80.avg_change_10d)">
                  {{ formatPercent(stats.by_score.score_80.avg_change_10d) }}
                </div>
                <div class="text-xs text-gray-500">正收益: {{ stats.by_score.score_80.positive_10d }}</div>
              </div>
              <div>
                <div class="text-gray-600">后20日</div>
                <div class="font-bold" :class="getColorClass(stats.by_score.score_80.avg_change_20d)">
                  {{ formatPercent(stats.by_score.score_80.avg_change_20d) }}
                </div>
                <div class="text-xs text-gray-500">正收益: {{ stats.by_score.score_80.positive_20d }}</div>
              </div>
              <div>
                <div class="text-gray-600">后60日</div>
                <div class="font-bold" :class="getColorClass(stats.by_score.score_80.avg_change_60d)">
                  {{ formatPercent(stats.by_score.score_80.avg_change_60d) }}
                </div>
                <div class="text-xs text-gray-500">正收益: {{ stats.by_score.score_80.positive_60d }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
      
      <!-- 条件统计：只统计前一个阶段为正收益的股票在下一阶段的表现 -->
      <div class="border-t pt-4 mt-4">
        <h3 class="text-md font-semibold text-gray-700 mb-3">📈 条件统计（前阶段正收益的股票在下一阶段的表现）</h3>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div class="text-center bg-blue-50 p-4 rounded-lg">
            <div class="text-sm text-gray-600 mb-2">后5日正收益 → 后10日平均涨幅</div>
            <div class="text-xl font-bold" :class="getColorClass(stats.avg_change_10d_after_positive_5d)">
              {{ formatPercent(stats.avg_change_10d_after_positive_5d) }}
            </div>
            <div class="text-xs text-gray-500 mt-1">
              样本数: {{ stats.count_10d_after_positive_5d || 0 }} | 
              正收益: {{ stats.positive_10d_after_positive_5d || 0 }}
            </div>
          </div>
          <div class="text-center bg-green-50 p-4 rounded-lg">
            <div class="text-sm text-gray-600 mb-2">后10日正收益 → 后20日平均涨幅</div>
            <div class="text-xl font-bold" :class="getColorClass(stats.avg_change_20d_after_positive_10d)">
              {{ formatPercent(stats.avg_change_20d_after_positive_10d) }}
            </div>
            <div class="text-xs text-gray-500 mt-1">
              样本数: {{ stats.count_20d_after_positive_10d || 0 }} | 
              正收益: {{ stats.positive_20d_after_positive_10d || 0 }}
            </div>
          </div>
          <div class="text-center bg-purple-50 p-4 rounded-lg">
            <div class="text-sm text-gray-600 mb-2">后20日正收益 → 后60日平均涨幅</div>
            <div class="text-xl font-bold" :class="getColorClass(stats.avg_change_60d_after_positive_20d)">
              {{ formatPercent(stats.avg_change_60d_after_positive_20d) }}
            </div>
            <div class="text-xs text-gray-500 mt-1">
              样本数: {{ stats.count_60d_after_positive_20d || 0 }} | 
              正收益: {{ stats.positive_60d_after_positive_20d || 0 }}
            </div>
          </div>
        </div>
      </div>
      
      <!-- 按成交额分组统计 -->
      <div class="border-t pt-4 mt-4">
        <h3 class="text-md font-semibold text-gray-700 mb-3">💰 按成交额分组统计</h3>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <!-- 成交额 < 30亿 -->
          <div v-if="stats.by_amount && stats.by_amount.low_amount" class="bg-blue-50 p-4 rounded-lg border-2 border-blue-300">
            <div class="text-center mb-3">
              <div class="text-lg font-bold text-blue-800">成交额 &lt; 30亿</div>
              <div class="text-sm text-gray-600">样本数: {{ stats.by_amount.low_amount.count }}</div>
            </div>
            <div class="grid grid-cols-2 gap-2 text-sm">
              <div>
                <div class="text-gray-600">后5日</div>
                <div class="font-bold" :class="getColorClass(stats.by_amount.low_amount.avg_change_5d)">
                  {{ formatPercent(stats.by_amount.low_amount.avg_change_5d) }}
                </div>
                <div class="text-xs text-gray-500">正收益: {{ stats.by_amount.low_amount.positive_5d }}</div>
              </div>
              <div>
                <div class="text-gray-600">后10日</div>
                <div class="font-bold" :class="getColorClass(stats.by_amount.low_amount.avg_change_10d)">
                  {{ formatPercent(stats.by_amount.low_amount.avg_change_10d) }}
                </div>
                <div class="text-xs text-gray-500">正收益: {{ stats.by_amount.low_amount.positive_10d }}</div>
              </div>
              <div>
                <div class="text-gray-600">后20日</div>
                <div class="font-bold" :class="getColorClass(stats.by_amount.low_amount.avg_change_20d)">
                  {{ formatPercent(stats.by_amount.low_amount.avg_change_20d) }}
                </div>
                <div class="text-xs text-gray-500">正收益: {{ stats.by_amount.low_amount.positive_20d }}</div>
              </div>
              <div>
                <div class="text-gray-600">后60日</div>
                <div class="font-bold" :class="getColorClass(stats.by_amount.low_amount.avg_change_60d)">
                  {{ formatPercent(stats.by_amount.low_amount.avg_change_60d) }}
                </div>
                <div class="text-xs text-gray-500">正收益: {{ stats.by_amount.low_amount.positive_60d }}</div>
              </div>
            </div>
          </div>
          
          <!-- 成交额 >= 30亿 -->
          <div v-if="stats.by_amount && stats.by_amount.high_amount" class="bg-green-50 p-4 rounded-lg border-2 border-green-300">
            <div class="text-center mb-3">
              <div class="text-lg font-bold text-green-800">成交额 ≥ 30亿</div>
              <div class="text-sm text-gray-600">样本数: {{ stats.by_amount.high_amount.count }}</div>
            </div>
            <div class="grid grid-cols-2 gap-2 text-sm">
              <div>
                <div class="text-gray-600">后5日</div>
                <div class="font-bold" :class="getColorClass(stats.by_amount.high_amount.avg_change_5d)">
                  {{ formatPercent(stats.by_amount.high_amount.avg_change_5d) }}
                </div>
                <div class="text-xs text-gray-500">正收益: {{ stats.by_amount.high_amount.positive_5d }}</div>
              </div>
              <div>
                <div class="text-gray-600">后10日</div>
                <div class="font-bold" :class="getColorClass(stats.by_amount.high_amount.avg_change_10d)">
                  {{ formatPercent(stats.by_amount.high_amount.avg_change_10d) }}
                </div>
                <div class="text-xs text-gray-500">正收益: {{ stats.by_amount.high_amount.positive_10d }}</div>
              </div>
              <div>
                <div class="text-gray-600">后20日</div>
                <div class="font-bold" :class="getColorClass(stats.by_amount.high_amount.avg_change_20d)">
                  {{ formatPercent(stats.by_amount.high_amount.avg_change_20d) }}
                </div>
                <div class="text-xs text-gray-500">正收益: {{ stats.by_amount.high_amount.positive_20d }}</div>
              </div>
              <div>
                <div class="text-gray-600">后60日</div>
                <div class="font-bold" :class="getColorClass(stats.by_amount.high_amount.avg_change_60d)">
                  {{ formatPercent(stats.by_amount.high_amount.avg_change_60d) }}
                </div>
                <div class="text-xs text-gray-500">正收益: {{ stats.by_amount.high_amount.positive_60d }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 表现统计标签页 -->
    <div v-if="activeTab === 'performance'">
      <!-- 数据表格 -->
      <div class="bg-white rounded-lg shadow-md overflow-hidden">
      <div class="overflow-x-auto">
        <table class="min-w-full divide-y divide-gray-200">
          <thead class="bg-gray-50">
            <tr>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">股票代码</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">股票名称</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">入选日期</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">得分</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">阶段</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">入选价</th>
              <th 
                class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                @click="sortBy('entry_amount')"
              >
                <div class="flex items-center justify-center space-x-1">
                  <span>成交额</span>
                  <span v-if="sortField === 'entry_amount'" class="text-blue-600">
                    {{ sortOrder === 'asc' ? '↑' : '↓' }}
                  </span>
                </div>
              </th>
              <th 
                class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                @click="sortBy('change_5d')"
              >
                <div class="flex items-center justify-center space-x-1">
                  <span>后5日涨幅</span>
                  <span v-if="sortField === 'change_5d'" class="text-blue-600">
                    {{ sortOrder === 'asc' ? '↑' : '↓' }}
                  </span>
                </div>
              </th>
              <th 
                class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                @click="sortBy('change_10d')"
              >
                <div class="flex items-center justify-center space-x-1">
                  <span>后10日涨幅</span>
                  <span v-if="sortField === 'change_10d'" class="text-blue-600">
                    {{ sortOrder === 'asc' ? '↑' : '↓' }}
                  </span>
                </div>
              </th>
              <th 
                class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                @click="sortBy('change_20d')"
              >
                <div class="flex items-center justify-center space-x-1">
                  <span>后20日涨幅</span>
                  <span v-if="sortField === 'change_20d'" class="text-blue-600">
                    {{ sortOrder === 'asc' ? '↑' : '↓' }}
                  </span>
                </div>
              </th>
              <th 
                class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                @click="sortBy('change_60d')"
              >
                <div class="flex items-center justify-center space-x-1">
                  <span>后60日涨幅</span>
                  <span v-if="sortField === 'change_60d'" class="text-blue-600">
                    {{ sortOrder === 'asc' ? '↑' : '↓' }}
                  </span>
                </div>
              </th>
            </tr>
          </thead>
          <tbody class="bg-white divide-y divide-gray-200">
            <tr v-for="stock in sortedStocks" :key="`${stock.ts_code}-${stock.entry_date}`" class="hover:bg-gray-50">
              <td class="px-4 py-3 whitespace-nowrap text-sm font-medium text-gray-900">{{ stock.ts_code }}</td>
              <td class="px-4 py-3 whitespace-nowrap text-sm text-gray-900">{{ stock.name }}</td>
              <td class="px-4 py-3 whitespace-nowrap text-sm text-gray-500">{{ stock.entry_date }}</td>
              <td class="px-4 py-3 whitespace-nowrap text-sm text-gray-900">
                <span class="px-2 py-1 rounded text-xs font-semibold" :class="getScoreClass(stock.score)">
                  {{ stock.score }}
                </span>
              </td>
              <td class="px-4 py-3 whitespace-nowrap text-sm text-gray-500">{{ stock.stage }}</td>
              <td class="px-4 py-3 whitespace-nowrap text-sm text-gray-900">{{ stock.entry_price }}</td>
              <td class="px-4 py-3 whitespace-nowrap text-sm text-gray-900">
                <span v-if="stock.entry_amount !== null && stock.entry_amount !== undefined">
                  {{ formatAmount(stock.entry_amount) }}
                </span>
                <span v-else class="text-gray-400">--</span>
              </td>
              <td class="px-4 py-3 whitespace-nowrap text-sm text-center">
                <div class="font-semibold" :class="getChangeClass(stock.change_5d)">
                  {{ formatPercent(stock.change_5d) }}
                </div>
                <div v-if="stock.change_5d_days && stock.change_5d_days < 5" class="text-xs text-gray-400">
                  ({{ stock.change_5d_days }}天)
                </div>
              </td>
              <td class="px-4 py-3 whitespace-nowrap text-sm text-center">
                <div class="font-semibold" :class="getChangeClass(stock.change_10d)">
                  {{ formatPercent(stock.change_10d) }}
                </div>
                <div v-if="stock.change_10d_days && stock.change_10d_days < 10" class="text-xs text-gray-400">
                  ({{ stock.change_10d_days }}天)
                </div>
              </td>
              <td class="px-4 py-3 whitespace-nowrap text-sm text-center">
                <div class="font-semibold" :class="getChangeClass(stock.change_20d)">
                  {{ formatPercent(stock.change_20d) }}
                </div>
                <div v-if="stock.change_20d_days && stock.change_20d_days < 20" class="text-xs text-gray-400">
                  ({{ stock.change_20d_days }}天)
                </div>
              </td>
              <td class="px-4 py-3 whitespace-nowrap text-sm text-center">
                <div class="font-semibold" :class="getChangeClass(stock.change_60d)">
                  {{ formatPercent(stock.change_60d) }}
                </div>
                <div v-if="stock.change_60d_days && stock.change_60d_days < 60" class="text-xs text-gray-400">
                  ({{ stock.change_60d_days }}天)
                </div>
              </td>
            </tr>
            <tr v-if="stocks.length === 0">
              <td colspan="11" class="px-4 py-8 text-center text-gray-500">
                <span v-if="loading">加载中...</span>
                <span v-else>暂无数据</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
    </div>

    <!-- 风险分析标签页 -->
    <div v-if="activeTab === 'risk-analysis'">
      <!-- 查询按钮 -->
      <div class="bg-white rounded-lg shadow-md p-6 mb-6">
        <button
          @click="fetchRiskAnalysis"
          :disabled="riskAnalysisLoading"
          class="px-6 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
        >
          <span v-if="riskAnalysisLoading">分析中...</span>
          <span v-else>🔍 开始分析</span>
        </button>
      </div>

      <!-- 风险分析结果 -->
      <div v-if="riskAnalysisData" class="space-y-6">
        <!-- 总体统计 -->
        <div class="bg-white rounded-lg shadow-md p-6">
          <h2 class="text-lg font-semibold text-gray-700 mb-4">📊 总体统计</h2>
          <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div class="text-center p-4 bg-gray-50 rounded-lg">
              <div class="text-sm text-gray-500">总数</div>
              <div class="text-2xl font-bold text-gray-900">{{ riskAnalysisData.summary.total_count }}</div>
            </div>
            <div class="text-center p-4 bg-green-50 rounded-lg">
              <div class="text-sm text-gray-500">正收益</div>
              <div class="text-2xl font-bold text-green-600">{{ riskAnalysisData.summary.positive_count }}</div>
              <div class="text-xs text-gray-500">{{ riskAnalysisData.summary.positive_rate }}%</div>
            </div>
            <div class="text-center p-4 bg-red-50 rounded-lg">
              <div class="text-sm text-gray-500">负收益</div>
              <div class="text-2xl font-bold text-red-600">{{ riskAnalysisData.summary.negative_count }}</div>
              <div class="text-xs text-gray-500">{{ riskAnalysisData.summary.negative_rate }}%</div>
            </div>
            <div class="text-center p-4 bg-gray-50 rounded-lg">
              <div class="text-sm text-gray-500">零收益</div>
              <div class="text-2xl font-bold text-gray-600">{{ riskAnalysisData.summary.zero_count }}</div>
            </div>
          </div>
        </div>

        <!-- 按risk_passed分类统计 -->
        <div class="bg-white rounded-lg shadow-md p-6">
          <h2 class="text-lg font-semibold text-gray-700 mb-4">🎯 按风险排除状态分类</h2>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div class="p-4 bg-green-50 rounded-lg">
              <div class="text-sm font-semibold text-gray-700 mb-2">✅ risk_passed = True（通过风险排除）</div>
              <div class="text-sm text-gray-600">总数: {{ riskAnalysisData.by_risk_passed.risk_passed_true.total }}</div>
              <div class="text-sm text-green-600">正收益: {{ riskAnalysisData.by_risk_passed.risk_passed_true.positive }}</div>
              <div class="text-sm text-red-600">负收益: {{ riskAnalysisData.by_risk_passed.risk_passed_true.negative }}</div>
              <div class="text-sm font-semibold text-blue-600 mt-2">正收益率: {{ riskAnalysisData.by_risk_passed.risk_passed_true.positive_rate }}%</div>
            </div>
            <div class="p-4 bg-yellow-50 rounded-lg">
              <div class="text-sm font-semibold text-gray-700 mb-2">⚠️ risk_passed = False（未通过风险排除）</div>
              <div class="text-sm text-gray-600">总数: {{ riskAnalysisData.by_risk_passed.risk_passed_false.total }}</div>
              <div class="text-sm text-green-600">正收益: {{ riskAnalysisData.by_risk_passed.risk_passed_false.positive }}</div>
              <div class="text-sm text-red-600">负收益: {{ riskAnalysisData.by_risk_passed.risk_passed_false.negative }}</div>
              <div class="text-sm font-semibold text-blue-600 mt-2">正收益率: {{ riskAnalysisData.by_risk_passed.risk_passed_false.positive_rate }}%</div>
            </div>
          </div>
        </div>

        <!-- 按风险原因分组统计 -->
        <div class="bg-white rounded-lg shadow-md p-6">
          <h2 class="text-lg font-semibold text-gray-700 mb-4">📋 按风险原因分组统计</h2>
          <div class="overflow-x-auto">
            <table class="min-w-full divide-y divide-gray-200">
              <thead class="bg-gray-50">
                <tr>
                  <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">风险原因</th>
                  <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">总数</th>
                  <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">正收益</th>
                  <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">负收益</th>
                  <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">零收益</th>
                  <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">平均涨幅</th>
                  <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">正收益率</th>
                </tr>
              </thead>
              <tbody class="bg-white divide-y divide-gray-200">
                <tr v-for="(stats, reason) in riskAnalysisData.by_risk_reasons" :key="reason" class="hover:bg-gray-50">
                  <td class="px-4 py-3 text-sm font-medium text-gray-900">{{ reason }}</td>
                  <td class="px-4 py-3 text-sm text-center text-gray-900">{{ stats.total }}</td>
                  <td class="px-4 py-3 text-sm text-center text-green-600 font-semibold">{{ stats.positive }}</td>
                  <td class="px-4 py-3 text-sm text-center text-red-600 font-semibold">{{ stats.negative }}</td>
                  <td class="px-4 py-3 text-sm text-center text-gray-600">{{ stats.zero }}</td>
                  <td class="px-4 py-3 text-sm text-center font-semibold" :class="getColorClass(stats.avg_change)">
                    {{ formatPercent(stats.avg_change) }}
                  </td>
                  <td class="px-4 py-3 text-sm text-center text-blue-600 font-semibold">{{ stats.positive_rate }}%</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import axios from 'axios'

export default {
  name: 'StartupPerformanceView',
  data() {
    return {
      activeTab: 'performance', // 'performance' 或 'risk-analysis' 或 'backtest'
      loading: false,
      riskAnalysisLoading: false,
      backtestLoading: false,
      stocks: [],
      stats: null,
      riskAnalysisData: null,
      backtestResult: null,
      sortField: null,  // 当前排序字段
      sortOrder: 'desc',  // 排序方向：'asc' 或 'desc'
      params: {
        days: 365,
        min_score: 60
      },
      backtestParams: {
        start_date: '',
        end_date: '',
        initial_capital: 300000,
        capital_per_stock: 30000,
        max_stocks_per_day: 10,
        max_hold_days: 5,
        stop_loss: -10,
        min_score: 60,
        risk_passed: true
      }
    }
  },
  computed: {
    sortedStocks() {
      if (!this.sortField) {
        return this.stocks
      }
      
      const sorted = [...this.stocks]
      sorted.sort((a, b) => {
        const aValue = a[this.sortField]
        const bValue = b[this.sortField]
        
        // 处理 null/undefined 值，将它们排在最后
        if (aValue === null || aValue === undefined) return 1
        if (bValue === null || bValue === undefined) return -1
        
        if (this.sortOrder === 'asc') {
          return aValue - bValue
        } else {
          return bValue - aValue
        }
      })
      
      return sorted
    }
  },
  mounted() {
    this.fetchData()
    // 设置默认回测日期
    const today = new Date()
    const oneYearAgo = new Date(today)
    oneYearAgo.setFullYear(today.getFullYear() - 1)
    this.backtestParams.end_date = today.toISOString().split('T')[0]
    this.backtestParams.start_date = oneYearAgo.toISOString().split('T')[0]
  },
  methods: {
    async fetchData() {
      this.loading = true
      try {
        const response = await axios.get('/api/startup/performance', {
          params: this.params
        })
        
        if (response.data.success) {
          this.stocks = response.data.data
          this.stats = response.data.stats
        } else {
          alert('查询失败')
        }
      } catch (error) {
        console.error('查询失败:', error)
        alert('查询失败: ' + (error.response?.data?.detail || error.message))
      } finally {
        this.loading = false
      }
    },
    async fetchRiskAnalysis() {
      this.riskAnalysisLoading = true
      try {
        const response = await axios.get('/api/startup/performance-analysis', {
          params: this.params
        })
        
        if (response.data.success) {
          this.riskAnalysisData = response.data
        } else {
          alert('分析失败')
        }
      } catch (error) {
        console.error('分析失败:', error)
        alert('分析失败: ' + (error.response?.data?.detail || error.message))
      } finally {
        this.riskAnalysisLoading = false
      }
    },
    async runBacktest() {
      this.backtestLoading = true
      try {
        const params = {
          ...this.backtestParams,
          stop_loss: this.backtestParams.stop_loss / 100  // 转换为小数
        }
        const response = await axios.get('/api/startup/backtest', {
          params: params
        })
        
        if (response.data.success) {
          this.backtestResult = response.data
        } else {
          alert('回测失败')
        }
      } catch (error) {
        console.error('回测失败:', error)
        alert('回测失败: ' + (error.response?.data?.detail || error.message))
      } finally {
        this.backtestLoading = false
      }
    },
    formatPercent(value) {
      if (value === null || value === undefined) {
        return '-'
      }
      return value >= 0 ? `+${value.toFixed(2)}%` : `${value.toFixed(2)}%`
    },
    getChangeClass(value) {
      if (value === null || value === undefined) {
        return 'text-gray-400'
      }
      return value >= 0 ? 'text-red-600' : 'text-green-600'
    },
    getColorClass(value) {
      if (value === null || value === undefined) {
        return 'text-gray-400'
      }
      return value >= 0 ? 'text-red-600' : 'text-green-600'
    },
    getScoreClass(score) {
      if (score >= 100) {
        return 'bg-red-100 text-red-800'
      } else if (score >= 60) {
        return 'bg-yellow-100 text-yellow-800'
      } else {
        return 'bg-gray-100 text-gray-800'
      }
    },
    formatCurrency(value) {
      if (value === null || value === undefined) {
        return '-'
      }
      return value >= 0 ? `+${value.toFixed(2)}` : `${value.toFixed(2)}`
    },
    formatAmount(value) {
      if (value === null || value === undefined) {
        return '--'
      }
      const v = value || 0
      if (v >= 1e8) return (v / 1e8).toFixed(2) + '亿'
      if (v >= 1e4) return (v / 1e4).toFixed(2) + '万'
      return v.toFixed(2)
    },
    getExitReasonText(reason) {
      const reasonMap = {
        'max_hold_days': '达到最大持有天数',
        'stop_loss': '触发止损',
        'end_of_backtest': '回测结束'
      }
      return reasonMap[reason] || reason
    },
    sortBy(field) {
      if (this.sortField === field) {
        // 如果点击的是同一列，切换排序方向
        this.sortOrder = this.sortOrder === 'asc' ? 'desc' : 'asc'
      } else {
        // 如果点击的是不同列，设置新的排序字段，默认降序
        this.sortField = field
        this.sortOrder = 'desc'
      }
    }
  }
}
</script>

<style scoped>
/* 可以添加自定义样式 */
</style>
