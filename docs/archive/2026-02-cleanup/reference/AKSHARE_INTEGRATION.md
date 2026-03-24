# AKShare 集成方案

## 一、AKShare 简介

[AKShare](https://github.com/akfamily/akshare) 是一个优雅、简单的 Python 金融数据接口库，提供了丰富的中国股票、基金、期货等金融数据接口。

**优势**：
- ✅ 开源免费
- ✅ 接口丰富（股票、基金、期货、债券等）
- ✅ 文档完善
- ✅ 社区活跃（14.4k stars）
- ✅ 持续更新

## 二、当前使用情况

### 已使用的接口

1. **行业板块数据** (`backend/services/sector_service.py`)
   - `ak.stock_board_industry_name_em()` - 获取行业板块列表
   - `ak.stock_board_industry_cons_em()` - 获取行业成分股
   - `ak.stock_board_industry_hist_em()` - 获取行业指数日K线

2. **实时行情** (`akshare_safe_wrapper.py`)
   - 通过 `easyquotation` 获取实时行情（腾讯数据源）

### 遇到的问题

- ⚠️ 网络连接不稳定（`Connection aborted`）
- ⚠️ 某些接口需要重试机制

## 三、可用的 AKShare 接口（对我们有用的）

### 1. 实时行情数据

```python
# 获取A股实时行情
df = ak.stock_zh_a_spot_em()
# 返回：股票代码、名称、最新价、涨跌幅、成交量、成交额等
```

**用途**：替代或补充现有的实时行情数据源

### 2. 历史K线数据

```python
# 获取A股历史K线（支持前复权、后复权）
df = ak.stock_zh_a_hist(
    symbol="000001",
    period="daily",
    start_date="20240101",
    end_date="20241118",
    adjust="qfq"  # qfq=前复权, hfq=后复权, ""=不复权
)
```

**用途**：
- 补充历史K线数据
- 替代现有的多源K线获取逻辑

### 3. 涨停板数据

```python
# 获取涨停板数据
df = ak.stock_zt_pool_em(date="20251118")
# 返回：股票代码、名称、涨停价、封单金额、涨停原因等
```

**用途**：
- 替代现有的东财涨停板接口
- 补全 `fact_limit_up_daily` 表

### 4. 板块数据（已在使用）

```python
# 行业板块列表
df = ak.stock_board_industry_name_em()

# 行业成分股
df = ak.stock_board_industry_cons_em(symbol="半导体")

# 行业指数日K
df = ak.stock_board_industry_hist_em(symbol="半导体", period="daily")
```

**用途**：
- 补全板块维表和关联表
- 获取板块日线数据

### 5. 资金流向数据

```python
# 个股资金流向
df = ak.stock_fund_flow_individual_em(symbol="000001")

# 板块资金流向
df = ak.stock_fund_flow_sector_em()
```

**用途**：
- 分析资金流向
- 识别热点板块

### 6. 基本面数据

```python
# 财务指标
df = ak.stock_financial_abstract_ths(symbol="000001")

# 业绩预告
df = ak.stock_yjyg_em()
```

**用途**：
- 补充财务数据
- 支持达尔文公司筛选

## 四、集成方案

### 方案1：增强现有服务（推荐）

在现有服务中添加 AKShare 作为备选数据源：

```python
# backend/services/intraday_service.py
def fetch_intraday_from_akshare(ts_code: str, ndays: int = 10):
    """使用 AKShare 获取分时数据（备选方案）"""
    try:
        # AKShare 可能没有直接的分钟级接口，但可以用日K线
        # 或者使用其他接口
        pass
    except Exception as e:
        logger.warning(f"[akshare] fetch intraday failed: {e}")
        return None
```

### 方案2：创建 AKShare 统一封装

```python
# backend/services/akshare_service.py
import akshare as ak
from typing import Optional
import pandas as pd
import time

class AKShareService:
    """AKShare 统一封装，添加重试和错误处理"""
    
    def __init__(self, max_retries=3, retry_delay=1):
        self.max_retries = max_retries
        self.retry_delay = retry_delay
    
    def _retry_call(self, func, *args, **kwargs):
        """带重试的函数调用"""
        for i in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if i == self.max_retries - 1:
                    raise
                logger.warning(f"重试 {i+1}/{self.max_retries}: {e}")
                time.sleep(self.retry_delay * (i + 1))
        return None
    
    def get_realtime_stocks(self):
        """获取实时行情"""
        return self._retry_call(ak.stock_zh_a_spot_em)
    
    def get_stock_history(self, symbol, start_date, end_date, adjust="qfq"):
        """获取历史K线"""
        return self._retry_call(
            ak.stock_zh_a_hist,
            symbol=symbol,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust=adjust
        )
    
    def get_limit_up_stocks(self, date):
        """获取涨停板数据"""
        return self._retry_call(ak.stock_zt_pool_em, date=date)
    
    def get_industry_list(self):
        """获取行业板块列表"""
        return self._retry_call(ak.stock_board_industry_name_em)
    
    def get_industry_stocks(self, industry_name):
        """获取行业成分股"""
        return self._retry_call(ak.stock_board_industry_cons_em, symbol=industry_name)
```

### 方案3：替换现有数据源

对于网络不稳定的接口，使用 AKShare 作为主要数据源：

1. **涨停板数据**：使用 `ak.stock_zt_pool_em()` 替代东财接口
2. **板块数据**：继续使用 AKShare（已在使用）
3. **历史K线**：使用 `ak.stock_zh_a_hist()` 作为备选

## 五、实施建议

### 优先级1：涨停板数据（立即实施）

```python
# backend/services/limitup_emotion_service.py
def fetch_limit_up_from_akshare(trade_date: datetime.date):
    """使用 AKShare 获取涨停板数据（替代东财）"""
    try:
        date_str = trade_date.strftime("%Y%m%d")
        df = ak.stock_zt_pool_em(date=date_str)
        
        # 转换格式
        results = []
        for _, row in df.iterrows():
            code = row.get("代码", "")
            # 转换为 ts_code 格式
            if code.startswith("6"):
                ts_code = f"{code}.SH"
            elif code.startswith("0") or code.startswith("3"):
                ts_code = f"{code}.SZ"
            else:
                continue
            
            results.append({
                "ts_code": ts_code,
                "close": float(row.get("最新价", 0)),
                "change_pct": float(row.get("涨跌幅", 0)),
                "limit_up_price": float(row.get("涨停价", 0)),
                "turnover_rate": float(row.get("换手率", 0)),
                "amount": float(row.get("成交额", 0)),
                # ... 其他字段
            })
        return results
    except Exception as e:
        logger.error(f"[akshare] fetch limit up failed: {e}")
        return []
```

### 优先级2：历史K线数据（备选方案）

```python
# backend/utils/data_sources.py
def fetch_from_akshare(ts_code: str, start_date: str, end_date: str):
    """使用 AKShare 获取历史K线（备选）"""
    try:
        # 转换代码格式：600519.SH -> 600519
        code = ts_code.split(".")[0]
        
        df = ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=start_date.replace("-", ""),
            end_date=end_date.replace("-", ""),
            adjust="qfq"  # 前复权
        )
        
        # 标准化列名
        df = df.rename(columns={
            "日期": "trade_date",
            "开盘": "open",
            "收盘": "close",
            "最高": "high",
            "最低": "low",
            "成交量": "volume",
            "成交额": "amount",
            "换手率": "turnover_rate",
            "涨跌幅": "change_pct"
        })
        
        return df
    except Exception as e:
        logger.warning(f"[akshare] fetch history failed: {e}")
        return None
```

### 优先级3：实时行情（补充）

```python
# backend/services/market_data_service.py
def get_realtime_stocks_from_akshare():
    """使用 AKShare 获取实时行情（备选）"""
    try:
        df = ak.stock_zh_a_spot_em()
        # 转换格式...
        return df
    except Exception as e:
        logger.warning(f"[akshare] fetch realtime failed: {e}")
        return None
```

## 六、网络问题处理

### 添加重试机制

```python
from functools import wraps
import time
import logging

def retry_on_failure(max_retries=3, delay=1):
    """重试装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for i in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if i == max_retries - 1:
                        raise
                    logger.warning(f"重试 {i+1}/{max_retries}: {e}")
                    time.sleep(delay * (i + 1))
            return None
        return wrapper
    return decorator

# 使用
@retry_on_failure(max_retries=3, delay=2)
def get_industry_list():
    return ak.stock_board_industry_name_em()
```

### 添加缓存机制

```python
from functools import lru_cache
import datetime

@lru_cache(maxsize=128)
def get_industry_list_cached():
    """带缓存的行业列表（1小时有效）"""
    return ak.stock_board_industry_name_em()
```

## 七、总结

### ✅ 建议使用 AKShare 的场景

1. **涨停板数据** - 替代东财接口
2. **历史K线数据** - 作为备选数据源
3. **板块数据** - 继续使用（已在使用）
4. **实时行情** - 作为备选数据源

### ⚠️ 注意事项

1. **网络稳定性**：添加重试机制
2. **数据格式**：统一转换为我们内部格式
3. **频率限制**：避免请求过于频繁
4. **错误处理**：完善的异常处理

### 📋 实施步骤

1. ✅ 创建 `AKShareService` 封装类
2. ✅ 实现涨停板数据获取（替代东财）
3. ✅ 添加重试机制
4. ✅ 更新现有服务使用 AKShare 作为备选
5. ⏳ 测试和验证

## 八、参考链接

- [AKShare GitHub](https://github.com/akfamily/akshare)
- [AKShare 文档](https://akshare.akfamily.xyz/)
- [AKShare 安装](https://github.com/akfamily/akshare#installation)

