"""
计算并更新5日均量（avg_volume_5）
在ETL过程中，为每只股票计算最近5个交易日的平均成交量
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import logging
from datetime import date, timedelta
from sqlalchemy import func, and_
from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models import FactDailyPrice
from data_warehouse.models import DimStock

logger = logging.getLogger(__name__)


def calculate_avg_volume_5(target_date: str = None, batch_size: int = 100):
    """
    计算并更新5日均量
    
    Args:
        target_date: 目标日期（YYYY-MM-DD），如果为None则计算所有日期
        batch_size: 批处理大小
    """
    warehouse_service = WarehouseService()
    session = warehouse_service.get_session()
    
    try:
        if target_date:
            # 计算指定日期
            trade_date = date.fromisoformat(target_date)
            logger.info(f"📊 开始计算 {target_date} 的5日均量")
            
            # 获取该日期的所有股票
            stocks = session.query(FactDailyPrice.ts_code).filter(
                FactDailyPrice.trade_date == trade_date
            ).distinct().all()
            
            stock_codes = [s[0] for s in stocks]
            logger.info(f"找到 {len(stock_codes)} 只股票需要计算5日均量")
            
            _calculate_for_stocks(session, stock_codes, trade_date, batch_size)
        else:
            # 计算所有日期
            logger.info("📊 开始计算所有日期的5日均量")
            
            # 获取所有有数据的日期
            dates = session.query(FactDailyPrice.trade_date).distinct().order_by(
                FactDailyPrice.trade_date.desc()
            ).all()
            
            date_list = [d[0] for d in dates]
            logger.info(f"找到 {len(date_list)} 个交易日需要计算")
            
            for trade_date in date_list:
                logger.info(f"处理日期: {trade_date}")
                
                # 获取该日期的所有股票
                stocks = session.query(FactDailyPrice.ts_code).filter(
                    FactDailyPrice.trade_date == trade_date
                ).distinct().all()
                
                stock_codes = [s[0] for s in stocks]
                _calculate_for_stocks(session, stock_codes, trade_date, batch_size)
        
        session.commit()
        logger.info("✅ 5日均量计算完成")
        
    except Exception as e:
        session.rollback()
        logger.error(f"❌ 计算5日均量失败: {e}", exc_info=True)
        raise
    finally:
        session.close()


def _calculate_for_stocks(session, stock_codes: list, trade_date: date, batch_size: int):
    """为一批股票计算5日均量"""
    updated_count = 0
    
    for i in range(0, len(stock_codes), batch_size):
        batch = stock_codes[i:i + batch_size]
        
        for ts_code in batch:
            try:
                # 获取最近5个交易日的数据（包括当天）
                # 按日期倒序排列，取前5条
                recent_data = session.query(FactDailyPrice).filter(
                    and_(
                        FactDailyPrice.ts_code == ts_code,
                        FactDailyPrice.trade_date <= trade_date,
                        FactDailyPrice.vol.isnot(None)
                    )
                ).order_by(
                    FactDailyPrice.trade_date.desc()
                ).limit(5).all()
                
                if len(recent_data) < 5:
                    # 如果数据不足5天，跳过
                    continue
                
                # 计算5日均量
                volumes = [float(r.vol) for r in recent_data if r.vol]
                if len(volumes) >= 5:
                    avg_volume_5 = sum(volumes) / len(volumes)
                    
                    # 更新当天的记录
                    today_record = session.query(FactDailyPrice).filter(
                        and_(
                            FactDailyPrice.ts_code == ts_code,
                            FactDailyPrice.trade_date == trade_date
                        )
                    ).first()
                    
                    if today_record:
                        today_record.avg_volume_5 = avg_volume_5
                        updated_count += 1
                        
                        if updated_count % 100 == 0:
                            session.commit()
                            logger.info(f"已更新 {updated_count} 只股票的5日均量")
            
            except Exception as e:
                logger.warning(f"计算股票 {ts_code} 的5日均量失败: {e}")
                continue
        
        session.commit()
    
    logger.info(f"✅ 完成批次更新，共更新 {updated_count} 只股票")


if __name__ == '__main__':
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    target_date = sys.argv[1] if len(sys.argv) > 1 else None
    calculate_avg_volume_5(target_date)

