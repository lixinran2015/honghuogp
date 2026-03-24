# 数据输出逻辑对比报告

## 一、达尔文公司筛选逻辑对比

### React 版本（frontend/src/App.jsx）
```javascript
// 筛选条件
.filter(stock => {
  const advice = stock.advice || stock.operationAdvice || stock.operation_advice || '';
  return advice === '买入';  // 严格等于 '买入'
})

// 排序
.sort((a, b) => {
  const scoreA = a.darwinScore || a.darwin_score || a.finalScore || a.final_score || 0;
  const scoreB = b.darwinScore || b.darwin_score || b.finalScore || b.final_score || 0;
  return scoreB - scoreA;
})

// 数量限制
.slice(0, 10)

// 数据格式化
.map(stock => {
  return {
    代码: stock.code || stock.ts_code || '',
    股票名称: stock.name || stock.stock_name || '',
    策略类型: '达尔文公司',
    最新价: stock.currentPrice || stock.current_price || stock.close || 0,
    涨跌幅: stock.changePct || stock.change_pct || stock.pct_chg || 0,
    换手率: turnover_rate,  // 已格式化
    成交额: stock.amount || stock.amt || 0,  // 原始数值
    所属行业: stock.sector || stock.industry || '未知',
    入手价格区间: stock.buyRange ? `¥${stock.buyRange.min.toFixed(2)} - ¥${stock.buyRange.max.toFixed(2)} 元` : '',
    推荐理由: stock.reason || `达尔文评分: ${score.toFixed(1)}分`,
    量价形态: stock.volumePricePattern || stock.comment || '',
    操作建议: stock.advice || stock.operationAdvice || stock.longTermAdvice || '长期持有',
    综合得分: score,
    darwinScore: score
  };
})
```

### Vue 版本（frontend-vue/src/views/RecommendationsView.vue）
```javascript
// 筛选条件
.filter(stock => {
  const advice = stock.advice || stock.operationAdvice || stock.operation_advice || stock.longTermAdvice || '';
  return advice === '买入' || advice.includes('买入');  // ⚠️ 差异：更宽松
})

// 排序（相同）
.sort((a, b) => {
  const scoreA = a.darwinScore || a.darwin_score || a.finalScore || a.final_score || 0;
  const scoreB = b.darwinScore || b.darwin_score || b.finalScore || b.final_score || 0;
  return scoreB - scoreA;
})

// 数量限制（相同）
.slice(0, 10)

// 数据格式化（使用 formatStockData 函数）
.map(formatStockData)
```

### ⚠️ 差异点
1. **筛选条件**：Vue 版本更宽松（`advice === '买入' || advice.includes('买入')`），可能包含更多股票
2. **数据格式化**：Vue 版本使用统一的 `formatStockData` 函数，字段名不同（英文 vs 中文）

---

## 二、波段股票数据处理对比

### React 版本
```javascript
// API 返回格式处理
let swingData = [];
if (result.data && result.data.swing) {
  swingData = result.data.swing;
} else if (result.items) {
  swingData = result.items;
} else if (result.recommendations) {
  swingData = result.recommendations;
} else if (Array.isArray(result)) {
  swingData = result;
}

// 数据格式化
.map(rec => {
  return {
    代码: code,
    股票名称: name,
    策略类型: '波段票',
    最新价: currentPrice,
    涨跌幅: changePct,
    换手率: turnoverRate,  // 已格式化
    成交额: amount,  // 原始数值
    所属行业: sector,
    入手价格区间: buyRangeStr,  // 已格式化字符串
    推荐理由: rec.reason || rec.推荐理由 || '',
    量价形态: rec.volumePricePattern || rec.量价形态 || '',
    操作建议: rec.advice || rec.操作建议 || '',
    综合得分: rec.score || rec.综合得分 || 0
  };
})
```

### Vue 版本
```javascript
// API 返回格式处理（相同）
// 使用 stockApi.getSwingStocks()，内部处理相同

// 数据格式化（使用 formatStockData）
.map(formatStockData)
```

### ⚠️ 差异点
1. **字段名**：React 使用中文字段名，Vue 使用英文字段名
2. **成交额格式化**：React 不格式化，Vue 格式化为亿/万单位

---

## 三、短线股票数据处理对比

### React 版本
```javascript
// API 返回格式处理
let stocks = [];
if (result.data && result.data.short) {
  stocks = result.data.short;
} else if (result.recommendations) {
  stocks = result.recommendations;
} else if (result.items) {
  stocks = result.items;
} else if (Array.isArray(result)) {
  stocks = result;
}

// 数据格式化
.map(rec => ({
  代码: rec.代码 || rec.code || '',
  股票名称: rec.股票名称 || rec.name || '',
  策略类型: rec.策略类型 || (rec.type === 'attack' ? '短线票（攻）' : 
          rec.type === 'bottom_fishing' ? '短线票（抄底）' : '短线票'),
  最新价: rec.最新价 || rec.currentPrice || 0,
  涨跌幅: rec.涨跌幅 || rec.changePct || 0,
  换手率: rec.换手率 || rec.turnoverRate || '0%',
  成交额: rec.成交额 || rec.amount || 0,  // 原始数值
  所属行业: rec.所属行业 || rec.sector || '未知',
  入手价格区间: rec.入手价格区间 || (rec.buyRange ? `¥${rec.buyRange.min.toFixed(2)} - ¥${rec.buyRange.max.toFixed(2)} 元` : ''),
  推荐理由: rec.推荐理由 || rec.reason || '',
  量价形态: rec.量价形态 || rec.volumePricePattern || '',
  操作建议: rec.操作建议 || rec.advice || '',
  综合得分: rec.综合得分 || rec.score || 0
}))
```

### Vue 版本
```javascript
// API 返回格式处理（相同）
// 使用 stockApi.getShortStocks()，内部处理相同

// 数据格式化（使用 formatStockData）
.map(formatStockData)
```

### ⚠️ 差异点
1. **策略类型**：React 版本有更详细的类型（攻/抄底），Vue 版本统一为 'short'
2. **字段名**：React 使用中文字段名，Vue 使用英文字段名

---

## 四、formatStockData 函数对比

### Vue 版本的 formatStockData（frontend-vue/src/api/stockApi.js）
```javascript
export function formatStockData(stock) {
  return {
    code: stock.代码 || stock.code || stock.ts_code || '',
    name: stock.名称 || stock.name || stock.股票名称 || stock.stock_name || '',
    price: price,  // 已格式化为字符串，保留2位小数
    change: stock.涨幅 || stock.change || 0,
    changePercent: changePercent,  // 已转换为数字
    volume: volume,  // 已格式化为亿/万单位字符串
    turnover: turnover,  // 已格式化为带%的字符串
    sector: stock.行业 || stock.sector || stock.板块 || stock.industry || '--',
    score: stock.darwinScore || stock.darwin_score || stock.finalScore || stock.final_score || stock.score || 0,
    trendScore: stock.trendScore || stock.trend_score || 0,
    sectorHeat: stock.sectorHeat || stock.sector_heat || 0,
    advice: stock.advice || stock.operationAdvice || stock.operation_advice || stock.longTermAdvice || '',
    reason: stock.reason || stock.explain || stock.推荐理由 || '',
    buyRange: buyRange,  // 对象格式 {min, max}，不是字符串
    volumePricePattern: stock.volumePricePattern || stock.volume_price_pattern || stock.量价形态 || '',
    analysis: stock.analysis || null,
    financialHealth: stock.financialHealth || stock.financial_health || 0,
  }
}
```

### ⚠️ 主要差异
1. **字段名**：Vue 使用英文字段名（code, name, price），React 使用中文字段名（代码, 股票名称, 最新价）
2. **成交额格式化**：Vue 自动格式化为亿/万单位，React 保持原始数值
3. **入手区间**：Vue 返回对象 `{min, max}`，React 返回格式化字符串
4. **额外字段**：Vue 包含 `trendScore`, `sectorHeat`, `analysis`, `financialHealth` 等字段

---

## 五、总结与建议

### ✅ 相同点
1. API 调用逻辑相同
2. 筛选条件基本相同（达尔文筛选略有差异）
3. 排序逻辑相同
4. 数量限制相同

### ⚠️ 差异点
1. **达尔文筛选**：Vue 版本更宽松（`advice.includes('买入')`）
2. **字段名**：Vue 使用英文，React 使用中文
3. **数据格式化**：Vue 更统一，自动格式化成交额、换手率等
4. **入手区间**：Vue 返回对象，React 返回字符串

### 🔧 建议修复
1. **统一达尔文筛选条件**：Vue 版本改为严格 `advice === '买入'`，与 React 版本一致
2. **统一字段名**：考虑在 Vue 版本中同时支持中英文字段名，或统一使用一种
3. **统一数据格式**：入手区间格式需要统一（建议 Vue 版本也格式化为字符串，与 React 一致）

