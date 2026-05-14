<template>
  <div class="w-full min-w-0 p-4 sm:p-6 space-y-4">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-semibold text-gray-900">操作池</h1>
        <p class="text-sm text-gray-500 mt-0.5">持仓管理与操作建议</p>
      </div>
      <div class="flex items-center gap-2">
        <Button size="sm" variant="primary" @click="showAddStockDialog = true" v-if="activeTab === 'current'">
          + 加入操作池
        </Button>
        <Button size="sm" variant="secondary" @click="handleRefresh" :disabled="loading">
          {{ loading ? '加载中...' : '刷新' }}
        </Button>
      </div>
    </div>

    <!-- Tab 切换 -->
    <div class="flex gap-3 border-b border-gray-200">
      <button
        @click="activeTab = 'current'"
        :class="[
          'pb-1.5 px-1 text-sm font-medium border-b-2 transition-colors',
          activeTab === 'current' 
            ? 'border-blue-500 text-blue-600' 
            : 'border-transparent text-gray-500 hover:text-gray-700'
        ]"
      >
        当前持仓 ({{ totalHoldings }})
      </button>
      <button
        @click="activeTab = 'history'; fetchHistory()"
        :class="[
          'pb-1.5 px-1 text-sm font-medium border-b-2 transition-colors',
          activeTab === 'history' 
            ? 'border-blue-500 text-blue-600' 
            : 'border-transparent text-gray-500 hover:text-gray-700'
        ]"
      >
        历史持仓 ({{ historyCount }})
      </button>
    </div>

    <!-- 当前持仓统计 -->
    <div v-if="activeTab === 'current'" class="grid grid-cols-5 gap-2">
      <StatCard
        label="总持仓"
        :value="totalHoldings"
        :icon="BriefcaseIcon"
      />
      <StatCard
        label="总市值"
        :value="formatAmount(totalMarketValue)"
        :icon="BanknotesIcon"
      />
      <StatCard
        label="总盈亏"
        :value="formatAmount(totalProfit)"
        :change="totalProfitRate"
        :icon="ArrowTrendingUpIcon"
      />
      <StatCard
        label="今日盈亏"
        :value="formatAmount(todayProfit)"
        :change="todayProfitRate"
        :icon="CalendarIcon"
      />
      <StatCard
        label="高风险持仓"
        :value="highRiskCount"
        :icon="ExclamationTriangleIcon"
      />
    </div>

    <!-- 历史持仓统计卡片 -->
    <div v-if="activeTab === 'history'" class="grid grid-cols-4 gap-3">
      <StatCard
        label="历史交易"
        :value="historyCount"
        :icon="BriefcaseIcon"
      />
      <StatCard
        label="总盈亏"
        :value="formatAmount(historyTotalProfit)"
        :icon="ArrowTrendingUpIcon"
      />
      <StatCard
        label="胜率"
        :value="`${Number(historyWinRate ?? 0).toFixed(2)}%`"
        :icon="ChartBarIcon"
      />
      <StatCard
        label="盈利次数"
        :value="historyWinCount"
        :icon="CheckCircleIcon"
      />
    </div>

    <!-- 说明信息（可收起） -->
    <div v-if="activeTab === 'current'" class="flex items-center gap-2">
      <button @click="showRiskTip = !showRiskTip" class="text-xs text-gray-500 hover:text-gray-700 flex items-center gap-1">
        {{ showRiskTip ? '▼' : '▶' }} 高风险说明
      </button>
      <span v-if="showRiskTip" class="text-xs text-gray-600">追高风险≥70分</span>
    </div>
    <div v-if="activeTab === 'current' && showRiskTip" class="bg-blue-50 border border-blue-200 rounded p-2 text-xs text-gray-600 mb-2">
      基于近3/5日涨幅、MA20偏离度、成交量放大、大阳线天数、突破位涨幅等
    </div>

    <!-- 操作池已满 -->
    <div v-if="activeTab === 'current' && poolFullSuggestion" class="bg-amber-50 border border-amber-200 rounded px-2 py-1.5 text-xs text-amber-900">
      ⚠️ 已满（{{ poolMaxSize }}只）— 建议清仓 {{ poolFullSuggestion.name }} 腾位
    </div>

    <!-- 龙头持仓上限 -->
    <div v-if="activeTab === 'current'" class="bg-slate-50 border border-slate-200 rounded px-2 py-1.5 text-xs text-slate-700">
      龙头持仓：{{ leaderCount }} / {{ leaderMaxSize }} 只
      <span v-if="leaderCount >= leaderMaxSize" class="text-rose-600 font-medium">（已达上限，新开龙头可能会被拒绝）</span>
    </div>

    <!-- AI 建议（可收起） -->
    <div v-if="activeTab === 'current' && aiBatchSuggestions?.suggestions?.length" class="border border-slate-200 rounded overflow-hidden">
      <button @click="showAiSuggestions = !showAiSuggestions" class="w-full px-2 py-1.5 text-left text-xs text-slate-600 bg-slate-50 hover:bg-slate-100 flex items-center justify-between">
        <span>🤖 AI建议 {{ aiBatchSuggestions.suggestions.length }}条</span>
        <div class="flex items-center gap-2">
          <button
            v-if="showAiSuggestions"
            @click.stop="refreshAiSuggestions"
            :disabled="aiRefreshCooldown > 0 || aiRefreshLoading"
            :class="[
              'px-2 py-0.5 text-xs rounded transition-colors',
              aiRefreshCooldown > 0 || aiRefreshLoading
                ? 'bg-slate-200 text-slate-400 cursor-not-allowed'
                : 'bg-blue-100 text-blue-600 hover:bg-blue-200'
            ]"
          >
            {{ aiRefreshLoading ? '刷新中...' : (aiRefreshCooldown > 0 ? `${aiRefreshCooldown}s` : '刷新') }}
          </button>
          <span>{{ showAiSuggestions ? '▼' : '▶' }}</span>
        </div>
      </button>
      <div v-show="showAiSuggestions" class="p-2 overflow-x-auto max-h-32 overflow-y-auto">
        <div v-for="s in aiBatchSuggestions.suggestions" :key="s.symbol" class="flex items-center gap-2 py-0.5 text-xs">
          <span class="font-medium text-slate-800 w-20 truncate">{{ s.name || s.symbol }}</span>
          <span :class="aiActionClass(s.action)" class="px-1.5 py-0.5 rounded shrink-0">{{ s.action }}</span>
          <span class="text-slate-600 truncate flex-1" :title="s.reason">{{ s.reason }}</span>
        </div>
      </div>
    </div>

    <!-- 筛选：分类 + 主线 -->
    <div v-if="activeTab === 'current'" class="flex items-center gap-1.5 flex-wrap">
      <span class="text-xs text-gray-500 mr-0.5">分类</span>
      <FilterButton
        v-for="type in boardTypes"
        :key="type.value"
        :label="type.label"
        :active="selectedBoardType === type.value"
        @click="selectedBoardType = type.value"
      />
      <span class="text-gray-300 mx-1">|</span>
      <FilterButton
        label="主线"
        :active="mainlineOnly"
        @click="mainlineOnly = !mainlineOnly"
      />
      <span v-if="mainlineCount > 0" class="text-xs text-emerald-600 ml-1" title="当前持仓中属于领涨板块的股票数">共 {{ mainlineCount }} 只</span>
    </div>

    <!-- 当前持仓列表 -->
    <div v-if="activeTab === 'current' && loading" class="py-12 text-center text-gray-500">
      <p>加载中...</p>
    </div>

    <div v-else-if="activeTab === 'current' && filteredHoldings.length === 0" class="py-12 text-center text-gray-500">
      <p>暂无持仓，点击"加入操作池"按钮添加股票</p>
    </div>

    <!-- 持仓列表表格 -->
    <div v-else-if="activeTab === 'current'" class="bg-white rounded-lg shadow overflow-hidden w-full">
      <div class="overflow-x-auto w-full">
      <table class="w-full min-w-[850px] table-fixed divide-y divide-gray-200 text-xs">
        <colgroup>
          <col style="width:12%" /><col style="width:8%" /><col style="width:8%" /><col style="width:6%" /><col style="width:6%" /><col style="width:5%" /><col style="width:8%" /><col style="width:8%" /><col style="width:4%" /><col style="width:4%" /><col style="width:6%" /><col style="width:5%" /><col style="width:8%" /><col style="width:4%" /><col style="width:6%" />
        </colgroup>
        <thead class="bg-gray-50">
          <tr>
            <th class="px-2 py-1.5 text-left text-xs font-medium text-gray-500">股票</th>
            <th class="px-2 py-1.5 text-center text-xs font-medium text-gray-500">类型</th>
            <th class="px-2 py-1.5 text-center text-xs font-medium text-gray-500 cursor-pointer hover:text-blue-600" @click="toggleSort('in_mainline')">主/龙头{{ sortField === 'in_mainline' ? (sortOrder === 'desc' ? '↓' : '↑') : '' }}</th>
            <th class="px-2 py-1.5 text-right text-xs font-medium text-gray-500">成本</th>
            <th class="px-2 py-1.5 text-right text-xs font-medium text-gray-500 cursor-pointer hover:text-blue-600" @click="toggleSort('current_price')">现价</th>
            <th class="px-2 py-1.5 text-right text-xs font-medium text-gray-500">数量</th>
            <th class="px-2 py-1.5 text-right text-xs font-medium text-gray-500 cursor-pointer hover:text-blue-600" @click="toggleSort('profit_rate')">盈亏{{ sortField === 'profit_rate' ? (sortOrder === 'desc' ? '↓' : '↑') : '' }}</th>
            <th class="px-2 py-1.5 text-right text-xs font-medium text-gray-500 cursor-pointer hover:text-blue-600" @click="toggleSort('today_profit')">当日盈亏{{ sortField === 'today_profit' ? (sortOrder === 'desc' ? '↓' : '↑') : '' }}</th>
            <th class="px-2 py-1.5 text-center text-xs font-medium text-gray-500" @click="toggleSort('holding_days')">持有</th>
            <th class="px-2 py-1.5 text-center text-xs font-medium text-gray-500" title="5日/10日线">均线</th>
            <th class="px-2 py-1.5 text-center text-xs font-medium text-gray-500">建议</th>
            <th class="px-2 py-1.5 text-center text-xs font-medium text-gray-500">风险</th>
            <th class="px-2 py-1.5 text-center text-xs font-medium text-gray-500 cursor-pointer hover:text-blue-600" @click="toggleSort('strength_score')">强度{{ sortField === 'strength_score' ? (sortOrder === 'desc' ? '↓' : '↑') : '' }}</th>
            <th class="px-2 py-1.5 text-center text-xs font-medium text-gray-500">回涨</th>
            <th class="px-2 py-1.5 text-center text-xs font-medium text-gray-500">操作</th>
          </tr>
        </thead>
        <tbody class="bg-white divide-y divide-gray-200">
          <tr v-for="holding in filteredHoldings" :key="holding.id" :class="['hover:bg-gray-50', poolFullSuggestion?.holding_id === holding.id ? 'bg-amber-50' : '']">
            <td class="px-2 py-1.5 whitespace-nowrap">
              <span class="font-medium text-gray-900">{{ holding.name || '--' }}</span>
              <span class="text-gray-500 text-xs"> {{ holding.symbol }}</span>
            </td>
            <td class="px-2 py-1.5 text-center">
              <span
                v-if="getLeaderTypeLabel(holding.symbol)"
                :class="getLeaderTypeLabel(holding.symbol) === '空间+刚启动'
                  ? 'bg-purple-50 text-purple-700'
                  : getLeaderTypeLabel(holding.symbol) === '空间龙头'
                    ? 'bg-amber-50 text-amber-700'
                    : 'bg-rose-50 text-rose-700'"
                class="inline-flex px-1.5 py-0.5 rounded text-[11px] font-medium"
              >
                {{ getLeaderTypeLabel(holding.symbol) }}
              </span>
              <span v-else class="text-gray-300">—</span>
            </td>
            <td class="px-2 py-1.5 text-center">
              <span v-if="holding.in_mainline || holding.sector_leader_role || holding.is_leader" :title="(holding.in_mainline ? (holding.mainline_sectors || []).join('、') + '\n' : '') + (holding.leader_type ? holding.leader_type + ' · ' : '') + (holding.sector_leader_of || '')">
                <span v-if="holding.in_mainline" class="text-emerald-600 mr-0.5">✓</span>
                <span v-if="holding.sector_leader_role" :class="holding.sector_leader_role === '绝对龙头' ? 'text-rose-600' : holding.sector_leader_role === '补涨' ? 'text-sky-600' : 'text-slate-500'" class="text-[11px]">
                  {{ holding.sector_leader_role === '绝对龙头' ? '绝对龙头' : holding.sector_leader_role === '补涨' ? '补涨' : '跟风' }}
                </span>
                <span v-else-if="holding.is_leader" class="text-amber-600 text-[11px]">{{ holding.leader_type || '龙' }}</span>
              </span>
              <span v-else class="text-gray-300">—</span>
            </td>
            <td class="px-2 py-1.5 text-right tabular-nums text-gray-600">{{ holding.avg_cost_price > 0 ? holding.avg_cost_price.toFixed(2) : '--' }}</td>
            <td class="px-2 py-1.5 text-right tabular-nums">{{ holding.current_price > 0 ? holding.current_price.toFixed(2) : '--' }}</td>
            <td class="px-2 py-1.5 text-right tabular-nums">{{ holding.total_quantity || 0 }}</td>
            <td class="px-2 py-1.5 text-right whitespace-nowrap tabular-nums">
              <div :class="(holding.profit_rate || 0) >= 0 ? 'text-red-600' : 'text-green-600'">
                <div class="font-medium">{{ (holding.profit_rate || 0) >= 0 ? '+' : '' }}{{ (holding.profit_rate || 0).toFixed(2) }}%</div>
                <div class="text-xs">{{ (holding.profit_amount || 0) >= 0 ? '+' : '' }}{{ formatAmount(holding.profit_amount || 0) }}元</div>
              </div>
            </td>
            <td class="px-2 py-1.5 text-right whitespace-nowrap tabular-nums">
              <div :class="(holding.today_profit || 0) >= 0 ? 'text-red-600' : 'text-green-600'">
                <div class="font-medium">{{ (holding.change_pct ?? 0) >= 0 ? '+' : '' }}{{ (holding.change_pct ?? 0).toFixed(2) }}%</div>
                <div class="text-xs">{{ (holding.today_profit || 0) >= 0 ? '+' : '' }}{{ formatAmount(holding.today_profit || 0) }}元</div>
              </div>
            </td>
            <td class="px-2 py-1.5 text-center tabular-nums" :title="holding.can_sell ? '交易日' : 'T+1'">{{ holding.holding_days || 0 }}天</td>
            <td class="px-2 py-1.5 text-center tabular-nums" title="5日线/10日线">
              <span :class="holding.below_ma5 ? 'text-green-500' : 'text-red-500'">{{ holding.below_ma5 ? '✗' : '✓' }}</span>
              <span :class="holding.below_ma10 ? 'text-green-500' : 'text-red-500'">{{ holding.below_ma10 ? '✗' : '✓' }}</span>
            </td>
            <td class="px-2 py-1.5 text-center">
              <span 
                v-if="poolFullSuggestion?.holding_id === holding.id"
                class="px-1.5 py-0.5 rounded bg-amber-200 text-amber-800 text-[11px] font-medium"
                :title="poolFullSuggestion?.reason"
              >清仓</span>
              <span 
                v-else
                :class="(actionBadgeColors[holding.today_action] || 'bg-gray-100 text-gray-700') + ' px-1.5 py-0.5 rounded text-[11px]'"
                :title="holding.today_action_reason"
              >{{ actionLabels[holding.today_action] || '持有' }}</span>
            </td>
            <td class="px-2 py-1.5 text-center">
              <span :class="riskBadgeColors[holding.chase_risk_level] || 'bg-gray-100 text-gray-700'" class="px-1.5 py-0.5 rounded text-[11px] cursor-help" :title="holding.chase_risk_reason">{{ riskLabels[holding.chase_risk_level] || '低' }}</span>
            </td>
            <td class="px-2 py-1.5 text-center">
              <span :class="strengthBadgeClass(holding.strength_level)" class="inline-flex items-baseline gap-0.5 px-1.5 py-0.5 rounded text-[11px] font-medium cursor-help" :title="`${holding.strength_score ?? '--'}分`">
                <span class="tabular-nums font-bold">{{ holding.strength_score ?? '--' }}</span>
                <span>{{ holding.strength_level || '—' }}</span>
              </span>
            </td>
            <td class="px-2 py-1.5 text-center">
              <span v-if="holding.recovery_analysis" :class="recoveryBadgeColors[holding.recovery_analysis.recovery_level]" class="px-1.5 py-0.5 rounded text-[11px] cursor-help" :title="formatRecoveryTooltip(holding.recovery_analysis)">
                {{ holding.recovery_analysis.recovery_probability?.toFixed(0) || 0 }}%
              </span>
              <span v-else class="text-gray-400">—</span>
            </td>
            <td class="px-2 py-1.5 text-center">
              <span class="inline-flex items-center gap-0.5 justify-center">
                <button v-if="poolFullSuggestion?.holding_id === holding.id" @click="openReducePositionDialog(holding)" class="px-1 py-0.5 rounded text-[10px] font-medium text-amber-700 bg-amber-100 hover:bg-amber-200">清仓</button>
                <button @click="openAddPositionDialog(holding)" title="加仓" class="p-0.5 rounded text-green-600 hover:bg-green-50"><PlusIcon class="w-3.5 h-3.5" /></button>
                <button @click="openReducePositionDialog(holding)" title="减仓" class="p-0.5 rounded text-orange-600 hover:bg-orange-50"><MinusIcon class="w-3.5 h-3.5" /></button>
                <button @click="openEditDialog(holding)" title="编辑" class="p-0.5 rounded text-blue-600 hover:bg-blue-50"><PencilSquareIcon class="w-3.5 h-3.5" /></button>
                <button @click="handleDelete(holding)" title="删除" class="p-0.5 rounded text-red-600 hover:bg-red-50"><TrashIcon class="w-3.5 h-3.5" /></button>
              </span>
            </td>
          </tr>
        </tbody>
      </table>
      </div>
    </div>

    <!-- 历史持仓列表 -->
    <div v-if="activeTab === 'history' && historyLoading" class="py-12 text-center text-gray-500">
      <p>加载中...</p>
    </div>

    <div v-else-if="activeTab === 'history' && historyHoldings.length === 0" class="py-12 text-center text-gray-500">
      <p>暂无历史交易记录</p>
    </div>

    <div v-else-if="activeTab === 'history'" class="bg-white rounded-lg shadow overflow-hidden">
      <table class="min-w-full divide-y divide-gray-200">
        <thead class="bg-gray-50">
          <tr>
            <th class="px-3 py-2 text-left text-xs font-medium text-gray-500">股票</th>
            <th class="px-3 py-2 text-center text-xs font-medium text-gray-500">买入日期</th>
            <th class="px-3 py-2 text-center text-xs font-medium text-gray-500">清仓日期</th>
            <th class="px-3 py-2 text-center text-xs font-medium text-gray-500">成本价</th>
            <th class="px-3 py-2 text-center text-xs font-medium text-gray-500">清仓价</th>
            <th class="px-3 py-2 text-center text-xs font-medium text-gray-500">数量</th>
            <th class="px-3 py-2 text-center text-xs font-medium text-gray-500">盈亏</th>
            <th class="px-3 py-2 text-center text-xs font-medium text-gray-500">清仓当日盈亏</th>
            <th class="px-3 py-2 text-center text-xs font-medium text-gray-500">持有天数</th>
            <th class="px-3 py-2 text-center text-xs font-medium text-gray-500">操作</th>
          </tr>
        </thead>
        <tbody class="bg-white divide-y divide-gray-200">
          <tr v-for="h in historyHoldings" :key="h.id" class="hover:bg-gray-50">
            <td class="px-3 py-3">
              <div class="text-sm font-medium text-gray-900">{{ h.name || h.symbol }}</div>
              <div class="text-xs text-gray-500">{{ h.symbol }}</div>
            </td>
            <td class="px-3 py-3 text-center text-sm text-gray-600">{{ h.buy_date || '--' }}</td>
            <td class="px-3 py-3 text-center text-sm text-gray-600">{{ h.close_date || '--' }}</td>
            <td class="px-3 py-3 text-center text-sm text-gray-600">¥{{ h.avg_cost_price?.toFixed(2) }}</td>
            <td class="px-3 py-3 text-center text-sm text-gray-600">
              <span v-if="h.close_price > 0">¥{{ h.close_price?.toFixed(2) }}</span>
              <span v-else class="text-orange-500">未填写</span>
            </td>
            <td class="px-3 py-3 text-center text-sm text-gray-600">{{ h.total_quantity }}</td>
            <td class="px-3 py-3 text-center">
              <span :class="h.realized_profit >= 0 ? 'text-red-600' : 'text-green-600'" class="text-sm font-medium">
                {{ h.realized_profit >= 0 ? '+' : '' }}{{ formatAmount(h.realized_profit) }}
              </span>
            </td>
            <td class="px-3 py-3 text-center">
              <span v-if="h.close_day_profit != null" :class="(h.close_day_profit || 0) >= 0 ? 'text-red-600' : 'text-green-600'" class="text-sm font-medium">
                {{ (h.close_day_profit || 0) >= 0 ? '盈利 ' : '亏损 ' }}{{ (h.close_day_profit || 0) >= 0 ? '+' : '' }}{{ formatAmount(h.close_day_profit || 0) }}
              </span>
              <span v-else class="text-gray-400 text-xs">--</span>
            </td>
            <td class="px-3 py-3 text-center text-sm text-gray-600">
              {{ calcHoldingDays(h.buy_date, h.close_date) }}天
            </td>
            <td class="px-3 py-3 text-center">
              <button @click="openHistoryEditDialog(h)" class="text-blue-600 hover:text-blue-800 text-xs">修改</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    
    <!-- 编辑对话框 -->
    <div v-if="showEditDialog" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg p-6 max-w-md w-full mx-4">
        <h3 class="text-lg font-semibold mb-4">编辑持仓</h3>
        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">股票代码</label>
            <input
              v-model.trim="editForm.symbol"
              type="text"
              maxlength="10"
              class="w-full px-3 py-2 border border-gray-300 rounded-md font-mono"
              placeholder="如 002487 或 002487.SZ"
            />
            <p class="mt-1 text-xs text-gray-500">填错代码时可在此修改，如大金重工应为 002487</p>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">股票名称</label>
            <input v-model.trim="editForm.name" type="text" class="w-full px-3 py-2 border border-gray-300 rounded-md" placeholder="股票名称" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">成本价</label>
            <input v-model.number="editForm.avg_cost_price" type="number" step="0.01" class="w-full px-3 py-2 border border-gray-300 rounded-md" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">持仓数量</label>
            <input v-model.number="editForm.total_quantity" type="number" step="100" class="w-full px-3 py-2 border border-gray-300 rounded-md" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">买入日期</label>
            <input v-model="editForm.buy_date" type="date" class="w-full px-3 py-2 border border-gray-300 rounded-md" />
            <p class="mt-1 text-xs text-gray-500">A股T+1规则：当日买入次日可卖</p>
          </div>
        </div>
        <div class="flex items-center gap-2 mt-6">
          <Button @click="handleConfirmEdit">确认</Button>
          <Button variant="secondary" @click="showEditDialog = false">取消</Button>
        </div>
      </div>
    </div>

    <!-- 历史持仓编辑对话框 -->
    <div v-if="showHistoryEditDialog" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg p-6 max-w-md w-full mx-4">
        <h3 class="text-lg font-semibold mb-4">修改清仓信息 - {{ editingHistory?.name || editingHistory?.symbol }}</h3>
        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">清仓价格</label>
            <input v-model.number="historyEditForm.close_price" type="number" step="0.01" class="w-full px-3 py-2 border border-gray-300 rounded-md" placeholder="输入实际卖出价格" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">清仓日期</label>
            <input v-model="historyEditForm.close_date" type="date" class="w-full px-3 py-2 border border-gray-300 rounded-md" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">清仓数量（股）</label>
            <input v-model.number="historyEditForm.total_quantity" type="number" step="100" min="0" class="w-full px-3 py-2 border border-gray-300 rounded-md" placeholder="实际卖出数量" />
          </div>
          <div class="bg-gray-50 p-3 rounded-md text-sm">
            <p class="text-gray-600">成本价：¥{{ editingHistory?.avg_cost_price?.toFixed(2) }}</p>
            <p class="mt-2 font-medium" :class="previewProfit >= 0 ? 'text-red-600' : 'text-green-600'">
              预计盈亏：{{ previewProfit >= 0 ? '+' : '' }}{{ formatAmount(previewProfit) }}
            </p>
          </div>
        </div>
        <div class="flex items-center gap-2 mt-6">
          <Button @click="handleConfirmHistoryEdit">确认</Button>
          <Button variant="secondary" @click="showHistoryEditDialog = false">取消</Button>
        </div>
      </div>
    </div>

    <!-- 加仓对话框 -->
    <div v-if="showAddPositionDialog" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg p-6 max-w-md w-full mx-4">
        <h3 class="text-lg font-semibold mb-4">加仓 - {{ editingHolding?.name }}</h3>
        <div class="space-y-4">
          <div class="bg-gray-50 p-3 rounded-md text-sm">
            <p class="text-gray-600">当前成本：¥{{ editingHolding?.avg_cost_price?.toFixed(2) || '0.00' }}</p>
            <p class="text-gray-600">当前持仓：{{ editingHolding?.total_quantity || 0 }} 股</p>
            <p class="text-gray-600">当前现价：¥{{ editingHolding?.current_price?.toFixed(2) || '0.00' }}</p>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">买入价格</label>
            <input 
              v-model.number="addPositionForm.price" 
              type="number" 
              step="0.01" 
              class="w-full px-3 py-2 border border-gray-300 rounded-md" 
              placeholder="输入买入价格"
            />
            <button
              v-if="editingHolding?.current_price"
              @click="addPositionForm.price = editingHolding.current_price"
              class="mt-1 text-xs text-blue-600 hover:text-blue-800"
            >
              使用当前价 ¥{{ editingHolding.current_price.toFixed(2) }}
            </button>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">买入数量（股）</label>
            <input 
              v-model.number="addPositionForm.quantity" 
              type="number" 
              step="100" 
              class="w-full px-3 py-2 border border-gray-300 rounded-md" 
              placeholder="输入买入数量"
            />
          </div>
          <div v-if="addPositionForm.price && addPositionForm.quantity" class="bg-blue-50 p-3 rounded-md text-sm">
            <p class="text-gray-700 font-medium">预计结果：</p>
            <p class="text-gray-600 mt-1">
              新持仓：{{ (editingHolding?.total_quantity || 0) + addPositionForm.quantity }} 股
            </p>
            <p class="text-gray-600">
              新成本：¥{{ calculateNewCost(editingHolding, addPositionForm.price, addPositionForm.quantity).toFixed(2) }}
            </p>
          </div>
        </div>
        <div class="flex items-center gap-2 mt-6">
          <Button @click="handleConfirmAddPosition">确认加仓</Button>
          <Button variant="secondary" @click="showAddPositionDialog = false">取消</Button>
        </div>
      </div>
    </div>

    <!-- 减仓对话框 -->
    <div v-if="showReducePositionDialog" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg p-6 max-w-md w-full mx-4">
        <h3 class="text-lg font-semibold mb-4">减仓 - {{ editingHolding?.name }}</h3>
        <div class="space-y-4">
          <div class="bg-gray-50 p-3 rounded-md text-sm">
            <p class="text-gray-600">当前成本：¥{{ editingHolding?.avg_cost_price?.toFixed(2) || '0.00' }}</p>
            <p class="text-gray-600">当前持仓：{{ editingHolding?.total_quantity || 0 }} 股</p>
            <p class="text-gray-600">当前现价：¥{{ editingHolding?.current_price?.toFixed(2) || '0.00' }}</p>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">卖出价格</label>
            <input 
              v-model.number="reducePositionForm.price" 
              type="number" 
              step="0.01" 
              class="w-full px-3 py-2 border border-gray-300 rounded-md" 
              placeholder="输入卖出价格"
            />
            <button
              v-if="editingHolding?.current_price"
              @click="reducePositionForm.price = editingHolding.current_price"
              class="mt-1 text-xs text-blue-600 hover:text-blue-800"
            >
              使用当前价 ¥{{ editingHolding.current_price.toFixed(2) }}
            </button>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">卖出数量（股）</label>
            <input 
              v-model.number="reducePositionForm.quantity" 
              type="number" 
              step="100" 
              class="w-full px-3 py-2 border border-gray-300 rounded-md" 
              placeholder="输入卖出数量"
              :max="editingHolding?.total_quantity || 0"
            />
            <p class="mt-1 text-xs text-gray-500">最多可卖：{{ editingHolding?.total_quantity || 0 }} 股</p>
          </div>
          <div v-if="reducePositionForm.price && reducePositionForm.quantity" class="bg-blue-50 p-3 rounded-md text-sm">
            <p class="text-gray-700 font-medium">预计结果：</p>
            <p class="text-gray-600 mt-1">
              剩余持仓：{{ Math.max(0, (editingHolding?.total_quantity || 0) - reducePositionForm.quantity) }} 股
            </p>
            <p class="text-gray-600">
              本次盈亏：<span :class="calculateReduceProfit(editingHolding, reducePositionForm.price, reducePositionForm.quantity) >= 0 ? 'text-red-600' : 'text-green-600'">
                {{ calculateReduceProfit(editingHolding, reducePositionForm.price, reducePositionForm.quantity) >= 0 ? '+' : '' }}{{ formatAmount(calculateReduceProfit(editingHolding, reducePositionForm.price, reducePositionForm.quantity)) }}
              </span>
            </p>
          </div>
        </div>
        <div class="flex items-center gap-2 mt-6">
          <Button @click="handleConfirmReducePosition">确认减仓</Button>
          <Button variant="secondary" @click="showReducePositionDialog = false">取消</Button>
        </div>
      </div>
    </div>

    <!-- 添加股票对话框 -->
    <div v-if="showAddStockDialog" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg p-6 max-w-2xl w-full mx-4 max-h-[80vh] flex flex-col">
        <h3 class="text-lg font-semibold mb-4">加入操作池</h3>

        <!-- 添加方式切换 -->
        <div class="flex gap-2 mb-4">
          <button
            :class="['px-3 py-1.5 rounded text-sm', addMode === 'search' ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200']"
            @click="addMode = 'search'; imageParseRecords = []; imageParseError = ''"
          >
            搜索添加
          </button>
          <button
            :class="['px-3 py-1.5 rounded text-sm', addMode === 'image' ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200']"
            @click="addMode = 'image'; selectedStock = null; stockSearchQuery = ''; stockSearchResults = []"
          >
            从图片识别
          </button>
        </div>

        <!-- 从图片识别 -->
        <div v-if="addMode === 'image'" class="space-y-4 flex-1 overflow-y-auto">
          <div class="border-2 border-dashed border-gray-300 rounded-lg p-6 text-center hover:border-blue-400 transition-colors">
            <input
              ref="imageFileInput"
              type="file"
              accept="image/*"
              class="hidden"
              @change="handleImageFileSelect"
            />
            <button
              type="button"
              @click="imageFileInput?.click()"
              class="text-blue-600 hover:text-blue-800 font-medium"
            >
              选择成交截图
            </button>
            <p class="text-xs text-gray-500 mt-1">支持 PNG、JPG，识别股票代码、买入价、数量</p>
          </div>
          <div v-if="imageParseLoading" class="text-sm text-gray-500 text-center py-4">AI 识别中...</div>
          <div v-else-if="imageParseError" class="text-sm text-red-600 bg-red-50 p-2 rounded flex items-center justify-between gap-2">
            <span class="flex-1">{{ imageParseError }}</span>
            <button type="button" class="text-red-700 underline shrink-0" @click="imageParseError = ''">重试</button>
          </div>
          <div v-else-if="imageParseRecords.length > 0" class="border rounded overflow-hidden">
            <p class="text-sm text-gray-600 bg-gray-50 px-2 py-1.5">识别到 {{ imageParseRecords.length }} 笔，勾选后批量加入</p>
            <div class="max-h-48 overflow-y-auto divide-y">
              <label
                v-for="(r, i) in imageParseRecords"
                :key="i"
                class="flex items-center gap-3 px-3 py-2 hover:bg-gray-50 cursor-pointer"
              >
                <input type="checkbox" v-model="r.checked" class="rounded" />
                <span class="font-medium w-20">{{ r.name || r.code }}</span>
                <span class="text-gray-500 text-sm">{{ r.code }}</span>
                <span class="text-sm">¥{{ (r.buy_price || 0).toFixed(2) }}</span>
                <span class="text-sm text-gray-500">{{ r.quantity || 0 }} 股</span>
              </label>
            </div>
            <div class="flex gap-2 p-2 bg-gray-50 border-t">
              <button
                @click="handleBatchAddFromImage"
                :disabled="!imageParseRecords.some(r => r.checked)"
                class="px-4 py-1.5 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed"
              >
                批量加入 ({{ imageParseRecords.filter(r => r.checked).length }})
              </button>
              <button @click="imageParseRecords = []; imageParseError = ''" class="px-4 py-1.5 bg-gray-200 text-gray-700 rounded text-sm hover:bg-gray-300">
                清空
              </button>
            </div>
          </div>
        </div>

        <!-- 股票搜索（原有方式） -->
        <div v-if="addMode === 'search'" class="mb-4 relative">
          <label class="block text-sm font-medium text-gray-700 mb-2">搜索股票（按名称或代码）</label>
          <input
            v-model="stockSearchQuery"
            @input="searchStocks"
            @blur="hideSearchResults"
            type="text"
            class="w-full px-3 py-2 border border-gray-300 rounded-md"
            placeholder="输入股票名称或代码..."
          />
          
          <!-- 搜索结果下拉层（绝对定位） -->
          <div v-if="stockSearchLoading" class="absolute left-0 right-0 top-full mt-1 bg-white border border-gray-200 rounded-md shadow-lg z-10 p-2 text-sm text-gray-500">
            搜索中...
          </div>
          <div v-else-if="stockSearchResults.length > 0" class="absolute left-0 right-0 top-full mt-1 bg-white border border-gray-200 rounded-md shadow-lg z-10 max-h-60 overflow-y-auto">
            <div
              v-for="stock in stockSearchResults"
              :key="stock.code || stock.ts_code || stock.代码"
              @mousedown.prevent="selectStock(stock)"
              class="px-3 py-2 hover:bg-blue-50 cursor-pointer border-b border-gray-100 last:border-b-0"
            >
              <div class="flex items-center justify-between">
                <div>
                  <p class="font-medium text-gray-900">{{ stock.name || stock.名称 }}</p>
                  <p class="text-xs text-gray-500">{{ stock.code || stock.ts_code || stock.代码 }}</p>
                </div>
              </div>
            </div>
          </div>
          <div v-else-if="stockSearchQuery && stockSearchQuery.length >= 1 && !stockSearchLoading" class="absolute left-0 right-0 top-full mt-1 bg-white border border-gray-200 rounded-md shadow-lg z-10 p-2 text-sm text-gray-500">
            未找到匹配的股票
          </div>
        </div>
        
        <!-- 已选股票信息 -->
        <div v-if="addMode === 'search' && selectedStock" class="mb-4 p-3 bg-gray-50 rounded-md">
          <p class="text-sm font-medium text-gray-700">已选择：{{ selectedStock.name || selectedStock.名称 }} ({{ selectedStock.code || selectedStock.ts_code || selectedStock.代码 }})</p>
        </div>
        
        <!-- 表单（搜索模式） -->
        <div v-if="addMode === 'search'" class="space-y-4 flex-1 overflow-y-auto">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">分类</label>
            <select v-model="addStockForm.board_type" class="w-full px-3 py-2 border border-gray-300 rounded-md">
              <option value="darwin">长线·达尔文</option>
              <option value="swing">波段</option>
              <option value="short">短线</option>
              <option value="other">其他</option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">买入价（可选）</label>
            <input
              v-model.number="addStockForm.buy_price"
              type="number"
              step="0.01"
              class="w-full px-3 py-2 border border-gray-300 rounded-md"
              placeholder="输入买入价"
            />
            <button
              v-if="selectedStock"
              @click="addStockForm.buy_price = selectedStock.current_price || selectedStock.close || selectedStock.price"
              class="mt-1 text-xs text-blue-600 hover:text-blue-800"
            >
              使用当前价
            </button>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">数量（可选）</label>
            <input
              v-model.number="addStockForm.quantity"
              type="number"
              step="100"
              class="w-full px-3 py-2 border border-gray-300 rounded-md"
              placeholder="输入数量（股）"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">买入日期</label>
            <input
              v-model="addStockForm.buy_date"
              type="date"
              class="w-full px-3 py-2 border border-gray-300 rounded-md"
            />
            <p class="mt-1 text-xs text-gray-500">A股T+1规则：当日买入次日可卖</p>
          </div>
        </div>
        
        <!-- 按钮（搜索模式） -->
        <div class="flex items-center gap-2 mt-6" v-if="addMode === 'search'">
          <button
            @click="handleConfirmAddStock"
            :disabled="!selectedStock"
            class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:bg-gray-300 disabled:cursor-not-allowed"
          >
            确认
          </button>
          <button
            @click="closeAddDialog"
            class="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition-colors"
          >
            取消
          </button>
        </div>
        <!-- 图片模式：仅取消 -->
        <div class="flex items-center gap-2 mt-6" v-else>
          <button
            @click="closeAddDialog"
            class="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition-colors"
          >
            关闭
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { dataCache, CACHE_KEYS } from '../../services/dataCache'
import { stockApi } from '../../api/stockApi'
import Button from '@/components/ui/Button.vue'
import StatCard from '@/components/ui/StatCard.vue'
import FilterButton from '@/components/ui/FilterButton.vue'
import HoldingCard from '@/components/ui/HoldingCard.vue'
import {
  BriefcaseIcon,
  BanknotesIcon,
  ArrowTrendingUpIcon,
  ExclamationTriangleIcon,
  CalendarIcon,
  ChartBarIcon,
  CheckCircleIcon,
  PlusIcon,
  MinusIcon,
  PencilSquareIcon,
  TrashIcon
} from '@heroicons/vue/24/outline'

// 与其它页面一致：未配置时直连后端，避免因未配置 Vite 代理导致类型拉取失败
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

// Tab切换
const activeTab = ref('current')

// 数据
const loading = ref(false)
const holdings = ref([])
const selectedBoardType = ref(null)
const poolMaxSize = ref(20)
const leaderMaxSize = ref(10)
const leaderCount = ref(0)
const poolFullSuggestion = ref(null)
const todayRealizedFromClosed = ref(0)  // 操作池已满时建议清仓的一只 { holding_id, symbol, name, reason }
const aiBatchSuggestions = ref(null)  // AI 综合建议
const aiRefreshCooldown = ref(0)  // AI 刷新冷却倒计时（秒）
const aiRefreshLoading = ref(false)  // AI 刷新加载状态
let aiRefreshTimer = null  // AI 刷新冷却计时器 { suggestions: [{ symbol, action, reason }], updated_at }

// 空间龙头/刚启动标签（由 sector-strength 接口填充）
const leaderTypeBySymbol = ref({})  // { "000001.SZ": "空间龙头" | "刚启动" | "空间+刚启动" }
const LEADER_TYPE_CACHE_KEY = 'holdings-leader-type-cache-v1'
try {
  const raw = window.localStorage.getItem(LEADER_TYPE_CACHE_KEY)
  if (raw) leaderTypeBySymbol.value = JSON.parse(raw) || {}
} catch {
  // ignore cache read errors
}

// 历史持仓
const historyLoading = ref(false)
const historyHoldings = ref([])
const historyCount = ref(0)
const historyWinRate = ref(0)
const historyTotalProfit = computed(() => historyHoldings.value.reduce((sum, h) => sum + (h.realized_profit || 0), 0))
const historyWinCount = computed(() => historyHoldings.value.filter(h => (h.realized_profit || 0) > 0).length)

// 历史持仓编辑
const showHistoryEditDialog = ref(false)
const editingHistory = ref(null)
const historyEditForm = ref({ close_price: 0, close_date: '', total_quantity: 0 })
const previewProfit = computed(() => {
  if (!editingHistory.value || !historyEditForm.value.close_price) return 0
  const qty = historyEditForm.value.total_quantity ?? editingHistory.value.total_quantity ?? 0
  const cost = editingHistory.value.avg_cost_price || 0
  const closePrice = historyEditForm.value.close_price || 0
  return (closePrice - cost) * qty
})

// 分类选项（与加入操作池下拉一致）
const boardTypes = [
  { value: null, label: '全部' },
  { value: 'darwin', label: '长线·达尔文' },
  { value: 'swing', label: '波段' },
  { value: 'short', label: '短线' },
  { value: 'other', label: '其他' },
]

// 排序
const sortField = ref('profit_rate')
const sortOrder = ref('desc')
const mainlineOnly = ref(false)
const showRiskTip = ref(false)
const showAiSuggestions = ref(false)

const toggleSort = (field) => {
  if (sortField.value === field) {
    sortOrder.value = sortOrder.value === 'desc' ? 'asc' : 'desc'
  } else {
    sortField.value = field
    sortOrder.value = 'desc'
  }
}

// 主线数量
const mainlineCount = computed(() => {
  const list = Array.isArray(holdings.value) ? holdings.value : []
  return list.filter(h => h.in_mainline).length
})

// 计算属性（确保 holdings 始终按数组处理）
const filteredHoldings = computed(() => {
  const list = Array.isArray(holdings.value) ? holdings.value : []
  let result = list
  if (selectedBoardType.value) {
    result = result.filter(h => h.board_type === selectedBoardType.value)
  }
  if (mainlineOnly.value) {
    result = result.filter(h => h.in_mainline)
  }
  // 排序（in_mainline 为布尔，主线优先时 true>false）
  return [...result].sort((a, b) => {
    const fn = sortField.value
    if (fn === 'in_mainline') {
      const aVal = a.in_mainline ? 1 : 0
      const bVal = b.in_mainline ? 1 : 0
      return sortOrder.value === 'desc' ? bVal - aVal : aVal - bVal
    }
    const aVal = a[fn] || 0
    const bVal = b[fn] || 0
    return sortOrder.value === 'desc' ? bVal - aVal : aVal - bVal
  })
})

const totalHoldings = computed(() => (Array.isArray(holdings.value) ? holdings.value : []).length)

const totalMarketValue = computed(() => {
  const list = Array.isArray(holdings.value) ? holdings.value : []
  return list.reduce((sum, h) => sum + (h.market_value || 0), 0)
})

const totalProfit = computed(() => {
  const list = Array.isArray(holdings.value) ? holdings.value : []
  return list.reduce((sum, h) => sum + (h.profit_amount || 0), 0)
})

const totalProfitRate = computed(() => {
  const list = Array.isArray(holdings.value) ? holdings.value : []
  const totalCost = list.reduce((sum, h) => {
    return sum + ((h.avg_cost_price || 0) * (h.total_quantity || 0))
  }, 0)
  if (totalCost === 0) return 0
  return (totalProfit.value / totalCost) * 100
})

const highRiskCount = computed(() => {
  const list = Array.isArray(holdings.value) ? holdings.value : []
  return list.filter(h => h.chase_risk_level === 'high').length
})

// 今日盈亏 = 当前持仓当日浮盈 + 今日清仓已实现盈亏
const todayProfit = computed(() => {
  const list = Array.isArray(holdings.value) ? holdings.value : []
  const holdingsToday = list.reduce((sum, h) => sum + (h.today_profit || 0), 0)
  return holdingsToday + (todayRealizedFromClosed.value || 0)
})

const todayProfitRate = computed(() => {
  const yesterdayMv = totalMarketValue.value - todayProfit.value
  if (yesterdayMv === 0) return 0
  return (todayProfit.value / yesterdayMv) * 100
})

// 方法
const fetchHoldings = async (forceRefresh = false) => {
  loading.value = true
  try {
    // 检查缓存（持仓数据不按board_type缓存，因为筛选是前端做的）
    if (!forceRefresh) {
      const cached = dataCache.get(CACHE_KEYS.HOLDINGS)
      if (cached) {
        const list = Array.isArray(cached) ? cached : (cached.data || [])
        if (list.length >= 0) {
          console.log('📦 使用缓存的持仓数据')
          holdings.value = list
          if (!Array.isArray(cached)) {
            poolMaxSize.value = cached.pool_max_size ?? 20
            leaderMaxSize.value = cached.leader_max_size ?? 10
            leaderCount.value = cached.leader_count ?? 0
            poolFullSuggestion.value = cached.pool_full_suggestion || null
            aiBatchSuggestions.value = cached.ai_batch_suggestions || null
            todayRealizedFromClosed.value = cached.today_realized ?? 0
          }
          // 避免 fetchLeaderTypes 的 Promise 未被消费导致页面产生 Uncaught
          fetchLeaderTypes().catch((e) => {
            // eslint-disable-next-line no-console
            console.error('fetchLeaderTypes promise rejected:', e)
          })
          loading.value = false
          return
        }
      }
    }
    
    // 使用统一的API封装（返回 { data, count, pool_max_size, pool_full_suggestion }）
    const res = await stockApi.getHoldings(selectedBoardType.value).catch(() => ({ data: [], pool_max_size: 8, leader_max_size: 5, leader_count: 0, pool_full_suggestion: null }))
    holdings.value = Array.isArray(res.data) ? res.data : (res.data || [])
    poolMaxSize.value = res.pool_max_size ?? 20
    leaderMaxSize.value = res.leader_max_size ?? 10
    leaderCount.value = res.leader_count ?? 0
    poolFullSuggestion.value = res.pool_full_suggestion || null
    aiBatchSuggestions.value = res.ai_batch_suggestions || null
    todayRealizedFromClosed.value = res.today_realized ?? 0
    dataCache.set(CACHE_KEYS.HOLDINGS, res)
    fetchLeaderTypes().catch((e) => {
      // eslint-disable-next-line no-console
      console.error('fetchLeaderTypes promise rejected:', e)
    })
  } catch (error) {
    console.error('获取持仓列表失败:', error)
  } finally {
    loading.value = false
  }
}

// 拉取空间龙头/刚启动列表，用于「类型」列展示
const fetchLeaderTypes = async () => {
  // 保底：失败时不清空已加载的映射，避免“类型突然全没了”
  const prevMap = leaderTypeBySymbol.value || {}
  try {
    // 让“我的自选类型”与“龙头跟踪”完全一致：用持久跟踪池兜底（优先）
    const query = [
      'min_score=60',
      "stage=confirmed",
      "stable_window_id=rolling_30d_v2",
      'bootstrap_days=180',
      'do_bootstrap=true',
      'force_sync=false',
      'catch_up_window_trading_days=30',
      'catch_up_max_syncs=30',
    ].join('&')

    // 优先走相对路径（Vite 代理/同源更稳），失败再回退绝对地址
    const relUrl = `/api/leader-tracking/pool?${query}`
    const absUrl = `${API_BASE_URL}/api/leader-tracking/pool?${query}`

    let poolRes = null
    try {
      poolRes = await fetch(relUrl).then((r) => r.json())
    } catch {
      poolRes = await fetch(absUrl).then((r) => r.json())
    }

    if (poolRes?.success && Array.isArray(poolRes?.pool)) {
      const map = {}
      for (const row of poolRes.pool) {
        const ts = row?.ts_code
        if (!ts) continue
        const isSpace = !!row?.is_space
        const isNew = !!row?.is_new
        if (isSpace && isNew) map[ts] = '空间+刚启动'
        else if (isSpace) map[ts] = '空间龙头'
        else if (isNew) map[ts] = '刚启动'
      }
      leaderTypeBySymbol.value = map
      try {
        window.localStorage.setItem(LEADER_TYPE_CACHE_KEY, JSON.stringify(map || {}))
      } catch {
        // ignore localStorage write errors
      }
      return
    }

    // 如果持久池接口失败，回退到原本的 sector-strength 口径
    const query2 = 'min_score=60&stable=true'
    const relUrl2 = `/api/startup/sector-strength?${query2}`
    const absUrl2 = `${API_BASE_URL}/api/startup/sector-strength?${query2}`

    let res = null
    try {
      res = await fetch(relUrl2).then((r) => r.json())
    } catch {
      res = await fetch(absUrl2).then((r) => r.json())
    }

    if (!res?.success) {
      leaderTypeBySymbol.value = {}
      return
    }

    const spaceCodes = new Set()
    for (const item of res.space_leaders_lead || []) {
      for (const s of item.stocks || []) {
        if (s.ts_code) spaceCodes.add(s.ts_code)
      }
    }
    const newCodes = new Set()
    for (const s of res.sectors || []) {
      for (const c of s.chain || []) {
        if (c.is_new_leader && c.ts_code) newCodes.add(c.ts_code)
      }
    }

    const map = {}
    for (const ts of spaceCodes) {
      map[ts] = newCodes.has(ts) ? '空间+刚启动' : '空间龙头'
    }
    for (const ts of newCodes) {
      if (!map[ts]) map[ts] = '刚启动'
    }
    leaderTypeBySymbol.value = map
    try {
      window.localStorage.setItem(LEADER_TYPE_CACHE_KEY, JSON.stringify(map || {}))
    } catch {
      // ignore localStorage write errors
    }
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error('fetchLeaderTypes 失败:', e)
    leaderTypeBySymbol.value = prevMap
  }
}

const getLeaderTypeLabel = (symbol) => {
  if (!symbol) return null
  const map = leaderTypeBySymbol.value || {}
  if (map[symbol]) return map[symbol]
  const bare = String(symbol).replace(/\.(SH|SZ|BJ)$/i, '')
  if (bare.length === 6) {
    return map[bare + '.SH'] || map[bare + '.SZ'] || map[bare + '.BJ'] || null
  }
  return null
}

const handleRefresh = () => {
  if (activeTab.value === 'current') {
    fetchHoldings(true)
  } else {
    fetchHistory()
  }
}

// 获取历史持仓
const fetchHistory = async () => {
  historyLoading.value = true
  try {
    const response = await fetch(`${API_BASE_URL}/api/holdings/history`)
    const result = await response.json()
    if (result.success) {
      historyHoldings.value = result.data || []
      historyCount.value = result.count || 0
      historyWinRate.value = result.summary?.win_rate ?? (result.win_rate ?? 0)
    }
  } catch (error) {
    console.error('获取历史持仓失败:', error)
  } finally {
    historyLoading.value = false
  }
}

// 计算持有天数
const calcHoldingDays = (buyDate, closeDate) => {
  if (!buyDate || !closeDate) return 0
  const buy = new Date(buyDate)
  const close = new Date(closeDate)
  return Math.ceil((close - buy) / (1000 * 60 * 60 * 24))
}

// 打开历史持仓编辑对话框
const openHistoryEditDialog = (h) => {
  editingHistory.value = h
  historyEditForm.value = {
    close_price: h.close_price || 0,
    close_date: h.close_date || new Date().toISOString().split('T')[0],
    total_quantity: h.total_quantity ?? 0
  }
  showHistoryEditDialog.value = true
}

// 确认历史持仓编辑
const handleConfirmHistoryEdit = async () => {
  if (!editingHistory.value) return
  if (!historyEditForm.value.close_price || historyEditForm.value.close_price <= 0) {
    alert('请输入有效的清仓价格')
    return
  }
  if (!historyEditForm.value.total_quantity || historyEditForm.value.total_quantity <= 0) {
    alert('请输入有效的清仓数量')
    return
  }
  try {
    const response = await fetch(`${API_BASE_URL}/api/holdings/${editingHistory.value.id}/update-close`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(historyEditForm.value)
    })
    const result = await response.json()
    if (result.success) {
      showHistoryEditDialog.value = false
      fetchHistory()
    } else {
      alert('修改失败: ' + (result.detail || '未知错误'))
    }
  } catch (error) {
    console.error('修改失败:', error)
    alert('修改失败')
  }
}

// 监听全局刷新事件
const handleGlobalRefresh = () => {
  fetchHoldings(true)
}

const handleUpdate = () => {
  fetchHoldings()
}

// 静默刷新价格数据（不触发loading，不重建列表）
const refreshPriceData = async () => {
  const list = Array.isArray(holdings.value) ? holdings.value : []
  if (list.length === 0) return
  
  try {
    const res = await stockApi.getHoldings(selectedBoardType.value).catch(() => ({ data: [] }))
    const data = Array.isArray(res.data) ? res.data : (res.data || [])
    if (data.length > 0) {
      // 只更新价格相关字段，保持列表引用不变
      data.forEach(newItem => {
        const existing = list.find(h => h.id === newItem.id)
        if (existing) {
          existing.current_price = newItem.current_price
          existing.profit_rate = newItem.profit_rate
          existing.profit_amount = newItem.profit_amount
          existing.market_value = newItem.market_value
          existing.today_profit = newItem.today_profit
          existing.change_pct = newItem.change_pct
        }
      })
    }
  } catch (error) {
    console.error('刷新价格失败:', error)
  }
}

const handleDelete = async (holding) => {
  // 弹窗让用户输入清仓价格
  const defaultPrice = holding.current_price || holding.avg_cost_price || 0
  const inputPrice = prompt(
    `确定要将 ${holding.name || holding.symbol} 移出操作池吗？\n\n请输入清仓价格（用于计算盈亏）：`,
    defaultPrice.toFixed(2)
  )
  
  if (inputPrice === null) return // 用户取消
  
  const closePrice = parseFloat(inputPrice)
  if (isNaN(closePrice) || closePrice <= 0) {
    alert('请输入有效的清仓价格')
    return
  }
  
  try {
    const response = await fetch(`${API_BASE_URL}/api/holdings/${holding.id}?close_price=${closePrice}`, { method: 'DELETE' })
    const result = await response.json()
    if (result.success) {
      fetchHoldings(true)
    } else {
      alert('清仓失败')
    }
  } catch (error) {
    console.error('清仓失败:', error)
    alert('清仓失败')
  }
}

const formatAmount = (amount) => {
  if (amount >= 100000000) {
    return `${(amount / 100000000).toFixed(2)}亿`
  } else if (amount >= 10000) {
    return `${(amount / 10000).toFixed(2)}万`
  }
  return amount.toFixed(2)
}

// 列表配置
const actionLabels = { buy: '买入', add: '加仓', hold: '持有', reduce: '减仓', close: '止损', skip: '跳过' }
const actionBadgeColors = {
  buy: 'bg-green-100 text-green-700', add: 'bg-blue-100 text-blue-700', hold: 'bg-gray-100 text-gray-700',
  reduce: 'bg-yellow-100 text-yellow-700', close: 'bg-red-100 text-red-700', skip: 'bg-gray-100 text-gray-700'
}
const riskLabels = { low: '低', medium: '中', high: '高' }
const riskBadgeColors = { low: 'bg-green-100 text-green-700', medium: 'bg-yellow-100 text-yellow-700', high: 'bg-red-100 text-red-700' }
const recoveryBadgeColors = { high: 'bg-green-100 text-green-700', medium: 'bg-yellow-100 text-yellow-700', low: 'bg-red-100 text-red-700', none: 'bg-gray-100 text-gray-700' }
const strengthBadgeClass = (level) => {
  if (level === '强') return 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200/60'
  if (level === '中') return 'bg-amber-50 text-amber-700 ring-1 ring-amber-200/60'
  if (level === '弱') return 'bg-slate-50 text-slate-600 ring-1 ring-slate-200/60'
  return 'bg-gray-50 text-gray-600'
}

// 格式化回涨分析tooltip
const formatRecoveryTooltip = (analysis) => {
  if (!analysis) return '暂无分析'
  let text = `回涨概率：${analysis.recovery_probability?.toFixed(0) || 0}%。`
  if (analysis.recovery_reasons?.length) {
    text += `有利因素：${analysis.recovery_reasons.join('；')}。`
  }
  if (analysis.risk_factors?.length) {
    text += `风险因素：${analysis.risk_factors.join('；')}`
  }
  return text
}

// AI 综合建议：更新时间显示
const formatAiSuggestionsTime = (updatedAt) => {
  if (!updatedAt) return ''
  const d = new Date(updatedAt)
  if (isNaN(d.getTime())) return updatedAt
  const now = new Date()
  const diff = Math.floor((now - d) / 60000)
  if (diff < 1) return '刚刚'
  if (diff < 5) return `${diff} 分钟前`
  return d.toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

// AI 综合建议：操作标签样式（加仓/减仓/清仓/持有）
const aiActionClass = (action) => {
  const map = {
    加仓: 'bg-green-100 text-green-700',
    减仓: 'bg-yellow-100 text-yellow-700',
    清仓: 'bg-red-100 text-red-700',
    持有: 'bg-slate-100 text-slate-600'
  }
  return map[action] || 'bg-gray-100 text-gray-600'
}

// 手动刷新 AI 建议（带 10 秒冷却）
const refreshAiSuggestions = async () => {
  if (aiRefreshCooldown.value > 0 || aiRefreshLoading.value) return

  aiRefreshLoading.value = true
  try {
    const result = await stockApi.refreshAiSuggestions()
    if (result.success) {
      // 重新加载持仓以获取最新 AI 建议
      await fetchHoldings(true)
      // 开始 10 秒冷却
      aiRefreshCooldown.value = 10
      startAiRefreshCooldown()
    }
  } catch (e) {
    console.error('刷新 AI 建议失败:', e)
    alert(e.message || '刷新 AI 建议失败，请稍后重试')
  } finally {
    aiRefreshLoading.value = false
  }
}

// 启动 AI 刷新冷却计时器
const startAiRefreshCooldown = () => {
  if (aiRefreshTimer) clearInterval(aiRefreshTimer)
  aiRefreshTimer = setInterval(() => {
    aiRefreshCooldown.value--
    if (aiRefreshCooldown.value <= 0) {
      clearInterval(aiRefreshTimer)
      aiRefreshTimer = null
    }
  }, 1000)
}

// 编辑对话框
const showEditDialog = ref(false)
const editingHolding = ref(null)
const editForm = ref({ symbol: '', name: '', avg_cost_price: 0, total_quantity: 0, buy_date: '' })

// 加仓对话框
const showAddPositionDialog = ref(false)
const addPositionForm = ref({ price: 0, quantity: 0 })

// 减仓对话框
const showReducePositionDialog = ref(false)
const reducePositionForm = ref({ price: 0, quantity: 0 })

const openEditDialog = (holding) => {
  editingHolding.value = holding
  editForm.value = { 
    symbol: holding.symbol || '',
    name: holding.name || '',
    avg_cost_price: holding.avg_cost_price, 
    total_quantity: holding.total_quantity,
    buy_date: holding.buy_date ? (holding.buy_date.slice ? holding.buy_date.slice(0, 10) : holding.buy_date) : ''
  }
  showEditDialog.value = true
}

// 打开加仓对话框
const openAddPositionDialog = (holding) => {
  editingHolding.value = holding
  addPositionForm.value = {
    price: holding.current_price || 0,
    quantity: 0
  }
  showAddPositionDialog.value = true
}

// 打开减仓对话框
const openReducePositionDialog = (holding) => {
  editingHolding.value = holding
  reducePositionForm.value = {
    price: holding.current_price || 0,
    quantity: 0
  }
  showReducePositionDialog.value = true
}

// 计算加仓后的新成本
const calculateNewCost = (holding, newPrice, newQuantity) => {
  if (!holding) return 0
  const oldTotal = holding.total_quantity || 0
  const oldCost = holding.avg_cost_price || 0
  const newTotal = oldTotal + newQuantity
  if (newTotal > 0) {
    return (oldTotal * oldCost + newQuantity * newPrice) / newTotal
  }
  return oldCost
}

// 计算减仓盈亏
const calculateReduceProfit = (holding, sellPrice, sellQuantity) => {
  if (!holding) return 0
  const cost = holding.avg_cost_price || 0
  return (sellPrice - cost) * sellQuantity
}

// 确认加仓
const handleConfirmAddPosition = async () => {
  if (!editingHolding.value) return
  
  if (!addPositionForm.value.price || addPositionForm.value.price <= 0) {
    alert('请输入有效的买入价格')
    return
  }
  
  if (!addPositionForm.value.quantity || addPositionForm.value.quantity <= 0) {
    alert('请输入有效的买入数量')
    return
  }
  
  try {
    const response = await fetch(`${API_BASE_URL}/api/holdings/${editingHolding.value.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        op_type: 'buy',
        price: addPositionForm.value.price,
        quantity: addPositionForm.value.quantity
      })
    })
    const result = await response.json()
    if (result.success) {
      showAddPositionDialog.value = false
      addPositionForm.value = { price: 0, quantity: 0 }
      alert('加仓成功')
      fetchHoldings(true)
    } else {
      alert('加仓失败: ' + (result.detail || '未知错误'))
    }
  } catch (error) {
    console.error('加仓失败:', error)
    alert('加仓失败')
  }
}

// 确认减仓
const handleConfirmReducePosition = async () => {
  if (!editingHolding.value) return
  
  if (!reducePositionForm.value.quantity || reducePositionForm.value.quantity <= 0) {
    alert('请输入有效的卖出数量')
    return
  }
  
  if (reducePositionForm.value.quantity > (editingHolding.value.total_quantity || 0)) {
    alert('卖出数量不能超过当前持仓')
    return
  }

  if (!reducePositionForm.value.price || reducePositionForm.value.price <= 0) {
    alert('请输入卖出价格，用于正确计算盈亏')
    return
  }
  
  try {
    const response = await fetch(`${API_BASE_URL}/api/holdings/${editingHolding.value.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        op_type: 'sell',
        price: reducePositionForm.value.price,
        quantity: reducePositionForm.value.quantity
      })
    })
    const result = await response.json()
    if (result.success) {
      showReducePositionDialog.value = false
      reducePositionForm.value = { price: 0, quantity: 0 }
      alert('减仓成功')
      fetchHoldings(true)
    } else {
      alert('减仓失败: ' + (result.detail || '未知错误'))
    }
  } catch (error) {
    console.error('减仓失败:', error)
    alert('减仓失败')
  }
}

const handleConfirmEdit = async () => {
  if (!editForm.value.name || !editForm.value.name.trim()) {
    alert('请输入股票名称')
    return
  }
  try {
    const payload = { op_type: 'edit', name: editForm.value.name, price: editForm.value.avg_cost_price, quantity: editForm.value.total_quantity, buy_date: editForm.value.buy_date }
    if (editForm.value.symbol !== undefined && editForm.value.symbol !== null && String(editForm.value.symbol).trim() !== '') {
      payload.symbol = String(editForm.value.symbol).trim()
    }
    const response = await fetch(`${API_BASE_URL}/api/holdings/${editingHolding.value.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    const result = await response.json()
    if (result.success) {
      showEditDialog.value = false
      fetchHoldings(true)
    } else {
      alert('编辑失败')
    }
  } catch (error) {
    console.error('编辑失败:', error)
    alert('编辑失败')
  }
}

// 添加股票相关
const showAddStockDialog = ref(false)
const addMode = ref('search')  // 'search' | 'image'
const stockSearchQuery = ref('')
const stockSearchResults = ref([])
const stockSearchLoading = ref(false)
const selectedStock = ref(null)
const imageFileInput = ref(null)
const imageParseRecords = ref([])
const imageParseLoading = ref(false)
const imageParseError = ref('')
const bypassTradingRules = ref(false)  // 是否绕过交易规则
const addStockForm = ref({
  board_type: 'other',
  buy_price: null,
  quantity: null,
  buy_date: new Date().toISOString().split('T')[0] // 默认今天
})

// 搜索股票（从全量股票表）
const searchStocks = async () => {
  if (!stockSearchQuery.value || stockSearchQuery.value.length < 1) {
    stockSearchResults.value = []
    return
  }
  
  stockSearchLoading.value = true
  try {
    // 从dim_stock全量表搜索
    const response = await fetch(`${API_BASE_URL}/api/watchlist/search?keyword=${encodeURIComponent(stockSearchQuery.value)}`)
    const result = await response.json()
    
    if (result.success && result.data) {
      stockSearchResults.value = result.data.map(stock => ({
        code: stock.code,
        ts_code: stock.ts_code,
        name: stock.name
      }))
    }
  } catch (error) {
    console.error('搜索股票失败:', error)
    stockSearchResults.value = []
  } finally {
    stockSearchLoading.value = false
  }
}

// 选择股票
const selectStock = (stock) => {
  selectedStock.value = stock
  addStockForm.value.buy_price = stock.current_price || stock.close || stock.price || null
  stockSearchQuery.value = stock.name || stock.名称 || ''
  stockSearchResults.value = []
}

// 隐藏搜索结果
const hideSearchResults = () => {
  setTimeout(() => {
    stockSearchResults.value = []
  }, 150)
}

// 关闭添加弹窗
const closeAddDialog = () => {
  showAddStockDialog.value = false
  addMode.value = 'search'
  selectedStock.value = null
  stockSearchQuery.value = ''
  stockSearchResults.value = []
  imageParseRecords.value = []
  imageParseError.value = ''
}

// 选择图片并识别
const handleImageFileSelect = async (e) => {
  const file = e.target?.files?.[0]
  if (!file || !file.type.startsWith('image/')) {
    imageParseError.value = '请选择图片文件'
    return
  }
  imageParseError.value = ''
  imageParseLoading.value = true
  imageParseRecords.value = []
  try {
    const formData = new FormData()
    formData.append('file', file)
    const resp = await fetch(`${API_BASE_URL}/api/holdings/parse-buy-image`, {
      method: 'POST',
      body: formData
    })
    const result = await resp.json().catch(() => ({}))
    if (result.success && Array.isArray(result.records)) {
      imageParseRecords.value = result.records.map(r => ({ ...r, checked: true }))
      imageParseError.value = ''
    } else {
      const msg = result.detail || result.message || '识别失败，请重试'
      imageParseError.value = msg
      if (/timeout|timed out|超时/i.test(msg)) {
        imageParseError.value += '（智谱接口较慢，可稍后重试或换一张图）'
      }
    }
  } catch (err) {
    console.error('图片识别失败:', err)
    const isNetworkErr = err?.message?.includes('Failed to fetch') || err?.message?.includes('NetworkError')
    imageParseError.value = isNetworkErr
      ? `请求本系统后端失败（${API_BASE_URL ? API_BASE_URL + ' ' : '相对路径（需 Vite 代理）'} /api/holdings/parse-buy-image）。请确认：1) 后端已启动（默认 http://localhost:8000）；2) 若未用 Vite 代理，在项目根 .env 中设置 VITE_API_BASE_URL=http://localhost:8000 并重启前端`
      : '识别失败，请重试'
  } finally {
    imageParseLoading.value = false
    e.target.value = ''
  }
}

// 批量加入（从图片识别的记录）
const handleBatchAddFromImage = async () => {
  const toAdd = imageParseRecords.value.filter(r => r.checked)
  if (!toAdd.length) return
  const today = new Date().toISOString().split('T')[0]
  let ok = 0
  let fail = 0
  const errors = []
  for (const r of toAdd) {
    try {
      const resp = await fetch(`${API_BASE_URL}/api/holdings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: r.code,
          name: r.name || r.code,
          board_type: addStockForm.value.board_type,
          buy_price: r.buy_price,
          quantity: r.quantity,
          buy_date: today,
          bypass_trading_rules: true
        })
      })
      const result = await resp.json().catch((e) => ({ error: e.message }))
      if (resp.ok && result.success) {
        ok++
      } else {
        fail++
        const errMsg = result.detail || result.message || result.error || `HTTP ${resp.status}`
        errors.push(`${r.name || r.code}: ${errMsg}`)
        console.error(`批量添加失败 ${r.code}:`, result)
      }
    } catch (e) {
      fail++
      errors.push(`${r.name || r.code}: ${e.message || '请求失败'}`)
      console.error(`批量添加异常 ${r.code}:`, e)
    }
  }
  if (ok > 0) {
    const errorMsg = fail > 0 ? `\n\n失败详情:\n${errors.slice(0, 5).join('\n')}${errors.length > 5 ? '\n...' : ''}` : ''
    alert(`成功加入 ${ok} 只${fail > 0 ? `，${fail} 只失败` : ''}${errorMsg}`)
    fetchHoldings(true)
    imageParseRecords.value = imageParseRecords.value.filter(r => !r.checked)
    if (imageParseRecords.value.length === 0) closeAddDialog()
  } else {
    alert(`加入失败:\n${errors.slice(0, 5).join('\n')}${errors.length > 5 ? '\n...' : ''}`)
  }
}

// 确认添加股票
const handleConfirmAddStock = async () => {
  if (!selectedStock.value) {
    alert('请先选择股票')
    return
  }
  
  try {
    const response = await fetch(`${API_BASE_URL}/api/holdings`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        symbol: selectedStock.value.code || selectedStock.value.ts_code || selectedStock.value.代码,
        name: selectedStock.value.name || selectedStock.value.名称,
        board_type: addStockForm.value.board_type,
        buy_price: addStockForm.value.buy_price,
        quantity: addStockForm.value.quantity,
        buy_date: addStockForm.value.buy_date,
      bypass_trading_rules: true
      })
    })
    
    const result = await response.json().catch(() => ({}))
    
    if (response.ok && result.success) {
      showAddStockDialog.value = false
      selectedStock.value = null
      stockSearchQuery.value = ''
      stockSearchResults.value = []
      alert('已加入操作池')
      fetchHoldings(true)
    } else {
      const msg = result.detail || result.message || '加入失败，请重试'
      alert(msg)
      if (response.status === 400) fetchHoldings(true)
    }
  } catch (error) {
    console.error('加入操作池失败:', error)
    alert('加入失败，请重试')
  }
}

// 自动刷新定时器
let refreshTimer = null

// 判断是否交易时间
const isTradingHours = () => {
  const now = new Date()
  const day = now.getDay()
  if (day === 0 || day === 6) return false // 周末
  const h = now.getHours()
  const m = now.getMinutes()
  const time = h * 60 + m
  // 9:30-11:30, 13:00-15:00
  return (time >= 570 && time <= 690) || (time >= 780 && time <= 900)
}

onMounted(() => {
  // 先尝试使用缓存，如果没有缓存再加载
  fetchHoldings(false)
  window.addEventListener('global-refresh', handleGlobalRefresh)
  
  // 每 60 秒静默刷新价格（只在交易时间刷新），避免频繁请求 /api/holdings
  refreshTimer = setInterval(() => {
    if (isTradingHours()) {
      refreshPriceData()
    }
  }, 60000)
})

onUnmounted(() => {
  window.removeEventListener('global-refresh', handleGlobalRefresh)
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
  if (aiRefreshTimer) {
    clearInterval(aiRefreshTimer)
    aiRefreshTimer = null
  }
})
</script>

