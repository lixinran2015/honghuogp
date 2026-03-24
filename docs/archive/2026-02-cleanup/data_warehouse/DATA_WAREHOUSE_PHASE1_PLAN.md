# 数据仓库第一阶段实施计划

## 目标

建立基于 PostgreSQL 的多数据源行情数据仓库，实现 Raw Layer + Clean Layer + 基础合并逻辑，打通"多数据源 → 数据库标准日线表"链路。

## 任务分解

### Task 1: 数据库表结构设计

**文件**: `data_warehouse/sql/schema.sql`

**内容**:
1. 维度表：
   - `dim_stock`: 股票维表（ts_code, exchange, symbol, name, list_date, industry等）
   - `dim_trade_calendar`: 交易日历（trade_date, is_open, exchange）

2. 原始层（Raw Layer）：
   - `raw_daily_price`: 日线行情原始表（多数据源，带source字段）
   - `raw_fundamental`: 财务数据原始表（多数据源，带source字段）

3. 标准层（Clean Layer）：
   - `fact_daily_price`: 标准日线行情表（多源合并后的标准数据）
   - `fact_fundamental`: 标准财务数据表（多源合并后的标准数据）

4. ETL日志表：
   - `etl_log`: 记录回补进度（ts_code, trade_date, source, status, created_at）

**索引设计**:
- `raw_daily_price`: (ts_code, trade_date, source)
- `fact_daily_price`: (ts_code, trade_date) PRIMARY KEY
- `raw_fundamental`: (ts_code, end_date, source)
- `fact_fundamental`: (ts_code, end_date, report_type) PRIMARY KEY

---

### Task 2: 数据源客户端封装

**文件**: 
- `data_warehouse/sources/tushare_client.py`
- `data_warehouse/sources/akshare_client.py`
- `data_warehouse/sources/base_client.py`

**功能**:
1. **BaseClient**（抽象基类）:
   - `get_daily_price(ts_code, start_date, end_date) -> List[Dict]`
   - `get_fundamental(ts_code, end_date) -> Dict`
   - `normalize_code(code) -> str` (统一代码格式为 ts_code)

2. **TushareClient**:
   - 封装 Tushare Pro API 调用
   - 实现 `get_daily_price` 和 `get_fundamental`
   - 返回标准格式数据

3. **AkShareClient**:
   - 封装 AkShare 调用
   - 实现 `get_daily_price` 和 `get_fundamental`
   - 代码格式转换（6位数字 -> ts_code格式）

**统一返回格式**:
```python
{
    'ts_code': '600519.SH',
    'trade_date': '2024-01-01',
    'open': 1800.0,
    'high': 1820.0,
    'low': 1790.0,
    'close': 1810.0,
    'pre_close': 1800.0,
    'vol': 1000000,  # 手
    'amount': 1810000000  # 元
}
```

---

### Task 3: Raw Layer 实现

**文件**: `data_warehouse/layers/raw_layer.py`

**功能**:
1. **RawDataLayer** 类:
   - `save_daily_price(ts_code, trade_date, data, source, raw_payload)`
   - `save_fundamental(ts_code, end_date, data, source, raw_payload)`
   - `get_raw_daily_price(ts_code, trade_date, source=None)`
   - `get_raw_fundamental(ts_code, end_date, source=None)`

2. **数据验证**:
   - 检查必填字段
   - 数据类型转换
   - 数据范围校验

3. **数据库连接**:
   - 使用 SQLAlchemy ORM
   - 连接池管理
   - 事务处理

---

### Task 4: Clean Layer 实现（多源合并）

**文件**: `data_warehouse/layers/clean_layer.py`

**功能**:
1. **CleanDataLayer** 类:
   - `merge_daily_prices(ts_code, trade_date) -> FactDailyPrice`
   - `merge_fundamental(ts_code, end_date) -> FactFundamental`
   - `save_fact_daily_price(fact_data)`
   - `save_fact_fundamental(fact_data)`

2. **多源合并算法**:
   ```python
   def merge_daily_prices(ts_code, trade_date):
       # 1. 从 raw_daily_price 获取所有数据源的数据
       raw_data = get_raw_daily_price(ts_code, trade_date)
       
       # 2. 按优先级排序（tushare > akshare > eastmoney）
       sorted_data = sort_by_priority(raw_data, SOURCE_PRIORITY)
       
       # 3. 选择主数据源（优先级最高的）
       base_data = sorted_data[0]
       
       # 4. 对比其他数据源，评估数据质量
       quality = assess_quality(base_data, sorted_data[1:])
       
       # 5. 生成 fact_daily_price 记录
       fact_data = {
           'ts_code': ts_code,
           'trade_date': trade_date,
           'open': base_data['open'],
           'high': base_data['high'],
           'low': base_data['low'],
           'close': base_data['close'],
           'pre_close': base_data['pre_close'],
           'vol': base_data['vol'],
           'amount': base_data['amount'],
           'data_quality': quality,
           'sources_used': [d['source'] for d in sorted_data]
       }
       
       return fact_data
   ```

3. **数据质量评估**:
   - A级：多源一致（差异 < 0.5%）
   - B级：单源或差异较小（0.5% < 差异 < 1%）
   - C级：差异较大（差异 > 1%）

---

### Task 5: Service Layer 实现

**文件**: `data_warehouse/service/warehouse_service.py`

**功能**:
1. **WarehouseService** 类:
   ```python
   class WarehouseService:
       def get_daily_ohlc(self, ts_code: str, start: date, end: date) -> List[Dict]:
           """从 fact_daily_price 读取日线数据"""
       
       def get_latest_daily(self, ts_code: str) -> Optional[Dict]:
           """读取最近一个交易日的日线"""
       
       def get_fundamental(self, ts_code: str, end_date: date) -> Optional[Dict]:
           """读取指定报告期的财务数据"""
       
       def get_stock_list(self, exchange: str = None) -> List[Dict]:
           """获取股票列表"""
   ```

2. **查询优化**:
   - 使用索引加速查询
   - 结果缓存（可选）
   - 分页支持

---

### Task 6: 样本回补脚本

**文件**: `data_warehouse/etl/backfill_sample.py`

**功能**:
1. **回补流程**:
   ```python
   def backfill_sample():
       # 1. 选择3只样本股票
       sample_stocks = ['600519.SH', '000001.SZ', '300750.SZ']
       
       # 2. 确定回补时间范围（最近1年）
       end_date = datetime.now().date()
       start_date = end_date - timedelta(days=365)
       
       # 3. 对每只股票：
       for ts_code in sample_stocks:
           # 3.1 从多个数据源获取数据
           for source in ['tushare', 'akshare']:
               data = client.get_daily_price(ts_code, start_date, end_date)
               # 3.2 写入 raw_daily_price
               raw_layer.save_daily_price(ts_code, data, source)
           
           # 3.3 合并到 fact_daily_price
           for trade_date in get_trade_dates(start_date, end_date):
               fact_data = clean_layer.merge_daily_prices(ts_code, trade_date)
               clean_layer.save_fact_daily_price(fact_data)
       
       # 4. 验证数据
       verify_data(sample_stocks)
   ```

2. **验证功能**:
   - 检查数据完整性
   - 对比多源数据一致性
   - 输出验证报告

---

## 技术栈

1. **数据库**: PostgreSQL 14+
2. **ORM**: SQLAlchemy 2.0+
3. **数据源**: Tushare Pro, AkShare
4. **依赖管理**: requirements.txt

## 目录结构

```
data_warehouse/
├── __init__.py
├── config.py              # 数据库配置、数据源优先级
├── sql/
│   └── schema.sql         # 数据库表结构
├── models/                # SQLAlchemy ORM 模型
│   ├── __init__.py
│   ├── dim_stock.py
│   ├── dim_trade_calendar.py
│   ├── raw_daily_price.py
│   ├── raw_fundamental.py
│   ├── fact_daily_price.py
│   └── fact_fundamental.py
├── sources/               # 数据源客户端
│   ├── __init__.py
│   ├── base_client.py
│   ├── tushare_client.py
│   └── akshare_client.py
├── layers/                # 数据层
│   ├── __init__.py
│   ├── raw_layer.py
│   └── clean_layer.py
├── service/               # 服务层
│   ├── __init__.py
│   └── warehouse_service.py
└── etl/                   # ETL脚本
    ├── __init__.py
    └── backfill_sample.py
```

## 配置文件

**文件**: `data_warehouse/config.py`

```python
# 数据库配置
DATABASE_URL = "postgresql://user:password@localhost:5432/quantitative_trading"

# 数据源优先级
SOURCE_PRIORITY = ["tushare", "akshare", "eastmoney"]

# 数据质量阈值
MAX_ALLOWED_DIFF_PCT = 0.5  # 0.5%

# 数据质量等级
DATA_QUALITY_A = "A"
DATA_QUALITY_B = "B"
DATA_QUALITY_C = "C"
```

## 实施顺序

1. **Step 1**: 创建数据库和表结构（Task 1）
2. **Step 2**: 封装数据源客户端（Task 2）
3. **Step 3**: 实现 Raw Layer（Task 3）
4. **Step 4**: 实现 Clean Layer（Task 4）
5. **Step 5**: 实现 Service Layer（Task 5）
6. **Step 6**: 编写样本回补脚本并验证（Task 6）

## 验收标准

1. ✅ 数据库表结构创建成功
2. ✅ 能够从 Tushare 和 AkShare 获取数据并写入 raw 层
3. ✅ 多源合并逻辑正确，能够生成 fact 层数据
4. ✅ 样本回补脚本能够成功回补3只股票1年数据
5. ✅ 数据质量评估正确（A/B/C等级）
6. ✅ Service Layer 能够正确查询数据

## 后续扩展

- 历史全量回补脚本（按股票/年份分批）
- 每日增量ETL任务
- 分钟线数据支持
- 资金流向数据支持
- 指标计算和缓存

