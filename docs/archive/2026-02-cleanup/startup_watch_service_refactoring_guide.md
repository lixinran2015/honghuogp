# 股票启动监控服务结构优化指南

## 优化概述

对 `backend/services/monitor/startup_watch_service.py` 进行了结构优化，主要改进包括：

## 1. 常量提取

### 问题
- 硬编码的魔法数字和字符串分散在代码中
- 难以维护和修改

### 优化
```python
# 监控配置
CHECK_INTERVAL_MINUTES = 5
SLOW_CHECK_THRESHOLD_SECONDS = 3
SLOW_DATA_FETCH_THRESHOLD_SECONDS = 2
PROGRESS_LOG_INTERVAL = 10

# 特殊关注的股票（用于调试）
DEBUG_STOCKS = ['002837.SZ']  # 英维克

# 核心条件名称
CORE_CONDITIONS = {
    'breakthrough_90d': '突破90日高点',
    'volume_amplified': '量能放大(量比≥1.5)',
    'bullish_alignment': '均线多头排列(5>10>20>60)'
}

# 高级阶段（已启动，不需要监控）
ADVANCED_STAGES = ['confirmed', 'started']
```

### 好处
- 集中管理配置，易于修改
- 提高代码可读性
- 避免硬编码错误

## 2. 方法职责优化

### 问题
- `check_watch_list` 方法过长（100+行）
- `_check_single_candidate` 方法过长（350+行），职责不清

### 优化建议（已部分实现）

#### 2.1 提取统计和日志方法
```python
def _log_candidates_statistics(self, candidates: List):
    """记录候选股票统计信息"""
    # 统计逻辑
    
def _log_debug_stocks(self, candidates: List):
    """记录调试股票的详细信息"""
    # 调试股票日志逻辑
```

#### 2.2 提取数据获取方法
```python
def _fetch_stock_data(self, candidate, log_level) -> Optional[Dict]:
    """获取股票数据"""
    # 数据获取逻辑
```

#### 2.3 提取条件检查方法
```python
def _check_missing_conditions(self, candidate, stock_data, missing_conditions, ...):
    """检查缺少的条件"""
    # 只检查缺少条件的逻辑
    
def _check_all_conditions(self, candidate, stock_data, ...):
    """重新检查所有核心条件"""
    # 检查所有条件的逻辑
```

#### 2.4 提取记录保存方法
```python
def _save_startup_record(self, candidate, stock_data, stage, score, signals, session, log_level):
    """保存启动记录到数据库"""
    # 保存记录逻辑
    
def _update_existing_record(self, existing, stage, score, signals, ...):
    """更新现有记录"""
    # 更新逻辑
    
def _create_new_record(self, candidate, stock_data, trade_date, ...):
    """创建新记录"""
    # 创建逻辑
```

#### 2.5 提取状态评估方法
```python
def _evaluate_startup_status(self, stock_data: Dict) -> Tuple[str, int, List[str]]:
    """评估启动状态（检查辅助和风险条件，计算阶段和得分）"""
    # 评估逻辑
```

#### 2.6 提取移除监控方法
```python
def _remove_from_watching(self, ts_code: str, session, reason: str = ""):
    """从监控池移除股票（清除所有历史记录的 is_watching 标记）"""
    # 移除逻辑（消除重复代码）
```

## 3. 重复代码消除

### 问题
- 清除历史记录的逻辑在多处重复（3处）
- 检查 confirmed/started 状态的逻辑重复

### 优化
- 提取 `_remove_from_watching` 方法
- 提取 `_is_advanced_stage` 方法
- 统一使用 `ADVANCED_STAGES` 常量

## 4. 代码可读性提升

### 4.1 变量命名
- `is_yingweike` → `is_debug`（更通用）
- 使用常量替代硬编码字符串

### 4.2 方法拆分
- 将大方法拆分为职责单一的小方法
- 每个方法只做一件事

### 4.3 日志优化
- 统一日志级别控制
- 提取日志方法

## 5. 进一步优化建议

### 5.1 完全重构 `_check_single_candidate` 方法

当前方法仍然过长，建议拆分为：

```python
def _check_single_candidate(self, candidate, session) -> bool:
    """检查单只待监控股票（主流程）"""
    is_debug = candidate.ts_code in DEBUG_STOCKS
    log_level = logger.info if is_debug else logger.debug
    
    try:
        # 1. 获取股票数据
        stock_data = self._fetch_stock_data(candidate, log_level)
        if not stock_data:
            return False
        
        # 2. 检查是否已是高级阶段
        if self._is_advanced_stage(candidate, session, log_level):
            return False
        
        # 3. 根据 missing_conditions 决定检查策略
        missing_conditions = candidate.missing_conditions or []
        
        if missing_conditions:
            return self._check_missing_conditions(candidate, stock_data, missing_conditions, session, log_level, is_debug)
        else:
            return self._check_all_conditions(candidate, stock_data, session, log_level, is_debug)
            
    except Exception as e:
        logger.error(f"检查股票 {candidate.ts_code} 失败: {e}", exc_info=True)
        return False
```

### 5.2 提取条件检查器

可以考虑创建一个专门的条件检查器类：

```python
class CandidateConditionChecker:
    """候选股票条件检查器"""
    
    def __init__(self, warehouse_service):
        self.ws = warehouse_service
    
    def check_single_condition(self, condition_name: str, stock_data: Dict) -> bool:
        """检查单个核心条件"""
        # ...
    
    def check_missing_conditions(self, candidate, stock_data, missing_conditions):
        """检查缺少的条件"""
        # ...
    
    def check_all_conditions(self, candidate, stock_data):
        """检查所有条件"""
        # ...
```

### 5.3 提取记录管理器

```python
class StartupRecordManager:
    """启动记录管理器"""
    
    def save_startup_record(self, candidate, stock_data, stage, score, signals, session):
        """保存启动记录"""
        # ...
    
    def update_existing_record(self, existing, stage, score, signals, ...):
        """更新现有记录"""
        # ...
    
    def create_new_record(self, candidate, stock_data, trade_date, ...):
        """创建新记录"""
        # ...
```

## 6. 测试建议

优化后应添加单元测试：

1. **常量测试**：验证常量值是否正确
2. **方法测试**：测试每个提取出来的小方法
3. **集成测试**：测试完整的检查流程
4. **边界测试**：测试各种边界情况

## 7. 性能优化建议

1. **批量操作**：考虑批量更新数据库记录
2. **缓存**：对频繁查询的数据进行缓存
3. **异步处理**：对于耗时的操作考虑异步处理

## 8. 总结

### 已完成的优化
- ✅ 提取常量定义
- ✅ 统一使用常量替代硬编码
- ✅ 提取 `_log_debug_stocks` 方法
- ✅ 提取 `_init_tts_engine` 方法
- ✅ 改进变量命名（`is_yingweike` → `is_debug`）

### 建议进一步优化
- ⚠️ 完全拆分 `_check_single_candidate` 方法
- ⚠️ 提取条件检查逻辑到独立类
- ⚠️ 提取记录管理逻辑到独立类
- ⚠️ 添加单元测试

### 优化效果
- **可维护性**：提高（常量集中管理，方法职责更清晰）
- **可读性**：提高（代码结构更清晰，命名更规范）
- **可扩展性**：提高（易于添加新功能）
- **可测试性**：提高（方法更小，更易测试）

