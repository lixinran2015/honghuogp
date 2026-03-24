/**
 * 数据预加载服务
 * 在应用启动时预加载所有页面的数据
 */

import { dataCache, CACHE_KEYS } from './dataCache'
import { stockApi } from '../api/stockApi'

/**
 * 预加载所有页面的数据
 */
// 预加载功能暂时全部禁用，各页面按需加载数据
// 如需启用，在 preloadTasks 中添加对应的 preloadXxx() 调用
export async function preloadAllData() {
  // no-op
}

/**
 * 预加载推荐选股数据
 */
async function preloadRecommendations() {
  try {
    console.log('📊 预加载推荐选股数据...')
    // 注意：达尔文数据由 preloadDarwinStocks 统一加载（limit=1000）
    // 这里只加载波段和短线数据，避免重复请求
    const results = await Promise.allSettled([
      stockApi.getSwingStocks(50).catch(() => []),
      stockApi.getShortStocks(50).catch(() => [])
    ])
    
    const [swing, short] = results.map(r => 
      r.status === 'fulfilled' ? (r.value || []) : []
    )
    
    // 达尔文数据从缓存获取（由 preloadDarwinStocks 加载）
    const darwinCached = dataCache.get(CACHE_KEYS.DARWIN_STOCKS)
    const darwin = Array.isArray(darwinCached) ? darwinCached : (darwinCached?.data || [])
    
    dataCache.set(CACHE_KEYS.RECOMMENDATIONS, {
      darwin: darwin.slice(0, 100) || [],  // 推荐页面只需要前100条
      swing: swing || [],
      short: short || []
    })
    console.log('✅ 推荐选股数据预加载完成', { darwin: darwin.length, swing: swing.length, short: short.length })
  } catch (error) {
    console.error('❌ 预加载推荐选股数据失败:', error)
    // 即使失败也设置空数据，避免页面报错
    dataCache.set(CACHE_KEYS.RECOMMENDATIONS, {
      darwin: [],
      swing: [],
      short: []
    })
  }
}

/**
 * 预加载达尔文评分数据
 */
async function preloadDarwinStocks() {
  try {
    console.log('⭐ 预加载达尔文评分数据...')
    const data = await stockApi.getDarwinStocks(1000).catch(() => [])
    dataCache.set(CACHE_KEYS.DARWIN_STOCKS, data || [])
    console.log('✅ 达尔文评分数据预加载完成')
  } catch (error) {
    console.error('❌ 预加载达尔文评分数据失败:', error)
    // 即使失败也设置空数据，避免页面报错
    dataCache.set(CACHE_KEYS.DARWIN_STOCKS, [])
  }
}

/**
 * 预加载持仓数据
 */
async function preloadHoldings() {
  try {
    console.log('💼 预加载持仓数据...')
    const res = await stockApi.getHoldings().catch(() => ({ data: [] }))
    dataCache.set(CACHE_KEYS.HOLDINGS, res && res.data ? res : { data: res?.data || [] })
    console.log('✅ 持仓数据预加载完成')
  } catch (error) {
    console.error('❌ 预加载持仓数据失败:', error)
  }
}

