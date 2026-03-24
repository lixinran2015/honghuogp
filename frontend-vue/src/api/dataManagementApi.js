// 数据管理API接口封装（与其它页面一致：支持代理或直连后端）
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

export const dataManagementApi = {
  /**
   * 获取数据源健康状态
   */
  async getDataSourceHealth() {
    const response = await fetch(`${API_BASE_URL}/api/data-management/health`)
    if (!response.ok) {
      const errorText = await response.text()
      throw new Error(`HTTP error! status: ${response.status}, ${errorText}`)
    }
    const result = await response.json()
    return result.data || {}
  },

  /**
   * 获取定时任务执行状态
   * @param {number} limit - 返回记录数限制
   * @param {string} taskName - 任务名称筛选（可选）
   */
  async getTaskExecutionStatus(limit = 50, taskName = null) {
    let url = `${API_BASE_URL}/api/data-management/tasks?limit=${limit}`
    if (taskName) {
      url += `&task_name=${encodeURIComponent(taskName)}`
    }
    const response = await fetch(url)
    if (!response.ok) {
      const errorText = await response.text()
      throw new Error(`HTTP error! status: ${response.status}, ${errorText}`)
    }
    const result = await response.json()
    return result.data || { tasks: [], total: 0 }
  },

  /**
   * 获取数据质量指标
   */
  async getDataQualityMetrics() {
    const response = await fetch(`${API_BASE_URL}/api/data-management/quality`)
    if (!response.ok) {
      const errorText = await response.text()
      throw new Error(`HTTP error! status: ${response.status}, ${errorText}`)
    }
    const result = await response.json()
    return result.data || {}
  },

  /**
   * 触发数据更新
   * @param {string} taskType - 任务类型（daily_update, fundamental_update, refresh_snapshot, sector_heat_update, sector_leaders_update）
   */
  async triggerDataUpdate(taskType) {
    const response = await fetch(`${API_BASE_URL}/api/data-management/trigger-update`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ task_type: taskType }),
    })
    if (!response.ok) {
      const errorText = await response.text()
      throw new Error(`HTTP error! status: ${response.status}, ${errorText}`)
    }
    const result = await response.json()
    return result.data || {}
  },

  /**
   * 获取指定任务的执行状态
   * @param {number} taskId - 任务ID
   */
  async getTaskStatus(taskId) {
    const response = await fetch(`${API_BASE_URL}/api/data-management/task/${taskId}`)
    if (!response.ok) {
      const errorText = await response.text()
      throw new Error(`HTTP error! status: ${response.status}, ${errorText}`)
    }
    const result = await response.json()
    return result.data || {}
  },

  /**
   * 检查缺失数据
   * @param {number} days - 检查最近N天，默认5天
   */
  async checkMissingData(days = 5) {
    const response = await fetch(`${API_BASE_URL}/api/data-management/check-missing?days=${days}`)
    if (!response.ok) {
      const errorText = await response.text()
      throw new Error(`HTTP error! status: ${response.status}, ${errorText}`)
    }
    const result = await response.json()
    return result.data || {}
  },

  /**
   * 补缺失日线：先查库最新日线日期，再只补近 N 天内、今天之前的缺失日期（后台执行）
   * @param {number} days - 近 N 天，默认 5
   * @param {number} timeoutMs - 请求超时（毫秒）
   */
  async fillMissingDaily(days = 5, timeoutMs = 60000) {
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs)
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/data-management/fill-missing-daily?days=${days}`,
        { method: 'POST', signal: controller.signal }
      )
      clearTimeout(timeoutId)
      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`HTTP ${response.status}: ${errorText || response.statusText}`)
      }
      const result = await response.json()
      return result.data || {}
    } catch (e) {
      clearTimeout(timeoutId)
      if (e.name === 'AbortError') {
        throw new Error(`请求在 ${Math.round(timeoutMs / 1000)} 秒内未收到响应，请稍后重试。`)
      }
      throw e
    }
  },

  /**
   * 增量更新缺失数据（日线等）
   * @param {number} days - 检查最近N天，默认5天
   * @param {number} timeoutMs - 请求超时（毫秒），默认 60000，与代理超时一致
   */
  async updateMissingData(days = 5, timeoutMs = 60000) {
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs)
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/data-management/update-missing?days=${days}&force=true`,
        { method: 'POST', signal: controller.signal }
      )
      clearTimeout(timeoutId)
      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`HTTP ${response.status}: ${errorText || response.statusText}`)
      }
      const result = await response.json()
      return result.data || {}
    } catch (e) {
      clearTimeout(timeoutId)
      if (e.name === 'AbortError') {
        const sec = Math.round(timeoutMs / 1000)
        throw new Error(
          `请求在 ${sec} 秒内未收到响应。请确认：① 后端服务已启动（如 http://localhost:8000）；② 开发环境下前端代理指向正确。可稍后重试。`
        )
      }
      throw e
    }
  },
}

