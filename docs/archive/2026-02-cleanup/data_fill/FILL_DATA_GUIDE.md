# 数据补全指南

## 一、分时数据补全

### 1. 测试运行（少量股票）

```bash
# 测试3只股票，补最近5天的数据
python3 backend/scripts/fill_intraday_data.py --limit 3 --ndays 5
```

### 2. 正式补全（分批处理）

**方案1：小批量测试（推荐先运行）**
```bash
# 先补100只股票，最近10天
python3 backend/scripts/fill_intraday_data.py --limit 100 --ndays 10
```

**方案2：后台运行（全部股票）**
```bash
# 使用脚本后台运行
./fill_intraday.sh

# 或手动运行
nohup python3 backend/scripts/fill_intraday_data.py --ndays 10 > logs/fill_intraday.log 2>&1 &
```

**方案3：断点续传**
```bash
# 如果中断了，可以从第N只股票继续
python3 backend/scripts/fill_intraday_data.py --ndays 10 --start-from 100
```

### 3. 查看进度

```bash
# 实时查看日志
tail -f logs/fill_intraday.log

# 查看数据库统计
python3 -c "
from sqlalchemy import create_engine, text
from data_warehouse.config import DATABASE_URL
engine = create_engine(DATABASE_URL, echo=False)
with engine.connect() as conn:
    result = conn.execute(text('''
        SELECT 
            COUNT(*) as total,
            COUNT(DISTINCT ts_code) as stocks,
            COUNT(DISTINCT trade_date) as dates,
            MIN(trade_date) as earliest,
            MAX(trade_date) as latest
        FROM fact_intraday_price_1m
    '''))
    stats = result.fetchone()
    print(f'总记录数: {stats[0]:,}')
    print(f'股票数量: {stats[1]} 只')
    print(f'交易日数: {stats[2]} 天')
    if stats[3]:
        print(f'日期范围: {stats[3]} ~ {stats[4]}')
"
```

### 4. 参数说明

- `--ndays`: 补最近几天的数据（默认10天）
- `--limit`: 限制股票数量（用于测试，不指定则处理所有股票）
- `--start-from`: 从第几只股票开始（用于断点续传）

---

## 二、后续数据补全（待实现）

按照用户要求，缺的数据一个个补，不要一类数据调一堆接口。

### 1. 涨停板数据（下一步）

等分时数据补完后，再实现：
- `backend/scripts/fill_limitup_data.py`
- 逐个日期补，不要一次性调用太多接口

### 2. 情绪数据（下一步）

等涨停板数据补完后：
- `backend/scripts/fill_emotion_data.py`

### 3. 板块数据（下一步）

等情绪数据补完后：
- `backend/scripts/fill_sector_data.py`

---

## 三、注意事项

1. **API限流**: 东财API可能有频率限制，脚本已实现逐个处理，避免并发
2. **网络稳定性**: 如果网络不稳定，可以使用 `--start-from` 参数断点续传
3. **数据量**: 每只股票每天约240条分时数据（4小时×60分钟），10天约2400条
4. **时间估算**: 
   - 每只股票约1-2秒
   - 5000只股票约1.5-3小时
   - 建议分批处理，避免一次性运行太久

---

## 四、监控命令

```bash
# 查看进程
ps aux | grep fill_intraday

# 查看最新日志
tail -20 logs/fill_intraday.log

# 查看数据库进度
python3 -c "
from sqlalchemy import create_engine, text
from data_warehouse.config import DATABASE_URL
engine = create_engine(DATABASE_URL, echo=False)
with engine.connect() as conn:
    result = conn.execute(text('SELECT COUNT(DISTINCT ts_code) FROM fact_intraday_price_1m'))
    count = result.fetchone()[0]
    print(f'已完成: {count} 只股票')
"
```

