# recommendations.py 结构优化方案

## 方法大小分析

### 发现的问题

| 函数名 | 行数 | 状态 | 问题 |
|--------|------|------|------|
| `get_recommendations` | **432行** | 🔴 严重 | 包含4种推荐类型的处理逻辑，职责过多 |
| `_merge_and_score` | **261行** | 🟡 较大 | 包含4个策略的融合逻辑，代码重复 |
| `get_recommendations_swing` | **179行** | 🟡 较大 | 包含精炼和格式转换逻辑 |
| `get_recommendations_short` | **160行** | 🟡 较大 | 包含精炼和格式转换逻辑 |

### 建议的函数长度标准
- ✅ **理想**: 20-50行
- ⚠️ **可接受**: 50-100行
- 🔴 **需要拆分**: >100行

---

## 优化方案

### 1. 拆分 `get_recommendations` 函数（432行 → 多个小函数）

#### 当前结构
```python
async def get_recommendations(...) -> Dict:
    # 初始化 (77-87行)
    # 短线推荐处理 (98-254行) - 156行
    # 波段推荐处理 (256-372行) - 116行
    # 长期推荐处理 (374-381行) - 7行
    # 新高回踩推荐处理 (383-481行) - 98行
    # 返回结果 (483行)
```

#### 优化后结构
```python
async def get_recommendations(...) -> Dict:
    """主入口，协调各个子函数"""
    result = _init_result(date)
    
    if type == "short" or type == "all":
        result["data"]["short"] = await _get_short_recommendations(...)
    
    if type == "swing" or type == "all":
        result["data"]["swing"] = await _get_swing_recommendations(...)
    
    if type == "long":
        result["data"]["long"] = await _get_long_recommendations(...)
    
    if type == "new_high" or type == "all":
        result["data"]["new_high"] = await _get_new_high_recommendations(...)
    
    return result

async def _get_short_recommendations(...) -> List[Dict]:
    """获取短线推荐"""
    pass

async def _get_swing_recommendations(...) -> List[Dict]:
    """获取波段推荐"""
    pass

async def _get_long_recommendations(...) -> List[Dict]:
    """获取长期推荐"""
    pass

async def _get_new_high_recommendations(...) -> List[Dict]:
    """获取新高回踩推荐"""
    pass
```

---

### 2. 拆分 `_merge_and_score` 函数（261行 → 多个小函数）

#### 当前结构
```python
def _merge_and_score(...) -> List[Dict]:
    # 辅助函数 get_sector_info (715-734行) - 20行
    # 打板策略处理 (736-781行) - 45行
    # 反转策略处理 (783-824行) - 41行
    # 波段低吸策略处理 (826-867行) - 41行
    # 新高回踩策略处理 (869-909行) - 40行
    # 排序和保存 (913-945行) - 32行
```

#### 优化后结构
```python
def _merge_and_score(...) -> List[Dict]:
    """主入口，协调各个策略融合"""
    recommendations = []
    
    # 融合各个策略
    recommendations.extend(_process_limit_up_strategy(...))
    recommendations.extend(_process_reversal_strategy(...))
    recommendations.extend(_process_pullback_strategy(...))
    recommendations.extend(_process_new_high_strategy(...))
    
    # 排序和保存
    recommendations.sort(...)
    _save_recommendations_to_db(recommendations)
    
    return recommendations[:limit]

def _process_limit_up_strategy(...) -> List[Dict]:
    """处理打板策略结果"""
    pass

def _process_reversal_strategy(...) -> List[Dict]:
    """处理反转策略结果"""
    pass

def _process_pullback_strategy(...) -> List[Dict]:
    """处理波段低吸策略结果"""
    pass

def _process_new_high_strategy(...) -> List[Dict]:
    """处理新高回踩策略结果"""
    pass

def _build_recommendation_from_stock(...) -> Dict:
    """从StockData构建推荐项（公共函数）"""
    pass
```

---

### 3. 提取公共逻辑到 `recommendation_helpers.py`

#### 需要提取的函数

1. **精炼结果转换为返回格式**
```python
def convert_refined_to_response_format(
    refined: List[Dict],
    recommendation_type: str,  # 'short' or 'swing'
    original_data_map: Dict,
    filter_service
) -> List[Dict]:
    """将精炼结果转换为API返回格式"""
    pass
```

2. **获取板块名称（统一逻辑）**
```python
def get_stock_sector_name(
    stock_code: str,
    stock_sector: str,
    filter_service,
    window_id: str = RecommendationConfig.DEFAULT_WINDOW_ID
) -> str:
    """获取股票板块名称（统一逻辑）"""
    pass
```

3. **构建推荐项（带说明文案）**
```python
def build_recommendation_with_explain(
    stock: StockData,
    item: Dict,
    original_rec: Dict,
    recommendation_type: str,  # 'short' or 'swing'
    filter_service
) -> Dict:
    """构建推荐项（包含说明文案和警告）"""
    pass
```

---

### 4. 优化 `get_recommendations_short` 和 `get_recommendations_swing`

#### 当前问题
- 仍有重复的K线映射构建逻辑（1198-1211行 vs 1357-1362行）
- 仍有重复的板块热度映射构建逻辑（1213-1232行 vs 1364-1370行）
- 仍有重复的格式转换逻辑

#### 优化方案
```python
async def get_recommendations_short(...) -> Dict:
    """获取短线推荐（简化版）"""
    result = await get_recommendations(type="short", ...)
    
    if "data" in result and "short" in result["data"]:
        short_recs = result["data"]["short"]
        if short_recs:
            # 使用统一的精炼函数
            items = await _refine_and_format_recommendations(
                short_recs, 
                recommendation_type='short',
                limit=limit
            )
        else:
            items = _format_fallback_recommendations(short_recs, limit)
    
    return {"date": ..., "items": items}

async def _refine_and_format_recommendations(
    recommendations: List[Dict],
    recommendation_type: str,
    limit: int
) -> List[Dict]:
    """统一的精炼和格式化逻辑"""
    # 1. 转换为StockData
    # 2. 获取K线、板块热度、龙头数据
    # 3. 精炼
    # 4. 转换为返回格式
    pass
```

---

## 优化优先级

### 高优先级（立即优化）
1. ✅ **拆分 `get_recommendations` 函数**（432行 → 4个小函数）
2. ✅ **拆分 `_merge_and_score` 函数**（261行 → 4个小函数）
3. ✅ **提取公共的格式转换逻辑**

### 中优先级（近期优化）
4. ⚠️ **统一 `get_recommendations_short` 和 `get_recommendations_swing`**
5. ⚠️ **提取板块名称获取逻辑**

---

## 预期效果

| 优化项 | 优化前 | 优化后 | 改善 |
|--------|--------|--------|------|
| `get_recommendations` | 432行 | ~50行（主函数）+ 4个~80行函数 | ⬇️ 60% |
| `_merge_and_score` | 261行 | ~30行（主函数）+ 4个~40行函数 | ⬇️ 50% |
| `get_recommendations_short` | 160行 | ~40行 | ⬇️ 75% |
| `get_recommendations_swing` | 179行 | ~40行 | ⬇️ 78% |
| 代码可读性 | 低 | 高 | ✅ 显著提升 |
| 可维护性 | 低 | 高 | ✅ 显著提升 |

---

## 实施步骤

1. **第一步**：拆分 `get_recommendations` 函数
2. **第二步**：拆分 `_merge_and_score` 函数
3. **第三步**：提取公共的格式转换逻辑到 `recommendation_helpers.py`
4. **第四步**：统一 `get_recommendations_short` 和 `get_recommendations_swing`
5. **第五步**：测试验证

---

## 注意事项

- ⚠️ 保持API接口签名不变（向后兼容）
- ⚠️ 保持返回数据格式不变
- ⚠️ 充分测试，确保功能不受影响
- ⚠️ 逐步重构，不要一次性改动太多

