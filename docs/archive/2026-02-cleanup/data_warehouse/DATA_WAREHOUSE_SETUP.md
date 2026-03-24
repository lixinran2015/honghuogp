# 数据仓库设置指南

## 前置要求

1. **PostgreSQL 数据库**
   - 版本：14+
   - 需要创建数据库：`quantitative_trading`

2. **Python 依赖**
   ```bash
   pip install sqlalchemy>=2.0.0 psycopg2-binary>=2.9.0 tushare>=1.2.89
   ```

## 数据库配置

### 方式1：环境变量
```bash
export DATABASE_URL="postgresql://user:password@localhost:5432/quantitative_trading"
```

### 方式2：修改配置文件
编辑 `data_warehouse/config.py`，修改 `DATABASE_URL`

## 初始化步骤

### Step 1: 创建数据库
```bash
# 使用psql
createdb quantitative_trading

# 或使用SQL
psql -U postgres
CREATE DATABASE quantitative_trading;
```

### Step 2: 初始化表结构
```bash
cd /Users/wuyanze/quantitative_trading
python -m data_warehouse.db_init
```

或者直接执行SQL文件：
```bash
psql -U postgres -d quantitative_trading -f data_warehouse/sql/schema.sql
```

### Step 3: 验证安装
运行样本回补脚本：
```bash
python -m data_warehouse.etl.backfill_sample
```

## 目录结构

```
data_warehouse/
├── __init__.py
├── config.py              # 配置文件
├── db_init.py             # 数据库初始化脚本
├── sql/
│   └── schema.sql         # SQL表结构
├── models/                # ORM模型
│   ├── dim_stock.py
│   ├── dim_trade_calendar.py
│   ├── raw_daily_price.py
│   ├── raw_fundamental.py
│   ├── fact_daily_price.py
│   ├── fact_fundamental.py
│   └── etl_log.py
├── sources/               # 数据源客户端
│   ├── base_client.py
│   ├── tushare_client.py
│   └── akshare_client.py
├── layers/                # 数据层
│   ├── raw_layer.py
│   └── clean_layer.py
├── service/               # 服务层
│   └── warehouse_service.py
└── etl/                   # ETL脚本
    └── backfill_sample.py
```

## 使用示例

### 1. 查询日线数据
```python
from data_warehouse.service.warehouse_service import WarehouseService
from datetime import date, timedelta

service = WarehouseService()

# 查询最近30天的数据
end_date = date.today()
start_date = end_date - timedelta(days=30)

data = service.get_daily_ohlc('600519.SH', start_date, end_date)
print(f"获取到 {len(data)} 条数据")
```

### 2. 查询最新日线
```python
latest = service.get_latest_daily('600519.SH')
if latest:
    print(f"最新收盘价: {latest['close']}, 质量: {latest['data_quality']}")
```

### 3. 查询财务数据
```python
financial = service.get_fundamental('600519.SH')
if financial:
    print(f"ROE: {financial['roe']}, 净利率: {financial['net_margin']}")
```

## 数据源优先级

当前配置（`data_warehouse/config.py`）：
1. **tushare**（最高优先级）
2. **akshare**（次优先级）
3. **eastmoney**（备选）
4. **easyquotation**（备选）

## 数据质量等级

- **A级**：多源一致（差异 < 0.5%）
- **B级**：单源或差异较小（0.5% < 差异 < 1%）
- **C级**：差异较大（差异 > 1%）

## 故障排查

### 问题1: 数据库连接失败
- 检查PostgreSQL服务是否运行
- 检查 `DATABASE_URL` 配置是否正确
- 检查数据库用户权限

### 问题2: 表不存在
- 运行 `python -m data_warehouse.db_init` 初始化表结构

### 问题3: Tushare/AkShare获取数据失败
- 检查网络连接
- 检查Tushare token是否有效
- 检查AkShare是否正常安装

## 下一步

- 实现历史全量回补脚本
- 实现每日增量ETL任务
- 集成到现有策略系统

