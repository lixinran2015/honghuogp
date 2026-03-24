<template>
  <div class="container mx-auto px-4 py-6">
    <!-- 页面标题 -->
    <div class="mb-6 flex items-start justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-800">👑 板块龙头管理</h1>
        <p class="text-sm text-gray-500 mt-1">查询和管理各行各业的龙头股票数据</p>
      </div>
      
      <div class="flex items-center space-x-2">
        <!-- 龙头判断原则按钮（与股票启动原则同款展示方式） -->
        <button
          @click="enterLeaderRules"
          class="px-4 py-2 bg-amber-500 text-white rounded hover:bg-amber-600 text-sm flex items-center space-x-1"
        >
          <span>📋</span>
          <span>龙头判断原则</span>
        </button>
        
        <!-- 操作按钮组 -->
        <!-- 更新方法选择 -->
        <select
          v-model="updateMethod"
          class="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-green-500 text-sm"
        >
          <option value="comprehensive">综合龙头（推荐）</option>
          <option value="value">价值龙头</option>
          <option value="market">市场龙头</option>
          <option value="market_cap">市值法</option>
          <option value="revenue">营收法</option>
        </select>
        
        <!-- 更新板块龙头按钮 -->
        <button
          @click="updateFromAPI"
          :disabled="updating"
          class="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:bg-gray-400 text-sm flex items-center space-x-1"
        >
          <span v-if="updating" class="animate-spin">⏳</span>
          <span v-else>🔄</span>
          <span>{{ updating ? '更新中...' : '更新板块龙头' }}</span>
        </button>
        
        <!-- 新增按钮 -->
        <button
          @click="showAddModal = true"
          class="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm flex items-center space-x-1"
        >
          <span>➕</span>
          <span>新增龙头</span>
        </button>
      </div>
    </div>

    <!-- 龙头判断原则说明（可折叠，与启动原则同款展示） -->
    <div v-if="showLeaderRules" id="leader-rules" class="bg-gradient-to-r from-amber-50 to-orange-50 border border-amber-200 rounded-lg p-6 mb-6">
      <div class="flex items-start justify-between mb-4">
        <h2 class="text-lg font-bold text-gray-800">📋 龙头判断原则</h2>
        <button
          @click="showLeaderRules = false"
          class="text-amber-700 hover:text-amber-900 text-sm px-2 py-1 rounded hover:bg-amber-100"
        >
          收起
        </button>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <!-- 一、行业龙头识别方法 -->
        <div class="bg-white rounded-lg p-4 shadow-sm">
          <h3 class="font-semibold text-amber-600 mb-3 flex items-center">
            <span class="text-lg mr-2">1️⃣</span>
            行业/板块龙头识别方法
          </h3>
          <p class="text-xs text-gray-500 mb-3">更新板块龙头时可选以下方法，综合龙头为推荐。</p>
          <div class="space-y-2 text-sm text-gray-700">
            <div class="flex items-start">
              <span class="text-amber-500 mr-2">✓</span>
              <span><strong>综合龙头（推荐）</strong>：市值 30% + 营收 25% + ROE 25% + 营收增长率 20%，综合考虑规模、盈利与成长性。</span>
            </div>
            <div class="flex items-start">
              <span class="text-amber-500 mr-2">○</span>
              <span><strong>价值龙头</strong>：基于 ROE、营收、增长率等财务指标的综合评分。</span>
            </div>
            <div class="flex items-start">
              <span class="text-amber-500 mr-2">○</span>
              <span><strong>市场龙头</strong>：基于市场热度、涨幅、成交额等市场表现评分。</span>
            </div>
            <div class="flex items-start">
              <span class="text-amber-500 mr-2">○</span>
              <span><strong>市值法</strong>：取市值最大的 N 只，数据简单但可能含高估或忽略盈利。</span>
            </div>
            <div class="flex items-start">
              <span class="text-amber-500 mr-2">○</span>
              <span><strong>营收法</strong>：取营收最大的 N 只，反映业务规模。</span>
            </div>
          </div>
        </div>

        <!-- 二、板块角色：绝对龙头 / 补涨 / 跟风 -->
        <div class="bg-white rounded-lg p-4 shadow-sm">
          <h3 class="font-semibold text-amber-600 mb-3 flex items-center">
            <span class="text-lg mr-2">2️⃣</span>
            板块角色（绝对龙头 / 补涨 / 跟风）
          </h3>
          <p class="text-xs text-gray-500 mb-3">在滚动窗口内按涨幅、成交额、市值识别板块内结构。</p>
          <div class="space-y-2 text-sm text-gray-700">
            <div class="flex items-start">
              <span class="text-amber-500 mr-2">✓</span>
              <span><strong>绝对龙头</strong>：综合评分 = 涨幅×0.4 + 成交额归一化×0.3 + 市值归一化×0.3，取评分最高的一只。</span>
            </div>
            <div class="flex items-start">
              <span class="text-amber-500 mr-2">○</span>
              <span><strong>补涨</strong>：排除绝对龙头后，按「成交额/涨幅」比排序，取成交额放大最明显的一只。</span>
            </div>
            <div class="flex items-start">
              <span class="text-amber-500 mr-2">○</span>
              <span><strong>跟风</strong>：其余窗口内有涨幅的股票，按涨幅排序，最多展示若干只。</span>
            </div>
          </div>
          <div class="mt-3 pt-3 border-t border-gray-200 text-xs text-gray-600">
            💡 若本板块普跌，则取跌幅最小（相对抗跌）作为代表，标注为「相对抗跌」；板块角色由「板块龙头更新」任务定期更新。
          </div>
        </div>
      </div>

      <!-- 龙头类型说明 -->
      <div class="mt-6 bg-white rounded-lg p-4 shadow-sm">
        <h3 class="font-semibold text-gray-800 mb-3">📊 龙头类型与数据来源</h3>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
          <div class="p-3 bg-yellow-50 rounded">
            <div class="font-bold text-yellow-700">行业龙头</div>
            <div class="text-gray-600 mt-1 text-xs">该行业内综合/价值/市场/市值/营收排名第 1 的股票</div>
          </div>
          <div class="p-3 bg-blue-50 rounded">
            <div class="font-bold text-blue-700">板块龙头</div>
            <div class="text-gray-600 mt-1 text-xs">同行业内排名第 2～N 的股票</div>
          </div>
          <div class="p-3 bg-green-50 rounded">
            <div class="font-bold text-green-700">细分龙头</div>
            <div class="text-gray-600 mt-1 text-xs">细分赛道或子板块的龙头，可手动维护</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 筛选器 -->
    <div class="bg-white rounded-lg shadow mb-6 p-4">
      <div class="grid grid-cols-1 md:grid-cols-6 gap-4">
        <!-- 行业筛选 -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">行业</label>
          <select
            v-model="filters.industry"
            @change="loadData"
            class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">全部行业</option>
            <option v-for="ind in industries" :key="ind" :value="ind">{{ ind }}</option>
          </select>
        </div>

        <!-- 行业搜索 -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">行业搜索</label>
          <input
            v-model="industrySearchKeyword"
            @input="handleIndustrySearch"
            @keyup.enter="loadData"
            type="text"
            placeholder="如「电力」匹配电力设备、新型电力"
            class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        <!-- 龙头类型筛选 -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">龙头类型</label>
          <select
            v-model="filters.leader_type"
            @change="loadData"
            class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">全部类型</option>
            <option value="行业龙头">行业龙头</option>
            <option value="板块龙头">板块龙头</option>
            <option value="细分龙头">细分龙头</option>
          </select>
        </div>

        <!-- 板块角色筛选 -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">板块角色</label>
          <select
            v-model="filters.sector_leader_role"
            class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">全部</option>
            <option value="绝对龙头">绝对龙头</option>
            <option value="补涨">补涨</option>
            <option value="跟风">跟风</option>
          </select>
        </div>

        <!-- 状态筛选 -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">状态</label>
          <select
            v-model="filters.is_active"
            @change="loadData"
            class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option :value="true">有效</option>
            <option :value="false">已删除</option>
            <option :value="null">全部</option>
          </select>
        </div>

        <!-- 搜索框 -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">搜索</label>
          <input
            v-model="searchKeyword"
            @input="handleSearch"
            @keyup.enter="doSearchNow()"
            type="text"
            placeholder="股票代码/名称"
            class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      </div>
    </div>

    <!-- 数据表格 -->
    <div class="bg-white rounded-lg shadow overflow-hidden">
      <div class="overflow-x-auto">
        <table class="min-w-full divide-y divide-gray-200">
          <thead class="bg-gray-50">
            <tr>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">股票代码</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">股票名称</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">行业</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">板块</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">龙头类型</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">板块角色</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">市值(亿)</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">龙头理由</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">状态</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">操作</th>
            </tr>
          </thead>
          <tbody class="bg-white divide-y divide-gray-200">
            <tr v-if="loading">
              <td colspan="10" class="px-6 py-4 text-center text-gray-500">
                <div class="flex items-center justify-center">
                  <div class="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
                  <span class="ml-2">加载中...</span>
                </div>
              </td>
            </tr>
            <tr v-else-if="displayedLeaders.length === 0">
              <td colspan="10" class="px-6 py-4 text-center text-gray-500">
                暂无数据
              </td>
            </tr>
            <tr v-else v-for="leader in displayedLeaders" :key="leader.id" class="hover:bg-gray-50">
              <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">{{ leader.ts_code }}</td>
              <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">{{ leader.stock_name }}</td>
              <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{{ leader.industry }}</td>
              <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{{ leader.sector_name || '-' }}</td>
              <td class="px-6 py-4 whitespace-nowrap">
                <span :class="{
                  'px-2 py-1 text-xs rounded': true,
                  'bg-yellow-100 text-yellow-800': leader.leader_type === '行业龙头',
                  'bg-blue-100 text-blue-800': leader.leader_type === '板块龙头',
                  'bg-green-100 text-green-800': leader.leader_type === '细分龙头'
                }">
                  {{ leader.leader_type }}
                </span>
              </td>
              <td class="px-6 py-4 whitespace-nowrap">
                <span v-if="leader.sector_leader_role" :class="{
                  'px-2 py-1 text-xs rounded': true,
                  'bg-amber-100 text-amber-800': leader.sector_leader_role === '绝对龙头',
                  'bg-sky-100 text-sky-800': leader.sector_leader_role === '补涨',
                  'bg-gray-100 text-gray-700': leader.sector_leader_role === '跟风'
                }">{{ leader.sector_leader_role }}</span>
                <span v-else class="text-gray-400 text-xs">-</span>
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                {{ leader.market_cap ? leader.market_cap.toFixed(2) : '-' }}
              </td>
              <td class="px-6 py-4 text-sm text-gray-500 max-w-xs truncate" :title="leader.leader_reason">
                {{ leader.leader_reason || '-' }}
              </td>
              <td class="px-6 py-4 whitespace-nowrap">
                <span :class="{
                  'px-2 py-1 text-xs rounded': true,
                  'bg-green-100 text-green-800': leader.is_active,
                  'bg-red-100 text-red-800': !leader.is_active
                }">
                  {{ leader.is_active ? '有效' : '已删除' }}
                </span>
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm font-medium">
                <button
                  @click="editLeader(leader)"
                  class="text-blue-600 hover:text-blue-900 mr-3"
                >
                  编辑
                </button>
                <button
                  @click="deleteLeader(leader.id)"
                  class="text-red-600 hover:text-red-900"
                >
                  删除
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 分页 -->
      <div v-if="pagination.total_pages > 1" class="bg-white px-4 py-3 border-t border-gray-200 sm:px-6">
        <div class="flex items-center justify-between">
          <div class="text-sm text-gray-700">
            显示第 {{ (pagination.page - 1) * pagination.page_size + 1 }} - 
            {{ Math.min(pagination.page * pagination.page_size, pagination.total) }} 条，
            共 {{ pagination.total }} 条
          </div>
          <div class="flex space-x-2">
            <button
              @click="changePage(pagination.page - 1)"
              :disabled="pagination.page === 1"
              :class="{
                'px-3 py-2 border border-gray-300 rounded-md text-sm': true,
                'bg-white text-gray-700 hover:bg-gray-50': pagination.page > 1,
                'bg-gray-100 text-gray-400 cursor-not-allowed': pagination.page === 1
              }"
            >
              上一页
            </button>
            <span class="px-3 py-2 text-sm text-gray-700">
              第 {{ pagination.page }} / {{ pagination.total_pages }} 页
            </span>
            <button
              @click="changePage(pagination.page + 1)"
              :disabled="pagination.page === pagination.total_pages"
              :class="{
                'px-3 py-2 border border-gray-300 rounded-md text-sm': true,
                'bg-white text-gray-700 hover:bg-gray-50': pagination.page < pagination.total_pages,
                'bg-gray-100 text-gray-400 cursor-not-allowed': pagination.page === pagination.total_pages
              }"
            >
              下一页
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 新增/编辑模态框 -->
    <div v-if="showAddModal || showEditModal" class="fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full z-50" @click.self="closeModal">
      <div class="relative top-20 mx-auto p-5 border w-11/12 md:w-3/4 lg:w-1/2 shadow-lg rounded-md bg-white">
        <div class="mt-3">
          <h3 class="text-lg font-medium text-gray-900 mb-4">
            {{ showAddModal ? '新增行业龙头' : '编辑行业龙头' }}
          </h3>
          
          <form @submit.prevent="saveLeader" class="space-y-4">
            <div class="grid grid-cols-2 gap-4">
              <!-- 股票代码 -->
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">股票代码 <span class="text-red-500">*</span></label>
                <input
                  v-model="formData.ts_code"
                  type="text"
                  :disabled="showEditModal"
                  placeholder="如：000001.SZ"
                  required
                  class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <!-- 股票名称 -->
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">股票名称 <span class="text-red-500">*</span></label>
                <input
                  v-model="formData.stock_name"
                  type="text"
                  required
                  class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <!-- 行业 -->
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">行业 <span class="text-red-500">*</span></label>
                <input
                  v-model="formData.industry"
                  type="text"
                  required
                  list="industries-list"
                  class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <datalist id="industries-list">
                  <option v-for="ind in industries" :key="ind" :value="ind"></option>
                </datalist>
              </div>

              <!-- 板块代码 -->
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">板块代码</label>
                <input
                  v-model="formData.sector_code"
                  type="text"
                  placeholder="如：BK0493"
                  class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <!-- 板块名称 -->
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">板块名称</label>
                <input
                  v-model="formData.sector_name"
                  type="text"
                  class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <!-- 龙头类型 -->
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">龙头类型 <span class="text-red-500">*</span></label>
                <select
                  v-model="formData.leader_type"
                  required
                  class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="行业龙头">行业龙头</option>
                  <option value="板块龙头">板块龙头</option>
                  <option value="细分龙头">细分龙头</option>
                </select>
              </div>

              <!-- 市值 -->
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">市值(亿元)</label>
                <input
                  v-model.number="formData.market_cap"
                  type="number"
                  step="0.01"
                  class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <!-- ROE -->
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">ROE(%)</label>
                <input
                  v-model.number="formData.roe"
                  type="number"
                  step="0.01"
                  class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <!-- 营收增长率 -->
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">营收增长率(%)</label>
                <input
                  v-model.number="formData.revenue_growth"
                  type="number"
                  step="0.01"
                  class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>

            <!-- 龙头理由 -->
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">龙头理由</label>
              <textarea
                v-model="formData.leader_reason"
                rows="3"
                placeholder="说明为什么是龙头（50-200字）"
                class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              ></textarea>
            </div>

            <!-- 主营业务 -->
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">主营业务</label>
              <textarea
                v-model="formData.main_business"
                rows="2"
                placeholder="主营业务描述"
                class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              ></textarea>
            </div>

            <!-- 按钮 -->
            <div class="flex justify-end space-x-3 pt-4">
              <button
                type="button"
                @click="closeModal"
                class="px-4 py-2 bg-gray-200 text-gray-700 rounded hover:bg-gray-300"
              >
                取消
              </button>
              <button
                type="submit"
                :disabled="saving"
                class="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-400"
              >
                {{ saving ? '保存中...' : '保存' }}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

// 数据
const leaders = ref([])
const industries = ref([])
const loading = ref(false)
const saving = ref(false)
const updating = ref(false)
const searchKeyword = ref('')
const industrySearchKeyword = ref('')
let searchDebounceTimer = null  // 搜索防抖定时器
let industrySearchDebounceTimer = null  // 行业搜索防抖
const updateMethod = ref('comprehensive') // 更新方法：comprehensive/value/market/market_cap/revenue

// 筛选器
const filters = ref({
  industry: '',
  leader_type: '',
  sector_leader_role: '',  // 板块角色：绝对龙头/补涨/跟风
  is_active: true
})

// 分页
const pagination = ref({
  page: 1,
  page_size: 50,
  total: 0,
  total_pages: 1
})

// 龙头判断原则面板（与股票启动原则同款展示）
const showLeaderRules = ref(false)

// 模态框
const showAddModal = ref(false)
const showEditModal = ref(false)
const editingLeaderId = ref(null)

// 表单数据
const formData = ref({
  ts_code: '',
  stock_name: '',
  industry: '',
  sector_code: '',
  sector_name: '',
  leader_type: '行业龙头',
  leader_reason: '',
  main_business: '',
  market_cap: null,
  roe: null,
  revenue_growth: null
})

// 计算属性：过滤后的数据（关键词、行业搜索已由后端处理，此处仅做板块角色筛选）
const displayedLeaders = computed(() => {
  let filtered = leaders.value

  // 板块角色过滤（前端过滤，因该字段由接口附带）
  if (filters.value.sector_leader_role) {
    filtered = filtered.filter(leader => leader.sector_leader_role === filters.value.sector_leader_role)
  }

  return filtered
})

// 进入龙头判断原则（与启动原则同款：展开并滚动到规则区域）
function enterLeaderRules() {
  showLeaderRules.value = true
  setTimeout(() => {
    const el = document.getElementById('leader-rules')
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, 100)
}

// 加载行业列表
async function loadIndustries() {
  try {
    const response = await axios.get(`${API_BASE_URL}/api/industry-leaders/industries`)
    if (response.data.success) {
      industries.value = response.data.data
    }
  } catch (error) {
    console.error('加载行业列表失败:', error)
  }
}

// 加载数据
async function loadData() {
  loading.value = true
  try {
    const params = {
      page: pagination.value.page,
      page_size: pagination.value.page_size
    }

    if (filters.value.industry) {
      params.industry = filters.value.industry
    }
    if (filters.value.leader_type) {
      params.leader_type = filters.value.leader_type
    }
    if (filters.value.is_active !== null) {
      params.is_active = filters.value.is_active
    }
    // 行业搜索（服务端 ILIKE，如「电力」可匹配电力设备、新型电力等）
    if (industrySearchKeyword.value && industrySearchKeyword.value.trim()) {
      params.industry_keyword = industrySearchKeyword.value.trim()
      params.page = 1
      pagination.value.page = 1
    }
    // 按股票代码/名称模糊搜索（服务端查询，支持全库检索）
    if (searchKeyword.value && searchKeyword.value.trim()) {
      params.keyword = searchKeyword.value.trim()
      params.page = 1
      pagination.value.page = 1  // 搜索时重置到第 1 页
    }

    const response = await axios.get(`${API_BASE_URL}/api/industry-leaders/`, { params })
    
    if (response.data.success) {
      leaders.value = response.data.data
      pagination.value = response.data.pagination
    } else {
      alert('加载数据失败: ' + (response.data.message || '未知错误'))
    }
  } catch (error) {
    console.error('加载数据失败:', error)
    alert('加载数据失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    loading.value = false
  }
}

// 搜索处理：带防抖，触发服务端按股票代码/名称查询
function handleSearch() {

  if (searchDebounceTimer) clearTimeout(searchDebounceTimer)
  searchDebounceTimer = setTimeout(() => {
    pagination.value.page = 1
    loadData()
  }, 300)
}
// 行业搜索：带防抖
function handleIndustrySearch() {
  if (industrySearchDebounceTimer) clearTimeout(industrySearchDebounceTimer)
  industrySearchDebounceTimer = setTimeout(() => {
    pagination.value.page = 1
    loadData()
  }, 300)
}

// 立即搜索（如按 Enter）
function doSearchNow() {
  if (searchDebounceTimer) {
    clearTimeout(searchDebounceTimer)
    searchDebounceTimer = null
  }
  pagination.value.page = 1
  loadData()
}

// 分页
function changePage(page) {
  if (page >= 1 && page <= pagination.value.total_pages) {
    pagination.value.page = page
    loadData()
  }
}

// 编辑
function editLeader(leader) {
  editingLeaderId.value = leader.id
  formData.value = {
    ts_code: leader.ts_code,
    stock_name: leader.stock_name,
    industry: leader.industry,
    sector_code: leader.sector_code || '',
    sector_name: leader.sector_name || '',
    leader_type: leader.leader_type,
    leader_reason: leader.leader_reason || '',
    main_business: leader.main_business || '',
    market_cap: leader.market_cap,
    roe: leader.roe,
    revenue_growth: leader.revenue_growth
  }
  showEditModal.value = true
}

// 删除
async function deleteLeader(id) {
  if (!confirm('确定要删除这条记录吗？')) {
    return
  }

  try {
    const response = await axios.delete(`${API_BASE_URL}/api/industry-leaders/${id}`)
    if (response.data.success) {
      alert('删除成功')
      loadData()
    } else {
      alert('删除失败: ' + (response.data.message || '未知错误'))
    }
  } catch (error) {
    console.error('删除失败:', error)
    alert('删除失败: ' + (error.response?.data?.detail || error.message))
  }
}

// 保存
async function saveLeader() {
  saving.value = true
  try {
    if (showAddModal.value) {
      // 新增
      const response = await axios.post(`${API_BASE_URL}/api/industry-leaders/`, formData.value)
      if (response.data.success) {
        alert('新增成功')
        closeModal()
        loadData()
      } else {
        alert('新增失败: ' + (response.data.message || '未知错误'))
      }
    } else {
      // 更新
      const response = await axios.put(`${API_BASE_URL}/api/industry-leaders/${editingLeaderId.value}`, formData.value)
      if (response.data.success) {
        alert('更新成功')
        closeModal()
        loadData()
      } else {
        alert('更新失败: ' + (response.data.message || '未知错误'))
      }
    }
  } catch (error) {
    console.error('保存失败:', error)
    alert('保存失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    saving.value = false
  }
}

// 关闭模态框
function closeModal() {
  showAddModal.value = false
  showEditModal.value = false
  editingLeaderId.value = null
  formData.value = {
    ts_code: '',
    stock_name: '',
    industry: '',
    sector_code: '',
    sector_name: '',
    leader_type: '行业龙头',
    leader_reason: '',
    main_business: '',
    market_cap: null,
    roe: null,
    revenue_growth: null
  }
}

// 更新板块龙头（从API获取）
async function updateFromAPI() {
  const methodNames = {
    'comprehensive': '综合龙头（价值+市场）',
    'value': '价值龙头（财务指标）',
    'market': '市场龙头（市场热度）',
    'market_cap': '市值法',
    'revenue': '营收法'
  }
  
  const methodName = methodNames[updateMethod.value] || updateMethod.value
  const selectedIndustry = filters.value.industry
  
  let confirmMessage = `确定要从Tushare API更新板块龙头数据吗？\n\n`
  confirmMessage += `识别方法：${methodName}\n`
  if (selectedIndustry) {
    confirmMessage += `更新行业：${selectedIndustry}\n`
  } else {
    confirmMessage += `更新范围：所有行业\n`
  }
  confirmMessage += `\n这将：\n1. 获取行业龙头股票\n2. 更新现有记录或创建新记录\n3. 可能需要几分钟时间`
  
  if (!confirm(confirmMessage)) {
    return
  }

  updating.value = true
  try {
    const requestData = {
      method: updateMethod.value,
      top_n: 3
    }
    
    // 如果选择了特定行业，只更新该行业
    if (selectedIndustry) {
      requestData.industry = selectedIndustry
    }
    
    // 如果是综合方法，可以设置权重（可选）
    if (updateMethod.value === 'comprehensive') {
      requestData.value_weight = 0.4
      requestData.market_weight = 0.6
    }
    
    const response = await axios.post(`${API_BASE_URL}/api/industry-leaders/update-from-api`, requestData)
    
    if (response.data.success) {
      const industryText = selectedIndustry ? `行业 "${selectedIndustry}"` : `${response.data.total_industries} 个行业`
      alert(`更新成功！\n\n处理了 ${industryText}\n成功导入 ${response.data.imported_count} 只龙头股票\n\n识别方法：${methodName}`)
      loadIndustries() // 重新加载行业列表
      loadData() // 重新加载数据
    } else {
      alert('更新失败: ' + (response.data.message || '未知错误'))
    }
  } catch (error) {
    console.error('更新失败:', error)
    alert('更新失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    updating.value = false
  }
}

// 初始化
onMounted(() => {
  loadIndustries()
  loadData()
})
</script>
