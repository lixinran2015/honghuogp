# 股票筛选逻辑说明

## 1. complete_data_warehouse.py 的筛选逻辑

### 目标
补全500只股票的财务数据（ROE、净利率、负债率、毛利率、经营现金流）

### 筛选依据
```python
# 从dim_stock表获取A股代码
stocks = session.query(DimStock).filter(
    DimStock.exchange.in_(['SSE', 'SZSE'])  # 只选择沪深A股
).limit(limit).all()  # limit=500

stock_codes = [stock.symbol for stock in stocks if stock.symbol.isdigit() and len(stock.symbol) == 6]
```

### 实际处理情况
- **设置limit**: 500只股票
- **实际处理**: 240只股票（已完成8批，每批30只）
- **原因**: 脚本可能因为某些原因提前结束，或者limit设置没有完全生效

### 当前状态
- `fact_fundamental`表中有**302只股票**的财务数据（2025-11-17）
- 说明补全脚本可能还在继续运行，或者有其他脚本也在补全数据

---

## 2. enhance_financial_data.py 的筛选逻辑

### 目标
专门补全毛利率和经营现金流数据

### 筛选依据
```sql
SELECT DISTINCT ts_code
FROM fact_fundamental
WHERE end_date = '2025-11-17'
AND (gross_margin IS NULL OR gross_margin = 0 OR op_cf IS NULL OR op_cf = 0)
LIMIT 500
```

### 筛选条件
- **已有财务数据**：从`fact_fundamental`表中选择
- **缺少毛利率或经营现金流**：`gross_margin IS NULL OR gross_margin = 0 OR op_cf IS NULL OR op_cf = 0`
- **限制数量**：最多500只股票

### 当前状态
- 找到**302只股票**需要补全毛利率或经营现金流
- 说明所有302只股票的财务数据都缺少这两个指标

---

## 3. 数据完整性分析

### fact_fundamental表（2025-11-17）
- **总股票数**: 302只
- **缺少毛利率**: 302只（100%）
- **缺少经营现金流**: 302只（100%）
- **有负债率数据**: 226只（75%）
- **有ROE数据**: 约95%

### 问题分析
1. **毛利率数据缺失**：
   - `stock_financial_abstract_ths`接口不提供毛利率
   - `stock_financial_analysis_indicator_em`接口可能也没有
   - 需要从利润表计算：毛利率 = (营业收入 - 营业成本) / 营业收入

2. **经营现金流数据缺失**：
   - `stock_financial_cash_ths`接口可能返回空数据
   - 字段名可能不匹配
   - 需要尝试多个接口和字段名

---

## 4. 优化方案

### 已实施的优化
1. ✅ **毛利率获取**：
   - 方法1: 从`stock_financial_analysis_indicator_em`获取
   - 方法2: 从利润表计算（`stock_financial_income_ths`）
   - 方法3: 从`stock_profit_forecast_ths`获取

2. ✅ **经营现金流获取**：
   - 方法1: 从`stock_financial_cash_ths`获取（尝试多个字段名）
   - 方法2: 从`stock_cash_flow_sheet_by_report_em`获取

### 进度输出优化
- ✅ 每只股票都输出详细进度
- ✅ 显示是否获取到毛利率和经营现金流
- ✅ 显示ROE等关键指标

---

## 5. 建议

### 短期方案
1. 等待`enhance_financial_data.py`脚本完成（302只股票，预计30-60分钟）
2. 检查优化后的获取逻辑是否生效
3. 如果仍然获取不到，需要进一步调试接口调用

### 长期方案
1. 考虑使用Tushare Pro（如果有权限）
2. 考虑从其他数据源获取（如Wind、Choice等）
3. 建立数据质量监控机制

