"""
为S1股票池补充毛利率数据（简化版）
从AkShare的stock_financial_abstract_ths接口获取利润表数据，计算毛利率
"""

import sys
import logging
from pathlib import Path
from datetime import date
from typing import Optional

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.services.data.postgres_warehouse import PostgresWarehouse
from data_warehouse.models import FactDailyFundamental
from sqlalchemy import text
import time
import signal

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 设置超时
TIMEOUT = 5  # 每个请求5秒超时


class TimeoutError(Exception):
    pass


def timeout_handler(signum, frame):
    raise TimeoutError("请求超时")


def get_gross_margin_from_abstract(code: str) -> Optional[float]:
    """从stock_financial_abstract_ths获取毛利率（通过利润表计算）"""
    try:
        import akshare as ak
        import pandas as pd
        
        # 设置超时
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(TIMEOUT)
        
        try:
            # 获取财务摘要数据
            df = ak.stock_financial_abstract_ths(symbol=code)
            
            if df is None or df.empty:
                return None
            
            # 查找最新一期的营业收入和营业成本
            latest = df.iloc[0]
            revenue = None
            cost = None
            
            # 查找字段（尝试多种可能的字段名）
            for col in df.columns:
                col_str = str(col)
                if revenue is None:
                    if '营业收入' in col_str or '营业总收入' in col_str:
                        val = latest[col]
                        if pd.notna(val):
                            try:
                                revenue = float(val)
                            except:
                                pass
                if cost is None:
                    if '营业成本' in col_str or '营业总成本' in col_str:
                        val = latest[col]
                        if pd.notna(val):
                            try:
                                cost = float(val)
                            except:
                                pass
            
            signal.alarm(0)  # 取消超时
            
            # 计算毛利率
            if revenue and revenue > 0 and cost is not None:
                gross_margin = ((revenue - cost) / revenue) * 100
                return gross_margin
            
            return None
            
        except TimeoutError:
            signal.alarm(0)
            logger.debug(f"获取 {code} 毛利率超时")
            return None
        except Exception as e:
            signal.alarm(0)
            logger.debug(f"获取 {code} 毛利率失败: {e}")
            return None
            
    except Exception as e:
        logger.debug(f"从abstract获取 {code} 毛利率失败: {e}")
        return None


def fill_s1_gross_margin_simple():
    """为S1股票池补充毛利率数据（简化版）"""
    logger.info("=" * 60)
    logger.info("为S1股票池补充毛利率数据（简化版）")
    logger.info("=" * 60)
    
    warehouse = PostgresWarehouse()
    if not warehouse.warehouse_service:
        logger.error("❌ 数据仓库未初始化")
        return
    
    # 获取S1股票代码
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
        s1_codes = []
        for row in results:
            code = row[0]
            if code.startswith('6'):
                s1_codes.append(f"{code}.SH")
            elif code.startswith(('0', '3')):
                s1_codes.append(f"{code}.SZ")
        
        logger.info(f"📊 找到 {len(s1_codes)} 只S1股票")
        
        # 获取最新交易日期
        query2 = text("SELECT MAX(trade_date) FROM fact_daily_price_qfq")
        latest_date = session.execute(query2).scalar()
        if not latest_date:
            logger.error("❌ 无法获取最新交易日期")
            return
        
        logger.info(f"📅 目标交易日期: {latest_date}")
        logger.info("")
        
        success_count = 0
        failed_count = 0
        
        for idx, ts_code in enumerate(s1_codes, 1):
            try:
                # 转换代码格式
                if '.SH' in ts_code:
                    code = ts_code.replace('.SH', '')
                elif '.SZ' in ts_code:
                    code = ts_code.replace('.SZ', '')
                else:
                    code = ts_code
                
                # 获取毛利率
                gross_margin = get_gross_margin_from_abstract(code)
                
                if gross_margin and gross_margin > 0:
                    # 更新数据库
                    existing = session.query(FactDailyFundamental).filter(
                        FactDailyFundamental.ts_code == ts_code,
                        FactDailyFundamental.trade_date == latest_date
                    ).first()
                    
                    if existing:
                        existing.gross_margin_ttm = gross_margin
                    else:
                        new_record = FactDailyFundamental(
                            ts_code=ts_code,
                            trade_date=latest_date,
                            gross_margin_ttm=gross_margin,
                            source='akshare_abstract'
                        )
                        session.add(new_record)
                    
                    session.commit()
                    success_count += 1
                    
                    if idx % 20 == 0 or idx <= 5:
                        logger.info(f"  进度: {idx}/{len(s1_codes)} - {ts_code}: 毛利率={gross_margin:.2f}%")
                else:
                    failed_count += 1
                
                # 延迟
                if idx % 10 == 0:
                    time.sleep(1)
                else:
                    time.sleep(0.3)
                    
            except Exception as e:
                logger.error(f"  ❌ 处理 {ts_code} 失败: {e}")
                failed_count += 1
                session.rollback()
                continue
        
        logger.info("")
        logger.info("=" * 60)
        logger.info(f"✅ 补充完成")
        logger.info(f"  成功: {success_count} 只")
        logger.info(f"  失败: {failed_count} 只")
        logger.info("=" * 60)
        
    finally:
        session.close()


if __name__ == '__main__':
    try:
        fill_s1_gross_margin_simple()
    except KeyboardInterrupt:
        logger.info("\n⚠️ 用户中断")
    except Exception as e:
        logger.error(f"❌ 补充失败: {e}", exc_info=True)
        sys.exit(1)

