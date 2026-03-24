# AKShare财务数据接口测试总结

## 测试结果

### ✅ 可以获取的指标

| 指标 | 接口 | 字段/计算方式 | 状态 |
|------|------|---------------|------|
| **营收TTM** | `ak.stock_financial_report_sina(symbol='利润表')` | 最近4期"营业总收入"之和 | ✅ |
| **净利润TTM** | `ak.stock_financial_report_sina(symbol='利润表')` | 最近4期"净利润"之和 | ✅ |
| **毛利率** | `ak.stock_financial_report_sina(symbol='利润表')` | (营业收入 - 营业成本) / 营业收入 * 100 | ✅ |
| **净利率** | `ak.stock_financial_report_sina(symbol='利润表')` | 净利润 / 营业收入 * 100 | ✅ |
| **ROE TTM** | `ak.stock_financial_abstract()` | "净资产收益率(ROE)"字段，最新一期 | ✅ |
| **经营现金流TTM** | `ak.stock_financial_report_sina(symbol='现金流量表')` | 最近4期"经营活动产生的现金流量净额"之和 | ✅ |

## 接口说明

### 1. ak.stock_financial_abstract(symbol='600519')
- **返回格式**：横向（每个季度一列）
- **可获取**：ROE、营收、净利润等指标
- **TTM计算**：取最近4个季度数据求和
- **示例**：
  ```python
  df = ak.stock_financial_abstract(symbol='600519')
  # 查找"净资产收益率(ROE)"行
  # 获取最新一期的ROE值
  ```

### 2. ak.stock_financial_report_sina(stock='sh600519', symbol='利润表')
- **返回格式**：纵向（每期一行）
- **可获取**：营业总收入、营业成本、净利润
- **计算**：
  - 毛利率 = (营业收入 - 营业成本) / 营业收入 * 100
  - 净利率 = 净利润 / 营业收入 * 100
  - TTM = 最近4期数据之和
- **示例**：
  ```python
  df = ak.stock_financial_report_sina(stock='sh600519', symbol='利润表')
  # 按报告日排序，取最新一期计算毛利率和净利率
  # 取最近4期计算TTM
  ```

### 3. ak.stock_financial_report_sina(stock='sh600519', symbol='现金流量表')
- **返回格式**：纵向（每期一行）
- **可获取**：经营活动产生的现金流量净额
- **TTM计算**：最近4期数据之和
- **示例**：
  ```python
  df = ak.stock_financial_report_sina(stock='sh600519', symbol='现金流量表')
  # 查找"经营活动产生的现金流量净额"字段
  # 取最近4期求和得到TTM
  ```

## 测试数据（600519 贵州茅台）

- **营收TTM**: 447,585,172,731 元
- **净利润TTM**: 230,994,850,233 元
- **毛利率**: 91.46%
- **净利率**: 51.11%
- **ROE**: 24.64%
- **经营现金流TTM**: 152,588,751,001 元

## 脚本

已创建脚本：`backend/scripts/fill_fundamental_from_akshare.py`

### 功能
- 从S1股票池获取股票代码
- 批量补齐财务基础指标
- 更新到 `fact_daily_fundamental` 表

### 运行方式
```bash
python backend/scripts/fill_fundamental_from_akshare.py
```

### 补齐的字段
- `revenue_ttm` - 营收TTM
- `net_profit_ttm` - 净利润TTM
- `gross_margin_ttm` - 毛利率TTM
- `net_margin_ttm` - 净利率TTM
- `roe_ttm` - ROE TTM
- `op_cf_ttm` - 经营现金流TTM

## 注意事项

1. **请求频率**：脚本中已添加0.5秒延迟，避免请求过快
2. **数据格式**：需要处理百分比、数值转换等
3. **错误处理**：单个股票失败不影响整体流程
4. **数据更新**：会更新或创建 `fact_daily_fundamental` 表记录

