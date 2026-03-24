"""
手动将英维克（002837.SZ）加入已启动状态
"""
import sys
from pathlib import Path
from datetime import datetime, date
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models.startup_candidate import FactStockStartupCandidate
from backend.services.stock.stock_startup_filter import StockStartupFilter
from backend.services.stock.startup.conditions.assist_condition_checker import AssistConditionChecker
from backend.services.stock.startup.conditions.risk_condition_checker import RiskConditionChecker
from backend.services.stock.startup.state.state_manager import StartupStateManager
from sqlalchemy import and_

ws = WarehouseService()
session = ws.get_session()

ts_code = '002837.SZ'
today = datetime.now().date()

try:
    print(f"=" * 80)
    print(f"将英维克（{ts_code}）加入已启动状态")
    print(f"=" * 80)
    
    # 1. 获取股票数据
    print(f"\n📊 步骤1: 获取股票数据...")
    filter_service = StockStartupFilter(warehouse_service=ws)
    
    try:
        stock_data = filter_service._get_stock_indicators(
            ts_code,
            today.isoformat(),
            force_realtime=True
        )
        
        if not stock_data:
            print(f"❌ 无法获取股票数据")
            exit(1)
        
        print(f"✅ 数据获取成功: 价格={stock_data.get('close', 0)}")
    except Exception as e:
        print(f"❌ 获取数据失败: {e}")
        exit(1)
    
    # 2. 检查辅助条件和风险条件
    print(f"\n📊 步骤2: 检查辅助条件和风险条件...")
    assist_checker = AssistConditionChecker()
    assist_checks = assist_checker.check(stock_data)
    
    risk_checker = RiskConditionChecker()
    risk_checks = risk_checker.check(stock_data)
    
    print(f"  辅助条件满足数: {assist_checks['count']}")
    print(f"  风险检查通过: {risk_checks['passed']}")
    
    # 3. 确定阶段和得分（假设满足3/3核心条件）
    print(f"\n📊 步骤3: 计算阶段和得分...")
    state_manager = StartupStateManager()
    result_stage, _ = state_manager.determine_state(
        basic_passed=True,  # 假设基础条件通过
        core_passed=True,  # 3/3核心条件已满足
        assist_count=assist_checks['count'],
        risk_passed=risk_checks['passed']
    )
    result_score = state_manager.calculate_score(
        basic_passed=True,
        core_passed=True,
        assist_count=assist_checks['count'],
        risk_passed=risk_checks['passed']
    )
    
    print(f"  阶段(stage): {result_stage}")
    print(f"  得分(score): {result_score}")
    
    # 4. 构建信号列表（3个核心条件都已满足）
    signals = ['突破90日高点', '量能放大(量比≥1.5)', '均线多头排列(5>10>20>60)']
    signals.extend(assist_checks.get('passed_signals', []))
    
    print(f"\n📊 步骤4: 保存记录到数据库...")
    
    # 检查今天是否已有记录
    existing = session.query(FactStockStartupCandidate).filter(
        and_(
            FactStockStartupCandidate.ts_code == ts_code,
            FactStockStartupCandidate.trade_date == today
        )
    ).first()
    
    if existing:
        # 更新现有记录
        print(f"  更新现有记录...")
        existing.score = result_score
        existing.stage = result_stage
        existing.is_started = result_score >= 100
        existing.core_passed = True
        existing.assist_count = assist_checks['count']
        existing.risk_passed = risk_checks['passed']
        existing.passed_signals = signals
        existing.risk_reasons = risk_checks.get('risks', [])
        existing.basic_passed = True
        existing.latest_price = float(stock_data.get('close', 0))
        existing.ma10 = float(stock_data.get('ma10', 0))
    else:
        # 创建新记录
        print(f"  创建新记录...")
        new_record = FactStockStartupCandidate(
            ts_code=ts_code,
            trade_date=today,
            score=result_score,
            is_started=result_score >= 100,
            stage=result_stage,
            basic_passed=True,
            core_passed=True,
            assist_count=assist_checks['count'],
            risk_passed=risk_checks['passed'],
            passed_signals=signals,
            risk_reasons=risk_checks.get('risks', []),
            latest_price=float(stock_data.get('close', 0)),
            ma10=float(stock_data.get('ma10', 0))
        )
        session.add(new_record)
    
    # 5. 提交更改
    session.commit()
    print(f"✅ 记录已保存: stage={result_stage}, score={result_score}")
    
    # 6. 验证
    print(f"\n📊 步骤5: 验证记录...")
    saved_record = session.query(FactStockStartupCandidate).filter(
        and_(
            FactStockStartupCandidate.ts_code == ts_code,
            FactStockStartupCandidate.trade_date == today
        )
    ).first()
    
    if saved_record:
        print(f"✅ 验证成功:")
        print(f"  stage: {saved_record.stage}")
        print(f"  score: {saved_record.score}")
        print(f"  is_started: {saved_record.is_started}")
        print(f"  core_passed: {saved_record.core_passed}")
        print(f"  assist_count: {saved_record.assist_count}")
        print(f"  risk_passed: {saved_record.risk_passed}")
    else:
        print(f"❌ 验证失败: 未找到保存的记录")
    
    print(f"\n" + "=" * 80)
    print(f"✅ 完成！英维克已加入已启动状态")
    print(f"=" * 80)
    
finally:
    session.close()

