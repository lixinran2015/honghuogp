// 模块配置 API
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

/**
 * 获取模块状态
 * @returns {Promise<{short_term: {enabled: boolean, features: Object}, long_term: {enabled: boolean, features: Object}, common: {enabled: boolean, features: Object}}>}
 */
export async function getModuleStatus() {
  const response = await fetch(`${API_BASE_URL}/api/modules`)
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`)
  return await response.json()
}

/**
 * 切换模块启用状态
 * @param {string} moduleName - 模块名称: short_term | long_term | common
 * @param {boolean} enabled - 是否启用
 */
export async function toggleModule(moduleName, enabled) {
  const response = await fetch(`${API_BASE_URL}/api/modules/${moduleName}/toggle`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ enabled })
  })
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`)
  return await response.json()
}

/**
 * 切换系统模式
 * @param {string} mode - 模式: short_term | long_term | all
 */
export async function switchMode(mode) {
  const response = await fetch(`${API_BASE_URL}/api/modules/switch-mode/${mode}`, {
    method: 'POST'
  })
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`)
  return await response.json()
}

/**
 * 重新加载模块配置
 */
export async function reloadModuleConfig() {
  const response = await fetch(`${API_BASE_URL}/api/modules/reload`, {
    method: 'POST'
  })
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`)
  return await response.json()
}
