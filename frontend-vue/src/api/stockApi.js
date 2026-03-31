// API 接口封装
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

export const stockApi = {
  // 获取今日推荐
  async getTodayRecommendations(limit = 10) {
    const response = await fetch(`${API_BASE_URL}/api/recommendations/today?limit=${limit}`)
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`)
    const result = await response.json()
    return result.recommendations || []
  },

  // 获取达尔文股票
  async getDarwinStocks(limit = 20) {
    const response = await fetch(`${API_BASE_URL}/api/darwin/stocks?limit=${limit}`)
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`)
    const result = await response.json()
    return result.items || []
  },

  // 获取波段股票
  async getSwingStocks(limit = 10) {
    const response = await fetch(`${API_BASE_URL}/api/recommendations?type=swing&limit=${limit}`)
    if (!response.ok) {
      const errorText = await response.text()
      throw new Error(`HTTP error! status: ${response.status}, ${errorText}`)
    }
    const result = await response.json()
    
    // 兼容多种返回格式（优先检查 data.swing）
    if (result.data && result.data.swing) {
      return result.data.swing
    } else if (result.items) {
      return result.items
    } else if (result.recommendations) {
      return result.recommendations
    } else if (Array.isArray(result)) {
      return result
    }
    return []
  },

  // 获取短线股票
  async getShortStocks(limit = 10) {
    const response = await fetch(`${API_BASE_URL}/api/recommendations?type=short&limit=${limit}`)
    if (!response.ok) {
      const errorText = await response.text()
      throw new Error(`HTTP error! status: ${response.status}, ${errorText}`)
    }
    const result = await response.json()
    
    // 兼容多种返回格式（优先检查 data.short）
    if (result.data && result.data.short) {
      return result.data.short
    } else if (result.items) {
      return result.items
    } else if (result.recommendations) {
      return result.recommendations
    } else if (Array.isArray(result)) {
      return result
    }
    return []
  },

  // 获取新高回踩股票
  async getNewHighStocks(limit = 10) {
    const response = await fetch(`${API_BASE_URL}/api/recommendations?type=new_high&limit=${limit}`)
    if (!response.ok) {
      const errorText = await response.text()
      throw new Error(`HTTP error! status: ${response.status}, ${errorText}`)
    }
    const result = await response.json()
    
    if (result.data && result.data.new_high) {
      return result.data.new_high
    } else if (result.items) {
      return result.items
    } else if (result.recommendations) {
      return result.recommendations
    } else if (Array.isArray(result)) {
      return result
    }
    return []
  },

  // 获取市场摘要
  async getMarketSummary() {
    const response = await fetch(`${API_BASE_URL}/api/market/summary`)
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`)
    return await response.json()
  },

  // 获取持仓列表（返回完整响应：data、count、pool_max_size、pool_full_suggestion）
  async getHoldings(boardType = null) {
    const params = new URLSearchParams()
    if (boardType) {
      params.append('board_type', boardType)
    }
    const response = await fetch(`${API_BASE_URL}/api/holdings?${params.toString()}`)
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`)
    const result = await response.json()
    return {
      data: result.data || [],
      count: result.count ?? 0,
      pool_max_size: result.pool_max_size ?? 8,
      pool_full_suggestion: result.pool_full_suggestion || null,
      ai_batch_suggestions: result.ai_batch_suggestions || null,
      today_realized: result.today_realized ?? 0
    }
  },

  // 添加持仓
  async addHolding(symbol, name, boardType, buyPrice = null, quantity = null) {
    const response = await fetch(`${API_BASE_URL}/api/holdings`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        symbol,
        name,
        board_type: boardType,
        buy_price: buyPrice,
        quantity: quantity
      })
    })
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`)
    const result = await response.json()
    return result.data
  },

  // 更新持仓
  async updateHolding(holdingId, opType, price = null, quantity = null) {
    const response = await fetch(`${API_BASE_URL}/api/holdings/${holdingId}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        op_type: opType,
        price,
        quantity
      })
    })
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`)
    const result = await response.json()
    return result.data
  },

  // 删除持仓
  async deleteHolding(holdingId) {
    const response = await fetch(`${API_BASE_URL}/api/holdings/${holdingId}`, {
      method: 'DELETE'
    })
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`)
    const result = await response.json()
    return result
  },

  // 手动刷新 AI 建议（10秒冷却）
  async refreshAiSuggestions(userId = 1) {
    const response = await fetch(`${API_BASE_URL}/api/holdings/ai-suggestions/refresh?user_id=${userId}`, {
      method: 'POST'
    })
    if (!response.ok) {
      const errorText = await response.text()
      throw new Error(errorText || `HTTP error! status: ${response.status}`)
    }
    return await response.json()
  },
}

// 格式化股票数据
export function formatStockData(stock) {
  // 处理价格
  let price = stock.价格 || stock.price || stock.currentPrice || stock.current_price || '--'
  if (typeof price === 'number') {
    price = price.toFixed(2)
  }
  
  // 处理涨跌幅
  let changePercent = stock.涨跌幅 || stock.changePercent || stock.changePct || stock.change_pct || stock.pct_chg || 0
  if (typeof changePercent === 'string') {
    changePercent = parseFloat(changePercent.replace('%', '')) || 0
  }
  
  // 处理成交额
  let volume = stock.成交额 || stock.volume || stock.volumeAmount || stock.amount || stock.amt || '--'
  if (typeof volume === 'number') {
    if (volume >= 100000000) {
      volume = (volume / 100000000).toFixed(2) + '亿'
    } else if (volume >= 10000) {
      volume = (volume / 10000).toFixed(2) + '万'
    } else {
      volume = volume.toFixed(2)
    }
  }
  
  // 处理换手率
  let turnover = stock.换手 || stock.turnover || stock.换手率 || stock.turnoverRate || stock.turnover_rate || '--'
  if (typeof turnover === 'string' && !turnover.includes('%')) {
    turnover = turnover + '%'
  } else if (typeof turnover === 'number') {
    turnover = turnover.toFixed(2) + '%'
  }
  
  // 处理入手区间
  let buyRange = stock.buyRange || stock.buy_range || null
  if (buyRange && typeof buyRange === 'object') {
    buyRange = {
      min: buyRange.min || buyRange.minPrice || 0,
      max: buyRange.max || buyRange.maxPrice || 0,
    }
  }
  
  return {
    code: stock.代码 || stock.code || stock.ts_code || '',
    name: stock.名称 || stock.name || stock.股票名称 || stock.stock_name || '',
    price: price,
    change: stock.涨幅 || stock.change || 0,
    changePercent: changePercent,
    volume: volume,
    turnover: turnover,
    sector: stock.行业 || stock.sector || stock.板块 || stock.industry || '--',
    score: stock.darwinScore || stock.darwin_score || stock.finalScore || stock.final_score || stock.score || 0,
    trendScore: stock.trendScore !== null && stock.trendScore !== undefined ? stock.trendScore : (stock.trend_score !== null && stock.trend_score !== undefined ? stock.trend_score : null),
    sectorHeat: stock.sectorHeat !== null && stock.sectorHeat !== undefined ? stock.sectorHeat : (stock.sector_heat !== null && stock.sector_heat !== undefined ? stock.sector_heat : null),
    isIndustryLeader: stock.isIndustryLeader || stock.is_industry_leader || false,
    advice: stock.advice || stock.operationAdvice || stock.operation_advice || stock.longTermAdvice || '',
    reason: stock.reason || stock.explain || stock.推荐理由 || '',
    buyRange: buyRange,
    volumePricePattern: stock.volumePricePattern || stock.volume_price_pattern || stock.量价形态 || '',
    vpAdvice: stock.vpAdvice || stock.vp_advice || stock.操作建议 || '',
    vpComment: stock.vpComment || stock.vp_comment || stock.形态解读 || '',
    analysis: stock.analysis || null,
    financialHealth: stock.financialHealth || stock.financial_health || 0,
    // AI评分相关字段
    aiScore: stock.AI评分 || stock.aiScore || null,
    deepseekScore: stock.Deepseek评分 || stock.deepseekScore || null,
    aiAnalysis: stock.AI分析 || stock.aiAnalysis || null,
    deepseekAnalysis: stock.Deepseek分析 || stock.deepseekAnalysis || null,
  }
}

