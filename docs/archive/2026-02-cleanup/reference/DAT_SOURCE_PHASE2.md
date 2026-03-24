

1. **新增 5 张表的建表 SQL**（可以直接贴到迁移里执行）
2. **数据获取 & 入库的 Python 服务骨架**（放到 `backend/services/` 下，Cursor 可补全细节）
3. **如何调度：每天一次的在线补数据方案**

你可以直接复制整段给 Cursor，让它按文件拆分实现。

---

## 一、SQL：新增 5 张表（直接可执行）

### 1. 分钟级分时数据表：`fact_intraday_price_1m`

```sql
-- 1. 分钟级分时数据表（只保留最近 N 日）
CREATE TABLE IF NOT EXISTS fact_intraday_price_1m (
    ts_code        VARCHAR(20) NOT NULL,                -- 600519.SH
    trade_time     TIMESTAMP   NOT NULL,                -- 精确到分钟
    trade_date     DATE        NOT NULL,
    open           NUMERIC(12,4),
    high           NUMERIC(12,4),
    low            NUMERIC(12,4),
    close          NUMERIC(12,4),
    volume         NUMERIC(20,4),                       -- 分钟成交量（股/手，按源注释）
    amount         NUMERIC(20,4),                       -- 分钟成交额（元）
    avg_price      NUMERIC(12,4),                       -- 分钟均价（腾讯会给）
    source         VARCHAR(20) NOT NULL,                -- tencent/eastmoney
    updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ts_code, trade_time)
);

CREATE INDEX IF NOT EXISTS idx_intraday_date 
    ON fact_intraday_price_1m (trade_date);
```

---

### 2. 每日涨停板明细：`fact_limit_up_daily`

```sql
-- 2. 每日涨停板明细（情绪 & 龙头识别基础）
CREATE TABLE IF NOT EXISTS fact_limit_up_daily (
    ts_code          VARCHAR(20) NOT NULL,
    trade_date       DATE        NOT NULL,
    first_hit_time   TIMESTAMP,             -- 首次触及涨停时间
    last_hit_time    TIMESTAMP,             -- 最后一次封住涨停时间
    is_one_word      BOOLEAN,               -- 是否一字板
    close            NUMERIC(12,4),
    change_pct       NUMERIC(8,4),
    limit_up_price   NUMERIC(12,4),
    turnover_rate    NUMERIC(8,4),
    amount           NUMERIC(20,4),
    seal_amount      NUMERIC(20,4),         -- 涨停板封单金额（东财）
    is_continuous    BOOLEAN,               -- 是否连板
    continuous_days  INTEGER,               -- 连板天数（2、3、4板…）
    limit_reason     TEXT,                  -- 东财/同花顺的涨停原因摘要
    source           VARCHAR(20) NOT NULL,  -- eastmoney 等
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ts_code, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_limitup_date 
    ON fact_limit_up_daily (trade_date);
```

---

### 3. 每日情绪摘要：`fact_market_emotion_daily`（可选但强烈推荐）

```sql
-- 3. 市场情绪日度统计
CREATE TABLE IF NOT EXISTS fact_market_emotion_daily (
    trade_date       DATE PRIMARY KEY,
    total_limit_up   INTEGER,       -- 涨停家数
    total_limit_down INTEGER,       -- 跌停家数
    broken_limit_up  INTEGER,       -- 炸板数量
    highest_streak   INTEGER,       -- 市场最高连板高度
    mainline_sector  VARCHAR(100),  -- 主线板块名称（可选，后续策略写入）
    emotion_stage    VARCHAR(20),   -- 冰点/回暖/高潮/退潮/震荡
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

### 4. 行业 & 板块维表：`dim_sector`

```sql
-- 4. 行业 & 板块维表
CREATE TABLE IF NOT EXISTS dim_sector (
    sector_id     VARCHAR(50) PRIMARY KEY, -- 如 SW_801010 / BK0471 / EM_I_X
    sector_type   VARCHAR(20) NOT NULL,    -- industry / concept / index
    name          VARCHAR(100) NOT NULL,
    level         INTEGER,                 -- 1: 一级行业; 2: 二级; null: 概念
    provider      VARCHAR(20),             -- sw / citic / eastmoney 等
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

### 5. 股票-板块关联表 + 板块日线：`fact_stock_sector` + `fact_sector_daily`

```sql
-- 5.1 股票所属板块（行业/概念）关联
CREATE TABLE IF NOT EXISTS fact_stock_sector (
    ts_code      VARCHAR(20) NOT NULL,
    sector_id    VARCHAR(50) NOT NULL,
    start_date   DATE NOT NULL,
    end_date     DATE,                     -- null 表示当前仍有效
    is_primary   BOOLEAN DEFAULT TRUE,     -- 是否主行业（vs 概念、辅行业）
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ts_code, sector_id, start_date)
);

CREATE INDEX IF NOT EXISTS idx_stock_sector_ts 
    ON fact_stock_sector (ts_code);
CREATE INDEX IF NOT EXISTS idx_stock_sector_sector 
    ON fact_stock_sector (sector_id);


-- 5.2 板块指数日线（用于板块热度 & 主线识别）
CREATE TABLE IF NOT EXISTS fact_sector_daily (
    sector_id       VARCHAR(50) NOT NULL,
    trade_date      DATE NOT NULL,
    close           NUMERIC(12,4),
    pre_close       NUMERIC(12,4),
    change_pct      NUMERIC(8,4),
    volume          NUMERIC(20,4),      -- 成交量
    amount          NUMERIC(20,4),      -- 成交额
    num_stocks      INTEGER,            -- 板块成分股数量
    num_up          INTEGER,            -- 上涨家数
    num_limit_up    INTEGER,            -- 涨停家数
    heat_score      NUMERIC(8,4),       -- 板块热度评分（策略层回写）
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (sector_id, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_sector_daily_date 
    ON fact_sector_daily (trade_date);
```

---

## 二、数据获取方法（Python，Cursor 可以直接继续补完）

建议新建目录：

```bash
backend/
  services/
    market_history_service.py     # 你已有的日线/历史服务
    intraday_service.py           # 分时数据（腾讯+东财）
    limitup_emotion_service.py    # 涨停板 & 情绪
    sector_service.py             # 行业 & 板块 & 热度
```

下面给的是**骨架 + 关键逻辑**，Cursor 可以自动补充 requests、DB 封装、日志等细节。

---

### 1. 分时数据：`intraday_service.py`

```python
# backend/services/intraday_service.py
import datetime
from typing import List, Optional
import pandas as pd
import requests
import psycopg2  # or use Django ORM / SQLAlchemy

from backend.settings import DB_DSN  # 你自己的配置

# ========== 工具函数：代码转换 ==========
def ts_code_to_tencent_symbol(ts_code: str) -> str:
    """
    600519.SH -> sh600519
    000001.SZ -> sz000001
    """
    code, exch = ts_code.split(".")
    if exch == "SH":
        return f"sh{code}"
    elif exch == "SZ":
        return f"sz{code}"
    else:
        raise ValueError(f"unsupported exchange: {ts_code}")


def ts_code_to_eastmoney_secid(ts_code: str) -> str:
    """
    600519.SH -> 1.600519
    000001.SZ -> 0.000001
    """
    code, exch = ts_code.split(".")
    if exch == "SH":
        return f"1.{code}"
    elif exch == "SZ":
        return f"0.{code}"
    else:
        raise ValueError(f"unsupported exchange: {ts_code}")


# ========== 1.1 腾讯分钟级数据 ==========
def fetch_intraday_from_tencent(ts_code: str, ndays: int = 10) -> Optional[pd.DataFrame]:
    """
    从腾讯 qt 拉最近 ndays 天的 1 分钟数据
    返回标准化 DataFrame: [trade_time, trade_date, open, high, low, close, volume, amount, avg_price]
    """
    symbol = ts_code_to_tencent_symbol(ts_code)
    url = "https://web.ifzq.gtimg.cn/appstock/app/minute/kline"
    # 部分接口参数可能需微调，Cursor 可以根据返回结构做适配
    params = {
        "param": f"{symbol},m1,,,{ndays}",  # m1=1分钟, m5=5分钟
    }
    try:
        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        text = resp.text.replace("min_data=", "").replace("kline_minute=", "")
        data_json = eval(text)
        data = data_json["data"][symbol]["data"]
    except Exception as e:
        print(f"[tencent] fetch intraday failed for {ts_code}: {e}")
        return None

    rows = []
    for day_block in data:
        date_str = day_block["date"]  # 如 '2025-11-18'
        klines = day_block["data"]    # ['09:30 100.00 100.10 99.90 100.00 12345 1234567', ...]
        for item in klines:
            # 以空格分隔
            parts = item.split(" ")
            if len(parts) < 7:
                continue
            t_str, o, h, l, c, v, a = parts[:7]
            trade_time = datetime.datetime.strptime(f"{date_str} {t_str}", "%Y-%m-%d %H:%M")
            rows.append(
                {
                    "trade_time": trade_time,
                    "trade_date": trade_time.date(),
                    "open": float(o),
                    "high": float(h),
                    "low": float(l),
                    "close": float(c),
                    "volume": float(v),
                    "amount": float(a),
                    "avg_price": None,  # 如有可从返回中取
                }
            )
    if not rows:
        return None

    df = pd.DataFrame(rows)
    return df


# ========== 1.2 东方财富分钟级兜底 ==========
def fetch_intraday_from_eastmoney(ts_code: str, ndays: int = 10) -> Optional[pd.DataFrame]:
    secid = ts_code_to_eastmoney_secid(ts_code)
    url = "https://push2his.eastmoney.com/api/qt/stock/trends2/get"
    params = {
        "secid": secid,
        "ndays": ndays,
        "fields1": "f1,f2,f3,f4,f5",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
    }
    try:
        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        klines = data.get("trends", [])
    except Exception as e:
        print(f"[eastmoney] fetch intraday failed for {ts_code}: {e}")
        return None

    rows = []
    for item in klines:
        # 示例：'2025-11-18 09:30,100.00,100.10,99.90,100.00,12345,1234567,100.01'
        parts = item.split(",")
        if len(parts) < 8:
            continue
        dt_str, o, c, h, l, v, a, avg = parts[:8]
        trade_time = datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
        rows.append(
            {
                "trade_time": trade_time,
                "trade_date": trade_time.date(),
                "open": float(o),
                "high": float(h),
                "low": float(l),
                "close": float(c),
                "volume": float(v),
                "amount": float(a),
                "avg_price": float(avg),
            }
        )
    if not rows:
        return None

    return pd.DataFrame(rows)


# ========== 1.3 入库逻辑 ==========
def upsert_intraday_df(ts_code: str, df: pd.DataFrame, source: str):
    """
    将 DataFrame 写入 fact_intraday_price_1m，按 (ts_code, trade_time) UPSERT
    这里用 psycopg2 写死 SQL，Cursor 可以改成 Django ORM / SQLAlchemy
    """
    if df is None or df.empty:
        return

    conn = psycopg2.connect(DB_DSN)
    cur = conn.cursor()
    sql = """
    INSERT INTO fact_intraday_price_1m (
        ts_code, trade_time, trade_date,
        open, high, low, close,
        volume, amount, avg_price,
        source, updated_at
    ) VALUES (
        %(ts_code)s, %(trade_time)s, %(trade_date)s,
        %(open)s, %(high)s, %(low)s, %(close)s,
        %(volume)s, %(amount)s, %(avg_price)s,
        %(source)s, NOW()
    )
    ON CONFLICT (ts_code, trade_time)
    DO UPDATE SET
        open = EXCLUDED.open,
        high = EXCLUDED.high,
        low  = EXCLUDED.low,
        close = EXCLUDED.close,
        volume = EXCLUDED.volume,
        amount = EXCLUDED.amount,
        avg_price = EXCLUDED.avg_price,
        source = EXCLUDED.source,
        updated_at = NOW();
    """
    records = []
    for _, row in df.iterrows():
        records.append(
            {
                "ts_code": ts_code,
                "trade_time": row["trade_time"],
                "trade_date": row["trade_date"],
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": row["volume"],
                "amount": row["amount"],
                "avg_price": row.get("avg_price"),
                "source": source,
            }
        )
    try:
        cur.executemany(sql, records)
        conn.commit()
    finally:
        cur.close()
        conn.close()


def update_intraday_last_ndays(ndays: int = 10, limit: Optional[int] = None):
    """
    每晚跑一次：对 dim_stock 中的 A 股，抓最近 ndays 的 1m 分时（腾讯优先，东财兜底）
    limit: 可选，调试时限制股票数量
    """
    conn = psycopg2.connect(DB_DSN)
    cur = conn.cursor()
    cur.execute("SELECT ts_code FROM dim_stock WHERE delist_date IS NULL;")
    all_codes = [r[0] for r in cur.fetchall()]
    cur.close()
    conn.close()

    if limit:
        all_codes = all_codes[:limit]

    for ts_code in all_codes:
        print(f"[intraday] fetching {ts_code} ...")
        df = fetch_intraday_from_tencent(ts_code, ndays=ndays)
        source = "tencent"
        if df is None:
            df = fetch_intraday_from_eastmoney(ts_code, ndays=ndays)
            source = "eastmoney" if df is not None else None
        if df is None:
            print(f"[intraday] no data for {ts_code}")
            continue
        upsert_intraday_df(ts_code, df, source=source)
```

> 你可以在定时任务里每天收盘后调用：
> `update_intraday_last_ndays(ndays=10)`

---

### 2. 涨停板 & 情绪：`limitup_emotion_service.py`

```python
# backend/services/limitup_emotion_service.py
import datetime
from typing import List, Dict
import requests
import psycopg2

from backend.settings import DB_DSN

def fetch_limit_up_from_eastmoney(trade_date: datetime.date) -> List[Dict]:
    """
    从东方财富获取某天涨停板列表.
    这里用的是 getTopicZTPool 或类似接口，Cursor 可以根据返回结构调整解析逻辑。
    返回结构统一为：
    [
      {
        "ts_code": "600519.SH",
        "close": 1234.56,
        "change_pct": 9.99,
        "limit_up_price": 1234.56,
        "turnover_rate": 12.34,
        "amount": 123456789.0,
        "seal_amount": 23456789.0,
        "first_hit_time": "2025-11-18 09:45:00",
        "last_hit_time": "2025-11-18 14:55:00",
        "is_one_word": True/False,
        "is_continuous": True/False,
        "continuous_days": 1/2/3/...,
        "limit_reason": "XX概念+YY预期"
      },
      ...
    ]
    """
    # 示例 URL（具体参数 Cursor 可以根据接口文档/实际返回调整）
    url = "https://push2ex.eastmoney.com/getTopicZTPool"
    params = {
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
        "dpt": "app_zdt",
        "Pageindex": 0,
        "pagesize": 200,
        "date": trade_date.strftime("%Y%m%d"),
        "type": "ZTP"  # 涨停池
    }
    resp = requests.get(url, params=params, timeout=5)
    resp.raise_for_status()
    data = resp.json().get("data", {})
    pool = data.get("pool", [])

    results = []
    for item in pool:
        # 这里字段名以东财当前格式为准，Cursor 可以查看真实返回调整
        # 例：item["c"] 股票代码, item["n"] 名称, item["p"] 收盘价, item["zdp"] 涨跌幅, ...
        code = item.get("c")           # 600519
        market = item.get("m")         # 1=SH, 0=SZ
        if market == 1:
            ts_code = f"{code}.SH"
        elif market == 0:
            ts_code = f"{code}.SZ"
        else:
            continue

        results.append(
            {
                "ts_code": ts_code,
                "close": float(item.get("p", 0)),
                "change_pct": float(item.get("zdp", 0)),
                "limit_up_price": float(item.get("np", 0)),
                "turnover_rate": float(item.get("hs", 0)),
                "amount": float(item.get("a", 0)),
                "seal_amount": float(item.get("fd", 0)),
                "first_hit_time": item.get("ft", None),  # '09:35'
                "last_hit_time": item.get("lt", None),
                "is_one_word": bool(item.get("yd", 0)),  # 一字
                "is_continuous": bool(item.get("lbc", 1) > 1),
                "continuous_days": int(item.get("lbc", 1)),
                "limit_reason": item.get("dr", ""),
            }
        )
    return results


def upsert_limitup_and_emotion(trade_date: datetime.date):
    """
    拉取指定日期的涨停板列表，写入 fact_limit_up_daily 和 fact_market_emotion_daily
    """
    records = fetch_limit_up_from_eastmoney(trade_date)
    conn = psycopg2.connect(DB_DSN)
    cur = conn.cursor()

    # 写入 fact_limit_up_daily
    sql_limit = """
    INSERT INTO fact_limit_up_daily (
        ts_code, trade_date,
        first_hit_time, last_hit_time, is_one_word,
        close, change_pct, limit_up_price,
        turnover_rate, amount, seal_amount,
        is_continuous, continuous_days, limit_reason,
        source, updated_at
    ) VALUES (
        %(ts_code)s, %(trade_date)s,
        %(first_hit_time)s, %(last_hit_time)s, %(is_one_word)s,
        %(close)s, %(change_pct)s, %(limit_up_price)s,
        %(turnover_rate)s, %(amount)s, %(seal_amount)s,
        %(is_continuous)s, %(continuous_days)s, %(limit_reason)s,
        'eastmoney', NOW()
    )
    ON CONFLICT (ts_code, trade_date)
    DO UPDATE SET
        first_hit_time = EXCLUDED.first_hit_time,
        last_hit_time  = EXCLUDED.last_hit_time,
        is_one_word    = EXCLUDED.is_one_word,
        close          = EXCLUDED.close,
        change_pct     = EXCLUDED.change_pct,
        limit_up_price = EXCLUDED.limit_up_price,
        turnover_rate  = EXCLUDED.turnover_rate,
        amount         = EXCLUDED.amount,
        seal_amount    = EXCLUDED.seal_amount,
        is_continuous  = EXCLUDED.is_continuous,
        continuous_days= EXCLUDED.continuous_days,
        limit_reason   = EXCLUDED.limit_reason,
        source         = EXCLUDED.source,
        updated_at     = NOW();
    """

    # 计算情绪统计
    total_limit_up = len(records)
    total_limit_down = 0  # 如需要可另写跌停接口
    broken_limit_up = 0   # 可由当日分时/日内数据计算
    highest_streak = max([r["continuous_days"] for r in records], default=0)

    # 写入明细
    for r in records:
        ft = r["first_hit_time"]
        lt = r["last_hit_time"]
        first_hit_dt = (
            datetime.datetime.strptime(f"{trade_date} {ft}", "%Y-%m-%d %H:%M")
            if ft else None
        )
        last_hit_dt = (
            datetime.datetime.strptime(f"{trade_date} {lt}", "%Y-%m-%d %H:%M")
            if lt else None
        )
        params = {
            **r,
            "trade_date": trade_date,
            "first_hit_time": first_hit_dt,
            "last_hit_time": last_hit_dt,
        }
        cur.execute(sql_limit, params)

    # 写入/更新情绪表
    sql_emotion = """
    INSERT INTO fact_market_emotion_daily (
        trade_date, total_limit_up, total_limit_down,
        broken_limit_up, highest_streak, mainline_sector,
        emotion_stage, updated_at
    ) VALUES (
        %(trade_date)s, %(total_limit_up)s, %(total_limit_down)s,
        %(broken_limit_up)s, %(highest_streak)s, %(mainline_sector)s,
        %(emotion_stage)s, NOW()
    )
    ON CONFLICT (trade_date)
    DO UPDATE SET
        total_limit_up   = EXCLUDED.total_limit_up,
        total_limit_down = EXCLUDED.total_limit_down,
        broken_limit_up  = EXCLUDED.broken_limit_up,
        highest_streak   = EXCLUDED.highest_streak,
        mainline_sector  = EXCLUDED.mainline_sector,
        emotion_stage    = EXCLUDED.emotion_stage,
        updated_at       = NOW();
    """
    # emotion_stage 暂时空，后续情绪模型算好再写回
    cur.execute(
        sql_emotion,
        {
            "trade_date": trade_date,
            "total_limit_up": total_limit_up,
            "total_limit_down": total_limit_down,
            "broken_limit_up": broken_limit_up,
            "highest_streak": highest_streak,
            "mainline_sector": None,
            "emotion_stage": None,
        },
    )

    conn.commit()
    cur.close()
    conn.close()
```

> 调度：
> 每个交易日收盘后：`upsert_limitup_and_emotion(trade_date=today)`

---

### 3. 行业 & 板块：`sector_service.py`（用 AkShare/东财初始化 + 日线更新）

```python
# backend/services/sector_service.py
import datetime
import psycopg2
import akshare as ak
from backend.settings import DB_DSN

def init_industry_from_akshare():
    """
    一次性初始化行业板块及成分股（以东财行业为例）
    """
    conn = psycopg2.connect(DB_DSN)
    cur = conn.cursor()

    # 1) 拉行业列表
    industry_df = ak.stock_board_industry_name_em()  # 行业列表
    # columns 示例: ['板块名称', '板块代码', ...]
    for _, row in industry_df.iterrows():
        sector_id = row["板块代码"]       # 如 'BK0471'
        name = row["板块名称"]
        cur.execute(
            """
            INSERT INTO dim_sector (sector_id, sector_type, name, level, provider, updated_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            ON CONFLICT (sector_id)
            DO UPDATE SET
                sector_type = EXCLUDED.sector_type,
                name = EXCLUDED.name,
                level = EXCLUDED.level,
                provider = EXCLUDED.provider,
                updated_at = NOW();
            """,
            (sector_id, "industry", name, 1, "eastmoney"),
        )

    # 2) 拉每个行业的成分股
    today = datetime.date.today()
    for _, row in industry_df.iterrows():
        sector_id = row["板块代码"]
        cons_df = ak.stock_board_industry_cons_em(symbol=row["板块名称"])
        # cons_df 中有 '代码', '名称'
        for _, c in cons_df.iterrows():
            code = c["代码"]    # 600519
            # 这里简单按前缀判断交易所，你也可以 join dim_stock 做更精确映射
            if code.startswith("6"):
                ts_code = f"{code}.SH"
            else:
                ts_code = f"{code}.SZ"
            cur.execute(
                """
                INSERT INTO fact_stock_sector (
                    ts_code, sector_id, start_date, end_date, is_primary, updated_at
                )
                VALUES (%s, %s, %s, NULL, %s, NOW())
                ON CONFLICT (ts_code, sector_id, start_date)
                DO NOTHING;
                """,
                (ts_code, sector_id, today, True),
            )

    conn.commit()
    cur.close()
    conn.close()


def update_sector_daily(trade_date: datetime.date):
    """
    每日更新板块指数日线（用于板块热度）
    """
    conn = psycopg2.connect(DB_DSN)
    cur = conn.cursor()
    cur.execute("SELECT sector_id, name FROM dim_sector WHERE sector_type = 'industry';")
    sectors = cur.fetchall()
    cur.close()

    cur = conn.cursor()
    for sector_id, name in sectors:
        # 示例：AkShare 行业指数日K
        try:
            k_df = ak.stock_board_industry_hist_em(
                symbol=name, period="daily", adjust=""
            )
        except Exception as e:
            print(f"[sector_daily] fetch failed for {sector_id} {name}: {e}")
            continue

        # k_df columns 示例: ['日期', '收盘', '涨跌幅', '成交量', '成交额', ...]
        row = k_df[k_df["日期"] == trade_date.strftime("%Y-%m-%d")]
        if row.empty:
            continue
        row = row.iloc[0]

        cur.execute(
            """
            INSERT INTO fact_sector_daily (
                sector_id, trade_date,
                close, pre_close, change_pct,
                volume, amount,
                num_stocks, num_up, num_limit_up,
                heat_score, updated_at
            ) VALUES (
                %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s, %s,
                NULL, NOW()
            )
            ON CONFLICT (sector_id, trade_date)
            DO UPDATE SET
                close       = EXCLUDED.close,
                pre_close   = EXCLUDED.pre_close,
                change_pct  = EXCLUDED.change_pct,
                volume      = EXCLUDED.volume,
                amount      = EXCLUDED.amount,
                num_stocks  = EXCLUDED.num_stocks,
                num_up      = EXCLUDED.num_up,
                num_limit_up= EXCLUDED.num_limit_up,
                updated_at  = NOW();
            """,
            (
                sector_id,
                trade_date,
                float(row["收盘"]),
                None,                          # 可用前一日值填
                float(row["涨跌幅"]),
                float(row["成交量"]),
                float(row["成交额"]),
                None,                          # 成分股数量可通过 fact_stock_sector 统计
                None,                          # 上涨家数后续由策略写回
                None,                          # 涨停家数可由 fact_limit_up_daily 统计
            ),
        )
    conn.commit()
    cur.close()
    conn.close()
```

---

## 三、调度建议（一天一次，安全又够用）

你可以在后端加一个简单的“日终 ETL 命令”，每天收盘后（比如 18:00）执行：

1. **更新分钟级分时（最近 10 日）：**

```python
from backend.services.intraday_service import update_intraday_last_ndays
update_intraday_last_ndays(ndays=10)
```

2. **更新今日涨停板 & 情绪：**

```python
from backend.services.limitup_emotion_service import upsert_limitup_and_emotion
upsert_limitup_and_emotion(trade_date=today)
```

3. **（可选）更新板块日线：**

```python
from backend.services.sector_service import update_sector_daily
update_sector_daily(trade_date=today)
```

---

