const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

export const monitorApi = {
  // 获取绩效统计
  async getPerformance(recentN = 20, gradeBreakdown = false) {
    const response = await fetch(
      `${API_BASE_URL}/api/short-term/monitor/performance?recent_n=${recentN}&grade_breakdown=${gradeBreakdown}`
    )
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`)
    return await response.json()
  },

  // 获取健康度报告
  async getHealth() {
    const response = await fetch(`${API_BASE_URL}/api/short-term/monitor/health`)
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`)
    return await response.json()
  },

  // 获取熔断状态
  async getCircuitBreaker() {
    const response = await fetch(`${API_BASE_URL}/api/short-term/monitor/circuit-breaker`)
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`)
    return await response.json()
  },
}
