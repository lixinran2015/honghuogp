# Tushare Pro 集成说明

## 概述

已成功集成 Tushare Pro 数据源，用于：
1. **财务数据**：替代 akshare 不稳定的财务接口
2. **资金流向数据**：用于月度热点统计
3. **板块数据**：用于行业分析

## Token 配置

Token 已配置在 `config.json` 中：
```json
{
  "api_sources": {
    "tushare": {
      "enabled": true,
      "token": "abf0532e01d1fccd63ca214d92b9b9655c5738e1a472b8f0d5487573",
      "base_url": "http://api.tushare.pro",
      "timeout": 10
    }
  }
}
```

## 数据服务

### 1. TushareService (`backend/services/tushare_service.py`)

**功能**：
- 获取财务数据（ROE、毛利率、净利率、负债率、现金流等）
- 获取资金流向数据（板块、行业）
- 获取概念板块数据

**主要方法**：
- `get_financial_data(stock_code)`: 获取单只股票的财务数据
- `batch_get_financial_data(stock_codes, delay)`: 批量获取财务数据
- `get_sector_moneyflow(trade_date)`: 获取板块资金流向
- `get_concept_sectors(trade_date)`: 获取概念板块数据

### 2. MoneyflowService (`backend/services/moneyflow_service.py`)

**功能**：
- 封装资金流向数据获取逻辑
- 用于月度热点统计

**主要方法**：
- `get_sector_moneyflow(trade_date)`: 获取板块资金流向
- `get_industry_moneyflow(trade_date)`: 获取行业资金流向
- `get_concept_performance(trade_date)`: 获取概念板块表现

## 数据获取策略

### 财务数据

**优先级**：
1. **Tushare Pro**（优先）：更稳定，数据更完整
2. **akshare**（备选）：如果 Tushare 失败，fallback 到 akshare

**更新频率**：
- 闭市后异步更新（每天一次）
- 每次更新前200只股票（避免请求过多）

**数据存储**：
- 保存到 `data_warehouse/financial/YYYY-MM-DD.json`

### 资金流向数据

**数据源**：Tushare Pro

**更新频率**：
- 闭市后异步更新（每天一次）
- 用于月度热点统计

**数据存储**：
- 保存到 `data_warehouse/moneyflow/YYYY-MM-DD.json`
- 包含：
  - `sector_moneyflow`: 板块资金流向
  - `industry_moneyflow`: 行业资金流向
  - `concept_performance`: 概念板块表现

## 数据仓库结构

```
data_warehouse/
├── stocks/          # 股票行情数据（CSV）
│   └── YYYY-MM-DD.csv
├── financial/       # 财务数据（JSON）
│   └── YYYY-MM-DD.json
└── moneyflow/      # 资金流向数据（JSON）
    └── YYYY-MM-DD.json
```

## 使用场景

### 1. 达尔文公司筛选

**数据需求**：
- ROE（TTM）
- 毛利率、净利率
- 负债率
- 经营现金流
- 盈利波动率

**数据来源**：Tushare Pro（优先）→ akshare（备选）

**使用位置**：
- `backend/services/darwin_scorer.py`
- `backend/strategy/darwin.py`

### 2. 月度热点统计

**数据需求**：
- 板块资金流向
- 行业资金流向
- 概念板块表现

**数据来源**：Tushare Pro

**使用位置**：
- `backend/services/moneyflow_service.py`
- `backend/strategy/monthly_theme.py`

## 数据更新流程

### 自动更新（DataScheduler）

1. **交易时间**：
   - 每10分钟更新股票行情数据（优先 easyquotation，包含换手率）

2. **闭市时间**：
   - 更新收盘数据
   - 异步更新财务数据（Tushare Pro，前200只股票）
   - 异步更新资金流向数据（Tushare Pro，用于月度热点统计）

### 手动更新

可以通过 API 手动触发更新：
- 财务数据：调用 `DataScheduler.update_financial_data()`
- 资金流向：调用 `DataScheduler.update_moneyflow_data()`

## 注意事项

1. **请求频率限制**：
   - Tushare Pro 有请求频率限制
   - 批量获取时已添加延迟（默认0.2秒）

2. **数据格式**：
   - Tushare 返回的财务指标可能是百分比或小数
   - 代码中已自动判断并转换

3. **容错机制**：
   - 如果 Tushare 失败，自动 fallback 到 akshare
   - 如果都失败，返回默认值（避免系统崩溃）

4. **数据存储**：
   - 所有数据都保存到数据仓库
   - 避免频繁调用外部 API

## 安装依赖

```bash
pip install tushare
```

## 参考文档

- [Tushare Pro 官方文档](https://tushare.pro/document/2)
- [Tushare Pro API 接口](https://tushare.pro/document/2?doc_id=109)

