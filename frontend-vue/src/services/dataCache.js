/**
 * 全局数据缓存服务
 * 用于缓存各个页面的数据，避免重复请求
 */

class DataCache {
  constructor() {
    this.cache = new Map()
    this.loadingPromises = new Map() // 防止重复请求
  }

  /**
   * 获取缓存数据
   * @param {string} key - 缓存键
   * @returns {any|null} 缓存的数据，如果不存在返回null
   */
  get(key) {
    return this.cache.get(key) || null
  }

  /**
   * 设置缓存数据
   * @param {string} key - 缓存键
   * @param {any} data - 要缓存的数据
   */
  set(key, data) {
    this.cache.set(key, {
      data,
      timestamp: Date.now()
    })
  }

  /**
   * 检查缓存是否存在且有效
   * @param {string} key - 缓存键
   * @param {number} maxAge - 最大缓存时间（毫秒），默认30分钟
   * @returns {boolean}
   */
  has(key, maxAge = 30 * 60 * 1000) {
    const cached = this.cache.get(key)
    if (!cached) return false
    
    const age = Date.now() - cached.timestamp
    return age < maxAge
  }

  /**
   * 清除指定缓存
   * @param {string} key - 缓存键
   */
  clear(key) {
    this.cache.delete(key)
    this.loadingPromises.delete(key)
  }

  /**
   * 清除所有缓存
   */
  clearAll() {
    this.cache.clear()
    this.loadingPromises.clear()
  }

  /**
   * 获取或加载数据（带防重复请求）
   * @param {string} key - 缓存键
   * @param {Function} loader - 数据加载函数（返回Promise）
   * @param {boolean} forceRefresh - 是否强制刷新
   * @returns {Promise<any>}
   */
  async getOrLoad(key, loader, forceRefresh = false) {
    // 如果正在加载，返回同一个Promise
    if (this.loadingPromises.has(key) && !forceRefresh) {
      return this.loadingPromises.get(key)
    }

    // 如果缓存有效且不强制刷新，直接返回缓存
    if (!forceRefresh && this.has(key)) {
      return this.get(key).data
    }

    // 清除旧的加载Promise
    this.loadingPromises.delete(key)

    // 开始加载
    const promise = loader()
      .then(data => {
        this.set(key, data)
        this.loadingPromises.delete(key)
        return data
      })
      .catch(error => {
        this.loadingPromises.delete(key)
        throw error
      })

    this.loadingPromises.set(key, promise)
    return promise
  }
}

// 导出单例
export const dataCache = new DataCache()

// 缓存键常量
export const CACHE_KEYS = {
  RECOMMENDATIONS: 'recommendations',
  DARWIN_STOCKS: 'darwin_stocks',
  HOLDINGS: 'holdings',
  STRATEGY: 'strategy',
  DATA_MANAGEMENT_HEALTH: 'data_management_health',
  DATA_MANAGEMENT_QUALITY: 'data_management_quality',
  DATA_MANAGEMENT_TASKS: 'data_management_tasks'
}

