"""
从fact_fundamental表读取财务数据，计算TTM值，更新到fact_daily_fundamental表
（不依赖Tushare高级权限）
"""

import sys
import logging
from pathlib import Path
from datetime import date, datetime
from typing import Optional, Dict, List
from decimal import Decimal

# 添加项目根目录到路径（backend/scripts/data_fill -> 需再上两级到项目根）
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.services.data.postgres_warehouse import PostgresWarehouse
from data_warehouse.models import FactDailyFundamental
from data_warehouse.models import FactFundamental
from data_warehouse.models import DimStock
from sqlalchemy import text, func

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_latest_trade_date(warehouse: PostgresWarehouse) -> Optional[date]:
    """获取最新的交易日期"""
    if not warehouse.warehouse_service:
        return None
    
    session = warehouse.warehouse_service.get_session()
    try:
        query = text("""
            SELECT MAX(trade_date) as latest_date
            FROM fact_daily_price_qfq
        """)
        result = session.execute(query).scalar()
        return result if result else None
    finally:
        session.close()


def calculate_ttm_from_fact_fundamental(
    session,
    ts_code: str
) -> Optional[Dict]:
    """
    从fact_fundamental表读取最近4个季度数据，计算TTM值
    
    Args:
        session: 数据库会话
        ts_code: 股票代码
    
    Returns:
        dict: TTM财务指标
    """
    try:
        # 获取最近4个季度的财务数据（按报告期倒序）
        quarters = session.query(FactFundamental).filter(
            FactFundamental.ts_code == ts_code,
            FactFundamental.end_date >= date(2023, 1, 1)  # 只取2023年后的数据
        ).order_by(
            FactFundamental.end_date.desc()
        ).limit(4).all()
        
        if not quarters:
            return None
        
        # 计算TTM值（包含亏损股：roe/net_margin 可为负）
        roe_values = []
        net_margin_values = []
        gross_margin_values = []
        op_cf_values = []

        for q in quarters:
            if q.roe is not None:
                roe_values.append(float(q.roe))
            if q.net_margin is not None:
                net_margin_values.append(float(q.net_margin))
            if q.gross_margin is not None and q.gross_margin >= 0:
                gross_margin_values.append(float(q.gross_margin))
            if q.op_cf is not None and q.op_cf != 0:
                op_cf_values.append(float(q.op_cf))

        result = {}

        if roe_values:
            result['roe_ttm'] = sum(roe_values) / len(roe_values)
        if net_margin_values:
            result['net_margin_ttm'] = sum(net_margin_values) / len(net_margin_values)
        if gross_margin_values:
            result['gross_margin_ttm'] = sum(gross_margin_values) / len(gross_margin_values)
        if op_cf_values:
            result['op_cf_ttm'] = sum(op_cf_values)

        # 若上述均为空，使用最新一期（含负值）
        if not result and len(quarters) > 0:
            latest = quarters[0]
            if latest.roe is not None:
                result['roe_ttm'] = float(latest.roe)
            if latest.net_margin is not None:
                result['net_margin_ttm'] = float(latest.net_margin)
            if latest.gross_margin is not None and latest.gross_margin >= 0:
                result['gross_margin_ttm'] = float(latest.gross_margin)
            if latest.op_cf is not None and latest.op_cf != 0:
                result['op_cf_ttm'] = float(latest.op_cf)

        # 营收同比增长率：取最近一期 fact_fundamental.revenue_growth（%）
        if quarters and hasattr(quarters[0], 'revenue_growth') and quarters[0].revenue_growth is not None:
            try:
                result['revenue_growth_yoy'] = float(quarters[0].revenue_growth)
            except (TypeError, ValueError):
                pass

        return result if result else None
        
    except Exception as e:
        logger.debug(f"计算 {ts_code} TTM值失败: {e}")
        return None


def update_daily_fundamental(
    session,
    ts_code: str,
    trade_date: date,
    financial_data: Dict
) -> bool:
    """
    更新fact_daily_fundamental表
    
    Args:
        session: 数据库会话
        ts_code: 股票代码
        trade_date: 交易日期
        financial_data: 财务数据
    
    Returns:
        bool: 是否成功
    """
    try:
        # 查询或创建记录
        existing = session.query(FactDailyFundamental).filter(
            FactDailyFundamental.ts_code == ts_code,
            FactDailyFundamental.trade_date == trade_date
        ).first()
        
        if existing:
            # 更新现有记录
            if financial_data.get('roe_ttm') is not None:
                existing.roe_ttm = financial_data['roe_ttm']
            if financial_data.get('net_margin_ttm') is not None:
                existing.net_margin_ttm = financial_data['net_margin_ttm']
            if financial_data.get('gross_margin_ttm') is not None:
                existing.gross_margin_ttm = financial_data['gross_margin_ttm']
            if financial_data.get('op_cf_ttm') is not None:
                existing.op_cf_ttm = financial_data['op_cf_ttm']
            if financial_data.get('revenue_growth_yoy') is not None:
                existing.revenue_growth_yoy = financial_data['revenue_growth_yoy']
        else:
            # 创建新记录
            new_record = FactDailyFundamental(
                ts_code=ts_code,
                trade_date=trade_date,
                roe_ttm=financial_data.get('roe_ttm'),
                net_margin_ttm=financial_data.get('net_margin_ttm'),
                gross_margin_ttm=financial_data.get('gross_margin_ttm'),
                op_cf_ttm=financial_data.get('op_cf_ttm'),
                revenue_growth_yoy=financial_data.get('revenue_growth_yoy'),
                source='fact_fund_calc'
            )
            session.add(new_record)
        
        session.commit()
        return True
        
    except Exception as e:
        logger.error(f"更新 {ts_code} 财务数据失败: {e}")
        session.rollback()
        return False


def fill_daily_fundamental_from_fact(
    limit: Optional[int] = None
):
    """
    从fact_fundamental表读取财务数据，计算TTM值，更新到fact_daily_fundamental表
    
    Args:
        limit: 限制处理的股票数量
    """
    logger.info("=" * 60)
    logger.info("从fact_fundamental表补充每日基本面指标（ROE、毛利率、净利率、现金流、营收增长）")
    logger.info("=" * 60)
    print("=" * 60)
    print("从fact_fundamental表补充每日基本面指标（ROE、毛利率、净利率、现金流、营收增长）")
    print("=" * 60)

    # 初始化服务
    warehouse = PostgresWarehouse()

    if not warehouse.warehouse_service:
        logger.error("❌ 数据仓库未初始化")
        print("❌ 数据仓库未初始化")
        return

    # 获取最新交易日期
    latest_date = get_latest_trade_date(warehouse)
    if not latest_date:
        logger.error("❌ 无法获取最新交易日期")
        print("❌ 无法获取最新交易日期（fact_daily_price_qfq 表可能为空）")
        return

    logger.info(f"📅 目标交易日期: {latest_date}")
    print(f"📅 目标交易日期: {latest_date}")
    
    # 获取有财务数据的股票列表
    session = warehouse.warehouse_service.get_session()
    try:
        # 获取有财务数据的股票代码
        query = session.query(FactFundamental.ts_code).distinct().filter(
            FactFundamental.end_date >= date(2023, 1, 1)
        )
        
        if limit:
            query = query.limit(limit)
        
        stock_codes = [r[0] for r in query.all()]

        logger.info(f"📊 共 {len(stock_codes)} 只股票有财务数据")
        print(f"📊 共 {len(stock_codes)} 只股票有财务数据，开始处理...")

        if not stock_codes:
            logger.warning("⚠️ 没有找到有财务数据的股票")
            print("⚠️ 没有找到有财务数据的股票（fact_fundamental 表 end_date>=2023-01-01 无数据）")
            return
        
        logger.info("")
        
        success_count = 0
        failed_count = 0
        skip_count = 0
        
        # 批量处理
        for idx, ts_code in enumerate(stock_codes, 1):
            try:
                # 计算TTM值
                financial_data = calculate_ttm_from_fact_fundamental(session, ts_code)
                
                if not financial_data:
                    if idx <= 5:
                        logger.debug(f"  ⚠️ {ts_code} 无法计算TTM值")
                    skip_count += 1
                    continue
                
                # 更新到数据库
                success = update_daily_fundamental(
                    session,
                    ts_code,
                    latest_date,
                    financial_data
                )
                
                if success:
                    success_count += 1
                    if idx % 50 == 0 or idx <= 5:
                        logger.info(f"  进度: {idx}/{len(stock_codes)} - {ts_code}: ROE={financial_data.get('roe_ttm', 0):.2f}%, 毛利率={financial_data.get('gross_margin_ttm', 0):.2f}%")
                else:
                    failed_count += 1
                
            except Exception as e:
                logger.error(f"  ❌ 处理 {ts_code} 失败: {e}")
                failed_count += 1
                continue
        
        logger.info("")
        logger.info("=" * 60)
        logger.info(f"✅ 补充完成")
        logger.info(f"  成功: {success_count} 只")
        logger.info(f"  失败: {failed_count} 只")
        logger.info(f"  跳过: {skip_count} 只")
        logger.info("=" * 60)
        print("")
        print("=" * 60)
        print(f"✅ 补充完成 - 成功: {success_count}, 失败: {failed_count}, 跳过: {skip_count}")
        print("=" * 60)
        
    finally:
        session.close()


if __name__ == '__main__':
    try:
        print("开始执行 fill_daily_fundamental_from_fact ...")
        # 从fact_fundamental表补充财务数据（不限制数量，处理所有有数据的股票）
        fill_daily_fundamental_from_fact(limit=None)
        print("执行完成")
    except KeyboardInterrupt:
        print("\n⚠️ 用户中断")
        logger.info("\n⚠️ 用户中断")
    except Exception as e:
        print(f"❌ 补充失败: {e}")
        logger.error(f"❌ 补充失败: {e}", exc_info=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)

