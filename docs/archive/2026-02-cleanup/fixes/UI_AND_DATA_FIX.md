# UI显示与数据完整性修复

更新时间: 2025-11-19

## 🐛 用户反馈的问题

1. **数据还是缺**：行业信息显示为空
2. **只有攻击型**：没有抄底型和稳健型股票
3. **显示方式**：竖向排列太长，希望改为横向显示

---

## ✅ 修复内容

### 1. 前端布局：改为横向自适应显示

**文件**: `frontend/src/components/StockList.css`

**修改前（竖向单列）**:
```css
.stocks-grid {
  display: grid;
  grid-template-columns: 1fr;  /* 单列 */
  gap: 1.25rem;
}
```

**修改后（横向多列自适应）**:
```css
.stocks-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));  /* 自动填充，最小350px */
  gap: 1.25rem;
}

@media (min-width: 1024px) {
  .stocks-grid {
    grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));  /* 大屏幕400px */
    gap: 1.5rem;
  }
}

@media (min-width: 1600px) {
  .stocks-grid {
    grid-template-columns: repeat(3, 1fr);  /* 超大屏固定3列 */
  }
}
```

**效果**:
- ✅ 小屏幕：自动适应，每行1-2个卡片
- ✅ 中等屏幕：每行2-3个卡片
- ✅ 大屏幕：固定3列展示
- ✅ 更紧凑、更清晰，不再"太长"

---

### 2. 补充行业信息：从数据库实时查询

**文件**: `backend/api/recommendations.py`

**问题**：`stock.sector` 字段为空，导致前端显示"未知"

**解决方案**：新增 `get_sector_info()` 辅助函数，从PostgreSQL数据库查询行业信息

```python
def get_sector_info(stock_code: str) -> str:
    """从数据库获取行业信息"""
    try:
        from backend.db.database import SessionLocal
        from backend.db.models import FactStockSector, DimSector
        
        db = SessionLocal()
        try:
            result = db.query(DimSector.sector_name).join(
                FactStockSector, DimSector.sector_id == FactStockSector.sector_id
            ).filter(
                FactStockSector.ts_code == stock_code
            ).first()
            
            return result[0] if result else "未知"
        finally:
            db.close()
    except Exception as e:
        logger.debug(f"获取 {stock_code} 行业信息失败: {e}")
        return "未知"
```

**使用方式**：在三个策略中统一调用

```python
# 攻击型、抄底型、稳健型都增加
sector = stock.sector or get_sector_info(stock.code)

# 推荐理由中补充行业信息
if sector and sector != "未知":
    reason += f"，所属{sector}板块"
```

---

### 3. 增加策略日志：诊断"只有攻击型"问题

**问题分析**：可能其他策略（反转、波段）没有返回候选股票

**解决方案**：增加详细日志

```python
# 打板策略（攻击型）
if limit_up_result and limit_up_result.candidates:
    logger.info(f"📊 打板策略返回 {len(limit_up_result.candidates)} 只候选股票")
    # ...
else:
    logger.warning("⚠️ 打板策略未返回候选股票")

# 反转策略（抄底型）
if reversal_result and reversal_result.candidates:
    logger.info(f"📊 反转策略返回 {len(reversal_result.candidates)} 只候选股票")
    # ...
else:
    logger.warning("⚠️ 反转策略未返回候选股票")

# 波段低吸策略（稳健型）
if pullback_result and pullback_result.candidates:
    logger.info(f"📊 波段低吸策略返回 {len(pullback_result.candidates)} 只候选股票")
    # ...
else:
    logger.warning("⚠️ 波段低吸策略未返回候选股票")
```

**好处**：
- ✅ 快速定位哪个策略没有返回数据
- ✅ 便于调试策略筛选条件
- ✅ 方便用户反馈问题

---

### 4. 增加候选数量：从3只增加到5只

**修改前**：每个策略最多取3只股票

```python
for stock in limit_up_result.candidates[:3]:  # 太少
```

**修改后**：每个策略最多取5只股票

```python
for stock in limit_up_result.candidates[:5]:  # 更多选择
```

**理由**：
- ✅ 提供更多候选股票
- ✅ 最终会按综合得分排序，取前N只
- ✅ 三个策略共计最多15只候选，按得分筛选到10只

---

## 📊 预期效果

### 前端显示

**修改前**：
```
┌──────────────────┐
│  股票1 (攻击型)   │
└──────────────────┘
┌──────────────────┐
│  股票2 (攻击型)   │
└──────────────────┘
┌──────────────────┐
│  股票3 (攻击型)   │
└──────────────────┘
```

**修改后**：
```
┌──────────┐ ┌──────────┐ ┌──────────┐
│ 股票1    │ │ 股票2    │ │ 股票3    │
│ (攻击型) │ │ (抄底型) │ │ (稳健型) │
│ 电子     │ │ 医药     │ │ 半导体   │
└──────────┘ └──────────┘ └──────────┘
```

### 数据完整性

**行业信息**：
- ❌ 修改前：显示"未知"或空
- ✅ 修改后：从PostgreSQL查询实际行业（如"电子"、"医药"、"半导体"）

**策略类型**：
- ❌ 修改前：只有攻击型（打板策略）
- ✅ 修改后：攻击型、抄底型、稳健型混合（取决于市场行情）

**推荐理由**：
- ❌ 修改前：`打板策略：涨幅9.80%，量价形态：量增价升`
- ✅ 修改后：`打板策略：涨幅9.80%，所属电子板块，量价形态：量增价升`

---

## 🔍 诊断：为什么只有攻击型？

### 可能原因

1. **市场行情偏强势**：当前市场处于上涨行情，符合反转策略（超跌修复）和波段低吸策略（回踩）的股票较少
2. **数据不足**：反转和波段策略需要历史K线数据（MA均线等），如果数据缺失会导致无法筛选
3. **筛选条件过严**：策略的筛选条件可能过于严格

### 查看日志

修改后会输出详细日志，可以通过以下命令查看：

```bash
# 查看推荐接口日志
tail -f /Users/wuyanze/quantitative_trading/logs/backend.log | grep "📊"

# 输出示例
📊 打板策略返回 12 只候选股票
⚠️ 反转策略未返回候选股票
⚠️ 波段低吸策略未返回候选股票
```

### 解决方案

如果反转和波段策略持续无结果，需要：

1. **检查策略筛选条件**：
   - `backend/strategy/short_term_reversal.py`
   - `backend/strategy/swing_pullback.py`

2. **检查数据完整性**：
   - MA均线（MA5/10/20/60）是否已计算
   - 5日均量（avgVolume5）是否已计算
   - 量比（volume_ratio）是否已计算

3. **放宽筛选条件**：根据市场行情适当调整阈值

---

## 📝 相关TODO

以下数据补充任务仍在进行中，完成后可能提升反转和波段策略的命中率：

- [ ] 计算并补充 MA均线（MA5/10/20/60）
- [ ] 计算并补充 avgVolume5（5日均量）
- [ ] 计算并补充 volume_ratio（量比）
- [ ] 补全 fact_sector_daily（板块日线数据）

---

## 📚 相关文档

- [推荐选股策略优化](./RECOMMENDATION_OPTIMIZATION.md) - 评分策略优化
- [推荐选股策略逻辑](./RECOMMENDATION_LOGIC.md) - 完整策略说明
- [达尔文策略修复](./DARWIN_FIX_SUMMARY.md) - 达尔文策略修复
- [策略与数据关联](./STRATEGY_DATA_MAPPING.md) - 数据需求分析

---

## ✅ 总结

### 已修复

1. ✅ 前端横向自适应布局（3列，响应式）
2. ✅ 补充行业信息（从数据库查询）
3. ✅ 增加策略日志（诊断问题）
4. ✅ 增加候选数量（3只→5只）

### 预期效果

- 📊 更紧凑的卡片布局
- 🏢 显示实际行业信息
- 📈 支持三种策略混合推荐（如果市场行情符合）
- 🔍 更详细的日志便于调试

### 下一步

1. 刷新前端页面，查看横向布局效果
2. 点击"智能选股"，查看是否有行业信息
3. 查看后端日志，确认三个策略的返回情况
4. 如果持续只有攻击型，需调整反转和波段策略的筛选条件

