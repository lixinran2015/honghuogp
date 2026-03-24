/**
 * 策略引擎API
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

/**
 * 获取策略引擎说明
 */
export async function getStrategyEngines() {
  try {
    const response = await fetch(`${API_BASE}/api/engines`)
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }
    const data = await response.json()
    return data.engines || []
  } catch (error) {
    console.error('获取策略引擎失败:', error)
    return []
  }
}

