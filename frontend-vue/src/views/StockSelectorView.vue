<template>
  <div class="stock-selector-page min-h-screen bg-gray-50 dark:bg-gray-900/40">
    <div class="max-w-[1600px] mx-auto px-4 sm:px-6 py-6 lg:py-8">
      <!-- 页面标题与 Tab -->
      <header class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
        <div>
          <h1 class="text-2xl sm:text-3xl font-bold tracking-tight text-gray-900 dark:text-white">
            选股
          </h1>
          <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">
            按投资风格、行业与财务条件筛选股票
          </p>
        </div>
        <nav class="flex rounded-xl bg-white dark:bg-gray-800/80 p-1 shadow-soft border border-gray-200/80 dark:border-gray-700/80" aria-label="筛选与回测">
          <button
            type="button"
            @click="activeTab = 'filter'"
            :class="[
              'px-5 py-2.5 rounded-lg text-sm font-medium transition-all',
              activeTab === 'filter'
                ? 'bg-primary-500 text-white shadow-sm'
                : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-700/60'
            ]"
          >
            筛选
          </button>
          <button
            type="button"
            @click="activeTab = 'backtest'; syncBacktestFromFilter()"
            :class="[
              'px-5 py-2.5 rounded-lg text-sm font-medium transition-all',
              activeTab === 'backtest'
                ? 'bg-primary-500 text-white shadow-sm'
                : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-700/60'
            ]"
          >
            回测
          </button>
        </nav>
      </header>

    <!-- 筛选 Tab -->
    <template v-if="activeTab === 'filter'">
    <!-- 筛选区 -->
    <section class="bg-white dark:bg-gray-800/90 rounded-2xl shadow-soft border border-gray-200/80 dark:border-gray-700/80 overflow-hidden mb-6">
      <div class="p-5 sm:p-6">
        <div class="grid grid-cols-1 lg:grid-cols-12 gap-5 items-end">
          <!-- 投资风格 -->
          <div class="lg:col-span-2">
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">投资风格</label>
            <div class="flex rounded-lg bg-gray-100 dark:bg-gray-700/60 p-1">
              <label class="flex-1 cursor-pointer">
                <input v-model="filter.style" type="radio" value="aggressive" class="sr-only" />
                <span :class="['block text-center py-2 px-3 rounded-md text-sm font-medium transition-all', filter.style === 'aggressive' ? 'bg-white dark:bg-gray-600 shadow-sm text-gray-900 dark:text-white' : 'text-gray-600 dark:text-gray-400']">激进型</span>
              </label>
              <label class="flex-1 cursor-pointer">
                <input v-model="filter.style" type="radio" value="conservative" class="sr-only" />
                <span :class="['block text-center py-2 px-3 rounded-md text-sm font-medium transition-all', filter.style === 'conservative' ? 'bg-white dark:bg-gray-600 shadow-sm text-gray-900 dark:text-white' : 'text-gray-600 dark:text-gray-400']">稳健型</span>
              </label>
            </div>
          </div>
          <div class="lg:col-span-2">
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">周期筛选</label>
            <select
              v-model="filter.cycle_filter"
              class="input-select w-full"
            >
              <option value="all">不限</option>
              <option value="exclude_declining">排除下滑期</option>
              <option value="rising_only">仅上升期</option>
              <option value="mature_only">仅成熟期</option>
            </select>
          </div>
          <div class="lg:col-span-2">
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">新高条件</label>
            <select
              v-model="filter.new_high"
              class="input-select w-full"
            >
              <option value="none">不限</option>
              <option value="30">30日新高</option>
              <option value="60">60日新高</option>
              <option value="90">90日新高</option>
              <option value="120">120日新高</option>
            </select>
          </div>
          <div class="lg:col-span-2">
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">排序</label>
            <select
              v-model="filter.order_by"
              class="input-select w-full"
            >
              <option value="roe">净资产收益率</option>
              <option value="revenue_growth">营收增速</option>
              <option value="gross_margin">毛利率</option>
              <option value="net_cash_ratio">净现比</option>
              <option value="revenue">营收</option>
            </select>
          </div>
          <div class="lg:col-span-2 flex items-center gap-2">
            <input
              id="use-cycle-thresholds"
              v-model="filter.use_cycle_thresholds"
              type="checkbox"
              class="h-4 w-4 rounded border-gray-300 dark:border-gray-600 text-primary-600 focus:ring-primary-500"
            />
            <label for="use-cycle-thresholds" class="text-sm text-gray-700 dark:text-gray-300">按周期调阈值</label>
          </div>
          <div class="lg:col-span-2 flex justify-end">
            <button
              type="button"
              @click="doQuery()"
              :disabled="loading"
              class="btn-primary px-5 py-2.5 rounded-xl text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {{ loading ? '筛选中...' : '筛选' }}
            </button>
          </div>
        </div>
        <!-- 进一步筛选：净现比>0、负债率<50%、仅行业/板块龙头 -->
        <div class="mt-3 pt-3 border-t border-gray-200 dark:border-gray-600/80 flex flex-wrap gap-x-6 gap-y-2">
          <label class="inline-flex items-center gap-1.5 text-sm text-gray-700 dark:text-gray-300 cursor-pointer select-none">
            <input
              v-model="filter.net_cash_ratio_positive"
              type="checkbox"
              class="rounded border-gray-300 dark:border-gray-500 text-primary-600 focus:ring-primary-500"
            />
            <span>净现比>0</span>
          </label>
          <label class="inline-flex items-center gap-1.5 text-sm text-gray-700 dark:text-gray-300 cursor-pointer select-none">
            <input
              v-model="filter.debt_ratio_lt_50"
              type="checkbox"
              class="rounded border-gray-300 dark:border-gray-500 text-primary-600 focus:ring-primary-500"
            />
            <span>负债率&lt;50%</span>
          </label>
          <label class="inline-flex items-center gap-1.5 text-sm text-gray-700 dark:text-gray-300 cursor-pointer select-none">
            <input
              v-model="filter.only_industry_leader"
              type="checkbox"
              class="rounded border-gray-300 dark:border-gray-500 text-primary-600 focus:ring-primary-500"
            />
            <span>仅行业/板块龙头</span>
          </label>
          <span class="inline-flex items-center gap-1.5 text-sm">
            <label class="text-gray-600 dark:text-gray-400">角色龙头：</label>
            <select
              v-model="filter.sector_leader_role_filter"
              class="input-select py-1 px-2 text-sm rounded-md border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-200"
            >
              <option value="">不限</option>
              <option value="绝对龙头">绝对龙头</option>
              <option value="补涨">补涨</option>
              <option value="跟风">跟风</option>
            </select>
          </span>
        </div>
        <!-- 行业多选：单独一行标题，下面逐项可多选 -->
        <div class="mt-4 pt-4 border-t border-gray-200 dark:border-gray-600/80">
          <p class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">行业</p>
          <p class="text-xs text-gray-500 dark:text-gray-400 mb-2">
            可多选，不选=全行业{{ filter.style === 'conservative' ? '；当前仅列成熟期' : filter.style === 'aggressive' ? '；当前仅列上升期' : '' }}
          </p>
          <div class="flex flex-wrap gap-x-4 gap-y-2">
            <label
              v-for="item in industryOptionsForSelect"
              :key="item.industry"
              class="inline-flex items-center gap-1.5 text-sm text-gray-700 dark:text-gray-300 cursor-pointer select-none"
            >
              <input
                type="checkbox"
                :checked="(filter.industries || []).includes(item.industry)"
                @change="toggleIndustry(item.industry)"
                class="rounded border-gray-300 dark:border-gray-500 text-primary-600 focus:ring-primary-500"
              />
              <span>{{ item.industry }}</span>
            </label>
          </div>
          <p class="text-xs text-gray-500 dark:text-gray-400 mt-2">
            <button type="button" @click="selectAllIndustries" class="text-primary-600 dark:text-primary-400 hover:underline">全选</button>
            <span class="mx-1">|</span>
            <button type="button" @click="clearAllIndustries" class="text-primary-600 dark:text-primary-400 hover:underline">清空</button>
          </p>
        </div>

        <!-- 当前筛选条件说明 -->
        <div class="mt-4 pt-4 border-t border-gray-200 dark:border-gray-600/80">
          <p class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">当前筛选条件</p>
          <ul class="text-sm text-gray-600 dark:text-gray-400 space-y-1 list-disc list-inside">
            <li>取每只股票<strong>最新报告期</strong>财报，排除 ST、资不抵债</li>
            <li v-for="(line, i) in styleConditionLines" :key="i">{{ line }}</li>
            <li v-if="filter.new_high && filter.new_high !== 'none'">满足<strong>{{ filter.new_high }}日新高</strong>（距区间最高价≤约 3%）</li>
            <li v-if="filter.use_cycle_thresholds">按行业周期使用<strong>动态净现比/收现比</strong>阈值</li>
            <li v-if="filter.net_cash_ratio_positive">进一步筛选：<strong>净现比&gt;0</strong></li>
            <li v-if="filter.debt_ratio_lt_50">进一步筛选：<strong>负债率&lt;50%</strong></li>
            <li v-if="filter.only_industry_leader">进一步筛选：<strong>仅行业/板块龙头</strong></li>
            <li v-if="filter.sector_leader_role_filter">进一步筛选：<strong>角色龙头={{ filter.sector_leader_role_filter }}</strong></li>
          </ul>
          <div class="mt-3 flex items-center gap-2">
            <button
              type="button"
              @click="openAiChat"
              class="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-purple-600 dark:text-purple-400 hover:bg-purple-50 dark:hover:bg-purple-900/30 rounded-lg transition-colors"
            >
              <span>💬</span>
              <span>问 AI</span>
            </button>
            <span class="text-xs text-gray-500 dark:text-gray-400">根据当前筛选条件向 AI 提问</span>
          </div>
          <details class="mt-3 group">
            <summary class="text-sm text-primary-600 dark:text-primary-400 cursor-pointer hover:underline">高级覆盖（可选）</summary>
            <div class="mt-3 flex flex-wrap gap-4">
              <div>
                <label class="block text-xs text-gray-500 dark:text-gray-400 mb-1">最低净资产收益率%</label>
                <input v-model.number="filter.min_roe" type="number" step="0.5" placeholder="覆盖" class="input-number w-24" />
              </div>
              <div>
                <label class="block text-xs text-gray-500 dark:text-gray-400 mb-1">最高负债率%</label>
                <input v-model.number="filter.max_debt_ratio" type="number" step="1" placeholder="覆盖" class="input-number w-24" />
              </div>
            </div>
          </details>
        </div>
      </div>
    </section>

    <!-- 结果区 -->
    <section class="bg-white dark:bg-gray-800/90 rounded-2xl shadow-soft border border-gray-200/80 dark:border-gray-700/80 overflow-hidden">
      <div v-if="loading" class="flex flex-col items-center justify-center py-16">
        <div class="inline-block animate-spin rounded-full h-10 w-10 border-2 border-primary-500 border-t-transparent"></div>
        <p class="mt-3 text-sm text-gray-500 dark:text-gray-400">正在筛选...</p>
      </div>
      <div v-else-if="error" class="text-center py-12 px-4">
        <p class="text-red-600 dark:text-red-400 font-medium">{{ error }}</p>
      </div>
      <div v-else-if="!resultList.length && hasQueried" class="text-center py-16 px-4 max-w-xl mx-auto">
        <p class="text-gray-500 dark:text-gray-400">暂无符合条件股票。</p>
        <p class="mt-2 text-sm text-gray-600 dark:text-gray-400">选股会同时应用<strong>行业</strong>与<strong>投资风格（稳健型/激进型）</strong>的全部财务与估值条件，并非“只按行业筛”。</p>
        <p v-if="queryHint" class="mt-3 text-sm text-amber-600 dark:text-amber-400">{{ queryHint }}</p>
      </div>
      <div v-else-if="resultList.length > 0" class="overflow-x-auto">
        <table class="stock-table min-w-full">
          <thead class="bg-gray-100/80 dark:bg-gray-700/60 sticky top-0 z-10">
            <tr>
              <th class="th-cell th-left">代码</th>
              <th class="th-cell th-left">名称</th>
              <th class="th-cell th-left">行业</th>
              <th class="th-cell th-left">行业周期</th>
              <th class="th-cell th-left">新高</th>
              <th class="th-cell th-left">报告期</th>
              <th class="th-cell th-left">行业/板块龙头</th>
              <th class="th-cell th-left" title="按板块划分：每只股在其所属板块中的角色，同一行业可含多板块故有多只绝对龙头">角色龙头</th>
              <th class="th-cell th-num">净资产收益率%</th>
              <th class="th-cell th-num">净利率%</th>
              <th class="th-cell th-num">负债率%</th>
              <th class="th-cell th-num">净现比</th>
              <th class="th-cell th-num">市盈率</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-200/80 dark:divide-gray-600/80">
            <tr
              v-for="row in resultList"
              :key="row.ts_code"
              class="tr-row"
            >
              <td class="td-cell font-medium text-gray-900 dark:text-gray-100 tabular-nums">{{ row.ts_code }}</td>
              <td class="td-cell text-gray-700 dark:text-gray-300">{{ row.name }}</td>
              <td class="td-cell text-gray-600 dark:text-gray-400">{{ row.industry || '--' }}</td>
              <td class="td-cell text-gray-600 dark:text-gray-400">{{ row.industry_cycle || '--' }}</td>
              <td class="td-cell text-gray-600 dark:text-gray-400">{{ row.new_high_type || '--' }}</td>
              <td class="td-cell text-gray-600 dark:text-gray-400">{{ row.end_date || '--' }}</td>
              <td class="td-cell text-gray-600 dark:text-gray-400">{{ row.industry_leader_label || '--' }}</td>
              <td class="td-cell" :title="row.sector_leader_of_sector ? `${row.sector_leader_role}（${row.sector_leader_of_sector}板块）` : ''">
                <span v-if="row.sector_leader_role" class="px-2 py-0.5 rounded text-xs font-medium" :class="{
                  'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300': row.sector_leader_role === '绝对龙头',
                  'bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-300': row.sector_leader_role === '补涨',
                  'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300': row.sector_leader_role === '跟风'
                }">
                  {{ row.sector_leader_role }}{{ row.sector_leader_of_sector ? `(${row.sector_leader_of_sector})` : '' }}
                </span>
                <span v-else class="text-gray-400">--</span>
              </td>
              <td class="td-cell td-num">{{ formatNum(row.roe) }}</td>
              <td class="td-cell td-num">{{ formatNum(row.net_margin) }}</td>
              <td class="td-cell td-num">{{ formatNum(row.debt_ratio) }}</td>
              <td class="td-cell td-num">{{ formatNum(row.net_cash_ratio) }}</td>
              <td class="td-cell td-num">{{ formatNum(row.pe_ttm) }}</td>
            </tr>
          </tbody>
        </table>
        <!-- 分页 -->
        <div v-if="pagination.total > pagination.page_size" class="px-4 py-3 flex items-center justify-between border-t border-gray-200 dark:border-gray-600/80 bg-gray-50/50 dark:bg-gray-800/50">
          <span class="text-sm text-gray-600 dark:text-gray-400">
            共 {{ pagination.total }} 条，第 {{ pagination.page }} / {{ totalPages }} 页
          </span>
          <div class="flex gap-2">
            <button
              type="button"
              @click="goPage(pagination.page - 1)"
              :disabled="pagination.page <= 1"
              class="px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              上一页
            </button>
            <button
              type="button"
              @click="goPage(pagination.page + 1)"
              :disabled="pagination.page >= totalPages"
              class="px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              下一页
            </button>
          </div>
        </div>
      </div>
    </section>
    </template>

    <!-- 回测 Tab -->
    <template v-if="activeTab === 'backtest'">
      <section class="bg-white dark:bg-gray-800/90 rounded-2xl shadow-soft border border-gray-200/80 dark:border-gray-700/80 overflow-hidden mb-6">
        <div class="p-5 sm:p-6">
          <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-4">回测参数</h2>
          <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-5">
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">开始日期</label>
              <input v-model="backtestParams.start_date" type="date" class="input-select w-full" />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">结束日期</label>
              <input v-model="backtestParams.end_date" type="date" class="input-select w-full" />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">投资风格</label>
              <select v-model="backtestParams.style" class="input-select w-full">
                <option value="aggressive">激进型</option>
                <option value="conservative">稳健型</option>
              </select>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">调仓频率</label>
              <select v-model="backtestParams.rebalance_freq" class="input-select w-full">
                <option value="monthly">每月</option>
                <option value="quarterly">每季</option>
              </select>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">持有天数</label>
              <input v-model.number="backtestParams.hold_days" type="number" min="1" max="250" class="input-select w-full" />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">每次调仓只数</label>
              <input v-model.number="backtestParams.max_stocks_per_rebalance" type="number" min="1" max="50" class="input-select w-full" />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">排序</label>
              <select v-model="backtestParams.order_by" class="input-select w-full">
                <option value="roe">净资产收益率</option>
                <option value="revenue_growth">营收增速</option>
                <option value="gross_margin">毛利率</option>
                <option value="net_cash_ratio">净现比</option>
                <option value="revenue">营收</option>
              </select>
            </div>
            <div class="sm:col-span-2">
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">行业（可选，逗号分隔）</label>
              <input v-model="backtestParams.industries" type="text" placeholder="如: 银行,医药" class="input-select w-full" />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">周期筛选</label>
              <select v-model="backtestParams.cycle_filter" class="input-select w-full">
                <option value="all">不限</option>
                <option value="exclude_declining">排除下滑期</option>
                <option value="rising_only">仅上升期</option>
                <option value="mature_only">仅成熟期</option>
              </select>
            </div>
            <div class="flex items-center gap-2">
              <input id="backtest-use-cycle-thresholds" v-model="backtestParams.use_cycle_thresholds" type="checkbox" class="h-4 w-4 rounded border-gray-300 dark:border-gray-600 text-primary-600 focus:ring-primary-500" />
              <label for="backtest-use-cycle-thresholds" class="text-sm text-gray-700 dark:text-gray-300">按行业周期调整净现比/收现比</label>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">新高条件</label>
              <select v-model="backtestParams.new_high" class="input-select w-full">
                <option value="none">不限</option>
                <option value="30">30日新高</option>
                <option value="60">60日新高</option>
                <option value="90">90日新高</option>
                <option value="120">120日新高</option>
              </select>
            </div>
          </div>
          <div class="flex items-center gap-4 flex-wrap">
            <button
              type="button"
              @click="runBacktest"
              :disabled="backtestLoading"
              class="btn-primary px-5 py-2.5 rounded-xl text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {{ backtestLoading ? '回测中...' : '开始回测' }}
            </button>
            <p v-if="backtestError" class="text-sm text-red-600 dark:text-red-400">{{ backtestError }}</p>
          </div>
        </div>
      </section>

      <!-- 回测结果 -->
      <section v-if="backtestResult" class="bg-white dark:bg-gray-800/90 rounded-2xl shadow-soft border border-gray-200/80 dark:border-gray-700/80 overflow-hidden">
        <div class="p-5 sm:p-6">
          <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-1">回测结果</h2>
          <p class="text-xs text-gray-500 dark:text-gray-400 mb-5">仅供参考，不构成投资建议。历史表现不代表未来。</p>
          <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
            <div class="backtest-card rounded-xl p-4 border border-gray-200/80 dark:border-gray-600/80">
              <div class="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">胜率</div>
              <div class="text-xl font-semibold text-gray-900 dark:text-white mt-1">{{ backtestResult.win_rate != null ? backtestResult.win_rate + '%' : '--' }}</div>
            </div>
            <div class="backtest-card rounded-xl p-4 border border-gray-200/80 dark:border-gray-600/80">
              <div class="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">平均收益</div>
              <div class="text-xl font-semibold mt-1" :class="backtestResult.avg_return != null && backtestResult.avg_return >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'">
                {{ backtestResult.avg_return != null ? backtestResult.avg_return + '%' : '--' }}
              </div>
            </div>
            <div class="backtest-card rounded-xl p-4 border border-gray-200/80 dark:border-gray-600/80">
              <div class="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">基准(沪深300)</div>
              <div class="text-xl font-semibold text-gray-900 dark:text-white mt-1">{{ backtestResult.benchmark_return != null ? backtestResult.benchmark_return + '%' : '--' }}</div>
            </div>
            <div class="backtest-card rounded-xl p-4 border border-gray-200/80 dark:border-gray-600/80">
              <div class="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">超额收益</div>
              <div class="text-xl font-semibold mt-1" :class="backtestResult.excess_return != null && backtestResult.excess_return >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'">
                {{ backtestResult.excess_return != null ? backtestResult.excess_return + '%' : '--' }}
              </div>
            </div>
            <div class="backtest-card rounded-xl p-4 border border-gray-200/80 dark:border-gray-600/80">
              <div class="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">交易次数</div>
              <div class="text-xl font-semibold text-gray-900 dark:text-white mt-1">{{ backtestResult.total_trades ?? 0 }}</div>
            </div>
            <div class="backtest-card rounded-xl p-4 border border-gray-200/80 dark:border-gray-600/80">
              <div class="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">调仓次数</div>
              <div class="text-xl font-semibold text-gray-900 dark:text-white mt-1">{{ backtestResult.rebalance_dates?.length ?? 0 }}</div>
            </div>
          </div>
          <div v-if="backtestResult.curve_dates?.length && backtestResult.curve_strategy_pct?.length" class="rounded-xl border border-gray-200/80 dark:border-gray-600/80 overflow-hidden mb-5" style="height: 300px">
            <div ref="backtestChartRef" class="w-full h-full"></div>
          </div>
          <div v-if="backtestResult.trades && backtestResult.trades.length > 0" class="overflow-x-auto rounded-xl border border-gray-200/80 dark:border-gray-600/80">
            <table class="stock-table min-w-full">
              <thead class="bg-gray-100/80 dark:bg-gray-700/60">
                <tr>
                  <th class="th-cell th-left">代码</th>
                  <th class="th-cell th-left">买入日</th>
                  <th class="th-cell th-left">卖出日</th>
                  <th class="th-cell th-num">买入价</th>
                  <th class="th-cell th-num">卖出价</th>
                  <th class="th-cell th-num">收益率%</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-200/80 dark:divide-gray-600/80">
                <tr v-for="(t, i) in backtestResult.trades" :key="i" class="tr-row">
                  <td class="td-cell font-medium text-gray-900 dark:text-gray-100">{{ t.ts_code }}</td>
                  <td class="td-cell text-gray-600 dark:text-gray-400">{{ t.buy_date }}</td>
                  <td class="td-cell text-gray-600 dark:text-gray-400">{{ t.sell_date }}</td>
                  <td class="td-cell td-num">{{ t.buy_price }}</td>
                  <td class="td-cell td-num">{{ t.sell_price }}</td>
                  <td class="td-cell td-num font-medium" :class="t.return_pct >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'">{{ t.return_pct }}%</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-else-if="backtestResult.success && backtestResult.total_trades === 0" class="py-10 text-center text-gray-500 dark:text-gray-400">
            该区间无有效交易，请调整日期或条件后重试。
          </div>
        </div>
      </section>
    </template>

    <p class="mt-8 text-center text-xs text-gray-500 dark:text-gray-400">
      选股结果与回测仅供研究参考，不构成投资建议。历史表现不代表未来，实盘可能与回测存在差异。
    </p>
    <!-- 问 AI（带入当前筛选条件） -->
    <AiChat
      v-model:open="aiChatOpen"
      :initial-question="aiContextQuestion"
    />
  </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import AiChat from '../components/AiChat.vue'

const MATURE_CYCLE = 'mature'   // 与接口 current_cycle 一致
const RISING_CYCLE = 'rising'   // 上升期
import axios from 'axios'
import * as echarts from 'echarts'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

const loading = ref(false)
const error = ref('')
const hasQueried = ref(false)
const queryHint = ref('')
const industryOptions = ref([])
const resultList = ref([])
const filter = ref({
  style: 'conservative',
  industries: [],
  cycle_filter: 'mature_only',  // 稳健型默认仅成熟期
  use_cycle_thresholds: false,
  new_high: 'none',
  order_by: 'roe',
  order_desc: true,
  // 高级覆盖（空则用风格默认）
  min_roe: null,
  min_gross_margin: null,
  max_debt_ratio: null,
  min_revenue_growth: null,
  // 进一步筛选
  net_cash_ratio_positive: false,
  debt_ratio_lt_50: false,
  only_industry_leader: false,
  sector_leader_role_filter: '',
})

// 与后端 STOCK_SELECTOR_STYLE_CONFIG 对应的条件说明（仅展示用）
const STYLE_CONDITIONS = {
  conservative: [
    '稳健型（核心 7 条）：净资产收益率≥6%、负债率≤60%',
    '净利>0、经营现金流>0；净现比≥0.35、净利率≥3%',
    '市盈率≤80、成交额≥0.5亿',
  ],
  aggressive: [
    '激进型（核心 7 条）：净资产收益率≥0%、负债率≤80%',
    '净现比不强制；净利率≥0%；成交额≥0.5亿',
  ],
}
const styleConditionLines = computed(() => STYLE_CONDITIONS[filter.value.style] || [])

const aiChatOpen = ref(false)
const aiContextQuestion = computed(() => {
  const f = filter.value
  const parts = [`投资风格：${f.style === 'conservative' ? '稳健型' : '激进型'}`]
  if (f.cycle_filter !== 'all') {
    const map = { exclude_declining: '排除下滑期', rising_only: '仅上升期', mature_only: '仅成熟期' }
    parts.push(`周期：${map[f.cycle_filter] || f.cycle_filter}`)
  }
  if (f.new_high && f.new_high !== 'none') parts.push(`${f.new_high}日新高`)
  if (f.use_cycle_thresholds) parts.push('按周期调阈值')
  if (f.net_cash_ratio_positive) parts.push('净现比>0')
  if (f.debt_ratio_lt_50) parts.push('负债率<50%')
  if (f.only_industry_leader) parts.push('仅行业/板块龙头')
  if (f.sector_leader_role_filter) parts.push(`角色龙头=${f.sector_leader_role_filter}`)
  if (Array.isArray(f.industries) && f.industries.length) parts.push(`行业：${f.industries.slice(0, 5).join('、')}${f.industries.length > 5 ? '等' : ''}`)
  const count = resultList.value?.length ?? 0
  return `我当前选股条件是：${parts.join('、')}。共筛选出 ${count} 只股票。请帮我分析这些股票适合买入吗？有哪些风险需要注意？`
})

function openAiChat() {
  aiChatOpen.value = true
}
const pagination = ref({
  total: 0,
  page: 1,
  page_size: 20,
})

const activeTab = ref('filter')

// 回测
const backtestParams = ref({
  start_date: (() => {
    const d = new Date()
    d.setFullYear(d.getFullYear() - 1)
    return d.toISOString().slice(0, 10)
  })(),
  end_date: new Date().toISOString().slice(0, 10),
  style: 'conservative',
  industries: '',
  cycle_filter: 'all',
  use_cycle_thresholds: false,
  new_high: 'none',
  order_by: 'roe',
  rebalance_freq: 'monthly',
  hold_days: 20,
  max_stocks_per_rebalance: 10,
})
const backtestLoading = ref(false)
const backtestError = ref('')
const backtestResult = ref(null)
const backtestChartRef = ref(null)
let backtestChartInstance = null

const totalPages = computed(() =>
  Math.max(1, Math.ceil(pagination.value.total / pagination.value.page_size))
)

// 稳健型只显示成熟期行业，激进型只显示上升期行业
const industryOptionsForSelect = computed(() => {
  const list = industryOptions.value
  if (filter.value.style === 'conservative') {
    return list.filter(o => o.current_cycle === MATURE_CYCLE)
  }
  if (filter.value.style === 'aggressive') {
    return list.filter(o => o.current_cycle === RISING_CYCLE)
  }
  return list
})

function toggleIndustry(industry) {
  const arr = Array.isArray(filter.value.industries) ? [...filter.value.industries] : []
  const idx = arr.indexOf(industry)
  if (idx >= 0) arr.splice(idx, 1)
  else arr.push(industry)
  filter.value.industries = arr
}

function selectAllIndustries() {
  filter.value.industries = industryOptionsForSelect.value.map(o => o.industry)
}

function clearAllIndustries() {
  filter.value.industries = []
}

function formatNum(v) {
  if (v == null) return '--'
  const n = Number(v)
  if (Number.isNaN(n)) return '--'
  if (Number.isInteger(n)) return n
  return n.toFixed(2)
}

function applyConservativeDefaults() {
  if (filter.value.style !== 'conservative') return
  filter.value.cycle_filter = 'mature_only'
  const mature = industryOptions.value
    .filter(o => o.current_cycle === MATURE_CYCLE)
    .map(o => o.industry)
  if (mature.length > 0) {
    filter.value.industries = [...mature]
  }
}

function applyAggressiveDefaults() {
  if (filter.value.style !== 'aggressive') return
  filter.value.cycle_filter = 'rising_only'
  const rising = industryOptions.value
    .filter(o => o.current_cycle === RISING_CYCLE)
    .map(o => o.industry)
  if (rising.length > 0) {
    filter.value.industries = [...rising]
  }
}

async function loadIndustries() {
  try {
    const res = await axios.get(`${API_BASE_URL}/api/stock-selector/industries`, {
      params: { with_cycle: true }
    })
    if (res.data?.success && Array.isArray(res.data.data)) {
      const raw = res.data.data
      industryOptions.value = raw.every(r => typeof r === 'object' && r !== null && 'industry' in r)
        ? raw
        : raw.map(ind => ({ industry: ind, current_cycle: '' }))
      applyConservativeDefaults()
    }
  } catch (e) {
    console.error('加载行业列表失败:', e)
  }
}

async function doQuery(page = 1) {
  loading.value = true
  error.value = ''
  hasQueried.value = true
  try {
    const industriesParam = Array.isArray(filter.value.industries) && filter.value.industries.length
      ? filter.value.industries.join(',')
      : ''
    const params = {
      style: filter.value.style,
      industries: industriesParam || undefined,
      cycle_filter: filter.value.cycle_filter,
      use_cycle_thresholds: filter.value.use_cycle_thresholds,
      new_high: filter.value.new_high,
      order_by: filter.value.order_by,
      order_desc: filter.value.order_desc,
      page,
      page_size: pagination.value.page_size,
    }
    if (filter.value.min_roe != null && filter.value.min_roe !== '') params.min_roe = filter.value.min_roe
    if (filter.value.min_gross_margin != null && filter.value.min_gross_margin !== '') params.min_gross_margin = filter.value.min_gross_margin
    if (filter.value.max_debt_ratio != null && filter.value.max_debt_ratio !== '') params.max_debt_ratio = filter.value.max_debt_ratio
    if (filter.value.min_revenue_growth != null && filter.value.min_revenue_growth !== '') params.min_revenue_growth = filter.value.min_revenue_growth
    if (filter.value.net_cash_ratio_positive) params.net_cash_ratio_positive = true
    if (filter.value.debt_ratio_lt_50) params.debt_ratio_lt_50 = true
    if (filter.value.only_industry_leader) params.only_industry_leader = true
    if (filter.value.sector_leader_role_filter) params.sector_leader_role_filter = filter.value.sector_leader_role_filter
    const res = await axios.get(`${API_BASE_URL}/api/stock-selector/query`, { params })
    if (res.data?.success) {
      resultList.value = res.data.data || []
      pagination.value.total = res.data.total ?? 0
      pagination.value.page = res.data.page ?? 1
      pagination.value.page_size = res.data.page_size ?? 20
      queryHint.value = res.data.hint || ''
    } else {
      error.value = res.data?.message || '请求失败'
    }
  } catch (e) {
    error.value = e.response?.data?.detail || e.message || '网络错误'
    resultList.value = []
  } finally {
    loading.value = false
  }
}

function goPage(p) {
  if (p < 1 || p > totalPages.value) return
  doQuery(p)
}

function syncBacktestFromFilter() {
  const f = filter.value
  backtestParams.value.style = f.style
  backtestParams.value.industries = Array.isArray(f.industries) ? f.industries.join(',') : (f.industries ?? '')
  backtestParams.value.cycle_filter = f.cycle_filter
  backtestParams.value.use_cycle_thresholds = f.use_cycle_thresholds
  backtestParams.value.new_high = f.new_high
  backtestParams.value.order_by = f.order_by
}

async function runBacktest() {
  backtestLoading.value = true
  backtestError.value = ''
  backtestResult.value = null
  try {
    const industriesParam = backtestParams.value.industries
      ? String(backtestParams.value.industries).trim()
      : ''
    const res = await axios.post(
      `${API_BASE_URL}/api/stock-selector/backtest`,
      null,
      {
        params: {
          start_date: backtestParams.value.start_date,
          end_date: backtestParams.value.end_date,
          style: backtestParams.value.style,
          industries: industriesParam || undefined,
          cycle_filter: backtestParams.value.cycle_filter,
          use_cycle_thresholds: backtestParams.value.use_cycle_thresholds,
          new_high: backtestParams.value.new_high,
          order_by: backtestParams.value.order_by,
          rebalance_freq: backtestParams.value.rebalance_freq,
          hold_days: backtestParams.value.hold_days,
          max_stocks_per_rebalance: backtestParams.value.max_stocks_per_rebalance,
        },
      }
    )
    if (res.data?.success) {
      backtestResult.value = {
        success: true,
        win_rate: res.data.win_rate,
        avg_return: res.data.avg_return,
        total_trades: res.data.total_trades ?? 0,
        trades: res.data.trades ?? [],
        rebalance_dates: res.data.rebalance_dates ?? [],
        benchmark_return: res.data.benchmark_return,
        excess_return: res.data.excess_return,
        curve_dates: res.data.curve_dates ?? [],
        curve_strategy_pct: res.data.curve_strategy_pct ?? [],
        curve_benchmark_pct: res.data.curve_benchmark_pct ?? [],
      }
    } else {
      backtestError.value = res.data?.message || '回测失败'
    }
  } catch (e) {
    backtestError.value = e.response?.data?.detail || e.message || '网络错误'
  } finally {
    backtestLoading.value = false
  }
}

function renderBacktestChart() {
  const r = backtestResult.value
  if (!r?.curve_dates?.length || !r?.curve_strategy_pct?.length || !backtestChartRef.value) return
  nextTick(() => {
    if (!backtestChartRef.value) return
    if (backtestChartInstance) {
      backtestChartInstance.dispose()
      backtestChartInstance = null
    }
    backtestChartInstance = echarts.init(backtestChartRef.value)
    const hasBenchmark = r.curve_benchmark_pct?.length === r.curve_dates.length
    const series = [
      { name: '策略累计', type: 'line', data: r.curve_strategy_pct, smooth: true, symbol: 'circle', symbolSize: 4 },
    ]
    if (hasBenchmark) {
      series.push({ name: '沪深300', type: 'line', data: r.curve_benchmark_pct, smooth: true, symbol: 'circle', symbolSize: 4 })
    }
    backtestChartInstance.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: series.map(s => s.name), bottom: 0 },
      grid: { left: '3%', right: '4%', bottom: '15%', top: '8%', containLabel: true },
      xAxis: { type: 'category', data: r.curve_dates, axisLabel: { rotate: 30 } },
      yAxis: { type: 'value', axisLabel: { formatter: '{value}%' } },
      series,
    })
  })
}

watch(backtestResult, (val) => {
  if (val?.curve_dates?.length) renderBacktestChart()
}, { deep: true })

watch(() => filter.value.style, (style) => {
  if (style === 'conservative') applyConservativeDefaults()
  if (style === 'aggressive') applyAggressiveDefaults()
})

const _onBacktestResize = () => backtestChartInstance?.resize()
onMounted(() => {
  loadIndustries()
  window.addEventListener('resize', _onBacktestResize)
})
onUnmounted(() => {
  window.removeEventListener('resize', _onBacktestResize)
})
</script>

<style scoped>
.input-select {
  @apply border rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-700 border-gray-300 dark:border-gray-600 text-gray-900 dark:text-gray-200 focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500 outline-none transition-colors;
}
.input-number {
  @apply border rounded-lg px-2 py-1.5 text-sm bg-white dark:bg-gray-700 border-gray-300 dark:border-gray-600 text-gray-900 dark:text-gray-200 focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500 outline-none;
}
.btn-primary {
  @apply bg-primary-500 hover:bg-primary-600 text-white shadow-sm transition-colors;
}
.stock-table :deep(.th-cell) {
  @apply px-4 py-3 text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider whitespace-nowrap;
}
.stock-table :deep(.th-left) { text-align: left; }
.stock-table :deep(.th-num) { text-align: right; }
.stock-table :deep(.td-cell) {
  @apply px-4 py-2.5 text-sm text-gray-700 dark:text-gray-300 whitespace-nowrap;
}
.stock-table :deep(.td-num) {
  @apply text-right tabular-nums font-mono text-gray-800 dark:text-gray-200;
}
.stock-table :deep(.tr-row) {
  @apply transition-colors hover:bg-gray-50 dark:hover:bg-gray-700/40;
}
.backtest-card {
  @apply bg-gray-50/80 dark:bg-gray-700/30;
}
</style>
