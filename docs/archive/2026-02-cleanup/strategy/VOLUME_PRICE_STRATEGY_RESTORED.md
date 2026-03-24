# 量价策略详细说明（已恢复）

## 恢复日期
2025-11-24

## 恢复内容

从React版本（`frontend/src/components/ShortTermStrategyPanel.jsx`）恢复了完整的12种量价形态详细说明。

## 12种量价形态详细说明

### 1. 量增价升 ✅ 买入
- **描述**: 成交量持续增加，股价趋势转为上升，多头主动进攻，是短中线最佳买入信号。
- **操作建议**: 买入
- **示例**: 在回调不破5日线时，可以小仓试探性买入。
- **颜色标识**: positive (绿色)

### 2. 量增价平 ⚪ 持有
- **描述**: 放量但股价基本持平，说明有资金博弈，关注后续方向选择。
- **操作建议**: 持有
- **示例**: 可持有观察，等待明确信号。
- **颜色标识**: neutral (灰色)

### 3. 量增价跌 ❌ 减仓/卖出
- **描述**: 高位放量下跌，获利盘集中出逃，是明显的卖出信号。
- **操作建议**: 减仓/卖出
- **示例**: 建议减仓或止损，避免深度回调。
- **颜色标识**: negative (红色)

### 4. 量缩价涨 ⚠️ 持有
- **描述**: 量缩价涨，多出现于上升末期或控盘阶段，暂可持有，警惕后续放量出货。
- **操作建议**: 持有
- **示例**: 如出现放量下跌需及时止盈。
- **颜色标识**: warning (黄色)

### 5. 量缩价跌 ⚪ 观望
- **描述**: 缩量下跌，空头动能有限，以观望为主，等待新的放量方向。
- **操作建议**: 观望
- **示例**: 可关注是否出现地量地价信号。
- **颜色标识**: neutral (灰色)

### 6. 量平价升 ✅ 买入
- **描述**: 等量温和上涨，趋势健康，可在回调时适量参与。
- **操作建议**: 买入
- **示例**: 适合波段操作，注意止盈。
- **颜色标识**: positive (绿色)

### 7. 量平价跌 ⚪ 观望
- **描述**: 等量下跌，说明抛压和承接力量相当，以观察为主。
- **操作建议**: 观望
- **示例**: 等待明确方向后再操作。
- **颜色标识**: neutral (灰色)

### 8. 无量价升 ⚠️ 观望
- **描述**: 无量上涨，可能是技术性反弹或控盘拉升，需谨慎。
- **操作建议**: 观望
- **示例**: 等待放量确认后再考虑介入。
- **颜色标识**: warning (黄色)

### 9. 无量价平 ⚪ 观望
- **描述**: 无量横盘，市场观望情绪浓厚，可等待突破方向。
- **操作建议**: 观望
- **示例**: 突破时需配合放量确认。
- **颜色标识**: neutral (灰色)

### 10. 无量价跌 ⚪ 观望
- **描述**: 无量下跌，可能是技术性调整，空头动能不足。
- **操作建议**: 观望
- **示例**: 可关注是否出现地量地价信号。
- **颜色标识**: neutral (灰色)

### 11. 天量天价 ❌ 减仓/卖出
- **描述**: 成交量和股价双创阶段新高，高位放量，警惕见顶风险。
- **操作建议**: 减仓/卖出
- **示例**: 建议逐步减仓，避免追高。
- **颜色标识**: negative (红色)

### 12. 地量地价 ℹ️ 观望
- **描述**: 成交量和股价双创阶段新低，底部放量后有望反弹，可小仓关注。
- **操作建议**: 观望
- **示例**: 等待放量确认后再介入。
- **颜色标识**: info (蓝色)

## 代码更新

### 1. 后端策略模块 (`backend/strategy/volume_price.py`)
- ✅ 添加了 `VOLUME_PRICE_PATTERNS_DETAIL` 字典，包含所有12种形态的详细说明
- ✅ 添加了 `get_volume_price_pattern_info()` 函数，获取单个形态的详细信息
- ✅ 添加了 `get_all_volume_price_patterns()` 函数，获取所有形态的详细信息列表

### 2. 策略模块导出 (`backend/strategy/__init__.py`)
- ✅ 导出了新增的函数和常量

### 3. 策略引擎API (`backend/api/engines.py`)
- ✅ 更新了量价关系模型的说明
- ✅ 添加了 `patterns` 字段，包含所有12种形态的详细说明
- ✅ 更新了示例，包含更详细的描述、示例和颜色标识

## API使用

### 获取所有量价形态信息
```python
from backend.strategy.volume_price import get_all_volume_price_patterns

patterns = get_all_volume_price_patterns()
# 返回包含所有12种形态详细信息的列表
```

### 获取单个形态信息
```python
from backend.strategy.volume_price import get_volume_price_pattern_info

info = get_volume_price_pattern_info("量增价升")
# 返回: {
#   "description": "成交量持续增加，股价趋势转为上升...",
#   "advice": "买入",
#   "example": "在回调不破5日线时，可以小仓试探性买入。",
#   "color": "positive"
# }
```

### API端点
```
GET /api/engines
```
返回包含所有策略引擎说明的JSON，其中量价关系模型包含完整的12种形态详细说明。

## 前端集成

Vue前端可以通过以下方式使用：

1. **调用API获取策略引擎说明**
   ```javascript
   const response = await fetch('/api/engines');
   const data = await response.json();
   const volumePriceEngine = data.engines.find(e => e.name === '量价关系模型');
   const patterns = volumePriceEngine.patterns; // 12种形态的详细说明
   ```

2. **直接使用后端函数**（如果前端有Python环境）
   ```python
   from backend.strategy.volume_price import get_all_volume_price_patterns
   ```

## 数据来源

- **原始数据**: `frontend/src/components/ShortTermStrategyPanel.jsx`
- **恢复日期**: 2025-11-24
- **恢复原因**: 策略引擎内容比之前的版本少了，需要从React版本找回

