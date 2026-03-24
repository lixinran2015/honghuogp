<template>
  <div class="container mx-auto px-4 py-6">
    <!-- 页面标题 -->
    <div class="mb-6">
      <h1 class="text-2xl font-bold text-gray-800">AI智能推荐股票池</h1>
      <p class="text-sm text-gray-500 mt-1">七维评分 + AI精选，专业风控建议</p>
    </div>

    <!-- 当前主线 -->
    <div class="rounded-lg border border-gray-200 bg-white shadow-sm overflow-hidden mb-6">
      <div class="px-4 py-3 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
        <h2 class="text-sm font-semibold text-gray-800">当前主线</h2>
        <button
          @click="fetchMainline"
          :disabled="mainlineLoading"
          class="text-xs text-blue-600 hover:underline disabled:opacity-50"
        >
          {{ mainlineLoading ? '加载中...' : '刷新' }}
        </button>
      </div>
      <div v-if="mainlineLoading && !mainlineData?.mainline?.length" class="p-6 text-center text-gray-500 text-sm">
        加载中...
      </div>
      <div v-else-if="mainlineError" class="p-6 text-center">
        <p class="text-red-600 text-sm">{{ mainlineError }}</p>
        <button @click="fetchMainline" class="mt-2 text-xs text-blue-600 hover:underline">重试</button>
      </div>
      <div v-else-if="!mainlineData?.mainline?.length" class="p-6 text-center text-gray-500 text-sm">
        <p>暂无主线数据，可能因数据更新中</p>
        <router-link to="/sector-board-leaders" class="mt-2 inline-block text-blue-600 hover:underline text-xs">
          查看板块领涨
        </router-link>
      </div>
      <div v-else class="p-4">
        <div class="flex flex-wrap gap-3">
          <router-link
            v-for="(m, idx) in mainlineData.mainline.slice(0, 5)"
            :key="m.sector_id || idx"
            :to="{ path: '/sector-board-leaders', query: { sector: m.sector_name } }"
            class="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-100 hover:bg-gray-200 text-sm transition-colors"
          >
            <span class="font-medium text-gray-900">{{ m.sector_name }}</span>
            <span
              v-if="m.signals?.momentum_5d != null"
              class="text-red-600 text-xs"
            >
              5日{{ m.signals.momentum_5d > 0 ? '+' : '' }}{{ m.signals.momentum_5d }}%
            </span>
            <span v-if="m.leader_stock" class="text-gray-500 text-xs">龙头: {{ m.leader_stock }}</span>
          </router-link>
        </div>
        <p class="mt-3 text-xs text-gray-400">
          基于近5日涨幅、龙头涨停数、成交额等综合计算。仅供参考，不构成投资建议。
        </p>
      </div>
    </div>

    <!-- 进入推荐池规则（可展开/收起） -->
    <div class="bg-amber-50 border border-amber-200 rounded-lg mb-6 overflow-hidden">
      <button
        type="button"
        @click="rulesExpanded = !rulesExpanded"
        class="w-full flex items-center justify-between px-4 py-3 text-left text-sm font-medium text-amber-900 hover:bg-amber-100 transition-colors"
      >
        <span>📋 进入推荐池的规则</span>
        <span class="text-amber-600">{{ rulesExpanded ? '▲ 收起' : '▼ 展开' }}</span>
      </button>
      <div v-show="rulesExpanded" class="px-4 pb-4 text-sm text-gray-700 space-y-4">
        <p class="text-amber-800 font-medium">按以下步骤筛选，最终总分 ≥ 75 分即进入推荐池。</p>

        <ul class="list-decimal list-inside space-y-2 text-gray-700 ml-1">
          <li><strong>筛选条件：</strong>阶段为「启动确认」或「完全启动」</li>
          <li><strong>排除：</strong>跟风股（只保留龙头 / 追赶型）</li>
          <li><strong>主题轮动：</strong>领涨板块内股票加 5 分</li>
          <li><strong>七维评分：</strong>技术面、龙头、资金流、板块周期、基本面、情绪、时机</li>
          <li><strong>入池：</strong>总分 ≥ 75 分即进入推荐池（不按日期限流，同一天多只达标则多只入池）</li>
          <li><strong>AI 精选：</strong>新入池的股票再经 AI 筛选，选中的标「AI精选」标签，未选中的无该标签</li>
        </ul>

        <div class="pt-2 border-t border-amber-200 text-gray-600">
          <span class="font-medium text-gray-700">说明：</span>
          5日涨跌 vs 预期：|5日−预期|≤5% 符合；≥+5% 超预期；≥+10% 超超预期
        </div>
      </div>
    </div>

    <!-- 市场环境面板 -->
    <div class="bg-white rounded-lg shadow p-4 mb-6">
      <div class="flex items-center justify-between">
        <div class="flex items-center space-x-8">
          <!-- 大盘趋势 -->
          <div class="text-center">
            <div class="text-xs text-gray-500 mb-1">大盘趋势</div>
            <div class="flex items-center space-x-1">
              <span :class="trendClass(marketEnv.market_trend)" class="text-lg font-bold">
                {{ trendLabel(marketEnv.market_trend) }}
              </span>
              <span class="text-xs text-gray-400">({{ marketEnv.trend_strength }})</span>
            </div>
          </div>
          
          <!-- 情绪指数 -->
          <div class="text-center">
            <div class="text-xs text-gray-500 mb-1">市场情绪</div>
            <div class="flex items-center space-x-1">
              <span :class="emotionClass(marketEnv.emotion_label)" class="text-lg font-bold">
                {{ marketEnv.emotion_label || '中性' }}
              </span>
              <span class="text-xs text-gray-400">({{ marketEnv.emotion_index }})</span>
            </div>
          </div>
          
          <!-- 涨跌比 -->
          <div class="text-center">
            <div class="text-xs text-gray-500 mb-1">涨跌比</div>
            <div class="text-lg font-bold text-gray-700">{{ marketEnv.up_down_ratio?.toFixed(2) || '--' }}</div>
          </div>
          
          <!-- 涨停/跌停 -->
          <div class="text-center">
            <div class="text-xs text-gray-500 mb-1">涨停/跌停</div>
            <div class="text-lg font-bold">
              <span class="text-red-600">{{ marketEnv.limit_up_count || 0 }}</span>
              <span class="text-gray-400">/</span>
              <span class="text-green-600">{{ marketEnv.limit_down_count || 0 }}</span>
            </div>
          </div>
          
          <!-- 北向资金 -->
          <div class="text-center">
            <div class="text-xs text-gray-500 mb-1">北向资金</div>
            <div class="text-lg font-bold" :class="marketEnv.north_flow >= 0 ? 'text-red-600' : 'text-green-600'">
              {{ marketEnv.north_flow >= 0 ? '+' : '' }}{{ marketEnv.north_flow?.toFixed(1) || 0 }}亿
            </div>
          </div>
        </div>
        
        <div class="flex items-center gap-2">
          <span class="text-xs text-gray-400">数据更新:</span>
          <button
            @click="triggerDataUpdate('daily_update')"
            :disabled="updateTriggering"
            class="px-2 py-1 text-xs rounded border border-gray-300 hover:bg-gray-50 disabled:opacity-50"
            title="更新日线数据，影响大盘趋势、涨跌比"
          >
            {{ updateTriggering === 'daily_update' ? '执行中...' : '日线' }}
          </button>
          <button
            @click="triggerDataUpdate('north_flow_update')"
            :disabled="updateTriggering"
            class="px-2 py-1 text-xs rounded border border-gray-300 hover:bg-gray-50 disabled:opacity-50"
            title="更新北向资金净流入"
          >
            {{ updateTriggering === 'north_flow_update' ? '执行中...' : '北向' }}
          </button>
          <button @click="loadMarketEnv" class="px-3 py-1 text-sm text-blue-600 hover:text-blue-800">
            刷新
          </button>
        </div>
      </div>
    </div>

    <!-- 历史表现统计 -->
    <div class="bg-gradient-to-r from-blue-50 to-purple-50 rounded-lg shadow p-4 mb-6">
      <div class="flex items-center justify-between mb-2">
        <h2 class="text-sm font-semibold text-gray-700">AI推荐历史表现（近{{ performanceDays }}天）</h2>
        <select v-model="performanceDays" @change="loadPerformance" class="text-xs border rounded px-2 py-1">
          <option :value="7">近7天</option>
          <option :value="30">近30天</option>
          <option :value="90">近90天</option>
        </select>
      </div>
      
      <div class="grid grid-cols-6 gap-4">
        <div class="text-center">
          <div class="text-2xl font-bold text-blue-600">{{ performance.win_rate || 0 }}%</div>
          <div class="text-xs text-gray-500">胜率</div>
        </div>
        <div class="text-center">
          <div class="text-2xl font-bold" :class="performance.avg_return >= 0 ? 'text-red-600' : 'text-green-600'">
            {{ performance.avg_return >= 0 ? '+' : '' }}{{ performance.avg_return || 0 }}%
          </div>
          <div class="text-xs text-gray-500">平均收益</div>
        </div>
        <div class="text-center">
          <div class="text-2xl font-bold text-purple-600">{{ performance.profit_factor || 0 }}</div>
          <div class="text-xs text-gray-500">盈亏比</div>
        </div>
        <div class="text-center">
          <div class="text-2xl font-bold text-gray-700">{{ performance.total_recommendations || 0 }}</div>
          <div class="text-xs text-gray-500">总推荐</div>
        </div>
        <div class="text-center">
          <div class="text-2xl font-bold text-green-600">{{ performance.win_count || 0 }}</div>
          <div class="text-xs text-gray-500">盈利</div>
        </div>
        <div class="text-center">
          <div class="text-2xl font-bold text-red-600">{{ performance.loss_count || 0 }}</div>
          <div class="text-xs text-gray-500">亏损</div>
        </div>
      </div>
      
      <div class="mt-2 text-xs text-gray-400 text-center">
        触达目标: {{ performance.hit_target_rate || 0 }}% | 触及止损: {{ performance.hit_stop_loss_rate || 0 }}%
      </div>
    </div>

    <!-- 控制面板 -->
    <div class="bg-white rounded-lg shadow p-4 mb-6">
      <div class="flex items-center justify-between">
        <div class="flex items-center space-x-4">
          <!-- 策略选择 -->
          <div class="flex items-center space-x-2">
            <label class="text-sm text-gray-700">策略</label>
            <select v-model="strategy" class="px-3 py-2 border border-gray-300 rounded text-sm">
              <option value="aggressive">短线激进</option>
              <option value="balanced">均衡</option>
              <option value="defensive">防守</option>
            </select>
          </div>

          <!-- 查询天数 -->
          <div class="flex items-center space-x-2">
            <label class="text-sm text-gray-700">最近</label>
            <input v-model="queryDays" type="number" min="1" max="90" class="px-3 py-2 border border-gray-300 rounded w-16 text-sm text-center" />
            <span class="text-sm text-gray-700">天</span>
          </div>

          <!-- 状态筛选 -->
          <div class="flex items-center space-x-2">
            <label class="text-sm text-gray-700">状态</label>
            <select v-model="statusFilter" class="px-3 py-2 border border-gray-300 rounded text-sm">
              <option value="">全部</option>
              <option value="active">活跃中</option>
              <option value="closed">跟踪结束</option>
              <option value="stopped">已止损</option>
            </select>
          </div>

          <!-- 最低预期收益 -->
          <div class="flex items-center space-x-2">
            <label class="text-sm text-gray-700">预期</label>
            <select v-model="minExpectedReturn" @change="loadRecommendations" class="px-3 py-2 border border-gray-300 rounded text-sm">
              <option :value="null">全部</option>
              <option :value="10">≥10%</option>
              <option :value="20">≥20%</option>
              <option :value="30">≥30%</option>
            </select>
          </div>

          <!-- 查询按钮 -->
          <button @click="loadRecommendations" :disabled="loading" class="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 text-sm">
            {{ loading ? '加载中...' : '查询' }}
          </button>
        </div>

        <div class="flex items-center space-x-3">
          <!-- AI精选（与刷新同一流程：入池后对新入池股票打「AI精选」标签） -->
          <button @click="triggerAISelect" :disabled="refreshing" class="px-6 py-2 bg-gradient-to-r from-purple-600 to-blue-600 text-white rounded-lg hover:from-purple-700 hover:to-blue-700 disabled:opacity-50 text-sm font-semibold shadow-lg">
            {{ refreshing ? '刷新中...' : '🤖 刷新并AI精选' }}
          </button>
          
          <!-- 刷新推荐（与上方同一流程，仅入口不同） -->
          <button @click="refreshRecommendations" :disabled="refreshing" class="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50 text-sm">
            {{ refreshing ? '刷新中...' : '🔄 刷新' }}
          </button>

          <!-- 回填追踪（补齐 5日/10日收益） -->
          <button @click="triggerTrackBackfill" :disabled="backfilling" class="px-4 py-2 bg-amber-600 text-white rounded hover:bg-amber-700 disabled:opacity-50 text-sm" title="回填历史追踪记录，使 5日收益、10日收益 有数据">
            {{ backfilling ? '回填中...' : '📊 回填追踪' }}
          </button>
          
          <!-- 清空数据 -->
          <button @click="clearAllRecommendations" class="px-4 py-2 bg-gray-500 text-white rounded hover:bg-gray-600 text-sm">
            🗑️ 清空
          </button>
        </div>
      </div>
    </div>

    <!-- AI精选结果 -->
    <div v-if="aiResult && aiResult.selected && aiResult.selected.length > 0" class="mb-6">
      <h2 class="text-lg font-semibold text-gray-800 mb-3">🤖 AI精选推荐</h2>
      
      <!-- 市场观点 -->
      <div v-if="aiResult.market_view" class="bg-blue-50 border border-blue-200 rounded-lg p-3 mb-4 text-sm text-blue-800">
        📊 {{ aiResult.market_view }}
      </div>
      
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div v-for="stock in aiResult.selected" :key="stock.ts_code" class="bg-white rounded-lg shadow-lg border-2 border-purple-200 overflow-hidden">
          <!-- 卡片头部 -->
          <div class="bg-gradient-to-r from-purple-500 to-blue-500 px-4 py-2 text-white">
            <div class="flex items-center justify-between">
              <div>
                <span class="font-bold">{{ stock.name }}</span>
                <span class="text-purple-200 text-sm ml-2">({{ stock.ts_code }})</span>
              </div>
              <span class="px-2 py-1 bg-white/20 rounded text-sm">{{ stock.recommend_level }}</span>
            </div>
          </div>
          
          <!-- 标签 -->
          <div class="px-4 py-2 bg-gray-50 border-b">
            <div class="flex flex-wrap gap-1">
              <span
                v-for="tag in (stock.recommend_tags || []).filter(t => t === 'AI精选')"
                :key="'ai-'+tag"
                class="px-2 py-0.5 bg-purple-200 text-purple-800 rounded text-xs font-medium"
              >{{ tag }}</span>
              <span
                v-for="tag in (stock.recommend_tags || []).filter(t => t !== 'AI精选').slice(0, 3)"
                :key="tag"
                class="px-2 py-0.5 bg-blue-100 text-blue-700 rounded text-xs"
              >{{ tag }}</span>
            </div>
          </div>
          
          <!-- 推荐理由 -->
          <div class="px-4 py-3">
            <div class="text-xs text-gray-500 mb-1">推荐理由</div>
            <ul class="text-sm space-y-1">
              <li v-for="(reason, idx) in stock.buy_reason" :key="idx" class="flex items-start">
                <span class="text-green-500 mr-1">✓</span>
                <span>{{ reason }}</span>
              </li>
            </ul>
          </div>
          
          <!-- 风控建议 -->
          <div class="px-4 py-3 bg-gray-50">
            <div class="text-xs text-gray-500 mb-2">风控建议</div>
            <div class="grid grid-cols-2 gap-2 text-sm">
              <div>
                <span class="text-gray-500">买入价:</span>
                <span class="font-semibold ml-1">¥{{ stock.entry_price?.toFixed(2) }}</span>
              </div>
              <div>
                <span class="text-gray-500">止损:</span>
                <span class="font-semibold text-green-600 ml-1">¥{{ stock.stop_loss_price?.toFixed(2) }} ({{ stock.stop_loss_pct != null ? stock.stop_loss_pct + '%' : '--' }})</span>
              </div>
              <div>
                <span class="text-gray-500">目标1:</span>
                <span class="font-semibold text-red-600 ml-1">¥{{ stock.target_price_1?.toFixed(2) }}</span>
              </div>
              <div>
                <span class="text-gray-500">目标2:</span>
                <span class="font-semibold text-red-600 ml-1">¥{{ stock.target_price_2?.toFixed(2) }}</span>
              </div>
              <div>
                <span class="text-gray-500">仓位:</span>
                <span class="font-semibold ml-1">{{ stock.position_suggestion }}</span>
              </div>
              <div>
                <span class="text-gray-500">周期:</span>
                <span class="font-semibold ml-1">{{ stock.holding_period }}</span>
              </div>
            </div>
          </div>
          
          <!-- 风险提示 -->
          <div v-if="stock.risk_warning" class="px-4 py-2 bg-yellow-50 border-t border-yellow-200 text-xs text-yellow-700">
            ⚠️ {{ stock.risk_warning }}
          </div>
        </div>
      </div>
      
      <!-- 风险免责声明 -->
      <div class="mt-4 p-3 bg-gray-100 rounded text-xs text-gray-500">
        <strong>⚠️ 重要风险提示：</strong>本推荐仅供参考，不构成投资建议。股市有风险，投资需谨慎。历史表现不代表未来收益。请根据自身风险承受能力做出决策。
      </div>
    </div>

    <!-- 推荐列表 -->
    <div class="bg-white rounded-lg shadow">
      <div class="px-4 py-3 border-b flex items-center justify-between">
        <h2 class="text-lg font-semibold text-gray-800">推荐列表</h2>
        <span class="text-sm text-gray-500">共 {{ recommendations.length }} 条</span>
      </div>
      
      <div class="overflow-x-auto">
        <table class="w-full">
          <thead class="bg-gray-50">
            <tr>
              <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('recommend_date')">
                日期 {{ sortIcon('recommend_date') }}
              </th>
              <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">代码/名称</th>
              <th class="px-3 py-2 text-center text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('startup_score')">
                得分 {{ sortIcon('startup_score') }}
              </th>
              <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">标签</th>
              <th class="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase" title="推荐买入价（入选当日参考价）">推荐买入价</th>
              <th class="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase">当前价</th>
              <th class="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('gain')">
                收益 {{ sortIcon('gain') }}
              </th>
              <th class="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase" title="有几天就计算几天收益，最多5日">5日收益</th>
              <th class="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase" title="有几天就计算几天收益，最多10日">10日收益</th>
              <th class="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase" title="目标价/买入价">预期</th>
              <th class="px-3 py-2 text-center text-xs font-medium text-gray-500 uppercase" title="5日收益 vs 预期：|差值|≤5%符合，≥+5%超预期，≥+10%超超">5日 vs 预期</th>
              <th class="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase">止损</th>
              <th class="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase">目标</th>
              <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase" title="近一年内收盘价创新高的日期">近一年新高时间</th>
              <th class="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase" title="近一年内最高收盘价">新高价格</th>
              <th class="px-3 py-2 text-center text-xs font-medium text-gray-500 uppercase">状态</th>
              <th class="px-3 py-2 text-center text-xs font-medium text-gray-500 uppercase">操作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-200">
            <tr v-if="displayList.length === 0">
              <td colspan="16" class="px-3 py-8 text-center text-gray-500">
                {{ loading ? '加载中...' : '暂无推荐股票' }}
              </td>
            </tr>
            <tr v-for="(stock, idx) in displayList" :key="stock.id != null ? `${stock.id}-${stock.ts_code}-${stock.recommend_date}` : idx" class="hover:bg-gray-50">
              <td class="px-3 py-2 text-xs">{{ formatDate(stock.recommend_date) }}</td>
              <td class="px-3 py-2 text-xs">
                <div class="font-medium">{{ stock.name }}</div>
                <div class="text-gray-500">{{ stock.ts_code }}</div>
              </td>
              <td class="px-3 py-2 text-xs text-center relative">
                <span
                  class="px-2 py-1 rounded cursor-help inline-block"
                  :class="scoreClass(stock.startup_score)"
                  @mouseenter="(e) => showScoreTooltip(stock, e)"
                  @mouseleave="hideScoreTooltip"
                >
                  {{ stock.startup_score }}
                </span>
              </td>
              <td class="px-3 py-2 text-xs">
                <div class="flex flex-wrap gap-1">
                  <span
                    v-for="tag in (stock.recommend_tags || []).filter(t => t === 'AI精选')"
                    :key="'ai-'+tag"
                    class="px-1.5 py-0.5 bg-purple-200 text-purple-800 rounded text-xs font-medium"
                  >{{ tag }}</span>
                  <span
                    v-for="tag in (stock.recommend_tags || []).filter(t => t !== 'AI精选').slice(0, 4)"
                    :key="tag"
                    class="px-1.5 py-0.5 bg-blue-100 text-blue-700 rounded text-xs"
                  >{{ tag }}</span>
                </div>
              </td>
              <td class="px-3 py-2 text-xs text-right">{{ stock.entry_price?.toFixed(2) }}</td>
              <td class="px-3 py-2 text-xs text-right">{{ stock.current_price?.toFixed(2) }}</td>
              <td class="px-3 py-2 text-xs text-right font-semibold" :class="gainClass(stock.gain)">
                {{ stock.gain > 0 ? '+' : '' }}{{ stock.gain?.toFixed(2) }}%
              </td>
              <td class="px-3 py-2 text-xs text-right" :class="stock.return_5d != null ? gainClass(stock.return_5d) : 'text-gray-400'" :title="stock.return_5d_days ? `${stock.return_5d_days}个交易日收益` : null">
                {{ stock.return_5d != null ? (stock.return_5d > 0 ? '+' : '') + stock.return_5d.toFixed(2) + '%' + (stock.return_5d_days && stock.return_5d_days !== 5 ? ` (${stock.return_5d_days}日)` : '') : '--' }}
              </td>
              <td class="px-3 py-2 text-xs text-right" :class="stock.return_10d != null ? gainClass(stock.return_10d) : 'text-gray-400'" :title="stock.return_10d_days ? `${stock.return_10d_days}个交易日收益` : null">
                {{ stock.return_10d != null ? (stock.return_10d > 0 ? '+' : '') + stock.return_10d.toFixed(2) + '%' + (stock.return_10d_days && stock.return_10d_days !== 10 ? ` (${stock.return_10d_days}日)` : '') : '--' }}
              </td>
              <td class="px-3 py-2 text-xs text-right text-gray-600">
                {{ stock.expected_return_pct != null ? '+' + stock.expected_return_pct.toFixed(1) + '%' : '--' }}
              </td>
              <td class="px-3 py-2 text-xs text-center" :title="expectationTooltip(stock)">
                <span v-if="stock.meet_expectation === 'exceed_exceed'" class="px-1.5 py-0.5 bg-amber-200 text-amber-900 rounded text-xs font-medium">超超</span>
                <span v-else-if="stock.meet_expectation === 'exceed'" class="px-1.5 py-0.5 bg-amber-100 text-amber-800 rounded text-xs">超预期</span>
                <span v-else-if="stock.meet_expectation === 'meet'" class="px-1.5 py-0.5 bg-green-100 text-green-700 rounded text-xs">✓</span>
                <span v-else-if="stock.meet_expectation === 'not_meet'" class="px-1.5 py-0.5 bg-red-100 text-red-700 rounded text-xs">✗</span>
                <span v-else class="text-gray-400">-</span>
              </td>
              <td class="px-3 py-2 text-xs text-right text-green-600">
                {{ stock.stop_loss_price ? stock.stop_loss_price.toFixed(2) : '--' }}
              </td>
              <td class="px-3 py-2 text-xs text-right text-red-600">
                {{ stock.target_price_1 ? stock.target_price_1.toFixed(2) : '--' }}
              </td>
              <td class="px-3 py-2 text-xs text-gray-600">
                {{ stock.high_1y_date ? formatDate(stock.high_1y_date) : '--' }}
              </td>
              <td class="px-3 py-2 text-xs text-right text-gray-600">
                {{ stock.high_1y_price != null ? stock.high_1y_price.toFixed(2) : '--' }}
              </td>
              <td class="px-3 py-2 text-xs text-center">
                <span
                  :class="statusClass(stock.status)"
                  class="px-2 py-1 rounded"
                  :title="stock.status !== 'active' ? '推荐跟踪已结束（模拟触及止损/目标或已移除，不代表实际买卖）' : ''"
                >
                  {{ stock.status === 'active' ? '跟踪中' : '跟踪结束' }}
                </span>
              </td>
              <td class="px-3 py-2 text-xs text-center">
                <button @click="showDetail(stock)" class="text-blue-600 hover:text-blue-800 mr-2" title="详情">📄</button>
                <button v-if="stock.status === 'active'" @click="closeRecommendation(stock.id)" class="text-red-600 hover:text-red-800" title="结束跟踪（移除出推荐池）">
                  ❌
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 七维得分悬浮详情 -->
    <Teleport to="body">
      <div
        v-if="scoreTooltipStock"
        class="fixed z-[9999] bg-gray-900 text-white text-xs rounded-lg shadow-xl px-3 py-2 min-w-[200px] pointer-events-none"
        :style="scoreTooltipStyle"
      >
        <div class="font-semibold mb-2 text-white/90">七维得分详情</div>
        <div v-if="scoreTooltipStock.dimension_scores && Object.keys(scoreTooltipStock.dimension_scores).length" class="space-y-1">
          <div v-for="(val, key) in scoreTooltipStock.dimension_scores" :key="key" class="flex justify-between gap-4">
            <span class="text-gray-300">{{ DIMENSION_LABELS[key] || key }}</span>
            <span class="font-medium">{{ Number(val)?.toFixed(0) ?? val }}</span>
          </div>
        </div>
        <div v-else class="text-gray-400">暂无细分数据</div>
      </div>
    </Teleport>

    <!-- 详情模态框 -->
    <div v-if="selectedStock" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50" @click="selectedStock = null">
      <div class="bg-white rounded-lg p-6 max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto" @click.stop>
        <div class="flex items-center justify-between mb-4">
          <div>
            <h2 class="text-xl font-bold">{{ selectedStock.name }} ({{ selectedStock.ts_code }})</h2>
            <p class="text-sm text-gray-500">推荐日期: {{ selectedStock.recommend_date }}</p>
          </div>
          <button @click="selectedStock = null" class="text-gray-500 hover:text-gray-700 text-2xl">×</button>
        </div>

        <div class="grid grid-cols-4 gap-4 mb-6">
          <div class="bg-gray-50 p-3 rounded text-center" :title="formatDimensionScores(selectedStock.dimension_scores)">
            <div class="text-xs text-gray-500">得分</div>
            <div class="text-lg font-bold text-blue-600 cursor-help">{{ selectedStock.startup_score }}</div>
          </div>
          <div class="bg-gray-50 p-3 rounded text-center">
            <div class="text-xs text-gray-500">推荐买入价</div>
            <div class="text-lg font-bold">{{ selectedStock.entry_price?.toFixed(2) }}</div>
          </div>
          <div class="bg-gray-50 p-3 rounded text-center">
            <div class="text-xs text-gray-500">当前价</div>
            <div class="text-lg font-bold">{{ selectedStock.current_price?.toFixed(2) }}</div>
          </div>
          <div class="bg-gray-50 p-3 rounded text-center">
            <div class="text-xs text-gray-500">收益率</div>
            <div class="text-lg font-bold" :class="gainClass(selectedStock.gain)">
              {{ selectedStock.gain > 0 ? '+' : '' }}{{ selectedStock.gain?.toFixed(2) }}%
            </div>
          </div>
        </div>
        <div class="grid grid-cols-4 gap-4 mb-4">
          <div class="bg-blue-50 p-3 rounded text-center">
            <div class="text-xs text-gray-500" :title="selectedStock.return_5d_days ? `有 ${selectedStock.return_5d_days} 个交易日` : null">5日收益</div>
            <div class="text-lg font-bold" :class="selectedStock.return_5d != null ? gainClass(selectedStock.return_5d) : ''">
              {{ selectedStock.return_5d != null ? (selectedStock.return_5d > 0 ? '+' : '') + selectedStock.return_5d.toFixed(2) + '%' + (selectedStock.return_5d_days && selectedStock.return_5d_days !== 5 ? ` (${selectedStock.return_5d_days}日)` : '') : '--' }}
            </div>
          </div>
          <div class="bg-blue-50 p-3 rounded text-center">
            <div class="text-xs text-gray-500" :title="selectedStock.return_10d_days ? `有 ${selectedStock.return_10d_days} 个交易日` : null">10日收益</div>
            <div class="text-lg font-bold" :class="selectedStock.return_10d != null ? gainClass(selectedStock.return_10d) : ''">
              {{ selectedStock.return_10d != null ? (selectedStock.return_10d > 0 ? '+' : '') + selectedStock.return_10d.toFixed(2) + '%' + (selectedStock.return_10d_days && selectedStock.return_10d_days !== 10 ? ` (${selectedStock.return_10d_days}日)` : '') : '--' }}
            </div>
          </div>
          <div class="bg-blue-50 p-3 rounded text-center">
            <div class="text-xs text-gray-500">预期收益</div>
            <div class="text-lg font-bold text-gray-700">{{ selectedStock.expected_return_pct != null ? '+' + selectedStock.expected_return_pct.toFixed(1) + '%' : '--' }}</div>
          </div>
          <div class="bg-blue-50 p-3 rounded text-center">
            <div class="text-xs text-gray-500">5日 vs 预期</div>
            <div class="text-lg font-bold">
              <span v-if="selectedStock.meet_expectation === 'exceed_exceed'" class="text-amber-700">超超预期</span>
              <span v-else-if="selectedStock.meet_expectation === 'exceed'" class="text-amber-600">超预期</span>
              <span v-else-if="selectedStock.meet_expectation === 'meet'" class="text-green-600">✓ 符合</span>
              <span v-else-if="selectedStock.meet_expectation === 'not_meet'" class="text-red-600">✗ 不符合</span>
              <span v-else class="text-gray-500">-</span>
            </div>
            <div class="text-xs text-gray-400 mt-0.5">|5日-预期|≤5符合；≥+5超预期；≥+10超超</div>
          </div>
        </div>
        <div class="grid grid-cols-2 gap-4 mb-4">
          <div class="bg-gray-50 p-3 rounded">
            <div class="text-xs text-gray-500">近一年新高时间</div>
            <div class="font-medium">{{ selectedStock.high_1y_date ? formatDate(selectedStock.high_1y_date) : '--' }}</div>
          </div>
          <div class="bg-gray-50 p-3 rounded">
            <div class="text-xs text-gray-500">新高价格</div>
            <div class="font-medium">{{ selectedStock.high_1y_price != null ? selectedStock.high_1y_price.toFixed(2) : '--' }}</div>
          </div>
        </div>

        <div class="mb-4">
          <h3 class="text-sm font-semibold text-gray-700 mb-2">推荐标签</h3>
          <div class="flex flex-wrap gap-2">
            <span
              v-for="tag in (selectedStock.recommend_tags || []).filter(t => t === 'AI精选')"
              :key="'ai-'+tag"
              class="px-3 py-1 bg-purple-200 text-purple-800 rounded font-medium"
            >{{ tag }}</span>
            <span
              v-for="tag in (selectedStock.recommend_tags || []).filter(t => t !== 'AI精选')"
              :key="tag"
              class="px-3 py-1 bg-blue-100 text-blue-700 rounded"
            >{{ tag }}</span>
          </div>
        </div>

        <div class="mb-4">
          <h3 class="text-sm font-semibold text-gray-700 mb-2">推荐原因</h3>
          <div class="bg-gray-50 p-4 rounded text-sm whitespace-pre-line">{{ selectedStock.recommend_reason }}</div>
        </div>

        <div v-if="selectedStock.risk_note" class="mb-4">
          <h3 class="text-sm font-semibold text-gray-700 mb-2">风险提示</h3>
          <div class="bg-yellow-50 border border-yellow-200 p-4 rounded text-sm">{{ selectedStock.risk_note }}</div>
        </div>

        <div class="flex justify-end space-x-3">
          <button @click="selectedStock = null" class="px-4 py-2 border border-gray-300 rounded hover:bg-gray-50">关闭</button>
          <button v-if="selectedStock.status === 'active'" @click="closeRecommendation(selectedStock.id); selectedStock = null" class="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700">
            结束跟踪
          </button>
        </div>
      </div>
    </div>
  </div>

  <AiChat />
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'
import AiChat from '../components/AiChat.vue'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

// 状态
const loading = ref(false)

// 当前主线
const mainlineLoading = ref(false)
const mainlineData = ref(null)
const mainlineError = ref('')
async function fetchMainline() {
  mainlineLoading.value = true
  mainlineError.value = ''
  try {
    const resp = await fetch(`${API_BASE_URL}/api/sector-rotation/current-mainline?top=5`)
    const json = await resp.json()
    if (json.success && json.data) {
      mainlineData.value = json.data
    } else {
      mainlineData.value = { mainline: [] }
    }
  } catch (e) {
    mainlineError.value = e.message || '获取主线失败'
    mainlineData.value = null
  } finally {
    mainlineLoading.value = false
  }
}
const refreshing = ref(false)
const aiSelecting = ref(false)
const backfilling = ref(false)
const recommendations = ref([])
const selectedStock = ref(null)
const marketEnv = ref({})
const performance = ref({})
const aiResult = ref(null)

// 规则展示（默认收起）
const rulesExpanded = ref(false)

// 筛选条件
const queryDays = ref(30)
const statusFilter = ref('')
const minExpectedReturn = ref(null)
const strategy = ref('balanced')
const performanceDays = ref(30)

// 排序
const sortField = ref('recommend_date')
const sortOrder = ref('desc')

// 得分悬浮详情
const scoreTooltipStock = ref(null)
const scoreTooltipStyle = ref({})

// 显示列表
const displayList = computed(() => {
  return [...recommendations.value].sort((a, b) => {
    const field = sortField.value
    let aVal = a[field]
    let bVal = b[field]
    if (aVal == null && bVal == null) return 0
    if (aVal == null) return 1
    if (bVal == null) return -1
    let comparison = typeof aVal === 'string' ? String(aVal).localeCompare(String(bVal), 'zh-CN') : Number(aVal) - Number(bVal)
    return sortOrder.value === 'desc' ? -comparison : comparison
  })
})

// 数据更新触发状态
const updateTriggering = ref('')

// 触发数据更新（日线、北向资金等）
async function triggerDataUpdate(taskName) {
  if (updateTriggering.value) return
  updateTriggering.value = taskName
  try {
    const response = await axios.post(`${API_BASE_URL}/api/scheduled-task/${taskName}/trigger`)
    if (response.data.success) {
      alert('任务已触发，后台执行中。完成后点击「刷新」查看最新数据。')
      setTimeout(() => loadMarketEnv(), 5000)
    } else {
      alert('触发失败: ' + (response.data.message || response.data.detail || '未知错误'))
    }
  } catch (error) {
    console.error('触发数据更新失败:', error)
    alert('触发失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    updateTriggering.value = ''
  }
}

// 加载市场环境
async function loadMarketEnv() {
  try {
    const response = await axios.get(`${API_BASE_URL}/api/recommendations/market-env`)
    if (response.data.success) {
      marketEnv.value = response.data.data
    }
  } catch (error) {
    console.error('加载市场环境失败:', error)
  }
}

// 加载历史表现
async function loadPerformance() {
  try {
    const response = await axios.get(`${API_BASE_URL}/api/recommendations/performance`, {
      params: { days: performanceDays.value }
    })
    if (response.data.success) {
      performance.value = response.data.data
    }
  } catch (error) {
    console.error('加载历史表现失败:', error)
  }
}

// 加载推荐列表
async function loadRecommendations() {
  loading.value = true
  try {
    const response = await axios.get(`${API_BASE_URL}/api/recommendations/pool`, {
      params: {
        days: queryDays.value,
        status: statusFilter.value || undefined,
        min_expected_return: minExpectedReturn.value ?? undefined
      }
    })
    if (response.data.success) {
      const data = Array.isArray(response.data.data) ? response.data.data : []
      recommendations.value = data
      const apiCount = response.data.count
      if (apiCount != null && data.length !== apiCount) {
        console.warn(`[推荐池] 接口返回 count=${apiCount} 但 data 长度为 ${data.length}`)
      }
    }
  } catch (error) {
    console.error('加载推荐失败:', error)
    alert('加载失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    loading.value = false
  }
}

// 清空所有推荐
async function clearAllRecommendations() {
  if (!confirm('⚠️ 确认清空所有推荐数据？此操作不可恢复！')) return
  if (!confirm('再次确认：真的要删除所有推荐记录吗？')) return
  
  try {
    const response = await axios.delete(`${API_BASE_URL}/api/recommendations/clear`, {
      params: { confirm: true }
    })
    if (response.data.success) {
      alert(response.data.message)
      recommendations.value = []
      aiResult.value = null
      await loadPerformance()
    }
  } catch (error) {
    console.error('清空推荐失败:', error)
    alert('清空失败: ' + (error.response?.data?.detail || error.message))
  }
}

// AI精选（与刷新推荐合并为同一流程：入池后对新入池股票做 AI 筛选并打「AI精选」标签）
async function triggerAISelect() {
  await refreshRecommendations()
}

// 回填追踪（补齐 5日/10日收益所需历史数据）
async function triggerTrackBackfill() {
  if (!confirm('回填追踪将对推荐日期至今日的每个交易日执行追踪，补齐 5日收益、10日收益 所需数据。\n\n建议在新增推荐后或 5日/10日收益为空时执行。\n\n确认执行？')) return
  backfilling.value = true
  try {
    const response = await axios.post(`${API_BASE_URL}/api/recommendations/track-backfill`)
    if (response.data.success) {
      alert(response.data.message || `回填完成：处理 ${response.data.days_processed || 0} 个交易日，5日/10日收益将可用`)
      await loadRecommendations()
    } else {
      alert('回填失败: ' + (response.data.message || response.data.error || '未知错误'))
    }
  } catch (error) {
    console.error('回填追踪失败:', error)
    alert('回填失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    backfilling.value = false
  }
}

// 刷新推荐
async function refreshRecommendations() {
  if (!confirm('确认刷新推荐？')) return
  refreshing.value = true
  try {
    const response = await axios.post(`${API_BASE_URL}/api/recommendations/refresh`)
    if (response.data.success) {
      alert(response.data.message)
      await loadRecommendations()
    }
  } catch (error) {
    console.error('刷新推荐失败:', error)
    alert('刷新失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    refreshing.value = false
  }
}

// 结束跟踪（移除推荐出池，不代表实际买卖）
async function closeRecommendation(id) {
  if (!confirm('确认结束跟踪此推荐？（将移出推荐池，不代表实际平仓）')) return
  try {
    const response = await axios.post(`${API_BASE_URL}/api/recommendations/${id}/close`)
    if (response.data.success) {
      alert(response.data.message)
      await loadRecommendations()
      await loadPerformance()
    }
  } catch (error) {
    console.error('结束跟踪失败:', error)
    alert('结束跟踪失败: ' + (error.response?.data?.detail || error.message))
  }
}

function showDetail(stock) { selectedStock.value = stock }

function showScoreTooltip(stock, e) {
  scoreTooltipStock.value = stock
  const rect = e.currentTarget?.getBoundingClientRect?.()
  if (rect) {
    const padding = 8
    let left = rect.right + padding
    let top = rect.top
    if (left + 220 > window.innerWidth) left = rect.left - 220 - padding
    if (top + 220 > window.innerHeight) top = window.innerHeight - 230
    if (top < 10) top = 10
    scoreTooltipStyle.value = { left: left + 'px', top: top + 'px' }
  } else {
    scoreTooltipStyle.value = {}
  }
}
function hideScoreTooltip() {
  scoreTooltipStock.value = null
}
function sortBy(field) {
  if (sortField.value === field) {
    sortOrder.value = sortOrder.value === 'desc' ? 'asc' : 'desc'
  } else {
    sortField.value = field
    sortOrder.value = 'desc'
  }
}
function sortIcon(field) { return sortField.value === field ? (sortOrder.value === 'desc' ? '↓' : '↑') : '' }

// 样式函数
function trendClass(trend) {
  return { bullish: 'text-red-600', bearish: 'text-green-600', sideways: 'text-yellow-600' }[trend] || 'text-gray-600'
}
function trendLabel(trend) {
  return { bullish: '牛市', bearish: '熊市', sideways: '震荡' }[trend] || '--'
}
function emotionClass(label) {
  return { '贪婪': 'text-red-600', '乐观': 'text-orange-500', '中性': 'text-gray-600', '悲观': 'text-blue-500', '恐惧': 'text-green-600' }[label] || 'text-gray-600'
}
function scoreClass(score) {
  if (score >= 90) return 'bg-red-100 text-red-700'
  if (score >= 80) return 'bg-orange-100 text-orange-700'
  if (score >= 70) return 'bg-yellow-100 text-yellow-700'
  return 'bg-gray-100 text-gray-700'
}
function gainClass(gain) {
  if (gain > 0) return 'text-red-600'
  if (gain < 0) return 'text-green-600'
  return 'text-gray-600'
}
function statusClass(status) {
  return status === 'active' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-700'
}
function formatDate(dateStr) { return dateStr ? dateStr.substring(5, 10).replace('-', '/') : '--' }

// 5日 vs 预期 悬浮说明（有几天算几天，不足5日会标注）
function expectationTooltip(stock) {
  const r5 = stock.return_5d
  const exp = stock.expected_return_pct
  const meet = stock.meet_expectation
  const days = stock.return_5d_days
  if (r5 == null || exp == null || !meet) return '5日收益/预期为空，无法判断'
  const diff = r5 - exp
  const labels = { exceed_exceed: '超超预期', exceed: '超预期', meet: '符合预期', not_meet: '不符合预期' }
  const dayLabel = days && days !== 5 ? `${days}日 ` : '5日 '
  return `${dayLabel}${(r5 > 0 ? '+' : '') + r5.toFixed(1)}% vs 预期 +${exp.toFixed(1)}%，差值 ${(diff >= 0 ? '+' : '') + diff.toFixed(1)}% → ${labels[meet] || meet}`
}

const DIMENSION_LABELS = {
  technical: '技术面',
  leader: '龙头地位',
  money_flow: '资金流向',
  sector_cycle: '板块周期',
  fundamental: '基本面',
  sentiment: '市场情绪',
  timing: '介入时机'
}
function formatDimensionScores(scores) {
  if (!scores || typeof scores !== 'object') return '暂无细分数据'
  const parts = []
  for (const [key, val] of Object.entries(scores)) {
    const label = DIMENSION_LABELS[key] || key
    parts.push(`${label} ${Number(val)?.toFixed(0) ?? val}`)
  }
  return parts.length ? parts.join(' | ') : '暂无细分数据'
}

onMounted(() => {
  fetchMainline()
  loadMarketEnv()
  loadPerformance()
  loadRecommendations()
})
</script>
