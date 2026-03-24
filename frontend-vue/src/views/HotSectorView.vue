<template>
  <div class="container mx-auto px-4 py-6">
    <!-- 页面标题 -->
    <div class="mb-6 flex items-start justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-800">热门板块管理</h1>
        <p class="text-sm text-gray-500 mt-1">管理自定义热门板块及板块内股票</p>
      </div>
    </div>

    <!-- 主内容区：左右分栏布局 -->
    <div class="flex gap-6">
      <!-- 左侧面板：板块列表 -->
      <div class="w-80 flex-shrink-0 bg-white rounded-lg shadow">
        <div class="p-4 border-b border-gray-200">
          <div class="flex items-center justify-between mb-3">
            <h2 class="text-lg font-semibold text-gray-800">板块列表</h2>
            <button
              @click="showCreateDialog = true"
              class="px-3 py-1.5 bg-green-600 text-white rounded hover:bg-green-700 text-sm flex items-center gap-1"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
              </svg>
              新建
            </button>
          </div>
          <!-- 搜索框 -->
          <input
            v-model="searchKeyword"
            type="text"
            placeholder="搜索板块名称..."
            class="w-full px-3 py-2 border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            @input="filterSectors"
          />
        </div>

        <!-- 板块列表 -->
        <div class="overflow-y-auto" style="max-height: calc(100vh - 280px)">
          <div
            v-for="sector in filteredSectors"
            :key="sector.id"
            @click="selectSector(sector)"
            :class="[
              'p-4 border-b border-gray-100 cursor-pointer hover:bg-gray-50 transition-colors',
              selectedSector?.id === sector.id ? 'bg-blue-50 border-l-4 border-l-blue-500' : ''
            ]"
          >
            <div class="flex items-start justify-between">
              <div class="flex-1">
                <div class="flex items-center gap-2 mb-1">
                  <h3 class="font-semibold text-gray-900">{{ sector.name }}</h3>
                  <span
                    :class="[
                      'px-2 py-0.5 text-xs rounded',
                      sector.status === 'active' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-700'
                    ]"
                  >
                    {{ sector.status === 'active' ? '启用' : '禁用' }}
                  </span>
                </div>
                <p v-if="sector.description" class="text-xs text-gray-500 mb-2 line-clamp-2">
                  {{ sector.description }}
                </p>
                <div class="flex items-center gap-3 text-xs text-gray-500">
                  <span>股票: {{ sector.stock_count || 0 }} 只</span>
                  <span v-if="sector.sort_order !== undefined">排序: {{ sector.sort_order }}</span>
                </div>
              </div>
              <div class="flex items-center gap-1 ml-2">
                <button
                  @click.stop="editSector(sector)"
                  class="p-1 text-blue-600 hover:text-blue-800"
                  title="编辑"
                >
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                  </svg>
                </button>
                <button
                  @click.stop="deleteSector(sector)"
                  class="p-1 text-red-600 hover:text-red-800"
                  title="删除"
                >
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </button>
              </div>
            </div>
          </div>

          <!-- 空状态 -->
          <div v-if="filteredSectors.length === 0" class="p-8 text-center text-gray-500">
            <p>暂无板块</p>
            <p class="text-sm mt-2">点击"新建"按钮创建板块</p>
          </div>
        </div>
      </div>

      <!-- 右侧面板：板块详情 -->
      <div class="flex-1 bg-white rounded-lg shadow">
        <div v-if="selectedSector" class="p-6">
          <!-- 板块信息编辑区 -->
          <div class="mb-6">
            <h2 class="text-lg font-semibold text-gray-800 mb-4">板块信息</h2>
            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">板块名称 *</label>
                <input
                  v-model="sectorForm.name"
                  type="text"
                  class="w-full px-3 py-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="请输入板块名称"
                />
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">排序序号</label>
                <input
                  v-model.number="sectorForm.sort_order"
                  type="number"
                  class="w-full px-3 py-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="0"
                />
              </div>
              <div class="col-span-2">
                <label class="block text-sm font-medium text-gray-700 mb-1">板块描述</label>
                <textarea
                  v-model="sectorForm.description"
                  rows="2"
                  class="w-full px-3 py-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="请输入板块描述"
                ></textarea>
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">状态</label>
                <select
                  v-model="sectorForm.status"
                  class="w-full px-3 py-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="active">启用</option>
                  <option value="inactive">禁用</option>
                </select>
              </div>
              <div class="col-span-2">
                <label class="block text-sm font-medium text-gray-700 mb-1">备注</label>
                <textarea
                  v-model="sectorForm.notes"
                  rows="2"
                  class="w-full px-3 py-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="请输入备注信息"
                ></textarea>
              </div>
            </div>
            <div class="mt-4 flex gap-2">
              <button
                @click="saveSector"
                :disabled="saving"
                class="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-400 text-sm"
              >
                {{ saving ? '保存中...' : '保存' }}
              </button>
              <button
                @click="cancelEdit"
                class="px-4 py-2 border border-gray-300 text-gray-700 rounded hover:bg-gray-50 text-sm"
              >
                取消
              </button>
            </div>
          </div>

          <!-- 股票列表区 -->
          <div>
            <div class="flex items-center justify-between mb-4">
              <h2 class="text-lg font-semibold text-gray-800">股票列表 ({{ stocks.length }})</h2>
              <button
                @click="showAddStockDialog = true"
                class="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 text-sm flex items-center gap-2"
              >
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
                </svg>
                添加股票
              </button>
            </div>

            <!-- 股票表格 -->
            <div class="overflow-x-auto">
              <table class="min-w-full divide-y divide-gray-200">
                <thead class="bg-gray-50">
                  <tr>
                    <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">股票代码</th>
                    <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">股票名称</th>
                    <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">添加时间</th>
                    <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">备注</th>
                    <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">操作</th>
                  </tr>
                </thead>
                <tbody class="bg-white divide-y divide-gray-200">
                  <tr v-for="stock in stocks" :key="stock.id" class="hover:bg-gray-50">
                    <td class="px-4 py-3 text-sm font-medium text-blue-600">{{ stock.ts_code }}</td>
                    <td class="px-4 py-3 text-sm text-gray-900">{{ stock.stock_name || '-' }}</td>
                    <td class="px-4 py-3 text-sm text-gray-500">{{ formatDate(stock.added_at) }}</td>
                    <td class="px-4 py-3 text-sm text-gray-500">{{ stock.notes || '-' }}</td>
                    <td class="px-4 py-3 text-sm text-center">
                      <button
                        @click="removeStock(stock)"
                        class="text-red-600 hover:text-red-800"
                        title="删除"
                      >
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                      </button>
                    </td>
                  </tr>
                </tbody>
              </table>

              <!-- 空状态 -->
              <div v-if="stocks.length === 0" class="p-8 text-center text-gray-500">
                <p>该板块暂无股票</p>
                <p class="text-sm mt-2">点击"添加股票"按钮添加股票</p>
              </div>
            </div>
          </div>
        </div>

        <!-- 未选择板块时的提示 -->
        <div v-else class="p-12 text-center text-gray-500">
          <svg class="w-16 h-16 mx-auto mb-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          <p class="text-lg">请从左侧选择一个板块</p>
          <p class="text-sm mt-2">或点击"新建"按钮创建新板块</p>
        </div>
      </div>
    </div>

    <!-- 创建板块对话框 -->
    <div
      v-if="showCreateDialog"
      class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
      @click.self="showCreateDialog = false"
    >
      <div class="bg-white rounded-lg p-6 w-full max-w-md">
        <h3 class="text-lg font-semibold text-gray-900 mb-4">新建板块</h3>
        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">板块名称 *</label>
            <input
              v-model="newSectorForm.name"
              type="text"
              class="w-full px-3 py-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="请输入板块名称"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">板块描述</label>
            <textarea
              v-model="newSectorForm.description"
              rows="3"
              class="w-full px-3 py-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="请输入板块描述"
            ></textarea>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">排序序号</label>
            <input
              v-model.number="newSectorForm.sort_order"
              type="number"
              class="w-full px-3 py-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="0"
            />
          </div>
        </div>
        <div class="flex justify-end gap-2 mt-6">
          <button
            @click="showCreateDialog = false"
            class="px-4 py-2 border border-gray-300 text-gray-700 rounded hover:bg-gray-50 text-sm"
          >
            取消
          </button>
          <button
            @click="createSector"
            :disabled="saving"
            class="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-400 text-sm"
          >
            {{ saving ? '创建中...' : '创建' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 添加股票对话框 -->
    <div
      v-if="showAddStockDialog"
      class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
      @click.self="showAddStockDialog = false"
    >
      <div class="bg-white rounded-lg p-6 w-full max-w-md">
        <h3 class="text-lg font-semibold text-gray-900 mb-4">添加股票</h3>
        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">股票代码或名称 *</label>
            <input
              v-model="stockSearchKeyword"
              type="text"
              class="w-full px-3 py-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="输入股票代码（如：600519）或名称（如：贵州茅台）"
              @blur="onStockSearchBlur"
            />
            <p v-if="searchedStock" class="mt-2 text-sm text-green-600">
              ✓ 找到: {{ searchedStock.stock_name }} ({{ searchedStock.ts_code }})
            </p>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">备注</label>
            <textarea
              v-model="addStockForm.notes"
              rows="2"
              class="w-full px-3 py-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="备注信息"
            ></textarea>
          </div>
        </div>
        <div class="flex justify-end gap-2 mt-6">
          <button
            @click="showAddStockDialog = false"
            class="px-4 py-2 border border-gray-300 text-gray-700 rounded hover:bg-gray-50 text-sm"
          >
            取消
          </button>
          <button
            @click="addStock"
            :disabled="!searchedStock || saving"
            class="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-400 text-sm"
          >
            {{ saving ? '添加中...' : '添加' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

const loading = ref(false)
const saving = ref(false)
const sectors = ref([])
const selectedSector = ref(null)
const stocks = ref([])
const searchKeyword = ref('')
const showCreateDialog = ref(false)
const showAddStockDialog = ref(false)
const isSearchingStock = ref(false)
const searchedStock = ref(null)

// 板块表单
const sectorForm = ref({
  id: null,
  name: '',
  description: '',
  sort_order: 0,
  status: 'active',
  notes: ''
})

// 新建板块表单
const newSectorForm = ref({
  name: '',
  description: '',
  sort_order: 0
})

// 添加股票表单
const addStockForm = ref({
  notes: ''
})

const stockSearchKeyword = ref('')

// 过滤后的板块列表
const filteredSectors = computed(() => {
  if (!searchKeyword.value) {
    return sectors.value
  }
  const keyword = searchKeyword.value.toLowerCase()
  return sectors.value.filter(s => 
    s.name.toLowerCase().includes(keyword)
  )
})

// 格式化日期
function formatDate(dateStr) {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

// 加载板块列表
async function loadSectors() {
  loading.value = true
  try {
    const response = await axios.get(`${API_BASE_URL}/api/hot-sector`)
    if (response.data.success) {
      sectors.value = response.data.data || []
    } else {
      alert('加载板块列表失败: ' + (response.data.message || '未知错误'))
    }
  } catch (error) {
    console.error('加载板块列表失败:', error)
    alert('加载板块列表失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    loading.value = false
  }
}

// 选择板块
async function selectSector(sector) {
  selectedSector.value = sector
  // 加载板块详情和股票列表
  sectorForm.value = {
    id: sector.id,
    name: sector.name,
    description: sector.description || '',
    sort_order: sector.sort_order || 0,
    status: sector.status || 'active',
    notes: sector.notes || ''
  }
  await loadStocks(sector.id)
}

// 加载股票列表
async function loadStocks(sectorId) {
  if (!sectorId) return
  
  loading.value = true
  try {
    const response = await axios.get(`${API_BASE_URL}/api/hot-sector/${sectorId}/stocks`)
    if (response.data.success) {
      stocks.value = response.data.data || []
    } else {
      alert('加载股票列表失败: ' + (response.data.message || '未知错误'))
    }
  } catch (error) {
    console.error('加载股票列表失败:', error)
    alert('加载股票列表失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    loading.value = false
  }
}

// 创建板块
async function createSector() {
  if (!newSectorForm.value.name) {
    alert('请输入板块名称')
    return
  }

  saving.value = true
  try {
    const response = await axios.post(`${API_BASE_URL}/api/hot-sector`, newSectorForm.value)
    if (response.data.success) {
      alert('创建成功')
      showCreateDialog.value = false
      newSectorForm.value = { name: '', description: '', sort_order: 0 }
      await loadSectors()
      // 自动选择新创建的板块
      if (response.data.data) {
        const newSector = sectors.value.find(s => s.id === response.data.data.id)
        if (newSector) {
          await selectSector(newSector)
        }
      }
    } else {
      alert('创建失败: ' + (response.data.message || '未知错误'))
    }
  } catch (error) {
    console.error('创建板块失败:', error)
    alert('创建板块失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    saving.value = false
  }
}

// 编辑板块
function editSector(sector) {
  selectSector(sector)
}

// 保存板块
async function saveSector() {
  if (!sectorForm.value.name) {
    alert('请输入板块名称')
    return
  }

  saving.value = true
  try {
    const { id, ...updateData } = sectorForm.value
    const response = await axios.put(`${API_BASE_URL}/api/hot-sector/${id}`, updateData)
    if (response.data.success) {
      alert('保存成功')
      await loadSectors()
      // 更新选中板块的信息
      if (selectedSector.value) {
        const updated = sectors.value.find(s => s.id === id)
        if (updated) {
          selectedSector.value = updated
          sectorForm.value = {
            id: updated.id,
            name: updated.name,
            description: updated.description || '',
            sort_order: updated.sort_order || 0,
            status: updated.status || 'active',
            notes: updated.notes || ''
          }
        }
      }
    } else {
      alert('保存失败: ' + (response.data.message || '未知错误'))
    }
  } catch (error) {
    console.error('保存板块失败:', error)
    alert('保存板块失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    saving.value = false
  }
}

// 取消编辑
function cancelEdit() {
  if (selectedSector.value) {
    selectSector(selectedSector.value)
  }
}

// 删除板块
async function deleteSector(sector) {
  if (!confirm(`确定要删除板块 "${sector.name}" 吗？\n\n此操作将同时删除板块内的所有股票，且不可恢复！`)) {
    return
  }

  try {
    const response = await axios.delete(`${API_BASE_URL}/api/hot-sector/${sector.id}`)
    if (response.data.success) {
      alert('删除成功')
      if (selectedSector.value?.id === sector.id) {
        selectedSector.value = null
        stocks.value = []
      }
      await loadSectors()
    } else {
      alert('删除失败: ' + (response.data.message || '未知错误'))
    }
  } catch (error) {
    console.error('删除板块失败:', error)
    alert('删除板块失败: ' + (error.response?.data?.detail || error.message))
  }
}

// 搜索股票
async function onStockSearchBlur() {
  if (!stockSearchKeyword.value || isSearchingStock.value) {
    return
  }

  const keyword = stockSearchKeyword.value.trim()
  if (!keyword) {
    searchedStock.value = null
    return
  }

  isSearchingStock.value = true
  try {
    const response = await axios.get(`${API_BASE_URL}/api/hot-sector/search-stock`, {
      params: { keyword }
    })
    if (response.data.success) {
      searchedStock.value = {
        ts_code: response.data.ts_code,
        stock_name: response.data.stock_name
      }
    } else {
      searchedStock.value = null
    }
  } catch (error) {
    console.error('搜索股票失败:', error)
    searchedStock.value = null
  } finally {
    isSearchingStock.value = false
  }
}

// 添加股票
async function addStock() {
  if (!searchedStock.value || !selectedSector.value) {
    alert('请先搜索并选择股票')
    return
  }

  saving.value = true
  try {
    const response = await axios.post(
      `${API_BASE_URL}/api/hot-sector/${selectedSector.value.id}/stocks`,
      {
        ts_code: searchedStock.value.ts_code,
        notes: addStockForm.value.notes
      }
    )
    if (response.data.success) {
      alert('添加成功')
      showAddStockDialog.value = false
      stockSearchKeyword.value = ''
      searchedStock.value = null
      addStockForm.value.notes = ''
      await loadStocks(selectedSector.value.id)
      await loadSectors() // 更新股票数量
    } else {
      alert('添加失败: ' + (response.data.message || '未知错误'))
    }
  } catch (error) {
    console.error('添加股票失败:', error)
    alert('添加股票失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    saving.value = false
  }
}

// 删除股票
async function removeStock(stock) {
  if (!confirm(`确定要从板块中删除股票 "${stock.stock_name || stock.ts_code}" 吗？`)) {
    return
  }

  try {
    const response = await axios.delete(
      `${API_BASE_URL}/api/hot-sector/${selectedSector.value.id}/stocks/${stock.ts_code}`
    )
    if (response.data.success) {
      alert('删除成功')
      await loadStocks(selectedSector.value.id)
      await loadSectors() // 更新股票数量
    } else {
      alert('删除失败: ' + (response.data.message || '未知错误'))
    }
  } catch (error) {
    console.error('删除股票失败:', error)
    alert('删除股票失败: ' + (error.response?.data?.detail || error.message))
  }
}

// 过滤板块
function filterSectors() {
  // 通过computed自动过滤
}

// 初始化
onMounted(() => {
  loadSectors()
})
</script>
