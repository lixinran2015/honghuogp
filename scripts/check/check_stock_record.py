#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""检查002922.SZ的数据库记录"""
import sys
from pathlib import Path
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models.startup_candidate import FactStockStartupCandidate
from datetime import datetime, date

ws = WarehouseService()
session = ws.get_session()

try:
    records = session.query(FactStockStartupCandidate).filter(
        FactStockStartupCandidate.ts_code == '002922.SZ'
    ).order_by(
        FactStockStartupCandidate.trade_date.desc()
    ).limit(10).all()
    
    print(f'找到 {len(records)} 条记录:')
    print('=' * 100)
    for r in records:
        print(f'日期: {r.trade_date}')
        print(f'  阶段: {r.stage}')
        print(f'  得分: {r.score}')
        print(f'  基础通过: {r.basic_passed}')
        print(f'  核心通过: {r.core_passed}')
        print(f'  辅助条件数: {r.assist_count}')
        print(f'  风险通过: {r.risk_passed}')
        print(f'  金叉日期: {r.golden_cross_date}')
        print(f'  通过的信号: {r.passed_signals}')
        print(f'  风险原因: {r.risk_reasons}')
        if r.indicators:
            indicators = dict(r.indicators) if hasattr(r.indicators, 'keys') else r.indicators
            amount = indicators.get('amount', 0) if isinstance(indicators, dict) else 0
            print(f'  成交额: {amount/1e8 if amount else 0:.2f}亿' if amount else '  成交额: 未记录')
        print('-' * 100)
finally:
    session.close()

