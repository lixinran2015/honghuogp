<template>
  <div class="container mx-auto px-4 py-6">
    <!-- 标题 -->
    <div class="mb-6">
      <h1 class="text-2xl font-bold text-gray-800">龙头买点回测</h1>
      <p class="text-sm text-gray-500 mt-1">
        基于「主线强度前 10 + 龙头买点」的历史信号，评估右侧确认 / 缩量回踩在不同时间窗口内的大致表现。
      </p>
    </div>

    <!-- 筛选区 -->
    <div class="bg-white rounded-xl shadow border border-gray-100 mb-6 p-4 lg:p-6 space-y-4">
      <div class="flex flex-wrap gap-4 items-end justify-between">
        <div class="flex flex-wrap gap-4 items-end">
        <div class="w-40">
          <label class="block text-xs font-medium text-gray-500 mb-1">开始日期</label>
          <input
            v-model="startDate"
            type="date"
            class="w-full px-3 py-1.5 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
          />
        </div>
        <div class="w-40">
          <label class="block text-xs font-medium text-gray-500 mb-1">结束日期</label>
          <input
            v-model="endDate"
            type="date"
            class="w-full px-3 py-1.5 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
          />
        </div>
        <div class="w-32">
          <label class="block text-xs font-medium text-gray-500 mb-1">主线强度下限</label>
          <input
            v-model.number="minStrength"
            type="number"
            min="0"
            max="20"
            step="0.5"
            class="w-full px-3 py-1.5 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
          />
        </div>
        <div class="w-40">
          <label class="block text-xs font-medium text-gray-500 mb-1">信号类型</label>
          <select
            v-model="signalType"
            class="w-full px-2 py-1.5 border border-gray-300 rounded-md text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 bg-white"
          >
            <option value="both">右侧 + 缩量</option>
            <option value="right">仅右侧确认</option>
            <option value="left">仅缩量回踩</option>
          </select>
        </div>
        <div class="w-40">
          <label class="block text-xs font-medium text-gray-500 mb-1">市场环境</label>
          <select
            v-model="marketRegime"
            class="w-full px-2 py-1.5 border border-gray-300 rounded-md text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 bg-white"
          >
            <option value="any">全部环境</option>
            <option value="bull">偏多（牛市 / 上升）</option>
            <option value="sideways">震荡市</option>
            <option value="bear">偏空（熊市 / 下跌）</option>
          </select>
        </div>
        <div class="w-40">
          <label class="block text-xs font-medium text-gray-500 mb-1">板块类型</label>
          <select
            v-model="sectorType"
            class="w-full px-2 py-1.5 border border-gray-300 rounded-md text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 bg-white"
          >
            <option value="any">全部板块</option>
            <option value="industry">行业</option>
            <option value="concept">题材</option>
            <option value="index">指数 / 风格</option>
          </select>
        </div>
        <div class="flex items-center gap-2">
          <button
            type="button"
            class="px-3 py-1.5 rounded-md text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60"
            :disabled="loading"
            @click="fetchData"
          >
            {{ loading ? '加载中...' : '刷新' }}
          </button>
          <button
            type="button"
            class="px-3 py-1.5 rounded-md text-xs font-medium text-gray-700 bg-gray-50 border border-gray-200 hover:bg-gray-100 disabled:opacity-60"
            :disabled="loading"
            @click="setRecentMonths(6)"
          >
            最近 6 个月
          </button>
          <button
            type="button"
            class="px-3 py-1.5 rounded-md text-xs font-medium text-gray-700 bg-gray-50 border border-gray-200 hover:bg-gray-100 disabled:opacity-60"
            :disabled="loading || totalSignals === 0"
            @click="exportCsv"
          >
            导出 CSV
          </button>
          <button
            type="button"
            class="px-3 py-1.5 rounded-md text-xs font-medium text-gray-700 bg-gray-50 border border-gray-200 hover:bg-gray-100 disabled:opacity-60"
            :disabled="headlineTexts.length === 0"
            @click="copySummary"
          >
            复制结论文案
          </button>
        </div>
        </div>
        <div class="flex flex-col items-end gap-1 text-[11px] text-gray-500">
          <div class="flex items-center gap-2">
            <span class="text-gray-400">账号角色：</span>
            <select
              v-model="currentUserRole"
              @change="(e) => setCurrentUserRole(e.target.value)"
              class="px-2 py-1 border border-gray-300 rounded-md text-[11px] bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500"
            >
              <option v-for="r in availableRoles" :key="r.value" :value="r.value">
                {{ r.label }}
              </option>
            </select>
          </div>
          <div class="text-[10px] text-gray-400">
            不同角色可回测区间与导出权限不同，对接登录后会自动识别。
          </div>
        </div>
      </div>
      <p class="text-[11px] text-gray-400">
        当前回测：主线强度前 10 板块内的空间龙头/刚启动龙头买点；收益为事件级净收益（含双边约 0.2% 成本），不含组合层仓位管理。
      </p>
      <p v-if="meta" class="text-[11px] text-gray-400 mt-0.5">
        回测数据区间：{{ meta.last_run_start_date }} ~ {{ meta.last_run_end_date }} · 规则版本：{{ meta.rule_version }}
        <span v-if="meta.updated_at">
          · 最近重算：{{ meta.updated_at.slice(0, 10) }}
        </span>
      </p>
    </div>

    <!-- 策略 Summary（自动生成的结论话术） -->
    <div
      v-if="summary && totalSignals > 0 && headlineTexts.length > 0"
      class="mb-4 text-[11px] text-gray-700 space-y-1"
    >
      <div v-for="line in headlineTexts" :key="line">
        {{ line }}
      </div>
    </div>

    <!-- 错误提示 -->
    <div
      v-if="error"
      class="mb-4 bg-red-50 border border-red-200 text-red-700 text-sm px-4 py-3 rounded-lg"
    >
      {{ error }}
    </div>

    <!-- Summary -->
    <div v-if="summary && totalSignals > 0" class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
      <div class="bg-white rounded-xl shadow border border-gray-100 p-4">
        <div class="text-xs text-gray-500 mb-1">样本数</div>
        <div class="text-2xl font-semibold text-gray-900">{{ totalSignals }}</div>
        <div class="text-[11px] text-gray-400 mt-1">
          包含右侧确认与缩量回踩（可在上方勾选）。
        </div>
      </div>
      <div class="bg-white rounded-xl shadow border border-gray-100 p-4">
        <div class="text-xs text-gray-500 mb-1">5 日净收益（均值 / 中位数）</div>
        <div class="text-lg font-semibold text-gray-900">
          {{ formatPct(summary.ret_5d?.avg) }} / {{ formatPct(summary.ret_5d?.p50) }}
        </div>
        <div class="text-[11px] text-gray-400 mt-1">
          胜率：{{ formatPct(summary.ret_5d?.win_rate) }}，尾部 5% 平均：{{ formatPct(summary.ret_5d?.tail_5_avg) }}。
        </div>
      </div>
      <div class="bg-white rounded-xl shadow border border-gray-100 p-4">
        <div class="text-xs text-gray-500 mb-1">10 日净收益（均值 / 中位数）</div>
        <div class="text-lg font-semibold text-gray-900">
          {{ formatPct(summary.ret_10d?.avg) }} / {{ formatPct(summary.ret_10d?.p50) }}
        </div>
        <div class="text-[11px] text-gray-400 mt-1">
          胜率：{{ formatPct(summary.ret_10d?.win_rate) }}，尾部 5% 平均：{{ formatPct(summary.ret_10d?.tail_5_avg) }}。
        </div>
      </div>
    </div>

    <!-- 右侧确认 vs 缩量回踩 对比 -->
    <div
      v-if="summary && totalSignals > 0 && (signalTypeSummary.right || signalTypeSummary.left)"
      class="bg-white rounded-xl shadow border border-gray-100 p-4 mb-6"
    >
      <div class="flex items-center justify-between mb-3">
        <div>
          <div class="text-sm font-semibold text-gray-800">右侧确认 vs 缩量回踩（5 / 10 日表现）</div>
          <div class="text-[11px] text-gray-400 mt-0.5">
            对比两类买点在当前窗口内的样本数、平均收益与胜率，帮助判断更适合重仓哪一类信号。
          </div>
        </div>
      </div>
      <div class="overflow-x-auto">
        <table class="min-w-full text-[11px]">
          <thead class="bg-gray-50 text-gray-500 border-b border-gray-100">
            <tr>
              <th class="px-2 py-2 text-left">信号类型</th>
              <th class="px-2 py-2 text-right">样本数</th>
              <th class="px-2 py-2 text-right">5日均值 / 中位</th>
              <th class="px-2 py-2 text-right">5日胜率</th>
              <th class="px-2 py-2 text-right">10日均值 / 中位</th>
              <th class="px-2 py-2 text-right">10日胜率</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="signalTypeSummary.right" class="border-b border-gray-50">
              <td class="px-2 py-1 text-gray-800">右侧确认</td>
              <td class="px-2 py-1 text-right text-gray-700">{{ signalTypeSummary.right.count }}</td>
              <td class="px-2 py-1 text-right" :class="valueColor(signalTypeSummary.right.ret_5d?.avg)">
                {{ formatPct(signalTypeSummary.right.ret_5d?.avg) }} / {{ formatPct(signalTypeSummary.right.ret_5d?.p50) }}
              </td>
              <td class="px-2 py-1 text-right text-gray-700">
                {{ formatPct(signalTypeSummary.right.ret_5d?.win_rate) }}
              </td>
              <td class="px-2 py-1 text-right" :class="valueColor(signalTypeSummary.right.ret_10d?.avg)">
                {{ formatPct(signalTypeSummary.right.ret_10d?.avg) }} / {{ formatPct(signalTypeSummary.right.ret_10d?.p50) }}
              </td>
              <td class="px-2 py-1 text-right text-gray-700">
                {{ formatPct(signalTypeSummary.right.ret_10d?.win_rate) }}
              </td>
            </tr>
            <tr v-if="signalTypeSummary.left" class="border-b border-gray-50">
              <td class="px-2 py-1 text-gray-800">缩量回踩</td>
              <td class="px-2 py-1 text-right text-gray-700">{{ signalTypeSummary.left.count }}</td>
              <td class="px-2 py-1 text-right" :class="valueColor(signalTypeSummary.left.ret_5d?.avg)">
                {{ formatPct(signalTypeSummary.left.ret_5d?.avg) }} / {{ formatPct(signalTypeSummary.left.ret_5d?.p50) }}
              </td>
              <td class="px-2 py-1 text-right text-gray-700">
                {{ formatPct(signalTypeSummary.left.ret_5d?.win_rate) }}
              </td>
              <td class="px-2 py-1 text-right" :class="valueColor(signalTypeSummary.left.ret_10d?.avg)">
                {{ formatPct(signalTypeSummary.left.ret_10d?.avg) }} / {{ formatPct(signalTypeSummary.left.ret_10d?.p50) }}
              </td>
              <td class="px-2 py-1 text-right text-gray-700">
                {{ formatPct(signalTypeSummary.left.ret_10d?.win_rate) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 简易收益分布图（5日净收益） -->
    <div
      v-if="summary && totalSignals > 0 && hist5d.bins.length > 0"
      class="bg-white rounded-xl shadow border border-gray-100 p-4 mb-6"
    >
      <div class="flex items-center justify-between mb-3">
        <div>
          <div class="text-sm font-semibold text-gray-800">5 日净收益分布</div>
          <div class="text-[11px] text-gray-400 mt-0.5">
            使用当前筛选条件下所有信号的 5 日收益，按区间聚合成简单柱状图，越靠右代表收益越高。
          </div>
        </div>
      </div>
      <div class="space-y-1 text-[11px] text-gray-600">
        <div
          v-for="bin in hist5d.bins"
          :key="bin.label"
          class="flex items-center gap-2"
        >
          <div class="w-20 text-right text-gray-500">
            {{ bin.label }}
          </div>
          <div class="flex-1 h-3 bg-gray-100 rounded-full overflow-hidden">
            <div
              class="h-full rounded-full bg-gradient-to-r from-indigo-400 to-indigo-600"
              :style="{ width: bin.width + '%' }"
            />
          </div>
          <div class="w-10 text-right text-gray-500">
            {{ bin.count }}
          </div>
        </div>
      </div>
    </div>

    <!-- 按市场环境分层表现 -->
    <div
      v-if="summary && totalSignals > 0 && marketEnvRows.length > 0"
      class="bg-white rounded-xl shadow border border-gray-100 p-4 mb-6"
    >
      <div class="flex items-center justify-between mb-3">
        <div>
          <div class="text-sm font-semibold text-gray-800">按市场环境分层表现</div>
          <div class="text-[11px] text-gray-400 mt-0.5">
            使用简单的指数趋势判断，将信号按牛市 / 震荡市 / 熊市分组，对比不同环境下的平均收益与胜率。
          </div>
        </div>
      </div>
      <div class="overflow-x-auto">
        <table class="min-w-full text-[11px]">
          <thead class="bg-gray-50 text-gray-500 border-b border-gray-100">
            <tr>
              <th class="px-2 py-2 text-left">市场环境</th>
              <th class="px-2 py-2 text-right">样本数</th>
              <th class="px-2 py-2 text-right">5日均值 / 中位</th>
              <th class="px-2 py-2 text-right">5日胜率</th>
              <th class="px-2 py-2 text-right">10日均值 / 中位</th>
              <th class="px-2 py-2 text-right">10日胜率</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in marketEnvRows"
              :key="row.key"
              class="border-b border-gray-50"
            >
              <td class="px-2 py-1 text-gray-800">
                {{ row.label }}
              </td>
              <td class="px-2 py-1 text-right text-gray-700">
                {{ row.count }}
              </td>
              <td class="px-2 py-1 text-right" :class="valueColor(row.ret5?.avg)">
                {{ formatPct(row.ret5?.avg) }} / {{ formatPct(row.ret5?.p50) }}
              </td>
              <td class="px-2 py-1 text-right text-gray-700">
                {{ formatPct(row.ret5?.win_rate) }}
              </td>
              <td class="px-2 py-1 text-right" :class="valueColor(row.ret10?.avg)">
                {{ formatPct(row.ret10?.avg) }} / {{ formatPct(row.ret10?.p50) }}
              </td>
              <td class="px-2 py-1 text-right text-gray-700">
                {{ formatPct(row.ret10?.win_rate) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 按主线强度分桶的平均收益 -->
    <div
      v-if="summary && totalSignals > 0 && strengthBuckets.length > 0"
      class="bg-white rounded-xl shadow border border-gray-100 p-4 mb-6"
    >
      <div class="flex items-center justify-between mb-3">
        <div>
          <div class="text-sm font-semibold text-gray-800">按主线强度分桶的平均收益（5 日）</div>
          <div class="text-[11px] text-gray-400 mt-0.5">
            将信号按所属主线的强度区间（4-5 / 5-6 / 6-7 / 7+）分组，对比不同强度主线中的平均 5 日收益和样本数。
          </div>
        </div>
      </div>
      <div class="space-y-1 text-[11px] text-gray-600">
        <div
          v-for="b in strengthBuckets"
          :key="b.label"
          class="flex items-center gap-2"
        >
          <div class="w-16 text-right text-gray-500">
            {{ b.label }}
          </div>
          <div class="flex-1 h-3 bg-gray-100 rounded-full overflow-hidden">
            <div
              class="h-full rounded-full bg-gradient-to-r from-emerald-400 to-emerald-600"
              :style="{ width: b.width + '%' }"
            />
          </div>
          <div class="w-28 text-right text-gray-700">
            平均 {{ formatPct(b.avg) }}
          </div>
          <div class="w-10 text-right text-gray-500">
            {{ b.count }}
          </div>
        </div>
      </div>
    </div>

    <!-- 无数据状态 -->
    <div
      v-if="!loading && !error && totalSignals === 0"
      class="bg-blue-50 border border-blue-100 text-blue-700 text-sm px-6 py-6 rounded-lg text-center"
    >
      当前条件下没有买点信号，请调整时间区间或主线强度下限。
    </div>

    <!-- 信号明细表 -->
    <div v-if="signals.length > 0" class="bg-white rounded-xl shadow border border-gray-100 p-4">
      <div class="flex items-center justify-between mb-3 text-xs text-gray-500">
        <div>
          共 {{ totalSignals }} 条信号，当前展示 {{ signals.length }} 条（第 {{ page }} 页，每页 {{ pageSize }} 条）
        </div>
        <div class="flex items-center gap-2">
          <button
            type="button"
            class="px-2 py-1 rounded border border-gray-200 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
            :disabled="page <= 1 || loading"
            @click="changePage(page - 1)"
          >
            上一页
          </button>
          <span>第 {{ page }} 页</span>
          <button
            type="button"
            class="px-2 py-1 rounded border border-gray-200 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
            :disabled="page * pageSize >= totalSignals || loading"
            @click="changePage(page + 1)"
          >
            下一页
          </button>
        </div>
      </div>
      <div class="overflow-x-auto">
        <table class="min-w-full text-xs">
          <thead class="bg-gray-50 text-gray-500 border-b border-gray-100">
            <tr>
              <th class="px-2 py-2 text-left">日期</th>
              <th class="px-2 py-2 text-left">名称 / 代码</th>
              <th class="px-2 py-2 text-left">主线</th>
              <th class="px-2 py-2 text-left">信号类型</th>
              <th class="px-2 py-2 text-right">
                <button
                  type="button"
                  class="inline-flex items-center gap-0.5 hover:text-gray-700"
                  @click="setSort('ret_5d')"
                >
                  <span>5日收益</span>
                  <span v-if="sortKey === 'ret_5d'">{{ sortLabel }}</span>
                </button>
              </th>
              <th class="px-2 py-2 text-right">
                <button
                  type="button"
                  class="inline-flex items-center gap-0.5 hover:text-gray-700"
                  @click="setSort('ret_10d')"
                >
                  <span>10日收益</span>
                  <span v-if="sortKey === 'ret_10d'">{{ sortLabel }}</span>
                </button>
              </th>
              <th class="px-2 py-2 text-right">
                <button
                  type="button"
                  class="inline-flex items-center gap-0.5 hover:text-gray-700"
                  @click="setSort('max_drawdown_5d')"
                >
                  <span>5日最大回撤</span>
                  <span v-if="sortKey === 'max_drawdown_5d'">{{ sortLabel }}</span>
                </button>
              </th>
              <th class="px-2 py-2 text-right">
                <button
                  type="button"
                  class="inline-flex items-center gap-0.5 hover:text-gray-700"
                  @click="setSort('max_drawdown_10d')"
                >
                  <span>10日最大回撤</span>
                  <span v-if="sortKey === 'max_drawdown_10d'">{{ sortLabel }}</span>
                </button>
              </th>
              <th class="px-2 py-2 text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="s in sortedSignals"
              :key="s.ts_code + s.trade_date + s.signal_type"
              class="border-b border-gray-50 hover:bg-gray-50 cursor-pointer"
              @click="openDrilldown(s.ts_code)"
            >
              <td class="px-2 py-1 text-gray-600">{{ s.trade_date }}</td>
              <td class="px-2 py-1">
                <div v-if="s.name" class="flex flex-col">
                  <span class="text-gray-900 text-xs font-medium">
                    {{ s.name }}
                  </span>
                  <span class="font-mono text-[11px] text-gray-500">
                    {{ s.ts_code }}
                  </span>
                </div>
                <div v-else>
                  <span class="font-mono text-xs text-gray-800">
                    {{ s.ts_code }}
                  </span>
                </div>
              </td>
              <td class="px-2 py-1">
                <span class="text-gray-800">{{ s.sector_name }}</span>
                <span class="ml-1 text-[10px] text-gray-400">({{ s.sector_type }})</span>
              </td>
              <td class="px-2 py-1">
                <span
                  class="inline-flex px-1.5 py-0.5 rounded-full text-[10px] font-medium"
                  :class="s.signal_type === 'right' ? 'bg-indigo-50 text-indigo-700' : 'bg-sky-50 text-sky-700'"
                >
                  {{ s.signal_type === 'right' ? '右侧确认' : '缩量回踩' }}
                </span>
              </td>
              <td class="px-2 py-1 text-right" :class="valueColor(s.ret_5d)">
                {{ formatPct(s.ret_5d) }}
              </td>
              <td class="px-2 py-1 text-right" :class="valueColor(s.ret_10d)">
                {{ formatPct(s.ret_10d) }}
              </td>
              <td class="px-2 py-1 text-right text-gray-500">
                {{ formatPct(s.max_drawdown_5d) }}
              </td>
              <td class="px-2 py-1 text-right text-gray-500">
                {{ formatPct(s.max_drawdown_10d) }}
              </td>
              <td class="px-2 py-1 text-right">
                <div class="flex items-center justify-end gap-1.5">
                  <button
                    type="button"
                    class="px-1.5 py-0.5 rounded border text-[10px]"
                    :class="isTracked(s.ts_code) ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : 'border-gray-200 bg-white text-gray-600'"
                    @click.stop="toggleTrackFromBacktest(s)"
                  >
                    {{ isTracked(s.ts_code) ? '已跟踪' : '跟踪' }}
                  </button>
                  <button
                    type="button"
                    class="px-1.5 py-0.5 rounded border border-indigo-200 bg-indigo-50 text-[10px] text-indigo-700"
                    @click.stop="openDiagnose(s.ts_code)"
                  >
                    诊股
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
    <!-- 单票 Drill-down 简易面板（当前页） -->
    <div
      v-if="drilldownStock"
      class="mt-4 bg-white rounded-xl shadow border border-gray-100 p-4"
    >
      <div class="flex items-center justify-between mb-2">
        <div>
          <div class="text-sm font-semibold text-gray-800">
            {{ drilldownStock }} 的当前页买点信号
          </div>
          <div class="text-[11px] text-gray-400 mt-0.5">
            展示当前页内该股票的所有买点信号（更详细的分时与 K 线可在诊股页查看）。
          </div>
        </div>
        <button
          type="button"
          class="text-[11px] text-gray-500 hover:text-gray-700 underline"
          @click="drilldownStock = ''"
        >
          关闭
        </button>
      </div>
      <div class="overflow-x-auto">
        <table class="min-w-full text-[11px]">
          <thead class="bg-gray-50 text-gray-500 border-b border-gray-100">
            <tr>
              <th class="px-2 py-2 text-left">日期</th>
              <th class="px-2 py-2 text-left">主线</th>
              <th class="px-2 py-2 text-left">信号</th>
              <th class="px-2 py-2 text-right">5日收益</th>
              <th class="px-2 py-2 text-right">10日收益</th>
              <th class="px-2 py-2 text-right">5日回撤</th>
              <th class="px-2 py-2 text-right">10日回撤</th>
              <th class="px-2 py-2 text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="s in drilldownSignals"
              :key="s.ts_code + s.trade_date + s.signal_type"
              class="border-b border-gray-50"
            >
              <td class="px-2 py-1 text-gray-600">{{ s.trade_date }}</td>
              <td class="px-2 py-1">
                <span class="text-gray-800">{{ s.sector_name }}</span>
                <span class="ml-1 text-[10px] text-gray-400">({{ s.sector_type }})</span>
              </td>
              <td class="px-2 py-1">
                <span
                  class="inline-flex px-1.5 py-0.5 rounded-full text-[10px] font-medium"
                  :class="s.signal_type === 'right' ? 'bg-indigo-50 text-indigo-700' : 'bg-sky-50 text-sky-700'"
                >
                  {{ s.signal_type === 'right' ? '右侧确认' : '缩量回踩' }}
                </span>
              </td>
              <td class="px-2 py-1 text-right" :class="valueColor(s.ret_5d)">
                {{ formatPct(s.ret_5d) }}
              </td>
              <td class="px-2 py-1 text-right" :class="valueColor(s.ret_10d)">
                {{ formatPct(s.ret_10d) }}
              </td>
              <td class="px-2 py-1 text-right text-gray-500">
                {{ formatPct(s.max_drawdown_5d) }}
              </td>
              <td class="px-2 py-1 text-right text-gray-500">
                {{ formatPct(s.max_drawdown_10d) }}
              </td>
              <td class="px-2 py-1 text-right">
                <div class="flex items-center justify-end gap-1.5">
                  <button
                    type="button"
                    class="px-1.5 py-0.5 rounded border text-[10px]"
                    :class="isTracked(s.ts_code) ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : 'border-gray-200 bg-white text-gray-600'"
                    @click.stop="toggleTrackFromBacktest(s)"
                  >
                    {{ isTracked(s.ts_code) ? '已跟踪' : '跟踪' }}
                  </button>
                  <button
                    type="button"
                    class="px-1.5 py-0.5 rounded border border-indigo-200 bg-indigo-50 text-[10px] text-indigo-700"
                    @click.stop="openDiagnose(s.ts_code)"
                  >
                    诊股
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 使用指南 + 风险提示 -->
    <div class="mt-6 space-y-1 text-[11px] text-gray-500">
      <div>
        日常建议工作流：先在「主线雷达」锁定当下主线 → 在「龙头跟踪」中挑出候选票 → 在本页用历史回测验证这类买点在类似环境下的大致表现 → 把看中的票加入跟踪池或进入诊股页做进一步分析。
      </div>
      <div class="text-gray-400">
        本回测基于历史数据和统一的执行 / 成本假设，仅用于评估策略大致区间表现，不构成任何收益承诺或投资建议，请结合自身风险承受能力谨慎决策。
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import { useCurrentUser } from '../../composables/useCurrentUser'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

const router = useRouter()
const { currentUserRole, setCurrentUserRole, availableRoles } = useCurrentUser()

const today = new Date()
const sixMonthsAgo = new Date()
sixMonthsAgo.setMonth(sixMonthsAgo.getMonth() - 6)

const formatDate = (d) => d.toISOString().slice(0, 10)

const startDate = ref(formatDate(sixMonthsAgo))
const endDate = ref(formatDate(today))
const minStrength = ref(4.0)
const signalType = ref('both')
const marketRegime = ref('any')
const sectorType = ref('any')

const loading = ref(false)
const error = ref(null)

const signals = ref([])
const summary = ref(null)
const totalSignals = ref(0)
const page = ref(1)
const pageSize = ref(200)
const meta = ref(null)

// 简单记录哪些股票已在当前会话中加入过跟踪池（不与全局 watchlist 强绑定，只做状态提示）
const trackedMap = ref({})

// 明细表排序状态
const sortKey = ref('')
const sortOrder = ref('desc') // 'asc' | 'desc'

const sortedSignals = computed(() => {
  const key = sortKey.value
  if (!key) return signals.value || []
  const order = sortOrder.value === 'asc' ? 1 : -1
  const list = [...(signals.value || [])]
  list.sort((a, b) => {
    const va = a[key]
    const vb = b[key]
    const na = va == null ? null : Number(va)
    const nb = vb == null ? null : Number(vb)
    if (na === null && nb === null) return 0
    if (na === null) return 1 // 空值排在后面
    if (nb === null) return -1
    if (Number.isNaN(na) && Number.isNaN(nb)) return 0
    if (Number.isNaN(na)) return 1
    if (Number.isNaN(nb)) return -1
    if (na === nb) return 0
    return na > nb ? order : -order
  })
  return list
})

const sortLabel = computed(() => (sortOrder.value === 'asc' ? '↑' : '↓'))

const setSort = (key) => {
  if (sortKey.value === key) {
    // 同一列点击时在 asc/desc 间切换
    sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortOrder.value = key.startsWith('max_drawdown') ? 'asc' : 'desc'
  }
}

// 不同角色允许查看的最大回测天数（只在前端做基础限制）
const maxDaysByRole = computed(() => {
  if (currentUserRole.value === 'pro') return 365 * 5 // 专业版最多 5 年
  if (currentUserRole.value === 'paid') return 365 // 付费版 1 年
  return 180 // 游客 / 试用版 180 天
})

const canExportCsv = computed(() => currentUserRole.value === 'paid' || currentUserRole.value === 'pro')

const setRecentMonths = (months) => {
  const end = new Date()
  const start = new Date()
  start.setMonth(start.getMonth() - months)
  startDate.value = formatDate(start)
  endDate.value = formatDate(end)
  page.value = 1
  fetchData()
}

const fetchData = async () => {
  loading.value = true
  error.value = null
  try {
    // 基础权限控制：限制不同角色的最大回测区间长度
    const start = new Date(startDate.value)
    const end = new Date(endDate.value)
    const diffMs = end.getTime() - start.getTime()
    const diffDays = diffMs / (1000 * 60 * 60 * 24)
    const maxDays = maxDaysByRole.value
    if (diffDays > maxDays + 1) {
      error.value = `当前账号最多支持回测最近 ${maxDays} 天的数据，请缩短时间窗口。`
      signals.value = []
      summary.value = null
      totalSignals.value = 0
      loading.value = false
      return
    }

    const params = {
      start_date: startDate.value,
      end_date: endDate.value,
      min_strength: minStrength.value,
      signal_type: signalType.value,
      market_regime: marketRegime.value,
      sector_type: sectorType.value,
      page: page.value,
      page_size: pageSize.value,
    }
    const res = await axios.get(`${API_BASE_URL}/api/startup/leader-buy-backtest/signals`, {
      params,
    })
    const data = res.data || {}
    if (!data.success) {
      error.value = data.message || data.detail || '加载失败'
      signals.value = []
      summary.value = null
      totalSignals.value = 0
      return
    }
    signals.value = data.items || []
    summary.value = data.summary || null
    totalSignals.value = data.total || 0

    // 根据返回的 items，初始化 trackedMap（保留之前的状态）
    const cur = { ...(trackedMap.value || {}) }
    for (const s of signals.value || []) {
      if (!s?.ts_code) continue
      if (cur[s.ts_code] == null) {
        cur[s.ts_code] = false
      }
    }
    trackedMap.value = cur
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error(e)
    error.value = e?.response?.data?.detail || e?.message || '请求失败'
    signals.value = []
    summary.value = null
    totalSignals.value = 0
  } finally {
    loading.value = false
  }
}

const fetchMeta = async () => {
  try {
    const res = await axios.get(`${API_BASE_URL}/api/startup/leader-buy-backtest/meta`)
    const data = res.data || {}
    if (data.success) {
      meta.value = data.meta || null
    }
  } catch (e) {
    // 静默失败，不影响主回测功能
    // eslint-disable-next-line no-console
    console.error('fetchMeta failed', e)
    meta.value = null
  }
}

const exportCsv = () => {
  if (!canExportCsv.value) {
    // eslint-disable-next-line no-alert
    alert('当前账号暂无导出权限，请升级后使用导出功能')
    return
  }
  const params = new URLSearchParams({
    start_date: startDate.value,
    end_date: endDate.value,
    min_strength: String(minStrength.value),
    signal_type: signalType.value,
    market_regime: marketRegime.value,
    sector_type: sectorType.value,
    role: currentUserRole.value,
    export: 'csv',
  })
  const url = `${API_BASE_URL}/api/startup/leader-buy-backtest/signals?${params.toString()}`
  window.open(url, '_blank')
}

const copySummary = async () => {
  const lines = headlineTexts.value || []
  if (!lines.length) return
  const text = lines.join('\n')
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text)
    } else {
      const textarea = document.createElement('textarea')
      textarea.value = text
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
    }
    // eslint-disable-next-line no-alert
    alert('结论文案已复制到剪贴板')
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error('copy summary failed', e)
  }
}

const changePage = (p) => {
  if (p < 1) return
  page.value = p
  fetchData()
}

const formatPct = (v) => {
  if (v === null || v === undefined) return '--'
  const num = Number(v)
  if (Number.isNaN(num)) return '--'
  const sign = num > 0 ? '+' : ''
  return `${sign}${num.toFixed(2)}%`
}

const valueColor = (v) => {
  if (v === null || v === undefined) return 'text-gray-500'
  const num = Number(v)
  if (Number.isNaN(num)) return 'text-gray-500'
  if (num > 0) return 'text-red-600'
  if (num < 0) return 'text-green-600'
  return 'text-gray-500'
}

// 5日收益简单直方图（基于当前页面 + summary 中的统计）
const hist5d = computed(() => {
  const all = (signals.value || []).map((s) => (s.ret_5d == null ? null : Number(s.ret_5d))).filter((v) => v != null && !Number.isNaN(v))
  if (!all.length) {
    return { bins: [] }
  }
  const ranges = [
    { label: '<-15%', min: -Infinity, max: -15 },
    { label: '-15~-10%', min: -15, max: -10 },
    { label: '-10~-5%', min: -10, max: -5 },
    { label: '-5~0%', min: -5, max: 0 },
    { label: '0~5%', min: 0, max: 5 },
    { label: '5~10%', min: 5, max: 10 },
    { label: '>=10%', min: 10, max: Infinity },
  ]
  const bins = ranges.map((r) => ({ label: r.label, count: 0, width: 0 }))
  all.forEach((v) => {
    const idx = ranges.findIndex((r) => v >= r.min && v < r.max)
    if (idx >= 0) {
      bins[idx].count += 1
    }
  })
  const maxCount = bins.reduce((m, b) => (b.count > m ? b.count : m), 0) || 1
  bins.forEach((b) => {
    b.width = b.count > 0 ? Math.max(6, (b.count / maxCount) * 100) : 0
  })
  return { bins }
})

// 按主线强度分桶的平均 5 日收益
const strengthBuckets = computed(() => {
  const s = summary.value
  if (!s || !s.by_strength_bucket) return []
  const raw = s.by_strength_bucket
  const buckets = []
  const labels = ['4-5', '5-6', '6-7', '7+']
  labels.forEach((label) => {
    const info = raw[label]
    if (!info || !info.count || !info.ret_5d) return
    buckets.push({
      label,
      count: info.count,
      avg: info.ret_5d.avg,
      width: 0,
    })
  })
  if (!buckets.length) return []
  const maxAbsAvg = buckets.reduce((m, b) => {
    const v = Math.abs(b.avg || 0)
    return v > m ? v : m
  }, 0) || 1
  buckets.forEach((b) => {
    const ratio = Math.abs(b.avg || 0) / maxAbsAvg
    b.width = ratio > 0 ? Math.max(6, ratio * 100) : 0
  })
  return buckets
})

// 按市场环境（牛 / 震荡 / 熊）分层表现
const marketEnvRows = computed(() => {
  const s = summary.value
  if (!s || !s.by_market_regime) return []
  const raw = s.by_market_regime
  const order = [
    { key: 'bull', label: '偏多（牛市 / 上升）' },
    { key: 'sideways', label: '震荡市' },
    { key: 'bear', label: '偏空（熊市 / 下跌）' },
  ]
  const rows = []
  order.forEach(({ key, label }) => {
    const info = raw[key]
    if (!info || !info.count) return
    rows.push({
      key,
      label,
      count: info.count,
      ret5: info.ret_5d || null,
      ret10: info.ret_10d || null,
    })
  })
  return rows
})

const signalTypeSummary = computed(() => {
  const s = summary.value
  const byType = (s && s.by_signal_type) || {}
  return {
    right: byType.right || null,
    left: byType.left || null,
  }
})

const isTracked = (tsCode) => {
  if (!tsCode) return false
  return !!(trackedMap.value || {})[tsCode]
}

const buildWatchlistNoteForSignal = (s) => {
  const parts = []
  if (s.signal_type === 'right') parts.push('右侧确认')
  else if (s.signal_type === 'left') parts.push('缩量回踩')
  if (s.sector_name) parts.push(String(s.sector_name))
  return `龙头回测-${parts.join('-') || '买点'}`
}

const toggleTrackFromBacktest = (s) => {
  if (!s?.ts_code) return
  const code = s.ts_code
  const cur = { ...(trackedMap.value || {}) }
  const currentlyTracked = !!cur[code]
  if (currentlyTracked) {
    // 仅前端标记，不从后端 watchlist 中删除，避免误操作
    cur[code] = false
    trackedMap.value = cur
    return
  }
  cur[code] = true
  trackedMap.value = cur

  axios
    .post(`${API_BASE_URL}/api/watchlist`, {
      ts_code: code,
      note: buildWatchlistNoteForSignal(s),
    })
    .catch((error) => {
      // eslint-disable-next-line no-console
      console.error('add to watchlist from backtest failed', error)
    })
}

const openDiagnose = (tsCode) => {
  if (!tsCode) return
  const pure = tsCode.replace(/\.(SH|SZ|BJ)$/i, '')
  router.push({ path: '/diagnose', query: { code: pure } })
}

// 顶部 Summary 文案（产品化结论）
const headlineTexts = computed(() => {
  const s = summary.value
  const total = totalSignals.value || 0
  if (!s || total === 0) return []

  const lines = []
  const avg5 = s.ret_5d?.avg
  const win5 = s.ret_5d?.win_rate
  if (avg5 != null && win5 != null) {
    lines.push(`在当前筛选条件下，共有 ${total} 条买点信号，5 日平均收益约 ${formatPct(avg5)}，胜率约 ${formatPct(win5)}。`)
  }

  const byType = s.by_signal_type || {}
  const right = byType.right
  const left = byType.left
  if (right && left && right.ret_5d && left.ret_5d) {
    const r5 = right.ret_5d.avg
    const l5 = left.ret_5d.avg
    if (r5 != null && l5 != null) {
      const better = r5 >= l5 ? '右侧确认' : '缩量回踩'
      lines.push(`同一窗口内，${better} 信号在 5 日平均收益上更优，可作为更值得重仓的一类买点。`)
    }
  }

  if (marketEnvRows.value.length > 0) {
    const bull = marketEnvRows.value.find((r) => r.key === 'bull')
    const bear = marketEnvRows.value.find((r) => r.key === 'bear')
    if (bull?.ret5?.avg != null && bear?.ret5?.avg != null) {
      lines.push(`牛市环境下 5 日平均收益约 ${formatPct(bull.ret5.avg)}，熊市环境下约 ${formatPct(bear.ret5.avg)}，提示在偏空环境中适当收缩仓位。`)
    }
  }

  return lines
})

const drilldownStock = ref('')
const drilldownSignals = computed(() => {
  if (!drilldownStock.value) return []
  return (signals.value || []).filter((s) => s.ts_code === drilldownStock.value)
})

const openDrilldown = (tsCode) => {
  if (!tsCode) return
  drilldownStock.value = tsCode
}

onMounted(() => {
  fetchData()
  fetchMeta()
})
</script>

<style scoped>
</style>

<style scoped>
</style>

