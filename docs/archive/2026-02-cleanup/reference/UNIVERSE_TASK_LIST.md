# 股票池过滤系统 - 任务清单

更新时间: 2025-11-19

## ✅ Phase 1: 让系统跑起来（已完成）

### 1.1 核心功能实现
- [x] 基础黑名单过滤器
- [x] S1/S2/S3策略专用股票池筛选器
- [x] 股票池数据库表和管理服务
- [x] 股票池更新脚本和API接口
- [x] 集成到推荐选股接口
- [x] 前端展示股票池统计

### 1.2 容错策略实现
- [x] 财务数据缺失 → 保留股票
- [x] 技术指标缺失 → 跳过该条件
- [x] ST/价格字段缺失 → 跳过过滤
- [x] 换手率数据为0 → 跳过过滤

### 1.3 降级过滤条件
- [x] S1: ROE 10% → 0%，毛利率 20% → 0%，PE 60 → 80
- [x] S2: 成交额 3亿 → 5000万，换手率 1.5% → 0.1%，不要求MA20
- [x] S3: 换手率 5% → 0.1%，涨幅 3% → 0%

### 1.4 配置化管理
- [x] 所有过滤条件提取到配置文件
- [x] 支持快速调整参数

---

## 📊 当前运行结果

| 股票池 | 原始 | 过滤后 | 状态 |
|--------|------|--------|------|
| **BASE** | 5165 | **1483** | ✅ |
| **S1** | 5165 | **1483** | ✅ |
| **S2** | 5165 | **1483** | ✅ |
| **S3** | 5165 | **1483** | ✅ |

**说明**: 所有股票池都能正常运行，容错策略生效。

---

## 📋 Phase 2: 补齐数据（待执行）

### 2.1 检查字段缺失情况

**任务**: 运行字段检查脚本，确认缺失情况

```bash
python backend/scripts/check_universe_fields.py
```

**需要检查的字段**:
- [ ] `is_st` - ST标识
- [ ] `close` / `currentPrice` - 价格
- [ ] `turnover_rate` - 换手率（当前全部为0）
- [ ] `change_pct` / `changePct` - 涨幅
- [ ] `ma5` / `ma10` / `ma20` / `ma60` - 均线
- [ ] `roe_ttm` / `gross_margin_ttm` / `pe_ttm` - 财务指标

---

### 2.2 补充财务数据（S1需要）

**目标**: 提升S1过滤精度

**需要字段**:
- `roe_ttm` - ROE TTM
- `gross_margin_ttm` - 毛利率TTM
- `net_margin_ttm` - 净利率TTM
- `pe_ttm` - PE TTM
- `op_cf_ttm` - 经营现金流TTM

**数据源选择**:
- [ ] **选项A**: Tushare（推荐，稳定）
- [ ] **选项B**: 东财API（免费但不稳定）
- [ ] **选项C**: 本地CSV（如果有）

**ETL任务**:
- [ ] 创建财务数据ETL脚本
- [ ] 批量获取财务数据（避免频繁调用）
- [ ] 写入 `fact_daily_fundamental` 表
- [ ] 验证数据完整性

**预计时间**: 2-4小时

---

### 2.3 计算技术指标（S2需要）

**目标**: 补充MA均线等技术指标

**需要计算的指标**:
- [ ] `ma5` = 5日均线
- [ ] `ma10` = 10日均线
- [ ] `ma20` = 20日均线
- [ ] `ma60` = 60日均线
- [ ] `slope_ma20` = (MA20_today - MA20_20_days_ago) / 20
- [ ] `price_above_ma20` = (close > ma20)
- [ ] `avg_amount_20d` = 20日均成交额

**计算方式**:
```python
# 从 fact_daily_price_qfq 读取历史数据
df['ma20'] = df['close'].rolling(20).mean()
df['slope_ma20'] = df['ma20'].diff(20) / 20
df['avg_amount_20d'] = df['amount'].rolling(20).mean()
df['price_above_ma20'] = df['close'] > df['ma20']
```

**ETL任务**:
- [ ] 创建技术指标计算脚本
- [ ] 从历史数据计算MA均线
- [ ] 写入 `fact_daily_price_qfq` 表（如果字段存在）或新建字段
- [ ] 验证计算正确性

**预计时间**: 1-2小时

---

### 2.4 补充涨停板数据（S3需要）

**目标**: 补充涨停板相关数据

**需要字段**:
- [ ] `is_today_limit_up` - 今日是否涨停
- [ ] `limit_up_days` - 连续涨停天数
- [ ] `seal_amount` - 封板金额
- [ ] `first_limit_time` - 首次涨停时间

**数据源**:
- [ ] 从东财接口获取（批量，避免频繁调用）
- [ ] 或从现有数据计算

**ETL任务**:
- [ ] 检查 `fact_limit_up_daily` 表是否存在
- [ ] 创建涨停板数据ETL脚本
- [ ] 批量获取涨停板数据
- [ ] 写入数据库
- [ ] 验证数据完整性

**预计时间**: 1-2小时

---

### 2.5 修复换手率数据为0的问题

**问题**: `turnover_rate` 字段值全部为0.00%

**可能原因**:
1. 数据是2天前的（2025-11-17）
2. 数据获取时未正确计算
3. 字段映射错误

**解决步骤**:
- [ ] 运行增量更新，获取最新数据
- [ ] 检查数据获取逻辑
- [ ] 验证换手率计算是否正确

---

## 🎯 执行顺序

### 第一步：立即执行（已完成）
1. ✅ 修正过滤逻辑，加入容错
2. ✅ 降级过滤条件
3. ✅ 配置文件化
4. ✅ 运行更新脚本，验证系统能跑起来

### 第二步：检查数据（待执行）
1. [ ] 运行字段检查脚本
2. [ ] 确认换手率数据为什么为0
3. [ ] 运行增量更新，获取最新数据

### 第三步：逐步补数据（不频繁调用外部接口）
1. [ ] 计算技术指标（从现有历史数据）
2. [ ] 补充财务数据（批量，避免频繁调用）
3. [ ] 补充涨停板数据（批量）

### 第四步：提升精度
1. [ ] 恢复原始过滤条件
2. [ ] 验证过滤效果
3. [ ] 优化过滤逻辑

---

## 📝 当前过滤条件（降级版）

### 配置文件位置
`backend/config/universe_filter_config.py`

### 快速查看
```bash
cd /Users/wuyanze/quantitative_trading
python -c "from backend.config.universe_filter_config import *; import json; print(json.dumps({'BASE': BASE_FILTER_CONFIG, 'S1': S1_FILTER_CONFIG, 'S2': S2_FILTER_CONFIG, 'S3': S3_FILTER_CONFIG}, indent=2, default=str))"
```

---

## 📚 相关文档

- [过滤条件配置](./UNIVERSE_FILTER_CONDITIONS.md) - 详细过滤条件说明
- [过滤条件分析](./UNIVERSE_FILTER_ANALYSIS.md) - 问题分析和调整建议
- [数据补齐任务](./UNIVERSE_DATA_TASKS.md) - 补数据任务清单
- [实现总结](./UNIVERSE_IMPLEMENTATION_SUMMARY.md) - 实现总结
- [股票池系统文档](./STOCK_UNIVERSE_SYSTEM.md) - 系统架构和使用说明

