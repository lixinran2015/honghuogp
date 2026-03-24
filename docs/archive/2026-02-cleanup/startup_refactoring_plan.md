# 股票启动监控系统重构方案

## 📊 当前代码结构分析

### 问题识别

1. **`stock_startup_filter.py` (1004行) - 职责过多**
   - 数据获取：`_get_stock_indicators()`
   - 指标计算：`_calculate_indicators()`
   - 条件检查：`_check_basic_conditions()`, `_check_core_conditions()`, `_check_assist_conditions()`, `_check_risk_conditions()`
   - 状态保存：`_save_candidate_stock()`
   - 批量处理：`batch_filter_startups()`
   - 主流程：`is_just_started()`

2. **`stock_startup.py` (1330行) - API层过于庞大**
   - 查询接口：`get_startup_candidates()`
   - 扫描接口：`scan_startup_stocks()`
   - 诊断接口：`diagnose_stock()`, `batch_diagnose_golden_cross_candidates()`
   - 辅助函数：`_clean_nan_values()`, `to_native()`

3. **代码耦合度高**
   - 数据获取、计算、检查、保存混在一起
   - 难以单独测试和维护
   - 代码复用性差

---

## 🎯 重构目标

1. **职责分离**：每个类/模块只负责一个明确的功能
2. **代码复用**：提取公共逻辑，避免重复代码
3. **易于测试**：每个组件可以独立测试
4. **易于维护**：代码结构清晰，修改影响范围小
5. **性能优化**：优化数据获取和计算逻辑

---

## 📁 重构后的代码结构

```
backend/services/stock/startup/
├── __init__.py
├── data/
│   ├── __init__.py
│   ├── stock_data_loader.py      # 股票数据加载器
│   └── indicator_calculator.py   # 指标计算器
├── conditions/
│   ├── __init__.py
│   ├── basic_condition_checker.py    # 基础条件检查器
│   ├── core_condition_checker.py     # 核心条件检查器
│   ├── assist_condition_checker.py   # 辅助条件检查器
│   └── risk_condition_checker.py     # 风险条件检查器
├── state/
│   ├── __init__.py
│   ├── state_manager.py          # 状态管理器（整合状态机）
│   └── candidate_repository.py   # 候选股票仓储（数据保存）
├── filter/
│   ├── __init__.py
│   └── startup_filter.py         # 启动筛选器（主流程编排）
└── batch/
    ├── __init__.py
    └── batch_processor.py        # 批量处理器

backend/api/startup/
├── __init__.py
├── candidates.py                 # 候选股票查询API
├── scan.py                       # 扫描API
├── diagnose.py                   # 诊断API
└── common.py                     # 公共辅助函数
```

---

## 🔧 详细重构方案

### 1. 数据层 (`data/`)

#### `stock_data_loader.py`
**职责**：负责从数据库加载股票数据
```python
class StockDataLoader:
    def load_stock_data(self, ts_code: str, trade_date: str) -> Dict:
        """加载单只股票的完整数据"""
    
    def load_kline_data(self, ts_code: str, trade_date: str, days: int = 100) -> pd.DataFrame:
        """加载K线数据"""
    
    def load_stock_info(self, ts_code: str) -> DimStock:
        """加载股票基本信息"""
```

#### `indicator_calculator.py`
**职责**：负责计算技术指标
```python
class IndicatorCalculator:
    def calculate_all(self, kline_df: pd.DataFrame, stock_info) -> Dict:
        """计算所有技术指标"""
    
    def calculate_ma(self, kline_df: pd.DataFrame) -> Dict:
        """计算均线"""
    
    def calculate_macd(self, kline_df: pd.DataFrame) -> Dict:
        """计算MACD"""
    
    def calculate_kdj(self, kline_df: pd.DataFrame) -> Dict:
        """计算KDJ"""
    
    def calculate_rsi(self, kline_df: pd.DataFrame) -> Dict:
        """计算RSI"""
```

### 2. 条件检查层 (`conditions/`)

#### `basic_condition_checker.py`
**职责**：检查基础条件
```python
class BasicConditionChecker:
    def check(self, stock_data: Dict) -> Dict:
        """检查基础条件（流通市值、成交额、股价、金叉）"""
        return {
            'passed': bool,
            'passed_signals': List[str],
            'failed_reasons': List[str]
        }
```

#### `core_condition_checker.py`
**职责**：检查核心条件
```python
class CoreConditionChecker:
    def check(self, stock_data: Dict) -> Dict:
        """检查核心条件（突破60日高点、量能放大、均线多头排列）"""
        return {
            'passed': bool,
            'passed_signals': List[str],
            'failed_reasons': List[str],
            'passed_count': int  # 满足的条件数量（用于2/3判断）
        }
```

#### `assist_condition_checker.py`
**职责**：检查辅助条件
```python
class AssistConditionChecker:
    def check(self, stock_data: Dict) -> Dict:
        """检查辅助条件（MACD、KDJ、RSI、资金流入、板块热度）"""
        return {
            'count': int,
            'passed_signals': List[str]
        }
```

#### `risk_condition_checker.py`
**职责**：检查风险条件
```python
class RiskConditionChecker:
    def check(self, stock_data: Dict) -> Dict:
        """检查风险条件（过度上涨、偏离均线、量能萎缩、超买）"""
        return {
            'passed': bool,
            'risks': List[str]
        }
```

### 3. 状态管理层 (`state/`)

#### `state_manager.py`
**职责**：管理状态流转（整合状态机）
```python
class StartupStateManager:
    def __init__(self, state_machine: StartupStateMachine):
        self.state_machine = state_machine
    
    def determine_state(self, checks: Dict) -> Dict:
        """根据检查结果确定状态"""
        return {
            'stage': str,
            'score': int,
            'is_started': bool,
            'stage_info': Dict
        }
    
    def can_transition(self, from_stage: str, to_stage: str) -> bool:
        """检查是否可以转换状态"""
```

#### `candidate_repository.py`
**职责**：候选股票数据持久化
```python
class CandidateRepository:
    def save(self, stock_data: Dict, result: Dict, trade_date: str) -> FactStockStartupCandidate:
        """保存候选股票"""
    
    def find_by_code_and_date(self, ts_code: str, trade_date: str) -> Optional[FactStockStartupCandidate]:
        """根据代码和日期查找"""
    
    def find_golden_cross_candidates(self, days: int = 5) -> List[FactStockStartupCandidate]:
        """查找金叉候选股票"""
```

### 4. 筛选器层 (`filter/`)

#### `startup_filter.py`
**职责**：主流程编排（简化版）
```python
class StartupFilter:
    def __init__(
        self,
        data_loader: StockDataLoader,
        indicator_calculator: IndicatorCalculator,
        basic_checker: BasicConditionChecker,
        core_checker: CoreConditionChecker,
        assist_checker: AssistConditionChecker,
        risk_checker: RiskConditionChecker,
        state_manager: StartupStateManager,
        repository: CandidateRepository
    ):
        # 依赖注入
    
    def is_just_started(self, stock_data: Dict, trade_date: str) -> Dict:
        """判断股票是否启动（主流程）"""
        # 1. 加载数据（如果stock_data不完整）
        # 2. 计算指标（如果缺少）
        # 3. 检查条件
        # 4. 确定状态
        # 5. 保存结果
        # 6. 返回结果
```

### 5. 批量处理层 (`batch/`)

#### `batch_processor.py`
**职责**：批量处理股票
```python
class BatchProcessor:
    def __init__(self, startup_filter: StartupFilter):
        self.filter = startup_filter
    
    def process_batch(self, stock_codes: List[str], trade_date: str) -> pd.DataFrame:
        """批量处理股票列表"""
    
    def process_universe(self, universe: str, trade_date: str) -> pd.DataFrame:
        """处理股票池"""
```

### 6. API层重构

#### `candidates.py`
**职责**：候选股票查询API
```python
@router.get("/candidates")
async def get_startup_candidates(...):
    """获取启动候选股票列表"""
```

#### `scan.py`
**职责**：扫描API
```python
@router.post("/scan")
async def scan_startup_stocks(...):
    """扫描启动股票"""
```

#### `diagnose.py`
**职责**：诊断API
```python
@router.get("/diagnose/{stock_input}")
async def diagnose_stock(...):
    """单票诊断"""

@router.post("/diagnose-batch")
async def batch_diagnose(...):
    """批量诊断"""
```

#### `common.py`
**职责**：公共辅助函数
```python
def clean_nan_values(data: Dict) -> Dict:
    """清理NaN值"""

def to_native(value) -> Any:
    """转换为原生Python类型"""
```

---

## 📋 重构步骤

### 阶段1：提取数据层
1. 创建 `data/stock_data_loader.py`
2. 创建 `data/indicator_calculator.py`
3. 从 `stock_startup_filter.py` 迁移相关代码
4. 更新 `stock_startup_filter.py` 使用新类

### 阶段2：提取条件检查层
1. 创建 `conditions/` 目录和各个检查器
2. 从 `stock_startup_filter.py` 迁移检查逻辑
3. 更新 `stock_startup_filter.py` 使用新检查器

### 阶段3：提取状态管理层
1. 创建 `state/state_manager.py`（整合状态机）
2. 创建 `state/candidate_repository.py`
3. 更新 `stock_startup_filter.py` 使用新类

### 阶段4：重构筛选器
1. 简化 `startup_filter.py`，只保留流程编排
2. 使用依赖注入，提高可测试性

### 阶段5：重构API层
1. 拆分 `stock_startup.py` 为多个文件
2. 提取公共函数到 `common.py`

### 阶段6：测试和优化
1. 编写单元测试
2. 性能测试和优化
3. 文档更新

---

## ✅ 重构收益

1. **代码可维护性提升**
   - 每个类职责单一，易于理解
   - 修改影响范围小

2. **代码可测试性提升**
   - 每个组件可独立测试
   - 依赖注入便于Mock

3. **代码复用性提升**
   - 数据加载器、指标计算器可复用
   - 条件检查器可组合使用

4. **性能优化空间**
   - 数据加载可缓存
   - 指标计算可并行

5. **扩展性提升**
   - 新增条件检查器容易
   - 新增指标计算容易

---

## 🚀 开始重构

让我们从阶段1开始，逐步重构代码。

