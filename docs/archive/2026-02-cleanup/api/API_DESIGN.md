# 🔌 API接口设计文档

## 一、现有API接口

### 1.1 混合推荐接口

**接口**: `GET /api/mixed-recommendations`

**参数**:
- `force_refresh` (bool, 可选): 是否强制刷新数据

**响应**:
```json
{
  "success": true,
  "data": [
    {
      "代码": "sh600711",
      "股票名称": "盛屯矿业",
      "策略类型": "短线票",
      "最新价": 12.64,
      "涨跌幅": 3.52,
      "成交额": 3164860000.0,
      "换手率": "8.14%",
      "入手价格区间": "¥12.39 - ¥12.89 元",
      "推荐理由": "低位启动(涨幅3.52%)，换手8.14%，成交316486.0亿，埋伏机会",
      "综合得分": 9497.392,
      "AI评分": "N/A",
      "AI分析": "待AI分析...",
      "投资建议": "分析中...",
      "Deepseek评分": "N/A",
      "Deepseek分析": "待AI分析...",
      "Deepseek建议": "分析中..."
    }
  ],
  "count": 5
}
```

### 1.2 市场数据接口

**接口**: `GET /api/market-data`

**响应**:
```json
{
  "success": true,
  "data": {
    "sh_index": {
      "current": "4023.97",
      "change": "-0.14%"
    },
    "sz_index": {
      "current": "13337.92",
      "change": "-1.03%"
    }
  }
}
```

### 1.3 AI分析接口

**接口**: `POST /api/ai-analysis`

**请求体**:
```json
["sh600711", "sh688472"]
```

**响应**:
```json
{
  "success": true,
  "data": [
    {
      "代码": "sh600711",
      "股票名称": "盛屯矿业",
      "AI评分": 75,
      "AI分析": "市场情绪偏强，个股表现良好，适合短期操作。",
      "投资建议": "买入"
    }
  ],
  "count": 2
}
```

---

## 二、优化后的API接口设计

### 2.1 推荐接口（优化版）

**接口**: `GET /api/recommendations`

**参数**:
- `type` (string, 可选): 推荐类型，可选值：`short`、`swing`、`long`、`all`（默认：`all`）
- `limit` (int, 可选): 每种类型推荐数量（默认：5）
- `date` (string, 可选): 日期，格式：`YYYY-MM-DD`（默认：今天）

**响应**:
```json
{
  "success": true,
  "data": {
    "short": [
      {
        "代码": "sh600711",
        "股票名称": "盛屯矿业",
        "策略类型": "短线票",
        "最新价": 12.64,
        "涨跌幅": 3.52,
        "换手率": "8.14%",
        "成交额": 3164860000.0,
        "所属行业": "未知",
        "入手价格区间": {
          "min": 12.39,
          "max": 12.89
        },
        "推荐理由": "低位启动(涨幅3.52%)，换手8.14%，成交316486.0亿，埋伏机会",
        "综合得分": 85.5,
        "AI评分": 75,
        "AI分析": "市场情绪偏强，个股表现良好，适合短期操作。",
        "投资建议": "买入"
      }
    ],
    "swing": [
      {
        "代码": "sz300274",
        "股票名称": "阳光电源",
        "策略类型": "波段票",
        "最新价": 190.47,
        "涨跌幅": -0.02,
        "换手率": "2.04%",
        "成交额": 6176080000.0,
        "所属行业": "未知",
        "入手价格区间": {
          "min": 180.95,
          "max": 199.99
        },
        "推荐理由": "超跌反弹(涨幅-0.02%)，换手2.04%，价值回归",
        "综合得分": 28.76,
        "AI评分": "N/A",
        "AI分析": "待AI分析...",
        "投资建议": "分析中..."
      }
    ]
  },
  "count": 5,
  "date": "2025-11-14"
}
```

### 2.2 市场概况接口（优化版）

**接口**: `GET /api/market/summary`

**响应**:
```json
{
  "success": true,
  "data": {
    "date": "2025-11-14",
    "indices": {
      "sse": {
        "name": "上证指数",
        "value": 4023.97,
        "changePct": -0.14,
        "change": "-0.14%"
      },
      "szse": {
        "name": "深证成指",
        "value": 13337.92,
        "changePct": -1.03,
        "change": "-1.03%"
      },
      "cyb": {
        "name": "创业板指",
        "value": 2456.78,
        "changePct": -0.85,
        "change": "-0.85%"
      }
    },
    "dataSource": "realtime",
    "updateTime": "2025-11-14 11:05:09"
  }
}
```

### 2.3 长线推荐接口（新增）

**接口**: `GET /api/recommendations/long-term`

**参数**:
- `limit` (int, 可选): 推荐数量（默认：10）

**响应**:
```json
{
  "success": true,
  "data": [
    {
      "代码": "000001",
      "股票名称": "平安银行",
      "策略类型": "长线票",
      "最新价": 10.0,
      "达尔文评分": 85.5,
      "财务健康系数": 0.92,
      "综合得分": 78.66,
      "建仓区间": {
        "min": 9.5,
        "max": 10.5
      },
      "推荐理由": "供需长期向上，行业格局好，ROE稳定，现金流强",
      "风险提示": ["行业周期风险", "现金流风险"]
    }
  ],
  "count": 10
}
```

### 2.4 基金定投接口（新增）

**接口**: `GET /api/fund/recommendations`

**响应**:
```json
{
  "success": true,
  "data": [
    {
      "code": "000300",
      "name": "沪深300",
      "pe_percentile": 45.2,
      "pb_percentile": 38.5,
      "recommendation": "正常定投",
      "reason": "PE分位数45.2%，PB分位数38.5%，处于合理区间",
      "suggested_amount": 1000
    }
  ],
  "count": 5
}
```

### 2.5 报告生成接口（新增）

**接口**: `GET /api/reports/{report_type}`

**参数**:
- `report_type` (string): 报告类型，可选值：`short-term`、`middle-term`、`long-term`、`fund`
- `date` (string, 可选): 日期，格式：`YYYY-MM-DD`（默认：今天）

**响应**:
```json
{
  "success": true,
  "data": {
    "type": "short-term",
    "date": "2025-11-14",
    "content": "# 每日短线战报\n\n## 今日主线板块\n...",
    "file_path": "output/ShortTerm_Report_20251114.md"
  }
}
```

---

## 三、前端数据对接

### 3.1 数据结构定义

```typescript
// 股票推荐数据
interface StockRecommendation {
  code: string;                    // 代码
  name: string;                    // 股票名称
  type: "short" | "swing" | "long"; // 策略类型
  currentPrice: number;            // 最新价
  changePct: number;               // 涨跌幅
  turnoverRate: string;            // 换手率
  amount: number;                  // 成交额
  sector: string;                  // 所属行业
  buyRange: {                      // 入手价格区间
    min: number;
    max: number;
  } | null;
  reason: string;                  // 推荐理由
  score: number;                   // 综合得分
  aiScore?: number | null;         // AI评分
  aiAnalysis?: string | null;      // AI分析
  suggestion?: string | null;      // 投资建议
}

// 市场概况数据
interface MarketSummary {
  date: string;
  indices: {
    sse: IndexData;
    szse: IndexData;
    cyb?: IndexData;
  };
  dataSource: string;
  updateTime: string;
}

interface IndexData {
  name: string;
  value: number;
  changePct: number;
  change: string;
}
```

### 3.2 API调用示例

```typescript
// 获取推荐股票
const fetchRecommendations = async () => {
  const response = await fetch('/api/recommendations?type=all&limit=5');
  const data = await response.json();
  
  if (data.success) {
    setShortStocks(data.data.short || []);
    setSwingStocks(data.data.swing || []);
  }
};

// 获取市场概况
const fetchMarketSummary = async () => {
  const response = await fetch('/api/market/summary');
  const data = await response.json();
  
  if (data.success) {
    setMarketData(data.data);
  }
};

// 触发AI分析
const analyzeStocks = async (stockCodes: string[]) => {
  const response = await fetch('/api/ai-analysis', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(stockCodes)
  });
  
  const data = await response.json();
  if (data.success) {
    // 更新股票数据
    updateStocksWithAI(data.data);
  }
};
```

---

## 四、错误处理

### 4.1 错误响应格式

```json
{
  "success": false,
  "error": {
    "code": "DATA_FETCH_ERROR",
    "message": "无法获取真实股票数据",
    "details": "网络连接失败"
  }
}
```

### 4.2 错误码定义

- `DATA_FETCH_ERROR`: 数据获取失败
- `FILTER_ERROR`: 筛选失败
- `AI_ANALYSIS_ERROR`: AI分析失败
- `INVALID_PARAMETER`: 参数错误
- `SERVICE_UNAVAILABLE`: 服务不可用

---

## 五、性能优化

### 5.1 缓存策略

- 市场数据：10分钟缓存
- 推荐结果：5分钟缓存
- AI分析结果：30分钟缓存

### 5.2 超时设置

- 数据获取：30秒
- AI分析：5分钟
- 报告生成：2分钟

---

## 六、版本控制

### 6.1 API版本

- 当前版本：`v1`
- 版本号通过URL路径传递：`/api/v1/recommendations`

### 6.2 向后兼容

- 保持旧接口可用
- 新功能通过新接口提供
- 逐步迁移到新接口

