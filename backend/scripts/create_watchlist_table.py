"""创建 fact_stock_watchlist 表"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models import FactStockWatchlist

ws = WarehouseService()
FactStockWatchlist.__table__.create(ws.engine, checkfirst=True)
print("fact_stock_watchlist 表创建成功")

