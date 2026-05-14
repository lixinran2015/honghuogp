<template>
  <div class="p-4 lg:p-6 bg-warm-50 min-h-screen">
    <!-- 标题 -->
    <div class="mb-6 flex items-center justify-between">
      <div>
        <h1 class="text-xl font-bold text-warmgray-900">龙头跟踪</h1>
        <p class="text-sm text-warmgray-500 mt-1 max-w-4xl">
          与「主线雷达」一致：仅纳入<strong class="text-warmgray-900">主线强度 &gt; 5</strong> 板块中强度排名前 <strong class="text-warmgray-900">10</strong> 的空间龙头与刚启动；并与<strong class="text-warmgray-900">持久跟踪池</strong>合并展示。
        </p>
      </div>
      <button
        class="px-4 py-2 rounded-md text-sm font-medium text-warmgray-900 bg-cta hover:bg-cta-hover disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        :disabled="loading"
        @click="fetchData"
      >
        {{ loading ? '加载中...' : '刷新数据' }}
      </button>
    </div>

    <!-- 错误提示 -->
    <div
      v-if="error"
      class="mb-4 bg-loss/10 border border-loss/30 text-loss text-sm px-4 py-3 rounded-lg"
    >
      <div class="flex items-center gap-2">
        <ExclamationCircleIcon class="w-4 h-4" />
        {{ error }}
      </div>
    </div>

    <!-- 健康分数卡片 -->
    <div
      v-if="healthData"
      class="mb-4 bg-white rounded-lg border border-border p-4"
    >
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-4">
          <!-- 健康分数圆圈 -->
          <div class="flex items-center gap-3">
            <div
              class="w-16 h-16 rounded-full flex items-center justify-center text-xl font-bold"
              :class="getHealthScoreBg(healthData.health_score) + ' ' + getHealthScoreColor(healthData.health_score)"
            >
              {{ healthData.health_score }}
            </div>
            <div>
              <div class="text-sm font-semibold text-warmgray-900">健康分数</div>
              <div class="text-xs text-warmgray-500">满分100分</div>
            </div>
          </div>

          <!-- 分隔线 -->
          <div class="w-px h-12 bg-warmgray-200"></div>

          <!-- 关键指标（与页面显示一致） -->
          <div class="flex items-center gap-4 text-sm">
            <div>
              <span class="text-warmgray-500">活跃龙头:</span>
              <span class="font-medium text-warmgray-900 ml-1">{{ healthData.metrics?.active_count || 0 }}只</span>
            </div>
            <div>
              <span class="text-warmgray-500">退潮:</span>
              <span class="font-medium text-warmgray-900 ml-1">{{ healthData.metrics?.retreat_count || 0 }}只</span>
            </div>
            <div>
              <span class="text-warmgray-500">跟踪总数:</span>
              <span class="font-medium text-warmgray-900 ml-1">{{ healthData.metrics?.total_tracked || 0 }}只</span>
            </div>
          </div>
        </div>

        <!-- 告警数量 -->
        <div class="flex-1 ml-8 text-right">
          <span
            v-if="healthData.alert_count > 0"
            class="px-2 py-1 rounded text-xs font-medium bg-amber-100 text-amber-700"
          >
            ⚠️ {{ healthData.alert_count }} 条告警
          </span>
          <span
            v-else
            class="px-2 py-1 rounded text-xs font-medium bg-green-100 text-green-700"
          >
            ✅ 系统健康
          </span>
        </div>
      </div>
    </div>

    <div class="space-y-4">
      <!-- 龙头列表 + 日线图 -->
      <div class="space-y-4">
        <!-- 全局筛选条 -->
        <div class="bg-warmgray-100 rounded-lg border border-warmgray-200 p-3 flex flex-wrap items-center gap-3">
          <div class="flex items-center gap-2">
            <span class="text-2xs text-warmgray-500 uppercase">筛选</span>
            <input
              v-model="keyword"
              type="text"
              class="px-2 py-1.5 bg-warmgray-50 border border-warmgray-200 rounded-md text-sm text-warmgray-900 focus:outline-none focus:border-primary-700 transition-colors"
              placeholder="按股票名称 / 代码 / 题材关键词过滤"
            />
          </div>
          <div class="flex items-center gap-2">
            <span class="text-2xs text-warmgray-500 uppercase">状态</span>
            <select
              v-model="retreatFilter"
              class="px-2 py-1.5 bg-warmgray-50 border border-warmgray-200 rounded-md text-sm text-warmgray-900 focus:outline-none focus:border-primary-700 transition-colors"
            >
              <option value="">全部</option>
              <option value="强势">强势</option>
              <option value="震荡">震荡</option>
              <option value="退潮风险">退潮风险</option>
            </select>
          </div>
          <div class="flex items-center gap-2">
            <span class="text-2xs text-warmgray-500 uppercase">类型</span>
            <select
              v-model="leaderTypeFilter"
              class="px-2 py-1.5 bg-warmgray-50 border border-warmgray-200 rounded-md text-sm text-warmgray-900 focus:outline-none focus:border-primary-700 transition-colors"
            >
              <option value="">全部</option>
              <option value="space">空间龙头</option>
              <option value="new">刚启动</option>
            </select>
          </div>
          <div class="flex items-center gap-2">
            <span class="text-2xs text-warmgray-500 uppercase">成交额</span>
            <select
              v-model="amountFilter"
              class="px-2 py-1.5 bg-warmgray-50 border border-warmgray-200 rounded-md text-sm text-warmgray-900 focus:outline-none focus:border-primary-700 transition-colors"
            >
              <option value="">全部</option>
              <option value="1">≥ 1 亿</option>
              <option value="2">≥ 2 亿</option>
              <option value="5">≥ 5 亿</option>
              <option value="10">≥ 10 亿</option>
            </select>
          </div>
        <div class="flex items-center gap-2" title="用于「历史买点回测」接口筛选；龙头列表当日主线口径固定为强度>5 的前 10 条，不受此项影响">
          <span class="text-2xs text-warmgray-500 uppercase">回测·主线强度下限</span>
          <input
            v-model.number="minStrength"
            type="number"
            min="0"
            max="20"
            step="0.5"
            class="w-20 px-2 py-1.5 bg-warmgray-50 border border-warmgray-200 rounded-md text-sm text-warmgray-900 focus:outline-none focus:border-primary-700 transition-colors"
          />
        </div>
          <label class="inline-flex items-center gap-1 text-warmgray-500 cursor-pointer hover:text-warmgray-900 transition-colors">
            <input
              v-model="onlyBuyCandidates"
              type="checkbox"
              class="w-3.5 h-3.5 rounded border-warmgray-200 bg-warmgray-50 text-cta focus:ring-cta focus:ring-offset-0"
            />
            <span>只看买点候选</span>
          </label>
          <label class="inline-flex items-center gap-1 text-warmgray-500 cursor-pointer hover:text-warmgray-900 transition-colors">
            <input
              v-model="onlyMultiSectors"
              type="checkbox"
              class="w-3.5 h-3.5 rounded border-warmgray-200 bg-warmgray-50 text-cta focus:ring-cta focus:ring-offset-0"
            />
            <span>只看涉及 ≥2 个题材/板块 的龙头</span>
          </label>
          <label class="inline-flex items-center gap-1 text-profit cursor-pointer hover:text-profit/80 transition-colors" title="强势/震荡排在前列；退潮风险沉底，避免长线龙头被挤到后页">
            <input
              v-model="prioritizeTrendAlive"
              type="checkbox"
              class="w-3.5 h-3.5 rounded border-warmgray-200 bg-warmgray-50 text-profit focus:ring-profit focus:ring-offset-0"
            />
            <span>优先趋势未断（强势/震荡靠前）</span>
          </label>
          <label
            class="inline-flex items-center gap-1 text-primary-400 cursor-pointer hover:text-primary-300 transition-colors"
            title="取消勾选可查看池中已标为退潮风险的标的（便于复盘）"
          >
            <input
              v-model="onlyTrendAlive"
              type="checkbox"
              class="w-3.5 h-3.5 rounded border-warmgray-200 bg-warmgray-50 text-cta focus:ring-cta focus:ring-offset-0"
            />
            <span>龙头列表仅展示趋势未断（隐藏退潮）</span>
          </label>
        </div>

        <!-- 调试信息（临时） -->
        <div v-if="!loading" class="mb-4 bg-blue-50 border border-blue-200 rounded-lg p-3 text-xs text-blue-800">
          <div class="font-semibold mb-1 flex items-center justify-between">
            <span>调试信息（列表已包含空间龙头+刚启动数据）：</span>
            <button
              type="button"
              class="px-2 py-1 bg-blue-600 text-white rounded text-[10px] hover:bg-blue-700"
              @click="clearCacheAndRefresh"
            >
              清除缓存并刷新
            </button>
          </div>
          <div>列表总数: {{ leaderRowsBase.length }} (持久池: {{ poolLeaders.length }} + 空间龙头: {{ spaceLeadersByStock.length }} + 刚启动: {{ newLeadersByStock.length }})</div>
        </div>

        <!-- 综合龙头列表：一行一个股票 -->
        <div class="bg-warmgray-100 rounded-lg border border-warmgray-200 overflow-hidden">
          <div class="flex items-center justify-between mb-3">
            <div>
              <div class="text-sm font-semibold text-warmgray-900">龙头列表（空间龙头 / 刚启动）</div>
              <div class="text-2xs text-warmgray-500 mt-0.5">
                列表 = <span class="text-warmgray-500">持久跟踪池</span> ∪ <span class="text-warmgray-500">当日雷达（强度 &gt; 5 的前 10 条主线上的空间/刚启动）</span>，按票去重。日线计算强势 / 震荡 / 退潮。勾选「仅展示趋势未断」会隐藏退潮；取消勾选可看退潮票。「优先趋势未断」排序时强势/震荡靠前。
              </div>
            </div>
            <div class="flex items-center gap-3">
              <button
                type="button"
                class="text-2xs text-cta hover:text-cta-hover underline transition-colors"
                @click="openLeaderBuyBacktest"
              >
                查看历史买点表现
              </button>
              <button
                type="button"
                class="px-3 py-1.5 rounded-md text-2xs font-medium border border-profit/30 text-profit bg-profit/10 hover:bg-profit/10 disabled:opacity-50"
                :disabled="leaderRowsPaged.length === 0"
                @click="bulkTrack('page')"
              >
                批量加入跟踪池
              </button>
            </div>
          </div>

          <!-- 今日真龙头推荐（Top3） -->
          <div
            v-if="dailyTrueDragons.length"
            class="bg-primary-700/20 border border-primary-700/30 rounded-lg p-3 mb-3"
            title="自动从当前龙头列表中选 Top3：连板高度/主线数/量能/末次信号，并受 仅展示趋势未断 过滤"
          >
            <div class="text-sm font-semibold text-primary-400">今日真龙头（3只）</div>
            <div class="text-2xs text-primary-400/80 mt-0.5">
              Top3 排序后展示；如勾选「仅展示趋势未断」，退潮风险会被过滤。
            </div>
            <div class="flex flex-wrap gap-2 mt-2">
              <div
                v-for="(d, i) in dailyTrueDragons"
                :key="d.row.ts_code"
                class="bg-warmgray-50/70 border border-primary-700/20 rounded-lg px-2 py-1.5 min-w-[220px]"
              >
                <div class="flex items-center justify-between gap-2">
              <div class="text-2xs text-primary-400 font-mono">#{{ i + 1 }}</div>
                  <div class="text-[10px] text-2xs text-warmgray-500 uppercase">
                    {{
                      d.row.is_space && d.row.is_new
                        ? '空间+刚启动'
                        : d.row.is_space
                          ? '空间龙头'
                          : '刚启动'
                    }}
                  </div>
                </div>
                <div class="text-sm font-semibold text-warmgray-900 truncate mt-0.5">
                  {{ d.row.name || d.row.ts_code }}
                </div>
                <div class="text-2xs text-primary-400/80 mt-0.5">
                  {{ d.buyText }}
                </div>
                <div v-if="d.possibleText" class="text-2xs text-primary-400/60 mt-0.5">
                  {{ d.possibleText }}
                </div>
                <div class="text-2xs text-warmgray-500 mt-0.5">{{ d.reason }}</div>
              </div>
            </div>
          </div>

          <!-- LSTM-MAB 智能评分 Top10 -->
          <div
            v-if="topScoredStocks.length"
            class="bg-purple-50 border border-purple-200 rounded-lg p-3 mb-3"
          >
            <div class="flex items-center justify-between">
              <div>
                <div class="text-sm font-semibold text-purple-700">AI智能评分 Top10</div>
                <div class="text-2xs text-purple-600/80 mt-0.5">
                  基于LSTM-MAB模型对龙头地位和技术形态的综合评分
                  <span v-if="currentEmotionCycle" class="ml-1">(当前情绪: {{ currentEmotionCycle }})</span>
                </div>
              </div>
              <button
                type="button"
                class="text-2xs text-purple-600 hover:text-purple-800 underline transition-colors"
                @click="fetchTopScored"
                :disabled="isScoring"
              >
                {{ isScoring ? '评分中...' : '刷新评分' }}
              </button>
            </div>
            <div v-if="scoringError" class="text-2xs text-red-500 mt-2">{{ scoringError }}</div>
            <div v-if="!modelAvailable && topScoredStocks.length" class="text-2xs text-amber-600 mt-2">
              模型未训练，显示原始排序
            </div>
            <div class="flex flex-wrap gap-2 mt-2">
              <div
                v-for="(stock, i) in topScoredStocks.slice(0, 10)"
                :key="stock.ts_code"
                class="bg-white border border-purple-200 rounded-lg px-2 py-1.5 min-w-[200px] cursor-pointer hover:shadow-sm transition-shadow"
                @click="selectStock(stock.ts_code, stock.name)"
              >
                <div class="flex items-center justify-between gap-2">
                  <div class="text-2xs text-purple-600 font-mono">#{{ i + 1 }}</div>
                  <div
                    class="px-1.5 py-0.5 rounded text-[10px] font-semibold"
                    :class="{
                      'bg-purple-100 text-purple-700': stock.lstm_mab_score?.grade === 'S',
                      'bg-green-100 text-green-700': stock.lstm_mab_score?.grade === 'A',
                      'bg-blue-100 text-blue-700': stock.lstm_mab_score?.grade === 'B',
                      'bg-gray-100 text-gray-700': !stock.lstm_mab_score?.grade || stock.lstm_mab_score?.grade === 'C'
                    }"
                  >
                    {{ stock.lstm_mab_score?.grade || '-' }}级
                  </div>
                </div>
                <div class="text-sm font-semibold text-warmgray-900 truncate mt-0.5">
                  {{ stock.name || stock.ts_code }}
                </div>
                <div class="flex items-center gap-2 mt-0.5">
                  <div class="text-2xs text-purple-700 font-medium">
                    评分: {{ stock.lstm_mab_score?.total_score?.toFixed(1) || '-' }}
                  </div>
                  <div class="text-2xs text-warmgray-500">
                    预期: {{ stock.lstm_mab_score?.expected_return?.toFixed ? `${stock.lstm_mab_score.expected_return.toFixed(1)}%` : '-' }}
                  </div>
                </div>
                <div v-if="stock.buy_signal" class="flex items-center gap-1 mt-0.5">
                  <span class="text-2xs px-1 py-0.5 rounded bg-emerald-50 text-emerald-700">
                    {{ stock.buy_signal.signal_type }}
                  </span>
                  <span class="text-2xs text-warmgray-500">{{ stock.buy_signal.strength_score }}分</span>
                </div>
                <div class="text-2xs text-warmgray-400 mt-0.5">
                  {{ stock.is_space && stock.is_new ? '空间+刚启动' : stock.is_space ? '空间龙头' : '刚启动' }}
                  <span v-if="stock.continuous_limit">· 连板{{ stock.continuous_limit }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 评分按钮 -->
          <div v-if="!topScoredStocks.length && !isScoring" class="flex justify-end mb-2">
            <button
              type="button"
              class="px-3 py-1.5 rounded-md text-2xs font-medium bg-purple-600 text-white hover:bg-purple-700 disabled:opacity-50 flex items-center gap-1"
              @click="fetchTopScored"
              :disabled="isScoring"
            >
              <span>🤖</span>
              <span>AI智能评分</span>
            </button>
          </div>
          <div class="text-2xs text-warmgray-500 border-b border-warmgray-200 pb-1 mb-2 grid grid-cols-[28px_36px_minmax(100px,1fr)_minmax(160px,1.35fr)_minmax(76px,0.55fr)_minmax(56px,0.45fr)_48px_52px_52px_52px_64px_72px_minmax(90px,0.9fr)_minmax(70px,0.75fr)_minmax(80px,0.7fr)_minmax(100px,1fr)_minmax(60px,0.6fr)] gap-x-0 gap-y-1 items-center">
            <div class="text-center">序号</div>
            <div class="text-center">自选</div>
            <div>名称 / 代码 / 类型</div>
            <div>主题 / 板块</div>
            <div
              class="text-left pl-0.5"
              title="优先为首次写入持久跟踪池的数据库时间；无记录时回退为首次空间/刚启动信号日；仅当日雷达未入库显示为 —"
            >
              入库时间
            </div>
            <button
              type="button"
              class="text-center flex items-center justify-center gap-1"
              @click="toggleSort('aiScore')"
              title="LSTM-MAB AI智能评分"
            >
              <span>AI评分</span>
              <span v-if="sortKey === 'aiScore'" class="text-[10px] text-warmgray-500">
                {{ sortOrder === 'desc' ? '↓' : '↑' }}
              </span>
            </button>
            <button
              type="button"
              class="text-right flex items-center justify-end gap-1"
              @click="toggleSort('pctToday')"
            >
              <span>今日涨幅</span>
              <span v-if="sortKey === 'pctToday'" class="text-[10px] text-warmgray-500">
                {{ sortOrder === 'desc' ? '↓' : '↑' }}
              </span>
            </button>
            <button
              type="button"
              class="text-right flex items-center justify-end gap-1"
              @click="toggleSort('pct20d')"
            >
              <span>近20日涨幅</span>
              <span v-if="sortKey === 'pct20d'" class="text-[10px] text-warmgray-500">
                {{ sortOrder === 'desc' ? '↓' : '↑' }}
              </span>
            </button>
            <button
              type="button"
              class="text-right flex items-center justify-end gap-1"
              @click="toggleSort('pct60d')"
            >
              <span>近60日涨幅</span>
              <span v-if="sortKey === 'pct60d'" class="text-[10px] text-warmgray-500">
                {{ sortOrder === 'desc' ? '↓' : '↑' }}
              </span>
            </button>
            <button
              type="button"
              class="text-right flex items-center justify-end gap-1"
              @click="toggleSort('dd20')"
            >
              <span>20日最大回撤</span>
              <span v-if="sortKey === 'dd20'" class="text-[10px] text-warmgray-500">
                {{ sortOrder === 'asc' ? '↑' : '↓' }}
              </span>
            </button>
            <div class="text-right">成交额</div>
            <div class="text-right">历史5日(均值/胜率)</div>
            <div class="text-right">历史10日均值</div>
            <div
              class="text-center"
              title="仅按库中最新日线判断：右侧接力 / 缩量回踩 / 刚启动。每只股票首次算出买点后会锁定，刷新数据不再改判；退潮风险仍不显示买点；该股离开本页龙头列表后锁定清除。"
            >
              买点
            </div>
            <div class="text-center">状态</div>
            <div class="text-center">20日线图</div>
            <div class="text-right">收盘价</div>
          </div>
          <div v-if="leaderRows.length === 0" class="text-xs text-warmgray-500">暂无数据。</div>
          <div v-else class="space-y-1 pr-1">
            <div class="min-h-[320px]">
            <button
              v-for="(row, index) in leaderRowsPaged"
              :key="row.ts_code"
              type="button"
              class="w-full text-left px-1 py-1.5 rounded-lg text-xs grid grid-cols-[28px_36px_minmax(100px,1fr)_minmax(160px,1.35fr)_minmax(76px,0.55fr)_minmax(56px,0.45fr)_48px_52px_52px_52px_64px_72px_minmax(90px,0.9fr)_minmax(70px,0.75fr)_minmax(80px,0.7fr)_minmax(100px,1fr)_minmax(60px,0.6fr)] gap-x-0 gap-y-1 items-center"
              :class="selectedTsCode === row.ts_code
                ? 'bg-indigo-50 border border-indigo-200'
                : 'hover:bg-warmgray-50 border border-transparent'"
              :data-testid="'leader-row-' + row.ts_code"
              @click="selectStock(row.ts_code, row.name)"
            >
              <div class="text-center text-2xs text-warmgray-500 uppercase font-mono text-[11px]">
                {{ (currentPage - 1) * PAGE_SIZE + index + 1 }}
              </div>
              <div class="flex justify-center">
                <span
                  class="text-[11px] cursor-pointer"
                  :class="isPinned(row.ts_code) ? 'text-yellow-500' : '--text-warmgray-500'"
                  @click.stop="togglePin(row.ts_code)"
                >
                  {{ isPinned(row.ts_code) ? '★' : '☆' }}
                </span>
              </div>
              <div class="flex flex-col min-w-0 space-y-0.5">
                <div class="flex items-center gap-1 min-w-0">
                  <span class="font-semibold truncate">{{ row.name || row.ts_code }}</span>
                  <button
                    type="button"
                    class="ml-1 px-1.5 py-0.5 rounded text-[10px] border"
                    :class="trackingPoolPlain[row.ts_code] ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-white text-2xs text-warmgray-500 uppercase border-warmgray-200'"
                    @click.stop="toggleTrack(row)"
                    :title="trackingPoolPlain[row.ts_code]?.reason || trackReasonForRow(row)"
                  >
                    {{ trackingPoolPlain[row.ts_code] ? '已跟踪' : '跟踪' }}
                  </button>
                </div>
                <div class="flex items-center gap-1 min-w-0">
                  <span class="font-mono text-[11px] text-2xs text-warmgray-500 uppercase truncate">{{ row.ts_code }}</span>
                  <span
                    v-if="row.is_space && row.is_new"
                    class="inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-semibold bg-purple-50 text-purple-700 flex-shrink-0"
                  >
                    空间+刚启动
                  </span>
                  <span
                    v-else-if="row.is_space"
                    class="inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-semibold bg-amber-50 text-amber-700 flex-shrink-0"
                  >
                    空间龙头
                  </span>
                  <span
                    v-else-if="row.is_new"
                    class="inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-semibold bg-rose-50 text-rose-700 flex-shrink-0"
                  >
                    刚启动
                  </span>
                </div>
                <div class="flex flex-wrap gap-1 text-[10px] text-2xs text-warmgray-500 uppercase">
                  <span v-if="row.continuous_limit != null">
                    连板: {{ row.continuous_limit }}
                  </span>
                  <span v-if="row.sectors && row.sectors.length">
                    主线数: {{ row.sectors.length }}
                  </span>
                  <span v-if="row.last_seen_date" class="text-indigo-600/90" title="系统最近一次将该股记入龙头信号池的交易日">
                    末次信号: {{ row.last_seen_date }}
                  </span>
                  <span v-if="rowStatsPlain[row.ts_code]?.isHigh20">
                    20日新高
                  </span>
                  <span v-else-if="rowStatsPlain[row.ts_code]?.fromHigh20Text">
                    距20日高点: {{ rowStatsPlain[row.ts_code].fromHigh20Text }}
                  </span>
                  <span v-if="rowStatsPlain[row.ts_code]?.amountRatio5_20Text">
                    量能: {{ rowStatsPlain[row.ts_code].amountRatio5_20Text }}
                  </span>
                </div>
              </div>
              <div class="space-y-0.5 min-w-0">
                <div
                  v-for="(sectorRow, sIdx) in chunkSectors(row.sectors)"
                  :key="sIdx"
                  class="flex flex-wrap gap-x-1 gap-y-0.5"
                >
                  <span
                    v-for="sector in sectorRow"
                    :key="sector"
                    class="inline-flex px-1.5 py-0.5 rounded text-[11px] bg-slate-50 text-slate-700 whitespace-nowrap"
                  >
                    {{ sector }}
                  </span>
                </div>
              </div>
              <div
                class="text-left text-[10px] text-warmgray-500 leading-snug pl-0.5 min-w-0"
                :title="poolInTimeTitle(row)"
              >
                {{ formatPoolInTime(row) }}
              </div>
              <!-- AI评分 -->
              <div class="text-center" title="LSTM-MAB AI智能评分">
                <div
                  v-if="row.lstm_mab_score"
                  class="inline-flex flex-col items-center"
                >
                  <span
                    class="px-1.5 py-0.5 rounded text-[10px] font-semibold"
                    :class="{
                      'bg-purple-100 text-purple-700': row.lstm_mab_score?.grade === 'S',
                      'bg-green-100 text-green-700': row.lstm_mab_score?.grade === 'A',
                      'bg-blue-100 text-blue-700': row.lstm_mab_score?.grade === 'B',
                      'bg-gray-100 text-gray-700': !row.lstm_mab_score?.grade || row.lstm_mab_score?.grade === 'C'
                    }"
                  >
                    {{ row.lstm_mab_score?.grade || '-' }}
                  </span>
                  <span class="text-[10px] text-purple-700 mt-0.5">
                    {{ row.lstm_mab_score?.total_score?.toFixed ? row.lstm_mab_score.total_score.toFixed(0) : '-' }}
                  </span>
                </div>
                <span v-else class="text-[10px] text-warmgray-400">-</span>
              </div>
              <div class="text-right" title="新浪实时">
                <span
                  v-if="realtimeQuotesMap[row.ts_code]?.pct_chg != null"
                  class="text-xs font-medium"
                  :class="(realtimeQuotesMap[row.ts_code].pct_chg ?? 0) > 0
                    ? 'text-loss'
                    : (realtimeQuotesMap[row.ts_code].pct_chg ?? 0) < 0
                      ? 'text-profit'
                      : 'text-warmgray-500'"
                >
                  {{ (realtimeQuotesMap[row.ts_code].pct_chg >= 0 ? '+' : '') + Number(realtimeQuotesMap[row.ts_code].pct_chg).toFixed(2) }}%
                </span>
                <span v-else class="--text-warmgray-500">--</span>
              </div>
              <div class="text-right">
                <span
                  v-if="rowStatsPlain[row.ts_code]?.pct20dText"
                  class="text-xs"
                  :class="(rowStatsPlain[row.ts_code]?.pct20d ?? 0) > 0
                    ? 'text-loss'
                    : (rowStatsPlain[row.ts_code]?.pct20d ?? 0) < 0
                      ? 'text-profit'
                      : 'text-warmgray-500'"
                >
                  {{ rowStatsPlain[row.ts_code].pct20dText }}
                </span>
                <span v-else class="--text-warmgray-500">--</span>
              </div>
              <div class="text-right">
                <span
                  v-if="rowStatsPlain[row.ts_code]?.pct60dText"
                  class="text-xs"
                  :class="(rowStatsPlain[row.ts_code]?.pct60d ?? 0) > 0
                    ? 'text-loss'
                    : (rowStatsPlain[row.ts_code]?.pct60d ?? 0) < 0
                      ? 'text-profit'
                      : 'text-warmgray-500'"
                >
                  {{ rowStatsPlain[row.ts_code].pct60dText }}
                </span>
                <span v-else class="--text-warmgray-500">--</span>
              </div>
              <div class="text-right">
                <span
                  v-if="rowStatsPlain[row.ts_code]?.maxDrawdown20Text"
                  class="text-xs"
                  :class="(rowStatsPlain[row.ts_code]?.maxDrawdown20 ?? 0) <= -15
                    ? 'text-loss'
                    : (rowStatsPlain[row.ts_code]?.maxDrawdown20 ?? 0) <= -5
                      ? 'text-warning'
                      : 'text-profit'"
                >
                  {{ rowStatsPlain[row.ts_code].maxDrawdown20Text }}
                </span>
                <span v-else class="--text-warmgray-500">--</span>
              </div>
              <div class="text-right">
                <span
                  v-if="rowStatsPlain[row.ts_code]?.lastAmountEText"
                  class="text-xs text-warmgray-600"
                >
                  {{ rowStatsPlain[row.ts_code].lastAmountEText }}
                </span>
                <span v-else class="--text-warmgray-500">--</span>
              </div>
              <div class="text-right">
                <span
                  v-if="getRowBacktest(row)"
                  class="text-xs text-warmgray-600"
                >
                  {{ formatPct(getRowBacktest(row).ret_5d_avg) }} / {{ formatPct(getRowBacktest(row).ret_5d_win_rate) }}
                </span>
                <span v-else class="--text-warmgray-500">--</span>
              </div>
              <div class="text-right">
                <span
                  v-if="getRowBacktest(row)"
                  class="text-xs text-warmgray-600"
                >
                  {{ formatPct(getRowBacktest(row).ret_10d_avg) }}
                </span>
                <span v-else class="--text-warmgray-500">--</span>
              </div>
              <div class="text-center">
                <span
                  v-if="buyPointMap[row.ts_code]?.type"
                  class="inline-flex flex-col items-center px-1.5 py-0.5 rounded text-[10px] font-medium"
                  :class="{
                    'bg-amber-50 text-amber-700': true,
                    'bg-indigo-50 text-indigo-700': ['右侧接力', '断板反包'].includes(buyPointMap[row.ts_code].type),
                    'bg-sky-50 text-sky-700': ['缩量回踩', '龙头首阴', '分时低吸'].includes(buyPointMap[row.ts_code].type),
                    'bg-emerald-50 text-emerald-700': ['首板放量', '二板缩量', '三板换手', '刚启动'].includes(buyPointMap[row.ts_code].type)
                  }"
                  :title="buyPointMap[row.ts_code]?.confidence || ''"
                >
                  {{ buyPointMap[row.ts_code].type }}
                  <span v-if="buyPointMap[row.ts_code]?.strength_score" class="text-[9px] opacity-80">
                    {{ buyPointMap[row.ts_code].strength_score }}分
                  </span>
                </span>
                <span v-else class="--text-warmgray-500">--</span>
              </div>
              <div class="text-center" :title="(rowStatsPlain[row.ts_code]?.retreat_reasons || []).join('；')">
                <span
                  v-if="rowStatsPlain[row.ts_code]?.retreat_label"
                  class="inline-flex px-1.5 py-0.5 rounded text-[10px] font-medium"
                  :class="rowStatsPlain[row.ts_code].retreat_label === '退潮风险'
                    ? 'bg-red-50 text-red-700'
                    : rowStatsPlain[row.ts_code].retreat_label === '强势'
                      ? 'bg-green-50 text-green-700'
                      : 'bg-amber-50 text-amber-700'"
                >
                  {{ rowStatsPlain[row.ts_code].retreat_label }}
                </span>
                <span v-else class="--text-warmgray-500">--</span>
              </div>
              <div>
                <MiniKLine
                  :ts-code="row.ts_code"
                  :points="rowKlinesPlain[row.ts_code] || []"
                />
              </div>
              <div class="text-right">
                <span
                  v-if="rowStatsPlain[row.ts_code]?.lastClose != null"
                  class="text-xs text-warmgray-600"
                >
                  {{ rowStatsPlain[row.ts_code].lastClose.toFixed(2) }}
                </span>
                <span v-else class="--text-warmgray-500">--</span>
              </div>
            </button>
            </div>
            <!-- 翻页：仅当总数 > 10 时显示 -->
            <div
              v-if="leaderRows.length > PAGE_SIZE"
              class="mt-3 pt-3 border-t border-warmgray-200-light flex items-center justify-between text-xs text-warmgray-500"
            >
              <span>共 {{ leaderRows.length }} 只</span>
              <div class="flex items-center gap-2">
                <button
                  type="button"
                  class="px-2 py-1 rounded border border-warmgray-200 hover:bg-warmgray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                  :disabled="currentPage <= 1"
                  @click="currentPage = Math.max(1, currentPage - 1)"
                >
                  上一页
                </button>
                <span class="min-w-[80px] text-center">第 {{ currentPage }} / {{ totalPages }} 页</span>
                <button
                  type="button"
                  class="px-2 py-1 rounded border border-warmgray-200 hover:bg-warmgray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                  :disabled="currentPage >= totalPages"
                  @click="currentPage = Math.min(totalPages, currentPage + 1)"
                >
                  下一页
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- 股票详情抽屉 -->
  <Teleport to="body">
    <div v-if="drawerOpen" class="fixed inset-0 z-[60]">
      <!-- 遮罩 -->
      <div
        class="absolute inset-0 bg-black/40 transition-opacity"
        @click="closeDrawer"
      />
      <!-- 抽屉面板 -->
      <div
        class="absolute right-0 top-0 h-full w-full max-w-md bg-white shadow-2xl transform transition-transform duration-300 ease-out flex flex-col translate-x-0"
      >
        <div class="flex items-center justify-between px-4 py-3 border-b border-warmgray-200">
          <h3 class="text-base font-semibold text-warmgray-900">
            {{ drawerStock?.name || selectedName || '股票详情' }}
          </h3>
          <button
            type="button"
            class="text-warmgray-500 hover:text-warmgray-900"
            @click="closeDrawer"
          >
            ✕
          </button>
        </div>
        <div class="flex-1 overflow-y-auto p-4 space-y-4">
          <div v-if="drawerLoading" class="text-sm text-warmgray-500">加载中...</div>
          <div v-else-if="drawerError" class="text-sm text-loss">{{ drawerError }}</div>
          <div v-else-if="drawerStock" class="space-y-4" data-testid="drawer-content">
            <div class="flex items-center justify-between">
              <div>
                <div class="text-2xl font-bold text-warmgray-900">{{ drawerStock.latest_price != null ? drawerStock.latest_price.toFixed(2) : '-' }}</div>
                <div class="text-sm" :class="drawerStock.price_change_pct >= 0 ? 'text-profit' : 'text-loss'">
                  {{ drawerStock.price_change_pct >= 0 ? '+' : '' }}{{ drawerStock.price_change_pct != null ? drawerStock.price_change_pct.toFixed(2) : '-' }}%
                </div>
              </div>
              <div v-if="drawerStock.lstm_mab_score" class="text-right">
                <div class="text-xl font-bold">{{ drawerStock.lstm_mab_score.total_score != null ? drawerStock.lstm_mab_score.total_score.toFixed(0) : '-' }}</div>
                <div class="text-xs">{{ drawerStock.lstm_mab_score.grade || 'D' }}级</div>
              </div>
            </div>
            <div v-if="drawerStock.buy_signal" class="bg-warmgray-50 rounded-lg p-3 space-y-1">
              <div class="text-xs text-warmgray-500">买点信号</div>
              <div class="text-sm font-medium text-cta">{{ drawerStock.buy_signal.signal_type }}</div>
            </div>
            <div v-if="drawerStock.sector_support" class="flex justify-between text-sm">
              <span class="text-warmgray-500">板块支持</span>
              <span class="font-medium">{{ drawerStock.sector_support.name }} (强度 {{ drawerStock.sector_support.strength }})</span>
            </div>
            <div v-if="drawerStock.trade_plan" class="bg-warmgray-50 rounded-lg p-3 space-y-2 text-sm">
              <div class="flex justify-between">
                <span class="text-warmgray-500">建仓价</span>
                <span class="font-medium">{{ drawerStock.trade_plan.entry_price != null ? drawerStock.trade_plan.entry_price.toFixed(2) : '-' }}</span>
              </div>
              <div class="flex justify-between">
                <span class="text-warmgray-500">止损价</span>
                <span class="font-medium text-loss">{{ drawerStock.trade_plan.stop_loss_price != null ? drawerStock.trade_plan.stop_loss_price.toFixed(2) : '-' }}</span>
              </div>
              <div class="flex justify-between">
                <span class="text-warmgray-500">止盈1</span>
                <span class="font-medium text-profit">{{ drawerStock.trade_plan.take_profit_1 != null ? drawerStock.trade_plan.take_profit_1.toFixed(2) : '-' }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import axios from 'axios'
import * as echarts from 'echarts'
import { ExclamationCircleIcon } from '@heroicons/vue/24/outline'
import MiniKLine from '../../components/MiniKLine.vue'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

const router = useRouter()
const route = useRoute()

const loading = ref(false)
const error = ref(null)
const sectors = ref([])
const spaceLeadersLead = ref([])
const apiDebugInfo = ref({}) // API 调试信息
// 永久入库后的龙头跟踪池成员（后端持久化）
const poolLeaders = ref([])

// 左侧筛选
const keyword = ref('')
const onlyMultiSectors = ref(false)
const retreatFilter = ref('') // '' | '强势' | '震荡' | '退潮风险'
const leaderTypeFilter = ref('') // '' | 'space' | 'new'
const amountFilter = ref('') // '' | '1' | '2' | '5' | '10'（单位：亿元）
const onlyBuyCandidates = ref(false) // 是否只看买点候选
const minStrength = ref(4) // 仅用于 leader-buy-backtest 汇总 API，与当日雷达主线 Top10（强度>5）无关
/** 默认开启：默认排序下强势/震荡在前、退潮在后，避免长线龙头沉到后页 */
const prioritizeTrendAlive = ref(true)
/** 默认仅展示趋势未断：隐藏退潮风险（无日线统计时仍显示，避免空白） */
const onlyTrendAlive = ref(true)

// 自选标的（本地存储）
const pinnedCodes = ref([])

// 跟踪池（本地存储，记录理由）
const trackingPool = ref({}) // { [ts_code]: { reason: string, ts_code: string, name?: string } }

// 行级日线数据与统计
const rowKlines = ref({})
const rowStats = ref({})
const rowStatsPlain = computed(() => rowStats.value || {})
const rowKlinesPlain = computed(() => rowKlines.value || {})

// 今日实时涨幅（新浪）
const realtimeQuotesMap = ref({})

// LSTM-MAB 智能评分
const isScoring = ref(false)
const topScoredStocks = ref([])
const scoringError = ref(null)
const modelAvailable = ref(false)
const currentEmotionCycle = ref('')

// 龙头跟踪系统健康分数
const healthData = ref(null)
const healthLoading = ref(false)

// 判断是否为 ST / *ST 股票（根据名称前缀）
const isSTStockName = (name) => {
  if (!name) return false
  const n = String(name).toUpperCase().trim()
  return n.startsWith('ST') || n.startsWith('*ST')
}

const chunkSectors = (sectors) => {
  const res = []
  const list = sectors || []
  for (let i = 0; i < list.length; i += 4) {
    res.push(list.slice(i, i + 4))
  }
  return res
}

/** 与 StartupMainlineRadarView「filteredSectors」完全一致：强度 &gt; 5，再取前 10 */
const MIN_MAINLINE_STRENGTH_RADAR = 5
const filteredSectorsRadar = computed(() => {
  const list = (sectors.value || []).filter((x) => Number(x.strength_score || 0) > MIN_MAINLINE_STRENGTH_RADAR)
  list.sort((a, b) => (b.strength_score || 0) - (a.strength_score || 0))
  return list.slice(0, 10)
})
const topSectorKeys = computed(() => new Set((filteredSectorsRadar.value || []).map((s) => s.sector_key)))

const trackingPoolPlain = computed(() => trackingPool.value || {})

const trackReasonForRow = (row) => {
  if (!row) return ''
  const isSpace = !!row.is_space
  const isNew = !!row.is_new
  if (isSpace && isNew) return '空间龙头 + 刚启动'
  if (isNew) return '刚启动'
  if (isSpace) return '空间龙头'
  return '其他'
}

/** 入库时间展示：DB created_at 优先，否则取与类型相关的最早 first_* 信号日 */
const formatPoolInTime = (row) => {
  if (!row) return '—'
  if (row.pool_created_at) {
    const s = String(row.pool_created_at)
    if (s.length >= 16) return `${s.slice(0, 10)} ${s.slice(11, 16)}`
    return s
  }
  const cands = []
  if (row.is_space && row.first_space_date) cands.push(String(row.first_space_date))
  if (row.is_new && row.first_new_date) cands.push(String(row.first_new_date))
  if (cands.length) return `${cands.sort()[0].slice(0, 10)} 信号`
  return '—'
}

const poolInTimeTitle = (row) => {
  if (!row) return ''
  const parts = []
  if (row.pool_created_at) parts.push(`写入池: ${row.pool_created_at}`)
  if (row.first_space_date) parts.push(`首次空间: ${row.first_space_date}`)
  if (row.first_new_date) parts.push(`首次刚启动: ${row.first_new_date}`)
  if (row.last_seen_date) parts.push(`末次信号: ${row.last_seen_date}`)
  if (!row.pool_created_at && !row.first_space_date && !row.first_new_date) {
    parts.push('未写入持久池（可能仅当日雷达）')
  }
  return parts.join('\n')
}

const buildWatchlistNoteForRow = (row) => {
  const reason = trackReasonForRow(row)
  return `龙头跟踪-${reason}`
}

// 按股票聚合：空间龙头（所有板块，不限于前10主线）
const spaceLeadersByStock = computed(() => {
  const byCode = new Map()
  // 显示所有空间龙头，不限于前10主线板块
  for (const item of spaceLeadersLead.value || []) {
    for (const stock of item.stocks || []) {
      const tc = stock.ts_code
      if (!tc) continue
      if (!byCode.has(tc)) {
        const name = stock.name || tc
        if (isSTStockName(name)) continue
        byCode.set(tc, {
          ts_code: tc,
          name,
          sectors: [],
          continuous_limit: stock.continuous_limit ?? null,
          first_seen_date: stock.first_seen_date || null,
          last_seen_date: stock.last_seen_date || null,
        })
      }
      const info = byCode.get(tc)
      const name = stock.name || tc
      if (isSTStockName(name)) continue
      if (name && info.name === tc) info.name = name
      if (item.sector_name && !info.sectors.includes(item.sector_name)) {
        info.sectors.push(item.sector_name)
      }
      // 取当前快照中的最大连板数
      const cl = stock.continuous_limit ?? null
      if (cl != null && (info.continuous_limit == null || cl > info.continuous_limit)) {
        info.continuous_limit = cl
      }
      // 取最早的 first_seen_date 和最新的 last_seen_date
      if (stock.first_seen_date && (!info.first_seen_date || stock.first_seen_date < info.first_seen_date)) {
        info.first_seen_date = stock.first_seen_date
      }
      if (stock.last_seen_date && (!info.last_seen_date || stock.last_seen_date > info.last_seen_date)) {
        info.last_seen_date = stock.last_seen_date
      }
    }
  }
  const pinSet = new Set(pinnedCodes.value || [])
  return Array.from(byCode.values()).sort((a, b) => {
    const pa = pinSet.has(a.ts_code) ? 1 : 0
    const pb = pinSet.has(b.ts_code) ? 1 : 0
    if (pa !== pb) return pb - pa
    const na = (a.sectors || []).length
    const nb = (b.sectors || []).length
    if (nb !== na) return nb - na
    return (a.name || '').localeCompare(b.name || '', 'zh-CN')
  })
})

// 按股票聚合：刚启动龙头（所有板块，不限于前10主线）
const newLeadersByStock = computed(() => {
  const byCode = new Map()
  // 显示所有板块的刚启动龙头，不限于前10主线
  for (const s of sectors.value || []) {
    const chain = s.chain || []
    for (const c of chain) {
      if (!c.is_new_leader) continue
      const tc = c.ts_code
      if (!tc) continue
      if (!byCode.has(tc)) {
        const name = c.name || tc
        if (isSTStockName(name)) continue
        byCode.set(tc, {
          ts_code: tc,
          name,
          sectors: [],
          continuous_limit: c.continuous_limit ?? null,
          first_seen_date: c.first_seen_date || null,
          last_seen_date: c.last_seen_date || null,
        })
      }
      const info = byCode.get(tc)
      const name = c.name || tc
      if (isSTStockName(name)) continue
      if (name && info.name === tc) info.name = name
      if (s.sector_name && !info.sectors.includes(s.sector_name)) {
        info.sectors.push(s.sector_name)
      }
      // 取当前快照中的最大连板数
      const cl = c.continuous_limit ?? null
      if (cl != null && (info.continuous_limit == null || cl > info.continuous_limit)) {
        info.continuous_limit = cl
      }
      // 取最早的 first_seen_date 和最新的 last_seen_date
      if (c.first_seen_date && (!info.first_seen_date || c.first_seen_date < info.first_seen_date)) {
        info.first_seen_date = c.first_seen_date
      }
      if (c.last_seen_date && (!info.last_seen_date || c.last_seen_date > info.last_seen_date)) {
        info.last_seen_date = c.last_seen_date
      }
    }
  }
  const pinSet = new Set(pinnedCodes.value || [])
  return Array.from(byCode.values()).sort((a, b) => {
    const pa = pinSet.has(a.ts_code) ? 1 : 0
    const pb = pinSet.has(b.ts_code) ? 1 : 0
    if (pa !== pb) return pb - pa
    const na = (a.sectors || []).length
    const nb = (b.sectors || []).length
    if (nb !== na) return nb - na
    return (a.name || '').localeCompare(b.name || '', 'zh-CN')
  })
})

// 主线维度的历史回测表现（按 sector_key 聚合）
const sectorBacktestMap = ref({})

// AI 评分数据（所有股票的评分映射）
const stockScoreMap = ref({})

// 汇总成单一列表：一行一只股票（基础顺序）
// 合并持久池 + 当日雷达：避免池子尚未同步或库内记录少时，页面上只剩几条
const leaderRowsBase = computed(() => {
  const pinSet = new Set(pinnedCodes.value || [])
  const byCode = new Map()

  const upsert = (partial) => {
    const tc = partial.ts_code
    if (!tc) return
    const cur = byCode.get(tc)
    if (!cur) {
      byCode.set(tc, { ...partial })
      return
    }
    const sectors = new Set([...(cur.sectors || []), ...(partial.sectors || [])])
    const pickName = (a, b) => {
      const na = a && a !== tc ? a : null
      const nb = b && b !== tc ? b : null
      return nb || na || tc
    }
    byCode.set(tc, {
      ts_code: tc,
      name: pickName(cur.name, partial.name),
      sectors: Array.from(sectors).sort((x, y) => x.localeCompare(y, 'zh-CN')),
      is_space: !!(cur.is_space || partial.is_space),
      is_new: !!(cur.is_new || partial.is_new),
      continuous_limit: (cur.continuous_limit != null && partial.continuous_limit != null)
        ? Math.max(cur.continuous_limit, partial.continuous_limit)
        : (cur.continuous_limit ?? partial.continuous_limit ?? null),
      last_seen_date: cur.last_seen_date ?? partial.last_seen_date ?? null,
      first_space_date: cur.first_space_date ?? partial.first_space_date ?? null,
      first_new_date: cur.first_new_date ?? partial.first_new_date ?? null,
      pool_created_at: cur.pool_created_at ?? partial.pool_created_at ?? null,
      // 保留评分数据
      score: cur.score ?? partial.score ?? null,
      grade: cur.grade ?? partial.grade ?? null,
      lstm_mab_score: cur.lstm_mab_score ?? partial.lstm_mab_score ?? null,
    })
  }

  for (const r of poolLeaders.value || []) {
    upsert({
      ts_code: r.ts_code,
      name: r.name || r.ts_code,
      sectors: Array.isArray(r.sectors) ? r.sectors : [],
      is_space: !!r.is_space,
      is_new: !!r.is_new,
      continuous_limit: r.continuous_limit ?? null,
      last_seen_date: r.last_seen_date || null,
      first_space_date: r.first_space_date || null,
      first_new_date: r.first_new_date || null,
      pool_created_at: r.pool_created_at || null,
      // 传入评分数据
      score: r.score ?? null,
      grade: r.grade ?? null,
      lstm_mab_score: r.lstm_mab_score ?? null,
    })
  }
  for (const r of spaceLeadersByStock.value || []) {
    upsert({
      ts_code: r.ts_code,
      name: r.name || r.ts_code,
      sectors: Array.isArray(r.sectors) ? r.sectors : [],
      is_space: true,
      is_new: false,
      continuous_limit: r.continuous_limit ?? null,
      last_seen_date: r.last_seen_date || null,
      first_space_date: r.first_seen_date || null,
    })
  }
  for (const r of newLeadersByStock.value || []) {
    upsert({
      ts_code: r.ts_code,
      name: r.name || r.ts_code,
      sectors: Array.isArray(r.sectors) ? r.sectors : [],
      is_space: false,
      is_new: true,
      continuous_limit: r.continuous_limit ?? null,
      last_seen_date: r.last_seen_date || null,
      first_new_date: r.first_seen_date || null,
    })
  }

  const arr = Array.from(byCode.values())
  arr.sort((a, b) => {
    const pa = pinSet.has(a.ts_code) ? 1 : 0
    const pb = pinSet.has(b.ts_code) ? 1 : 0
    if (pa !== pb) return pb - pa
    // 方案A：连板数优先于主线数
    const cla = a.continuous_limit ?? -1
    const clb = b.continuous_limit ?? -1
    if (clb !== cla) return clb - cla
    const na = (a.sectors || []).length
    const nb = (b.sectors || []).length
    if (nb !== na) return nb - na
    return (a.name || '').localeCompare(b.name || '', 'zh-CN')
  })
  return arr
})

// 今日真龙头：从当前龙头列表（空间+刚启动）中选出 Top3
const dailyTrueDragons = computed(() => {
  const base = leaderRowsBase.value || []
  if (!base.length) return []
  const stats = rowStatsPlain.value || {}
  const klinesMap = rowKlinesPlain.value || {}
  const bpFresh = buyPointMapFresh.value || {}

  const toNum = (v) => {
    if (v == null) return null
    const n = Number(v)
    return Number.isFinite(n) ? n : null
  }

  const fmtRange2 = (low, high) => {
    const l = low != null && Number.isFinite(low) ? low.toFixed(2) : '--'
    const h = high != null && Number.isFinite(high) ? high.toFixed(2) : '--'
    if (l === '--' || h === '--') return '--'
    return `${l}~${h}`
  }

  const calcBuyPriceRange = (code, buyType) => {
    const pts = klinesMap[code] || []
    if (!pts || pts.length < 2) return null

    const prevClose = toNum(pts[pts.length - 2]?.close)
    const firstClose = toNum(pts[0]?.close)
    const lastClose = toNum(pts[pts.length - 1]?.close)
    const ma20 = toNum(pts[pts.length - 1]?.ma20)
    const closes = pts.map((p) => toNum(p?.close)).filter((v) => v != null)
    const maxClose20 = closes.length ? Math.max(...closes) : null

    const ranges = []
    const addRange = (a, b) => {
      const lo = a != null ? a : null
      const hi = b != null ? b : null
      if (lo == null || hi == null || !Number.isFinite(lo) || !Number.isFinite(hi)) return
      const low = Math.min(lo, hi)
      const high = Math.max(lo, hi)
      ranges.push([low, high])
    }

    if (buyType === 'breakout') {
      // 来自 pctToday：(+5%~+11%)
      addRange(prevClose != null ? prevClose * 1.05 : null, prevClose != null ? prevClose * 1.11 : null)
      // 来自 fromHigh20：(-7%~+1%)
      addRange(maxClose20 != null ? maxClose20 * 0.93 : null, maxClose20 != null ? maxClose20 * 1.01 : null)
    } else if (buyType === 'pullback') {
      // 来自 fromHigh20：(-15%~-3%)
      addRange(maxClose20 != null ? maxClose20 * 0.85 : null, maxClose20 != null ? maxClose20 * 0.97 : null)
      // 来自 pctToday：(-2%~+4%)
      addRange(prevClose != null ? prevClose * 0.98 : null, prevClose != null ? prevClose * 1.04 : null)
      // 来自 nearMa20：|close/ma20-1|<=4%
      if (ma20 != null && ma20 > 0) addRange(ma20 * 0.96, ma20 * 1.04)
    } else if (buyType === 'first_move') {
      // 来自 pctToday：(+7%~+11%)
      addRange(prevClose != null ? prevClose * 1.07 : null, prevClose != null ? prevClose * 1.11 : null)
      // 来自 pct20d：(+10%~+40%)
      addRange(firstClose != null ? firstClose * 1.1 : null, firstClose != null ? firstClose * 1.4 : null)
    }

    if (!ranges.length) return null
    const low = Math.max(...ranges.map((r) => r[0]))
    const high = Math.min(...ranges.map((r) => r[1]))
    if (!Number.isFinite(low) || !Number.isFinite(high) || low > high) {
      // 如果交集为空，返回更宽松的第一段（避免显示 '--'）
      return fmtRange2(ranges[0][0], ranges[0][1])
    }
    return fmtRange2(low, high)
  }

  let candidates = base.filter((r) => r && (r.is_space || r.is_new))

  // 尊重当前页面“仅展示趋势未断”的开关：退潮风险不进入候选
  if (onlyTrendAlive.value) {
    candidates = candidates.filter((r) => stats[r.ts_code]?.retreat_label !== '退潮风险')
  }

  const recencyMs = (d) => {
    if (!d) return 0
    const t = Date.parse(String(d))
    return Number.isFinite(t) ? t : 0
  }

  const retreatTier = (ts) => {
    const lb = stats[ts]?.retreat_label
    if (!lb) return 2
    if (lb === '强势') return 0
    if (lb === '震荡') return 1
    if (lb === '退潮风险') return 3
    return 2
  }

  const cmp = (a, b) => {
    const ta = retreatTier(a.ts_code)
    const tb = retreatTier(b.ts_code)
    if (ta !== tb) return ta - tb

    // 方案A：连板数优先于主线数
    const cla = a.continuous_limit ?? -1
    const clb = b.continuous_limit ?? -1
    if (cla !== clb) return clb - cla

    const ma = (a.sectors || []).length
    const mb = (b.sectors || []).length
    if (ma !== mb) return mb - ma

    const aa = stats[a.ts_code]?.amountRatio5_20 ?? -1
    const ab = stats[b.ts_code]?.amountRatio5_20 ?? -1
    if (aa !== ab) return ab - aa

    const ra = recencyMs(a.last_seen_date)
    const rb = recencyMs(b.last_seen_date)
    if (ra !== rb) return rb - ra

    const da = stats[a.ts_code]?.fromHigh20 ?? -999
    const db = stats[b.ts_code]?.fromHigh20 ?? -999
    // fromHigh20 越接近 0 越好（例如 -2 比 -10 强）
    return db - da
  }

  const sorted = [...candidates].sort(cmp).slice(0, 3)

  return sorted.map((r) => {
    const st = stats[r.ts_code] || {}
    const cl = r.continuous_limit ?? 0
    const mainCount = (r.sectors || []).length
    const ar = st.amountRatio5_20Text || (st.amountRatio5_20 != null ? `${st.amountRatio5_20.toFixed(1)}x` : '--')
    const lastSeen = r.last_seen_date || '—'
    const buyType = bpFresh[r.ts_code]?.type ?? null
    const typeToLabel = (t) => {
      const map = {
        'breakout': '右侧接力',
        'pullback': '缩量回踩',
        'first_move': '刚启动',
        '首板放量': '首板放量',
        '二板缩量': '二板缩量',
        '三板换手': '三板换手',
        '断板反包': '断板反包',
        '龙头首阴': '龙头首阴',
        '分时低吸': '分时低吸'
      }
      return map[t] || '未触发'
    }
    const buyLabel = typeToLabel(buyType)

    let buyRange = '--'
    if (buyType) {
      const res = calcBuyPriceRange(r.ts_code, buyType)
      buyRange = res || '--'
    }

    let possibleText = null
    if (!buyType) {
      const pts = klinesMap[r.ts_code] || []
      if (pts.length >= 2) {
        const prevClose = toNum(pts[pts.length - 2]?.close)
        const close = toNum(pts[pts.length - 1]?.close)
        const pctToday = prevClose != null && prevClose !== 0 && close != null ? (close / prevClose - 1) * 100 : null
        const fromHigh20 = st.fromHigh20
        const pct20d = st.pct20d

        const within = (v, lo, hi) => v != null && v >= lo && v <= hi

        let possibleType = null
        if (within(pctToday, 5, 11) && within(fromHigh20, -7, 1)) possibleType = 'breakout'
        else if (within(fromHigh20, -15, -3) && within(pctToday, -2, 4)) possibleType = 'pullback'
        else if (within(pctToday, 7, 11) && within(pct20d, 10, 40)) possibleType = 'first_move'

        if (possibleType) {
          const range = calcBuyPriceRange(r.ts_code, possibleType) || '--'
          possibleText = `可能买点:${typeToLabel(possibleType)} | 参考价:${range}`
        }
      }
    }

    return {
      row: r,
      buyText: buyType ? `买点:${buyLabel} | 参考价:${buyRange}` : `买点:${buyLabel}`,
      possibleText,
      reason: `连板:${cl} / 主线数:${mainCount} / 量能:${ar} / 末次信号:${lastSeen}`,
    }
  })
})

// 排序状态
const sortKey = ref('default') // default | pct20d | pctToday | pct60d | dd20 | aiScore
const sortOrder = ref('desc') // asc | desc

// 买点「新鲜」判定：仅用库中最新日线；与 buyPointLockedByCode 合并后对外暴露
const buyPointMapFresh = computed(() => {
  const stats = rowStatsPlain.value || {}
  const klinesMap = rowKlinesPlain.value || {}
  const rows = leaderRowsBase.value || []
  const rowByCode = {}
  for (const r of rows) {
    if (r?.ts_code) rowByCode[r.ts_code] = r
  }
  const res = {}

  const pctLastBarFromDb = (code) => {
    const pts = klinesMap[code] || []
    if (pts.length < 2) return null
    const a = pts[pts.length - 2]
    const b = pts[pts.length - 1]
    const ca = a?.close
    const cb = b?.close
    if (ca == null || cb == null || Number(ca) === 0) return null
    return ((Number(cb) / Number(ca)) - 1) * 100
  }

  for (const code of Object.keys(stats)) {
    const st = stats[code]
    if (!st) continue

    if (st.retreat_label === '退潮风险') {
      res[code] = { type: null }
      continue
    }

    const close = st.lastClose
    const ma20 = st.lastMa20
    const diff20 =
      close != null && ma20 != null && ma20 > 0
        ? ((close / ma20) - 1) * 100
        : null

    const fromHigh20 = st.fromHigh20
    const pct20d = st.pct20d
    const pct60d = st.pct60d
    const maxDrawdown20 = st.maxDrawdown20
    const amountRatio5_20 = st.amountRatio5_20
    const lastAmountE = st.lastAmountE
    const pctToday = pctLastBarFromDb(code)

    const nearMa20 = diff20 != null && Math.abs(diff20) <= 4

    let isPullback = false
    if (
      fromHigh20 != null &&
      fromHigh20 <= -3 &&
      fromHigh20 >= -15 &&
      nearMa20 &&
      amountRatio5_20 != null &&
      amountRatio5_20 <= 1.0 &&
      pctToday != null &&
      pctToday >= -2 &&
      pctToday <= 4 &&
      (pctToday <= 0 ? amountRatio5_20 <= 0.8 : true)
    ) {
      isPullback = true
    }

    let isBreakout = false
    if (
      pct20d != null &&
      pct20d >= 30 &&
      fromHigh20 != null &&
      fromHigh20 >= -7 &&
      fromHigh20 <= 1 &&
      pctToday != null &&
      pctToday >= 5 &&
      pctToday <= 11 &&
      amountRatio5_20 != null &&
      amountRatio5_20 >= 1.2 &&
      lastAmountE != null &&
      lastAmountE >= 2
    ) {
      isBreakout = true
    }

    let isFirstMove = false
    if (
      pct20d != null &&
      pct20d >= 10 &&
      pct20d <= 40 &&
      pct60d != null &&
      pct60d <= 120 &&
      maxDrawdown20 != null &&
      maxDrawdown20 >= -20 &&
      pctToday != null &&
      pctToday >= 7 &&
      pctToday <= 11 &&
      amountRatio5_20 != null &&
      amountRatio5_20 >= 1.5
    ) {
      isFirstMove = true
    }

    let type = null
    if (isBreakout) type = 'breakout'
    else if (isPullback) type = 'pullback'
    else if (isFirstMove) type = 'first_move'

    const backendSignal = rowByCode[code]?.buy_signal
    if (backendSignal?.signal_type) {
      res[code] = {
        type: backendSignal.signal_type,
        strength_score: backendSignal.strength_score,
        confidence: backendSignal.confidence,
        suggested_position: backendSignal.suggested_position,
        source: 'backend',
      }
      continue
    }

    res[code] = { type }
  }

  return res
})

/** 已算出过的买点类型，刷新/K 线更新后不改判；随该股离开 leaderRowsBase 清除 */
const buyPointLockedByCode = ref({})

watch(
  buyPointMapFresh,
  (m) => {
    const cur = buyPointLockedByCode.value || {}
    const next = { ...cur }
    let changed = false
    for (const [code, v] of Object.entries(m || {})) {
      if (v?.type && !next[code]) {
        next[code] = v.type
        changed = true
      }
    }
    if (changed) buyPointLockedByCode.value = next
  },
  { deep: true },
)

const leaderTsCodesKey = computed(() =>
  (leaderRowsBase.value || [])
    .map((r) => r?.ts_code)
    .filter(Boolean)
    .sort()
    .join('\u0001'),
)

watch(leaderTsCodesKey, () => {
  const allowed = new Set(
    (leaderRowsBase.value || []).map((r) => r?.ts_code).filter(Boolean),
  )
  const cur = buyPointLockedByCode.value || {}
  const next = { ...cur }
  let changed = false
  for (const c of Object.keys(next)) {
    if (!allowed.has(c)) {
      delete next[c]
      changed = true
    }
  }
  if (changed) buyPointLockedByCode.value = next
})

const buyPointMap = computed(() => {
  const fresh = buyPointMapFresh.value || {}
  const locked = buyPointLockedByCode.value || {}
  const stats = rowStatsPlain.value || {}
  const res = {}
  const codes = new Set([...Object.keys(fresh), ...Object.keys(locked)])
  for (const code of codes) {
    if (stats[code]?.retreat_label === '退潮风险') {
      res[code] = { type: null }
      continue
    }
    const t = locked[code] || fresh[code]?.type || null
    res[code] = { type: t }
  }
  return res
})

const toggleSort = (key) => {
  if (sortKey.value === key) {
    if (sortOrder.value === 'desc') {
      sortOrder.value = 'asc'
    } else if (sortOrder.value === 'asc') {
      sortKey.value = 'default'
      sortOrder.value = 'desc'
    }
  } else {
    sortKey.value = key
    sortOrder.value = key === 'dd20' ? 'asc' : 'desc'
  }
}

// 应用排序后的最终列表
const leaderRows = computed(() => {
  const base = [...(leaderRowsBase.value || [])]
  // 合并 AI 评分到每行数据：优先使用后端返回的评分，没有则从 stockScoreMap 获取
  const withScores = base.map(row => ({
    ...row,
    lstm_mab_score: (row.lstm_mab_score?.total_score != null ? row.lstm_mab_score : null)
      || stockScoreMap.value[row.ts_code]
      || null
  }))
  // 历史票持续展示：只排除 ST/ *ST，避免回调后”空间/刚启动”候选瞬间消失
  let filtered = withScores.filter((r) => !isSTStockName(r.name || r.ts_code))
  const kw = keyword.value.trim()
  if (kw) {
    const lower = kw.toLowerCase()
    filtered = filtered.filter((r) => {
      const name = (r.name || '').toLowerCase()
      const code = (r.ts_code || '').toLowerCase()
      const sectorsText = (r.sectors || []).join(' ').toLowerCase()
      return name.includes(lower) || code.includes(lower) || sectorsText.includes(lower)
    })
  }
  if (onlyMultiSectors.value) {
    filtered = filtered.filter((r) => (r.sectors || []).length >= 2)
  }
  if (retreatFilter.value) {
    const stats = rowStatsPlain.value || {}
    filtered = filtered.filter((r) => stats[r.ts_code]?.retreat_label === retreatFilter.value)
  }
  if (leaderTypeFilter.value === 'space') {
    filtered = filtered.filter((r) => r.is_space)
  } else if (leaderTypeFilter.value === 'new') {
    filtered = filtered.filter((r) => r.is_new)
  }
  if (amountFilter.value) {
    const minE = Number(amountFilter.value)
    if (!Number.isNaN(minE)) {
      const stats = rowStatsPlain.value || {}
      filtered = filtered.filter((r) => {
        const st = stats[r.ts_code] || {}
        return st.lastAmountE != null && st.lastAmountE >= minE
      })
    }
  }
  if (onlyBuyCandidates.value) {
    const bpMap = buyPointMap.value || {}
    filtered = filtered.filter((r) => !!bpMap[r.ts_code]?.type)
  }
  if (onlyTrendAlive.value) {
    const stats = rowStatsPlain.value || {}
    filtered = filtered.filter((r) => {
      const lb = stats[r.ts_code]?.retreat_label
      if (!lb) return true
      return lb !== '退潮风险'
    })
  }
  const key = sortKey.value
  if (key === 'default') {
    if (!prioritizeTrendAlive.value) {
      return filtered
    }
    const statsMap = rowStatsPlain.value || {}
    const pinSet = new Set(pinnedCodes.value || [])
    const retreatTier = (ts) => {
      const lb = statsMap[ts]?.retreat_label
      if (!lb) return 2
      if (lb === '强势') return 0
      if (lb === '震荡') return 1
      if (lb === '退潮风险') return 3
      return 2
    }
    const sorted = [...filtered]
    sorted.sort((a, b) => {
      const pa = pinSet.has(a.ts_code) ? 1 : 0
      const pb = pinSet.has(b.ts_code) ? 1 : 0
      if (pa !== pb) return pb - pa
      const ta = retreatTier(a.ts_code)
      const tb = retreatTier(b.ts_code)
      if (ta !== tb) return ta - tb
      // 方案A：连板数优先于主线数
      const cla = a.continuous_limit ?? -1
      const clb = b.continuous_limit ?? -1
      if (clb !== cla) return clb - cla
      const na = (a.sectors || []).length
      const nb = (b.sectors || []).length
      if (nb !== na) return nb - na
      return (a.name || '').localeCompare(b.name || '', 'zh-CN')
    })
    return sorted
  }
  const order = sortOrder.value === 'asc' ? 1 : -1
  const statsMap = rowStatsPlain.value || {}
  const rtMap = realtimeQuotesMap.value || {}
  const pinSet = new Set(pinnedCodes.value || [])

  const baseCompare = (a, b) => {
    const pa = pinSet.has(a.ts_code) ? 1 : 0
    const pb = pinSet.has(b.ts_code) ? 1 : 0
    if (pa !== pb) return pb - pa
    // 方案A：连板数优先于主线数
    const cla = a.continuous_limit ?? -1
    const clb = b.continuous_limit ?? -1
    if (clb !== cla) return clb - cla
    const na = (a.sectors || []).length
    const nb = (b.sectors || []).length
    if (nb !== na) return nb - na
    return (a.name || '').localeCompare(b.name || '', 'zh-CN')
  }

  filtered.sort((a, b) => {
    const sa = statsMap[a.ts_code] || {}
    const sb = statsMap[b.ts_code] || {}
    let va = null
    let vb = null
    if (key === 'pct20d') {
      va = sa.pct20d
      vb = sb.pct20d
    } else if (key === 'pctToday') {
      va = rtMap[a.ts_code]?.pct_chg
      vb = rtMap[b.ts_code]?.pct_chg
    } else if (key === 'pct60d') {
      va = sa.pct60d
      vb = sb.pct60d
    } else if (key === 'dd20') {
      va = sa.maxDrawdown20 != null ? Math.abs(sa.maxDrawdown20) : null
      vb = sb.maxDrawdown20 != null ? Math.abs(sb.maxDrawdown20) : null
    } else if (key === 'aiScore') {
      va = a.lstm_mab_score?.total_score ?? null
      vb = b.lstm_mab_score?.total_score ?? null
    }
    if (va == null && vb == null) {
      return baseCompare(a, b)
    }
    if (va == null) return 1
    if (vb == null) return -1
    if (va === vb) {
      return baseCompare(a, b)
    }
    return va < vb ? -1 * order : 1 * order
  })
  return filtered
})

// 今日主线 + 龙头/买点概览（基于当前筛选条件）
const topTodaySectors = computed(() => {
  const secs = sectors.value || []
  if (!secs.length) return []
  const leaders = leaderRows.value || []
  const bpMap = buyPointMap.value || {}
  const btMap = sectorBacktestMap.value || {}
  const byKey = new Map()
  for (const s of secs) {
    if (!topSectorKeys.value.has(s.sector_key)) continue
    const bt = btMap[s.sector_key] || {}
    byKey.set(s.sector_key, {
      sector_key: s.sector_key,
      sector_name: s.sector_name || s.sector_key,
      strength_score: typeof s.strength_score === 'number' ? s.strength_score : 0,
      leader_count: 0,
      buy_count: 0,
      ret5_avg: bt.ret_5d_avg ?? null,
      ret5_win: bt.ret_5d_win_rate ?? null,
      ret10_avg: bt.ret_10d_avg ?? null,
      leaders: [],
      leaders_with_buy: [],
    })
  }
  if (!byKey.size) return []
  for (const row of leaders) {
    const codesBuy = bpMap[row.ts_code]
    const hasBuy = !!codesBuy?.type
    const rowSectors = row.sectors || []
    for (const secName of rowSectors) {
      for (const s of secs) {
        if (s.sector_name !== secName) continue
        const info = byKey.get(s.sector_key)
        if (!info) continue
        info.leader_count += 1
        if (hasBuy) info.buy_count += 1
        info.leaders.push({
          ts_code: row.ts_code,
          name: row.name || row.ts_code,
          hasBuy,
        })
        if (hasBuy) {
          info.leaders_with_buy.push({
            ts_code: row.ts_code,
            name: row.name || row.ts_code,
          })
        }
      }
    }
  }
  const items = Array.from(byKey.values())
    .filter((x) => x.leader_count > 0)
    .sort((a, b) => (b.strength_score || 0) - (a.strength_score || 0))
    .slice(0, 3)
  // 每条主线只展示前 3 个龙头名称
  items.forEach((x) => {
    x.leaders = (x.leaders || []).slice(0, 3)
  })
  return items
})

const PAGE_SIZE = 10
const currentPage = ref(1)
const totalPages = computed(() => {
  const total = leaderRows.value?.length ?? 0
  return total <= 0 ? 1 : Math.ceil(total / PAGE_SIZE)
})
const leaderRowsPaged = computed(() => {
  const list = leaderRows.value || []
  const start = (currentPage.value - 1) * PAGE_SIZE
  return list.slice(start, start + PAGE_SIZE)
})

// 筛选/排序变化时回到第一页
watch([() => leaderRows.value?.length, keyword, retreatFilter, leaderTypeFilter, onlyMultiSectors, amountFilter, onlyBuyCandidates, onlyTrendAlive, prioritizeTrendAlive, sortKey], () => {
  currentPage.value = 1
})

const selectedTsCode = ref('')
const selectedName = ref('')
const kline = ref([])

const chartRef = ref(null)
let chartInstance = null

const fetchData = async () => {
  loading.value = true
  error.value = null
  try {
    // 主线雷达榜单稳定性：同一天内固定 sector-strength 的结果，
    // 避免由于“今天数据更新/强度波动”导致空间龙头/刚启动榜单频繁消失重排
    const cacheKey = 'leader-tracking-sector-strength-cache-v2'
    const todayKey = new Date().toISOString().slice(0, 10)
    const forceRefresh = String(route.query?.refreshSectorStrength || route.query?.forceRefresh || '').trim() === '1'
    const historyDays = (() => {
      const raw = route.query?.leaderHistoryDays || route.query?.historyDays
      const n = Number(raw)
      // sector-strength 仅用于“主线强度/今日板块排名”，不再用于候选池持久化
      // 默认只拉到最近 5 天，减少返回体
      return Number.isFinite(n) && n > 0 ? Math.floor(n) : 5
    })()
    const startDt = new Date()
    startDt.setDate(startDt.getDate() - historyDays)
    const startDate = startDt.toISOString().slice(0, 10)
    const cachedRaw = window.localStorage.getItem(cacheKey)
    const cached = cachedRaw ? (() => { try { return JSON.parse(cachedRaw) } catch (e) { return null } })() : null
    const useCached = !forceRefresh && cached
      && cached.fetchedDate === todayKey
      && cached.start_date === startDate
      && cached.min_score === 60
      && cached.stage === 'confirmed'
      && cached.stable === true
      && cached.payload

    let data = {}
    const apiParams = { start_date: startDate, min_score: 60, stage: 'confirmed', stable: true }
    apiDebugInfo.value = { params: apiParams, cached: useCached, startDateUsed: startDate }
    if (useCached) {
      data = cached.payload || {}
    } else {
      const res = await axios.get(`${API_BASE_URL}/api/startup/sector-strength`, {
        params: apiParams,
      })
      data = res.data || {}
      apiDebugInfo.value.rawResponse = { success: data.success, sectorsCount: (data.sectors || []).length, spaceLeadersLeadCount: (data.space_leaders_lead || []).length }
      if (data && data.success !== false) {
        window.localStorage.setItem(
          cacheKey,
          JSON.stringify({
            fetchedDate: todayKey,
            start_date: startDate,
            min_score: 60,
            stage: 'confirmed',
            stable: true,
            payload: data,
          })
        )
      }
    }
    if (data.success === false) {
      error.value = data.message || '加载失败'
      sectors.value = []
      spaceLeadersLead.value = []
      poolLeaders.value = []
      return
    }
    sectors.value = data.sectors || []
    spaceLeadersLead.value = data.space_leaders_lead || []

    // 从后端“永久入库”的龙头跟踪池拉取成员（避免昨天有今天消失）
    const replayPool = String(route.query?.replayPoolSync || '').trim() === '1'
    const poolRes = await axios.get(`${API_BASE_URL}/api/leader-tracking/pool`, {
      params: {
        min_score: 60,
        stage: 'confirmed',
        stable_window_id: 'rolling_30d_v2',
        // 池为空时一次性 bootstrap 的历史跨度（与后端默认 180 对齐，便于找回更多历史龙头）
        bootstrap_days: 180,
        do_bootstrap: true,
        force_sync: false,
        catch_up_window_trading_days: 30,
        catch_up_max_syncs: 30,
        ...(replayPool ? { replay_sync_days: 30 } : {}),
      },
    })
    const poolData = poolRes.data || {}
    if (!poolData.success) {
      poolLeaders.value = []
    } else {
      poolLeaders.value = poolData.pool || []
    }

    await nextTick()
    await loadAllRowKlines()
    const codes = (leaderRows.value || []).map((r) => r.ts_code).filter(Boolean)
    if (codes.length) await loadRealtimeQuotes(codes)

    // 获取所有股票的 AI 评分（使用较大的 top_n 获取全部）
    await fetchAllStockScores()
    // 获取龙头跟踪系统健康分数
    await fetchHealthData()
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error(e)
    error.value = e?.response?.data?.detail || e?.message || '请求失败'
    sectors.value = []
    spaceLeadersLead.value = []
    poolLeaders.value = []
  } finally {
    loading.value = false
  }
}

// 获取龙头跟踪系统健康分数
const fetchHealthData = async () => {
  healthLoading.value = true
  try {
    const res = await axios.get(`${API_BASE_URL}/api/leader-tracking/health`)
    if (res.data?.success) {
      healthData.value = res.data.data
    }
  } catch (e) {
    // 健康分数获取失败不影响主功能
    console.warn('获取健康分数失败:', e)
  } finally {
    healthLoading.value = false
  }
}

// 获取健康分数颜色
const getHealthScoreColor = (score) => {
  if (score >= 80) return 'text-green-600'
  if (score >= 60) return 'text-amber-600'
  return 'text-red-600'
}

// 获取健康分数背景色
const getHealthScoreBg = (score) => {
  if (score >= 80) return 'bg-green-100'
  if (score >= 60) return 'bg-amber-100'
  return 'bg-red-100'
}

// 获取告警等级图标
const getAlertIcon = (level) => {
  switch (level) {
    case 'CRITICAL': return '🔴'
    case 'WARNING': return '🟡'
    case 'NOTICE': return '🔵'
    default: return 'ℹ️'
  }
}

// 获取 LSTM-MAB 智能评分 Top10
const fetchTopScored = async () => {
  isScoring.value = true
  scoringError.value = null
  try {
    // 获取当前页面显示的所有股票代码
    const codes = (leaderRowsBase.value || []).map(r => r.ts_code).filter(Boolean).join(',')
    const res = await axios.get(`${API_BASE_URL}/api/leader-tracking/top-scored`, {
      params: {
        // 不传 top_n，获取所有股票评分
        min_score: 0,  // 不限制最低分，显示所有股票
        stage: 'confirmed',
        ts_codes: codes || undefined,  // 传入所有股票代码
      },
    })
    const data = res.data || {}
    if (data.success) {
      topScoredStocks.value = data.top_stocks || []
      modelAvailable.value = data.model_available || false
      currentEmotionCycle.value = data.emotion_cycle || ''
      // 同时更新 stockScoreMap，使龙头跟踪列表中的AI评分也更新
      const newScoreMap = { ...stockScoreMap.value }
      for (const stock of data.top_stocks || []) {
        if (stock.ts_code && stock.lstm_mab_score) {
          newScoreMap[stock.ts_code] = stock.lstm_mab_score
        }
      }
      stockScoreMap.value = newScoreMap
      saveStockScores()
      if (data.warning) {
        scoringError.value = data.warning
      }
    } else {
      scoringError.value = data.error || '获取评分失败'
      topScoredStocks.value = []
    }
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error('获取智能评分失败:', e)
    scoringError.value = e?.response?.data?.detail || e?.message || '评分请求失败'
    topScoredStocks.value = []
  } finally {
    isScoring.value = false
  }
}

// 获取所有股票的 AI 评分（用于主列表显示）
const fetchAllStockScores = async () => {
  try {
    // 获取当前页面显示的所有股票代码
    const codes = (leaderRowsBase.value || []).map(r => r.ts_code).filter(Boolean).join(',')
    const res = await axios.get(`${API_BASE_URL}/api/leader-tracking/top-scored`, {
      params: {
        // 不传 top_n，获取所有股票评分
        min_score: 0,  // 获取所有评分，不限制最低分
        stage: 'confirmed',
        ts_codes: codes || undefined,  // 传入所有股票代码
      },
    })
    const data = res.data || {}
    if (data.success) {
      // 构建股票代码到评分的映射
      const scoreMap = {}
      for (const stock of data.top_stocks || []) {
        if (stock.ts_code && stock.lstm_mab_score) {
          scoreMap[stock.ts_code] = stock.lstm_mab_score
        }
      }
      stockScoreMap.value = scoreMap
      modelAvailable.value = data.model_available || false
      // 保存到localStorage
      saveStockScores()
    }
  } catch (e) {
    // 静默失败，不影响主列表显示
    console.warn('获取全部评分失败:', e)
  }
}

const drawerOpen = ref(false)
const drawerStock = ref(null)
const drawerLoading = ref(false)
const drawerError = ref('')

const openStockDetailDrawer = async (tsCode) => {
  drawerOpen.value = true
  drawerLoading.value = true
  drawerError.value = ''
  drawerStock.value = null
  try {
    const res = await axios.get(`${API_BASE_URL}/api/leader-tracking/stock-detail/${tsCode}`)
    const data = res.data || {}
    if (!data.success) {
      drawerError.value = data.message || '获取详情失败'
      return
    }
    drawerStock.value = data.data
  } catch (e) {
    drawerError.value = '网络错误，请稍后重试'
  } finally {
    drawerLoading.value = false
  }
}

const closeDrawer = () => {
  drawerOpen.value = false
  drawerStock.value = null
  drawerError.value = ''
}

const selectStock = (tsCode, name) => {
  selectedTsCode.value = tsCode
  selectedName.value = name || tsCode
  openStockDetailDrawer(tsCode)
}

watch(
  () => selectedTsCode.value,
  async (val) => {
    if (!val) {
      kline.value = []
      return
    }
    try {
      const res = await axios.get(`${API_BASE_URL}/api/stock/kline-20`, {
        params: { ts_code: val },
      })
      const data = res.data || {}
      if (!data.success) {
        kline.value = []
        return
      }
      kline.value = data.kline || []
      renderChart()
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error(e)
      kline.value = []
    }
  }
)

const renderChart = () => {
  if (!chartRef.value) return
  if (!chartInstance) {
    chartInstance = echarts.init(chartRef.value)
  }
  const points = kline.value || []
  if (!points.length) {
    chartInstance.clear()
    return
  }
  const dates = points.map((p) => p.trade_date)
  const closes = points.map((p) => p.close)
  const ma20 = points.map((p) => p.ma20)

  // 根据当前位置动态调整收盘价线颜色
  let closeColor = '#4f46e5'
  const last = points[points.length - 1]
  if (last && last.close != null && last.ma20 != null && last.ma20 > 0) {
    const diffPct = ((last.close / last.ma20) - 1) * 100
    if (diffPct > 3) {
      closeColor = '#16a34a' // 强势在20日线上方
    } else if (diffPct < -3) {
      closeColor = '#dc2626' // 明显跌破20日线
    } else {
      closeColor = '#4f46e5' // 震荡区域，用默认色
    }
  }

  const option = {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'line' },
      formatter: (params) => {
        if (!params || !params.length) return ''
        const idx = params[0].dataIndex
        const p = points[idx]
        return [
          `<div class="text-xs">`,
          `<div><strong>${p.trade_date}</strong></div>`,
          `<div>收盘价：${p.close != null ? p.close.toFixed(2) : '-'}</div>`,
          `<div>MA20：${p.ma20 != null ? p.ma20.toFixed(2) : '-'}</div>`,
          `</div>`,
        ].join('')
      },
    },
    grid: { left: 40, right: 16, top: 20, bottom: 32 },
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: {
        fontSize: 10,
        formatter: (v) => v.slice(5),
      },
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLabel: { fontSize: 10 },
      splitLine: { lineStyle: { type: 'dashed', color: '#e5e7eb' } },
    },
    series: [
      {
        name: '收盘价',
        type: 'line',
        data: closes,
        showSymbol: false,
        smooth: true,
        lineStyle: { width: 2, color: closeColor },
      },
      {
        name: 'MA20',
        type: 'line',
        data: ma20,
        showSymbol: false,
        smooth: true,
        lineStyle: { width: 1.5, color: '#f97316', type: 'dashed' },
      },
    ],
  }
  chartInstance.setOption(option, true)
}

const loadAllRowKlines = async () => {
  const rows = leaderRows.value || []
  const codes = Array.from(new Set(rows.map((r) => r.ts_code).filter(Boolean)))
  // eslint-disable-next-line no-console
  console.log('[loadAllRowKlines] 开始加载，股票数量:', codes.length, '当前rowStats key数量:', Object.keys(rowStats.value || {}).length)
  if (!codes.length) return
  const newRowKlines = { ...rowKlines.value }
  const newRowStats = { ...rowStats.value }
  let loadedCount = 0
  let skippedCount = 0
  for (const code of codes) {
    let points = null
    let fromCache = false
    if (newRowKlines[code] && newRowKlines[code].length) {
      if (newRowStats[code] && Object.keys(newRowStats[code]).length > 0) {
        // eslint-disable-next-line no-console
        console.log('[loadAllRowKlines] 跳过缓存股票:', code, '已有K线数据:', newRowKlines[code].length, '条')
        skippedCount++
        continue
      }
      points = newRowKlines[code]
      fromCache = true
      // eslint-disable-next-line no-console
      console.log('[loadAllRowKlines] 缓存K线存在但rowStats缺失，复用计算:', code, points.length, '条')
    }
    let data = {}
    try {
      if (!points) {
        const res = await axios.get(`${API_BASE_URL}/api/stock/kline-20`, {
          params: { ts_code: code },
        })
        data = res.data || {}
        if (!data.success) {
          // eslint-disable-next-line no-console
          console.log('[loadAllRowKlines] API返回失败:', code, data.message)
          continue
        }
        points = data.kline || []
        if (!points.length) {
          // eslint-disable-next-line no-console
          console.log('[loadAllRowKlines] K线数据为空:', code)
          continue
        }
        newRowKlines[code] = points
      }
      // eslint-disable-next-line no-console
      console.log('[loadAllRowKlines] K线数据:', code, 'points数量:', points.length, '第一条amount:', points[0]?.amount, '最后一条amount:', points[points.length-1]?.amount, fromCache ? '(缓存)' : '(API)')
      const first = points[0]
      const last = points[points.length - 1]
      const close = last.close
      const ma20 = last.ma20
      // 优先使用后端返回的 20/60 日涨幅；若不存在则在前端兜底计算 20 日
      let pct20d = typeof data.pct20d === 'number' ? data.pct20d : null
      let pct60d = typeof data.pct60d === 'number' ? data.pct60d : null
      if (pct20d == null && first.close != null && last.close != null && first.close !== 0) {
        pct20d = ((last.close / first.close) - 1) * 100
      }
      let pct20dText = ''
      if (pct20d != null) {
        const sign20 = pct20d >= 0 ? '+' : ''
        pct20dText = `${sign20}${pct20d.toFixed(1)}%`
      }
      let pct60dText = ''
      if (pct60d != null) {
        const sign60 = pct60d >= 0 ? '+' : ''
        pct60dText = `${sign60}${pct60d.toFixed(1)}%`
      }

      // 计算最近20日最大回撤（基于收盘价）
      let maxDrawdown20 = null
      let peak = null
      for (const p of points) {
        if (p.close == null) continue
        const c = Number(p.close)
        if (!Number.isFinite(c)) continue
        if (peak == null || c > peak) {
          peak = c
        }
        if (peak != null && peak > 0) {
          const dd = (c / peak - 1) * 100
          if (maxDrawdown20 == null || dd < maxDrawdown20) {
            maxDrawdown20 = dd
          }
        }
      }
      let maxDrawdown20Text = ''
      if (maxDrawdown20 != null) {
        maxDrawdown20Text = `${maxDrawdown20.toFixed(1)}%`
      }

      // 20日新高 & 距离高点
      let isHigh20 = false
      let fromHigh20 = null
      let fromHigh20Text = ''
      const closes = points.map((p) => p.close).filter((v) => v != null)
      const maxClose20 = closes.length ? Math.max(...closes) : null
      if (closes.length) {
        if (close != null && maxClose20 > 0) {
          isHigh20 = close === maxClose20
          fromHigh20 = (close / maxClose20 - 1) * 100
          fromHigh20Text = `${fromHigh20.toFixed(1)}%`
        }
      }

      // 成交额及量能（单位：亿元）
      const amounts = points.map((p) => p.amount).filter((v) => v != null)
      let lastAmountE = null
      let lastAmountEText = ''
      let amountRatio5_20 = null
      let amountRatio5_20Text = ''
      if (amounts.length) {
        const lastAmt = points[points.length - 1].amount
        if (lastAmt != null) {
          lastAmountE = Number(lastAmt) / 1e5
          lastAmountEText = `${lastAmountE.toFixed(1)}亿`
        }
        const last5 = amounts.slice(-5)
        const last20 = amounts.slice(-20)
        const avg5 = last5.length ? last5.reduce((s, v) => s + v, 0) / last5.length : null
        const avg20 = last20.length ? last20.reduce((s, v) => s + v, 0) / last20.length : null
        if (avg5 != null && avg20 != null && avg20 > 0) {
          amountRatio5_20 = avg5 / avg20
          amountRatio5_20Text = `${amountRatio5_20.toFixed(1)}x`
        }
      }

      let positionTag = ''
      let positionClass = ''
      if (close != null && ma20 != null && ma20 > 0) {
        const diffPct = ((close / ma20) - 1) * 100
        if (Math.abs(diffPct) <= 3) {
          positionTag = '围绕20日线震荡'
          positionClass = 'bg-amber-50 text-amber-700'
        } else if (diffPct > 3) {
          positionTag = '强于20日线'
          positionClass = 'bg-green-50 text-green-700'
        } else {
          positionTag = '跌破20日线'
          positionClass = 'bg-red-50 text-red-700'
        }
      }

      // 退潮判断（按方案 + 第七章优化：深度回撤合并、跌破MA20持续性、放量滞涨前置条件）
      const last5 = points.slice(-5)
      let breakMa20Persist = false
      if (last5.length >= 3) {
        let countBelow = 0
        for (const p of last5) {
          if (p.close != null && p.ma20 != null && p.ma20 > 0 && p.close < p.ma20) countBelow++
        }
        breakMa20Persist = countBelow >= 3
      }
      const deepDrawdown =
        (fromHigh20 != null && fromHigh20 <= -15) ||
        (maxDrawdown20 != null && maxDrawdown20 <= -20)
      const firstClose = first?.close
      const pctFromStartToHigh =
        firstClose != null && firstClose > 0 && maxClose20 != null
          ? (maxClose20 / firstClose - 1) * 100
          : null
      const volumePriceDivergence =
        pctFromStartToHigh != null &&
        pctFromStartToHigh >= 20 &&
        amountRatio5_20 != null &&
        amountRatio5_20 >= 1.5 &&
        pct20d != null &&
        pct20d < 0 &&
        fromHigh20 != null &&
        fromHigh20 <= -8
      const shrinkVolumeDown =
        amountRatio5_20 != null && amountRatio5_20 <= 0.7 && pct20d != null && pct20d < 0

      const retreatReasons = []
      if (breakMa20Persist) retreatReasons.push('跌破20日线(持续)')
      if (deepDrawdown) retreatReasons.push('深度回撤')
      if (volumePriceDivergence) retreatReasons.push('高位放量滞涨')
      if (shrinkVolumeDown) retreatReasons.push('缩量阴跌')
      const N_retreat = retreatReasons.length

      const aboveMa20 =
        ma20 != null && ma20 > 0 && close != null && close >= ma20 * 1.03
      const strongTrendVolume =
        pct20d != null && pct20d > 10 && amountRatio5_20 != null && amountRatio5_20 >= 1.0
      const hasStrong = aboveMa20 || isHigh20 || strongTrendVolume
      let retreat_label = '震荡'
      if (N_retreat >= 2) retreat_label = '退潮风险'
      else if (N_retreat === 0 && hasStrong) retreat_label = '强势'

      newRowStats[code] = {
        pct20d,
        pct20dText,
        pct60d,
        pct60dText,
        maxDrawdown20,
        maxDrawdown20Text,
        isHigh20,
        fromHigh20,
        fromHigh20Text,
        lastAmountE,
        lastAmountEText,
        amountRatio5_20,
        amountRatio5_20Text,
        lastClose: close,
        lastMa20: ma20,
        positionTag,
        positionClass,
        retreat_label,
        retreat_score: N_retreat,
        retreat_reasons: retreatReasons,
      }
      loadedCount++
      // eslint-disable-next-line no-console
      console.log('[loadAllRowKlines] 已加载股票:', code, 'lastAmountE:', lastAmountE, 'lastAmountEText:', lastAmountEText, 'points数量:', points.length)
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error('loadAllRowKlines error', code, e)
    }
  }
  rowKlines.value = newRowKlines
  rowStats.value = newRowStats
  // eslint-disable-next-line no-console
  console.log('[loadAllRowKlines] 完成，新加载:', loadedCount, '跳过:', skippedCount, '最终rowStats key数量:', Object.keys(newRowStats).length)
}

const loadRealtimeQuotes = async (tsCodes) => {
  if (!tsCodes?.length) return
  try {
    const codesParam = tsCodes.join(',')
    const res = await axios.get(`${API_BASE_URL}/api/stock/realtime-quotes`, {
      params: { codes: codesParam },
    })
    const data = res.data || {}
    if (data.success && data.data) {
      realtimeQuotesMap.value = { ...data.data }
    } else {
      realtimeQuotesMap.value = {}
    }
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error('loadRealtimeQuotes error', e)
    realtimeQuotesMap.value = {}
  }
}

const summary = computed(() => {
  const pts = kline.value || []
  if (!pts.length) {
    return {
      priceText: '',
      pct20dText: '',
      positionTag: '',
      positionClass: '',
    }
  }
  const first = pts[0]
  const last = pts[pts.length - 1]
  const close = last.close
  const ma20 = last.ma20
  let pct20dText = ''
  if (first.close && last.close) {
    const pct = ((last.close / first.close) - 1) * 100
    const sign = pct >= 0 ? '+' : ''
    pct20dText = `${sign}${pct.toFixed(1)}%`
  }
  let positionTag = ''
  let positionClass = ''
  if (close != null && ma20 != null && ma20 > 0) {
    const diffPct = ((close / ma20) - 1) * 100
    if (Math.abs(diffPct) <= 3) {
      positionTag = '围绕20日线震荡'
      positionClass = 'bg-amber-50 text-amber-700'
    } else if (diffPct > 3) {
      positionTag = '强于20日线'
      positionClass = 'bg-green-50 text-green-700'
    } else {
      positionTag = '跌破20日线'
      positionClass = 'bg-red-50 text-red-700'
    }
  }
  const priceText = close != null ? `当前收盘价 ${close.toFixed(2)}，MA20 ${ma20 != null ? ma20.toFixed(2) : '-'}` : ''
  return {
    priceText,
    pct20dText,
    positionTag,
    positionClass,
    lastClose: close,
  }
})

const openDiagnose = (tsCode) => {
  if (!tsCode) return
  const pure = tsCode.replace(/\.(SH|SZ|BJ)$/i, '')
  router.push({ path: '/diagnose', query: { code: pure } })
}

const openLeaderBuyBacktest = () => {
  router.push({ path: '/leader-buy-backtest' })
}

const loadPinned = () => {
  try {
    const raw = window.localStorage.getItem('leader-tracking-pins')
    if (!raw) return
    const arr = JSON.parse(raw)
    if (Array.isArray(arr)) {
      pinnedCodes.value = arr.filter((x) => typeof x === 'string')
    }
  } catch (e) {
    // eslint-disable-next-line no-console
    console.warn('loadPinned error', e)
  }
}

const savePinned = () => {
  try {
    window.localStorage.setItem('leader-tracking-pins', JSON.stringify(pinnedCodes.value || []))
  } catch (e) {
    // eslint-disable-next-line no-console
    console.warn('savePinned error', e)
  }
}

const isPinned = (tsCode) => {
  if (!tsCode) return false
  return (pinnedCodes.value || []).includes(tsCode)
}

const togglePin = (tsCode) => {
  if (!tsCode) return
  const arr = [...(pinnedCodes.value || [])]
  const idx = arr.indexOf(tsCode)
  if (idx >= 0) {
    arr.splice(idx, 1)
  } else {
    arr.push(tsCode)
  }
  pinnedCodes.value = arr
  savePinned()
}

const loadTrackingPool = () => {
  try {
    const raw = window.localStorage.getItem('leader-tracking-pool')
    if (!raw) return
    const obj = JSON.parse(raw)
    if (obj && typeof obj === 'object') {
      trackingPool.value = obj
    }
  } catch (e) {
    // eslint-disable-next-line no-console
    console.warn('loadTrackingPool error', e)
  }
}

const saveTrackingPool = () => {
  try {
    window.localStorage.setItem('leader-tracking-pool', JSON.stringify(trackingPool.value || {}))
  } catch (e) {
    // eslint-disable-next-line no-console
    console.warn('saveTrackingPool error', e)
  }
}

const saveStockScores = () => {
  try {
    window.localStorage.setItem('leader-tracking-stock-scores', JSON.stringify(stockScoreMap.value || {}))
  } catch (e) {
    // eslint-disable-next-line no-console
    console.warn('saveStockScores error', e)
  }
}

const loadStockScores = () => {
  try {
    const raw = window.localStorage.getItem('leader-tracking-stock-scores')
    if (!raw) return
    const obj = JSON.parse(raw)
    if (obj && typeof obj === 'object') {
      stockScoreMap.value = obj
    }
  } catch (e) {
    // eslint-disable-next-line no-console
    console.warn('loadStockScores error', e)
  }
}

const toggleTrack = (row) => {
  if (!row || !row.ts_code) return
  const code = row.ts_code
  const current = { ...(trackingPool.value || {}) }
  if (current[code]) {
    delete current[code]
  } else {
    current[code] = {
      ts_code: code,
      name: row.name || code,
      reason: trackReasonForRow(row),
    }
    // 同步加入全局股票跟踪（后端 watchlist）
    axios.post(`${API_BASE_URL}/api/watchlist`, {
      ts_code: code,
      note: buildWatchlistNoteForRow(row),
    }).catch((error) => {
      // eslint-disable-next-line no-console
      console.error('add to watchlist from leader tracking failed', error)
    })
  }
  trackingPool.value = current
  saveTrackingPool()
}

// 批量加入当前页股票到跟踪池（仅添加，不取消）
const bulkTrack = (scope) => {
  const list = scope === 'page' ? (leaderRowsPaged.value || []) : (leaderRows.value || [])
  if (!list.length) return
  const current = { ...(trackingPool.value || {}) }
  const toAdd = []
  for (const row of list) {
    if (!row || !row.ts_code) continue
    const code = row.ts_code
    if (current[code]) continue
    current[code] = {
      ts_code: code,
      name: row.name || code,
      reason: trackReasonForRow(row),
    }
    toAdd.push(row)
  }
  trackingPool.value = current
  saveTrackingPool()

  // 批量同步到后端 watchlist
  if (!toAdd.length) return
  let successCount = 0
  let existingCount = 0
  let failCount = 0
  Promise.all(
    toAdd.map((row) =>
      axios
        .post(`${API_BASE_URL}/api/watchlist`, {
          ts_code: row.ts_code,
          note: buildWatchlistNoteForRow(row),
        })
        .then((res) => {
          const data = res.data || {}
          if (data.success) {
            successCount += 1
          } else if ((data.message || data.detail || '').includes('已在跟踪列表中')) {
            existingCount += 1
          } else {
            failCount += 1
          }
        })
        .catch((error) => {
          const msg =
            error?.response?.data?.message || error?.response?.data?.detail || error?.message || ''
          if (msg.includes('已在跟踪列表中')) {
            existingCount += 1
          } else {
            failCount += 1
          }
        }),
    ),
  ).then(() => {
    // 简单提示一次汇总结果
    // eslint-disable-next-line no-alert
    alert(
      `批量加入跟踪池完成：\n成功 ${successCount} 只\n已在跟踪池 ${existingCount} 只\n失败 ${failCount} 只`,
    )
  })
}

const formatPct = (v) => {
  if (v === null || v === undefined) return '--'
  const num = Number(v)
  if (Number.isNaN(num)) return '--'
  const sign = num > 0 ? '+' : ''
  return `${sign}${num.toFixed(2)}%`
}

const fetchSectorBacktestSummary = async () => {
  try {
    const today = new Date()
    const oneYearAgo = new Date()
    oneYearAgo.setFullYear(today.getFullYear() - 1)
    const params = {
      start_date: oneYearAgo.toISOString().slice(0, 10),
      end_date: today.toISOString().slice(0, 10),
      min_strength: minStrength.value,
      signal_type: 'both',
      sector_type: 'any',
    }
    const res = await axios.get(`${API_BASE_URL}/api/startup/leader-buy-backtest/summary/by-sector`, {
      params,
    })
    const data = res.data || {}
    if (!data.success) {
      sectorBacktestMap.value = {}
      return
    }
    const map = {}
    for (const item of data.items || []) {
      if (!item?.sector_key) continue
      map[item.sector_key] = item
    }
    sectorBacktestMap.value = map
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error('fetchSectorBacktestSummary failed', e)
    sectorBacktestMap.value = {}
  }
}

const getRowBacktest = (row) => {
  if (!row || !row.sectors || !row.sectors.length) return null
  const btMap = sectorBacktestMap.value || {}
  const secs = sectors.value || []
  for (const secName of row.sectors) {
    const sec = secs.find((s) => s.sector_name === secName)
    if (!sec || !sec.sector_key) continue
    const bt = btMap[sec.sector_key]
    if (bt && bt.ret_5d_avg != null && bt.ret_10d_avg != null) {
      return bt
    }
  }
  return null
}

// 清除缓存并刷新数据
const clearCacheAndRefresh = () => {
  try {
    window.localStorage.removeItem('leader-tracking-sector-strength-cache-v2')
    // eslint-disable-next-line no-alert
    alert('缓存已清除，即将刷新数据')
    fetchData()
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error('清除缓存失败', e)
  }
}

onMounted(() => {
  loadPinned()
  loadTrackingPool()
  loadStockScores()
  fetchData()
  fetchSectorBacktestSummary()
  // 若通过 ?code= 进入，自动选中对应股票
  const code = route.query?.code
  if (typeof code === 'string' && code.trim()) {
    const c = code.trim()
    if (/^\d{6}$/.test(c)) {
      selectedTsCode.value = c.startsWith('6') ? `${c}.SH` : `${c}.SZ`
      selectedName.value = ''
    } else if (/^\d{6}\.(SH|SZ|BJ)$/i.test(c)) {
      selectedTsCode.value = c
      selectedName.value = ''
    }
  }
  window.addEventListener('resize', _onChartResize)
})
const _onChartResize = () => chartInstance?.resize()
onUnmounted(() => {
  window.removeEventListener('resize', _onChartResize)
})
</script>

<style scoped>
</style>

