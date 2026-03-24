# 数据仓库系统说明

## 概述

数据仓库系统用于存储和管理股票数据、财务数据，避免频繁调用外部API，提高系统稳定性和响应速度。

## 目录结构

```
data_warehouse/
├── stocks/          # 股票行情数据（按日期存储CSV文件）
│   ├── 2025-11-14.csv
│   ├── 2025-11-13.csv
│   └── ...
└── financial/       # 财务数据（按日期存储JSON文件）
    ├── 2025-11-14.json
    ├── 2025-11-13.json
    └── ...
```

## 更新规则

### 开市时间段（9:30-11:30, 13:00-15:00）
- **股票数据**：每10分钟自动更新一次
- **财务数据**：每天更新一次（通常在收盘后）

### 闭市时间段
- **股票数据**：使用15点收盘数据（如果已存在则不再更新）
- **财务数据**：使用最新可用数据

## 初始化

### 自动初始化
系统启动时会自动初始化数据仓库（异步执行，不阻塞启动）。

### 手动初始化
如果需要手动初始化或重新初始化，可以运行：

```bash
cd /Users/wuyanze/quantitative_trading
python3 backend/scripts/init_data_warehouse.py
```

这将：
1. 拉取近180天（约半年）的股票数据（如果可用）
2. 拉取当前所有股票的财务数据

## 数据获取

### 股票数据
- 来源：`akshare` / `easyquotation`
- 格式：CSV文件，包含代码、名称、价格、涨跌幅、成交额等

### 财务数据
- 来源：`akshare.stock_financial_analysis_indicator_em()`
- 格式：JSON文件，包含ROE、毛利率、净利率、现金流、负债率等
- 更新频率：每天一次（通常在收盘后）

## 使用方式

### 在代码中使用

```python
from backend.services.data_warehouse import DataWarehouse

# 创建数据仓库实例
warehouse = DataWarehouse()

# 读取今日股票数据
today = "2025-11-14"
stocks = warehouse.load_stocks_data(today)

# 读取今日财务数据
financial = warehouse.load_financial_data(today)

# 获取单只股票的财务数据
financial_data = warehouse.get_stock_financial_data("000001")
```

### 在服务中使用

`FinancialDataService` 已自动从数据仓库读取数据：

```python
from backend.services.financial_data_service import FinancialDataService

service = FinancialDataService()
financial_data = service.get_financial_data("000001")
```

## 数据清理

数据仓库会自动保留最近365天的数据，更早的数据会被自动清理。

也可以手动清理：

```python
warehouse.cleanup_old_data(days=365)
```

## 注意事项

1. **初始化时间**：首次初始化可能需要较长时间（取决于股票数量）
2. **网络要求**：需要稳定的网络连接访问akshare
3. **存储空间**：每天的数据约占用几MB空间，建议定期清理旧数据
4. **数据准确性**：财务数据来自akshare，可能存在延迟或缺失

## 故障排查

### 数据更新失败
- 检查网络连接
- 检查akshare是否正常
- 查看日志文件：`logs/api_YYYYMMDD.log`

### 数据不存在
- 确认数据仓库已初始化
- 检查日期格式是否正确（YYYY-MM-DD）
- 确认该日期是否为交易日（周末和节假日无数据）

