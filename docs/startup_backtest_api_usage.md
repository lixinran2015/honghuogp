# 已启动股票回测数据API使用指南

## 📡 API接口

### 1. 获取回测信号数据

**接口地址**：`GET /api/startup/backtest-signals`

**功能**：获取指定日期范围内所有符合"已启动"条件的股票信息，用于回测

**请求参数**：
- `start_date` (可选): 回测开始日期，格式 `YYYY-MM-DD`，默认1年前
- `end_date` (可选): 回测结束日期，格式 `YYYY-MM-DD`，默认今天
- `min_score` (可选): 最低得分，默认 `60`
- `stage_filter` (可选): 阶段过滤
  - `confirmed`: 只返回"启动确认"阶段的股票
  - `started`: 只返回"完全启动"阶段的股票
  - 不传: 返回所有已启动的股票（包括 confirmed 和 started）

**响应示例**：
```json
{
  "success": true,
  "count": 156,
  "signals": [
    {
      "signal_date": "2024-01-15",
      "ts_code": "002837.SZ",
      "stock_name": "英维克",
      "entry_score": 85,
      "entry_stage": "started",
      "risk_passed": true,
      "assist_count": 3,
      "passed_signals": [
        "突破90日高点",
        "量能放大(量比≥1.5)",
        "均线多头排列(5>10>20>60)",
        "RSI健康区间(50-70)"
      ],
      "risk_reasons": [],
      "core_passed": true,
      "basic_passed": true,
      "is_started": true,
      "golden_cross_date": "2024-01-10"
    }
  ],
  "period": {
    "start_date": "2023-12-24",
    "end_date": "2024-12-24"
  },
  "filters": {
    "min_score": 60,
    "stage_filter": "all"
  }
}
```

**使用示例**：

1. **获取最近1年的所有已启动股票**：
```bash
curl http://localhost:8000/api/startup/backtest-signals
```

2. **获取指定日期范围的已启动股票**：
```bash
curl "http://localhost:8000/api/startup/backtest-signals?start_date=2024-01-01&end_date=2024-12-31"
```

3. **只获取完全启动的股票（score >= 100）**：
```bash
curl "http://localhost:8000/api/startup/backtest-signals?stage_filter=started&min_score=100"
```

4. **只获取启动确认的股票（有风险）**：
```bash
curl "http://localhost:8000/api/startup/backtest-signals?stage_filter=confirmed"
```

### 2. 获取回测信号统计信息

**接口地址**：`GET /api/startup/backtest-signals/stats`

**功能**：获取回测信号的统计信息，包括按阶段、得分区间、月份的分组统计

**请求参数**：
- `start_date` (可选): 回测开始日期，格式 `YYYY-MM-DD`，默认1年前
- `end_date` (可选): 回测结束日期，格式 `YYYY-MM-DD`，默认今天
- `min_score` (可选): 最低得分，默认 `60`

**响应示例**：
```json
{
  "success": true,
  "total_count": 156,
  "by_stage": {
    "confirmed": 98,
    "started": 58
  },
  "by_score_range": {
    "60-69": 45,
    "70-99": 68,
    "100+": 43
  },
  "by_month": [
    {
      "month": "2024-01",
      "count": 12
    },
    {
      "month": "2024-02",
      "count": 15
    }
  ],
  "period": {
    "start_date": "2023-12-24",
    "end_date": "2024-12-24"
  }
}
```

**使用示例**：

```bash
curl http://localhost:8000/api/startup/backtest-signals/stats
```

## 💻 Python代码示例

### 获取回测数据

```python
import requests
from datetime import datetime, timedelta

# API基础URL
BASE_URL = "http://localhost:8000"

# 获取最近1年的回测信号
def get_backtest_signals(start_date=None, end_date=None, min_score=60, stage_filter=None):
    """
    获取回测信号数据
    
    Args:
        start_date: 开始日期，格式 'YYYY-MM-DD'，默认1年前
        end_date: 结束日期，格式 'YYYY-MM-DD'，默认今天
        min_score: 最低得分，默认60
        stage_filter: 阶段过滤，'confirmed' 或 'started'，默认None（全部）
    
    Returns:
        dict: 回测信号数据
    """
    url = f"{BASE_URL}/api/startup/backtest-signals"
    params = {
        'min_score': min_score
    }
    
    if start_date:
        params['start_date'] = start_date
    if end_date:
        params['end_date'] = end_date
    if stage_filter:
        params['stage_filter'] = stage_filter
    
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()

# 使用示例
if __name__ == "__main__":
    # 获取最近1年的所有已启动股票
    result = get_backtest_signals()
    print(f"找到 {result['count']} 个回测信号")
    print(f"日期范围：{result['period']['start_date']} 至 {result['period']['end_date']}")
    
    # 打印前5个信号
    for signal in result['signals'][:5]:
        print(f"{signal['signal_date']} - {signal['ts_code']} ({signal['stock_name']}) - "
              f"得分: {signal['entry_score']}, 阶段: {signal['entry_stage']}")
    
    # 获取统计信息
    stats_response = requests.get(f"{BASE_URL}/api/startup/backtest-signals/stats")
    stats = stats_response.json()
    print(f"\n统计信息：")
    print(f"总数: {stats['total_count']}")
    print(f"按阶段: {stats['by_stage']}")
    print(f"按得分区间: {stats['by_score_range']}")
```

### 导出为CSV

```python
import requests
import pandas as pd
from datetime import datetime

def export_backtest_signals_to_csv(start_date=None, end_date=None, output_file='backtest_signals.csv'):
    """
    导出回测信号数据为CSV文件
    
    Args:
        start_date: 开始日期，格式 'YYYY-MM-DD'
        end_date: 结束日期，格式 'YYYY-MM-DD'
        output_file: 输出文件名
    """
    BASE_URL = "http://localhost:8000"
    url = f"{BASE_URL}/api/startup/backtest-signals"
    
    params = {}
    if start_date:
        params['start_date'] = start_date
    if end_date:
        params['end_date'] = end_date
    
    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    
    # 转换为DataFrame
    df = pd.DataFrame(data['signals'])
    
    # 展开数组字段
    df['passed_signals_str'] = df['passed_signals'].apply(lambda x: '、'.join(x) if x else '')
    df['risk_reasons_str'] = df['risk_reasons'].apply(lambda x: '、'.join(x) if x else '')
    
    # 选择需要的列
    columns = [
        'signal_date', 'ts_code', 'stock_name', 'entry_score', 'entry_stage',
        'risk_passed', 'assist_count', 'passed_signals_str', 'risk_reasons_str',
        'golden_cross_date'
    ]
    
    df_export = df[columns].copy()
    df_export.columns = [
        '入选日期', '股票代码', '股票名称', '得分', '阶段',
        '无风险', '辅助条件数', '通过的信号', '风险原因', '金叉日期'
    ]
    
    # 保存为CSV
    df_export.to_csv(output_file, index=False, encoding='utf-8-sig')
    print(f"✅ 已导出 {len(df_export)} 条记录到 {output_file}")

# 使用示例
if __name__ == "__main__":
    # 导出最近1年的数据
    export_backtest_signals_to_csv()
    
    # 导出指定日期范围的数据
    export_backtest_signals_to_csv(
        start_date='2024-01-01',
        end_date='2024-12-31',
        output_file='backtest_signals_2024.csv'
    )
```

## 📊 数据字段说明

### signal_date (入选日期)
- **说明**：股票入选"已启动"状态的日期
- **用途**：作为回测的买入信号日期
- **注意**：实际买入日期应该是 `signal_date` 的下一个交易日

### ts_code (股票代码)
- **说明**：股票代码，格式如 `002837.SZ`

### entry_score (入选得分)
- **说明**：股票入选时的得分（60-100）
- **用途**：可用于分析不同得分区间的表现

### entry_stage (入选阶段)
- **说明**：`confirmed`（启动确认）或 `started`（完全启动）
- **区别**：
  - `confirmed`: 有风险，得分通常60-99
  - `started`: 无风险，得分通常70-100

### risk_passed (风险通过)
- **说明**：是否通过风险检查
- **用途**：可用于对比有风险和无风险股票的表现

### passed_signals (通过的信号)
- **说明**：股票满足的启动信号列表
- **示例**：`["突破90日高点", "量能放大(量比≥1.5)", "均线多头排列(5>10>20>60)"]`

### risk_reasons (风险原因)
- **说明**：如果 `risk_passed=False`，这里列出风险原因
- **示例**：`["短期涨幅过大(5日:35.0%,10日:45.0%)", "偏离60日线过远(25.0%)"]`

## 🔍 查询建议

1. **回测1年数据**：不传 `start_date` 和 `end_date`，使用默认值
2. **回测特定时期**：指定 `start_date` 和 `end_date`
3. **只回测高分股票**：设置 `min_score=100` 和 `stage_filter=started`
4. **对比有风险vs无风险**：分别查询 `stage_filter=confirmed` 和 `stage_filter=started`

## ⚠️ 注意事项

1. **数据量**：1年的数据可能有几百条记录，注意API响应时间
2. **日期格式**：必须使用 `YYYY-MM-DD` 格式
3. **交易日**：`signal_date` 是入选日期，实际买入应该是下一个交易日
4. **数据完整性**：确保数据库中有足够的历史数据

