完全理解，你现在想做的是——
**把 AkShare / Tushare / 东财（甚至以后更多）当“原材料”，自己建一个稳定的数据仓库，策略层永远只用自己的库，不再直接依赖第三方。**

我给你写一份可以直接丢给 Cursor 执行的 **《多数据源行情数据仓库需求》**，包括：

* 要采什么数据
* 仓库表怎么设计
* 历史一次性回补怎么做
* 每天增量怎么跑
* 多源冲突时谁优先

---

## 《多数据源 A 股行情数据仓库 · 需求文档（给 Cursor）》

### 🎯 一、目标

1. 综合 **AkShare / Tushare / 东财网页接口** 等多数据源，建立**自有 A 股数据仓库**。
2. 一次性把 **历史数据全量拉取并落库**，以后每天只做增量更新。
3. 对上层应用（智能选股 / 达尔文评分 / 短线策略）暴露 **统一查询接口**，不再直接依赖第三方库。
4. 为未来扩展（港股、美股、基金、指数）预留结构。

---

## 🧱 二、系统分层

整体按 3 层设计：

1. **Raw Layer（原始层）**：按数据源一字不改地落库，并打上 `source` 标签。
2. **Clean Layer（标准层）**：统一字段、去重、做数据对齐和质量校验，形成自己认定的“标准价格/指标”。
3. **Service Layer（服务层视图/接口）**：给策略/前端用的 API，如：

   * `get_daily_ohlc(code, start, end)`
   * `get_realtime_snapshot(code)`
   * `get_fundamental(code, date)`

---

## 🗄️ 三、数据仓库表结构设计（以 PostgreSQL 为例）

### 3.1 维度表（Dim）

#### 1）股票维表 `dim_stock`

```sql
CREATE TABLE dim_stock (
  ts_code        VARCHAR(20) PRIMARY KEY,  -- tushare 风格，如 600519.SH
  exchange       VARCHAR(10),             -- SSE / SZSE
  symbol         VARCHAR(10),             -- 600519
  name           VARCHAR(50),
  list_date      DATE,
  delist_date    DATE,
  industry       VARCHAR(100),
  concept_tags   TEXT[],                  -- 概念标签
  updated_at     TIMESTAMP
);
```

#### 2）交易日历 `dim_trade_calendar`

```sql
CREATE TABLE dim_trade_calendar (
  trade_date DATE PRIMARY KEY,
  is_open    BOOLEAN,
  exchange   VARCHAR(10)
);
```

---

### 3.2 原始层（Raw Layer）

#### 1）日线行情原始表 `raw_daily_price`

一张表存所有来源，靠 `source` 区分：

```sql
CREATE TABLE raw_daily_price (
  id           BIGSERIAL PRIMARY KEY,
  ts_code      VARCHAR(20),
  trade_date   DATE,
  open         NUMERIC(12,4),
  high         NUMERIC(12,4),
  low          NUMERIC(12,4),
  close        NUMERIC(12,4),
  pre_close    NUMERIC(12,4),
  vol          NUMERIC(20,4),   -- 手
  amount       NUMERIC(20,4),   -- 元
  source       VARCHAR(20),     -- 'tushare' | 'akshare' | 'eastmoney'
  raw_payload  JSONB,           -- 原始返回(备查)
  created_at   TIMESTAMP DEFAULT now()
);

CREATE INDEX idx_raw_daily_price_key ON raw_daily_price(ts_code, trade_date, source);
```

#### 2）分钟/实时行情原始表 `raw_intraday_price`（可选）

短线/量价策略需要的话再做：

```sql
CREATE TABLE raw_intraday_price (
  id           BIGSERIAL PRIMARY KEY,
  ts_code      VARCHAR(20),
  ts           TIMESTAMP,       -- 时间戳（精确到分钟）
  price        NUMERIC(12,4),
  vol          NUMERIC(20,4),
  amount       NUMERIC(20,4),
  source       VARCHAR(20),
  raw_payload  JSONB,
  created_at   TIMESTAMP DEFAULT now()
);
```

#### 3）财务与基本面原始表 `raw_fundamental`

```sql
CREATE TABLE raw_fundamental (
  id            BIGSERIAL PRIMARY KEY,
  ts_code       VARCHAR(20),
  end_date      DATE,           -- 报告期
  report_type   VARCHAR(20),    -- 'annual','q1','q2','q3'
  roe           NUMERIC(8,4),
  net_margin    NUMERIC(8,4),
  gross_margin  NUMERIC(8,4),
  op_cf         NUMERIC(20,4),  -- 经营现金流
  total_debt    NUMERIC(20,4),
  total_asset   NUMERIC(20,4),
  source        VARCHAR(20),    -- 'tushare','akshare',etc.
  raw_payload   JSONB,
  created_at    TIMESTAMP DEFAULT now()
);
```

---

### 3.3 标准层（Clean Layer）

#### 1）标准日线行情 `fact_daily_price`

这里是**多源合并后的“我们认的价格”**：

```sql
CREATE TABLE fact_daily_price (
  ts_code      VARCHAR(20),
  trade_date   DATE,
  open         NUMERIC(12,4),
  high         NUMERIC(12,4),
  low          NUMERIC(12,4),
  close        NUMERIC(12,4),
  pre_close    NUMERIC(12,4),
  vol          NUMERIC(20,4),
  amount       NUMERIC(20,4),
  data_quality VARCHAR(10),    -- 'A','B','C' 等级
  sources_used VARCHAR(50)[],  -- 实际参与合并的数据源
  updated_at   TIMESTAMP,
  PRIMARY KEY (ts_code, trade_date)
);
```

多源合并规则（后面会写清楚）。

#### 2）标准财务 `fact_fundamental`

```sql
CREATE TABLE fact_fundamental (
  ts_code       VARCHAR(20),
  end_date      DATE,
  report_type   VARCHAR(20),
  roe           NUMERIC(8,4),
  net_margin    NUMERIC(8,4),
  gross_margin  NUMERIC(8,4),
  op_cf         NUMERIC(20,4),
  total_debt    NUMERIC(20,4),
  total_asset   NUMERIC(20,4),
  data_quality  VARCHAR(10),
  sources_used  VARCHAR(50)[],
  updated_at    TIMESTAMP,
  PRIMARY KEY (ts_code, end_date, report_type)
);
```

---

## ⚙️ 四、多数据源合并规则（重点）

### 4.1 数据源信任等级

先设定一个“优先级”：

1. **优先：Tushare**

   * 官方结构化数据，适合作为主基准；
2. **次之：AkShare**

   * 很多也是从同一源爬，但可作为交叉验证；
3. **备选：东财/同花顺网页接口**

   * 用于当日实时/补洞 & 交叉检查。

可以配置为：

```python
SOURCE_PRIORITY = ["tushare", "akshare", "eastmoney"]
MAX_ALLOWED_DIFF_PCT = 0.5  # 不同源价格差异超过 0.5% 则标记为低质量
```

### 4.2 合并算法（日线）

伪代码：

```python
def merge_daily_prices(ts_code, trade_date) -> FactDailyPrice:
    rows = get_raw_daily_price(ts_code, trade_date)  # 同一交易日三家数据

    # 1. 如果只有一个数据源：直接使用，quality = 'B'
    if len(rows) == 1:
        row = rows[0]
        return build_fact(row, quality='B', sources=[row.source])

    # 2. 多个数据源：按优先级排序
    rows_sorted = sorted(rows, key=lambda r: SOURCE_PRIORITY.index(r.source))

    base = rows_sorted[0]  # 主数据
    used_sources = [base.source]
    quality = 'A'

    # 3. 对比其他来源数据
    for r in rows_sorted[1:]:
        if abs(r.close - base.close) / base.close > MAX_ALLOWED_DIFF_PCT / 100:
            # 差异太大，降级数据质量
            quality = 'C'
        used_sources.append(r.source)

    return FactDailyPrice(
        ts_code=ts_code,
        trade_date=trade_date,
        open=base.open,
        high=base.high,
        low=base.low,
        close=base.close,
        pre_close=base.pre_close,
        vol=base.vol,
        amount=base.amount,
        data_quality=quality,
        sources_used=used_sources
    )
```

同样的逻辑可用于财务数据合并。

---

## ⏱️ 五、历史全量 + 每日增量的任务设计

### 5.1 一次性历史回补（Backfill）

为每个数据域写 **`backfill_*.py` 脚本**：

1. `backfill_stock_list.py`：

   * 用 Tushare / AkShare 获取全部 A 股列表，填充 `dim_stock`。

2. `backfill_daily_price.py`：

   * 对每只股票，从最早上市日到今天，分批从 **多源拉数据**，写入 `raw_daily_price`；
   * 然后跑 `merge_daily_prices`，填 `fact_daily_price`。

3. `backfill_fundamental.py`：

   * 按报告期拉历年财务数据，填 `raw_fundamental`，再合并到 `fact_fundamental`。

注意要做：

* 分批（按年份/按股票分组）以避免接口限流；
* 加断点续跑机制（记录已完成的 `ts_code + year`）。

### 5.2 每日增量任务（Daily ETL）

每天收盘后（例如 16:00）跑 `daily_etl.py`：

1. 获取当天交易日 `trade_date`（从 `dim_trade_calendar`）。
2. 对所有在市股票：

   * 分批从 Tushare / AkShare / 东财 拉取当日日线行情，插入 `raw_daily_price`；
   * 对新增日期 `trade_date` 跑合并逻辑，更新 `fact_daily_price`。
3. 拉取有更新的财报数据 → 更新 `raw_fundamental` → 合并到 `fact_fundamental`。

可以用：

* `cron + python`
* 或 `Django management command + crontab`
* 或 `Airflow / Prefect` 做编排（后期再升级）。

---

## 🌉 六、服务层接口（给策略 / 前端用）

在后端实现一个统一的 `DataWarehouseService`，对外提供方法：

```python
class DataWarehouseService:

    def get_daily_ohlc(self, ts_code: str, start: date, end: date) -> list[FactDailyPrice]:
        """从 fact_daily_price 读取日线数据"""

    def get_latest_daily(self, ts_code: str) -> FactDailyPrice:
        """读取最近一个交易日的日线"""

    def get_fundamental(self, ts_code: str, end_date: date) -> FactFundamental:
        """读取指定报告期的财务数据"""

    def get_realtime_snapshot(self, ts_code: str) -> dict:
        """
        通过实时数据源（例如 AkShare + 东财接口）获取当前分钟行情；
        这个可以不入仓库，只供短线策略即时用。
        """
```

智能选股系统（短线 / 波段 / 达尔文）今后 **只调用这些接口**，不再直接依赖 AkShare/Tushare。

---

## 📁 七、目录结构建议

```text
data_warehouse/
  __init__.py
  config.py                  # 数据库连接 & 数据源配置
  models/                    # SQLAlchemy / ORM 模型定义
    dim_stock.py
    dim_trade_calendar.py
    raw_daily_price.py
    raw_fundamental.py
    fact_daily_price.py
    fact_fundamental.py
  etl/
    backfill_stock_list.py
    backfill_daily_price.py
    backfill_fundamental.py
    daily_etl.py
  sources/                   # 封装第三方数据源
    tushare_client.py
    akshare_client.py
    eastmoney_client.py
  merge/
    daily_price_merge.py     # 多源合并算法
    fundamental_merge.py
  service/
    warehouse_service.py     # DataWarehouseService 对外接口
```

