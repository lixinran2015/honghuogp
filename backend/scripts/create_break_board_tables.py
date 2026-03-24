"""创建断板监控相关表"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models import (
    FactStockWatchlistBreakBoard,
    FactBreakBoardPriceAlert,
    FactBreakBoardMonitorLog,
)

ws = WarehouseService()

# 创建断板监控表
FactStockWatchlistBreakBoard.__table__.create(ws.engine, checkfirst=True)
print("✓ fact_stock_watchlist_break_board 表创建成功")

FactBreakBoardPriceAlert.__table__.create(ws.engine, checkfirst=True)
print("✓ fact_break_board_price_alert 表创建成功")

FactBreakBoardMonitorLog.__table__.create(ws.engine, checkfirst=True)
print("✓ fact_break_board_monitor_log 表创建成功")

print("\n断板监控表创建完成！")
