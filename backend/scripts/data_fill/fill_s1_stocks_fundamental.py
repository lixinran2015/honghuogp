"""
为S1股票池的126只股票补充财务数据
从fact_fundamental表读取数据，计算TTM值，更新到fact_daily_fundamental表
"""

import sys
import logging
from pathlib import Path
from datetime import date, datetime
from typing import Optional, Dict, List

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.services.data.postgres_warehouse import PostgresWarehouse
from data_warehouse.models import FactDailyFundamental
from data_warehouse.models import FactFundamental
from sqlalchemy import text

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def normalize_code(code: str) -> str:
    """将6位数字代码转换为Tushare格式"""
    if isinstance(code, str) and len(code) == 6 and code.isdigit():
        if code.startswith('6'):
            return f"{code}.SH"
        elif code.startswith(('0', '3')):
            return f"{code}.SZ"
        elif code.startswith(('8', '4')):
            return f"{code}.BJ"
    return code  # 已经是Tushare格式或无法识别


def get_s1_stock_codes(warehouse: PostgresWarehouse) -> List[str]:
    """获取S1股票池的股票代码列表（Tushare格式）"""
    if not warehouse.warehouse_service:
        return []
    
    session = warehouse.warehouse_service.get_session()
    try:
        query = text("""
            SELECT DISTINCT ts_code
            FROM dim_stock_universe
            WHERE universe_type = 's1'
                AND is_active = TRUE
                AND trade_date = (SELECT MAX(trade_date) FROM dim_stock_universe WHERE universe_type = 's1')
            ORDER BY ts_code
        """)
        results = session.execute(query).fetchall()
        codes = [normalize_code(row[0]) for row in results]
        return codes
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
        ts_code: 股票代码（Tushare格式）
    
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
        
        # 计算TTM值（简单平均）
        roe_values = []
        net_margin_values = []
        gross_margin_values = []
        op_cf_values = []
        
        for q in quarters:
            if q.roe is not None and q.roe > 0:
                roe_values.append(float(q.roe))
            if q.net_margin is not None and q.net_margin > 0:
                net_margin_values.append(float(q.net_margin))
            if q.gross_margin is not None and q.gross_margin > 0:
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
        
        # 如果只有最新一期数据，直接使用
        if not result and len(quarters) > 0:
            latest = quarters[0]
            if latest.roe is not None and latest.roe > 0:
                result['roe_ttm'] = float(latest.roe)
            if latest.net_margin is not None and latest.net_margin > 0:
                result['net_margin_ttm'] = float(latest.net_margin)
            if latest.gross_margin is not None and latest.gross_margin > 0:
                result['gross_margin_ttm'] = float(latest.gross_margin)
            if latest.op_cf is not None and latest.op_cf != 0:
                result['op_cf_ttm'] = float(latest.op_cf)
        
        return result if result else None
        
    except Exception as e:
        logger.debug(f"计算 {ts_code} TTM值失败: {e}")
        return None


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
        ts_code: 股票代码（Tushare格式）
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
        else:
            # 创建新记录
            new_record = FactDailyFundamental(
                ts_code=ts_code,
                trade_date=trade_date,
                roe_ttm=financial_data.get('roe_ttm'),
                net_margin_ttm=financial_data.get('net_margin_ttm'),
                gross_margin_ttm=financial_data.get('gross_margin_ttm'),
                op_cf_ttm=financial_data.get('op_cf_ttm'),
                source='s1_fill'
            )
            session.add(new_record)
        
        session.commit()
        return True
        
    except Exception as e:
        logger.error(f"更新 {ts_code} 财务数据失败: {e}")
        session.rollback()
        return False


def fill_s1_stocks_fundamental():
    """
    为S1股票池的股票补充财务数据
    """
    logger.info("=" * 60)
    logger.info("为S1股票池补充财务数据")
    logger.info("=" * 60)
    
    # 初始化服务
    warehouse = PostgresWarehouse()
    
    if not warehouse.warehouse_service:
        logger.error("❌ 数据仓库未初始化")
        return
    
    # 获取S1股票代码列表
    s1_codes = get_s1_stock_codes(warehouse)
    if not s1_codes:
        logger.warning("⚠️ 没有找到S1股票")
        return
    
    logger.info(f"📊 找到 {len(s1_codes)} 只S1股票")
    
    # 获取最新交易日期
    latest_date = get_latest_trade_date(warehouse)
    if not latest_date:
        logger.error("❌ 无法获取最新交易日期")
        return
    
    logger.info(f"📅 目标交易日期: {latest_date}")
    logger.info("")
    
    session = warehouse.warehouse_service.get_session()
    try:
        success_count = 0
        failed_count = 0
        skip_count = 0
        
        for idx, ts_code in enumerate(s1_codes, 1):
            try:
                # 计算TTM值
                financial_data = calculate_ttm_from_fact_fundamental(session, ts_code)
                
                if not financial_data:
                    if idx <= 5:
                        logger.warning(f"  ⚠️ {ts_code} 无法计算TTM值（fact_fundamental表中无数据）")
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
                    if idx % 20 == 0 or idx <= 5:
                        logger.info(f"  进度: {idx}/{len(s1_codes)} - {ts_code}: ROE={financial_data.get('roe_ttm', 0):.2f}%, 毛利率={financial_data.get('gross_margin_ttm', 0):.2f}%")
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
        logger.info(f"  跳过: {skip_count} 只（fact_fundamental表中无数据）")
        logger.info("=" * 60)
        
    finally:
        session.close()


if __name__ == '__main__':
    try:
        fill_s1_stocks_fundamental()
    except KeyboardInterrupt:
        logger.info("\n⚠️ 用户中断")
    except Exception as e:
        logger.error(f"❌ 补充失败: {e}", exc_info=True)
        sys.exit(1)

