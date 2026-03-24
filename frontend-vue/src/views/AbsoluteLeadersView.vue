<template>
  <div class="container mx-auto px-4 py-6">
    <!-- 页面标题 -->
    <div class="mb-6 flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-800">👑 绝对龙头一览</h1>
        <p class="text-sm text-gray-500 mt-1">
          展示当前滚动窗口内，各板块识别出的<span class="font-semibold text-amber-600">绝对龙头</span>股票（来自板块龙头快照 + 行业龙头表）。
        </p>
      </div>
    </div>

    <!-- 筛选器 -->
    <div class="bg-white rounded-lg shadow mb-6 p-4">
      <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
        <!-- 行业筛选 -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">行业</label>
          <select
            v-model="filters.industry"
            @change="reload"
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
            @keyup.enter="reload"
            type="text"
            placeholder="如「电力」匹配电力设备、新型电力等"
            class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        <!-- 搜索框 -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">搜索</label>
          <input
            v-model="searchKeyword"
            @input="handleSearch"
            @keyup.enter="doSearchNow"
            type="text"
            placeholder="股票代码/名称"
            class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        <!-- 状态筛选 -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">状态</label>
          <select
            v-model="filters.is_active"
            @change="reload"
            class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option :value="true">仅有效</option>
            <option :value="false">仅已删除</option>
            <option :value="null">全部</option>
          </select>
        </div>
      </div>

      <div class="mt-2 text-xs text-gray-500">
        固定筛选：仅展示板块角色为
        <span class="px-2 py-0.5 rounded bg-amber-100 text-amber-800 font-medium">绝对龙头</span>
        的股票。
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
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">标记时间</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">龙头理由</th>
            </tr>
          </thead>
          <tbody class="bg-white divide-y divide-gray-200">
            <tr v-if="loading">
              <td colspan="8" class="px-6 py-4 text-center text-gray-500">
                <div class="flex items-center justify-center">
                  <div class="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
                  <span class="ml-2">加载中...</span>
                </div>
              </td>
            </tr>
            <tr v-else-if="displayedLeaders.length === 0">
              <td colspan="8" class="px-6 py-4 text-center text-gray-500">
                暂无绝对龙头数据
              </td>
            </tr>
            <tr
              v-else
              v-for="leader in displayedLeaders"
              :key="leader.id"
              class="hover:bg-gray-50"
            >
              <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">{{ leader.ts_code }}</td>
              <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">{{ leader.stock_name }}</td>
              <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{{ leader.industry }}</td>
              <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{{ leader.sector_name || '-' }}</td>
              <td class="px-6 py-4 whitespace-nowrap">
                <span
                  :class="{
                    'px-2 py-1 text-xs rounded': true,
                    'bg-yellow-100 text-yellow-800': leader.leader_type === '行业龙头',
                    'bg-blue-100 text-blue-800': leader.leader_type === '板块龙头',
                    'bg-green-100 text-green-800': leader.leader_type === '细分龙头'
                  }"
                >
                  {{ leader.leader_type }}
                </span>
              </td>
              <td class="px-6 py-4 whitespace-nowrap">
                <span class="px-2 py-1 text-xs rounded bg-amber-100 text-amber-800">绝对龙头</span>
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                {{ leader.market_cap ? leader.market_cap.toFixed(2) : '-' }}
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                {{ leader.marked_at ? new Date(leader.marked_at).toLocaleString('zh-CN') : '-' }}
              </td>
              <td class="px-6 py-4 text-sm text-gray-500 max-w-xs truncate" :title="leader.leader_reason">
                {{ leader.leader_reason || '-' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 分页 -->
      <div
        v-if="pagination.total_pages > 1"
        class="bg-white px-4 py-3 border-t border-gray-200 sm:px-6"
      >
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
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

const leaders = ref([])
const industries = ref([])
const loading = ref(false)
const searchKeyword = ref('')
const industrySearchKeyword = ref('')
let searchDebounceTimer = null
let industrySearchDebounceTimer = null

const filters = ref({
  industry: '',
  is_active: true,
})

const pagination = ref({
  page: 1,
  page_size: 50,
  total: 0,
  total_pages: 1,
})

const displayedLeaders = computed(() => {
  // 后端未直接按板块角色筛选，这里只展示 sector_leader_role === '绝对龙头' 的记录
  return leaders.value.filter((l) => l.sector_leader_role === '绝对龙头')
})

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

async function loadData() {
  loading.value = true
  try {
    const params = {
      page: pagination.value.page,
      page_size: pagination.value.page_size,
      is_active: filters.value.is_active,
    }

    if (filters.value.industry) {
      params.industry = filters.value.industry
    }
    if (industrySearchKeyword.value && industrySearchKeyword.value.trim()) {
      params.industry_keyword = industrySearchKeyword.value.trim()
      params.page = 1
      pagination.value.page = 1
    }
    if (searchKeyword.value && searchKeyword.value.trim()) {
      params.keyword = searchKeyword.value.trim()
      params.page = 1
      pagination.value.page = 1
    }

    const response = await axios.get(`${API_BASE_URL}/api/industry-leaders/absolute-leaders`, { params })
    if (response.data.success) {
      leaders.value = response.data.data || []
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

function reload() {
  pagination.value.page = 1
  loadData()
}

function handleSearch() {
  if (searchDebounceTimer) clearTimeout(searchDebounceTimer)
  searchDebounceTimer = setTimeout(() => {
    pagination.value.page = 1
    loadData()
  }, 300)
}

function handleIndustrySearch() {
  if (industrySearchDebounceTimer) clearTimeout(industrySearchDebounceTimer)
  industrySearchDebounceTimer = setTimeout(() => {
    pagination.value.page = 1
    loadData()
  }, 300)
}

function doSearchNow() {
  if (searchDebounceTimer) {
    clearTimeout(searchDebounceTimer)
    searchDebounceTimer = null
  }
  pagination.value.page = 1
  loadData()
}

function changePage(page) {
  if (page >= 1 && page <= pagination.value.total_pages) {
    pagination.value.page = page
    loadData()
  }
}

onMounted(() => {
  loadIndustries()
  loadData()
})
</script>

