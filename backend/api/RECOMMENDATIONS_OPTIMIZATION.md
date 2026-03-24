# recommendations.py 优化方案

## 发现的优化点

### 1. 大量重复代码（严重）

#### 问题描述
- **短线推荐和波段推荐逻辑重复**（89-329行 vs 331-494行）
  - 数据转换逻辑完全相同
  - 获取实时数据、K线数据、板块热度的逻辑重复
  - 精炼逻辑结构相同，只是调用的方法不同

- **`get_recommendations_short` 和 `get_recommendations_swing` 重复**（1268-1429行 vs 1432-1657行）
  - 几乎完全相同的代码结构
  - 只有精炼方法调用不同（`refine_short_candidates` vs `refine_swing_candidates`）

#### 优化建议
提取公共函数：
```python
# 提取到 recommendation_helpers.py
def convert_recommendations_to_stock_data(
    recommendations: List[Dict],
    realtime_map: Dict
) -> Tuple[List[StockData], Dict]:
    """将推荐结果转换为StockData列表"""
    pass

def build_kline_map(
    candidate_codes: List[str],
    market_service,
    days: int = 120,
    max_codes: int = 50
) -> Dict:
    """构建K线映射"""
    pass

def build_sector_and_leaders_map(
    candidates: List[StockData],
    filter_service,
    window_id: str = 'current_rolling_30d'
) -> Tuple[Dict, Dict]:
    """构建板块热度和龙头映射"""
    pass

def refine_recommendations(
    recommendation_type: str,  # 'short' or 'swing'
    candidates: List[StockData],
    kline_map: Dict,
    sector_map: Dict,
    leaders_map: Dict,
    limit: int,
    filter_service
) -> List[Dict]:
    """统一的精炼逻辑"""
    pass
```

---

### 2. 魔法值和硬编码（中等）

#### 问题描述
- `limit * 2` 在多处使用（获取更多候选用于精炼）
- `'current_rolling_30d'` 硬编码在多处
- `days=120, max_codes=50` 硬编码在多处

#### 优化建议
提取为配置常量：
```python
# 在文件顶部定义
class RecommendationConfig:
    """推荐配置常量"""
    CANDIDATE_MULTIPLIER = 2  # 候选数量倍数
    DEFAULT_WINDOW_ID = 'current_rolling_30d'
    DEFAULT_KLINE_DAYS = 120
    DEFAULT_MAX_CODES = 50
    FALLBACK_KLINE_DAYS = 60
```

---

### 3. 函数过长（中等）

#### 问题描述
- `get_recommendations` 函数有 **500+ 行**
- `get_recommendations_short` 函数有 **160+ 行**
- `get_recommendations_swing` 函数有 **220+ 行**
- 嵌套层级过深（最多5-6层）

#### 优化建议
拆分函数：
```python
# 将 get_recommendations 拆分为：
async def get_recommendations(...) -> Dict:
    """主入口，协调各个子函数"""
    pass

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

### 4. 性能问题（中等）

#### 问题描述
- **多次调用 `get_realtime_stocks`**（129行、360行、1468行等）
  - 可以缓存结果，避免重复调用
- **多次查询数据库**（获取板块热度、龙头数据等）
  - 可以批量查询

#### 优化建议
```python
# 添加缓存机制
_realtime_data_cache = {}
_realtime_data_cache_time = None
CACHE_TTL = 60  # 缓存60秒

def get_realtime_data_cached(force_refresh: bool = False):
    """获取实时数据（带缓存）"""
    global _realtime_data_cache, _realtime_data_cache_time
    
    now = datetime.now()
    if (not force_refresh and 
        _realtime_data_cache_time and 
        (now - _realtime_data_cache_time).seconds < CACHE_TTL):
        return _realtime_data_cache
    
    market_service = get_service_manager().get_market_data_service()
    data = market_service.get_realtime_stocks(force_refresh=False, use_warehouse=True)
    _realtime_data_cache = data
    _realtime_data_cache_time = now
    return data
```

---

### 5. 代码转换逻辑重复（轻微）

#### 问题描述
- 股票代码转换逻辑在多处重复：
  - `code.split('.')[0] if '.' in code else code`
  - `str(code).replace('sh', '').replace('sz', '').replace('bj', '').strip()`

#### 优化建议
使用已有的 `clean_stock_code` 函数（已在 `recommendation_helpers.py` 中）

---

### 6. 错误处理不一致（轻微）

#### 问题描述
- 有些地方使用 `logger.warning`，有些使用 `logger.error`
- 有些地方返回空列表，有些抛出异常

#### 优化建议
统一错误处理策略：
```python
def handle_recommendation_error(
    error: Exception,
    recommendation_type: str,
    fallback_value: Any = None
) -> Any:
    """统一的错误处理"""
    logger.error(f"❌ 获取{recommendation_type}推荐失败: {error}", exc_info=True)
    if fallback_value is not None:
        logger.warning(f"⚠️ 使用降级值: {fallback_value}")
        return fallback_value
    raise HTTPException(status_code=500, detail=f"获取{recommendation_type}推荐失败: {str(error)}")
```

---

## 优化优先级

### 高优先级（立即优化）
1. ✅ **提取重复的精炼逻辑**（短线/波段）
2. ✅ **提取数据转换函数**
3. ✅ **提取K线映射构建函数**

### 中优先级（近期优化）
4. ⚠️ **提取配置常量**
5. ⚠️ **拆分超长函数**
6. ⚠️ **添加实时数据缓存**

### 低优先级（可选优化）
7. 📝 **统一错误处理**
8. 📝 **优化代码转换逻辑**

---

## 预期效果

| 优化项 | 优化前 | 优化后 | 改善 |
|--------|--------|--------|------|
| 代码行数 | 1662行 | ~1200行 | ⬇️ 28% |
| 重复代码 | 大量 | 少量 | ⬇️ 80% |
| 函数平均长度 | 200+行 | 50-100行 | ⬇️ 50% |
| 嵌套层级 | 5-6层 | 2-3层 | ⬇️ 50% |
| 实时数据调用 | 多次 | 1次（缓存） | ⬇️ 70% |

---

## 实施步骤

1. **第一步**：提取公共函数到 `recommendation_helpers.py`
2. **第二步**：重构 `get_recommendations`，使用提取的函数
3. **第三步**：重构 `get_recommendations_short` 和 `get_recommendations_swing`
4. **第四步**：添加配置常量和缓存机制
5. **第五步**：统一错误处理

---

## 注意事项

- ⚠️ 保持API接口签名不变（向后兼容）
- ⚠️ 保持返回数据格式不变
- ⚠️ 充分测试，确保功能不受影响
- ⚠️ 逐步重构，不要一次性改动太多

