/**
 * 模块配置管理
 * 根据后端 /api/modules 返回的状态，控制前端菜单和功能的显示/隐藏
 */
import { ref, computed, readonly } from 'vue'
import { getModuleStatus, toggleModule, switchMode, reloadModuleConfig } from '../api/moduleApi.js'

// 模块状态
const moduleStatus = ref({
  short_term: { enabled: true, features: {} },
  long_term: { enabled: false, features: {} },
  common: { enabled: true, features: {} }
})

const isLoading = ref(false)
const error = ref(null)

/**
 * 加载模块状态
 */
async function loadModuleStatus() {
  isLoading.value = true
  error.value = null
  try {
    const status = await getModuleStatus()
    moduleStatus.value = {
      short_term: status.short_term || { enabled: true, features: {} },
      long_term: status.long_term || { enabled: false, features: {} },
      common: status.common || { enabled: true, features: {} }
    }
    return moduleStatus.value
  } catch (e) {
    error.value = e.message
    console.error('加载模块状态失败:', e)
    // 使用默认值
    return moduleStatus.value
  } finally {
    isLoading.value = false
  }
}

/**
 * 启用/禁用模块
 */
async function setModuleEnabled(moduleName, enabled) {
  try {
    await toggleModule(moduleName, enabled)
    moduleStatus.value[moduleName].enabled = enabled
    return true
  } catch (e) {
    console.error(`切换模块 ${moduleName} 失败:`, e)
    return false
  }
}

/**
 * 切换系统模式
 */
async function setSystemMode(mode) {
  try {
    await switchMode(mode)
    await loadModuleStatus()
    return true
  } catch (e) {
    console.error('切换系统模式失败:', e)
    return false
  }
}

/**
 * 重新加载配置
 */
async function refreshConfig() {
  try {
    await reloadModuleConfig()
    await loadModuleStatus()
    return true
  } catch (e) {
    console.error('重新加载配置失败:', e)
    return false
  }
}

// 计算属性
const isShortTermEnabled = computed(() => moduleStatus.value.short_term?.enabled ?? true)
const isLongTermEnabled = computed(() => moduleStatus.value.long_term?.enabled ?? false)
const isCommonEnabled = computed(() => moduleStatus.value.common?.enabled ?? true)

// 当前系统模式
const systemMode = computed(() => {
  const shortTerm = isShortTermEnabled.value
  const longTerm = isLongTermEnabled.value

  if (shortTerm && !longTerm) return 'short_term'
  if (!shortTerm && longTerm) return 'long_term'
  if (shortTerm && longTerm) return 'all'
  return 'unknown'
})

export function useModuleConfig() {
  return {
    // 状态
    moduleStatus: readonly(moduleStatus),
    isLoading: readonly(isLoading),
    error: readonly(error),

    // 计算属性
    isShortTermEnabled,
    isLongTermEnabled,
    isCommonEnabled,
    systemMode,

    // 方法
    loadModuleStatus,
    setModuleEnabled,
    setSystemMode,
    refreshConfig
  }
}
