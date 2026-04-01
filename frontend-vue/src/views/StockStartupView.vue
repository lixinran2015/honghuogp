<template>
  <div class="container mx-auto px-4 py-6">
    <!-- 页面标题 -->
    <div class="mb-6 flex items-start justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-800">股票启动监控</h1>
        <p class="text-sm text-gray-500 mt-1">三阶段筛选：金叉候选 → 待候选监控 → 已启动</p>
      </div>
      
      <!-- 启动原则按钮 -->
      <button
        @click="enterStartupRules"
        class="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm flex items-center space-x-1"
      >
        <span>📋 进入启动原则</span>
      </button>
    </div>

    <!-- 重点关注提示（独立显示） -->
    <div class="mb-6 bg-yellow-50 border-l-4 border-yellow-400 p-4 rounded-r-lg">
      <div class="flex items-start">
        <span class="text-yellow-600 text-xl mr-2">⚠️</span>
        <div>
          <div class="font-semibold text-yellow-800 mb-1">重点关注</div>
          <div class="text-sm text-yellow-700">金叉候选中"3/4条件"的股票 = <strong class="text-red-600">低吸买点</strong></div>
        </div>
      </div>
    </div>

    <!-- 筛选规则说明（可折叠） -->
    <div v-if="showRules" id="startup-rules" class="bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 rounded-lg p-6 mb-6">
      <h2 class="text-lg font-bold text-gray-800 mb-4">📋 四层筛选规则</h2>
      
      <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <!-- 第一阶段：基础过滤 + 金叉 -->
        <div class="bg-white rounded-lg p-4 shadow-sm">
          <h3 class="font-semibold text-blue-600 mb-3 flex items-center">
            <span class="text-lg mr-2">1️⃣</span>
            基础过滤 + 金叉（20分）
          </h3>
          <div class="space-y-2 text-sm text-gray-700">
            <div class="flex items-start">
              <span class="text-blue-500 mr-2">✓</span>
              <span><strong>流通市值</strong> ≥ 40亿</span>
            </div>
            <div class="flex items-start">
              <span class="text-blue-500 mr-2">✓</span>
              <span><strong>成交额</strong> ≥ 10亿</span>
            </div>
            <div class="flex items-start">
              <span class="text-blue-500 mr-2">✓</span>
              <span><strong>股价</strong> ≥ 60日均线</span>
            </div>
            <div class="flex items-start">
              <span class="text-blue-500 mr-2">✓</span>
              <span><strong>5日金叉10日</strong>（MA5 > MA10）</span>
            </div>
            <div class="flex items-start">
              <span class="text-blue-500 mr-2">✓</span>
              <span><strong>仅主板</strong>（600/601/603/000/001/002）</span>
            </div>
          </div>
          <div class="mt-3 pt-3 border-t border-gray-200 text-xs text-gray-600">
            💡 满足条件 → 🟡 <strong>金叉候选</strong>（观察期7日）
          </div>
        </div>

        <!-- 第二阶段：核心确认 -->
        <div class="bg-white rounded-lg p-4 shadow-sm">
          <h3 class="font-semibold text-green-600 mb-3 flex items-center">
            <span class="text-lg mr-2">2️⃣</span>
            核心确认（+40分）
          </h3>
          <div class="space-y-2 text-sm text-gray-700">
            <div class="flex items-start">
              <span class="text-green-500 mr-2">✓</span>
              <span><strong>突破60日高点</strong>（收盘价 > 前60个交易日的收盘价最高价）<span class="text-green-600 ml-1">+10分</span></span>
            </div>
            <div class="flex items-start">
              <span class="text-green-500 mr-2">✓</span>
              <span><strong>量能放大</strong>（量比 ≥ 1.5倍）<span class="text-green-600 ml-1">+10分</span></span>
            </div>
            <div class="flex items-start">
              <span class="text-green-500 mr-2">✓</span>
              <span><strong>均线多头排列</strong>（5>10>20>60）<span class="text-green-600 ml-1">+10分</span></span>
            </div>
            <div class="flex items-start">
              <span class="text-green-500 mr-2">✓</span>
              <span><strong>近6个交易日有涨停</strong>（包含金叉当日）<span class="text-green-600 ml-1">+10分</span></span>
            </div>
          </div>
          <div class="mt-3 pt-3 border-t border-gray-200 text-xs text-gray-600">
            💡 <strong class="text-red-600">四者必须全部满足</strong> → 进入下一阶段<br/>
            💡 满足3/4条件 → 自动加入<strong class="text-purple-600">待监控池</strong>（低吸观察点）<br/>
            💡 <strong class="text-blue-600">替代路径</strong>：仅不符合「突破60日高点」时，若满足<strong>净买入&gt;8000万</strong>+<strong>绝对龙头</strong> → 视为核心通过
          </div>
        </div>

        <!-- 第三阶段：辅助确认 -->
        <div class="bg-white rounded-lg p-4 shadow-sm">
          <h3 class="font-semibold text-purple-600 mb-3 flex items-center">
            <span class="text-lg mr-2">3️⃣</span>
            辅助确认（+10-30分）
          </h3>
          <div class="space-y-2 text-sm text-gray-700">
            <div class="flex items-start">
              <span class="text-purple-500 mr-2">○</span>
              <span><strong>MACD金叉</strong>（DIF上穿DEA）<span class="text-purple-600 ml-1">+10分</span></span>
            </div>
            <div class="flex items-start">
              <span class="text-purple-500 mr-2">○</span>
              <span><strong>KDJ金叉</strong>（J值50-70）<span class="text-purple-600 ml-1">+10分</span></span>
            </div>
            <div class="flex items-start">
              <span class="text-purple-500 mr-2">○</span>
              <span><strong>大单净流入</strong>（占比 ≥ 5%）<span class="text-purple-600 ml-1">+10分</span></span>
            </div>
          </div>
          <div class="mt-3 pt-3 border-t border-gray-200 text-xs text-gray-600">
            💡 至少满足 <strong>1个</strong> → 继续下一阶段<br/>
            每满足1个加10分，最多30分
          </div>
        </div>

        <!-- 第四阶段：风险排除 -->
        <div class="bg-white rounded-lg p-4 shadow-sm">
          <h3 class="font-semibold text-orange-600 mb-3 flex items-center">
            <span class="text-lg mr-2">4️⃣</span>
            风险排除（最终评级）
          </h3>
          <div class="space-y-2 text-sm text-gray-700">
            <div class="flex items-start">
              <span class="text-orange-500 mr-2">×</span>
              <span><strong>RSI超买</strong>（RSI > 70）</span>
            </div>
            <div class="flex items-start">
              <span class="text-orange-500 mr-2">×</span>
              <span><strong>KDJ超买</strong>（J值 > 85）</span>
            </div>
          </div>
          <div class="mt-3 pt-3 border-t border-gray-200 text-xs text-gray-600">
            💡 <strong class="text-red-600">全部不满足</strong> → ✅ <strong>完全启动</strong><br/>
            有任何风险 → 🟢 <strong>启动确认</strong>（有风险提示）
          </div>
        </div>
      </div>

      <!-- 得分说明 -->
      <div class="mt-6 bg-white rounded-lg p-4 shadow-sm">
        <h3 class="font-semibold text-gray-800 mb-3">📊 得分体系</h3>
        <div class="grid grid-cols-1 md:grid-cols-5 gap-4 text-sm">
          <div class="text-center p-3 bg-yellow-50 rounded">
            <div class="font-bold text-yellow-600 text-lg">20分</div>
            <div class="text-gray-600 mt-1 text-xs">金叉候选</div>
            <div class="text-gray-500 mt-1 text-xs">基础条件</div>
          </div>
          <div class="text-center p-3 bg-blue-50 rounded">
            <div class="font-bold text-blue-600 text-lg">20-60分</div>
            <div class="text-gray-600 mt-1 text-xs">金叉+部分核心</div>
            <div class="text-gray-500 mt-1 text-xs">每个核心条件+10分</div>
          </div>
          <div class="text-center p-3 bg-green-50 rounded">
            <div class="font-bold text-green-600 text-lg">60分</div>
            <div class="text-gray-600 mt-1 text-xs">核心确认</div>
            <div class="text-gray-500 mt-1 text-xs">核心全满足，辅助不足</div>
          </div>
          <div class="text-center p-3 bg-orange-50 rounded">
            <div class="font-bold text-orange-600 text-lg">70-90分</div>
            <div class="text-gray-600 mt-1 text-xs">启动确认</div>
            <div class="text-gray-500 mt-1 text-xs">核心+辅助，但有风险</div>
          </div>
          <div class="text-center p-3 bg-red-50 rounded">
            <div class="font-bold text-red-600 text-lg">70-100分</div>
            <div class="text-gray-600 mt-1 text-xs">完全启动</div>
            <div class="text-gray-500 mt-1 text-xs">核心+辅助+无风险</div>
          </div>
        </div>
        <div class="mt-4 pt-4 border-t border-gray-200 text-xs text-gray-600">
          <div class="font-semibold mb-2">得分计算公式：</div>
          <div class="space-y-1">
            <div>• <strong>基础分</strong>：金叉 = 20分</div>
            <div>• <strong>核心条件</strong>：每个条件 = 10分（共4个条件，最多40分）</div>
            <div>• <strong>辅助条件</strong>：每个条件 = 10分（共3个条件，最多30分）</div>
            <div>• <strong>最终得分</strong> = 基础分 + 核心条件分 + 辅助条件分</div>
            <div class="mt-2 text-gray-500">
              <div>示例：金叉(20) + 核心全满足(40) + 辅助2个(20) + 无风险 = 80分</div>
              <div>示例：金叉(20) + 核心全满足(40) + 辅助1个(10) + 有风险 = 70分</div>
              <div>示例：金叉(20) + 核心全满足(40) + 辅助0个(0) = 60分（核心确认）</div>
            </div>
          </div>
        </div>
      </div>

      <!-- 使用建议 -->
      <div class="mt-4 bg-yellow-50 border border-yellow-200 rounded-lg p-4">
        <div class="font-semibold text-yellow-800 mb-2">⭐ 操作建议</div>
        <div class="space-y-1 text-sm text-yellow-700">
          <div>• <strong>3/4核心条件</strong>的金叉候选 = <strong class="text-red-600">低吸观察点</strong>（重点关注，自动加入待监控池）</div>
          <div>• <strong>仅差突破90日高点</strong>：若满足 <strong>净买入&gt;8000万</strong>+<strong>绝对龙头</strong> → <strong class="text-blue-600">替代路径通过</strong>，视为核心确认</div>
          <div>• <strong>核心确认</strong>（60分）= 核心条件全满足但辅助不足，可关注</div>
          <div>• <strong>启动确认</strong>（70-90分）= 核心+辅助满足但有风险，<strong>注意风险提示</strong></div>
          <div>• <strong>完全启动</strong>（70-100分）= 所有条件满足且无风险，自动进入<strong class="text-purple-600">💎 推荐池</strong></div>
        </div>
      </div>

      <!-- 流程说明 -->
      <div class="mt-4 bg-blue-50 border border-blue-200 rounded-lg p-4">
        <div class="font-semibold text-blue-800 mb-2">🔄 检查流程</div>
        <div class="space-y-1 text-sm text-blue-700">
          <div><strong>第1天</strong>：检查金叉 → 保存金叉候选（20分）</div>
          <div><strong>第2-7天</strong>：根据已有记录状态决定检查哪些条件</div>
          <div class="ml-4 text-xs text-blue-600">
            • 如果只有金叉（score=20）→ 检查核心条件、辅助条件、风险排除
          </div>
          <div class="ml-4 text-xs text-blue-600">
            • 如果核心条件已通过 → 检查辅助条件和风险排除
          </div>
          <div class="ml-4 text-xs text-blue-600">
            • 如果辅助条件已满足 → 只检查风险排除条件
          </div>
          <div class="mt-2 text-xs text-blue-600">
            💡 每天都会按此流程运行，直到所有条件满足或超过观察期（7个交易日）
          </div>
        </div>
      </div>
    </div>

    <!-- Tab切换 -->
    <div class="bg-white rounded-lg shadow mb-6">
      <div class="border-b border-gray-200">
        <nav class="flex">
          <button
            v-for="tab in tabs"
            :key="tab.key"
            @click="activeTab = tab.key"
            :class="{
              'border-b-2 border-blue-500 text-blue-600': activeTab === tab.key,
              'text-gray-600 hover:text-gray-800': activeTab !== tab.key
            }"
            class="px-6 py-3 font-medium text-sm"
          >
            {{ tab.label }}
            <span v-if="tab.count !== undefined" class="ml-2 px-2 py-0.5 bg-gray-100 rounded text-xs">
              {{ tab.count }}
            </span>
          </button>
        </nav>
      </div>

      <!-- Tab内容区 -->
      <div class="p-6">
        <!-- 控制面板 -->
        <div class="mb-4">
          <div class="flex items-center justify-between mb-2">
            <!-- 第一行：筛选器和查询按钮 -->
            <div class="flex items-center space-x-3 flex-wrap">
              <div class="flex items-center space-x-2">
                <label class="text-sm text-gray-700">查询最近</label>
                <input
                  v-model="queryDays"
                  type="number"
                  :min="activeTab === 'started' ? 30 : 1"
                  max="60"
                  class="px-3 py-2 border border-gray-300 rounded w-16 text-sm text-center"
                />
                <span class="text-sm text-gray-700">{{ activeTab === 'started' ? '个交易日' : '天' }}</span>
              </div>
              
              <!-- 金叉候选Tab的筛选器：只显示待监控股票 -->
              <label v-if="activeTab === 'golden_cross'" class="flex items-center space-x-2">
                <input type="checkbox" v-model="showWatchingOnly" class="rounded" />
                <span class="text-sm">只显示待监控</span>
              </label>
              
              <!-- 金叉候选Tab：按诊断条件内容搜索 / 未突破90日高点 -->
              <div v-if="activeTab === 'golden_cross'" class="flex items-center space-x-2">
                <label class="text-sm text-gray-700 whitespace-nowrap">诊断条件包含：</label>
                <input
                  v-model.trim="diagnosisSearch"
                  type="text"
                  placeholder="例如：距离90日高点 / 量能放大"
                  class="px-3 py-2 border border-gray-300 rounded text-sm w-56"
                />
                <label class="flex items-center space-x-1 text-sm text-gray-700">
                  <input type="checkbox" v-model="notBreakthrough90dOnly" class="rounded" />
                  <span>仅未突破90日高点</span>
                </label>
              </div>
              
              <!-- 已启动Tab的筛选器：启动确认/完全启动 -->
              <div v-if="activeTab === 'started'" class="flex items-center space-x-2">
                <label class="text-sm text-gray-700">类型：</label>
                <select v-model="startedFilter" class="px-3 py-2 border border-gray-300 rounded text-sm">
                  <option value="all">全部</option>
                  <option value="confirmed">启动确认</option>
                  <option value="started">完全启动</option>
                </select>
              </div>
              
              <!-- 已启动Tab的筛选器：财务检测 -->
              <div v-if="activeTab === 'started'" class="flex items-center space-x-2">
                <label class="text-sm text-gray-700">财务检测：</label>
                <select v-model="financialCheckFilter" class="px-3 py-2 border border-gray-300 rounded text-sm">
                  <option value="all">全部</option>
                  <option value="passed">✅ 通过</option>
                  <option value="failed">❌ 未通过</option>
                  <option value="not_checked">⚪ 未检测</option>
                </select>
              </div>
              
              <!-- 已启动Tab的筛选器：板块角色 -->
              <div v-if="activeTab === 'started'" class="flex items-center space-x-2">
                <label class="text-sm text-gray-700">板块角色：</label>
                <select v-model="sectorLeaderRoleFilter" class="px-3 py-2 border border-gray-300 rounded text-sm">
                  <option value="all">全部</option>
                  <option value="绝对龙头">绝对龙头</option>
                  <option value="补涨">补涨</option>
                  <option value="跟风">跟风</option>
                </select>
              </div>
              
              <label v-if="activeTab === 'started'" class="flex items-center space-x-2">
                <input type="checkbox" v-model="excludeBrokenMa10" class="rounded" />
                <span class="text-sm">排除已破20日线</span>
              </label>
              
              <button
                @click="loadData"
                :disabled="loading"
                class="px-6 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 text-sm"
              >
                {{ loading ? '加载中...' : '🔍 查询' }}
              </button>
            </div>
          </div>
          
          <!-- 第二行：操作按钮 -->
          <div class="flex items-center space-x-3 flex-wrap">
            <button
              v-if="activeTab === 'golden_cross'"
              @click="batchDiagnose"
              :disabled="diagnosing"
              class="px-6 py-2 bg-purple-600 text-white rounded hover:bg-purple-700 disabled:opacity-50 text-sm relative"
              :title="hasDiagnosisResults ? '重新诊断' : '诊断核心条件'"
            >
              {{ diagnosing ? '诊断中...' : (hasDiagnosisResults ? '🔄 重新诊断' : '🔍 批量诊断') }}
              <span v-if="hasDiagnosisResults" class="absolute -top-1 -right-1 w-2 h-2 bg-green-500 rounded-full"></span>
            </button>
            
            <!-- 待监控Tab的控制按钮 -->
            <button
              v-if="activeTab === 'watching'"
              @click="watchServiceRunning ? stopWatchService() : startWatchService()"
              :class="watchServiceRunning ? 'bg-orange-600 hover:bg-orange-700' : 'bg-green-600 hover:bg-green-700'"
              class="px-6 py-2 text-white rounded disabled:opacity-50 text-sm"
            >
              {{ watchServiceRunning ? '⏸️ 停止监控' : '▶️ 启动监控' }}
            </button>
            
            <!-- 已启动Tab的控制按钮：加入跟踪池 -->
            <button
              v-if="activeTab === 'started'"
              @click="batchAddToWatchlist"
              :disabled="loading || addingToWatchlist || displayStocks.length === 0"
              class="px-6 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50 text-sm"
              :title="displayStocks.length === 0 ? '没有可添加的股票' : `将当前列表中的 ${displayStocks.length} 只股票加入跟踪池`"
            >
              {{ addingToWatchlist ? '添加中...' : '📋 加入跟踪池' }}
            </button>
            
            <button
              v-if="activeTab === 'watching' && watchServiceRunning"
              @click="checkNow"
              class="px-6 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm"
            >
              🔍 立即检查
            </button>
            
            <button
              v-if="activeTab !== 'watching'"
              @click="scanTodayStocks"
              :disabled="scanning"
              class="px-6 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50 text-sm"
            >
              {{ scanning ? '扫描中...' : '🔍 扫描' }}
            </button>
            
            <button
              v-if="activeTab !== 'watching'"
              @click="recalculatePerformance"
              :disabled="recalculating"
              class="px-6 py-2 bg-purple-600 text-white rounded hover:bg-purple-700 disabled:opacity-50 text-sm"
            >
              {{ recalculating ? '计算中...' : '🔄 计算表现' }}
            </button>
            
            <button
              v-if="activeTab === 'started'"
              @click="checkExit"
              :disabled="checkingExit"
              class="px-6 py-2 bg-orange-600 text-white rounded hover:bg-orange-700 disabled:opacity-50 text-sm"
            >
              {{ checkingExit ? '检查中...' : '🔍 退出检查' }}
            </button>
            
            <button
              v-if="activeTab === 'started'"
              @click="checkFinancial"
              :disabled="checkingFinancial || displayStocks.length === 0"
              class="px-6 py-2 bg-purple-600 text-white rounded hover:bg-purple-700 disabled:opacity-50 text-sm"
              :title="financialCheckMessage || '对当前列表中未检测的股票进行财务检测（已检测的会自动跳过）'"
            >
              <span v-if="checkingFinancial">
                {{ financialCheckProgress > 0 ? `${financialCheckProgress}% ${financialCheckMessage}` : '启动中...' }}
              </span>
              <span v-else>💰 财务检测</span>
            </button>

            <button
              v-if="activeTab === 'started'"
              @click="autoCheckAllFinancial"
              :disabled="checkingFinancial"
              class="px-6 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50 text-sm"
              :title="financialCheckMessage || '自动检测所有已启动但未检测的股票'"
            >
              <span v-if="checkingFinancial">
                {{ financialCheckProgress > 0 ? `${financialCheckProgress}% ${financialCheckMessage}` : '启动中...' }}
              </span>
              <span v-else>🚀 自动检测全部</span>
            </button>
            
            <button
              v-if="activeTab === 'golden_cross'"
              @click="checkMa20"
              :disabled="checkingMa20"
              class="px-6 py-2 bg-orange-600 text-white rounded hover:bg-orange-700 disabled:opacity-50 text-sm"
            >
              {{ checkingMa20 ? '检查中...' : '🔍 检查20日线' }}
            </button>
          </div>
          
          <!-- 统计信息 -->
          <div class="mt-2 text-sm text-gray-600 space-y-1">
            <div>{{ tabSummary.line1 }}</div>
            <div v-if="tabSummary.line2">{{ tabSummary.line2 }}</div>
          </div>
        </div>

        <!-- 表格：table-layout:fixed 防止长文本导致列变形 -->
        <div class="overflow-x-auto">
          <table class="w-full min-w-[1200px]" style="table-layout: fixed">
            <thead class="bg-gray-50">
              <tr>
                <th v-if="activeTab === 'watching'" class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('first_entry_date')">
                  首次入选 {{ sortIcon('first_entry_date') }}
                </th>
                <th v-if="activeTab === 'watching'" class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('latest_entry_date')">
                  最新入选 {{ sortIcon('latest_entry_date') }}
                </th>
                <th v-if="activeTab === 'watching'" class="px-3 py-2 text-center text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('count_5d')">
                  5日次数 {{ sortIcon('count_5d') }}
                </th>
                <th v-if="activeTab === 'started'" class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('latest_entry_date')">
                  最新入选 {{ sortIcon('latest_entry_date') }}
                </th>
                <th v-if="activeTab === 'started'" class="px-3 py-2 text-center text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('score')">
                  状态 {{ sortIcon('score') }}
                </th>
                <th v-if="activeTab !== 'watching' && activeTab !== 'started'" class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('entry_date')">
                  入选日期 {{ sortIcon('entry_date') }}
                </th>
                <th v-if="activeTab === 'golden_cross'" class="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('days_since_cross')">
                  距金叉 {{ sortIcon('days_since_cross') }}
                </th>
                <th v-if="activeTab === 'golden_cross'" class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('golden_cross_date')">
                  金叉日期 {{ sortIcon('golden_cross_date') }}
                </th>
                <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('ts_code')">
                  代码 {{ sortIcon('ts_code') }}
                </th>
                <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('name')">
                  名称 {{ sortIcon('name') }}
                </th>
                <th v-if="activeTab === 'started' || activeTab === 'golden_cross'" class="px-3 py-2 text-center text-xs font-medium text-gray-500 uppercase">
                  龙头
                </th>
                <th v-if="activeTab === 'started' || activeTab === 'golden_cross'" class="px-3 py-2 text-center text-xs font-medium text-gray-500 uppercase">
                  板块角色
                </th>
                <th v-if="activeTab === 'started'" class="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('entry_amount')">
                  入选日成交额 {{ sortIcon('entry_amount') }}
                </th>
                <th v-if="activeTab === 'golden_cross'" class="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('entry_main_net_inflow_wan')">
                  入选日净流入(万) {{ sortIcon('entry_main_net_inflow_wan') }}
                </th>
                <th v-if="activeTab !== 'started'" class="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('pct_before_5d')">
                  前5日 {{ sortIcon('pct_before_5d') }}
                </th>
                <th v-if="activeTab !== 'started'" class="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('pct_after_5d')">
                  入选后5日 {{ sortIcon('pct_after_5d') }}
                </th>
                <th v-if="activeTab === 'started'" class="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('pct_after_5d_from_latest')">
                  后5日 {{ sortIcon('pct_after_5d_from_latest') }}
                </th>
                <th v-if="activeTab === 'started'" class="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('pct_after_10d_from_latest')">
                  后10日 {{ sortIcon('pct_after_10d_from_latest') }}
                </th>
                <th v-if="activeTab === 'started'" class="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('pct_after_30d_from_latest')">
                  后30日 {{ sortIcon('pct_after_30d_from_latest') }}
                </th>
                <th v-if="activeTab !== 'started'" class="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('latest_change')">
                  今日 {{ sortIcon('latest_change') }}
                </th>
                <th v-if="activeTab === 'golden_cross'" class="px-3 py-2 text-center text-xs font-medium text-gray-500 uppercase">
                  核心条件
                </th>
                <th v-if="activeTab === 'watching'" class="px-3 py-2 text-center text-xs font-medium text-gray-500 uppercase cursor-pointer" @click="sortBy('check_count')">
                  检查次数 {{ sortIcon('check_count') }}
                </th>
                <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase" :style="activeTab === 'started' ? { width: '180px' } : {}">
                  {{ activeTab === 'golden_cross' ? '诊断建议' : activeTab === 'watching' ? '缺少条件' : '风险原因' }}
                </th>
                <th v-if="activeTab === 'started'" class="px-3 py-2 text-center text-xs font-medium text-gray-500 uppercase" style="width: 80px">
                  操作建议
                </th>
                <th v-if="activeTab === 'started'" class="px-3 py-2 text-center text-xs font-medium text-gray-500 uppercase" style="width: 120px">
                  财务检测
                </th>
                <th v-if="activeTab === 'started'" class="px-3 py-2 text-center text-xs font-medium text-gray-500 uppercase" style="width: 140px">
                  操作
                </th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-200">
              <tr v-if="loading">
                <td :colspan="activeTab === 'golden_cross' ? 12 : activeTab === 'watching' ? 11 : activeTab === 'started' ? 14 : 7" class="px-4 py-8 text-center text-gray-500">
                  加载中...
                </td>
              </tr>
              <tr v-else-if="displayStocks.length === 0">
                <td :colspan="activeTab === 'golden_cross' ? 12 : activeTab === 'watching' ? 11 : activeTab === 'started' ? 14 : 7" class="px-4 py-8 text-center text-gray-500">
                  {{ activeTab === 'watching' ? '暂无待监控股票（批量诊断时会自动加入3/4条件的股票）' : '暂无数据' }}
                </td>
              </tr>
              <tr v-for="stock in displayStocks" :key="`${stock.ts_code}-${stock.entry_date || stock.watch_start_date}`" class="hover:bg-gray-50">
                <td v-if="activeTab === 'watching'" class="px-3 py-2 text-xs text-gray-600">
                  {{ formatDate(stock.first_entry_date) }}
                </td>
                <td v-if="activeTab === 'watching'" class="px-3 py-2 text-xs text-gray-600">
                  {{ formatDate(stock.latest_entry_date) }}
                </td>
                <td v-if="activeTab === 'watching'" class="px-3 py-2 text-xs text-center">
                  <span :class="{
                    'text-red-600 font-semibold': stock.count_5d >= 3,
                    'text-yellow-600 font-semibold': stock.count_5d === 2,
                    'text-gray-600': stock.count_5d === 1
                  }">
                    {{ stock.count_5d || 0 }}次
                  </span>
                </td>
                <td v-if="activeTab === 'started'" class="px-3 py-2 text-xs text-gray-600">
                  {{ formatDate(stock.latest_entry_date || stock.entry_date) }}
                </td>
                <td v-if="activeTab === 'started'" class="px-3 py-2 text-xs text-center">
                  <span v-if="stock.stage === 'started'" class="px-2 py-1 bg-green-100 text-green-700 rounded text-xs font-semibold" title="无风险，可进推荐池">
                    ✅ 完全启动
                  </span>
                  <span v-else class="px-2 py-1 bg-yellow-100 text-yellow-700 rounded text-xs font-semibold" :title="stock.risks?.length ? '有风险原因，不进推荐池' : '核心+辅助满足'">
                    🟢 启动确认
                  </span>
                </td>
                <td v-if="activeTab !== 'watching' && activeTab !== 'started'" class="px-3 py-2 text-xs text-gray-600">
                  {{ formatDate(stock.entry_date || stock.watch_start_date) }}
                </td>
                <td v-if="activeTab === 'golden_cross'" class="px-3 py-2 text-xs text-right">
                  <span :class="{
                    'text-green-600 font-semibold': stock.days_since_cross <= 3,
                    'text-yellow-600': stock.days_since_cross > 3 && stock.days_since_cross <= 7,
                    'text-gray-600': stock.days_since_cross > 5
                  }">
                    {{ stock.days_since_cross }}天
                  </span>
                </td>
                <td v-if="activeTab === 'golden_cross'" class="px-3 py-2 text-xs text-gray-600">
                  {{ formatDate(stock.golden_cross_date) }}
                </td>
                <td class="px-3 py-2 text-xs text-gray-600">{{ stock.ts_code }}</td>
                <td class="px-3 py-2 text-xs font-medium">{{ stock.name }}</td>
                <td v-if="activeTab === 'started' || activeTab === 'golden_cross'" class="px-3 py-2 text-xs text-center">
                  <span v-if="stock.industry_leader_type" class="px-2 py-0.5 rounded text-xs font-medium" :class="{
                    'bg-amber-100 text-amber-800': stock.industry_leader_type === '行业龙头',
                    'bg-blue-100 text-blue-800': stock.industry_leader_type === '板块龙头',
                    'bg-slate-100 text-slate-700': stock.industry_leader_type === '细分龙头'
                  }" :title="stock.industry_leader_source === 'diagnosis' ? '来自AI龙头诊断' : '来自板块龙头表'">{{ stock.industry_leader_type }}{{ stock.industry_leader_source === 'diagnosis' ? ' (诊)' : '' }}</span>
                  <span v-else class="text-gray-400">--</span>
                </td>
                <td v-if="activeTab === 'started' || activeTab === 'golden_cross'" class="px-3 py-2 text-xs text-center">
                  <span v-if="stock.sector_leader_role" class="px-2 py-0.5 rounded text-xs font-medium" :class="{
                    'bg-amber-100 text-amber-800': stock.sector_leader_role === '绝对龙头',
                    'bg-sky-100 text-sky-800': stock.sector_leader_role === '补涨',
                    'bg-gray-100 text-gray-700': stock.sector_leader_role === '跟风'
                  }" :title="stock.sector_leader_of ? `跟风于: ${stock.sector_leader_of}` : ''">{{ stock.sector_leader_role }}</span>
                  <span v-else class="text-gray-400">--</span>
                  <span v-if="stock.sector_leader_role === '跟风' && stock.sector_leader_of" class="ml-1 text-gray-500 cursor-help" title="跟风于: 绝对龙头股">→{{ stock.sector_leader_of.split('（')[0] }}</span>
                </td>
                <td v-if="activeTab === 'started'" class="px-3 py-2 text-xs text-right text-gray-700">
                  {{ formatAmount(stock.entry_amount) }}
                </td>
                <td v-if="activeTab === 'golden_cross'" class="px-3 py-2 text-xs text-right text-gray-700">
                  <span v-if="stock.entry_main_net_inflow_wan != null">
                    {{ stock.entry_main_net_inflow_wan >= 0 ? '+' : '' }}{{ stock.entry_main_net_inflow_wan.toFixed(0) }}万
                  </span>
                  <span v-else class="text-gray-400">--</span>
                </td>
                <td v-if="activeTab !== 'started'" class="px-3 py-2 text-xs text-right">
                  <span v-if="stock.pct_before_5d !== null" :class="stock.pct_before_5d >= 0 ? 'text-red-600' : 'text-green-600'">
                    {{ stock.pct_before_5d >= 0 ? '+' : '' }}{{ stock.pct_before_5d.toFixed(2) }}%
                  </span>
                  <span v-else class="text-gray-400">--</span>
                </td>
                <td v-if="activeTab !== 'started'" class="px-3 py-2 text-xs text-right">
                  <span v-if="stock.pct_after_5d !== null" :class="stock.pct_after_5d >= 0 ? 'text-red-600' : 'text-green-600'">
                    {{ stock.pct_after_5d >= 0 ? '+' : '' }}{{ stock.pct_after_5d.toFixed(2) }}%
                  </span>
                  <span v-else class="text-gray-400">--</span>
                </td>
                <td v-if="activeTab === 'started'" class="px-3 py-2 text-xs text-right">
                  <span v-if="stock.pct_after_5d_from_latest !== null && stock.pct_after_5d_from_latest !== undefined" :class="stock.pct_after_5d_from_latest >= 0 ? 'text-red-600' : 'text-green-600'">
                    {{ stock.pct_after_5d_from_latest >= 0 ? '+' : '' }}{{ stock.pct_after_5d_from_latest.toFixed(2) }}%
                  </span>
                  <span v-else class="text-gray-400">--</span>
                </td>
                <td v-if="activeTab === 'started'" class="px-3 py-2 text-xs text-right">
                  <span v-if="stock.pct_after_10d_from_latest !== null && stock.pct_after_10d_from_latest !== undefined" :class="stock.pct_after_10d_from_latest >= 0 ? 'text-red-600' : 'text-green-600'">
                    {{ stock.pct_after_10d_from_latest >= 0 ? '+' : '' }}{{ stock.pct_after_10d_from_latest.toFixed(2) }}%
                  </span>
                  <span v-else class="text-gray-400">--</span>
                </td>
                <td v-if="activeTab === 'started'" class="px-3 py-2 text-xs text-right">
                  <span v-if="stock.pct_after_30d_from_latest !== null && stock.pct_after_30d_from_latest !== undefined" :class="stock.pct_after_30d_from_latest >= 0 ? 'text-red-600' : 'text-green-600'">
                    {{ stock.pct_after_30d_from_latest >= 0 ? '+' : '' }}{{ stock.pct_after_30d_from_latest.toFixed(2) }}%
                  </span>
                  <span v-else class="text-gray-400">--</span>
                </td>
                <td v-if="activeTab !== 'started'" class="px-3 py-2 text-xs text-right">
                  <span :class="stock.latest_change >= 0 ? 'text-red-600' : 'text-green-600'">
                    {{ stock.latest_change >= 0 ? '+' : '' }}{{ stock.latest_change.toFixed(2) }}%
                  </span>
                </td>
                <td v-if="activeTab === 'golden_cross'" class="px-3 py-2 text-xs text-center">
                  <span v-if="getDiagnosis(stock.ts_code)" class="font-semibold">
                    {{ getDiagnosis(stock.ts_code).passed_count }}/3
                  </span>
                  <span v-else class="text-gray-400">-</span>
                </td>
                <td v-if="activeTab === 'watching'" class="px-3 py-2 text-xs text-center">
                  <span class="text-blue-600">{{ stock.check_count || 0 }}</span>
                </td>
                <td class="px-3 py-2 text-xs align-top" :class="{ 'overflow-hidden min-w-0': activeTab === 'started' }">
                  <span v-if="activeTab === 'golden_cross' && getDiagnosis(stock.ts_code)" :class="{
                    'text-green-600 font-semibold': getDiagnosis(stock.ts_code).passed_count === 3,
                    'text-yellow-600 font-semibold': getDiagnosis(stock.ts_code).passed_count === 2,
                    'text-blue-600': getDiagnosis(stock.ts_code).passed_count === 1,
                    'text-gray-600': getDiagnosis(stock.ts_code).passed_count === 0
                  }">
                    {{ getDiagnosis(stock.ts_code).advice }}
                  </span>
                  <div v-else-if="activeTab === 'watching' && stock.missing_conditions" class="text-green-600 font-semibold">
                    <template v-for="(condition, index) in stock.missing_conditions" :key="index">
                      <span>{{ condition }}</span>
                      <span v-if="index < stock.missing_conditions.length - 1">、</span>
                    </template>
                    <!-- 显示诊断结果中的距离信息 -->
                    <span v-if="getDiagnosis(stock.ts_code) && getDiagnosis(stock.ts_code).breakthrough_90d_detail" class="ml-2 text-gray-600">
                      （{{ getDiagnosis(stock.ts_code).breakthrough_90d_detail }}）
                    </span>
                  </div>
                  <!-- 显示已启动股票的风险原因列：只显示风险原因， truncate 防止撑破列 -->
                  <div v-if="activeTab === 'started'" class="overflow-hidden">
                    <div v-if="stock.risk_reasons && stock.risk_reasons.length > 0" class="truncate text-orange-600 text-xs" :title="stock.risk_reasons.join('、')">
                      {{ stock.risk_reasons.join('、') }}
                    </div>
                    <span v-else class="text-gray-400">--</span>
                  </div>
                  <!-- 其他标签页：显示风险原因或诊断建议 -->
                  <div v-else-if="stock.risk_reasons && stock.risk_reasons.length > 0" class="max-w-xs truncate text-orange-600" :title="stock.risk_reasons.join('、')">
                    {{ stock.risk_reasons.join('、') }}
                  </div>
                  <span v-else class="text-gray-400">--</span>
                </td>
                <!-- 操作建议列（应该在财务检测之前） -->
                <td v-if="activeTab === 'started'" class="px-3 py-2 text-center">
                  <div v-if="leaderDiagnosisActions[stock.ts_code]" class="flex items-center justify-center">
                    <span 
                      :class="{
                        'px-2 py-1 rounded text-xs font-semibold': true,
                        'bg-green-100 text-green-700': leaderDiagnosisActions[stock.ts_code] === '买入',
                        'bg-yellow-100 text-yellow-700': leaderDiagnosisActions[stock.ts_code] === '观望',
                        'bg-red-100 text-red-700': leaderDiagnosisActions[stock.ts_code] === '卖出',
                        'bg-gray-100 text-gray-700': !['买入', '观望', '卖出'].includes(leaderDiagnosisActions[stock.ts_code])
                      }"
                      :title="`点击查看详细诊断结果`"
                      @click="showLeaderDiagnose(stock)"
                      class="cursor-pointer hover:opacity-80"
                    >
                      {{ leaderDiagnosisActions[stock.ts_code] }}
                    </span>
                  </div>
                  <span v-else class="text-gray-400 text-xs">--</span>
                </td>
                <!-- 财务检测列：固定宽度，失败原因 truncate 防撑破 -->
                <td v-if="activeTab === 'started'" class="px-3 py-2 text-center align-top">
                  <div v-if="financialCheckResults[stock.ts_code]" class="overflow-hidden min-w-0">
                    <span v-if="financialCheckResults[stock.ts_code].is_passed" class="px-2 py-1 bg-green-100 text-green-700 rounded text-xs font-semibold">
                      ✅ 通过
                    </span>
                    <template v-else>
                      <span class="px-2 py-1 bg-red-100 text-red-700 rounded text-xs font-semibold block" :title="financialCheckResults[stock.ts_code].failure_reasons.join('、')">
                        ❌ 未通过
                      </span>
                      <div v-if="financialCheckResults[stock.ts_code].failure_reasons.length > 0" class="mt-1 text-xs text-red-600 truncate w-full" :title="financialCheckResults[stock.ts_code].failure_reasons.join('、')">
                        {{ financialCheckResults[stock.ts_code].failure_reasons[0] }}
                      </div>
                    </template>
                  </div>
                  <span v-else class="text-gray-400 text-xs">--</span>
                </td>
                <td v-if="activeTab === 'started'" class="px-3 py-2 text-center align-top">
                  <div class="flex items-center gap-2 justify-center">
                    <button
                      @click="showLeaderDiagnose(stock)"
                      :disabled="diagnosingLeader"
                      class="px-3 py-1 bg-purple-600 text-white text-xs rounded hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed"
                      :title="leaderDiagnosisActions[stock.ts_code] ? '查看诊断结果（已有缓存）' : '生成龙头诊断'"
                    >
                      {{ leaderDiagnosisActions[stock.ts_code] ? '👑 查看诊断' : '👑 龙头诊断' }}
                    </button>
                    <button
                      @click="addToWatchlist(stock)"
                      :disabled="addingToWatchlist"
                      class="px-3 py-1 bg-green-600 text-white text-xs rounded hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed"
                      title="加入跟踪池"
                    >
                      📋 加入
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- 快速提示（待候选监控页面不显示） -->
    <div v-if="!showRules && activeTab !== 'watching'" class="bg-blue-50 border border-blue-200 rounded-lg p-4 text-sm text-blue-700">
      <div class="font-semibold mb-2">💡 使用提示</div>
      <div class="space-y-1 text-xs">
        <div>• <strong>金叉候选</strong>：已金叉，等待核心条件满足（20分）</div>
        <div>• <strong>已启动</strong>：核心条件已满足，包含启动确认（70-90分，有风险）和完全启动（70-100分，无风险）</div>
        <div>• <strong>得分规则</strong>：金叉(20) + 核心条件(10分/条件，共4个条件最多40分) + 辅助条件(10分/条件，共3个条件最多30分）</div>
      </div>
    </div>

    <!-- 龙头诊断弹窗 -->
    <div v-if="showLeaderDiagnoseModal" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-lg max-w-4xl w-full max-h-[90vh] overflow-y-auto">
        <div class="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
          <h2 class="text-xl font-bold text-gray-800">👑 龙头诊断</h2>
          <button
            @click="showLeaderDiagnoseModal = false"
            class="text-gray-500 hover:text-gray-700 text-2xl"
          >
            ×
          </button>
        </div>
        
        <div class="p-6">
          <!-- 股票信息 -->
          <div v-if="leaderDiagnoseData?.stock_info" class="mb-4 pb-4 border-b border-gray-200">
            <div class="flex items-center justify-between">
              <div class="text-sm text-gray-600">
                <span class="font-semibold">{{ leaderDiagnoseData.stock_info.name }}</span>
                <span class="text-gray-400 mx-2">|</span>
                <span>{{ leaderDiagnoseData.stock_info.ts_code }}</span>
                <span class="text-gray-400 mx-2">|</span>
                <span>{{ leaderDiagnoseData.stock_info.trade_date }}</span>
              </div>
              <div class="flex items-center space-x-2">
                <span 
                  v-if="leaderDiagnoseData.cached" 
                  class="px-2 py-1 bg-blue-100 text-blue-700 rounded text-xs"
                  title="这是缓存的诊断结果"
                >
                  💾 缓存结果
                </span>
                <span 
                  v-if="leaderDiagnoseData.generated_at" 
                  class="text-xs text-gray-500"
                >
                  生成于: {{ new Date(leaderDiagnoseData.generated_at).toLocaleString('zh-CN') }}
                </span>
                <button
                  @click="refreshLeaderDiagnose(currentDiagnoseStock)"
                  class="px-3 py-1 bg-yellow-500 text-white rounded text-xs hover:bg-yellow-600"
                  title="重新生成诊断结果（将消耗API额度）"
                >
                  🔄 重新诊断
                </button>
              </div>
            </div>
          </div>

          <!-- 加载状态 -->
          <div v-if="diagnosingLeader" class="text-center py-8">
            <div class="text-gray-500">AI诊断中，请稍候...</div>
          </div>

          <!-- 错误提示 -->
          <div v-if="leaderDiagnoseError" class="bg-red-50 border border-red-300 rounded-lg p-4 mb-4">
            <div class="text-red-700">{{ leaderDiagnoseError }}</div>
          </div>

          <!-- 诊断结果 -->
          <div v-if="leaderDiagnoseData?.diagnosis && !diagnosingLeader">
            <!-- 龙头判断 -->
            <div v-if="leaderDiagnoseData.diagnosis.is_leader !== undefined" class="mb-6">
              <div class="bg-gradient-to-r from-purple-50 to-indigo-50 border-2 border-purple-300 rounded-lg p-4">
                <div class="flex items-center justify-between mb-2">
                  <h3 class="text-lg font-semibold text-gray-800 flex items-center">
                    <span class="text-2xl mr-2">{{ leaderDiagnoseData.diagnosis.is_leader ? '👑' : '📊' }}</span>
                    {{ leaderDiagnoseData.diagnosis.is_leader ? '是行业/板块龙头' : '非行业/板块龙头' }}
                  </h3>
                  <span 
                    :class="{
                      'px-3 py-1 rounded text-sm font-semibold': true,
                      'bg-green-100 text-green-700': leaderDiagnoseData.diagnosis.is_leader,
                      'bg-gray-100 text-gray-700': !leaderDiagnoseData.diagnosis.is_leader
                    }"
                  >
                    {{ leaderDiagnoseData.diagnosis.leader_type || '非龙头' }}
                  </span>
                </div>
                <div v-if="leaderDiagnoseData.diagnosis.leader_reason" class="text-sm text-gray-700 bg-white rounded p-3 mt-2">
                  <div class="font-semibold text-gray-800 mb-1">判断理由：</div>
                  {{ leaderDiagnoseData.diagnosis.leader_reason }}
                </div>
              </div>
            </div>
            
            <!-- 综合分析 -->
            <div v-if="leaderDiagnoseData.diagnosis.analysis" class="mb-6">
              <h3 class="text-lg font-semibold text-gray-800 mb-2">📊 综合分析</h3>
              <div class="bg-blue-50 border border-blue-200 rounded-lg p-4 text-sm text-gray-700 whitespace-pre-wrap">
                {{ leaderDiagnoseData.diagnosis.analysis }}
              </div>
            </div>

            <!-- 三级漏斗分析 -->
            <div class="space-y-4 mb-6">
              <div v-if="leaderDiagnoseData.diagnosis.level1_logic">
                <h3 class="text-md font-semibold text-gray-800 mb-2">第一级：逻辑与基本面驱动（核心）</h3>
                <div class="bg-green-50 border border-green-200 rounded-lg p-4 text-sm text-gray-700 whitespace-pre-wrap">
                  {{ leaderDiagnoseData.diagnosis.level1_logic }}
                </div>
              </div>

              <div v-if="leaderDiagnoseData.diagnosis.level2_market">
                <h3 class="text-md font-semibold text-gray-800 mb-2">第二级：市场与资金选择（量化模型作为初筛）</h3>
                <div class="bg-yellow-50 border border-yellow-200 rounded-lg p-4 text-sm text-gray-700 whitespace-pre-wrap">
                  {{ leaderDiagnoseData.diagnosis.level2_market }}
                </div>
              </div>

              <div v-if="leaderDiagnoseData.diagnosis.level3_timing">
                <h3 class="text-md font-semibold text-gray-800 mb-2">第三级：参与时机与风险管理</h3>
                <div class="bg-purple-50 border border-purple-200 rounded-lg p-4 text-sm text-gray-700 whitespace-pre-wrap">
                  {{ leaderDiagnoseData.diagnosis.level3_timing }}
                </div>
              </div>
            </div>

            <!-- 操作建议卡片 -->
            <div v-if="leaderDiagnoseData.diagnosis.recommendation" class="bg-gradient-to-r from-purple-50 to-blue-50 border border-purple-300 rounded-lg p-6">
              <h3 class="text-lg font-semibold text-gray-800 mb-4">💡 操作建议</h3>
              <div class="grid grid-cols-2 md:grid-cols-3 gap-4">
                <div v-if="leaderDiagnoseData.diagnosis.recommendation.action">
                  <div class="text-xs text-gray-600 mb-1">操作</div>
                  <div class="text-lg font-bold" :class="{
                    'text-green-600': leaderDiagnoseData.diagnosis.recommendation.action === '买入',
                    'text-yellow-600': leaderDiagnoseData.diagnosis.recommendation.action === '观望',
                    'text-red-600': leaderDiagnoseData.diagnosis.recommendation.action === '卖出'
                  }">
                    {{ leaderDiagnoseData.diagnosis.recommendation.action }}
                  </div>
                </div>
                <div v-if="leaderDiagnoseData.diagnosis.recommendation.price_range">
                  <div class="text-xs text-gray-600 mb-1">价格区间</div>
                  <div class="text-lg font-semibold text-gray-800">{{ leaderDiagnoseData.diagnosis.recommendation.price_range }}</div>
                </div>
                <div v-if="leaderDiagnoseData.diagnosis.recommendation.stop_loss">
                  <div class="text-xs text-gray-600 mb-1">止损位</div>
                  <div class="text-lg font-semibold text-red-600">{{ leaderDiagnoseData.diagnosis.recommendation.stop_loss }}</div>
                </div>
                <div v-if="leaderDiagnoseData.diagnosis.recommendation.target">
                  <div class="text-xs text-gray-600 mb-1">目标位</div>
                  <div class="text-lg font-semibold text-green-600">{{ leaderDiagnoseData.diagnosis.recommendation.target }}</div>
                </div>
                <div v-if="leaderDiagnoseData.diagnosis.recommendation.position">
                  <div class="text-xs text-gray-600 mb-1">建议仓位</div>
                  <div class="text-lg font-semibold text-gray-800">{{ leaderDiagnoseData.diagnosis.recommendation.position }}</div>
                </div>
                <div v-if="leaderDiagnoseData.diagnosis.recommendation.holding_period">
                  <div class="text-xs text-gray-600 mb-1">持有周期</div>
                  <div class="text-lg font-semibold text-gray-800">{{ leaderDiagnoseData.diagnosis.recommendation.holding_period }}</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 底部按钮 -->
        <div class="sticky bottom-0 bg-gray-50 border-t border-gray-200 px-6 py-4 flex items-center justify-end gap-2">
          <button
            @click="showLeaderDiagnoseModal = false"
            class="px-4 py-2 bg-gray-200 text-gray-700 rounded hover:bg-gray-300"
          >
            关闭
          </button>
          <button
            v-if="leaderDiagnoseData?.stock_info && leaderDiagnoseData.diagnosis.recommendation?.action === '买入'"
            @click="handleAddToWatchlistFromDiagnose"
            class="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700"
          >
            📋 加入跟踪池
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

// Tab配置（3个Tab：金叉候选、待候选监控、已启动）
const tabs = ref([
  { key: 'golden_cross', label: '🟡 金叉候选（观察池）', count: 0 },
  { key: 'watching', label: '🔔 待候选监控', count: 0 },
  { key: 'started', label: '✅ 已启动', count: 0 }  // 合并启动确认和完全启动
])

const activeTab = ref('golden_cross')
const queryDays = ref(10)
const excludeBrokenMa10 = ref(false)
// 筛选器：已启动Tab的子类型筛选（启动确认/完全启动）
const startedFilter = ref('all')  // 'all' | 'confirmed' | 'started'
// 筛选器：金叉候选Tab中是否只显示待监控股票
const showWatchingOnly = ref(false)
// 筛选器：金叉候选Tab中按诊断条件内容搜索
const diagnosisSearch = ref('')
// 筛选器：金叉候选Tab中仅显示未突破90日高点的股票
const notBreakthrough90dOnly = ref(false)
// 筛选器：财务检测筛选（已启动Tab）
const financialCheckFilter = ref('all')  // 'all' | 'passed' | 'failed' | 'not_checked'
// 筛选器：板块角色筛选（已启动Tab）
const sectorLeaderRoleFilter = ref('all')  // 'all' | '绝对龙头' | '补涨' | '跟风'
const loading = ref(false)
const diagnosing = ref(false)
const scanning = ref(false)
const recalculating = ref(false)
const checkingMa20 = ref(false)
const checkingExit = ref(false)
const checkingFinancial = ref(false)
const financialCheckResults = ref({})  // {ts_code: {is_passed, failure_reasons, industry}}
const leaderDiagnosisActions = ref({})  // {ts_code: '买入'|'观望'|'卖出'} 操作建议
const showRules = ref(false)
const watchServiceRunning = ref(false)
const watchList = ref([])
const allStocks = ref([])
const diagnosisResults = ref({})
const sortField = ref('entry_date')
const sortOrder = ref('desc')
const addingToWatchlist = ref(false)
const diagnosingLeader = ref(false)
const showLeaderDiagnoseModal = ref(false)
const leaderDiagnoseData = ref(null)
const leaderDiagnoseError = ref(null)
const currentDiagnoseStock = ref(null)

// 是否有诊断结果
const hasDiagnosisResults = computed(() => {
  return Object.keys(diagnosisResults.value).length > 0
})

// Tab统计信息（返回对象，包含两行信息）
const tabSummary = computed(() => {
  const stocks = displayStocks.value
  if (stocks.length === 0) return { line1: '暂无数据', line2: '' }
  
  if (activeTab.value === 'golden_cross') {
    const diagnosed = Object.keys(diagnosisResults.value).length
    const watchingCount = stocks.filter(s => s.is_watching).length
    return {
      line1: `共 ${stocks.length} 只 | 已诊断: ${diagnosed} 只`,
      line2: `待监控: ${watchingCount} 只`
    }
  } else if (activeTab.value === 'watching') {
    const status = watchServiceRunning.value ? '🟢 监控中' : '⚪ 已停止'
    return {
      line1: `共 ${stocks.length} 只`,
      line2: `监控状态: ${status}`
    }
  } else if (activeTab.value === 'started') {
    const confirmedCount = stocks.filter(s => s.stage === 'confirmed' || (s.score >= 40 && s.score < 70)).length
    const startedCount = stocks.filter(s => s.stage === 'started').length
    const broken = stocks.filter(s => s.is_broken_ma10).length
    const financialPassed = stocks.filter(s => financialCheckResults.value[s.ts_code]?.is_passed === true).length
    const financialFailed = stocks.filter(s => financialCheckResults.value[s.ts_code]?.is_passed === false).length
    const financialNotChecked = stocks.filter(s => !financialCheckResults.value[s.ts_code]).length
    return {
      line1: `共 ${stocks.length} 只 | 启动确认: ${confirmedCount} 只 | 完全启动: ${startedCount} 只 | 已破线: ${broken} 只`,
      line2: `财务检测: ✅通过 ${financialPassed} 只 | ❌未通过 ${financialFailed} 只 | ⚪未检测 ${financialNotChecked} 只`
    }
  }
  return { line1: '暂无数据', line2: '' }
})

// 显示的股票列表（根据Tab筛选）
const displayStocks = computed(() => {
  let filtered = allStocks.value

  // 根据Tab筛选
  if (activeTab.value === 'golden_cross') {
    filtered = filtered.filter(s => s.stage === 'golden_cross' && s.days_since_cross <= 7)
    // 金叉候选页面自动过滤跌破20日线的股票
    filtered = filtered.filter(s => !s.is_broken_ma10)
    // 筛选器：只显示待监控股票
    if (showWatchingOnly.value) {
      filtered = filtered.filter(s => s.is_watching === true)
    }
    // 筛选器：按诊断条件内容搜索（在诊断建议、细节描述中模糊匹配）
    const keyword = diagnosisSearch.value.trim()
    if (keyword) {
      const lower = keyword.toLowerCase()
      filtered = filtered.filter(s => {
        const d = getDiagnosis(s.ts_code)
        if (!d) return false
        const parts = []
        if (d.advice) parts.push(String(d.advice))
        if (d.breakthrough_90d_detail) parts.push(String(d.breakthrough_90d_detail))
        if (Array.isArray(d.core_details)) {
          parts.push(...d.core_details.map(x => String(x)))
        }
        const text = parts.join(' ').toLowerCase()
        return text.includes(lower)
      })
    }
  } else if (activeTab.value === 'watching') {
    // 待监控Tab显示单独的watchList（已排序）
    return sortWatchList(watchList.value)
  } else if (activeTab.value === 'started') {
    // 已启动Tab：合并启动确认和完全启动
    filtered = filtered.filter(s => 
      (s.stage === 'confirmed' || 
      s.stage === 'started' || 
      (s.score >= 40 && s.score < 100 && s.stage !== 'golden_cross')) &&
      !s.is_exited  // 排除已退出的股票
    )
    
    // 排除最新入选日期超过N个交易日前的数据
    // 只显示最近N个交易日内的数据（与后端查询保持一致，使用queryDays）
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    
    // 计算N个交易日前的日期（排除周末）
    // 往前查找，直到找到N个交易日（不包括今天）
    const tradingDaysToShow = queryDays.value  // 使用查询天数
    let cutoffDate = null
    let tradeDaysCount = 0
    let calendarDaysBack = 0
    
    // 往前查找N个交易日（不包括今天）
    while (tradeDaysCount < tradingDaysToShow && calendarDaysBack < tradingDaysToShow * 2) {
      calendarDaysBack++
      const checkDate = new Date(today)
      checkDate.setDate(checkDate.getDate() - calendarDaysBack)
      
      // 判断是否为交易日（周一到周五，排除周末）
      const dayOfWeek = checkDate.getDay()
      if (dayOfWeek >= 1 && dayOfWeek <= 5) { // 周一到周五
        tradeDaysCount++
        if (tradeDaysCount === tradingDaysToShow) {
          cutoffDate = new Date(checkDate)
          cutoffDate.setHours(0, 0, 0, 0)
          break
        }
      }
    }
    
    // 如果没找到N个交易日，使用一个默认的较早日期（往前推N*2个日历天）
    if (!cutoffDate) {
      cutoffDate = new Date(today)
      cutoffDate.setDate(cutoffDate.getDate() - tradingDaysToShow * 2)
      cutoffDate.setHours(0, 0, 0, 0)
    }
    
    // 将截止日期转换为字符串格式用于比较
    const cutoffDateStr = cutoffDate.toISOString().split('T')[0] // YYYY-MM-DD
    
    filtered = filtered.filter(s => {
      const latestEntryDate = s.latest_entry_date || s.entry_date
      if (!latestEntryDate) return true // 如果没有日期，保留
      
      // 解析日期字符串 (YYYY-MM-DD)
      // 处理可能的日期格式：YYYY-MM-DD 或 YYYY/MM/DD
      let entryDateStr
      if (typeof latestEntryDate === 'string') {
        // 统一转换为 YYYY-MM-DD 格式
        entryDateStr = latestEntryDate.replace(/\//g, '-').substring(0, 10)
      } else {
        // 如果是Date对象，转换为字符串
        const d = new Date(latestEntryDate)
        entryDateStr = d.toISOString().split('T')[0]
      }
      
      // 直接使用字符串比较（YYYY-MM-DD格式可以直接字符串比较）
      // 只保留最新入选日期在最近N个交易日内的数据（大于等于N个交易日前的日期）
      // 使用 >= 确保包含截止日期当天的数据
      const shouldKeep = entryDateStr >= cutoffDateStr
      
      return shouldKeep
    })
    
    // 筛选器：按子类型筛选
    if (startedFilter.value === 'confirmed') {
      filtered = filtered.filter(s => s.stage === 'confirmed' || (s.score >= 40 && s.score < 70))
    } else if (startedFilter.value === 'started') {
      filtered = filtered.filter(s => s.stage === 'started')
    }
  }

  // 排除已破20日线（已启动Tab可选）
  if (excludeBrokenMa10.value && activeTab.value === 'started') {
    filtered = filtered.filter(s => !s.is_broken_ma10)
  }

  // 财务检测筛选（已启动Tab）
  if (activeTab.value === 'started' && financialCheckFilter.value !== 'all') {
    if (financialCheckFilter.value === 'passed') {
      filtered = filtered.filter(s => financialCheckResults.value[s.ts_code]?.is_passed === true)
    } else if (financialCheckFilter.value === 'failed') {
      filtered = filtered.filter(s => financialCheckResults.value[s.ts_code]?.is_passed === false)
    } else if (financialCheckFilter.value === 'not_checked') {
      filtered = filtered.filter(s => !financialCheckResults.value[s.ts_code])
    }
  }

  // 板块角色筛选（已启动Tab）
  if (activeTab.value === 'started' && sectorLeaderRoleFilter.value !== 'all') {
    filtered = filtered.filter(s => s.sector_leader_role === sectorLeaderRoleFilter.value)
  }

  // 排序
  return [...filtered].sort((a, b) => {
    const field = sortField.value
    let aVal = a[field]
    let bVal = b[field]
    
    if (aVal == null && bVal == null) return 0
    if (aVal == null) return 1
    if (bVal == null) return -1
    
    let comparison = 0
    // ✅ 日期字段按字符串比较
    if (field === 'previous_entry_date' || field === 'latest_entry_date' || field === 'entry_date' || field === 'watch_start_date') {
      comparison = String(aVal).localeCompare(String(bVal))
    } else if (field === 'ts_code' || field === 'name') {
      comparison = String(aVal).localeCompare(String(bVal), 'zh-CN')
    } else {
      comparison = Number(aVal) - Number(bVal)
    }
    
    return sortOrder.value === 'desc' ? -comparison : comparison
  })
})

// 待监控列表排序（特殊处理）
function sortWatchList(list) {
  if (!list || list.length === 0) {
    return []
  }
  
  const field = sortField.value
  
  // 字段映射：将 entry_date 映射到 watch_start_date
  const fieldMap = {
    'entry_date': 'watch_start_date'
  }
  const actualField = fieldMap[field] || field
  
  const sorted = [...list].sort((a, b) => {
    let aVal = a[actualField]
    let bVal = b[actualField]
    
    if (aVal == null && bVal == null) return 0
    if (aVal == null) return 1
    if (bVal == null) return -1
    
    let comparison = 0
    // 日期字段按字符串比较
    if (actualField === 'watch_start_date' || actualField === 'golden_cross_date' || 
        actualField === 'first_entry_date' || actualField === 'latest_entry_date') {
      comparison = String(aVal).localeCompare(String(bVal))
    } else if (actualField === 'ts_code' || actualField === 'name') {
      comparison = String(aVal).localeCompare(String(bVal), 'zh-CN')
    } else {
      // 数值字段（包括 count_5d, check_count 等）
      const numA = Number(aVal) || 0
      const numB = Number(bVal) || 0
      comparison = numA - numB
    }
    
    // 如果主排序字段相同，使用次要排序（按股票代码）
    if (comparison === 0 && actualField !== 'ts_code') {
      comparison = String(a.ts_code).localeCompare(String(b.ts_code))
    }
    
    return sortOrder.value === 'desc' ? -comparison : comparison
  })
  
  return sorted
}

// 排序图标
function sortIcon(field) {
  if (sortField.value !== field) return ''
  return sortOrder.value === 'desc' ? '↓' : '↑'
}

// 排序
function sortBy(field) {
  if (sortField.value === field) {
    sortOrder.value = sortOrder.value === 'desc' ? 'asc' : 'desc'
  } else {
    sortField.value = field
    sortOrder.value = 'desc'
  }
}

// 进入启动原则
function enterStartupRules() {
  showRules.value = true
  // 滚动到规则区域
  setTimeout(() => {
    const rulesElement = document.getElementById('startup-rules')
    if (rulesElement) {
      rulesElement.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, 100)
}

// 加载数据
async function loadData() {
  loading.value = true
  
  try {
    // ✅ 根据当前Tab决定是否去重
    // 金叉候选、已启动都去重，只显示每只股票的最新记录
    const shouldDeduplicate = activeTab.value === 'golden_cross' || activeTab.value === 'started'
    
    const params = {
      days: queryDays.value,
      min_score: 20,  // 包含所有阶段
      started_only: false,
      exclude_broken_ma10: activeTab.value === 'golden_cross',  // ✅ 金叉候选Tab排除已破10日线的股票
      golden_cross_only: activeTab.value === 'golden_cross',  // ✅ 金叉候选Tab只查询金叉候选股票
      deduplicate: shouldDeduplicate  // ✅ 金叉候选、启动确认、完全启动Tab都去重
    }

    // 若在金叉候选Tab中填写了诊断条件搜索词，则传给后端做SQL级过滤
    if (activeTab.value === 'golden_cross') {
      if (diagnosisSearch.value.trim()) {
        params.diagnosis_contains = diagnosisSearch.value.trim()
      }
      if (notBreakthrough90dOnly.value) {
        params.not_breakthrough_90d_only = true
      }
    }

    const response = await axios.get(`${API_BASE_URL}/api/startup/candidates`, {
      params
    })
    
    if (response.data.success) {
      allStocks.value = response.data.data
      
      // 更新Tab计数（金叉候选排除已破10日线的股票）
      tabs.value[0].count = allStocks.value.filter(s => 
        s.stage === 'golden_cross' && 
        s.days_since_cross <= 7 && 
        !s.is_broken_ma10  // ✅ 排除已破20日线的股票（复用字段）
      ).length
      // 待监控数量由 loadWatchList 更新，此处不覆盖
      // 已启动Tab：合并启动确认和完全启动
      // ✅ 计数逻辑需要与displayStocks的筛选逻辑保持一致
      const startedStocks = allStocks.value.filter(s => {
        // 基本筛选：阶段和分数
        const stageMatch = s.stage === 'confirmed' || 
                          s.stage === 'started' || 
                          (s.score >= 40 && s.score < 100 && s.stage !== 'golden_cross')
        
        if (!stageMatch) return false
        
        // 排除已退出的股票
        if (s.is_exited) return false
        
        // ✅ 日期筛选：只计算在查询天数范围内的股票
        const latestEntryDate = s.latest_entry_date || s.entry_date
        if (!latestEntryDate) return true // 如果没有日期，保留
        
        // 解析日期字符串
        let entryDateStr
        if (typeof latestEntryDate === 'string') {
          entryDateStr = latestEntryDate.replace(/\//g, '-').substring(0, 10)
        } else {
          entryDateStr = latestEntryDate.toISOString().split('T')[0]
        }
        
        // 计算截止日期（与displayStocks逻辑一致）
        const today = new Date()
        today.setHours(0, 0, 0, 0)
        const tradingDaysToShow = queryDays.value
        let cutoffDate = null
        let tradeDaysCount = 0
        let calendarDaysBack = 0
        
        while (tradeDaysCount < tradingDaysToShow && calendarDaysBack < tradingDaysToShow * 2) {
          calendarDaysBack++
          const checkDate = new Date(today)
          checkDate.setDate(checkDate.getDate() - calendarDaysBack)
          const dayOfWeek = checkDate.getDay()
          if (dayOfWeek >= 1 && dayOfWeek <= 5) {
            tradeDaysCount++
            if (tradeDaysCount === tradingDaysToShow) {
              cutoffDate = new Date(checkDate)
              cutoffDate.setHours(0, 0, 0, 0)
              break
            }
          }
        }
        
        if (!cutoffDate) {
          cutoffDate = new Date(today)
          cutoffDate.setDate(cutoffDate.getDate() - tradingDaysToShow * 2)
          cutoffDate.setHours(0, 0, 0, 0)
        }
        
        const cutoffDateStr = cutoffDate.toISOString().split('T')[0]
        return entryDateStr >= cutoffDateStr
      })
      
      tabs.value[2].count = startedStocks.length
      
      console.log('数据加载成功:', allStocks.value.length, '只股票')
      
      // 调试：检查财务检测结果数据
      const stocksWithFinancialCheck = allStocks.value.filter(s => s.financial_check_result)
      console.log(`🔍 调试：从API返回的数据中，有 ${stocksWithFinancialCheck.length} 只股票包含财务检测结果`)
      if (stocksWithFinancialCheck.length > 0) {
        console.log('🔍 示例股票财务检测结果:', stocksWithFinancialCheck[0].ts_code, stocksWithFinancialCheck[0].financial_check_result)
      }
      
      // 检查持久化的诊断结果，自动加载到内存（排除已破20日线的股票）
      const goldenStocks = allStocks.value.filter(s => 
        s.stage === 'golden_cross' && 
        s.days_since_cross <= 7 && 
        !s.is_broken_ma10  // ✅ 排除已破20日线的股票（复用字段）
      )
      let loadedFromDb = 0
      goldenStocks.forEach(stock => {
        if (stock.diagnosis_result && !diagnosisResults.value[stock.ts_code]) {
          diagnosisResults.value[stock.ts_code] = stock.diagnosis_result
          loadedFromDb++
        }
      })
      
      if (loadedFromDb > 0) {
        console.log(`✅ 从数据库加载了 ${loadedFromDb} 只股票的诊断结果`)
      }
      
      // ✅ 检查持久化的财务检测结果，自动加载到内存（已启动Tab）
      await reloadFinancialCheckResultsFromDb()
      
      // ✅ 加载龙头诊断操作建议（已启动Tab）
      if (activeTab.value === 'started') {
        await loadLeaderDiagnosisActions()
      }
      
      // 如果当前是已启动tab，统计未检测的股票数量
      const startedStocksForFinancial = allStocks.value.filter(s => 
        s.stage === 'confirmed' || s.stage === 'started'
      )
      if (activeTab.value === 'started' && startedStocksForFinancial.length > 0) {
        const uncheckedCount = startedStocksForFinancial.filter(s => 
          !s.financial_check_result || !s.last_financial_check_date
        ).length
        
        if (uncheckedCount > 0) {
          console.log(`💡 发现 ${uncheckedCount} 只未检测的股票，可点击"自动检测全部"按钮进行批量检测`)
        }
      }
      
      // 检查是否有诊断结果，如果金叉候选数量变化，提示重新诊断
      const currentGoldenCount = tabs.value[0].count
      const diagnosedCount = Object.keys(diagnosisResults.value).length
      if (currentGoldenCount > 0 && diagnosedCount === 0) {
        console.log('💡 提示：有金叉候选股票，可点击"批量诊断"查看核心条件满足情况')
      } else if (loadedFromDb > 0) {
        console.log(`📊 已加载历史诊断结果（${diagnosedCount}只），点击"重新诊断"可更新最新数据`)
      }
      
      // ✅ 同步刷新待监控列表及Tab计数（批量诊断、扫描等操作后数量会变化）
      await loadWatchList()
    }
  } catch (error) {
    console.error('加载失败:', error)
    alert('加载失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    loading.value = false
  }
}

// 重新计算表现数据
async function recalculatePerformance() {
  recalculating.value = true
  
  try {
    // ✅ 根据当前Tab决定计算哪些股票的表现
    const startedOnly = activeTab.value === 'started'
    const goldenCrossOnly = activeTab.value === 'golden_cross'
    const excludeBrokenMa10 = activeTab.value === 'golden_cross'  // 金叉候选Tab排除破20日线
    
    const response = await axios.post(`${API_BASE_URL}/api/startup/candidates/recalculate-performance`, null, {
      params: {
        days: queryDays.value,
        started_only: startedOnly,
        golden_cross_only: goldenCrossOnly,
        exclude_broken_ma10: excludeBrokenMa10
      }
    })
    
    if (response.data.success) {
      alert(`✅ ${response.data.message}\n\n${response.data.note}`)
      // 重新加载数据以显示最新计算结果
      await loadData()
    } else {
      alert('重新计算失败: ' + (response.data.message || '未知错误'))
    }
  } catch (error) {
    console.error('重新计算失败:', error)
    alert('重新计算失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    recalculating.value = false
  }
}

// 检查退出条件
async function checkExit() {
  checkingExit.value = true
  
  try {
    const response = await axios.post(`${API_BASE_URL}/api/startup/check-exit`)
    
    if (response.data.success) {
      const data = response.data.data
      alert(
        `✅ ${response.data.message}\n\n` +
        `检查数量: ${data.checked_count} 只\n` +
        `已退出: ${data.exited_count} 只`
      )
      // 重新加载数据，已退出的股票会被自动过滤
      await loadData()
    } else {
      alert('检查失败: ' + (response.data.message || '未知错误'))
    }
  } catch (error) {
    console.error('检查退出条件失败:', error)
    alert('检查失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    checkingExit.value = false
  }
}

// 从数据库重新加载财务检测结果
async function reloadFinancialCheckResultsFromDb() {
  const startedStocksForFinancial = allStocks.value.filter(s => 
    s.stage === 'confirmed' || s.stage === 'started'
  )
  let loadedFinancialFromDb = 0
  let skippedCount = 0
  
  console.log(`🔍 开始加载财务检测结果，已启动股票数量: ${startedStocksForFinancial.length}`)
  
  startedStocksForFinancial.forEach(stock => {
    if (stock.financial_check_result) {
      // 更新或添加财务检测结果（不清空已有结果）
      financialCheckResults.value[stock.ts_code] = {
        is_passed: stock.financial_check_result.is_passed || false,
        failure_reasons: stock.financial_check_result.failure_reasons || [],
        industry: stock.financial_check_result.industry || '未知',
        sector: stock.financial_check_result.sector || '未知',
        check_date: stock.financial_check_result.check_date || stock.last_financial_check_date
      }
      loadedFinancialFromDb++
      console.log(`  ✅ ${stock.ts_code} (${stock.name}): 加载财务检测结果 - 通过: ${stock.financial_check_result.is_passed}`)
    } else {
      skippedCount++
      // 调试：检查为什么没有财务检测结果
      if (stock.last_financial_check_date) {
        console.log(`  ⚠️ ${stock.ts_code} (${stock.name}): 有检测日期但无结果数据`)
      }
    }
  })
  
  console.log(`✅ 财务检测结果加载完成: 加载 ${loadedFinancialFromDb} 只，跳过 ${skippedCount} 只`)
  
  if (loadedFinancialFromDb > 0) {
    console.log(`✅ 从数据库加载了 ${loadedFinancialFromDb} 只股票的财务检测结果`)
  } else {
    console.log(`⚠️ 未找到任何财务检测结果，请检查数据库或重新检测`)
  }
}

// 财务检测任务轮询
const financialCheckTaskId = ref(null)
const financialCheckProgress = ref(0)
const financialCheckMessage = ref('')

// 财务检测（仅检测当前列表中尚未有结果的股票）- 异步版本
async function checkFinancial() {
  if (displayStocks.value.length === 0) {
    alert('当前没有可检测的股票')
    return
  }

  // 只检测尚未有财务检测结果的股票
  const ts_codes = displayStocks.value
    .filter(s => !financialCheckResults.value[s.ts_code])
    .map(s => s.ts_code)

  if (ts_codes.length === 0) {
    alert('当前列表中的股票均已检测过，无需重复检测')
    return
  }

  checkingFinancial.value = true
  financialCheckProgress.value = 0
  financialCheckMessage.value = '正在创建检测任务...'

  try {
    // 1. 创建异步任务
    const response = await axios.post(`${API_BASE_URL}/api/startup/financial-check`, {
      ts_codes: ts_codes
    })

    if (!response.data.success) {
      alert('创建检测任务失败: ' + (response.data.message || '未知错误'))
      checkingFinancial.value = false
      return
    }

    const taskId = response.data.task_id
    financialCheckTaskId.value = taskId
    financialCheckMessage.value = '检测任务已创建，正在执行...'

    // 2. 轮询查询任务状态
    const result = await pollFinancialCheckStatus(taskId)

    if (result.success) {
      // 将结果存储到financialCheckResults中
      result.results.forEach(r => {
        financialCheckResults.value[r.ts_code] = {
          is_passed: r.is_passed,
          failure_reasons: r.failure_reasons || [],
          industry: r.industry || '未知',
          sector: r.sector || '未知',
          check_date: r.check_date || r.actual_data_date
        }
      })

      // 检测完成后，重新从数据库加载
      await reloadFinancialCheckResultsFromDb()

      // 显示统计信息
      const summary = result.summary
      alert(
        `✅ 财务检测完成\n\n` +
        `检测数量: ${summary.total} 只\n` +
        `通过: ${summary.passed} 只\n` +
        `未通过: ${summary.failed} 只\n` +
        `通过率: ${summary.pass_rate}%`
      )
    } else {
      alert('财务检测失败: ' + (result.error || '未知错误'))
    }
  } catch (error) {
    console.error('财务检测失败:', error)
    alert('财务检测失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    checkingFinancial.value = false
    financialCheckTaskId.value = null
    financialCheckProgress.value = 0
    financialCheckMessage.value = ''
  }
}

// 轮询财务检测任务状态
async function pollFinancialCheckStatus(taskId, maxRetries = 60) {
  const pollInterval = 2000 // 2秒轮询一次

  for (let i = 0; i < maxRetries; i++) {
    try {
      const response = await axios.get(`${API_BASE_URL}/api/startup/financial-check/status/${taskId}`)
      const data = response.data

      if (!data.success) {
        return { success: false, error: data.message || '查询状态失败' }
      }

      financialCheckProgress.value = data.progress || 0
      financialCheckMessage.value = data.message || '检测中...'

      if (data.status === 'completed') {
        return {
          success: true,
          results: data.results || [],
          summary: data.summary || {}
        }
      } else if (data.status === 'failed') {
        return { success: false, error: data.error || '检测失败' }
      }

      // 继续轮询
      await new Promise(resolve => setTimeout(resolve, pollInterval))
    } catch (error) {
      console.error('轮询任务状态失败:', error)
      await new Promise(resolve => setTimeout(resolve, pollInterval))
    }
  }

  return { success: false, error: '检测超时，请稍后刷新页面查看结果' }
}

// 自动检测所有未检测的股票 - 异步版本
async function autoCheckAllFinancial() {
  if (!confirm('是否自动检测所有已启动但未检测的股票？\n\n这将检测最近30天内所有已启动但未进行财务检测的股票。')) {
    return
  }

  checkingFinancial.value = true
  financialCheckProgress.value = 0
  financialCheckMessage.value = '正在创建自动检测任务...'

  try {
    // 1. 创建异步任务
    const response = await axios.post(`${API_BASE_URL}/api/startup/financial-check/auto?days=30`)

    if (!response.data.success) {
      // 如果没有需要检测的股票
      if (response.data.message && response.data.message.includes('没有需要检测')) {
        alert(response.data.message)
      } else {
        alert('创建检测任务失败: ' + (response.data.message || '未知错误'))
      }
      checkingFinancial.value = false
      return
    }

    // 如果没有任务ID，说明没有需要检测的股票
    if (!response.data.task_id) {
      alert(response.data.message || '没有需要检测的股票')
      checkingFinancial.value = false
      return
    }

    const taskId = response.data.task_id
    financialCheckTaskId.value = taskId
    financialCheckMessage.value = '自动检测任务已创建，正在执行...'

    // 2. 轮询查询任务状态
    const result = await pollFinancialCheckStatus(taskId)

    if (result.success) {
      // 将结果存储到financialCheckResults中
      result.results.forEach(r => {
        financialCheckResults.value[r.ts_code] = {
          is_passed: r.is_passed,
          failure_reasons: r.failure_reasons || [],
          industry: r.industry || '未知',
          sector: r.sector || '未知'
        }
      })

      // 显示统计信息
      const summary = result.summary
      alert(
        `✅ 自动检测完成\n\n` +
        `检测数量: ${summary.total} 只\n` +
        `通过: ${summary.passed} 只\n` +
        `未通过: ${summary.failed} 只\n` +
        `通过率: ${summary.pass_rate}%\n\n` +
        `提示：请刷新页面查看最新结果`
      )

      // 自动刷新数据
      await loadStocks()
      await reloadFinancialCheckResultsFromDb()
    } else {
      alert('自动检测失败: ' + (result.error || '未知错误'))
    }
  } catch (error) {
    console.error('自动检测失败:', error)
    alert('自动检测失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    checkingFinancial.value = false
    financialCheckTaskId.value = null
    financialCheckProgress.value = 0
    financialCheckMessage.value = ''
  }
}

// 检查20日线
async function checkMa20() {
  checkingMa20.value = true
  
  try {
    const response = await axios.post(`${API_BASE_URL}/api/startup/candidates/check-ma20`)
    
    if (response.data.success) {
      const data = response.data.data
      alert(
        `✅ ${response.data.message}\n\n` +
        `检查数量: ${data.checked_count} 只\n` +
        `跌破20日线: ${data.broken_count} 只\n` +
        `已更新状态: ${data.updated_count} 只`
      )
      // 重新加载数据，跌破20日线的股票会被自动过滤（如果excludeBrokenMa10为true）
      await loadData()
    } else {
      alert('检查失败: ' + (response.data.message || '未知错误'))
    }
  } catch (error) {
    console.error('检查20日线失败:', error)
    alert('检查失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    checkingMa20.value = false
  }
}

// 批量诊断
async function batchDiagnose() {
  diagnosing.value = true
  
  try {
    const response = await axios.post(`${API_BASE_URL}/api/startup/diagnose-batch`)
    
    if (response.data.success) {
      const results = {}
      response.data.data.forEach(item => {
        results[item.ts_code] = item
      })
      diagnosisResults.value = results
      
      const message = `✅ 批量诊断完成！\n\n诊断股票: ${response.data.count} 只\n更新数据库: ${response.data.updated_count} 只`
      console.log(message)
      alert(message)
      
      // 重新加载数据以显示更新后的stage和score
      // 注意：不清空 diagnosisResults，保留诊断结果
      await loadData()
      
      // 刷新待监控列表（批量诊断会自动标记3/4条件的股票）
      await loadWatchList()
      
      // 提示推荐数量（后端已不再自动推荐，此字段可能不存在）
      if (response.data.recommended_count && response.data.recommended_count > 0) {
        console.log(`💎 新增推荐: ${response.data.recommended_count} 只`)
      }
    }
  } catch (error) {
    console.error('批量诊断失败:', error)
    alert('诊断失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    diagnosing.value = false
  }
}

// 扫描新股票
async function scanTodayStocks() {
  if (!confirm('确认扫描今日所有主板股票？此操作可能需要几分钟。')) {
    return
  }
  
  scanning.value = true
  
  try {
    const response = await axios.get(`${API_BASE_URL}/api/startup/scan`, {
      params: {
        universe: 'mainboard',  // 主板股票
        min_score: 20  // 包含金叉候选（最低20分）
      }
    })
    
    if (response.data.success) {
      const summary = response.data.summary
      alert(
        `✅ 扫描完成！\n\n` +
        `扫描总数: ${summary.total_scanned} 只\n` +
        `保存候选: ${summary.saved_count} 只\n` +
        `  🟡 金叉候选: ${summary.golden_cross_count} 只\n` +
        `  ✅ 已启动: ${(summary.confirmed_count || 0) + (summary.started_count || 0)} 只（启动确认: ${summary.confirmed_count || 0} 只，完全启动: ${summary.started_count || 0} 只）`
      )
      
      // 重新加载数据
      await loadData()
    }
  } catch (error) {
    console.error('扫描失败:', error)
    alert('扫描失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    scanning.value = false
  }
}

// 格式化日期
function formatDate(dateStr) {
  if (!dateStr) return '--'
  // YYYY-MM-DD 转为 MM/DD
  if (typeof dateStr === 'string' && dateStr.length === 10) {
    return dateStr.substring(5).replace('-', '/')
  }
  return dateStr
}

// 格式化成交额
function formatAmount(value) {
  if (value === null || value === undefined) {
    return '--'
  }
  const v = value || 0
  if (v >= 1e8) return (v / 1e8).toFixed(2) + '亿'
  if (v >= 1e4) return (v / 1e4).toFixed(2) + '万'
  return v.toFixed(2)
}

// 获取诊断结果（优先从内存，其次从数据库）
function getDiagnosis(ts_code) {
  // 1. 优先从内存中的批量诊断结果获取
  if (diagnosisResults.value[ts_code]) {
    return diagnosisResults.value[ts_code]
  }
  
  // 2. 从数据库持久化的诊断结果获取
  const stock = allStocks.value.find(s => s.ts_code === ts_code)
  if (stock && stock.diagnosis_result) {
    return stock.diagnosis_result
  }
  
  // 3. 从待监控列表获取
  if (activeTab.value === 'watching') {
    const watchStock = watchList.value.find(s => s.ts_code === ts_code)
    if (watchStock && watchStock.diagnosis_result) {
      return watchStock.diagnosis_result
    }
  }
  
  return null
}

// 加载待监控列表
async function loadWatchList() {
  try {
    const response = await axios.get(`${API_BASE_URL}/api/startup/watch/list`)
    
    if (response.data.success) {
      watchList.value = response.data.data
      tabs.value[1].count = watchList.value.length
    }
  } catch (error) {
    console.error('加载待监控列表失败:', error)
  }
}

// 启动监控服务
async function startWatchService() {
  try {
    const response = await axios.post(`${API_BASE_URL}/api/startup/watch/start`)
    
    if (response.data.success) {
      watchServiceRunning.value = true
      alert(response.data.message)
      await loadWatchStatus()
    } else {
      alert(response.data.message)
    }
  } catch (error) {
    console.error('启动监控服务失败:', error)
    alert('启动失败: ' + (error.response?.data?.detail || error.message))
  }
}

// 停止监控服务
async function stopWatchService() {
  try {
    const response = await axios.post(`${API_BASE_URL}/api/startup/watch/stop`)
    
    if (response.data.success) {
      watchServiceRunning.value = false
      alert(response.data.message)
    } else {
      alert(response.data.message)
    }
  } catch (error) {
    console.error('停止监控服务失败:', error)
    alert('停止失败: ' + (error.response?.data?.detail || error.message))
  }
}

// 加载监控服务状态
async function loadWatchStatus() {
  try {
    const response = await axios.get(`${API_BASE_URL}/api/startup/watch/status`)
    
    if (response.data.success) {
      watchServiceRunning.value = response.data.data.is_running
    }
  } catch (error) {
    console.error('加载监控状态失败:', error)
  }
}

// 立即检查
async function checkNow() {
  try {
    const response = await axios.post(`${API_BASE_URL}/api/startup/watch/check-now`)
    
    if (response.data.success) {
      alert('✅ 检查已执行')
      await loadWatchList()
    }
  } catch (error) {
    console.error('执行检查失败:', error)
    alert('检查失败: ' + (error.response?.data?.detail || error.message))
  }
}

// 单只股票加入跟踪池
async function addToWatchlist(stock) {
  try {
    const stageText = stock.stage === 'started' ? '完全启动' : '启动确认'
    const note = `股票启动-${stageText}`
    
    const response = await axios.post(`${API_BASE_URL}/api/watchlist`, {
      ts_code: stock.ts_code,
      note: note
    })
    
    if (response.data.success) {
      alert(`✅ ${stock.name} (${stock.ts_code}) 已加入跟踪池`)
    } else {
      alert('加入失败：' + (response.data.message || '未知错误'))
    }
  } catch (error) {
    console.error('加入跟踪池失败:', error)
    const errorMsg = error.response?.data?.message || error.response?.data?.detail || error.message
    // 如果股票已在跟踪列表中，提示信息更友好
    if (errorMsg && errorMsg.includes('已在跟踪列表中')) {
      alert(`ℹ️ ${stock.name} (${stock.ts_code}) 已在跟踪池中`)
    } else {
      alert('加入失败：' + errorMsg)
    }
  }
}

// 批量加入跟踪池
async function batchAddToWatchlist() {
  const stocks = displayStocks.value
  if (stocks.length === 0) {
    alert('没有可添加的股票')
    return
  }
  
  if (!confirm(`确定要将当前列表中的 ${stocks.length} 只股票加入跟踪池吗？\n加入理由：股票启动`)) {
    return
  }
  
  addingToWatchlist.value = true
  let successCount = 0
  let failCount = 0
  let existingCount = 0
  
  try {
    for (const stock of stocks) {
      try {
        const stageText = stock.stage === 'started' ? '完全启动' : '启动确认'
        const note = `股票启动-${stageText}`
        
        const response = await axios.post(`${API_BASE_URL}/api/watchlist`, {
          ts_code: stock.ts_code,
          note: note
        })
        
        if (response.data.success) {
          successCount++
        } else {
          if (response.data.message && response.data.message.includes('已在跟踪列表中')) {
            existingCount++
          } else {
            failCount++
          }
        }
      } catch (error) {
        const errorMsg = error.response?.data?.message || error.response?.data?.detail || ''
        if (errorMsg.includes('已在跟踪列表中')) {
          existingCount++
        } else {
          failCount++
        }
      }
    }
    
    const message = `批量加入完成：\n成功: ${successCount} 只\n已存在: ${existingCount} 只${failCount > 0 ? `\n失败: ${failCount} 只` : ''}`
    alert(message)
  } catch (error) {
    console.error('批量加入跟踪池失败:', error)
    alert('批量加入失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    addingToWatchlist.value = false
  }
}

// ✅ 监听Tab切换，重新加载数据（确保去重参数正确）
watch(activeTab, (newTab) => {
  // 切换到"已启动"Tab时，自动设置为30个交易日
  if (newTab === 'started') {
    if (queryDays.value < 30) {
      queryDays.value = 30
    }
    // 加载操作建议
    loadLeaderDiagnosisActions()
  }
  // 切换到"待候选监控"Tab时，加载待监控列表
  if (newTab === 'watching') {
    loadWatchList()
  }
  // 切换到"已启动"Tab时，需要重新加载数据以应用去重
  if (newTab === 'confirmed' || newTab === 'started' || newTab === 'golden_cross') {
    loadData()
  }
})

// 龙头诊断
async function showLeaderDiagnose(stock, forceRefresh = false) {
  currentDiagnoseStock.value = stock
  showLeaderDiagnoseModal.value = true
  leaderDiagnoseData.value = null
  leaderDiagnoseError.value = null
  diagnosingLeader.value = true

  try {
    const params = { trade_date: new Date().toISOString().split('T')[0] }
    if (forceRefresh) {
      params.force_refresh = 'true'
    }
    
    const response = await axios.post(
      `${API_BASE_URL}/api/startup/leader-diagnose/${stock.ts_code}`,
      null,
      { params }
    )

    if (response.data.success) {
      leaderDiagnoseData.value = response.data
      if (response.data.cached) {
        console.log('使用缓存的诊断结果')
      } else {
        console.log('生成新的诊断结果')
      }
      // 更新操作建议（无论缓存还是新生成）
      if (response.data.diagnosis?.recommendation?.action) {
        leaderDiagnosisActions.value[stock.ts_code] = response.data.diagnosis.recommendation.action
      }
    } else {
      leaderDiagnoseError.value = response.data.message || '龙头诊断失败'
    }
  } catch (error) {
    leaderDiagnoseError.value = error.response?.data?.message || error.message || '龙头诊断请求失败'
  } finally {
    diagnosingLeader.value = false
  }
}

async function refreshLeaderDiagnose(stock) {
  // 强制刷新：先删除缓存，再重新诊断
  await showLeaderDiagnose(stock, true)
  // 刷新后重新加载操作建议
  if (activeTab.value === 'started') {
    await loadLeaderDiagnosisActions()
  }
}

async function loadLeaderDiagnosisActions() {
  // 批量加载已启动股票的操作建议
  const startedStocks = allStocks.value.filter(s => 
    s.stage === 'confirmed' || s.stage === 'started'
  )
  
  if (startedStocks.length === 0) {
    return
  }
  
  try {
    const tsCodes = startedStocks.map(s => s.ts_code).join(',')
    const tradeDate = new Date().toISOString().split('T')[0]
    
    const response = await axios.get(`${API_BASE_URL}/api/startup/leader-diagnosis/batch`, {
      params: {
        ts_codes: tsCodes,
        trade_date: tradeDate
      }
    })
    
    if (response.data.success) {
      // 更新操作建议
      Object.assign(leaderDiagnosisActions.value, response.data.results)
      console.log(`✅ 加载了 ${Object.keys(response.data.results).length} 个操作建议`)
    }
  } catch (error) {
    console.error('加载操作建议失败:', error)
  }
}

function handleAddToWatchlistFromDiagnose() {
  if (currentDiagnoseStock.value) {
    addToWatchlist(currentDiagnoseStock.value)
    showLeaderDiagnoseModal.value = false
  }
}

// 页面加载时自动查询
onMounted(() => {
  loadData()
  loadWatchList()
  loadWatchStatus()
})
</script>

