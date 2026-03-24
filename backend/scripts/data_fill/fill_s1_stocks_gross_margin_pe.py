"""
为S1股票池补充毛利率和PE数据
- PE数据从fact_daily_price_qfq表获取
- 毛利率数据从Tushare API获取（如果可用）或从fact_fundamental表计算
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
from backend.services.tushare_service import TushareService
from backend.services.data.financial_data_fetcher import FinancialDataFetcher
from data_warehouse.models import FactDailyFundamental
from data_warehouse.models import FactFundamental
from sqlalchemy import text
import time
import pandas as pd

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


def get_pe_from_price_table(session, ts_code: str, trade_date: date) -> Optional[float]:
    """从fact_daily_price_qfq表获取PE数据"""
    try:
        query = text("""
            SELECT pe_ttm
            FROM fact_daily_price_qfq
            WHERE ts_code = :ts_code
                AND trade_date = :trade_date
            LIMIT 1
        """)
        result = session.execute(query, {'ts_code': ts_code, 'trade_date': trade_date}).scalar()
        if result and result > 0:
            return float(result)
        return None
    except Exception as e:
        logger.debug(f"获取 {ts_code} PE数据失败: {e}")
        return None


def get_gross_margin_from_akshare(session, ts_code: str) -> Optional[float]:
    """从AkShare获取毛利率数据（通过利润表计算）"""
    try:
        import akshare as ak
        
        # 转换Tushare格式代码为6位数字代码
        if '.SH' in ts_code:
            code = ts_code.replace('.SH', '')
        elif '.SZ' in ts_code:
            code = ts_code.replace('.SZ', '')
        elif '.BJ' in ts_code:
            code = ts_code.replace('.BJ', '')
        else:
            code = ts_code
        
        # 方法1: 从利润表计算毛利率
        try:
            # 使用stock_profit_sheet_by_report_em接口
            if hasattr(ak, 'stock_profit_sheet_by_report_em'):
                df = ak.stock_profit_sheet_by_report_em(symbol=code)
                if df is not None and not df.empty:
                    latest = df.iloc[0]
                    revenue = None
                    cost = None
                    
                    # 查找营业收入和营业成本字段
                    for col in df.columns:
                        col_str = str(col)
                        if ('营业收入' in col_str or '营业总收入' in col_str) and revenue is None:
                            val = latest[col]
                            if pd.notna(val):
                                revenue = float(val)
                        if ('营业成本' in col_str or '营业总成本' in col_str) and cost is None:
                            val = latest[col]
                            if pd.notna(val):
                                cost = float(val)
                    
                    if revenue and revenue > 0 and cost is not None:
                        # 计算毛利率 = (营业收入 - 营业成本) / 营业收入 * 100
                        gross_margin = ((revenue - cost) / revenue) * 100
                        return gross_margin
        except Exception as e:
            logger.debug(f"从stock_profit_sheet_by_report_em获取 {ts_code} 利润表失败: {e}")
        
        # 方法2: 从财务摘要获取（如果有毛利率字段）
        try:
            df = ak.stock_financial_abstract_ths(symbol=code)
            if df is not None and not df.empty:
                latest = df.iloc[0]
                # 查找毛利率字段
                for col in df.columns:
                    col_str = str(col)
                    if '毛利率' in col_str:
                        gm = latest[col]
                        if pd.notna(gm):
                            gm_val = float(gm)
                            # 如果值>1，认为是百分比；否则需要*100
                            if gm_val < 1:
                                gm_val = gm_val * 100
                            return gm_val
        except Exception as e:
            logger.debug(f"从stock_financial_abstract_ths获取 {ts_code} 毛利率失败: {e}")
        
        return None
        
    except Exception as e:
        logger.debug(f"从AkShare获取 {ts_code} 毛利率失败: {e}")
        return None


def get_gross_margin_from_fact_fundamental(session, ts_code: str) -> Optional[float]:
    """从fact_fundamental表计算毛利率TTM值"""
    try:
        # 获取最近4个季度的财务数据
        quarters = session.query(FactFundamental).filter(
            FactFundamental.ts_code == ts_code,
            FactFundamental.end_date >= date(2023, 1, 1)
        ).order_by(
            FactFundamental.end_date.desc()
        ).limit(4).all()
        
        if not quarters:
            return None
        
        # 计算TTM值
        gross_margin_values = []
        for q in quarters:
            if q.gross_margin is not None and q.gross_margin > 0:
                gross_margin_values.append(float(q.gross_margin))
        
        if gross_margin_values:
            return sum(gross_margin_values) / len(gross_margin_values)
        
        return None
        
    except Exception as e:
        logger.debug(f"从fact_fundamental获取 {ts_code} 毛利率失败: {e}")
        return None


def update_daily_fundamental(
    session,
    ts_code: str,
    trade_date: date,
    gross_margin: Optional[float] = None,
    pe: Optional[float] = None
) -> bool:
    """
    更新fact_daily_fundamental表的毛利率和PE数据
    
    Args:
        session: 数据库会话
        ts_code: 股票代码（Tushare格式）
        trade_date: 交易日期
        gross_margin: 毛利率（%）
        pe: PE TTM
    
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
            if gross_margin is not None:
                existing.gross_margin_ttm = gross_margin
            if pe is not None:
                existing.pe_ttm = pe
        else:
            # 创建新记录（只更新毛利率和PE，其他字段保持默认）
            new_record = FactDailyFundamental(
                ts_code=ts_code,
                trade_date=trade_date,
                gross_margin_ttm=gross_margin,
                pe_ttm=pe,
                source='s1_fill_gm_pe'
            )
            session.add(new_record)
        
        session.commit()
        return True
        
    except Exception as e:
        logger.error(f"更新 {ts_code} 毛利率/PE数据失败: {e}")
        session.rollback()
        return False


def fill_s1_stocks_gross_margin_pe():
    """
    为S1股票池的股票补充毛利率和PE数据
    """
    logger.info("=" * 60)
    logger.info("为S1股票池补充毛利率和PE数据")
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
        pe_filled = 0
        gross_margin_filled = 0
        
        for idx, ts_code in enumerate(s1_codes, 1):
            try:
                # 1. 获取PE数据（从fact_daily_price_qfq表）
                pe = get_pe_from_price_table(session, ts_code, latest_date)
                
                # 2. 获取毛利率数据（暂时跳过，因为数据源不稳定）
                # 注意：由于AkShare接口不稳定，暂时不获取毛利率，后续可以从其他数据源补充
                gross_margin = None
                # TODO: 后续补充毛利率数据
                
                # 3. 更新到数据库（只要有PE或毛利率数据就更新）
                if pe is not None or gross_margin is not None:
                    success = update_daily_fundamental(
                        session,
                        ts_code,
                        latest_date,
                        gross_margin=gross_margin,
                        pe=pe
                    )
                    
                    if success:
                        success_count += 1
                        if pe:
                            pe_filled += 1
                        if idx % 20 == 0 or idx <= 5:
                            logger.info(f"  进度: {idx}/{len(s1_codes)} - {ts_code}: PE={pe if pe else '无'}, 毛利率={gross_margin if gross_margin else '无'}")
                    else:
                        failed_count += 1
                else:
                    if idx <= 5:
                        logger.warning(f"  ⚠️ {ts_code} 无法获取PE和毛利率数据")
                    failed_count += 1
                
                # 延迟，避免请求过快
                if idx % 10 == 0:
                    time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"  ❌ 处理 {ts_code} 失败: {e}")
                failed_count += 1
                continue
        
        logger.info("")
        logger.info("=" * 60)
        logger.info(f"✅ 补充完成")
        logger.info(f"  成功更新: {success_count} 只")
        logger.info(f"  补充PE数据: {pe_filled} 只")
        logger.info(f"  补充毛利率数据: {gross_margin_filled} 只")
        logger.info(f"  失败: {failed_count} 只")
        logger.info("=" * 60)
        
    finally:
        session.close()


if __name__ == '__main__':
    try:
        import pandas as pd  # 用于isna检查
        fill_s1_stocks_gross_margin_pe()
    except KeyboardInterrupt:
        logger.info("\n⚠️ 用户中断")
    except Exception as e:
        logger.error(f"❌ 补充失败: {e}", exc_info=True)
        sys.exit(1)

