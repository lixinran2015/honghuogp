"""创建监控结果表"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models import FactMonitorNear5940

ws = WarehouseService()
FactMonitorNear5940.__table__.create(ws.engine, checkfirst=True)
print('fact_monitor_near5_940 表创建成功')

