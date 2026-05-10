<template>
  <div class="p-8 space-y-8">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-semibold text-gray-900 mb-2">定时任务管理</h1>
        <p class="text-sm text-gray-500">配置和管理系统定时任务的执行时间</p>
      </div>
      <div class="flex gap-2">
        <Button
          size="sm"
          variant="primary"
          @click="handleCreateTask"
          class="bg-green-600 hover:bg-green-700 text-white"
        >
          新建任务
        </Button>
        <Button
          size="sm"
          variant="primary"
          @click="handleResetRunningStatus"
          :disabled="resetting"
          class="bg-orange-600 hover:bg-orange-700 text-white"
        >
          {{ resetting ? '重置中...' : '重置运行状态' }}
        </Button>
        <Button
          size="sm"
          variant="primary"
          @click="handleRefresh"
          :disabled="loading"
          class="bg-blue-600 hover:bg-blue-700 text-white"
        >
          {{ loading ? '加载中...' : '刷新' }}
        </Button>
      </div>
    </div>

    <!-- 任务列表 -->
    <div>
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-semibold text-gray-900">任务列表</h2>
        <div class="flex gap-2">
          <select
            v-model="filterEnabled"
            class="px-3 py-1.5 text-sm border border-gray-300 rounded-md"
          >
            <option :value="null">全部</option>
            <option :value="true">已启用</option>
            <option :value="false">已禁用</option>
          </select>
        </div>
      </div>

      <div class="bg-white rounded-lg border border-gray-200 overflow-hidden">
        <table class="min-w-full divide-y divide-gray-200">
          <thead class="bg-gray-50">
            <tr>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">任务名称</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">分类</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">执行时间</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">执行日期</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">状态</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">最后执行</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">操作</th>
            </tr>
          </thead>
          <tbody class="bg-white divide-y divide-gray-200">
            <tr v-for="task in filteredTasks" :key="task.id" class="hover:bg-gray-50">
              <td class="px-4 py-3 whitespace-nowrap">
                <div class="flex items-center gap-2">
                  <span class="text-sm font-medium text-gray-900">
                    {{ task.task_display_name }}
                  </span>
                </div>
                <div class="text-xs text-gray-500 mt-0.5">{{ task.task_description || '--' }}</div>
              </td>
              <td class="px-4 py-3 whitespace-nowrap">
                <span class="px-2 py-1 text-xs rounded font-medium" :class="categoryStyle(task.task_type).class">
                  {{ categoryStyle(task.task_type).label }}
                </span>
              </td>
              <td class="px-4 py-3 whitespace-nowrap">
                <div class="text-sm text-gray-900">{{ task.schedule_time || '--' }}</div>
                <div v-if="task.cron_expression" class="text-xs text-gray-500">{{ task.cron_expression }}</div>
              </td>
              <td class="px-4 py-3 whitespace-nowrap">
                <div class="text-sm text-gray-900">{{ formatScheduleDays(task.schedule_days) }}</div>
              </td>
              <td class="px-4 py-3 whitespace-nowrap">
                <div class="flex items-center gap-2">
                  <span
                    :class="[
                      'px-2 py-1 text-xs rounded font-medium',
                      task.is_enabled
                        ? 'bg-green-100 text-green-700'
                        : 'bg-gray-100 text-gray-700'
                    ]"
                  >
                    {{ task.is_enabled ? '已启用' : '已禁用' }}
                  </span>
                  <span
                    v-if="task.is_running"
                    class="px-2 py-1 text-xs rounded font-medium bg-blue-100 text-blue-700"
                  >
                    运行中
                  </span>
                </div>
              </td>
              <td class="px-4 py-3 whitespace-nowrap">
                <div class="text-sm text-gray-900">
                  {{ task.last_run_at ? formatDateTime(task.last_run_at) : '--' }}
                </div>
              </td>
              <td class="px-4 py-3 whitespace-nowrap text-sm font-medium">
                <div class="flex items-center gap-2">
                  <button
                    @click="handleEditTask(task)"
                    class="text-blue-600 hover:text-blue-900"
                  >
                    编辑
                  </button>
                  <button
                    @click="handleTriggerTask(task)"
                    :disabled="task.is_running"
                    class="text-green-600 hover:text-green-900 disabled:opacity-50"
                  >
                    {{ task.is_running ? '运行中' : '执行' }}
                  </button>
                  <button
                    @click="handleDeleteTask(task)"
                    class="text-red-600 hover:text-red-900"
                  >
                    删除
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 编辑任务模态框 -->
    <div
      v-if="showEditModal"
      class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
      @click.self="showEditModal = false"
    >
      <div class="bg-white rounded-lg p-6 w-full max-w-md">
        <h3 class="text-lg font-semibold text-gray-900 mb-4">
          {{ editingTask ? '编辑任务' : '创建任务' }}
        </h3>

        <div class="space-y-4">
          <div v-if="!editingTask">
            <label class="block text-sm font-medium text-gray-700 mb-1">任务类型</label>
            <select
              v-model="editForm.task_type"
              class="w-full px-3 py-2 border border-gray-300 rounded-md"
              @change="onTaskTypeChange"
            >
              <option value="">请选择任务类型</option>
              <optgroup v-for="cat in TASK_TYPE_CATEGORIES" :key="cat.key" :label="cat.label">
                <option v-for="opt in cat.options" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
              </optgroup>
            </select>
          </div>
          <div v-if="!editingTask">
            <label class="block text-sm font-medium text-gray-700 mb-1">任务名称（唯一标识）</label>
            <input
              v-model="editForm.task_name"
              type="text"
              class="w-full px-3 py-2 border border-gray-300 rounded-md"
              placeholder="如：sync_industry、industry_cycle_collect"
            />
            <p class="text-xs text-gray-500 mt-1">英文，用于系统标识，创建后不可修改</p>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">任务显示名称</label>
            <input
              v-model="editForm.task_display_name"
              type="text"
              class="w-full px-3 py-2 border border-gray-300 rounded-md"
              placeholder="请输入任务显示名称"
            />
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">任务描述</label>
            <textarea
              v-model="editForm.task_description"
              rows="3"
              class="w-full px-3 py-2 border border-gray-300 rounded-md"
              placeholder="请输入任务描述"
            />
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">执行时间</label>
            <input
              v-model="editForm.schedule_time"
              type="time"
              class="w-full px-3 py-2 border border-gray-300 rounded-md"
              placeholder="HH:MM"
            />
            <p class="text-xs text-gray-500 mt-1">格式：HH:MM（如：15:30）</p>
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">执行日期</label>
            <input
              v-model="editForm.schedule_days"
              type="text"
              class="w-full px-3 py-2 border border-gray-300 rounded-md"
              placeholder="1-5 或 1,3,5"
            />
            <p class="text-xs text-gray-500 mt-1">格式：1-5（周一到周五）或 1,3,5（周一三五）</p>
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Cron表达式（可选）</label>
            <input
              v-model="editForm.cron_expression"
              type="text"
              class="w-full px-3 py-2 border border-gray-300 rounded-md"
              placeholder="0 15 * * 1-5"
            />
            <p class="text-xs text-gray-500 mt-1">高级：使用Cron表达式（如：0 15 * * 1-5）</p>
          </div>

          <div class="flex items-center">
            <input
              v-model="editForm.is_enabled"
              type="checkbox"
              id="is_enabled"
              class="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
            />
            <label for="is_enabled" class="ml-2 block text-sm text-gray-700">启用任务</label>
          </div>
        </div>

        <div class="flex justify-end gap-2 mt-6">
          <button
            @click="showEditModal = false"
            class="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200"
          >
            取消
          </button>
          <button
            @click="handleSaveTask"
            :disabled="saving"
            class="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50"
          >
            {{ saving ? '保存中...' : '保存' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'
import Button from '../components/ui/Button.vue'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

const loading = ref(false)
const saving = ref(false)
const resetting = ref(false)
const tasks = ref([])
const filterEnabled = ref(null)
const showEditModal = ref(false)
const editingTask = ref(null)

const editForm = ref({
  task_name: '',
  task_display_name: '',
  task_description: '',
  task_type: '',
  schedule_time: '',
  schedule_days: '',
  cron_expression: '',
  is_enabled: true,
})

const TASK_TYPE_CATEGORIES = [
  {
    key: 'data',
    label: '数据更新',
    options: [
      { value: 'daily_update', label: '日线数据更新' },
      { value: 'fundamental_update', label: '财务数据更新' },
      { value: 'refresh_snapshot', label: '股票快照刷新' },
      { value: 'sync_stock', label: '更新股票列表' },
      { value: 'sync_industry', label: '申万行业同步' },
      { value: 'sync_trade_calendar', label: '同步交易日历' },
      { value: 'pe_pb_update', label: 'PE/PB 更新' },
      { value: 'moneyflow_update', label: '资金流向更新（行业/板块）' },
      { value: 'money_flow_update', label: '个股主力资金更新' },
    ],
  },
  {
    key: 'sector',
    label: '板块与行业',
    options: [
      { value: 'sector_daily_maintenance', label: '板块日终维护（热度+龙头+日线）' },
      { value: 'sector_heat_update', label: '板块热度更新（兼容）' },
      { value: 'sector_leaders_update', label: '板块龙头更新（兼容）' },
      { value: 'sector_daily_update', label: '板块日线更新（兼容）' },
      { value: 'industry_cycle_collect', label: '行业周期数据采集' },
      { value: 'industry_cycle_suggest', label: '行业周期建议生成' },
    ],
  },
  {
    key: 'recommendation',
    label: '推荐系统',
    options: [
      { value: 'recommendation_daily', label: '推荐系统日终维护（追踪+平仓）' },
      { value: 'recommendation_daily_track', label: '推荐效果追踪（兼容）' },
      { value: 'recommendation_auto_close', label: '推荐自动平仓（兼容）' },
    ],
  },
  {
    key: 'north',
    label: '北向资金',
    options: [
      { value: 'north_money_update', label: '北向资金更新（持股+净流入）' },
      { value: 'north_holding_update', label: '北向持股更新（兼容）' },
      { value: 'north_flow_update', label: '北向净流入更新（兼容）' },
    ],
  },
  {
    key: 'market',
    label: '市场情绪',
    options: [
      { value: 'limit_up_emotion_update', label: '涨停情绪更新' },
      { value: 'abnormal_analysis_scan', label: '异动分析扫描' },
    ],
  },
  {
    key: 'short_term',
    label: '短线监控',
    options: [
      { value: 'break_board_detect', label: '断板龙头识别' },
      { value: 'break_board_price_monitor', label: '断板价格监控' },
    ],
  },
  {
    key: 'strategy',
    label: '投资策略',
    options: [
      { value: 's1_universe_update', label: 'S1股票池更新' },
    ],
  },
  {
    key: 'ai_model',
    label: 'AI模型',
    options: [
      { value: 'lstm_mab_daily_feedback', label: 'LSTM-MAB每日反馈' },
      { value: 'lstm_mab_retrain_check', label: 'LSTM-MAB重训练检查' },
    ],
  },
  {
    key: 'crawler',
    label: '资讯爬虫',
    options: [
      { value: 'guba_popularity_crawl', label: '股吧人气榜爬虫' },
      { value: 'guba_popularity_crawl_morning', label: '股吧人气榜爬虫（早盘）' },
      { value: 'guba_popularity_crawl_noon', label: '股吧人气榜爬虫（午盘）' },
    ],
  },
  {
    key: 'long_term',
    label: '长线投资',
    options: [
      { value: 'long_term_selection_scan', label: '长线选股扫描' },
      { value: 'calc_valuation_percentile', label: '估值分位数计算' },
      { value: 'long_term_monitor_scan', label: '持仓监控扫描' },
    ],
  },
]

const ALL_TASK_OPTIONS = TASK_TYPE_CATEGORIES.flatMap(c => c.options)

const CATEGORY_MAP = {
  data: { label: '数据更新', class: 'bg-blue-100 text-blue-700' },
  sector: { label: '板块与行业', class: 'bg-cyan-100 text-cyan-700' },
  recommendation: { label: '推荐系统', class: 'bg-purple-100 text-purple-700' },
  north: { label: '北向资金', class: 'bg-indigo-100 text-indigo-700' },
  market: { label: '市场情绪', class: 'bg-rose-100 text-rose-700' },
  short_term: { label: '短线监控', class: 'bg-red-100 text-red-700' },
  strategy: { label: '投资策略', class: 'bg-emerald-100 text-emerald-700' },
  ai_model: { label: 'AI模型', class: 'bg-violet-100 text-violet-700' },
  crawler: { label: '资讯爬虫', class: 'bg-amber-100 text-amber-700' },
  long_term: { label: '长线投资', class: 'bg-teal-100 text-teal-700' },
  other: { label: '其他', class: 'bg-gray-100 text-gray-700' },
}

const getTaskCategory = (task) => {
  const type = task.task_type
  if (['daily_update', 'fundamental_update', 'refresh_snapshot', 'sync_stock', 'sync_industry', 'sync_trade_calendar', 'pe_pb_update', 'moneyflow_update', 'money_flow_update'].includes(type)) return 'data'
  if (['sector_daily_maintenance', 'sector_heat_update', 'sector_leaders_update', 'sector_daily_update', 'industry_cycle_collect', 'industry_cycle_suggest'].includes(type)) return 'sector'
  if (['recommendation_daily', 'recommendation_daily_track', 'recommendation_auto_close'].includes(type)) return 'recommendation'
  if (['north_money_update', 'north_holding_update', 'north_flow_update'].includes(type)) return 'north'
  if (['limit_up_emotion_update', 'abnormal_analysis_scan'].includes(type)) return 'market'
  if (['break_board_detect', 'break_board_price_monitor'].includes(type)) return 'short_term'
  if (['s1_universe_update'].includes(type)) return 'strategy'
  if (['lstm_mab_daily_feedback', 'lstm_mab_retrain_check'].includes(type)) return 'ai_model'
  if (['guba_popularity_crawl', 'guba_popularity_crawl_morning', 'guba_popularity_crawl_noon'].includes(type)) return 'crawler'
  if (['long_term_selection_scan', 'calc_valuation_percentile', 'long_term_monitor_scan'].includes(type)) return 'long_term'
  return 'other'
}

const categoryStyle = (type) => {
  const catKey = getTaskCategory({ task_type: type })
  return CATEGORY_MAP[catKey] || CATEGORY_MAP.other
}

const filteredTasks = computed(() => {
  let list = tasks.value
  if (filterEnabled.value !== null) {
    list = list.filter(task => task.is_enabled === filterEnabled.value)
  }
  // 按分类排序（保持列表清晰）
  const order = Object.keys(CATEGORY_MAP)
  return list.slice().sort((a, b) => {
    const ca = getTaskCategory(a)
    const cb = getTaskCategory(b)
    const ia = order.indexOf(ca)
    const ib = order.indexOf(cb)
    if (ia !== ib) return ia - ib
    return a.task_name.localeCompare(b.task_name)
  })
})

const formatScheduleDays = (days) => {
  if (!days) return '--'
  if (days === '1-5') return '周一到周五'
  if (days === '1') return '周一'
  if (days.includes(',')) {
    const dayNames = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
    return days.split(',').map(d => dayNames[parseInt(d) - 1]).join('、')
  }
  return days
}

const formatDateTime = (dateStr) => {
  if (!dateStr) return '--'
  return new Date(dateStr).toLocaleString('zh-CN')
}

const loadTasks = async () => {
  loading.value = true
  try {
    const params = {}
    if (filterEnabled.value !== null) {
      params.is_enabled = filterEnabled.value
    }
    const response = await axios.get(`${API_BASE_URL}/api/scheduled-task/list`, { params })
    if (response.data.success) {
      tasks.value = response.data.data || []
    } else {
      alert('加载任务列表失败: ' + (response.data.message || '未知错误'))
    }
  } catch (error) {
    console.error('加载任务列表失败:', error)
    alert('加载任务列表失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    loading.value = false
  }
}

const handleRefresh = () => {
  loadTasks()
}

const onTaskTypeChange = () => {
  const opt = ALL_TASK_OPTIONS.find(o => o.value === editForm.value.task_type)
  if (opt) {
    if (!editForm.value.task_display_name) {
      editForm.value.task_display_name = opt.label
    }
    if (!editForm.value.task_name) {
      editForm.value.task_name = opt.value
    }
  }
}

const handleCreateTask = () => {
  editingTask.value = null
  editForm.value = {
    task_name: '',
    task_display_name: '',
    task_description: '',
    task_type: '',
    schedule_time: '15:30',
    schedule_days: '1-5',
    cron_expression: '',
    is_enabled: true,
  }
  showEditModal.value = true
}

const handleEditTask = (task) => {
  editingTask.value = task
  editForm.value = {
    task_name: task.task_name || '',
    task_display_name: task.task_display_name || '',
    task_description: task.task_description || '',
    task_type: task.task_type || '',
    schedule_time: task.schedule_time || '',
    schedule_days: task.schedule_days || '',
    cron_expression: task.cron_expression || '',
    is_enabled: task.is_enabled !== undefined ? task.is_enabled : true,
  }
  showEditModal.value = true
}

const handleSaveTask = async () => {
  const isCreate = !editingTask.value
  if (isCreate) {
    if (!editForm.value.task_name?.trim()) {
      alert('请输入任务名称')
      return
    }
    if (!editForm.value.task_display_name?.trim()) {
      alert('请输入任务显示名称')
      return
    }
    if (!editForm.value.task_type?.trim()) {
      alert('请选择任务类型')
      return
    }
  }

  saving.value = true
  try {
    let response
    if (isCreate) {
      response = await axios.post(
        `${API_BASE_URL}/api/scheduled-task/create`,
        {
          task_name: editForm.value.task_name.trim(),
          task_display_name: editForm.value.task_display_name.trim(),
          task_description: editForm.value.task_description || null,
          task_type: editForm.value.task_type,
          schedule_time: editForm.value.schedule_time || null,
          schedule_days: editForm.value.schedule_days || null,
          cron_expression: editForm.value.cron_expression || null,
          is_enabled: editForm.value.is_enabled,
        }
      )
    } else {
      response = await axios.put(
        `${API_BASE_URL}/api/scheduled-task/${editingTask.value.task_name}`,
        {
          task_display_name: editForm.value.task_display_name,
          task_description: editForm.value.task_description,
          schedule_time: editForm.value.schedule_time,
          schedule_days: editForm.value.schedule_days,
          cron_expression: editForm.value.cron_expression,
          is_enabled: editForm.value.is_enabled,
        }
      )
    }
    if (response.data.success) {
      alert(isCreate ? '创建成功' : '保存成功')
      showEditModal.value = false
      editingTask.value = null
      loadTasks()
    } else {
      alert((isCreate ? '创建失败' : '保存失败') + ': ' + (response.data.message || response.data.detail || '未知错误'))
    }
  } catch (error) {
    console.error('保存任务失败:', error)
    const detail = error.response?.data?.detail
    const msg = typeof detail === 'string' ? detail : (Array.isArray(detail) ? detail.map(d => d.msg || d).join(', ') : error.message)
    alert((isCreate ? '创建任务失败' : '保存任务失败') + ': ' + msg)
  } finally {
    saving.value = false
  }
}

const handleTriggerTask = async (task) => {
  if (!confirm(`确认立即执行任务 "${task.task_display_name}"？`)) {
    return
  }

  try {
    const response = await axios.post(
      `${API_BASE_URL}/api/scheduled-task/${task.task_name}/trigger`
    )
    if (response.data.success) {
      alert('任务已触发执行')
      loadTasks()
    } else {
      alert('触发任务失败: ' + (response.data.message || '未知错误'))
    }
  } catch (error) {
    console.error('触发任务失败:', error)
    alert('触发任务失败: ' + (error.response?.data?.detail || error.message))
  }
}

const handleDeleteTask = async (task) => {
  if (!confirm(`确认删除任务 "${task.task_display_name}"？\n\n此操作不可恢复！`)) {
    return
  }

  try {
    const response = await axios.delete(
      `${API_BASE_URL}/api/scheduled-task/${task.task_name}`
    )
    if (response.data.success) {
      alert('任务已删除')
      loadTasks()
    } else {
      alert('删除任务失败: ' + (response.data.message || '未知错误'))
    }
  } catch (error) {
    console.error('删除任务失败:', error)
    alert('删除任务失败: ' + (error.response?.data?.detail || error.message))
  }
}

const handleResetRunningStatus = async () => {
  if (!confirm('确认重置所有标记为"运行中"但实际已停止的任务状态？\n\n这将重置所有 is_running=true 的任务状态为 false。')) {
    return
  }

  resetting.value = true
  try {
    const response = await axios.post(
      `${API_BASE_URL}/api/scheduled-task/reset-running-status`
    )
    if (response.data.success) {
      const data = response.data.data
      alert(
        `✅ ${response.data.message}\n\n` +
        `重置数量: ${data.reset_count} 个\n` +
        (data.reset_tasks && data.reset_tasks.length > 0
          ? `重置的任务: ${data.reset_tasks.join(', ')}`
          : '')
      )
      loadTasks()
    } else {
      alert('重置失败: ' + (response.data.message || '未知错误'))
    }
  } catch (error) {
    console.error('重置运行状态失败:', error)
    alert('重置失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    resetting.value = false
  }
}

onMounted(() => {
  loadTasks()
})
</script>
