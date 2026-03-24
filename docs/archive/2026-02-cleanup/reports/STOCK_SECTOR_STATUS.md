# 股票-板块关联数据补全状态

## 当前状态

- **板块维表 (dim_sector)**: ✅ 86 个板块（已完成）
- **股票-板块关联 (fact_stock_sector)**: ⚠️ 0 条记录（待补全）

## 问题

当前网络环境下，AKShare API 无法连接：
- 所有请求都返回 `Connection aborted`
- 直接调用 `ak.stock_board_industry_cons_em()` 也失败
- 这是网络问题，不是代码问题

## 解决方案

### 方案1：等待网络恢复后运行（推荐）

脚本已优化，包含：
- ✅ 重试机制（最多5次，指数退避）
- ✅ 请求延迟（可配置，默认1-3秒）
- ✅ 断点续传支持（`--start-from`）
- ✅ 每50个板块额外休息10秒

**运行命令**：
```bash
# 后台运行，延迟2秒
nohup python3 backend/scripts/fill_stock_sector_robust.py --delay 2.0 > logs/fill_stock_sector.log 2>&1 &

# 查看进度
tail -f logs/fill_stock_sector.log

# 如果中断，从第N个板块继续
python3 backend/scripts/fill_stock_sector_robust.py --start-from N --delay 2.0
```

### 方案2：使用 Tushare（需要权限）

如果 Tushare 有权限，可以使用：
```bash
python3 backend/scripts/fill_sector_from_tushare.py
```

### 方案3：手动导入（如果有其他数据源）

如果有其他数据源的股票-板块关联数据（CSV/Excel），可以创建导入脚本。

## 脚本说明

### `fill_stock_sector_robust.py`

**功能**：
- 补全股票-板块关联数据
- 使用 AKShareService（带重试机制）
- 支持断点续传
- 自动跳过已有数据的板块

**参数**：
- `--limit N`: 限制板块数量（用于测试）
- `--delay N`: 每次请求延迟（秒，默认1.0）
- `--start-from N`: 从第N个板块开始（用于断点续传）

**示例**：
```bash
# 测试前5个板块
python3 backend/scripts/fill_stock_sector_robust.py --limit 5 --delay 2.0

# 从第10个板块开始继续
python3 backend/scripts/fill_stock_sector_robust.py --start-from 10 --delay 2.0

# 后台运行全部
nohup python3 backend/scripts/fill_stock_sector_robust.py --delay 2.0 > logs/fill_stock_sector.log 2>&1 &
```

## 数据统计

补全完成后，应该会有：
- 约 86 个板块
- 每个板块约 10-200 只股票
- 总计约 5000-10000 条关联记录（一只股票可能属于多个板块）

## 监控命令

```bash
# 查看当前关联数据数量
python3 -c "
from sqlalchemy import create_engine, text
from data_warehouse.config import DATABASE_URL
engine = create_engine(DATABASE_URL, echo=False)
with engine.connect() as conn:
    result = conn.execute(text('SELECT COUNT(*) FROM fact_stock_sector'))
    count = result.fetchone()[0]
    print(f'当前关联数据: {count} 条')
"

# 查看已完成的板块
python3 -c "
from sqlalchemy import create_engine, text
from data_warehouse.config import DATABASE_URL
engine = create_engine(DATABASE_URL, echo=False)
with engine.connect() as conn:
    result = conn.execute(text('''
        SELECT COUNT(DISTINCT sector_id) as completed
        FROM fact_stock_sector
    '''))
    count = result.fetchone()[0]
    print(f'已完成板块: {count}/86')
"
```

## 下一步

1. **等待网络恢复**：AKShare API 网络连接恢复后运行脚本
2. **监控进度**：使用上述监控命令查看补全进度
3. **断点续传**：如果中断，使用 `--start-from` 继续
4. **验证数据**：补全后验证数据完整性

